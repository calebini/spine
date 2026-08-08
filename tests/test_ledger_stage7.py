from __future__ import annotations

import unittest

from spine.commands import CommandContext, handle
from spine.core import SpineValidationError
from spine.core.hashing import side_effect_request_hash, side_effect_request_payload_hash
from spine.ledger import (
    assert_candidate_action_not_stale,
    assert_work_instance_not_stale,
    connect,
    create_candidate_action,
    create_external_projection,
    create_next_item_version,
    create_started_attempt,
    create_work_instance,
    get_candidate_action,
    get_side_effect_attempt,
    initialize_schema,
    start_work_instance,
)
from tests.canonical_helpers import seed_notification_work

NOW = "2026-08-01T00:00:00Z"
SUBJECT_ID = "subject-stage7"


class LedgerStage7Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = connect()
        initialize_schema(self.connection)

    def tearDown(self) -> None:
        self.connection.close()

    def test_canonical_notification_materialization_produces_bound_work(self) -> None:
        seeded = self._seed("stage7-bound")
        work = self.connection.execute(
            "SELECT * FROM work_instances WHERE work_instance_id = ?",
            (seeded["work_instance_id"],),
        ).fetchone()

        self.assertEqual(work["item_id"], seeded["item_id"])
        self.assertEqual(work["notification_intent_id"], seeded["notification_intent_id"])
        self.assertEqual(work["notification_policy_id"], seeded["notification_policy_id"])
        self.assertEqual(work["status"], "eligible")
        self.assertIsNotNone(work["notification_opportunity_id"])

    def test_side_effect_requires_exactly_one_durable_origin(self) -> None:
        with self.assertRaisesRegex(SpineValidationError, "side_effect_attempt_rejected"):
            create_started_attempt(
                self.connection,
                attempt_id="attempt-without-origin",
                adapter_name="notification",
                idempotency_key="idem-without-origin",
                request_envelope={"body": "Reminder"},
                attempted_at_utc=NOW,
            )

    def test_stable_notification_intent_remains_processable_after_copy_forward(self) -> None:
        seeded = self._seed("stage7-copy")
        current = self._current_version(seeded["item_id"])
        create_next_item_version(
            self.connection,
            item_id=str(seeded["item_id"]),
            target_version=current,
            audit_id="audit-stage7-copy-vnext",
            created_at_utc="2026-08-01T00:10:00Z",
            created_by_subject_id=SUBJECT_ID,
            supporting_command_id="cmd-stage7-copy-forward",
        )

        assert_work_instance_not_stale(self.connection, str(seeded["work_instance_id"]))

    def test_policyless_work_is_stale_after_item_version_changes(self) -> None:
        seeded = self._seed("stage7-policyless")
        current = self._current_version(seeded["item_id"])
        created = create_work_instance(
            self.connection,
            work_instance_id="work-policyless-stale",
            item_id=str(seeded["item_id"]),
            item_version=current,
            work_subject_ref=SUBJECT_ID,
            eligible_at_utc="2026-08-01T01:00:00Z",
            created_at_utc=NOW,
        )
        create_next_item_version(
            self.connection,
            item_id=str(seeded["item_id"]),
            target_version=current,
            audit_id="audit-stage7-policyless-vnext",
            created_at_utc="2026-08-01T00:10:00Z",
            created_by_subject_id=SUBJECT_ID,
            supporting_command_id="cmd-stage7-policyless-forward",
        )

        with self.assertRaisesRegex(SpineValidationError, "stale_work_instance"):
            assert_work_instance_not_stale(self.connection, created.work_instance_id)

    def test_disabled_current_policy_blocks_prior_materialized_work(self) -> None:
        seeded = self._seed("stage7-disable")
        current = self._current_version(seeded["item_id"])
        response = handle(
            "reminder.disable",
            {
                "command_id": "cmd-stage7-disable",
                "actor_subject_id": SUBJECT_ID,
                "item_id": seeded["item_id"],
                "target_version": str(current),
                "notification_intent_id": seeded["notification_intent_id"],
                "notification_policy_id": seeded["notification_policy_id"],
                "disabled_at_utc": "2026-08-01T00:10:00Z",
            },
            CommandContext(ledger=self.connection),
        )
        self.assertTrue(response["ok"], response)
        with self.assertRaisesRegex(SpineValidationError, "stale_work_instance"):
            assert_work_instance_not_stale(self.connection, str(seeded["work_instance_id"]))

    def test_candidate_action_and_projection_freshness_are_version_bound(self) -> None:
        seeded = self._seed("stage7-candidate")
        item_id = str(seeded["item_id"])
        current = self._current_version(item_id)
        candidate = create_candidate_action(
            self.connection,
            candidate_action_id="candidate-stage7",
            item_id=item_id,
            item_version=current,
            action_kind="sync_projection",
            requires_approval=True,
            created_at_utc=NOW,
            evidence_ref="policy-check",
        )
        create_external_projection(
            self.connection,
            projection_id="projection-stage7",
            item_id=item_id,
            adapter_name="calendar",
            external_ref="external-1",
            projection_status="current",
            last_projected_version=current,
            updated_at_utc=NOW,
        )
        self.assertEqual(get_candidate_action(self.connection, candidate.candidate_action_id)["status"], "open")
        create_next_item_version(
            self.connection,
            item_id=item_id,
            target_version=current,
            audit_id="audit-stage7-candidate-vnext",
            created_at_utc="2026-08-01T00:10:00Z",
            created_by_subject_id=SUBJECT_ID,
            supporting_command_id="cmd-stage7-candidate-forward",
        )

        with self.assertRaisesRegex(SpineValidationError, "stale_candidate_action"):
            assert_candidate_action_not_stale(self.connection, candidate.candidate_action_id)
        with self.assertRaisesRegex(SpineValidationError, "side_effect_attempt_rejected"):
            create_started_attempt(
                self.connection,
                attempt_id="attempt-stale-projection",
                projection_id="projection-stage7",
                item_id=item_id,
                source_item_version=current,
                adapter_name="calendar",
                idempotency_key="idem-stale-projection",
                request_envelope={"summary": "Canonical notification test"},
                attempted_at_utc=NOW,
            )

    def test_started_attempt_persists_canonical_request_hashes(self) -> None:
        seeded = self._seed("stage7-attempt")
        work_id = str(seeded["work_instance_id"])
        start_work_instance(
            self.connection,
            work_instance_id=work_id,
            started_at_utc="2026-08-01T01:00:00Z",
        )
        envelope = {"body": "Canonical notification test", "to": SUBJECT_ID}
        started = create_started_attempt(
            self.connection,
            attempt_id="attempt-stage7-work",
            work_instance_id=work_id,
            adapter_name="notification",
            idempotency_key="idem-stage7-work",
            request_envelope=envelope,
            attempted_at_utc="2026-08-01T01:00:00Z",
        )

        payload_hash = side_effect_request_payload_hash(
            adapter_name="notification", request_envelope=envelope
        )
        request_hash = side_effect_request_hash(
            adapter_name="notification",
            idempotency_key="idem-stage7-work",
            request_payload_hash=payload_hash,
            work_instance_id=work_id,
        )
        self.assertEqual(started.request_payload_hash, payload_hash)
        self.assertEqual(started.request_hash, request_hash)
        self.assertEqual(
            get_side_effect_attempt(self.connection, "attempt-stage7-work")["attempt_status"],
            "started",
        )

    def test_attempt_rejects_ambiguous_origin_linkage(self) -> None:
        seeded = self._seed("stage7-ambiguous")
        item_id = str(seeded["item_id"])
        current = self._current_version(item_id)
        create_candidate_action(
            self.connection,
            candidate_action_id="candidate-ambiguous",
            item_id=item_id,
            item_version=current,
            action_kind="deliver_notification",
            requires_approval=False,
            created_at_utc=NOW,
        )
        start_work_instance(
            self.connection,
            work_instance_id=str(seeded["work_instance_id"]),
            started_at_utc="2026-08-01T01:00:00Z",
        )
        with self.assertRaisesRegex(SpineValidationError, "side_effect_attempt_rejected"):
            create_started_attempt(
                self.connection,
                attempt_id="attempt-ambiguous",
                work_instance_id=str(seeded["work_instance_id"]),
                candidate_action_id="candidate-ambiguous",
                adapter_name="notification",
                idempotency_key="idem-ambiguous",
                request_envelope={"body": "Reminder"},
                attempted_at_utc="2026-08-01T01:00:00Z",
            )

    def _seed(self, prefix: str) -> dict[str, object]:
        return seed_notification_work(
            self.connection,
            prefix=prefix,
            subject_id=SUBJECT_ID,
            now_utc=NOW,
            eligible_at_utc="2026-08-01T01:00:00Z",
        )

    def _current_version(self, item_id: object) -> int:
        return int(
            self.connection.execute(
                "SELECT current_version FROM coordination_items WHERE item_id = ?",
                (str(item_id),),
            ).fetchone()[0]
        )


if __name__ == "__main__":
    unittest.main()
