# Spine Agent Quickstart

Status: executable cold-start path for the current schema-7 runtime
Audience: an agent with repository access and no prior Spine context

Use this document to reach a verified first success. Use `docs/AGENT_OPERATOR_GUIDE.md` afterward for migration, long-running operation, real-send controls, inspection, and troubleshooting.

## The Five Facts to Retain

1. Spine is the canonical coordination ledger; calendars, messengers, and dashboards are projections.
2. Authoring commands never send. Notification work must be materialized before a worker can process it.
3. Recurring-item cadence, notification cadence, and delivery retry are separate facts.
4. Recurrence-bound notifications require current `occurrence_provenance` before opportunity expansion.
5. Real delivery requires an explicit target, active worker mode, gateway sender, and `--allow-real-send`. This quickstart uses only the fake sender.

## Prerequisites

Bind the host-selected checkout first. No checked-in path is authoritative for a deployment:

```bash
export SPINE_CHECKOUT=/absolute/path/to/spine
export SPINE_PYTHON="$SPINE_CHECKOUT/.venv/bin/python"
export SPINE_COMMAND="$SPINE_CHECKOUT/.venv/bin/spine-command"
export SPINE_MIGRATE="$SPINE_CHECKOUT/.venv/bin/spine-ledger-migrate"
export SPINE_WORKER="$SPINE_CHECKOUT/.venv/bin/spine-worker"
```

From that Spine checkout, require:

- Python 3.12 or newer;
- `sqlite3` and `jq` on `PATH`;
- Spine installed into the checkout-local virtual environment;
- Tickerd installed into that environment or a `TICKERD_SRC` path pointing to its `src` directory.

Verify the checkout-local installation. Create the virtual environment first only when provisioning a new checkout:

```bash
test -d "$SPINE_CHECKOUT/src"
test -x "$SPINE_PYTHON" || python3 -m venv "$SPINE_CHECKOUT/.venv"
"$SPINE_PYTHON" --version
sqlite3 --version
jq --version
"$SPINE_PYTHON" -m pip install -e "$SPINE_CHECKOUT[test,dev]"
test -x "$SPINE_COMMAND"
test -x "$SPINE_MIGRATE"
```

If Tickerd is not installed, point Python at a sibling checkout:

```bash
export TICKERD_SRC=/absolute/path/to/tickerd/src
export PYTHONPATH="$TICKERD_SRC${PYTHONPATH:+:$PYTHONPATH}"
"$SPINE_PYTHON" -c 'import tickerd; print("tickerd import ok")'
```

Do not continue to worker commands until that import succeeds.

## Choose the Correct Ledger Entry Path

### New disposable ledger

Create a unique directory and initialize a new schema-7 ledger:

```bash
export SPINE_DEMO_ROOT="$(mktemp -d /tmp/spine-agent-quickstart.XXXXXX)"
export SPINE_DB="$SPINE_DEMO_ROOT/spine.sqlite"
export SPINE_STATE_DIR="$SPINE_DEMO_ROOT/worker-state"
"$SPINE_MIGRATE" --db "$SPINE_DB" --initialize-if-empty
```

### Existing current ledger

Do not initialize or migrate it. Verify it without mutation:

```bash
export SPINE_DB=/absolute/path/to/ledger.sqlite
"$SPINE_MIGRATE" --db "$SPINE_DB" --verify-only
```

### Existing older ledger that requires migration

Stop its worker first. Do not run current-schema `--verify-only` as a prerequisite because an older schema is expected to fail that check. Back up, migrate once, then verify:

```bash
export SPINE_DB=/absolute/path/to/ledger.sqlite
cp "$SPINE_DB" "$SPINE_DB.pre-schema-7"
"$SPINE_MIGRATE" --db "$SPINE_DB"
"$SPINE_MIGRATE" --db "$SPINE_DB" --verify-only
```

If migration preflight rejects provisional scheduling rows, stop and inspect the reported inventory. Do not edit around it.

## Discover the Exact Local Authoring Context

Never copy a timezone-data version from documentation or another host. Read it from the executing runtime and ledger:

```bash
"$SPINE_COMMAND" --db "$SPINE_DB" --pretty system info
```

Successful output includes:

- `runtime_version`;
- equal `implemented_ledger_schema_version` and `ledger_schema_version`;
- `timezone_database_version`, which must be copied exactly into local-date and local-instant authoring;
- `implemented_contract_versions`.

For `schedule.create`, callers do not need to copy the concrete timezone version into the request. Use `"timezone_database_version":{"kind":"system_current"}` and Spine pins the executing runtime's concrete version before mutation. The response and later `schedule.show` return that concrete version. Replaying the same `command_id` retains the originally pinned version; omission is not a default and remains invalid. Lower-level local-time authoring continues to use the concrete value discovered here.

To capture the timezone-data version:

```bash
export SPINE_TZ_VERSION="$("$SPINE_COMMAND" --db "$SPINE_DB" system info | jq -r '.timezone_database_version')"
test -n "$SPINE_TZ_VERSION"
```

## Ten-Minute Automated First Success

The checked-in example exercises the complete safe path on a new disposable ledger:

- bootstrap one agent subject and explicit fake-only delivery target;
- author an event every three days at 08:00 local using the installed timezone-data version;
- expand four occurrences;
- author six hourly notification opportunities before every occurrence;
- regenerate recurrence provenance before opportunity expansion;
- expand 24 opportunities and materialize 24 future work rows;
- seed one immediately eligible canary;
- prove observe-only creates zero send evidence;
- process exactly one fake send in bounded active mode;
- verify one successful attempt and zero foreign-key errors.

Run it from the repository root:

```bash
PATH="$SPINE_CHECKOUT/.venv/bin:$PATH" \
TICKERD_SRC="${TICKERD_SRC:-$SPINE_CHECKOUT/../tickerd/src}" \
"$SPINE_CHECKOUT/examples/agent-first-success.sh"
```

It creates a unique directory under `/tmp` and prints a summary like:

```json
{
  "ok": true,
  "recurrence_occurrences": 4,
  "notification_opportunities": 24,
  "materialized_notification_work": 24,
  "observe_only_fake_sends": 0,
  "active_fake_sends": 1,
  "item_id": "item_...",
  "timezone_database_version": "<installed-version>",
  "evidence_root": "/tmp/spine-agent-first-success...."
}
```

No gateway sender or external destination is used. Preserve the printed evidence directory while reviewing the generated request and response JSON.

## Stable CLI Invocation Shape

CLI options precede command words. A request may come from a file:

```bash
"$SPINE_COMMAND" --db "$SPINE_DB" --input /absolute/path/request.json --pretty event create
```

Or from stdin:

```bash
"$SPINE_COMMAND" --db "$SPINE_DB" --pretty schedule create < /absolute/path/schedule-create-request.json
```

## Preferred Atomic Scheduling Path

Use `schedule.create` for a new event or task that must receive reminders. It is one transaction and one receipt: the item, optional recurrence, all initial policies, optional occurrence provenance, and optional bounded work either commit together or all roll back. It never sends and never creates a `side_effect_attempts` row.

Start from the checked-in executable event request:

```bash
cp "$SPINE_CHECKOUT/tests/fixtures/schedule_create/contracts/request_event_repeat_window_materialized.json" \
  "$SPINE_DEMO_ROOT/schedule-create-request.json"
```

Before invocation, replace its actor, recipient, and explicit `delivery_target_id` with active rows from this ledger. The request uses `timezone_database_version.kind=system_current`, so the command pins the executing runtime's exact local timezone-data version and returns that resolved version in its receipt. Then preview and commit using the same request:

```bash
"$SPINE_COMMAND" --db "$SPINE_DB" --input "$SPINE_DEMO_ROOT/schedule-create-request.json" \
  --dry-run --pretty schedule create
"$SPINE_COMMAND" --db "$SPINE_DB" --input "$SPINE_DEMO_ROOT/schedule-create-request.json" \
  --pretty schedule create
```

The example creates a two-hour countdown every 20 minutes and materializes six work rows. Require `effect=schedule_created`, `phases.delivery=not_attempted`, `materialization.work_instance_count=6`, and six returned work IDs. Repeating the committed request with the same `command_id` returns `effect=schedule_create_replay` and no new rows.

Read the committed schedule back without SQL:

```bash
export ITEM_ID=item-id-from-schedule-create
"$SPINE_COMMAND" --db "$SPINE_DB" \
  --item-id "$ITEM_ID" \
  --include policies,work,attempts \
  --pretty schedule show
```

The four lifecycle sections are independent: authored, opportunities, work, and delivery. Immediately after authoring, delivery remains `attempt_state=not_attempted`; after a worker runs, the same readback exposes attempts and terminal outcome evidence.

For chat-sized audit output, add `--compact` to either command. Full JSON remains the default:

```bash
"$SPINE_COMMAND" --db "$SPINE_DB" --input "$SPINE_DEMO_ROOT/schedule-create-request.json" \
  --compact schedule create
"$SPINE_COMMAND" --db "$SPINE_DB" --item-id "$ITEM_ID" --compact schedule show
```

For the common relative intent “event in two hours; every 30 minutes until it starts,” use the read-only `schedule.build` request defined in `specs/schedule-operator-tools.md`. Supply an explicit `reference_time_utc`, `event_delay_seconds=7200`, and `reminder_interval_seconds=1800`; inspect `effect=schedule_create_request_built`, then submit the returned `schedule_create_request` unchanged. The builder pins the executing timezone-data version and resolves any context-default delivery route to an explicit target before authoring.

For a request that uses `delivery.target.resolution=context_default`, bind the name explicitly in the CLI context:

```bash
"$SPINE_COMMAND" --db "$SPINE_DB" \
  --delivery-target-default owner_whatsapp=delivery_target_owner_whatsapp \
  --input /absolute/path/context-default-schedule-request.json \
  --pretty schedule create
```

The option only resolves an existing active route. It cannot create, approve, reactivate, or authorize sending through that route. Zero or multiple values for the requested default key fail closed.

A separate read request can also come from stdin; for example:

```bash
"$SPINE_COMMAND" --db "$SPINE_DB" --input - --pretty item occurrences <<JSON
{
  "item_id": "<item-id>",
  "range_start": "2035-01-01T00:00:00",
  "range_end": "2035-01-12T00:00:00",
  "range_basis": "original_schedule",
  "limit": "100",
  "include_diagnostics": true
}
JSON
```

For `reminder.create` with `channel=whatsapp`, include the local binding switch before the command words:

```bash
"$SPINE_COMMAND" --db "$SPINE_DB" --input - --pretty --openclaw-whatsapp reminder create
```

That switch validates authoring context only. It does not send.

## Canonical Scheduling Command Order

For a recurring item with recurrence-bound notifications, use this order:

1. `subject.upsert`
2. `delivery_target.upsert`
3. `event.create` or `task.create` with a structured recurrence set
4. `item.occurrences` to inspect current virtual occurrences and capture recurrence identities
5. `reminder.create` with `application_scope=each_occurrence` or `selected_occurrence`
6. `occurrence_provenance.regenerate` for `consumer=notification_schedule`
7. `notification.opportunities`
8. `notification_work.materialize`
9. `"$SPINE_WORKER" --mode observe_only ... --max-cycles 1`
10. `"$SPINE_WORKER" --mode active --openclaw-sender fake ... --max-cycles 1`

Do not reverse steps 6 and 7. Recurrence-bound opportunity expansion reads current active provenance; without it, no recurrence targets authorize opportunities.

Every successful item-version mutation returns `current_version`. Use that exact value as the next write's `target_version`. After a recurrence mutation, call `item.occurrences` again and use the returned current `recurrence_revision_id`; occurrence keys and provenance are revision-bound.

Capture these response facts rather than reconstructing them:

| Response | Facts needed by the next operation |
|---|---|
| `event.create` or `task.create` | `item_id`, `current_version` |
| `item.occurrences` | `recurrence_set_id`, `recurrence_revision_id`, `occurrences[].occurrence_key` |
| `reminder.create` | new `current_version`, `notification_intent_id`, `notification_policy_id` |
| `occurrence_provenance.regenerate` | `effect`, `selected_count`, unresolved or closed report facts |
| `notification.opportunities` | `notification_opportunity_id`, `eligible_at_utc`, `actionable`, `next_cursor` |
| `notification_work.materialize` | `effect`, created/retained/cancelled work-instance IDs |

The executable example captures these with `jq` and stops when any expected count or success fact is missing.

## Public Command Map

| Purpose | Command | Writes? | External send? |
|---|---|---:|---:|
| Inspect local authority | `system.info` | No | No |
| Verify one complete schedule lifecycle | `schedule.show` | No | No |
| Read a bounded cross-item agenda | `agenda.show` | No | No |
| Bootstrap/update actor | `subject.upsert` | Yes | No |
| Create/update delivery endpoint | `delivery_target.upsert` | Yes | No |
| Atomically create scheduled item + reminders | `schedule.create` | Yes | No |
| Atomically update schedule truth and reconcile work | `schedule.update` | Yes | No |
| Cancel a schedule and never-started work | `schedule.cancel` | Yes | No |
| Author recurring event | `event.create` | Yes | No |
| Attach recurrence to non-recurring event | `event.reschedule` | Yes | No |
| Author recurring task | `task.create` | Yes | No |
| Expand occurrences | `item.occurrences` | No | No |
| Add one occurrence | `recurrence.instance.add` | Yes | No |
| Remove one occurrence | `recurrence.instance.remove` | Yes | No |
| Move/change one occurrence | `recurrence.instance.override` | Yes | No |
| Edit one/following/whole series | `recurrence.series.edit` | Yes | No |
| Refresh occurrence authorization | `occurrence_provenance.regenerate` | Yes | No |
| Author notification policy | `reminder.create` | Yes | No |
| Revise notification policy | `reminder.edit` | Yes | No |
| Disable notification policy | `reminder.disable` | Yes | No |
| Expand virtual opportunities | `notification.opportunities` | No | No |
| Persist actionable work | `notification_work.materialize` | Yes | No |

The complete command catalog, including ordinary item and relation commands, is normative in `specs/agent-command-contract.md`.

## Evidence and Source Map

Use these in order when more detail is needed:

1. `docs/AGENT_OPERATOR_GUIDE.md` — operations, migration, worker modes, inspection, and troubleshooting.
2. `specs/agent-command-contract.md` — exact public command behavior and errors.
3. `specs/schedule-create.md`, `specs/schedule-show.md`, `specs/schedule-operations.md`, `specs/recurrence.md`, and `specs/notifications.md` — atomic orchestration, readback, operational lifecycle, scheduling semantics, and identity.
4. `contracts/schemas/schedule-*.schema.json`, `contracts/schemas/recurrence-*.schema.json`, and `contracts/schemas/notification-*.schema.json` — machine-readable shapes.
5. `tests/fixtures/schedule_create/contracts/`, `tests/fixtures/schedule_operations/contracts/`, `tests/fixtures/recurrence/contracts/`, and `tests/fixtures/notifications/contracts/` — copyable structural examples.
6. `tests/fixtures/recurrence/vectors/` and `tests/fixtures/notifications/vectors/` — computed identity and expansion evidence.

Never infer a write from the relational schema. Use public commands and verify the structured response plus ledger readback.

## Handoff Checklist

An agent is ready to operate when it can truthfully report all of the following:

- the ledger verifies at schema 7;
- `system.info` reports matching implemented and actual schema versions;
- it used the locally reported timezone-data version for local schedules;
- it can explain recurrence cadence versus notification cadence versus retry;
- it can author and expand a recurring item;
- it regenerates provenance before recurrence-bound opportunity expansion;
- it can materialize work without claiming that materialization sent anything;
- observe-only produced no attempt and no fake-send evidence;
- bounded active fake mode produced a durable `side_effect_attempts` row;
- it knows that gateway mode requires separate explicit approval.
