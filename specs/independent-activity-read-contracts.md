# Independent Activity Read Machine Contracts

Status: Contract codification v1; accepted read design; runtime implementation pending
Updated: 2026-09-16
Authority: [Independent activity reads](independent-activity-reads.md)

This companion closes the wire-level choices of the accepted read design. It does
not advertise a running endpoint. The existing v1 API, command registry, schema pins,
CLI, write resolvers and persisted identity names remain unchanged. The new schemas
are deliberately separate from canonical command output schemas.

## 1. Transport and exact registration

The closed [read registry](../contracts/spine.trusted-web-read-registry.v1.json)
is authoritative for paths, HTTP methods, request/response schemas, result tags,
guards and includes. The two command routes and agenda route accept JSON objects
with `contract_version=spine.trusted-web-api.v2` and `request`. Optional guards are
outer fields; the inner request is untagged. Agenda rejects singular item/recurrence
guards at either level, even for one selected item. No command ID, actor, owner
override, DB path or authorization claim is accepted. Read requests make no durable
receipts or other domain writes.

Selected-identity admission, Origin/CSRF protection, trusted deployment mode,
request limits, no-store responses and generic pre-admission denials inherit the
v1 transport rules. Success uses `identity_basis=self_selected`: this is not proof
of authentication. Identity revisions in the success envelope are server-derived.
`account_subject_binding_revision` maps the existing persisted identity-binding
revision, never a temporal-binding revision. All new families are exact-match;
there is no silent v1 fallback and no v2 write endpoint.

`GET /api/v2/read-capabilities` requires selected-identity admission and returns
the closed registry projection in its schema. It reads no item graph and gives the
same capabilities for every admitted identity. It is independent of hidden content.
An implementation must either support this complete initial registry or leave v2
unadvertised. Registry and transitive schema bytes must match the new pins. Do not
modify v1 pins to admit v2. Packaging/runtime declarations wait for implementation.

## 2. Closed projection and temporal mapping

[Shared types](../contracts/schemas/trusted-web-read-types.schema.json) close every
returned object. [Projection rules](../contracts/trusted-web-read-projection.v1.json)
map every core and section field to its authority. A definition's property list is
the complete allowlist, not permission to serialize an underlying domain object.
Apply the declared predicate before row selection and pagination. Unknown protected
reference semantics fail closed by excluding that row; never assume parent read
permission authorizes an independently governed reference.

Core `detail_status` is current event/task detail lifecycle. The root title is the
current item-version title. Occurrence title is the effective authorized title after
canonical overlays (base title when no title overlay applies). Occurrence IDs, keys,
expressed schedule key, versions, lifecycle and actionability are copied from the
canonical expansion, not re-derived by this projection. Canonical occurrence and
expressed-schedule keys are opaque engine encodings, not resource IDs: they are not
subject to the generic 256-character ID limit. Their shared schema type and cursor
ordering slots retain the exact engine bytes, bounded by the overall response/cursor
byte ceilings. This unadvertised schema correction was established with real ledger
expansion during the 2026-09-18 internal assembly slice. The `range_basis` in each
occurrence must equal the request/result basis. Recurrence identity is null only
when the readable item has no recurrence; unknown required source time does not
erase an otherwise readable root's recurrence identity.

`time.anchors` strips provenance and reference IDs. Anchor roles are unique, ordered
`event_start`, `event_end`, `task_due`, `task_defer_until`; an event has only event
roles and a task only task roles. Available event time requires its start. A task
may expose due and/or defer time, but only a resolved due anchor places it in agenda.
End/defer absence means no applicable authored
anchor, not a fabricated value. All required anchors resolve together or the whole
time is unavailable. Local-date anchors carry the canonical date and pinned zone;
local instants also carry resolved UTC and canonical ambiguity resolution. UTC
anchors omit zone facts. Window bounds are canonical resolved UTC bounds, with
the pinned zone also present for local windows. Bounds must be strictly increasing.
Local dates/date-times require real Gregorian dates, not merely matching a regex.
V2 validation MUST assert the schema's `date`, `date-time`, and
`spine-local-date-time` formats, including through nested and union references.
`spine-local-date-time` means exactly `YYYY-MM-DDTHH:MM:SS`, a real proleptic-Gregorian
date in years 0001–9999, and a 00–23/00–59/00–59 clock, with no offset, suffix,
fraction, rollover or timezone inference. Leap years follow the Gregorian rule
(divisible by 4, except centuries not divisible by 400). A validator that ignores
formats or does not recognize this format is not a conforming v2 validator and
MUST NOT admit the contract as supported. The static test checker is the executable
reference oracle; runtime integration of that mandatory assertion remains pending.
The rule covers request/result range endpoints, original/expressed scheduled facts
and cursor ordering facts wherever they reference the shared type, not just anchors.
No offset, stored-source ID or last-known due time escapes unavailable time.

An occurrence always has available time. Its item/type/current version and recurrence
IDs must match the admitted root; its effective lifecycle/time/title may differ.
Cancelled/completed occurrences are not actionable. Archived roots likewise cannot
produce actionable occurrences. Do not discard valid excluded/nonexistent-date
omissions or change canonical expansion semantics. Direct occurrence reads of a
non-recurring item fail generically as `domain_failure`; the unavailable-series
success branch applies only to a readable recurrence root with unresolved own time.

Agenda `activity` is the canonical root core, but its `time` is the effective entry
time for a recurring entry. `occurrence` is required and non-null for recurring
entries, null for single items. The entry's anchor role matches its item type.
Canonical agenda view-time conversion supplies view date/time, all-day flag,
`sort_at_utc`, start and end. `end_at_utc=null` means no end for a point event;
date/window bounds retain domain-defined exclusive-end semantics. These view
instants are never written back to source anchors.

No unrestricted diagnostics, rendered messages, source arrays, raw receipts,
owner details, provider payloads or full recurrence authoring objects are released
in v2. This is a supported projection, not a partial canonical v1 response.

## 3. Context and receipt selection

Schedule detail always includes all eleven named section states. Omitted includes
mean `not_requested`, not an empty query. Available collection rows use the declared
section key order and authorized-only continuation; available singleton absence
is null. An inaccessible row is not an unavailable section. Unknown includes fail.

Agenda has four fixed singleton section states: `primary_location`, `policies`,
`work`, and `attempts`. The latter three contain authorized-only count/status buckets
over the same row predicates as detail. Their count equals the sum of all buckets.
Zero authorized evidence produces zero buckets, not null. They summarize the item
root, not an individual recurrence occurrence; an occurrence page may repeat the
same item summary. Policy presence does not prove expansion, materialization or
delivery. Attempts are separate from work, and only succeeded attempt evidence
supports a delivery-success claim. No next-opportunity calculation is added here.
Other detail sections are available through the separate schedule view. This avoids
nesting per-item collection pagination inside agenda pagination.

Receipt projection uses existing `command_receipts.item_id` indexed selection,
restricted to successful item-creation commands listed in the projection artifact.
Verify persisted result identity facts establish creation of this item, not a mention
or later update. Compatible replays point at the original receipt, not new candidates.
Authorize candidates before selection; deduplicate by receipt ID, order by
`created_at_utc`, then receipt ID, and select the first. Selection does not use the
v1 command-priority shortcut. All fields of the selected summary share this predicate.
If the receipt ID commits to protected facts that cannot be disclosed, omit that
candidate. No disclosed candidate means available null, whether missing or hidden.
Do not include command IDs, semantic hashes, original request/response, nested
resources or actors. Reads never synthesize a new receipt to fill this section.

## 4. Normalization, bounded selection and continuation

[Normalization](../contracts/trusted-web-read-normalization.v1.json) declares exact
defaults, set-array ordering, query-hash fields and budgets. Reject duplicate values
in set arrays. Do not trim IDs or normalize Unicode. Preserve null guards explicitly
in hash preimages; omitted request defaults are materialized before hashing.
Exclude transport cursor fields from the query hash, but include every other
normalized request fact and the three nullable outer guard slots (agenda's two
inapplicable slots are null, never accepted input). Limits cannot change mid-query.
V2 agenda requires a concrete pinned tzdb version; `system_current` is rejected.
The client can obtain the concrete version from existing context/system discovery.

Ranges are half-open. Occurrence endpoints must match the recurrence time basis
exactly and obey the existing 3660-day rule. Agenda obeys its 31-local-day cap and
canonical timezone ambiguity/invalid-local-time rules. Unknown requested item IDs
are admitted individually: an explicitly selected unavailable ID produces the same
generic resource denial as a direct read, not an existence-bearing per-ID result.
Non-temporal filters precede expansion and unplaced classification. A truly
unscheduled item is omitted from agenda, not put in `unplaced_items`.

Core and optional budgets are separate. Byte/VM/row ceilings in the normalization
artifact are hard maxima, not permission for hidden-row scans. Maximum returned
rows are 100 (default 50), shared by agenda entries plus unplaced cores. A section
limit applies to each requested detail collection. Whole-query temporal coverage
is incomplete if any authorized candidate is unplaced, even on a resolved-only
first page. Unknown-time roots cannot displace resolved entries ahead of them.
Root budget failure is `capacity_exceeded`; a bounded authorized optional computation
may instead return `context_unavailable`. Hidden membership cannot decide either.

Section cursors appear only for included collection names in `section_cursors`.
All supplied section cursors must share the same original query, source snapshot,
issuance and expiry. Other included sections start at their first page within that
same snapshot; previously supplied cursors may be repeated to keep those pages.
Returned cursors are present exactly when more rows remain. `has_more=false` means
`next_cursor=null`. Empty pages cannot claim more rows. Agenda emits all resolved
entries in canonical agenda order, then unplaced cores by item ID. Its one limit
counts both lists; coverage does not stand in for pagination.

## 5. Cursor and freshness contract

[Cursor protocol](../contracts/trusted-web-read-cursor.v2.json) and
[payload schema](../contracts/schemas/trusted-web-read-cursor.schema.json) define
the independent v2 encoding and closed stream-specific ordering tuples. The MAC
uses standard HMAC-SHA256 over domain-separated canonical JSON bytes. This is
integrity protection, **not encryption**: every payload field must be safe to disclose.
The fixture key is public and must never be installed. V1's codec is unchanged.

The cursor artifact also pins selected-identity encoding. The existing persisted
account-subject binding revision maps directly to `account_subject_binding_revision`.
Subjects have no persisted numeric revision. `subject_revision` is an opaque
content revision: take SHA-256 of Spine canonical JSON
`{contract_version: "spine.trusted-web-subject-revision.v1", subject}` with the
selected subject's six fields (`subject_id`, `subject_kind`, `display_name`,
`status`, `created_at_utc`, `updated_at_utc`), interpret the digest as an unsigned
big-endian integer, add one, and encode as positive decimal. It supports equality
only, not chronological ordering; it is neither a ledger counter nor a temporal
binding revision. The selected subject is authorized identity evidence. No other
subject or arbitrary metadata may enter this fingerprint. A computed vector pins
the encoding; private fences additionally compare the complete canonical row.

Continuation retains a bounded private proof in service-local volatile memory,
never the assembled response or an authorization bypass. Every page reassembles
authorized facts and runs the fresh release fence. The family key hashes the closed
cursor payload without `stream` and `last_key`; all other fields remain bound.
Keep at most 128 families and 8 MiB of serialized private proofs per service
instance (deployments may lower these limits). Prune at original expiry or an
earlier authorization deadline. Live families are not evicted to admit new ones;
exhaustion fails with `capacity_exceeded`. Never replace a different private proof
under the same public family. A missing proof, including process restart or a
request reaching an instance without it, yields `access_changed` and requires a
fresh query. There is no stateless fallback or durable cursor cache. Key rotation
invalidates old signatures under the normal codec error rule.

`query_hash` is SHA-256 over the exact normalized query preimage. For
`source_snapshot_hash`, use Spine canonical JSON with this exact object:
`{contract_version: "spine.trusted-web-read-snapshot.v1", route, query_hash, facts}`.
`facts` contains unique `{kind, id, value_hash}` records sorted by `(kind,id)`;
`value_hash` is SHA-256 of the relevant authorized value's canonical JSON.
Kinds and value projections are:

| Kind | ID / hash-bearing value |
|---|---|
| `item` | Authorized candidate item ID / its closed core |
| `recurrence` | Authorized recurrence revision ID / canonical normalized recurrence set |
| `temporal_source` | Necessary authorized source item ID / source core |
| `temporal_binding` | Authorized required binding ID / current canonical binding revision |
| Section name | Authorized row's canonical JSON ordering-key array encoded as a string / its closed projected row; singleton key is root item ID |

Only requested sections enter the snapshot. For agenda summaries use the matching
authorized projected evidence rows, not just their aggregate count. Include the
entire authorized candidate membership for the query, not only the emitted page;
include relevant authorized temporal proofs. Null/empty sections add no row record.
Unavailable time is already hash-bearing in the item core. Do not hash inaccessible
source IDs, inaccessible binding revisions, hidden row counts or excluded followers.
If relevant canonical proof contains additional protected references, it cannot be
hashed for public release until those facts are authorized; otherwise time/row
availability follows the parent contract. Hashes are not a redaction mechanism.

Private release checks additionally cover account/subject/binding revisions,
ledger/realm/recovery epoch, access epoch, and all authorizations used, including
potential newly visible candidates and time-triggered grant transitions. Freeze
`authorization_evaluated_at_utc` at initial selection; the nullable validity deadline
is the earliest relevant activation/expiry across candidate admission and dependency
checks. Do not expose which grant causes it. Null means no known timed transition,
not permission to skip release checks. Query source and authorization fences run
on the first page as well as continuation. Required proofs that cannot be completed
within the bounded budget fail closed; no mixed or guessed snapshot.

Fixed expiry is at most 900 seconds after original issuance; continuation does not
renew it. Every request independently validates signature, query, identity, current
authorization and authorized source state. Fresh changed direct versions produce
`version_changed`; changed continuation/agenda state produces `access_changed`.
Root admission precedes revealing any version mismatch. Invalid selection retains
the admission denial rather than optional-section unavailability. Codec failures
and cross-route/section/root tokens yield `invalid_request` without parser details.

## 6. Failures, fixtures and delivery gate

The error schema has closed generic codes and fixed non-disclosing text. HTTP status
is 400 for `invalid_request`, 404 for `resource_unavailable`/`operation_unavailable`,
403 for `identity_unavailable`, 409 for `access_changed`/`version_changed`, 503 for
`capacity_exceeded`/`admission_unavailable`, and 422 for `domain_failure`. No raw domain
errors, hidden current versions, partial core, hashes or source IDs accompany failures.

The [fixture manifest](../contracts/independent-activity-read-fixture-manifest.json)
separates schema-valid examples, invalid shapes and the pending IR-01–IR-16 runtime
matrix. Example occurrence IDs are placeholders for wire-shape checks, not claimed
canonical identity derivation vectors. Computed normalization and MAC vectors pin
bytes separately. Static semantic oracles cover cross-field constraints that JSON
Schema cannot express; they are not authorization, concurrency or HTTP tests.

Before runtime: review this codification, assess query/index migration requirements,
implement snapshot/release checks and resolvers, then satisfy all behavioral oracles
with real domain fixtures. Only then package/pin/advertise v2 and update Kinflow.
No schema acceptance test substitutes for the unchanged-v1, non-disclosure, time
freshness, write-isolation and no-durable-write behavioral tests.
