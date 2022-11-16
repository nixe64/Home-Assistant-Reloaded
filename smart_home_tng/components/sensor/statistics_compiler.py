"""
Sensor Component for Smart Home - The Next Generation.

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

import collections.abc
import datetime as dt
import itertools
import logging
import math
import typing

from ... import core

# pylint: disable=unused-variable

_LOGGER: typing.Final = logging.getLogger(__name__)

_DEFAULT_STATISTICS: typing.Final = {
    core.Sensor.StateClass.MEASUREMENT: {"mean", "min", "max"},
    core.Sensor.StateClass.TOTAL: {"sum"},
    core.Sensor.StateClass.TOTAL_INCREASING: {"sum"},
}

# Normalized units which will be stored in the statistics table
_DEVICE_CLASS_UNITS: typing.Final = dict[str, str](
    {
        core.Sensor.DeviceClass.ENERGY: core.Const.ENERGY_KILO_WATT_HOUR,
        core.Sensor.DeviceClass.POWER: core.Const.POWER_WATT,
        core.Sensor.DeviceClass.PRESSURE: core.Const.PRESSURE_PA,
        core.Sensor.DeviceClass.TEMPERATURE: core.Const.TEMP_CELSIUS,
        core.Sensor.DeviceClass.GAS: core.Const.VOLUME_CUBIC_METERS,
    }
)

_DEFAULT_UNITS: typing.Final = core.UnitSystem.METRIC()

_UNIT_CONVERSIONS: typing.Final = dict[str, dict[str, typing.Callable]](
    {
        # Convert energy to kWh
        core.Sensor.DeviceClass.ENERGY: {
            core.Const.ENERGY_KILO_WATT_HOUR: lambda x: x,
            core.Const.ENERGY_MEGA_WATT_HOUR: lambda x: x * 1000,
            core.Const.ENERGY_WATT_HOUR: lambda x: x / 1000,
        },
        # Convert power W
        core.Sensor.DeviceClass.POWER: {
            core.Const.POWER_WATT: lambda x: x,
            core.Const.POWER_KILO_WATT: lambda x: x * 1000,
        },
        # Convert pressure to Pa
        # Note: pressure_util.convert is bypassed to avoid redundant error checking
        core.Sensor.DeviceClass.PRESSURE: {
            core.Const.PRESSURE_BAR: lambda x: _DEFAULT_UNITS.pressure(
                x, core.Const.PRESSURE_BAR
            ),
            core.Const.PRESSURE_HPA: lambda x: _DEFAULT_UNITS.pressure(
                x, core.Const.PRESSURE_HPA
            ),
            core.Const.PRESSURE_INHG: lambda x: _DEFAULT_UNITS.pressure(
                x, core.Const.PRESSURE_INHG
            ),
            core.Const.PRESSURE_KPA: lambda x: _DEFAULT_UNITS.pressure(
                x, core.Const.PRESSURE_KPA
            ),
            core.Const.PRESSURE_MBAR: lambda x: _DEFAULT_UNITS.pressure(
                x, core.Const.PRESSURE_MBAR
            ),
            core.Const.PRESSURE_PA: lambda x: x,
            core.Const.PRESSURE_PSI: lambda x: _DEFAULT_UNITS.pressure(
                x, core.Const.PRESSURE_PSI
            ),
        },
        # Convert temperature to °C
        # Note: temperature_util.convert is bypassed to avoid redundant error checking
        core.Sensor.DeviceClass.TEMPERATURE: {
            core.Const.TEMP_CELSIUS: lambda x: x,
            core.Const.TEMP_FAHRENHEIT: lambda x: _DEFAULT_UNITS.temperature(
                x, core.Const.TEMP_FAHRENHEIT
            ),
            core.Const.TEMP_KELVIN: lambda x: _DEFAULT_UNITS.temperature(
                x, core.Const.TEMP_KELVIN
            ),
        },
        # Convert volume to cubic meter
        core.Sensor.DeviceClass.GAS: {
            core.Const.VOLUME_CUBIC_METERS: lambda x: x,
            # metric unitsystem uses liters: 1000l == 1 m³
            core.Const.VOLUME_CUBIC_FEET: lambda x: _DEFAULT_UNITS.volume(
                x, core.Const.VOLUME_CUBIC_FEET
            )
            / 1000,
        },
    }
)

_LINK_DEV_STATISTICS: typing.Final = (
    "https://my.home-assistant.io/redirect/developer_statistics"
)


def _compile_statistics(
    owner: core.SensorComponent,
    rec_comp: core.RecorderComponent,
    session: core.SqlSession,
    start: dt.datetime,
    end: dt.datetime,
    sensor_states: list[core.State],
    warned_unstable_unit: set[str],
    warned_unsupported_unit: set[str],
) -> core.PlatformCompiledStatistics:
    """Compile statistics for all entities during start-end."""
    result: list[core.StatisticResult] = []

    wanted_statistics = _wanted_statistics(sensor_states)
    old_metadatas = rec_comp.get_metadata_with_session(
        session, statistic_ids=[state.entity_id for state in sensor_states]
    )

    # Get history between start and end
    entities_full_history = [
        i.entity_id for i in sensor_states if "sum" in wanted_statistics[i.entity_id]
    ]
    history_list: collections.abc.MutableMapping[str, list[core.State]] = {}
    if entities_full_history:
        history_list = rec_comp.get_full_significant_states_with_session(
            session,
            start - dt.timedelta.resolution,
            end,
            entity_ids=entities_full_history,
            significant_changes_only=False,
        )
    entities_significant_history = [
        i.entity_id
        for i in sensor_states
        if "sum" not in wanted_statistics[i.entity_id]
    ]
    if entities_significant_history:
        _history_list = rec_comp.get_full_significant_states_with_session(
            session,
            start - dt.timedelta.resolution,
            end,
            entity_ids=entities_significant_history,
        )
        history_list = {**history_list, **_history_list}
    # If there are no recent state changes, the sensor's state may already be pruned
    # from the recorder. Get the state from the state machine instead.
    for _state in sensor_states:
        if _state.entity_id not in history_list:
            history_list[_state.entity_id] = [_state]

    to_process = []
    to_query = []
    for _state in sensor_states:
        entity_id = _state.entity_id
        if entity_id not in history_list:
            continue

        device_class = _state.attributes.get(core.Const.ATTR_DEVICE_CLASS)
        entity_history = history_list[entity_id]
        unit, fstates = _normalize_states(
            old_metadatas,
            entity_history,
            device_class,
            entity_id,
            warned_unstable_unit,
            warned_unsupported_unit,
        )

        if not fstates:
            continue

        state_class = _state.attributes[core.Sensor.ATTR_STATE_CLASS]

        to_process.append((entity_id, unit, state_class, fstates))
        if "sum" in wanted_statistics[entity_id]:
            to_query.append(entity_id)

    last_stats = rec_comp.get_latest_short_term_statistics(
        to_query, metadata=old_metadatas
    )
    for (  # pylint: disable=too-many-nested-blocks
        entity_id,
        unit,
        state_class,
        fstates,
    ) in to_process:
        # Check metadata
        if old_metadata := old_metadatas.get(entity_id):
            if old_metadata[1]["unit_of_measurement"] != unit:
                if entity_id not in warned_unstable_unit:
                    warned_unstable_unit.add(entity_id)
                    desc = "normalized " if device_class in _DEVICE_CLASS_UNITS else ""
                    _LOGGER.warning(
                        f"The {desc}unit of {entity_id} ({unit}) does not match "
                        + "the unit of already compiled statistics "
                        + f"({old_metadata[1]['unit_of_measurement']}). Generation "
                        + "of long term statistics will be suppressed unless the unit "
                        + f"changes back to {old_metadata[1]['unit_of_measurement']}. "
                        + f"Go to {_LINK_DEV_STATISTICS} to fix this",
                    )
                continue

        # Set meta data
        meta: core.StatisticMetaData = {
            "has_mean": "mean" in wanted_statistics[entity_id],
            "has_sum": "sum" in wanted_statistics[entity_id],
            "name": None,
            "source": core.Const.RECORDER_COMPONENT_NAME,
            "statistic_id": entity_id,
            "unit_of_measurement": unit,
        }

        # Make calculations
        stat: core.StatisticData = {"start": start}
        if "max" in wanted_statistics[entity_id]:
            stat["max"] = max(*itertools.islice(zip(*fstates), 1))
        if "min" in wanted_statistics[entity_id]:
            stat["min"] = min(*itertools.islice(zip(*fstates), 1))

        if "mean" in wanted_statistics[entity_id]:
            stat["mean"] = _time_weighted_average(fstates, start, end)

        if "sum" in wanted_statistics[entity_id]:
            last_reset = old_last_reset = None
            new_state = old_state = None
            _sum = 0.0
            if entity_id in last_stats:
                # We have compiled history for this sensor before, use that as a starting point
                last_reset = old_last_reset = last_stats[entity_id][0]["last_reset"]
                new_state = old_state = last_stats[entity_id][0]["state"]
                _sum = last_stats[entity_id][0]["sum"] or 0.0

            for fstate, state in fstates:
                reset = False
                if (
                    state_class != core.Sensor.StateClass.TOTAL_INCREASING
                    and (
                        last_reset := _last_reset_as_utc_isoformat(
                            state.attributes.get("last_reset"), entity_id
                        )
                    )
                    != old_last_reset
                    and last_reset is not None
                ):
                    if old_state is None:
                        _LOGGER.info(
                            f"Compiling initial sum statistics for {entity_id}, "
                            + f"zero point set to {fstate}",
                        )
                    else:
                        _LOGGER.info(
                            f"Detected new cycle for {entity_id}, last_reset set to "
                            + f"{last_reset} (old last_reset {old_last_reset})",
                        )
                    reset = True
                elif old_state is None and last_reset is None:
                    reset = True
                    _LOGGER.info(
                        f"Compiling initial sum statistics for {entity_id}, "
                        + f"zero point set to {fstate}",
                    )
                elif state_class == core.Sensor.StateClass.TOTAL_INCREASING:
                    try:
                        if old_state is None or owner.reset_detected(
                            entity_id, fstate, new_state, state
                        ):
                            reset = True
                            _LOGGER.info(
                                f"Detected new cycle for {entity_id}, value dropped "
                                + f"from {fstate} to {new_state}, "
                                + "triggered by state with last_updated set to "
                                + f"{state.last_updated.isoformat()}",
                            )
                    except core.SmartHomeControllerError:
                        continue

                if reset:
                    # The sensor has been reset, update the sum
                    if old_state is not None:
                        _sum += new_state - old_state
                    # ..and update the starting point
                    new_state = fstate
                    old_last_reset = last_reset
                    # Force a new cycle for an existing sensor to start at 0
                    if old_state is not None:
                        old_state = 0.0
                    else:
                        old_state = new_state
                else:
                    new_state = fstate

            if new_state is None or old_state is None:
                # No valid updates
                continue

            # Update the sum with the last state
            _sum += new_state - old_state
            if last_reset is not None:
                stat["last_reset"] = core.helpers.parse_datetime(last_reset)
            stat["sum"] = _sum
            stat["state"] = new_state

        result.append({"meta": meta, "stat": stat})

    return core.PlatformCompiledStatistics(result, old_metadatas)


def _wanted_statistics(sensor_states: list[core.State]) -> dict[str, set[str]]:
    """Prepare a dict with wanted statistics for entities."""
    wanted_statistics = {}
    for state in sensor_states:
        state_class = state.attributes[core.Sensor.ATTR_STATE_CLASS]
        wanted_statistics[state.entity_id] = _DEFAULT_STATISTICS[state_class]
    return wanted_statistics


def _normalize_states(
    old_metadatas: dict[str, tuple[int, core.StatisticMetaData]],
    entity_history: typing.Iterable[core.State],
    device_class: str,
    entity_id: str,
    warned_unstable_unit: set[str],
    warned_unsupported_unit: set[str],
) -> tuple[str, list[tuple[float, core.State]]]:
    """Normalize units."""
    unit = None

    if device_class not in _UNIT_CONVERSIONS:
        # We're not normalizing this device class, return the state as they are
        fstates = []
        for state in entity_history:
            try:
                fstate = _parse_float(state.state)
            except (ValueError, TypeError):  # TypeError to guard for NULL state in DB
                continue
            fstates.append((fstate, state))

        if fstates:
            all_units = _get_units(fstates)
            if len(all_units) > 1:
                if entity_id not in warned_unstable_unit:
                    warned_unstable_unit.add(entity_id)
                    extra = ""
                    if old_metadata := old_metadatas.get(entity_id):
                        extra = (
                            " and matches the unit of already compiled statistics "
                            + f"({old_metadata[1]['unit_of_measurement']})"
                        )
                    _LOGGER.warning(
                        f"The unit of {entity_id} is changing, got multiple {all_units}, "
                        + "generation of long term statistics will be suppressed unless "
                        + f"the unit is stable{extra}. "
                        + f"Go to {_LINK_DEV_STATISTICS} to fix this",
                    )
                return None, []
            unit = fstates[0][1].attributes.get(core.Const.ATTR_UNIT_OF_MEASUREMENT)
        return unit, fstates

    fstates = []

    for state in entity_history:
        try:
            fstate = _parse_float(state.state)
        except ValueError:
            continue
        unit = state.attributes.get(core.Const.ATTR_UNIT_OF_MEASUREMENT)
        # Exclude unsupported units from statistics
        if unit not in _UNIT_CONVERSIONS[device_class]:
            if entity_id not in warned_unsupported_unit:
                warned_unsupported_unit.add(entity_id)
                _LOGGER.warning(
                    f"{entity_id} has unit {unit} which is unsupported for "
                    + f"device_class {device_class}",
                )
            continue

        fstates.append((_UNIT_CONVERSIONS[device_class][unit](fstate), state))

    return _DEVICE_CLASS_UNITS[device_class], fstates


def _parse_float(state: str) -> float:
    """Parse a float string, throw on inf or nan."""
    fstate = float(state)
    if math.isnan(fstate) or math.isinf(fstate):
        raise ValueError
    return fstate


def _get_units(fstates: list[tuple[float, core.State]]) -> set[str]:
    """Return True if all states have the same unit."""
    return {
        item[1].attributes.get(core.Const.ATTR_UNIT_OF_MEASUREMENT) for item in fstates
    }


def _time_weighted_average(
    fstates: list[tuple[float, core.State]], start: dt.datetime, end: dt.datetime
) -> float:
    """Calculate a time weighted average.

    The average is calculated by weighting the states by duration in seconds between
    state changes.
    Note: there's no interpolation of values between state changes.
    """
    old_fstate: float = None
    old_start_time: dt.datetime = None
    accumulated = 0.0

    for fstate, state in fstates:
        # The recorder will give us the last known state, which may be well
        # before the requested start time for the statistics
        start_time = start if state.last_updated < start else state.last_updated
        if old_start_time is None:
            # Adjust start time, if there was no last known state
            start = start_time
        else:
            duration = start_time - old_start_time
            # Accumulate the value, weighted by duration until next state change
            assert old_fstate is not None
            accumulated += old_fstate * duration.total_seconds()

        old_fstate = fstate
        old_start_time = start_time

    if old_fstate is not None:
        # Accumulate the value, weighted by duration until end of the period
        assert old_start_time is not None
        duration = end - old_start_time
        accumulated += old_fstate * duration.total_seconds()

    return accumulated / (end - start).total_seconds()


def _last_reset_as_utc_isoformat(last_reset_s: typing.Any, entity_id: str) -> str:
    """Parse last_reset and convert it to UTC."""
    if last_reset_s is None:
        return None
    if isinstance(last_reset_s, str):
        last_reset = core.helpers.parse_datetime(last_reset_s)
    else:
        last_reset = None
    if last_reset is None:
        _LOGGER.warning(f"Ignoring invalid last reset '{last_reset_s}' for {entity_id}")
        return None
    return core.helpers.as_utc(last_reset).isoformat()
