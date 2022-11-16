"""
Home Assistant Cloud Component for Smart Home - The Next Generation.

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

import async_timeout
import voluptuous as vol
from aiohttp import web

from ... import core
from .const import Const
from .helpers import _handle_cloud_errors

if not typing.TYPE_CHECKING:

    class CloudComponent:
        pass


if typing.TYPE_CHECKING:
    from .cloud_component import CloudComponent

_VALIDATOR: typing.Final = core.RequestDataValidator(
    vol.Schema({vol.Required("email"): str})
)


# pylint: disable=unused-variable
class CloudResendConfirmView(core.SmartHomeControllerView):
    """Resend email confirmation code."""

    def __init__(self, owner: CloudComponent):
        url = "/api/cloud/resend_confirm"
        name = "api:cloud:resend_confirm"
        super().__init__(url, name)
        self._owner = owner

    @_handle_cloud_errors
    async def post(self, request: web.Request):
        """Handle resending confirm email code request."""
        data, error = await _VALIDATOR.async_get_request_data(request)
        if error is not None:
            return error

        cloud = self._owner.cloud

        async with async_timeout.timeout(Const.REQUEST_TIMEOUT):
            await cloud.auth.async_resend_email_confirm(data["email"])

        return self.json_message("ok")
