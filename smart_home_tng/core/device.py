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

import attr

from . import helpers
from .device_base import DeviceBase
from .device_registry_entry_disabler import DeviceRegistryEntryDisabler
from .device_registry_entry_type import DeviceRegistryEntryType


# pylint: disable=unused-variable
@attr.s(slots=True, frozen=True)
class Device(DeviceBase):
    """Device Registry Entry."""

    id: str = (attr.ib(factory=helpers.random_uuid_hex),)
    area_id: str | None = (attr.ib(default=None),)
    configuration_url: str | None = (attr.ib(default=None),)
    disabled_by: DeviceRegistryEntryDisabler | None = (attr.ib(default=None),)
    entry_type: DeviceRegistryEntryType | None = (attr.ib(default=None),)
    manufacturer: str | None = (attr.ib(default=None),)
    model: str | None = (attr.ib(default=None),)
    name_by_user: str | None = (attr.ib(default=None),)
    name: str | None = (attr.ib(default=None),)
    suggested_area: str | None = (attr.ib(default=None),)
    sw_version: str | None = (attr.ib(default=None),)
    hw_version: str | None = (attr.ib(default=None),)
    via_device_id: str | None = (attr.ib(default=None),)
    # This value is not stored, just used to keep track of events to fire.
    is_new: bool = (attr.ib(default=False),)

    @property
    def disabled(self) -> bool:
        """Return if entry is disabled."""
        return self.disabled_by is not None
