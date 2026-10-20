"""Private people helpers; no runtime command/permission qualification claimed."""

import json
import unittest
from pathlib import Path

from spine.core.errors import SpineValidationError
from spine.core.people import (
    RoleAssociation,
    managed_facts,
    managed_role,
    normalize_people,
    people_id,
    replacement_is_noop,
    replacement_rows,
    role_set_hash,
    subjects_needing_admission,
)


class PeopleCoreTests(unittest.TestCase):
    def test_omission_is_distinct_from_clear_and_create_default(self):
        for item_type, key in (("event", "participants"), ("task", "assignees")):
            self.assertIsNone(normalize_people(item_type=item_type))
            self.assertEqual(normalize_people(item_type=item_type, creating=True), ())
            self.assertEqual(normalize_people(item_type=item_type, value={key: []}), ())

    def test_closed_patch_shape_and_item_type(self):
        for value in (None, {}, [], {"assignees": []}, {"participants": [], "owner": []},
                      {"participants": (), "assignees": []}, {"participants": "subject"}):
            with self.subTest(value=value), self.assertRaises(SpineValidationError):
                normalize_people(item_type="event", value=value)
        with self.assertRaises(SpineValidationError):
            managed_role("project")

    def test_ids_preserve_codepoints_and_reject_invalid_values(self):
        for value in ("", 1, True, None, "a\x00", "a\x1f", "a\x7f", "\ud800", "\udfff", "a" * 257):
            with self.subTest(value=repr(value)), self.assertRaises(SpineValidationError):
                people_id(value)
        for value in (" é ", "é", "e\u0301", "𐀀", "a" * 256):
            self.assertEqual(people_id(value), value)
        ids = ["𐀀", "é", "e\u0301", "A", "a"]
        self.assertEqual(normalize_people(item_type="event", value={"participants": ids}), tuple(sorted(ids)))

    def test_duplicates_and_array_bounds(self):
        for value in (["s", "s"], [str(index) for index in range(101)], [False]):
            with self.assertRaises(SpineValidationError):
                normalize_people(item_type="task", value={"assignees": value})
        self.assertEqual(len(normalize_people(item_type="task", value={"assignees": [str(i) for i in range(100)]})), 100)

    def test_noop_compares_inactive_rows_and_ignores_other_roles(self):
        rows = [RoleAssociation("old", "s", "participant", "active"), RoleAssociation("owner", "o", "owner", "active")]
        self.assertTrue(replacement_is_noop("event", rows, ("s",)))
        self.assertTrue(replacement_is_noop("event", rows, None))
        self.assertFalse(replacement_is_noop("event", rows, ()))
        rows.append(RoleAssociation("inactive", "x", "participant", "inactive"))
        self.assertFalse(replacement_is_noop("event", rows, ("s",)))
        self.assertEqual(rows[0].item_subject_role_id, "old")

    def test_fresh_admission_selects_additions_and_reactivations_not_retention(self):
        rows = [RoleAssociation("a", "retained", "assignee", "active"),
                RoleAssociation("b", "reactivated", "assignee", "inactive"),
                RoleAssociation("c", "new", "owner", "active")]
        self.assertEqual(subjects_needing_admission("task", rows, ("retained", "reactivated", "new")), ("new", "reactivated"))
        self.assertEqual(subjects_needing_admission("task", rows, ()), ())

    def test_role_hash_ignores_physical_identity_and_row_order_not_status(self):
        rows = [RoleAssociation("a", "s", "participant", "active"), RoleAssociation("b", "t", "participant", "inactive")]
        other = [RoleAssociation("different", row.subject_id, row.role, row.status) for row in reversed(rows)]
        self.assertEqual(role_set_hash("event", rows), role_set_hash("event", other))
        self.assertNotEqual(role_set_hash("event", rows), role_set_hash("event", rows[:1]))
        with self.assertRaises(SpineValidationError):
            managed_facts("event", [rows[0], rows[0]])

    def test_replacement_identity_matches_reviewed_canonical_vector(self):
        path = Path(__file__).parent / "fixtures/people_and_responsibility/computed-vectors.json"
        vectors = {row["id"]: row for row in json.loads(path.read_text())["vectors"]}
        rows = replacement_rows(item_type="event", subjects=("z", "a"), command="item.people.update",
                                command_id="command_people_update_example")
        self.assertEqual(rows[0].subject_id, "a")
        self.assertEqual(rows[0].item_subject_role_id, "item_subject_role_" + vectors["new_managed_row_id"]["sha256"])
        reversed_rows = replacement_rows(item_type="event", subjects=("a", "z"), command="item.people.update",
                                         command_id="command_people_update_example")
        self.assertEqual(rows, reversed_rows)
        self.assertTrue(all(row.status == "active" for row in rows))

    def test_command_and_path_context_change_identity(self):
        outputs = [replacement_rows(item_type="task", subjects=("s",), command=command, command_id="c")[0]
                   for command in ("item.people.update", "schedule.create", "schedule.update")]
        self.assertEqual(len({row.item_subject_role_id for row in outputs}), 3)
        with self.assertRaises(SpineValidationError):
            replacement_rows(item_type="task", subjects=("s",), command="task.update", command_id="c")
