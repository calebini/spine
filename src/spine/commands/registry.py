"""Compiled command-to-runtime-contract authority."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from spine import IMPLEMENTED_CONTRACT_VERSIONS

COMMAND_RUNTIME_CONTRACT_REGISTRY_ID = "spine.command-runtime-contract-registry.v1"
CANONICAL_JSON_CONTRACT = "spine.canonical-json.v1"


@dataclass(frozen=True)
class CommandContractEntry:
    command: str
    access_mode: Literal["read", "write"]
    required_contract_versions: tuple[str, ...]


_READ_COMMANDS = frozenset(
    {
        "agenda.show",
        "item.list",
        "item.occurrences",
        "item.show",
        "item_archetype.list",
        "item_archetype.show",
        "notification.opportunities",
        "notification_profile.binding.list",
        "notification_profile.list",
        "notification_profile.resolve",
        "notification_profile.show",
        "owner_scope.list",
        "relation.list",
        "schedule.binding.list",
        "schedule.build",
        "schedule.show",
        "system.info",
    }
)

_BASE_COMMANDS = {
    "subject.upsert",
    "subject_group.upsert",
    "delivery_target.upsert",
    "item.show",
    "item.list",
    "item.archive",
    "event.create",
    "event.update",
    "event.reschedule",
    "event.cancel",
    "task.create",
    "task.update",
    "task.complete",
    "task.cancel",
    "relation.create",
    "relation.list",
}

_ADDITIONAL_REQUIREMENTS: dict[str, tuple[str, ...]] = {command: () for command in _BASE_COMMANDS}


def _requirements(commands: set[str], *versions: str) -> None:
    for command in commands:
        _ADDITIONAL_REQUIREMENTS[command] = versions


_requirements({"system.info"}, "spine.system-info.v2", "spine.tickerd-compatibility.v1")
_requirements(
    {"owner_scope.list"},
    "spine.owner-scope-discovery.v2",
    "spine.owner-scope-list-response.v2",
    "spine.owner-scope-list-cursor.v2",
)
_requirements({"item.occurrences"}, "spine.recurrence.contract.v1", "spine.item-occurrences.recurrence.v1")
_requirements(
    {"recurrence.instance.add", "recurrence.instance.remove", "recurrence.instance.override", "recurrence.series.edit"},
    "spine.recurrence-authoring.v1",
    "spine.recurrence.contract.v1",
    "spine.recurrence.normalization.v1",
)
_requirements(
    {"occurrence_provenance.regenerate"},
    "spine.recurrence.contract.v1",
    "spine.recurrence.normalization.v1",
)
_requirements(
    {"reminder.create", "reminder.edit", "reminder.disable"},
    "spine.notification-schedule-authoring.v1",
    "spine.notification-schedule.contract.v1",
    "spine.notification-schedule.normalization.v1",
)
_requirements(
    {"notification.opportunities", "notification_work.materialize"},
    "spine.notification-schedule-authoring.v1",
    "spine.notification-schedule.contract.v1",
    "spine.notification-schedule.normalization.v1",
    "spine.notification-opportunities.v1",
)
_requirements(
    {"schedule.build"},
    "spine.schedule-create.v2",
    "spine.schedule-create-normalization.v1",
    "spine.schedule-countdown-builder.v1",
    "spine.schedule-countdown-builder-response.v1",
    "spine.notification-schedule.contract.v1",
)
_requirements(
    {"schedule.create"},
    "spine.schedule-create.v2",
    "spine.schedule-create-normalization.v1",
    "spine.schedule-create-response.v2",
    "spine.schedule-create-receipt.v2",
    "spine.recurrence-authoring.v1",
    "spine.recurrence.contract.v1",
    "spine.recurrence.normalization.v1",
    "spine.notification-schedule-authoring.v1",
    "spine.notification-schedule.contract.v1",
    "spine.notification-schedule.normalization.v1",
    "spine.notification-opportunities.v1",
    "spine.schedule-primary-location.v1",
    "spine.schedule-primary-location-authoring.v1",
    "spine.schedule-primary-location-view.v1",
    "spine.schedule-primary-location-normalization.v1",
    "spine.item-archetypes.v1",
    "spine.notification-profiles.v1",
    "spine.notification-profile-bindings.v1",
    "spine.notification-profile-application.v1",
)
_requirements(
    {"schedule.show"},
    "spine.schedule-show.v1",
    "spine.schedule-compact.v1",
    "spine.schedule-primary-location.v1",
    "spine.schedule-primary-location-view.v1",
    "spine.relative-temporal-binding.v1",
    "spine.notification-rendering.v1",
    "spine.notification-rendering.concise-en-ca.v1",
    "spine.notification-rendering-input.v1",
)
_requirements(
    {"agenda.show"},
    "spine.schedule-operations-normalization.v1",
    "spine.schedule-agenda.v1",
    "spine.schedule-agenda-response.v1",
    "spine.schedule-primary-location.v1",
    "spine.schedule-primary-location-view.v1",
    "spine.relative-temporal-binding.v1",
)
_requirements(
    {"schedule.update"},
    "spine.schedule-operations-normalization.v1",
    "spine.schedule-update.v2",
    "spine.schedule-update-response.v2",
    "spine.schedule-update-receipt.v2",
    "spine.recurrence-authoring.v1",
    "spine.recurrence.contract.v1",
    "spine.recurrence.normalization.v1",
    "spine.notification-schedule-authoring.v1",
    "spine.notification-schedule.contract.v1",
    "spine.notification-schedule.normalization.v1",
    "spine.notification-opportunities.v1",
    "spine.schedule-primary-location.v1",
    "spine.schedule-primary-location-authoring.v1",
    "spine.schedule-primary-location-view.v1",
    "spine.schedule-primary-location-normalization.v1",
    "spine.relative-temporal-binding.v1",
    "spine.item-archetypes.v1",
    "spine.notification-profiles.v1",
    "spine.notification-profile-bindings.v1",
    "spine.notification-profile-application.v1",
)
_requirements(
    {"schedule.cancel"},
    "spine.schedule-operations-normalization.v1",
    "spine.schedule-cancel.v1",
    "spine.schedule-cancel-response.v1",
    "spine.schedule-cancel-receipt.v1",
    "spine.notification-schedule.contract.v1",
    "spine.relative-temporal-binding.v1",
)
_requirements(
    {"schedule.related_task.create"},
    "spine.relative-temporal-binding.v1",
    "spine.relative-temporal-binding-normalization.v1",
    "spine.normalized-temporal-binding-revision-hash.v1",
    "spine.temporal-binding-catalog.v1",
    "spine.schedule-related-task-create.v1",
    "spine.schedule-related-task-create-response.v1",
    "spine.schedule-related-task-create-receipt.v1",
    "spine.notification-schedule-authoring.v1",
    "spine.notification-schedule.contract.v1",
    "spine.notification-schedule.normalization.v1",
    "spine.notification-opportunities.v1",
)
_requirements(
    {"schedule.binding.list"},
    "spine.relative-temporal-binding.v1",
    "spine.temporal-binding-catalog.v1",
    "spine.schedule-binding-list.v1",
    "spine.schedule-binding-list-response.v1",
    "spine.schedule-binding-list-cursor.v1",
)
_requirements(
    {"schedule.binding.reconcile"},
    "spine.relative-temporal-binding.v1",
    "spine.relative-temporal-binding-normalization.v1",
    "spine.normalized-temporal-binding-revision-hash.v1",
    "spine.temporal-binding-catalog.v1",
    "spine.schedule-binding-reconcile.v1",
    "spine.schedule-binding-reconcile-response.v1",
    "spine.schedule-binding-reconcile-receipt.v1",
)
_requirements(
    {
        "item_archetype.create",
        "item_archetype.revise",
        "item_archetype.retire",
        "item_archetype.show",
        "item_archetype.list",
    },
    "spine.item-archetypes.v1",
    "spine.notification-profile-readback.v1",
    "spine.notification-profile-catalog-cursor.v1",
)
_requirements(
    {
        "notification_profile.create",
        "notification_profile.revise",
        "notification_profile.retire",
        "notification_profile.show",
        "notification_profile.list",
    },
    "spine.notification-profiles.v1",
    "spine.notification-profile-readback.v1",
    "spine.notification-profile-catalog-cursor.v1",
)
_requirements(
    {
        "notification_profile.binding.set",
        "notification_profile.binding.remove",
        "notification_profile.binding.list",
        "notification_profile.resolve",
    },
    "spine.item-archetypes.v1",
    "spine.notification-profiles.v1",
    "spine.notification-profile-bindings.v1",
    "spine.notification-profile-readback.v1",
    "spine.notification-profile-catalog-cursor.v1",
)


def _entry(command: str, additional: tuple[str, ...]) -> CommandContractEntry:
    return CommandContractEntry(
        command=command,
        access_mode="read" if command in _READ_COMMANDS else "write",
        required_contract_versions=tuple(sorted({CANONICAL_JSON_CONTRACT, *additional})),
    )


COMMAND_RUNTIME_CONTRACT_REGISTRY: Mapping[str, CommandContractEntry] = MappingProxyType(
    {command: _entry(command, additional) for command, additional in sorted(_ADDITIONAL_REQUIREMENTS.items())}
)
MVP_COMMANDS = frozenset(COMMAND_RUNTIME_CONTRACT_REGISTRY)
WRITE_COMMANDS = frozenset(command for command, entry in COMMAND_RUNTIME_CONTRACT_REGISTRY.items() if entry.access_mode == "write")

WORKER_COMMANDS = (
    "notification_work.materialize",
    "occurrence_provenance.regenerate",
    "schedule.binding.reconcile",
)
WORKER_REQUIRED_CONTRACT_VERSIONS = tuple(
    sorted(
        {
            version
            for command in WORKER_COMMANDS
            for version in COMMAND_RUNTIME_CONTRACT_REGISTRY[command].required_contract_versions
        }
        | {
            "spine.notification-rendering.v1",
            "spine.notification-rendering.concise-en-ca.v1",
            "spine.notification-rendering-input.v1",
            "spine.tickerd-compatibility.v1",
        }
    )
)


def missing_runtime_contract_versions(
    command: str,
    implemented_versions: frozenset[str] | None = None,
) -> tuple[str, ...]:
    versions = IMPLEMENTED_CONTRACT_VERSIONS if implemented_versions is None else implemented_versions
    return tuple(
        version
        for version in COMMAND_RUNTIME_CONTRACT_REGISTRY[command].required_contract_versions
        if version not in versions
    )


def missing_worker_runtime_contract_versions(
    implemented_versions: frozenset[str] | None = None,
) -> tuple[str, ...]:
    versions = IMPLEMENTED_CONTRACT_VERSIONS if implemented_versions is None else implemented_versions
    return tuple(version for version in WORKER_REQUIRED_CONTRACT_VERSIONS if version not in versions)
