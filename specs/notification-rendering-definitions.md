# Spine Notification Rendering Definitions

Status: Draft v0.1.2 — bounded-audit manual corrections; not ratified or implemented
Created: 2026-10-03
Updated: 2026-10-03
Scope: Owner-scoped declarative rendering definitions, explicit facet-field selection,
profile/policy snapshot application, disclosure boundaries, and attempt-time evidence

## 1. Purpose and authority

Ordinary reminders can already describe an item's title, target time and primary
location. Typed facets can hold useful additional facts, such as a flight number or
terminal, but the implemented renderer does not consume them. This proposal adds
explicit, deterministic presentation of selected facet values without turning facet
schemas into message templates or notification profiles into executable programs.

This is the logical owner of the proposed extension. Requirements below are design
targets, not additions to current closed request schemas or runtime capabilities.
The agreed product directions and remaining implementation gates are in Section 12.

Existing authorities remain:

- [notification-rendering.md](notification-rendering.md): ordinary prose, time/locale
  rules, adapter boundary, immutable attempt evidence and replay.
- [notifications.md](notifications.md): policy, opportunity, work, eligibility,
  reconciliation, late handling and attempt admission.
- [notification-profiles.md](notification-profiles.md): reusable authoring templates,
  catalog ownership and snapshot application into item-owned policies.
- [archetype-facets.md](archetype-facets.md) and
  [archetype-facet-storage.md](archetype-facet-storage.md): definitions, typed values,
  immutable historical decoding and item-version snapshots.
- [permissions.md](permissions.md): resource access and the distinction between
  reading data and releasing it to a destination.
- [STORAGE_ATOMICITY_SPEC.md](STORAGE_ATOMICITY_SPEC.md): persistence and transaction
  authority; this draft does not select new SQL tables or a ledger schema number.
- [agent-command-contract.md](agent-command-contract.md): command admission,
  version checks, audit, receipts, replay and dry-run.

Spine owns validation, storage, resolution, rendering and evidence. Spine Packs may
distribute definitions and references as installation inputs to public commands.
A pack is neither a renderer nor a runtime plugin. Its installer and manifest
extension require a separate downstream contract; this draft does not change them.

## 2. Preservation invariants and non-goals

1. A notification policy determines when and where a reminder may be attempted. A
   rendering definition determines only which approved details appear in its body.
2. Existing unselected reminders retain the current renderer, exact output rules and
   evidence semantics. No pack installation or runtime upgrade enables detail output
   implicitly.
3. Defining or publishing a rendering does not change item state, schedules, profile
   applications, policies, work or attempts. Applying a reference is explicit.
4. Facet edits remain item-version edits. They do not create notification opportunities,
   resend delivered work, or independently materialize/cancel reminder work.
5. A rendering may not replace canonical target time, primary location, item title,
   ownership, recurrence, route or lifecycle truth with facet values.
6. Work retention does not authorize stale data use. Rendering resolves current facts
   at attempt start and preserves the existing admission checks.
7. There is one external send path and one canonical `side_effect_attempts` ledger.
   Optional-detail failure does not create a second fallback work item or send.
8. Exact-definition pinning and immutable attempt evidence prevent catalog changes
   from reinterpreting historical messages.

Excluded from this first extension: LLM generation; advisory activation; external
lookups; executable templates; arbitrary JSON paths, expressions, loops or scripts;
per-occurrence facet overrides; automatic field discovery; custom time formatting;
localization beyond the existing renderer; and changes to pack-managed user data.
The governed [contextual-advisories.md](contextual-advisories.md) path stays separate.
If that future path selects ordinary fallback, the ordinary rendering selection here
may apply, but it neither authorizes enrichment nor creates another delivery identity.

## 3. Logical catalog

### 3.1 Definition root and revision

A `notification_rendering_definition` root has an immutable ID, immutable owner
(`system|subject|subject_group` with the corresponding owner ID), owner-local key,
`active|retired` status, current revision pointer, and creation/retirement provenance.
Owner plus key is unique even after retirement. System definitions follow existing
read-only system-catalog rules; ordinary operators cannot create them.

Each immutable revision contains its root ID, contiguous revision number, display
name, nullable description, supported item types (`event`, `task`, or both), a pinned
base-renderer contract/profile, ordered field selections and a canonical content hash.
Display metadata is revisioned in this proposal; there is no independent mutable
metadata operation in the first slice. IDs, revision preimages and exact encodings
must be codified before runtime implementation, not inferred from example strings.

Publishing never modifies a prior revision. Retiring a root prevents fresh selection
or application; historical reads and decoding remain available. Existing policies
retain their exact selection. Retirement is not an emergency disclosure revocation;
Section 8 separates those meanings.

### 3.2 Field selection

Each selection has a unique `selection_key`, `facet_key`, exact
`facet_schema_revision_id`, declared `field_key`, and a literal display `label`.
Array order is presentation order and hash-bearing. Duplicate selections of the same
facet/schema/field are invalid. There is no wildcard, latest-revision selector, nested
lookup or cross-item traversal.

The referenced schema revision must exist, belong to the definition's owner in this
first slice, and declare the field. An applicable item must actually hold that facet
key with that exact schema revision. Matching field names in another revision are
not sufficient, even if their apparent types happen to match. A definition may be
reused by several archetypes that bind the same schema; it need not embed an archetype ID.

Proposed first-slice value types are `text`, `enum`, `integer`, `boolean`, and `date`.
One reference type is also supported by this proposal: a facet `reference` field
whose declared target kind is `location`. It may project only that location's
canonical `label`, using Section 6.1. Subject references and other reference kinds,
arbitrary referenced fields, nested traversal and raw-ID output are rejected at
definition authoring. A location remains a reference, never copied into a text field
solely to satisfy this renderer. This restriction does not change which field types
facets themselves support.

All selected values are optional message detail in this first slice. There is no
required-detail mode that cancels an otherwise eligible ordinary reminder. Labels
and text are plain data, not instructions, HTML, mention syntax or adapter directives.

## 4. Bounded declarative rendering

The agreed first form is a detail suffix on the unchanged ordinary body, not a
general string-interpolation language or a replacement for the time/title template.
It produces the ordinary body first using its existing exact rules. For each available
selection in declared order, append ` · {label}: {value}`. If none are available,
the body is byte-identical to ordinary rendering.

Text/enum values and labels use the existing renderer's whitespace normalization and
control-character rejection. An empty normalized value is unavailable. Integers use
their canonical decimal value, booleans use `true` or `false`, and dates use canonical
`YYYY-MM-DD`; no locale, enum-label lookup or timezone inference is added. The schema's
stored enum token is displayed as data. A location reference displays its authorized
canonical label under the same text rules. Adapters retain only their existing
transport-escaping role and must not add facts or reinterpret labels.

Proposed fixed bounds for the first contract: at most eight selections, labels of at
most 40 normalized Unicode scalar values, and at most 120 normalized scalar values
per displayed value. A value above that bound is omitted whole, not truncated. The
complete body still has the ordinary 1,024-scalar limit. If otherwise usable details
would exceed that limit, omit the entire suffix and retain the ordinary body. The
ordinary body itself is never truncated or given weaker validation. Catalog request,
read, transaction and evidence byte/work bounds must also be closed in machine
contracts before implementation; these text limits alone do not bound database work.

Illustrative output, assuming an appropriate current title, primary location and time:

```text
Reminder: Flight to Paris @ Toronto Pearson in 2 hours · Flight: AC872 · Terminal: 1
```

Here `Toronto Pearson` is canonical primary location, not a facet replacing it.
`Flight` and `Terminal` are explicitly selected scalar facet labels. No airport lookup,
live gate assertion or flight-status inference has occurred.

## 5. Profile and policy selection

A future version of notification-profile templates may carry an optional exact
rendering-definition root/revision reference. Each reminder template can select a
different definition, so a week-before reminder and a one-hour reminder can present
different fields. Absence selects ordinary rendering, not an implicit archetype default.

At profile publication, validate reference existence, active root, owner equality,
item-type compatibility and field declarations. At application, repeat applicable
lifecycle/access checks and validate the target archetype's active facet binding and
exact schema revision. Values may be absent: item creation and facet attachment are
currently separate commands. Do not require a populated optional facet at creation.

Applying the profile snapshots the exact rendering selection into each corresponding
item-owned policy's presentation facts and records application provenance. Delivery
must not join to the profile's current revision. Copy-forward preserves presentation
facts explicitly, including explicit ordinary-rendering selection. Direct/custom
reminder policies should have the same selection semantics in the future authoring
contract; profile use must not be the only route to the capability.

Disclosure scope follows each policy's recorded composition origin, not merely the
presence of a profile in the enclosing schedule request:

| Policy origin | Authorization classification |
|---|---|
| Unsuppressed profile template | Profile-scoped to the originating notification-profile root ID |
| Replacement of a named profile template | Profile-scoped to that same root ID; retains exact profile-revision/template provenance |
| Custom addition within a profile-backed application | Direct-policy scoped; does not inherit the enclosing profile's authorization |
| Direct reminder without a profile application | Direct-policy scoped |
| Suppressed profile template | No resulting policy or disclosure application |

In both authorization branches, the actual selected definition, effective fields,
owner, destination and permitted location identities must independently match
Section 8.1. Being a profile replacement does not authorize a different definition
or additional fields. A custom addition cannot claim profile origin by reusing a
template key, copying its schedule or naming the same rendering definition. Record
origin and exact source provenance at authoring and preserve them on copy-forward;
do not infer the branch at attempt start from keys or the current profile catalog.
Policies selecting ordinary rendering require no facet-disclosure authorization.

Installing a definition, publishing a new profile revision, or moving a default
binding never changes existing policy selections. Reapplication or changing the
selection on existing items requires an explicit item-versioned command and normal
freshness, replay and reconciliation. No bulk migration is implicit.

Presentation is not a second timing discriminator: two otherwise duplicate reminder
templates cannot become two sends merely by selecting different renderings. Existing
duplicate-policy validation must remain effective. Explicit presentation-only edits
must not create a new delivery for already attempted or terminal work. The exact
policy hash/copy-forward/work-continuity treatment is a machine-contract integration
gate (Section 12), not permission to alter current identity derivation in place.

## 6. Current values and historical decoding

After ordinary attempt admission, resolve the policy selection and the current item
version's facet snapshot under one consistent ledger view. Decode through the exact
schema revision stored with that snapshot; then check equality with the revision
selected by the definition. Never decode old values using the latest schema.

Record the actual facet binding identity, schema revision, item version and selected
field evidence used. Removing a facet, clearing an archetype, or upgrading a facet
to an unselected schema revision makes the corresponding fields unavailable for
this rendering; it does not reinterpret them or re-enable an old item snapshot.
Historical bindings need not still be active to decode valid retained snapshots.
Catalog retirement alone does not rewrite those snapshots or prior policy selections.

Recurring reminders use the current series item's facet values, not fabricated
occurrence-specific values. Target time still comes from the admitted occurrence.
A bound task uses its own facets, not its source event's facets. Existing follow-source
freshness checks run first and are not weakened by this proposal.

### 6.1 Location-reference labels

Resolve at most one location row by exact primary key per selected location reference;
reuse repeated resolutions within the same consistent attempt-start view. Read only
the canonical `label`. Do not expand address, coordinates, metadata, provider data,
timezone, related records or an external place directory. Never substitute the event's
primary location for a missing facet reference, or use facet locations as time authority.

Use the existing immutable canonical location record, not a new mutable venue entity.
Referenced historical location facts remain decodable under the existing immutability
contract. Replacing a location means an explicit new reference in a new item version;
the renderer neither follows a latest-location alias nor repoints old events. A future
reusable location catalog is separate work, not a prerequisite or implied feature here.

Resolve only after referenced-location read and label-disclosure authority succeeds.
The authorization must cover that location identity, not merely an arbitrary reference
typed as location. Missing, unavailable, unapproved or unauthorized rows omit the
selection without revealing which condition exposed a private resource. An unusable
label follows the optional-text omission rules. Storage corruption and operational
failure are not converted into absence. No raw location ID is printed as fallback.

Record the permitted location ID and normalized label actually used in protected
attempt evidence, alongside the facet's item/schema/binding identities. Because the
canonical location row is immutable, do not invent a location revision identifier.
The already implemented primary-location rendering path stays unchanged.

## 7. Attempt transaction, failure and evidence

The selected definition revision, current policy lineage, facet snapshot and disclosure
decision must be validated inside the existing attempt-start transaction, or rechecked
there if preparation occurred beforehand. A concurrent edit cannot produce a body
from one version and evidence claiming another. Reuse the canonical policy-specific
lineage resolver; shared notification intents are not unique policy identities.

Expected optional-detail outcomes are deterministic omissions: missing facet/field,
schema mismatch, invalid display text, value too long, and disclosure not authorized.
Each selection records its outcome; output-budget overflow records a suffix-level
fallback. These are not successful enrichments. Ordinary admission failures remain
failures: stale work, unavailable pinned time data, invalid base title/location,
route denial, lifecycle denial or expired grace cannot become successful fallback.
Storage errors, corrupt immutable definitions, exhausted transaction budgets or failure
to persist evidence also fail the attempt-start operation; do not mask them as missing
optional detail. Exact closed error/outcome strings are a codification gate.

The rendering and started attempt commit atomically before external contact. A future
versioned rendering evidence shape must include:

- existing base source facts and actual rendered item version;
- exact selected definition root, revision, definition hash and rendering contract;
- ordered selection identities and outcomes, pinned facet schema/binding identities
  where available, and the minimal normalized values actually included;
- applied reusable authorization ID/scope hash, its verified active state at attempt
  start, effective field subset, destination evidence and applicable policy version;
- base-only versus detail-bearing outcome, exact final body, input/content hashes.

Do not copy every facet into evidence, logs, errors or receipts. Omitted private values
must not be retained merely to explain omission. Detailed field outcomes follow the
owning item's read permission; transport errors must not enumerate inaccessible fields.
Readback projects persisted evidence, never recomputes historical prose.

Compatible replay of the same attempt uses its existing immutable body. A genuinely
new retry follows existing attempt-time rendering rules and may observe newer values;
the provider idempotency key and single logical delivery remain unchanged. A provider
may have accepted an earlier body before a timeout, so readback must not claim a later
retry body was necessarily the one seen by the recipient.

There is no new scheduled job, polling loop, durable no-op receipt or second attempt
ledger for this extension. Only selected bounded fields are resolved; no item scan or
per-attempt catalog discovery is permitted.

## 8. Ownership, disclosure and retirement

Catalog read/use/admin follows an explicit future permission mapping independent of
item access. The initial proposal keeps rendering definition, profile and referenced
schema in one owner scope; ordinary group membership is not catalog administration.
Using a catalog does not change an item's owner. Protected web exposure requires
explicit registry/grant mappings and tests; no new web commands are allowed by inference.
The CLI remains trusted-local full scope, not authenticated per-user isolation.

Field selection means that a definition is designed to display those fields. It does
not prove that a particular destination is allowed to receive them. A reused profile
must not silently release private values to every group to which it can be applied.
Authoring therefore needs an explicit disclosure decision bound to the selected fields
and actual recipient/delivery-target context as specified below. Retargeting cannot
carry an old decision forward unquestioned. Attempt start must verify the applicable
disclosure authorization; without it, omit facet detail and preserve only an
independently permitted ordinary reminder. Do not log denied values or infer recipient
membership from a target label. This is not a claim that ordinary reminder delivery
already implements these release controls.

### 8.1 Configure once; record each application

The operator-approved direction is reusable, scoped disclosure authorization, not a
new confirmation for every event or every send. The first contract must represent an
immutable authorization scope with stable identity, issuer/command/time provenance
and `active|revoked` lifecycle. The scope names:

- the explicit item-owner scope in which it applies;
- the exact rendering-definition revision and approved selection keys;
- the stable notification-profile root ID when it is profile-scoped, or an explicit
  direct-policy use scope (omission must not mean all profiles); Section 5 determines
  this branch separately for each policy;
- the exact recipient kind/ID and delivery target, including its channel, adapter
  and destination reference snapshot; and
- for location-label selections, the explicit permitted location IDs.

The same authorization may serve many matching events. Profile application records
the authorization ID and immutable scope hash alongside each policy's selected
definition and effective field subset. The authoring service may resolve a uniquely
matching authorization; missing matches require explicit approval or ordinary-only
selection, and multiple eligible matches require an explicit ID rather than a hidden
precedence rule. Applying a profile is not itself permission to mint an authorization.
The operator's instruction may authorize provisioning and application in one workflow,
but independent commands are not collectively atomic without a separate contract.

The exact applied notification-profile revision and template provenance remain
immutable application evidence, but the profile revision is not an authorization
match key. A newer revision of the same profile may reuse an active authorization
when all disclosure-relevant scope facts still match. Schedule or late-handling
changes alone therefore do not require renewed disclosure approval; they still
require ordinary schedule authoring permission, validation and work reconciliation.
A different profile root cannot reuse profile-scoped authorization merely because
its key or displayed name matches. Existing policies never inherit the new revision.

Authorize field selection, not one scalar value snapshot: corrections to a flight
number or terminal remain covered. This does not permit changing the selected field,
schema/definition revision, profile root/use branch or destination. A changed location reference
must name an already permitted location ID or require a new scoped authorization;
approving a location-label field does not authorize disclosing arbitrary private places.
These exact-match rules favor explicit refresh over implicit compatibility inference.

No authorization is embedded as an operative grant inside a portable pack. Pack
installation may create definitions but requires an independently authorized operator
action to provision destination-specific disclosure. Chat instructions are represented
by the trusted executor under today's attribution posture; the record is auditable
configuration, not proof of independently authenticated human consent.

### 8.2 Per-policy exceptions and lifecycle

An application may explicitly narrow the approved selection keys, including selecting
no facet detail. Record that effective subset with the policy; no new broad grant is
needed for a subset. Additional fields or a different destination need an authorization
covering that scope, even if fewer fields are sent there. For example, permission for
flight details in a family chat cannot authorize even flight-number-only output to a
client chat. Scope never transfers between chats by reducing the field list.

Changing the selection/subset on existing policies is an explicit item-versioned
mutation, not an in-place edit to past application evidence. Authorization scope is
immutable: expanding it creates a new authorization that must be selected explicitly.
Revocation is one-way, auditable and checked at attempt start; it affects existing
policy applications as well as new ones. An application snapshot is evidence of what
was authorized, not an exemption from later revocation. When authorization is revoked,
use ordinary rendering only if ordinary admission still permits the reminder. Do not
resurrect, cancel or duplicate work just to remove facet detail.

Authorization covers the configured destination, not a cryptographically established
roster of its external group members. Spine does not poll WhatsApp membership or claim
to detect external audience changes. An operator who no longer trusts that audience
must revoke or replace the authorization. Changes in Spine's explicit recipient/route
facts are checked locally and invalidate a mismatching scope automatically.

Revocation and attempt-start must serialize: revocation committed first forbids detail
in a new started attempt; an already committed started attempt and its body remain
immutable and cannot be unsent. Preventing provider contact after that committed
boundary would require a separate cancellation contract and is not promised here.
Catalog-use authority, referenced-location read/disclosure authority and authorization
issuance/revocation permissions still require exact machine mappings before exposure.

### 8.3 Retirement is not revocation

Catalog retirement is a ban on new uses, not revocation of existing disclosures.
Emergency removal of detail from existing reminders must use an explicit permission
revocation or presentation-selection change; it must not rewrite already started
attempts. The first contract needs scoped authorization revocation; it does not
introduce a bulk rewrite of policies or cancellation of already started attempts.

## 9. Command and pack boundary

Reserve a conceptual `notification_rendering_definition` command family with create,
publish, retire, show and list operations. These names are proposals, not registered
CLI commands. Writes require exact expected revisions where applicable, command IDs,
actor/time attribution, atomic audit and replay receipts. Publish of equivalent
normalized content and repeated retirement need deterministic no-op semantics. Reads
are bounded, permission-aware on protected transports, and nondurable. Exact envelopes,
effects, pagination, identity preimages and field limits precede implementation.

The same codification must define bounded provision/revoke/show/list operations for
reusable disclosure authorizations and their application evidence. They share common
audit/replay rules but are distinct from publishing a rendering definition. No current
catalog, schedule or permission command accepts these new facts by implication.

Versioned profile and direct-policy authoring contracts must express exact selection
and explicit clearing to ordinary rendering. Existing closed v1/v2 schemas are not
extended silently. The implemented `rendering_profile` constant names an algorithm;
it is not interchangeable with a reusable definition ID or a notification profile ID.

Packs may supply owner-neutral schema definitions, archetype bindings, rendering
definitions and profile references. A future installer resolves pack-local references
to exact Spine IDs, provisions dependencies before references, and verifies canonical
readback. Each command remains its own transaction unless a separate atomic composite
is explicitly contracted. Partial installation is reported and replayed, not described
as globally atomic. Missing dependencies block dependent writes, not ordinary reminders.
Pack upgrades must detect operator divergence and require explicit reconciliation;
they cannot overwrite customizations, grant disclosure, or rewrite live item policies
merely because a bundled default changed.

## 10. Flight example and expected behavior

A pack could supply a `flight_details` schema with scalar `flight_number` and
`terminal`, a flight archetype binding to that schema revision, and a rendering
definition selecting those fields in that order. An installed notification profile
could select it only for the one-hour template while keeping other reminders ordinary.

The reminder still fires solely under its existing offset and late-handling policy.
If the current item has `AC872` and `1`, approved detail appears as in Section 4.
If terminal is absent, only flight number appears. If the facet was upgraded to a
different schema revision, neither field is borrowed from history; ordinary prose
remains until an explicit compatible selection is applied. Publishing a new catalog
revision changes none of these existing reminders. Reference-valued origin/destination
fields may select the referenced location's label under Section 6.1 and the approved
location set, without replacing primary location.

## 11. Verification families required before implementation acceptance

| Family | Required oracle |
|---|---|
| Ordinary preservation | Every existing v1 rendering vector and unselected reminder remains unchanged |
| Catalog lifecycle | Owner/key uniqueness, exact revisions, retirement, no-op/replay and concurrent publish |
| Selection validation | Unknown field, wrong type/owner/schema, duplicate selector and unsupported expressions rejected |
| Snapshot application | Profile changes do not mutate policies; different templates may pin different definitions; exact profile revision remains evidence rather than a disclosure match key |
| Disclosure | One scoped authorization serves multiple events with per-policy evidence; narrowing permitted; changed chat/fields denied without matching authorization; revoked approval never leaks detail |
| Composition origin | Templates and replacements use profile scope; custom additions in the same request require direct-policy scope; copied keys/schedules cannot borrow profile approval |
| Approval reuse | Timing/late-handling-only revisions of the same profile retain matching authorization; changed definition/fields/destination/use branch or profile root cannot inherit it |
| Location labels | Only a single authorized location label is resolved; missing/denied/unapproved reference omits detail; no raw ID, address expansion, new catalog or primary-location override |
| Deterministic text | Ordered scalar formatting, whitespace/control rejection, absent values and all size boundaries |
| Schema evolution | Exact historical decoding, explicit upgrade mismatch, removed facets, retired catalogs and retained bindings |
| Work preservation | Queued/leased/attempted/terminal work across facet and presentation edits; no duplicate opportunities or sends |
| Transaction races | Facet/policy/route/disclosure edits versus attempt start produce one consistent snapshot or rejection |
| Replay and retry | Exact same-attempt body; new retry evidence with unchanged provider idempotency |
| Recurrence and bindings | Current series/own-task fields only; occurrence and follow-source freshness unchanged |
| Failure separation | Optional-detail fallback does not bypass base admission or suppress infrastructure failures |
| Bounds and persistence | Indexed bounded reads, request/evidence limits, migration history preservation and no idle durable writes |
| Pack interoperability | Dependency resolution, partial install/replay, operator divergence and no implicit policy migration |

Fixtures must publish inputs, exact body, omission outcomes and hash preimages/digests,
not merely human examples. Stateful tests must prove negative side effects and race
behavior; JSON Schema validation alone does not establish these properties.

## 12. Decisions and next gates

The operator agreed the following product directions on 2026-10-03:

1. **Disclosure:** configure reusable approval for a defined scope and record its
   application on each event/policy, with explicit exceptions. There is no repeated
   per-send confirmation and no implicit authorization of another destination.
2. **First rendering form:** direct facet values plus the narrow exception of
   location-reference labels. Preserve location references; do not require duplicated
   text or create a new location catalog. Other reference lookup and freeform sentence
   replacement remain deferred.
3. **Lifecycle:** retirement blocks new selection/application; existing pinned use
   remains subject to current disclosure authority. Revocation is a separate action.

These directions do not ratify every technical rule in this draft or make it
implementation-ready. Exact authorization matching, scope/exception/revocation
representation and permission mapping require bounded review and machine codification;
surface any new product tradeoff instead of silently inferring a broader grant.

The first bounded consistency audit returned one major and two minor findings. This
revision manually clarifies composition-origin scope, removes profile revision from
the disclosure match key while retaining it in provenance, and aligns the architecture's
schedule baseline with implemented v2 contracts. These corrections have not received
a reviewer recheck and are not a convergence or implementation-readiness claim.

Next: focused bounded recheck after exact send-scope authorization, then codify
schemas/registry/fixtures and the versioned authoring/evidence integration. Close
exact policy-presentation identity and continuity rules, comparison/no-op semantics,
permission/disclosure mappings, catalog pagination/resource bounds, reference handling,
storage/migration/rollback and version declarations before runtime work. Changes to
definition selection must enter the policy-continuity proof without turning a
presentation change into a new send. Workers lacking the new capability must reject
startup against a release requiring it, not silently ignore populated selections.
No schema number, runtime release, pack version or deployment change is assigned here.
