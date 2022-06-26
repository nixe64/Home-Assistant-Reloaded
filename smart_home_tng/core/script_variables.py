"""Script variables."""
import collections.abc
import typing

from .callback import callback
from .smart_home_controller import SmartHomeController
from .template import Template


# pylint: disable=unused-variable
class ScriptVariables:
    """Class to hold and render script variables."""

    def __init__(self, variables: dict[str, typing.Any]) -> None:
        """Initialize script variables."""
        self._variables = variables
        self._has_template: bool | None = None

    @callback
    def async_render(
        self,
        shc: SmartHomeController,
        run_variables: collections.abc.Mapping[str, typing.Any] | None,
        *,
        render_as_defaults: bool = True,
        limited: bool = False,
    ) -> dict[str, typing.Any]:
        """Render script variables.

        The run variables are used to compute the static variables.

        If `render_as_defaults` is True, the run variables will not be overridden.

        """
        if self._has_template is None:
            self._has_template = Template.is_complex(self._variables)
            Template.attach(shc, self._variables)

        if not self._has_template:
            if render_as_defaults:
                rendered_variables = dict(self._variables)

                if run_variables is not None:
                    rendered_variables.update(run_variables)
            else:
                rendered_variables = (
                    {} if run_variables is None else dict(run_variables)
                )
                rendered_variables.update(self._variables)

            return rendered_variables

        rendered_variables = {} if run_variables is None else dict(run_variables)

        for key, value in self._variables.items():
            # We can skip if we're going to override this key with
            # run variables anyway
            if render_as_defaults and key in rendered_variables:
                continue

            rendered_variables[key] = Template.render_complex(
                value, rendered_variables, limited
            )

        return rendered_variables

    def as_dict(self) -> dict[str, typing.Any]:
        """Return dict version of this class."""
        return self._variables
