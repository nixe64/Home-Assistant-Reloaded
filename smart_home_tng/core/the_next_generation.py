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

import asyncio
import collections.abc
import contextlib
import datetime
import functools
import importlib
import importlib.metadata
import logging
import os
import pathlib
import re
import shutil
import signal
import subprocess  # nosec
import sys
import threading
import time
import timeit
import types
import typing

import awesomeversion as asv
import pkg_resources
import typing_extensions
import voluptuous as vol
import voluptuous.humanize as vh
from urllib3.util import url

from ..auth import AUTH_PROVIDER_SCHEMA, MULTI_FACTOR_AUTH_MODULE_SCHEMA, AuthManager
from . import helpers
from .area_registry import AreaRegistry
from .callback import callback
from .callback_type import CALLBACK_TYPE
from .circular_dependency import CircularDependency
from .components import Components
from .config import Config
from .config_entries import ConfigEntries
from .config_flow import CONFIG_HANDLERS
from .config_source import ConfigSource
from .config_type import CONFIG_TYPE
from .config_validation import ConfigValidation as cv
from .const import Const
from .core_state import CoreState
from .dependency_error import DependencyError
from .entity_registry import EntityRegistry
from .entity_values import EntityValues
from .event import Event
from .event_bus import EventBus
from .integration import Integration
from .integration_not_found import IntegrationNotFound
from .platform import Platform
from .registry import Registry
from .requirements_not_found import RequirementsNotFound
from .secrets import Secrets
from .service_registry import ServiceRegistry
from .smart_home_controller import DeviceRegistry, SmartHomeController
from .smart_home_controller_config import SmartHomeControllerConfig
from .smart_home_controller_error import SmartHomeControllerError
from .smart_home_controller_http import SmartHomeControllerHTTP
from .smart_home_controller_job import SmartHomeControllerJob
from .smart_home_controller_job_type import SmartHomeControllerJobType
from .state_machine import StateMachine
from .store import Store
from .timeout_manager import TimeoutManager
from .unit_system import UnitSystem
from .yaml_loader import YamlLoader

_P = typing.ParamSpec("_P")
_R = typing.TypeVar("_R")
_T = typing.TypeVar("_T")

_LOGGER: typing.Final = logging.getLogger(__name__)
_BASE_PLATFORMS: typing.Final = {platform.value for platform in Platform}


# pylint: disable=unused-variable
@typing.overload
class TheNextGeneration:
    """Forward declaration"""


class TheNextGeneration(SmartHomeController):
    """Root object of the home automation."""

    # How long to wait to log tasks that are blocking
    _BLOCK_LOG_TIMEOUT: typing.Final = 60
    _DOMAIN: typing.Final = "smart_home_tng"

    _DATA_PERSISTENT_ERRORS: typing.Final = "bootstrap_persistent_errors"
    _RE_YAML_ERROR: typing.Final = re.compile(r"smart-home-tng\.util\.yaml")
    _RE_ASCII: typing.Final = re.compile(r"\033\[[^m]*m")
    _YAML_CONFIG_FILE: typing.Final = "configuration.yaml"
    _VERSION_FILE: typing.Final = ".SHC_VERSION"
    _CONFIG_DIR_NAME: typing.Final = ".smart-home-tng"
    _DATA_CUSTOMIZE: typing.Final = "shc_customize"
    # The default is too low when the internet connection is satellite or high latency
    _PIP_TIMEOUT: typing.Final = 60
    _MAX_INSTALL_FAILURES: typing.Final = 3
    _DATA_PIP_LOCK: typing.Final = "pip_lock"
    _DATA_PKG_CACHE: typing.Final = "pkg_cache"
    _DATA_INTEGRATIONS_WITH_REQS: typing.Final = "integrations_with_reqs"
    _DATA_INSTALL_FAILURE_HISTORY: typing.Final = "install_failure_history"
    _DATA_AUTH_REQS: typing.Final = "auth_prov_reqs_processed"
    _DATA_MFA_REQS: typing.Final = "mfa_auth_module_reqs_processed"

    _CONSTRAINT_FILE: typing.Final = "package_constraints.txt"
    _DISCOVERY_INTEGRATIONS: typing.Final[dict[str, collections.abc.Iterable[str]]] = {
        "dhcp": ("dhcp",),
        "mqtt": ("mqtt",),
        "ssdp": ("ssdp",),
        "zeroconf": ("zeroconf", "homekit"),
    }

    _AUTOMATION_CONFIG_PATH: typing.Final = "automations.yaml"
    _SCRIPT_CONFIG_PATH: typing.Final = "scripts.yaml"
    _SCENE_CONFIG_PATH: typing.Final = "scenes.yaml"

    _LOAD_EXCEPTIONS: typing.Final = (ImportError, FileNotFoundError)
    _INTEGRATION_LOAD_EXCEPTIONS: typing.Final = (
        IntegrationNotFound,
        RequirementsNotFound,
        *_LOAD_EXCEPTIONS,
    )
    _STAGE_1_SHUTDOWN_TIMEOUT: typing.Final = 100
    _STAGE_2_SHUTDOWN_TIMEOUT: typing.Final = 60
    _STAGE_3_SHUTDOWN_TIMEOUT: typing.Final = 30

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
    _DEFAULT_SECRETS: typing.Final = """
# Use this file to store secrets like usernames and passwords.
# Learn more at https://www.home-assistant.io/docs/configuration/secrets/
some_password: welcome
"""
    _TTS_PRE_92: typing.Final = """
tts:
- platform: google
"""
    _TTS_92: typing.Final = """
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

    _DATA_SETUP_DONE: typing.Final = "setup_done"
    _DATA_SETUP_STARTED: typing.Final = "setup_started"
    _DATA_SETUP_TIME: typing.Final = "setup_time"

    _DATA_SETUP: typing.Final = "setup_tasks"
    _DATA_DEPS_REQS: typing.Final = "deps_reqs_processed"

    _SLOW_SETUP_WARNING: typing.Final = 10
    _SLOW_SETUP_MAX_WAIT: typing.Final = 300
    _ATTR_COMPONENT: typing.Final = "component"

    def __init__(self) -> None:
        """
        Initialize new The Next Generation Smart Home Controller object.
        """
        super().__init__(self)

        self._auth: AuthManager | None = None
        self._http: SmartHomeControllerHTTP | None = None
        self._config_entries: ConfigEntries | None = None

        self._loop = asyncio.get_running_loop()
        self._pending_tasks: list[asyncio.Future[typing.Any]] = []
        self._track_task = True
        self._bus = EventBus(self, self._loop)
        self._services = ServiceRegistry(self)
        self._states = StateMachine(self._bus, self._loop)
        self._config = Config(self)
        self._components = Components(self)
        # This is a dictionary that any component can store any data on.
        self._data: dict[str, typing.Any] = {}
        self._state: CoreState = CoreState.NOT_RUNNING
        self._exit_code: int = 0
        # If not None, use to signal end-of-loop
        self._stopped: asyncio.Event | None = None
        # Timeout handler for Core/Helper namespace
        self._timeout: TimeoutManager = TimeoutManager()
        self._entity_info: dict[str, dict[str, str]] = {}
        self._area_registry: AreaRegistry | None = None
        self._entity_registry: EntityRegistry | None = None
        self._config_entries: ConfigEntries | None = None
        self._device_registry: DeviceRegistry | None = None

    @property
    def area_registry(self) -> AreaRegistry | None:
        return self._area_registry

    @property
    def auth(self) -> AuthManager | None:
        return self._auth

    @property
    def bus(self) -> EventBus:
        return self._bus

    @property
    def components(self) -> Components:
        return self._components

    @property
    def config_flow_handlers(self) -> Registry:
        return CONFIG_HANDLERS

    @property
    def services(self) -> ServiceRegistry:
        return self._services

    @property
    def states(self) -> StateMachine:
        return self._states

    @property
    def config(self) -> Config:
        return self._config

    @property
    def config_entries(self) -> ConfigEntries | None:
        return self._config_entries

    @property
    def entity_registry(self) -> EntityRegistry | None:
        return self._entity_registry

    @property
    def device_registry(self) -> DeviceRegistry | None:
        return self._device_registry

    @property
    def entity_sources(self) -> dict[str, dict[str, str]]:
        return self._entity_info

    @property
    def in_safe_mode(self) -> bool:
        """Return if the Smart Home Controller running in safe mode."""
        return self._config.safe_mode

    @property
    def is_running(self) -> bool:
        """Return if Home Assistant is running."""
        return self._state in (CoreState.STARTING, CoreState.RUNNING)

    @property
    def is_stopping(self) -> bool:
        """Return if Home Assistant is stopping."""
        return self._state in (CoreState.STOPPING, CoreState.FINAL_WRITE)

    @property
    def state(self) -> CoreState:
        return self._state

    @property
    def http(self) -> SmartHomeControllerHTTP | None:
        return self._http

    def start(self) -> int:
        """Start Home Assistant.

        Note: This function is only used for testing.
        For regular use, use "await hass.run()".
        """
        # Register the async start
        helpers.fire_coroutine_threadsafe(self.async_start(), self._loop)

        # Run forever
        # Block until stopped
        _LOGGER.info("Starting Home Assistant core loop")
        self._loop.run_forever()
        return self._exit_code

    async def _async_get_integration(self, domain: str) -> Integration:
        """Get an integration."""
        if (cache := self._data.get(self._DATA_INTEGRATIONS)) is None:
            if not self.async_mount_config_dir():
                raise IntegrationNotFound(domain)
            cache = self._data[self._DATA_INTEGRATIONS] = {}

        int_or_evt: Integration | asyncio.Event | None = cache.get(domain, None)

        if isinstance(int_or_evt, asyncio.Event):
            await int_or_evt.wait()

            if (int_or_evt := cache.get(domain, None)) is None:
                raise IntegrationNotFound(domain)

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

    async def async_get_custom_components(self) -> dict[str, Integration]:
        """Return list of custom integrations."""
        if self.in_safe_mode:
            return {}

        custom_path = pathlib.Path(
            self._config.config_dir, self._DATA_CUSTOM_COMPONENTS
        )
        if not custom_path.exists() or not custom_path.is_dir():
            return {}

        def get_sub_directories(paths: list[str]) -> list[pathlib.Path]:
            """Return all sub directories in a set of paths."""
            return [
                entry
                for path in paths
                for entry in pathlib.Path(path).iterdir()
                if entry.is_dir()
            ]

        dirs = await self.async_add_executor_job(get_sub_directories, custom_path)

        integrations = await helpers.gather_with_concurrency(
            self.MAX_LOAD_CONCURRENTLY,
            *(
                self.async_add_executor_job(
                    Integration.resolve_from_root, self, custom_path, comp.name
                )
                for comp in dirs
            ),
        )

        return {
            integration.domain: integration
            for integration in integrations
            if integration is not None
        }

    async def async_get_integration(self, domain: str) -> Integration:
        if "." in domain:
            raise ValueError(f"Invalid domain {domain}")

        # Instead of using resolve_from_root we use the cache of custom
        # components to find the integration.
        if integration := (await self.async_get_custom_components()).get(domain):
            return integration

        comp_path = pathlib.Path(".", self._DATA_COMPONENTS)

        if integration := await self.async_add_executor_job(
            Integration.resolve_from_root, self, comp_path, domain
        ):
            return integration
        raise IntegrationNotFound(domain)

    def async_mount_config_dir(self) -> bool:
        """Mount config dir in order to load custom_component.

        Async friendly but not a coroutine.
        """
        if self.config.config_dir is None:
            _LOGGER.error(
                "Can't load integrations - configuration directory is not set"
            )
            return False
        if self.config.config_dir not in sys.path:
            sys.path.insert(0, self.config.config_dir)
        return True

    async def async_component_dependencies(
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
                raise CircularDependency(domain, dependency_domain)

            loaded.add(dependency_domain)

            dep_integration = await self.async_get_integration(dependency_domain)

            if start_domain in dep_integration.after_dependencies:
                raise CircularDependency(start_domain, dependency_domain)

            if dep_integration.dependencies:
                dep_loaded = await self.async_component_dependencies(
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
        if self.state != CoreState.NOT_RUNNING:
            raise RuntimeError("Home Assistant is already running")

        # _async_stop will set this instead of stopping the loop
        self._stopped = asyncio.Event()

        await self.async_start()
        if attach_signals:
            self.async_register_signal_handling()

        await self._stopped.wait()
        return self._exit_code

    @callback
    def async_register_signal_handling(self) -> None:
        """Register system signal handler for core."""

        @callback
        def async_signal_handle(exit_code: int) -> None:
            """Wrap signal handling.

            * queue call to shutdown task
            * re-instate default handler
            """
            self._loop.remove_signal_handler(signal.SIGTERM)
            self._loop.remove_signal_handler(signal.SIGINT)
            self.async_create_task(self.async_stop(exit_code))

        try:
            self._loop.add_signal_handler(signal.SIGTERM, async_signal_handle, 0)
        except ValueError:
            _LOGGER.warning("Could not bind to SIGTERM")

        try:
            self._loop.add_signal_handler(signal.SIGINT, async_signal_handle, 0)
        except ValueError:
            _LOGGER.warning("Could not bind to SIGINT")

        try:
            self._loop.add_signal_handler(
                signal.SIGHUP, async_signal_handle, Const.RESTART_EXIT_CODE
            )
        except ValueError:
            _LOGGER.warning("Could not bind to SIGHUP")

    async def async_start(self) -> None:
        """Finalize startup from inside the event loop.

        This method is a coroutine.
        """
        _LOGGER.info("Starting Home Assistant")
        setattr(self._loop, "_thread_ident", threading.get_ident())

        self._state = CoreState.STARTING
        self.bus.async_fire(Const.EVENT_CORE_CONFIG_UPDATE)
        self.bus.async_fire(Const.EVENT_SHC_START)

        try:
            # Only block for EVENT_ASSISTANT_START listener
            self.async_stop_track_tasks()
            async with self._timeout.async_timeout(Const.TIMEOUT_EVENT_START):
                await self.async_block_till_done()
        except asyncio.TimeoutError:
            _LOGGER.warning(
                "Something is blocking Smart Home - The Next Generation from wrapping up the "
                + "start up phase. We're going to continue anyway. Please report the following "
                + "info at https://github.com/nixe64/The-Next-Generation/issues: "
                + f"{', '.join(self._config.components)}"
            )

        # Allow automations to set up the start triggers before changing state
        await asyncio.sleep(0)

        if self.state != CoreState.STARTING:
            _LOGGER.warning(
                "Smart Home - The Next Generation startup has been interrupted. "
                + "Its state may be inconsistent"
            )
            return

        self.state = CoreState.RUNNING
        self.bus.async_fire(Const.EVENT_CORE_CONFIG_UPDATE)
        self.bus.async_fire(Const.EVENT_SHC_STARTED)

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
        self._loop.call_soon_threadsafe(self.async_add_job, target, *args)

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
        return self.async_add_shc_job(SmartHomeControllerJob(target), *args)

    @callback
    def async_add_shc_job(
        self,
        job: SmartHomeControllerJob[
            asyncio.coroutines.Coroutine[typing.Any, typing.Any, _R] | _R
        ],
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
        if job.job_type == SmartHomeControllerJobType.COROUTINE_FUNCTION:
            task = self._loop.create_task(job.target(*args))
        elif job.job_type == SmartHomeControllerJobType.CALLBACK:
            self._loop.call_soon(job.target, *args)
            return None
        else:
            if typing.TYPE_CHECKING:
                task = self._loop.run_in_executor(None, job.target, *args)

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
        self._loop.call_soon_threadsafe(self.async_create_task, target)

    @callback
    def async_create_task(
        self, target: asyncio.coroutines.Coroutine[typing.Any, typing.Any, _R]
    ) -> asyncio.Task[_R]:
        """Create a task from within the eventloop.

        This method must be run in the event loop.

        target: target to call.
        """
        task = self._loop.create_task(target)

        if self._track_task:
            self._pending_tasks.append(task)

        return task

    @callback
    def async_add_executor_job(
        self, target: typing.Callable[..., _T], *args: typing.Any
    ) -> asyncio.Future[_T]:
        """Add an executor job from within the event loop."""
        task = self._loop.run_in_executor(None, target, *args)

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

    @callback
    def async_run_shc_job(
        self,
        job: SmartHomeControllerJob[
            asyncio.coroutines.Coroutine[typing.Any, typing.Any, _R] | _R
        ],
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
        if job.job_type == SmartHomeControllerJobType.CALLBACK:
            job.target(*args)
            return None

        return self.async_add_shc_job(job, *args)

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
        return self.async_run_shc_job(SmartHomeControllerJob(target), *args)

    def block_till_done(self) -> None:
        """Block until all pending work is done."""
        asyncio.run_coroutine_threadsafe(
            self.async_block_till_done(), self._loop
        ).result()

    @staticmethod
    async def await_and_log_pending(
        pending: collections.abc.Iterable[collections.abc.Awaitable[typing.Any]],
    ) -> None:
        """Await and log tasks that take a long time."""
        wait_time = 0
        done = False
        while not done:
            done, still_pending = await asyncio.wait(
                pending, timeout=TheNextGeneration._BLOCK_LOG_TIMEOUT
            )
            if done:
                return
            wait_time += TheNextGeneration._BLOCK_LOG_TIMEOUT
            for task in still_pending:
                _LOGGER.debug(f"Waited {wait_time} seconds for task: {task}")

    async def async_block_till_done(self) -> None:
        """Block until all pending work is done."""
        # To flush out any call_soon_threadsafe
        await asyncio.sleep(0)
        start_time: float | None = None

        while self._pending_tasks:
            pending = [task for task in self._pending_tasks if not task.done()]
            self._pending_tasks.clear()
            if pending:
                await self.await_and_log_pending(pending)

                if start_time is None:
                    # Avoid calling monotonic() until we know
                    # we may need to start logging blocked tasks.
                    start_time = 0
                elif start_time == 0:
                    # If we have waited twice then we set the start
                    # time
                    start_time = time.monotonic()
                elif (
                    time.monotonic() - start_time > TheNextGeneration._BLOCK_LOG_TIMEOUT
                ):
                    # We have waited at least three loops and new tasks
                    # continue to block. At this point we start
                    # logging all waiting tasks.
                    for task in pending:
                        _LOGGER.debug(f"Waiting for task: {task}")
            else:
                await asyncio.sleep(0)

    def stop(self) -> None:
        """Stop Home Assistant and shuts down all threads."""
        if self._state == CoreState.NOT_RUNNING:  # just ignore
            return
        helpers.fire_coroutine_threadsafe(self.async_stop(), self._loop)

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
            if self._state == CoreState.NOT_RUNNING:  # just ignore
                return
            if self.is_stopping:
                _LOGGER.info("Additional call to async_stop was ignored")
                return
            if self._state == CoreState.STARTING:
                # This may not work
                _LOGGER.warning(
                    "Stopping Home Assistant before startup has completed may fail"
                )

        # stage 1
        self._state = CoreState.STOPPING
        self.async_track_tasks()
        self._bus.async_fire(Const.EVENT_SHC_STOP)
        try:
            async with self._timeout.async_timeout(self._STAGE_1_SHUTDOWN_TIMEOUT):
                await self.async_block_till_done()
        except asyncio.TimeoutError:
            _LOGGER.warning(
                "Timed out waiting for shutdown stage 1 to complete, the shutdown will continue"
            )

        # stage 2
        self.state = CoreState.FINAL_WRITE
        self._bus.async_fire(Const.EVENT_SHC_FINAL_WRITE)
        try:
            async with self._timeout.async_timeout(self._STAGE_2_SHUTDOWN_TIMEOUT):
                await self.async_block_till_done()
        except asyncio.TimeoutError:
            _LOGGER.warning(
                "Timed out waiting for shutdown stage 2 to complete, the shutdown will continue"
            )

        # stage 3
        self.state = CoreState.NOT_RUNNING
        self._bus.async_fire(Const.EVENT_SHC_CLOSE)

        # Prevent run_callback_threadsafe from scheduling any additional
        # callbacks in the event loop as callbacks created on the futures
        # it returns will never run after the final `self.async_block_till_done`
        # which will cause the futures to block forever when waiting for
        # the `result()` which will cause a deadlock when shutting down the executor.
        helpers.shutdown_run_callback_threadsafe(self._loop)

        try:
            async with self._timeout.async_timeout(self._STAGE_3_SHUTDOWN_TIMEOUT):
                await self.async_block_till_done()
        except asyncio.TimeoutError:
            _LOGGER.warning(
                "Timed out waiting for shutdown stage 3 to complete, the shutdown will continue"
            )

        self._exit_code = exit_code
        self._state = CoreState.STOPPED

        if self._stopped is not None:
            self._stopped.set()

    @staticmethod
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

    @staticmethod
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

    @staticmethod
    def _filter_bad_internal_external_urls(conf: dict) -> dict:
        """Filter internal/external URL with a path."""
        for key in Const.CONF_INTERNAL_URL, Const.CONF_EXTERNAL_URL:
            if key in conf and url.parse_url(conf[key]).path not in ("", "/"):
                # We warn but do not fix, because if this was incorrectly configured,
                # adjusting this value might impact security.
                _LOGGER.warning(
                    f"Invalid {key} set. It's not allowed to have a path (/bla)"
                )

        return conf

    @staticmethod
    def get_default_config_dir() -> str:
        """Put together the default configuration directory based on the OS."""
        data_dir = os.path.expanduser("~")
        return os.path.join(data_dir, TheNextGeneration._CONFIG_DIR_NAME)

    async def async_ensure_config_exists(self) -> bool:
        """Ensure a configuration file exists in given configuration directory.

        Creating a default one if needed.
        Return boolean if configuration dir is ready to go.
        """
        config_path = self.config.path(TheNextGeneration._YAML_CONFIG_FILE)

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
            TheNextGeneration._write_default_config, self.config.config_dir
        )

    @staticmethod
    def _write_default_config(config_dir: str) -> bool:
        """Write the default config."""
        config_path = os.path.join(config_dir, TheNextGeneration._YAML_CONFIG_FILE)
        secret_path = os.path.join(config_dir, TheNextGeneration.SECRET_YAML)
        version_path = os.path.join(config_dir, TheNextGeneration._VERSION_FILE)
        automation_yaml_path = os.path.join(
            config_dir, TheNextGeneration._AUTOMATION_CONFIG_PATH
        )
        script_yaml_path = os.path.join(
            config_dir, TheNextGeneration._SCRIPT_CONFIG_PATH
        )
        scene_yaml_path = os.path.join(config_dir, TheNextGeneration._SCENE_CONFIG_PATH)

        # Writing files with YAML does not create the most human readable results
        # So we're hard coding a YAML template.
        try:
            with open(config_path, "wt", encoding="utf8") as config_file:
                config_file.write(TheNextGeneration._DEFAULT_CONFIG)

            if not os.path.isfile(secret_path):
                with open(secret_path, "wt", encoding="utf8") as secret_file:
                    secret_file.write(TheNextGeneration._DEFAULT_SECRETS)

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

    async def async_shc_config_yaml(self) -> dict:
        """Load YAML from a Home Assistant configuration file.

        This function allow a component inside the asyncio loop to reload its
        configuration by itself. Include package merge.
        """
        if self._config.config_dir is None:
            secrets = None
        else:
            secrets = Secrets(pathlib.Path(self._config.config_dir))

        # Not using async_add_executor_job because this is an internal method.
        config = await self._loop.run_in_executor(
            None,
            self.load_yaml_config_file,
            self._config.path(self._YAML_CONFIG_FILE),
            secrets,
        )
        core_config = config.get(self._DOMAIN, {})
        await self.merge_packages_config(
            config, core_config.get(Const.CONF_PACKAGES, {})
        )
        return config

    @staticmethod
    def load_yaml_config_file(
        config_path: str, secrets: Secrets | None = None
    ) -> dict[typing.Any, typing.Any]:
        """Parse a YAML configuration file.

        Raises FileNotFoundError or NextGenerationError.

        This method needs to run in an executor.
        """
        conf_dict = YamlLoader.load_yaml(config_path, secrets)

        if not isinstance(conf_dict, dict):
            msg = (
                f"The configuration file {os.path.basename(config_path)} "
                "does not contain a dictionary"
            )
            _LOGGER.error(msg)
            raise SmartHomeControllerError(msg)

        # Convert values to dictionaries if they are None
        for key, value in conf_dict.items():
            conf_dict[key] = value or {}
        return conf_dict

    def process_ha_config_upgrade(self) -> None:
        """Upgrade configuration if necessary.

        This method needs to run in an executor.
        """
        version_path = self.config.path(self._VERSION_FILE)

        try:
            with open(version_path, encoding="utf8") as inp:
                conf_version = inp.readline().strip()
        except FileNotFoundError:
            # Last version to not have this file
            conf_version = "0.7.7"

        if conf_version == Const.__version__:
            return

        _LOGGER.info(
            f"Upgrading configuration directory from {conf_version} to {Const.__version__}"
        )

        version_obj = asv.AwesomeVersion(conf_version)

        if version_obj < asv.AwesomeVersion("0.50"):
            # 0.50 introduced persistent deps dir.
            lib_path = self.config.path("deps")
            if os.path.isdir(lib_path):
                shutil.rmtree(lib_path)

        if version_obj < asv.AwesomeVersion("0.92"):
            # 0.92 moved google/tts.py to google_translate/tts.py
            config_path = self.config.path(TheNextGeneration._YAML_CONFIG_FILE)

            with open(config_path, encoding="utf-8") as config_file:
                config_raw = config_file.read()

            if TheNextGeneration._TTS_PRE_92 in config_raw:
                _LOGGER.info("Migrating google tts to google_translate tts")
                config_raw = config_raw.replace(
                    TheNextGeneration._TTS_PRE_92, TheNextGeneration._TTS_92
                )
                try:
                    with open(config_path, "wt", encoding="utf-8") as config_file:
                        config_file.write(config_raw)
                except OSError:
                    _LOGGER.exception("Migrating to google_translate tts failed")

        if (
            version_obj < asv.AwesomeVersion("0.94")
            and TheNextGeneration.is_docker_env()
        ):
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
        message, is_friendly = TheNextGeneration._format_config_error(
            ex, domain, config, link
        )
        _LOGGER.error(message, exc_info=not is_friendly and ex)

    @callback
    @staticmethod
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

        if domain != TheNextGeneration._DOMAIN and link:
            message += f"Please check the docs at {link}"

        return message, is_friendly

    async def async_process_core_config(self, config: dict) -> None:
        """Process the [TheNextGeneration] section from the configuration.

        This method is a coroutine.
        """
        config = TheNextGeneration._CORE_CONFIG_SCHEMA(config)

        # Only load auth during startup.
        if not hasattr(self, "auth"):
            if (auth_conf := config.get(Const.CONF_AUTH_PROVIDERS)) is None:
                auth_conf = [{Const.CONF_TYPE: "smart_home_tng"}]

            mfa_conf = config.get(
                Const.CONF_AUTH_MFA_MODULES,
                [
                    {
                        Const.CONF_TYPE: Const.CONF_TOTP,
                        Const.CONF_ID: Const.CONF_TOTP,
                        Const.CONF_NAME: "Authenticator app",
                    }
                ],
            )

            self.auth = await self.auth.aut_manager_from_config(
                self, auth_conf, mfa_conf
            )

        await self.config.async_load()

        tng_config = self.config

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
            tng_config.config_source = ConfigSource.YAML

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
                setattr(tng_config, attr, config[key])

        if Const.CONF_TIME_ZONE in config:
            tng_config.set_time_zone(config[Const.CONF_TIME_ZONE])

        if Const.CONF_MEDIA_DIRS not in config:
            if self.is_docker_env():
                tng_config.media_dirs = {"local": "/media"}
            else:
                tng_config.media_dirs = {"local": self.config.path("media")}

        # Init whitelist external dir
        tng_config.allowlist_external_dirs = {
            self.config.path("www"),
            *tng_config.media_dirs.values(),
        }
        if Const.CONF_ALLOWLIST_EXTERNAL_DIRS in config:
            tng_config.allowlist_external_dirs.update(
                set(config[Const.CONF_ALLOWLIST_EXTERNAL_DIRS])
            )

        elif Const.LEGACY_CONF_WHITELIST_EXTERNAL_DIRS in config:
            _LOGGER.warning(
                f"Key {Const.LEGACY_CONF_WHITELIST_EXTERNAL_DIRS} has been replaced "
                + f"with {Const.CONF_ALLOWLIST_EXTERNAL_DIRS}. Please update your config"
            )
            tng_config.allowlist_external_dirs.update(
                set(config[Const.LEGACY_CONF_WHITELIST_EXTERNAL_DIRS])
            )

        # Init whitelist external URL list – make sure to add / to every URL that doesn't
        # already have it so that we can properly test "path ownership"
        if Const.CONF_ALLOWLIST_EXTERNAL_URLS in config:
            tng_config.allowlist_external_urls.update(
                url if url.endswith("/") else f"{url}/"
                for url in config[Const.CONF_ALLOWLIST_EXTERNAL_URLS]
            )

        # Customize
        cust_exact = dict(config[Const.CONF_CUSTOMIZE])
        cust_domain = dict(config[Const.CONF_CUSTOMIZE_DOMAIN])
        cust_glob = collections.OrderedDict(config[Const.CONF_CUSTOMIZE_GLOB])

        for name, pkg in config[Const.CONF_PACKAGES].items():
            if (pkg_cust := pkg.get(self._DOMAIN)) is None:
                continue

            try:
                pkg_cust = Const.CUSTOMIZE_CONFIG_SCHEMA(pkg_cust)
            except vol.Invalid:
                _LOGGER.warning(f"Package {name} contains invalid customize")
                continue

            cust_exact.update(pkg_cust[Const.CONF_CUSTOMIZE])
            cust_domain.update(pkg_cust[Const.CONF_CUSTOMIZE_DOMAIN])
            cust_glob.update(pkg_cust[Const.CONF_CUSTOMIZE_GLOB])

        self._data[self._DATA_CUSTOMIZE] = EntityValues(
            cust_exact, cust_domain, cust_glob
        )

        if Const.CONF_UNIT_SYSTEM in config:
            if config[Const.CONF_UNIT_SYSTEM] == Const.CONF_UNIT_SYSTEM_IMPERIAL:
                tng_config.units = UnitSystem.IMPERIAL
            else:
                tng_config.units = UnitSystem.METRIC
        elif Const.CONF_TEMPERATURE_UNIT in config:
            unit = config[Const.CONF_TEMPERATURE_UNIT]
            tng_config.units = (
                UnitSystem.METRIC if unit == Const.TEMP_CELSIUS else UnitSystem.IMPERIAL
            )
            _LOGGER.warning(
                "Found deprecated temperature unit in core "
                + "configuration expected unit system. "
                + f"Replace '{Const.CONF_TEMPERATURE_UNIT}: {unit}' "
                f"with '{Const.CONF_UNIT_SYSTEM}: {tng_config.units.name}'",
            )

    @staticmethod
    def _log_pkg_error(
        package: str, component: str, config: dict, message: str
    ) -> None:
        """Log an error while merging packages."""
        message = f"Package {package} setup failed. Integration {component} {message}"

        pack_config = config[TheNextGeneration._DOMAIN][Const.CONF_PACKAGES].get(
            package, config
        )
        message += (
            f" (See {getattr(pack_config, '__config_file__', '?')}:"
            f"{getattr(pack_config, '__line__', '?')}). "
        )

        _LOGGER.error(message)

    @staticmethod
    def _identify_config_schema(module: types.ModuleType) -> str | None:
        """Extract the schema and identify list or dict based."""
        result = None
        if isinstance(module.CONFIG_SCHEMA, vol.Schema):
            schema = module.CONFIG_SCHEMA.schema

            if isinstance(schema, vol.All):
                for subschema in schema.validators:
                    if isinstance(subschema, dict):
                        schema = subschema
                        break
                else:
                    schema = None

            if schema is not None:
                try:
                    key = next(k for k in schema if k == module.DOMAIN)
                except (TypeError, AttributeError, StopIteration):
                    key = None
                except Exception:  # pylint: disable=broad-except
                    _LOGGER.exception("Unexpected error identifying config schema")
                    key = None

                if (
                    key is not None
                    and hasattr(key, "default")
                    and not isinstance(key.default, vol.schema_builder.Undefined)
                ):
                    default_value = module.CONFIG_SCHEMA(
                        {module.DOMAIN: key.default()}
                    )[module.DOMAIN]

                    if isinstance(default_value, dict):
                        result = "dict"

                    if isinstance(default_value, list):
                        result = "list"

            if result is None and schema is not None and key is not None:
                domain_schema = schema[key]

                t_schema = str(domain_schema)
                if t_schema.startswith("{") or "schema_with_slug_keys" in t_schema:
                    result = "dict"
                elif t_schema.startswith(("[", "All(<function ensure_list")):
                    result = "list"
        return result

    @staticmethod
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
                error = TheNextGeneration._recursive_merge(
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
        TheNextGeneration._PACKAGES_CONFIG_SCHEMA(packages)
        for pack_name, pack_conf in packages.items():
            for comp_name, comp_conf in pack_conf.items():
                if comp_name == self._DOMAIN:
                    continue
                # If component name is given with a trailing description, remove it
                # when looking for component
                domain = comp_name.split(" ")[0]

                try:
                    integration = await self.async_get_integration_with_requirements(
                        domain
                    )
                    component = integration.get_component()
                except TheNextGeneration._INTEGRATION_LOAD_EXCEPTIONS as ex:
                    _log_pkg_error(pack_name, comp_name, config, str(ex))
                    continue

                try:
                    config_platform: types.ModuleType | None = integration.get_platform(
                        "config"
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

                error = TheNextGeneration._recursive_merge(
                    conf=config[comp_name], package=comp_conf
                )
                if error:
                    _log_pkg_error(
                        pack_name, comp_name, config, f"has duplicate key '{error}'"
                    )

        return config

    async def async_migrator(
        self,
        old_path: str,
        store: Store,
        *,
        old_conf_load_func: typing.Callable | None = None,
        old_conf_migrate_func: typing.Callable | None = None,
    ) -> typing.Any:
        """Migrate old data to a store and then load data.

        async def old_conf_migrate_func(old_data)
        """
        # If we already have store data we have already migrated in the past.
        if (store_data := await store.async_load()) is not None:
            return store_data

        def load_old_config():
            """Load old config."""
            if not os.path.isfile(old_path):
                return None

            if old_conf_load_func is not None:
                return old_conf_load_func(old_path)

            return helpers.load_json(old_path)

        config = await self.async_add_executor_job(load_old_config)

        if config is None:
            return None

        if old_conf_migrate_func is not None:
            config = await old_conf_migrate_func(config)

        await store.async_save(config)
        await self.async_add_executor_job(os.remove, old_path)
        return config

    async def async_process_component_config(
        self, config: CONFIG_TYPE, integration: Integration
    ) -> CONFIG_TYPE | None:
        """Check component configuration and return processed configuration.

        Returns None on error.

        This method must be run in the event loop.
        """
        domain = integration.domain
        try:
            component = integration.get_component()
        except TheNextGeneration._LOAD_EXCEPTIONS as ex:
            _LOGGER.error(f"Unable to import {domain}: {ex}")
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
                _LOGGER.error(f"Error importing config platform {domain}: {err}")
                return None

        if config_validator is not None and hasattr(
            config_validator, "async_validate_config"
        ):
            try:
                return await config_validator.async_validate_config(self, config)
            except (vol.Invalid, SmartHomeControllerError) as ex:
                self.async_log_exception(ex, domain, config, integration.documentation)
                return None
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception(f"Unknown error calling {domain} config validator")
                return None

        # No custom config validator, proceed with schema validation
        if hasattr(component, "CONFIG_SCHEMA"):
            try:
                return component.CONFIG_SCHEMA(config)
            except vol.Invalid as ex:
                self.async_log_exception(ex, domain, config, integration.documentation)
                return None
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception(f"Unknown error calling {domain} CONFIG_SCHEMA")
                return None

        component_platform_schema = getattr(
            component,
            "PLATFORM_SCHEMA_BASE",
            getattr(component, "PLATFORM_SCHEMA", None),
        )

        if component_platform_schema is None:
            return config

        platforms = []
        for p_name, p_config in self.config.config_per_platform(config, domain):
            # Validate component specific platform schema
            try:
                p_validated = component_platform_schema(p_config)
            except vol.Invalid as ex:
                self.async_log_exception(
                    ex, domain, p_config, integration.documentation
                )
                continue
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception(
                    f"Unknown error validating {p_name} platform config with "
                    + f"{domain} component platform schema"
                )
                continue

            # Not all platform components follow same pattern for platforms
            # So if p_name is None we are not going to validate platform
            # (the automation component is one of them)
            if p_name is None:
                platforms.append(p_validated)
                continue

            try:
                p_integration = await self.async_get_integration_with_requirements(
                    p_name
                )
            except (
                RequirementsNotFound,
                IntegrationNotFound,
            ) as ex:
                _LOGGER.error(f"Platform error: {domain} - {ex}")
                continue

            try:
                platform = p_integration.get_platform(domain)
            except TheNextGeneration._LOAD_EXCEPTIONS:
                _LOGGER.exception(f"Platform error: {domain}")
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
                        "Unknown error validating config for "
                        + f"{p_name} platform for {domain} "
                        + "component with PLATFORM_SCHEMA"
                    )
                    continue

            platforms.append(p_validated)

        # Create a copy of the configuration with all config for current
        # component removed and add validated config back in.
        config = TheNextGeneration.config_without_domain(config, domain)
        config[domain] = platforms

        return config

    @callback
    @staticmethod
    def config_without_domain(config: CONFIG_TYPE, domain: str) -> CONFIG_TYPE:
        """Return a config with all configuration for a domain removed."""
        filter_keys = Config.extract_domain_configs(config, domain)
        return {key: value for key, value in config.items() if key not in filter_keys}

    async def async_check_tng_config_file(self) -> str | None:
        """Check if Home Assistant configuration file is valid.

        This method is a coroutine.
        """

        res = await self._async_check_tng_config_file()

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
        if (errors := self._data.get(Const.DATA_PERSISTENT_ERRORS)) is None:
            errors = self._data[Const.DATA_PERSISTENT_ERRORS] = {}

        errors[component] = errors.get(component) or display_link

        message = "The following integrations and platforms could not be set up:\n\n"

        for name, link in errors.items():
            show_logs = f"[Show logs](/config/logs?filter={name})"
            part = f"[{name}]({link})" if link else name
            message += f" - {part} ({show_logs})\n"

        message += "\nPlease check your config and [logs](/config/logs)."

        self.bus.async_fire(
            Const.EVENT_PERSISTENT_NOTIFICATION_CREATE,
            {
                "notification_id": self.INVALID_CONFIG_NOTIFICATION_ID,
                "title": "Invalid config",
                "message:": message,
            },
        )

    @staticmethod
    def threaded_listener_factory(
        async_factory: typing.Callable[
            typing_extensions.Concatenate[TheNextGeneration, _P], typing.Any
        ]
    ) -> typing.Callable[
        typing_extensions.Concatenate[TheNextGeneration, _P], CALLBACK_TYPE
    ]:
        """Convert an async event helper to a threaded one."""

        @functools.wraps(async_factory)
        def factory(
            tng: TheNextGeneration, *args: _P.args, **kwargs: _P.kwargs
        ) -> CALLBACK_TYPE:
            """Call async event helper safely."""
            if not isinstance(tng, TheNextGeneration):
                raise TypeError(
                    "First parameter needs to be a TheNextGeneration instance"
                )

            # pylint: disable=protected-access
            async_remove = helpers.run_callback_threadsafe(
                tng._loop, functools.partial(async_factory, tng, *args, **kwargs)
            ).result()

            def remove() -> None:
                """Threadsafe removal."""
                helpers.run_callback_threadsafe(tng._loop, async_remove).result()

            return remove

        return factory

    @callback
    def async_call_later(
        self,
        delay: float | datetime.timedelta,
        action: SmartHomeControllerJob[collections.abc.Awaitable[None] | None]
        | typing.Callable[[datetime.datetime], collections.abc.Awaitable[None] | None],
    ) -> CALLBACK_TYPE:
        """Add a listener that is called in <delay>."""
        if not isinstance(delay, datetime.timedelta):
            delay = datetime.timedelta(seconds=delay)
        return self.async_track_point_in_utc_time(action, helpers.utcnow() + delay)

    def call_later(
        self,
        delay: float,
        func: typing.Callable[..., typing.Any],
        *args: typing.Any,
    ) -> asyncio.TimerHandle:
        return self._loop.call_later(delay, func, args)

    @callback
    def async_track_time_interval(
        self,
        action: typing.Callable[
            [datetime.datetime], collections.abc.Awaitable[None] | None
        ],
        interval: datetime.timedelta,
    ) -> CALLBACK_TYPE:
        """Add a listener that fires repetitively at every timedelta interval."""
        remove: CALLBACK_TYPE
        interval_listener_job: SmartHomeControllerJob[None]

        job = SmartHomeControllerJob(action)

        def next_interval() -> datetime:
            """Return the next interval."""
            return helpers.utcnow() + interval

        @callback
        def interval_listener(now: datetime) -> None:
            """Handle elapsed intervals."""
            nonlocal remove
            nonlocal interval_listener_job

            remove = self.async_track_point_in_utc_time(
                interval_listener_job, next_interval()
            )
            self.async_run_shc_job(job, now)

        interval_listener_job = SmartHomeControllerJob(interval_listener)
        remove = self.async_track_point_in_utc_time(
            interval_listener_job, next_interval()
        )

        def remove_listener() -> None:
            """Remove interval listener."""
            remove()

        return remove_listener

    @callback
    def async_track_point_in_utc_time(
        self,
        action: SmartHomeControllerJob[collections.abc.Awaitable[None] | None]
        | typing.Callable[[datetime.datetime], collections.abc.Awaitable[None] | None],
        point_in_time: datetime.datetime,
    ) -> CALLBACK_TYPE:
        """Add a listener that fires once after a specific point in UTC time."""
        # Ensure point_in_time is UTC
        utc_point_in_time = helpers.as_utc(point_in_time)

        # Since this is called once, we accept a HassJob so we can avoid
        # having to figure out how to call the action every time its called.
        cancel_callback: asyncio.TimerHandle | None = None

        @callback
        def run_action(
            job: SmartHomeControllerJob[collections.abc.Awaitable[None] | None],
        ) -> None:
            """Call the action."""
            nonlocal cancel_callback

            now = helpers.utcnow()

            # Depending on the available clock support (including timer hardware
            # and the OS kernel) it can happen that we fire a little bit too early
            # as measured by utcnow(). That is bad when callbacks have assumptions
            # about the current time. Thus, we rearm the timer for the remaining
            # time.
            if (delta := (utc_point_in_time - now).total_seconds()) > 0:
                _LOGGER.debug(f"Called {delta} seconds too early, rearming")

                cancel_callback = self._loop.call_later(delta, run_action, job)
                return

            self.async_run_shc_job(job, utc_point_in_time)

        job = (
            action
            if isinstance(action, SmartHomeControllerJob)
            else SmartHomeControllerJob(action)
        )
        delta = utc_point_in_time.timestamp() - time.time()
        cancel_callback = self._loop.call_later(delta, run_action, job)

        @callback
        def unsub_point_in_time_listener() -> None:
            """Cancel the call_later."""
            assert cancel_callback is not None
            cancel_callback.cancel()

        return unsub_point_in_time_listener

    def lookup_path(self) -> list[str]:
        """Return the lookup paths for legacy lookups."""
        if self.in_safe_mode:
            return [self.PACKAGE_BUILTIN]
        return [
            self._PACKAGE_CUSTOM_COMPONENTS,
            self.PACKAGE_BUILTIN,
        ]

    def load_file(
        self, comp_or_platform: str, base_paths: list[str]
    ) -> types.ModuleType | None:
        """Try to load specified file.

        Looks in config dir first, then built-in components.
        Only returns it if also found to be valid.
        Async friendly.
        """
        with contextlib.suppress(KeyError):
            return self._data[self._DATA_COMPONENTS][comp_or_platform]

        if (cache := self._data.get(self._DATA_COMPONENTS)) is None:
            if not self.async_mount_config_dir():
                return None
            cache = self._data[TheNextGeneration._DATA_COMPONENTS] = {}

        for path in (f"{base}.{comp_or_platform}" for base in base_paths):
            try:
                module = importlib.import_module(path)

                # In Python 3 you can import files from directories that do not
                # contain the file __init__.py. A directory is a valid module if
                # it contains a file with the .py extension. In this case Python
                # will succeed in importing the directory as a module and call it
                # a namespace. We do not care about namespaces.
                # This prevents that when only
                # custom_components/switch/some_platform.py exists,
                # the import custom_components.switch would succeed.
                # __file__ was unset for namespaces before Python 3.7
                if getattr(module, "__file__", None) is None:
                    continue

                cache[comp_or_platform] = module

                return module

            except ImportError as err:
                # This error happens if for example custom_components/switch
                # exists and we try to load switch.demo.
                # Ignore errors for custom_components, custom_components.switch
                # and custom_components.switch.demo.
                white_listed_errors = []
                parts = []
                for part in path.split("."):
                    parts.append(part)
                    white_listed_errors.append(f"No module named '{'.'.join(parts)}'")

                if str(err) not in white_listed_errors:
                    _LOGGER.exception(
                        f"Error loading {path}. Make sure all dependencies are installed."
                    )
        return None

    async def async_get_integration_with_requirements(
        self, domain: str, done: set[str] | None = None
    ) -> Integration:
        """Get an integration with all requirements installed, including the dependencies.

        This can raise IntegrationNotFound if manifest or integration
        is invalid, RequirementNotFound if there was some type of
        failure to install requirements.
        """
        if done is None:
            done = {domain}
        else:
            done.add(domain)

        integration = await self.async_get_integration(domain)

        if self.config.skip_pip:
            return integration

        if (cache := self._data.get(self._DATA_INTEGRATIONS_WITH_REQS)) is None:
            cache = self._data[self._DATA_INTEGRATIONS_WITH_REQS] = {}

        int_or_evt: Integration | asyncio.Event | None = cache.get(domain, None)

        if isinstance(int_or_evt, asyncio.Event):
            await int_or_evt.wait()

            # When we have waited and it's UNDEFINED, it doesn't exist
            # We don't cache that it doesn't exist, or else people can't fix it
            # and then restart, because their config will never be valid.
            if (int_or_evt := cache.get(domain, None)) is None:
                raise IntegrationNotFound(domain)

        if int_or_evt is not None:
            return typing.cast(Integration, int_or_evt)

        event = cache[domain] = asyncio.Event()

        try:
            await self.async_process_integration(integration, done)
        except Exception:
            del cache[domain]
            event.set()
            raise

        cache[domain] = integration
        event.set()
        return integration

    async def async_process_integration(
        self, integration: Integration, done: set[str]
    ) -> None:
        """Process an integration and requirements."""
        if integration.requirements:
            await self.async_process_requirements(
                integration.domain, integration.requirements
            )

        deps_to_check = [
            dep
            for dep in integration.dependencies + integration.after_dependencies
            if dep not in done
        ]

        for check_domain, to_check in TheNextGeneration._DISCOVERY_INTEGRATIONS.items():
            if (
                check_domain not in done
                and check_domain not in deps_to_check
                and any(check in integration.manifest for check in to_check)
            ):
                deps_to_check.append(check_domain)

        if not deps_to_check:
            return

        results = await asyncio.gather(
            *(
                self.async_get_integration_with_requirements(dep, done)
                for dep in deps_to_check
            ),
            return_exceptions=True,
        )
        for result in results:
            if not isinstance(result, BaseException):
                continue
            if not isinstance(result, IntegrationNotFound) or not (
                not integration.is_built_in
                and result.domain in integration.after_dependencies
            ):
                raise result

    @callback
    def async_clear_install_history(self) -> None:
        """Forget the install history."""
        if install_failure_history := self._data.get(
            self._DATA_INSTALL_FAILURE_HISTORY
        ):
            install_failure_history.clear()

    async def async_process_requirements(
        self, name: str, requirements: list[str]
    ) -> None:
        """Install the requirements for a component or platform.

        This method is a coroutine. It will raise RequirementsNotFound
        if an requirement can't be satisfied.
        """
        if (pip_lock := self._data.get(self._DATA_PIP_LOCK)) is None:
            pip_lock = self._data[self._DATA_PIP_LOCK] = asyncio.Lock()
        install_failure_history = self._data.get(self._DATA_INSTALL_FAILURE_HISTORY)
        if install_failure_history is None:
            install_failure_history = self._data[
                self._DATA_INSTALL_FAILURE_HISTORY
            ] = set()

        kwargs = self.pip_kwargs(self._config.config_dir)

        async with pip_lock:
            for req in requirements:
                await self._async_process_requirements(
                    name, req, install_failure_history, kwargs
                )

    async def _async_process_requirements(
        self,
        name: str,
        req: str,
        install_failure_history: set[str],
        kwargs: typing.Any,
    ) -> None:
        """Install a requirement and save failures."""
        if req in install_failure_history:
            _LOGGER.info(
                f"Multiple attempts to install {req} failed, "
                + "install will be retried after next configuration check or restart"
            )
            raise RequirementsNotFound(name, [req])

        if TheNextGeneration.is_installed(req):
            return

        def _install(req: str, kwargs: dict[str, typing.Any]) -> bool:
            """Install requirement."""
            return TheNextGeneration.install_package(req, **kwargs)

        for _ in range(TheNextGeneration._MAX_INSTALL_FAILURES):
            if await self.async_add_executor_job(_install, req, kwargs):
                return

        install_failure_history.add(req)
        raise RequirementsNotFound(name, [req])

    @staticmethod
    def pip_kwargs(config_dir: str | None) -> dict[str, typing.Any]:
        """Return keyword arguments for PIP install."""
        is_docker = TheNextGeneration.is_docker_env()
        kwargs = {
            "constraints": os.path.join(
                os.path.dirname(__file__), TheNextGeneration._CONSTRAINT_FILE
            ),
            "no_cache_dir": is_docker,
            "timeout": TheNextGeneration._PIP_TIMEOUT,
        }
        if "WHEELS_LINKS" in os.environ:
            kwargs["find_links"] = os.environ["WHEELS_LINKS"]
        if (
            not (config_dir is None or TheNextGeneration.is_virtual_env())
            and not is_docker
        ):
            kwargs["target"] = os.path.join(config_dir, "deps")
        return kwargs

    @staticmethod
    def is_virtual_env() -> bool:
        """Return if we run in a virtual environment."""
        # Check supports venv && virtualenv
        return getattr(sys, "base_prefix", sys.prefix) != sys.prefix or hasattr(
            sys, "real_prefix"
        )

    @staticmethod
    def is_docker_env() -> bool:
        """Return True if we run in a docker env."""
        return pathlib.Path("/.dockerenv").exists()

    @staticmethod
    def is_installed(package: str) -> bool:
        """Check if a package is installed and will be loaded when we import it.

        Returns True when the requirement is met.
        Returns False when the package is not installed or doesn't meet req.
        """
        try:
            pkg_resources.get_distribution(package)
            return True
        except (pkg_resources.ResolutionError, pkg_resources.ExtractionError):
            req = pkg_resources.Requirement.parse(package)
        except ValueError:
            # This is a zip file. We no longer use this in Home Assistant,
            # leaving it in for custom components.
            req = pkg_resources.Requirement.parse(url.parse_url(package).fragment)

        try:
            installed_version = importlib.metadata.version(req.project_name)
            # This will happen when an install failed or
            # was aborted while in progress see
            # https://github.com/home-assistant/core/issues/47699
            if installed_version is None:
                _LOGGER.error(
                    f"Installed version for {req.project_name} resolved to None"
                )
                return False
            return installed_version in req
        except importlib.metadata.PackageNotFoundError:
            return False

    @staticmethod
    def install_package(
        package: str,
        upgrade: bool = True,
        target: str | None = None,
        constraints: str | None = None,
        find_links: str | None = None,
        install_timeout: int | None = None,
        no_cache_dir: bool | None = False,
    ) -> bool:
        """Install a package on PyPi. Accepts pip compatible package strings.

        Return boolean if install successful.
        """
        # Not using 'import pip; pip.main([])' because it breaks the logger
        _LOGGER.info(f"Attempting install of {package}")
        env = os.environ.copy()
        args = [sys.executable, "-m", "pip", "install", "--quiet", package]
        if install_timeout:
            args += ["--timeout", str(install_timeout)]
        if no_cache_dir:
            args.append("--no-cache-dir")
        if upgrade:
            args.append("--upgrade")
        if constraints is not None:
            args += ["--constraint", constraints]
        if find_links is not None:
            args += ["--find-links", find_links, "--prefer-binary"]
        if target:
            assert not TheNextGeneration.is_virtual_env()
            # This only works if not running in venv
            args += ["--user"]
            env["PYTHONUSERBASE"] = os.path.abspath(target)
            # Workaround for incompatible prefix setting
            # See http://stackoverflow.com/a/4495175
            args += ["--prefix="]
        _LOGGER.debug(f"Running pip command: args={args}")
        with subprocess.Popen(  # nosec
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        ) as process:
            _, stderr = process.communicate()
            if process.returncode != 0:
                msg = stderr.decode("utf-8").lstrip().strip()
                _LOGGER.error(f"Unable to install package {package}: {msg}")
                return False
        return True

    async def async_get_user_site(deps_dir: str) -> str:
        """Return user local library path.

        This function is a coroutine.
        """
        env = os.environ.copy()
        env["PYTHONUSERBASE"] = os.path.abspath(deps_dir)
        args = [sys.executable, "-m", "site", "--user-site"]
        process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=env,
        )
        stdout, _ = await process.communicate()
        lib_dir = stdout.decode().strip()
        return lib_dir

    async def _async_check_tng_config_file(self) -> SmartHomeControllerConfig:
        """Load and check if Home Assistant configuration file is valid.

        This method is a coroutine.
        """
        result = SmartHomeControllerConfig()
        self.async_clear_install_history()

        def _pack_error(
            package: str, component: str, config: CONFIG_TYPE, message: str
        ) -> None:
            """Handle errors from packages: _log_pkg_error."""
            message = f"Package {package} setup failed. Component {component} {message}"
            domain = f"smart-home-tng.packages.{package}.{component}"
            pack_config = core_config[Const.CONF_PACKAGES].get(package, config)
            result.add_error(message, domain, pack_config)

        def _comp_error(ex: Exception, domain: str, config: CONFIG_TYPE) -> None:
            """Handle errors from components: async_log_exception."""
            result.add_error(
                TheNextGeneration._format_config_error(ex, domain, config)[0],
                domain,
                config,
            )

        # Load configuration.yaml
        config_path = self.config.path(TheNextGeneration._YAML_CONFIG_FILE)
        try:
            if not await self.async_add_executor_job(os.path.isfile, config_path):
                return result.add_error("File configuration.yaml not found.")

            assert self.config.config_dir is not None

            config = await self.async_add_executor_job(
                TheNextGeneration.load_yaml_config_file,
                config_path,
                Secrets(pathlib.Path(self.config.config_dir)),
            )
        except FileNotFoundError:
            return result.add_error(f"File not found: {config_path}")
        except SmartHomeControllerError as err:
            return result.add_error(f"Error loading {config_path}: {err}")

        # Extract and validate core [homeassistant] config
        try:
            core_config = config.pop(self._DOMAIN, {})
            core_config = self._CORE_CONFIG_SCHEMA(core_config)
            result[self._DOMAIN] = core_config
        except vol.Invalid as err:
            result.add_error(err, self._DOMAIN, core_config)
            core_config = {}

        # Merge packages
        await self.merge_packages_config(
            config, core_config.get(Const.CONF_PACKAGES, {}), _pack_error
        )
        core_config.pop(Const.CONF_PACKAGES, None)

        # Filter out repeating config sections
        components = {key.split(" ")[0] for key in config.keys()}

        # Process and validate config
        for domain in components:
            try:
                integration = await self.async_get_integration_with_requirements(domain)
            except IntegrationNotFound as ex:
                if not self.config.safe_mode:
                    result.add_error(f"Integration error: {domain} - {ex}")
                continue
            except RequirementsNotFound as ex:
                result.add_error(f"Integration error: {domain} - {ex}")
                continue

            try:
                component = integration.get_component()
            except ImportError as ex:
                result.add_error(f"Component error: {domain} - {ex}")
                continue

            # Check if the integration has a custom config validator
            config_validator = None
            try:
                config_validator = integration.get_platform("config")
            except ImportError as err:
                # Filter out import error of the config platform.
                # If the config platform contains bad imports, make sure
                # that still fails.
                if err.name != f"{integration.pkg_path}.config":
                    result.add_error(f"Error importing config platform {domain}: {err}")
                    continue

            if config_validator is not None and hasattr(
                config_validator, "async_validate_config"
            ):
                try:
                    result[domain] = (
                        await config_validator.async_validate_config(self, config)
                    )[domain]
                    continue
                except (vol.Invalid, SmartHomeControllerError) as ex:
                    _comp_error(ex, domain, config)
                    continue
                except Exception as err:  # pylint: disable=broad-except
                    _LOGGER.exception("Unexpected error validating config")
                    result.add_error(
                        f"Unexpected error calling config validator: {err}",
                        domain,
                        config.get(domain),
                    )
                    continue

            config_schema = getattr(component, "CONFIG_SCHEMA", None)
            if config_schema is not None:
                try:
                    config = config_schema(config)
                    result[domain] = config[domain]
                except vol.Invalid as ex:
                    _comp_error(ex, domain, config)
                    continue

            component_platform_schema = getattr(
                component,
                "PLATFORM_SCHEMA_BASE",
                getattr(component, "PLATFORM_SCHEMA", None),
            )

            if component_platform_schema is None:
                continue

            platforms = []
            for p_name, p_config in Config.config_per_platform(config, domain):
                # Validate component specific platform schema
                try:
                    p_validated = component_platform_schema(p_config)
                except vol.Invalid as ex:
                    _comp_error(ex, domain, config)
                    continue

                # Not all platform components follow same pattern for platforms
                # So if p_name is None we are not going to validate platform
                # (the automation component is one of them)
                if p_name is None:
                    platforms.append(p_validated)
                    continue

                try:
                    p_integration = await self.async_get_integration_with_requirements(
                        p_name
                    )
                    platform = p_integration.get_platform(domain)
                except IntegrationNotFound as ex:
                    if not self.config.safe_mode:
                        result.add_error(f"Platform error {domain}.{p_name} - {ex}")
                    continue
                except (
                    RequirementsNotFound,
                    ImportError,
                ) as ex:
                    result.add_error(f"Platform error {domain}.{p_name} - {ex}")
                    continue

                # Validate platform specific schema
                platform_schema = getattr(platform, "PLATFORM_SCHEMA", None)
                if platform_schema is not None:
                    try:
                        p_validated = platform_schema(p_validated)
                    except vol.Invalid as ex:
                        _comp_error(ex, f"{domain}.{p_name}", p_validated)
                        continue

                platforms.append(p_validated)

            # Remove config for current component and add validated config back in.
            for filter_comp in Config.extract_domain_configs(config, domain):
                del config[filter_comp]
            result[domain] = platforms

        return result

    async def support_entry_unload(self, domain: str) -> bool:
        """Test if a domain supports entry unloading."""
        integration = await self.async_get_integration(domain)
        component = integration.get_component()
        return hasattr(component, "async_unload_entry")

    async def support_remove_from_device(self, domain: str) -> bool:
        """Test if a domain supports being removed from a device."""
        integration = await self.async_get_integration(domain)
        component = integration.get_component()
        return hasattr(component, "async_remove_config_entry_device")

    async def async_setup_component(self, domain: str, config: CONFIG_TYPE) -> bool:
        """Set up a component and all its dependencies.

        This method is a coroutine.
        """
        if domain in self._config.components:
            return True

        setup_tasks: dict[str, asyncio.Task[bool]] = self._data.setdefault(
            self._DATA_SETUP, {}
        )

        if domain in setup_tasks:
            return await setup_tasks[domain]

        task = setup_tasks[domain] = self.async_create_task(
            self._async_setup_component(domain, config)
        )

        try:
            return await task
        finally:
            if domain in self._data.get(self._DATA_SETUP_DONE, {}):
                self._data[self._DATA_SETUP_DONE].pop(domain).set()

    async def _async_process_dependencies(
        self, config: CONFIG_TYPE, integration: Integration
    ) -> list[str]:
        """Ensure all dependencies are set up.

        Returns a list of dependencies which failed to set up.
        """
        dependencies_tasks = {
            dep: self._loop.create_task(self.async_setup_component(dep, config))
            for dep in integration.dependencies
            if dep not in self._config.components
        }

        after_dependencies_tasks = {}
        to_be_loaded = self._data.get(self._DATA_SETUP_DONE, {})
        for dep in integration.after_dependencies:
            if (
                dep not in dependencies_tasks
                and dep in to_be_loaded
                and dep not in self._config.components
            ):
                after_dependencies_tasks[dep] = self._loop.create_task(
                    to_be_loaded[dep].wait()
                )

        if not dependencies_tasks and not after_dependencies_tasks:
            return []

        if dependencies_tasks:
            _LOGGER.debug(
                f"Dependency {integration.domain} will wait for dependencies "
                + f"{list(dependencies_tasks)}"
            )
        if after_dependencies_tasks:
            _LOGGER.debug(
                f"Dependency {integration.domain} will wait for after dependencies "
                + f"{list(after_dependencies_tasks)}"
            )

        async with self._timeout.async_freeze(integration.domain):
            results = await asyncio.gather(
                *dependencies_tasks.values(), *after_dependencies_tasks.values()
            )

        failed = [
            domain for idx, domain in enumerate(dependencies_tasks) if not results[idx]
        ]

        if failed:
            _LOGGER.error(
                f"Unable to set up dependencies of {integration.domain}. "
                + f"Setup failed for dependencies: {', '.join(failed)}"
            )

        return failed

    async def _async_setup_component(self, domain: str, config: CONFIG_TYPE) -> bool:
        """Set up a component for Home Assistant.

        This method is a coroutine.
        """
        integration: Integration | None = None

        def log_error(msg: str) -> None:
            """Log helper."""
            if integration is None:
                custom = ""
                link = None
            else:
                custom = "" if integration.is_built_in else "custom integration "
                link = integration.documentation
            _LOGGER.error(f"Setup failed for {custom}{domain}: {msg}")
            self.async_notify_setup_error(domain, link)

        try:
            integration = await self.async_get_integration(domain)
        except IntegrationNotFound:
            log_error("Integration not found.")
            return False

        if integration.disabled:
            log_error(f"Dependency is disabled - {integration.disabled}")
            return False

        # Validate all dependencies exist and there are no circular dependencies
        if not await integration.resolve_dependencies():
            return False

        # Process requirements as soon as possible, so we can import the component
        # without requiring imports to be in functions.
        try:
            await self.async_process_deps_reqs(config, integration)
        except SmartHomeControllerError as err:
            log_error(str(err))
            return False

        # Some integrations fail on import because they call functions incorrectly.
        # So we do it before validating config to catch these errors.
        try:
            component = integration.get_component()
        except ImportError as err:
            log_error(f"Unable to import component: {err}")
            return False

        processed_config = await self.async_process_component_config(
            config, integration
        )

        if processed_config is None:
            log_error("Invalid config.")
            return False

        start = timeit.default_timer()
        _LOGGER.info(f"Setting up {domain}")
        with self.async_start_setup([domain]):
            if hasattr(component, "PLATFORM_SCHEMA"):
                # Entity components have their own warning
                warn_task = None
            else:
                warn_task = self._loop.call_later(
                    self._SLOW_SETUP_WARNING,
                    _LOGGER.warning,
                    f"Setup of{domain} is taking over {self._SLOW_SETUP_WARNING} seconds.",
                )

            task = None
            result: typing.Any | bool = True
            try:
                if hasattr(component, "async_setup"):
                    task = component.async_setup(self, processed_config)
                elif hasattr(component, "setup"):
                    # This should not be replaced with hass.async_add_executor_job because
                    # we don't want to track this task in case it blocks startup.
                    task = self._loop.run_in_executor(
                        None, component.setup, self, processed_config
                    )
                elif not hasattr(component, "async_setup_entry"):
                    log_error("No setup or config entry setup function defined.")
                    return False

                if task:
                    async with self._timeout.async_timeout(
                        self._SLOW_SETUP_MAX_WAIT, domain
                    ):
                        result = await task
            except asyncio.TimeoutError:
                _LOGGER.error(
                    f"Setup of {domain} is taking longer than {self._SLOW_SETUP_MAX_WAIT} seconds."
                    + " Startup will proceed without waiting any longer"
                )
                return False
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception(f"Error during setup of component {domain}")
                self.async_notify_setup_error(domain, integration.documentation)
                return False
            finally:
                end = timeit.default_timer()
                if warn_task:
                    warn_task.cancel()
            _LOGGER.info(f"Setup of domain {domain} took {end - start}.1f seconds")

            if result is False:
                log_error("Integration failed to initialize.")
                return False
            if result is not True:
                log_error(
                    f"Integration {domain!r} did not return boolean if setup was "
                    "successful. Disabling component."
                )
                return False

            # Flush out async_setup calling create_task. Fragile but covered by test.
            await asyncio.sleep(0)
            await self._config_entries.flow.async_wait_init_flow_finish(domain)

            await asyncio.gather(
                *(
                    entry.async_setup(self, integration=integration)
                    for entry in self._config_entries.async_entries(domain)
                )
            )

            self._config.components.add(domain)

        # Cleanup
        if domain in self._data[self._DATA_SETUP]:
            self._data[self._DATA_SETUP].pop(domain)

        self._bus.async_fire(
            Const.EVENT_COMPONENT_LOADED, {self._ATTR_COMPONENT: domain}
        )

        return True

    async def async_process_deps_reqs(
        self, config: CONFIG_TYPE, integration: Integration
    ) -> None:
        """Process all dependencies and requirements for a module.

        Module is a Python module of either a component or platform.
        """
        if (processed := self._data.get(self._DATA_DEPS_REQS)) is None:
            processed = self._data[self._DATA_DEPS_REQS] = set()
        elif integration.domain in processed:
            return

        if failed_deps := await self._async_process_dependencies(config, integration):
            raise DependencyError(failed_deps)

        if not self._config.skip_pip and integration.requirements:
            async with self._timeout.async_freeze(integration.domain):
                await self.async_get_integration_with_requirements(integration.domain)

        processed.add(integration.domain)

    @contextlib.contextmanager
    def async_start_setup(
        self, components: collections.abc.Iterable[str]
    ) -> collections.abc.Generator[None, None, None]:
        """Keep track of when setup starts and finishes."""
        setup_started = self._data.setdefault(self._DATA_SETUP_STARTED, {})
        started = helpers.utcnow()
        unique_components: dict[str, str] = {}
        for domain in components:
            unique = helpers.ensure_unique_string(domain, setup_started)
            unique_components[unique] = domain
            setup_started[unique] = started

        yield

        setup_time: dict[str, datetime.timedelta] = self._data.setdefault(
            self._DATA_SETUP_TIME, {}
        )
        time_taken = helpers.utcnow() - started
        for unique, domain in unique_components.items():
            del setup_started[unique]
            if "." in domain:
                _, integration = domain.split(".", 1)
            else:
                integration = domain
            if integration in setup_time:
                setup_time[integration] += time_taken
            else:
                setup_time[integration] = time_taken

    @callback
    def async_when_setup(
        self,
        component: str,
        when_setup_cb: typing.Callable[
            [SmartHomeController, str], collections.abc.Awaitable[None]
        ],
    ) -> None:
        """Call a method when a component is setup."""
        self._async_when_setup(component, when_setup_cb, False)

    @callback
    def async_when_setup_or_start(
        self,
        component: str,
        when_setup_cb: typing.Callable[
            [SmartHomeController, str], collections.abc.Awaitable[None]
        ],
    ) -> None:
        """Call a method when a component is setup or state is fired."""
        self._async_when_setup(component, when_setup_cb, True)

    @callback
    def _async_when_setup(
        self,
        component: str,
        when_setup_cb: typing.Callable[
            [SmartHomeController, str], collections.abc.Awaitable[None]
        ],
        start_event: bool,
    ) -> None:
        """Call a method when a component is setup or the start event fires."""

        async def when_setup() -> None:
            """Call the callback."""
            try:
                await when_setup_cb(self, component)
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception(f"Error handling when_setup callback for {component}")

        if component in self._config.components:
            self.async_create_task(when_setup())
            return

        listeners: list[CALLBACK_TYPE] = []

        async def _matched_event(_event: Event) -> None:
            """Call the callback when we matched an event."""
            for listener in listeners:
                listener()
            await when_setup()

        async def _loaded_event(event: Event) -> None:
            """Call the callback if we loaded the expected component."""
            if event.data[self._ATTR_COMPONENT] == component:
                await _matched_event(event)

        listeners.append(
            self._bus.async_listen(Const.EVENT_COMPONENT_LOADED, _loaded_event)
        )
        if start_event:
            listeners.append(
                self._bus.async_listen(Const.EVENT_SHC_START, _matched_event)
            )

    @callback
    def async_get_loaded_integrations(self) -> set[str]:
        """Return the complete list of loaded integrations."""
        integrations = set()
        for component in self._config.components:
            if "." not in component:
                integrations.add(component)
                continue
            domain, platform = component.split(".", 1)
            if domain in _BASE_PLATFORMS:
                integrations.add(platform)
        return integrations

    async def load_auth_provider_module(self, provider: str) -> types.ModuleType:
        """Load an auth provider."""
        try:
            module = importlib.import_module(
                f"smart_home_tng.auth.providers.{provider}"
            )
        except ImportError as err:
            _LOGGER.error(f"Unable to load auth provider {provider}: {err}")
            raise SmartHomeControllerError(
                f"Unable to load auth provider {provider}: {err}"
            ) from err

        if self._config.skip_pip or not hasattr(module, "REQUIREMENTS"):
            return module

        if (processed := self._data.get(self._DATA_AUTH_REQS)) is None:
            processed = self._data[self._DATA_AUTH_REQS] = set()
        elif provider in processed:
            return module

        reqs = module.REQUIREMENTS
        await self.async_process_requirements(f"auth provider {provider}", reqs)

        processed.add(provider)
        return module

    async def load_mfa_module(self, module_name: str) -> types.ModuleType:
        """Load an mfa auth module."""
        module_path = f"smart_home_tng.auth.mfa_modules.{module_name}"

        try:
            module = importlib.import_module(module_path)
        except ImportError as err:
            _LOGGER.error(f"Unable to load mfa module {module_name}: {err}")
            raise SmartHomeControllerError(
                f"Unable to load mfa module {module_name}: {err}"
            ) from err

        if self._config.skip_pip or not hasattr(module, "REQUIREMENTS"):
            return module

        processed = self._data.get(self._DATA_MFA_REQS)
        if processed and module_name in processed:
            return module

        processed = self._data[self._DATA_MFA_REQS] = set()

        await self.async_process_requirements(module_path, module.REQUIREMENTS)

        processed.add(module_name)
        return module

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
                        AUTH_PROVIDER_SCHEMA.extend(
                            {
                                Const.CONF_TYPE: vol.NotIn(
                                    ["insecure_example"],
                                    "The insecure_example auth provider"
                                    + " is for testing only.",
                                )
                            }
                        )
                    ],
                    _no_duplicate_auth_provider,
                ),
                vol.Optional(Const.CONF_AUTH_MFA_MODULES): vol.All(
                    cv.ensure_list,
                    [
                        MULTI_FACTOR_AUTH_MODULE_SCHEMA.extend(
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
