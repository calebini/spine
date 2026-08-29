import unittest

from spine.models import (
    AttemptStatus,
    CandidateActionKind,
    CandidateActionStatus,
    EventStatus,
    GenerationSourceKind,
    ItemLocationRole,
    ItemStatus,
    ItemSubjectRole,
    ItemType,
    LocationKind,
    NotificationPolicyStatus,
    ProjectionStatus,
    RelationStatus,
    RelationType,
    SubjectKind,
    SubjectMembershipRole,
    SubjectMembershipStatus,
    SubjectStatus,
    TaskStatus,
    TemporalAnchorKind,
    WorkKind,
    WorkStatus,
)


class EnumTests(unittest.TestCase):
    def test_mvp_enum_values(self) -> None:
        self.assertEqual({value.value for value in ItemType}, {"event", "task", "project", "collection"})
        self.assertEqual({value.value for value in ItemStatus}, {"active", "archived"})
        self.assertEqual({value.value for value in SubjectKind}, {"person", "agent"})
        self.assertEqual({value.value for value in SubjectStatus}, {"active", "inactive"})
        self.assertEqual({value.value for value in SubjectMembershipRole}, {"member", "owner"})
        self.assertEqual({value.value for value in SubjectMembershipStatus}, {"active", "ended"})
        self.assertEqual({value.value for value in EventStatus}, {"scheduled", "cancelled"})
        self.assertEqual({value.value for value in TaskStatus}, {"open", "done", "cancelled"})
        self.assertEqual(
            {value.value for value in TemporalAnchorKind},
            {"instant_utc", "local_instant", "local_date", "utc_window", "local_window"},
        )
        self.assertEqual({value.value for value in RelationType}, {"depends_on", "part_of"})
        self.assertEqual({value.value for value in RelationStatus}, {"active", "inactive"})
        self.assertEqual({value.value for value in LocationKind}, {"address", "place", "virtual", "relative", "unknown"})
        self.assertEqual(
            {value.value for value in ItemLocationRole},
            {"primary", "pickup", "dropoff", "meeting_link", "context"},
        )
        self.assertEqual(
            {value.value for value in ItemSubjectRole},
            {"participant", "assignee", "watcher", "owner", "recipient"},
        )
        self.assertEqual({value.value for value in NotificationPolicyStatus}, {"active", "disabled"})
        self.assertEqual(
            {value.value for value in GenerationSourceKind},
            {"work_instance", "notification_policy", "schedule_tick", "user_action", "item_version"},
        )
        self.assertEqual({value.value for value in WorkKind}, {"notification_reminder"})
        self.assertEqual(
            {value.value for value in WorkStatus},
            {"eligible", "in_progress", "succeeded", "failed", "cancelled"},
        )
        self.assertEqual(
            {value.value for value in CandidateActionKind},
            {"deliver_notification", "sync_projection", "request_user_decision"},
        )
        self.assertEqual({value.value for value in CandidateActionStatus}, {"open", "resolved", "dismissed"})
        self.assertEqual({value.value for value in AttemptStatus}, {"started", "succeeded", "failed", "rejected"})
        self.assertEqual({value.value for value in ProjectionStatus}, {"current", "stale", "failed"})

    def test_unknown_enum_values_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ItemType("deadline")

        with self.assertRaises(ValueError):
            RelationType("blocks")


if __name__ == "__main__":
    unittest.main()
