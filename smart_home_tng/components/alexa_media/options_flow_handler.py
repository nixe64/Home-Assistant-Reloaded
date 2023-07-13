"""
Amazon Alexa MediaPlayer Integration for Smart Home - The Next Generation.

Smart Home - TNG is a Home Automation framework for observing the state
of entities and react to changes. It is based on Home Assistant from
home-assistant.io and the Home Assistant Community.

Copyright (c) 2022-2023, Andreas Nixdorf

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

This integration is based custom_component "alexa_media_player"
from the Home Assistant Community Store (HACS), which is distributed
under the Terms of the Apache License, Version 2.0

The original source code and license terms can be found under:
https://github.com/custom_components/alexa_media_player
"""

import voluptuous as vol

from ... import core
from .const import Const


# pylint: disable=unused-variable
class OptionsFlowHandler(core.OptionsFlow):
    """Handle a option flow for Alexa Media."""

    def __init__(self, config_entry: core.ConfigEntry):
        """Initialize options flow."""
        super().__init__(None)
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Handle options flow."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        data_schema = vol.Schema(
            {
                vol.Optional(
                    Const.CONF_QUEUE_DELAY,
                    default=self._config_entry.options.get(
                        Const.CONF_QUEUE_DELAY, Const.DEFAULT_QUEUE_DELAY
                    ),
                ): vol.All(vol.Coerce(float), vol.Clamp(min=0)),
                vol.Required(
                    Const.CONF_EXTENDED_ENTITY_DISCOVERY,
                    default=self._config_entry.options.get(
                        Const.CONF_EXTENDED_ENTITY_DISCOVERY,
                        Const.DEFAULT_EXTENDED_ENTITY_DISCOVERY,
                    ),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=data_schema)
