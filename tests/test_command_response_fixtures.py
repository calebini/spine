import json
import unittest
from copy import deepcopy
from pathlib import Path

from spine.commands import (
    command_receipt,
    event_reschedule_response,
    event_update_response,
    item_list_response,
    item_show_response,
    task_update_response,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "command_responses"


class CommandResponseFixtureTests(unittest.TestCase):
    def test_item_show_event_matches_golden_fixture(self) -> None:
        self.assertEqual(
            item_show_response(_event_item()),
            _fixture("item_show_event.json"),
        )

    def test_item_list_matches_golden_fixture(self) -> None:
        self.assertEqual(
            item_list_response([_event_item(), _task_item()]),
            _fixture("item_list.json"),
        )

    def test_event_update_fresh_matches_golden_fixture(self) -> None:
        self.assertEqual(
            event_update_response(
                updated=True,
                item=_event_item(),
                target_version="1",
                audit_id="audit-event-update",
                command_receipt_id="command_receipt-event-update",
            ),
            _fixture("event_update_fresh.json"),
        )

    def test_event_reschedule_noop_matches_golden_fixture(self) -> None:
        self.assertEqual(
            event_reschedule_response(
                rescheduled=False,
                item=_event_item(),
                target_version="2",
                audit_id=None,
                command_receipt_id="command_receipt-event-reschedule-noop",
            ),
            _fixture("event_reschedule_noop.json"),
        )

    def test_task_update_replay_matches_golden_fixture(self) -> None:
        self.assertEqual(
            task_update_response(
                updated=False,
                item=_task_item(),
                target_version="1",
                audit_id=None,
                command_receipt_id="command_receipt-task-update-replay",
            ),
            _fixture("task_update_replay.json"),
        )

    def test_command_receipt_matches_golden_fixture(self) -> None:
        self.assertEqual(
            command_receipt(
                command="event.update",
                command_id="cmd-event-update",
                actor_subject_id="subject-agent",
                action_timestamp_utc="2026-06-06T11:00:00Z",
                effect="event_updated",
                item_id="event-1",
                target_version="1",
                command_receipt_id="command_receipt-event-update",
                semantic_facts={
                    "command": "event.update",
                    "command_id": "cmd-event-update",
                    "actor_subject_id": "subject-agent",
                    "action_timestamp_utc": "2026-06-06T11:00:00Z",
                    "item_id": "event-1",
                    "target_version": "1",
                    "version": "2",
                    "updated": True,
                },
                result_identity_facts={
                    "command_receipt_id": "command_receipt-event-update",
                    "item_id": "event-1",
                    "target_version": "1",
                    "version": "2",
                    "current_version": "2",
                    "audit_id": "audit-event-update",
                },
            ),
            _fixture("command_receipt_event_update.json"),
        )


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_DIR / name).read_text())


def _event_item() -> dict[str, object]:
    return {
        "item_id": "event-1",
        "item_type": "event",
        "current_version": 2,
        "status": "active",
        "created_at_utc": "2026-06-06T10:00:00Z",
        "updated_at_utc": "2026-06-06T11:00:00Z",
        "archived_at_utc": None,
        "version": {
            "title": "Dentist",
            "summary": "Bring forms",
            "source_ref": "manual",
            "intent_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "normalized_fields_hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "created_at_utc": "2026-06-06T11:00:00Z",
            "created_by_subject_id": "subject-agent",
        },
        "detail": {
            "event_status": "scheduled",
            "all_day": False,
            "start_anchor_id": "anchor-start",
            "start_anchor": {
                "anchor_id": "anchor-start",
                "anchor_kind": "instant_utc",
                "created_at_utc": "2026-06-06T10:00:00Z",
                "utc_instant": "2026-06-06T14:00:00Z",
            },
            "end_anchor_id": None,
            "end_anchor": None,
            "visibility": None,
            "attendance_policy_ref": None,
        },
        "locations": [],
        "subject_roles": [],
        "notification_policies": [],
    }


def _task_item() -> dict[str, object]:
    item = deepcopy(_event_item())
    item.update(
        {
            "item_id": "task-1",
            "item_type": "task",
            "current_version": 1,
            "created_at_utc": "2026-06-06T09:00:00Z",
            "updated_at_utc": "2026-06-06T09:00:00Z",
            "version": {
                "title": "File paperwork",
                "summary": None,
                "source_ref": None,
                "intent_hash": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
                "normalized_fields_hash": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
                "created_at_utc": "2026-06-06T09:00:00Z",
                "created_by_subject_id": "subject-agent",
            },
            "detail": {
                "task_status": "open",
                "due_anchor_id": None,
                "due_anchor": None,
                "defer_until_anchor_id": None,
                "defer_until_anchor": None,
                "completed_at_utc": None,
                "completed_by_subject_id": None,
                "completion_state": None,
                "priority": None,
            },
        }
    )
    return item


if __name__ == "__main__":
    unittest.main()
