"""
Core components of Home Assistant.

Home Assistant is a Home Automation framework for observing the state
of entities and react to changes.

Copyright (c) 2022, Andreas Nixdorf

This program is free software: you can redistribute it and/or
modify it under the terms of the GNU General Public License as
published by the Free Software Foundation, either version 3 of
the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
General Public License for more details.

You should have received a copy of the GNU General Public
License along with this program.  If not, see
http://www.gnu.org/licenses/.
"""
from __future__ import annotations

import asyncio
from collections.abc import (
    Awaitable,
    Callable,
    Collection,
    Coroutine,
    Iterable,
    Mapping,
)
import abc
import datetime
import enum
import functools
import logging
import os
import pathlib
import re
import threading
import time
import typing
import urllib.parse as url_parse


from . import block_async_io, loader, util
from .backports.enum import StrEnum
from . import Const, CoreState, callback, ConfigSource, EventBus, HassJob, HassJobType, ServiceRegistry, StateMachine

from .util import dt as dt_util, location, ulid as ulid_util
from .util.async_ import (
    fire_coroutine_threadsafe,
    run_callback_threadsafe,
    shutdown_run_callback_threadsafe,
)
from .util.read_only_dict import ReadOnlyDict
from .util.timeout import TimeoutManager
from .util.unit_system import IMPERIAL_SYSTEM, METRIC_SYSTEM, UnitSystem

# Typing imports that create a circular dependency
if typing.TYPE_CHECKING:
    from .auth import AuthManager
    from .components.http import ApiConfig, HomeAssistantHTTP
    from .config_entries import ConfigEntries


_STAGE_1_SHUTDOWN_TIMEOUT = 100
_STAGE_2_SHUTDOWN_TIMEOUT = 60
_STAGE_3_SHUTDOWN_TIMEOUT = 30

block_async_io.enable()

_T = typing.TypeVar("_T")
_R = typing.TypeVar("_R")
# Internal; not helpers.typing.UNDEFINED due to circular dependency
#_UNDEF: dict[typing.Any, typing.Any] = {}

_CORE_STORAGE_KEY = "core.config"
_CORE_STORAGE_VERSION = 1

_DOMAIN = "homeassistant"

# How long to wait to log tasks that are blocking
_BLOCK_LOG_TIMEOUT = 60

# How long we wait for the result of a service call
_SERVICE_CALL_LIMIT = 10  # seconds


# SOURCE_* are deprecated as of Home Assistant 2022.2, use ConfigSource instead
_SOURCE_DISCOVERED = ConfigSource.DISCOVERED.value
_SOURCE_STORAGE = ConfigSource.STORAGE.value
_SOURCE_YAML = ConfigSource.YAML.value

# How long to wait until things that run on startup have to finish.
_TIMEOUT_EVENT_START = 15


_LOGGER = logging.getLogger(__name__)


class HomeAssistant(abc.ABC):
    """Root object of the Home Assistant home automation."""

    auth: AuthManager
    http: HomeAssistantHTTP = None  # type: ignore[assignment]
    config_entries: ConfigEntries = None  # type: ignore[assignment]

    def __init__(self) -> None:
        """Initialize new Home Assistant object."""
        self.loop = asyncio.get_running_loop()
        self._pending_tasks: list[asyncio.Future[typing.Any]] = []
        self._track_task = True
        self.bus = EventBus(self)
        self.services = ServiceRegistry(self)
        self.states = StateMachine(self.bus, self.loop)
        self.config = Config(self)
        self.components = loader.Components(self)
        self.helpers = loader.Helpers(self)
        # This is a dictionary that any component can store any data on.
        self.data: dict[str, typing.Any] = {}
        self.state: CoreState = CoreState.not_running
        self.exit_code: int = 0
        # If not None, use to signal end-of-loop
        self._stopped: asyncio.Event | None = None
        # Timeout handler for Core/Helper namespace
        self.timeout: TimeoutManager = TimeoutManager()

    @property
    def is_running(self) -> bool:
        """Return if Home Assistant is running."""
        return self.state in (CoreState.starting, CoreState.running)

    @property
    def is_stopping(self) -> bool:
        """Return if Home Assistant is stopping."""
        return self.state in (CoreState.stopping, CoreState.final_write)

    def start(self) -> int:
        """Start Home Assistant.

        Note: This function is only used for testing.
        For regular use, use "await hass.run()".
        """
        # Register the async start
        fire_coroutine_threadsafe(self.async_start(), self.loop)

        # Run forever
        # Block until stopped
        _LOGGER.info("Starting Home Assistant core loop")
        self.loop.run_forever()
        return self.exit_code

    async def async_run(self, *, attach_signals: bool = True) -> int:
        """Home Assistant main entry point.

        Start Home Assistant and block until stopped.

        This method is a coroutine.
        """
        if self.state != CoreState.not_running:
            raise RuntimeError("Home Assistant is already running")

        # _async_stop will set this instead of stopping the loop
        self._stopped = asyncio.Event()

        await self.async_start()
        if attach_signals:
            # pylint: disable=import-outside-toplevel
            from .helpers.signal import async_register_signal_handling

            async_register_signal_handling(self)

        await self._stopped.wait()
        return self.exit_code

    async def async_start(self) -> None:
        """Finalize startup from inside the event loop.

        This method is a coroutine.
        """
        _LOGGER.info("Starting Home Assistant")
        setattr(self.loop, "_thread_ident", threading.get_ident())

        self.state = CoreState.starting
        self.bus.async_fire(Const.EVENT_CORE_CONFIG_UPDATE)
        self.bus.async_fire(Const.EVENT_HOMEASSISTANT_START)

        try:
            # Only block for EVENT_HOMEASSISTANT_START listener
            self.async_stop_track_tasks()
            async with self.timeout.async_timeout(Const.TIMEOUT_EVENT_START):
                await self.async_block_till_done()
        except asyncio.TimeoutError:
            _LOGGER.warning(
                "Something is blocking Home Assistant from wrapping up the "
                "start up phase. We're going to continue anyway. Please "
                "report the following info at https://github.com/home-assistant/core/issues: %s",
                ", ".join(self.config.components),
            )

        # Allow automations to set up the start triggers before changing state
        await asyncio.sleep(0)

        if self.state != CoreState.starting:
            _LOGGER.warning(
                "Home Assistant startup has been interrupted. "
                "Its state may be inconsistent"
            )
            return

        self.state = CoreState.running
        self.bus.async_fire(Const.EVENT_CORE_CONFIG_UPDATE)
        self.bus.async_fire(Const.EVENT_HOMEASSISTANT_STARTED)

    def add_job(
        self, target: Callable[..., typing.Any] | Coroutine[typing.Any, typing.Any, typing.Any], *args: typing.Any
    ) -> None:
        """Add a job to be executed by the event loop or by an executor.

        If the job is either a coroutine or decorated with @callback, it will be
        run by the event loop, if not it will be run by an executor.

        target: target to call.
        args: parameters for method to call.
        """
        if target is None:
            raise ValueError("Don't call add_job with None")
        self.loop.call_soon_threadsafe(self.async_add_job, target, *args)

    @abc.abstractmethod
    @callback
    def async_add_job(
        self, target: Callable[..., Coroutine[typing.Any, typing.Any, _R]], *args: typing.Any
    ) -> asyncio.Future[_R] | None:
        ...

    @abc.abstractmethod
    @callback
    def async_add_job(
        self, target: Callable[..., Coroutine[typing.Any, typing.Any, _R] | _R], *args: typing.Any
    ) -> asyncio.Future[_R] | None:
        ...

    @abc.abstractmethod
    @callback
    def async_add_job(
        self, target: Coroutine[typing.Any, typing.Any, _R], *args: typing.Any
    ) -> asyncio.Future[_R] | None:
        ...

    @callback
    def async_add_job(
        self,
        target: Callable[..., Coroutine[typing.Any, typing.Any, _R] | _R] | Coroutine[typing.Any, typing.Any, _R],
        *args: typing.Any,
    ) -> asyncio.Future[_R] | None:
        """Add a job to be executed by the event loop or by an executor.

        If the job is either a coroutine or decorated with @callback, it will be
        run by the event loop, if not it will be run by an executor.

        This method must be run in the event loop.

        target: target to call.
        args: parameters for method to call.
        """
        if target is None:
            raise ValueError("Don't call async_add_job with None")

        if asyncio.iscoroutine(target):
            return self.async_create_task(target)

        # This code path is performance sensitive and uses
        # if TYPE_CHECKING to avoid the overhead of constructing
        # the type used for the cast. For history see:
        # https://github.com/home-assistant/core/pull/71960
        if typing.TYPE_CHECKING:
            target = typing.cast(Callable[..., typing.Union[Coroutine[typing.Any, typing.Any, _R], _R]], target)
        return self.async_add_hass_job(HassJob(target), *args)

    @abc.abstractmethod
    @callback
    def async_add_hass_job(
        self, hassjob: HassJob[Coroutine[typing.Any, typing.Any, _R]], *args: typing.Any
    ) -> asyncio.Future[_R] | None:
        ...

    @abc.abstractmethod
    @callback
    def async_add_hass_job(
        self, hassjob: HassJob[Coroutine[typing.Any, typing.Any, _R] | _R], *args: typing.Any
    ) -> asyncio.Future[_R] | None:
        ...

    @callback
    def async_add_hass_job(
        self, hassjob: HassJob[Coroutine[typing.Any, typing.Any, _R] | _R], *args: typing.Any
    ) -> asyncio.Future[_R] | None:
        """Add a HassJob from within the event loop.

        This method must be run in the event loop.
        hassjob: HassJob to call.
        args: parameters for method to call.
        """
        task: asyncio.Future[_R]
        # This code path is performance sensitive and uses
        # if TYPE_CHECKING to avoid the overhead of constructing
        # the type used for the cast. For history see:
        # https://github.com/home-assistant/core/pull/71960
        if hassjob.job_type == HassJobType.Coroutinefunction:
            if typing.TYPE_CHECKING:
                hassjob.target = typing.cast(
                    Callable[..., Coroutine[typing.Any, typing.Any, _R]], hassjob.target
                )
            task = self.loop.create_task(hassjob.target(*args))
        elif hassjob.job_type == HassJobType.Callback:
            if typing.TYPE_CHECKING:
                hassjob.target = typing.cast(Callable[..., _R], hassjob.target)
            self.loop.call_soon(hassjob.target, *args)
            return None
        else:
            if typing.TYPE_CHECKING:
                hassjob.target = typing.cast(Callable[..., _R], hassjob.target)
            task = self.loop.run_in_executor(None, hassjob.target, *args)

        # If a task is scheduled
        if self._track_task:
            self._pending_tasks.append(task)

        return task

    def create_task(self, target: Coroutine[typing.Any, typing.Any, typing.Any]) -> None:
        """Add task to the executor pool.

        target: target to call.
        """
        self.loop.call_soon_threadsafe(self.async_create_task, target)

    @callback
    def async_create_task(self, target: Coroutine[typing.Any, typing.Any, _R]) -> asyncio.Task[_R]:
        """Create a task from within the eventloop.

        This method must be run in the event loop.

        target: target to call.
        """
        task = self.loop.create_task(target)

        if self._track_task:
            self._pending_tasks.append(task)

        return task

    @callback
    def async_add_executor_job(
        self, target: Callable[..., _T], *args: typing.Any
    ) -> asyncio.Future[_T]:
        """Add an executor job from within the event loop."""
        task = self.loop.run_in_executor(None, target, *args)

        # If a task is scheduled
        if self._track_task:
            self._pending_tasks.append(task)

        return task

    @callback
    def async_track_tasks(self) -> None:
        """Track tasks so you can wait for all tasks to be done."""
        self._track_task = True

    @callback
    def async_stop_track_tasks(self) -> None:
        """Stop track tasks so you can't wait for all tasks to be done."""
        self._track_task = False

    @abc.abstractmethod
    @callback
    def async_run_hass_job(
        self, hassjob: HassJob[Coroutine[typing.Any, typing.Any, _R]], *args: typing.Any
    ) -> asyncio.Future[_R] | None:
        ...

    @abc.abstractmethod
    @callback
    def async_run_hass_job(
        self, hassjob: HassJob[Coroutine[typing.Any, typing.Any, _R] | _R], *args: typing.Any
    ) -> asyncio.Future[_R] | None:
        ...

    @callback
    def async_run_hass_job(
        self, hassjob: HassJob[Coroutine[typing.Any, typing.Any, _R] | _R], *args: typing.Any
    ) -> asyncio.Future[_R] | None:
        """Run a HassJob from within the event loop.

        This method must be run in the event loop.

        hassjob: HassJob
        args: parameters for method to call.
        """
        # This code path is performance sensitive and uses
        # if TYPE_CHECKING to avoid the overhead of constructing
        # the type used for the cast. For history see:
        # https://github.com/home-assistant/core/pull/71960
        if hassjob.job_type == HassJobType.Callback:
            if typing.TYPE_CHECKING:
                hassjob.target = typing.cast(Callable[..., _R], hassjob.target)
            hassjob.target(*args)
            return None

        return self.async_add_hass_job(hassjob, *args)

    @abc.abstractmethod
    @callback
    def async_run_job(
        self, target: Callable[..., Coroutine[typing.Any, typing.Any, _R]], *args: typing.Any
    ) -> asyncio.Future[_R] | None:
        ...

    @abc.abstractmethod
    @callback
    def async_run_job(
        self, target: Callable[..., Coroutine[typing.Any, typing.Any, _R] | _R], *args: typing.Any
    ) -> asyncio.Future[_R] | None:
        ...

    @abc.abstractmethod
    @callback
    def async_run_job(
        self, target: Coroutine[typing.Any, typing.Any, _R], *args: typing.Any
    ) -> asyncio.Future[_R] | None:
        ...

    @callback
    def async_run_job(
        self,
        target: Callable[..., Coroutine[typing.Any, typing.Any, _R] | _R] | Coroutine[typing.Any, typing.Any, _R],
        *args: typing.Any,
    ) -> asyncio.Future[_R] | None:
        """Run a job from within the event loop.

        This method must be run in the event loop.

        target: target to call.
        args: parameters for method to call.
        """
        if asyncio.iscoroutine(target):
            return self.async_create_task(target)

        # This code path is performance sensitive and uses
        # if TYPE_CHECKING to avoid the overhead of constructing
        # the type used for the cast. For history see:
        # https://github.com/home-assistant/core/pull/71960
        if typing.TYPE_CHECKING:
            target = typing.cast(Callable[..., typing.Union[Coroutine[typing.Any, typing.Any, _R], _R]], target)
        return self.async_run_hass_job(HassJob(target), *args)

    def block_till_done(self) -> None:
        """Block until all pending work is done."""
        asyncio.run_coroutine_threadsafe(
            self.async_block_till_done(), self.loop
        ).result()

    async def async_block_till_done(self) -> None:
        """Block until all pending work is done."""
        # To flush out any call_soon_threadsafe
        await asyncio.sleep(0)
        start_time: float | None = None

        while self._pending_tasks:
            pending = [task for task in self._pending_tasks if not task.done()]
            self._pending_tasks.clear()
            if pending:
                await self._await_and_log_pending(pending)

                if start_time is None:
                    # Avoid calling monotonic() until we know
                    # we may need to start logging blocked tasks.
                    start_time = 0
                elif start_time == 0:
                    # If we have waited twice then we set the start
                    # time
                    start_time = time.monotonic()
                elif time.monotonic() - start_time > _BLOCK_LOG_TIMEOUT:
                    # We have waited at least three loops and new tasks
                    # continue to block. At this point we start
                    # logging all waiting tasks.
                    for task in pending:
                        _LOGGER.debug("Waiting for task: %s", task)
            else:
                await asyncio.sleep(0)

    async def _await_and_log_pending(self, pending: Iterable[Awaitable[typing.Any]]) -> None:
        """Await and log tasks that take a long time."""
        wait_time = 0
        while pending:
            _, pending = await asyncio.wait(pending, timeout=_BLOCK_LOG_TIMEOUT)
            if not pending:
                return
            wait_time += _BLOCK_LOG_TIMEOUT
            for task in pending:
                _LOGGER.debug("Waited %s seconds for task: %s", wait_time, task)

    def stop(self) -> None:
        """Stop Home Assistant and shuts down all threads."""
        if self.state == CoreState.not_running:  # just ignore
            return
        fire_coroutine_threadsafe(self.async_stop(), self.loop)

    async def async_stop(self, exit_code: int = 0, *, force: bool = False) -> None:
        """Stop Home Assistant and shuts down all threads.

        The "force" flag commands async_stop to proceed regardless of
        Home Assistant's current state. You should not set this flag
        unless you're testing.

        This method is a coroutine.
        """
        if not force:
            # Some tests require async_stop to run,
            # regardless of the state of the loop.
            if self.state == CoreState.not_running:  # just ignore
                return
            if self.state in [CoreState.stopping, CoreState.final_write]:
                _LOGGER.info("Additional call to async_stop was ignored")
                return
            if self.state == CoreState.starting:
                # This may not work
                _LOGGER.warning(
                    "Stopping Home Assistant before startup has completed may fail"
                )

        # stage 1
        self.state = CoreState.stopping
        self.async_track_tasks()
        self.bus.async_fire(Const.EVENT_HOMEASSISTANT_STOP)
        try:
            async with self.timeout.async_timeout(Const.STAGE_1_SHUTDOWN_TIMEOUT):
                await self.async_block_till_done()
        except asyncio.TimeoutError:
            _LOGGER.warning(
                "Timed out waiting for shutdown stage 1 to complete, the shutdown will continue"
            )

        # stage 2
        self.state = CoreState.final_write
        self.bus.async_fire(Const.EVENT_HOMEASSISTANT_FINAL_WRITE)
        try:
            async with self.timeout.async_timeout(Const.STAGE_2_SHUTDOWN_TIMEOUT):
                await self.async_block_till_done()
        except asyncio.TimeoutError:
            _LOGGER.warning(
                "Timed out waiting for shutdown stage 2 to complete, the shutdown will continue"
            )

        # stage 3
        self.state = CoreState.not_running
        self.bus.async_fire(Const.EVENT_HOMEASSISTANT_CLOSE)

        # Prevent run_callback_threadsafe from scheduling any additional
        # callbacks in the event loop as callbacks created on the futures
        # it returns will never run after the final `self.async_block_till_done`
        # which will cause the futures to block forever when waiting for
        # the `result()` which will cause a deadlock when shutting down the executor.
        shutdown_run_callback_threadsafe(self.loop)

        try:
            async with self.timeout.async_timeout(Const.STAGE_3_SHUTDOWN_TIMEOUT):
                await self.async_block_till_done()
        except asyncio.TimeoutError:
            _LOGGER.warning(
                "Timed out waiting for shutdown stage 3 to complete, the shutdown will continue"
            )

        self.exit_code = exit_code
        self.state = CoreState.stopped

        if self._stopped is not None:
            self._stopped.set()
