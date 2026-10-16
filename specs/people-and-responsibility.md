# People and Responsibility

Status: Ratified v1.0.0 — logical design accepted; machine codification pending review; not implemented
Created: 2026-10-16
Ratified: 2026-10-16, following bounded consistency audit people-and-responsibility-contract-audit-001
Inspected baseline: `8f3c50b6fd1b4aa534e50925b7417a7a80d19122`, runtime 0.10.0/schema 19
Scope: Item participation, task assignment, scoped subject selection and person-filtered reads

## 1. Purpose and authority

Make it possible to express and inspect:

> Lynn attends a medical appointment. Caleb is assigned its preparation task.
> The records belong to Kinflow. Reminders go to its selected delivery target.

These are four separate statements, not four spellings of ownership. Reuse
`subjects`, arbitrary `subject_groups`, explicit `subject_memberships` and immutable
item-versioned `item_subject_roles`. Do not add an account, family-member, contact,
participant or responsibility identity registry beside them.

[Ontology](ontology.md) owns identities, role rows and versions;
[permissions](permissions.md) owns resource access;
[accounts and attribution](accounts-and-chat-attribution.md) owns caller identity;
[notifications](notifications.md) owns recipients, policy and delivery eligibility.
[Storage atomicity](STORAGE_ATOMICITY_SPEC.md) remains the persistence owner.
This leaf owns participation/assignment behavior and its successor public surfaces.
[Schedule creation](schedule-create.md), [operations](schedule-operations.md),
[independent reads](independent-activity-reads.md) and
[relative bindings](relative-temporal-bindings.md) retain their existing authority.

This accepted design changes no implemented command, schema, registry, permission,
package version or released pack. New names and examples below are not callable
runtime contracts. Product decisions D-01/D-02 and the reviewed logical design were
approved on 2026-10-16. The source-only machine companion and schemas codify that
design; their review and Section 12 runtime gates still precede implementation.
Ratification is not an implementation-readiness claim.

## 2. Four independent dimensions

| Dimension | Canonical source | Meaning | Does not imply |
| --- | --- | --- | --- |
| Participation | `item_subject_roles`, `role=participant` | Subject involved in attending an event | Responsibility for tasks, access, RSVP acceptance, notification delivery |
| Assignment | `item_subject_roles`, `role=assignee` | Subject responsible for a task | Access ownership, attendance, exclusive responsibility, reminder recipient |
| Ownership/access | `item_access_owners`, current memberships/roles and grants | Which resource scope owns the item and who may act on it | Participation or assignment |
| Notification routing | Effective `notification_policies` and `delivery_targets` | Who receives which reminder and where | Attendance, task responsibility or item ownership |

Command actors, account bindings and creators are separate again. Never select an
assignee or participant by falling back to the executing agent, requesting account,
item creator, catalog owner, group name or route. An account is not required for a
subject to participate or be assigned; an accountless child remains a subject.

Existing `role=owner` is a coordination role used by task contracts, not an access
owner. Existing `owner`, `watcher` and `recipient` role rows retain their contracts;
the new managed surface MUST NOT relabel, delete or interpret them as `assignee`.
In particular, a `recipient` role is not an effective notification policy.

No participation/assignment mutation issues a grant, changes membership, adopts or
transfers ownership, activates an account, selects a profile, or configures a route.

## 3. Initial logical scope

- Events support zero or more participants. Tasks support zero or more assignees.
- Reuse existing `person|agent` subjects; do not add built-in family or occupation
  types. Human-oriented clients may request person-only discovery explicitly.
- Group assignment, event assignees, task participants, lead assignees, RSVP state,
  delegation/acceptance, beneficiary/guardian/driver roles and custom role taxonomies
  are outside this first slice. Do not infer them from natural-language descriptions.
- Multiple task assignees are preserved as the existing set model. They do not create
  subtasks, per-person completion state, a voting rule or an automatic completion quorum.
- Participation is item/series-level, not an occurrence-specific overlay. Existing
  occurrence contracts remain closed; no per-date people patch is accepted here.

Use a related task when an event entails work: assigning Caleb to a preparation or
transport task is distinct from making him a participant in Lynn's appointment.
Neither `part_of` nor `follow_source` inherits people, access owners, memberships,
recipient choices or responsibility. Existing temporal bindings still govern time
only. Reads of the event do not require traversal into an inaccessible assigned task.

Subjects and groups are referenced by exact IDs. Display names, phone numbers,
channel metadata and archetype keys are not identity selectors. Agents must resolve
ambiguous names through supported discovery or ask the operator, not silently upsert
a duplicate subject. Do not copy people relationships into facets to bypass the core.

## 4. Existing runtime and compatibility boundary

At the inspected baseline:

- Storage supports `participant|assignee|watcher|owner|recipient`, active/inactive
  role status, immutable `(item_id, version)` sets and unique `(subject_id, role)` pairs.
- Task authoring/update and schedule task detail accept assignee/owner sets. This
  contract does not remove or reinterpret those accepted requests or historical rows.
- `item.show` exposes bounded role rows. Independent web reads have an optional
  `subject_roles` section whose implemented projection is limited to the selected
  subject. The existing web write adapter rejects other-subject role references.
- `owner_scope.list` is complete trusted-local owner inventory, not a protected
  people directory. It MUST NOT be silently narrowed or exposed as one.
- Facet-only continuity includes equality of `item_subject_roles`. A people edit is
  not a facet-only edit and MUST NOT be routed through a weakened facet equivalence.

Implement this only through explicit additive/successor contracts. Existing
schedule v3, root reads, compact output and frozen HTTP registries/schemas remain
unchanged. A new protected family must name its permission and reference checks;
removing the existing self-only guard globally is not such a family.

## 5. Successor public operations

These are accepted logical operations with source-only machine candidates in
Section 13, not implemented selectors or routes:

| Proposed operation | Required meaning |
| --- | --- |
| `people.list` | Bounded subject choices in one explicit subject/group owner scope; separate eligibility from granted item access |
| `item.people.show` | Current or exact historical participation/assignment snapshot for one readable item |
| `item.people.update` | Atomic replacement of the requested managed role set on one expected item version |
| Schedule-create successor | Author initial people in the same transaction as the existing atomic schedule bundle |
| Schedule-update successor | Combine people with already supported schedule changes in one existing item transaction |
| Item/agenda/occurrence read successors | Apply the exact person/role filter under existing item authorization and temporal rules |

Use one canonical mutation service for standalone and composite authoring. A direct
people command does not require reconstructing a schedule, reminder plan or route.
Conversely, create-with-people MUST NOT be implemented as a successful create followed
by a separately failing people update. No new multi-item atomic composite is proposed.

The illustrative people patch is:

```json
{
  "participants": ["lynn"]
}
```

For a task, the applicable key is `assignees`. A complete command additionally
needs its versioned selector, command ID, actor, action timestamp, item ID and
expected version under the owning command contract. This fragment is not a runnable
request. Machine codification must finalize exact selectors, envelopes, receipt fields
and HTTP paths before registration; no global schema/release number is reserved here.

### 5.1 Set semantics

On creation, omission means an empty managed set; no actor/default-owner inference.
On update, omission of a role key preserves all rows for that role. A present array
replaces the complete current-version set for that role; `[]` clears it. Null is not
a clear operation. An empty people patch is invalid. An unsupported role key for the
item type is invalid even if its array is empty; it does not create a different item.

Arrays contain unique opaque nonempty subject IDs, canonically ordered by Unicode
code point for semantic comparison/identity derivation. Reject invalid Unicode;
do not normalize IDs or resolve by label. Reject duplicates rather than silently
collapsing them. New emitted
rows from these arrays have `status=active`; arbitrary status authoring is not added.

A supplied replacement removes inactive rows for that managed role from the new
version as well as replacing its active rows. Prior versions remain unchanged.
Thus removal of an inactive current row is a semantic change even if active IDs
are equal. Other role kinds and omitted managed roles copy forward unchanged.

Fresh additions/reactivations require active, eligible subjects. Retaining the exact
existing active association or removing an association MUST NOT require that a subject
still be eligible for a fresh addition. Inactivity/membership changes never rewrite
historical associations or automatically unassign somebody. Historical role status
and current subject/membership status are different facts.

Fresh updates require an active shell and a nonterminal event/task under the owning
lifecycle contract; no reopening, unarchiving or status transition is implicit.
The standalone people update requires no scheduled anchor: an open unscheduled task
can still be assigned. Composite schedule updates retain their existing target-shape
requirements. Current or historical terminal people remain readable with permission.
Compatible replay is not a fresh edit; apply current protected authority checks and
the common replay rules without re-authoring history or rerunning fresh-add checks.

## 6. Scoped discovery and protected admission — approved product policy

The operator approved the following first-slice policy as D-01. It does not modify
the current protected adapter, create a new grant kind, or authenticate the caller.

`people.list` requires an explicit subject/group owner scope, page limit and optional
opaque cursor. It returns exact subject IDs, current display labels, subject kinds
and the declared lifecycle/eligibility facts needed for selection, never accounts,
phone numbers, transport addresses, credentials or unrelated group memberships.

Protected discovery: a subject-owned scope offers that subject; a group
scope offers its explicit current roster to a caller with current authority to view
that scope's roster. First-slice group roster authority is current active membership
in that same group, independent of whether the caller is member/admin/owner. Item
grants alone do not authorize directory enumeration. Exact scope and current authority
are checked again before releasing a page. A subject may appear without an account.

Fresh protected associations must be eligible for the target item's actual owner
scope: its own subject, or an active subject with an effective active membership in
that group. Labels, catalog ownership, profile use, chat membership and a route do not
establish this condition. An unrelated readable item does not authorize roster use.

Trusted-local callers keep their existing full-ledger reference authority: active
subjects can be selected by exact ID without a group-membership restriction. This
does not become a request-selectable web bypass. An inactive scope cannot authorize
fresh protected associations. Cross-group/non-member protected additions require an
explicit successor policy, not a made-up membership or implicit grant.
This also defers assigning a subject-owned private task to another group member,
even when the caller and that person share a group. Shared membership alone does
not broaden the target item's reference scope or change its ownership.
An unowned trusted-local item remains unowned; people editing does not adopt it.

Inactive subjects/ended memberships remain historical facts. Discovery's exact
active/inactive filters and observation-time binding must be codified; do not present
a historical directory entry as currently eligible. All membership intervals use
the service's admitted evaluation time, never client-selected authorization time.

Protected mutation requires current item-edit authority (or scope creation authority
for creation), expected access evidence, the target owner and eligibility of every
fresh reference, plus the caller's current scoped directory authority for those
references. Item-edit permission alone must not permit probing roster membership by
trying subject IDs. Check them inside the same write boundary. Existing permitted
references may be retained and removed without discovering other private subjects.
An assignee does not gain item-edit authority; explicitly share the item through
existing access provisioning if that is the operator's intent.

## 7. Readback and identity disclosure — approved product policy

The operator approved the following disclosure rule as D-02: readable item
participation/assignment tuples are item content. New people
read contracts may disclose their subject IDs, roles and role statuses under current
item-read permission, including historical associations. They do not disclose a
subject's private records, account, phone number, other groups or other assignments.
This is a deliberate new projection, not a reinterpretation of the self-only section.

Current directory labels are separate: resolve a display name/kind/lifecycle only
with the chosen directory authority. Otherwise retain the authorized association ID
with a closed `not_disclosed` subject-label projection; do not substitute the caller,
drop the association or invent a name. This must not expose *why* a label is absent.
A missing canonical FK or corrupt role row is an integrity failure, not a fabricated
label or an authorized missing person. Exact unions/fields require machine contracts.
Do not turn a capacity/service failure into `not_disclosed`: direct lookup fails
without partial output, while optional read sections follow the independent-read
unavailability rules and cannot remove the authorized core/time projection.

`item.people.show` binds item ID, selected item version and the complete managed role
projection; unmanaged role kinds are outside this view, not silently deleted from the
ledger. An empty result means no participation/assignment in that version, not that
there are no subject roles of any kind. Include role status and immutable supporting
row identity; order by role and exact subject ID. No new receipt or audit is written.

Historical association facts come from the selected version. A displayed label is
explicitly current catalog metadata at read time, not the person's historical name.
Renaming a subject does not rewrite role history, no-op hashes or past receipts.
Protected history uses current item permission and current label authority. Switching
accounts, revocation or an owner transfer invalidates prior permission/cursor proofs.

Keep the independent-read boundary: participation may be read without fetching related
tasks, their assignees, a temporal source's people, policies or private catalog content.
Only the owning temporal contract may require a time source; this feature adds no
graph traversal. Labels are optional context, not a reason to lose readable item/time
facts. Protected sections keep their closed authorized-only availability semantics.

## 8. Person-filtered reads

Proposed successor filters take one exact `subject_id` and a nonempty unique subset
of `participant|assignee` (default both). The predicate is OR across those roles,
AND with all existing owner/type/lifecycle/time filters. Match only `status=active`
rows at the selected current item version. No name matching, group expansion,
implicit "my family", follower propagation or assignee-as-owner shortcut is allowed.

The filter narrows authorized items; it never discovers private items by subject.
A supplied filter ID is not an identity lookup: absent and otherwise undisclosed
subjects with no matching authorized items have the same empty result. No public
person-existence validation or error may distinguish them. Inactive subjects with
retained active associations may still match; directory eligibility is not the query
predicate. Do not silently delete those matches from the operator's agenda.

Apply authority and role predicates before counts, pagination, expansion and public
diagnostics. Use the actual item's roles, never its parent's or child's. Recurring
occurrences inherit the current root's series-level role set; canonical occurrence
identity/time are unchanged. Tasks with unavailable time remain unplaced under the
independent-read contract after non-temporal people filters; never guess a date.

Page/cursor bindings include selected identity/access evidence, normalized filter,
owner scope and authorized source snapshot, including contributing item versions and
role facts. Role changes affecting that source invalidate continuation; recheck at
release. Hidden item/role changes must not affect authorized values/counts/coverage or
produce hidden-membership diagnostics. Preserve existing access-epoch rules; invent
neither a public whole-ledger people fingerprint nor a globally complete count.

## 9. Versioning, atomicity and notification continuity

One effective mutation creates one contiguous item version, complete supporting sets,
normal audit and receipt atomically. Copy forward unchanged details, anchors, locations,
unmanaged roles, archetype assignment, facets, recurrence/binding facts, profile
application, policy ancestry and presentation evidence under their owning contracts.
Do not copy role rows in place or alter past item versions. Shared services must use
the existing transaction-aware producer/finalizer boundary, not a second writer.

Normalized equality against the complete affected role sets is a no-op: no item
version/audit; retain the ordinary fresh-command receipt rule. Compatible replay
returns the original command evidence without another receipt/version. Dry-run uses
the same checks and rolls back every proposed row; it is not a reservation or a
delivery. Reuse existing row-role identity registration, with canonical request paths
for new arrays; enumerate paths and replay facts in machine contracts before coding.

People-only edits do not change reminder schedules, recipients, routes, profile
selection, delivery targets, opportunity identity or existing attempt content. They
do not materialize missing work, notify the new assignee, cancel other recipients'
reminders or resend anything. Routing changes require an explicit notification edit.

Preserving work across the new item version requires a **separate role-only
equivalence proof**: permit exactly the requested role delta and copy bookkeeping;
prove all other comparison facts, policy bijection/ancestry, target snapshots and
recurrence/temporal-source freshness unchanged. Do not relax the existing facet-only
proof, which requires role equality. The shared worker and scheduler must recognize
only a successfully proven lineage, not every higher item version.

On that proof, preserve eligible/leased/retry work identities, leases, retry/provider
keys and started/terminal attempt history. Independently stale work remains stale.
If the proof fails, roll back the authoring transaction; do not cancel all work or
pretend continuity succeeded. A composite changing time, lifecycle, policy, routing or
other semantic facts uses its owning reconciliation rules and truthful receipt, not
this people-only shortcut. Do not equate this proof with future advisory freshness:
any execution consuming people must separately invalidate changed context as required.

No automatic notification-text enrichment is proposed. Participant/assignee names
are not appended to reminders merely because they exist; a future rendering/disclosure
contract must explicitly authorize that audience and field selection.

## 10. Bounds, physical model and failure posture

Keep `item_subject_roles` authoritative, using its existing uniqueness/FKs and
item-version copy-forward. Do not introduce an alternate people JSON blob or mutable
current-only responsibility table. Reuse the existing subject/status/item/version
index as a candidate path, not proof of query cost. Before implementation, EXPLAIN
and runtime tests must prove both indexed authorized-owner/grant selection and exact
current-version matching; if an additional index is necessary, specify its versioned
migration/manifest explicitly. This contract activates no DDL or schema number.

Proposed new-family ceilings are 100 total role rows in a touched item version
(including copied unmanaged roles) and page limit 1–100, default 25. Existing
over-limit data is preserved, not trimmed or scanned at startup. New operations fail
capacity instead of silently replacing/truncating a partial role set. Codification
must specify aggregate reference, request/response byte, SQL-step, time/lock and
candidate budgets, using the stricter owning-adapter ceiling throughout one operation.
Pagination or a small reply is not permission to scan/sort the complete ledger first.

Use the common command and adapter taxonomies: malformed/duplicate/type-incompatible
input is invalid request; version races are stale/conflict; bad persistence or missing
decoder is environment failure; exhausted bounds are capacity failure. Protected fresh
reference errors conflate absent, inactive and unauthorized targets. Fail before
mutation and do not echo private person/owner facts. Detailed field/error precedence,
safe messages and CLI/HTTP exit mapping remain a machine-contract gate.

Reads, failed writes, preflight and idle cycles create no durable no-op records.
No direct SQLite access is an operator/client workaround for missing surfaces.

## 11. Approved product decisions

Both decisions were explicitly approved by the operator on 2026-10-16 for this
first scope. The logical design was subsequently ratified; neither act activates
runtime exposure or accepts the not-yet-reviewed machine candidates.

| ID | Decision | Approved first scope |
| --- | --- | --- |
| D-01 | Who may discover/select another subject in protected scheduling? | Shared-group current roster for active members; subject scope offers its own subject. Fresh protected references stay in the target owner scope; outsiders require later explicit policy. Trusted-local exact-ID authority remains unchanged. |
| D-02 | Does reading an item disclose all of its people association tuples? | Yes, in the new explicit projection: subject ID, role and role status are item content, including history. Directory labels require separate current authority; no private subject/account/item access follows. Preserve the old self-only projection. |

These policies are not implemented grants or retrospective consent. If either
changes, reconcile Sections 6–8 and their vectors before codifying/implementing the
protected path. Do not silently choose a broader directory or apply existing
full-scope CLI behavior through HTTP. No new beneficiary/RSVP/lead/driver taxonomy is
needed to settle these two decisions; any such expansion is a separately selected use.

## 12. Next contracts and acceptance evidence

The logical v0.1.1 draft passed the bounded consistency review with no findings;
the operator accepted logical v1.0.0. Section 13 and the source-only machine
companion now define candidate closed schemas, successors, planned declarations,
permission/error mappings, cursor rules, continuity requirements and offline
fixtures. Review this codification before runtime implementation. Compiled
declarations, executable continuity/query/concurrency proof, installed-package
closure and public-transport tests are still pending. Preserve frozen registries
and v1/v2/v3 families; do not add fields to released closed envelopes.

The acceptance corpus must cover:

| Family | Required evidence |
| --- | --- |
| Four-way separation | Appointment participant, related-task assignee, different access owner and independent reminder route; no grants/memberships/accounts/policies created by people edits |
| Role semantics | Zero/multiple subjects; event/task type errors; unscheduled-task assignment and terminal-write rejection; duplicate and ambiguous IDs; person/agent and accountless subjects; no automatic event/task role inheritance |
| Sets/history | Omit/preserve, replace, clear, inactive-row removal, subject rename/inactivity, old-version readback and unmanaged-role copy-forward |
| Transactions | Atomic create-with-people/composite update; failure rollback with facets/policies present; canonical no-op, replay, conflict, stale version and dry-run |
| Admission | Self/group/membership/admin versus item-edit rights; fresh outsider denial, preserved ineligible references, revoked access and missing/inactive/denied indistinguishability |
| Disclosure | Approved D-02 tuple visibility, directory label denial, historical IDs/current labels, independent event read despite hidden related tasks, no account/phone/global-roster leakage |
| Filters/cursors | Exact current active role match; private-owner item omitted even for its assignee; authorized-before-pagination; recurrence identities; unavailable-time tasks; stale pages and hidden-row metamorphic tests |
| Work continuity | Eligible, leased, retry, started, terminal and absent work; several people-only edits; shared-intent policies, recurring/follow-source targets; broken-proof rollback and explicit routing edit distinction |
| Capacity/concurrency | Real query plans and all bounds; oversized current role sets preserved; concurrent version, membership, label and access changes; no preflight/deep scans or durable read effects |
| Compatibility | Existing local task roles, self-only web contracts and all frozen wire bytes unchanged; additive registry/package closure and client handoff; no Packs or UI implementation inferred |

One coherent delivery may span core/CLI and explicit protected successors, but not
activate a partial contract. First draft, machine contracts, runtime verification,
frontend adoption, deployment and pack adoption remain distinct claims.

## 13. Machine codification — candidate v0.1.0, pending review

The [machine companion](../contracts/people-and-responsibility.v1.json) owns the
exact planned registry, selectors, sorted prerequisites, limits, error mappings,
normalization and identity paths. [Schemas](../contracts/schemas/people/) are a
source-only namespace, deliberately outside the flat globs used by current web
packagers. They are not installed runtime declarations or capability discovery.
The [fixture manifest](../contracts/people-and-responsibility-fixture-manifest.json)
distinguishes structural fixtures, pure-model witnesses and pending PR-01–16
runtime obligations. A passing offline test is not proof of authorization,
transactions, SQLite query cost, worker races or transport implementation.

### 13.1 Explicit surface/version boundary

| Surface | Planned selector / result | Exposure when implemented |
| --- | --- | --- |
| `people.list`, `item.people.show`, `item.people.update` | `spine.people-and-responsibility.v1` | Trusted-local and separately registered protected routes |
| `schedule.create` | `spine.schedule-create.v4` / `spine.schedule-create-response.v4` | Additive local selector and protected successor |
| `schedule.update` | `spine.schedule-update.v4` / `spine.schedule-update-response.v4` | Additive local selector and protected successor |
| Protected people/scheduling/read family | `spine.trusted-web-people.v1` | Eight closed operations; `/api/v3/commands/<command>` except `/api/v3/agenda` |
| Protected `schedule.show`, `agenda.show`, `item.occurrences` | `spine.people-schedule-view.v1`, `spine.people-agenda-view.v1`, `spine.people-occurrences-view.v1` | Independent read successors, not local read selector changes |
| Cursor / role-only proof | `spine.people-cursor.v1` / `spine.people-notification-continuity.v1` | Internal admitted configuration and shared services |

URL version 3 names a separate route family, not a replacement for every prior web
API. Existing CLI `schedule.show`, `agenda.show`, compact output and local recurrence
reads remain unchanged; standalone `item.people.show` supplies local people evidence.
No MCP route, user/group provisioning, UI or pack installation is added.

Protected outer requests never select an account, subject, grant or trusted-local
mode. Identity comes from existing admitted self-selection. Writes require the
existing `expected_access_epoch`; schedule creation additionally requires an explicit
`create_owner_scope`. Every success echoes the admitted identity/revisions/epoch.
The inner actor must equal the selected subject under existing web rules; a model-
authored actor is not authentication. Single-operator mode retains its existing
deployment-selected full-scope permission exception; it is not a request flag.

`people.list` takes `owner`, optional `subject_status=active|inactive|all` (default
active), `subject_kind=person|agent|all` (default all), decimal-string `limit`
(default `"25"`) and optional opaque cursor. A group roster includes only effective
current memberships, deduplicated by subject; conflicting simultaneous membership
facts fail closed. Inactive subjects may be listed through the explicit filter but
are not fresh-selection eligible. Subject scope contains that exact subject only.
An inactive scope cannot be used for protected directory discovery. Historical
membership is not offered as a current roster. Eligibility is derived, not stored
as a second people registry. Local discovery uses the same explicit scope and filters;
only local exact-ID authoring has the broader reference privilege.

`item.people.show` takes item ID and optional exact positive `version`. Missing
version selects current. The complete managed projection binds item ID/type and
selected version, sorted association rows and one subject-label projection per unique
associated ID. Current version is separate. No role set is truncated; over-budget
direct reads fail. Tuple sort is `(role, subject_id)`; labels sort by subject ID.
Only event participants or task assignees are managed. Inactive managed rows appear
in historical/current show but do not match person filters. Current directory labels
use a fresh authorized snapshot; they are not historical names or receipt facts.

### 13.2 Authoring, identity and receipts

The standalone update uses `target_version`, `updated_at_utc`, command ID, actor,
item ID and `people`. It supports open unscheduled tasks. Scheduling v4 adds optional
top-level `people` on create and `patch.people` on update. Omitted create people
normalizes to the applicable empty array; omitted update people remains omitted,
meaning preserve all rows, not clear. Wrong-role arrays fail even when empty.

V4 rejects legacy `task_detail.subject_roles` authoring, including under
`patch.item.task_detail`, rather than accepting two competing managed-role inputs.
Existing owner/watcher/recipient rows copy forward unchanged. V3 and older role
authoring remain supported with their existing semantics; this is not a global
removal. Authoring those unmanaged roles through v4 is outside this slice.

Canonical arrays sort by Unicode scalar code point before path assignment, after
rejecting duplicates. IDs are opaque nonempty scalar strings, at most 256 code
points, without ASCII controls/DEL; no trimming, case folding or Unicode normalization.
All decimal fields are JSON strings. Ordinary row IDs reuse `spine.command-id.v1`
and its canonical preimage. The companion enumerates the normalized array paths;
unchanged omitted rows use the existing `/copy_forward/item_subject_role/<prior_id>`.
Requested replacements emit new active rows at their normalized array paths,
including retained subjects. Historical source rows are never updated.

Standalone changed success has `effect=item_people_updated`, one next item version,
one audit and one receipt. Semantic no-op has `effect=item_people_noop`, unchanged
version and no audit; a fresh command still records its normal receipt. Compatible
replay returns `effect=item_people_replay`, the original result's versions, immutable
association rows, truth_changed and receipt (with original effect), without writes.
Thus a changed replay reports original `truth_changed=true`, not a new mutation.
Dry-run marks `dry_run=true` and returns deterministic would-be IDs/effects after
the same proof, rolling everything back. It is a context flag, never request JSON.

`work_changed=false` always for standalone people edits. V4 schedule effects keep
their existing changed/reconciled/no-op/replay meanings; `people` joins
`changed_dimensions`. A people-only v4 patch requires `materialization.mode=none`;
presentation-only exclusivity remains unchanged. People combined with other existing
schedule dimensions is one ordinary atomic composite, not two handler commits.

The standalone semantic receipt hash preimage is canonical JSON exactly
`{derivation_version:"spine.item-people-semantic-facts.v1",
canonical_json_version:"spine.canonical-json.v1",request:<normalized complete request>}`.
This includes command ID, actor and action timestamp. A managed role-set hash is
`{derivation_version:"spine.people-role-set.v1",canonical_json_version:
"spine.canonical-json.v1",item_type,roles:[{subject_id,role,status}]}` with tuples sorted
by role/subject/status, excluding physical row IDs and timestamps. It includes
inactive rows, so removing one is not an active-set no-op. V4 receipts use their
new receipt selectors and include normalized people in the owning scheduling
semantic preimage; all other facts/defaults retain v3 normalization. Historical
receipts are never rehashed. Protected replay first checks initiating identity and
current receipt/item disclosure, then exact normalized compatibility; it does not
rerun fresh-add eligibility or require fresh edit authority. Labels are not replayed.

### 13.3 Protected admission, failures and independent reads

The companion's ordered stages and CLI/HTTP mappings are normative for this
candidate. Shape errors select the smallest extra JSON Pointer, then smallest
missing pointer, then selector errors, then other schema errors by pointer and
keyword (code-point order), returning one error. Apply all reference/type/lifecycle
checks only after root admission; replay precedes fresh expected-version checks.
Expected-access mismatch precedes target-version mismatch. No missing/private item
or fresh subject reference may be distinguished by an error message or error field
containing a hidden ID. A fresh reference error points to the whole people field.
Protected errors use the closed generic envelope; direct local errors use the
common command taxonomy and the candidate's safe message classes. Scheduling
errors outside people validation retain their owning command semantics.

Protected item-only grantees may retain/remove existing associations, but cannot
enumerate the group's roster or add/reactivate a fresh reference without directory
authority. A subject-owned item has only its owner subject as a fresh protected
reference. D-02 allows association IDs/statuses under current item read, not discovery
of account/contact/other-item facts. Label authority is evaluated for the associated
subject through self-directory authority or a shared currently readable group roster;
it is not limited to the item's current owner if ownership changed. If no such
authority exists, emit only `availability=not_disclosed` for that subject's label.
Fresh additions still require the target owner's scope under D-01.

New protected read successors preserve every existing independent-read core/time
and optional-section rule. They add a complete optional `people` section to schedule
and agenda views; it is available, not_requested or unavailable with a closed
non-private reason. Never interpret not_disclosed as service failure, or failure
as ordinary nondisclosure. There is no people-section cursor: the entire managed
set must fit its 100-row/byte ceiling. Existing subject_roles remains self-only.
People count/labels cannot remove an otherwise readable activity/time result.

Agenda and occurrence requests may carry `person_filter`; omitted roles default
to sorted `["assignee","participant"]`. No filter means no people restriction.
Filtering accepts a syntactically valid ID without subject-existence lookup.
Authorize candidate items first, then apply current active exact role matching,
then temporal expansion, output ordering and pagination. Hidden IDs have the same
empty result as absent IDs when neither matches an authorized item. A nonmatching
direct occurrence query returns empty complete occurrences while preserving its
authorized activity/time, unless time itself is unavailable under the independent
read contract. Recurrence occurrence identity/order is unchanged; roles are series-
level. Tasks with unavailable time remain in the authorized unplaced stream.

### 13.4 Cursor, snapshot and resource contract

Every budget is request-global, including initial reads, current-authority/release
fences, role/label queries, proof construction and serialization; do not reset per
section, person, policy or page. The companion gives exact ceilings. Use the stricter
owning adapter ceiling. The 1000 authorized-candidate ceiling is not permission to
resolve 1000 protected resources: the separate 100-resource/access-proof ceilings
still apply. Fetch at most ceiling+1 for overflow detection; fail rather than
returning a success with an incompletely computed source snapshot. A 1000+ roster
may therefore require a later contract, not hidden-offset traversal. Existing
over-limit item roles remain untouched; do not run startup scans or trim history.

People optional sections share the existing optional SQL/byte budget, cannot consume
the core reserve, and cannot suppress activity/time on their own overflow. Hard
outer expiry/SQL limits may still fail the operation. Both first page and continuation
use one admitted snapshot and a final current-authority/source fence, without automatic
retry. Reads never write a receipt, cursor row, audit or cache generation.

The cursor token is `pc1.<payload>.<mac>`: unpadded canonical base64url of canonical
UTF-8 JSON and a 32-byte HMAC-SHA256. MAC input is UTF-8
`spine.people-cursor.v1`, NUL, then the exact canonical payload bytes. Enforce canonical
encoding/JSON, constant-time MAC comparison, the exact admitted key ID/generation
and ledger instance; never accept another cursor family. Configuration is protected
service context or local `SPINE_PEOPLE_CURSOR_CONFIG`, not request JSON. Missing
configuration fails closed before listing. No secret is returned or placed in
fixtures other than clearly marked test-only bytes.

`query_hash` hashes exactly `{derivation_version:"spine.people-query.v1",
canonical_json_version:"spine.canonical-json.v1",route,request,guards}`. Strip cursor
and section_cursors; normalize declared defaults/set arrays, bind all limits/includes,
and represent absent expected access/item/recurrence guards as null. No new server
authorization time comes from request evaluation timestamps. Empty optional include
normalizes to `[]`; role omission means both, not an empty role set. Continuations
retain the original issue/expiry, at most 900 seconds, and authorization validity
ends at the next relevant grant/membership activation or expiry, even without an
epoch change. Keys/identity/access/query/source changes invalidate continuation.

`source_hash` hashes `{derivation_version:"spine.people-source.v1",
canonical_json_version:"spine.canonical-json.v1",route,sources}`. Sources are the
owning independent read's authorized contributing facts plus role tuples and any
directory metadata actually used for disclosed labels; roster sources are the
authorized scope, effective membership evidence and filtered subject ID/status/kind/
label/update facts, sorted by subject ID. Never hash hidden item graphs or private
directory facts. A hidden label change alone cannot invalidate a redacted label view.
For agenda, person-filter mismatches do not contribute source facts. Relevant
authorized insertions/removals require recomputing bounded candidate selection.

`authorization_hash` hashes `{derivation_version:"spine.people-authorization.v1",
canonical_json_version:"spine.canonical-json.v1",context}`. Local context is
`{mode:"trusted_local",ledger_instance_id}`. Protected context is the exact admitted
realm/recovery/account/subject/selection/revision/access-epoch tuple plus sorted
scope/item/directory permission proofs actually used and their transition fence;
it never contains secrets. Recheck that proof at release. Cursor schema additionally
binds route, stream, required item/range fields and last ordering tuple. Roster order
is exact subject ID; existing sections/agenda/occurrences reuse v2 ordering tuples
with new family binding. No people section is pageable.

### 13.5 Role-only continuity and physical verification

The new proof compares every same-item immediate version edge, allowing only the
normalized requested managed-role delta and documented copy bookkeeping. Everything
else in the companion's unchanged dimensions must compare equal. All prior policy
rows, including disabled/ordinary/presentation rows, require a unique immediate
successor via source_notification_policy_id; compare all existing policy meaning
fields plus presentation and resolved targets. No intent-only matching, forks,
cross-item ancestry or nondecreasing links. Source row IDs may change; original
work/attempt FKs, provider IDs and histories may not.

Mixed facet-only, presentation-only and role-only lineages must validate each edge
under that edge's own unchanged proof contract. Do not use one enlarged allowlist
for every edge or weaken facet-only role equality. No persistent proof registry/table
is introduced. Bound ancestry traversal by 100 edges under the same request budget;
overflow fails closed as capacity, without mutation or cancellation. A composite
whose time/route/policy meaning changes follows its ordinary reconciliation instead.

Editing a source event can independently stale a follow_source task's binding by
existing source-version rules, even when the source change is people-only. This
proof preserves the edited item's unchanged target binding; it does not bless
dependent source-version snapshots. Reconcile dependents separately, preserving the
existing granularity and no implicit role inheritance. No future advisory input
freshness is relaxed. Started attempts remain immutable, regardless of later edits.

Existing `(item_id,version,subject_id,role)` uniqueness and the subject/status/item/
version index remain physical authority. Roster reads use group/status/subject
membership indexing with current membership/subject/scope checks. Item projection
uses bounded exact `(item_id,version)` reads; person filters use EXISTS against exact
current-version role tuples after indexed authorized-owner/grant candidate selection.
Do not rely on an SQLite autoindex's generated spelling. PR-12 must record EXPLAIN
and candidate/VM-step evidence on sparse/dense authorized and hidden data; a required
additional index would need its own migration/manifest, not an implicit startup DDL.
No schema number, migration or physical layout change is allocated by this contract.

Runtime activation requires PR-01–16 in the companion, including public CLI/HTTP
tests, writer/finalizer inventory, mixed continuity/work state/race tests and exact
installed dependency closure. Neither this accepted logical spec nor structural/
pure-model fixture checks establish those completed runtime proofs.
