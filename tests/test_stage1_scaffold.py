import unittest

import spine
from spine.core import SpineValidationError
from spine.core.canonical_json import canonical_json_bytes
from spine.models import ItemStatus, ItemType


class Stage1ScaffoldTests(unittest.TestCase):
    def test_package_imports(self) -> None:
        self.assertEqual(spine.__version__, "0.1.0")
        self.assertEqual(ItemType.EVENT.value, "event")
        self.assertEqual(ItemStatus.ACTIVE.value, "active")

    def test_validation_error_has_stable_code(self) -> None:
        error = SpineValidationError("invalid_status", "unknown item status")
        self.assertEqual(str(error), "invalid_status: unknown item status")

    def test_canonical_json_boundary_is_explicitly_stage_2(self) -> None:
        with self.assertRaisesRegex(NotImplementedError, "Stage 2"):
            canonical_json_bytes({"title": "dentist"})


if __name__ == "__main__":
    unittest.main()
