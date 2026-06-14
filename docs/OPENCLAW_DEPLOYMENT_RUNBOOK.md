# OpenClaw Deployment Runbook

Status: operational draft  
Scope: narrow Kinflow replacement path for OpenClaw reminder delivery

This runbook covers the first production-shaped Spine path: generated reminder work processed by Tickerd and delivered through the OpenClaw gateway adapter. It is intentionally narrower than the full Spine product surface.

## Goal

Use Spine as the durable coordination ledger and OpenClaw message runner for reminder work that currently flows through Kinflow.

The rollout target is:

- Spine owns item, work, attempt, and outcome truth.
- Tickerd owns foreground runtime cadence, health, file lock, and cycle records.
- OpenClaw owns external message transport.
- Kinflow remains available as rollback until Spine has proven stable in production-like operation.

## Host Prerequisites

On the deployment host:

- `git`
- Python 3.12+
- Spine checkout
- Tickerd checkout or installed Tickerd package
- OpenClaw CLI only for real gateway sends
- SQLite CLI for operator readbacks

Install or refresh Spine from the repository root:

```bash
git pull --ff-only
python3 -m pip install -e ".[dev,test]"
```

If Tickerd is not installed as a package, export its source directory for runtime commands:

```bash
export TICKERD_SRC=/path/to/tickerd/src
```

## Filesystem Layout

Recommended production-shaped paths:

```text
SPINE_DB=/var/lib/spine/ledger.sqlite
SPINE_STATE_DIR=/var/lib/spine/openclaw-runner
```

For non-root trials, use an operator-owned equivalent:

```text
SPINE_DB=$HOME/.spine/ledger.sqlite
SPINE_STATE_DIR=$HOME/.spine/openclaw-runner
```

The state directory contains operational runtime files:

- `tickerd.lock`
- `owner.json`
- `health.json`
- `events.jsonl`
- `openclaw_sends.jsonl` for fake OpenClaw smokes only

The database file is the canonical ledger. Back it up before migration or active send trials.

## Install Verification

Run the local suite after pulling changes:

```bash
python3 -m unittest discover -s tests
ruff check src/spine/core src/spine/ledger
mypy --strict src/spine/core src/spine/ledger
```

Run the installed-script smoke help checks:

```bash
spine-ledger-migrate --help
spine-seed-demo --help
PYTHONPATH="$TICKERD_SRC" spine-openclaw-runner --help
PYTHONPATH="$TICKERD_SRC" spine-openclaw-smoke --help
PYTHONPATH="$TICKERD_SRC" spine-tickerd-runner --help
```

## Schema Migration

For a new ledger:

```bash
spine-ledger-migrate \
  --db "$SPINE_DB" \
  --initialize-if-empty
```

For an existing ledger:

```bash
spine-ledger-migrate \
  --db "$SPINE_DB"
```

For verification only:

```bash
spine-ledger-migrate \
  --db "$SPINE_DB" \
  --verify-only
```

## Fake OpenClaw Smoke

Use fake mode before any real gateway send. This performs active Spine/Tickerd processing but writes only fake send evidence.

```bash
PYTHONPATH="$TICKERD_SRC" spine-openclaw-smoke \
  --db /tmp/spine-openclaw-smoke.sqlite \
  --state-dir /tmp/spine-openclaw-state \
  --seed-demo \
  --max-cycles 1
```

Expected summary shape:

```json
{
  "cycles_completed": 1,
  "exit_code": 0,
  "fake_result": "delivered",
  "reason": "max_cycles_reached",
  "sender": "fake"
}
```

Expected readback:

```bash
cat /tmp/spine-openclaw-state/health.json
tail -n 20 /tmp/spine-openclaw-state/events.jsonl
cat /tmp/spine-openclaw-state/openclaw_sends.jsonl

sqlite3 /tmp/spine-openclaw-smoke.sqlite "
SELECT work_instance_id, status, attempt_count, reason_code
FROM work_instances;

SELECT attempt_id, adapter_name, attempt_status, provider_ref, reason_code
FROM side_effect_attempts;
"
```

For a bounded smoke, `health.json` should end in `DOWN` with `last_failure_reason=max_cycles_reached`. That is expected because the process intentionally exits after one cycle.

The expected successful ledger terminal state is:

- one `work_instances` row with `status=succeeded`
- `attempt_count=1`
- `reason_code=openclaw_delivered`
- one `side_effect_attempts` row with `adapter_name=openclaw`
- `attempt_status=succeeded`
- provider reference recorded

## Observe-Only Runner

Use observe-only mode to verify runtime cadence and work visibility without side effects:

```bash
PYTHONPATH="$TICKERD_SRC" spine-openclaw-runner \
  --db "$SPINE_DB" \
  --state-dir "$SPINE_STATE_DIR" \
  --mode observe_only \
  --sender fake \
  --max-cycles 1 \
  --trace-id spine-openclaw-observe
```

Expected behavior:

- runtime starts and writes owner, health, and events files
- eligible current work may be scanned
- work is blocked with `SIDE_EFFECTS_BLOCKED`
- no OpenClaw gateway send occurs

## Real Gateway Trial

Real sends require all of the following:

- OpenClaw CLI installed on the host
- gateway target configured
- gateway credential configured
- explicit `--sender gateway`
- explicit `--allow-real-send`
- operator-selected test ledger/work item

Environment variables:

```bash
export SPINE_OPENCLAW_GATEWAY_URL="<gateway-url>"
export SPINE_OPENCLAW_GATEWAY_TIMEOUT_MS=10000
export SPINE_OPENCLAW_RETRY_DELAY_SECONDS=300
```

Set exactly one gateway credential in the protected env file:

- `SPINE_OPENCLAW_GATEWAY_TOKEN`
- `SPINE_OPENCLAW_GATEWAY_PASSWORD`

Kinflow gateway env names are accepted as migration fallback:

- `KINFLOW_GATEWAY_URL`
- `KINFLOW_GATEWAY_TOKEN`
- `KINFLOW_GATEWAY_PASSWORD`
- `KINFLOW_GATEWAY_TIMEOUT_MS`

Bounded gateway smoke:

```bash
PYTHONPATH="$TICKERD_SRC" spine-openclaw-runner \
  --db "$SPINE_DB" \
  --state-dir "$SPINE_STATE_DIR" \
  --mode active \
  --sender gateway \
  --allow-real-send \
  --max-cycles 1 \
  --trace-id spine-openclaw-gateway-trial
```

Do not run gateway mode against production reminder work until the target work row, recipient, message body, and idempotency key have been inspected.

## Long-Running Runner

The long-running command shape is:

```bash
PYTHONPATH="$TICKERD_SRC" spine-openclaw-runner \
  --db "$SPINE_DB" \
  --state-dir "$SPINE_STATE_DIR" \
  --mode active \
  --sender gateway \
  --allow-real-send \
  --trace-id spine-openclaw-runner
```

At the current stage, prefer a supervised shell/session trial before creating a service unit. Once the command is stable, a process supervisor should own restart policy, logs, environment loading, and host boot behavior.

## Operational Readbacks

Health:

```bash
cat "$SPINE_STATE_DIR/health.json"
cat "$SPINE_STATE_DIR/owner.json"
tail -n 50 "$SPINE_STATE_DIR/events.jsonl"
```

Recent work:

```bash
sqlite3 "$SPINE_DB" "
SELECT work_instance_id, item_id, item_version, work_kind, status,
       attempt_count, eligible_at_utc, next_attempt_at_utc, reason_code
FROM work_instances
ORDER BY updated_at_utc DESC, work_instance_id DESC
LIMIT 20;
"
```

Recent OpenClaw attempts:

```bash
sqlite3 "$SPINE_DB" "
SELECT attempt_id, work_instance_id, adapter_name, attempt_status,
       provider_ref, reason_code, attempted_at_utc, completed_at_utc
FROM side_effect_attempts
WHERE adapter_name = 'openclaw'
ORDER BY attempted_at_utc DESC, attempt_id DESC
LIMIT 20;
"
```

Failed or retryable work:

```bash
sqlite3 "$SPINE_DB" "
SELECT work_instance_id, status, attempt_count, next_attempt_at_utc, reason_code
FROM work_instances
WHERE status IN ('eligible', 'in_progress', 'failed')
ORDER BY eligible_at_utc, work_instance_id;
"
```

## Rollback

Rollback means stopping Spine as the OpenClaw runner and returning reminder execution to Kinflow.

Immediate rollback steps:

1. Stop the Spine runner process or supervisor unit.
2. Confirm `health.json` moves to `DOWN` or the process is absent.
3. Leave the Spine SQLite ledger intact for audit.
4. Restart or re-enable the Kinflow production path.
5. Record the final Spine `events.jsonl` tail and recent `side_effect_attempts` rows.

Do not delete the Spine ledger during rollback. It is the record of what Spine attempted before rollback.

## Cutover Checklist

Before production cutover:

- CI is passing on `main`.
- Deployment host has pulled the intended commit.
- `spine-ledger-migrate --verify-only` passes on the target ledger.
- Fake OpenClaw smoke passes on host.
- Observe-only runner pass is understood.
- Gateway credentials are configured outside git.
- A single bounded real gateway trial succeeds.
- Operator readbacks show expected work and attempt rows.
- Kinflow rollback command/path is known.
- The first active production run has an explicit operator watching health, events, work rows, and attempt rows.

## Deployment Templates

The repository includes deployment templates:

- `deploy/env/openclaw-runner.env.example`
- `deploy/systemd/spine-openclaw-runner.service`

The systemd template defaults to `observe_only` with the fake sender. Edit the `ExecStart` line only after observe-only and fake active trials have passed.
