"""
Location helpers for Smart Home - The Next Generation.

detect_location_info and elevation are mocked by default during tests.

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

import asyncio
import math
import typing

import aiohttp
from .. import Const


_WHOAMI_URL: typing.Final = "https://services.home-assistant.io/whoami/v1"
_WHOAMI_URL_DEV: typing.Final = "https://services-dev.home-assistant.workers.dev/whoami/v1"

# Constants from https://github.com/maurycyp/vincenty
# Earth ellipsoid according to WGS 84
# Axis a of the ellipsoid (Radius of the earth in meters)
_AXIS_A: typing.Final = 6378137
# Flattening f = (a-b) / a
_FLATTENING: typing.Final = 1 / 298.257223563
# Axis b of the ellipsoid in meters.
_AXIS_B: typing.Final = 6356752.314245

_MILES_PER_KILOMETER: typing.Final = 0.621371
_MAX_ITERATIONS: typing.Final = 200
_CONVERGENCE_THRESHOLD: typing.Final = 1e-12


class LocationInfo(typing.NamedTuple):
    """Tuple with location information."""
    ip: str
    country_code: str
    currency: str
    region_code: str
    region_name: str
    city: str
    zip_code: str
    time_zone: str
    latitude: float
    longitude: float
    use_metric: bool


async def async_detect_location_info(
    session: aiohttp.ClientSession,
) -> LocationInfo | None:
    """Detect location information."""
    if (data := await _get_whoami(session)) is None:
        return None

    data["use_metric"] = data["country_code"] not in ("US", "MM", "LR")

    return LocationInfo(**data)


def distance(
    lat1: float | None, lon1: float | None, lat2: float, lon2: float
) -> float | None:
    """Calculate the distance in meters between two points.

    Async friendly.
    """
    if lat1 is None or lon1 is None:
        return None
    result = vincenty((lat1, lon1), (lat2, lon2))
    if result is None:
        return None
    return result * 1000


# Author: https://github.com/maurycyp
# Source: https://github.com/maurycyp/vincenty
# License: https://github.com/maurycyp/vincenty/blob/master/LICENSE
def vincenty(
    point1: tuple[float, float], point2: tuple[float, float], miles: bool = False
) -> float | None:
    """
    Vincenty formula (inverse method) to calculate the distance.

    Result in kilometers or miles between two points on the surface of a
    spheroid.

    Async friendly.
    """
    # short-circuit coincident points
    if point1[0] == point2[0] and point1[1] == point2[1]:
        return 0.0

    # pylint: disable=invalid-name
    U1 = math.atan((1 - _FLATTENING) * math.tan(math.radians(point1[0])))
    U2 = math.atan((1 - _FLATTENING) * math.tan(math.radians(point2[0])))
    L = math.radians(point2[1] - point1[1])
    Lambda = L

    sinU1 = math.sin(U1)
    cosU1 = math.cos(U1)
    sinU2 = math.sin(U2)
    cosU2 = math.cos(U2)

    for _ in range(_MAX_ITERATIONS):
        sinLambda = math.sin(Lambda)
        cosLambda = math.cos(Lambda)
        sinSigma = math.sqrt(
            (cosU2 * sinLambda) ** 2 + (cosU1 * sinU2 - sinU1 * cosU2 * cosLambda) ** 2
        )
        if sinSigma == 0.0:
            return 0.0  # coincident points
        cosSigma = sinU1 * sinU2 + cosU1 * cosU2 * cosLambda
        sigma = math.atan2(sinSigma, cosSigma)
        sinAlpha = cosU1 * cosU2 * sinLambda / sinSigma
        cosSqAlpha = 1 - sinAlpha**2
        try:
            cos2SigmaM = cosSigma - 2 * sinU1 * sinU2 / cosSqAlpha
        except ZeroDivisionError:
            cos2SigmaM = 0
        C = _FLATTENING / 16 * cosSqAlpha * (4 + _FLATTENING * (4 - 3 * cosSqAlpha))
        LambdaPrev = Lambda
        Lambda = L + (1 - C) * _FLATTENING * sinAlpha * (
            sigma
            + C * sinSigma * (cos2SigmaM + C * cosSigma * (-1 + 2 * cos2SigmaM**2))
        )
        if abs(Lambda - LambdaPrev) < _CONVERGENCE_THRESHOLD:
            break  # successful convergence
    else:
        return None  # failure to converge

    uSq = cosSqAlpha * (_AXIS_A**2 - _AXIS_B**2) / (_AXIS_B**2)
    A = 1 + uSq / 16384 * (4096 + uSq * (-768 + uSq * (320 - 175 * uSq)))
    B = uSq / 1024 * (256 + uSq * (-128 + uSq * (74 - 47 * uSq)))
    deltaSigma = (
        B
        * sinSigma
        * (
            cos2SigmaM
            + B
            / 4
            * (
                cosSigma * (-1 + 2 * cos2SigmaM**2)
                - B
                / 6
                * cos2SigmaM
                * (-3 + 4 * sinSigma**2)
                * (-3 + 4 * cos2SigmaM**2)
            )
        )
    )
    s = _AXIS_B * A * (sigma - deltaSigma)

    s /= 1000  # Conversion of meters to kilometers
    if miles:
        s *= _MILES_PER_KILOMETER  # kilometers to miles

    return round(s, 6)


async def _get_whoami(session: aiohttp.ClientSession) -> dict[str, typing.Any] | None:
    """Query whoami.home-assistant.io for location data."""
    try:
        resp = await session.get(
            _WHOAMI_URL_DEV if Const.__version__.endswith("0.dev0") else _WHOAMI_URL, timeout=30
        )
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return None

    try:
        raw_info = await resp.json()
    except (aiohttp.ClientError, ValueError):
        return None

    return {
        "ip": raw_info.get("ip"),
        "country_code": raw_info.get("country"),
        "currency": raw_info.get("currency"),
        "region_code": raw_info.get("region_code"),
        "region_name": raw_info.get("region"),
        "city": raw_info.get("city"),
        "zip_code": raw_info.get("postal_code"),
        "time_zone": raw_info.get("timezone"),
        "latitude": float(raw_info.get("latitude")),
        "longitude": float(raw_info.get("longitude")),
    }
