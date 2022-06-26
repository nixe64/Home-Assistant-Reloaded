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

import collections.abc
import typing

import attr

from . import helpers
from .callback import callback
from .const import Const
from .entity_category import EntityCategory
from .entity_registry_entry_disabler import EntityRegistryEntryDisabler
from .entity_registry_entry_hider import EntityRegistryEntryHider
from .smart_home_controller import SmartHomeController


# pylint: disable=unused-variable
@attr.s(slots=True, frozen=True)
class EntityRegistryEntry:
    """Entity Registry Entry."""

    _entity_id: str = attr.ib()
    _unique_id: str = attr.ib()
    _platform: str = attr.ib()
    _area_id: str | None = attr.ib(default=None)
    _capabilities: collections.abc.Mapping[str, typing.Any] | None = attr.ib(
        default=None
    )
    _config_entry_id: str | None = attr.ib(default=None)
    _device_class: str | None = attr.ib(default=None)
    _device_id: str | None = attr.ib(default=None)
    _domain: str = attr.ib(init=False, repr=False)
    _disabled_by: EntityRegistryEntryDisabler | None = attr.ib(default=None)
    _entity_category: EntityCategory | None = attr.ib(default=None)
    _hidden_by: EntityRegistryEntryHider | None = attr.ib(default=None)
    _icon: str | None = attr.ib(default=None)
    _id: str = attr.ib(factory=helpers.random_uuid_hex)
    _name: str | None = attr.ib(default=None)
    _options: collections.abc.Mapping[
        str, collections.abc.Mapping[str, typing.Any]
    ] = attr.ib(default=None, converter=attr.converters.default_if_none(factory=dict))
    # As set by integration
    _original_device_class: str | None = attr.ib(default=None)
    _original_icon: str | None = attr.ib(default=None)
    _original_name: str | None = attr.ib(default=None)
    _supported_features: int = attr.ib(default=0)
    _unit_of_measurement: str | None = attr.ib(default=None)

    @_domain.default
    def _domain_default(self) -> str:
        """Compute domain value."""
        return helpers.split_entity_id(self.entity_id)[0]

    @property
    def entity_id(self) -> str:
        return self._entity_id

    @property
    def unique_id(self) -> str:
        return self._unique_id

    @property
    def platform(self) -> str:
        return self._platform

    @property
    def area_id(self) -> str | None:
        return self._area_id

    @property
    def capabilities(self) -> collections.abc.Mapping[str, typing.Any] | None:
        return self._capabilities

    @property
    def config_entry_id(self) -> str | None:
        return self._config_entry_id

    @property
    def device_class(self) -> str | None:
        return self._device_class

    @property
    def device_id(self) -> str | None:
        return self._device_id

    @property
    def domain(self) -> str:
        return self._domain

    @property
    def disabled_by(self) -> EntityRegistryEntryDisabler | None:
        return self._disabled_by

    @property
    def entity_category(self) -> EntityCategory | None:
        return self._entity_category

    @property
    def hidden_by(self) -> EntityRegistryEntryHider | None:
        return self._hidden_by

    @property
    def icon(self) -> str | None:
        return self._icon

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str | None:
        return self._name

    @property
    def options(
        self,
    ) -> collections.abc.Mapping[str, collections.abc.Mapping[str, typing.Any]] | None:
        return self._options

    @property
    def original_device_class(self) -> str | None:
        return self._original_device_class

    @property
    def original_icon(self) -> str | None:
        return self._original_icon

    @property
    def original_name(self) -> str | None:
        return self._original_name

    @property
    def supported_features(self) -> int:
        return self._supported_features

    @property
    def unit_of_measurement(self) -> str | None:
        return self._unit_of_measurement

    @property
    def disabled(self) -> bool:
        """Return if entry is disabled."""
        return self._disabled_by is not None

    @property
    def hidden(self) -> bool:
        """Return if entry is hidden."""
        return self._hidden_by is not None

    @callback
    def write_unavailable_state(self, shc: SmartHomeController) -> None:
        """Write the unavailable state to the state machine."""
        attrs: dict[str, typing.Any] = {Const.ATTR_RESTORED: True}

        if self._capabilities is not None:
            attrs.update(self._capabilities)

        device_class = self._device_class or self.original_device_class
        if device_class is not None:
            attrs[Const.ATTR_DEVICE_CLASS] = device_class

        icon = self._icon or self._original_icon
        if icon is not None:
            attrs[Const.ATTR_ICON] = icon

        name = self._name or self._original_name
        if name is not None:
            attrs[Const.ATTR_FRIENDLY_NAME] = name

        if self._supported_features is not None:
            attrs[Const.ATTR_SUPPORTED_FEATURES] = self._supported_features

        if self._unit_of_measurement is not None:
            attrs[Const.ATTR_UNIT_OF_MEASUREMENT] = self._unit_of_measurement

        shc.states.async_set(self.entity_id, Const.STATE_UNAVAILABLE, attrs)
