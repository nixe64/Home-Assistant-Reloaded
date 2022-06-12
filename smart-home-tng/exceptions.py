"""
The exceptions used by Smart Home - The Next Generation.

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
from __future__ import annotations

import collections.abc
import typing

import attr

if typing.TYPE_CHECKING:
    from . import Context


class HomeAssistantError(Exception):
    """General Home Assistant exception occurred."""


class InvalidEntityFormatError(HomeAssistantError):
    """When an invalid formatted entity is encountered."""


class NoEntitySpecifiedError(HomeAssistantError):
    """When no entity is specified."""


class TemplateError(HomeAssistantError):
    """Error during template rendering."""

    def __init__(self, exception: Exception) -> None:
        """Init the error."""
        super().__init__(f"{exception.__class__.__name__}: {exception}")


@attr.s
class ConditionError(HomeAssistantError):
    """Error during condition evaluation."""

    # The type of the failed condition, such as 'and' or 'numeric_state'
    type: str = attr.ib()

    @staticmethod
    def _indent(indent: int, message: str) -> str:
        """Return indentation."""
        return "  " * indent + message

    def output(self, indent: int) -> collections.abc.Generator[str, None, None]:
        """Yield an indented representation."""
        raise NotImplementedError()

    def __str__(self) -> str:
        """Return string representation."""
        return "\n".join(list(self.output(indent=0)))


@attr.s
class ConditionErrorMessage(ConditionError):
    """Condition error message."""

    # A message describing this error
    message: str = attr.ib()

    def output(self, indent: int) -> collections.abc.Generator[str, None, None]:
        """Yield an indented representation."""
        yield self._indent(indent, f"In '{self.type}' condition: {self.message}")


@attr.s
class ConditionErrorIndex(ConditionError):
    """Condition error with index."""

    # The zero-based index of the failed condition, for conditions with multiple parts
    index: int = attr.ib()
    # The total number of parts in this condition, including non-failed parts
    total: int = attr.ib()
    # The error that this error wraps
    error: ConditionError = attr.ib()

    def output(self, indent: int) -> collections.abc.Generator[str, None, None]:
        """Yield an indented representation."""
        if self.total > 1:
            yield self._indent(
                indent, f"In '{self.type}' (item {self.index+1} of {self.total}):"
            )
        else:
            yield self._indent(indent, f"In '{self.type}':")

        yield from self.error.output(indent + 1)


@attr.s
class ConditionErrorContainer(ConditionError):
    """Condition error with subconditions."""

    # List of ConditionErrors that this error wraps
    errors: collections.abc.Sequence[ConditionError] = attr.ib()

    def output(self, indent: int) -> collections.abc.Generator[str, None, None]:
        """Yield an indented representation."""
        for item in self.errors:
            yield from item.output(indent)


class IntegrationError(HomeAssistantError):
    """Base class for platform and config entry exceptions."""

    def __str__(self) -> str:
        """Return a human readable error."""
        return super().__str__() or str(self.__cause__)


class PlatformNotReady(IntegrationError):
    """Error to indicate that platform is not ready."""


class ConfigEntryNotReady(IntegrationError):
    """Error to indicate that config entry is not ready."""


class ConfigEntryAuthFailed(IntegrationError):
    """Error to indicate that config entry could not authenticate."""


class InvalidStateError(HomeAssistantError):
    """When an invalid state is encountered."""


class Unauthorized(HomeAssistantError):
    """When an action is unauthorized."""

    def __init__(
        self,
        context: Context | None = None,
        user_id: str | None = None,
        entity_id: str | None = None,
        config_entry_id: str | None = None,
        perm_category: str | None = None,
        permission: str | None = None,
    ) -> None:
        """Unauthorized error."""
        super().__init__(self.__class__.__name__)
        self.context = context

        if user_id is None and context is not None:
            user_id = context.user_id

        self.user_id = user_id
        self.entity_id = entity_id
        self.config_entry_id = config_entry_id
        # Not all actions have an ID (like adding config entry)
        # We then use this fallback to know what category was unauth
        self.perm_category = perm_category
        self.permission = permission


class UnknownUser(Unauthorized):
    """When call is made with user ID that doesn't exist."""


class ServiceNotFound(HomeAssistantError):
    """Raised when a service is not found."""

    def __init__(self, domain: str, service: str) -> None:
        """Initialize error."""
        super().__init__(self, f"Service {domain}.{service} not found")
        self.domain = domain
        self.service = service

    def __str__(self) -> str:
        """Return string representation."""
        return f"Unable to find service {self.domain}.{self.service}"


class MaxLengthExceeded(HomeAssistantError):
    """Raised when a property value has exceeded the max character length."""

    def __init__(self, value: str, property_name: str, max_length: int) -> None:
        """Initialize error."""
        super().__init__(
            self,
            (
                f"Value {value} for property {property_name} has a max length of "
                f"{max_length} characters"
            ),
        )
        self.value = value
        self.property_name = property_name
        self.max_length = max_length


class RequiredParameterMissing(HomeAssistantError):
    """Raised when a required parameter is missing from a function call."""

    def __init__(self, parameter_names: list[str]) -> None:
        """Initialize error."""
        super().__init__(
            self,
            (
                "Call must include at least one of the following parameters: "
                f"{', '.join(parameter_names)}"
            ),
        )
        self.parameter_names = parameter_names


class DependencyError(HomeAssistantError):
    """Raised when dependencies can not be setup."""

    def __init__(self, failed_dependencies: list[str]) -> None:
        """Initialize error."""
        super().__init__(
            self,
            f"Could not setup dependencies: {', '.join(failed_dependencies)}",
        )
        self.failed_dependencies = failed_dependencies

class LoaderError(Exception):
    """Loader base error."""


class IntegrationNotFound(LoaderError):
    """Raised when a component is not found."""

    def __init__(self, domain: str) -> None:
        """Initialize a component not found error."""
        super().__init__(f"Integration '{domain}' not found.")
        self.domain = domain


class CircularDependency(LoaderError):
    """Raised when a circular dependency is found when resolving components."""

    def __init__(self, from_domain: str, to_domain: str) -> None:
        """Initialize circular dependency error."""
        super().__init__(f"Circular dependency detected: {from_domain} -> {to_domain}.")
        self.from_domain = from_domain
        self.to_domain = to_domain


