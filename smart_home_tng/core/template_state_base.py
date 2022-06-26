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

from .const import Const
from .state import State
from .smart_home_controller import SmartHomeController
from .render_info import RenderInfo as ri


# pylint: disable=unused-variable
class TemplateStateBase(State):
    """Class to represent a state object in a template."""

    _COLLECTABLE_STATE_ATTRIBUTES: typing.Final = {
        "state",
        "attributes",
        "last_changed",
        "last_updated",
        "context",
        "domain",
        "object_id",
        "name",
    }

    __slots__ = ("_shc", "_collect")

    # Inheritance is done so functions that check against State keep working
    # pylint: disable=super-init-not-called
    def __init__(self, shc: SmartHomeController, collect: bool, entity_id: str) -> None:
        """Initialize template state."""
        self._shc = shc
        self._collect = collect
        self._entity_id = entity_id

    def _collect_state(self) -> None:
        if self._collect and ri.current:
            ri.current.add_entity(self._entity_id)

    # Jinja will try __getitem__ first and it avoids the need
    # to call is_safe_attribute
    def __getitem__(self, item):
        """Return a property as an attribute for jinja."""
        if item in TemplateStateBase._COLLECTABLE_STATE_ATTRIBUTES:
            # _collect_state inlined here for performance
            if self._collect and ri.current:
                ri.current.add_entity(self._entity_id)
            return getattr(self._state, item)
        if item == "entity_id":
            return self._entity_id
        if item == "state_with_unit":
            return self.state_with_unit
        raise KeyError

    @property
    def entity_id(self) -> str:
        """Wrap State.entity_id.

        Intentionally does not collect state
        """
        return self._entity_id

    @property
    def state(self) -> str:
        """Wrap State.state."""
        self._collect_state()
        return super().state

    @property
    def attributes(self):
        """Wrap State.attributes."""
        self._collect_state()
        return super().attributes

    @property
    def last_changed(self):
        """Wrap State.last_changed."""
        self._collect_state()
        return self._last_changed

    @property
    def last_updated(self):
        """Wrap State.last_updated."""
        self._collect_state()
        return self._last_updated

    @property
    def context(self):
        """Wrap State.context."""
        self._collect_state()
        return self._context

    @property
    def domain(self):
        """Wrap State.domain."""
        self._collect_state()
        return self._domain

    @property
    def object_id(self):
        """Wrap State.object_id."""
        self._collect_state()
        return self._object_id

    @property
    def name(self):
        """Wrap State.name."""
        self._collect_state()
        return super().name

    @property
    def state_with_unit(self) -> str:
        """Return the state concatenated with the unit if available."""
        self._collect_state()
        unit = self._attributes.get(Const.ATTR_UNIT_OF_MEASUREMENT)
        return f"{super().state} {unit}" if unit else super().state

    def __eq__(self, other: typing.Any) -> bool:
        """Ensure we collect on equality check."""
        self._collect_state()
        return super().__eq__(other)
