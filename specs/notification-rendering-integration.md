# Notification Rendering Integration

Status: Accepted v1.0 — ratified specification; not implemented
Created: 2026-10-04
Ratified: 2026-10-04 — operator approval after bounded buildability recheck 003
Scope: Persistence, authoring, continuity, attempt evidence, permissions and bounded reads

## 1. Authority and delivery boundary

[Rendering definitions](notification-rendering-definitions.md) remains the accepted
logical owner. This leaf specifies the engineering closure of its Section 12 gates;
it does not change the accepted product decisions. [Storage and atomicity](STORAGE_ATOMICITY_SPEC.md)
remains the Spine-wide persistence owner. [Notifications](notifications.md),
[ordinary rendering](notification-rendering.md), [profiles](notification-profiles.md)
and [permissions](permissions.md) retain their respective authority.

The clean machine-contract audits establish consistency of the existing source-only
family. Integration buildability recheck 003 passed with zero findings and preserved
boundaries; subsequent operator ratification accepts this design, not runtime behavior.
Runtime 0.8.3/schema 18 implements only the
facet-location prerequisite. No migration number, package release, new web route or
implemented capability is assigned here. No existing closed schema is extended in
place. [The integration matrix](../contracts/notification-rendering-integration.v1.json)
is a source-only companion. Section 11 codifies successor wire contracts and reference
fixtures; their review and executable runtime proofs remain required before activation.
Normative provisions below specify future implementation, not present behavior.

Preserve: ordinary reminder bytes and v1 hashes; one work/opportunity identity per
logical reminder; policy-specific ancestry even for shared intents; current facet
decoding; no automatic new grants; one side-effect attempt ledger; no idle writes.
Neither packs nor notification templates become executable code. No advisory,
general automation, new authentication or shared-location catalog is introduced.

## 2. Versioned integration surfaces

Reserve these successors. They are not added to compiled runtime declarations,
packaged web registries or capabilities by this document.

| Surface | Specified successor | Integration delta |
| --- | --- | --- |
| Profile create/revise/show/list and revision content | `spine.notification-profiles.v2` | Optional template rendering reference, exact revision decoder |
| Profile application/readback | `spine.notification-profile-application.v2`, `spine.notification-profile-readback.v2` | Per-policy presentation pins and separate presentation hash |
| Schedule create/update | `spine.schedule-create.v3`, `spine.schedule-update.v3` | Application selections and explicit policy-presentation edit branch |
| Direct reminder authoring/edit | `spine.notification-schedule-authoring.v2` | Optional direct presentation selection; existing timing identity unchanged |
| Full schedule readback | `spine.schedule-show.v2` | Current policy presentation plus v1/v2 persisted attempt rendering |
| Attempt rendering envelope | `spine.notification-rendering.v2` | Ordinary base plus approved detail evidence in one final rendering |
| Integration capability | `spine.notification-rendering-integration.v1` | Atomic enablement of this complete integration |

Existing metadata-only profile updates, archetype/binding commands, recurrence,
opportunity/materialization and compact/read-only web contracts retain their exact
versions and shapes. An old read projection cannot mislabel v2 rendering as v1:
retain its documented summary/redaction policy, or reject an unsupported full-evidence
projection. No new fields are injected into the frozen web v1/v2 families.

Old authoring requests remain ordinary on fresh creation. When they copy existing
policies unchanged, they must preserve their presentation supporting facts. An old
whole-plan replacement that would remove or change a selected presentation without
expressing that intent MUST fail `unsupported_field`, field `notification_plan`,
with no writes and a fixed upgrade-contract diagnostic. It must not silently clear
details, auto-resolve a new grant or drop sidecar state. Exact stored receipt replay
remains unchanged and must not require today's catalogs to be active.

For `notification_profile.revise`, compatible stored receipt replay precedes all
fresh-execution checks, including the guard below; incompatible command-ID reuse
still fails under the existing replay rules. On fresh execution, perform existing
root/lifecycle and expected-current-revision checks first. If the current revision
uses the v2 decoder, a `spine.notification-profiles.v1` revise request MUST fail
`unsupported_field`, field `revision`, with diagnostic
`Use spine.notification-profiles.v2 to revise a v2 profile revision.`
This includes v2 revisions whose templates are all ordinary and requests that would
otherwise be no-ops. Do not demote to v1, copy pins implicitly, or silently clear them.
No revision, pointer, audit or receipt is written by that failure. V1-to-v1 revision
remains unchanged; a v2 request may revise a v1 or v2 current revision using the v2
normalization/hashes. In v2 complete replacements, omitted template rendering means
ordinary as specified below. Historical v1 hashes and compatible replay never change.
Metadata-only updates and retirement remain governed by their existing contracts.

All writers must understand copy-forward before storage activation, even writers
whose public schema cannot author rendering. A runtime without the integration
capability must reject the activated schema at bounded preflight. Enclosing schemas,
runtime family requirements and release manifests must ship atomically, with old
history decoders retained. This is internal historical decoding, not a second model.

## 3. Authoring and application

### 3.1 Profile revisions and complete plans

V2 profile templates add `rendering` with the closed union `{kind: ordinary}` or
`{kind: definition, definition: <definitionReference>}`. Omission normalizes to
ordinary. They never store disclosure IDs, destinations or effective field subsets.
The existing definitionReference pins root and exact revision. Definition/profile/
schema owner equality and compatibility rules remain logical Section 5.

V2 revision and template hashes use new preimages: respectively
`{derivation_version: spine.notification-profile-revision-hash.v2, canonical_json_version,
revision}` and `{derivation_version: spine.notification-profile-template-hash.v2,
canonical_json_version, template}`. `revision` is the complete normalized revision;
`template` is a normalized template without its derived hash. Neither rewrites v1
hashes. The ordinary effective-policy-set hash still excludes presentation; add a
separate `effective_presentation_set_hash` defined in Section 4.

V3 schedule `notification_plan` and complete replacement plans add an optional
`rendering_applications` array, maximum 32, sorted by `(source_kind, source_key)`.
Each entry is exactly `{source_kind, source_key, selection}`: source_kind is
`profile_template|custom_addition`; source_key is the existing template/policy key;
selection is the existing `authoringSelection` schema. Replaced templates still use
`profile_template` as address; composition derives `profile_replacement` as origin.
No duplicate address, suppressed/missing address or client-supplied origin is legal.

For each surviving profile template whose definition is not ordinary, an application
entry is required: it selects that exact definition with explicit effective keys and
exact/unique-match authorization, or explicitly chooses ordinary. An alternate
definition is allowed only on a named complete template replacement and must pass
fresh definition checks. For ordinary templates and custom additions, omission means
ordinary, while an explicit entry may opt into a definition with fresh validation.
Missing required application is `missing_required_field`; unknown/duplicate address
or incompatible template pin is `semantic_conflict`, field `rendering_applications`.
A missing grant fails authoring rather than silently switching to ordinary.

Suppression, replacements and additions compose first; normalize and reject duplicate
ordinary policies before applying presentation. Two identical timing/target/recipient
policies with different renderings are still duplicates, not two sends. Full-plan
replacement is still full replacement, not a new patch/upsert interpretation.

### 3.2 Presentation-only edit and direct authoring

V3 `schedule.update.patch.policy_presentations` is a nonempty, maximum-32 array of
`{notification_policy_id, selection}`, sorted by exact current policy ID. The branch
is mutually exclusive with all other patch fields and requires materialization mode
`none`. The normal item target-version guard is required; each addressed policy must
belong to that exact current version and be active. Unknown/stale or duplicate targets
fail without mutation. Unaddressed policies copy forward unchanged.

This branch is the ergonomic way to select, narrow, replace a grant or clear details
without reconstructing the reminder plan. `ordinary` explicitly clears; null is invalid.
Resolve selections, preserve origin from exact policy ancestry, compare normalized
presentations and emit one normal schedule receipt. Equal presentations are a no-op;
otherwise create one item version, successor policy rows and supporting sets. Reuse
existing schedule success/no-op effects; additionally report `presentation_changes`,
an ordered array of `{source_policy_id, policy_id, before_hash, after_hash}` in the
v3 response. No changed rows means an empty array. No presentation edit sends or
retries a notification, renews a lease or creates absent work.

Direct reminder v2 create/edit adds `presentation: authoringSelection` inside the
notification authoring object, identified by its `authoring_contract` selector. Fresh create
omission means ordinary and origin `direct`. Edit omission retains; explicit ordinary
clears. An edit of an existing profile-derived policy preserves its recorded origin;
it does not rewrite application history or become profile-derived by naming a key.
Disablement copies presentation unchanged into the disabled successor. Reapplying a
profile is a distinct operation that can produce new origin evidence.

Every path checks adopted item ownership for selected details, including trusted-local
authoring: use `item_access_owners`, never recipient, actor or participant inference.
An unadopted item can keep ordinary reminders, but selecting detail fails
`rendering_disclosure_unavailable` until explicit ownership adoption. This adds no
implicit adoption inside schedule commands. Composite rollback includes profile
application, policy presentation, materialization, audit and receipt.

### 3.3 Fresh trusted-local creation and explicit adoption

This slice does not add an owner input or ownership establishment to the trusted-local
schedule-create command. Fresh trusted-local creation is therefore **ordinary-only**:
a definition selection fails `rendering_disclosure_unavailable` before any durable
item, policy, work, audit or receipt commit. A profile containing definition pins may
still be used at creation, but every surviving pinned template must have an explicit
ordinary application entry under Section 3.1. Never infer an owner from that profile.

`materialization=none` suppresses only the invoking command's work creation. It is
not a scheduler hold. Automatic planning can materialize missing actionable work for
the committed active policies regardless of pending ownership adoption or presentation
setup. Without an operational exclusion, an ordinary reminder may start between any
two setup steps, including for a reminder already due within its late-delivery grace.

If details must be configured before any reminder can start, the operator MUST establish
and verify an operational exclusion of concurrent materialization **before creation**
and retain it until the presentation edit commits. This includes automatic schedulers,
other explicit materializers and their in-flight operations: for example, quiesce the
relevant worker/scheduler processes and exclude other materializing callers. Merely
requesting a stop, omitting initial work, or relying on an unadopted owner is not proof
of exclusion. Keep the exclusion through step 4 when explicit materialization is to
control readiness, allowing only that designated materialization. This is an external
operational precondition, not an implicit command lock or new durable hold state.
If exclusion cannot be verified or is lost, no details-before-delivery guarantee may
be claimed. This amendment authorizes no automatic service stop/restart.

The supported detail-enabled setup sequence, subject to that ordering qualification, is:

1. Create the item with ordinary presentations and materialization mode `none` to
   avoid work creation by this command; this does not exclude automatic scheduling.
2. Explicitly adopt the created item's exact current version into a subject/group
   owner using the existing trusted-local ownership provisioning boundary in
   [the web API specification, Section 4](trusted-multi-operator-web-api.md).
   Adoption is not ownership transfer and grants no inferred creator entitlement.
3. Read the current item version/policy IDs and apply the Section 3.2 presentation-only
   edit against that version, resolving the exact definition/disclosure. This edit
   still requires materialization mode `none` and creates no work.
4. When delivery is wanted, invoke the existing bounded notification-work
   materialization command explicitly and verify the resulting work/readback.
   Release any operational exclusion deliberately after the required setup succeeds.
   Normal current-time/late-handling eligibility still applies; setup delay neither
   extends grace nor creates a guarantee that an expired opportunity will be delivered.

These are separately receipted transactions, not one atomic composite. If adoption
or selection fails, the already created item remains ordinary; do not auto-delete it
or claim the entire sequence rolled back. If strict ordering was required, do not
automatically release the exclusion on failure: the operator must finish setup or
explicitly accept ordinary delivery before resuming materialization. Retrying uses
each step's own command ID and current-version checks. If ordinary work was already materialized, existing
attempt/continuity rules apply; later setup cannot retract an already started send.
Protected creation's existing envelope ownership orchestration is not removed, but
this amendment neither activates rendering there nor extends its registry. An atomic
trusted-local owner-plus-rendering create would require a separate explicit contract.

## 4. Identity, copy-forward and work continuity

Presentation is an immutable supporting fact of a versioned policy, not a new policy
timing discriminator. `presentation_hash` is SHA-256 of canonical JSON exactly:
`{derivation_version: spine.notification-policy-presentation-hash.v1,
canonical_json_version: spine.canonical-json.v1, presentation}`. `presentation` is
the resolved existing policyPresentation union, including ordinary explicitly.
No command ID, policy row ID or item version is added to this content hash.

`effective_presentation_set_hash` hashes exactly
`{derivation_version: spine.notification-presentation-set-hash.v1,
canonical_json_version: spine.canonical-json.v1, entries}`. Entries are
`{notification_policy_id, presentation_hash}` sorted by policy ID. This is a version's
snapshot hash, not a cross-version delivery identity. Neither hash enters existing
intent, schedule, slot, opportunity, work or provider-idempotency preimages.

Copy-forward must produce exactly one presentation for every successor policy,
including disabled and ordinary rows. Compare each successor to its explicit immediate
`source_notification_policy_id`; require same item and intent, decreasing ancestry
versions and no fork. Do not join by intent alone. Profile-plan replacement can retain
an old policy's delivery lineage only through the existing unique ordinary-semantic
match plus exact ancestry; ambiguity is a conflict, never a guessed match by title,
key, equal eligibility time or shared intent. Presentation must not break an otherwise
valid ordinary match. A changed schedule/route/target still uses existing reconciliation.

For a presentation-only change, prove the prior/current policy bijection and equality
of all comparison fields in `spine.facet-notification-continuity.v1`: intent creation
facts, status, recipient, channel, target, route, schedule hash and late handling.
Also preserve target snapshots, recurrence and temporal-binding freshness. Source
row/version IDs may change; old work FKs may not. Fail the transaction on a broken
proof. This is a bounded selected-item proof, not a scan of every work row in history.

| Work state | Presentation/facet-only change |
| --- | --- |
| Eligible, no attempt | Retain work identity; attempt resolves current descendant and presentation |
| Leased/in progress, no started attempt | Preserve lease/state; fresh fence before attempt commit |
| Eligible retry | Preserve retry and provider key; a new attempt may render current values |
| Started attempt | Immutable body/evidence; later edits or revocation cannot unsend it |
| Terminal | Preserve outcome and history; no new opportunity or resend |
| Independently stale | Existing stale-work handling; presentation cannot bless it |
| No work exists | Do not materialize in a presentation-only operation |

The same rules apply after multiple copy-forwards, with shared-intent policies and
recurring/follow-source items. Worker and scheduler must use the same current-descendant
resolver. Disclosure revocation, catalog retirement and publication create no item
versions or work churn. Attempt-time revalidation, not a sweep, enforces revocation.

## 5. Physical persistence

Use relational identities, immutable canonical JSON payloads and bounded relational
reference projections. Pure JSON would hide FKs and require discovery scans; EAV
would make snapshot reconstruction needlessly complex. No dynamic tables per definition.

Notation: T = non-null TEXT/BINARY, I = INTEGER with exact integer type and positive
signed-64-bit range; ? allows NULL. Versions are decimal strings on wire, integers in
SQL. Hashes are lowercase 64-hex; timestamps use the existing canonical UTC form.
All FKs are NO ACTION on update/delete, DEFERRABLE INITIALLY DEFERRED. Every JSON
column stores exact `spine.canonical-json.v1` UTF-8, rejects duplicate keys/surrogates,
and has explicit immutable decoder version. JSON validity alone is insufficient.
Owner triples use existing system/subject/group exclusivity and FKs to subjects/groups.
Receipt references below target `command_receipts(command_receipt_id)`; policy refs
target `notification_policies(policy_id)`. Receipt provenance supplies actor/time/command.

The following inventories are exhaustive; key abbreviations do not rename public IDs.

### 5.1 Catalog and grants

`notification_rendering_definitions`:
`notification_rendering_definition_id T PK`, `owner_kind T`, `owner_subject_id T?`,
`owner_group_id T?`, `definition_key T`, `status T active|retired`,
`current_revision_id T`, `created_receipt_id T FK`, `retired_receipt_id T? FK`,
`retired_reason_code T?`. Active requires both retirement fields NULL; retired requires
both populated. Immutable root/owner/key/creation; terminal retirement only.
Three partial unique owner/key indexes (system, subject, group) include retired roots.

`notification_rendering_definition_revisions`:
`notification_rendering_definition_revision_id T PK`,
`notification_rendering_definition_id T FK root`, `revision_number I`,
`contract_version T`, `canonical_json_version T`, `revision_json T`,
`definition_hash T`, `created_receipt_id T FK`.
UNIQUE(root ID, revision number) and UNIQUE(root ID, revision ID); root/current pointer
has a composite FK to the latter. Revision JSON is precisely the existing revision
object, not the record envelope. Enforce its 8192-byte bound and existing hash preimage.

`notification_rendering_definition_fields`:
`definition_revision_id T FK revision`, `selection_index I0`, `selection_key T`,
`facet_key T`, `facet_schema_revision_id T FK facet_schema_revisions`, `field_key T`,
`projection T value|location_label`, `label T`.
I0 is integer 0–7. PK(revision,index); UNIQUE(revision,selection_key) and
UNIQUE(revision,facet_key,facet_schema_revision_id,field_key).
Composite FK(schema revision,field key) -> `facet_schema_fields`' existing key.
These 1–8 rows are exact projections of revision JSON, including order; never an
independent editable definition. Keep historical references and prevent schema deletion.

`notification_rendering_disclosures`:
`disclosure_authorization_id T PK`, `owner_kind T`, `owner_subject_id T?`,
`owner_group_id T?`, `definition_root_id T`, `definition_revision_id T`,
`scope_contract_version T`, `canonical_json_version T`, `scope_json T`, `scope_hash T`,
`match_hash T`, `status T active|revoked`, `created_receipt_id T FK`,
`revoked_receipt_id T? FK`, `revoked_reason_code T?`.
Composite definition FK binds root/revision. Owner here is the scope's item owner;
system item scope is invalid. Active has NULL revocation facts, revoked has both.
Scope is the complete existing disclosureScope object, maximum 24576 bytes.
Scope identity/hash/owner and match_hash never mutate. No unique scope hash: distinct
commands may create identical grants, deliberately making unique-match ambiguous.

`notification_rendering_disclosure_locations`:
`disclosure_authorization_id T FK disclosure`, `location_id T FK locations`,
PK(disclosure,location). Exactly the scope's permitted IDs, at most 64; immutable,
including after revocation. These rows protect deletion but do not newly freeze labels:
facet-reference immutability remains owned by schema 18.

`notification_rendering_disclosure_profiles`:
`disclosure_authorization_id T PK FK disclosure`,
`notification_profile_id T FK notification_profiles`. Exactly one row for profile use
scope and none for direct-policy scope; protects the stable root, not its current revision.
Delivery-target and recipient IDs in scope require FKs too: add
`delivery_target_id T FK delivery_targets`, `recipient_subject_id T? FK subjects`,
`recipient_group_id T? FK subject_groups` to the disclosure row, exactly matching its
scope with one recipient ID. Scope equality is verified; JSON IDs are not an FK substitute.

### 5.2 Profile and item supporting facts

`notification_profile_rendering_revisions`:
`notification_profile_revision_id T PK FK notification_profile_revisions`,
`profile_contract_version T` (v2). Its presence selects the v2 hash decoder; absence
on historical revisions selects v1. Do not fabricate v2 hashes for v1 revisions.

`notification_profile_template_renderings`:
`notification_profile_template_id T PK FK notification_profile_templates`,
`kind T ordinary|definition`, `definition_root_id T?`, `definition_revision_id T?`.
Definition requires both IDs and their composite FK; ordinary requires both NULL.
Exactly one row per template of a marked v2 revision, including ordinary. No rows
for unmarked v1 revisions. Template schedule/late-handling rows stay authoritative.

`notification_policy_presentations`:
`notification_policy_id T PK FK policy`, `item_id T`, `item_version I`,
`presentation_contract_version T`, `canonical_json_version T`, `presentation_json T`,
`presentation_hash T`, `definition_root_id T?`, `definition_revision_id T?`,
`disclosure_authorization_id T? FK disclosure`, `source_policy_id T? FK policy`.
Composite definition FK; composite FK(item_id,item_version) -> coordination_item_versions.
Trigger binds item/version/source exactly to the policy row. Definition branch requires
all definition/grant IDs; ordinary requires all NULL. JSON is policyPresentation, at
most 8192 bytes. Validate grant scope hash, root/revision and projection parity.
Historical origin profile/root/template references use the existing application
mapping where available; new copied origin may not forge or borrow another policy's
application. Reference validation is performed on every fresh write; immutable catalog
roots/revisions cannot be physically deleted while used by any stored origin.

Exactly one presentation row is required per policy after activation. The shared
item-version finalizer covers every policy producer (schedule, reminder, recurrence,
facet, temporal binding, lifecycle, import and maintenance). Register actual producers
in a release writer inventory; touched versions come from the transaction allocator,
not caller-supplied lists. Verify count, parity and predecessor provenance before
commit. Missing rows are corruption, never implicit ordinary. Historical migration
backfill is the only path that creates ordinary rows without a new authoring receipt.

### 5.3 One rendering row per attempt

Extend/rebuild the existing `notification_renderings` table in the future migration;
do not create a parallel send/rendering ledger. Preserve all v1 rows and columns.
Add nullable `base_rendering_json T?`, `details_evidence_json T?`,
`details_contract_version T?`. For v1 all three are NULL. For v2 all are present;
the base JSON is the complete unchanged v1 rendering object, and details is the exact
existing details-evidence schema. Existing top-level body/hash/id columns are the
final v2 values; common source/phrase/location columns equal the nested base facts.
SQL contract/profile checks admit only explicitly supported v1/v2 branches.

Retain UNIQUE(attempt_id) and attempt/work/item/time-binding trigger. Add immutable
update/delete guards for rendering rows and cross-field validation at attempt insertion.
Base and detail bodies each obey 1024 scalars; details JSON <=16384 UTF-8 bytes;
the complete canonical v2 envelope <=32768 bytes. No evidence overflow fallback.
All immutable new tables prohibit update/delete; only root pointers/lifecycle and
catalog generation may change through guarded mutations. Hash/JSON/projection parity
is a shared write-finalizer and explicit deep-verifier obligation, not a startup scan.

## 6. Attempts and readback

Ordinary selection uses the existing v1 renderer/row/envelope unchanged. Definition
selection, including revoked/empty/overflow fallback, creates v2 evidence: do not
erase the fact that optional detail was evaluated. The v2 rendering object is exactly
`{rendering_contract, notification_rendering_id, base_rendering, details,
rendering_input_hash, rendered_content_hash, body_text}`; rendering_contract is v2,
base_rendering is the existing complete v1 object, details is details-evidence.v1.
Both carry the same attempt, work, item and actual rendered version. `details.policy_id`
names the unique current descendant, not the historical policy FK on work.

V2 preimages, all canonical JSON with canonical_json_version explicitly included:

- input: `{derivation_version: spine.notification-rendering-input-hash.v2,
  canonical_json_version, base_rendering_input_hash, details_input_hash}`;
- content: `{derivation_version: spine.notification-rendering-content-hash.v2,
  canonical_json_version, rendering_input_hash, body_text}`;
- identity: `{derivation_version: spine.notification-rendering-id.v2,
  canonical_json_version, attempt_id, rendering_input_hash, rendered_content_hash}`,
  prefix `notification_rendering`.

The base keeps its v1 identity/hashes as nested computation evidence, not a second
persisted rendering or attempt. Details binds base input/content hashes by equality.
Final body equals details.body_text. The existing OpenClaw outbound v2 fields already
bind a rendering ID, content hash and body; fill them with the final v2 facts without
changing its shape, provider key or per-attempt dedupe rule. No new transport is needed.

Attempt transaction order: ordinary admission -> exact current policy/presentation ->
base rendering -> disclosure and allowed source resolution -> details -> final evidence
validation -> immutable rendering and started attempt in the same commit -> adapter.
All prepared facts and current access/source state are rechecked under the same writer
transaction. A stale lease or failed base gate cannot be rescued by detail omission.
SQLite serialization determines edit/revoke versus attempt-start ordering. A committed
started attempt may still send its committed body even if revocation commits next.

Missing/revoked/mismatching grant yields disclosure_unavailable without private value
reads. Broken stored FKs, noncanonical bytes, hash mismatch, missing presentation,
unknown decoder, capacity exhaustion or evidence persistence failure are operational
failures, no started attempt and no adapter call. They are not optional absence.
Catalog retirement does not invalidate old pinned use. A same-attempt replay reads
the stored v1/v2 object; a new retry uses new facts and the same provider idempotency
key. An uncertain prior provider outcome is not proof that the latest body was delivered.

Schedule-show v2 adds `presentation` and `presentation_hash` to policy projections;
under the existing attempts include, rendering is a v1/v2 discriminated union.
It does not add a second top-level rendering collection or recompute old prose.
Protected summaries must not expose body, detail values, source IDs or scope contents
merely because an item is readable. Follow the existing attempt-evidence release
boundary. Compact receipts continue reporting lifecycle/work facts without facet values.

## 7. Permission and release mapping

Reuse the current subject/group role model, not new roles or inferred chat ownership.
Catalog resources use kind `notification_rendering_definition`, immutable owner
revision 1, catalog.read/catalog.use grants, and existing owner/admin management rules.
Adding that resource kind to grant storage/provisioning is part of the future release,
not permitted by today's enum. Disclosure management has no independent transferable
grant in this slice: item-owner subject or that group's admin/owner controls it.

| Operation | Required authority on fresh execution |
| --- | --- |
| Definition create/publish/retire | Catalog owner administration; referenced schemas readable/usable and same owner |
| Definition show/list | Catalog read or use, with authorized candidates before pagination |
| Disclosure provision | Scope-owner administration, definition use, actual route use/release, all permitted-location authority |
| Disclosure revoke/show/list | Scope-owner administration; revocation must remain possible after losing definition/route use |
| Apply/change presentation | Item create/edit, fresh definition use, same-owner profile/schema rules, exact active disclosure and actual route release |
| Item policy readback | Current item read; embedded pins/hashes only, not whole reusable grant/catalog discovery |
| Full attempt evidence | Existing protected attempt/body release plus reference restrictions |

Protected replay follows the existing initiating-account/subject and receipt-read
checks, not fresh administration or active-catalog checks. Revocation never deletes
old receipt evidence; current receipt disclosure still governs visibility. Trusted-local
CLI remains full scope but must validate explicit owner/scope/reference consistency.
Single-operator access bypasses role filtering, not domain disclosure matching.

The protected subset retains same-owner item/route release and existing member-route
approvals; no new cross-owner send permission is inferred. Applying a previously
approved scope is not authority to provision one. Worker detail release uses current
item owner, route facts and the stored active scope, not a browser session or the
continued membership of its issuing person. Issuer suspension alone does not revoke
an organizational grant; explicit revocation/owner-route mismatch does. This preserves
accepted-work service authority and is not general multi-user notification authorization.

Locations currently have no protected sharing resolver. Preserve the existing facet
rule: permission-enforced location-reference authoring/lookup is unavailable until its
own family contract exists. Protected disclosure provisioning with nonempty permitted
locations is denied; do not infer visibility from a primary-location link or group label.
Trusted-local grants can permit location IDs. At worker attempt time they are usable
under the trusted-local location resolver plus exact scope coverage. Protected paths
must not downgrade to that resolver. Scalar-only protected integration can be released
independently; exposing location labels on that transport is a separate product scope.

Future web registration must explicitly pin schemas, permission mappings, receipt
attribution and evidence redaction in an additive family. These logical mappings are
not authorization to extend the deployed web allowlist. Until that release contract is
codified, rendering authoring is planned for trusted-local commands only.

## 8. Catalog reads, indexes and capacity

Create `notification_rendering_catalog_state(singleton I PK CHECK=1, generation I)`;
initialize to 1. Changed create/publish/retire/provision/revoke increments once per
transaction. No-op, replay and reads do not increment. Overflow fails closed. Global
generation deliberately invalidates pages across owners; it is not a user-visible count.

Required indexes: roots `(owner_kind,owner_subject_id,owner_group_id,status,root_id)`
with required owner/status predicates; disclosures likewise ending in
disclosure_authorization_id; revisions `(root_id,revision_number)`; fields by revision;
policy presentations by `(item_id,item_version,notification_policy_id)` and by grant;
template-renderings by definition revision. Root/revision IDs refer to the full column
names in Section 5. Add reverse-FK indexes for all reference tables and receipt FKs.

`match_hash` hashes exactly `{derivation_version: spine.rendering-disclosure-match.v1,
canonical_json_version, item_owner, definition, use_scope, destination}`. These fields
come from the normalized scope; fields and permitted locations are intentionally
excluded. Index disclosures `(match_hash,status,disclosure_authorization_id)`. Unique
resolution inspects at most 101 active candidates; if more than 100 exist, fail capacity,
even if an early candidate matched. Under the cap, compare full structural scope,
effective-key subset and required authority; zero/multiple matching grants retain
existing unavailable/ambiguous errors. Empty facet values do not constrain the allowed
location set at authoring; each actual location is checked at attempt time. Exact-ID
selection uses a PK lookup and the same semantic checks. Never globally scan grants.

List uses binary root/grant keyset order, not OFFSET. Filter owner/lifecycle and
authority before page size; no totals. Fetch at most limit+1 authorized candidates.
Permission-enforced enumeration must use owner rights or indexed grant candidate
unions, not unbounded post-filtering. Up to 101 candidates, 100 returned records,
100 access-proof rows, 4 MiB serialized response, 5 seconds and 100000 SQLite VM
steps per read (including fence); lower configured limits win. Exceeding a bound is
environment_failure, never a partial successful page. Definitions/scopes have their
existing per-record byte bounds. One attempt resolves <=8 selections/unique locations
by PK; no catalog discovery at send time. Existing runtime transaction ceilings apply.

Reserve `spine.notification-rendering-cursor.v1`, prefix `nrc1`. Token is
`nrc1.<key_id>.<base64url(payload)>.<base64url(mac)>`, canonical unpadded base64url.
MAC = HMAC-SHA256(key, UTF8(`spine.notification-rendering-cursor.v1`) + NUL +
UTF8(key_id) + NUL + canonical payload bytes). Protected key config reuses the facet
cursor file lifecycle/permissions and minimum 32-byte secret, but uses a distinct
domain; no generated fallback. Max token 4096 bytes, original TTL 900 seconds, fixed
expiry across pages. Key retirement, restore-generation change or ledger clone invalidates it.

Payload has exactly: contract_version, ledger_instance_id, key_generation, command,
query_hash, context_hash, access_hash, catalog_generation, last_id, issued_at_utc,
expires_at_utc, access_epoch, access_valid_until_utc. Canonical query is
`{owner,status,limit}`. Status is required by both existing closed list contracts:
definition lists accept `active|retired`, disclosure lists accept `active|revoked`.
Omitted, null or otherwise invalid status fails request validation before cursor
processing; there is no unfiltered-list mode or null-status normalization. Use the
admitted status enum verbatim. Limit is bound, not adjustable mid-pagination.
Hash preimages use the exact
objects `{derivation_version,canonical_json_version,<named object>}` with domains
`spine.rendering-cursor-query.v1`, `spine.rendering-cursor-context.v1`,
`spine.rendering-cursor-access.v1` and keys query, context, access respectively.
Context is `{mode,account_id,subject_id,audience,ledger_instance_id}`; trusted-local
uses null account/subject and audience `trusted_local_full_scope`. Access is
`{access_epoch,valid_until_utc}` from the existing permission resolver;
trusted-local uses nulls. Payload access_valid_until_utc is that valid_until_utc,
null when no temporal transition exists. It limits expiry to the next temporal access
transition. Continuation verifies access_hash against these authenticated payload facts,
then recomputes authority at current time, checks current epoch/context and rejects an
expired transition bound. It does not compare a fresh evaluation timestamp with the
old one. Section 11 and the cursor schemas close token field domains and reference
vectors; stateful permission and catalog fences remain runtime obligations.

Malformed/MAC/query/expired/source/context mismatch is stale_cursor without payload
release; missing key/config or capacity is environment_failure. Revalidate current
authority and catalog generation after serialization, before release. First-page
source/access change is environment_failure; continuation is stale_cursor. No automatic
reconstruction, retry, durable cursor session or read receipt. Concurrent retirement,
revocation and access changes must never release a stale page.

## 9. Migration, atomicity and cutover

Future migration starts from schema 18 or a separately verified successor. Stop all
writers, take and verify a consistent backup, validate expected objects, then one
exclusive writer transaction creates the new tables/indexes/guards, rebuilds the
rendering branch constraints and backfills exactly one ordinary presentation per
existing policy (active, disabled and historical). Preserve every old policy, profile,
work, receipt and attempt ID/hash/body. Historical profile revisions remain v1 and
receive no rendering rows. Backfill is not an authored application or grant.

Verify counts, all FK/projection/hash invariants, v1 row byte equality, schema manifest
and writer coverage before activation. Full historical verification belongs to this
offline path, never routine command/worker startup. Failure at any step rolls back
schema/data/version activation together. Provision no definitions or disclosure grants
automatically. Fresh initialization must reach identical schema and invariants.

Ordinary new policies receive explicit ordinary presentations; all version writers
copy state. Finalizer omissions or projection mismatch roll back supporting sets,
audit/receipt and current pointers. Catalog writes atomically change rows, common
catalog audit, receipt and generation. Use existing coordination_catalog_audit_log
with new resource-kind validation, not a separate audit ledger. Replay/no-op follows
logical Section 13; no-op still has its normal audit/receipt but no generation change.

Rollback after activation requires all writers stopped and restoration of the verified
pre-migration backup with compatible code. Preserve the newer ledger before restore;
subsequent writes are not magically merged. No down migration, manual schema-number
decrement, deletion of sidecars to appease an old binary, or fabricated old evidence.

## 10. Required fixtures and readiness

The integration matrix names the required proof families; they are obligations until
executable fixtures are checked in and run. At minimum:

| ID | Required oracle |
| --- | --- |
| RI-01 | V1 unselected body, hashes and provider envelope byte-identical before/after migration |
| RI-02 | Profile v2 and presentation hash preimages/digests; explicit ordinary, empty subset, unique/exact grant selection; v1 request against v1 current, v2 request against v1/v2 current; fresh v1 against v2 rejected even all-ordinary/no-op, stale guard first, historical replay unchanged |
| RI-03 | Fresh local detail create rejected with no residue; staged ordinary create/adoption/edit/materialization obeys Section 3.3 operational exclusion for strict ordering; without exclusion ordinary sends may start between steps; adoption/edit failure preserves prior commits; each individual create/full-plan transaction rolls back all its item/policy/presentation/work/audit/receipt writes; scheduler-interleaving oracles below |
| RI-04 | Presentation-only change/no-op/dry-run/replay with identical work IDs; old schema cannot silently clear |
| RI-05 | Shared intent, multiple predecessors and repeated copy-forward; wrong/forked ancestry fails closed |
| RI-06 | Queued, leased, retry, started, terminal and absent work across facet/presentation edits |
| RI-07 | Attempt versus edit/revoke/ownership/route races: exact serial body and no private values on omission |
| RI-08 | One v2 rendering+attempt atomic commit; interruption/overflow/corruption invokes no adapter |
| RI-09 | Same-attempt replay and new retry; stable provider key, old body never recomputed |
| RI-10 | Subject/group roles, forbidden grant issuance, protected location denial, trusted-local exact-location approval |
| RI-11 | Signed cursor tamper/query/identity/epoch/generation/time transitions, bounded plans and no read writes; required legal status on both lists, omitted/null rejected before cursor processing, status change invalidates continuation |
| RI-12 | Populated/fresh migration, interruption at each DDL stage, backup restore and old-worker refusal |
| RI-13 | Every item-version producer copies presentations; omitted producer/finalizer/row is detected |
| RI-14 | Full readback discriminates v1/v2; old summaries leak no details; packaging excludes unimplemented families |

RI-03 additionally requires a future stateful scheduler-interleaving oracle: create
an ordinary reminder already due within grace using materialization=none, then run an
automatic cycle before adoption/edit and prove ordinary work can be materialized and
started. After editing, preserve the started attempt/body and delivery identity.
Under verified operational exclusion from before creation through presentation commit,
prove no interleaved materialization/start occurs; releasing only after setup permits
normal current-policy rendering with no duplicate delivery. Also cover exclusion
through explicit step 4, failed setup retaining prior commits, and opportunity expiry
without grace extension. Source-only consistency checks do not execute these oracles.

The amendment is ratified and Section 11 supplies the source-only successor schemas,
cursor config/payload and computed vectors with a registry/fixture manifest. Audit
those artifacts before implementation. Do not count a JSON obligation as execution.
Then implement one environment-sized slice spanning authoring through attempt/readback,
with staged activation only after the stateful, migration and regression tests pass.

No new product decision is presumed. This design deliberately preserves trusted-local
location access and the protected transport's existing denial. Broader cross-owner
release, shared-location permissions, pack installation and web exposure are separate
choices, not silently settled here. Review may identify a genuine tradeoff to take
back to the operator; none of these deferrals licenses weakening existing protection.

## 11. Successor machine contracts and reference fixtures

The [integration registry](../contracts/notification-rendering-integration-contract-registry.v1.json)
is the source-only index of exact request, response and embedded contracts. The
[fixture manifest](../contracts/notification-rendering-integration-fixture-manifest.json)
distinguishes wire validation, computed reference proofs and pending stateful oracles.
These files are excluded from packaged web contracts and implemented declarations.
No existing schema, compiled registry, CLI selector or SQL migration is activated here.

Successor requests use their exact Section 2 contract_version, including the new
required selector on schedule.show v2; direct authoring uses authoring_contract.
The exact direct-create wrapper is notification as before, now using authoring v2.
The v2 direct-edit wrapper is patch.notification, a partial object requiring
authoring_contract; it may carry target, schedule, late_handling and presentation.
Omitted fields retain current values. Recipient/channel/route patch fields retain
their existing outer positions. Flattened timing fields cannot be mixed into this
new wrapper. A selector-only notification object performs no notification change;
existing no-op/replay rules apply. Old direct command envelopes remain unchanged.
Create/update responses and receipt_contract use matching v3 suffixes
(`spine.schedule-create-response.v3`, `spine.schedule-create-receipt.v3`,
`spine.schedule-update-response.v3`, `spine.schedule-update-receipt.v3`). Existing
effects, replay semantics and standard command failure envelopes remain unchanged;
detail selection additionally permits the logical rendering error codes. Command
failures use the registry's shared standard failure envelope; dry-run failures carry
dry_run=true. All successor success projections, including schedule-create/update v3,
profile v2 and schedule-show v2, likewise permit only the optional dry_run=true marker,
not false. No schema rejection is a substitute for
fresh ownership/grant validation.
Presentation edits report changed_dimensions=policy_presentations when changed, an empty list on
no-op, and required presentation_changes (empty if none). Each new policy projection
includes presentation and presentation_hash, including ordinary policies.

Profile create/revise/show/list v2 use the closed successor schemas. V2 read records
project a normalized owner object and selected revision envelope rather than raw SQL
joins. revision_contract selects the historical v1 or v2 content decoder; old hashes
are never recomputed as v2. V2 normalization preserves existing timing normalization,
sorts compatible_item_types and templates by template_key, and inserts explicit
ordinary rendering for omission. Hash each template without derived fields first;
the complete normalized revision includes those normalized_template_hash values.
Catalog IDs, row indexes and timestamps do not enter the revision-content preimage.
Profile-list v2 retains the existing 1–500 request limit and a maximum 500-entry
response; the separate rendering-definition/disclosure catalog's 100-entry bound
does not apply to notification-profile lists.

Application v2 is a closed projection of a persisted selected-profile application,
not a replacement plan or an instruction to select a profile. It carries explicit
application_contract, existing application/profile/revision/binding IDs, selection
mode, scope_chain, normalized_profile_revision_hash, suppress_template_keys,
replacements, custom_additions, ordinary effective-policy hash,
effective_presentation_set_hash and policy
mappings ordered by notification_policy_id. Each mapping retains policy_origin and
source_key as well as the resolved presentation/hash. No selected profile means null
application, including custom-only policies; those policies still expose presentation
through ordinary policy projections. Schedule create/update notification_profile is
this application projection or null. Full schedule.show uses readback v2 with nullable
application, nullable pinned/current revision IDs, and the existing upgrade/divergence
booleans. With no application both IDs are null and both booleans false; otherwise
the pinned ID equals application's revision and upgrade_available compares the two.
Archetype assignment remains a nullable, closed projection with assignment/item/version,
archetype/revision, selection-source/source-ref and creator/time facts; no nested raw
catalog join is exposed. Historical revision content retains normalized template hashes.

Application evidence preserves the accepted selection/composition snapshot, not a
fresh resolution against today's catalog. scope_chain is the ordered unique owner
chain (one through eight) actually searched for archetype_default, whose binding ID
is required; explicit selection records an empty chain and null binding. Owner
objects use the profile owner's closed wire shape. normalized_profile_revision_hash
is the pinned revision's stored hash using its original v1/v2 decoder, never a v2
rehash of historical v1 content. The three overlay arrays are always present, empty
when unused: sorted unique suppress_template_keys, replacements ordered uniquely by
template_key with complete normalized schedule/late_handling, and custom_additions
ordered uniquely by policy_key with complete normalized schedule/late_handling.
They retain the profile composition contract's bounds and semantics; the projection
calls the stored additions facts custom_additions to match the authoring contract.
Readback embeds this same evidence, including its scope chain and binding, rather
than discarding it. Copy-forward/direct edits preserve that snapshot and report
divergence by the existing rules, not by rewriting original composition facts.

Schema validation alone cannot enforce ordering, unique policy/source addresses,
grant availability, current ancestry, cross-object equality, page fences or hash
recomputation. The manifest names reference oracles for the pure checks. Ledger,
permission, transaction and lifecycle checks remain mandatory runtime validation.
Rendering v2 must bind the same attempt/item version as its v1 base and detail evidence,
use details.body_text as final body, and verify all nested hashes before persistence.
Omission of details after selection remains a v2 envelope with no private source/value
facts in omitted selections; wholly unselected ordinary rendering stays v1.

### 11.1 Cursor configuration and exact scalar domains

The separate protected config file has exactly contract_version
`spine.notification-rendering-cursor-config.v1`, key_id, key_generation,
ledger_instance_id and secret_hex. It reuses the facet configuration's deployment
lifecycle, not its file shape or key. One active key is supported; key_id and
key_generation are opaque 1–64 ASCII alphanumeric/underscore/hyphen tokens. The
secret is 32–64 cryptographically random bytes represented as lowercase hex. Fixture
keys are public test values and MUST NOT be provisioned. Config ledger_instance_id
must match the actual ledger; missing/invalid/mismatched config fails environment_failure.
Config is protected deployment input, never request JSON, receipt or log content.

catalog_generation and non-null access_epoch are canonical positive decimal strings,
bounded by 9223372036854775807; JSON-schema length is only the first bound. UTC timestamps
are real Gregorian seconds in YYYY-MM-DDTHH:MM:SSZ format, without fractions, offsets
or leap seconds. All three cursor hashes are lowercase SHA-256 over the exact canonical
preimages in Section 8. context.mode is trusted_local or permission_enforced; the
latter requires non-null account_id and subject_id and its resolver-provided audience.
Trusted-local access has null epoch/valid_until; permission-enforced access has a
positive epoch and optional transition bound. Cross-object mode/access checks are
semantic constraints, not grounds for weakening admission.

Continuation requires issued_at <= now < expires_at <= issued_at+900 seconds; expiry
must also be <= any non-null access_valid_until. Reject noncanonical base64url or
payload bytes, not just bad MACs. Verify the MAC before trusting payload facts, then
compare command, query, context, ledger/key/catalog generation and current access
epoch/time fence. No token renewal on continuation. The reference vectors exercise
these pure decisions, not database permission resolution or a running cursor service.
