"""
Helper methods for various modules in Smart Home - The Next Generation.

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

import typing

import voluptuous as vol

from .color_temp_selector_config import ColorTempSelectorConfig
from .selector import SELECTORS, Selector


# pylint: disable=unused-variable
@SELECTORS.register("color_temp")
class ColorTempSelector(Selector):
    """Selector of an color temperature."""

    _CONFIG_SCHEMA: typing.Final = vol.Schema(
        {
            vol.Optional("max_mireds"): vol.Coerce(int),
            vol.Optional("min_mireds"): vol.Coerce(int),
        }
    )

    def config_schema(self, config: typing.Any) -> typing.Callable:
        return ColorTempSelector._CONFIG_SCHEMA(config)

    def __init__(self, config: ColorTempSelectorConfig | None = None) -> None:
        """Instantiate a selector."""
        super().__init__("color_temp", config)

    def __call__(self, data: typing.Any) -> int:
        """Validate the passed selection."""
        value: int = vol.All(
            vol.Coerce(float),
            vol.Range(
                min=self._config.get("min_mireds"),
                max=self._config.get("max_mireds"),
            ),
        )(data)
        return value