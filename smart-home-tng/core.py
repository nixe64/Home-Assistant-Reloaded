"""
Core components of Smart Home - The Next Generation.

Smart Home - TNG is a Home Automation framework for observing the state
of entities and react to changes. It is based on Home Assistant from
home-assistant.io and the Home Assistant Community.

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

import abc
import awesomeversion as asv
import asyncio
import certifi
import collections
import collections.abc
import contextvars
import datetime
import enum
import functools
import importlib
import ipaddress
import json
import logging
import numbers
import os
import pathlib
import re
import shutil
import ssl
import sys
import tempfile
import threading
import time
import typing

import aiohttp.hdrs
import aiohttp.typedefs
import aiohttp.web
import aiohttp.web_middlewares
import aiohttp.web_urldispatcher
import cryptography.x509
import cryptography.x509.oid
import urllib3.util.url as url
import voluptuous as vol
import voluptuous.humanize as vh
import yarl
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from . import (
    Config,
    ConfigSource,
    ConfigType,
    Const,
    Context,
    CoreState,
    Event,
    EventBus,
    HassJob,
    HassJobType,
    ServiceRegistry,
    StateMachine,
    UnitSystem,
    block_async_io,
    callback,
    exceptions,
    loader,
)
from .helpers import ConfigValidation as cv
from .util import dt, io, location, timeout
from .util import ulid as ulid_util

# Typing imports that create a circular dependency
if typing.TYPE_CHECKING:
    from .auth import AuthManager
    from .config_entries import ConfigEntries


block_async_io.enable()

_T = typing.TypeVar("_T")
_R = typing.TypeVar("_R")
# Internal; not helpers.typing.UNDEFINED due to circular dependency
# _UNDEF: dict[typing.Any, typing.Any] = {}

_CORE_STORAGE_KEY: typing.Final = "core.config"
_CORE_STORAGE_VERSION: typing.Final = 1

_DOMAIN: typing.Final = "homeassistant"

# How long to wait to log tasks that are blocking
_BLOCK_LOG_TIMEOUT: typing.Final = 60

# How long we wait for the result of a service call
_SERVICE_CALL_LIMIT: typing.Final = 10  # seconds


# SOURCE_* are deprecated as of Home Assistant 2022.2, use ConfigSource instead
_SOURCE_DISCOVERED: typing.Final = ConfigSource.DISCOVERED.value
_SOURCE_STORAGE: typing.Final = ConfigSource.STORAGE.value
_SOURCE_YAML: typing.Final = ConfigSource.YAML.value

# How long to wait until things that run on startup have to finish.
_TIMEOUT_EVENT_START: typing.Final = 15

_LOGGER: typing.Final = logging.getLogger(__name__)


class CachingStaticResource(aiohttp.web_urldispatcher.StaticResource):
    """Static Resource handler that will add cache headers."""

    async def _handle(self, request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        rel_url = request.match_info["filename"]
        try:
            filename = pathlib.Path(rel_url)
            if filename.anchor:
                # rel_url is an absolute name like
                # /static/\\machine_name\c$ or /static/D:\path
                # where the static dir is totally different
                raise aiohttp.web.HTTPForbidden()
            filepath = self._directory.joinpath(filename).resolve()
            if not self._follow_symlinks:
                filepath.relative_to(self._directory)
        except (ValueError, FileNotFoundError) as error:
            # relatively safe
            raise aiohttp.web.HTTPNotFound() from error
        except Exception as error:
            # perm error or other kind!
            request.app.logger.exception(error)
            raise aiohttp.web.HTTPNotFound() from error

        # on opening a dir, load its contents if allowed
        if filepath.is_dir():
            return await super()._handle(request)
        if filepath.is_file():
            return aiohttp.web.FileResponse(
                filepath,
                chunk_size=self._chunk_size,
                headers=Const.CACHE_HEADERS,
            )
        raise aiohttp.web.HTTPNotFound


class HomeAssistant(abc.ABC):
    """Root object of the Home Assistant home automation."""

    _DATA_PERSISTENT_ERRORS: typing.Final = "bootstrap_persistent_errors"
    _RE_YAML_ERROR: typing.Final = re.compile(r"homeassistant\.util\.yaml")
    _RE_ASCII: typing.Final = re.compile(r"\033\[[^m]*m")
    _YAML_CONFIG_FILE: typing.Final = "configuration.yaml"
    _VERSION_FILE: typing.Final = ".HA_VERSION"
    _CONFIG_DIR_NAME: typing.Final = ".homeassistant"
    _DATA_CUSTOMIZE: typing.Final = "hass_customize"

    _AUTOMATION_CONFIG_PATH: typing.Final = "automations.yaml"
    _SCRIPT_CONFIG_PATH: typing.Final = "scripts.yaml"
    _SCENE_CONFIG_PATH: typing.Final = "scenes.yaml"
    _SECRET_YAML = "secrets.yaml"

    _LOAD_EXCEPTIONS: typing.Final = (ImportError, FileNotFoundError)
    _INTEGRATION_LOAD_EXCEPTIONS: typing.Final = (
        exceptions.IntegrationNotFound,
        exceptions.RequirementsNotFound,
        *_LOAD_EXCEPTIONS,
    )

    _DEFAULT_CONFIG: typing.Final = f"""
# Loads default set of integrations. Do not remove.
default_config:

# Text to speech
tts:
- platform: google_translate

automation: !include {_AUTOMATION_CONFIG_PATH}
script: !include {_SCRIPT_CONFIG_PATH}
scene: !include {_SCENE_CONFIG_PATH}
"""
    _DEFAULT_SECRETS = """
# Use this file to store secrets like usernames and passwords.
# Learn more at https://www.home-assistant.io/docs/configuration/secrets/
some_password: welcome
"""
    _TTS_PRE_92 = """
tts:
- platform: google
"""
    _TTS_92 = """
tts:
- platform: google_translate
    service_name: google_say
"""
    _PACKAGES_CONFIG_SCHEMA: typing.Final = (
        cv.schema_with_slug_keys(  # Package names are slugs
            vol.Schema({cv.string: vol.Any(dict, list, None)})  # Component config
        )
    )

    _CUSTOMIZE_DICT_SCHEMA: typing.Final = vol.Schema(
        {
            vol.Optional(Const.ATTR_FRIENDLY_NAME): cv.string,
            vol.Optional(Const.ATTR_HIDDEN): cv.boolean,
            vol.Optional(Const.ATTR_ASSUMED_STATE): cv.boolean,
        },
        extra=vol.ALLOW_EXTRA,
    )

    _CUSTOMIZE_CONFIG_SCHEMA: typing.Final = vol.Schema(
        {
            vol.Optional(Const.CONF_CUSTOMIZE, default={}): vol.Schema(
                {cv.entity_id: _CUSTOMIZE_DICT_SCHEMA}
            ),
            vol.Optional(Const.CONF_CUSTOMIZE_DOMAIN, default={}): vol.Schema(
                {cv.string: _CUSTOMIZE_DICT_SCHEMA}
            ),
            vol.Optional(Const.CONF_CUSTOMIZE_GLOB, default={}): vol.Schema(
                {cv.string: _CUSTOMIZE_DICT_SCHEMA}
            ),
        }
    )

    _DictT = typing.TypeVar("_DictT", bound=dict)

    auth: AuthManager
    http: HomeAssistantHTTP | None = None  # type: ignore[assignment]
    config_entries: ConfigEntries | None = None  # type: ignore[assignment]

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
        self.timeout: timeout.TimeoutManager = timeout.TimeoutManager()

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
        io.fire_coroutine_threadsafe(self.async_start(), self.loop)

        # Run forever
        # Block until stopped
        _LOGGER.info("Starting Home Assistant core loop")
        self.loop.run_forever()
        return self.exit_code

    async def async_get_integration(self, domain: str) -> Integration:
        """Get an integration."""
        if (cache := self.data.get(Integration._DATA_INTEGRATIONS)) is None:
            if not self._async_mount_config_dir():
                raise exceptions.IntegrationNotFound(domain)
            cache = self.data[Integration._DATA_INTEGRATIONS] = {}

        int_or_evt: Integration | asyncio.Event | None = cache.get(domain, None)

        if isinstance(int_or_evt, asyncio.Event):
            await int_or_evt.wait()

            if (int_or_evt := cache.get(domain, None)) is None:
                raise exceptions.IntegrationNotFound(domain)

        if int_or_evt is not None:
            return typing.cast(Integration, int_or_evt)

        event = cache[domain] = asyncio.Event()

        try:
            integration = await self._async_get_integration(domain)
        except Exception:
            # Remove event from cache.
            cache.pop(domain)
            event.set()
            raise

        cache[domain] = integration
        event.set()
        return integration

    async def _async_get_integration(self, domain: str) -> Integration:
        if "." in domain:
            raise ValueError(f"Invalid domain {domain}")

        # Instead of using resolve_from_root we use the cache of custom
        # components to find the integration.
        if integration := (await self.async_get_custom_components()).get(domain):
            return integration

        from . import components  # pylint: disable=import-outside-toplevel

        if integration := await self.async_add_executor_job(
            Integration.resolve_from_root, components, domain
        ):
            return integration
        raise exceptions.IntegrationNotFound(domain)

    def _async_mount_config_dir(self) -> bool:
        """Mount config dir in order to load custom_component.

        Async friendly but not a coroutine.
        """
        if self.config.config_dir is None:
            _LOGGER.error("Can't load integrations - configuration directory is not set")
            return False
        if self.config.config_dir not in sys.path:
            sys.path.insert(0, self.config.config_dir)
        return True

    async def _async_component_dependencies(
        self,
        start_domain: str,
        integration: Integration,
        loaded: set[str],
        loading: set[str],
    ) -> set[str]:
        """Recursive function to get component dependencies.

        Async friendly.
        """
        domain = integration.domain
        loading.add(domain)

        for dependency_domain in integration.dependencies:
            # Check not already loaded
            if dependency_domain in loaded:
                continue

            # If we are already loading it, we have a circular dependency.
            if dependency_domain in loading:
                raise exceptions.CircularDependency(domain, dependency_domain)

            loaded.add(dependency_domain)

            dep_integration = await self.async_get_integration(dependency_domain)

            if start_domain in dep_integration.after_dependencies:
                raise exceptions.CircularDependency(start_domain, dependency_domain)

            if dep_integration.dependencies:
                dep_loaded = await self._async_component_dependencies(
                    start_domain, dep_integration, loaded, loading
                )

                loaded.update(dep_loaded)

        loaded.add(domain)
        loading.remove(domain)

        return loaded

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
        self,
        target: typing.Callable[..., typing.Any]
        | asyncio.coroutines.Coroutine[typing.Any, typing.Any, typing.Any],
        *args: typing.Any,
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
        self,
        target: typing.Callable[
            ..., asyncio.coroutines.Coroutine[typing.Any, typing.Any, _R]
        ],
        *args: typing.Any,
    ) -> asyncio.Future[_R] | None:
        ...

    @abc.abstractmethod
    @callback
    def async_add_job(
        self,
        target: typing.Callable[
            ..., asyncio.coroutines.Coroutine[typing.Any, typing.Any, _R] | _R
        ],
        *args: typing.Any,
    ) -> asyncio.Future[_R] | None:
        ...

    @abc.abstractmethod
    @callback
    def async_add_job(
        self,
        target: asyncio.coroutines.Coroutine[typing.Any, typing.Any, _R],
        *args: typing.Any,
    ) -> asyncio.Future[_R] | None:
        ...

    @callback
    def async_add_job(
        self,
        target: typing.Callable[
            ..., asyncio.coroutines.Coroutine[typing.Any, typing.Any, _R] | _R
        ]
        | asyncio.coroutines.Coroutine[typing.Any, typing.Any, _R],
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
            target = typing.cast(
                typing.Callable[
                    ...,
                    typing.Union[
                        asyncio.coroutines.Coroutine[typing.Any, typing.Any, _R], _R
                    ],
                ],
                target,
            )
        return self.async_add_hass_job(HassJob(target), *args)

    @abc.abstractmethod
    @callback
    def async_add_hass_job(
        self,
        hassjob: HassJob[asyncio.coroutines.Coroutine[typing.Any, typing.Any, _R]],
        *args: typing.Any,
    ) -> asyncio.Future[_R] | None:
        ...

    @abc.abstractmethod
    @callback
    def async_add_hass_job(
        self,
        hassjob: HassJob[asyncio.coroutines.Coroutine[typing.Any, typing.Any, _R] | _R],
        *args: typing.Any,
    ) -> asyncio.Future[_R] | None:
        ...

    @callback
    def async_add_hass_job(
        self,
        hassjob: HassJob[asyncio.coroutines.Coroutine[typing.Any, typing.Any, _R] | _R],
        *args: typing.Any,
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
                    typing.Callable[
                        ..., asyncio.coroutines.Coroutine[typing.Any, typing.Any, _R]
                    ],
                    hassjob.target,
                )
            task = self.loop.create_task(hassjob.target(*args))
        elif hassjob.job_type == HassJobType.Callback:
            if typing.TYPE_CHECKING:
                hassjob.target = typing.cast(typing.Callable[..., _R], hassjob.target)
            self.loop.call_soon(hassjob.target, *args)
            return None
        else:
            if typing.TYPE_CHECKING:
                hassjob.target = typing.cast(typing.Callable[..., _R], hassjob.target)
            task = self.loop.run_in_executor(None, hassjob.target, *args)

        # If a task is scheduled
        if self._track_task:
            self._pending_tasks.append(task)

        return task

    def create_task(
        self, target: asyncio.coroutines.Coroutine[typing.Any, typing.Any, typing.Any]
    ) -> None:
        """Add task to the executor pool.

        target: target to call.
        """
        self.loop.call_soon_threadsafe(self.async_create_task, target)

    @callback
    def async_create_task(
        self, target: asyncio.coroutines.Coroutine[typing.Any, typing.Any, _R]
    ) -> asyncio.Task[_R]:
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
        self, target: typing.Callable[..., _T], *args: typing.Any
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
        self,
        hassjob: HassJob[asyncio.coroutines.Coroutine[typing.Any, typing.Any, _R]],
        *args: typing.Any,
    ) -> asyncio.Future[_R] | None:
        ...

    @abc.abstractmethod
    @callback
    def async_run_hass_job(
        self,
        hassjob: HassJob[asyncio.coroutines.Coroutine[typing.Any, typing.Any, _R] | _R],
        *args: typing.Any,
    ) -> asyncio.Future[_R] | None:
        ...

    @callback
    def async_run_hass_job(
        self,
        hassjob: HassJob[asyncio.coroutines.Coroutine[typing.Any, typing.Any, _R] | _R],
        *args: typing.Any,
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
                hassjob.target = typing.cast(typing.Callable[..., _R], hassjob.target)
            hassjob.target(*args)
            return None

        return self.async_add_hass_job(hassjob, *args)

    @abc.abstractmethod
    @callback
    def async_run_job(
        self,
        target: typing.Callable[
            ..., asyncio.coroutines.Coroutine[typing.Any, typing.Any, _R]
        ],
        *args: typing.Any,
    ) -> asyncio.Future[_R] | None:
        ...

    @abc.abstractmethod
    @callback
    def async_run_job(
        self,
        target: typing.Callable[
            ..., asyncio.coroutines.Coroutine[typing.Any, typing.Any, _R] | _R
        ],
        *args: typing.Any,
    ) -> asyncio.Future[_R] | None:
        ...

    @abc.abstractmethod
    @callback
    def async_run_job(
        self,
        target: asyncio.coroutines.Coroutine[typing.Any, typing.Any, _R],
        *args: typing.Any,
    ) -> asyncio.Future[_R] | None:
        ...

    @callback
    def async_run_job(
        self,
        target: typing.Callable[
            ..., asyncio.coroutines.Coroutine[typing.Any, typing.Any, _R] | _R
        ]
        | asyncio.coroutines.Coroutine[typing.Any, typing.Any, _R],
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
            target = typing.cast(
                typing.Callable[
                    ...,
                    typing.Union[
                        asyncio.coroutines.Coroutine[typing.Any, typing.Any, _R], _R
                    ],
                ],
                target,
            )
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

    async def _await_and_log_pending(
        self, pending: collections.abc.Iterable[collections.abc.Awaitable[typing.Any]]
    ) -> None:
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
        asyncio.fire_coroutine_threadsafe(self.async_stop(), self.loop)

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
        io.shutdown_run_callback_threadsafe(self.loop)

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

    def _no_duplicate_auth_provider(
        configs: collections.abc.Sequence[dict[str, typing.Any]]
    ) -> collections.abc.Sequence[dict[str, typing.Any]]:
        """No duplicate auth provider config allowed in a list.

        Each type of auth provider can only have one config without optional id.
        Unique id is required if same type of auth provider used multiple times.
        """
        config_keys: set[tuple[str, str | None]] = set()
        for config in configs:
            key = (config[Const.CONF_TYPE], config.get(Const.CONF_ID))
            if key in config_keys:
                raise vol.Invalid(
                    f"Duplicate auth provider {config[Const.CONF_TYPE]} found. "
                    "Please add unique IDs "
                    "if you want to have the same auth provider twice"
                )
            config_keys.add(key)
        return configs

    def _no_duplicate_auth_mfa_module(
        configs: collections.abc.Sequence[dict[str, typing.Any]]
    ) -> collections.abc.Sequence[dict[str, typing.Any]]:
        """No duplicate auth mfa module item allowed in a list.

        Each type of mfa module can only have one config without optional id.
        A global unique id is required if same type of mfa module used multiple
        times.
        Note: this is different than auth provider
        """
        config_keys: set[str] = set()
        for config in configs:
            key = config.get(Const.CONF_ID, config[Const.CONF_TYPE])
            if key in config_keys:
                raise vol.Invalid(
                    f"Duplicate mfa module {config[Const.CONF_TYPE]} found. "
                    "Please add unique IDs "
                    "if you want to have the same mfa module twice"
                )
            config_keys.add(key)
        return configs

    def _filter_bad_internal_external_urls(conf: dict) -> dict:
        """Filter internal/external URL with a path."""
        for key in Const.CONF_INTERNAL_URL, Const.CONF_EXTERNAL_URL:
            if key in conf and url.parse_url(conf[key]).path not in ("", "/"):
                # We warn but do not fix, because if this was incorrectly configured,
                # adjusting this value might impact security.
                _LOGGER.warning(
                    "Invalid %s set. It's not allowed to have a path (/bla)", key
                )

        return conf

    def get_default_config_dir() -> str:
        """Put together the default configuration directory based on the OS."""
        data_dir = os.path.expanduser("~")
        return os.path.join(data_dir, HomeAssistant._CONFIG_DIR_NAME)

    async def async_ensure_config_exists(self) -> bool:
        """Ensure a configuration file exists in given configuration directory.

        Creating a default one if needed.
        Return boolean if configuration dir is ready to go.
        """
        config_path = self.config.path(HomeAssistant._YAML_CONFIG_FILE)

        if os.path.isfile(config_path):
            return True

        print(
            "Unable to find configuration. Creating default one in",
            self.config.config_dir,
        )
        return await self.async_create_default_config()

    async def async_create_default_config(self) -> bool:
        """Create a default configuration file in given configuration directory.

        Return if creation was successful.
        """
        return await self.async_add_executor_job(
            HomeAssistant._write_default_config, self.config.config_dir
        )

    def _write_default_config(config_dir: str) -> bool:
        """Write the default config."""
        config_path = os.path.join(config_dir, HomeAssistant._YAML_CONFIG_FILE)
        secret_path = os.path.join(config_dir, HomeAssistant._SECRET_YAML)
        version_path = os.path.join(config_dir, HomeAssistant._VERSION_FILE)
        automation_yaml_path = os.path.join(
            config_dir, HomeAssistant._AUTOMATION_CONFIG_PATH
        )
        script_yaml_path = os.path.join(config_dir, HomeAssistant._SCRIPT_CONFIG_PATH)
        scene_yaml_path = os.path.join(config_dir, HomeAssistant._SCENE_CONFIG_PATH)

        # Writing files with YAML does not create the most human readable results
        # So we're hard coding a YAML template.
        try:
            with open(config_path, "wt", encoding="utf8") as config_file:
                config_file.write(HomeAssistant._DEFAULT_CONFIG)

            if not os.path.isfile(secret_path):
                with open(secret_path, "wt", encoding="utf8") as secret_file:
                    secret_file.write(HomeAssistant._DEFAULT_SECRETS)

            with open(version_path, "wt", encoding="utf8") as version_file:
                version_file.write(Const.__version__)

            if not os.path.isfile(automation_yaml_path):
                with open(
                    automation_yaml_path, "wt", encoding="utf8"
                ) as automation_file:
                    automation_file.write("[]")

            if not os.path.isfile(script_yaml_path):
                with open(script_yaml_path, "wt", encoding="utf8"):
                    pass

            if not os.path.isfile(scene_yaml_path):
                with open(scene_yaml_path, "wt", encoding="utf8"):
                    pass

            return True

        except OSError:
            print("Unable to create default configuration file", config_path)
            return False

    async def async_hass_config_yaml(self) -> dict:
        """Load YAML from a Home Assistant configuration file.

        This function allow a component inside the asyncio loop to reload its
        configuration by itself. Include package merge.
        """
        if self.config.config_dir is None:
            secrets = None
        else:
            secrets = Secrets(pathlib.Path(self.config.config_dir))

        # Not using async_add_executor_job because this is an internal method.
        config = await self.loop.run_in_executor(
            None,
            HomeAssistant.load_yaml_config_file,
            self.config.path(HomeAssistant._YAML_CONFIG_FILE),
            secrets,
        )
        core_config = config.get(Const.CONF_CORE, {})
        await self.merge_packages_config(
            config, core_config.get(Const.CONF_PACKAGES, {})
        )
        return config

    def load_yaml_config_file(
        config_path: str, secrets: Secrets | None = None
    ) -> dict[typing.Any, typing.Any]:
        """Parse a YAML configuration file.

        Raises FileNotFoundError or HomeAssistantError.

        This method needs to run in an executor.
        """
        conf_dict = load_yaml(config_path, secrets)

        if not isinstance(conf_dict, dict):
            msg = (
                f"The configuration file {os.path.basename(config_path)} "
                "does not contain a dictionary"
            )
            _LOGGER.error(msg)
            raise exceptions.HomeAssistantError(msg)

        # Convert values to dictionaries if they are None
        for key, value in conf_dict.items():
            conf_dict[key] = value or {}
        return conf_dict

    def process_ha_config_upgrade(self) -> None:
        """Upgrade configuration if necessary.

        This method needs to run in an executor.
        """
        version_path = self.config.path(HomeAssistant._VERSION_FILE)

        try:
            with open(version_path, encoding="utf8") as inp:
                conf_version = inp.readline().strip()
        except FileNotFoundError:
            # Last version to not have this file
            conf_version = "0.7.7"

        if conf_version == Const.__version__:
            return

        _LOGGER.info(
            "Upgrading configuration directory from %s to %s",
            conf_version,
            Const.__version__,
        )

        version_obj = asv.AwesomeVersion(conf_version)

        if version_obj < asv.AwesomeVersion("0.50"):
            # 0.50 introduced persistent deps dir.
            lib_path = self.config.path("deps")
            if os.path.isdir(lib_path):
                shutil.rmtree(lib_path)

        if version_obj < asv.AwesomeVersion("0.92"):
            # 0.92 moved google/tts.py to google_translate/tts.py
            config_path = self.config.path(HomeAssistant._YAML_CONFIG_FILE)

            with open(config_path, encoding="utf-8") as config_file:
                config_raw = config_file.read()

            if HomeAssistant._TTS_PRE_92 in config_raw:
                _LOGGER.info("Migrating google tts to google_translate tts")
                config_raw = config_raw.replace(
                    HomeAssistant._TTS_PRE_92, HomeAssistant._TTS_92
                )
                try:
                    with open(config_path, "wt", encoding="utf-8") as config_file:
                        config_file.write(config_raw)
                except OSError:
                    _LOGGER.exception("Migrating to google_translate tts failed")

        if version_obj < asv.AwesomeVersion("0.94") and is_docker_env():
            # In 0.94 we no longer install packages inside the deps folder when
            # running inside a Docker container.
            lib_path = self.config.path("deps")
            if os.path.isdir(lib_path):
                shutil.rmtree(lib_path)

        with open(version_path, "wt", encoding="utf8") as outp:
            outp.write(Const.__version__)

    @callback
    def async_log_exception(
        self,
        ex: Exception,
        domain: str,
        config: dict,
        link: str | None = None,
    ) -> None:
        """Log an error for configuration validation.

        This method must be run in the event loop.
        """
        self.async_notify_setup_error(domain, link)
        message, is_friendly = HomeAssistant._format_config_error(
            ex, domain, config, link
        )
        _LOGGER.error(message, exc_info=not is_friendly and ex)

    @callback
    def _format_config_error(
        ex: Exception, domain: str, config: dict, link: str | None = None
    ) -> tuple[str, bool]:
        """Generate log exception for configuration validation.

        This method must be run in the event loop.
        """
        is_friendly = False
        message = f"Invalid config for [{domain}]: "
        if isinstance(ex, vol.Invalid):
            if "extra keys not allowed" in ex.error_message:
                path = "->".join(str(m) for m in ex.path)
                message += (
                    f"[{ex.path[-1]}] is an invalid option for [{domain}]. "
                    f"Check: {domain}->{path}."
                )
            else:
                message += f"{vh.humanize_error(config, ex)}."
            is_friendly = True
        else:
            message += str(ex) or repr(ex)

        try:
            domain_config = config.get(domain, config)
        except AttributeError:
            domain_config = config

        message += (
            f" (See {getattr(domain_config, '__config_file__', '?')}, "
            f"line {getattr(domain_config, '__line__', '?')}). "
        )

        if domain != Const.CONF_CORE and link:
            message += f"Please check the docs at {link}"

        return message, is_friendly

    async def async_process_ha_core_config(self, config: dict) -> None:
        """Process the [homeassistant] section from the configuration.

        This method is a coroutine.
        """
        config = HomeAssistant._CORE_CONFIG_SCHEMA(config)

        # Only load auth during startup.
        if not hasattr(self, "auth"):
            if (auth_conf := config.get(Const.CONF_AUTH_PROVIDERS)) is None:
                auth_conf = [{Const.CONF_TYPE: "homeassistant"}]

            mfa_conf = config.get(
                Const.CONF_AUTH_MFA_MODULES,
                [{Const.CONF_TYPE: "totp", "id": "totp", "name": "Authenticator app"}],
            )

            self.auth = await self.auth.aut_manager_from_config(
                self, auth_conf, mfa_conf
            )

        await self.config.async_load()

        hac = self.config

        if any(
            k in config
            for k in (
                Const.CONF_LATITUDE,
                Const.CONF_LONGITUDE,
                Const.CONF_NAME,
                Const.CONF_ELEVATION,
                Const.CONF_TIME_ZONE,
                Const.CONF_UNIT_SYSTEM,
                Const.CONF_EXTERNAL_URL,
                Const.CONF_INTERNAL_URL,
                Const.CONF_CURRENCY,
            )
        ):
            hac.config_source = ConfigSource.YAML

        for key, attr in (
            (Const.CONF_LATITUDE, "latitude"),
            (Const.CONF_LONGITUDE, "longitude"),
            (Const.CONF_NAME, "location_name"),
            (Const.CONF_ELEVATION, "elevation"),
            (Const.CONF_INTERNAL_URL, "internal_url"),
            (Const.CONF_EXTERNAL_URL, "external_url"),
            (Const.CONF_MEDIA_DIRS, "media_dirs"),
            (Const.CONF_LEGACY_TEMPLATES, "legacy_templates"),
            (Const.CONF_CURRENCY, "currency"),
        ):
            if key in config:
                setattr(hac, attr, config[key])

        if Const.CONF_TIME_ZONE in config:
            hac.set_time_zone(config[Const.CONF_TIME_ZONE])

        if Const.CONF_MEDIA_DIRS not in config:
            if is_docker_env():
                hac.media_dirs = {"local": "/media"}
            else:
                hac.media_dirs = {"local": self.config.path("media")}

        # Init whitelist external dir
        hac.allowlist_external_dirs = {
            self.config.path("www"),
            *hac.media_dirs.values(),
        }
        if Const.CONF_ALLOWLIST_EXTERNAL_DIRS in config:
            hac.allowlist_external_dirs.update(
                set(config[Const.CONF_ALLOWLIST_EXTERNAL_DIRS])
            )

        elif Const.LEGACY_CONF_WHITELIST_EXTERNAL_DIRS in config:
            _LOGGER.warning(
                "Key %s has been replaced with %s. Please update your config",
                Const.LEGACY_CONF_WHITELIST_EXTERNAL_DIRS,
                Const.CONF_ALLOWLIST_EXTERNAL_DIRS,
            )
            hac.allowlist_external_dirs.update(
                set(config[Const.LEGACY_CONF_WHITELIST_EXTERNAL_DIRS])
            )

        # Init whitelist external URL list – make sure to add / to every URL that doesn't
        # already have it so that we can properly test "path ownership"
        if Const.CONF_ALLOWLIST_EXTERNAL_URLS in config:
            hac.allowlist_external_urls.update(
                url if url.endswith("/") else f"{url}/"
                for url in config[Const.CONF_ALLOWLIST_EXTERNAL_URLS]
            )

        # Customize
        cust_exact = dict(config[Const.CONF_CUSTOMIZE])
        cust_domain = dict(config[Const.CONF_CUSTOMIZE_DOMAIN])
        cust_glob = collections.OrderedDict(config[Const.CONF_CUSTOMIZE_GLOB])

        for name, pkg in config[Const.CONF_PACKAGES].items():
            if (pkg_cust := pkg.get(Const.CONF_CORE)) is None:
                continue

            try:
                pkg_cust = Const.CUSTOMIZE_CONFIG_SCHEMA(pkg_cust)
            except vol.Invalid:
                _LOGGER.warning("Package %s contains invalid customize", name)
                continue

            cust_exact.update(pkg_cust[Const.CONF_CUSTOMIZE])
            cust_domain.update(pkg_cust[Const.CONF_CUSTOMIZE_DOMAIN])
            cust_glob.update(pkg_cust[Const.CONF_CUSTOMIZE_GLOB])

        self.data[Const.DATA_CUSTOMIZE] = EntityValues(
            cust_exact, cust_domain, cust_glob
        )

        if Const.CONF_UNIT_SYSTEM in config:
            if config[Const.CONF_UNIT_SYSTEM] == Const.CONF_UNIT_SYSTEM_IMPERIAL:
                hac.units = UnitSystem.IMPERIAL
            else:
                hac.units = UnitSystem.METRIC
        elif Const.CONF_TEMPERATURE_UNIT in config:
            unit = config[Const.CONF_TEMPERATURE_UNIT]
            hac.units = (
                UnitSystem.METRIC if unit == Const.TEMP_CELSIUS else UnitSystem.IMPERIAL
            )
            _LOGGER.warning(
                "Found deprecated temperature unit in core "
                "configuration expected unit system. Replace '%s: %s' "
                "with '%s: %s'",
                Const.CONF_TEMPERATURE_UNIT,
                unit,
                Const.CONF_UNIT_SYSTEM,
                hac.units.name,
            )

    def _log_pkg_error(
        package: str, component: str, config: dict, message: str
    ) -> None:
        """Log an error while merging packages."""
        message = f"Package {package} setup failed. Integration {component} {message}"

        pack_config = config[Const.CONF_CORE][Const.CONF_PACKAGES].get(package, config)
        message += (
            f" (See {getattr(pack_config, '__config_file__', '?')}:"
            f"{getattr(pack_config, '__line__', '?')}). "
        )

        _LOGGER.error(message)

    def _identify_config_schema(module: typing.ModuleType) -> str | None:
        """Extract the schema and identify list or dict based."""
        if not isinstance(module.CONFIG_SCHEMA, vol.Schema):
            return None

        schema = module.CONFIG_SCHEMA.schema

        if isinstance(schema, vol.All):
            for subschema in schema.validators:
                if isinstance(subschema, dict):
                    schema = subschema
                    break
            else:
                return None

        try:
            key = next(k for k in schema if k == module.DOMAIN)
        except (TypeError, AttributeError, StopIteration):
            return None
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected error identifying config schema")
            return None

        if hasattr(key, "default") and not isinstance(
            key.default, vol.schema_builder.Undefined
        ):
            default_value = module.CONFIG_SCHEMA({module.DOMAIN: key.default()})[
                module.DOMAIN
            ]

            if isinstance(default_value, dict):
                return "dict"

            if isinstance(default_value, list):
                return "list"

            return None

        domain_schema = schema[key]

        t_schema = str(domain_schema)
        if t_schema.startswith("{") or "schema_with_slug_keys" in t_schema:
            return "dict"
        if t_schema.startswith(("[", "All(<function ensure_list")):
            return "list"
        return None

    def _recursive_merge(
        conf: dict[str, typing.Any], package: dict[str, typing.Any]
    ) -> bool | str:
        """Merge package into conf, recursively."""
        error: bool | str = False
        for key, pack_conf in package.items():
            if isinstance(pack_conf, dict):
                if not pack_conf:
                    continue
                conf[key] = conf.get(key, collections.OrderedDict())
                error = HomeAssistant._recursive_merge(
                    conf=conf[key], package=pack_conf
                )

            elif isinstance(pack_conf, list):
                conf[key] = cv.remove_falsy(
                    cv.ensure_list(conf.get(key)) + cv.ensure_list(pack_conf)
                )

            else:
                if conf.get(key) is not None:
                    return key
                conf[key] = pack_conf
        return error

    async def merge_packages_config(
        self,
        config: dict,
        packages: dict[str, typing.Any],
        _log_pkg_error: typing.Callable = _log_pkg_error,
    ) -> dict:
        """Merge packages into the top-level configuration. Mutate config."""
        HomeAssistant._PACKAGES_CONFIG_SCHEMA(packages)
        for pack_name, pack_conf in packages.items():
            for comp_name, comp_conf in pack_conf.items():
                if comp_name == Const.CONF_CORE:
                    continue
                # If component name is given with a trailing description, remove it
                # when looking for component
                domain = comp_name.split(" ")[0]

                try:
                    integration = await self.async_get_integration_with_requirements(
                        domain
                    )
                    component = integration.get_component()
                except HomeAssistant._INTEGRATION_LOAD_EXCEPTIONS as ex:
                    _log_pkg_error(pack_name, comp_name, config, str(ex))
                    continue

                try:
                    config_platform: typing.ModuleType | None = (
                        integration.get_platform("config")
                    )
                    # Test if config platform has a config validator
                    if not hasattr(config_platform, "async_validate_config"):
                        config_platform = None
                except ImportError:
                    config_platform = None

                merge_list = False

                # If integration has a custom config validator, it needs to provide a hint.
                if config_platform is not None:
                    merge_list = config_platform.PACKAGE_MERGE_HINT == "list"

                if not merge_list:
                    merge_list = hasattr(component, "PLATFORM_SCHEMA")

                if not merge_list and hasattr(component, "CONFIG_SCHEMA"):
                    merge_list = self._identify_config_schema(component) == "list"

                if merge_list:
                    config[comp_name] = cv.remove_falsy(
                        cv.ensure_list(config.get(comp_name))
                        + cv.ensure_list(comp_conf)
                    )
                    continue

                if comp_conf is None:
                    comp_conf = collections.OrderedDict()

                if not isinstance(comp_conf, dict):
                    _log_pkg_error(
                        pack_name,
                        comp_name,
                        config,
                        "cannot be merged. Expected a dict.",
                    )
                    continue

                if comp_name not in config or config[comp_name] is None:
                    config[comp_name] = collections.OrderedDict()

                if not isinstance(config[comp_name], dict):
                    _log_pkg_error(
                        pack_name,
                        comp_name,
                        config,
                        "cannot be merged. Dict expected in main config.",
                    )
                    continue

                error = HomeAssistant._recursive_merge(
                    conf=config[comp_name], package=comp_conf
                )
                if error:
                    _log_pkg_error(
                        pack_name, comp_name, config, f"has duplicate key '{error}'"
                    )

        return config

    async def async_process_component_config( 
        self, config: ConfigType, integration: Integration
    ) -> ConfigType | None:
        """Check component configuration and return processed configuration.

        Returns None on error.

        This method must be run in the event loop.
        """
        domain = integration.domain
        try:
            component = integration.get_component()
        except HomeAssistant._LOAD_EXCEPTIONS as ex:
            _LOGGER.error("Unable to import %s: %s", domain, ex)
            return None

        # Check if the integration has a custom config validator
        config_validator = None
        try:
            config_validator = integration.get_platform("config")
        except ImportError as err:
            # Filter out import error of the config platform.
            # If the config platform contains bad imports, make sure
            # that still fails.
            if err.name != f"{integration.pkg_path}.config":
                _LOGGER.error("Error importing config platform %s: %s", domain, err)
                return None

        if config_validator is not None and hasattr(
            config_validator, "async_validate_config"
        ):
            try:
                return await config_validator.async_validate_config( self, config )
            except (vol.Invalid, exceptions.HomeAssistantError) as ex:
                self.async_log_exception(ex, domain, config, integration.documentation)
                return None
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unknown error calling %s config validator", domain)
                return None

        # No custom config validator, proceed with schema validation
        if hasattr(component, "CONFIG_SCHEMA"):
            try:
                return component.CONFIG_SCHEMA(config)
            except vol.Invalid as ex:
                self.async_log_exception(ex, domain, config, integration.documentation)
                return None
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unknown error calling %s CONFIG_SCHEMA", domain)
                return None

        component_platform_schema = getattr(
            component,
            "PLATFORM_SCHEMA_BASE",
            getattr(component, "PLATFORM_SCHEMA", None),
        )

        if component_platform_schema is None:
            return config

        platforms = []
        for p_name, p_config in self.config.config_per_platform(domain):
            # Validate component specific platform schema
            try:
                p_validated = component_platform_schema(p_config)
            except vol.Invalid as ex:
                self.async_log_exception(
                    ex, domain, p_config, integration.documentation
                )
                continue
            except Exception: 
                _LOGGER.exception(
                    "Unknown error validating %s platform config with %s component platform schema",
                    p_name,
                    domain,
                )
                continue

            # Not all platform components follow same pattern for platforms
            # So if p_name is None we are not going to validate platform
            # (the automation component is one of them)
            if p_name is None:
                platforms.append(p_validated)
                continue

            try:
                p_integration = await self.async_get_integration_with_requirements( p_name )
            except (exceptions.RequirementsNotFound, exceptions.IntegrationNotFound) as ex:
                _LOGGER.error("Platform error: %s - %s", domain, ex)
                continue

            try:
                platform = p_integration.get_platform(domain)
            except HomeAssistant._LOAD_EXCEPTIONS:
                _LOGGER.exception("Platform error: %s", domain)
                continue

            # Validate platform specific schema
            if hasattr(platform, "PLATFORM_SCHEMA"):
                try:
                    p_validated = platform.PLATFORM_SCHEMA(p_config)
                except vol.Invalid as ex:
                    self.async_log_exception(
                        ex,
                        f"{domain}.{p_name}",
                        p_config,
                        p_integration.documentation,
                    )
                    continue
                except Exception:  # pylint: disable=broad-except
                    _LOGGER.exception(
                        "Unknown error validating config for %s platform for %s component with PLATFORM_SCHEMA",
                        p_name,
                        domain,
                    )
                    continue

            platforms.append(p_validated)

        # Create a copy of the configuration with all config for current
        # component removed and add validated config back in.
        config = HomeAssistant.config_without_domain(config, domain)
        config[domain] = platforms

        return config

    @callback
    def config_without_domain(config: ConfigType, domain: str) -> ConfigType:
        """Return a config with all configuration for a domain removed."""
        filter_keys = Config.extract_domain_configs(config, domain)
        return {key: value for key, value in config.items() if key not in filter_keys}

    async def async_check_ha_config_file(self) -> str | None:
        """Check if Home Assistant configuration file is valid.

        This method is a coroutine.
        """
        # pylint: disable=import-outside-toplevel
        from .helpers import check_config

        res = await check_config.async_check_ha_config_file(self)

        if not res.errors:
            return None
        return res.error_str

    @callback
    def async_notify_setup_error(
        self, component: str, display_link: str | None = None
    ) -> None:
        """Print a persistent notification.

        This method must be run in the event loop.
        """
        from .components import persistent_notification

        if (errors := self.data.get(Const.DATA_PERSISTENT_ERRORS)) is None:
            errors = self.data[Const.DATA_PERSISTENT_ERRORS] = {}

        errors[component] = errors.get(component) or display_link

        message = "The following integrations and platforms could not be set up:\n\n"

        for name, link in errors.items():
            show_logs = f"[Show logs](/config/logs?filter={name})"
            part = f"[{name}]({link})" if link else name
            message += f" - {part} ({show_logs})\n"

        message += "\nPlease check your config and [logs](/config/logs)."

        persistent_notification.async_create(
            self, message, "Invalid config", "invalid_config"
        )

    _CORE_CONFIG_SCHEMA: typing.Final = vol.All(
        _CUSTOMIZE_CONFIG_SCHEMA.extend(
            {
                Const.CONF_NAME: vol.Coerce(str),
                Const.CONF_LATITUDE: cv.latitude,
                Const.CONF_LONGITUDE: cv.longitude,
                Const.CONF_ELEVATION: vol.Coerce(int),
                vol.Optional(Const.CONF_TEMPERATURE_UNIT): cv.temperature_unit,
                Const.CONF_UNIT_SYSTEM: cv.unit_system,
                Const.CONF_TIME_ZONE: cv.time_zone,
                vol.Optional(Const.CONF_INTERNAL_URL): cv.url,
                vol.Optional(Const.CONF_EXTERNAL_URL): cv.url,
                vol.Optional(Const.CONF_ALLOWLIST_EXTERNAL_DIRS): vol.All(
                    cv.ensure_list,
                    [vol.IsDir()],  # pylint: disable=no-value-for-parameter
                ),
                vol.Optional(Const.LEGACY_CONF_WHITELIST_EXTERNAL_DIRS): vol.All(
                    cv.ensure_list,
                    [vol.IsDir()],  # pylint: disable=no-value-for-parameter
                ),
                vol.Optional(Const.CONF_ALLOWLIST_EXTERNAL_URLS): vol.All(
                    cv.ensure_list, [cv.url]
                ),
                vol.Optional(Const.CONF_PACKAGES, default={}): _PACKAGES_CONFIG_SCHEMA,
                vol.Optional(Const.CONF_AUTH_PROVIDERS): vol.All(
                    cv.ensure_list,
                    [
                        auth_providers.AUTH_PROVIDER_SCHEMA.extend(
                            {
                                Const.CONF_TYPE: vol.NotIn(
                                    ["insecure_example"],
                                    "The insecure_example auth provider"
                                    " is for testing only.",
                                )
                            }
                        )
                    ],
                    _no_duplicate_auth_provider,
                ),
                vol.Optional(Const.CONF_AUTH_MFA_MODULES): vol.All(
                    cv.ensure_list,
                    [
                        auth_mfa_modules.MULTI_FACTOR_AUTH_MODULE_SCHEMA.extend(
                            {
                                Const.CONF_TYPE: vol.NotIn(
                                    ["insecure_example"],
                                    "The insecure_example mfa module is for testing only.",
                                )
                            }
                        )
                    ],
                    _no_duplicate_auth_mfa_module,
                ),
                # pylint: disable=no-value-for-parameter
                vol.Optional(Const.CONF_MEDIA_DIRS): cv.schema_with_slug_keys(
                    vol.IsDir()
                ),
                vol.Optional(Const.CONF_LEGACY_TEMPLATES): cv.boolean,
                vol.Optional(Const.CONF_CURRENCY): cv.currency,
            }
        ),
        _filter_bad_internal_external_urls,
    )


class HomeAssistantHTTP:
    """HTTP server for Home Assistant."""

    _current_request: contextvars.ContextVar[
        aiohttp.web.Request | None
    ] = contextvars.ContextVar("current_request", default=None)
    _MAX_CLIENT_SIZE: typing.Final = 1024**2 * 16
    _SECURITY_FILTERS: typing.Final = re.compile(
        r"(?:"
        # Common exploits
        r"proc/self/environ" r"|(<|%3C).*script.*(>|%3E)"
        # File Injections
        r"|(\.\.//?)+"  # ../../anywhere
        r"|[a-zA-Z0-9_]=/([a-z0-9_.]//?)+"  # .html?v=/.//test
        # SQL Injections
        r"|union.*select.*\(" r"|union.*all.*select.*" r"|concat.*\(" r")",
        flags=re.IGNORECASE,
    )
    _SCHEMA_IP_BAN_ENTRY: typing.Final = vol.Schema(
        {vol.Optional("banned_at"): vol.Any(None, cv.datetime)}
    )

    def __init__(
        self,
        hass: HomeAssistant,
        ssl_certificate: str | None,
        ssl_peer_certificate: str | None,
        ssl_key: str | None,
        server_host: list[str] | None,
        server_port: int,
        trusted_proxies: list[ipaddress.IPv4Network | ipaddress.IPv6Network],
        ssl_profile: str,
    ) -> None:
        """Initialize the HTTP Home Assistant server."""
        self.app = aiohttp.web.Application(
            middlewares=[], client_max_size=HomeAssistantHTTP._MAX_CLIENT_SIZE
        )
        self.hass = hass
        self.ssl_certificate = ssl_certificate
        self.ssl_peer_certificate = ssl_peer_certificate
        self.ssl_key = ssl_key
        self.server_host = server_host
        self.server_port = server_port
        self.trusted_proxies = trusted_proxies
        self.ssl_profile = ssl_profile
        self.runner: aiohttp.web.AppRunner | None = None
        self.site: HomeAssistantTCPSite | None = None
        self.context: ssl.SSLContext | None = None

    async def async_initialize(
        self,
        *,
        cors_origins: list[str],
        use_x_forwarded_for: bool,
        login_threshold: int,
        is_ban_enabled: bool,
    ) -> None:
        """Initialize the server."""
        self.app[Const.KEY_HASS] = self.hass

        # Order matters, security filters middleware needs to go first,
        # forwarded middleware needs to go second.
        self.setup_security_filter()

        self.async_setup_forwarded(use_x_forwarded_for, self.trusted_proxies)

        self.setup_request_context(self.app, HomeAssistantHTTP._current_request)

        if is_ban_enabled:
            self.setup_bans(login_threshold)

        await async_setup_auth(self.hass, self.app)

        setup_cors(self.app, cors_origins)

        if self.ssl_certificate:
            self.context = await self.hass.async_add_executor_job(
                self._create_ssl_context
            )

    @callback
    def setup_security_filter(self) -> None:
        """Create security filter middleware for the app."""

        @aiohttp.web_middlewares.middleware
        async def security_filter_middleware(
            request: aiohttp.web.Request,
            handler: typing.Callable[
                [aiohttp.web.Request],
                collections.abc.Awaitable[aiohttp.web.StreamResponse],
            ],
        ) -> aiohttp.web.StreamResponse:
            """Process request and tblock commonly known exploit attempts."""
            if HomeAssistantHTTP._SECURITY_FILTERS.search(request.path):
                _LOGGER.warning(
                    "Filtered a potential harmful request to: %s", request.raw_path
                )
                raise aiohttp.web.HTTPBadRequest

            if HomeAssistantHTTP._SECURITY_FILTERS.search(request.query_string):
                _LOGGER.warning(
                    "Filtered a request with a potential harmful query string: %s",
                    request.raw_path,
                )
                raise aiohttp.web.HTTPBadRequest

            return await handler(request)

        self.app.middlewares.append(security_filter_middleware)

    @callback
    def async_setup_forwarded(
        self,
        use_x_forwarded_for: bool | None,
        trusted_proxies: list[ipaddress.IPv4Network | ipaddress.IPv6Network],
    ) -> None:
        """Create forwarded middleware for the app.

        Process IP addresses, proto and host information in the forwarded for headers.

        `X-Forwarded-For: <client>, <proxy1>, <proxy2>`
        e.g., `X-Forwarded-For: 203.0.113.195, 70.41.3.18, 150.172.238.178`

        We go through the list from the right side, and skip all entries that are in our
        trusted proxies list. The first non-trusted IP is used as the client IP. If all
        items in the X-Forwarded-For are trusted, including the most left item (client),
        the most left item is used. In the latter case, the client connection originated
        from an IP that is also listed as a trusted proxy IP or network.

        `X-Forwarded-Proto: <client>, <proxy1>, <proxy2>`
        e.g., `X-Forwarded-Proto: https, http, http`
        OR `X-Forwarded-Proto: https` (one entry, even with multiple proxies)

        The X-Forwarded-Proto is determined based on the corresponding entry of the
        X-Forwarded-For header that is used/chosen as the client IP. However,
        some proxies, for example, Kubernetes NGINX ingress, only retain one element
        in the X-Forwarded-Proto header. In that case, we'll just use what we have.

        `X-Forwarded-Host: <host>`
        e.g., `X-Forwarded-Host: example.com`

        If the previous headers are processed successfully, and the X-Forwarded-Host is
        present, it will be used.

        Additionally:
        - If no X-Forwarded-For header is found, the processing of all headers is skipped.
        - Throw HTTP 400 status when untrusted connected peer provides
            X-Forwarded-For headers.
        - If multiple instances of X-Forwarded-For, X-Forwarded-Proto or
            X-Forwarded-Host are found, an HTTP 400 status code is thrown.
        - If malformed or invalid (IP) data in X-Forwarded-For header is found,
            an HTTP 400 status code is thrown.
        - The connected client peer on the socket of the incoming connection,
            must be trusted for any processing to take place.
        - If the number of elements in X-Forwarded-Proto does not equal 1 or
            is equal to the number of elements in X-Forwarded-For, an HTTP 400
            status code is thrown.
        - If an empty X-Forwarded-Host is provided, an HTTP 400 status code is thrown.
        - If an empty X-Forwarded-Proto is provided, or an empty element in the list,
            an HTTP 400 status code is thrown.
        """

        remote: typing.Literal[False] | None | typing.ModuleType = None

        @aiohttp.web_middlewares.middleware
        async def forwarded_middleware(
            request: aiohttp.web.Request,
            handler: typing.Callable[
                [aiohttp.web.Request],
                collections.abc.Awaitable[aiohttp.web.StreamResponse],
            ],
        ) -> aiohttp.web.StreamResponse:
            """Process forwarded data by a reverse proxy."""
            nonlocal remote

            if remote is None:
                remote = False
                # Initialize remote method
                #try:
                #    from hass_nabucasa import (
                #        remote,
                #    )  # pylint: disable=import-outside-toplevel
                #
                #    # venv users might have an old version installed if they don't have cloud around anymore
                #    if not hasattr(remote, "is_cloud_request"):
                #        remote = False
                #except ImportError:
                #    remote = False

            # Skip requests from Remote UI
            if remote and remote.is_cloud_request.get():
                return await handler(request)

            # Handle X-Forwarded-For
            forwarded_for_headers: list[str] = request.headers.getall(
                aiohttp.hdrs.X_FORWARDED_FOR, []
            )
            if not forwarded_for_headers:
                # No forwarding headers, continue as normal
                return await handler(request)

            # Get connected IP
            if (
                request.transport is None
                or request.transport.get_extra_info("peername") is None
            ):
                # Connected IP isn't retrieveable from the request transport, continue
                return await handler(request)

            connected_ip = ipaddress.ip_address(
                request.transport.get_extra_info("peername")[0]
            )

            # We have X-Forwarded-For, but config does not agree
            if not use_x_forwarded_for:
                _LOGGER.error(
                    "A request from a reverse proxy was received from %s, but your "
                    "HTTP integration is not set-up for reverse proxies",
                    connected_ip,
                )
                raise aiohttp.web.HTTPBadRequest

            # Ensure the IP of the connected peer is trusted
            if not any(
                connected_ip in trusted_proxy for trusted_proxy in trusted_proxies
            ):
                _LOGGER.error(
                    "Received X-Forwarded-For header from an untrusted proxy %s",
                    connected_ip,
                )
                raise aiohttp.web.HTTPBadRequest

            # Multiple X-Forwarded-For headers
            if len(forwarded_for_headers) > 1:
                _LOGGER.error(
                    "Too many headers for X-Forwarded-For: %s", forwarded_for_headers
                )
                raise aiohttp.web.HTTPBadRequest

            # Process X-Forwarded-For from the right side (by reversing the list)
            forwarded_for_split = list(reversed(forwarded_for_headers[0].split(",")))
            try:
                forwarded_for = [
                    ipaddress.ip_address(addr.strip()) for addr in forwarded_for_split
                ]
            except ValueError as err:
                _LOGGER.error(
                    "Invalid IP address in X-Forwarded-For: %s",
                    forwarded_for_headers[0],
                )
                raise aiohttp.web.HTTPBadRequest from err

            overrides: dict[str, str] = {}

            # Find the last trusted index in the X-Forwarded-For list
            forwarded_for_index = 0
            for forwarded_ip in forwarded_for:
                if any(
                    forwarded_ip in trusted_proxy for trusted_proxy in trusted_proxies
                ):
                    forwarded_for_index += 1
                    continue
                overrides["remote"] = str(forwarded_ip)
                break
            else:
                # If all the IP addresses are from trusted networks, take the left-most.
                forwarded_for_index = -1
                overrides["remote"] = str(forwarded_for[-1])

            # Handle X-Forwarded-Proto
            forwarded_proto_headers: list[str] = request.headers.getall(
                aiohttp.hdrs.X_FORWARDED_PROTO, []
            )
            if forwarded_proto_headers:
                if len(forwarded_proto_headers) > 1:
                    _LOGGER.error(
                        "Too many headers for X-Forward-Proto: %s",
                        forwarded_proto_headers,
                    )
                    raise aiohttp.web.HTTPBadRequest

                forwarded_proto_split = list(
                    reversed(forwarded_proto_headers[0].split(","))
                )
                forwarded_proto = [proto.strip() for proto in forwarded_proto_split]

                # Catch empty values
                if "" in forwarded_proto:
                    _LOGGER.error(
                        "Empty item received in X-Forward-Proto header: %s",
                        forwarded_proto_headers[0],
                    )
                    raise aiohttp.web.HTTPBadRequest

                # The X-Forwarded-Proto contains either one element, or the equals number
                # of elements as X-Forwarded-For
                if len(forwarded_proto) not in (1, len(forwarded_for)):
                    _LOGGER.error(
                        "Incorrect number of elements in X-Forward-Proto. Expected 1 or %d, got %d: %s",
                        len(forwarded_for),
                        len(forwarded_proto),
                        forwarded_proto_headers[0],
                    )
                    raise aiohttp.web.HTTPBadRequest

                # Ideally this should take the scheme corresponding to the entry
                # in X-Forwarded-For that was chosen, but some proxies only retain
                # one element. In that case, use what we have.
                overrides["scheme"] = forwarded_proto[-1]
                if len(forwarded_proto) != 1:
                    overrides["scheme"] = forwarded_proto[forwarded_for_index]

            # Handle X-Forwarded-Host
            forwarded_host_headers: list[str] = request.headers.getall(
                aiohttp.hdrs.X_FORWARDED_HOST, []
            )
            if forwarded_host_headers:
                # Multiple X-Forwarded-Host headers
                if len(forwarded_host_headers) > 1:
                    _LOGGER.error(
                        "Too many headers for X-Forwarded-Host: %s",
                        forwarded_host_headers,
                    )
                    raise aiohttp.web.HTTPBadRequest

                forwarded_host = forwarded_host_headers[0].strip()
                if not forwarded_host:
                    _LOGGER.error("Empty value received in X-Forward-Host header")
                    raise aiohttp.web.HTTPBadRequest

                overrides["host"] = forwarded_host

            # Done, create a new request based on gathered data.
            request = request.clone(**overrides)  # type: ignore[arg-type]
            return await handler(request)

        self.app.middlewares.append(forwarded_middleware)

    @callback
    def setup_request_context(
        self, context: contextvars.ContextVar[aiohttp.web.Request | None]
    ) -> None:
        """Create request context middleware for the app."""

        @aiohttp.web_middlewares.middleware
        async def request_context_middleware(
            request: aiohttp.web.Request,
            handler: typing.Callable[
                [aiohttp.web.Request],
                collections.abc.Awaitable[aiohttp.web.StreamResponse],
            ],
        ) -> aiohttp.web.StreamResponse:
            """Request context middleware."""
            context.set(request)
            return await handler(request)

        self.app.middlewares.append(request_context_middleware)

    @callback
    def setup_bans(self, login_threshold: int) -> None:
        """Create IP Ban middleware for the app."""
        self.app.middlewares.append(HomeAssistantHTTP.ban_middleware)
        self.app[Const.KEY_FAILED_LOGIN_ATTEMPTS] = collections.defaultdict(int)
        self.app[Const.KEY_LOGIN_THRESHOLD] = login_threshold

        async def ban_startup(app: aiohttp.web.Application) -> None:
            """Initialize bans when app starts up."""
            self.app[Const.KEY_BANNED_IPS] = await self.async_load_ip_bans_config()

        self.app.on_startup.append(ban_startup)

    @aiohttp.web_middlewares.middleware
    async def ban_middleware(
        request: aiohttp.web.Request,
        handler: typing.Callable[
            [aiohttp.web.Request], collections.abc.Awaitable[aiohttp.web.StreamResponse]
        ],
    ) -> aiohttp.web.StreamResponse:
        """IP Ban middleware."""
        if Const.KEY_BANNED_IPS not in request.app:
            _LOGGER.error("IP Ban middleware loaded but banned IPs not loaded")
            return await handler(request)

        # Verify if IP is not banned
        ip_address_ = ip_address(request.remote)  # type: ignore[arg-type]
        is_banned = any(
            ip_ban.ip_address == ip_address_
            for ip_ban in request.app[Const.KEY_BANNED_IPS]
        )

        if is_banned:
            raise aiohttp.web.HTTPForbidden()

        try:
            return await handler(request)
        except aiohttp.web.HTTPUnauthorized:
            await process_wrong_login(request)
            raise

    async def async_load_ip_bans_config(self) -> list[IpBan]:
        """Load list of banned IPs from config file."""
        ip_list: list[IpBan] = []
        path = self.hass.config.path(Const.IP_BANS_FILE)

        try:
            list_ = await self.hass.async_add_executor_job(HomeAssistant.load_yaml_config_file, path)
        except FileNotFoundError:
            return ip_list
        except exceptions.HomeAssistantError as err:
            _LOGGER.error("Unable to load %s: %s", path, str(err))
            return ip_list

        for ip_ban, ip_info in list_.items():
            try:
                ip_info = HomeAssistantHTTP._SCHEMA_IP_BAN_ENTRY(ip_info)
                ip_list.append(IpBan(ip_ban, ip_info["banned_at"]))
            except vol.Invalid as err:
                _LOGGER.error("Failed to load IP ban %s: %s", ip_info, err)
                continue

        return ip_list

    def register_view(self, view: HomeAssistantView | type[HomeAssistantView]) -> None:
        """Register a view with the WSGI server.

        The view argument must be a class that inherits from HomeAssistantView.
        It is optional to instantiate it before registering; this method will
        handle it either way.
        """
        if isinstance(view, type):
            # Instantiate the view, if needed
            view = view()

        if not hasattr(view, "url"):
            class_name = view.__class__.__name__
            raise AttributeError(f'{class_name} missing required attribute "url"')

        if not hasattr(view, "name"):
            class_name = view.__class__.__name__
            raise AttributeError(f'{class_name} missing required attribute "name"')

        view.register(self.app, self.app.router)

    def register_redirect(
        self,
        url: str,
        redirect_to: aiohttp.typedefs.StrOrURL,
        *,
        redirect_exc: type[
            aiohttp.web.HTTPRedirection
        ] = aiohttp.web.HTTPMovedPermanently,
    ) -> None:
        """Register a redirect with the server.

        If given this must be either a string or callable. In case of a
        callable it's called with the url adapter that triggered the match and
        the values of the URL as keyword arguments and has to return the target
        for the redirect, otherwise it has to be a string with placeholders in
        rule syntax.
        """

        async def redirect(_request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
            """Redirect to location."""
            # Should be instance of aiohttp.web_exceptions._HTTPMove.
            raise redirect_exc(redirect_to)  # type: ignore[arg-type,misc]

        self.app["allow_configured_cors"](
            self.app.router.add_route("GET", url, redirect)
        )

    def register_static_path(
        self, url_path: str, path: str, cache_headers: bool = True
    ) -> None:
        """Register a folder or file to serve as a static path."""
        if os.path.isdir(path):
            if cache_headers:
                resource: CachingStaticResource | aiohttp.web.StaticResource = (
                    CachingStaticResource(url_path, path)
                )
            else:
                resource = aiohttp.web.StaticResource(url_path, path)
            self.app.router.register_resource(resource)
            self.app["allow_configured_cors"](resource)
            return

        async def serve_file(_request: aiohttp.web.Request) -> aiohttp.web.FileResponse:
            """Serve file from disk."""
            if cache_headers:
                return aiohttp.web.FileResponse(path, headers=Const.CACHE_HEADERS)
            return aiohttp.web.FileResponse(path)

        self.app["allow_configured_cors"](
            self.app.router.add_route("GET", url_path, serve_file)
        )

    def _create_ssl_context(self) -> ssl.SSLContext | None:
        context: ssl.SSLContext | None = None
        assert self.ssl_certificate is not None
        try:
            if self.ssl_profile == Const.SSL_INTERMEDIATE:
                context = HomeAssistantHTTP._server_context_intermediate()
            else:
                context = HomeAssistantHTTP._server_context_modern()
            context.load_cert_chain(self.ssl_certificate, self.ssl_key)
        except OSError as error:
            if not self.hass.config.safe_mode:
                raise exceptions.HomeAssistantError(
                    f"Could not use SSL certificate from {self.ssl_certificate}: {error}"
                ) from error
            _LOGGER.error(
                "Could not read SSL certificate from %s: %s",
                self.ssl_certificate,
                error,
            )
            try:
                context = self._create_emergency_ssl_context()
            except OSError as error2:
                _LOGGER.error(
                    "Could not create an emergency self signed ssl certificate: %s",
                    error2,
                )
                context = None
            else:
                _LOGGER.critical(
                    "Home Assistant is running in safe mode with an emergency self signed ssl certificate because the configured SSL certificate was not usable"
                )
                return context

        if self.ssl_peer_certificate:
            if context is None:
                raise exceptions.HomeAssistantError(
                    "Failed to create ssl context, no fallback available because a peer certificate is required."
                )

            context.verify_mode = ssl.CERT_REQUIRED
            context.load_verify_locations(self.ssl_peer_certificate)

        return context

    def _create_emergency_ssl_context(self) -> ssl.SSLContext:
        """Create an emergency ssl certificate so we can still startup."""
        context = HomeAssistantHTTP._server_context_modern()
        host: str
        try:
            host = typing.cast(
                str, yarl.URL(get_url(self.hass, prefer_external=True)).host
            )
        except aiohttp.web.NoURLAvailableError:
            host = "homeassistant.local"
        key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        subject = issuer = cryptography.x509.Name(
            [
                cryptography.x509.NameAttribute(
                    cryptography.x509.oid.NameOID.ORGANIZATION_NAME,
                    "Home Assistant Emergency Certificate",
                ),
                cryptography.x509.NameAttribute(
                    cryptography.x509.oid.NameOID.COMMON_NAME, host
                ),
            ]
        )
        cert = (
            cryptography.x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(cryptography.x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=30))
            .add_extension(
                cryptography.x509.SubjectAlternativeName(
                    [cryptography.x509.DNSName(host)]
                ),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )
        with tempfile.NamedTemporaryFile() as cert_pem, tempfile.NamedTemporaryFile() as key_pem:
            cert_pem.write(cert.public_bytes(serialization.Encoding.PEM))
            key_pem.write(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
            cert_pem.flush()
            key_pem.flush()
            context.load_cert_chain(cert_pem.name, key_pem.name)
        return context

    def _client_context() -> ssl.SSLContext:
        """Return an SSL context for making requests."""

        # Reuse environment variable definition from requests, since it's already a requirement
        # If the environment variable has no value, fall back to using certs from certifi package
        cafile = os.environ.get("REQUESTS_CA_BUNDLE", certifi.where())

        context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH, cafile=cafile)
        return context


    def _server_context_modern() -> ssl.SSLContext:
        """Return an SSL context following the Mozilla recommendations.

        TLS configuration follows the best-practice guidelines specified here:
        https://wiki.mozilla.org/Security/Server_Side_TLS
        Modern guidelines are followed.
        """
        context = ssl.SSLContext(ssl.PROTOCOL_TLS)

        context.options |= (
            ssl.OP_NO_SSLv2
            | ssl.OP_NO_SSLv3
            | ssl.OP_NO_TLSv1
            | ssl.OP_NO_TLSv1_1
            | ssl.OP_CIPHER_SERVER_PREFERENCE
        )
        if hasattr(ssl, "OP_NO_COMPRESSION"):
            context.options |= ssl.OP_NO_COMPRESSION

        context.set_ciphers(
            "ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:"
            "ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:"
            "ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:"
            "ECDHE-ECDSA-AES256-SHA384:ECDHE-RSA-AES256-SHA384:"
            "ECDHE-ECDSA-AES128-SHA256:ECDHE-RSA-AES128-SHA256"
        )

        return context


    def _server_context_intermediate() -> ssl.SSLContext:
        """Return an SSL context following the Mozilla recommendations.

        TLS configuration follows the best-practice guidelines specified here:
        https://wiki.mozilla.org/Security/Server_Side_TLS
        Intermediate guidelines are followed.
        """
        context = ssl.SSLContext(ssl.PROTOCOL_TLS)

        context.options |= (
            ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3 | ssl.OP_CIPHER_SERVER_PREFERENCE
        )
        if hasattr(ssl, "OP_NO_COMPRESSION"):
            context.options |= ssl.OP_NO_COMPRESSION

        context.set_ciphers(
            "ECDHE-ECDSA-CHACHA20-POLY1305:"
            "ECDHE-RSA-CHACHA20-POLY1305:"
            "ECDHE-ECDSA-AES128-GCM-SHA256:"
            "ECDHE-RSA-AES128-GCM-SHA256:"
            "ECDHE-ECDSA-AES256-GCM-SHA384:"
            "ECDHE-RSA-AES256-GCM-SHA384:"
            "DHE-RSA-AES128-GCM-SHA256:"
            "DHE-RSA-AES256-GCM-SHA384:"
            "ECDHE-ECDSA-AES128-SHA256:"
            "ECDHE-RSA-AES128-SHA256:"
            "ECDHE-ECDSA-AES128-SHA:"
            "ECDHE-RSA-AES256-SHA384:"
            "ECDHE-RSA-AES128-SHA:"
            "ECDHE-ECDSA-AES256-SHA384:"
            "ECDHE-ECDSA-AES256-SHA:"
            "ECDHE-RSA-AES256-SHA:"
            "DHE-RSA-AES128-SHA256:"
            "DHE-RSA-AES128-SHA:"
            "DHE-RSA-AES256-SHA256:"
            "DHE-RSA-AES256-SHA:"
            "ECDHE-ECDSA-DES-CBC3-SHA:"
            "ECDHE-RSA-DES-CBC3-SHA:"
            "EDH-RSA-DES-CBC3-SHA:"
            "AES128-GCM-SHA256:"
            "AES256-GCM-SHA384:"
            "AES128-SHA256:"
            "AES256-SHA256:"
            "AES128-SHA:"
            "AES256-SHA:"
            "DES-CBC3-SHA:"
            "!DSS"
        )
        return context

    async def start(self) -> None:
        """Start the aiohttp server."""
        # Aiohttp freezes apps after start so that no changes can be made.
        # However in Home Assistant components can be discovered after boot.
        # This will now raise a RunTimeError.
        # To work around this we now prevent the router from getting frozen
        # pylint: disable=protected-access
        self.app._router.freeze = lambda: None  # type: ignore[assignment]

        self.runner = aiohttp.web.AppRunner(self.app)
        await self.runner.setup()

        self.site = HomeAssistantTCPSite(
            self.runner, self.server_host, self.server_port, ssl_context=self.context
        )
        try:
            await self.site.start()
        except OSError as error:
            _LOGGER.error(
                "Failed to create HTTP server at port %d: %s", self.server_port, error
            )

        _LOGGER.info("Now listening on port %d", self.server_port)

    async def stop(self) -> None:
        """Stop the aiohttp server."""
        if self.site is not None:
            await self.site.stop()
        if self.runner is not None:
            await self.runner.cleanup()


class HomeAssistantTCPSite(aiohttp.web.BaseSite):
    """HomeAssistant specific aiohttp Site.

    Vanilla TCPSite accepts only str as host. However, the underlying asyncio's
    create_server() implementation does take a list of strings to bind to multiple
    host IP's. To support multiple server_host entries (e.g. to enable dual-stack
    explicitly), we would like to pass an array of strings. Bring our own
    implementation inspired by TCPSite.

    Custom TCPSite can be dropped when https://github.com/aio-libs/aiohttp/pull/4894
    is merged.
    """

    __slots__ = ("_host", "_port", "_reuse_address", "_reuse_port", "_hosturl")

    def __init__(
        self,
        runner: aiohttp.web.BaseRunner,
        host: None | str | list[str],
        port: int,
        *,
        shutdown_timeout: float = 10.0,
        ssl_context: ssl.SSLContext | None = None,
        backlog: int = 128,
        reuse_address: bool | None = None,
        reuse_port: bool | None = None,
    ) -> None:
        """Initialize HomeAssistantTCPSite."""
        super().__init__(
            runner,
            shutdown_timeout=shutdown_timeout,
            ssl_context=ssl_context,
            backlog=backlog,
        )
        self._host = host
        self._port = port
        self._reuse_address = reuse_address
        self._reuse_port = reuse_port

    @property
    def name(self) -> str:
        """Return server URL."""
        scheme = "https" if self._ssl_context else "http"
        host = self._host[0] if isinstance(self._host, list) else "0.0.0.0"
        return str(yarl.URL.build(scheme=scheme, host=host, port=self._port))

    async def start(self) -> None:
        """Start server."""
        await super().start()
        loop = asyncio.get_running_loop()
        server = self._runner.server
        assert server is not None
        self._server = await loop.create_server(
            server,
            self._host,
            self._port,
            ssl=self._ssl_context,
            backlog=self._backlog,
            reuse_address=self._reuse_address,
            reuse_port=self._reuse_port,
        )


class Integration:
    """An integration in Home Assistant."""
    _CallableT = typing.TypeVar("_CallableT", bound=typing.Callable[..., typing.Any])

    _DATA_COMPONENTS = "components"
    _DATA_INTEGRATIONS = "integrations"
    _DATA_CUSTOM_COMPONENTS = "custom_components"
    _PACKAGE_CUSTOM_COMPONENTS = "custom_components"
    _PACKAGE_BUILTIN = "homeassistant.components"
    _CUSTOM_WARNING = (
        "We found a custom integration %s which has not "
        "been tested by Home Assistant. This component might "
        "cause stability problems, be sure to disable it if you "
        "experience issues with Home Assistant"
    )

    _MAX_LOAD_CONCURRENTLY = 4

    _MOVED_ZEROCONF_PROPS = ("macaddress", "model", "manufacturer")

    @classmethod
    def resolve_from_root(
        cls, hass: HomeAssistant, root_module: typing.ModuleType, domain: str
    ) -> Integration | None:
        """Resolve an integration from a root module."""
        for base in root_module.__path__:
            manifest_path = pathlib.Path(base) / domain / "manifest.json"

            if not manifest_path.is_file():
                continue

            try:
                manifest = json.loads(manifest_path.read_text())
            except ValueError as err:
                _LOGGER.error(
                    "Error parsing manifest.json file at %s: %s", manifest_path, err
                )
                continue

            integration = cls(
                hass,
                f"{root_module.__name__}.{domain}",
                manifest_path.parent,
                manifest,
            )

            if integration.is_built_in:
                return integration

            _LOGGER.warning(Integration._CUSTOM_WARNING, integration.domain)
            if integration.version is None:
                _LOGGER.error(
                    "The custom integration '%s' does not have a "
                    "version key in the manifest file and was blocked from loading. "
                    "See https://developers.home-assistant.io/blog/2021/01/29/custom-integration-changes#versions for more details",
                    integration.domain,
                )
                return None
            try:
                asv.AwesomeVersion(
                    integration.version,
                    [
                        asv.AwesomeVersionStrategy.CALVER,
                        asv.AwesomeVersionStrategy.SEMVER,
                        asv.AwesomeVersionStrategy.SIMPLEVER,
                        asv.AwesomeVersionStrategy.BUILDVER,
                        asv.AwesomeVersionStrategy.PEP440,
                    ],
                )
            except asv.AwesomeVersionException:
                _LOGGER.error(
                    "The custom integration '%s' does not have a "
                    "valid version key (%s) in the manifest file and was blocked from loading. "
                    "See https://developers.home-assistant.io/blog/2021/01/29/custom-integration-changes#versions for more details",
                    integration.domain,
                    integration.version,
                )
                return None
            return integration

        return None

    def __init__(
        self,
        hass: HomeAssistant,
        pkg_path: str,
        file_path: pathlib.Path,
        manifest: Manifest,
    ) -> None:
        """Initialize an integration."""
        self.hass = hass
        self.pkg_path = pkg_path
        self.file_path = file_path
        self.manifest = manifest
        manifest["is_built_in"] = self.is_built_in

        if self.dependencies:
            self._all_dependencies_resolved: bool | None = None
            self._all_dependencies: set[str] | None = None
        else:
            self._all_dependencies_resolved = True
            self._all_dependencies = set()

        _LOGGER.info("Loaded %s from %s", self.domain, pkg_path)

    @property
    def name(self) -> str:
        """Return name."""
        return self.manifest["name"]

    @property
    def disabled(self) -> str | None:
        """Return reason integration is disabled."""
        return self.manifest.get("disabled")

    @property
    def domain(self) -> str:
        """Return domain."""
        return self.manifest["domain"]

    @property
    def dependencies(self) -> list[str]:
        """Return dependencies."""
        return self.manifest.get("dependencies", [])

    @property
    def after_dependencies(self) -> list[str]:
        """Return after_dependencies."""
        return self.manifest.get("after_dependencies", [])

    @property
    def requirements(self) -> list[str]:
        """Return requirements."""
        return self.manifest.get("requirements", [])

    @property
    def config_flow(self) -> bool:
        """Return config_flow."""
        return self.manifest.get("config_flow") or False

    @property
    def documentation(self) -> str | None:
        """Return documentation."""
        return self.manifest.get("documentation")

    @property
    def issue_tracker(self) -> str | None:
        """Return issue tracker link."""
        return self.manifest.get("issue_tracker")

    @property
    def loggers(self) -> list[str] | None:
        """Return list of loggers used by the integration."""
        return self.manifest.get("loggers")

    @property
    def quality_scale(self) -> str | None:
        """Return Integration Quality Scale."""
        return self.manifest.get("quality_scale")

    @property
    def iot_class(self) -> str | None:
        """Return the integration IoT Class."""
        return self.manifest.get("iot_class")

    @property
    def integration_type(self) -> typing.Literal["integration", "helper"]:
        """Return the integration type."""
        return self.manifest.get("integration_type", "integration")

    @property
    def mqtt(self) -> list[str] | None:
        """Return Integration MQTT entries."""
        return self.manifest.get("mqtt")

    @property
    def ssdp(self) -> list[dict[str, str]] | None:
        """Return Integration SSDP entries."""
        return self.manifest.get("ssdp")

    @property
    def zeroconf(self) -> list[str | dict[str, str]] | None:
        """Return Integration zeroconf entries."""
        return self.manifest.get("zeroconf")

    @property
    def dhcp(self) -> list[dict[str, str | bool]] | None:
        """Return Integration dhcp entries."""
        return self.manifest.get("dhcp")

    @property
    def usb(self) -> list[dict[str, str]] | None:
        """Return Integration usb entries."""
        return self.manifest.get("usb")

    @property
    def homekit(self) -> dict[str, list[str]] | None:
        """Return Integration homekit entries."""
        return self.manifest.get("homekit")

    @property
    def is_built_in(self) -> bool:
        """Test if package is a built-in integration."""
        return self.pkg_path.startswith(Integration._PACKAGE_BUILTIN)

    @property
    def version(self) -> asv.AwesomeVersion | None:
        """Return the version of the integration."""
        if "version" not in self.manifest:
            return None
        return asv.AwesomeVersion(self.manifest["version"])

    @property
    def all_dependencies(self) -> set[str]:
        """Return all dependencies including sub-dependencies."""
        if self._all_dependencies is None:
            raise RuntimeError("Dependencies not resolved!")

        return self._all_dependencies

    @property
    def all_dependencies_resolved(self) -> bool:
        """Return if all dependencies have been resolved."""
        return self._all_dependencies_resolved is not None

    async def resolve_dependencies(self) -> bool:
        """Resolve all dependencies."""
        if self._all_dependencies_resolved is not None:
            return self._all_dependencies_resolved

        try:
            dependencies = await self.hass._async_component_dependencies(
                self.hass, self.domain, self, set(), set()
            )
            dependencies.discard(self.domain)
            self._all_dependencies = dependencies
            self._all_dependencies_resolved = True
        except exceptions.IntegrationNotFound as err:
            _LOGGER.error(
                "Unable to resolve dependencies for %s:  we are unable to resolve (sub)dependency %s",
                self.domain,
                err.domain,
            )
            self._all_dependencies_resolved = False
        except exceptions.CircularDependency as err:
            _LOGGER.error(
                "Unable to resolve dependencies for %s:  it contains a circular dependency: %s -> %s",
                self.domain,
                err.from_domain,
                err.to_domain,
            )
            self._all_dependencies_resolved = False

        return self._all_dependencies_resolved

    def get_component(self) -> typing.ModuleType:
        """Return the component."""
        cache: dict[str, typing.ModuleType] = self.hass.data.setdefault(Integration._DATA_COMPONENTS, {})
        if self.domain in cache:
            return cache[self.domain]

        try:
            cache[self.domain] = importlib.import_module(self.pkg_path)
        except ImportError:
            raise
        except Exception as err:
            _LOGGER.exception(
                "Unexpected exception importing component %s", self.pkg_path
            )
            raise ImportError(f"Exception importing {self.pkg_path}") from err

        return cache[self.domain]

    def get_platform(self, platform_name: str) -> typing.ModuleType:
        """Return a platform for an integration."""
        cache: dict[str, typing.ModuleType] = self.hass.data.setdefault(Integration._DATA_COMPONENTS, {})
        full_name = f"{self.domain}.{platform_name}"
        if full_name in cache:
            return cache[full_name]

        try:
            cache[full_name] = self._import_platform(platform_name)
        except ImportError:
            raise
        except Exception as err:
            _LOGGER.exception(
                "Unexpected exception importing platform %s.%s",
                self.pkg_path,
                platform_name,
            )
            raise ImportError(
                f"Exception importing {self.pkg_path}.{platform_name}"
            ) from err

        return cache[full_name]

    def _import_platform(self, platform_name: str) -> typing.ModuleType:
        """Import the platform."""
        return importlib.import_module(f"{self.pkg_path}.{platform_name}")

    def __repr__(self) -> str:
        """Text representation of class."""
        return f"<Integration {self.domain}: {self.pkg_path}>"

class Manifest(typing.TypedDict, total=False):
    """
    Integration manifest.

    Note that none of the attributes are marked Optional here. However, some of them may be optional in manifest.json
    in the sense that they can be omitted altogether. But when present, they should not have null values in it.
    """
    name: str
    disabled: str
    domain: str
    integration_type: typing.Literal["integration", "helper"]
    dependencies: list[str]
    after_dependencies: list[str]
    requirements: list[str]
    config_flow: bool
    documentation: str
    issue_tracker: str
    quality_scale: str
    iot_class: str
    mqtt: list[str]
    ssdp: list[dict[str, str]]
    zeroconf: list[str | dict[str, str]]
    dhcp: list[dict[str, bool | str]]
    usb: list[dict[str, str]]
    homekit: dict[str, list[str]]
    is_built_in: bool
    version: str
    codeowners: list[str]
    loggers: list[str]

class IpBan:
    """Represents banned IP address."""

    def __init__(
        self,
        ip_ban: str | ipaddress.IPv4Address | ipaddress.IPv6Address,
        banned_at: datetime.datetime | None = None,
    ) -> None:
        """Initialize IP Ban object."""
        self.ip_address = ipaddress.ip_address(ip_ban)
        self.banned_at = banned_at or dt.utcnow()

class Secrets:
    """Store secrets while loading YAML."""

    def __init__(self, config_dir: pathlib.Path) -> None:
        """Initialize secrets."""
        self.config_dir = config_dir
        self._cache: dict[pathlib.Path, dict[str, str]] = {}

    def get(self, requester_path: str, secret: str) -> str:
        """Return the value of a secret."""
        current_path = pathlib.Path(requester_path)

        secret_dir = current_path
        while True:
            secret_dir = secret_dir.parent

            try:
                secret_dir.relative_to(self.config_dir)
            except ValueError:
                # We went above the config dir
                break

            secrets = self._load_secret_yaml(secret_dir)

            if secret in secrets:
                _LOGGER.debug(
                    "Secret %s retrieved from secrets.yaml in folder %s",
                    secret,
                    secret_dir,
                )
                return secrets[secret]

        raise exceptions.HomeAssistantError(f"Secret {secret} not defined")

    def _load_secret_yaml(self, secret_dir: pathlib.Path) -> dict[str, str]:
        """Load the secrets yaml from path."""
        if (secret_path := secret_dir / HomeAssistant._SECRET_YAML) in self._cache:
            return self._cache[secret_path]

        _LOGGER.debug("Loading %s", secret_path)
        try:
            secrets = load_yaml(str(secret_path))

            if not isinstance(secrets, dict):
                raise exceptions.HomeAssistantError("Secrets is not a dictionary")

            if "logger" in secrets:
                logger = str(secrets["logger"]).lower()
                if logger == "debug":
                    _LOGGER.setLevel(logging.DEBUG)
                else:
                    _LOGGER.error(
                        "Error in secrets.yaml: 'logger: debug' expected, but 'logger: %s' found",
                        logger,
                    )
                del secrets["logger"]
        except FileNotFoundError:
            secrets = {}

        self._cache[secret_path] = secrets

        return secrets
