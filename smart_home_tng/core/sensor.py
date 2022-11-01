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

# pylint: disable=unused-variable

import contextlib
import dataclasses
import datetime as dt
import decimal as dec
import enum
import logging
import math
import typing

from ..backports import strenum
from . import helpers
from .callback import callback
from .const import Const
from .entity import _SensorEntityBase
from .entity_description import EntityDescription
from .extra_stored_data import ExtraStoredData
from .state_type import StateType
from .unit_system import UnitSystem

_LOGGER: typing.Final = logging.getLogger(__name__)


class _DeviceClass(strenum.LowercaseStrEnum):
    """Device class for sensors."""

    # apparent power (VA)
    APPARENT_POWER = enum.auto()

    # Air Quality Index
    AQI = enum.auto()

    # % of battery that is left
    BATTERY = enum.auto()

    # ppm (parts per million) Carbon Monoxide gas concentration
    CO = enum.auto()

    # ppm (parts per million) Carbon Dioxide gas concentration
    CO2 = enum.auto()

    # current (A)
    CURRENT = enum.auto()

    # date (ISO8601)
    DATE = enum.auto()

    # fixed duration (TIME_DAYS, TIME_HOURS, TIME_MINUTES, TIME_SECONDS)
    DURATION = enum.auto()

    # energy (Wh, kWh, MWh)
    ENERGY = enum.auto()

    # frequency (Hz, kHz, MHz, GHz)
    FREQUENCY = enum.auto()

    # gas (m³ or ft³)
    GAS = enum.auto()

    # % of humidity in the air
    HUMIDITY = enum.auto()

    # current light level (lx/lm)
    ILLUMINANCE = enum.auto()

    # Amount of money (currency)
    MONETARY = enum.auto()

    # Amount of NO2 (µg/m³)
    NITROGEN_DIOXIDE = enum.auto()

    # Amount of NO (µg/m³)
    NITROGEN_MONOXIDE = enum.auto()

    # Amount of N2O  (µg/m³)
    NITROUS_OXIDE = enum.auto()

    # Amount of O3 (µg/m³)
    OZONE = enum.auto()

    # Particulate matter <= 0.1 μm (µg/m³)
    PM1 = enum.auto()

    # Particulate matter <= 10 μm (µg/m³)
    PM10 = enum.auto()

    # Particulate matter <= 2.5 μm (µg/m³)
    PM25 = enum.auto()

    # power factor (%)
    POWER_FACTOR = enum.auto()

    # power (W/kW)
    POWER = enum.auto()

    # pressure (hPa/mbar)
    PRESSURE = enum.auto()

    # reactive power (var)
    REACTIVE_POWER = enum.auto()

    # signal strength (dB/dBm)
    SIGNAL_STRENGTH = enum.auto()

    # Amount of SO2 (µg/m³)
    SULPHUR_DIOXIDE = enum.auto()

    # temperature (C/F)
    TEMPERATURE = enum.auto()

    # timestamp (ISO8601)
    TIMESTAMP = enum.auto()

    # Amount of VOC (µg/m³)
    VOLATILE_ORGANIC_COMPOUNDS = enum.auto()

    # voltage (V)
    VOLTAGE = enum.auto()


class _StateClass(strenum.LowercaseStrEnum):
    """State class for sensors."""

    MEASUREMENT = enum.auto()
    """The state represents a measurement in present time"""

    TOTAL = enum.auto()
    """The state represents a total amount, e.g. net energy consumption"""

    TOTAL_INCREASING = enum.auto()
    """The state represents a monotonically increasing total, e.g. an amount of consumed gas"""


@dataclasses.dataclass()
class _EntityDescription(EntityDescription):
    """A class that describes sensor entities."""

    device_class: _DeviceClass | str = None
    last_reset: dt.datetime = None
    native_unit_of_measurement: str = None
    state_class: _StateClass | str = None
    unit_of_measurement: None = None  # Type override, use native_unit_of_measurement


@dataclasses.dataclass
class _ExtraStoredData(ExtraStoredData):
    """Object to hold extra stored data."""

    native_value: StateType | dt.date | dt.datetime | dec.Decimal
    native_unit_of_measurement: str

    def as_dict(self) -> dict[str, typing.Any]:
        """Return a dict representation of the sensor data."""
        native_value: StateType | dt.date | dt.datetime | dec.Decimal | dict[
            str, str
        ] = self.native_value
        if isinstance(native_value, (dt.date, dt.datetime)):
            native_value = {
                "__type": str(type(native_value)),
                "isoformat": native_value.isoformat(),
            }
        if isinstance(native_value, dec.Decimal):
            native_value = {
                "__type": str(type(native_value)),
                "decimal_str": str(native_value),
            }
        return {
            "native_value": native_value,
            "native_unit_of_measurement": self.native_unit_of_measurement,
        }

    @classmethod
    def from_dict(cls, restored: dict[str, typing.Any]):
        """Initialize a stored sensor state from a dict."""
        try:
            native_value = restored["native_value"]
            native_unit_of_measurement: str = restored["native_unit_of_measurement"]
        except KeyError:
            return None
        try:
            type_ = native_value["__type"]
            if type_ == "<class 'datetime.datetime'>":
                native_value = helpers.parse_datetime(native_value["isoformat"])
            elif type_ == "<class 'datetime.date'>":
                native_value = helpers.parse_date(native_value["isoformat"])
            elif type_ == "<class 'decimal.Decimal'>":
                native_value = dec.Decimal(native_value["decimal_str"])
        except TypeError:
            # native_value is not a dict
            pass
        except KeyError:
            # native_value is a dict, but does not have all values
            return None
        except dec.InvalidOperation:
            # native_value coulnd't be returned from decimal_str
            return None

        return cls(native_value, native_unit_of_measurement)


_ATTR_LAST_RESET: typing.Final = "last_reset"
_ATTR_STATE_CLASS: typing.Final = "state_class"
_UNIT_CONVERSIONS: dict[str, typing.Callable[[float, str, str], float]] = {
    _DeviceClass.PRESSURE: UnitSystem.convert_pressure,
    _DeviceClass.TEMPERATURE: UnitSystem.convert_temperature,
}
_UNIT_RATIOS: dict[str, dict[str, float]] = {
    _DeviceClass.PRESSURE: UnitSystem.PRESSURE_RATIO,
    _DeviceClass.TEMPERATURE: UnitSystem.TEMPERATURE_RATIO,
}
_VALID_UNITS: typing.Final = {
    _DeviceClass.PRESSURE: UnitSystem.PRESSURE_UNITS,
    _DeviceClass.TEMPERATURE: UnitSystem.TEMPERATURE_UNITS,
}


class _Entity(_SensorEntityBase):
    """Base class for sensor entities."""

    _entity_description: _EntityDescription
    _attr_device_class: _DeviceClass | str
    _attr_last_reset: dt.datetime
    _attr_native_unit_of_measurement: str
    _attr_native_value: StateType | dt.date | dt.datetime = None
    _attr_state_class: _StateClass | str
    _attr_state: None = None  # Subclasses of SensorEntity should not set this
    _attr_unit_of_measurement: None = (
        None  # Subclasses of SensorEntity should not set this
    )
    _last_reset_reported = False
    _temperature_conversion_reported = False
    _sensor_option_unit_of_measurement: str = None

    # Temporary private attribute to track if deprecation has been logged.
    __datetime_as_string_deprecation_logged = False

    async def async_internal_added_to_shc(self) -> None:
        """Call when the sensor entity is added to the Smart Home Controller."""
        await super().async_internal_added_to_shc()
        if not self.registry_entry:
            return
        self.async_registry_entry_updated()

    @property
    def entity_description(self) -> _EntityDescription:
        return super().entity_description

    @property
    def device_class(self) -> str:
        """Return the class of this entity."""
        if hasattr(self, "_attr_device_class"):
            return str(self._attr_device_class)
        if (description := self.entity_description) is not None:
            return str(description.device_class)
        return None

    @property
    def state_class(self) -> _StateClass | str:
        """Return the state class of this entity, if any."""
        if hasattr(self, "_attr_state_class"):
            return self._attr_state_class
        if (description := self.entity_description) is not None:
            return description.state_class
        return None

    @property
    def last_reset(self) -> dt.datetime:
        """Return the time when the sensor was last reset, if any."""
        if hasattr(self, "_attr_last_reset"):
            return self._attr_last_reset
        if (description := self.entity_description) is not None:
            return description.last_reset
        return None

    @property
    def capability_attributes(self) -> typing.Mapping[str, typing.Any]:
        """Return the capability attributes."""
        if state_class := self.state_class:
            return {_ATTR_STATE_CLASS: state_class}

        return None

    @typing.final
    @property
    def state_attributes(self) -> dict[str, typing.Any]:
        """Return state attributes."""
        if last_reset := self.last_reset:
            if self.state_class != _StateClass.TOTAL and not self._last_reset_reported:
                self._last_reset_reported = True
                report_issue = self._suggest_report_issue()
                # This should raise in Home Assistant Core 2022.5
                _LOGGER.warning(
                    f"Entity {self._entity_id} ({type(self)}) with state_class "
                    + f"{self.state_class} has set last_reset. Setting "
                    + "last_reset for entities with state_class other than 'total' is "
                    + "not supported. "
                    + "Please update your configuration if state_class is manually "
                    + f"configured, otherwise {report_issue}",
                    self.entity_id,
                    type(self),
                    self.state_class,
                    report_issue,
                )

            if self.state_class == _StateClass.TOTAL:
                return {_ATTR_LAST_RESET: last_reset.isoformat()}

        return None

    @property
    def native_value(self) -> StateType | dt.date | dt.datetime:
        """Return the value reported by the sensor."""
        return self._attr_native_value

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement of the sensor, if any."""
        if hasattr(self, "_attr_native_unit_of_measurement"):
            return self._attr_native_unit_of_measurement
        if (description := self.entity_description) is not None:
            return description.native_unit_of_measurement
        return None

    @typing.final
    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement of the entity, after unit conversion."""
        if self._sensor_option_unit_of_measurement:
            return self._sensor_option_unit_of_measurement

        native_unit_of_measurement = self.native_unit_of_measurement

        if (
            self.device_class == _DeviceClass.TEMPERATURE
            and native_unit_of_measurement
            in (Const.TEMP_CELSIUS, Const.TEMP_FAHRENHEIT)
        ):
            return self._shc.config.units.temperature_unit

        return native_unit_of_measurement

    @typing.final
    @property
    def state(self) -> typing.Any:
        """Return the state of the sensor and perform unit conversions, if needed."""
        native_unit_of_measurement = self.native_unit_of_measurement
        unit_of_measurement = self.unit_of_measurement
        value = self.native_value
        device_class = self.device_class

        # Received a datetime
        if value is not None and device_class == _DeviceClass.TIMESTAMP:
            try:
                # We cast the value, to avoid using isinstance, but satisfy
                # typechecking. The errors are guarded in this try.
                value = typing.cast(dt.datetime, value)
                if value.tzinfo is None:
                    raise ValueError(
                        f"Invalid datetime: {self._entity_id} provides state '{value}', "
                        "which is missing timezone information"
                    )

                if value.tzinfo != dt.timezone.utc:
                    value = value.astimezone(dt.timezone.utc)

                return value.isoformat(timespec="seconds")
            except (AttributeError, TypeError) as err:
                raise ValueError(
                    f"Invalid datetime: {self._entity_id} has a timestamp device class "
                    + f"but does not provide a datetime state but {type(value)}"
                ) from err

        # Received a date value
        if value is not None and device_class == _DeviceClass.DATE:
            try:
                # We cast the value, to avoid using isinstance, but satisfy
                # typechecking. The errors are guarded in this try.
                value = typing.cast(dt.date, value)
                return value.isoformat()
            except (AttributeError, TypeError) as err:
                raise ValueError(
                    f"Invalid date: {self._entity_id} has a date device class "
                    f"but does not provide a date state but {type(value)}"
                ) from err

        if (
            value is not None
            and native_unit_of_measurement != unit_of_measurement
            and self.device_class in _UNIT_CONVERSIONS
        ):
            assert unit_of_measurement
            assert native_unit_of_measurement

            value_s = str(value)
            prec = len(value_s) - value_s.index(".") - 1 if "." in value_s else 0

            # Scale the precision when converting to a larger unit
            # For example 1.1 Wh should be rendered as 0.0011 kWh, not 0.0 kWh
            ratio_log = max(
                0,
                math.log10(
                    _UNIT_RATIOS[self.device_class][native_unit_of_measurement]
                    / _UNIT_RATIOS[self.device_class][unit_of_measurement]
                ),
            )
            prec = prec + math.floor(ratio_log)

            # Suppress ValueError (Could not convert sensor_value to float)
            with contextlib.suppress(ValueError):
                value_f = float(value)
                value_f_new = _UNIT_CONVERSIONS[self.device_class](
                    value_f,
                    native_unit_of_measurement,
                    unit_of_measurement,
                )

                # Round to the wanted precision
                value = round(value_f_new) if prec == 0 else round(value_f_new, prec)

        return value

    def __repr__(self) -> str:
        """Return the representation.

        Entity.__repr__ includes the state in the generated string, this fails if we're
        called before self._shc is set.
        """
        if not self._shc:
            return f"<Entity {self.name}>"

        return super().__repr__()

    @callback
    def async_registry_entry_updated(self) -> None:
        """Run when the entity registry entry has been updated."""
        assert self._registry_entry
        if (
            (sensor_options := self._registry_entry.options.get("sensor"))
            and (custom_unit := sensor_options.get(Const.CONF_UNIT_OF_MEASUREMENT))
            and (device_class := self.device_class) in _UNIT_CONVERSIONS
            and self.native_unit_of_measurement in _VALID_UNITS[device_class]
            and custom_unit in _VALID_UNITS[device_class]
        ):
            self._sensor_option_unit_of_measurement = custom_unit
            return

        self._sensor_option_unit_of_measurement = None


# pylint: disable=invalid-name
class Sensor:
    """Sensor namespace."""

    ATTR_LAST_RESET: typing.Final = _ATTR_LAST_RESET
    ATTR_STATE_CLASS: typing.Final = _ATTR_STATE_CLASS
    STATE_CLASSES: typing.Final[list[str]] = [cls.value for cls in _StateClass]

    DeviceClass: typing.TypeAlias = _DeviceClass
    Entity: typing.TypeAlias = _Entity
    EntityDescription: typing.TypeAlias = _EntityDescription
    ExtraStoredData: typing.TypeAlias = _ExtraStoredData
    StateClass: typing.TypeAlias = _StateClass
