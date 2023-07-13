"""
Core components of Smart Home - The Next Generation.

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
"""

import typing

from .context import Context
from .trace_base import TraceBase


# pylint: disable=unused-variable
class RestoredTrace(TraceBase):
    """Container for a restored script or automation trace."""

    def __init__(self, data: dict[str, typing.Any]) -> None:
        """Restore from dict."""
        extended_dict = data["extended_dict"]
        short_dict = data["short_dict"]
        context = Context(
            user_id=extended_dict["context"]["user_id"],
            parent_id=extended_dict["context"]["parent_id"],
            context_id=extended_dict["context"]["id"],
        )
        self._context = context
        self._key = f"{extended_dict['domain']}.{extended_dict['item_id']}"
        self._run_id = extended_dict["run_id"]
        self._dict = extended_dict
        self._short_dict = short_dict

    @property
    def context(self) -> Context:
        return self._context

    @property
    def key(self) -> str:
        return self._key

    @property
    def run_id(self) -> str:
        return self._run_id

    def as_extended_dict(self) -> dict[str, typing.Any]:
        """Return an extended dictionary version of this RestoredTrace."""
        return self._dict

    def as_short_dict(self) -> dict[str, typing.Any]:
        """Return a brief dictionary version of this RestoredTrace."""
        return self._short_dict
