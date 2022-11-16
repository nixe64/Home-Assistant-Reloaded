"""
Switch As X Component for Smart Home - The Next Generation.

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

from ... import core
from .base_toggle_entity import BaseToggleEntity


# pylint: disable=unused-variable
class FanSwitch(BaseToggleEntity, core.Fan.Entity):
    """Represents a Switch as a Fan."""

    @property
    def is_on(self) -> bool:
        """Return true if the entity is on.

        Fan logic uses speed percentage or preset mode to determine
        if it's on or off, however, when using a wrapped switch, we
        just use the wrapped switch's state.
        """
        return self._attr_is_on

    async def async_turn_on(
        self,
        _percentage: int = None,
        _preset_mode: str = None,
        **_kwargs: typing.Any,
    ) -> None:
        """Turn on the fan.

        Arguments of the turn_on methods fan entity differ,
        thus we need to override them here.
        """
        await super().async_turn_on()


async def async_setup_fans(
    owner: core.SmartHomeControllerComponent,
    config_entry: core.ConfigEntry,
    async_add_entities: core.AddEntitiesCallback,
) -> None:
    """Initialize Fan Switch config entry."""
    registry = owner.controller.entity_registry
    entity_id = registry.async_validate_entity_id(
        config_entry.options[core.Const.CONF_ENTITY_ID]
    )
    wrapped_switch = registry.async_get(entity_id)
    device_id = wrapped_switch.device_id if wrapped_switch else None

    async_add_entities(
        [
            FanSwitch(
                config_entry.title,
                entity_id,
                config_entry.entry_id,
                device_id,
            )
        ]
    )
