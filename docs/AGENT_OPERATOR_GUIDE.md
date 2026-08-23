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
- Existing current ledger requiring explicit deep verification: `"$SPINE_MIGRATE" --db "$SPINE_DB" --verify-only`.
- Existing older ledger: stop its worker, take a recoverable copy, run `"$SPINE_MIGRATE" --db "$SPINE_DB"`, and only then run `--verify-only`.

`spine-ledger-migrate --verify-only` is the explicit deep-integrity path: it checks the full SQLite database, foreign keys, and unscoped Spine ledger invariants and may take time proportional to database size, especially with a cold filesystem cache. Use it for controlled deployment, migration, or incident verification; do not put it in an interactive command loop or a worker heartbeat. The bounded-runtime-preflight amendment in `specs/agent-command-contract.md` requires ordinary `spine-command` and worker startup to use a separate structural check whose cost is independent of ledger size. Until the executing release declares and tests that amendment as implemented, operators MUST assume routine command startup may still perform the older deep verification and MUST NOT claim bounded-preflight behavior from documentation alone.

Do not require current-schema verification before an intended migration; an older valid schema is expected to fail that check. After initialization or migration, run:

```bash
"$SPINE_MIGRATE" --db "$SPINE_DB" --verify-only
"$SPINE_COMMAND" --db "$SPINE_DB" --pretty system info
```

Require equal `implemented_ledger_schema_version` and `ledger_schema_version`. Before using the atomic and operator surfaces, also require `implemented_contract_versions` to include `spine.schedule-create.v1`, `spine.schedule-show.v1`, the complete agenda/update/cancel family, `spine.schedule-compact.v1`, and the countdown-builder family. Before authoring or reading primary locations, require `spine.schedule-primary-location.v1`, `spine.schedule-primary-location-authoring.v1`, `spine.schedule-primary-location-view.v1`, and `spine.schedule-primary-location-normalization.v1`. Before using related tasks, additionally require `spine.relative-temporal-binding.v1`, `spine.schedule-related-task-create.v1`, and both `spine.schedule-binding-list.v1` and `spine.schedule-binding-reconcile.v1` with their response/receipt/cursor versions.

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

The scheduling command surface is `schedule.build`, `schedule.create`, `schedule.related_task.create`, `schedule.show`, `agenda.show`, `schedule.update`, `schedule.cancel`, `schedule.binding.list`, `schedule.binding.reconcile`, `event.create`, `event.reschedule`, `task.create`, `item.occurrences`, `recurrence.instance.add`, `recurrence.instance.remove`, `recurrence.instance.override`, `recurrence.series.edit`, `occurrence_provenance.regenerate`, `reminder.create`, `reminder.edit`, `reminder.disable`, `notification.opportunities`, and `notification_work.materialize`. Prefer `schedule.related_task.create` when one intent includes a new task, `part_of` relation, event-relative due time, and optional reminders. Use `schedule.binding.list` and `.reconcile` for explicit follow-source lifecycle. Use the lower-level family for occurrence-specific or otherwise independent mutations. See `docs/AGENT_QUICKSTART.md` for the complete executable path; see `specs/agent-command-contract.md` for normative request, response, replay, and failure behavior.

## Stable Scheduling Lifecycle Language

Use the following words consistently in operator messages, agent logs, and handoffs:

- **Authored** or **saved** means canonical item and policy truth committed. It does not mean reminder times were calculated, work was queued, or delivery occurred.
- **Expanded** or **calculated** means Spine evaluated the bounded policy into notification opportunities. An opportunity is a virtual eligible moment, not executable work and not a delivery attempt.
- **Materialized** or **queued** means durable `work_instances` rows exist. Queued work has not necessarily started and has not necessarily crossed an adapter boundary.
- **Attempted** means a worker persisted a `side_effect_attempts` row before invoking an external boundary. An attempt may still be pending, failed, or rejected.
- **Delivered** means terminal attempt evidence records a successful outcome. Do not use **sent** or **delivered** for authored policy, expanded opportunity, or materialized work alone.

The compact operator shorthand is:

> Saved is not queued; queued is not attempted; attempted is not delivered.

When a routine chat acknowledgement needs one line, derive it from the returned lifecycle facts. For example: `Saved; 4 reminders queued; delivery not attempted.` Do not infer a later stage from an earlier one and do not replace the underlying structured receipt with this prose.

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

## Atomic Related Tasks and Temporal Bindings

Use `schedule.related_task.create` when the operator's one intent is “create this task as part of that event, due at an offset from it, with these reminders.” Do not emulate it with separate task, relation, and reminder commands. The source must be an exact active event ID and version. A non-recurring event uses `source.scope=item`; a recurring event requires one current occurrence key, its recurrence revision, and its revision-independent selector from the occurrence identity.

Choose binding behavior explicitly:

- `snapshot` copies the resolved event time once. Later event changes do not move or cancel the task.
- `follow_source` governs the task due time and requires `source_terminal_behavior=cancel_target|detach_at_last_value|require_decision`. Source changes are reconciled into ordinary task versions; they are never hidden read-time changes.

The zero-reminder snapshot example is directly copyable from `tests/fixtures/relative_temporal_bindings/contracts/request_create_snapshot_task.json`. Preview and commit the unchanged request with the same `command_id`:

```bash
"$SPINE_COMMAND" --db "$SPINE_DB" \
  --input "$SPINE_CHECKOUT/tests/fixtures/relative_temporal_bindings/contracts/request_create_snapshot_task.json" \
  --dry-run --pretty schedule related_task create
"$SPINE_COMMAND" --db "$SPINE_DB" \
  --input /absolute/path/related-task-request.json \
  --pretty schedule related_task create
```

Fresh success must enumerate the task, relation, binding/revision, concrete task-due anchor, policies, work, audit, and receipt separately. It always reports `delivery_state=not_attempted_by_command`. Read the granular evidence without SQL:

```bash
export RELATED_TASK_ID=item-id-from-related-task-receipt
"$SPINE_COMMAND" --db "$SPINE_DB" \
  --item-id "$RELATED_TASK_ID" \
  --include policies,work,attempts,relations,temporal_bindings \
  --pretty schedule show
```

For follow-source operation, discover bounded state and use the exact returned `reconcile_inputs`; do not reconstruct versions or query binding tables:

```bash
"$SPINE_COMMAND" --db "$SPINE_DB" --input /absolute/path/binding-list-request.json \
  --pretty schedule binding list
"$SPINE_COMMAND" --db "$SPINE_DB" --input /absolute/path/binding-reconcile-request.json \
  --dry-run --pretty schedule binding reconcile
"$SPINE_COMMAND" --db "$SPINE_DB" --input /absolute/path/binding-reconcile-request.json \
  --pretty schedule binding reconcile
```

`automatic_reconcile_eligible=true` is safe for the configured bounded scheduler loop. `operator_decision_required=true` requires an explicit supported resolution; do not repeatedly submit no-op decision receipts. A stale follow binding leaves the task visible but makes `agenda.show.schedule_actionable=false` and blocks schedule-dependent notification work before any attempt starts. Direct `schedule.update` replacement of its due time fails until the binding is explicitly detached. Snapshot and retired bindings do not add that freshness gate.

## Operational Schedule Lifecycle

Use the generic JSON-input CLI form for all three lifecycle commands:

```bash
"$SPINE_COMMAND" --db "$SPINE_DB" --input /absolute/path/agenda-request.json --pretty agenda show
"$SPINE_COMMAND" --db "$SPINE_DB" --input /absolute/path/schedule-update-request.json --dry-run --pretty schedule update
"$SPINE_COMMAND" --db "$SPINE_DB" --input /absolute/path/schedule-update-request.json --pretty schedule update
"$SPINE_COMMAND" --db "$SPINE_DB" --input /absolute/path/schedule-cancel-request.json --pretty schedule cancel
```

`agenda.show` is read-only. Its local range is half-open, bounded to 366 elapsed days, and pinned to one concrete timezone-data version. Repeat every non-cursor request fact unchanged on the next page. Treat `stale_cursor` as a requirement to restart from page one; Spine never continues against changed item, recurrence, policy, route, or requested work-summary facts.

`schedule.update` requires the exact current item version and an explicit `materialization` mode. Its patch is desired successor truth: `recurrence` is a whole-series replacement and `reminders`, when present, is the complete desired active set keyed by stable `policy_key`. It classifies existing work as cancelled, retained, or protected stale before optional bounded replacement materialization. Require `phases.delivery=not_attempted`; the command never starts work or sends. Preview the exact request with `--dry-run`, then commit it unchanged with the same `command_id`.

`schedule.cancel` creates the next cancelled item version and cancels every eligible, zero-attempt work row using `parent_lifecycle_terminal`. In-progress, retried, attempted, and terminal work remains immutable evidence under `protected_stale_work_instance_ids`. A fresh call against terminal truth fails; only a compatible replay of the original `command_id` returns success.

After either write, use `schedule.show` for complete item/policy/work/attempt evidence. Use lower-level recurrence commands for one-occurrence changes and series splits; the composite update intentionally preserves those precision surfaces. Structural examples live in `tests/fixtures/schedule_operations/contracts/`, and the exact contracts live in `specs/schedule-operations.md`.

### Relative event plus countdown builder

Use `schedule.build` when the operator intent is relative and the current reference instant is known. The command below compiles “event in two hours; remind every 30 minutes until it starts” and writes nothing:

```json
{
  "contract_version": "spine.schedule-countdown-builder.v1",
  "command_id": "appointment-countdown-001",
  "actor_subject_id": "agent",
  "reference_time_utc": "2026-08-15T14:00:00Z",
  "title": "Leave for appointment",
  "timezone": "America/Toronto",
  "timezone_database_version": {"kind": "system_current"},
  "event_delay_seconds": "7200",
  "reminder_interval_seconds": "1800",
  "delivery": {
    "recipient_kind": "subject",
    "recipient_subject_id": "agent",
    "channel": "whatsapp",
    "target": {"resolution": "context_default", "default_key": "owner_whatsapp"}
  }
}
```

Invoke it with the named existing route bound in context:

```bash
"$SPINE_COMMAND" --db "$SPINE_DB" \
  --delivery-target-default owner_whatsapp=delivery_target_owner_whatsapp \
  --input /absolute/path/countdown-builder-request.json \
  --pretty schedule build > /absolute/path/countdown-builder-response.json
jq '.schedule_create_request' /absolute/path/countdown-builder-response.json \
  > /absolute/path/countdown-schedule-create.json
"$SPINE_COMMAND" --db "$SPINE_DB" \
  --input /absolute/path/countdown-schedule-create.json \
  --compact schedule create
```

Require `effect=schedule_create_request_built` before extracting the generated request. The generated request uses an explicit timezone-data version and delivery target, and it is the artifact whose `command_id` is consumed by `schedule.create`.

### Compact receipts

Add `--compact` to successful create or readback commands when the consumer needs the stable audit subset rather than the full JSON:

```bash
"$SPINE_COMMAND" --db "$SPINE_DB" --input /absolute/path/schedule-create-request.json \
  --compact schedule create
"$SPINE_COMMAND" --db "$SPINE_DB" --item-id "$ITEM_ID" \
  --compact schedule show
```

The compact projection retains scheduled times, concrete timezone version, policy/intent IDs, work count/IDs, route adapter and target references, command identity, and separate lifecycle states. It does not mean delivery occurred. A preview explicitly returns `dry_run=true` and `lifecycle.authored=preview`; committed output returns `dry_run=false`. Omit `--compact` whenever the complete canonical receipt or readback is required.

Use compact and full output deliberately:

- Use `schedule.create --compact` for routine post-validation chat acknowledgement when the compact truncation flags are false and the operator does not need per-opportunity evidence.
- Use `schedule.show --compact` for a quick current-state check or chat response when policy/work identities and aggregate lifecycle are sufficient.
- Use full `schedule.create` output to inspect exact normalized policies, opportunity/work evidence, recurrence provenance, route resolution, or a consequential dry run before commit.
- Use full `schedule.show --include policies,work,attempts` before claiming delivery, diagnosing a failure, inspecting cancellation or staleness, reconciling IDs, or following any compact truncation flag.
- `schedule.update` and `schedule.cancel` currently return their full composite receipts; use `schedule.show` afterward when current row-level evidence matters.
- Use `agenda.show` for “what is coming up?”; it is a bounded projection and is not a substitute for full single-item delivery evidence.

Compact output is not less authoritative for the fields it contains, but it is intentionally incomplete. Full output is the escalation surface whenever the question depends on omitted detail.

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

Multiple reminders may be attached to one event or task by issuing repeated `reminder.create` commands. Use the `current_version` returned by each successful command as the next call's `target_version`. Each intent remains independently addressable as later policy commands advance the item version. Run notification scheduling only after the current schema-version-9 migration verifies successfully.

For a multi-reminder canary, verify before active processing that every expected work row is still `status=eligible`, has its own `notification_policy_id`, and has the intended `eligible_at_utc`. After processing, require one terminal successful work row and one successful side-effect attempt per reminder. Cancelling or archiving the parent item must suppress all remaining reminders; disabling a bound policy or cancelling a work row must suppress that reminder only.

Destination routing is explicit:

- `channel_hint` becomes OpenClaw gateway param `channel`.
- `delivery_targets.target_ref` becomes OpenClaw gateway param `to`.
- `work_subject_ref` is retained only as recipient-owner provenance for routed work.
- `body_text` is deterministically rendered from the current title, target time,
  attempt time, target timezone, item type, and current primary location. For example,
  it may be `Reminder: Tee time @ Lakeridge at 2 PM tomorrow` or
  `Reminder: Tee time @ Lakeridge in 1 hour`. The exact body and its hashes are
  persisted atomically with the started attempt and appear under that attempt in
  `schedule.show`.
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

## Primary Schedule Locations

Use the singular `item.primary_location` field on `schedule.create`; do not write
`locations` or `item_locations` directly and do not supply a general locations array.
Create a new canonical place inline:

```json
{
  "primary_location": {
    "mode": "create",
    "label": "Lakeside Golf Club",
    "kind": "place",
    "address_text": "123 Fairway Road",
    "timezone": "America/Toronto"
  }
}
```

Or explicitly link a known canonical row:

```json
{
  "primary_location": {
    "mode": "reference",
    "location_id": "location_..."
  }
}
```

Spine does not search, geocode, infer, or deduplicate a venue. Latitude and longitude,
when used, are paired decimal strings. A location's optional timezone is descriptive:
it never supplies or changes `scheduled_time.timezone` or its pinned timezone-data
version.

Use `schedule.update.patch.primary_location` with the same create/reference shapes to
replace the current location, JSON `null` to clear it, or omit the field to retain it.
An exact inline semantic match or reference to the current `location_id` is a no-op.
Location-only updates create ordinary item history but retain otherwise-current
recurrence provenance and notification work.

Read the clean bound view explicitly:

```bash
"$SPINE_COMMAND" --db "$SPINE_DB" \
  --item-id "$ITEM_ID" \
  --include primary_location \
  --pretty schedule show
```

Add `primary_location` to an `agenda.show.include` array when each agenda entry needs
the view. Explicit reads return `primary_location=null` when absent; omission means the
projection was not requested. Full `item.locations` remains the granular catalog
surface. `schedule.build` accepts the same authoring value and passes it into its
generated `schedule.create` request without resolving or writing it.

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
  --include policies,work,attempts,primary_location \
  --pretty schedule show
```

The response provides current item state; stored local time, concrete timezone-data version, and UTC resolution; current recurrence; policy and intent identities; work status; delivery route snapshots; and side-effect attempts. Include `primary_location` for the clean current location view, and add `relations,temporal_bindings` when inspecting a related task. Collection counts and lifecycle summaries cover all matching evidence even when a detail limit truncates an array. The public field `notification_policy_id` intentionally aliases `notification_policies.policy_id`; `work_instances.notification_policy_id` is also the canonical foreign-key column.

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
3. `specs/agent-command-contract.md`, `specs/schedule-create.md`, `specs/schedule-show.md`, `specs/schedule-primary-location.md`, `specs/recurrence.md`, and `specs/notifications.md` for normative behavior.
4. `contracts/schemas/` for machine-readable request and response shapes.
5. `tests/fixtures/schedule_create/contracts/`, `tests/fixtures/recurrence/contracts/`, and `tests/fixtures/notifications/contracts/` for structural examples.
6. `tests/fixtures/recurrence/vectors/` and `tests/fixtures/notifications/vectors/` for computed identity evidence.
