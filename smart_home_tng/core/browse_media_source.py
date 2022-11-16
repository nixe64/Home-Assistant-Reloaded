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

import typing

from .browse_media import BrowseMedia
from .const import Const


# pylint: disable=unused-variable
class BrowseMediaSource(BrowseMedia):
    """Represent a browsable media file."""

    def __init__(self, *, domain: str, identifier: str, **kwargs: typing.Any) -> None:
        """Initialize media source browse media."""
        media_content_id = f"{Const.MEDIA_SOURCE_URI_SCHEME}{domain or ''}"
        if identifier:
            media_content_id += f"/{identifier}"

        super().__init__(media_content_id=media_content_id, **kwargs)

        self._domain = domain
        self._identifier = identifier

    @property
    def domain(self) -> str:
        return self._domain

    @property
    def identifier(self) -> str:
        return self._identifier
