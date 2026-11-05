# Live-profile synthetic contextual notification capture

Version: `spine.contextual-notification-live-capture.v1`

Status: Implemented offline synthetic consumer, SPINE-069 (2026-11-03). The
SPINE-068 design is adopted for the bounded implementation below. Connected tests
use fake clocks and mock provider transports; real provider execution and real
reminders remain separately qualified and authorized work. SPINE-067's
[deterministic capture](contextual-notification-capture.md), checkpoint `c0a7b13`,
retains its original meaning. See [operations](../docs/CONTEXTUAL_NOTIFICATION_LIVE_CAPTURE.md)
and [decision 0007](decisions/0007-offline-live-capture-profile.md).

## 1. Selected boundary

The live-profile consumer exports one opted-in synthetic event from a fresh
disposable Spine ledger, invokes the independent Impetus worker, and retains
a non-sending capture. It uses context only, one generation, a preceding token
count, and zero tools. `no_addition` remains a valid successful outcome. Real events,
real-reminder disclosure, sourced additions and message inclusion are later work.

Spine owns source selection, disclosure, exact original request bytes, opportunity
identity, freshness and capture. Impetus owns provider configuration/credentials,
provider I/O, durable execution/usage facts, admission exposure and recovery.
There is no governor in this experiment. Current schema 19, release 0.11.2,
registered commands, Tickerd, reminder rendering and delivery are unchanged.

## 2. Adopted owner wire contract

The wire contract is `impetus.openai.v1`, interface
`contextual-notification-experiment`, from Impetus checkpoint
`5ff3c0c4530fe07e81cc9067eddadd967a90acc4`. Its complete
[owner schema](../../impetus/contracts/schemas/contextual-notification-openai-v1.schema.json)
is copied exactly to `contracts/contextual_notification/openai-v1.schema.json`
and the corresponding installed package resource. SHA-256:
`bf3d132392c41ab21e9f7bf44f765aa79799a8dd41f8666d1d39ad646c442c4b`.
The module verifies that digest at import. Source/package closure and independent
request/read/late-response vectors are pinned by `live-pins.v1.json` in that family.
The existing deterministic files are unchanged. See the
[owner semantics](../../impetus/specs/openai-model-adapter.md).

The original SPINE-068 inspection baseline was Impetus `eba6578` and schema
`5de8e9de0a4052e91091e3f641215daae1dae8b087cc51adfc02865cf76b6b57`.
It rejected a late generation observation at ordinal 2 after counting. The
[owner correction](../../impetus/docs/openai-late-observation-correction.md)
resolved that inconsistency and rejects observations referencing a count or absent
call. The owner retained the wire version; compatibility requires the corrected
bytes, not the version string alone. The original [handoff](../docs/CONTEXTUAL_NOTIFICATION_LIVE_CAPTURE_HANDOFF.md)
is design history; this specification records the adopted pin.

The complete owner schema still supports non-counting generation at ordinal 1.
Spine's separate consumer semantics require counting and generation at ordinal 2;
Spine does not narrow or edit the owner schema by proxy.

## 3. Export, configuration and identity

Retain SPINE-067's explicit item opt-in, `synthetic_only=true`, full ordinary-text
permission and primitive facet allowlist. Export event title, start and timezone,
archetype, selected facet values and the nominal ordinary preview. Exclude notes,
summary, recipients, routes, unselected facets and location. Enforce both the
schema and the owner's UTF-8 byte/semantic bounds; character-count schema limits
alone do not establish a valid worker request.

Use the existing source references and work derivation, including the ledger
namespace and notification opportunity. Selecting a provider, profile, prompt or
new configuration must not create replacement work for an existing opportunity.
The first live demo requires a new synthetic ledger and private owner stores;
resetting stores or relabeling an existing deterministic opportunity is prohibited.

The live request differs from the deterministic export as follows:

| Field | First live consumer requirement |
| --- | --- |
| `interface` | `contextual-notification-experiment` |
| `version` | `impetus.openai.v1` |
| `allowed_tools` | Empty array |
| `limits.model_calls` | 1 generation; token counting is a separate provider operation |
| `limits.tool_calls` | 0 |
| `limits.elapsed_seconds` | 20 |
| `limits.addendum_utf8_bytes` | 512 |
| `request_expires_at_utc`, `selection_cutoff_utc` | Nominal reminder eligibility instant |

Persist the chosen UTF-8 request bytes, including their newline, before invocation.
Bind every response/read to their SHA-256, namespace and work ID. Never regenerate
bytes for retries or readback. The request cannot choose a provider, model,
credential, endpoint, tariff, launcher flag or worker configuration path.

The trusted operator supplies a non-secret immutable worker-configuration artifact
with token counting enabled, its exact configuration revision, and the expected
prompt revision `helpful-personable-openai.v1`. Credential values and credential
file locators stay solely in the worker launcher environment, outside source,
requests, captures and configuration pins. Provider execution requires a distinct
explicit launcher opt-in; choosing this profile or running offline tests does not
authorize a real call. Do not install a default model/tariff or inherit live
enablement from event content.

The worker's configuration revision is `openai.responses.v1:` plus SHA-256 of its
validated configuration encoded as compact UTF-8 JSON with insertion order
preserved. It is **not** Spine's sorted-key digest or the raw config file hash.
Persist the operator's expected revision and original non-secret configuration
encoding at export; compare the returned configuration and revision to these
pins before treating execution as conformant. Preserve the encoding separately
from normalized capture JSON so sorting cannot change the revision calculation.
Check the configured artifact before launch. A trusted immutable artifact and
launcher are assumptions: post-call detection of drift cannot undo a disclosure
or charge, and this wire request contains no provider-configuration authorization.

## 4. Private sidecar and version separation

The live capture record contract is
`spine.contextual-notification-live-capture.v1`. `LiveCaptureStore` uses a new
explicitly initialized format-2 sidecar, tied to the actual fresh synthetic ledger
identity. Keep original request bytes, work/opportunity identity,
source fingerprint, launch marker and captures, plus an immutable export binding:
wire version/schema hash, expected configuration revision/encoding, prompt revision,
counting requirement and capture contract. The binding also stores source-config
and disclosure SHA-256 fingerprints; the original source fingerprint is retained
with the export and each capture. Commit request and binding together. SQL triggers
prevent changing/deleting exports, clearing launch markers or rewriting captures.
Include these pins in source/config freshness comparison.

Format 1 retains its current deterministic meaning. This slice neither migrates
nor reuses it; the existing reader continues to handle its original captures.
A live reader must refuse a missing/unknown binding or format instead of guessing
from current operator configuration. Existing deterministic records cannot be
re-exported under the live profile to bypass their opportunity or launch marker.
Any later support for live export from an existing ledger needs a separate
continuity design; fresh synthetic initialization is the bounded first consumer.

Readback can reopen without the provider configuration file or ambient profile
JSON. Missing/changed ambient configuration makes usability stale, while original
execution remains readable. `LiveLauncher` strips credential environment variables
and passes neither provider-config nor enable-live flags to its reader. Readback
chooses the wire version, schema and expected pins stored with the
original export, even if ambient configuration has changed. Such changes make
the proposal unusable without erasing the original execution facts. There is no
transaction spanning provider work and no canonical ledger write during capture.

## 5. Invoke, timing and readback

Retain bounded lead selection (1–300 seconds) and the existing pre-invocation
source/disclosure checks. The cutoff stays at nominal reminder time. Impetus
clips its shared count/generation allowance to the request duration, source
cutoff and its own 20-second live limit, with its existing one-second clock margin.
Counting gets at most five seconds; at least one second must remain afterward
before generation. A lead window does not guarantee a full execution allowance.

Commit one original launch marker before spawning. A marker without a response,
timeout, process loss, `absent` or `unavailable` never authorizes another invoke.
Readback uses exactly interface, stored version, namespace, work ID and original
request digest. It needs no credential or live-enablement flag. Explicit Impetus
recovery may terminalize an abandoned claim when the original worker is gone;
it never resumes counting or generation. Spine does not automatically run recovery.

Retain the current invoke/read disposition sets and envelope binding checks.
Unknown schema/version, mismatched bindings or malformed execution produce an
unusable invalid-response capture; retain the validation reason and response
digest when available, and the original launch marker. Response digests use
normalized sorted-key JSON, not original stdout bytes. The request digest always
uses the exact persisted original bytes. Worker-side execution
remains the authority for its retained usage; an invalid response is not evidence
of zero usage. No fallback to a deterministic provider or replacement research.

Use the actual observation clock for live capture. A successful result is usable
only at a finite observation time no later than cutoff, with completion by cutoff,
current source/disclosure/config and valid execution pins. Late results, including
late-response observations within failed executions, remain review evidence and
never a new proposal. `selected=false` and `sent=false` are mandatory on all captures.

SPINE-072's observation-precision correction preserves all available datetime
fractions when formatting clock-derived invoke/readback observations in UTC.
Do not truncate or round observations into a different completion/cutoff ordering:
same-second completion can already be usable, while even one microsecond after
cutoff is unusable. Explicit caller-supplied observation timestamps retain their
exact precision and conservative interpretation. This is a compatible correction
within capture v1/format 2; request/export formatting, deterministic profile bytes,
schema pins, original exports and historical capture records remain unchanged.

## 6. Execution, count binding and accounting

Validate the agreed closed owner schema first, then these stricter consumer
semantics. Pending/failed executions may contain a prefix of the allowed sequence;
success requires the complete sequence and a closed valid result.

| Ordinal | Operation | Required interpretation |
| --- | --- | --- |
| 1 | `openai.responses.input_tokens.v1` | Count preflight; `usage=null`, `tokens=null`; count is not consumed generation tokens or proof of a free call |
| 2 | `openai.responses.v1` | The one generation; `count_call_ordinal=1`; its request digest equals the count record's `generation_request_sha256` |

Reject duplicate/reordered ordinals, other operations and generation without a
completed count. Successful counting has a non-boolean integer count within the
pinned input ceiling; successful generation reports exactly that input count,
valid input/output/total token arithmetic and provider/model identifiers matching
the pinned configuration. Null reasoning-token data means unavailable, never zero.
Output includes reasoning; do not add it to charges a second time. Successful
addenda must be `provided_context`, with empty sources and at most 512 UTF-8 bytes;
`no_addition` has its own closed result shape. Failed/interrupted/uncertain/pending
work has no usable result. Observations do not replace the execution result.

Retain `provider_configuration`, configuration/prompt revisions, interface version,
`live_day`, `authorized_nanodollars`, calls, usage, residual reserves, timestamps,
failure reason and late observations under their original meanings. Check actual
UTC timestamps and call/observation ordinal references, not just their JSON shapes.
Do not require failure records to satisfy success-only usage/count equalities.

Amounts use integer `usd_nanodollars`. Preserve generation usage and residual
reservation separately; preserve the count fee contingency even after a valid
count. Null usage stays unknown. Computed charges use pinned rates and are not
invoices. Impetus's current admission bounds are at most 20,000,000 nanodollars
per run, 20 new runs and 400,000,000 nanodollars of new exposure per UTC day.
Spine retains those facts without becoming another budget allocator. For exposure
display, the worker uses the maximum of original authorization and observed usage
plus remaining reserves; do not add authorization to that sum or release it on
restart. Preserve known overruns and their failure, rather than rejecting the
truthful accounting merely because it exceeds authorization. These controls rely
on qualified configuration and do not prove a hard upstream billing cap.

## 7. Implemented surface and qualification boundary

`runtime.contextual_live_capture.initialize` validates a non-secret configuration
and creates a new synthetic source directory/ledger plus format-2 sidecar. Existing
directories fail; no ledger or format-1 store is repurposed. Low-level service/store
callers are trusted operators and must preserve this fresh-source precondition.
`services.contextual_live.LiveExperiment` provides export/run/readback/capture;
`adapters.contextual_live.LiveLauncher` provides distinct explicitly enabled invoke
and credential-free read commands. New invocation checks the immutable non-secret
configuration artifact before committing the launch marker. Reading an existing
opportunity uses its original stored bindings even if ambient configuration changed.

Independent vectors and resource checks pin the exact complete owner schema.
Connected subprocess tests use the independent worker with a fake clock and mock
transport, covering success/no-addition, count failure/over-limit, mismatched usage,
late generation at ordinal 2, invalid references/records, source/config drift,
lost responses and worker death during count, after completed count and during
generation. Reopen/readback never repeats research. Tests assert unchanged source
and zero notification attempts. The [operations note](../docs/CONTEXTUAL_NOTIFICATION_LIVE_CAPTURE.md)
and SPINE-069 record actual checks and installed-wheel evidence.

This is offline integration support, not provider/account/tariff qualification.
The existing subprocess adapter still assumes a trusted bounded child; this adds
no hostile-process containment or general resilience/storage qualification claim.
A real end-to-end trial requires separate authorization of the exact synthetic
request, non-secret configuration, admitted exposure and count/generation
operations, using new disposable stores. No real-reminder disclosure or delivery
is enabled by this module, its tests or an earlier independent Impetus trial.
