# People and Responsibility

Status: Draft v0.1.1 — operator-approved product policies; contract not ratified or implemented
Created: 2026-10-16
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
This leaf proposes participation/assignment behavior and its public surfaces.
[Schedule creation](schedule-create.md), [operations](schedule-operations.md),
[independent reads](independent-activity-reads.md) and
[relative bindings](relative-temporal-bindings.md) retain their existing authority.

This draft changes no implemented command, schema, registry, permission, package
version or released pack. Proposed names and examples below are not callable runtime
contracts. Product decisions D-01/D-02 were approved on 2026-10-16; review and
Section 12 gates still precede ratification and implementation. This document is
not an implementation-readiness claim.

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
  draft does not remove or reinterpret those accepted requests or historical rows.
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

## 5. Proposed public operations

These are logical operation reservations, not implemented selectors or routes:

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
migration/manifest explicitly. This draft activates no DDL or schema number.

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
first scope. Approval settles product policy, not ratification or runtime exposure.

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

Before implementation: review this draft with approved D-01/D-02; define closed schemas,
versioned standalone/composite/read projections, compiled/runtime declarations,
permission/reference/effect mapping, exact cursor/preimage and limit/error rules,
role-only work-continuity integration, physical/query-plan requirements, operator
examples and fixtures. Preserve frozen registries and v1/v2/v3 families; do not add
fields to a released closed envelope or claim machine artifacts already exist.

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
