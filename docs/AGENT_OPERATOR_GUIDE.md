# Agent Operator Guide

Status: operational contract for current runtime surfaces
Audience: local agents and agent operators integrating with Spine

This guide tells an agent how to interact with Spine safely. It is intentionally narrower than the ontology and architecture specs. If this guide and implementation behavior disagree, stop and ask an operator before writing or sending.

## Operating Posture

Spine is the canonical coordination ledger. Agents may propose or create coordination records through supported Spine APIs and commands, then verify the resulting ledger rows. Agents must not treat calendars, messengers, local dashboards, or prior reminder runners as canonical truth once Spine owns a record.

Current production-shaped delivery path:

- Spine stores items, versions, notification policies, generated work, side-effect attempts, and outcomes.
- Tickerd provides the worker cadence, process lock, health file, and event stream.
- `spine-worker` adapts eligible Spine work into Tickerd work items.
- The OpenClaw binding can deliver `notification_reminder` work through `openclaw gateway call send`.

## Safety Rules

Agents must follow these rules:

- Do not write Spine tables directly with ad hoc SQL.
- Use Spine ledger/services APIs or installed CLI commands.
- Do not run real gateway sends unless the operator explicitly approves the exact work row and command.
- Do not use `--openclaw-sender gateway` without `--allow-real-send`.
- Do not run unbounded active workers during tests or canaries; use `--max-cycles 1`.
- Inspect the work row and predicted outbound envelope before any real gateway send.
- Treat `side_effect_attempts` as the source of truth for external send attempts.
- Keep private deployment evidence out of git. Use `ops/private/` or `*.private.md`.

## Preflight Sanity Check

Run this before mutation, worker, or gateway commands:

```bash
export SPINE_ROOT="${SPINE_ROOT:-/opt/spine}"
export TICKERD_SRC="${TICKERD_SRC:-/opt/tickerd/src}"
export SPINE_DB="${SPINE_DB:-/var/lib/spine/ledger.sqlite}"
export SPINE_STATE_DIR="${SPINE_STATE_DIR:-/var/lib/spine/worker}"

echo "SPINE_ROOT=${SPINE_ROOT}"
test -d "${SPINE_ROOT}" || { echo "ERROR: invalid SPINE_ROOT"; exit 1; }
test -d "${SPINE_ROOT}/src" || { echo "ERROR: Spine src path missing"; exit 1; }
test -f "${SPINE_DB}" || { echo "ERROR: Spine DB missing: ${SPINE_DB}"; exit 1; }
python3 --version || { echo "ERROR: python3 not available"; exit 1; }
cd "${SPINE_ROOT}" || { echo "ERROR: cannot cd to SPINE_ROOT"; exit 1; }
git status --short
spine-ledger-migrate --db "${SPINE_DB}" --verify-only
```

If preflight fails, stop and fix the environment before running mutation or send commands.

## Supported CLI Surfaces

Install or refresh Spine from the repository root:

```bash
python3 -m pip install -e .
```

If Tickerd is not installed as a package, include its source path for runtime commands:

```bash
export TICKERD_SRC=/path/to/tickerd/src
```

Current commands:

- `spine-ledger-migrate`: initialize, migrate, and verify a ledger.
- `spine-seed-demo`: create or reuse a deterministic demo reminder.
- `spine-seed-canary`: create or reuse a controlled canary reminder and print the predicted OpenClaw envelope.
- `spine-worker`: run the production-shaped worker in `observe_only`, `active`, or `suspended`.
- `spine-openclaw-smoke`: run a bounded fake OpenClaw smoke.

## Task Assignment Commands

Use `task.create` with `subject_roles` to author task assignees and owners without direct SQL. Every referenced subject must already exist through `subject.upsert`.

```json
{
  "command_id": "task-create-001",
  "actor_subject_id": "agent",
  "created_at_utc": "2026-07-16T16:00:00Z",
  "title": "Prepare stage canary",
  "subject_roles": [
    {"subject_id": "operator", "role": "assignee"},
    {"subject_id": "agent", "role": "owner"}
  ]
}
```

Use `task.update` with `patch.subject_roles` to replace the complete assignee/owner set. Omit `subject_roles` to preserve current assignments; pass an empty array to clear them. Accepted roles are `assignee` and `owner`, and optional `status` defaults to `active`.

```json
{
  "command_id": "task-reassign-001",
  "actor_subject_id": "agent",
  "item_id": "<task-item-id>",
  "target_version": 1,
  "updated_at_utc": "2026-07-16T16:05:00Z",
  "patch": {
    "subject_roles": [
      {"subject_id": "operator-2", "role": "assignee"},
      {"subject_id": "agent", "role": "owner"}
    ]
  }
}
```

Verify the returned `subject_roles` array or call `item.show` and inspect its current-version `subject_roles` before relying on the assignment.

## Flexible Recurrence Commands

Attach a structured recurrence set to an event start or task due anchor. This example schedules every three days at 08:00 local. The IANA timezone and pinned timezone-database version are canonical facts, so the expressed local time remains 08:00 when the UTC offset changes.

```json
{
  "command_id": "event-create-daily-0800-001",
  "actor_subject_id": "agent",
  "created_at_utc": "2026-07-25T14:00:00Z",
  "title": "Daily planning",
  "all_day": false,
  "start_anchor": {
    "anchor_kind": "local_instant",
    "local_date": "2026-07-26",
    "local_time": "08:00:00",
    "timezone": "America/Denver",
    "timezone_database_version": "2026a",
    "recurrence_set": {
      "time_basis": "local_instant",
      "timezone": "America/Denver",
      "timezone_database_version": "2026a",
      "rules": [
        {
          "frequency": "DAILY",
          "interval": "3",
          "seed": "2026-07-26T08:00:00",
          "start_bound": "2026-07-26T08:00:00",
          "end_condition": {"kind": "unbounded"}
        }
      ]
    }
  }
}
```

Expand a bounded range with the read-only `item.occurrences` command:

```json
{
  "item_id": "<event-item-id>",
  "range_start": "2026-07-26T00:00:00",
  "range_end": "2026-08-08T00:00:00",
  "range_basis": "original_schedule",
  "limit": "100",
  "include_diagnostics": true
}
```

Invoke those JSON bodies through `spine event create` and `spine item occurrences`, respectively. Expansion returns virtual occurrences and stable occurrence identities; it does not create reminders, work, projections, or external sends. The canonical engine supports local dates, local instants, fixed UTC instants, daily/weekly/monthly/yearly rules, selectors, exceptions, moves, and bounded cursor pagination. Use the `recurrence.instance.*` commands for one occurrence and `recurrence.series.edit` for one, following, or whole-series changes.

## Quick Start

Run from `SPINE_ROOT` after preflight.

Observe current eligible work without side effects:

```bash
PYTHONPATH="$TICKERD_SRC" spine-worker \
  --db "$SPINE_DB" \
  --state-dir "$SPINE_STATE_DIR" \
  --mode observe_only \
  --bindings openclaw \
  --openclaw-channel whatsapp \
  --openclaw-sender fake \
  --max-cycles 1
```

Seed a controlled canary without sending it:

```bash
spine-seed-canary "$SPINE_DB" \
  --prefix "<canary-prefix>" \
  --target-ref "<openclaw-target>" \
  --title "<canary-title>" \
  --openclaw-channel whatsapp \
  --if-absent
```

Run one fake active cycle:

```bash
PYTHONPATH="$TICKERD_SRC" spine-worker \
  --db "$SPINE_DB" \
  --state-dir "$SPINE_STATE_DIR" \
  --mode active \
  --bindings openclaw \
  --openclaw-channel whatsapp \
  --openclaw-sender fake \
  --max-cycles 1
```

## One-Patch Migration and Verification

Apply this delivery while the worker is stopped. Take a recoverable copy of the ledger first; a committed schema migration is rolled back operationally by restoring that copy together with the prior application build.

```bash
cp "$SPINE_DB" "$SPINE_DB.pre-canonical-scheduling"
spine-ledger-migrate --db "$SPINE_DB"
spine-ledger-migrate --db "$SPINE_DB" --verify-only
```

The migration is transactional. A failed attempt leaves the prior schema intact. It also fails closed when it finds scheduling rows whose missing canonical facts cannot be inferred exactly; inspect the reported table/count inventory instead of editing around the preflight.

Verify the committed surface before restarting Tickerd:

```bash
sqlite3 "$SPINE_DB" "SELECT MAX(schema_version) AS schema_version FROM ledger_schema;"
sqlite3 "$SPINE_DB" "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('recurrence_sets','recurrence_revisions','notification_policies','notification_schedules','occurrence_provenance') ORDER BY name;"
sqlite3 "$SPINE_DB" "PRAGMA foreign_key_check;"
```

Expected schema version is `7`, all five named tables are present, and `foreign_key_check` returns no rows. Then run `spine-seed-canary`, one observe-only worker cycle, and one active cycle with the fake sender. Do not enable the gateway sender during migration verification.

## Notification Schedule Handoff

Use `reminder.create` to persist a policy without creating work. Use `notification.opportunities` to inspect a bounded virtual schedule, then `notification_work.materialize` to persist actionable work. Authoring never sends and opportunity output never authorizes delivery by itself.

For “every hour during the six hours before an event,” use this notification body inside `reminder.create`:

```json
{
  "authoring_contract": "spine.notification-schedule-authoring.v1",
  "target": {"anchor_role": "event_start", "application_scope": "item"},
  "schedule": {
    "kind": "repeat_window",
    "start": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-21600"},
    "stop": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "0"},
    "stop_inclusive": false,
    "cadence": {"kind": "fixed_elapsed", "interval_seconds": "3600"}
  },
  "late_handling": {"kind": "deliver_within", "grace_seconds": "900"}
}
```

The full request also supplies the item/version, recipient owner, channel, and explicit `delivery_target_id`. For recurring items, use `application_scope=each_occurrence` or `selected_occurrence`; regenerate current occurrence provenance before materializing recurrence-bound work.

A deliverable reminder must eventually produce:

- a current task/item row
- a notification policy row
- an explicit active `delivery_targets` row for the OpenClaw endpoint
- an eligible `work_instances` row with `work_kind=notification_reminder` and matching `delivery_target_id`
- a channel value, currently `whatsapp` for the OpenClaw gateway path

Multiple reminders may be attached to one event or task by issuing repeated `reminder.create` commands. Use the `current_version` returned by each successful command as the next call's `target_version`. Each intent remains independently addressable as later policy commands advance the item version. Run notification scheduling only after the schema-version-7 migration verifies successfully.

For a multi-reminder canary, verify before active processing that every expected work row is still `status=eligible`, has its own `notification_policy_id`, and has the intended `eligible_at_utc`. After processing, require one terminal successful work row and one successful side-effect attempt per reminder. Cancelling or archiving the parent item must suppress all remaining reminders; disabling a bound policy or cancelling a work row must suppress that reminder only.

Destination routing is explicit:

- `channel_hint` becomes OpenClaw gateway param `channel`.
- `delivery_targets.target_ref` becomes OpenClaw gateway param `to`.
- `work_subject_ref` is retained only as recipient-owner provenance for routed work.
- `body_text` is currently derived as `Reminder: <current item title>`.
- `dedupe_key` is currently `openclaw:<work_instance_id>:<attempt_count>`.

The agent must persist or pass the destination intentionally. It must not infer a destination from conversational context at send time.

For controlled canary preparation:

```bash
spine-seed-canary "$SPINE_DB" \
  --prefix operator-canary \
  --target-ref "<openclaw-target>" \
  --title "Spine canary reminder" \
  --openclaw-channel whatsapp \
  --if-absent
```

Before any send, inspect the JSON output:

- `predicted_openclaw_envelope.channel_hint`
- `predicted_openclaw_envelope.target_ref`
- `predicted_openclaw_envelope.body_text`
- `predicted_openclaw_envelope.dedupe_key`
- `predicted_openclaw_envelope.attempt_id`

If any field is wrong, do not send. Fix the source record or integration path first.

## What Success Looks Like

Observe-only visibility success:

- `cycle_summary.cycle_success=true`
- `runtime_mode=observe_only`
- eligible work may show `work_item_blocked` with `reason=SIDE_EFFECTS_BLOCKED`
- work row remains `status=eligible`
- no OpenClaw side-effect attempt row is created

Fake active success:

- `cycle_summary.items_processed=1`
- work row becomes `status=succeeded`
- work row has `reason_code=openclaw_delivered`
- one `side_effect_attempts` row exists with `adapter_name=openclaw`
- attempt row has `attempt_status=succeeded`
- fake evidence exists in `openclaw_sends.jsonl`

Gateway active success:

- same ledger outcome as fake active success
- attempt row has a provider reference from OpenClaw
- no fake send evidence is created
- the operator can reconcile the provider reference with OpenClaw gateway logs

## Worker Modes

Use `observe_only` for visibility checks:

```bash
PYTHONPATH="$TICKERD_SRC" spine-worker \
  --db "$SPINE_DB" \
  --state-dir "$SPINE_STATE_DIR" \
  --mode observe_only \
  --bindings openclaw \
  --openclaw-channel whatsapp \
  --openclaw-sender fake \
  --max-cycles 1
```

Expected behavior:

- eligible work is scanned
- no side effects execute
- blocked records use `reason=SIDE_EFFECTS_BLOCKED`
- no `side_effect_attempts` row is created
- no `openclaw_sends.jsonl` file is created by the worker

Use `active` with fake sender for bounded dry runs:

```bash
PYTHONPATH="$TICKERD_SRC" spine-worker \
  --db "$SPINE_DB" \
  --state-dir "$SPINE_STATE_DIR" \
  --mode active \
  --bindings openclaw \
  --openclaw-channel whatsapp \
  --openclaw-sender fake \
  --max-cycles 1
```

Expected behavior:

- one eligible work row may be processed
- a `side_effect_attempts` row is created
- fake send evidence is written to `openclaw_sends.jsonl`

Use `active` with gateway only after explicit approval:

```bash
PYTHONPATH="$TICKERD_SRC" spine-worker \
  --db "$SPINE_DB" \
  --state-dir "$SPINE_STATE_DIR" \
  --mode active \
  --bindings openclaw \
  --openclaw-channel whatsapp \
  --openclaw-sender gateway \
  --allow-real-send \
  --max-cycles 1
```

This command can send a real message. Confirm the exact work row, target, body, channel, attempt id, and dedupe key before running it.

## Verification Queries

Inspect current recurrence identity and revision state:

```bash
sqlite3 "$SPINE_DB" "
SELECT rs.source_item_id, rs.recurrence_set_id, rr.recurrence_revision_id,
       rr.revision_number, rr.source_item_version,
       rr.normalized_recurrence_set_hash
FROM recurrence_sets AS rs
JOIN recurrence_revisions AS rr ON rr.recurrence_set_id = rs.recurrence_set_id
WHERE rs.source_item_id = '<item-id>'
  AND rr.revision_number = (
    SELECT MAX(current_rr.revision_number)
    FROM recurrence_revisions AS current_rr
    WHERE current_rr.recurrence_set_id = rs.recurrence_set_id
  );
"
```

Inspect current notification policy and schedule state:

```bash
sqlite3 "$SPINE_DB" "
SELECT p.notification_intent_id, p.policy_id, p.version, p.status,
       p.application_scope, p.delivery_target_id,
       p.normalized_notification_schedule_hash,
       s.schedule_kind, s.cadence_kind
FROM notification_policies AS p
JOIN notification_schedules AS s ON s.schedule_id = p.schedule_id
JOIN coordination_items AS i
  ON i.item_id = p.item_id AND i.current_version = p.version
WHERE p.item_id = '<item-id>'
ORDER BY p.notification_intent_id;
"
```

For recurrence-bound policies, inspect active authorization evidence and open recovery reports:

```bash
sqlite3 "$SPINE_DB" "
SELECT occurrence_provenance_id, occurrence_key, recurrence_revision_id,
       lifecycle, actionable, management_status
FROM occurrence_provenance
WHERE item_id = '<item-id>' AND management_status = 'active'
ORDER BY original_scheduled_fact, occurrence_key;
SELECT block_report_id, consumer, range_start, range_end, reason_code
FROM recurrence_provenance_block_reports
WHERE item_id = '<item-id>' AND status = 'open'
ORDER BY block_report_id;
"
```

Inspect a work row:

```bash
sqlite3 "$SPINE_DB" "
SELECT work_instance_id, status, eligible_at_utc, next_attempt_at_utc,
       attempt_count, reason_code, work_subject_ref
FROM work_instances
WHERE work_instance_id = '<work-instance-id>';
"
```

Inspect OpenClaw attempts for a work row:

```bash
sqlite3 "$SPINE_DB" "
SELECT attempt_id, adapter_name, attempt_status, provider_ref,
       reason_code, idempotency_key
FROM side_effect_attempts
WHERE work_instance_id = '<work-instance-id>'
ORDER BY attempt_id;
"
```

Inspect worker health and events:

```bash
cat "$SPINE_STATE_DIR/health.json"
tail -n 120 "$SPINE_STATE_DIR/events.jsonl"
```

For bounded one-cycle runs, `health.json` ending in `DOWN` with `last_failure_reason=max_cycles_reached` is expected. For a long-running service, health should be `UP` and `is_ready=true`.

Confirm no fake evidence exists for a real gateway state directory:

```bash
test ! -f "$SPINE_STATE_DIR/openclaw_sends.jsonl" && echo "no fake send evidence"
```

## Outcome Interpretation

Common work outcomes:

- `status=succeeded`, `reason_code=openclaw_delivered`: send succeeded and provider reference should be recorded.
- `status=eligible` with `reason_code=openclaw_gateway_transient`: gateway failed transiently and `next_attempt_at_utc` controls retry eligibility.
- `status=failed` with `reason_code=openclaw_gateway_permanent`: gateway rejected the request permanently.
- `status=cancelled` with a gateway or policy reason: delivery was blocked and should not be retried without operator review.

Common event records:

- `work_item_blocked` with `SIDE_EFFECTS_BLOCKED`: observe-only saw eligible work and correctly refused side effects.
- `cycle_summary` with `cycle_success=true`: Tickerd cycle completed.
- `items_processed=1`: one work item was actively processed.

## Failure Taxonomy

Use a deterministic failure class when reporting agent/operator failures:

- `ENVIRONMENT_ERROR`: missing checkout, missing dependency, invalid `SPINE_DB`, invalid `TICKERD_SRC`.
- `VALIDATION_ERROR`: missing required reminder fields, invalid timestamp, invalid target, invalid channel.
- `STATE_ERROR`: work row is missing, stale, already terminal, or not eligible.
- `RUNTIME_ERROR`: worker, SQLite, Tickerd, or command execution failed unexpectedly.
- `GATEWAY_ERROR`: OpenClaw gateway returned transient, permanent, blocked, or unverifiable result.
- `PATH_UNAVAILABLE`: requested ingest/send path is not supported by current Spine runtime.

Never claim success without the matching command result and ledger readback.

## Failure Handling

On validation failure:

1. Do not edit SQLite directly.
2. Capture the command, JSON output, and relevant `events.jsonl` tail.
3. Inspect the work row and side-effect attempts.
4. If the failed command could send externally, do not retry automatically.
5. Ask an operator to approve the next bounded action.

On gateway failure:

1. Preserve `side_effect_attempts`.
2. Inspect `reason_code`, `provider_ref`, and `idempotency_key`.
3. Check OpenClaw gateway logs without printing secrets.
4. Do not retry unless the operator approves the exact next attempt.

## Troubleshooting Map

`SIDE_EFFECTS_BLOCKED`:

- Expected in `observe_only`.
- Confirms the worker saw eligible work and refused side effects.

`openclaw_gateway_transient`:

- Gateway failure treated as retryable.
- Inspect `next_attempt_at_utc` before any future active run.

`openclaw_gateway_permanent`:

- Gateway rejected the request shape.
- Inspect channel, target, message body, auth configuration, and gateway logs.

`openclaw_gateway_auth_unresolved`:

- Gateway URL was configured without token or password.
- Fix protected environment configuration; do not retry by changing ledger rows.

`openclaw_accepted_unverified`:

- Gateway returned success-like output without a transport-meaningful receipt.
- Treat as failed until operator reviews OpenClaw evidence.

Unexpected duplicate send risk:

- Check `side_effect_attempts.idempotency_key`.
- Do not rerun active/gateway with a changed key for the same semantic send unless the operator explicitly approves.

## Integration Boundary

An ingest agent should translate user intent into the public structured recurrence and notification command families. It must not infer direct table writes from the relational schema. Keep recurrence cadence, notification cadence, and delivery retry as three distinct facts and let Spine derive their canonical identities.
