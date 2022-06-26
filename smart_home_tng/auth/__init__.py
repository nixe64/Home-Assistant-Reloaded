"""
Authentication Layer for Smart Home - The Next Generation.

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

# pylint: disable=unused-variable, unused-import

from . import mfa_modules, permissions, providers
from .auth_manager import AuthManager, auth_manager_from_config
from .auth_manager_flow_manager import AuthManagerFlowManager
from .auth_store import AuthStore
from .const import Const
from .credentials import Credentials
from .group import Group
from .invalid_auth_error import InvalidAuthError
from .invalid_provider import InvalidProvider
from .invalid_user_error import InvalidUserError
from .mfa_modules.multi_factor_auth_module import MULTI_FACTOR_AUTH_MODULE_SCHEMA
from .providers.auth_provider import AUTH_PROVIDER_SCHEMA
from .refresh_token import RefreshToken
from .token_type import TokenType
from .user import User
from .user_meta import UserMeta
