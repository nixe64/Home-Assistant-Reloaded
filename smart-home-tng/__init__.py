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
import aiohttp.hdrs
import asyncio
import attr
import collections.abc
import datetime
import enum
import functools
import logging
import numbers
import os
import pathlib
import re
import strenum
import typing
import urllib3.util.url as url
import voluptuous as vol
import yarl
#from .helpers.storage import Store

from . import core, util, exceptions
from .util import io, dt, location

_R_co = typing.TypeVar("_R_co", covariant=True)
_CallableT = typing.TypeVar("_CallableT", bound=typing.Callable[..., typing.Any])
_CALLBACK_TYPE = typing.Callable[[], None] 
_StateT = typing.TypeVar("_StateT", bound="State")

_LOGGER = logging.getLogger(__name__)

def callback(func: _CallableT) -> _CallableT:
    """Annotation to mark method as safe to call from within the event loop."""
    setattr(func, "_hass_callback", True)
    return func


def is_callback(func: typing.Callable[..., typing.Any]) -> bool:
    """Check if function is safe to be called in the event loop."""
    return getattr(func, "_hass_callback", False) is True

class ApiConfig:
    """Configuration settings for API server."""

    def __init__(
        self,
        local_ip: str,
        host: str,
        port: int,
        use_ssl: bool,
    ) -> None:
        """Initialize a new API config object."""
        self.local_ip = local_ip
        self.host = host
        self.port = port
        self.use_ssl = use_ssl


class Config:
    """Configuration settings for Home Assistant."""

    def __init__(self, hass: core.HomeAssistant) -> None:
        """Initialize a new config object."""
        self.hass = hass

        self.latitude: float = 0
        self.longitude: float = 0
        self.elevation: int = 0
        self.location_name: str = "Home"
        self.time_zone: str = "UTC"
        self.units: UnitSystem = UnitSystem.METRIC
        self.internal_url: str | None = None
        self.external_url: str | None = None
        self.currency: str = "EUR"

        self.config_source: ConfigSource = ConfigSource.DEFAULT

        # If True, pip install is skipped for requirements on startup
        self.skip_pip: bool = False

        # List of loaded components
        self.components: set[str] = set()

        # API (HTTP) server configuration
        self.api: ApiConfig | None = None

        # Directory that holds the configuration
        self.config_dir: str | None = None

        # List of allowed external dirs to access
        self.allowlist_external_dirs: set[str] = set()

        # List of allowed external URLs that integrations may use
        self.allowlist_external_urls: set[str] = set()

        # Dictionary of Media folders that integrations may use
        self.media_dirs: dict[str, str] = {}

        # If Home Assistant is running in safe mode
        self.safe_mode: bool = False

        # Use legacy template behavior
        self.legacy_templates: bool = False

    def distance(self, lat: float, lon: float) -> float | None:
        """Calculate distance from Home Assistant.

        Async friendly.
        """
        return self.units.length(
            location.distance(self.latitude, self.longitude, lat, lon), Const.LENGTH_METERS
        )

    def path(self, *path: str) -> str:
        """Generate path to the file within the configuration directory.

        Async friendly.
        """
        if self.config_dir is None:
            raise exceptions.HomeAssistantError("config_dir is not set")
        return os.path.join(self.config_dir, *path)

    def is_allowed_external_url(self, url: str) -> bool:
        """Check if an external URL is allowed."""
        parsed_url = f"{str(yarl.URL(url))}/"

        return any(
            allowed
            for allowed in self.allowlist_external_urls
            if parsed_url.startswith(allowed)
        )

    def is_allowed_path(self, path: str) -> bool:
        """Check if the path is valid for access from outside."""
        assert path is not None

        thepath = pathlib.Path(path)
        try:
            # The file path does not have to exist (it's parent should)
            if thepath.exists():
                thepath = thepath.resolve()
            else:
                thepath = thepath.parent.resolve()
        except (FileNotFoundError, RuntimeError, PermissionError):
            return False

        for allowed_path in self.allowlist_external_dirs:
            try:
                thepath.relative_to(allowed_path)
                return True
            except ValueError:
                pass

        return False

    def as_dict(self) -> dict[str, typing.Any]:
        """Create a dictionary representation of the configuration.

        Async friendly.
        """
        return {
            Const.CONF_LATITUDE: self.latitude,
            Const.CONF_LONGITUDE: self.longitude,
            Const.CONF_ELEVATION: self.elevation,
            Const.CONF_UNIT_SYSTEM: self.units.as_dict(),
            Const.CONF_LOCATION_NAME: self.location_name,
            Const.CONF_TIME_ZONE: self.time_zone,
            Const.CONF_COMPONENTS: self.components,
            Const.CONF_CONFIG_DIR: self.config_dir,
            # legacy, backwards compat
            Const.LEGACY_CONF_WHITELIST_EXTERNAL_DIRS: self.allowlist_external_dirs,
            Const.CONF_ALLOWLIST_EXTERNAL_DIRS: self.allowlist_external_dirs,
            Const.CONF_ALLOWLIST_EXTERNAL_URLS: self.allowlist_external_urls,
            Const.CONF_VERSION: Const.__version__,
            Const.CONF_CONFIG_SOURCE: self.config_source,
            Const.CONF_SAFE_MODE: self.safe_mode,
            Const.CONF_STATE: self.hass.state.value,
            Const.CONF_EXTERNAL_URL: self.external_url,
            Const.CONF_INTERNAL_URL: self.internal_url,
            Const.CONF_CURRENCY: self.currency,
        }

    def set_time_zone(self, time_zone_str: str) -> None:
        """Help to set the time zone."""
        if time_zone := dt.get_time_zone(time_zone_str):
            self.time_zone = time_zone_str
            dt.set_default_time_zone(time_zone)
        else:
            raise ValueError(f"Received invalid time zone {time_zone_str}")

    @callback
    def _update(
        self,
        *,
        source: ConfigSource,
        latitude: float | None = None,
        longitude: float | None = None,
        elevation: int | None = None,
        unit_system: str | None = None,
        location_name: str | None = None,
        time_zone: str | None = None,
        external_url: str | dict[typing.Any, typing.Any] | None = None,
        internal_url: str | dict[typing.Any, typing.Any] | None = None,
        currency: str | None = None,
    ) -> None:
        """Update the configuration from a dictionary."""
        self.config_source = source
        if latitude is not None:
            self.latitude = latitude
        if longitude is not None:
            self.longitude = longitude
        if elevation is not None:
            self.elevation = elevation
        if unit_system is not None:
            if unit_system == Const.CONF_UNIT_SYSTEM_IMPERIAL:
                self.units = UnitSystem.IMPERIAL
            else:
                self.units = UnitSystem.METRIC
        if location_name is not None:
            self.location_name = location_name
        if time_zone is not None:
            self.set_time_zone(time_zone)
        if external_url is not None:
            self.external_url = typing.cast(typing.Optional[str], external_url)
        if internal_url is not None:
            self.internal_url = typing.cast(typing.Optional[str], internal_url)
        if currency is not None:
            self.currency = currency

    async def async_update(self, **kwargs: typing.Any) -> None:
        """Update the configuration from a dictionary."""
        self._update(source=ConfigSource.STORAGE, **kwargs)
        await self.async_store()
        self.hass.bus.async_fire(Const.EVENT_CORE_CONFIG_UPDATE, kwargs)

    async def async_load(self) -> None:
        """Load [homeassistant] core config."""
        # Circular dep
        # pylint: disable=import-outside-toplevel
        from .helpers.storage import Store

        store = Store(
            self.hass,
            Const.CORE_STORAGE_VERSION,
            Const.CORE_STORAGE_KEY,
            private=True,
            atomic_writes=True,
        )

        if not (data := await store.async_load()) or not isinstance(data, dict):
            return

        # In 2021.9 we fixed validation to disallow a path (because that's never correct)
        # but this data still lives in storage, so we print a warning.
        if data.get("external_url") and url.parse_url(data["external_url"]).path not in (
            "",
            "/",
        ):
            _LOGGER.warning("Invalid external_url set. It's not allowed to have a path")

        if data.get("internal_url") and url.parse_url(data["internal_url"]).path not in (
            "",
            "/",
        ):
            _LOGGER.warning("Invalid internal_url set. It's not allowed to have a path")

        self._update(
            source=ConfigSource.STORAGE,
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            elevation=data.get("elevation"),
            unit_system=data.get("unit_system"),
            location_name=data.get("location_name"),
            time_zone=data.get("time_zone"),
            external_url=data.get("external_url", None),
            internal_url=data.get("internal_url", None),
            currency=data.get("currency"),
        )

    async def async_store(self) -> None:
        """Store [homeassistant] core config."""
        data = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "elevation": self.elevation,
            "unit_system": self.units.name,
            "location_name": self.location_name,
            "time_zone": self.time_zone,
            "external_url": self.external_url,
            "internal_url": self.internal_url,
            "currency": self.currency,
        }

        store = Store(
            self.hass,
            Const.CORE_STORAGE_VERSION,
            Const.CORE_STORAGE_KEY,
            private=True,
            atomic_writes=True,
        )
        await store.async_save(data)

    def config_per_platform(self, domain: str) -> collections.abc.Iterable[tuple[str | None, ConfigType]]:
        """Break a component config into different platforms.

        For example, will find 'switch', 'switch 2', 'switch 3', .. etc
        Async friendly.
        """
        for config_key in self.extract_domain_configs(domain):
            if not (platform_config := self[config_key]):
                continue

            if not isinstance(platform_config, list):
                platform_config = [platform_config]

            item: ConfigType
            platform: str | None
            for item in platform_config:
                try:
                    platform = item.get(Const.CONF_PLATFORM)
                except AttributeError:
                    platform = None

                yield platform, item


    def extract_domain_configs(config: ConfigType, domain: str) -> collections.abc.Sequence[str]:
        """Extract keys from config for given domain name.

        Async friendly.
        """
        pattern = re.compile(rf"^{domain}(| .+)$")
        return [key for key in config.keys() if pattern.match(key)]

class ConfigSource(strenum.StrEnum):
    """Source of core configuration."""
    DEFAULT = "default"
    DISCOVERED = "discovered"
    STORAGE = "storage"
    YAML = "yaml"

class Const:
    MAJOR_VERSION: typing.Final = 2022
    MINOR_VERSION: typing.Final = 6
    PATCH_VERSION: typing.Final = "0.dev0"
    __short_version__: typing.Final = f"{MAJOR_VERSION}.{MINOR_VERSION}"
    __version__: typing.Final = f"{__short_version__}.{PATCH_VERSION}"
    REQUIRED_PYTHON_VER: typing.Final[tuple[int, int, int]] = (3, 9, 0)
    REQUIRED_NEXT_PYTHON_VER: typing.Final[tuple[int, int, int]] = (3, 9, 0)
    # Truthy date string triggers showing related deprecation warning messages.
    REQUIRED_NEXT_PYTHON_HA_RELEASE: typing.Final = ""

    # Format for platform files
    PLATFORM_FORMAT: typing.Final = "{platform}.{domain}"

    # Can be used to specify a catch all when registering state or event listeners.
    MATCH_ALL: typing.Final = "*"

    # Entity target all constant
    ENTITY_MATCH_NONE: typing.Final = "none"
    ENTITY_MATCH_ALL: typing.Final = "all"
    ENTITY_MATCH_ANY: typing.Final = "any"

    # If no name is specified
    DEVICE_DEFAULT_NAME: typing.Final = "Unnamed Device"

    # Max characters for data stored in the recorder (changes to these limits would require
    # a database migration)
    MAX_LENGTH_EVENT_EVENT_TYPE: typing.Final = 64
    MAX_LENGTH_EVENT_ORIGIN: typing.Final = 32
    MAX_LENGTH_EVENT_CONTEXT_ID: typing.Final = 36
    MAX_LENGTH_STATE_DOMAIN: typing.Final = 64
    MAX_LENGTH_STATE_ENTITY_ID: typing.Final = 255
    MAX_LENGTH_STATE_STATE: typing.Final = 255

    # Sun events
    SUN_EVENT_SUNSET: typing.Final = "sunset"
    SUN_EVENT_SUNRISE: typing.Final = "sunrise"

    # Cache Headers
    CACHE_TIME: typing.Final = 31 * 86400  # = 1 month
    CACHE_HEADERS: typing.Final[collections.abc.Mapping[str, str]] = {
        aiohttp.hdrs.CACHE_CONTROL: f"public, max-age={CACHE_TIME}"
    }

    CONF_SERVER_HOST: typing.Final = "server_host"
    CONF_SERVER_PORT: typing.Final = "server_port"
    CONF_BASE_URL: typing.Final = "base_url"
    CONF_SSL_CERTIFICATE: typing.Final = "ssl_certificate"
    CONF_SSL_PEER_CERTIFICATE: typing.Final = "ssl_peer_certificate"
    CONF_SSL_KEY: typing.Final = "ssl_key"
    CONF_CORS_ORIGINS: typing.Final = "cors_allowed_origins"
    CONF_USE_X_FORWARDED_FOR: typing.Final = "use_x_forwarded_for"
    CONF_TRUSTED_PROXIES: typing.Final = "trusted_proxies"
    CONF_LOGIN_ATTEMPTS_THRESHOLD: typing.Final = "login_attempts_threshold"
    CONF_IP_BAN_ENABLED: typing.Final = "ip_ban_enabled"
    CONF_SSL_PROFILE: typing.Final = "ssl_profile"

    SSL_MODERN: typing.Final = "modern"
    SSL_INTERMEDIATE: typing.Final = "intermediate"

    # #### CONFIG ####
    CONF_ABOVE: typing.Final = "above"
    CONF_ACCESS_TOKEN: typing.Final = "access_token"
    CONF_ADDRESS: typing.Final = "address"
    CONF_AFTER: typing.Final = "after"
    CONF_ALIAS: typing.Final = "alias"
    CONF_ALLOWLIST_EXTERNAL_URLS: typing.Final = "allowlist_external_urls"
    CONF_API_KEY: typing.Final = "api_key"
    CONF_API_TOKEN: typing.Final = "api_token"
    CONF_API_VERSION: typing.Final = "api_version"
    CONF_ARMING_TIME: typing.Final = "arming_time"
    CONF_AT: typing.Final = "at"
    CONF_ATTRIBUTE: typing.Final = "attribute"
    CONF_AUTH_MFA_MODULES: typing.Final = "auth_mfa_modules"
    CONF_AUTH_PROVIDERS: typing.Final = "auth_providers"
    CONF_AUTHENTICATION: typing.Final = "authentication"
    CONF_BASE: typing.Final = "base"
    CONF_BEFORE: typing.Final = "before"
    CONF_BELOW: typing.Final = "below"
    CONF_BINARY_SENSORS: typing.Final = "binary_sensors"
    CONF_BRIGHTNESS: typing.Final = "brightness"
    CONF_BROADCAST_ADDRESS: typing.Final = "broadcast_address"
    CONF_BROADCAST_PORT: typing.Final = "broadcast_port"
    CONF_CHOOSE: typing.Final = "choose"
    CONF_CLIENT_ID: typing.Final = "client_id"
    CONF_CLIENT_SECRET: typing.Final = "client_secret"
    CONF_CODE: typing.Final = "code"
    CONF_COLOR_TEMP: typing.Final = "color_temp"
    CONF_COMMAND: typing.Final = "command"
    CONF_COMMAND_CLOSE: typing.Final = "command_close"
    CONF_COMMAND_OFF: typing.Final = "command_off"
    CONF_COMMAND_ON: typing.Final = "command_on"
    CONF_COMMAND_OPEN: typing.Final = "command_open"
    CONF_COMMAND_STATE: typing.Final = "command_state"
    CONF_COMMAND_STOP: typing.Final = "command_stop"
    CONF_COMPONENTS: typing.Final = "components"
    CONF_CONDITION: typing.Final = "condition"
    CONF_CONDITIONS: typing.Final = "conditions"
    CONF_CONFIG_DIR: typing.Final = "config_dir"
    CONF_CONFIG_SOURCE: typing.Final = "config_source"
    CONF_CONTINUE_ON_ERROR: typing.Final = "continue_on_error"
    CONF_CONTINUE_ON_TIMEOUT: typing.Final = "continue_on_timeout"
    CONF_COUNT: typing.Final = "count"
    CONF_COVERS: typing.Final = "covers"
    CONF_CURRENCY: typing.Final = "currency"
    CONF_CUSTOMIZE: typing.Final = "customize"
    CONF_CUSTOMIZE_DOMAIN: typing.Final = "customize_domain"
    CONF_CUSTOMIZE_GLOB: typing.Final = "customize_glob"
    CONF_DEFAULT: typing.Final = "default"
    CONF_DELAY: typing.Final = "delay"
    CONF_DELAY_TIME: typing.Final = "delay_time"
    CONF_DESCRIPTION: typing.Final = "description"
    CONF_DEVICE: typing.Final = "device"
    CONF_DEVICES: typing.Final = "devices"
    CONF_DEVICE_CLASS: typing.Final = "device_class"
    CONF_DEVICE_ID: typing.Final = "device_id"
    CONF_DISARM_AFTER_TRIGGER: typing.Final = "disarm_after_trigger"
    CONF_DISCOVERY: typing.Final = "discovery"
    CONF_DISKS: typing.Final = "disks"
    CONF_DISPLAY_CURRENCY: typing.Final = "display_currency"
    CONF_DISPLAY_OPTIONS: typing.Final = "display_options"
    CONF_DOMAIN: typing.Final = "domain"
    CONF_DOMAINS: typing.Final = "domains"
    CONF_EFFECT: typing.Final = "effect"
    CONF_ELEVATION: typing.Final = "elevation"
    CONF_ELSE: typing.Final = "else"
    CONF_EMAIL: typing.Final = "email"
    CONF_ENABLED: typing.Final = "enabled"
    CONF_ENTITIES: typing.Final = "entities"
    CONF_ENTITY_CATEGORY: typing.Final = "entity_category"
    CONF_ENTITY_ID: typing.Final = "entity_id"
    CONF_ENTITY_NAMESPACE: typing.Final = "entity_namespace"
    CONF_ENTITY_PICTURE_TEMPLATE: typing.Final = "entity_picture_template"
    CONF_ERROR: typing.Final = "error"
    CONF_EVENT: typing.Final = "event"
    CONF_EVENT_DATA: typing.Final = "event_data"
    CONF_EVENT_DATA_TEMPLATE: typing.Final = "event_data_template"
    CONF_EXCLUDE: typing.Final = "exclude"
    CONF_EXTERNAL_URL: typing.Final = "external_url"
    CONF_FILENAME: typing.Final = "filename"
    CONF_FILE_PATH: typing.Final = "file_path"
    CONF_FOR: typing.Final = "for"
    CONF_FOR_EACH: typing.Final = "for_each"
    CONF_FORCE_UPDATE: typing.Final = "force_update"
    CONF_FRIENDLY_NAME: typing.Final = "friendly_name"
    CONF_FRIENDLY_NAME_TEMPLATE: typing.Final = "friendly_name_template"
    CONF_HEADERS: typing.Final = "headers"
    CONF_HOST: typing.Final = "host"
    CONF_HOSTS: typing.Final = "hosts"
    CONF_HS: typing.Final = "hs"
    CONF_ICON: typing.Final = "icon"
    CONF_ICON_TEMPLATE: typing.Final = "icon_template"
    CONF_ID: typing.Final = "id"
    CONF_IF: typing.Final = "if"
    CONF_INCLUDE: typing.Final = "include"
    CONF_INTERNAL_URL: typing.Final = "internal_url"
    CONF_IP_ADDRESS: typing.Final = "ip_address"
    CONF_LATITUDE: typing.Final = "latitude"
    CONF_LEGACY_TEMPLATES: typing.Final = "legacy_templates"
    CONF_LIGHTS: typing.Final = "lights"
    CONF_LOCATION: typing.Final = "location"
    CONF_LOCATION_NAME: typing.Final = "location_name"
    CONF_LONGITUDE: typing.Final = "longitude"
    CONF_MAC: typing.Final = "mac"
    CONF_MATCH: typing.Final = "match"
    CONF_MAXIMUM: typing.Final = "maximum"
    CONF_MEDIA_DIRS: typing.Final = "media_dirs"
    CONF_METHOD: typing.Final = "method"
    CONF_MINIMUM: typing.Final = "minimum"
    CONF_MODE: typing.Final = "mode"
    CONF_MODEL: typing.Final = "model"
    CONF_MONITORED_CONDITIONS: typing.Final = "monitored_conditions"
    CONF_MONITORED_VARIABLES: typing.Final = "monitored_variables"
    CONF_NAME: typing.Final = "name"
    CONF_OFFSET: typing.Final = "offset"
    CONF_OPTIMISTIC: typing.Final = "optimistic"
    CONF_PACKAGES: typing.Final = "packages"
    CONF_PARALLEL: typing.Final = "parallel"
    CONF_PARAMS: typing.Final = "params"
    CONF_PASSWORD: typing.Final = "password"
    CONF_PATH: typing.Final = "path"
    CONF_PAYLOAD: typing.Final = "payload"
    CONF_PAYLOAD_OFF: typing.Final = "payload_off"
    CONF_PAYLOAD_ON: typing.Final = "payload_on"
    CONF_PENDING_TIME: typing.Final = "pending_time"
    CONF_PIN: typing.Final = "pin"
    CONF_PLATFORM: typing.Final = "platform"
    CONF_PORT: typing.Final = "port"
    CONF_PREFIX: typing.Final = "prefix"
    CONF_PROFILE_NAME: typing.Final = "profile_name"
    CONF_PROTOCOL: typing.Final = "protocol"
    CONF_PROXY_SSL: typing.Final = "proxy_ssl"
    CONF_QUOTE: typing.Final = "quote"
    CONF_RADIUS: typing.Final = "radius"
    CONF_RECIPIENT: typing.Final = "recipient"
    CONF_REGION: typing.Final = "region"
    CONF_REPEAT: typing.Final = "repeat"
    CONF_RESOURCE: typing.Final = "resource"
    CONF_RESOURCES: typing.Final = "resources"
    CONF_RESOURCE_TEMPLATE: typing.Final = "resource_template"
    CONF_RGB: typing.Final = "rgb"
    CONF_ROOM: typing.Final = "room"
    CONF_SAFE_MODE: typing.Final = "safe_mode"
    CONF_SCAN_INTERVAL: typing.Final = "scan_interval"
    CONF_SCENE: typing.Final = "scene"
    CONF_SELECTOR: typing.Final = "selector"
    CONF_SENDER: typing.Final = "sender"
    CONF_SENSORS: typing.Final = "sensors"
    CONF_SENSOR_TYPE: typing.Final = "sensor_type"
    CONF_SEQUENCE: typing.Final = "sequence"
    CONF_SERVICE: typing.Final = "service"
    CONF_SERVICE_DATA: typing.Final = "data"
    CONF_SERVICE_TEMPLATE: typing.Final = "service_template"
    CONF_SHOW_ON_MAP: typing.Final = "show_on_map"
    CONF_SLAVE: typing.Final = "slave"
    CONF_SOURCE: typing.Final = "source"
    CONF_SSL: typing.Final = "ssl"
    CONF_STATE: typing.Final = "state"
    CONF_STATE_TEMPLATE: typing.Final = "state_template"
    CONF_STOP: typing.Final = "stop"
    CONF_STRUCTURE: typing.Final = "structure"
    CONF_SWITCHES: typing.Final = "switches"
    CONF_TARGET: typing.Final = "target"
    CONF_TEMPERATURE_UNIT: typing.Final = "temperature_unit"
    CONF_THEN: typing.Final = "then"
    CONF_TIMEOUT: typing.Final = "timeout"
    CONF_TIME_ZONE: typing.Final = "time_zone"
    CONF_TOKEN: typing.Final = "token"
    CONF_TOTP: typing.Final = "totp"
    CONF_TRIGGER_TIME: typing.Final = "trigger_time"
    CONF_TTL: typing.Final = "ttl"
    CONF_TYPE: typing.Final = "type"
    CONF_UNIQUE_ID: typing.Final = "unique_id"
    CONF_UNIT_OF_MEASUREMENT: typing.Final = "unit_of_measurement"
    CONF_UNIT_SYSTEM: typing.Final = "unit_system"
    CONF_UNTIL: typing.Final = "until"
    CONF_URL: typing.Final = "url"
    CONF_USERNAME: typing.Final = "username"
    CONF_VALUE_TEMPLATE: typing.Final = "value_template"
    CONF_VARIABLES: typing.Final = "variables"
    CONF_VERIFY_SSL: typing.Final = "verify_ssl"
    CONF_VERSION: typing.Final = "version"
    CONF_WAIT_FOR_TRIGGER: typing.Final = "wait_for_trigger"
    CONF_WAIT_TEMPLATE: typing.Final = "wait_template"
    CONF_WEBHOOK_ID: typing.Final = "webhook_id"
    CONF_WEEKDAY: typing.Final = "weekday"
    CONF_WHILE: typing.Final = "while"
    CONF_WHITELIST: typing.Final = "whitelist"
    CONF_ALLOWLIST_EXTERNAL_DIRS: typing.Final = "allowlist_external_dirs"
    LEGACY_CONF_WHITELIST_EXTERNAL_DIRS: typing.Final = "whitelist_external_dirs"
    CONF_WHITE_VALUE: typing.Final = "white_value"
    CONF_XY: typing.Final = "xy"
    CONF_ZONE: typing.Final = "zone"

    # #### EVENTS ####
    EVENT_CALL_SERVICE: typing.Final = "call_service"
    EVENT_COMPONENT_LOADED: typing.Final = "component_loaded"
    EVENT_CORE_CONFIG_UPDATE: typing.Final = "core_config_updated"
    EVENT_HOMEASSISTANT_CLOSE: typing.Final = "homeassistant_close"
    EVENT_HOMEASSISTANT_START: typing.Final = "homeassistant_start"
    EVENT_HOMEASSISTANT_STARTED: typing.Final = "homeassistant_started"
    EVENT_HOMEASSISTANT_STOP: typing.Final = "homeassistant_stop"
    EVENT_HOMEASSISTANT_FINAL_WRITE: typing.Final = "homeassistant_final_write"
    EVENT_LOGBOOK_ENTRY: typing.Final = "logbook_entry"
    EVENT_SERVICE_REGISTERED: typing.Final = "service_registered"
    EVENT_SERVICE_REMOVED: typing.Final = "service_removed"
    EVENT_STATE_CHANGED: typing.Final = "state_changed"
    EVENT_THEMES_UPDATED: typing.Final = "themes_updated"

    # #### DEVICE CLASSES ####
    # DEVICE_CLASS_* below are deprecated as of 2021.12
    # use the SensorDeviceClass enum instead.
    DEVICE_CLASS_AQI: typing.Final = "aqi"
    DEVICE_CLASS_BATTERY: typing.Final = "battery"
    DEVICE_CLASS_CO: typing.Final = "carbon_monoxide"
    DEVICE_CLASS_CO2: typing.Final = "carbon_dioxide"
    DEVICE_CLASS_CURRENT: typing.Final = "current"
    DEVICE_CLASS_DATE: typing.Final = "date"
    DEVICE_CLASS_ENERGY: typing.Final = "energy"
    DEVICE_CLASS_FREQUENCY: typing.Final = "frequency"
    DEVICE_CLASS_GAS: typing.Final = "gas"
    DEVICE_CLASS_HUMIDITY: typing.Final = "humidity"
    DEVICE_CLASS_ILLUMINANCE: typing.Final = "illuminance"
    DEVICE_CLASS_MONETARY: typing.Final = "monetary"
    DEVICE_CLASS_NITROGEN_DIOXIDE = "nitrogen_dioxide"
    DEVICE_CLASS_NITROGEN_MONOXIDE = "nitrogen_monoxide"
    DEVICE_CLASS_NITROUS_OXIDE = "nitrous_oxide"
    DEVICE_CLASS_OZONE: typing.Final = "ozone"
    DEVICE_CLASS_PM1: typing.Final = "pm1"
    DEVICE_CLASS_PM10: typing.Final = "pm10"
    DEVICE_CLASS_PM25: typing.Final = "pm25"
    DEVICE_CLASS_POWER_FACTOR: typing.Final = "power_factor"
    DEVICE_CLASS_POWER: typing.Final = "power"
    DEVICE_CLASS_PRESSURE: typing.Final = "pressure"
    DEVICE_CLASS_SIGNAL_STRENGTH: typing.Final = "signal_strength"
    DEVICE_CLASS_SULPHUR_DIOXIDE = "sulphur_dioxide"
    DEVICE_CLASS_TEMPERATURE: typing.Final = "temperature"
    DEVICE_CLASS_TIMESTAMP: typing.Final = "timestamp"
    DEVICE_CLASS_VOLATILE_ORGANIC_COMPOUNDS = "volatile_organic_compounds"
    DEVICE_CLASS_VOLTAGE: typing.Final = "voltage"

    # #### HomeAssistantHttp Keys ####
    KEY_AUTHENTICATED: typing.Final = "ha_authenticated"
    KEY_HASS: typing.Final = "hass"
    KEY_HASS_USER: typing.Final = "hass_user"
    KEY_HASS_REFRESH_TOKEN_ID: typing.Final = "hass_refresh_token_id"
    KEY_BANNED_IPS: typing.Final = "ha_banned_ips"
    KEY_FAILED_LOGIN_ATTEMPTS: typing.Final = "ha_failed_login_attempts"
    KEY_LOGIN_THRESHOLD: typing.Final = "ha_login_threshold"

    NOTIFICATION_ID_BAN: typing.Final = "ip-ban"
    NOTIFICATION_ID_LOGIN: typing.Final = "http-login"

    IP_BANS_FILE: typing.Final = "ip_bans.yaml"
    ATTR_BANNED_AT: typing.Final = "banned_at"

    # #### STATES ####
    STATE_ON: typing.Final = "on"
    STATE_OFF: typing.Final = "off"
    STATE_HOME: typing.Final = "home"
    STATE_NOT_HOME: typing.Final = "not_home"
    STATE_UNKNOWN: typing.Final = "unknown"
    STATE_OPEN: typing.Final = "open"
    STATE_OPENING: typing.Final = "opening"
    STATE_CLOSED: typing.Final = "closed"
    STATE_CLOSING: typing.Final = "closing"
    STATE_BUFFERING: typing.Final = "buffering"
    STATE_PLAYING: typing.Final = "playing"
    STATE_PAUSED: typing.Final = "paused"
    STATE_IDLE: typing.Final = "idle"
    STATE_STANDBY: typing.Final = "standby"
    STATE_ALARM_DISARMED: typing.Final = "disarmed"
    STATE_ALARM_ARMED_HOME: typing.Final = "armed_home"
    STATE_ALARM_ARMED_AWAY: typing.Final = "armed_away"
    STATE_ALARM_ARMED_NIGHT: typing.Final = "armed_night"
    STATE_ALARM_ARMED_VACATION: typing.Final = "armed_vacation"
    STATE_ALARM_ARMED_CUSTOM_BYPASS: typing.Final = "armed_custom_bypass"
    STATE_ALARM_PENDING: typing.Final = "pending"
    STATE_ALARM_ARMING: typing.Final = "arming"
    STATE_ALARM_DISARMING: typing.Final = "disarming"
    STATE_ALARM_TRIGGERED: typing.Final = "triggered"
    STATE_LOCKED: typing.Final = "locked"
    STATE_UNLOCKED: typing.Final = "unlocked"
    STATE_LOCKING: typing.Final = "locking"
    STATE_UNLOCKING: typing.Final = "unlocking"
    STATE_JAMMED: typing.Final = "jammed"
    STATE_UNAVAILABLE: typing.Final = "unavailable"
    STATE_OK: typing.Final = "ok"
    STATE_PROBLEM: typing.Final = "problem"

    # #### STATE AND EVENT ATTRIBUTES ####
    # Attribution
    ATTR_ATTRIBUTION: typing.Final = "attribution"

    # Credentials
    ATTR_CREDENTIALS: typing.Final = "credentials"

    # Contains time-related attributes
    ATTR_NOW: typing.Final = "now"
    ATTR_DATE: typing.Final = "date"
    ATTR_TIME: typing.Final = "time"
    ATTR_SECONDS: typing.Final = "seconds"

    # Contains domain, service for a SERVICE_CALL event
    ATTR_DOMAIN: typing.Final = "domain"
    ATTR_SERVICE: typing.Final = "service"
    ATTR_SERVICE_DATA: typing.Final = "service_data"

    # IDs
    ATTR_ID: typing.Final = "id"

    # Name
    ATTR_NAME: typing.Final = "name"

    # Contains one string or a list of strings, each being an entity id
    ATTR_ENTITY_ID: typing.Final = "entity_id"

    # Contains one string or a list of strings, each being an area id
    ATTR_AREA_ID: typing.Final = "area_id"

    # Contains one string, the device ID
    ATTR_DEVICE_ID: typing.Final = "device_id"

    # String with a friendly name for the entity
    ATTR_FRIENDLY_NAME: typing.Final = "friendly_name"

    # A picture to represent entity
    ATTR_ENTITY_PICTURE: typing.Final = "entity_picture"

    ATTR_IDENTIFIERS: typing.Final = "identifiers"

    # Icon to use in the frontend
    ATTR_ICON: typing.Final = "icon"

    # The unit of measurement if applicable
    ATTR_UNIT_OF_MEASUREMENT: typing.Final = "unit_of_measurement"

    CONF_UNIT_SYSTEM_METRIC: typing.Final = "metric"
    CONF_UNIT_SYSTEM_IMPERIAL: typing.Final = "imperial"

    # Electrical attributes
    ATTR_VOLTAGE: typing.Final = "voltage"

    # Location of the device/sensor
    ATTR_LOCATION: typing.Final = "location"

    ATTR_MODE: typing.Final = "mode"

    ATTR_CONFIGURATION_URL: typing.Final = "configuration_url"
    ATTR_CONNECTIONS: typing.Final = "connections"
    ATTR_DEFAULT_NAME: typing.Final = "default_name"
    ATTR_MANUFACTURER: typing.Final = "manufacturer"
    ATTR_MODEL: typing.Final = "model"
    ATTR_SUGGESTED_AREA: typing.Final = "suggested_area"
    ATTR_SW_VERSION: typing.Final = "sw_version"
    ATTR_HW_VERSION: typing.Final = "hw_version"
    ATTR_VIA_DEVICE: typing.Final = "via_device"

    ATTR_BATTERY_CHARGING: typing.Final = "battery_charging"
    ATTR_BATTERY_LEVEL: typing.Final = "battery_level"
    ATTR_WAKEUP: typing.Final = "wake_up_interval"

    # For devices which support a code attribute
    ATTR_CODE: typing.Final = "code"
    ATTR_CODE_FORMAT: typing.Final = "code_format"

    # For calling a device specific command
    ATTR_COMMAND: typing.Final = "command"

    # For devices which support an armed state
    ATTR_ARMED: typing.Final = "device_armed"

    # For devices which support a locked state
    ATTR_LOCKED: typing.Final = "locked"

    # For sensors that support 'tripping', eg. motion and door sensors
    ATTR_TRIPPED: typing.Final = "device_tripped"

    # For sensors that support 'tripping' this holds the most recent
    # time the device was tripped
    ATTR_LAST_TRIP_TIME: typing.Final = "last_tripped_time"

    # For all entity's, this hold whether or not it should be hidden
    ATTR_HIDDEN: typing.Final = "hidden"

    # Location of the entity
    ATTR_LATITUDE: typing.Final = "latitude"
    ATTR_LONGITUDE: typing.Final = "longitude"

    # Accuracy of location in meters
    ATTR_GPS_ACCURACY: typing.Final = "gps_accuracy"

    # If state is assumed
    ATTR_ASSUMED_STATE: typing.Final = "assumed_state"
    ATTR_STATE: typing.Final = "state"

    ATTR_EDITABLE: typing.Final = "editable"
    ATTR_OPTION: typing.Final = "option"

    # The entity has been restored with restore state
    ATTR_RESTORED: typing.Final = "restored"

    # Bitfield of supported component features for the entity
    ATTR_SUPPORTED_FEATURES: typing.Final = "supported_features"

    # Class of device within its domain
    ATTR_DEVICE_CLASS: typing.Final = "device_class"

    # Temperature attribute
    ATTR_TEMPERATURE: typing.Final = "temperature"

    # Persons attribute
    ATTR_PERSONS: typing.Final = "persons"

    # #### UNITS OF MEASUREMENT ####
    # Apparent power units
    POWER_VOLT_AMPERE: typing.Final = "VA"

    # Power units
    POWER_WATT: typing.Final = "W"
    POWER_KILO_WATT: typing.Final = "kW"
    POWER_BTU_PER_HOUR: typing.Final = "BTU/h"

    # Reactive power units
    POWER_VOLT_AMPERE_REACTIVE: typing.Final = "var"

    # Energy units
    ENERGY_WATT_HOUR: typing.Final = "Wh"
    ENERGY_KILO_WATT_HOUR: typing.Final = "kWh"
    ENERGY_MEGA_WATT_HOUR: typing.Final = "MWh"

    # Electric_current units
    ELECTRIC_CURRENT_MILLIAMPERE: typing.Final = "mA"
    ELECTRIC_CURRENT_AMPERE: typing.Final = "A"

    # Electric_potential units
    ELECTRIC_POTENTIAL_MILLIVOLT: typing.Final = "mV"
    ELECTRIC_POTENTIAL_VOLT: typing.Final = "V"

    # Degree units
    DEGREE: typing.Final = "°"

    # Currency units
    CURRENCY_EURO: typing.Final = "€"
    CURRENCY_DOLLAR: typing.Final = "$"
    CURRENCY_CENT: typing.Final = "¢"

    # Temperature units
    TEMP_CELSIUS: typing.Final = "°C"
    TEMP_FAHRENHEIT: typing.Final = "°F"
    TEMP_KELVIN: typing.Final = "K"

    # Time units
    TIME_MICROSECONDS: typing.Final = "μs"
    TIME_MILLISECONDS: typing.Final = "ms"
    TIME_SECONDS: typing.Final = "s"
    TIME_MINUTES: typing.Final = "min"
    TIME_HOURS: typing.Final = "h"
    TIME_DAYS: typing.Final = "d"
    TIME_WEEKS: typing.Final = "w"
    TIME_MONTHS: typing.Final = "m"
    TIME_YEARS: typing.Final = "y"

    # Length units
    LENGTH_MILLIMETERS: typing.Final = "mm"
    LENGTH_CENTIMETERS: typing.Final = "cm"
    LENGTH_METERS: typing.Final = "m"
    LENGTH_KILOMETERS: typing.Final = "km"

    LENGTH_INCHES: typing.Final = "in"
    LENGTH_FEET: typing.Final = "ft"
    LENGTH_YARD: typing.Final = "yd"
    LENGTH_MILES: typing.Final = "mi"

    # Frequency units
    FREQUENCY_HERTZ: typing.Final = "Hz"
    FREQUENCY_KILOHERTZ: typing.Final = "kHz"
    FREQUENCY_MEGAHERTZ: typing.Final = "MHz"
    FREQUENCY_GIGAHERTZ: typing.Final = "GHz"

    # Pressure units
    PRESSURE_PA: typing.Final = "Pa"
    PRESSURE_HPA: typing.Final = "hPa"
    PRESSURE_KPA: typing.Final = "kPa"
    PRESSURE_BAR: typing.Final = "bar"
    PRESSURE_CBAR: typing.Final = "cbar"
    PRESSURE_MBAR: typing.Final = "mbar"
    PRESSURE_MMHG: typing.Final = "mmHg"
    PRESSURE_INHG: typing.Final = "inHg"
    PRESSURE_PSI: typing.Final = "psi"

    # Sound pressure units
    SOUND_PRESSURE_DB: typing.Final = "dB"
    SOUND_PRESSURE_WEIGHTED_DBA: typing.Final = "dBa"

    # Volume units
    VOLUME_LITERS: typing.Final = "L"
    VOLUME_MILLILITERS: typing.Final = "mL"
    VOLUME_CUBIC_METERS: typing.Final = "m³"
    VOLUME_CUBIC_FEET: typing.Final = "ft³"

    VOLUME_GALLONS: typing.Final = "gal"
    VOLUME_FLUID_OUNCE: typing.Final = "fl. oz."

    # Volume Flow Rate units
    VOLUME_FLOW_RATE_CUBIC_METERS_PER_HOUR: typing.Final = "m³/h"
    VOLUME_FLOW_RATE_CUBIC_FEET_PER_MINUTE: typing.Final = "ft³/m"

    # Area units
    AREA_SQUARE_METERS: typing.Final = "m²"

    # Mass units
    MASS_GRAMS: typing.Final = "g"
    MASS_KILOGRAMS: typing.Final = "kg"
    MASS_MILLIGRAMS: typing.Final = "mg"
    MASS_MICROGRAMS: typing.Final = "µg"

    MASS_OUNCES: typing.Final = "oz"
    MASS_POUNDS: typing.Final = "lb"

    # Conductivity units
    CONDUCTIVITY: typing.Final = "µS/cm"

    # Light units
    LIGHT_LUX: typing.Final = "lx"

    # UV Index units
    UV_INDEX: typing.Final = "UV index"

    # Percentage units
    PERCENTAGE: typing.Final = "%"

    # Irradiation units
    IRRADIATION_WATTS_PER_SQUARE_METER: typing.Final = "W/m²"
    IRRADIATION_BTUS_PER_HOUR_SQUARE_FOOT: typing.Final = "BTU/(h×ft²)"

    # Precipitation units
    PRECIPITATION_MILLIMETERS_PER_HOUR: typing.Final = "mm/h"
    PRECIPITATION_INCHES: typing.Final = "in"
    PRECIPITATION_INCHES_PER_HOUR: typing.Final = "in/h"

    # Concentration units
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER: typing.Final = "µg/m³"
    CONCENTRATION_MILLIGRAMS_PER_CUBIC_METER: typing.Final = "mg/m³"
    CONCENTRATION_MICROGRAMS_PER_CUBIC_FOOT: typing.Final = "μg/ft³"
    CONCENTRATION_PARTS_PER_CUBIC_METER: typing.Final = "p/m³"
    CONCENTRATION_PARTS_PER_MILLION: typing.Final = "ppm"
    CONCENTRATION_PARTS_PER_BILLION: typing.Final = "ppb"

    # Speed units
    SPEED_MILLIMETERS_PER_DAY: typing.Final = "mm/d"
    SPEED_INCHES_PER_DAY: typing.Final = "in/d"
    SPEED_METERS_PER_SECOND: typing.Final = "m/s"
    SPEED_INCHES_PER_HOUR: typing.Final = "in/h"
    SPEED_KILOMETERS_PER_HOUR: typing.Final = "km/h"
    SPEED_MILES_PER_HOUR: typing.Final = "mph"

    # Signal_strength units
    SIGNAL_STRENGTH_DECIBELS: typing.Final = "dB"
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT: typing.Final = "dBm"

    # Data units
    DATA_BITS: typing.Final = "bit"
    DATA_KILOBITS: typing.Final = "kbit"
    DATA_MEGABITS: typing.Final = "Mbit"
    DATA_GIGABITS: typing.Final = "Gbit"
    DATA_BYTES: typing.Final = "B"
    DATA_KILOBYTES: typing.Final = "kB"
    DATA_MEGABYTES: typing.Final = "MB"
    DATA_GIGABYTES: typing.Final = "GB"
    DATA_TERABYTES: typing.Final = "TB"
    DATA_PETABYTES: typing.Final = "PB"
    DATA_EXABYTES: typing.Final = "EB"
    DATA_ZETTABYTES: typing.Final = "ZB"
    DATA_YOTTABYTES: typing.Final = "YB"
    DATA_KIBIBYTES: typing.Final = "KiB"
    DATA_MEBIBYTES: typing.Final = "MiB"
    DATA_GIBIBYTES: typing.Final = "GiB"
    DATA_TEBIBYTES: typing.Final = "TiB"
    DATA_PEBIBYTES: typing.Final = "PiB"
    DATA_EXBIBYTES: typing.Final = "EiB"
    DATA_ZEBIBYTES: typing.Final = "ZiB"
    DATA_YOBIBYTES: typing.Final = "YiB"

    # Data_rate units
    DATA_RATE_BITS_PER_SECOND: typing.Final = "bit/s"
    DATA_RATE_KILOBITS_PER_SECOND: typing.Final = "kbit/s"
    DATA_RATE_MEGABITS_PER_SECOND: typing.Final = "Mbit/s"
    DATA_RATE_GIGABITS_PER_SECOND: typing.Final = "Gbit/s"
    DATA_RATE_BYTES_PER_SECOND: typing.Final = "B/s"
    DATA_RATE_KILOBYTES_PER_SECOND: typing.Final = "kB/s"
    DATA_RATE_MEGABYTES_PER_SECOND: typing.Final = "MB/s"
    DATA_RATE_GIGABYTES_PER_SECOND: typing.Final = "GB/s"
    DATA_RATE_KIBIBYTES_PER_SECOND: typing.Final = "KiB/s"
    DATA_RATE_MEBIBYTES_PER_SECOND: typing.Final = "MiB/s"
    DATA_RATE_GIBIBYTES_PER_SECOND: typing.Final = "GiB/s"


    # #### SERVICES ####
    SERVICE_HOMEASSISTANT_STOP: typing.Final = "stop"
    SERVICE_HOMEASSISTANT_RESTART: typing.Final = "restart"

    SERVICE_TURN_ON: typing.Final = "turn_on"
    SERVICE_TURN_OFF: typing.Final = "turn_off"
    SERVICE_TOGGLE: typing.Final = "toggle"
    SERVICE_RELOAD: typing.Final = "reload"

    SERVICE_VOLUME_UP: typing.Final = "volume_up"
    SERVICE_VOLUME_DOWN: typing.Final = "volume_down"
    SERVICE_VOLUME_MUTE: typing.Final = "volume_mute"
    SERVICE_VOLUME_SET: typing.Final = "volume_set"
    SERVICE_MEDIA_PLAY_PAUSE: typing.Final = "media_play_pause"
    SERVICE_MEDIA_PLAY: typing.Final = "media_play"
    SERVICE_MEDIA_PAUSE: typing.Final = "media_pause"
    SERVICE_MEDIA_STOP: typing.Final = "media_stop"
    SERVICE_MEDIA_NEXT_TRACK: typing.Final = "media_next_track"
    SERVICE_MEDIA_PREVIOUS_TRACK: typing.Final = "media_previous_track"
    SERVICE_MEDIA_SEEK: typing.Final = "media_seek"
    SERVICE_REPEAT_SET: typing.Final = "repeat_set"
    SERVICE_SHUFFLE_SET: typing.Final = "shuffle_set"

    SERVICE_ALARM_DISARM: typing.Final = "alarm_disarm"
    SERVICE_ALARM_ARM_HOME: typing.Final = "alarm_arm_home"
    SERVICE_ALARM_ARM_AWAY: typing.Final = "alarm_arm_away"
    SERVICE_ALARM_ARM_NIGHT: typing.Final = "alarm_arm_night"
    SERVICE_ALARM_ARM_VACATION: typing.Final = "alarm_arm_vacation"
    SERVICE_ALARM_ARM_CUSTOM_BYPASS: typing.Final = "alarm_arm_custom_bypass"
    SERVICE_ALARM_TRIGGER: typing.Final = "alarm_trigger"


    SERVICE_LOCK: typing.Final = "lock"
    SERVICE_UNLOCK: typing.Final = "unlock"

    SERVICE_OPEN: typing.Final = "open"
    SERVICE_CLOSE: typing.Final = "close"

    SERVICE_CLOSE_COVER: typing.Final = "close_cover"
    SERVICE_CLOSE_COVER_TILT: typing.Final = "close_cover_tilt"
    SERVICE_OPEN_COVER: typing.Final = "open_cover"
    SERVICE_OPEN_COVER_TILT: typing.Final = "open_cover_tilt"
    SERVICE_SAVE_PERSISTENT_STATES: typing.Final = "save_persistent_states"
    SERVICE_SET_COVER_POSITION: typing.Final = "set_cover_position"
    SERVICE_SET_COVER_TILT_POSITION: typing.Final = "set_cover_tilt_position"
    SERVICE_STOP_COVER: typing.Final = "stop_cover"
    SERVICE_STOP_COVER_TILT: typing.Final = "stop_cover_tilt"
    SERVICE_TOGGLE_COVER_TILT: typing.Final = "toggle_cover_tilt"

    SERVICE_SELECT_OPTION: typing.Final = "select_option"

    # #### API / REMOTE ####
    SERVER_PORT: typing.Final = 8123

    URL_ROOT: typing.Final = "/"
    URL_API: typing.Final = "/api/"
    URL_API_STREAM: typing.Final = "/api/stream"
    URL_API_CONFIG: typing.Final = "/api/config"
    URL_API_STATES: typing.Final = "/api/states"
    URL_API_STATES_ENTITY: typing.Final = "/api/states/{}"
    URL_API_EVENTS: typing.Final = "/api/events"
    URL_API_EVENTS_EVENT: typing.Final = "/api/events/{}"
    URL_API_SERVICES: typing.Final = "/api/services"
    URL_API_SERVICES_SERVICE: typing.Final = "/api/services/{}/{}"
    URL_API_COMPONENTS: typing.Final = "/api/components"
    URL_API_ERROR_LOG: typing.Final = "/api/error_log"
    URL_API_LOG_OUT: typing.Final = "/api/log_out"
    URL_API_TEMPLATE: typing.Final = "/api/template"

    HTTP_BASIC_AUTHENTICATION: typing.Final = "basic"
    HTTP_BEARER_AUTHENTICATION: typing.Final = "bearer_token"
    HTTP_DIGEST_AUTHENTICATION: typing.Final = "digest"

    HTTP_HEADER_X_REQUESTED_WITH: typing.Final = "X-Requested-With"

    CONTENT_TYPE_JSON: typing.Final = "application/json"
    CONTENT_TYPE_MULTIPART: typing.Final = "multipart/x-mixed-replace; boundary={}"
    CONTENT_TYPE_TEXT_PLAIN: typing.Final = "text/plain"

    # The exit code to send to request a restart
    RESTART_EXIT_CODE: typing.Final = 100

    UNIT_NOT_RECOGNIZED_TEMPLATE: typing.Final = "{} is not a recognized {} unit."

    LENGTH: typing.Final = "length"
    MASS: typing.Final = "mass"
    PRESSURE: typing.Final = "pressure"
    VOLUME: typing.Final = "volume"
    TEMPERATURE: typing.Final = "temperature"
    SPEED: typing.Final = "speed"
    WIND_SPEED: typing.Final = "wind_speed"
    ILLUMINANCE: typing.Final = "illuminance"
    ACCUMULATED_PRECIPITATION: typing.Final = "accumulated_precipitation"

    WEEKDAYS: typing.Final[list[str]] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

    # The degree of precision for platforms
    PRECISION_WHOLE: typing.Final = 1
    PRECISION_HALVES: typing.Final = 0.5
    PRECISION_TENTHS: typing.Final = 0.1

    # Static list of entities that will never be exposed to
    # cloud, alexa, or google_home components
    CLOUD_NEVER_EXPOSED_ENTITIES: typing.Final[list[str]] = ["group.all_locks"]

    # ENTITY_CATEGOR* below are deprecated as of 2021.12
    # use the EntityCategory enum instead.
    ENTITY_CATEGORY_CONFIG: typing.Final = "config"
    ENTITY_CATEGORY_DIAGNOSTIC: typing.Final = "diagnostic"
    ENTITY_CATEGORIES: typing.Final[list[str]] = [
        ENTITY_CATEGORY_CONFIG,
        ENTITY_CATEGORY_DIAGNOSTIC,
    ]

    # The ID of the Home Assistant Media Player Cast App
    CAST_APP_ID_HOMEASSISTANT_MEDIA: typing.Final = "B45F4572"
    # The ID of the Home Assistant Lovelace Cast App
    CAST_APP_ID_HOMEASSISTANT_LOVELACE: typing.Final = "A078F6B0"

    # User used by Supervisor
    HASSIO_USER_NAME = "Supervisor"
    SIGNAL_BOOTSTRAP_INTEGRATONS = "bootstrap_integrations"

@typing.attr.s(slots=True, frozen=True)
class Context:
    """The context that triggered something."""

    user_id: str | None = attr.ib(default=None)
    parent_id: str | None = attr.ib(default=None)
    id: str = attr.ib(factory=ulid_util.ulid)

    def as_dict(self) -> dict[str, str | None]:
        """Return a dictionary representation of the context."""
        return {"id": self.id, "parent_id": self.parent_id, "user_id": self.user_id}

class CoreState(enum.Enum):
    """Represent the current state of Home Assistant."""
    not_running = "NOT_RUNNING"
    starting = "STARTING"
    running = "RUNNING"
    stopping = "STOPPING"
    final_write = "FINAL_WRITE"
    stopped = "STOPPED"

    def __str__(self) -> str:
        """Return the event."""
        return self.value

class EventOrigin(enum.Enum):
    """Represent the origin of an event."""
    local = "LOCAL"
    remote = "REMOTE"
    def __str__(self) -> str:
        """Return the event."""
        return self.value

class Event:
    """Representation of an event within the bus."""
    __slots__ = ["event_type", "data", "origin", "time_fired", "context"]

    def __init__(
        self,
        event_type: str,
        data: dict[str, typing.Any] | None = None,
        origin: EventOrigin = EventOrigin.local,
        time_fired: datetime.datetime | None = None,
        context: Context | None = None,
    ) -> None:
        """Initialize a new event."""
        self.event_type = event_type
        self.data = data or {}
        self.origin = origin
        self.time_fired = time_fired or dt.utcnow()
        self.context: Context = context or Context(
            id=ulid_util.ulid(dt.utc_to_timestamp(self.time_fired))
        )

    def __hash__(self) -> int:
        """Make hashable."""
        # The only event type that shares context are the TIME_CHANGED
        return hash((self.event_type, self.context.id, self.time_fired))

    def as_dict(self) -> dict[str, typing.Any]:
        """Create a dict representation of this Event.

        Async friendly.
        """
        return {
            "event_type": self.event_type,
            "data": dict(self.data),
            "origin": str(self.origin.value),
            "time_fired": self.time_fired.isoformat(),
            "context": self.context.as_dict(),
        }

    def __repr__(self) -> str:
        """Return the representation."""
        if self.data:
            return f"<Event {self.event_type}[{str(self.origin)[0]}]: {util.repr_helper(self.data)}>"

        return f"<Event {self.event_type}[{str(self.origin)[0]}]>"

    def __eq__(self, other: typing.Any) -> bool:
        """Return the comparison."""
        return (  # type: ignore[no-any-return]
            self.__class__ == other.__class__
            and self.event_type == other.event_type
            and self.data == other.data
            and self.origin == other.origin
            and self.time_fired == other.time_fired
            and self.context == other.context
        )

class EventBus:
    """Allow the firing of and listening for events."""

    def __init__(self, hass: core.HomeAssistant) -> None:
        """Initialize a new event bus."""
        self._listeners: dict[str, list[_FilterableJob]] = {}
        self._hass = hass

    @callback
    def async_listeners(self) -> dict[str, int]:
        """Return dictionary with events and the number of listeners.

        This method must be run in the event loop.
        """
        return {key: len(listeners) for key, listeners in self._listeners.items()}

    @property
    def listeners(self) -> dict[str, int]:
        """Return dictionary with events and the number of listeners."""
        return io.run_callback_threadsafe(self._hass.loop, self.async_listeners).result()

    def fire(
        self,
        event_type: str,
        event_data: dict[str, typing.Any] | None = None,
        origin: EventOrigin = EventOrigin.local,
        context: Context | None = None,
    ) -> None:
        """Fire an event."""
        self._hass.loop.call_soon_threadsafe(
            self.async_fire, event_type, event_data, origin, context
        )

    @callback
    def async_fire(
        self,
        event_type: str,
        event_data: dict[str, typing.Any] | None = None,
        origin: EventOrigin = EventOrigin.local,
        context: Context | None = None,
        time_fired: datetime.datetime | None = None,
    ) -> None:
        """Fire an event.

        This method must be run in the event loop.
        """
        if len(event_type) > Const.MAX_LENGTH_EVENT_EVENT_TYPE:
            raise exceptions.MaxLengthExceeded(
                event_type, "event_type", Const.MAX_LENGTH_EVENT_EVENT_TYPE
            )

        listeners = self._listeners.get(event_type, [])

        # EVENT_HOMEASSISTANT_CLOSE should go only to this listeners
        match_all_listeners = self._listeners.get(Const.MATCH_ALL)
        if match_all_listeners is not None and event_type != Const.EVENT_HOMEASSISTANT_CLOSE:
            listeners = match_all_listeners + listeners

        event = Event(event_type, event_data, origin, time_fired, context)

        _LOGGER.debug("Bus:Handling %s", event)

        if not listeners:
            return

        for job, event_filter, run_immediately in listeners:
            if event_filter is not None:
                try:
                    if not event_filter(event):
                        continue
                except Exception: 
                    _LOGGER.exception("Error in event filter")
                    continue
            if run_immediately:
                try:
                    job.target(event)
                except Exception:  
                    _LOGGER.exception("Error running job: %s", job)
            else:
                self._hass.async_add_hass_job(job, event)

    def listen(
        self,
        event_type: str,
        listener: typing.Callable[[Event], None | collections.abc.Awaitable[None]],
    ) -> _CALLBACK_TYPE:
        """Listen for all events or events of a specific type.

        To listen to all events specify the constant ``MATCH_ALL``
        as event_type.
        """
        async_remove_listener = io.run_callback_threadsafe(
            self._hass.loop, self.async_listen, event_type, listener
        ).result()

        def remove_listener() -> None:
            """Remove the listener."""
            io.run_callback_threadsafe(self._hass.loop, async_remove_listener).result()

        return remove_listener

    @callback
    def async_listen(
        self,
        event_type: str,
        listener: typing.Callable[[Event], None | collections.abc.Awaitable[None]],
        event_filter: typing.Callable[[Event], bool] | None = None,
        run_immediately: bool = False,
    ) -> _CALLBACK_TYPE:
        """Listen for all events or events of a specific type.

        To listen to all events specify the constant ``MATCH_ALL``
        as event_type.

        An optional event_filter, which must be a callable decorated with
        @callback that returns a boolean value, determines if the
        listener callable should run.

        If run_immediately is passed, the callback will be run
        right away instead of using call_soon. Only use this if
        the callback results in scheduling another task.

        This method must be run in the event loop.
        """
        if event_filter is not None and not is_callback(event_filter):
            raise exceptions.HomeAssistantError(f"Event filter {event_filter} is not a callback")
        if run_immediately and not is_callback(listener):
            raise exceptions.HomeAssistantError(f"Event listener {listener} is not a callback")
        return self._async_listen_filterable_job(
            event_type, _FilterableJob(HassJob(listener), event_filter, run_immediately)
        )

    @callback
    def _async_listen_filterable_job(
        self, event_type: str, filterable_job: _FilterableJob
    ) -> _CALLBACK_TYPE:
        self._listeners.setdefault(event_type, []).append(filterable_job)

        def remove_listener() -> None:
            """Remove the listener."""
            self._async_remove_listener(event_type, filterable_job)

        return remove_listener

    def listen_once(
        self, event_type: str, listener: typing.Callable[[Event], None | collections.abc.Awaitable[None]]
    ) -> _CALLBACK_TYPE:
        """Listen once for event of a specific type.

        To listen to all events specify the constant ``MATCH_ALL``
        as event_type.

        Returns function to unsubscribe the listener.
        """
        async_remove_listener = io.run_callback_threadsafe(
            self._hass.loop, self.async_listen_once, event_type, listener
        ).result()

        def remove_listener() -> None:
            """Remove the listener."""
            io.run_callback_threadsafe(self._hass.loop, async_remove_listener).result()

        return remove_listener

    @callback
    def async_listen_once(
        self, event_type: str, listener: typing.Callable[[Event], None | collections.abc.Awaitable[None]]
    ) -> _CALLBACK_TYPE:
        """Listen once for event of a specific type.

        To listen to all events specify the constant ``MATCH_ALL``
        as event_type.

        Returns registered listener that can be used with remove_listener.

        This method must be run in the event loop.
        """
        filterable_job: _FilterableJob | None = None

        @callback
        def _onetime_listener(event: Event) -> None:
            """Remove listener from event bus and then fire listener."""
            nonlocal filterable_job
            if hasattr(_onetime_listener, "run"):
                return
            # Set variable so that we will never run twice.
            # Because the event bus loop might have async_fire queued multiple
            # times, its possible this listener may already be lined up
            # multiple times as well.
            # This will make sure the second time it does nothing.
            setattr(_onetime_listener, "run", True)
            assert filterable_job is not None
            self._async_remove_listener(event_type, filterable_job)
            self._hass.async_run_job(listener, event)

        functools.update_wrapper(
            _onetime_listener, listener, ("__name__", "__qualname__", "__module__"), []
        )

        filterable_job = _FilterableJob(HassJob(_onetime_listener), None, False)

        return self._async_listen_filterable_job(event_type, filterable_job)

    @callback
    def _async_remove_listener(
        self, event_type: str, filterable_job: _FilterableJob
    ) -> None:
        """Remove a listener of a specific event_type.

        This method must be run in the event loop.
        """
        try:
            self._listeners[event_type].remove(filterable_job)

            # delete event_type list if empty
            if not self._listeners[event_type]:
                self._listeners.pop(event_type)
        except (KeyError, ValueError):
            # KeyError is key event_type listener did not exist
            # ValueError if listener did not exist within event_type
            _LOGGER.exception(
                "Unable to remove unknown job listener %s", filterable_job
            )

class _FilterableJob(typing.NamedTuple):
    """Event listener job to be executed with optional filter."""

    job: HassJob[None | collections.abc.Awaitable[None]]
    event_filter: typing.Callable[[Event], bool] | None
    run_immediately: bool

class HassJob(typing.Generic[_R_co]):
    """Represent a job to be run later.

    We check the callable type in advance
    so we can avoid checking it every time
    we run the job.
    """

    def _get_callable_job_type(target: typing.Callable[..., typing.Any]) -> HassJobType:
        """Determine the job type from the callable."""
        # Check for partials to properly determine if coroutine function
        check_target = target
        while isinstance(check_target, functools.partial):
            check_target = check_target.func

        if asyncio.iscoroutinefunction(check_target):
            return HassJobType.Coroutinefunction
        if is_callback(check_target):
            return HassJobType.Callback
        if asyncio.iscoroutine(check_target):
            raise ValueError("Coroutine not allowed to be passed to HassJob")
        return HassJobType.Executor

    __slots__ = ("job_type", "target")

    def __init__(self, target: typing.Callable[..., _R_co]) -> None:
        """Create a job object."""
        self.target = target
        self.job_type = HassJob._get_callable_job_type(target)

    def __repr__(self) -> str:
        """Return the job."""
        return f"<Job {self.job_type} {self.target}>"

@enum.unique
class HassJobType(enum.Enum):
    """Represent a job type."""
    Coroutinefunction = 1
    Callback = 2
    Executor = 3

class Platform(strenum.StrEnum):
    """Available entity platforms."""
    AIR_QUALITY = "air_quality"
    ALARM_CONTROL_PANEL = "alarm_control_panel"
    BINARY_SENSOR = "binary_sensor"
    BUTTON = "button"
    CALENDAR = "calendar"
    CAMERA = "camera"
    CLIMATE = "climate"
    COVER = "cover"
    DEVICE_TRACKER = "device_tracker"
    FAN = "fan"
    GEO_LOCATION = "geo_location"
    HUMIDIFIER = "humidifier"
    IMAGE_PROCESSING = "image_processing"
    LIGHT = "light"
    LOCK = "lock"
    MAILBOX = "mailbox"
    MEDIA_PLAYER = "media_player"
    NOTIFY = "notify"
    NUMBER = "number"
    REMOTE = "remote"
    SCENE = "scene"
    SELECT = "select"
    SENSOR = "sensor"
    SIREN = "siren"
    STT = "stt"
    SWITCH = "switch"
    TTS = "tts"
    VACUUM = "vacuum"
    UPDATE = "update"
    WATER_HEATER = "water_heater"
    WEATHER = "weather"

class State:
    """Object to represent a state within the state machine.

    entity_id: the entity that is represented.
    state: the state of the entity
    attributes: extra information on entity and state
    last_changed: last time the state was changed, not the attributes.
    last_updated: last time this object was updated.
    context: Context in which it was created
    domain: Domain of this state.
    object_id: Object id of this state.
    """

    _VALID_ENTITY_ID: typing.Final = re.compile(r"^(?!.+__)(?!_)[\da-z_]+(?<!_)\.(?!_)[\da-z_]+(?<!_)$")
    _MAX_EXPECTED_ENTITY_IDS: typing.Final = 16384

    __slots__ = [
        "entity_id",
        "state",
        "attributes",
        "last_changed",
        "last_updated",
        "context",
        "domain",
        "object_id",
        "_as_dict",
    ]

    def __init__(
        self,
        entity_id: str,
        state: str,
        attributes: collections.abc.Mapping[str, typing.Any] | None = None,
        last_changed: datetime.datetime | None = None,
        last_updated: datetime.datetime | None = None,
        context: Context | None = None,
        validate_entity_id: bool | None = True,
    ) -> None:
        """Initialize a new state."""
        state = str(state)

        if validate_entity_id and not State._valid_entity_id(entity_id):
            raise exceptions.InvalidEntityFormatError(
                f"Invalid entity id encountered: {entity_id}. "
                "Format should be <domain>.<object_id>"
            )

        if not State._valid_state(state):
            raise exceptions.InvalidStateError(
                f"Invalid state encountered for entity ID: {entity_id}. "
                "State max length is 255 characters."
            )

        self.entity_id = entity_id.lower()
        self.state = state
        self.attributes = util.ReadOnlyDict(attributes or {})
        self.last_updated = last_updated or dt.utcnow()
        self.last_changed = last_changed or self.last_updated
        self.context = context or Context()
        self.domain, self.object_id = State._split_entity_id(self.entity_id)
        self._as_dict: util.ReadOnlyDict[str, collections.abc.Collection[typing.Any]] | None = None

    def _valid_entity_id(entity_id: str) -> bool:
        """Test if an entity ID is a valid format.

        Format: <domain>.<entity> where both are slugs.
        """
        return State._VALID_ENTITY_ID.match(entity_id) is not None

    def _valid_state(state: str) -> bool:
        """Test if a state is valid."""
        return len(state) <= Const.MAX_LENGTH_STATE_STATE

    @functools.lru_cache(_MAX_EXPECTED_ENTITY_IDS)
    def _split_entity_id(entity_id: str) -> tuple[str, str]:
        """Split a state entity ID into domain and object ID."""
        domain, _, object_id = entity_id.partition(".")
        if not domain or not object_id:
            raise ValueError(f"Invalid entity ID {entity_id}")
        return domain, object_id

    @property
    def name(self) -> str:
        """Name of this state."""
        return self.attributes.get(Const.ATTR_FRIENDLY_NAME) or self.object_id.replace(
            "_", " "
        )

    def as_dict(self) -> util.ReadOnlyDict[str, collections.abc.Collection[typing.Any]]:
        """Return a dict representation of the State.

        Async friendly.

        To be used for JSON serialization.
        Ensures: state == State.from_dict(state.as_dict())
        """
        if not self._as_dict:
            last_changed_isoformat = self.last_changed.isoformat()
            if self.last_changed == self.last_updated:
                last_updated_isoformat = last_changed_isoformat
            else:
                last_updated_isoformat = self.last_updated.isoformat()
            self._as_dict = util.ReadOnlyDict(
                {
                    "entity_id": self.entity_id,
                    "state": self.state,
                    "attributes": self.attributes,
                    "last_changed": last_changed_isoformat,
                    "last_updated": last_updated_isoformat,
                    "context": util.ReadOnlyDict(self.context.as_dict()),
                }
            )
        return self._as_dict

    @classmethod
    def from_dict(cls: type[_StateT], json_dict: dict[str, typing.Any]) -> _StateT | None:
        """Initialize a state from a dict.

        Async friendly.

        Ensures: state == State.from_json_dict(state.to_json_dict())
        """
        if not (json_dict and "entity_id" in json_dict and "state" in json_dict):
            return None

        last_changed = json_dict.get("last_changed")

        if isinstance(last_changed, str):
            last_changed = dt.parse_datetime(last_changed)

        last_updated = json_dict.get("last_updated")

        if isinstance(last_updated, str):
            last_updated = dt.parse_datetime(last_updated)

        if context := json_dict.get("context"):
            context = Context(id=context.get("id"), user_id=context.get("user_id"))

        return cls(
            json_dict["entity_id"],
            json_dict["state"],
            json_dict.get("attributes"),
            last_changed,
            last_updated,
            context,
        )

    def __eq__(self, other: typing.Any) -> bool:
        """Return the comparison of the state."""
        return (  # type: ignore[no-any-return]
            self.__class__ == other.__class__
            and self.entity_id == other.entity_id
            and self.state == other.state
            and self.attributes == other.attributes
            and self.context == other.context
        )

    def __repr__(self) -> str:
        """Return the representation of the states."""
        attrs = f"; {util.repr_helper(self.attributes)}" if self.attributes else ""

        return (
            f"<state {self.entity_id}={self.state}{attrs}"
            f" @ {dt.as_local(self.last_changed).isoformat()}>"
        )

class StateMachine:
    """Helper class that tracks the state of different entities."""

    def __init__(self, bus: EventBus, loop: asyncio.events.AbstractEventLoop) -> None:
        """Initialize state machine."""
        self._states: dict[str, State] = {}
        self._reservations: set[str] = set()
        self._bus = bus
        self._loop = loop

    def entity_ids(self, domain_filter: str | None = None) -> list[str]:
        """List of entity ids that are being tracked."""
        future = io.run_callback_threadsafe(
            self._loop, self.async_entity_ids, domain_filter
        )
        return future.result()

    @callback
    def async_entity_ids(
        self, domain_filter: str | collections.abc.Iterable[str] | None = None
    ) -> list[str]:
        """List of entity ids that are being tracked.

        This method must be run in the event loop.
        """
        if domain_filter is None:
            return list(self._states)

        if isinstance(domain_filter, str):
            domain_filter = (domain_filter.lower(),)

        return [
            state.entity_id
            for state in self._states.values()
            if state.domain in domain_filter
        ]

    @callback
    def async_entity_ids_count(
        self, domain_filter: str | collections.abc.Iterable[str] | None = None
    ) -> int:
        """Count the entity ids that are being tracked.

        This method must be run in the event loop.
        """
        if domain_filter is None:
            return len(self._states)

        if isinstance(domain_filter, str):
            domain_filter = (domain_filter.lower(),)

        return len(
            [None for state in self._states.values() if state.domain in domain_filter]
        )

    def all(self, domain_filter: str | collections.abc.Iterable[str] | None = None) -> list[State]:
        """Create a list of all states."""
        return io.run_callback_threadsafe(
            self._loop, self.async_all, domain_filter
        ).result()

    @callback
    def async_all(
        self, domain_filter: str | collections.abc.Iterable[str] | None = None
    ) -> list[State]:
        """Create a list of all states matching the filter.

        This method must be run in the event loop.
        """
        if domain_filter is None:
            return list(self._states.values())

        if isinstance(domain_filter, str):
            domain_filter = (domain_filter.lower(),)

        return [
            state for state in self._states.values() if state.domain in domain_filter
        ]

    def get(self, entity_id: str) -> State | None:
        """Retrieve state of entity_id or None if not found.

        Async friendly.
        """
        return self._states.get(entity_id.lower())

    def is_state(self, entity_id: str, state: str) -> bool:
        """Test if entity exists and is in specified state.

        Async friendly.
        """
        state_obj = self.get(entity_id)
        return state_obj is not None and state_obj.state == state

    def remove(self, entity_id: str) -> bool:
        """Remove the state of an entity.

        Returns boolean to indicate if an entity was removed.
        """
        return io.run_callback_threadsafe(
            self._loop, self.async_remove, entity_id
        ).result()

    @callback
    def async_remove(self, entity_id: str, context: Context | None = None) -> bool:
        """Remove the state of an entity.

        Returns boolean to indicate if an entity was removed.

        This method must be run in the event loop.
        """
        entity_id = entity_id.lower()
        old_state = self._states.pop(entity_id, None)

        if entity_id in self._reservations:
            self._reservations.remove(entity_id)

        if old_state is None:
            return False

        self._bus.async_fire(
            Const.EVENT_STATE_CHANGED,
            {"entity_id": entity_id, "old_state": old_state, "new_state": None},
            EventOrigin.local,
            context=context,
        )
        return True

    def set(
        self,
        entity_id: str,
        new_state: str,
        attributes: collections.abc.Mapping[str, typing.Any] | None = None,
        force_update: bool = False,
        context: Context | None = None,
    ) -> None:
        """Set the state of an entity, add entity if it does not exist.

        Attributes is an optional dict to specify attributes of this state.

        If you just update the attributes and not the state, last changed will
        not be affected.
        """
        io.run_callback_threadsafe(
            self._loop,
            self.async_set,
            entity_id,
            new_state,
            attributes,
            force_update,
            context,
        ).result()

    @callback
    def async_reserve(self, entity_id: str) -> None:
        """Reserve a state in the state machine for an entity being added.

        This must not fire an event when the state is reserved.

        This avoids a race condition where multiple entities with the same
        entity_id are added.
        """
        entity_id = entity_id.lower()
        if entity_id in self._states or entity_id in self._reservations:
            raise exceptions.HomeAssistantError(
                "async_reserve must not be called once the state is in the state machine."
            )

        self._reservations.add(entity_id)

    @callback
    def async_available(self, entity_id: str) -> bool:
        """Check to see if an entity_id is available to be used."""
        entity_id = entity_id.lower()
        return entity_id not in self._states and entity_id not in self._reservations

    @callback
    def async_set(
        self,
        entity_id: str,
        new_state: str,
        attributes: collections.abc.Mapping[str, typing.Any] | None = None,
        force_update: bool = False,
        context: Context | None = None,
    ) -> None:
        """Set the state of an entity, add entity if it does not exist.

        Attributes is an optional dict to specify attributes of this state.

        If you just update the attributes and not the state, last changed will
        not be affected.

        This method must be run in the event loop.
        """
        entity_id = entity_id.lower()
        new_state = str(new_state)
        attributes = attributes or {}
        if (old_state := self._states.get(entity_id)) is None:
            same_state = False
            same_attr = False
            last_changed = None
        else:
            same_state = old_state.state == new_state and not force_update
            same_attr = old_state.attributes == attributes
            last_changed = old_state.last_changed if same_state else None

        if same_state and same_attr:
            return

        now = dt.utcnow()

        if context is None:
            context = Context(id=ulid_util.ulid(dt.utc_to_timestamp(now)))

        state = State(
            entity_id,
            new_state,
            attributes,
            last_changed,
            now,
            context,
            old_state is None,
        )
        self._states[entity_id] = state
        self._bus.async_fire(
            Const.EVENT_STATE_CHANGED,
            {"entity_id": entity_id, "old_state": old_state, "new_state": state},
            EventOrigin.local,
            context,
            time_fired=now,
        )

class Service:
    """Representation of a callable service."""

    __slots__ = ["job", "schema"]

    def __init__(
        self,
        func: typing.Callable[[ServiceCall], None | collections.abc.Awaitable[None]],
        schema: vol.Schema | None,
        context: Context | None = None,
    ) -> None:
        """Initialize a service."""
        self.job = HassJob(func)
        self.schema = schema

class ServiceCall:
    """Representation of a call to a service."""

    __slots__ = ["domain", "service", "data", "context"]

    def __init__(
        self,
        domain: str,
        service: str,
        data: dict[str, typing.Any] | None = None,
        context: Context | None = None,
    ) -> None:
        """Initialize a service call."""
        self.domain = domain.lower()
        self.service = service.lower()
        self.data = util.ReadOnlyDict(data or {})
        self.context = context or Context()

    def __repr__(self) -> str:
        """Return the representation of the service."""
        if self.data:
            return (
                f"<ServiceCall {self.domain}.{self.service} "
                f"(c:{self.context.id}): {util.repr_helper(self.data)}>"
            )

        return f"<ServiceCall {self.domain}.{self.service} (c:{self.context.id})>"

class ServiceRegistry:
    """Offer the services over the eventbus."""

    def __init__(self, hass: core.HomeAssistant) -> None:
        """Initialize a service registry."""
        self._services: dict[str, dict[str, Service]] = {}
        self._hass = hass

    @property
    def services(self) -> dict[str, dict[str, Service]]:
        """Return dictionary with per domain a list of available services."""
        return io.run_callback_threadsafe(self._hass.loop, self.async_services).result()

    @callback
    def async_services(self) -> dict[str, dict[str, Service]]:
        """Return dictionary with per domain a list of available services.

        This method must be run in the event loop.
        """
        return {domain: service.copy() for domain, service in self._services.items()}

    def has_service(self, domain: str, service: str) -> bool:
        """Test if specified service exists.

        Async friendly.
        """
        return service.lower() in self._services.get(domain.lower(), [])

    def register(
        self,
        domain: str,
        service: str,
        service_func: typing.Callable[[ServiceCall], collections.abc.Awaitable[None] | None],
        schema: vol.Schema | None = None,
    ) -> None:
        """
        Register a service.

        Schema is called to coerce and validate the service data.
        """
        io.run_callback_threadsafe(
            self._hass.loop, self.async_register, domain, service, service_func, schema
        ).result()

    @callback
    def async_register(
        self,
        domain: str,
        service: str,
        service_func: typing.Callable[[ServiceCall], collections.abc.Awaitable[None] | None],
        schema: vol.Schema | None = None,
    ) -> None:
        """
        Register a service.

        Schema is called to coerce and validate the service data.

        This method must be run in the event loop.
        """
        domain = domain.lower()
        service = service.lower()
        service_obj = Service(service_func, schema)

        if domain in self._services:
            self._services[domain][service] = service_obj
        else:
            self._services[domain] = {service: service_obj}

        self._hass.bus.async_fire(
            Const.EVENT_SERVICE_REGISTERED, {Const.ATTR_DOMAIN: domain, Const.ATTR_SERVICE: service}
        )

    def remove(self, domain: str, service: str) -> None:
        """Remove a registered service from service handler."""
        io.run_callback_threadsafe(
            self._hass.loop, self.async_remove, domain, service
        ).result()

    @callback
    def async_remove(self, domain: str, service: str) -> None:
        """Remove a registered service from service handler.

        This method must be run in the event loop.
        """
        domain = domain.lower()
        service = service.lower()

        if service not in self._services.get(domain, {}):
            _LOGGER.warning("Unable to remove unknown service %s/%s", domain, service)
            return

        self._services[domain].pop(service)

        if not self._services[domain]:
            self._services.pop(domain)

        self._hass.bus.async_fire(
            Const.EVENT_SERVICE_REMOVED, {Const.ATTR_DOMAIN: domain, Const.ATTR_SERVICE: service}
        )

    def call(
        self,
        domain: str,
        service: str,
        service_data: dict[str, typing.Any] | None = None,
        blocking: bool = False,
        context: Context | None = None,
        limit: float | None = Const.SERVICE_CALL_LIMIT,
        target: dict[str, Const.Any] | None = None,
    ) -> bool | None:
        """
        Call a service.

        See description of async_call for details.
        """
        return asyncio.run_coroutine_threadsafe(
            self.async_call(
                domain, service, service_data, blocking, context, limit, target
            ),
            self._hass.loop,
        ).result()

    async def async_call(
        self,
        domain: str,
        service: str,
        service_data: dict[str, Const.Any] | None = None,
        blocking: bool = False,
        context: Context | None = None,
        limit: float | None = Const.SERVICE_CALL_LIMIT,
        target: dict[str, typing.Any] | None = None,
    ) -> bool | None:
        """
        Call a service.

        Specify blocking=True to wait until service is executed.
        Waits a maximum of limit, which may be None for no timeout.

        If blocking = True, will return boolean if service executed
        successfully within limit.

        This method will fire an event to indicate the service has been called.

        Because the service is sent as an event you are not allowed to use
        the keys ATTR_DOMAIN and ATTR_SERVICE in your service_data.

        This method is a coroutine.
        """
        domain = domain.lower()
        service = service.lower()
        context = context or Context()
        service_data = service_data or {}

        try:
            handler = self._services[domain][service]
        except KeyError:
            raise exceptions.ServiceNotFound(domain, service) from None

        if target:
            service_data.update(target)

        if handler.schema:
            try:
                processed_data: dict[str, typing.Any] = handler.schema(service_data)
            except vol.Invalid:
                _LOGGER.debug(
                    "Invalid data for service call %s.%s: %s",
                    domain,
                    service,
                    service_data,
                )
                raise
        else:
            processed_data = service_data

        service_call = ServiceCall(domain, service, processed_data, context)

        self._hass.bus.async_fire(
            Const.EVENT_CALL_SERVICE,
            {
                Const.ATTR_DOMAIN: domain.lower(),
                Const.ATTR_SERVICE: service.lower(),
                Const.ATTR_SERVICE_DATA: service_data,
            },
            context=context,
        )

        coro = self._execute_service(handler, service_call)
        if not blocking:
            self._run_service_in_background(coro, service_call)
            return None

        task = self._hass.async_create_task(coro)
        try:
            await asyncio.wait({task}, timeout=limit)
        except asyncio.CancelledError:
            # Task calling us was cancelled, so cancel service call task, and wait for
            # it to be cancelled, within reason, before leaving.
            _LOGGER.debug("Service call was cancelled: %s", service_call)
            task.cancel()
            await asyncio.wait({task}, timeout=Const.SERVICE_CALL_LIMIT)
            raise

        if task.cancelled():
            # Service call task was cancelled some other way, such as during shutdown.
            _LOGGER.debug("Service was cancelled: %s", service_call)
            raise asyncio.CancelledError
        if task.done():
            # Propagate any exceptions that might have happened during service call.
            task.result()
            # Service call completed successfully!
            return True
        # Service call task did not complete before timeout expired.
        # Let it keep running in background.
        self._run_service_in_background(task, service_call)
        _LOGGER.debug("Service did not complete before timeout: %s", service_call)
        return False

    def _run_service_in_background(
        self,
        coro_or_task: typing.Coroutine[typing.Any, typing.Any, None] | asyncio.Task[None],
        service_call: ServiceCall,
    ) -> None:
        """Run service call in background, catching and logging any exceptions."""

        async def catch_exceptions() -> None:
            try:
                await coro_or_task
            except exceptions.Unauthorized:
                _LOGGER.warning(
                    "Unauthorized service called %s/%s",
                    service_call.domain,
                    service_call.service,
                )
            except asyncio.CancelledError:
                _LOGGER.debug("Service was cancelled: %s", service_call)
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Error executing service: %s", service_call)

        self._hass.async_create_task(catch_exceptions())

    async def _execute_service(
        self, handler: Service, service_call: ServiceCall
    ) -> None:
        """Execute a service."""
        if handler.job.job_type == HassJobType.Coroutinefunction:
            await typing.cast(typing.Callable[[ServiceCall], collections.abc.Awaitable[None]], handler.job.target)(
                service_call
            )
        elif handler.job.job_type == HassJobType.Callback:
            typing.cast(typing.Callable[[ServiceCall], None], handler.job.target)(service_call)
        else:
            await self._hass.async_add_executor_job(
                typing.cast(typing.Callable[[ServiceCall], None], handler.job.target), service_call
            )

class UnitSystem:
    """A container for units of measure."""
    _LENGTH_UNITS: typing.Final = (
        Const.LENGTH_KILOMETERS,
        Const.LENGTH_MILES,
        Const.LENGTH_FEET,
        Const.LENGTH_METERS,
        Const.LENGTH_CENTIMETERS,
        Const.LENGTH_MILLIMETERS,
        Const.LENGTH_INCHES,
        Const.LENGTH_YARD,
    )

    _TO_METERS: typing.Final = {
        Const.LENGTH_METERS: lambda meters: meters,
        Const.LENGTH_MILES: lambda miles: miles * 1609.344,
        Const.LENGTH_YARD: lambda yards: yards * 0.9144,
        Const.LENGTH_FEET: lambda feet: feet * 0.3048,
        Const.LENGTH_INCHES: lambda inches: inches * 0.0254,
        Const.LENGTH_KILOMETERS: lambda kilometers: kilometers * 1000,
        Const.LENGTH_CENTIMETERS: lambda centimeters: centimeters * 0.01,
        Const.LENGTH_MILLIMETERS: lambda millimeters: millimeters * 0.001,
    }

    _METERS_TO: typing.Final = {
        Const.LENGTH_METERS: lambda meters: meters,
        Const.LENGTH_MILES: lambda meters: meters * 0.000621371,
        Const.LENGTH_YARD: lambda meters: meters * 1.09361,
        Const.LENGTH_FEET: lambda meters: meters * 3.28084,
        Const.LENGTH_INCHES: lambda meters: meters * 39.3701,
        Const.LENGTH_KILOMETERS: lambda meters: meters * 0.001,
        Const.LENGTH_CENTIMETERS: lambda meters: meters * 100,
        Const.LENGTH_MILLIMETERS: lambda meters: meters * 1000,
    }

    _SPEED_UNITS: typing.Final = (
        Const.SPEED_METERS_PER_SECOND,
        Const.SPEED_KILOMETERS_PER_HOUR,
        Const.SPEED_MILES_PER_HOUR,
        Const.SPEED_MILLIMETERS_PER_DAY,
        Const.SPEED_INCHES_PER_DAY,
        Const.SPEED_INCHES_PER_HOUR,
    )

    _HRS_TO_SECS: typing.Final = 60 * 60  # 1 hr = 3600 seconds
    _KM_TO_M: typing.Final = 1000  # 1 km = 1000 m
    _KM_TO_MILE: typing.Final = 0.62137119  # 1 km = 0.62137119 mi
    _M_TO_IN: typing.Final = 39.3700787  # 1 m = 39.3700787 in

    # Units in terms of m/s
    _SPEED_CONVERSION: typing.Final = {
        Const.SPEED_METERS_PER_SECOND: 1,
        Const.SPEED_KILOMETERS_PER_HOUR: _HRS_TO_SECS / _KM_TO_M,
        Const.SPEED_MILES_PER_HOUR: _HRS_TO_SECS * _KM_TO_MILE / _KM_TO_M,
        Const.SPEED_MILLIMETERS_PER_DAY: (24 * _HRS_TO_SECS) * 1000,
        Const.SPEED_INCHES_PER_DAY: (24 * _HRS_TO_SECS) * _M_TO_IN,
        Const.SPEED_INCHES_PER_HOUR: _HRS_TO_SECS * _M_TO_IN,
    }

    _TEMPERATURE_UNITS: typing.Final = (
        Const.TEMP_CELSIUS,
        Const.TEMP_FAHRENHEIT,
        Const.TEMP_KELVIN,
    )

    _MASS_UNITS: typing.Final = (
        Const.MASS_POUNDS, 
        Const.MASS_OUNCES, 
        Const.MASS_KILOGRAMS, 
        Const.MASS_GRAMS
    )

    _VOLUME_UNITS: typing.Final = (
        Const.VOLUME_LITERS,
        Const.VOLUME_MILLILITERS,
        Const.VOLUME_GALLONS,
        Const.VOLUME_FLUID_OUNCE,
        Const.VOLUME_CUBIC_METERS,
        Const.VOLUME_CUBIC_FEET,
    )

    _PRESSURE_UNITS: typing.Final = (
        Const.PRESSURE_PA,
        Const.PRESSURE_HPA,
        Const.PRESSURE_KPA,
        Const.PRESSURE_BAR,
        Const.PRESSURE_CBAR,
        Const.PRESSURE_MBAR,
        Const.PRESSURE_INHG,
        Const.PRESSURE_PSI,
        Const.PRESSURE_MMHG,
    )

    _PRESSURE_CONVERSION: typing.Final = {
        Const.PRESSURE_PA: 1,
        Const.PRESSURE_HPA: 1 / 100,
        Const.PRESSURE_KPA: 1 / 1000,
        Const.PRESSURE_BAR: 1 / 100000,
        Const.PRESSURE_CBAR: 1 / 1000,
        Const.PRESSURE_MBAR: 1 / 100,
        Const.PRESSURE_INHG: 1 / 3386.389,
        Const.PRESSURE_PSI: 1 / 6894.757,
        Const.PRESSURE_MMHG: 1 / 133.322,
    }

    def __init__(
        self,
        name: str,
        temperature: str,
        length: str,
        wind_speed: str,
        volume: str,
        mass: str,
        pressure: str,
        accumulated_precipitation: str,
    ) -> None:
        """Initialize the unit system object."""
        errors: str = ", ".join(
            Const.UNIT_NOT_RECOGNIZED_TEMPLATE.format(unit, unit_type)
            for unit, unit_type in (
                (accumulated_precipitation, Const.ACCUMULATED_PRECIPITATION),
                (temperature, Const.TEMPERATURE),
                (length, Const.LENGTH),
                (wind_speed, Const.WIND_SPEED),
                (volume, Const.VOLUME),
                (mass, Const.MASS),
                (pressure, Const.PRESSURE),
            )
            if not UnitSystem._is_valid_unit(unit, unit_type)
        )

        if errors:
            raise ValueError(errors)

        self.name = name
        self.accumulated_precipitation_unit = accumulated_precipitation
        self.temperature_unit = temperature
        self.length_unit = length
        self.mass_unit = mass
        self.pressure_unit = pressure
        self.volume_unit = volume
        self.wind_speed_unit = wind_speed

    def _is_valid_unit(unit: str, unit_type: str) -> bool:
        """Check if the unit is valid for it's type."""
        if unit_type == Const.LENGTH:
            units = UnitSystem._LENGTH_UNITS
        elif unit_type == Const.ACCUMULATED_PRECIPITATION:
            units = UnitSystem._LENGTH_UNITS
        elif unit_type == Const.WIND_SPEED:
            units = UnitSystem._SPEED_UNITS
        elif unit_type == Const.TEMPERATURE:
            units = UnitSystem._TEMPERATURE_UNITS
        elif unit_type == Const.MASS:
            units = UnitSystem._MASS_UNITS
        elif unit_type == Const.VOLUME:
            units = UnitSystem._VOLUME_UNITS
        elif unit_type == Const.PRESSURE:
            units = UnitSystem._PRESSURE_UNITS
        else:
            return False
        return unit in units

    def _convert_length(value: float, unit_1: str, unit_2: str) -> float:
        """Convert one unit of measurement to another."""
        if unit_1 not in UnitSystem._LENGTH_UNITS:
            raise ValueError(Const.UNIT_NOT_RECOGNIZED_TEMPLATE.format(unit_1, Const.LENGTH))
        if unit_2 not in UnitSystem._LENGTH_UNITS:
            raise ValueError(Const.UNIT_NOT_RECOGNIZED_TEMPLATE.format(unit_2, Const.LENGTH))

        if not isinstance(value, numbers.Number):
            raise TypeError(f"{value} is not of numeric type")

        if unit_1 == unit_2 or unit_1 not in UnitSystem._LENGTH_UNITS:
            return value

        meters: float = UnitSystem._TO_METERS[unit_1](value)
        return UnitSystem._METERS_TO[unit_2](meters)


    def _convert_speed(value: float, unit_1: str, unit_2: str) -> float:
        """Convert one unit of measurement to another."""
        if unit_1 not in UnitSystem._SPEED_UNITS:
            raise ValueError(Const.UNIT_NOT_RECOGNIZED_TEMPLATE.format(unit_1, Const.SPEED))
        if unit_2 not in UnitSystem._SPEED_UNITS:
            raise ValueError(Const.UNIT_NOT_RECOGNIZED_TEMPLATE.format(unit_2, Const.SPEED))

        if not isinstance(value, numbers.Number):
            raise TypeError(f"{value} is not of numeric type")

        if unit_1 == unit_2:
            return value

        meters_per_second = value / UnitSystem._SPEED_CONVERSION[unit_1]
        return meters_per_second * UnitSystem._SPEED_CONVERSION[unit_2]

    def _fahrenheit_to_celsius(fahrenheit: float, interval: bool = False) -> float:
        """Convert a temperature in Fahrenheit to Celsius."""
        if interval:
            return fahrenheit / 1.8
        return (fahrenheit - 32.0) / 1.8


    def _kelvin_to_celsius(kelvin: float, interval: bool = False) -> float:
        """Convert a temperature in Kelvin to Celsius."""
        if interval:
            return kelvin
        return kelvin - 273.15


    def _celsius_to_fahrenheit(celsius: float, interval: bool = False) -> float:
        """Convert a temperature in Celsius to Fahrenheit."""
        if interval:
            return celsius * 1.8
        return celsius * 1.8 + 32.0


    def _celsius_to_kelvin(celsius: float, interval: bool = False) -> float:
        """Convert a temperature in Celsius to Fahrenheit."""
        if interval:
            return celsius
        return celsius + 273.15


    def _convert_temperature(
        temperature: float, from_unit: str, to_unit: str, interval: bool = False
    ) -> float:
        """Convert a temperature from one unit to another."""
        if from_unit not in UnitSystem._TEMPERATURE_UNITS:
            raise ValueError(Const.UNIT_NOT_RECOGNIZED_TEMPLATE.format(from_unit, Const.TEMPERATURE))
        if to_unit not in UnitSystem._TEMPERATURE_UNITS:
            raise ValueError(Const.UNIT_NOT_RECOGNIZED_TEMPLATE.format(to_unit, Const.TEMPERATURE))

        if from_unit == to_unit:
            return temperature

        if from_unit == Const.TEMP_CELSIUS:
            if to_unit == Const.TEMP_FAHRENHEIT:
                return UnitSystem._celsius_to_fahrenheit(temperature, interval)
            # kelvin
            return UnitSystem._celsius_to_kelvin(temperature, interval)

        if from_unit == Const.TEMP_FAHRENHEIT:
            if to_unit == Const.TEMP_CELSIUS:
                return UnitSystem._fahrenheit_to_celsius(temperature, interval)
            # kelvin
            return UnitSystem._celsius_to_kelvin(UnitSystem._fahrenheit_to_celsius(temperature, interval), interval)

        # from_unit == kelvin
        if to_unit == Const.TEMP_CELSIUS:
            return UnitSystem._kelvin_to_celsius(temperature, interval)
        # fahrenheit
        return UnitSystem._celsius_to_fahrenheit(UnitSystem._kelvin_to_celsius(temperature, interval), interval)

    def _liter_to_gallon(liter: float) -> float:
        """Convert a volume measurement in Liter to Gallon."""
        return liter * 0.2642


    def _gallon_to_liter(gallon: float) -> float:
        """Convert a volume measurement in Gallon to Liter."""
        return gallon * 3.785


    def _cubic_meter_to_cubic_feet(cubic_meter: float) -> float:
        """Convert a volume measurement in cubic meter to cubic feet."""
        return cubic_meter * 35.3146667


    def _cubic_feet_to_cubic_meter(cubic_feet: float) -> float:
        """Convert a volume measurement in cubic feet to cubic meter."""
        return cubic_feet * 0.0283168466

    def _convert_volume(volume: float, from_unit: str, to_unit: str) -> float:
        """Convert a temperature from one unit to another."""
        if from_unit not in UnitSystem._VOLUME_UNITS:
            raise ValueError(Const.UNIT_NOT_RECOGNIZED_TEMPLATE.format(from_unit, Const.VOLUME))
        if to_unit not in UnitSystem._VOLUME_UNITS:
            raise ValueError(Const.UNIT_NOT_RECOGNIZED_TEMPLATE.format(to_unit, Const.VOLUME))

        if not isinstance(volume, numbers.Number):
            raise TypeError(f"{volume} is not of numeric type")

        if from_unit == to_unit:
            return volume

        result: float = volume
        if from_unit == Const.VOLUME_LITERS and to_unit == Const.VOLUME_GALLONS:
            result = UnitSystem._liter_to_gallon(volume)
        elif from_unit == Const.VOLUME_GALLONS and to_unit == Const.VOLUME_LITERS:
            result = UnitSystem._gallon_to_liter(volume)
        elif from_unit == Const.VOLUME_CUBIC_METERS and to_unit == Const.VOLUME_CUBIC_FEET:
            result = UnitSystem._cubic_meter_to_cubic_feet(volume)
        elif from_unit == Const.VOLUME_CUBIC_FEET and to_unit == Const.VOLUME_CUBIC_METERS:
            result = UnitSystem._cubic_feet_to_cubic_meter(volume)
        return result

    def _convert_pressure(value: float, unit_1: str, unit_2: str) -> float:
        """Convert one unit of measurement to another."""
        if unit_1 not in UnitSystem._PRESSURE_UNITS:
            raise ValueError(Const.UNIT_NOT_RECOGNIZED_TEMPLATE.format(unit_1, Const.PRESSURE))
        if unit_2 not in UnitSystem._PRESSURE_UNITS:
            raise ValueError(Const.UNIT_NOT_RECOGNIZED_TEMPLATE.format(unit_2, Const.PRESSURE))

        if not isinstance(value, numbers.Number):
            raise TypeError(f"{value} is not of numeric type")

        if unit_1 == unit_2:
            return value

        pascals = value / UnitSystem._PRESSURE_CONVERSION[unit_1]
        return pascals * UnitSystem._PRESSURE_CONVERSION[unit_2]

    @property
    def is_metric(self) -> bool:
        """Determine if this is the metric unit system."""
        return self.name == Const.CONF_UNIT_SYSTEM_METRIC

    def temperature(self, temperature: float, from_unit: str) -> float:
        """Convert the given temperature to this unit system."""
        if not isinstance(temperature, numbers.Number):
            raise TypeError(f"{temperature!s} is not a numeric value.")
        return UnitSystem._convert_temperature(temperature, from_unit, self.temperature_unit)

    def mass(self, mass: float | None, from_unit: str) -> float:
        """Convert the given mass to this unit system."""
        if not isinstance(mass, numbers.Number):
            raise TypeError(f"{mass!s} is not a numeric value.")
        return UnitSystem._convert_mass(
            mass, from_unit, self.mass_unit
        )

    def length(self, length: float | None, from_unit: str) -> float:
        """Convert the given length to this unit system."""
        if not isinstance(length, numbers.Number):
            raise TypeError(f"{length!s} is not a numeric value.")

        # type ignore: https://github.com/python/mypy/issues/7207
        return UnitSystem._convert_length(  # type: ignore[unreachable]
            length, from_unit, self.length_unit
        )

    def accumulated_precipitation(self, precip: float | None, from_unit: str) -> float:
        """Convert the given length to this unit system."""
        if not isinstance(precip, numbers.Number):
            raise TypeError(f"{precip!s} is not a numeric value.")

        # type ignore: https://github.com/python/mypy/issues/7207
        return UnitSystem._convert_length(  # type: ignore[unreachable]
            precip, from_unit, self.accumulated_precipitation_unit
        )

    def pressure(self, pressure: float | None, from_unit: str) -> float:
        """Convert the given pressure to this unit system."""
        if not isinstance(pressure, numbers.Number):
            raise TypeError(f"{pressure!s} is not a numeric value.")

        # type ignore: https://github.com/python/mypy/issues/7207
        return pressure_util.convert(  # type: ignore[unreachable]
            pressure, from_unit, self.pressure_unit
        )

    def wind_speed(self, wind_speed: float | None, from_unit: str) -> float:
        """Convert the given wind_speed to this unit system."""
        if not isinstance(wind_speed, numbers.Number):
            raise TypeError(f"{wind_speed!s} is not a numeric value.")

        # type ignore: https://github.com/python/mypy/issues/7207
        return speed_util.convert(wind_speed, from_unit, self.wind_speed_unit)  # type: ignore[unreachable]

    def volume(self, volume: float | None, from_unit: str) -> float:
        """Convert the given volume to this unit system."""
        if not isinstance(volume, numbers.Number):
            raise TypeError(f"{volume!s} is not a numeric value.")

        # type ignore: https://github.com/python/mypy/issues/7207
        return volume_util.convert(volume, from_unit, self.volume_unit)  # type: ignore[unreachable]

    def as_dict(self) -> dict[str, str]:
        """Convert the unit system to a dictionary."""
        return {
            Const.LENGTH: self.length_unit,
            Const.ACCUMULATED_PRECIPITATION: self.accumulated_precipitation_unit,
            Const.MASS: self.mass_unit,
            Const.PRESSURE: self.pressure_unit,
            Const.TEMPERATURE: self.temperature_unit,
            Const.VOLUME: self.volume_unit,
            Const.WIND_SPEED: self.wind_speed_unit,
        }

    METRIC: UnitSystem | None = None
    IMPERIAL: UnitSystem | None = None

    def __static_init__():
        UnitSystem.METRIC = UnitSystem(
            Const.CONF_UNIT_SYSTEM_METRIC,
            Const.TEMP_CELSIUS,
            Const.LENGTH_KILOMETERS,
            Const.SPEED_METERS_PER_SECOND,
            Const.VOLUME_LITERS,
            Const.MASS_GRAMS,
            Const.PRESSURE_PA,
            Const.LENGTH_MILLIMETERS,
        )
        UnitSystem.IMPERIAL = UnitSystem(
            Const.CONF_UNIT_SYSTEM_IMPERIAL,
            Const.TEMP_FAHRENHEIT,
            Const.LENGTH_MILES,
            Const.SPEED_MILES_PER_HOUR,
            Const.VOLUME_GALLONS,
            Const.MASS_POUNDS,
            Const.PRESSURE_PSI,
            Const.LENGTH_INCHES,
        )

    __static_init__()


GPSType = tuple[float, float]
ConfigType = dict[str, typing.Any]
ContextType = Context
DiscoveryInfoType = dict[str, typing.Any]
EventType = Event
ServiceDataType = dict[str, typing.Any]
StateType = typing.Union[None, str, int, float]
TemplateVarsType = typing.Optional[collections.abc.Mapping[str, typing.Any]]
JsonType = typing.Union[list, dict, str] 
# Custom type for recorder Queries
QueryType = typing.Any
