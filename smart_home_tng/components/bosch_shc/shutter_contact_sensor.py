"""
Bosch SHC Integration for Smart Home - The Next Generation.

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

import boschshcpy as bosch

from ... import core
from .bosch_entity import BoschEntity


# pylint: disable=unused-variable
class ShutterContactSensor(BoschEntity, core.BinarySensor.Entity):
    """Representation of a SHC shutter contact sensor."""

    @property
    def is_on(self):
        """Return the state of the sensor."""
        return (
            self._device.state
            == bosch.SHCShutterContact.ShutterContactService.State.OPEN
        )

    @property
    def device_class(self):
        """Return the class of this device."""
        switcher = {
            "ENTRANCE_DOOR": core.BinarySensor.DeviceClass.DOOR,
            "REGULAR_WINDOW": core.BinarySensor.DeviceClass.WINDOW,
            "FRENCH_WINDOW": core.BinarySensor.DeviceClass.DOOR,
            "GENERIC": core.BinarySensor.DeviceClass.WINDOW,
        }
        return str(
            switcher.get(
                self._device.device_class, core.BinarySensor.DeviceClass.WINDOW
            )
        )
