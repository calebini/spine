# Opt-in enriched reminder delivery

SPINE-074 implements the [bounded contract](../specs/notification-enrichment-delivery.md)
as an optional library integration. It is qualified with fictional source data,
an independent mocked Impetus worker and fake notification senders. Nothing in
this change enrolls real work, accesses credentials, invokes a provider or activates
delivery. Normal workers remain ordinary unless explicitly injected with enrichment.

## Operator-owned inputs

Select one existing timed, non-recurring event reminder and its resolved subject
owner. Agree the exact disclosed ordinary prose/selected primitive facets and
private retention with the operator and Impetus owner before actual use. Notes,
routes, contacts and unselected structured fields are omitted; ordinary prose may
itself contain locations or facet values and must be reviewed in full.

The closed configuration schema is
`contracts/contextual_notification/enrichment-v1.schema.json`, `$defs.config`.
It requires `synthetic_only=false`, one exact `work_instance_id`, one opted-in item,
`actor_subject_id`, `permit_ordinary_text=true`, selected `facet_fields`, definition
and disclosure revisions, a retention reference, the approved context SHA-256,
lead seconds (1–300) and zero allowed tools. Provider configuration is the existing
counting-capable profile and is required for fresh export/invocation. Readback can
omit it and uses the immutable stored binding to retain execution facts. Omitting
or changing it changes the current configuration fingerprint, so that readback
does not establish freshness for delivery. Restore the approved configuration to
consider a previously observed on-time candidate; never invoke again.

These local references are trusted operator configuration, not authenticated
consent grants. A changed context requires a new explicit approval; it does not
authorize reusing or replacing a consumed research opportunity.

## Library flow

1. `spine.adapters.enrichment.open_source(existing_path)` opens a schema-19 source
   read-only without bootstrapping, migrating or changing its journal mode.
   `source.preview(work_id, config)` exposes the exact `context` for local review.
   Approve its canonical digest with `spine.adapters.contextual_experiment.digest`
   and put that value in `approved_context_sha256`. Do not paste real context into
   a chat as part of approval.
2. Explicitly initialize a fresh `EnrichmentStore` for the source namespace and
   independent Impetus worker state. Open that same continuous store thereafter;
   existing synthetic stores cannot be adopted. Do not recreate a missing store
   to resume research. The profile reuses format 2 with extra immutable choices
   and prepared envelopes, without changing synthetic formats or canonical tables.
3. Construct `EnrichmentExperiment(source, store, launcher, config, enabled=True)`
   only under trusted configuration. The default is disabled. The independent
   `LiveLauncher` also requires explicit invocation enablement/configuration.
   Call `export(work_id, now_utc)` and `run(opportunity, now_utc)` before the reminder.
   Exact original request bytes and bindings precede the launch-once marker.
   Invocation follows the existing mandatory count/one-generation/zero-tools bounds.
4. If invocation response is lost, reopen the same state and use `readback`, or
   `run` on the consumed marker. This never starts a second invocation and needs
   neither credentials nor live enablement. A first observation after cutoff is
   retained but cannot become an on-time proposal.
5. Inject the configured experiment through
   `run_spine_worker(..., enrichment=experiment)` or
   `OpenClawNotificationProcessor(sender, enrichment=experiment)`. Delivery reads
   persisted state only. It never launches research, polls the worker or waits for
   a provider. The ordinary attempt gate, rendering/route checks, work identity and
   gateway idempotency key remain in force.

The source connection and sidecar are caller-owned; close them after use. There is
no new CLI switch or environment default. The connected test module is a fully
disposable example of construction, approval, mocked research and fake delivery;
it is not a real-ledger trial command.

## Outcomes and evidence

An on-time usable addendum is appended after two newlines. No-addition, failed,
uncertain, absent, stale, revoked or late capture sends the ordinary body. Reject
an overlong composition rather than truncate it. A persisted ordinary choice never
upgrades. An enriched choice may downgrade when stale; it never changes addendum.
Consent/source and prepared evidence are checked again inside the canonical
attempt transaction. A failed enrichment check rolls back and immediately takes
the ordinary path. Private-store trouble cannot hold the reminder hostage.

Captures retain `selected=false` and `sent=false` as capture facts. Enriched outbound
v3 records the ordinary rendering hash separately from the composed-body hash and
selection. The canonical rendering row/public rendering readback describes the
ordinary base. Use `experiment.delivery_evidence(connection, attempt_id)` for the
full private composed envelope and canonical attempt status/provider reference.
It verifies the canonical request hash and returns no enriched evidence for an
unused prepared envelope after ordinary fallback. An attempted/failed envelope is
not proof of delivery. Missing private content cannot be reconstructed from a hash.

Research is launch-once. Delivery keeps normal retry behavior and a stable gateway
key; one logical message depends on the gateway honoring that key. Current ordinary
text can be re-rendered on retry, and stale enrichment is removed. Late capture
never creates a new notification or invokes research again.

## Qualification and next activation decision

The backlog records exact offline commands, totals and limitations. This includes
the connected independent worker, fallback/races/replay/retry, ordinary regressions,
contract/resource parity and installed-wheel checks. Schema 19/runtime 0.11.2 and
existing registered capabilities remain unchanged. This is experimental injected
behavior, not a released or deployed public capability.

For an actual reminder, separately agree the specific source/owner/disclosed
context, provider configuration/account and spend bounds, continuous private store
locations/retention, gateway duplicate suppression and the one-message authorization.
Then review that concrete configuration and activate only the selected work.
There is no additional usefulness study or general resilience campaign prerequisite.
No real-source, live-provider or real-reminder qualification is claimed here.
