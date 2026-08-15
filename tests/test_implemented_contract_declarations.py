import unittest

from spine import IMPLEMENTED_CONTRACT_VERSIONS, IMPLEMENTED_LEDGER_SCHEMA_VERSION
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
                "spine.schedule-create.v1",
                "spine.schedule-create-normalization.v1",
                "spine.schedule-create-response.v1",
                "spine.schedule-create-receipt.v1",
                "spine.schedule-show.v1",
                "spine.system-info.v1",
            }.issubset(IMPLEMENTED_CONTRACT_VERSIONS)
        )


if __name__ == "__main__":
    unittest.main()
