# Opt-in enriched reminder delivery

Version: `spine.notification-enrichment.v1`

Status: Implemented and qualified offline, SPINE-074 (2026-11-06), default off.
Real-source/provider/delivery activation remains separately authorized. This supersedes the
larger [capture pilot draft](contextual-notification-real-capture-pilot.md) for
the selected slice; it does not adopt its registry, format-3 or purge requirements.
Real-data reads, provider execution and actual sending need separate enablement.

## Boundary and disclosure

Enroll one exact existing event reminder/work under trusted local configuration.
Require its resolved subject owner to match the configured actor, an active timed
non-recurring event, the exact opted-in item/work and explicit ordinary-prose
disclosure. Selected facets remain primitive-only. A local preview exposes the
exact model context (including location/facet details already present in ordinary
prose); consent pins its canonical SHA-256. There is no blanket location exclusion
and no automatic disclosure from rendering permission. Notes/summary/routes/
contacts and unselected structured facets remain outside the export. Review the
whole context as non-sensitive; scalar type does not establish permission.

The preview is a local operation, not permission to paste real context into chat.
Runtime configuration requires explicit disclosure and private-retention references,
actor/work selection and the approved context digest. These are operator-owned
records, not authenticated grants. Consent/source/config drift invalidates enrichment.
Use an existing read-only source connection for research; no seed, migration or
source write. Delivery independently uses its normal canonical connection.

## Research and storage

Keep Impetus `5ff3c0c4530fe07e81cc9067eddadd967a90acc4`, corrected complete
schema `bf3d132392c41ab21e9f7bf44f765aa79799a8dd41f8666d1d39ad646c442c4b`,
`contextual-notification-experiment` / `impetus.openai.v1`, mandatory count then
one generation, zero tools, 20 seconds and 512 UTF-8 addendum bytes. Keep current
count/body/model/prompt/configuration/token/reservation/reference validation.
Config revision uses insertion-order compact JSON. Work derivation remains
`spine.experiment-work.v1` over actual namespace/opportunity, independent of model,
profile and clock. Persist original newline-bearing bytes before the launch marker.

Use one explicitly initialized continuous enrichment sidecar and independent
worker state for the namespace. Reuse format-2 exports/captures with a distinct
enrichment profile marker and capture contract, plus small immutable choices and
prepared-message evidence tables. Do not adopt existing synthetic stores or
reinterpret their capture contracts. No create-if-missing, automatic reset,
profile-based replacement research, global registry or canonical migration.
Missing/unknown continuity disables research; ordinary delivery remains available.
Arbitrary host rollback/replacement is outside this trusted local boundary.

Research is an explicit pre-reminder operation, disabled by default. It never runs
inside delivery. It requires eligible unattempted work, current consent/source and
remaining lead/cutoff allowance. A consumed launch marker always resolves through
credential-free readback, even after lost stdout, absent state or restart. Once
ordinary fallback/selection has been committed, no new research may start.

## Content decision and attempt gate

At ordinary delivery, inspect only already persisted captures; never wait for the
worker, provider or another result. A candidate must have succeeded and been
actually observed usable no later than nominal reminder cutoff, with exact original
identity/pins, context-only result and current source/disclosure. Selecting at an
ordinary attempt after cutoff may use that previously observed on-time candidate;
a first observation after cutoff cannot manufacture timely availability.

Persist one choice per work before its first attempt: enriched with a bounded
validated addendum, or ordinary with a reason. No-addition, failure/uncertainty,
late/missing/invalid result, revoked/drifted consent/source and overlong composition
choose ordinary. Ordinary never upgrades. Enriched may only downgrade to ordinary
when newly stale, unavailable or revoked; it never acquires a different addendum.
Existing attempts without matching enrichment evidence also force ordinary.

Compose the current ordinary body plus two newlines and the addendum, preserving
the normal 1,024-scalar total body bound. Do not truncate either component. New
enriched outbound envelope `spine.openclaw.outbound.v3` identifies the ordinary
rendering separately and binds the full composed body and selected evidence.
Keep the canonical rendering row as honest ordinary rendering, not a fabricated
v1/v2 enriched rendering. Store complete prepared enriched envelopes privately;
the canonical attempt payload hash binds that envelope before external send.
Prepared evidence alone is not proof of attempted or delivered content.
The library `delivery_evidence(connection, attempt_id)` returns the closed
`spine.notification-enrichment-evidence.v1` shape only when the complete private
envelope recomputes to the actual canonical attempt hash. It includes the canonical
attempt status/provider reference. It returns no enriched evidence for an unused
prepared envelope after ordinary fallback. Existing public rendering readback still
describes the ordinary base; it does not expose the private composed envelope.

Recheck enrichment/source under the existing canonical attempt-start transaction,
alongside normal rendering/route checks. Stale enrichment at that gate rolls back
the attempt and immediately takes ordinary fallback, without research. Selection
and private evidence commit before the canonical attempt; there is no cross-database
atomicity claim. A partial operation can lose enrichment, never authorize another
research invocation or upgrade a committed ordinary attempt.

Retain the existing work/delivery identity, per-attempt ledger IDs and stable
provider idempotency key across delivery retries. Late research cannot enqueue or
send another message. Provider duplicate suppression still depends on the gateway
honoring that key; no exactly-once external-send guarantee is introduced. Research
is never retried; ordinary delivery keeps its existing retry policy and may re-render
current ordinary text. Revoked/stale enrichment cannot survive as a retry suffix.

## Enablement, retention and verification

Default delivery remains ordinary; the new library/worker injection is explicit
and disabled unless supplied by the trusted operator. No environment default,
delivery CLI activation, Tickerd pin or ledger schema change is implied.
Capture-only records remain selected=false/sent=false; separate choice,
prepared envelope and canonical attempts establish actual inclusion/send evidence.

Private source/proposal retention uses an explicit operator-agreed policy supported
by both owners; no invented seven-day purge or deletion capability. Confirm real-data
scope/provider terms and owner retention before actual use. This does not block
the fake-data implementation and does not authorize editing/deleting owner state.

Prove the full path using disposable ledgers, fake clocks, independent mocked
Impetus transport and fake delivery: addendum/no-addition/failure/stale/late/fallback,
lost response/restart, immutable choice/no late upgrade, source/consent race at
attempt gate, stable retry key, source disclosure and unchanged ordinary paths.
All new serialized shapes/resources need closed schemas and parity tests. Run
appropriate full regressions and existing checks; report pre-existing errors.

## Trusted-local staging capture pilot

`spine-enrichment-pilot` is a separate, manually invoked operator entrypoint
(`spine.notification-enrichment-pilot.v1`). It has no normal command/web registry
entry and cannot enroll or alter reminder delivery. The operator designates one
staging ledger identity, one exact already-materialized, eligible, unattempted
single-event work instance, and one private Spine/Impetus state pair. Apply the
source/actor checks above and require a positive pre-event offset. The first pilot
exports no structured facets and allows zero tools. Review nominal ordinary prose
in full: information already rendered into that prose is not redacted.

`preview` reads the source without changing it and freezes the exact original
Impetus request, provider configuration binding, source/disclosure fingerprints,
and local execution/retention references in a newly created private state directory.
The request SHA-256 covers the exact original UTF-8 export including its terminal
newline. The approval SHA-256 covers the sorted compact UTF-8 preview JSON object
without a newline. Receipt output is metadata only; preview bytes stay private.
Preview has no launcher, credential lookup or Impetus exchange. It does not
authorize capture or application of the result.

`capture` requires a separately supplied exact approved digest and an explicit
Impetus owner approval reference for real-source use and retention. These are
trusted operator attestations, not authenticated consent or automatic proof of
Impetus qualification. Recheck the exact existing ledger, current work/owner,
eligibility, no prior attempt, disclosure, frozen request and configuration before
entry. Both commands run within the configured lead window (at most 300 seconds)
and require more than 30 seconds remaining before the nominal reminder cutoff.
No ledger transaction spans process entry. If source facts change after the final
check, only the already approved bytes can be disclosed; do not claim atomic
revocation across the source and the provider.

Commit the approval and once-only marker in the same private transaction before
subprocess entry. No retry, no implicit Impetus read and no automatic recreation
or replacement of missing state. Preserve the designated continuous state; host
rollback or intentional replacement is outside the trusted-local guarantee.
`show` reads only retained local state, including when a launch yielded no local
result. The separate pilot profile cannot be opened as delivery enrichment; its
records are not usable for selection, are never sent, and never create configured
reminder work, messages or canonical attempts. An ordinary worker may independently
send the ordinary reminder on schedule. The local [preview and receipt schema](../contracts/contextual_notification/enrichment-pilot-v1.schema.json)
does not change the pinned Impetus wire contract.
