# Handoff: Spine live-profile synthetic capture

Update, 2026-11-03: the owner correction is adopted for offline SPINE-069 support
from Impetus `5ff3c0c4530fe07e81cc9067eddadd967a90acc4`, schema SHA-256
`bf3d132392c41ab21e9f7bf44f765aa79799a8dd41f8666d1d39ad646c442c4b`.
The wire version remains `impetus.openai.v1`. See the
[current consumer contract](../specs/contextual-notification-live-capture.md),
[owner correction](../../impetus/docs/openai-late-observation-correction.md) and
[operations](CONTEXTUAL_NOTIFICATION_LIVE_CAPTURE.md). The original request and
sequence below are preserved as design history; the owner correction is no longer
pending. No real-provider call or real-reminder qualification follows.

This is the implementation handoff for SPINE-068 and the proposed
[Spine consumer contract](../specs/contextual-notification-live-capture.md).
It does not enable the live worker in Spine. SPINE-067 remains the implemented
deterministic integration; the broader experiment and real reminders remain draft.

## Existing owner surface

Impetus checkpoint `eba6578bcdba0e33818b7963aea983603f93ba1d` implements
`impetus.openai.v1`, its independent CLI, explicit provider enablement,
count/generation binding, accounting and credential-free readback. Its schema hash
at inspection is
`5de8e9de0a4052e91091e3f641215daae1dae8b087cc51adfc02865cf76b6b57`.
The [owner specification](../../impetus/specs/openai-model-adapter.md) and
[schema](../../impetus/contracts/schemas/contextual-notification-openai-v1.schema.json)
are owner inputs. Spine does not amend them by copying or describing them here.

## Concrete owner correction before adoption

The current schema rejects an actual worker late-response record when token
counting precedes generation:

| Surface | Observed behavior |
| --- | --- |
| `services/live_worker.py`, late-response append | Uses the generation record's ordinal: 2 after count ordinal 1 |
| Schema `$defs.response.properties.execution.anyOf[0].properties.observations.items.properties.call_ordinal` | `const: 1` |
| Result | A truthful failed/deadline envelope is not valid against its own response schema |

An offline reproduction used the owner's existing `CountingTransport`, a fake
monotonic/wall clock and a disposable Impetus store. Counting returned 50; generation
returned a normal mocked receipt, then the clock advanced to 21 seconds. There
was one fake count entry and one fake generation entry, zero real requests. The
worker retained `status=failed`, `reason=deadline`, two call records and a late
observation referencing call 2. The published response schema rejected it. Changing
only that ordinal constraint in an in-memory control to integer range 1–2 made
the same envelope validate. This confirms a concrete schema/producer mismatch,
not a request to weaken Spine validation. The check completed in 0.013 seconds.

The owner should correct the schema and add a regression proving schema-valid
invoke and readback for a late counted generation at ordinal 2. A range correction
alone must not imply that arbitrary ordinal references are semantically valid:
consumer validation must still require a reference to an actual generation call.
Keep deterministic contracts unchanged. Record the corrected owner checkpoint,
wire-version decision and schema digest; those become the inputs for Spine adoption.
The Impetus checkout was not changed by this design task.

## Spine implementation sequence

1. Pin and copy the corrected owner schema, then add independent live-profile byte
   vectors and installed-resource parity checks. Pin the counting-capable closure,
   not an older single-call live schema. Keep deterministic schema copies unchanged.
2. Add a separate live export/capture profile with one generation, mandatory count,
   zero tools, synthetic source/disclosure configuration and trusted launcher
   opt-in. Persist expected configuration/prompt/schema pins alongside exact
   request bytes in a newly initialized format-2 sidecar. Use a fresh synthetic
   ledger; do not migrate, reset or repurpose format-1 opportunities in this slice.
3. Validate the new execution facts without the deterministic provider-only rule.
   Keep the existing deterministic validator intact. Preserve source freshness,
   launch-once/readback, timing, late facts, usage uncertainty and selected/sent false.
   Configuration revision is the owner's insertion-order compact-JSON digest,
   not Spine's sorted-key hash. Configuration changes cannot reopen work.
4. Prove the consumer with an independent worker subprocess using mock transport
   and fake clocks, followed by installed-wheel checks and appropriate ordinary
   reminder/capture regressions. Check the late-ordinal case, replay/restart,
   source/config drift, count binding, costs/reserves and unchanged source/attempts.

These steps require no live credentials, provider request or deployment. Provider
configuration artifacts and credential locators stay outside the checkout and
capture records. Pin configuration content without embedding machine-specific
paths. Readback/recovery do not receive live-enablement permission.

## Separate trial boundary

After offline implementation, present the exact synthetic request, non-secret
configuration, maximum admitted exposure and expected count/generation operations
for a separately authorized single trial. Use a new ledger, sidecar and matching
worker namespace; retain results/readback even for failure or no addition. Generated
notifications remain disabled. A real-reminder opt-in/disclosure policy is a later
Spine task, not an implication of this trial or the earlier independent live result.
