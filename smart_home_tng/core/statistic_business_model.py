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


This module includes all classes that are required to support
platform compiled statistics for the recorder component.
"""

# pylint: disable=unused-variable

import dataclasses
import datetime as dt
import typing


class StatisticMetaData(typing.TypedDict):
    """Statistic meta data class."""

    has_mean: bool
    has_sum: bool
    name: str
    source: str
    statistic_id: str
    unit_of_measurement: str


class StatisticDataBase(typing.TypedDict):
    """Mandatory fields for statistic data class."""

    start: dt.datetime


class StatisticData(StatisticDataBase, total=False):
    """Statistic data class."""

    mean: float
    min: float
    max: float
    last_reset: dt.datetime
    state: float
    sum: float


class StatisticResult(typing.TypedDict):
    """Statistic result data class.

    Allows multiple datapoints for the same statistic_id.
    """

    meta: StatisticMetaData
    stat: StatisticData


@dataclasses.dataclass()
class PlatformCompiledStatistics:
    """Compiled Statistics from a platform."""

    platform_stats: list[StatisticResult]
    current_metadata: dict[str, tuple[int, StatisticMetaData]]
