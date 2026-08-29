# OpenClaw Deployment Runbook

Status: operational draft  
Scope: OpenClaw reminder delivery through the Spine worker

This runbook covers the first production-shaped Spine path: generated reminder work processed by Tickerd and delivered through the OpenClaw gateway adapter. It is intentionally narrower than the full Spine product surface.

## Goal

Use Spine as the durable coordination ledger and OpenClaw message runner for reminder work.

The rollout target is:

- Spine owns item, work, attempt, and outcome truth.
- Tickerd owns foreground runtime cadence, health, file lock, and cycle records.
- OpenClaw owns external message transport.
- The existing reminder runner remains available as rollback until Spine has proven stable in production operation.

## Host Prerequisites

On the deployment host:

- `git`
- Python 3.12+
- Spine checkout
- Tickerd checkout or installed Tickerd package
- OpenClaw CLI only for real gateway sends
- SQLite CLI for operator readbacks

Bind the host-selected checkout and its local entrypoints. No checked-in path is authoritative for a deployment:

```bash
export SPINE_CHECKOUT=/absolute/path/to/spine
export EXPECTED_SPINE_REVISION=approved-commit-or-tag
export SPINE_PYTHON="$SPINE_CHECKOUT/.venv/bin/python"
export SPINE_COMMAND="$SPINE_CHECKOUT/.venv/bin/spine-command"
export SPINE_MIGRATE="$SPINE_CHECKOUT/.venv/bin/spine-ledger-migrate"
export SPINE_SEED_DEMO="$SPINE_CHECKOUT/.venv/bin/spine-seed-demo"
export SPINE_SEED_CANARY="$SPINE_CHECKOUT/.venv/bin/spine-seed-canary"
export SPINE_WORKER="$SPINE_CHECKOUT/.venv/bin/spine-worker"
export SPINE_OPENCLAW_SMOKE="$SPINE_CHECKOUT/.venv/bin/spine-openclaw-smoke"
export SPINE_TICKERD_RUNNER="$SPINE_CHECKOUT/.venv/bin/spine-tickerd-runner"
```

Update only a clean checkout, then refresh that checkout's virtual environment:

```bash
git -C "$SPINE_CHECKOUT" status --short
git -C "$SPINE_CHECKOUT" pull --ff-only
test -x "$SPINE_PYTHON" || python3 -m venv "$SPINE_CHECKOUT/.venv"
"$SPINE_PYTHON" -m pip install -e "$SPINE_CHECKOUT[dev,test]"
test "$(git -C "$SPINE_CHECKOUT" rev-parse HEAD)" = \
  "$(git -C "$SPINE_CHECKOUT" rev-parse "$EXPECTED_SPINE_REVISION^{commit}")"
```

If the initial status output is non-empty, stop instead of mixing deployment changes with local work. `EXPECTED_SPINE_REVISION` is release input supplied outside the repository; the equality check fails a pull of the wrong branch or tracking target. Keep the deployment-specific service stopped until installation, schema, and fake-path verification complete.

Install the audited Tickerd checkout into the Spine environment. A source-only
`PYTHONPATH` binding is not accepted by runtime admission:

```bash
export TICKERD_CHECKOUT=/path/to/audited/tickerd
"$SPINE_PYTHON" -m pip install --no-deps "$TICKERD_CHECKOUT"
```

## Filesystem Layout

Recommended production-shaped paths:

```text
SPINE_CHECKOUT=/opt/spine
TICKERD_CHECKOUT=/opt/tickerd
SPINE_DB=/var/lib/spine/ledger.sqlite
SPINE_STATE_DIR=/var/lib/spine/worker
```

For non-root trials, use an operator-owned equivalent:

```text
SPINE_CHECKOUT=$HOME/spine
TICKERD_CHECKOUT=$HOME/tickerd
SPINE_DB=$HOME/.spine/ledger.sqlite
SPINE_STATE_DIR=$HOME/.spine/worker
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
cd "$SPINE_CHECKOUT"
"$SPINE_PYTHON" -m unittest discover -s tests
"$SPINE_CHECKOUT/.venv/bin/ruff" check src/spine/core src/spine/ledger
"$SPINE_CHECKOUT/.venv/bin/mypy" --strict src/spine/core src/spine/ledger
```

Run the installed-script smoke help checks:

```bash
"$SPINE_MIGRATE" --help
"$SPINE_SEED_CANARY" --help
"$SPINE_SEED_DEMO" --help
"$SPINE_WORKER" --help
"$SPINE_OPENCLAW_SMOKE" --help
"$SPINE_TICKERD_RUNNER" --help
```

## Schema Migration

For a new ledger:

```bash
"$SPINE_MIGRATE" \
  --db "$SPINE_DB" \
  --initialize-if-empty
```

For an existing ledger:

```bash
"$SPINE_MIGRATE" \
  --db "$SPINE_DB"
```

For verification only:

```bash
"$SPINE_MIGRATE" \
  --db "$SPINE_DB" \
  --verify-only
```

`--verify-only` is a deliberate deep-ledger operation. It performs full SQLite integrity and foreign-key checks plus unscoped Spine ledger-invariant validation, so its runtime may grow with ledger size and a cold filesystem cache. Run it during a controlled migration, deployment verification window, or storage-incident investigation, not on every interactive command, worker heartbeat, or routine scheduler restart. The bounded-runtime-preflight amendment requires ordinary `spine-command` and worker startup to use a separate structural check, but deployment automation MUST verify that the selected release implements that amendment before relying on bounded startup latency.

The current runtime requires ledger schema version 11. Run the normal migration command and explicit deep verification during initialization, schema-changing deployment, or a scheduled verification window, then require `system.info` to report schema 12 before starting the updated worker. A routine restart of an unchanged, already admitted schema MUST NOT acquire a new implicit deep-verification dependency. Do not run a current worker against an older ledger or an older worker against a migrated ledger.

```bash
"$SPINE_MIGRATE" --db "$SPINE_DB" --verify-only
"$SPINE_COMMAND" --db "$SPINE_DB" --pretty system info
```

Require equal implemented and actual schema versions. If this deployment will use atomic scheduling, also require `spine.schedule-create.v2`, `spine.schedule-create-normalization.v1`, `spine.schedule-create-response.v2`, `spine.schedule-create-receipt.v2`, and the item-archetype and notification-profile contract families before accepting authoring traffic.

For persistent-ledger visibility checks, seed the deterministic demo row only when it is absent:

```bash
"$SPINE_SEED_DEMO" --if-absent "$SPINE_DB"
```

Without `--if-absent`, the seed-demo command refuses existing database paths.

For real gateway canary preparation, seed a controlled reminder and inspect the predicted OpenClaw envelope before any active/gateway run:

```bash
"$SPINE_SEED_CANARY" "$SPINE_DB" \
  --prefix operator-canary \
  --target-ref "<openclaw-target>" \
  --title "Spine canary reminder" \
  --openclaw-channel whatsapp \
  --if-absent
```

The command returns `predicted_openclaw_envelope`, including `channel_hint`, `target_ref`, `body_text`, `dedupe_key`, and the expected first `attempt_id`.

## Fake OpenClaw Smoke

Use fake mode before any real gateway send. This performs active Spine/Tickerd processing but writes only fake send evidence.

```bash
"$SPINE_OPENCLAW_SMOKE" \
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
"$SPINE_WORKER" \
  --db "$SPINE_DB" \
  --state-dir "$SPINE_STATE_DIR" \
  --mode observe_only \
  --bindings openclaw \
  --openclaw-sender fake \
  --max-cycles 1 \
  --trace-id spine-worker-observe
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
- explicit `--openclaw-channel whatsapp` or another known gateway-supported channel
- explicit `--openclaw-sender gateway`
- explicit `--allow-real-send`
- operator-selected test ledger/work item

Environment variables:

```bash
export SPINE_OPENCLAW_GATEWAY_URL="<gateway-url>"
export SPINE_OPENCLAW_CHANNEL=whatsapp
export SPINE_OPENCLAW_GATEWAY_TIMEOUT_MS=10000
export SPINE_OPENCLAW_COMMAND_TIMEOUT_MS=15000
export SPINE_OPENCLAW_RETRY_DELAY_SECONDS=300
```

`SPINE_OPENCLAW_GATEWAY_TIMEOUT_MS` is passed to `openclaw gateway call send --timeout`.
`SPINE_OPENCLAW_COMMAND_TIMEOUT_MS` wraps the local OpenClaw CLI subprocess and must remain
larger than the gateway timeout. If it is omitted or set too low, Spine uses gateway timeout plus
5000 ms of process headroom. A subprocess timeout records `openclaw_gateway_cli_timeout`; gateway
or provider-side timeout failures are normalized separately from CLI wrapper expiry.

Set exactly one gateway credential in the protected env file:

- `SPINE_OPENCLAW_GATEWAY_TOKEN`
- `SPINE_OPENCLAW_GATEWAY_PASSWORD`

Bounded gateway smoke:

```bash
"$SPINE_WORKER" \
  --db "$SPINE_DB" \
  --state-dir "$SPINE_STATE_DIR" \
  --mode active \
  --bindings openclaw \
  --openclaw-channel whatsapp \
  --openclaw-sender gateway \
  --allow-real-send \
  --max-cycles 1 \
  --trace-id spine-worker-gateway-trial
```

Do not run gateway mode against production reminder work until the target work row, recipient, message body, and idempotency key have been inspected.

If an operator confirms that OpenClaw delivered a message but Spine recorded the attempt as
`openclaw_gateway_cli_timeout`, do not rerun the active worker against that same work item until
the already-delivered attempt is reconciled or the staging DB is reset. The work may still be
eligible for retry, and rerunning it can duplicate the external WhatsApp send.

## Long-Running Runner

The long-running command shape is:

```bash
"$SPINE_WORKER" \
  --db "$SPINE_DB" \
  --state-dir "$SPINE_STATE_DIR" \
  --mode active \
  --bindings openclaw \
  --openclaw-channel whatsapp \
  --openclaw-sender gateway \
  --allow-real-send \
  --trace-id spine-worker
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

Rollback means stopping Spine as the OpenClaw runner and returning reminder execution to the prior production reminder path.

Immediate rollback steps:

1. Stop the Spine runner process or supervisor unit.
2. Confirm `health.json` moves to `DOWN` or the process is absent.
3. Leave the Spine SQLite ledger intact for audit.
4. Restart or re-enable the prior production reminder path.
5. Record the final Spine `events.jsonl` tail and recent `side_effect_attempts` rows.

Do not delete the Spine ledger during rollback. It is the record of what Spine attempted before rollback.

## Cutover Checklist

Before production cutover:

- CI is passing on `main`.
- Deployment host has pulled the intended commit.
- The target ledger has a successful explicit deep verification appropriate to the deployment or incident window; routine restarts do not silently rerun it.
- Fake OpenClaw smoke passes on host.
- Observe-only runner pass is understood.
- Gateway credentials are configured outside git.
- A single bounded real gateway trial succeeds.
- Operator readbacks show expected work and attempt rows.
- Prior-runner rollback command/path is known.
- The first active production run has an explicit operator watching health, events, work rows, and attempt rows.

## Deployment Templates

The repository includes deployment templates:

- `deploy/env/worker.env.example`
- `deploy/systemd/spine-worker.service`

The systemd template defaults to `observe_only` with the OpenClaw fake sender binding. Edit the `ExecStart` line only after observe-only and fake active trials have passed.
