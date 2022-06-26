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

import abc
import asyncio
import collections.abc
import concurrent.futures
import datetime
import functools
import logging
import multiprocessing.synchronize
import traceback
import types
import typing

from aiohttp import web

from .callback import callback
from .callback_type import CALLBACK_TYPE
from .config_type import CONFIG_TYPE
from .core_state import CoreState
from .missing_integration_frame import MissingIntegrationFrame
from .registry import Registry
from .smart_home_controller_error import SmartHomeControllerError


@typing.overload
class AreaRegistry:
    ...


@typing.overload
class AuthManager:
    ...


@typing.overload
class Components:
    ...


@typing.overload
class Config:
    ...


@typing.overload
class ConfigEntries:
    ...


@typing.overload
class DeviceRegistry:
    ...


@typing.overload
class EntityRegistry:
    ...


@typing.overload
class EventBus:
    ...


@typing.overload
class Integration:
    ...


@typing.overload
class ShcAuthProvider:
    ...


@typing.overload
class SmartHomeControllerHTTP:
    ...


@typing.overload
class SmartHomeControllerJob:
    ...


@typing.overload
class Secrets:
    ...


@typing.overload
class ServiceRegistry:
    ...


@typing.overload
class StateMachine:
    ...


@typing.overload
class Store:
    ...


_T = typing.TypeVar("_T")
_R = typing.TypeVar("_R")
_CallableT = typing.TypeVar("_CallableT", bound=typing.Callable)

_LOGGER: typing.Final = logging.getLogger(__name__)
_reported_integrations: set[str] = set()


# pylint: disable=unused-variable
@typing.overload
class SmartHomeController:
    ...


class SmartHomeController(abc.ABC):
    """
    The Base-Class for all Smart Home Controllers.

    Necessary to avoid circular imports.
    """

    INVALID_CONFIG_NOTIFICATION_ID: typing.Final = "invalid_config"

    _the_instance: SmartHomeController | None = None

    def __init__(self):
        if SmartHomeController._the_instance is not None:
            raise SmartHomeControllerError("There can be only one!")
        SmartHomeController._the_instance = self

    _DATA_COMPONENTS: typing.Final = "components"
    _DATA_INTEGRATIONS: typing.Final = "integrations"
    _DATA_CUSTOM_COMPONENTS: typing.Final = "custom_components"
    _PACKAGE_CUSTOM_COMPONENTS: typing.Final = "custom_components"
    PACKAGE_BUILTIN: typing.Final = "smart_home_tng.components"
    CUSTOM_WARNING: typing.Final = (
        "We found a custom integration %s which has not "
        + "been tested by Smart Home - The Next Generation. This component might "
        + "cause stability problems, be sure to disable it if you "
        + "experience issues with Smart Home - The Next Generation"
    )
    MAX_EXPECTED_ENTITY_IDS: typing.Final = 16384
    MAX_LOAD_CONCURRENTLY: typing.Final = 4
    SECRET_YAML: typing.Final = "secrets.yaml"
    STORAGE_DIR: typing.Final = ".storage"

    @property
    @abc.abstractmethod
    def area_registry(self) -> AreaRegistry | None:
        """Return the Area Registry for the Smart Home Controller."""

    @property
    @abc.abstractmethod
    def auth(self) -> AuthManager | None:
        """Return the Authorization Manager for the Smart Home Controller."""

    @callback
    def async_get_shc_auth_provider(self) -> ShcAuthProvider:
        """Get the provider."""
        for prv in self.auth.auth_providers:
            if prv.type == "smart_home_tng":
                return typing.cast(ShcAuthProvider, prv)
        raise RuntimeError("Provider not found")

    @property
    @abc.abstractmethod
    def bus(self) -> EventBus:
        """Return the Event Bus."""

    @property
    @abc.abstractmethod
    def components(self) -> Components:
        """Return the Components of the Smart Home Controller."""

    @property
    @abc.abstractmethod
    def config(self) -> Config:
        """Return the Core Configuration of the Smart Home Controller."""

    @property
    @abc.abstractmethod
    def config_flow_handlers(self) -> Registry:
        """Return the registered Config Flow Handlers"""

    @property
    @abc.abstractmethod
    def config_entries(self) -> ConfigEntries:
        """Return the Config Entries of the Smart Home Controller."""

    @property
    @abc.abstractmethod
    def device_registry(self) -> DeviceRegistry | None:
        """Return the Device Registry of the Smart Home Controller."""

    @property
    @abc.abstractmethod
    def entity_registry(self) -> EntityRegistry | None:
        """Return the Entity Registry of the Smart Home Controller."""

    @property
    @abc.abstractmethod
    def entity_sources(self) -> dict[str, dict[str, str]]:
        """Get the Entity Sources / Entity Info."""

    @property
    @abc.abstractmethod
    def http(self) -> SmartHomeControllerHTTP | None:
        """Get the HTTP Server of the Smart Home Controller."""

    @property
    @abc.abstractmethod
    def services(self) -> ServiceRegistry:
        """Return the Service Registry of the Smart Home Controller."""

    @property
    @abc.abstractmethod
    def states(self) -> StateMachine:
        """Return the State Machine of the Smart Home Controller."""

    @property
    @abc.abstractmethod
    def is_running(self) -> bool:
        """Return if Smart Home Controller is running."""

    # If Home Assistant is running in safe mode
    @property
    @abc.abstractmethod
    def in_safe_mode(self) -> bool:
        """Return if the Smart Home Controller running in safe mode."""

    @property
    @abc.abstractmethod
    def is_stopping(self) -> bool:
        """Return if Smart Home Controller is stopping."""

    @property
    @abc.abstractmethod
    def state(self) -> CoreState:
        """Returns the state of the Smart Home Controller."""

    @property
    @abc.abstractmethod
    def legacy_templates(self) -> bool:
        """Use legacy template behaviour?"""

    @abc.abstractmethod
    def start(self) -> int:
        """Start the Smart Home Controller.

        Note: This function is only used for testing.
        For regular use, use "await hass.run()".
        """

    @abc.abstractmethod
    async def async_get_integration(self, domain: str) -> Integration:
        """Get an integration."""

    @abc.abstractmethod
    async def async_get_custom_components(self) -> dict[str, Integration]:
        """Return list of custom integrations."""

    @abc.abstractmethod
    def async_mount_config_dir(self) -> bool:
        """Mount config dir in order to load custom_component.

        Async friendly but not a coroutine.
        """

    @abc.abstractmethod
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

    @abc.abstractmethod
    async def async_run(self, *, attach_signals: bool = True) -> int:
        """Smart Home Controller main entry point.

        Start the Smart Home Controller and block until stopped.

        This method is a coroutine.
        """

    @callback
    @abc.abstractmethod
    def async_register_signal_handling(self) -> None:
        """Register system signal handler for core."""

    @abc.abstractmethod
    async def async_start(self) -> None:
        """Finalize startup from inside the event loop.

        This method is a coroutine.
        """

    @abc.abstractmethod
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

    @callback
    @abc.abstractmethod
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

    @callback
    @abc.abstractmethod
    def async_add_shc_job(
        self,
        job: SmartHomeControllerJob[
            asyncio.coroutines.Coroutine[typing.Any, typing.Any, _R] | _R
        ],
        *args: typing.Any,
    ) -> asyncio.Future[_R] | None:
        """Add a SmartHomeControllerJob from within the event loop.

        This method must be run in the event loop.
        job: SmartHomeControllerJob to call.
        args: parameters for method to call.
        """

    @abc.abstractmethod
    def create_task(
        self, target: asyncio.coroutines.Coroutine[typing.Any, typing.Any, typing.Any]
    ) -> None:
        """Add task to the executor pool.

        target: target to call.
        """

    @callback
    @abc.abstractmethod
    def async_create_task(
        self, target: asyncio.coroutines.Coroutine[typing.Any, typing.Any, _R]
    ) -> asyncio.Task[_R]:
        """Create a task from within the eventloop.

        This method must be run in the event loop.

        target: target to call.
        """

    @callback
    @abc.abstractmethod
    def async_add_executor_job(
        self, target: typing.Callable[..., _T], *args: typing.Any
    ) -> asyncio.Future[_T]:
        """Add an executor job from within the event loop."""

    @callback
    @abc.abstractmethod
    def async_track_tasks(self) -> None:
        """Track tasks so you can wait for all tasks to be done."""

    @callback
    @abc.abstractmethod
    def async_stop_track_tasks(self) -> None:
        """Stop track tasks so you can't wait for all tasks to be done."""

    @callback
    @abc.abstractmethod
    def async_run_shc_job(
        self,
        job: SmartHomeControllerJob[
            asyncio.coroutines.Coroutine[typing.Any, typing.Any, _R] | _R
        ],
        *args: typing.Any,
    ) -> asyncio.Future[_R] | None:
        """Run a Smart Home Controller Job from within the event loop.

        This method must be run in the event loop.

        job: SmartHomeControllerJob
        args: parameters for method to call.
        """

    @callback
    @abc.abstractmethod
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

    @abc.abstractmethod
    def block_till_done(self) -> None:
        """Block until all pending work is done."""

    @abc.abstractmethod
    async def await_and_log_pending(
        pending: collections.abc.Iterable[collections.abc.Awaitable[typing.Any]],
    ) -> None:
        """Await and log tasks that take a long time."""

    @abc.abstractmethod
    async def async_block_till_done(self) -> None:
        """Block until all pending work is done."""

    @abc.abstractmethod
    def stop(self) -> None:
        """Stop Home Assistant and shuts down all threads."""

    @abc.abstractmethod
    async def async_stop(self, exit_code: int = 0, *, force: bool = False) -> None:
        """Stop Home Assistant and shuts down all threads.

        The "force" flag commands async_stop to proceed regardless of
        Home Assistant's current state. You should not set this flag
        unless you're testing.

        This method is a coroutine.
        """

    @abc.abstractmethod
    async def load_auth_provider_module(self, provider: str) -> types.ModuleType:
        """Load an auth provider."""

    @abc.abstractmethod
    async def load_mfa_module(self, module_name: str) -> types.ModuleType:
        """Load an mfa auth module."""

    @abc.abstractmethod
    def get_default_config_dir() -> str:
        """Put together the default configuration directory based on the OS."""

    @abc.abstractmethod
    async def async_ensure_config_exists(self) -> bool:
        """Ensure a configuration file exists in given configuration directory.

        Creating a default one if needed.
        Return boolean if configuration dir is ready to go.
        """

    @abc.abstractmethod
    async def async_create_default_config(self) -> bool:
        """Create a default configuration file in given configuration directory.

        Return if creation was successful.
        """

    @abc.abstractmethod
    async def async_shc_config_yaml(self) -> dict:
        """Load YAML from a Smart Home Controller configuration file.

        This function allow a component inside the asyncio loop to reload its
        configuration by itself. Include package merge.
        """

    @staticmethod
    @abc.abstractmethod
    def load_yaml_config_file(
        config_path: str, secrets: Secrets | None = None
    ) -> dict[typing.Any, typing.Any]:
        """Parse a YAML configuration file.

        Raises FileNotFoundError or NextGenerationError.

        This method needs to run in an executor.
        """

    @abc.abstractmethod
    def process_shc_config_upgrade(self) -> None:
        """Upgrade configuration if necessary.

        This method needs to run in an executor.
        """

    @callback
    @abc.abstractmethod
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

    @abc.abstractmethod
    async def async_process_shc_core_config(self, config: dict) -> None:
        """Process the core configuration section from the configuration.

        This method is a coroutine.
        """

    @abc.abstractmethod
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

    async def async_process_component_config(
        self, config: CONFIG_TYPE, integration: Integration
    ) -> CONFIG_TYPE | None:
        """Check component configuration and return processed configuration.

        Returns None on error.

        This method must be run in the event loop.
        """

    @callback
    @staticmethod
    @abc.abstractmethod
    def config_without_domain(config: CONFIG_TYPE, domain: str) -> CONFIG_TYPE:
        """Return a config with all configuration for a domain removed."""

    @abc.abstractmethod
    async def async_check_shc_config_file(self) -> str | None:
        """Check if Smart Home Controller configuration file is valid.

        This method is a coroutine.
        """

    @callback
    @abc.abstractmethod
    def async_notify_setup_error(
        self, component: str, display_link: str | None = None
    ) -> None:
        """Print a persistent notification.

        This method must be run in the event loop.
        """

    @callback
    @abc.abstractmethod
    def async_call_later(
        self,
        delay: float | datetime.timedelta,
        action: SmartHomeControllerJob[collections.abc.Awaitable[None] | None]
        | typing.Callable[[datetime.datetime], collections.abc.Awaitable[None] | None],
    ) -> CALLBACK_TYPE:
        """Add a action that is called in <delay>."""

    @abc.abstractmethod
    def call_later(
        self, delay: float, func: typing.Callable[..., typing.Any], *args: typing.Any
    ) -> asyncio.TimerHandle:
        """
        Put a delayed function call in the Event Loop
        of the Smart Home Controller.
        """

    @callback
    @abc.abstractmethod
    def async_track_time_interval(
        self,
        action: typing.Callable[
            [datetime.datetime], collections.abc.Awaitable[None] | None
        ],
        interval: datetime.timedelta,
    ) -> CALLBACK_TYPE:
        """Add a listener that fires repetitively at every timedelta interval."""

    @callback
    @abc.abstractmethod
    def async_track_point_in_utc_time(
        self,
        action: SmartHomeControllerJob[collections.abc.Awaitable[None] | None]
        | typing.Callable[[datetime.datetime], collections.abc.Awaitable[None] | None],
        point_in_time: datetime.datetime,
    ) -> CALLBACK_TYPE:
        """Add a listener that fires once after a specific point in UTC time."""

    @abc.abstractmethod
    def lookup_path(self) -> list[str]:
        """Return the lookup paths for legacy lookups."""

    @abc.abstractmethod
    def load_file(
        self, comp_or_platform: str, base_paths: list[str]
    ) -> types.ModuleType | None:
        """Try to load specified file.

        Looks in config dir first, then built-in components.
        Only returns it if also found to be valid.
        Async friendly.
        """

    @abc.abstractmethod
    async def async_get_integration_with_requirements(
        self, domain: str, done: set[str] | None = None
    ) -> Integration:
        """Get an integration with all requirements installed, including the dependencies.

        This can raise IntegrationNotFound if manifest or integration
        is invalid, RequirementNotFound if there was some type of
        failure to install requirements.
        """

    @abc.abstractmethod
    async def async_process_integration(
        self, integration: Integration, done: set[str]
    ) -> None:
        """Process an integration and requirements."""

    @callback
    @abc.abstractmethod
    def async_clear_install_history(self) -> None:
        """Forget the install history."""

    @abc.abstractmethod
    async def async_process_requirements(
        self, name: str, requirements: list[str]
    ) -> None:
        """Install the requirements for a component or platform.

        This method is a coroutine. It will raise RequirementsNotFound
        if an requirement can't be satisfied.
        """

    @abc.abstractmethod
    def pip_kwargs(config_dir: str | None) -> dict[str, typing.Any]:
        """Return keyword arguments for PIP install."""

    @staticmethod
    @abc.abstractmethod
    def is_virtual_env() -> bool:
        """Return if we run in a virtual environment."""
        # Check supports venv && virtualenv

    @staticmethod
    @abc.abstractmethod
    def is_docker_env() -> bool:
        """Return True if we run in a docker env."""

    @staticmethod
    @abc.abstractmethod
    def is_installed(package: str) -> bool:
        """Check if a package is installed and will be loaded when we import it.

        Returns True when the requirement is met.
        Returns False when the package is not installed or doesn't meet req.
        """

    @staticmethod
    @abc.abstractmethod
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

    @abc.abstractmethod
    @staticmethod
    async def async_get_user_site(deps_dir: str) -> str:
        """Return user local library path.

        This function is a coroutine.
        """

    @abc.abstractmethod
    async def async_setup_auth(
        self,
        aiohttp_app: web.Application,
        provider_configs: list[CONFIG_TYPE] | None = None,
        module_configs: list[CONFIG_TYPE] | None = None,
        setup_api=False,
    ) -> None:
        """Set up authentication and create an HTTP client."""

    @abc.abstractmethod
    async def async_setup_component(self, domain: str, config: CONFIG_TYPE) -> bool:
        """Set up a component and all its dependencies.

        This method is a coroutine.
        """

    @abc.abstractmethod
    def run_callback_threadsafe(
        callback_func: typing.Callable[..., _T],
        *args: typing.Any,
    ) -> concurrent.futures.Future[_T]:
        """Submit a callback object to the main event loop.

        Return a concurrent.futures.Future to access the result.
        """

    @abc.abstractmethod
    def run_coroutine_threadsafe(
        coro: asyncio.coroutines.Coroutine[typing.Any, typing.Any, typing.Any]
    ) -> concurrent.futures.Future[_T]:
        """Submit a coroutine object to a given event loop.

        Return a concurrent.futures.Future to access the result.
        """

    @abc.abstractmethod
    def get_url(
        self,
        *,
        require_current_request: bool = False,
        require_ssl: bool = False,
        require_standard_port: bool = False,
        allow_internal: bool = True,
        allow_external: bool = True,
        allow_ip: bool | None = None,
        prefer_external: bool | None = None,
    ) -> str:
        """Get a URL to this instance."""

    @abc.abstractmethod
    def config_path(self, *filename: str) -> str:
        """Generate path to the file within the configuration directory.

        Async friendly.
        """

    @abc.abstractmethod
    async def process_wrong_login(self, request: web.Request) -> None:
        """Process a wrong login attempt.

        Increase failed login attempts counter for remote IP address.
        Add ip ban entry if failed login attempts exceeds threshold.
        """

    @abc.abstractmethod
    def get_semaphore(
        self, key: str, counter: int
    ) -> multiprocessing.synchronize.Semaphore:
        """
        Get or create the semaphore for [key].

        If the Semaphore doesn't exist, a new one is created with [counter].
        """

    # ----------------------- Frame Helpers -------------------------------------
    def get_integration_frame(
        self,
        exclude_integrations: set | None = None,
    ) -> tuple[traceback.FrameSummary, str, str]:
        """Return the frame, integration and integration path of the current stack frame."""
        found_frame = None
        path = None
        if not exclude_integrations:
            exclude_integrations = set()

        for frame in reversed(traceback.extract_stack()):
            for path in self.lookup_path():
                try:
                    index = frame.filename.index(path)
                    start = index + len(path)
                    end = frame.filename.index("/", start)
                    integration = frame.filename[start:end]
                    if integration not in exclude_integrations:
                        found_frame = frame

                    break
                except ValueError:
                    continue

            if found_frame is not None:
                break

        if found_frame is None:
            raise MissingIntegrationFrame

        return found_frame, integration, path

    def report(
        self,
        what: str,
        exclude_integrations: set | None = None,
        error_if_core: bool = True,
        level: int = logging.WARNING,
    ) -> None:
        """Report incorrect usage.

        Async friendly.
        """
        try:
            integration_frame = self.get_integration_frame(
                exclude_integrations=exclude_integrations
            )
        except MissingIntegrationFrame as err:
            msg = f"Detected code that {what}. Please report this issue."
            if error_if_core:
                raise RuntimeError(msg) from err
            _LOGGER.warning(msg, stack_info=True)
            return

        self.report_integration(what, integration_frame, level)

    def report_integration(
        self,
        what: str,
        integration_frame: tuple[traceback.FrameSummary, str, str],
        level: int = logging.WARNING,
    ) -> None:
        """Report incorrect usage in an integration.

        Async friendly.
        """
        found_frame, integration, path = integration_frame

        # Keep track of integrations already reported to prevent flooding
        key = f"{found_frame.filename}:{found_frame.lineno}"
        if key in _reported_integrations:
            return
        _reported_integrations.add(key)

        index = found_frame.filename.index(path)
        if path == "custom_components/":
            extra = " to the custom component author"
        else:
            extra = ""

        source_code = (found_frame.line or "?").strip()
        _LOGGER.log(
            level,
            f"Detected integration that {what}. "
            + f"Please report issue{extra} for {integration} using this method at "
            + f"{found_frame.filename[index:]}, line {found_frame.lineno}: "
            + f"{source_code}",
        )

    def warn_use(self, func: _CallableT, what: str) -> _CallableT:
        """Mock a function to warn when it was about to be used."""
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def report_use(*_args: typing.Any, **_kwargs: typing.Any) -> None:
                self.report(what)

        else:

            @functools.wraps(func)
            def report_use(*_args: typing.Any, **_kwargs: typing.Any) -> None:
                self.report(what)

        return typing.cast(_CallableT, report_use)

    @staticmethod
    def report_(
        what: str,
        exclude_integrations: set | None = None,
        error_if_core: bool = True,
        level: int = logging.WARNING,
    ) -> None:
        if SmartHomeController._the_instance is not None:
            SmartHomeController._the_instance.report(
                what, exclude_integrations, error_if_core, level
            )

    @abc.abstractmethod
    async def support_entry_unload(self, domain: str) -> bool:
        """Test if a domain supports entry unloading."""

    @abc.abstractmethod
    async def support_remove_from_device(domain: str) -> bool:
        """Test if a domain supports being removed from a device."""
