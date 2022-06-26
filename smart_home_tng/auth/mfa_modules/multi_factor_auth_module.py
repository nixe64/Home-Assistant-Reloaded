"""
Multi Factor Authentication Layer for Smart Home - The Next Generation.

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

import logging
import typing

import voluptuous as vol
import voluptuous.humanize as vh

from ... import core


@typing.overload
class SetupFlow:
    ...


_DEFAULT_TITLE: typing.Final = "Unnamed auth module"
_MAX_RETRY_TIME: typing.Final = 3
_LOGGER: typing.Final = logging.getLogger(__name__)


# pylint: disable=unused-variable
class MultiFactorAuthModule:
    """Multi-factor Auth Module of validation function."""

    def __init__(
        self, shc: core.SmartHomeController, config: dict[str, typing.Any]
    ) -> None:
        """Initialize an auth module."""
        self._shc = shc
        self._config = config

    @property
    def default_title(self) -> str:
        return _DEFAULT_TITLE

    @property
    def max_retry_time(self) -> int:
        return _MAX_RETRY_TIME

    @property
    def id(self) -> str:
        """Return id of the auth module.

        Default is same as type
        """
        return self._config.get(core.Const.CONF_ID, self.type)

    @property
    def type(self) -> str:
        """Return type of the module."""
        return self._config[core.Const.CONF_TYPE]

    @property
    def name(self) -> str:
        """Return the name of the auth module."""
        return self._config.get(core.Const.CONF_NAME, self.default_title)

    # Implement by extending class

    @property
    def input_schema(self) -> vol.Schema:
        """Return a voluptuous schema to define mfa auth module's input."""
        raise NotImplementedError

    async def async_setup_flow(self, _user_id: str) -> SetupFlow:
        """Return a data entry flow handler for setup module.

        Mfa module should extend SetupFlow
        """
        raise NotImplementedError

    async def async_setup_user(
        self, _user_id: str, _setup_data: typing.Any
    ) -> typing.Any:
        """Set up user for mfa auth module."""
        raise NotImplementedError

    async def async_depose_user(self, _user_id: str) -> None:
        """Remove user from mfa module."""
        raise NotImplementedError

    async def async_is_user_setup(self, _user_id: str) -> bool:
        """Return whether user is setup."""
        raise NotImplementedError

    async def async_validate(
        self, _user_id: str, _user_input: dict[str, typing.Any]
    ) -> bool:
        """Return True if validation passed."""
        raise NotImplementedError


async def auth_mfa_module_from_config(
    shc: core.SmartHomeController, config: dict[str, typing.Any]
) -> MultiFactorAuthModule:
    """Initialize an auth module from a config."""
    module_name: str = config[core.Const.CONF_TYPE]
    module = await shc.load_mfa_module(module_name)

    try:
        config = module.CONFIG_SCHEMA(config)
    except vol.Invalid as err:
        _LOGGER.error(
            f"Invalid configuration for multi-factor module {module_name}: "
            + f"{vh.humanize_error(config, err)}"
        )
        raise

    return MULTI_FACTOR_AUTH_MODULES[module_name](shc, config)


# pylint: disable=unused-variable
MULTI_FACTOR_AUTH_MODULES: typing.Final[
    core.Registry[str, type[MultiFactorAuthModule]]
] = core.Registry()

# pylint: disable=unused-variable
MULTI_FACTOR_AUTH_MODULE_SCHEMA: typing.Final = vol.Schema(
    {
        vol.Required(core.Const.CONF_TYPE): str,
        vol.Optional(core.Const.CONF_NAME): str,
        # Specify ID if you have two mfa auth module for same type.
        vol.Optional(core.Const.CONF_ID): str,
    },
    extra=vol.ALLOW_EXTRA,
)
