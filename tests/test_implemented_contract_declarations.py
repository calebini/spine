import json
import unittest
from pathlib import Path

from spine import IMPLEMENTED_CONTRACT_VERSIONS, IMPLEMENTED_LEDGER_SCHEMA_VERSION
from spine.commands.registry import COMMAND_RUNTIME_CONTRACT_REGISTRY
from spine.core.notifications import (
    NOTIFICATION_AUTHORING_VERSION,
    NOTIFICATION_CONTRACT_VERSION,
    NOTIFICATION_NORMALIZATION_VERSION,
)
from spine.core.recurrence_set import AUTHORING_VERSION as RECURRENCE_AUTHORING_VERSION
from spine.core.schedule import (
    CANONICAL_JSON_VERSION,
    RECURRENCE_CONTRACT_VERSION,
    RECURRENCE_NORMALIZATION_VERSION,
)
from spine.ledger.migrate import CURRENT_SCHEMA_VERSION


class ImplementedContractDeclarationTests(unittest.TestCase):
    def test_draft_facet_contracts_are_not_advertised(self) -> None:
        # Repository-wide integration assertion, separate from the bounded facet
        # fixture bundle. Its evidence includes the runtime and web registries.
        root = Path(__file__).parents[1]
        facet_registry = json.loads((root / "contracts/archetype-facet-contract-registry.v1.json").read_text())
        web_registry = json.loads((root / "contracts/spine.trusted-web-command-registry.v1.json").read_text())
        commands = set(facet_registry["commands"])
        self.assertTrue(commands.isdisjoint(COMMAND_RUNTIME_CONTRACT_REGISTRY))
        self.assertTrue(commands.isdisjoint(row["command"] for row in web_registry["commands"]))
        for entry in facet_registry["commands"].values():
            self.assertNotIn(entry["contract_version"], IMPLEMENTED_CONTRACT_VERSIONS)

    def test_runtime_versions_are_declared_once_at_package_boundary(self) -> None:
        self.assertEqual(IMPLEMENTED_LEDGER_SCHEMA_VERSION, CURRENT_SCHEMA_VERSION)
        self.assertTrue(
            {
                CANONICAL_JSON_VERSION,
                RECURRENCE_CONTRACT_VERSION,
                RECURRENCE_NORMALIZATION_VERSION,
                RECURRENCE_AUTHORING_VERSION,
                NOTIFICATION_AUTHORING_VERSION,
                NOTIFICATION_CONTRACT_VERSION,
                NOTIFICATION_NORMALIZATION_VERSION,
                "spine.schedule-create.v2",
                "spine.schedule-create-normalization.v1",
                "spine.schedule-create-response.v2",
                "spine.schedule-create-receipt.v2",
                "spine.schedule-compact.v1",
                "spine.schedule-countdown-builder.v1",
                "spine.schedule-countdown-builder-response.v1",
                "spine.schedule-show.v1",
                "spine.owner-scope-discovery.v2",
                "spine.owner-scope-list-response.v2",
                "spine.owner-scope-list-cursor.v2",
                "spine.notification-profile-metadata-update.v1",
                "spine.system-info.v3",
                "spine.ledger-instance.v1",
                "spine.tickerd-compatibility.v1",
            }.issubset(IMPLEMENTED_CONTRACT_VERSIONS)
        )


if __name__ == "__main__":
    unittest.main()
