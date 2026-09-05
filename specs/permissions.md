# Spine Resource Permissions and Access Modes

Status: Draft v0.2.0; trusted multi-operator identification first; protected authentication deferred; not implemented or audited
Created: 2026-09-05

## 1. Scope and Authority

Specify the full multi-user permission model with trusted multi-operator identification
as the first delivery. Single-operator and multi-user are modes of one architecture, not two
different account or item ontologies. This document owns proposed resource permissions,
group roles, and mode semantics. [accounts-and-chat-attribution.md](accounts-and-chat-attribution.md)
owns accounts and assurance; [identity-and-access.md](identity-and-access.md) owns
authentication and delegation boundaries; [ontology.md](ontology.md) remains the
implemented storage authority. No current enums, schemas, or commands change here.

The role defaults in Section 5 develop the earlier proposal and remain subject to
review. Supported-operation contracts and policy tests precede multi-user behavior;
authentication qualification additionally precedes verified-identity or secure-isolation
claims. The direct CLI remains a trusted-local
full-scope administrative path; this draft does not move it behind a service.

## 2. Access Modes

The server uses one administrator-configured mode per ledger deployment. It is not a
request flag, account attribute, group role, or caller-selectable parameter.

| Mode | Sign-in and application access |
|---|---|
| `single_operator` | Only the explicitly configured active operator account is admitted to the coordination application; it has full ledger-wide application permissions |
| `multi_user` | Each admitted active account uses its current subject binding and resource permissions, not automatic ledger-wide operator access |

Identity posture is independent: `identity_mode=trusted_identity` accepts honest web
selection or registered observed-agent attribution; `verified_identity` requires
qualified authentication. The first target is `multi_user` plus `trusted_identity`.
Permissions apply to the selected identity but cannot prevent choosing someone else's.
These are administrator-configured modes, never per-request downgrade flags.
[permission-enforcement-and-web-admission.md](permission-enforcement-and-web-admission.md)
Section 1 defines the trusted deployment and deferred protected gates. No openly reachable
website or authenticated-isolation claim is permitted under trusted identity.

In multi-user mode an unbound account may access only its explicitly defined account
onboarding/self-service surface, not coordination records. Provisional, suspended, or
closed accounts follow their lifecycle restrictions; knowing a phone number is not
sign-in. A valid account with no group memberships can access only its own or explicitly
shared resources. Signup grants no existing data, group membership, or administrative role.

Single-operator mode gives the configured operator read, creation, mutation, sharing,
and administration authority across application resources, regardless of their owners.
Other accounts can exist without being admitted as operators. No unknown caller maps
to the operator, and no subject/group rows are rewritten to implement this mode.
Full access does not bypass domain validation, immutable system-catalog restrictions,
transaction/receipt rules, or separately required external-action approval.

Neither mode authenticates the local CLI today. Its existing host privilege is an
explicit exception in Section 11, not an implicit single-operator session. Observed
chat attribution cannot satisfy verified web login in either mode.

## 3. Resource Ownership

Every item exposed through multi-user coordination access has one explicit owner:
a subject or a subject group. Existing `item_subject_roles.owner` is not this record.
Unresolved legacy item ownership requires adoption; it must not become public by default.

Catalogs, bindings, and delivery targets reuse their existing canonical owner facts;
do not duplicate those owners in a competing registry. System-owned catalogs require
an explicit deployment read/use policy; system ownership is not automatic public access.

Subject-owned resources are private to that subject unless explicitly shared. A group
admin gains no access to a member's private items, account methods, or other groups.
Acting for a child or another subject requires an explicit grant; being in the same
group or creating that subject does not automatically confer account or data ownership.

| Resource family | Access rule |
|---|---|
| Items and their versions | Current item owner, group-role rights, and explicit item grants |
| Recurrence, effective policies, and item-bound work | Governed by item access; mutating their behavior requires item mutation permission |
| Item history and receipt evidence | Current resource permission plus receipt-disclosure rules; old IDs do not preserve revoked access |
| Archetypes, profiles, default bindings | Own catalog owner/role/grant policy, independent from items applying them |
| Delivery targets | Own read/use/administration policy; route visibility or use does not authorize releasing every item's contents |
| Accounts and authentication methods | Account-management policy; not inherited from group administration |
| Shared locations, relations, and reusable references | Explicit family-specific mapping and endpoint checks before multi-user exposure |

New item creation supplies the chosen owner explicitly. The server checks permission
to create within that scope. Profile selection, participants, assignment, conversation,
creator identity, and notification recipients cannot silently change ownership.
An item may use a permitted shared profile and still remain privately owned.

## 4. Permission Operations

Permission operations distinguish read, create, mutate, use, share, administer,
release content, and transfer ownership. Each resource family defines which apply;
the release command-to-permission registry must map exact commands and nested effects.
Missing mappings deny exposure, rather than treating every write as equivalent.

Read includes current resource content and authorized history, not unredacted nested
foreign resources or security secrets. Item mutation includes edits, completion,
cancellation, and archive subject to ordinary domain rules. It does not imply sharing,
ownership transfer, catalog administration, or arbitrary delivery release.

Catalog use includes the definition necessary to validate/explain its application,
not revision, retirement, or default rebinding. Route use and content release are
separate checks: neither a readable item nor a usable target alone is sufficient to
send that item to an arbitrary audience. Per-command effect schemas must make this
distinction enforceable for both direct commands and composite scheduling commands.

Explicit grants supplement ownership and role permissions. Each names one resource,
subject/group grantee, allowed operations, status, effective interval, revision, and
granting evidence. Initial grant kinds are item read/edit and catalog read/use;
delegated re-sharing and free-form role definitions are deferred. Grant administrators
cannot delegate rights they do not control. Revocation of one grant does not cancel
an independent valid grant; access inspection must explain the remaining authority.

## 5. Group Roles

Roles are membership facts scoped to one arbitrary subject group, not account types
or reserved group labels. The proposed effective roles are member, admin, and owner.
Admin includes member rights; owner includes admin rights. No group hierarchy or
cross-group inheritance is implied. Their physical membership representation requires
an explicit ontology extension before implementation.

| Operation on group-owned resources | Member | Admin | Owner |
|---|---|---|---|
| Read items and use group catalogs | Yes | Yes | Yes |
| Create group items | Yes | Yes | Yes |
| Edit/complete/cancel/archive own created items | While actively a member | Yes | Yes |
| Mutate another member's item | Explicit edit grant | Yes | Yes |
| Revise/retire group catalogs or default bindings | No | Yes | Yes |
| Manage item sharing and group delivery targets | No | Yes | Yes |
| Add/remove ordinary members | No | Yes | Yes |
| Appoint/demote admins | No | No | Yes |
| Transfer group ownership or retire the group | No | No | Yes |

Group-owned items are visible to all active members under these proposed defaults.
Private exceptions use subject-owned items and explicit sharing, not hidden per-item
denies inside the group. Readability does not imply every member may release data to
an outside audience. Default route-use and content-release policy need explicit
operation mappings; the table does not grant arbitrary sends.

Creator mutation rights bind to the original initiating subject, not the executing
agent or caller-controlled participant fields, and apply only while the item remains
owned by that same group and the creator remains an active member. Transferred items
do not carry these rights to another group. Unproven historical creator identity
receives no automatic creator-derived entitlement during adoption.

Each active group has exactly one designated owner in this proposal. The owner's
eligibility to act is checked separately. Ownership handoff is
atomic, requires an eligible accepting successor, and cannot leave the group ownerless.
An admin cannot promote themselves, remove the owner, or change account bindings.
Requests affecting both membership and role must be checked by resulting authority;
an admin cannot evade the rule by deleting and recreating an owner's membership.

Account suspension and subject inactivity immediately prevent that person's access;
they must not be rejected merely to preserve a group owner. If that leaves a group
without an eligible acting owner, block owner-only administration until explicit
trusted recovery appoints a successor. This does not grant the acting admin ownership.
The migration and recovery contract must distinguish a designated owner from an
eligible acting owner rather than silently restore suspended access.

## 6. Multi-User Evaluation

The proposed decision order is:

1. Establish the account under the configured identity posture and require eligible
   account/binding state; verify authentication proof only in `verified_identity`.
2. Resolve deployment mode and current account-to-subject binding.
3. Establish the requested command, complete resource set, and all nested effects.
4. In single-operator mode, require the configured operator; otherwise evaluate current
   owners, active memberships/roles, and explicit grants for every required operation.
5. Apply any authenticated executor/delegation restrictions and response-audience
   constraints. A less-privileged executor cannot borrow broader user rights.
6. Check applicable external-action governance independently, then normal domain
   preconditions. Commit authorized mutations with current policy/ownership revisions.

No permissions from distinct identities are unioned into a more privileged caller.
Web is not automatically high-assurance; trusted selection is explicitly unverified.
In protected admission the actual method/session determines assurance.
Account presence and prompt metadata cannot supply a missing
verified principal or authenticated executor. The trusted-local exception is not
implemented as a request-selectable fallback through this evaluator.

Permission revision checks must linearize with mutations; a prior committed revocation
blocks subsequent writes. Read results require consistent current authorization before
release. Caches/cursors bind to caller, mode, query, audience, and access revision;
switching modes invalidates them. Detailed race/locking and failure mappings require
machine contracts and concurrency fixtures before deployment.

## 7. Reads, Links, and Existing Domain Behavior

Filtering occurs before list counts, pagination, includes, and expansion. No authorized
caller may enumerate private resources through errors, IDs, receipts, search counts,
or side-effect diagnostics. Existing full-inventory discovery must have a declared
access-scoped successor or remain restricted; it cannot silently change its contract.

Cross-resource relationships confer no access inheritance. Linking requires an explicit
permission check on both endpoints; exact family rules precede exposing those commands.
A relation, follow-source binding, or shared place must not leak an inaccessible item's
title/time through another visible resource. Unsupported redaction fails closed; do not
invent a partial JSON shape or export sensitive data and expect the GUI to hide it.

Authorized profile snapshots remain part of the item's evidence even if later catalog
access changes. Current or historical catalog content outside that stored snapshot
requires separate permission. Resolution scope chains must not skip unauthorized scopes
and silently choose a different profile. Permissions never rewrite recurrence, work
identity, delivery outcome, or immutable historical receipts.

## 8. Transfers, Revocation, and Background Work

Ownership transfer requires current-owner authority, explicit acceptance authority in
the destination scope, expected revisions, and an atomic grant/delivery review. It
does not transfer related items, source catalogs, or routes. No new share/route rights
are inferred from the destination's name or transport channel.

Account logout does not cancel accepted work. Group membership removal removes only
group-derived rights; independent explicit grants require their own revocation.
Workers retain separately defined service authority, not an expired browser session.
Before multi-user notifications ship, a delivery-authority contract must define which
current item/route grants allow each attempt, revoke future release when necessary,
and preserve actual in-flight or completed outcomes. This draft does not introduce
that machinery into today's trusted-local worker.

Future facet values should inherit their owning item's access; facet-schema catalogs
need separate use/administration rules. Advisory runtimes receive explicitly authorized
bounded context and output acceptance, not general ledger access. Neither future area
requires changing the account identity or group-role model, and neither is implemented
by these permission rules alone.

## 9. Mode Changes and Adoption

The immediate target is trusted multi-operator use with a declared supported-operation
policy surface. Reject unsupported identity/access combinations and operations, and
advertise actual trust posture, not authenticated isolation. Single-operator full scope
remains optional. Complete protected-mode gates apply when enabling `verified_identity`,
not as a requirement to build every future feature for the trusted first slice.

Switching to multi-user mode is privileged deployment administration, never a browser
or chat parameter. It requires eligible accounts under the configured identity posture,
explicit subject bindings and item owners,
resolved memberships, grant/route policy, revision-aware reads/replay, and activation
tests. Ambiguous existing ownership needs an operator decision, not an inferred backfill.

Switching back requires explicit approval of broader operator visibility, session and
cache invalidation, and a safe stop/restart or equivalent atomic mode transition. Do
not select permissive mode when authentication or authorization is unavailable.
Mode changes preserve account IDs, subject IDs, item owners, and historical evidence.

## 10. Policy Administration and Inspection

Group owner, resource owner, deployment operator, account administrator, and executor
are distinct authorities. An owner of one group is not the deployment operator. Account
administration cannot silently grant resource access through subject relinking.
Recovery requires explicit trusted administrative authority and audit evidence.

An effective-access read surface must explain the caller's allowed operations and
their ownership/role/grant source, mode, and revision without revealing private grants
of unrelated callers. Changes to roles, grants, owners, and configuration are auditable;
ordinary permission checks and denied requests must not produce unbounded ledger rows.
Exact operations, error names, evidence schemas, and budgets remain release gates.

## 11. Trusted-Local CLI Boundary

No CLI restriction is introduced now. Existing direct local tools retain their current
full ledger scope and domain validations. There is no executor-token deployment or
OpenClaw extension in this slice. Code modules and direct database access available to
that OS identity remain outside web admission.

Multi-user web permissions protect only server-mediated callers. Anyone with trusted
local ledger access can bypass that permission boundary and must be treated as a host
administrator. A deployment must not give untrusted users or user-controlled code that
OS access and claim end-to-end isolation. This is an explicit operational trust boundary,
not a defect hidden by a successful permission test.

The web backend calls shared command handlers directly, not by shelling out to the CLI.
Web, CLI, and worker may coexist against the ledger after concurrency, stale-version,
busy-timeout, rollback, and retry behavior are verified. Routing CLI through the backend
is a separate future enforcement change, not a prerequisite for the data/role model.

## 12. Required Acceptance Families and Gates

| ID | Future oracle |
|---|---|
| PERM-01 | Active authenticated accounts sign in without acquiring existing records or group roles |
| PERM-02 | Only the configured single operator receives ledger-wide application access; other accounts and unknown callers do not |
| PERM-03 | Multi-user callers see own, group-role-accessible, and explicitly shared resources only |
| PERM-04 | Members cannot edit another subject's items without an explicit edit grant; group catalog and delivery-route administration requires the admin or owner role under the proposed defaults |
| PERM-05 | Admins can manage their group's resources but not private member items or owner-only actions |
| PERM-06 | Owner handoff and suspension/recovery preserve access revocation without self-promotion or automatic succession |
| PERM-07 | Direct and embedded effects enforce the same permissions; failures roll back the entire composite |
| PERM-08 | Revocation and mode transitions invalidate cached allows, pages, sessions as required, and unreleased private results |
| PERM-09 | Unauthorized nested references, counts, history, and replay cannot leak data |
| PERM-10 | Profile snapshots and existing domain identities remain unchanged by access changes |
| PERM-11 | Mode changes do not rewrite owners or silently backfill account/group roles |
| PERM-12 | Trusted-local CLI retains existing behavior; tests and docs do not claim that web checks constrain host administrators |
| PERM-13 | Two trusted operators retain distinct bindings and role-based behavior; identity switching clears context and never claims authentication or grants full scope |

The immediate trusted slice requires exact schemas/tests for its declared policy surface;
the full list below gates protected multi-user implementation, not every trusted feature.
Before protected multi-user implementation, publish physical ownership/role/grant schemas,
command-to-permission/effect mappings, sign-in/session admission, provisioning and
adoption commands, bounded authorized query contracts, delivery authorization, recovery,
and concurrency fixtures. Role and policy defaults require ratification and a bounded
audit. This specification does not implement an IAM provider or a new general policy language.
