# Synthetic contextual notification capture

Version: `spine.contextual-notification-capture.v1`. Implemented experimental subset,
2026-10-29, under the user's request to connect Spine export, Impetus and non-sending
capture. The broader [experiment design](contextual-notification-experiment.md)
remains a draft for real reminders and later delivered content.

The adopted cross-owner contract and semantics are in
[Impetus's integration specification](../../impetus/specs/spine-capture-integration.md).
The machine contract owner is Impetus; Spine's
[checked-in schema](../contracts/contextual_notification/local-v1.schema.json)
and installed `spine.contracts/contextual_notification/local-v1.schema.json` are exact
copies of its `impetus.local.v1` closure. The [request fixture](../contracts/contextual_notification/request.json)
and [byte vector](../contracts/contextual_notification/vector.json) are independent
fixtures for contract checks, not real ledger IDs. The earlier flight examples remain
historical sketches; their draft version is not the shared command version.

Spine's experimental module exports from its existing ledger and ordinary renderer
under an explicit synthetic-only, item-opted-in operator configuration. It stores
requests, source fingerprints, a once-only send intent and append-only captures in a
private experiment sidecar tied to the actual ledger identity. It does not modify
schema 19, canonical work, policy, rendering history or the generic attempt ledger.
A separate module-level binding/version is declared; existing registered public
commands, HTTP, Tickerd and runtime release declarations remain unchanged.

Source responsibility stays with Spine: actual non-recurring event, archetype,
permitted primitive facet values, ordinary preview, times, current work eligibility
and disclosure/configuration must resolve. Notes, summary, recipients and unselected
fields are excluded. The full ordinary text is separately opted in. Export location
is omitted in this subset. Request/rendering pins and source fingerprint retain the
original facts; source/config changes make old proposals unusable and cannot open
replacement research. Only real ledger transactions read source facts. No lock or
transaction spans provider execution. Configured callers are trusted local operators;
there is no real-data disclosure authorization claim.

The service uses a separately configured subprocess adapter, never importing the
worker or sharing stores. New execution requires an original durable launch marker.
After uncertainty or restart it uses readback only; absent and unavailable do not
clear that marker. The initial exporter uses a bounded lead window and fixes expiry
and selection cutoff to the nominal reminder instant. Capture never moves that time.

Each capture binds the original exact bytes/digest, result/usage facts and current
source classification. Late/stale/failed/unknown/no-addition records remain reviewable.
Ordinary reminder text is a **nominal preview**, not evidence of actual delivery.
A boolean hypothetical-usability observation has a finite check time and cannot imply
selection, governance acceptance, source locking or permission to send. Every capture
explicitly says `selected=false` and `sent=false`. The ordinary work/attempt path is
not invoked by this integration. A later message-inclusion feature needs separate
Spine-owned selection, fallback and attempt protection.

See [operations and validation](../docs/CONTEXTUAL_NOTIFICATION_CAPTURE.md).
No live providers, real event sampling, public API or staging deployment is enabled.

The [offline live-profile consumer](contextual-notification-live-capture.md)
is a separate implemented experimental profile. It does not expand this implemented deterministic version
or reinterpret its stored opportunities and captures.
