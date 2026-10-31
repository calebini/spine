# Impetus handoff: contextual notification experiment

Update, 2026-10-29: the subsequent operator-selected synthetic capture integration is
implemented under [the adopted contract](../specs/contextual-notification-capture.md)
and [operations](CONTEXTUAL_NOTIFICATION_CAPTURE.md). The design handoff below is
retained as history; its rough examples and open choices are superseded only for
that implemented subset.

Date: 2026-10-29. Design handoff only; no runtime implementation is requested by
this document. The normative proposal is
[contextual-notification-experiment.md](../specs/contextual-notification-experiment.md),
version `0.1.0-draft.1`. Current task evidence lives in
[SPINE-066](BACKLOG.md#spine-066--draft-a-direct-advisory-experiment-and-impetus-handoff).
This is a working-tree proposal; record an exact containing commit when an owner
adopts it after checkpointing. A moving checkout is not a compatibility pin.

## Product objective

Make opted-in event reminders more helpful or more personable using the archetype,
permitted facets, relative timing and ordinary rendered reminder. Let the model
choose whether a bounded read-only lookup is worthwhile. No addition is valid;
friendly context-only wording can also be a worthwhile result. Flights are an example,
not the only supported archetype or a hard-coded tool sequence. Capture proposals
for review before enabling their inclusion in delivered reminders.

Read the [request](../examples/contextual-notification-experiment.request.json)
and [result](../examples/contextual-notification-experiment.result.json) together.
They demonstrate a week-before flight reminder with a personable addition and no
tool call. Their field names, numerical limits and source-ID aliases are provisional.

## Impetus owner decisions before implementation

1. Explicitly select a separate experimental mode. The current
   [governor integration](../../impetus/specs/governor-integration.md) and
   [Light-first decision](../../impetus/specs/decisions/0003-threshold-light-first-governor.md)
   remain unchanged. This mode omits governor admission/acceptance and does not
   claim conformance to those requirements. Use real experimental records, without
   dummy native grants or acceptance references. Preserve historical governed work.
2. Agree the exact request/result and independently authorized local readback shape
   with Spine. Propose a small local JSON command boundary initially, including
   trusted invocation, duplicate/conflict results, uncertain admission and retained
   readback. Keep provider credentials solely in Impetus adapters. Do not add a
   shared database or require a network deployment merely to exercise this boundary.
3. Select the model configuration, any first read-only tool, prompt/configuration
   revisions, complete input/output limits, accounting and call/whole-run deadlines.
   Weather is optional; no tool or external factual claim is required for a
   personable line. The example's two-model/one-tool/30-second ceilings are proposals,
   not a waiver or adoption of current Impetus provider requirements.
4. Define the smallest durable work claim, pre-call record, immutable terminal result
   and readback needed for zero automatic research retries. State what process exit,
   missing response, cancellation and restart actually establish. Retain uncertain
   provider activity truthfully. Determine readiness for new work after restart.

Spine separately owns immutable source/work derivation, disclosure projection,
definition and notification pins, cutoff mapping, capture storage and later
selection/delivery contracts. Neither owner may adopt the other's changes by proxy.
Do not infer that facet rendering permission permits external model disclosure.

## First connected proof

Use real Spine source export and capture with an independent minimal Impetus worker
and deterministic provider adapters. The exact same work resolves without a new
call; changed request bytes conflict. Prove context-only wording, sourced information,
no addition, truthful failure/uncertainty, stale source, lost acknowledgement,
late result and restart without repeated research. Report capture separately from
selection and sending. No live-provider or real-notification claim follows from it.

Then configure a supported live backend and opted-in non-sensitive reminders for
the usefulness/tone experiment. Keep records of what was checked even when nothing
was added, without requiring private chain-of-thought or unnecessary transcripts.
Threshold/Light integration remains future work informed by the observed needs.
