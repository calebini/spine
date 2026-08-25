import unittest

import spine
from spine.core import SpineValidationError
from spine.core.canonical_json import canonical_json_text
from spine.models import EventStatus, ItemStatus, ItemType, RelationType, TemporalAnchorKind


class Stage1ScaffoldTests(unittest.TestCase):
    def test_package_imports(self) -> None:
        self.assertEqual(spine.__version__, "0.2.0")
        self.assertEqual(ItemType.EVENT.value, "event")
        self.assertEqual(ItemStatus.ACTIVE.value, "active")
        self.assertEqual(EventStatus.SCHEDULED.value, "scheduled")
        self.assertEqual(TemporalAnchorKind.LOCAL_DATE.value, "local_date")
        self.assertEqual(RelationType.DEPENDS_ON.value, "depends_on")

    def test_validation_error_has_stable_code(self) -> None:
        error = SpineValidationError("invalid_status", "unknown item status")
        self.assertEqual(str(error), "invalid_status: unknown item status")

    def test_canonical_json_boundary_is_real(self) -> None:
        self.assertEqual(canonical_json_text({"title": "dentist"}), '{"title":"dentist"}')


if __name__ == "__main__":
    unittest.main()
