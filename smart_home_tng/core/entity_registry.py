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

import collections.abc
import logging
import typing

import attr
import voluptuous as vol

from . import helpers
from .callback import callback
from .config_entry import ConfigEntry
from .const import Const
from .device_registry_entry_disabler import DeviceRegistryEntryDisabler
from .entity_category import EntityCategory
from .entity_registry_entry import EntityRegistryEntry
from .entity_registry_entry_disabler import EntityRegistryEntryDisabler
from .entity_registry_entry_hider import EntityRegistryEntryHider
from .entity_registry_items import EntityRegistryItems
from .entity_registry_store import EntityRegistryStore
from .event import Event
from .max_length_exceeded import MaxLengthExceeded
from .smart_home_controller import SmartHomeController
from .yaml_loader import YamlLoader

_STORAGE_VERSION_MAJOR: typing.Final = 1
_STORAGE_VERSION_MINOR: typing.Final = 6
_STORAGE_KEY: typing.Final = "core.entity_registry"
_LOGGER: typing.Final = logging.getLogger(__name__)
_PATH_REGISTRY: typing.Final = "entity_registry.yaml"
_SAVE_DELAY: typing.Final = 10
_UNDEFINED: typing.Final = object()


# pylint: disable=unused-variable
class EntityRegistry:
    """Class to hold a registry of entities."""

    EVENT_REGISTRY_UPDATED: typing.Final = "entity_registry_updated"

    def __init__(self, shc: SmartHomeController) -> None:
        """Initialize the registry."""
        self._entities = None
        self._shc = shc
        self._store = EntityRegistryStore(
            shc,
            _STORAGE_VERSION_MAJOR,
            _STORAGE_KEY,
            atomic_writes=True,
            minor_version=_STORAGE_VERSION_MINOR,
        )
        shc.bus.async_listen(
            Const.EVENT_DEVICE_REGISTRY_UPDATED, self.async_device_modified
        )

    @property
    def entities(self) -> EntityRegistryItems | None:
        return self._entities

    @callback
    def async_get_device_class_lookup(
        self, domain_device_classes: set[tuple[str, str | None]]
    ) -> dict[str, dict[tuple[str, str | None], str]]:
        """Return a lookup of entity ids for devices which have matching entities.

        Entities must match a set of (domain, device_class) tuples.
        The result is indexed by device_id, then by the matching (domain, device_class)
        """
        lookup: dict[str, dict[tuple[str, str | None], str]] = {}
        for entity in self._entities.values():
            if not entity.device_id:
                continue
            device_class = entity.device_class or entity.original_device_class
            domain_device_class = (entity.domain, device_class)
            if domain_device_class not in domain_device_classes:
                continue
            if entity.device_id not in lookup:
                lookup[entity.device_id] = {domain_device_class: entity.entity_id}
            else:
                lookup[entity.device_id][domain_device_class] = entity.entity_id
        return lookup

    @callback
    def async_is_registered(self, entity_id: str) -> bool:
        """Check if an entity_id is currently registered."""
        return entity_id in self._entities

    @callback
    def async_get(self, entity_id: str) -> EntityRegistryEntry | None:
        """Get EntityEntry for an entity_id."""
        return self._entities.get(entity_id)

    @callback
    def async_get_entity_id(
        self, domain: str, platform: str, unique_id: str
    ) -> str | None:
        """Check if an entity_id is currently registered."""
        return self._entities.get_entity_id((domain, platform, unique_id))

    @callback
    def async_generate_entity_id(
        self,
        domain: str,
        suggested_object_id: str,
        known_object_ids: collections.abc.Iterable[str] | None = None,
    ) -> str:
        """Generate an entity ID that does not conflict.

        Conflicts checked against registered and currently existing entities.
        """
        preferred_string = f"{domain}.{helpers.slugify(suggested_object_id)}"

        if len(domain) > Const.MAX_LENGTH_STATE_DOMAIN:
            raise MaxLengthExceeded(domain, "domain", Const.MAX_LENGTH_STATE_DOMAIN)

        test_string = preferred_string[: Const.MAX_LENGTH_STATE_ENTITY_ID]
        if not known_object_ids:
            known_object_ids = {}

        tries = 1
        while (
            test_string in self._entities
            or test_string in known_object_ids
            or not self._shc.states.async_available(test_string)
        ):
            tries += 1
            len_suffix = len(str(tries)) + 1
            test_string = (
                f"{preferred_string[:Const.MAX_LENGTH_STATE_ENTITY_ID-len_suffix]}"
                + f"_{tries}"
            )

        return test_string

    @callback
    def async_get_or_create(
        self,
        domain: str,
        platform: str,
        unique_id: str,
        *,
        # To influence entity ID generation
        known_object_ids: collections.abc.Iterable[str] | None = None,
        suggested_object_id: str | None = None,
        # To disable or hide an entity if it gets created
        disabled_by: EntityRegistryEntryDisabler | None = None,
        hidden_by: EntityRegistryEntryHider | None = None,
        # Data that we want entry to have
        area_id: str | None = None,
        capabilities: collections.abc.Mapping[str, typing.Any] | None = None,
        config_entry: ConfigEntry | None = None,
        device_id: str | None = None,
        entity_category: EntityCategory | None = None,
        original_device_class: str | None = None,
        original_icon: str | None = None,
        original_name: str | None = None,
        supported_features: int | None = None,
        unit_of_measurement: str | None = None,
    ) -> EntityRegistryEntry:
        """Get entity. Create if it doesn't exist."""
        config_entry_id = None
        if config_entry:
            config_entry_id = config_entry.entry_id

        entity_id = self.async_get_entity_id(domain, platform, unique_id)

        if entity_id:
            return self.async_update_entity(
                entity_id,
                area_id=area_id,
                capabilities=capabilities,
                config_entry_id=config_entry_id,
                device_id=device_id,
                entity_category=entity_category,
                original_device_class=original_device_class,
                original_icon=original_icon,
                original_name=original_name,
                supported_features=supported_features,
                unit_of_measurement=unit_of_measurement,
                # When we changed our slugify algorithm, we invalidated some
                # stored entity IDs with either a __ or ending in _.
                # Fix introduced in 0.86 (Jan 23, 2019). Next line can be
                # removed when we release 1.0 or in 2020.
                new_entity_id=".".join(
                    helpers.slugify(part) for part in entity_id.split(".", 1)
                ),
            )

        entity_id = self.async_generate_entity_id(
            domain, suggested_object_id or f"{platform}_{unique_id}", known_object_ids
        )

        if disabled_by and not isinstance(disabled_by, EntityRegistryEntryDisabler):
            raise ValueError("disabled_by must be a RegistryEntryDisabler value")

        if (
            disabled_by is None
            and config_entry
            and config_entry.pref_disable_new_entities
        ):
            disabled_by = EntityRegistryEntryDisabler.INTEGRATION

        if entity_category and not isinstance(entity_category, EntityCategory):
            raise ValueError("entity_category must be a valid EntityCategory instance")

        entry = EntityRegistryEntry(
            area_id=area_id,
            capabilities=capabilities,
            config_entry_id=config_entry_id,
            device_id=device_id,
            disabled_by=disabled_by,
            entity_category=entity_category,
            entity_id=entity_id,
            hidden_by=hidden_by,
            original_device_class=original_device_class,
            original_icon=original_icon,
            original_name=original_name,
            platform=platform,
            supported_features=supported_features or 0,
            unique_id=unique_id,
            unit_of_measurement=unit_of_measurement,
        )
        self._entities[entity_id] = entry
        _LOGGER.info(f"Registered new {domain}.{platform} entity: {entity_id}")
        self.async_schedule_save()

        self._shc.bus.async_fire(
            self.EVENT_REGISTRY_UPDATED,
            {"action": "create", "entity_id": entity_id},
        )

        return entry

    @callback
    def async_remove(self, entity_id: str) -> None:
        """Remove an entity from registry."""
        self._entities.pop(entity_id)
        self._shc.bus.async_fire(
            self.EVENT_REGISTRY_UPDATED,
            {"action": "remove", "entity_id": entity_id},
        )
        self.async_schedule_save()

    @callback
    def async_device_modified(self, event: Event) -> None:
        """Handle the removal or update of a device.

        Remove entities from the registry that are associated to a device when
        the device is removed.

        Disable entities in the registry that are associated to a device when
        the device is disabled.
        """
        if event.data["action"] == "remove":
            entities = self.async_entries_for_device(
                event.data["device_id"], include_disabled_entities=True
            )
            for entity in entities:
                self.async_remove(entity.entity_id)
            return

        if event.data["action"] != "update":
            # Ignore "create" action
            return

        device_registry = self._shc.device_registry
        device = device_registry.async_get(event.data["device_id"])

        # The device may be deleted already if the event handling is late, do nothing
        # in that case. Entities will be removed when we get the "remove" event.
        if not device:
            return

        # Remove entities which belong to config entries no longer associated with the
        # device
        entities = self.async_entries_for_device(
            event.data["device_id"], include_disabled_entities=True
        )
        for entity in entities:
            if (
                entity.config_entry_id is not None
                and entity.config_entry_id not in device.config_entries
            ):
                self.async_remove(entity.entity_id)

        # Re-enable disabled entities if the device is no longer disabled
        if not device.disabled:
            entities = self.async_entries_for_device(
                event.data["device_id"], include_disabled_entities=True
            )
            for entity in entities:
                if entity.disabled_by is not EntityRegistryEntryDisabler.DEVICE:
                    continue
                self.async_update_entity(entity.entity_id, disabled_by=None)
            return

        # Ignore device disabled by config entry, this is handled by
        # async_config_entry_disabled
        if device.disabled_by is DeviceRegistryEntryDisabler.CONFIG_ENTRY:
            return

        # Fetch entities which are not already disabled and disable them
        entities = self.async_entries_for_device(event.data["device_id"])
        for entity in entities:
            self.async_update_entity(
                entity.entity_id, disabled_by=EntityRegistryEntryDisabler.DEVICE
            )

    @callback
    def _async_update_entity(
        self,
        entity_id: str,
        *,
        area_id: str | None | object = _UNDEFINED,
        capabilities: collections.abc.Mapping[str, typing.Any]
        | None
        | object = _UNDEFINED,
        config_entry_id: str | None | object = _UNDEFINED,
        device_class: str | None | object = _UNDEFINED,
        device_id: str | None | object = _UNDEFINED,
        disabled_by: EntityRegistryEntryDisabler | None | object = _UNDEFINED,
        entity_category: EntityCategory | None | object = _UNDEFINED,
        hidden_by: EntityRegistryEntryHider | None | object = _UNDEFINED,
        icon: str | None | object = _UNDEFINED,
        name: str | None | object = _UNDEFINED,
        new_entity_id: str | object = _UNDEFINED,
        new_unique_id: str | object = _UNDEFINED,
        original_device_class: str | None | object = _UNDEFINED,
        original_icon: str | None | object = _UNDEFINED,
        original_name: str | None | object = _UNDEFINED,
        supported_features: int | object = _UNDEFINED,
        unit_of_measurement: str | None | object = _UNDEFINED,
        platform: str | None | object = _UNDEFINED,
        options: collections.abc.Mapping[str, collections.abc.Mapping[str, typing.Any]]
        | object = _UNDEFINED,
    ) -> EntityRegistryEntry:
        """Private facing update properties method."""
        old = self._entities[entity_id]

        # Dict with new key/value pairs
        new_values: dict[str, typing.Any] = {}
        # Dict with old key/value pairs
        old_values: dict[str, typing.Any] = {}

        if disabled_by and not isinstance(disabled_by, EntityRegistryEntryDisabler):
            raise ValueError("disabled_by must be a RegistryEntryDisabler value")

        if entity_category and not isinstance(entity_category, EntityCategory):
            raise ValueError("entity_category must be a valid EntityCategory instance")

        for attr_name, value in (
            ("area_id", area_id),
            ("capabilities", capabilities),
            ("config_entry_id", config_entry_id),
            ("device_class", device_class),
            ("device_id", device_id),
            ("disabled_by", disabled_by),
            ("entity_category", entity_category),
            ("hidden_by", hidden_by),
            ("icon", icon),
            ("name", name),
            ("original_device_class", original_device_class),
            ("original_icon", original_icon),
            ("original_name", original_name),
            ("supported_features", supported_features),
            ("unit_of_measurement", unit_of_measurement),
            ("platform", platform),
            ("options", options),
        ):
            if value is not _UNDEFINED and value != getattr(old, attr_name):
                new_values[attr_name] = value
                old_values[attr_name] = getattr(old, attr_name)

        if new_entity_id is not _UNDEFINED and new_entity_id != old.entity_id:
            if self.async_is_registered(new_entity_id):
                raise ValueError("Entity with this ID is already registered")

            if not helpers.valid_entity_id(new_entity_id):
                raise ValueError("Invalid entity ID")

            if (
                helpers.split_entity_id(new_entity_id)[0]
                != helpers.split_entity_id(entity_id)[0]
            ):
                raise ValueError("New entity ID should be same domain")

            self._entities.pop(entity_id)
            entity_id = new_values["entity_id"] = new_entity_id
            old_values["entity_id"] = old.entity_id

        if new_unique_id is not _UNDEFINED:
            conflict_entity_id = self.async_get_entity_id(
                old.domain, old.platform, new_unique_id
            )
            if conflict_entity_id:
                raise ValueError(
                    f"Unique id '{new_unique_id}' is already in use by "
                    f"'{conflict_entity_id}'"
                )
            new_values["unique_id"] = new_unique_id
            old_values["unique_id"] = old.unique_id

        if not new_values:
            return old

        new = self._entities[entity_id] = attr.evolve(old, **new_values)

        self.async_schedule_save()

        data: dict[str, str | dict[str, typing.Any]] = {
            "action": "update",
            "entity_id": entity_id,
            "changes": old_values,
        }

        if old.entity_id != entity_id:
            data["old_entity_id"] = old.entity_id

        self._shc.bus.async_fire(self.EVENT_REGISTRY_UPDATED, data)

        return new

    @callback
    def async_update_entity(
        self,
        entity_id: str,
        *,
        area_id: str | None | object = _UNDEFINED,
        capabilities: collections.abc.Mapping[str, typing.Any]
        | None
        | object = _UNDEFINED,
        config_entry_id: str | None | object = _UNDEFINED,
        device_class: str | None | object = _UNDEFINED,
        device_id: str | None | object = _UNDEFINED,
        disabled_by: EntityRegistryEntryDisabler | None | object = _UNDEFINED,
        entity_category: EntityCategory | None | object = _UNDEFINED,
        hidden_by: EntityRegistryEntryHider | None | object = _UNDEFINED,
        icon: str | None | object = _UNDEFINED,
        name: str | None | object = _UNDEFINED,
        new_entity_id: str | object = _UNDEFINED,
        new_unique_id: str | object = _UNDEFINED,
        original_device_class: str | None | object = _UNDEFINED,
        original_icon: str | None | object = _UNDEFINED,
        original_name: str | None | object = _UNDEFINED,
        supported_features: int | object = _UNDEFINED,
        unit_of_measurement: str | None | object = _UNDEFINED,
    ) -> EntityRegistryEntry:
        """Update properties of an entity."""
        return self._async_update_entity(
            entity_id,
            area_id=area_id,
            capabilities=capabilities,
            config_entry_id=config_entry_id,
            device_class=device_class,
            device_id=device_id,
            disabled_by=disabled_by,
            entity_category=entity_category,
            hidden_by=hidden_by,
            icon=icon,
            name=name,
            new_entity_id=new_entity_id,
            new_unique_id=new_unique_id,
            original_device_class=original_device_class,
            original_icon=original_icon,
            original_name=original_name,
            supported_features=supported_features,
            unit_of_measurement=unit_of_measurement,
        )

    @callback
    def async_update_entity_platform(
        self,
        entity_id: str,
        new_platform: str,
        *,
        new_config_entry_id: str | object = _UNDEFINED,
        new_unique_id: str | object = _UNDEFINED,
        new_device_id: str | None | object = _UNDEFINED,
    ) -> EntityRegistryEntry:
        """
        Update entity platform.

        This should only be used when an entity needs to be migrated between
        integrations.
        """
        if (
            state := self._shc.states.get(entity_id)
        ) is not None and state.state != Const.STATE_UNKNOWN:
            raise ValueError("Only entities that haven't been loaded can be migrated")

        old = self._entities[entity_id]
        if new_config_entry_id == _UNDEFINED and old.config_entry_id is not None:
            raise ValueError(
                f"new_config_entry_id required because {entity_id} is already linked "
                "to a config entry"
            )

        return self._async_update_entity(
            entity_id,
            new_unique_id=new_unique_id,
            config_entry_id=new_config_entry_id,
            device_id=new_device_id,
            platform=new_platform,
        )

    @callback
    def async_update_entity_options(
        self, entity_id: str, domain: str, options: dict[str, typing.Any]
    ) -> EntityRegistryEntry:
        """Update entity options."""
        old = self._entities[entity_id]
        new_options: collections.abc.Mapping[
            str, collections.abc.Mapping[str, typing.Any]
        ] = {**old.options, domain: options}
        return self._async_update_entity(entity_id, options=new_options)

    async def async_load(self) -> None:
        """Load the entity registry."""
        self.async_setup_entity_restore()

        data = await self._shc.async_migrator(
            self._shc.config.path(_PATH_REGISTRY),
            self._store,
            old_conf_load_func=YamlLoader.load_yaml,
            old_conf_migrate_func=self._async_migrate_yaml_to_json,
        )
        entities = EntityRegistryItems()

        if data is not None:
            for entity in data["entities"]:
                # Some old installations can have some bad entities.
                # Filter them out as they cause errors down the line.
                # Can be removed in Jan 2021
                if not helpers.valid_entity_id(entity["entity_id"]):
                    continue

                # We removed this in 2022.5. Remove this check in 2023.1.
                if entity["entity_category"] == "system":
                    entity["entity_category"] = None

                entities[entity["entity_id"]] = EntityRegistryEntry(
                    area_id=entity["area_id"],
                    capabilities=entity["capabilities"],
                    config_entry_id=entity["config_entry_id"],
                    device_class=entity["device_class"],
                    device_id=entity["device_id"],
                    disabled_by=EntityRegistryEntryDisabler(entity["disabled_by"])
                    if entity["disabled_by"]
                    else None,
                    entity_category=EntityCategory(entity["entity_category"])
                    if entity["entity_category"]
                    else None,
                    entity_id=entity["entity_id"],
                    hidden_by=entity["hidden_by"],
                    icon=entity["icon"],
                    id=entity["id"],
                    name=entity["name"],
                    options=entity["options"],
                    original_device_class=entity["original_device_class"],
                    original_icon=entity["original_icon"],
                    original_name=entity["original_name"],
                    platform=entity["platform"],
                    supported_features=entity["supported_features"],
                    unique_id=entity["unique_id"],
                    unit_of_measurement=entity["unit_of_measurement"],
                )

        self._entities = entities

    @callback
    def async_schedule_save(self) -> None:
        """Schedule saving the entity registry."""
        self._store.async_delay_save(self._data_to_save, _SAVE_DELAY)

    @callback
    def _data_to_save(self) -> dict[str, typing.Any]:
        """Return data of entity registry to store in a file."""
        data: dict[str, typing.Any] = {}

        data["entities"] = [
            {
                "area_id": entry.area_id,
                "capabilities": entry.capabilities,
                "config_entry_id": entry.config_entry_id,
                "device_class": entry.device_class,
                "device_id": entry.device_id,
                "disabled_by": entry.disabled_by,
                "entity_category": entry.entity_category,
                "entity_id": entry.entity_id,
                "hidden_by": entry.hidden_by,
                "icon": entry.icon,
                "id": entry.id,
                "name": entry.name,
                "options": entry.options,
                "original_device_class": entry.original_device_class,
                "original_icon": entry.original_icon,
                "original_name": entry.original_name,
                "platform": entry.platform,
                "supported_features": entry.supported_features,
                "unique_id": entry.unique_id,
                "unit_of_measurement": entry.unit_of_measurement,
            }
            for entry in self._entities.values()
        ]

        return data

    @callback
    def async_clear_config_entry(self, config_entry: str) -> None:
        """Clear config entry from registry entries."""
        for entity_id in [
            entity_id
            for entity_id, entry in self._entities.items()
            if config_entry == entry.config_entry_id
        ]:
            self.async_remove(entity_id)

    @callback
    def async_clear_area_id(self, area_id: str) -> None:
        """Clear area id from registry entries."""
        for entity_id, entry in self._entities.items():
            if area_id == entry.area_id:
                self.async_update_entity(entity_id, area_id=None)

    @callback
    def async_entries_for_device(
        self, device_id: str, include_disabled_entities: bool = False
    ) -> list[EntityRegistryEntry]:
        """Return entries that match a device."""
        return [
            entry
            for entry in self._entities.values()
            if entry.device_id == device_id
            and (not entry.disabled_by or include_disabled_entities)
        ]

    @callback
    def async_setup_entity_restore(self) -> None:
        """Set up the entity restore mechanism."""

        @callback
        def cleanup_restored_states_filter(event: Event) -> bool:
            """Clean up restored states filter."""
            return bool(event.data["action"] == "remove")

        @callback
        def cleanup_restored_states(event: Event) -> None:
            """Clean up restored states."""
            state = self._shc.states.get(event.data["entity_id"])

            if state is None or not state.attributes.get(Const.ATTR_RESTORED):
                return

            self._shc.states.async_remove(
                event.data["entity_id"], context=event.context
            )

        self._shc.bus.async_listen(
            self.EVENT_REGISTRY_UPDATED,
            cleanup_restored_states,
            event_filter=cleanup_restored_states_filter,
        )

        if self._shc.is_running:
            return

        @callback
        def _write_unavailable_states(_: Event) -> None:
            """Make sure state machine contains entry for each registered entity."""
            existing = set(self._shc.states.async_entity_ids())

            for entry in self._entities.values():
                if entry.entity_id in existing or entry.disabled:
                    continue

                entry.write_unavailable_state(self._shc)

        self._shc.bus.async_listen(
            Const.EVENT_HOMEASSISTANT_START, _write_unavailable_states
        )

    @staticmethod
    async def _async_migrate_yaml_to_json(
        entities: dict[str, typing.Any]
    ) -> dict[str, list[dict[str, typing.Any]]]:
        """Migrate the YAML config file to storage helper format."""
        entities_1_1 = {
            "entities": [
                {"entity_id": entity_id, **info} for entity_id, info in entities.items()
            ]
        }
        return await EntityRegistryStore.async_migrate(1, 1, entities_1_1)

    @callback
    def async_entries_for_area(self, area_id: str) -> list[EntityRegistryEntry]:
        """Return entries that match an area."""
        return [entry for entry in self._entities.values() if entry.area_id == area_id]

    @callback
    def async_entries_for_config_entry(
        self, config_entry_id: str
    ) -> list[EntityRegistryEntry]:
        """Return entries that match a config entry."""
        return [
            entry
            for entry in self._entities.values()
            if entry.config_entry_id == config_entry_id
        ]

    @callback
    def async_config_entry_disabled_by_changed(self, config_entry: ConfigEntry) -> None:
        """Handle a config entry being disabled or enabled.

        Disable entities in the registry that are associated with a config entry when
        the config entry is disabled, enable entities in the registry that are associated
        with a config entry when the config entry is enabled and the entities are marked
        DISABLED_CONFIG_ENTRY.
        """

        entities = self.async_entries_for_config_entry(config_entry.entry_id)

        if not config_entry.disabled_by:
            for entity in entities:
                if entity.disabled_by is not EntityRegistryEntryDisabler.CONFIG_ENTRY:
                    continue
                self.async_update_entity(entity.entity_id, disabled_by=None)
            return

        for entity in entities:
            if entity.disabled:
                # Entity already disabled, do not overwrite
                continue
            self.async_update_entity(
                entity.entity_id, disabled_by=EntityRegistryEntryDisabler.CONFIG_ENTRY
            )

    @callback
    def async_validate_entity_id(self, entity_id_or_uuid: str) -> str:
        """Validate and resolve an entity id or UUID to an entity id.

        Raises vol.Invalid if the entity or UUID is invalid, or if the UUID is not
        associated with an entity registry item.
        """
        if helpers.valid_entity_id(entity_id_or_uuid):
            return entity_id_or_uuid
        if (entry := self._entities.get_entry(entity_id_or_uuid)) is None:
            raise vol.Invalid(f"Unknown entity registry entry {entity_id_or_uuid}")
        return entry.entity_id

    @callback
    def async_resolve_entity_id(self, entity_id_or_uuid: str) -> str | None:
        """Validate and resolve an entity id or UUID to an entity id.

        Returns None if the entity or UUID is invalid, or if the UUID is not
        associated with an entity registry item.
        """
        if helpers.valid_entity_id(entity_id_or_uuid):
            return entity_id_or_uuid
        if (entry := self._entities.get_entry(entity_id_or_uuid)) is None:
            return None
        return entry.entity_id

    @callback
    def async_validate_entity_ids(self, entity_ids_or_uuids: list[str]) -> list[str]:
        """Validate and resolve a list of entity ids or UUIDs to a list of entity ids.

        Returns a list with UUID resolved to entity_ids.
        Raises vol.Invalid if any item is invalid, or if any a UUID is not associated with
        an entity registry item.
        """

        return [self.async_validate_entity_id(item) for item in entity_ids_or_uuids]

    async def async_migrate_entries(
        self,
        config_entry_id: str,
        entry_callback: typing.Callable[
            [EntityRegistryEntry], dict[str, typing.Any] | None
        ],
    ) -> None:
        """Migrator of unique IDs."""
        for entry in self._entities.values():
            if entry.config_entry_id != config_entry_id:
                continue

            updates = entry_callback(entry)

            if updates is not None:
                self.async_update_entity(entry.entity_id, **updates)
