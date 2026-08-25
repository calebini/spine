#!/usr/bin/env bash
set -euo pipefail

command -v spine >/dev/null
command -v spine-ledger-migrate >/dev/null
command -v spine-seed-canary >/dev/null
command -v spine-worker >/dev/null
command -v jq >/dev/null
command -v sqlite3 >/dev/null

SPINE_EXAMPLE_ROOT="$(mktemp -d /tmp/spine-agent-first-success.XXXXXX)"
SPINE_EXAMPLE_DB="$SPINE_EXAMPLE_ROOT/spine.sqlite"
SPINE_EXAMPLE_OBSERVE_STATE="$SPINE_EXAMPLE_ROOT/observe-state"
SPINE_EXAMPLE_ACTIVE_STATE="$SPINE_EXAMPLE_ROOT/active-state"

if ! python3 -c 'from importlib.metadata import version; assert version("tickerd") == "0.2.0"' >/dev/null 2>&1; then
  echo "Exact Tickerd 0.2.0 distribution metadata is required; install the audited checkout first." >&2
  exit 1
fi

spine-ledger-migrate --db "$SPINE_EXAMPLE_DB" --initialize-if-empty >"$SPINE_EXAMPLE_ROOT/migration.json"
spine --db "$SPINE_EXAMPLE_DB" system info >"$SPINE_EXAMPLE_ROOT/system-info.json"
SPINE_EXAMPLE_TZ_VERSION="$(jq -r '.timezone_database_version' "$SPINE_EXAMPLE_ROOT/system-info.json")"

spine --db "$SPINE_EXAMPLE_DB" --input - subject upsert >"$SPINE_EXAMPLE_ROOT/subject.json" <<JSON
{
  "command_id": "agent-first-success-subject",
  "actor_subject_id": "agent-first-success",
  "subject_id": "agent-first-success",
  "subject_kind": "agent",
  "display_name": "Agent First Success",
  "status": "active",
  "updated_at_utc": "2034-12-31T00:00:00Z"
}
JSON

spine --db "$SPINE_EXAMPLE_DB" --input - delivery_target upsert >"$SPINE_EXAMPLE_ROOT/delivery-target.json" <<JSON
{
  "command_id": "agent-first-success-target",
  "actor_subject_id": "agent-first-success",
  "delivery_target_id": "agent-first-success-openclaw",
  "owner_kind": "subject",
  "owner_subject_id": "agent-first-success",
  "channel": "whatsapp",
  "adapter_name": "openclaw",
  "target_ref": "agent-first-success@example.invalid",
  "display_name": "Fake-only first-success target",
  "status": "active",
  "updated_at_utc": "2034-12-31T00:01:00Z"
}
JSON

spine --db "$SPINE_EXAMPLE_DB" --input - event create >"$SPINE_EXAMPLE_ROOT/event.json" <<JSON
{
  "command_id": "agent-first-success-event",
  "actor_subject_id": "agent-first-success",
  "created_at_utc": "2034-12-31T00:02:00Z",
  "title": "Planning every three days",
  "all_day": false,
  "start_anchor": {
    "anchor_kind": "local_instant",
    "local_date": "2035-01-01",
    "local_time": "08:00:00",
    "timezone": "America/Los_Angeles",
    "timezone_database_version": "$SPINE_EXAMPLE_TZ_VERSION",
    "recurrence_set": {
      "time_basis": "local_instant",
      "timezone": "America/Los_Angeles",
      "timezone_database_version": "$SPINE_EXAMPLE_TZ_VERSION",
      "rules": [
        {
          "frequency": "DAILY",
          "interval": "3",
          "seed": "2035-01-01T08:00:00",
          "start_bound": "2035-01-01T08:00:00",
          "end_condition": {"kind": "count", "count": "4"}
        }
      ]
    }
  }
}
JSON

SPINE_EXAMPLE_ITEM_ID="$(jq -r '.item_id' "$SPINE_EXAMPLE_ROOT/event.json")"

spine --db "$SPINE_EXAMPLE_DB" --input - item occurrences >"$SPINE_EXAMPLE_ROOT/occurrences.json" <<JSON
{
  "item_id": "$SPINE_EXAMPLE_ITEM_ID",
  "range_start": "2035-01-01T00:00:00",
  "range_end": "2035-01-12T00:00:00",
  "range_basis": "original_schedule",
  "limit": "100",
  "include_diagnostics": true
}
JSON

jq -e '.ok == true and (.occurrences | length) == 4' "$SPINE_EXAMPLE_ROOT/occurrences.json" >/dev/null
SPINE_EXAMPLE_RECURRENCE_SET_ID="$(jq -r '.recurrence_set_id' "$SPINE_EXAMPLE_ROOT/occurrences.json")"
SPINE_EXAMPLE_RECURRENCE_REVISION_ID="$(jq -r '.recurrence_revision_id' "$SPINE_EXAMPLE_ROOT/occurrences.json")"

spine --db "$SPINE_EXAMPLE_DB" --input - --openclaw-whatsapp reminder create >"$SPINE_EXAMPLE_ROOT/reminder.json" <<JSON
{
  "command_id": "agent-first-success-reminder",
  "actor_subject_id": "agent-first-success",
  "item_id": "$SPINE_EXAMPLE_ITEM_ID",
  "target_version": "1",
  "created_at_utc": "2034-12-31T00:03:00Z",
  "recipient_kind": "subject",
  "recipient_subject_id": "agent-first-success",
  "channel": "whatsapp",
  "delivery_target_id": "agent-first-success-openclaw",
  "notification": {
    "authoring_contract": "spine.notification-schedule-authoring.v1",
    "target": {"anchor_role": "event_start", "application_scope": "each_occurrence"},
    "schedule": {
      "kind": "repeat_window",
      "start": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-21600"},
      "stop": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "0"},
      "stop_inclusive": false,
      "cadence": {"kind": "fixed_elapsed", "interval_seconds": "3600"}
    },
    "late_handling": {"kind": "skip"}
  }
}
JSON

SPINE_EXAMPLE_ITEM_VERSION="$(jq -r '.current_version' "$SPINE_EXAMPLE_ROOT/reminder.json")"

spine --db "$SPINE_EXAMPLE_DB" --input - occurrence_provenance regenerate >"$SPINE_EXAMPLE_ROOT/provenance.json" <<JSON
{
  "command_id": "agent-first-success-provenance",
  "actor_subject_id": "agent-first-success",
  "item_id": "$SPINE_EXAMPLE_ITEM_ID",
  "target_version": "$SPINE_EXAMPLE_ITEM_VERSION",
  "recurrence_set_id": "$SPINE_EXAMPLE_RECURRENCE_SET_ID",
  "recurrence_revision_id": "$SPINE_EXAMPLE_RECURRENCE_REVISION_ID",
  "regenerated_at_utc": "2034-12-31T00:04:00Z",
  "consumer": "notification_schedule",
  "range_basis": "original_schedule",
  "range_start": "2035-01-01T00:00:00",
  "range_end": "2035-01-12T00:00:00"
}
JSON

jq -e '.ok == true and .selected_count == "4"' "$SPINE_EXAMPLE_ROOT/provenance.json" >/dev/null

spine --db "$SPINE_EXAMPLE_DB" --input - notification opportunities >"$SPINE_EXAMPLE_ROOT/opportunities.json" <<JSON
{
  "item_id": "$SPINE_EXAMPLE_ITEM_ID",
  "evaluated_at_utc": "2034-12-31T00:05:00Z",
  "range_start_utc": "2035-01-01T00:00:00Z",
  "range_end_utc": "2035-01-12T00:00:00Z",
  "limit": "100",
  "include_diagnostics": true
}
JSON

jq -e '.ok == true and (.opportunities | length) == 24' "$SPINE_EXAMPLE_ROOT/opportunities.json" >/dev/null

spine --db "$SPINE_EXAMPLE_DB" --input - notification_work materialize >"$SPINE_EXAMPLE_ROOT/materialized.json" <<JSON
{
  "command_id": "agent-first-success-materialize",
  "actor_subject_id": "agent-first-success",
  "item_id": "$SPINE_EXAMPLE_ITEM_ID",
  "target_version": "$SPINE_EXAMPLE_ITEM_VERSION",
  "materialized_at_utc": "2034-12-31T00:06:00Z",
  "range_start_utc": "2035-01-01T00:00:00Z",
  "range_end_utc": "2035-01-12T00:00:00Z",
  "limit": "100"
}
JSON

jq -e '.ok == true and (.created_work_instance_ids | length) == 24' "$SPINE_EXAMPLE_ROOT/materialized.json" >/dev/null

spine-seed-canary "$SPINE_EXAMPLE_DB" \
  --prefix agent-first-success-canary \
  --target-ref agent-first-success-canary@example.invalid \
  --title "Agent first-success fake canary" \
  --openclaw-channel whatsapp >"$SPINE_EXAMPLE_ROOT/canary.json"

spine-worker \
  --db "$SPINE_EXAMPLE_DB" \
  --state-dir "$SPINE_EXAMPLE_OBSERVE_STATE" \
  --mode observe_only \
  --bindings openclaw \
  --openclaw-sender fake \
  --max-work-items 1 \
  --max-cycles 1 >"$SPINE_EXAMPLE_ROOT/observe.json"

test ! -e "$SPINE_EXAMPLE_OBSERVE_STATE/openclaw_sends.jsonl"

spine-worker \
  --db "$SPINE_EXAMPLE_DB" \
  --state-dir "$SPINE_EXAMPLE_ACTIVE_STATE" \
  --mode active \
  --bindings openclaw \
  --openclaw-sender fake \
  --max-work-items 1 \
  --max-cycles 1 >"$SPINE_EXAMPLE_ROOT/active.json"

test "$(wc -l <"$SPINE_EXAMPLE_ACTIVE_STATE/openclaw_sends.jsonl")" -eq 1
spine --db "$SPINE_EXAMPLE_DB" \
  --item-id "$SPINE_EXAMPLE_ITEM_ID" \
  --include policies,work,attempts \
  schedule show >"$SPINE_EXAMPLE_ROOT/schedule-show.json"
jq -e '
  .ok == true
  and .lifecycle.authored.state == "committed"
  and .lifecycle.delivery.attempt_state == "attempted"
  and .lifecycle.delivery.outcome_state == "succeeded"
  and .lifecycle.delivery.status_counts.succeeded == "1"
' "$SPINE_EXAMPLE_ROOT/schedule-show.json" >/dev/null
test "$(sqlite3 "$SPINE_EXAMPLE_DB" "SELECT COUNT(*) FROM pragma_foreign_key_check;")" -eq 0

jq -n \
  --arg evidence_root "$SPINE_EXAMPLE_ROOT" \
  --arg item_id "$SPINE_EXAMPLE_ITEM_ID" \
  --arg timezone_database_version "$SPINE_EXAMPLE_TZ_VERSION" \
  '{
    ok: true,
    recurrence_occurrences: 4,
    notification_opportunities: 24,
    materialized_notification_work: 24,
    observe_only_fake_sends: 0,
    active_fake_sends: 1,
    item_id: $item_id,
    timezone_database_version: $timezone_database_version,
    evidence_root: $evidence_root
  }'
