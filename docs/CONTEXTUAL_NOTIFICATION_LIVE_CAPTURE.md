# Offline live-profile capture

SPINE-069 implements the [synthetic live-profile consumer](../specs/contextual-notification-live-capture.md).
It adopts Impetus `5ff3c0c4530fe07e81cc9067eddadd967a90acc4`, interface
`contextual-notification-experiment`, version `impetus.openai.v1`, schema SHA-256
`bf3d132392c41ab21e9f7bf44f765aa79799a8dd41f8666d1d39ad646c442c4b`.
The independent worker has its own state and provider adapters; Spine owns export,
original identity, execution pins and non-sending capture. Runtime 0.11.2 and
canonical schema 19 remain unchanged.

## Reproduce the offline proof

Use the existing dependency-equipped interpreter and sibling Impetus checkout:

```sh
PYTHONDONTWRITEBYTECODE=1 IMPETUS_SRC="$PWD/../impetus/src" PYTHONPATH=src:tests \
  .venv/bin/python -m pytest -o addopts='' -p no:cacheprovider -q \
  tests/test_contextual_live.py tests/test_contextual_live_contract.py \
  tests/test_contextual_experiment.py tests/test_contextual_experiment_contract.py \
  tests/test_notification_rendering.py tests/test_schedule_create_command.py \
  tests/test_rendering_delivery.py
```

The live tests invoke `tests/fixtures/contextual_live_worker.py` in independent
subprocesses. That fixture uses Impetus's actual worker/store/model adapter, a
fake clock and mock transport, with socket creation forbidden. Its fixed fake key
is not a credential; no credential file or real provider is used. Both provider
operations are visible in retained records. Connected tests explicitly skip if
the independent checkout is unavailable. Resource/vector checks work separately.

`contracts/contextual_notification/live-configuration.json` is a synthetic test
configuration with invented model/tariff values, not a deployable provider config.
The independent request/read/late-response vector and complete schema copies are
hashed by `live-pins.v1.json` and also included as installed package resources.
The original deterministic files are untouched.

## Service and storage

`runtime.contextual_live_capture.initialize(directory, now, configuration_json)`
creates a new directory, source ledger and format-2 sidecar, returning the ledger,
synthetic work ID, explicit source configuration and open capture store. Existing
directories fail rather than being reused. Close both ledger and store afterward.
Initialization does not invoke a worker or provider.

Construct `LiveExperiment(Source(ledger), store, launcher, config, clock=...)` for
export/run/readback/capture. Clock injection is for deterministic tests; the default
uses UTC observation time. The trusted source config contains only explicit opt-in,
ordinary-text permission, selected primitive facets, definition/disclosure revisions,
lead time, empty allowed tools and optional `provider_configuration_json`.
Unknown config fields are refused. New export needs the configuration JSON; retained
readback may omit it and use the export's durable bindings.

`LiveLauncher` accepts a trusted worker command, optional non-secret provider-config
path, environment and `enabled=False` by default. Keep provider invocation flags out
of the base command. Its invoker adds the configured path/enablement flags only to
the invocation command; its reader receives neither flags nor credential environment.
An enabled invocation first compares configuration content with the stored encoding.
This assumes an operator-owned immutable artifact and trusted child; it does not
lock that artifact across worker entry or qualify hostile subprocess output.

Persisted requests and bindings cannot be rewritten and markers cannot be cleared.
After a marker, run performs only readback, including after timeout, process loss,
absent/unavailable responses or restart. Missing original stdout never permits a
second invoke. Explicit owner recovery may terminalize an abandoned claim without
resuming count/generation. Do not clear state, copy format-1 opportunities or retry
research to obtain a different result.

The capture retains original request identity, binding and source fingerprints,
execution/usage/reserves, late facts, nominal preview and finite usability observation.
Successful no-addition remains a valid outcome. Unknown usage stays unknown; token
counting keeps its fee reserve even on success. Computed USD usage is not an invoice.
All captures explicitly say selected=false and sent=false, with no notification attempt.

## Separately authorized single live trial

Offline support does not authorize the following action. Before selecting one real
provider invocation through Spine:

1. Select and review the exact synthetic request and a non-secret, counting-enabled
   model/configuration artifact, including token bounds, qualified rates, counting
   contingency, maximum admitted exposure and source cutoff. Test-fixture prices/model
   names are unsuitable. Impetus owns credential loading and provider/account terms.
2. Prepare a fresh synthetic directory/ledger and format-2 sidecar plus a new independent
   worker store with the matching ledger namespace. Pin the original configuration
   encoding/revision, schema and prompt; retain request bytes before invocation.
3. Obtain explicit authorization for one original invocation with its count plus one
   generation, zero tools and stated exposure. Only then configure the trusted launcher
   for that invocation. Keep credential values/locators outside Spine configuration,
   requests, captures and the checkout; do not paste them into a chat.
4. Retain capture and credential-free readback for success, no-addition, failure or
   uncertainty. Review source/timing and observed usage plus remaining reserves.
   Preserve the marker even if the trial loses its response.

Generated delivery remains disabled. Real source ledgers, recurring reminders,
real-reminder opt-in/disclosure and delivered content require separate work.

## Validation record

SPINE-069 in [the backlog](BACKLOG.md) records exact final commands, totals,
durations, known repository issues and installed-wheel results. Initial development
checks found and corrected a timedelta comparison in the new consumer; that issue
is separate from the pre-existing strict-mypy errors and deadline-trace warning.
No live provider, real credential, network, notification, deployment or dependency
acquisition was used for this implementation proof.
