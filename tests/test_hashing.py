import hashlib
import unittest

from spine.core.hashing import (
    audit_log_payload_hash,
    coordination_item_version_intent_hash,
    coordination_item_version_normalized_fields_hash,
    hash_canonical_json,
    side_effect_request_hash,
    side_effect_request_payload_hash,
)


class HashingTests(unittest.TestCase):
    def test_hash_is_sha256_over_canonical_json_bytes(self) -> None:
        value = {"b": "two", "a": "one"}
        expected = hashlib.sha256(b'{"a":"one","b":"two"}').hexdigest()

        self.assertEqual(hash_canonical_json(value), expected)

    def test_hash_is_stable_across_mapping_insertion_order(self) -> None:
        left = {"title": "Dentist", "summary": "Bring forms"}
        right = {"summary": "Bring forms", "title": "Dentist"}

        self.assertEqual(hash_canonical_json(left), hash_canonical_json(right))

    def test_intent_hash_omits_absent_optional_fields(self) -> None:
        self.assertEqual(
            coordination_item_version_intent_hash(title="Dentist"),
            hash_canonical_json({"title": "Dentist"}),
        )

    def test_intent_hash_includes_present_optional_fields(self) -> None:
        self.assertEqual(
            coordination_item_version_intent_hash(
                title="Dentist",
                summary="Bring forms",
                source_ref="calendar-import",
            ),
            hash_canonical_json(
                {
                    "title": "Dentist",
                    "summary": "Bring forms",
                    "source_ref": "calendar-import",
                }
            ),
        )

    def test_normalized_fields_hash_omits_source_ref(self) -> None:
        self.assertEqual(
            coordination_item_version_normalized_fields_hash(title="Dentist", summary="Bring forms"),
            hash_canonical_json({"title": "Dentist", "summary": "Bring forms"}),
        )

    def test_audit_log_payload_hash_uses_canonical_json(self) -> None:
        self.assertEqual(
            audit_log_payload_hash({"event": "item_created", "item_id": "item-1"}),
            hash_canonical_json({"item_id": "item-1", "event": "item_created"}),
        )

    def test_side_effect_request_payload_hash_uses_adapter_envelope_payload(self) -> None:
        self.assertEqual(
            side_effect_request_payload_hash(
                adapter_name="notification",
                request_envelope={"body": "Dentist", "to": "subject-1"},
            ),
            hash_canonical_json(
                {
                    "adapter_name": "notification",
                    "request_envelope": {"body": "Dentist", "to": "subject-1"},
                }
            ),
        )

    def test_side_effect_request_hash_omits_absent_optional_origins(self) -> None:
        request_payload_hash = hash_canonical_json({"payload": "abc"})

        self.assertEqual(
            side_effect_request_hash(
                adapter_name="notification",
                idempotency_key="idem-1",
                request_payload_hash=request_payload_hash,
                work_instance_id="work-1",
            ),
            hash_canonical_json(
                {
                    "adapter_name": "notification",
                    "idempotency_key": "idem-1",
                    "request_payload_hash": request_payload_hash,
                    "work_instance_id": "work-1",
                }
            ),
        )


if __name__ == "__main__":
    unittest.main()
