# Run synthetic contextual notification capture

This is the isolated deterministic connected proof. It creates a real Spine ledger,
a Spine-owned experiment sidecar and a separate Impetus state directory. Public
Spine authoring commands create the synthetic event, archetype and reminder; export
uses the existing renderer. No gateway or provider is contacted and no attempt is
created. The rendered reminder in the capture is a preview at nominal notification time.

From the Spine checkout, use an interpreter with the Spine dependencies installed:

```sh
PYTHONPATH=src .venv/bin/python -m spine.runtime.contextual_experiment_demo \
  --directory /tmp/spine-contextual-demo-NEW \
  --impetus-python "$PWD/.venv/bin/python" \
  --impetus-source "$PWD/../impetus/src"
```

The directory must be new. Preserve it for review; it contains `spine.sqlite3`,
`capture.sqlite3` and `impetus/`. Do not replace/reset state to repeat real work.
The printed capture contains original binding, ordinary preview, execution and
proposal, source/currentness, timeliness and hypothetical usability. `selected` and
`sent` are false. The demo is a fixture, not an experiment scheduler or service.

The reusable Spine module `services.contextual_experiment.Experiment` provides
`export`, `run`, `readback` and `capture`. `Source` reads canonical facts;
`CaptureStore` owns sidecar transactions; `LocalImpetus` owns the configured subprocess.
Callers configure the opted-in synthetic items, permission for the full ordinary
text, selected primitive facet fields, definition/disclosure revisions, optional
fixture tool and bounded lead. For context-only, allowed_tools is empty. The operator
configures a worker scenario separately; request content cannot choose it.

Spine commits exact request bytes before invocation and commits one original-send
marker before spawning. If stdout is lost or either process exits, reopen the existing
sidecar and call run/readback for the original opportunity. They read the existing
worker claim and never invoke it a second time after the marker. If Impetus has an
unfinished claim, inspect it, explicitly run its `recover` operation when the original
worker is gone, then read again. No provider call is resumed. A crash between marker
and spawn may lose the opportunity; a missing read does not prove it is safe to send.

Run the connected proof and scoped reminder regressions:

```sh
IMPETUS_SRC="$PWD/../impetus/src" PYTHONPATH=src .venv/bin/python -m pytest -o addopts='' \
  tests/test_contextual_experiment.py tests/test_contextual_experiment_contract.py \
  tests/test_notification_rendering.py tests/test_schedule_create_command.py \
  tests/test_rendering_delivery.py -q
```

The connected tests require an independent Impetus checkout; they skip explicitly if
it is absent. They import no Impetus internals into Spine. The contract-only test
works without it. Tests use disposable synthetic ledgers, subprocesses and retained
readback; fault cases include an actual worker exit after durable possible entry.
Unknown/late/unusable work stays captured; it never delays or alters ordinary reminders.

Real-reminder opt-in/disclosure, live providers, production retention/restore,
resource limits and inclusion in delivered messages remain separate work. The
subprocess adapter assumes a trusted bounded fixture child; response size checks do
not qualify hostile streaming output. See [the adopted subset](../specs/contextual-notification-capture.md).

## Local verification record — 2026-10-29

The listed scoped pytest command passes **74 tests and 49 subtests**. This includes
12 independent-worker connected cases and one schema/vector test. The Impetus suite
passes **20 tests** under this dependency-equipped interpreter, including actual CLI
schema/readback checks. Ruff passes for the five new Python modules/tests. The demo
completed in a disposable local directory, with a context-only addendum,
no selected content and no send. Session-specific scratch locations are omitted;
the demo directory is not a fixture pin.
The contract files and tests are the reproducible evidence. Full Spine regression
was not rerun. An offline wheel attempt could not import `setuptools.build_meta` in
the local environment; source-checkout integration is verified, installed-wheel
qualification is not claimed. No live providers, deployment, release or sends occurred.
