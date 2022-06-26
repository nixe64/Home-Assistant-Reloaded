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

import collections
import typing

from .check_config_error import CheckConfigError
from .config_type import CONFIG_TYPE


@typing.overload
class SmartHomeControllerConfig:
    ...


# pylint: disable=unused-variable
class SmartHomeControllerConfig(collections.OrderedDict):
    """Configuration result with errors attribute."""

    def __init__(self) -> None:
        """Initialize HA config."""
        super().__init__()
        self.errors: list[CheckConfigError] = []

    def add_error(
        self,
        message: str,
        domain: str | None = None,
        config: CONFIG_TYPE | None = None,
    ) -> SmartHomeControllerConfig:
        """Add a single error."""
        self.errors.append(CheckConfigError(str(message), domain, config))
        return self

    @property
    def error_str(self) -> str:
        """Return errors as a string."""
        return "\n".join([err.message for err in self.errors])
