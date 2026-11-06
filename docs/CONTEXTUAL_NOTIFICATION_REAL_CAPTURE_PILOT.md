# Real-reminder capture pilot: design and next implementation

Historical proposal: the operator subsequently selected the smaller
[enriched delivery implementation](NOTIFICATION_ENRICHMENT_DELIVERY.md), SPINE-074.
Its current contract supersedes the standalone registry, format-3 and seven-day
purge proposed below. This document remains design history.

SPINE-073, drafted 2026-11-05, completed 2026-11-06. Design only. The authoritative proposal is
[one real-reminder capture pilot](../specs/contextual-notification-real-capture-pilot.md),
version `0.1.0-draft.1`. Current status and design evidence belong in
[BACKLOG.md](BACKLOG.md#spine-073--design-one-real-reminder-capture-pilot).
No actual event, ledger path, consent, model configuration or execution is selected
by these documents. The design is not a supported command or feature activation.

## Proposed first case and decisions

Choose one future ordinary reminder for a non-sensitive, non-recurring timed
event that the approving local operator owns. Keep the ordinary pipeline running.
The pilot reads a bounded source snapshot, obtains approval for its exact export,
invokes the independent Impetus worker at most once, and retains results for local
review. No generated content enters a message. Successful no_addition is useful
evidence; there is no retry to get a different answer.

| Design choice | Proposed first slice and reason |
| --- | --- |
| Source scope | One exact existing-ledger work/opportunity; no scanning, recurrence or auto-materialization |
| Actor/authority | Trusted local operator acting as resolved subject owner; no group or legacy ownership ambiguity |
| Disclosure | Exact title/start/timezone/archetype/nominal prose; optional four primitive fields from one facet revision, empty by default |
| Prose restriction | No primary location or facet-detail presentation; otherwise the ordinary body could bypass a structured-field allowlist |
| Review/consent | Local exact-byte preview, approved digest and explicit provider/counting/retention bindings; no automatic paste into chat |
| Existing ledger access | Separate read-only opener and adapter; no synthetic flag flip, bootstrap or migration |
| Continuity | Fixed persistent enrollment registry with lifetime opportunity key and one authoritative original-entry marker |
| Private content | Proposed fresh format 3; retain exact requests/bindings and append-only captures, never migrate formats 1/2 |
| Owner wire | Propose unchanged corrected `impetus.openai.v1`; local consent/registry fields do not enter the closed request |
| Timing | Prepare within 300 seconds of nominal reminder; launch with more than 30 seconds remaining; cutoff/expiry stays nominal |
| Output | One count, at most one generation, zero tools/retries; every capture selected=false/sent=false |
| Retention | Propose seven days maximum for content copies, with separate longer-lived continuity/accounting metadata and agreed closeout |
| Delivery | Normal delivery neither waits for nor consumes research; its attempts may legitimately change source ledger state |

These are proposed choices for review, not owner-adopted agreements. The seven-day
content limit is a consent requirement to implement and agree before enrollment;
current worker commands do not implement a purge promise. An operator who wants
a different data scope or retention period should amend this draft before code.

## Concrete operator journey after offline implementation

1. Establish the deployment-designated registry and continuity history through
   an explicit first-use operation. Register one source key and its exact private
   content/owner store pair. Existing known keys resolve their original records;
   unknown history, a missing expected store or an old restored registry disables
   new admission. An empty worker read is not permission to start over.
2. With separate permission to read the selected real reminder, prepare a local
   read-only preview. Show the exact model-visible context/objective and the local
   source references, current owner, eligible opportunity, definition/disclosure
   pins, provider/configuration/prompt, both disclosures, budgets, cutoff and
   local/provider retention assumptions. Reject unsupported prose/ownership/data.
3. Persist the exact original request bytes, newline-inclusive digest and immutable
   source/disclosure/configuration bindings in the new private sidecar. Pin them
   in the existing registry enrollment. Obtain explicit consent for those exact
   bytes and retained-review policy while the launcher remains disabled. Never
   copy real values into a tracked example or an unapproved review destination.
4. After a separately authorized one-off execution, recheck the approved bindings,
   source and ordinary eligibility. Atomically consume consent/launch in the
   registry, then invoke only those stored bytes through the trusted launcher.
   The independent worker records its claim/reservations before count/generation.
   No source transaction stays open across this process.
5. Retain invoke output and credential-free readback for all outcomes. Record
   content freshness, ordinary eligibility and execution status separately; never
   relaunch for a missing response. Current source access is optional for retained
   execution retrieval, but required for a positive current freshness assertion.
   Local payload display additionally needs retained-review consent; revocation
   or expiry leaves status/accounting-only review.
6. Review the nominal approved reminder alongside any independently authorized
   actual ordinary-attempt evidence. Label missing/changed baseline, no_addition,
   usefulness, tone, repetition, unsupported claims and lateness. Do not create an
   ordinary attempt just to populate this review. Close the pilot without opening
   another opportunity.
7. Before the agreed content deadline, perform the owner-agreed, separately
   authorized closeout: reconcile local process state, preserve conservative
   accounting and irreversible retired metadata, then remove the explicitly
   inventoried experiment content copies. Source ledger data is untouched. Keep
   the enrollment retired even if content removal is incomplete. Do not promise
   secure deletion of unknown WAL/export/backup copies or upstream provider data.

No actual command syntax is reserved here. An eventual CLI/library manifest must
be closed, versioned and tested; a filename or unchecked JSON field cannot grant
authority. A proposed consent record needs these groups of fields:

| Record group | Required binding |
| --- | --- |
| Selection | Actual namespace, item/version, work/opportunity/policy, actor and resolved owner |
| State continuity | Fixed registry identity, enrollment ID, content-store identity, owner locator/file identity and namespace |
| Exact disclosure | Original request SHA-256, source/disclosure hashes, approved primitive field/revision allowlist, exact preview hash |
| Execution | Complete wire/schema pin, trusted code/launcher descriptor, configuration encoding/revision, prompt, count requirement and admitted exposure |
| Consent/lifecycle | Approval revision/time, entry expiry by cutoff, revocation state, separately bounded retained-review access/expiry and retention-policy revision |

Identifiers and hashes do not authenticate the actor, erase sensitivity or make
snapshot disclosure revocable after entry. Keep launcher/configuration locations
in private trusted configuration; credential values/locators never enter these
records. The first offline implementation should codify the proposed fields and
state relationships as machine contracts before adding runtime behavior.

## Offline implementation acceptance oracles

Use disposable ledgers, fake clocks, mocked provider transports and the independent
Impetus subprocess only. Do not reuse the retained SPINE-071 trial stores or a
real operator ledger. The following IDs are proposed test oracles, not existing
test results:

| Oracle | Required proof |
| --- | --- |
| RP-01 — Read/owner boundary | Missing file/identity/schema, group/unknown owner, unapproved actor, recurrence/task/all-day/stale or attempted work refuses before export/entry; no source initialization or writes |
| RP-02 — Prose and field disclosure | Notes/routes/people/location/reference data cannot reach provider bodies; primary location and detail-bearing presentation are refused; unapproved facet field/value/revision fails |
| RP-03 — Exact consent | Missing/revoked/expired consent or changed request newline, source/version, disclosure, code/config/prompt pin prevents entry; sorted-key config digest cannot substitute for owner insertion order |
| RP-04 — Provider payload | Actual mock adapter receives only approved objective/context in both operations, including explicitly approved facet revision IDs; work/source_refs/registry/consent metadata remain local |
| RP-05 — Identity | Renaming pilot/profile, changing prompt/model/transport or reopening stores cannot create new work for an opportunity; a successor work/opportunity is not auto-selected |
| RP-06 — Continuity and concurrency | Unknown prior history, missing/replaced/rolled-back expected state and duplicate enrollments fail closed; racing launchers yield at most one original invoke |
| RP-07 — Partial preparation | Crash after enrollment, request persistence or registry pinning resolves original bytes or stops; never silently reconstruct/replace a frozen request |
| RP-08 — Launch loss/restart | Crash after registry marker before spawn, during/after count, during generation and lost stdout leaves launch consumed; read/recovery cannot resume research |
| RP-09 — Counting/execution | Context addendum/no_addition, count failure/over-limit/mismatch, unknown usage, ordinal-2 late observation and invalid execution references retain current owner meanings and reserves |
| RP-10 — Time edges | Preparation/launch windows, completion-before-observation and microsecond cutoff edges remain strict; late read retains facts without claiming cutoff usability |
| RP-11 — Drift/revocation | Relevant edits/revoke before marker refuse; after marker stale/unusable capture retains original execution and acknowledged cancellation limitation |
| RP-12 — Read without source/secrets | Stored identity/version/digest/config/prompt permit execution retrieval without source/config/credentials/live flags; no current freshness is invented and revoked review hides payload |
| RP-13 — Ordinary delivery | Ordinary worker proceeds while research waits/fails; fake ordinary delivery may advance work/write attempts; pilot itself issues no source writes/attempts and no generated bytes enter delivered content |
| RP-14 — Baseline truth | Nominal preview remains labeled; actual ordinary body is read only from authorized retained attempts; missing/changed baseline is not replaced or sent to provider |
| RP-15 — Retention/retirement | Before content removal, retire authoritative enrollment and preserve owner-agreed conservative exposure; expired review becomes metadata-only; missing/deleted payloads never permit another invocation |
| RP-16 — Existing compatibility | Formats 1/2, synthetic initializers and deterministic vectors remain unchanged; registry/format-3 schemas/resources are separately pinned; ordinary runtime/schema/public commands are not implicitly activated |

Verification should include contract/resource parity, connected pilot/synthetic
regressions, normal reminder/rendering/delivery regression, required repository
checks and installed-package boundary checks if the existing environment supports
them. Report actual commands/totals/skips and pre-existing typing/deadline issues.
No real-source or paid-provider call is necessary for these oracles.

## Bounded Impetus scope/retention handoff

This note is prepared for operator forwarding; nothing has been sent externally
and no Impetus file is changed. Inspect the owner at checkpoint
`5ff3c0c4530fe07e81cc9067eddadd967a90acc4`, including
[the model adapter](../../impetus/specs/openai-model-adapter.md),
[local binding](../../impetus/specs/local-experiment-worker.md),
[broader experiment retention requirement](../../impetus/specs/contextual-notification-experiment.md),
and complete schema `contracts/schemas/contextual-notification-openai-v1.schema.json`,
SHA-256 `bf3d132392c41ab21e9f7bf44f765aa79799a8dd41f8666d1d39ad646c442c4b`.

Ask the owner to decide these exact points before real enrollment:

1. Confirm that one explicitly authorized real, non-sensitive event opportunity
   and its actual namespace/IDs may use the existing context-only counting wire.
   Schema validation and a synthetic success alone do not establish this scope.
2. Agree the seven-day experiment-content limit and retained local-review access.
   Confirm which owner raw/request/result/config/export/WAL/backup copies exist,
   and whether trusted-operator retirement of the isolated one-run store is
   supported or needs a bounded owner-owned procedure. No producer SQL edits by
   Spine, automatic purge claim or new response disposition is assumed.
3. Specify the minimal owner-approved accounting/continuity receipt that survives
   content retirement without releasing unknown count/generation liability or
   resetting UTC-day exposure. Whole-store deletion cannot silently erase admission.
4. Confirm the no-reset/no-repeat and namespace/store-binding assumptions, including
   startup/read/recovery after store loss or retirement. Proposed filesystem identity
   is operator trust evidence, not a producer-issued store UUID or rollback proof.
5. Return the accepted operating decision and exact document/schema/runtime pins.
   If any change to owner wire or supported operations is required, identify it
   explicitly for a separate owner task and Spine repin; do not infer adoption.

This is not a request to run a provider, inspect credentials or real source data,
implement general retention/recovery infrastructure, or modify the Spine checkout.
The schema appears reusable; owner scope/retention agreement is still necessary
even when its digest/version remain unchanged.

## Next selected work and activation boundary

First review/accept the Spine-owned draft choices and obtain the bounded owner
decision. Then separately select closed machine-contract/vector work and the
offline implementation. Owner retention support is a prerequisite for actual
real enrollment; offline fake-data development must not be advertised as that
support. No deploy/runtime/public-command version is selected by this design.

An eventual real trial needs its own operator-selected reminder, local read
permission, exact disclosure/retention consent, qualified provider/account terms,
budget/cutoff, continuous store pair and explicit one-invocation enablement.
No earlier synthetic approval, current design request or successful mock test
authorizes that real-data disclosure. Broader sampling and generated delivery
remain separate work.
