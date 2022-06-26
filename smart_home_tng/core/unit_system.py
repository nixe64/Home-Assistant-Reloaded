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

import numbers
import typing

from .const import Const


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
    Const.MASS_GRAMS,
)

_MASS_CONVERSION: typing.Final = {
    Const.MASS_GRAMS: 1,
    Const.MASS_KILOGRAMS: 1000,
    Const.MASS_OUNCES: 28.49523125,
    Const.MASS_POUNDS: 16 * 28.349523125,
}

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


@typing.overload
class UnitSystem:
    ...


class UnitSystem:
    """A container for units of measure."""

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
            if not self._is_valid_unit(unit, unit_type)
        )

        if errors:
            raise ValueError(errors)

        self._name = name
        self._accumulated_precipitation_unit = accumulated_precipitation
        self._temperature_unit = temperature
        self._length_unit = length
        self._mass_unit = mass
        self._pressure_unit = pressure
        self._volume_unit = volume
        self._wind_speed_unit = wind_speed

    @property
    def name(self) -> str:
        return self._name

    @property
    def accumulated_precipitation_unit(self) -> str:
        return self._accumulated_precipitation_unit

    @property
    def temperature_unit(self) -> str:
        return self._temperature_unit

    @property
    def length_unit(self) -> str:
        return self._length_unit

    @property
    def mass_unit(self) -> str:
        return self._mass_unit

    @property
    def pressure_unit(self) -> str:
        return self._pressure_unit

    @property
    def volume_unit(self) -> str:
        return self._volume_unit

    @property
    def wind_speed_unit(self) -> str:
        return self._wind_speed_unit

    @staticmethod
    def _is_valid_unit(unit: str, unit_type: str) -> bool:
        """Check if the unit is valid for it's type."""
        if unit_type == Const.LENGTH:
            units = _LENGTH_UNITS
        elif unit_type == Const.ACCUMULATED_PRECIPITATION:
            units = _LENGTH_UNITS
        elif unit_type == Const.WIND_SPEED:
            units = _SPEED_UNITS
        elif unit_type == Const.TEMPERATURE:
            units = _TEMPERATURE_UNITS
        elif unit_type == Const.MASS:
            units = _MASS_UNITS
        elif unit_type == Const.VOLUME:
            units = _VOLUME_UNITS
        elif unit_type == Const.PRESSURE:
            units = _PRESSURE_UNITS
        else:
            return False
        return unit in units

    @staticmethod
    def _convert_length(value: float, unit_1: str, unit_2: str) -> float:
        """Convert one unit of measurement to another."""
        if unit_1 not in _LENGTH_UNITS:
            raise ValueError(
                Const.UNIT_NOT_RECOGNIZED_TEMPLATE.format(unit_1, Const.LENGTH)
            )
        if unit_2 not in _LENGTH_UNITS:
            raise ValueError(
                Const.UNIT_NOT_RECOGNIZED_TEMPLATE.format(unit_2, Const.LENGTH)
            )

        if not isinstance(value, numbers.Number):
            raise TypeError(f"{value} is not of numeric type")

        if unit_1 == unit_2:
            return value

        meters: float = _TO_METERS[unit_1](value)
        return _METERS_TO[unit_2](meters)

    @staticmethod
    def _convert_mass(value: float, unit_1: str, unit_2: str) -> float:
        if unit_1 not in _MASS_UNITS:
            raise ValueError(
                Const.UNIT_NOT_RECOGNIZED_TEMPLATE.format(unit_1, Const.MASS)
            )
        if unit_2 not in _MASS_UNITS:
            raise ValueError(
                Const.UNIT_NOT_RECOGNIZED_TEMPLATE.format(unit_2, Const.MASS)
            )

        if not isinstance(value, numbers.Number):
            raise TypeError(f"{value} is not of numeric type")

        if unit_1 == unit_2:
            return value

        grams = value * _MASS_CONVERSION[unit_1]
        return grams / _MASS_CONVERSION[unit_2]

    @staticmethod
    def _convert_speed(value: float, unit_1: str, unit_2: str) -> float:
        """Convert one unit of measurement to another."""
        if unit_1 not in _SPEED_UNITS:
            raise ValueError(
                Const.UNIT_NOT_RECOGNIZED_TEMPLATE.format(unit_1, Const.SPEED)
            )
        if unit_2 not in _SPEED_UNITS:
            raise ValueError(
                Const.UNIT_NOT_RECOGNIZED_TEMPLATE.format(unit_2, Const.SPEED)
            )

        if not isinstance(value, numbers.Number):
            raise TypeError(f"{value} is not of numeric type")

        if unit_1 == unit_2:
            return value

        meters_per_second = value / _SPEED_CONVERSION[unit_1]
        return meters_per_second * _SPEED_CONVERSION[unit_2]

    @staticmethod
    def _fahrenheit_to_celsius(fahrenheit: float, interval: bool = False) -> float:
        """Convert a temperature in Fahrenheit to Celsius."""
        if interval:
            return fahrenheit / 1.8
        return (fahrenheit - 32.0) / 1.8

    @staticmethod
    def _kelvin_to_celsius(kelvin: float, interval: bool = False) -> float:
        """Convert a temperature in Kelvin to Celsius."""
        if interval:
            return kelvin
        return kelvin - 273.15

    @staticmethod
    def _celsius_to_fahrenheit(celsius: float, interval: bool = False) -> float:
        """Convert a temperature in Celsius to Fahrenheit."""
        if interval:
            return celsius * 1.8
        return celsius * 1.8 + 32.0

    @staticmethod
    def _celsius_to_kelvin(celsius: float, interval: bool = False) -> float:
        """Convert a temperature in Celsius to Fahrenheit."""
        if interval:
            return celsius
        return celsius + 273.15

    @staticmethod
    def _convert_temperature(
        temperature: float, from_unit: str, to_unit: str, interval: bool = False
    ) -> float:
        """Convert a temperature from one unit to another."""
        if from_unit not in _TEMPERATURE_UNITS:
            raise ValueError(
                Const.UNIT_NOT_RECOGNIZED_TEMPLATE.format(from_unit, Const.TEMPERATURE)
            )
        if to_unit not in _TEMPERATURE_UNITS:
            raise ValueError(
                Const.UNIT_NOT_RECOGNIZED_TEMPLATE.format(to_unit, Const.TEMPERATURE)
            )

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
            return UnitSystem._celsius_to_kelvin(
                UnitSystem._fahrenheit_to_celsius(temperature, interval), interval
            )

        # from_unit == kelvin
        if to_unit == Const.TEMP_CELSIUS:
            return UnitSystem._kelvin_to_celsius(temperature, interval)
        # fahrenheit
        return UnitSystem._celsius_to_fahrenheit(
            UnitSystem._kelvin_to_celsius(temperature, interval), interval
        )

    @staticmethod
    def _liter_to_gallon(liter: float) -> float:
        """Convert a volume measurement in Liter to Gallon."""
        return liter * 0.2642

    @staticmethod
    def _gallon_to_liter(gallon: float) -> float:
        """Convert a volume measurement in Gallon to Liter."""
        return gallon * 3.785

    @staticmethod
    def _cubic_meter_to_cubic_feet(cubic_meter: float) -> float:
        """Convert a volume measurement in cubic meter to cubic feet."""
        return cubic_meter * 35.3146667

    @staticmethod
    def _cubic_feet_to_cubic_meter(cubic_feet: float) -> float:
        """Convert a volume measurement in cubic feet to cubic meter."""
        return cubic_feet * 0.0283168466

    @staticmethod
    def _convert_volume(volume: float, from_unit: str, to_unit: str) -> float:
        """Convert a temperature from one unit to another."""
        if from_unit not in _VOLUME_UNITS:
            raise ValueError(
                Const.UNIT_NOT_RECOGNIZED_TEMPLATE.format(from_unit, Const.VOLUME)
            )
        if to_unit not in _VOLUME_UNITS:
            raise ValueError(
                Const.UNIT_NOT_RECOGNIZED_TEMPLATE.format(to_unit, Const.VOLUME)
            )

        if not isinstance(volume, numbers.Number):
            raise TypeError(f"{volume} is not of numeric type")

        if from_unit == to_unit:
            return volume

        result: float = volume
        if from_unit == Const.VOLUME_LITERS and to_unit == Const.VOLUME_GALLONS:
            result = UnitSystem._liter_to_gallon(volume)
        elif from_unit == Const.VOLUME_GALLONS and to_unit == Const.VOLUME_LITERS:
            result = UnitSystem._gallon_to_liter(volume)
        elif (
            from_unit == Const.VOLUME_CUBIC_METERS
            and to_unit == Const.VOLUME_CUBIC_FEET
        ):
            result = UnitSystem._cubic_meter_to_cubic_feet(volume)
        elif (
            from_unit == Const.VOLUME_CUBIC_FEET
            and to_unit == Const.VOLUME_CUBIC_METERS
        ):
            result = UnitSystem._cubic_feet_to_cubic_meter(volume)
        return result

    @staticmethod
    def _convert_pressure(value: float, unit_1: str, unit_2: str) -> float:
        """Convert one unit of measurement to another."""
        if unit_1 not in _PRESSURE_UNITS:
            raise ValueError(
                Const.UNIT_NOT_RECOGNIZED_TEMPLATE.format(unit_1, Const.PRESSURE)
            )
        if unit_2 not in _PRESSURE_UNITS:
            raise ValueError(
                Const.UNIT_NOT_RECOGNIZED_TEMPLATE.format(unit_2, Const.PRESSURE)
            )

        if not isinstance(value, numbers.Number):
            raise TypeError(f"{value} is not of numeric type")

        if unit_1 == unit_2:
            return value

        pascals = value / _PRESSURE_CONVERSION[unit_1]
        return pascals * _PRESSURE_CONVERSION[unit_2]

    @property
    def is_metric(self) -> bool:
        """Determine if this is the metric unit system."""
        return self._name == Const.CONF_UNIT_SYSTEM_METRIC

    def temperature(self, temperature: float, from_unit: str) -> float:
        """Convert the given temperature to this unit system."""
        if not isinstance(temperature, numbers.Number):
            raise TypeError(f"{temperature!s} is not a numeric value.")
        return UnitSystem._convert_temperature(
            temperature, from_unit, self._temperature_unit
        )

    def mass(self, mass: float | None, from_unit: str) -> float:
        """Convert the given mass to this unit system."""
        if not isinstance(mass, numbers.Number):
            raise TypeError(f"{mass!s} is not a numeric value.")
        return UnitSystem._convert_mass(mass, from_unit, self._mass_unit)

    def length(self, length: float | None, from_unit: str) -> float:
        """Convert the given length to this unit system."""
        if not isinstance(length, numbers.Number):
            raise TypeError(f"{length!s} is not a numeric value.")

        return UnitSystem._convert_length(length, from_unit, self._length_unit)

    def accumulated_precipitation(self, precip: float | None, from_unit: str) -> float:
        """Convert the given length to this unit system."""
        if not isinstance(precip, numbers.Number):
            raise TypeError(f"{precip!s} is not a numeric value.")

        return UnitSystem._convert_length(
            precip, from_unit, self._accumulated_precipitation_unit
        )

    def pressure(self, pressure: float | None, from_unit: str) -> float:
        """Convert the given pressure to this unit system."""
        if not isinstance(pressure, numbers.Number):
            raise TypeError(f"{pressure!s} is not a numeric value.")

        return UnitSystem._convert_pressure(pressure, from_unit, self._pressure_unit)

    def wind_speed(self, wind_speed: float | None, from_unit: str) -> float:
        """Convert the given wind_speed to this unit system."""
        if not isinstance(wind_speed, numbers.Number):
            raise TypeError(f"{wind_speed!s} is not a numeric value.")

        return UnitSystem._convert_speed(wind_speed, from_unit, self.wind_speed_unit)

    def volume(self, volume: float | None, from_unit: str) -> float:
        """Convert the given volume to this unit system."""
        if not isinstance(volume, numbers.Number):
            raise TypeError(f"{volume!s} is not a numeric value.")

        return UnitSystem._convert_volume(volume, from_unit, self.volume_unit)

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

    METRIC: typing.Final[UnitSystem] = UnitSystem(
        Const.CONF_UNIT_SYSTEM_METRIC,
        Const.TEMP_CELSIUS,
        Const.LENGTH_KILOMETERS,
        Const.SPEED_METERS_PER_SECOND,
        Const.VOLUME_LITERS,
        Const.MASS_GRAMS,
        Const.PRESSURE_PA,
        Const.LENGTH_MILLIMETERS,
    )
    IMPERIAL: typing.Final[UnitSystem] = UnitSystem(
        Const.CONF_UNIT_SYSTEM_IMPERIAL,
        Const.TEMP_FAHRENHEIT,
        Const.LENGTH_MILES,
        Const.SPEED_MILES_PER_HOUR,
        Const.VOLUME_GALLONS,
        Const.MASS_POUNDS,
        Const.PRESSURE_PSI,
        Const.LENGTH_INCHES,
    )
