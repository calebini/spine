# One synthetic provider trial through Spine

Prepared 2026-11-04 for SPINE-070. This is an offline preparation and proposed
invocation, not permission to execute it. Current task status and verification
are in [the backlog](BACKLOG.md#spine-070--prepare-one-synthetic-real-provider-capture-trial).

**Execution follow-up:** The operator subsequently approved this single trial.
SPINE-071 completed with successful no_addition, retained credential-free readback
and a documented observation-precision limitation; see the
[trial review](CONTEXTUAL_NOTIFICATION_SINGLE_TRIAL_REVIEW.md). That one invocation
authorization is fulfilled. The preparation recipe below is retained as history,
not permission for another provider call.
The [implemented contract](../specs/contextual-notification-live-capture.md),
[operations](CONTEXTUAL_NOTIFICATION_LIVE_CAPTURE.md) and original
[handoff note](CONTEXTUAL_NOTIFICATION_LIVE_CAPTURE_HANDOFF.md) define the boundary.

## Pinned inputs and proposed configuration

| Input | Selected value |
| --- | --- |
| Spine checkpoint | `1f7947d0e9894729ecd1d3cf46faf9a81fdb3595` (SPINE-069) |
| Impetus checkpoint | `5ff3c0c4530fe07e81cc9067eddadd967a90acc4` |
| Interface / version | `contextual-notification-experiment` / `impetus.openai.v1` |
| Complete owner/source/package schema SHA-256 | `bf3d132392c41ab21e9f7bf44f765aa79799a8dd41f8666d1d39ad646c442c4b` |
| Capture contract / sidecar format | `spine.contextual-notification-live-capture.v1` / 2 |
| Prompt revision | `helpful-personable-openai.v1` |
| Candidate raw file SHA-256 | `6e93379ed73a5dafccafdd7286e6aed126203eb01ee466c1b6ffa051bdaba2be` |
| Insertion-order configuration revision | `openai.responses.v1:88ad7139cd591f01ceb017b46b491525554aa377be257aa2c64434dd6cdb8e12` |

Carry forward the owner's
[candidate artifact](../../impetus/examples/openai-gpt-6-luna.candidate.json),
byte-identical to its checkpoint. This is a real-model candidate, distinct from
Spine's fictional contract test configuration. Its exact JSON is:

```json
{
  "model": "gpt-6-luna",
  "model_binding": "documented_alias",
  "reasoning_effort": "low",
  "max_output_tokens": 512,
  "input_token_upper_bound": 8192,
  "input_nanodollars_per_million": 400000000,
  "output_nanodollars_per_million": 600000000,
  "qualification_reference": "docs/first-synthetic-live-call.md#execution-status",
  "token_counting": {
    "charge_bound_nanodollars": 1000000
  }
}
```

The owner's [preparation](../../impetus/docs/first-synthetic-live-call.md) records
official model/tariff inspection on **2026-10-30**. Its locally edited
[trial review](../../impetus/docs/first-synthetic-live-call-review.md) reports one
direct successful no-addition result with matching count/generation input tokens.
Those documents are supplied owner evidence; this preparation did not inspect
the prior trial's private stores or credentials. They do not qualify a new Spine
invocation, today's model availability, current account terms or final billing.
No documentation network access was used to refresh that dated evidence.

The mutable model alias and counting contingency need explicit acceptance.
Before execution, confirm the selected account's model access, data terms and
applicable all-in generation/counting charges fit this configuration, or select
a revised candidate and recompute/review its bindings offline. The qualification
reference is provenance, not an automatically verified tariff guarantee. Do not
claim current qualification from the presence of that string.

## Exposure, timing and synthetic disclosure

| Bound | Proposed trial |
| --- | --- |
| Provider operations | At most one count, followed by at most one generation; zero retries/tools |
| Input admission ceiling | 8,192 tokens, checked by provider count before generation |
| Output ceiling | 512 tokens, including reasoning |
| Accounting rates | USD 0.40 input / USD 0.60 output per million tokens |
| Generation reservation | 3,584,000 nanodollars = USD 0.003584 |
| Unknown counting contingency | 1,000,000 nanodollars = USD 0.001; retained after successful count |
| Total original admitted exposure | **4,584,000 nanodollars = USD 0.004584** |
| Owner ceilings | USD 0.02/run; 20 new runs and USD 0.40 new exposure/UTC day per owner store |
| Execution allowance | 20 seconds total; count at most 5 seconds; at least 1 second remains before generation |
| Launcher timeout | 35 seconds; timeout never permits another invoke |
| Source cutoff / expiry | Synthetic initialization time T0 + 120 seconds |
| Event time | T0 + 3,720 seconds; one-hour ordinary reminder |
| Proposed prelaunch check | More than 30 seconds remain before cutoff |
| Addendum size / disposition | At most 512 UTF-8 bytes; selected=false, sent=false |

Arithmetic: `8192 * 400 + 512 * 600 = 3,584,000` nanodollars, plus
the 1,000,000 counting contingency. This is the maximum **local admission** for
this candidate, conditional on the charge assumptions. It is not a hard upstream
billing cap; timeouts do not guarantee upstream cancellation. Usage and remaining
reserves are retained separately. Do not add original authorization to usage plus
remaining reserves, or interpret unknown usage/counting charges as zero. No fresh
state may be used to evade an existing budget or retry an attempted opportunity.

The fresh source has title `Synthetic lesson`, archetype `lesson`, timezone UTC,
no disclosed facets, and the ordinary reminder rendered by Spine. The seed's
summary, delivery target and recipient remain outside the export. The fixed
objective is the implemented context-only-compatible objective; despite its
generic mention of optional tools, `allowed_tools=[]` and `tool_calls=0` prohibit
them. Impetus sends only the permitted context/objective under its pinned system
instructions and strict response schema, not the full source ledger or credentials.
Counting also discloses that input. `store=false` is not a provider-wide retention
guarantee. No real event or recipient is used, and no notification worker is run.

## Proposed executable recipe

Use the existing Spine interpreter as an interpreter for the independent Impetus
subprocess, with only the sibling's `src` on its PYTHONPATH. No installation or
Impetus source modification is needed. Run from the Spine repository root.
Save the following single Python block to an operator-owned `trial_driver.py`
outside both checkouts. Set `TRIAL_DRIVER` to that non-secret script path and
`TRIAL_ROOT` to a **new absolute directory outside both checkouts** whose parent
already exists. Neither variable is a credential locator. Do not put runtime
files in Git. The driver creates a 0700 root, synthetic `spine.sqlite3`, format-2
`capture.sqlite3`, independent `worker/state.sqlite3`, and non-secret evidence.

`prepare` is offline. The review specimen from preparation is never invoked.
After separate execution approval, prepare one new final directory just in time;
inspect its persisted `request.json`, `binding.json` and `preparation.json`, then
invoke only that export. Random ledger/item/opportunity IDs and UTC timestamps
necessarily differ from the review specimen. The approved fixed input and relative
timing stay the same; persist the final exact bytes/digest before any provider I/O.
Never edit the specimen into a new request or refresh an attempted opportunity.

```python
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from spine.adapters.contextual_experiment import Source, dump, require
from spine.adapters.contextual_live import LiveCaptureStore, LiveLauncher
from spine.ledger import connect
from spine.runtime.contextual_live_capture import initialize
from spine.services.contextual_experiment import instant, utc
from spine.services.contextual_live import LiveExperiment, configuration_binding

ROOT = Path.cwd().resolve()
OWNER = ROOT.parent / "impetus"
CHECKPOINT = "5ff3c0c4530fe07e81cc9067eddadd967a90acc4"
CANDIDATE_SHA = "6e93379ed73a5dafccafdd7286e6aed126203eb01ee466c1b6ffa051bdaba2be"
REVISION = "openai.responses.v1:88ad7139cd591f01ceb017b46b491525554aa377be257aa2c64434dd6cdb8e12"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, raw):
    with path.open("xb") as stream:
        os.chmod(path, 0o600)
        stream.write(raw)


def save_json(path, value):
    save(path, dump(value) + b"\n")


def source_hash(ledger):
    return sha("\n".join(ledger.iterdump()).encode())


def worker_command(trial):
    return [str(ROOT / ".venv/bin/python"), "-m", "impetus", "--state", str(trial / "worker")]


def worker_environment():
    return {"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(OWNER / "src")}


def prepare(trial):
    spine_head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).decode().strip()
    require(spine_head == "1f7947d0e9894729ecd1d3cf46faf9a81fdb3595", "spine_checkpoint")
    subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", "HEAD", "--",
                    "src", "contracts", "pyproject.toml"], check=True)
    head = subprocess.check_output(["git", "-C", str(OWNER), "rev-parse", "HEAD"]).decode().strip()
    require(head == CHECKPOINT, "owner_checkpoint")
    subprocess.run(["git", "-C", str(OWNER), "diff", "--quiet", "HEAD", "--", "src"], check=True)
    raw = (OWNER / "examples/openai-gpt-6-luna.candidate.json").read_bytes()
    require(sha(raw) == CANDIDATE_SHA, "candidate_bytes")
    require(configuration_binding(raw.decode())["configuration_revision"] == REVISION, "candidate_revision")
    now = datetime.now(UTC).replace(microsecond=0)
    ledger, work, config, store = initialize(trial, now, raw.decode())
    try:
        source = Source(ledger)
        save(trial / "provider.json", raw)
        os.chmod(trial / "provider.json", 0o400)
        launcher = LiveLauncher(worker_command(trial), environment=worker_environment())
        experiment = LiveExperiment(source, store, launcher, config)
        opportunity, exported = experiment.export(work)
        save(trial / "request.json", exported["request"])
        save_json(trial / "binding.json", exported["binding"])
        request = json.loads(exported["request"])
        read = dict(interface=request["interface"], version=request["version"],
                    ledger_instance_id=source.namespace, work_id=request["work_id"],
                    request_sha256=sha(exported["request"]))
        save_json(trial / "read.json", read)
        save_json(trial / "preparation.json", dict(
            initialized_at_utc=utc(now), namespace=source.namespace, opportunity=opportunity,
            source_config=config, source_sha256=source_hash(ledger), request_sha256=read["request_sha256"]))
        result = subprocess.run([*worker_command(trial), "init", "--namespace", source.namespace],
                                env=worker_environment(), check=True, capture_output=True)
        save(trial / "worker-init.json", result.stdout)
        require(not store.get(opportunity)["launched"], "unexpected_marker")
        require(ledger.execute("SELECT count(*) FROM side_effect_attempts").fetchone()[0] == 0, "unexpected_attempt")
    finally:
        store.close()
        ledger.close()


def observe(trial, operation):
    meta = json.loads((trial / "preparation.json").read_bytes())
    require((trial / "spine.sqlite3").is_file(), "missing_source")
    ledger = connect(trial / "spine.sqlite3")
    ledger.execute("PRAGMA query_only=ON")
    source = Source(ledger)
    store = LiveCaptureStore(trial / "capture.sqlite3", source.namespace)
    try:
        require(source.namespace == meta["namespace"], "namespace")
        opportunity = meta["opportunity"]
        exported = store.get(opportunity)
        require(exported is not None and sha(exported["request"]) == meta["request_sha256"], "original_bytes")
        require(source_hash(ledger) == meta["source_sha256"], "source_changed")
        env = worker_environment()
        entering = operation == "invoke" and not exported["launched"]
        if entering:
            cutoff = json.loads(exported["request"])["selection_cutoff_utc"]
            require((instant(cutoff) - datetime.now(UTC)).total_seconds() > 30, "insufficient_window")
            # Only the separately authorized invocation may read this environment locator.
            # Never print it or include it in an evidence file.
            env["IMPETUS_OPENAI_API_KEY_FILE"] = os.environ["IMPETUS_OPENAI_API_KEY_FILE"]
        launcher = LiveLauncher(worker_command(trial), environment=env, enabled=entering,
                                provider_configuration_path=trial / "provider.json" if entering else None)
        experiment = LiveExperiment(source, store, launcher, meta["source_config"])
        record = experiment.run(opportunity) if operation == "invoke" else experiment.readback(opportunity)
        index = len(store.history(opportunity))
        save_json(trial / f"{operation}-{index:04d}-{os.urandom(4).hex()}.json", record)
        require(record["selected"] is False and record["sent"] is False, "capture_only")
        print(json.dumps(dict(reason=record["reason"], exchange=record["exchange"],
                              usable=record["usable_for_hypothetical_selection"])))
    finally:
        unchanged = source_hash(ledger) == meta["source_sha256"]
        attempts = ledger.execute("SELECT count(*) FROM side_effect_attempts").fetchone()[0]
        store.close()
        ledger.close()
        require(unchanged and attempts == 0, "source_or_attempt_changed")


if __name__ == "__main__":
    operation, directory = sys.argv[1:]
    require(operation in ("prepare", "invoke", "read"), "operation")
    trial = Path(directory)
    require(trial.is_absolute(), "absolute_trial_directory")
    trial = trial.resolve()
    require(not trial.is_relative_to(ROOT) and not trial.is_relative_to(OWNER), "external_trial_directory")
    os.umask(0o077)
    if operation == "prepare":
        prepare(trial)
    else:
        observe(trial, operation)
```

Offline preparation command (credentials excluded from parent and child):

```sh
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  "$PWD/.venv/bin/python" "$TRIAL_DRIVER" prepare "$TRIAL_ROOT"
```

**Proposed invocation, only after separate approval and account qualification:**
the trusted operator supplies the existing worker-owned credential file locator
in `IMPETUS_OPENAI_API_KEY_FILE` through the private execution environment.
Do not include its value in this document, a command transcript or chat. Run:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  "$PWD/.venv/bin/python" "$TRIAL_DRIVER" invoke "$TRIAL_ROOT"
```

For original entry, the launcher command is exactly the selected interpreter,
`-m impetus --state <trial>/worker --provider-config <trial>/provider.json
--enable-live invoke`, with the **stored request bytes** on stdin. The service
commits its launch marker first. There is no invocation from `prepare` or `read`.
The credential locator goes only into the worker invocation environment, not its
arguments, request, configuration or capture. Impetus alone opens the credential.
The parent recipe reads only its locator during approved original entry.

Credential-free retained readback, including after lost stdout or restart:

```sh
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  "$PWD/.venv/bin/python" "$TRIAL_DRIVER" read "$TRIAL_ROOT"
```

This calls `LiveExperiment.readback` and retains another capture. The child
command is `<python> -m impetus --state <trial>/worker read`, with the stored
version/namespace/work/digest envelope, no live/configuration flags or credential
environment. The source configuration JSON is retained in `preparation.json`;
readback does not open `provider.json`. If the original marker exists, even a
repeated `invoke` recipe follows only readback and does not load a credential locator.
Absent/unavailable state is unresolved evidence, not permission for new research.
If needed after confirmed worker exit, separately select the owner's `recover`
command without credentials/enablement; recovery never resumes provider work.
Do not clear the marker, edit requests, delete stores or invent replacement work.

## Offline review specimen

The prepared specimen and execution evidence are outside the checkout. The exact
request below is a review copy, not an invocation-ready request. Its stored digest
includes compact sorted JSON and the final newline; the pretty display does not.
Final execution uses a new source initialized after approval, with its own exact
persisted bytes and the same fixed input/relative timing.

Request SHA-256: `edbad5996dee8b1e69d523d55a90a037902990b405be9743a2497127dec9fe7e` (1603 bytes, including newline).

Canonical source dump SHA-256: `f2dff5b2e31f126830163c1df4ae15870a90015c3ec65af0b46d778275104b8d`.

Immutable service export fingerprint: `7cce6a5921d642f212848ead4257c3eca90446cad581cc2e7d915c24e58f9c5f`.

Source configuration SHA-256: `645fddbf5251b715d1c094b389b67d87e12e072c5a8b8acbf74ca5eb1791ea64`.

Disclosure SHA-256: `0d7d1ee570c345d2526518e35debdf6865e89faea3fa3111d1ce02232ed93f42`.

```json
{
  "allowed_tools": [],
  "captured_at_utc": "2026-11-03T23:44:56Z",
  "context": {
    "archetype": "lesson",
    "event": {
      "starts_at_utc": "2026-11-04T00:46:56Z",
      "timezone": "UTC",
      "title": "Synthetic lesson"
    },
    "facets": [],
    "notification": {
      "eligible_at_utc": "2026-11-03T23:46:56Z",
      "ordinary_text": "Reminder: Synthetic lesson in 1 hour",
      "seconds_before_event": 3600
    }
  },
  "interface": "contextual-notification-experiment",
  "limits": {
    "addendum_utf8_bytes": 512,
    "elapsed_seconds": 20,
    "model_calls": 1,
    "tool_calls": 0
  },
  "objective": "Make this reminder more helpful or more personable. Add a brief relevant line when worthwhile; avoid repetition, invented facts and inferred preferences. Use optional read-only tools only when useful. No addition is fine.",
  "request_expires_at_utc": "2026-11-03T23:46:56Z",
  "selection_cutoff_utc": "2026-11-03T23:46:56Z",
  "source_refs": {
    "disclosure_revision": "synthetic-context-only.v1",
    "experiment_definition_revision": "synthetic-helpful-personable.v1",
    "item_id": "item_373b7ce4173d1e60c9ad20700123e6c97b7a5879a4ccde6fc9e3c61c6f0da502",
    "item_version": 1,
    "ledger_instance_id": "ledger_instance_da32d476b951617acac431d0556cfb3fcd504ac94d104805cd56b93178a45d2c",
    "notification_opportunity_id": "notification_opportunity_68a0a94c50e47f358e479963edc2679ad8c3d2e8e43c41b74f227bb910fab658",
    "notification_policy_id": "notification_policy_2b835951f31a9c4342d54f21628cda3adba4b335a45ff74eb94eb861c791c08e",
    "rendering_definition_revision": "sha256:6e7596cef150adcf0ace4b222322b6a40c3679c371519c1f48f77e0183eba685"
  },
  "version": "impetus.openai.v1",
  "work_id": "experiment:53ca78c96663ce50feae89178b3c227e016bb1913d3aa2d07ded6396527d2750"
}
```

## Acceptance and evidence to retain

The owner adapter was also exercised offline with a forbidden transport and fake
key to construct the specimen's exact provider projections: generation body 1,385
bytes, SHA-256 `b6d5f319892c2a5737d5f96ef284ce2d693feed4e699e2aa95385c84921a813d`;
count body 1,307 bytes, SHA-256
`35aee561a47bf2efa0e0828b51b90ac5ac344ca3bc1d7543ba70cb0579d01b50`.
These local body bytes are retained outside Git. The count projection preserves
the generation input/schema/settings and excludes only the owner's documented
generation-only controls. Configuration revision and reservation match Spine
exactly. No provider operation was performed by this projection check.

1. Before original entry, retain request bytes/SHA-256, binding, original
   configuration bytes/encoding/revision, source/disclosure hashes, namespace,
   opportunity, cutoff and unchanged canonical-source dump digest. Worker namespace
   must match; launch marker changes only from zero to one. Review both checkouts
   for intervening runtime/contract changes before approving execution.
2. Retain the independent owner store plus Spine sidecar and invoke/read capture
   JSON. Capture JSON preserves parsed execution; it is not a byte-for-byte raw
   stdout transcript. Apply the complete schema and Spine consumer checks to each
   retained response. Require count ordinal 1 and generation ordinal 2 linked by
   exact generation request digest and count ordinal, correct config/prompt/model,
   token arithmetic, count/input equality, timing, usage and residual reserves.
3. `no_addition` or a context-only addendum with no sources is a valid successful
   result. For a usable success require current source/config and capture/completion
   before cutoff. This one sparse example establishes no general usefulness claim.
4. Failed/late/uncertain/invalid or missing output remains captured and unusable;
   retain known/unknown charges and marker. A count failure can validly mean zero
   generations. Schema-valid late observations must reference the actual generation
   at ordinal 2. Do not turn an unsuccessful qualification into another invocation.
5. Credential-free readback must preserve identity and original execution without
   changing operation count. Logical source data remains identical and
   `side_effect_attempts` stays zero. Every capture has selected=false/sent=false.

Stop after that one original invocation and readback. A successful trial would
qualify this specific synthetic through-Spine path only. Real reminders,
opt-in/disclosure, recurring sampling, generated delivery and broader live failure
campaigns remain separately selected work.

## Authorization requested during preparation

After resolving or explicitly bounding the account/tariff assumptions above,
approve one original invocation through Spine using this candidate revision:
**one provider count and, if admitted, one generation; gpt-6-luna/low; zero tools
and retries; USD 0.004584 local admitted exposure under the stated charge
assumptions; one fresh synthetic source and retained non-sending readback**.
Approval must include the two synthetic input disclosures and the acknowledged
mutable alias/counting contingency. It does not authorize another opportunity
after failure/uncertainty, credentials in evidence, real-ledger access, notification,
commit, push, deployment or feature activation. This preparation itself grants
none of that execution authority.
