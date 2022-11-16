"""
Code Generator for Smart Home - The Next Generation.

Generates helper code from component manifests.

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

import json
import typing

from .code_generator import CodeGenerator
from .config import Config
from .integration import Integration

_NAME: typing.Final = "application_credentials"

_BASE: typing.Final = """
\"\"\"Automatically generated by shc_from_manifests.

To update, run python3 -m script.sch_from_manifests.
\"\"\"

import typing

# fmt: off

# pylint: disable=unused-variable
APPLICATION_CREDENTIALS: typing.Final = {}
""".strip()


# pylint: disable=unused-variable
class ApplicationCredentialsGenerator(CodeGenerator):
    """Generate application_credentials data."""

    def __init__(self):
        super().__init__(_NAME)

    def generate_and_validate(
        self, integrations: dict[str, Integration], config: Config
    ) -> str:
        """Validate and generate application_credentials data."""

        match_list = []

        for domain in sorted(integrations):
            integration = integrations[domain]
            application_credentials_file = (
                integration.path / "application_credentials.py"
            )
            if not application_credentials_file.is_file():
                continue

            match_list.append(domain)

        return _BASE.format(json.dumps(match_list, indent=4))

    def validate(self, integrations: dict[str, Integration], config: Config) -> None:
        """Validate application_credentials data."""
        application_credentials_path = (
            config.root / "smart_home_tng/core/generated/application_credentials.py"
        )
        config.cache["application_credentials"] = content = self.generate_and_validate(
            integrations, config
        )

        if config.specific_integrations:
            return

        if not application_credentials_path.is_file() or (
            application_credentials_path.read_text(encoding="utf-8").strip() != content
        ):
            config.add_error(
                "application_credentials",
                "File application_credentials.py is not up to date. "
                + "Run python3 -m script.shc_from_manifests.",
                fixable=True,
            )

    def generate(self, integrations: dict[str, Integration], config: Config):
        """Generate application_credentials data."""
        application_credentials_path = (
            config.root / "smart_home_tng/core/generated/application_credentials.py"
        )
        application_credentials_path.write_text(
            f"{config.cache['application_credentials']}\n", encoding="utf-8"
        )