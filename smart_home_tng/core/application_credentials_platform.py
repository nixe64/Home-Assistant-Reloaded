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

import abc

from .abstract_oauth2_implementation import AbstractOAuth2Implementation
from .authorization_server import AuthorizationServer
from .client_credential import ClientCredential
from .platform_implementation import PlatformImplementation


# pylint: disable=unused-variable
class ApplicationCredentialsPlatform(PlatformImplementation):
    """
    Required base class for all integrations, that implement
    the Application Credentials Platform.
    """

    @abc.abstractmethod
    async def async_get_authorization_server(self) -> AuthorizationServer:
        """Return authorization server, for the default auth implementation."""

    @abc.abstractmethod
    async def async_get_auth_implementation(
        self,
        auth_domain: str,
        credential: ClientCredential,
    ) -> AbstractOAuth2Implementation:
        """Return a custom auth implementation."""