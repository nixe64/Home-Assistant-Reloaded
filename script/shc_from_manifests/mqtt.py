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

import collections
import json
import typing

from .code_generator import CodeGenerator
from .config import Config
from .integration import Integration

_NAME: typing.Final = "mqtt"
_BASE: typing.Final = """
\"\"\"Automatically generated by shc_from_manifests.

To update, run python3 -m script.shc_from_manifests.
\"\"\"

import typing

# fmt: off

# pylint: disable=unused-variable
MQTT: typing.Final = {}
""".strip()


# pylint: disable=unused-variable
class MqttGenerator(CodeGenerator):
    """Generate MQTT file."""

    def __init__(self):
        super().__init__(_NAME)

    def generate_and_validate(self, integrations: dict[str, Integration], config: Config):
        """Validate and generate MQTT data."""

        data = collections.defaultdict(list)

        for domain in sorted(integrations):
            integration = integrations[domain]

            if not integration.manifest or not integration.config_flow:
                continue

            mqtt = integration.manifest.get("mqtt")

            if not mqtt:
                continue

            for topic in mqtt:
                data[domain].append(topic)

        return _BASE.format(json.dumps(data, indent=4))

    def validate(self, integrations: dict[str, Integration], config: Config):
        """Validate MQTT file."""
        mqtt_path = config.root / "smart_home_tng/core/generated/mqtt.py"
        config.cache["mqtt"] = content = self.generate_and_validate(integrations, config)

        if config.specific_integrations:
            return

        if not mqtt_path.is_file():
            config.add_error(
                "mqtt",
                "File mqtt.py is not up to date. Run python3 -m script.shc_from_manifests.",
                fixable=True,
            )
            return

        with open(str(mqtt_path), encoding="utf-8") as fp:
            if fp.read().strip() != content:
                config.add_error(
                    "mqtt",
                    "File mqtt.py is not up to date. Run python3 -m script.shc_from_manifests.",
                    fixable=True,
                )
            return

    def generate(self, integrations: dict[str, Integration], config: Config):
        """Generate MQTT file."""
        mqtt_path = config.root / "smart_home_tng/core/generated/mqtt.py"
        with open(str(mqtt_path), "w", encoding="utf-8") as fp:
            fp.write(f"{config.cache['mqtt']}\n")