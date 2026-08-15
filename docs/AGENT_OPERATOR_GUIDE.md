# Agent Operator Guide

Status: operational contract for current runtime surfaces
Audience: local agents and agent operators integrating with Spine

This guide tells an agent how to interact with Spine safely. It is intentionally narrower than the ontology and architecture specs. If this guide and implementation behavior disagree, stop and ask an operator before writing or sending.

New agents start with `docs/AGENT_QUICKSTART.md`. Its checked-in `examples/agent-first-success.sh` path proves recurrence, recurring notifications, provenance, materialization, observe-only behavior, and one fake delivery on a disposable ledger. Return here for existing-ledger migration, production-shaped operation, inspection, and failure handling.

## Contents

- Operating posture and safety rules
- Environment prerequisites and ledger entry paths
- Public command and runtime surfaces
- Flexible recurrence and notification workflows
- Migration, rollback, and worker modes
- Verification queries and success evidence
- Failure taxonomy and troubleshooting

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

## Environment and Ledger Entry Paths

Spine requires Python 3.12 or newer. Operator workflows also use `sqlite3`; the executable first-success example uses `jq`. Tickerd must be installed or importable through `PYTHONPATH` before worker commands.

Set explicit paths rather than relying on host defaults. `SPINE_CHECKOUT` is host-supplied; no checked-in path is authoritative for a deployment:

```bash
export SPINE_CHECKOUT=/absolute/path/to/spine
export EXPECTED_SPINE_REVISION=approved-commit-or-tag
export SPINE_DB=/absolute/path/to/ledger.sqlite
export SPINE_STATE_DIR=/absolute/path/to/spine-worker-state
export TICKERD_SRC=/absolute/path/to/tickerd/src

export SPINE_PYTHON="$SPINE_CHECKOUT/.venv/bin/python"
export SPINE_COMMAND="$SPINE_CHECKOUT/.venv/bin/spine-command"
export SPINE_MIGRATE="$SPINE_CHECKOUT/.venv/bin/spine-ledger-migrate"
export SPINE_SEED_CANARY="$SPINE_CHECKOUT/.venv/bin/spine-seed-canary"
export SPINE_WORKER="$SPINE_CHECKOUT/.venv/bin/spine-worker"

test -d "$SPINE_CHECKOUT/src"
test -x "$SPINE_PYTHON"
test -x "$SPINE_COMMAND"
test -x "$SPINE_MIGRATE"
"$SPINE_PYTHON" --version
sqlite3 --version
git -C "$SPINE_CHECKOUT" status --short
```

Then choose exactly one ledger entry path:

- New disposable ledger: `"$SPINE_MIGRATE" --db "$SPINE_DB" --initialize-if-empty`.
- Existing current ledger: `"$SPINE_MIGRATE" --db "$SPINE_DB" --verify-only`.
- Existing older ledger: stop its worker, take a recoverable copy, run `"$SPINE_MIGRATE" --db "$SPINE_DB"`, and only then run `--verify-only`.

Do not require current-schema verification before an intended migration; an older valid schema is expected to fail that check. After initialization or migration, run:

```bash
"$SPINE_MIGRATE" --db "$SPINE_DB" --verify-only
"$SPINE_COMMAND" --db "$SPINE_DB" --pretty system info
```

Require equal `implemented_ledger_schema_version` and `ledger_schema_version`. Before using the atomic surface, also require `implemented_contract_versions` to include `spine.schedule-create.v1`, `spine.schedule-create-normalization.v1`, `spine.schedule-create-response.v1`, `spine.schedule-create-receipt.v1`, and `spine.schedule-show.v1`.

For `schedule.create`, prefer the request directive `"timezone_database_version":{"kind":"system_current"}`. Spine resolves it once during fresh execution, stores the concrete installed version, and returns that concrete value in receipts and readback. A compatible replay returns the original resolved version even if the host later installs newer timezone data. Operators may instead use `{"kind":"explicit","version":"<exact-version>"}`. Omission is invalid; Spine never chooses timezone data through a hidden default. For lower-level local-time commands that require the concrete string directly, use the value returned by `system.info`. Never copy a version from an example or another machine.

## Supported CLI Surfaces

Update only a clean checkout and refresh that checkout's existing virtual environment. If `git status --short` is non-empty, stop rather than overwriting or mixing local work. A deployment-specific supervisor remains stopped until schema and runtime verification complete.

```bash
git -C "$SPINE_CHECKOUT" status --short
git -C "$SPINE_CHECKOUT" pull --ff-only
"$SPINE_PYTHON" -m pip install -e "$SPINE_CHECKOUT"
test "$(git -C "$SPINE_CHECKOUT" rev-parse HEAD)" = \
  "$(git -C "$SPINE_CHECKOUT" rev-parse "$EXPECTED_SPINE_REVISION^{commit}")"
"$SPINE_COMMAND" --help
"$SPINE_MIGRATE" --help
```

`EXPECTED_SPINE_REVISION` is deployment input supplied outside the repository. The equality check prevents a successful pull on the wrong branch or tracking target from being mistaken for the approved build.

If Tickerd is not installed as a package, include its source path for runtime commands:

```bash
export TICKERD_SRC=/path/to/tickerd/src
```

Current commands:

- `"$SPINE_COMMAND"`: public structured command adapter. Stable syntax is `"$SPINE_COMMAND" --db <path> --input <path-or-> [options] <resource> <verb>`; CLI options precede command words.
- `"$SPINE_COMMAND" --db <path> system info`: read exact runtime, schema, timezone-data, and contract versions without mutation.
- `"$SPINE_MIGRATE"`: initialize, migrate, and verify a ledger.
- `"$SPINE_CHECKOUT/.venv/bin/spine-seed-demo"`: create or reuse a deterministic demo reminder.
- `"$SPINE_SEED_CANARY"`: create or reuse a controlled canary reminder and print the predicted OpenClaw envelope.
- `"$SPINE_WORKER"`: run the production-shaped worker in `observe_only`, `active`, or `suspended`.
- `"$SPINE_CHECKOUT/.venv/bin/spine-openclaw-smoke"`: run a bounded fake OpenClaw smoke.

The scheduling command surface is `schedule.create`, `schedule.show`, `event.create`, `event.reschedule`, `task.create`, `item.occurrences`, `recurrence.instance.add`, `recurrence.instance.remove`, `recurrence.instance.override`, `recurrence.series.edit`, `occurrence_provenance.regenerate`, `reminder.create`, `reminder.edit`, `reminder.disable`, `notification.opportunities`, and `notification_work.materialize`. Prefer `schedule.create` for a new scheduled item plus its initial reminders and `schedule.show` for canonical verification. Use the lower-level family for independent authoring, reads, and later mutations. See `docs/AGENT_QUICKSTART.md` for the complete executable path; see `specs/agent-command-contract.md` for normative request, response, replay, and failure behavior.

## Atomic Event or Task Scheduling

`schedule.create` is the safest operator-facing creation path when item and reminder authoring belong to one intent. One accepted request can create:

- item version 1 and its local-instant start/due anchor;
- optional recurrence on that anchor;
- one to 32 canonically ordered reminder policies;
- current occurrence provenance when recurrence and bounded materialization are both requested; and
- zero to 1000 bounded eligible work rows.

The command writes exactly one composite `schedule_created` audit and one command receipt. It invokes no public subcommands, creates no lower-level receipts, starts no work, makes no adapter call, and records no side-effect attempt. A failure in policy normalization, provenance, opportunity expansion, work creation, audit, receipt, or a commit invariant rolls the complete bundle back.

Use an already-active `delivery_target_id`, or supply a named context default at invocation:

```bash
"$SPINE_COMMAND" --db "$SPINE_DB" \
  --delivery-target-default owner_whatsapp=delivery_target_owner_whatsapp \
  --input /absolute/path/schedule-create-request.json \
  --dry-run --pretty schedule create
```

After inspecting the preview, remove `--dry-run` without changing the request or `command_id`. The committed response must distinguish `policies=authored`, `opportunities=expanded` or `not_requested`, `work=materialized`, `completed_zero_selected`, or `not_requested`, and always `delivery=not_attempted`. Replay returns the stored delivery and timezone snapshots even if current environment defaults later change; it does not repair missing evidence or re-resolve the route.

Verify the result without SQL:

```bash
export ITEM_ID=item-id-from-schedule-create
"$SPINE_COMMAND" --db "$SPINE_DB" \
  --item-id "$ITEM_ID" \
  --include policies,work,attempts \
  --pretty schedule show
```

Require `lifecycle.authored.state=committed`. Treat `lifecycle.opportunities`, `lifecycle.work`, `lifecycle.delivery.attempt_state`, and `lifecycle.delivery.outcome_state` as separate evidence. Authoring never implies delivery.

Structural request examples live in `tests/fixtures/schedule_create/contracts/`. The repeat-window event fixture is the quickest complete bounded example, and the recurring-task fixture shows inherited recurrence plus named route resolution without immediate work.

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

First discover and capture the exact installed timezone-data version:

```bash
export SPINE_TZ_VERSION="$("$SPINE_COMMAND" --db "$SPINE_DB" system info | jq -r '.timezone_database_version')"
test -n "$SPINE_TZ_VERSION"
```

The placeholders below mean the exact value in `SPINE_TZ_VERSION`; no literal version from this guide is portable across hosts.

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
    "timezone_database_version": "<SPINE_TZ_VERSION>",
    "recurrence_set": {
      "time_basis": "local_instant",
      "timezone": "America/Denver",
      "timezone_database_version": "<SPINE_TZ_VERSION>",
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

Invoke a request file with options before the command words:

```bash
"$SPINE_COMMAND" --db "$SPINE_DB" --input /absolute/path/event-create.json --pretty event create
"$SPINE_COMMAND" --db "$SPINE_DB" --input /absolute/path/occurrences.json --pretty item occurrences
```

For a directly executable variable-expanded request, use the event command in `examples/agent-first-success.sh`. Expansion returns virtual occurrences and stable occurrence identities; it does not create reminders, work, projections, or external sends. The canonical engine supports local dates, local instants, fixed UTC instants, daily/weekly/monthly/yearly rules, selectors, exceptions, moves, and bounded cursor pagination. Use the `recurrence.instance.*` commands for one occurrence and `recurrence.series.edit` for one, following, or whole-series changes.

## Worker Quick Reference

Run from `SPINE_CHECKOUT` only after choosing and completing the correct ledger entry path above. For a complete first-use sequence, run `docs/AGENT_QUICKSTART.md` instead of starting here.

Observe current eligible work without side effects:

```bash
PYTHONPATH="$TICKERD_SRC" "$SPINE_WORKER" \
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
"$SPINE_SEED_CANARY" "$SPINE_DB" \
  --prefix "<canary-prefix>" \
  --target-ref "<openclaw-target>" \
  --title "<canary-title>" \
  --openclaw-channel whatsapp \
  --if-absent
```

Run one fake active cycle:

```bash
PYTHONPATH="$TICKERD_SRC" "$SPINE_WORKER" \
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
"$SPINE_MIGRATE" --db "$SPINE_DB"
"$SPINE_MIGRATE" --db "$SPINE_DB" --verify-only
```

The migration is transactional. A failed attempt leaves the prior schema intact. It also fails closed when it finds scheduling rows whose missing canonical facts cannot be inferred exactly; inspect the reported table/count inventory instead of editing around the preflight.

Verify the committed surface before restarting Tickerd:

```bash
sqlite3 "$SPINE_DB" "SELECT MAX(schema_version) AS schema_version FROM ledger_schema;"
sqlite3 "$SPINE_DB" "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('recurrence_sets','recurrence_revisions','notification_policies','notification_schedules','occurrence_provenance') ORDER BY name;"
sqlite3 "$SPINE_DB" "PRAGMA foreign_key_check;"
```

Expected schema version is `7`, all five named tables are present, and `foreign_key_check` returns no rows. Then run `"$SPINE_SEED_CANARY"`, one observe-only worker cycle, and one active cycle with the fake sender. Do not enable the gateway sender during migration verification.

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

The full request also supplies the item/version, recipient owner, channel, and explicit `delivery_target_id`. Invoke WhatsApp policy authoring with the local binding switch before the command words:

```bash
"$SPINE_COMMAND" --db "$SPINE_DB" --input /absolute/path/reminder-create.json \
  --pretty --openclaw-whatsapp reminder create
```

That command persists policy truth and cannot send. `examples/agent-first-success.sh` contains a complete executable request with every required outer field; `tests/fixtures/notifications/contracts/command_reminder_create.json` is the corresponding structural contract example.

For recurring items, use `application_scope=each_occurrence` or `selected_occurrence`. After policy authoring and before the first `notification.opportunities` read, run `occurrence_provenance.regenerate` with `consumer=notification_schedule` over the target recurrence range. Opportunity expansion reads current active provenance; without it, recurrence-bound policies have no authorized targets. Regenerate again after recurrence truth changes, then recompute opportunities before materializing work.

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
"$SPINE_SEED_CANARY" "$SPINE_DB" \
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
PYTHONPATH="$TICKERD_SRC" "$SPINE_WORKER" \
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
PYTHONPATH="$TICKERD_SRC" "$SPINE_WORKER" \
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
PYTHONPATH="$TICKERD_SRC" "$SPINE_WORKER" \
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

## Canonical Schedule Verification

Use one read-only command after schedule creation, reminder mutation, work materialization, or worker processing:

```bash
"$SPINE_COMMAND" --db "$SPINE_DB" \
  --item-id "$ITEM_ID" \
  --include policies,work,attempts \
  --pretty schedule show
```

The response provides current item state; stored local time, concrete timezone-data version, and UTC resolution; current recurrence; policy and intent identities; work status; delivery route snapshots; and side-effect attempts. Collection counts and lifecycle summaries cover all matching evidence even when a detail limit truncates an array. The public field `notification_policy_id` intentionally aliases schema-7 `notification_policies.policy_id`; `work_instances.notification_policy_id` is also the canonical foreign-key column.

Do not infer delivery from authoring or materialization. Require `lifecycle.delivery.attempt_state=attempted` before claiming that a worker tried delivery, and inspect `lifecycle.delivery.outcome_state` plus `side_effect_attempts` before claiming success or failure. For virtual occurrence inspection, continue to use bounded `item.occurrences`; for provenance repair, use `occurrence_provenance.regenerate` and inspect its structured receipt.

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

Use repository evidence in this order:

1. `docs/AGENT_QUICKSTART.md` and `examples/agent-first-success.sh` for cold-start execution.
2. This guide for operations and failure handling.
3. `specs/agent-command-contract.md`, `specs/schedule-create.md`, `specs/schedule-show.md`, `specs/recurrence.md`, and `specs/notifications.md` for normative behavior.
4. `contracts/schemas/` for machine-readable request and response shapes.
5. `tests/fixtures/schedule_create/contracts/`, `tests/fixtures/recurrence/contracts/`, and `tests/fixtures/notifications/contracts/` for structural examples.
6. `tests/fixtures/recurrence/vectors/` and `tests/fixtures/notifications/vectors/` for computed identity evidence.
