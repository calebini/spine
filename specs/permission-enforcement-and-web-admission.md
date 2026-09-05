# Permission Enforcement and Web Admission Contract

Status: Draft v0.2.0; trusted multi-operator identification first; protected authentication deferred; not implemented or audited
Created: 2026-09-05

## 1. Authority and Delivery Boundary

[permissions.md](permissions.md) owns the access modes and role/grant policy. This
document operationalizes that policy: proposed storage, admission, effect resolution,
command exposure, revocation, and evidence. [accounts-and-chat-attribution.md](accounts-and-chat-attribution.md)
owns account lifecycle and observed chat attribution; [identity-and-access.md](identity-and-access.md)
owns authentication/delegation architecture. [ontology.md](ontology.md) and
[agent-command-contract.md](agent-command-contract.md) remain the implemented ledger
and command authorities. No existing schema, enum, handler, or response changes merely
because this draft names a successor. Where physical changes are proposed below,
an explicit ontology amendment, migration, schemas, and fixtures precede implementation.

### 1.1 Immediate trusted multi-operator delivery

First delivery supports multiple trusted operators, initially two, using honest
identification rather than verified authentication. Accounts stay distinct from
subjects; owners, roles and grants remain application policy. Calling someone an
operator does not automatically grant full ledger scope.

Two administrator-configured settings are independent:

- `access_mode=single_operator|multi_user`: one configured full-scope account versus
  ownership/role/grant-based access for several accounts.
- `identity_mode=trusted_identity|verified_identity`: honest selection/attribution
  versus qualified authentication.

The immediate target is `multi_user` plus `trusted_identity`. Neither setting is a
caller-selectable fallback. Permissions apply to the selected identity, but anyone
with interface access can select another available identity. Disclose this in the UI
and documentation; do not claim authenticated isolation or verified human intent.
Restrict reachability to trusted devices/operators with host/network controls, not an
unadvertised URL. This is not suitable for an openly reachable website.

Administratively provision active accounts, subject bindings and an eligible operator
list. Web users choose who they are: identification, not login. The restricted chooser
exposes configured operator labels, not a public phone lookup. Unknown/missing selection,
inactive/suspended/closed accounts or missing bindings block operations, with no default
to either operator. Arbitrary names/numbers cannot create an account or subject binding.

A browser may retain selection as interaction context, not proof. Each request resolves
current account/binding state and checks owners, roles and grants for that subject.
Identity switching clears views, drafts, confirmations and cursors; pending mutations
are never resubmitted under another account or command ID. Ordinary request-integrity,
origin/CSRF and resource-limit protections still apply without authenticating the human.

WhatsApp continues registered observed sender mapping, trusting agent attribution and
respect for mapped-subject rights. Direct CLI access stays privileged; no protected
executor ceiling is claimed. Evidence records `identity_basis=self_selected` for web
or `agent_observed` for chat, never `verified`; later login cannot upgrade past evidence.

The first slice needs declared supported-operation policy checks, explicit ownership/
membership state, bounded filtered reads and ordinary domain replay/transaction safety.
Unsupported operations deny; unresolved owners never become shared. Every future grant,
transfer, delivery-mandate and recovery command need not ship first. Existing trusted
CLI/worker behavior is unchanged; per-user attempt-level delivery enforcement is deferred.

Recovery is manual trusted-local account/binding repair. Verified login, automated
WhatsApp/password recovery, executor tokens and OpenClaw qualification are deferred.
Later verification replaces selection without replacing accounts, bindings, owners or
roles, but requires explicit verification, fresh sessions and review of trusted changes.

Immediate acceptance families (future tests, not implemented behavior):

| ID | Required outcome |
|---|---|
| TID-01 | Two eligible accounts retain distinct subject bindings and group-role behavior; neither gains full scope merely by being selectable |
| TID-02 | Unknown/missing/inactive/unbound identity blocks operations with no fallback; switching clears prior identity context and pending intents |
| TID-03 | Allowed/denied actions reflect the selected identity, including owner-only transfers and approved member routes where exposed |
| TID-04 | Evidence distinguishes self-selection, agent observation and verified authentication; no historical promotion of assurance |
| TID-05 | Trusted-only reachability and visible impersonation warning are verified before deployment; current local CLI/worker behavior is preserved |
| TID-06 | Identity-mode changes are administrative, invalidate contexts and never downgrade failed verified authentication to trusted selection |

Publish the immediate subset's exact request/evidence shapes and tests before declaring
it implemented. The protected `spine.permission-enforcement.v1` family cannot be advertised
merely for passing these trusted-identity checks.

### 1.2 Preserved deferred protected delivery

The remaining first-delivery language below and Sections 2-12 describe the future
`verified_identity` path, including S/M command exposure and protected release gates.
They are not prerequisites for Section 1.1. Shared role/domain semantics apply in both;
authentication and delivery-security requirements remain preserved, not weakened.

The retained protected design permits a verified single-operator gateway before full
protected multi-user qualification; it does not require an existing trusted two-user
deployment to collapse to one user. Verified multi-user activation requires its full
protected gates. Both reuse shared command handlers. The current local
CLI and worker retain their privileged host access. Protected agent delegation,
OpenClaw qualification, and moving the CLI behind a service are later capabilities,
not prerequisites for that web delivery. This sequence supersedes the earlier
chat-first implementation sequence in the protected-admission drafts, not their
security requirements if those paths are eventually exposed.

The first release MUST implement sections 3, 5-8, 10-12 as applicable to single-operator
requests: stable account/binding admission, sessions and revocation, an exact exposure
registry, bounded reads, atomic authorization evidence, configured budgets, and
trusted-local coexistence. Multi-user ownership/roles/grants, access-scoped queries,
and delivery mandates are specified here but MAY remain unavailable. A build without
all protected multi-user gates MUST reject `verified_identity` plus `multi_user` configuration.
No new login method, identity provider, arbitrary policy language, facet engine,
advisory runtime, or HTTP framework is selected by this contract.

## 2. Value, Identity, and Revision Conventions

The proposed family is `spine.permission-enforcement.v1`; its registry is
`spine.permission-command-registry.v1`. These identifiers MUST NOT enter implemented
capability declarations until the owning schemas, tests, and behavior ship.

New persisted IDs are TEXT opaque identifiers; public strings are nonempty, at most
256 UTF-8 bytes, and contain no control characters. References to existing IDs retain
their current contract. Integers are SQLite INTEGER in `0..9223372036854775807` and
canonical unsigned decimal strings on the wire; revisions begin at 1, never wrap.
Timestamps use `YYYY-MM-DDTHH:MM:SSZ`; intervals are `[starts_at_utc, ends_at_utc)`;
SQL NULL / omitted wire field means no end. All times in a decision use one captured
server evaluation instant, never caller time. Caller domain timestamps retain their
existing domain meaning. Optional values are omitted from canonical JSON hashes.
Hashes and serialization use `spine.canonical-json.v1` as defined in the ontology.

Command-created security records use the existing `spine.command-id.v1` derivation
with new row roles explicitly registered before release. Prefix equals row role:
`item_access_owner`, `access_grant`, `access_transfer`, `delivery_mandate`, and
`authorization_evidence`. Paths are respectively `/access_owner`, `/grant`, `/transfer`,
`/mandates/<policy_id>`, and `/authorization`; identifiers must not encode phone numbers.
Membership creation uses role `subject_membership` and path `/membership`. Revision
identity is `(record_id, revision)`; a revision has no second generated ID.
Security/session secrets use cryptographic randomness, not command-derived IDs.

Every canonical security mutation writes one immutable revision and changes its head
in the same transaction as audit/receipt evidence. Common revision fields are
`revision`, `changed_at_utc`, `changed_by_subject_id`, `command_receipt_id` and the
complete resulting state, not a JSON patch. Heads contain identity and current revision;
required searchable fields may be mirrored only with transactional parity checks.
No-op and replay create no revision or access-epoch increment. History cannot be
edited by a metadata update. The single `command_receipts` authority remains the replay
index; these tables do not create an independent replay store.

## 3. Persistence and Linearization

### 3.1 Deployment access state

`ledger_access_state` contains exactly one row keyed by the existing configured ledger
identity: `ledger_id`, `realm_id`, `mode` (`single_operator|multi_user`),
`identity_mode` (`trusted_identity|verified_identity`),
`operator_account_id` (required only in single-operator mode), `access_epoch`,
`mode_epoch`, `recovery_epoch`, `configuration_revision`, `registry_version`,
`registry_hash`, and `budget_hash`. Epochs start at 1. Realm and ledger are server
configuration, never accepted database paths in a request.

An authorization-relevant mutation increments `access_epoch` once per transaction.
This includes owners, roles, grants, subject/group status, account eligibility or
binding, executor grants, system-catalog policy, and route audience/mandate changes.
Mode change increments both mode and access epochs; restored backups require a fresh
externally established recovery epoch before reopening admission. Ordinary item edits
use item revisions; owner transfer also increments access epoch. Global invalidation
also applies to identity-mode changes, which require explicit administration and
invalidate previous interaction/session contexts. Failed verified admission never
falls back to trusted selection. Invalidation
is intentionally conservative and uses a single indexed row, not a ledger-wide hash.

### 3.2 Item access ownership

`item_access_owners` has unique `item_id` FK to `coordination_items`, stable
`item_access_owner_id` PK, and `current_revision`. `item_access_owner_revisions` has
PK `(item_access_owner_id, revision)`, common revision fields, `owner_kind`
(`subject|subject_group`), exactly one of `owner_subject_id`/`owner_group_id` with
the corresponding FK, and optional `creator_entitlement_subject_id` FK. The creator
entitlement is set only from proven initiating-subject evidence when the item is
created into that group; adoption cannot infer it from an historical agent actor.
Transfer clears it. It never grants rights to a new owner group.

Every multi-user-visible item has exactly one current access owner. No owner means
unadopted, not public. Recurrence sets, anchors exclusive to the item, effective
policies, work, stored profile snapshots, and attempts resolve to the root item for
access. Archetypes, profile definitions/default bindings, and delivery targets retain
their existing canonical owners; do not copy them into `item_access_owners`.
For the current immutable catalog-owner contracts, the access-owner revision is 1;
profile/template/metadata revisions do not advance it. Any future catalog ownership
transfer needs an explicit successor owner-revision contract. Route-security revisions
are instead advanced on owner, status, endpoint or audience changes, not on a harmless
display-name edit. The head projections must enforce those distinctions.
Owner indexes cover `(owner_subject_id,item_id)` and `(owner_group_id,item_id)` on the
validated current projection. Item versions and IDs are unchanged by an access transfer.

### 3.3 Membership roles

The successor `subject_memberships` retains its identity, group/subject FKs, start/end
semantics, and ended-terminal lifecycle. It adds `current_revision`; the successor
role domain is exactly `member|admin|owner`. `subject_membership_revisions` stores
complete role/status/start/end state and common revision fields. Existing current
columns remain the transactionally checked head projection, not a competing ACL.

Partial unique indexes permit at most one active membership per `(group_id,subject_id)`
and at most one active owner membership per group. Every adopted active group MUST
have exactly one designated owner at transaction commit; creation, handoff, retirement,
and adoption enforce this transaction invariant. An inactive owner subject or suspended
account remains designated but cannot act; recovery must not reactivate them to satisfy
the invariant. Rejoining creates a new membership ID. Role changes require the expected
membership revision and never reopen an ended membership.

### 3.4 Explicit grants

`access_grants` has `grant_id` PK and `current_revision`. `access_grant_revisions`
contains common fields, `resource_kind` (`item|item_archetype|notification_profile`),
`resource_id`, `resource_owner_revision`, `grantee_kind` (`subject|subject_group`),
exactly one corresponding grantee FK, `status` (`active|revoked`), `starts_at_utc`,
optional `ends_at_utc`, and `grantor_subject_id` FK. Polymorphic resource references
MUST be checked against the fixed three-table dispatch, with deletion protection;
unknown kinds cannot be accepted as strings and resolved later.

`access_grant_operations` has PK `(grant_id,revision,operation)` and FK to its revision.
For items its nonempty set is a subset of `{item.read,item.edit}` and `item.edit`
requires `item.read`. Catalog sets are subsets of `{catalog.read,catalog.use}`;
`catalog.use` requires `catalog.read`. No route, share, administration, ownership,
or delegation operation is grantable in this version. In particular item edit never
permits catalog/default-binding or route administration.

Revoked is terminal. Each new grant needs a new command ID and grant ID; overlapping
grants remain independent authorities. Current grant lookups are indexed by resource
and grantee; no recursive group expansion exists. A group grantee matches active direct
membership in an active group. Inactive grantees cannot act. Owner transfer invalidates
old-owner grants using the owner-revision fence even before bounded cleanup; no silent
grant carry-forward. Grant effectiveness requires active status, effective interval,
current owner revision, and an eligible grantee. Grantor membership ending alone does
not revoke an already accepted group-owned grant.

Member route approval is separate from explicit item/catalog grants.
`route_member_use_approvals` has `delivery_target_id` PK/FK and `current_revision`;
`route_member_use_approval_revisions` has PK `(delivery_target_id,revision)`, common
revision fields, `owner_group_id` FK, `approved_route_security_revision`, and
`status=approved|revoked`. Approval is valid only for an active group-owned route
with that same owner and security revision. Missing approval means not approved.
Only the route-owning group's eligible admin or owner may approve, revoke or reapprove
member use. Each change advances the access epoch; reapproval is an explicit new
revision, never revival of an old mandate. Route owner/endpoint/audience/security
changes invalidate the approval and require fresh approval. Display-name-only edits
do not invalidate it. No per-member arbitrary route-grant kind is introduced.
Approval is necessary but not sufficient: Section 4 still checks active membership,
same-group item ownership, permission to act on the item, and audience acceptance.

### 3.5 Authentication fences and transactions

The account component publishes nonsecret `account_admission_fences` keyed by account
and realm: account revision/state, `authentication_epoch`, method-revocation epoch,
current binding ID/revision/subject, and authoritative source revision. This is an
admission projection, not a second account authority. Security mutations MUST commit
the fence before acknowledging revocation; if the account component cannot synchronously
fence access, protected admission stays unavailable. An asynchronous stale cache is
not sufficient. Passwords and authenticator private material stay out of these rows.

Protected writes acquire the SQLite writer transaction, read current fences/epochs and
domain revisions, authorize, mutate, and commit evidence together. They MUST NOT
authorize on one connection then invoke a handler that independently commits on another.
Refactoring handler transaction ownership is an implementation requirement, not assumed
behavior of today's `CommandContext`. No network call or authentication challenge may
run while holding this transaction. Busy/timeout rolls back without partial effects.

Read projection uses one bounded snapshot. Before releasing a buffered result, compare
its access/mode/recovery epochs and account/session validity to current state; reject
on change. That final check is the read-release linearization point. Revocation after
release cannot retract bytes already sent; requests linearized after revocation deny.
No permission cache survives a relevant epoch change. Subject/group status, route and
ACL changes through trusted-local tools MUST update the same fences while a protected
deployment runs. Uninstrumented raw database writes require quiescing that deployment;
host administrators remain able to bypass controls, but mixed operation cannot silently
ignore their legitimate permission-state changes.

## 4. Resource Resolution and Policy Evaluation

Use exact persisted IDs and the requested command's registered resolver. Owner scopes
are discriminated `{owner_kind,owner_subject_id}` or `{owner_kind,owner_group_id}`;
`system` is permitted only for existing system catalog resolution. Never infer an
owner from profile selection, item participants, display names, chat IDs, route names,
or `item_subject_roles.owner`. New multi-user items require `create_owner_scope` in
the protected envelope. Legacy inner command JSON remains unchanged; ownership is
committed by orchestration in the same transaction. Single-operator creation may omit
it and leave adoption pending, explicitly reported as such.

Current references resolve by PK, then current revision. Exact historical references
retain their historical domain content but use current resource access. Child IDs
resolve through their canonical FKs to the item; mismatched child/item pairs deny.
Relations require both endpoints; temporal bindings require source and target; a
reusable location has no inferred ownership and cannot be exposed across unrelated
items until its own sharing contract ships. Inline new locations inherit the created
item's view, not a general right to the reusable location catalog.

The closed operation vocabulary is `item.read`, `item.create`, `item.edit`, `item.share`,
`item.transfer`, `catalog.read`, `catalog.use`, `catalog.admin`, `route.read`,
`route.use`, `route.admin`, `item.release`, `group.member_admin`, `group.admin_admin`,
`group.transfer`, `group.retire`, `identity.admin`, `deployment.admin`, and
`work.reconcile`. Each requested operation must have an owner/role/grant source below.

- Single operator: its configured active account has all operations, subject to domain,
  system-catalog immutability, response-audience, and external governance constraints.
- Subject ownership: the active bound subject controls its own resources. Creation into
  another subject's scope, or acting as that subject, is not enabled by an item grant.
- Group roles: apply the exact matrix in `permissions.md` Section 5. Catalog/route
  administration requires admin or owner. `item.share` belongs to admin/owner, not
  creator rights. Only the source group's eligible designated owner may authorize
  transfer of a group-owned item to another owner or ownership scope. Group admins
  administer within the group but cannot cross this ownership boundary. This is the
  ratified multi-user role rule; the explicit single-operator and trusted-local modes
  retain their separately specified full scope.
- Explicit grants: only the three resource families and operation sets in Section 3.4.
- System catalogs: read/use only when an explicit deployment policy permits them;
  ordinary commands cannot mutate them even for the single operator.

Item editors may reconcile item-owned work, but `work.reconcile` is not an external-send
permission. Route owners and group admins/owners may read/use/administer their routes.
An ordinary member may use a group-owned route only with a current explicit admin/owner
member-use approval, active membership in its owning group, and an item owned by that
same group on which the member has `item.edit` (or prospective creator authority in an
authorized creation). Together these facts permit `route.use` and `item.release` for
that item/route pair's ordinary notification content, subject to explicit audience
acceptance and governance. None alone permits release; item edit is not arbitrary
external-send authority. This approval does not cover private subject-owned items,
another group's items, unrelated destinations, or arbitrary payloads. Route creation,
configuration, member-use approval and administration remain admin/owner operations.
Necessary route snapshot readback is limited to that authorized item/route use; member
approval is not full route-inventory access. `item.release` remains distinct from edit
and is required for new/replaced mandates. Account/identity administration and deployment mode
changes are trusted-local provisioning only in this slice; group roles do not grant them.

## 5. Closed Command and Nested-Effect Registry

The following is the complete disposition of the current 53 commands. Rows expand to
one entry per exact command; no prefix/wildcard matching or read/write inference is
allowed. `S` means first single-operator gateway; `M` means future multi-user gateway
after all stated prerequisites. `S only` is an explicit multi-user denial, not a
missing mapping. Local tools remain outside this exposure registry.

For each entry the published machine registry MUST pin the exact request/response
contract versions, runtime contract requirements, resolver version, effect vocabulary,
projection version, allowed modes and principal kinds. Registry coverage must exactly
match the dispatcher and `spine.command-runtime-contract-registry.v1` at that release.
The current runtime registry is a baseline to compare, not a dynamic inheritance rule:
a newly installed command or version cannot acquire access automatically. Registry hash
is SHA-256 of its canonical JSON; startup rejects absent, duplicate, changed, or unknown
entries. The tables below are proposed mappings, not claims that a manifest exists.

| Exact commands | Exposure | Required resources/operations |
|---|---|---|
| `system.info`, `owner_scope.list` | S only | Operator; complete inventory/runtime response |
| `subject.upsert`, `subject_group.upsert` | S only | `identity.admin`; actor/account state still protected |
| `delivery_target.upsert` | S; M after audience gate | `route.admin` at old and requested owner; ownership changes require dedicated transfer, not this upsert |
| `event.create`, `task.create`, `schedule.create` | S, M | `item.create` in explicit scope; new item owner; all nested effects |
| `schedule.related_task.create` | S, M | Create target; `item.read` source; `item.edit` source for new relation; binding effects |
| `event.update`, `event.reschedule`, `event.cancel`, `task.update`, `task.complete`, `task.cancel`, `item.archive`, `schedule.update`, `schedule.cancel` | S, M | `item.edit` target; nested effects and mandatory reconciliation |
| `recurrence.instance.add`, `recurrence.instance.remove`, `recurrence.instance.override`, `recurrence.series.edit` | S, M | `item.edit` recurrence root; nested policy/work effects |
| `reminder.create`, `reminder.edit`, `reminder.disable` | S, M | `item.edit` policy root; route/release checks for new delivery authority |
| `notification_work.materialize`, `occurrence_provenance.regenerate` | S, M | `item.read` plus `work.reconcile` root; no new release rights |
| `schedule.binding.reconcile` | S, M | `work.reconcile` target and authorized source derivation; bounded target selection |
| `item.show`, `schedule.show`, `item.occurrences`, `notification.opportunities` | S, M | `item.read` root and every separately governed returned reference |
| `item.list`, `agenda.show` | S only | Existing whole-ledger projections; use `access.items.list` in M until exact successor projections ship |
| `relation.create` | S, M | `item.edit` both endpoints, which includes required read; no permission inheritance |
| `relation.list`, `schedule.binding.list` | S only | Existing projection; M requires a separately versioned authorized graph projection |
| `schedule.build` | S, M | Read/use all ledger-resolved references; future creation owner permission; no write or command-ID consumption |
| `item_archetype.create`, `notification_profile.create` | S, M | `catalog.admin` requested owner scope |
| `item_archetype.revise`, `item_archetype.retire`, `notification_profile.revise`, `notification_profile.metadata.update`, `notification_profile.retire` | S, M | `catalog.admin` existing owner; no owner change |
| `item_archetype.show`, `notification_profile.show` | S, M | `catalog.read` definition owner or explicit resource grant |
| `item_archetype.list`, `notification_profile.list`, `notification_profile.binding.list` | S, M | Explicit owner scope with catalog read rights; scope filtering before pagination |
| `notification_profile.binding.set`, `notification_profile.binding.remove` | S, M | `catalog.admin` binding scope and `catalog.use` referenced definitions |
| `notification_profile.resolve` | S, M | `catalog.use` each requested scope and referenced definition; preserve exact scope order, no skip/fallback on denial |

Future protected worker pseudo-operations are exactly `worker.reconcile` and
`worker.attempt.start`; these are not public command aliases. They require an admitted
service identity, its current grant, and Section 9's predicates. Browser sessions cannot
call them. Autonomous and delegated service authority cannot be unioned or substituted.
There is no protected agent principal kind in first delivery; attempts to supply one
fail closed until the stronger admission capability is implemented and qualified.

Resolvers must enumerate the following closed effect set from the normalized request
and bounded current state, including implicit defaults, copied references, and mandatory
reconciliation. Absence from raw JSON is not proof that an effect is absent.

| Effect tag | Additional checks |
|---|---|
| `item_create` / `item_change` | Scope create or root edit; write ownership with creation |
| `catalog_apply` | Use archetype/profile and every explicit resolution scope; applied immutable snapshots later follow item read |
| `relation_link` | Edit/read both endpoints; creation does not grant endpoint access |
| `binding_derive` | Read source and edit target; copied source values cannot exceed target audience authority |
| `location_attach` | New inline location allowed with item edit/create; existing cross-item location reference unavailable in M |
| `policy_author` | Edit item plus route use/release for a new or changed mandate |
| `work_reconcile` | Root edit or service reconciliation grant; preserve terminal/attempted history |
| `route_change` | Route admin; reauthorize delivery, never derive it from item edit |
| `content_release` | Explicit current item release, route use, audience policy, and mandate acceptance |
| `evidence_read` | Root read plus receipt/projection disclosure checks |

Unknown effects or resource kinds deny the entire request. A composite cannot commit
an authorized portion then fail the remainder. Creation has prospective rights only
inside its authorized scope and transaction. New location, relation, profile, and work
facts remain ordinary domain facts, not alternate ledgers. Response assembly must
validate all included foreign resources; absent a versioned redaction shape, reject
the whole response rather than leaking or silently omitting schema-required content.
The prospective response resource set is checked before mutation. A later revocation
between commit and response release can suppress the response; it does not roll back
an already committed command. Clients preserve the command ID and use authorized replay
or readback to resolve that uncertainty, never blindly submit a replacement command.

## 6. Verified Web Sign-In and Session Admission

The first web authentication method remains an explicit release decision (Section 13).
This interface supports configured local methods without mandating an IDP or OAuth.
An established session library and qualified authentication adapter MUST implement it;
implementations must not invent a password or signature protocol from this prose.

The protected adapter result has `realm_id`, `account_id`, `method_id`,
`method_revision`, `verification_evidence_ref`, `verified_at_utc`, `expires_at_utc`,
`authentication_epoch`, and `audience_ledger_id`. Its exact method profile must define
proof verification, challenge replay prevention, assurance and revocation. The result
arrives through a protected in-process interface, not browser JSON or forwarded headers.
Observed chat identity is not such a result. Entering a phone number only starts an
indistinguishable lookup/challenge path; it never grants a session or reclaims an
established account solely from a newly acquired number.

After accepted verification, resolve the current active account and binding. In S only
the configured account is admitted to coordination. In M unbound active accounts may
reach account self-service, never coordination; no onboarding rights are inferred here.
Issue a new random opaque session secret with at least 256 bits of entropy; never
upgrade a caller-supplied session ID. Browser storage is a Secure, HttpOnly, host-only
cookie with Path=/ and SameSite=Lax; HTTPS is required for browser-facing deployment.
Non-idempotent browser actions require session-bound CSRF protection and exact allowed
Origin. Credentialed cross-origin access and bearer secrets in URLs are forbidden.

`web_sessions` is authentication state, not coordination truth: `session_id` PK,
`token_digest` unique (SHA-256 of the random secret), realm/account/method/binding refs
and revisions, authentication/mode/recovery epochs, `created_at_utc`,
`absolute_expires_at_utc`, and `status` (`active|revoked`). Raw secrets are never persisted
in receipts or logs. Each session uses a fixed expiry; ordinary reads do not extend it
or durably update last-seen. Expired means evaluation time >= absolute expiry, regardless
of stored status. Explicit renewal requires fresh verification and revokes the old
session atomically; replaying a login response must not issue a second usable session.
Session establishment/revocation is bounded authentication-state work, not a domain
command_receipt containing credential material.

Every request checks the digest, active session/account/subject/binding/method,
matching revisions/epochs, configured mode, audience, and expiry. Account suspension,
closure, binding or authentication-method changes increment the account authentication
epoch conservatively invalidating all its sessions. Logout revokes that session;
account-wide sign-out increments the account epoch. Role/grant changes re-evaluate
resource access and invalidate cursors without logging out unaffected accounts.

Mode transitions are trusted-local maintenance: quiesce protected admission and worker
attempt admission, validate adoption/capability prerequisites, atomically change mode
and epochs, then restart compatible services. All old sessions/cursors deny. Mode
fallback on errors is forbidden. Recovering an older ledger or authentication store
starts not-ready and requires explicit epoch/fence reconciliation and fresh sign-in;
restored sessions are never accepted by default.

## 7. Protected Request, Failures, and Bounded Queries

Proposed envelope fields are exactly `contract_version`, `command`, `request`, optional
`create_owner_scope`, and optional `expected_access_epoch`. The contract version is
`spine.permission-enforcement.v1`; the inner request keeps its command contract.
Credentials, principal, assurance, mode, executor, ledger path, and evaluation time are
not payload fields. The gateway supplies immutable context outside that envelope and
requires inner `actor_subject_id` to equal the current bound initiating subject for
mutations. Unknown envelope fields fail before any effect; a caller cannot select
trusted-local fallback. External-action approval remains separate from authorization.

Validation precedence is: size/syntax and configured operation; runtime capability;
authentication/CSRF; current mode/account/binding; bounded reference resolution and
resource/audience authorization; currently authorized replay; expected access/domain
revisions; domain validation; atomic write; authorized response release. Public errors
are a new outer envelope, not new values silently inserted into existing domain schemas:
`ok=false`, `contract_version`, `error.code`, and opaque `correlation_id`. Domain results
on success are carried unchanged as `result`, alongside bounded access evidence.

| Outer code | HTTP | Meaning visible to caller |
|---|---|---|
| `invalid_request` | 400 | Invalid syntax/size/unsupported outer field without resource details |
| `operation_unavailable` | 404 | Command/version/mode not exposed, independent of target existence |
| `authentication_required` | 401 | Missing, expired, revoked, wrong-audience or blocked session; no account-existence detail |
| `request_not_permitted` | 403 | CSRF/assurance failure or resource absent/inaccessible/ambiguous; identical resource failure shape |
| `access_changed` | 409 | Authenticated caller's supplied epoch/cursor no longer current |
| `request_id_unavailable` | 409 | A command ID cannot be used or disclosed under this principal |
| `capacity_exceeded` | 429 | Configured request/work/query budget reached; no partial result |
| `admission_unavailable` | 503 | Missing authority, readiness, fence, storage, or deadline; no fallback |

Only after authorized resource resolution may normal domain errors be exposed. A private
missing resource and private existing resource follow the same outward failure and
bounded query plan; absolute timing equality is not claimed. Internal diagnostics may
distinguish causes only within an access-controlled, redacted, rate/byte-bounded sink.
No full query text, credential, phone number, private title, or foreign ID in public errors.

`access.items.list` and `access.owner_scopes.list` are proposed M-safe read commands,
also usable in S. Request fields are `contract_version`, `limit`, optional `cursor`,
and optional exact owner scope; item listing additionally permits `item_type=event|task`.
Limit is a decimal string, default 50, maximum 100. Output is ordered by raw opaque ID
lexicographically and contains only authorized IDs, type, current revision, owner scope,
allowed operations and their access revision; detail comes from authorized show calls.
`has_more` and cursor concern authorized rows only. No global totals, offset pagination,
hidden-owner counts, or unbounded search. An explicit inaccessible owner scope denies
instead of returning an apparently empty catalog. Item-less scopes can be listed when
the caller has scope creation/use authority; appearance never grants it.

Queries apply indexed owner, active direct membership and explicit-grant predicates
before LIMIT, count, and expansion. All candidate work, memberships, grants, references,
and output bytes have hard configured budgets. If a bounded query cannot fill a page
without exceeding its work/deadline budget, return capacity failure, not an inaccurate
`has_more=false`. No full-ledger materialization followed by Python/GUI filtering.

Cursors are authenticated opaque encodings of ledger/realm, subject/account,
executor/delegation if present, audience, exact normalized query, last authorized ID,
access/mode/recovery epochs, registry hash, and expiry. The authenticator uses a server
secret outside model/payload control; its exact library/envelope must be published with
the machine contract. Limit is bound; altered queries, expiry or epoch mismatch return
`access_changed`, with no embedded foreign IDs disclosed. No domain-row scan computes
cursor identity. A cache key includes these same fences and never bypasses fresh
session or authorization checks.

## 8. Provisioning, Administration, Evidence, and Replay

The proposed additional command set below is closed. All require explicit expected
revisions for changed records, `command_id`, actor, canonical timestamp, and current
authority; authorization timestamps come from the server. Their exact machine schemas
must be published before exposure. No generic update permits changing ownership,
authentication, roles, or assurance by smuggling fields into display metadata.
New security mutation responses use `effect=access_mutated|access_noop`, `changed`,
command/receipt IDs, resulting record IDs/revisions, and the resulting access epoch.
An authorized compatible replay returns the original result inside the fresh admission
envelope; session/evaluation metadata is not substituted into the original receipt.
No-op means structural equality of the normalized resulting state; it still consumes
the fresh command ID under existing explicit-command receipt rules. Creating a new
independent grant is a change even if its rights overlap another grant. Reads never
consume command IDs. Exact per-command field schemas and no-op/failure fixtures remain
publication gates; the names above are not implemented CLI commands.


| Command | Authority and atomic effect |
|---|---|
| `access.deployment.configure` | Trusted local only; set mode/operator/registry/budgets after readiness/adoption validation |
| `access.item_owner.adopt` | Trusted local only; explicit owner of an unadopted item; no inferred creator rights |
| `access.group.adopt` | Trusted local only; explicit designated owner and reconciled membership heads for existing group |
| `access.group.create` | Trusted local only initially; create group and explicit owner membership together |
| `access.membership.add` | Group admin/owner; add ordinary member only, reject duplicate active membership |
| `access.membership.end` | Admin ends ordinary member; owner may end admin; designated owner cannot be ended without handoff |
| `access.membership.role.set` | Owner only; member/admin transition; owner is not assignable through this command |
| `access.group_owner.offer`, `access.group_owner.accept` | Current owner offers to eligible subject; that subject accepts, atomic handoff and prior owner becomes admin |
| `access.group.retire` | Owner; mark group inactive and invalidate group-derived access; history retained |
| `access.grant.create`, `access.grant.revoke` | Item share authority or catalog admin, exact operation subset; one grant per command |
| `access.item_owner.offer`, `access.item_owner.accept` | Source subject owner or, for a group-owned item, the source group's eligible designated owner offers; explicitly authorized destination accepts; recheck source authority and revisions, invalidate prior grants/mandates atomically |
| `access.delivery_mandate.set`, `access.delivery_mandate.revoke` | Section 9 release/route authorities; explicit item/policy/target and expected revisions |
| `access.route_member_use.set` | Route-owning group admin/owner only; explicit approved/revoked status and expected approval/route-security revisions; advance access epoch atomically |
| `access.effective.show` | Own effective access only for a readable resource; no caller-specified impersonation |
| `access.items.list`, `access.owner_scopes.list` | Section 7 bounded projections; reads write no receipt |

Account enrollment, identifier linking, methods, recovery, and account/subject binding
remain the account specification's operations; there is no generic `access.*` bypass
for them. Account provisioning is trusted-local until their exact qualified management
contracts ship. This draft does not authorize public self-service enrollment.

`access_transfers` records offers with common revision fields, `transfer_id`,
`kind=group_owner|item_owner`, resource ID, expected source owner/membership revisions,
destination subject or owner scope, `status=pending|accepted|cancelled`, and expiry.
Group-owner acceptance requires the exact destination subject; item-owner acceptance
requires explicit acceptance authority in the exact destination owner scope. Both
recheck unchanged source authority and expected revisions; offers confer no temporary
rights. For a group-owned item, the offer's authorizer must still be the source group's
eligible designated owner at acceptance. Admin status, item edit/share rights, or
destination authority cannot substitute for that source-owner authorization. Expired
or stale offers cannot be accepted. Fresh replacement cancels an earlier pending offer
in the same transaction. Group acceptance creates/updates eligible successor membership,
demotes the prior owner to admin, advances access epoch, and records acceptance evidence.
No account suspension or lost eligibility is repaired implicitly. Trusted recovery is
separate from acceptance and requires operator audit; it never self-promotes an admin.

Item acceptance atomically changes the access owner, clears creator entitlement,
advances the owner revision/access epoch, and invalidates old-owner grants and delivery
mandates before any later access or attempt admission. It preserves domain item IDs,
versions and historical outcomes, and transfers no related item, source catalog or
route. Any new grant or mandate requires explicit destination-authorized provisioning;
there is no automatic carry-forward. These proposed commands still require machine
contracts and implementation before exposure; ratifying this rule does not enable them.

Fresh authorization metadata includes principal kind, initiating account/subject,
executing identity, binding/authentication references (not secrets), assurance,
ledger/access/mode/recovery epochs, registry hash, canonical protected-envelope hash,
resolved `(resource_kind,id,revision,operation,authority_source)` tuples in lexical
order, audience, and decision time. `command_authorizations` binds one immutable
`authorization_evidence_id` to one existing receipt ID. Child evidence rows normalize
the tuples; the exact canonical envelope preimage includes all supplied outer semantic
fields, command and normalized inner request, excluding transport/session secrets.
Authorization evidence commits with fresh domain mutation or explicit durable no-op
receipt; failure to persist it rolls back. No idle/read/denial receipt is added.

The global command-ID namespace remains unchanged. Fresh collision or replay checks
must first establish the right to see that original operation. Protected replay requires
the same initiating account/subject, compatible envelope and current read access to all
returned resources; a permitted resource administrator may inspect separate authorized
evidence, not impersonate another caller's replay. Different sessions for the same
account may replay; changed authenticated binding or lost receipt access denies. A
foreign/local historical receipt without protected attribution yields
`request_id_unavailable` on the protected replay path, with no underlying details.
This does not prevent the single operator's separate authorized historical readback.

Compatible replay returns original domain evidence without rechecking domain writeability
or replaying effects; current authentication, registry eligibility and disclosure rules
still apply. A new grant is not permission to replay another account's command. Expected
access epoch is part of fresh-write comparison but an original replay remains possible
after epoch change if current read disclosure is authorized; cursor rules are separate.

`access.effective.show` returns a lexically sorted operation list plus each actual source
(owning subject, own active group role, applicable explicit grant, or operator mode),
current epochs and requested resource revision. It must explain surviving independent
grants after one is revoked, not imply that revoking one removes all access. It exposes
neither unrelated grant holders nor authenticator/session material. Forbidden resources
receive the same non-enumerating failure as missing resources.
Member release/use evidence names the applicable item/route pair and approval revision;
it MUST NOT report route approval as an unrestricted right to release every readable
item. Revocation of route approval invalidates that derived authority independently
of an unchanged item edit grant.

## 9. Delivery and Derived-Work Authorization

This section is mandatory before multi-user delivery, not a change to today's trusted
local worker. Session expiry/logout does not revoke accepted schedules. Work materialized
does not mean delivery authorized, attempted, or delivered. Unqualified protected agent
or worker identity cannot be inferred from command names, process IDs or model fields.

`delivery_mandates` has stable `mandate_id` PK and current revision. Revisions contain
common fields, item/policy/target FKs, item-owner revision, exact route-security revision,
authorizing owner scope, authorizing subject, `audience_kind` (`fixed_endpoint|dynamic_group_endpoint`),
`audience_ref`, `status` (`active|revoked`), effective interval, and authorized content
class `ordinary_item_notification`. One active current mandate is permitted per
`(item_id,policy_id,delivery_target_id)`. Target endpoint fingerprint covers adapter,
adapter-account, channel and exact target reference; endpoint changes invalidate it.
Notification templates/profile keys alone cannot issue a mandate. There is no arbitrary
payload or tool-execution permission in this content class.
Mandates created under ordinary-member route use also record the exact member-use
approval revision. At creation, verify the Section 4 item/route/membership predicate;
the actor cannot substitute item edit for approval. Subsequent attempts require that
same approval to remain effective. Revoking or replacing approval blocks new attempts
under the old mandate; fresh explicit mandate authorization is needed after reapproval.
The original member's later departure alone does not revoke accepted group-owned
schedules; continuing mandate authority belongs to the group, not their session.

Fresh or changed delivery intent requires both item content-release and target-use
authority, explicit audience acceptance, and independent governance approval when
applicable. Existing same-owner/same-route mandates may continue after an ordinary
item edit; item editors cannot change the endpoint or widen the content class through
that edit. A dynamic group endpoint explicitly accepts a changing transport audience;
it is never inferred from a group-owned route. Without a ratified audience rule,
multi-user mandate creation and corresponding delivery remain unavailable.

Attempt-start transaction checks admitted service grant, active owner/item/route,
mandate status/interval/owner and endpoint fences, source/binding freshness, and ordinary
work eligibility, including the member-use approval fence when recorded. Missing mandate
means blocked authorization, not zero opportunities
or a successful send. It records a bounded authorization reference on the existing
`side_effect_attempts` admission before external contact; no second attempt ledger.
Worker reconciliation uses the same service grant and root resolution, never a human
browser session. Follow-source derivation also requires persistent approved source-to-target
disclosure authority; without that future contract multi-user follow-source work is
disabled, not run with a blanket privileged read.

Revocation linearizes before a subsequent attempt-start and prevents it. An already
admitted in-flight attempt records its actual result; revocation does not promise to
recall the message. A retry needs a fresh current authorization, not old admission.
Ending the schedule creator's group membership does not revoke a group mandate by
itself. Ownership/endpoint changes fence old mandates immediately; reauthorization is
explicit. Bounded reconciliation records an inspectable authorization-blocked state
once per relevant revision, not one durable row per failed tick. New blocked-state and
attempt-evidence schemas must ship before claiming this behavior.

## 10. Budgets, Readiness, and Transport Parity

Extend the operational-budget catalog, not a second hidden limits file. Required positive
bounded values are maximum envelope/result bytes, resources/effects per command, direct
memberships/grants inspected, query candidates/steps, query and transaction deadlines,
active sessions per account/deployment, session lifetime, login/challenge attempts and
expiry, enrollment count/storage, cursor lifetime, diagnostic bytes/retention, and pending
offers per resource. Missing/zero/overflowing limits leave admission not-ready. Catalog
identity and effective nonsecret values are inspectable by the operator. Numeric defaults
and their load-test justification are release artifacts, not guessed production settings.

Deadline/work-budget exhaustion fails closed with no partial command; reads and idle
authorization checks write no canonical rows. Accepted security mutations and mandates
retain audit evidence; expiration of ephemeral sessions/challenges follows an explicit
bounded authentication-store retention policy, not deletion of canonical receipts.
New indices and mutation-scoped checks must prove row-count-independent startup and
bounded request work. Do not add full integrity, foreign-key or invariant scans to
routine preflight. Recovery/adoption inventory is explicit paginated maintenance.

Every exposed protected adapter calls the same admission/effect/transaction service;
HTTP middleware alone is insufficient. Transport cannot turn denied authorization into
local execution, reroute an audience, or downgrade to observed attribution. First web
release exposes only verified direct sessions. Later agent/worker profiles require
qualified non-model-controlled executor identity, independent scopes and protected
origin/audience as applicable; until then those protected paths are unavailable.

Trusted-local CLI/worker behavior remains the named exception, not a client-selectable
principal. No token check is advertised as containment while its holder can directly
open the ledger. Deployed untrusted web callers have no host shell/ledger credentials.
Single-operator coexistence tests must prove command IDs, transactions, stale versions,
busy failures, revocation fences and worker attempt evidence still compose.
Multi-user mode requires all supported workers to enforce mandates before readiness;
an older unrestricted worker running against that deployment is a release blocker.

## 11. Required Conformance Families

These are future acceptance oracles, not tests claimed implemented by this draft.

| ID | Required proof |
|---|---|
| ENF-01 | Registry lists all 53 baseline commands once; unknown command/version/effect and M-disabled entry fail closed |
| ENF-02 | Own item edit grant permits edit, never catalog/binding or route administration |
| ENF-03 | Exactly one adopted item owner, one active group membership per pair and one designated owner; concurrent handoffs cannot violate constraints |
| ENF-04 | Account suspension blocks a designated owner without promoting admin; explicit recovery preserves history |
| ENF-05 | Creator leaves/transfers item: creator entitlement ends; independent explicit grants remain explainable |
| ENF-06 | Forged actor/mode/assurance, observed phone, unknown sender, session fixation, CSRF and revoked/expired sessions fail before domain access |
| ENF-07 | S admits only configured account; M admits active accounts but signup/unbound identity grants no existing data |
| ENF-08 | Nested profile/relation/location/route/reference effects denied atomically; inaccessible scope does not trigger profile fallback |
| ENF-09 | Concurrent CLI/web changes honor access epochs and domain versions; busy/timeout/evidence failure leaves no partial writes |
| ENF-10 | Foreign/missing command ID probes indistinguishable; authorized replay preserves original IDs/effects after domain terminal state |
| ENF-11 | Filtering precedes pagination/counts; denial, nested output, caches and cursors reveal no inaccessible resources |
| ENF-12 | Mode/recovery change rejects old sessions/pages, missing adoption prevents M startup, no permissive fallback |
| ENF-13 | Logout leaves delivery intent; mandate revocation blocks new attempts, in-flight outcomes and mandatory reconciliation remain truthful |
| ENF-14 | Equivalent protected transport contexts yield identical permission outcomes; trusted-local exception is explicit, never user-selectable |
| ENF-15 | Idle/read/denial stress stays within latency/storage budgets; no per-request canonical evidence flood |
| ENF-16 | Existing profile applications, notification identities, rendering and recurrence remain domain-authoritative across access changes |
| ENF-17 | Group admin cannot offer/authorize an item transfer; eligible designated owner plus destination acceptance can; lost source authority, stale revisions or missing acceptance deny; prior grants/mandates never carry automatically |
| ENF-18 | Approved route plus active membership and same-group item authority permits member notification use; missing/revoked approval, foreign/private item, or edit-only authority denies; members cannot administer routes and reapproval does not revive old mandates |

## 12. Publication and Implementation Gates

These gates apply to deferred protected delivery; Section 1.1 owns the immediate slice.
The implementation package must publish exact schema/registry/outer-envelope versions,
storage migration and rollback/adoption procedure, method/session adapter profile,
failure/receipt/query shapes, configured budgets and a fixture for each ENF family.
Ontology amendments must name the new role domain and current/history projections;
existing command declarations must not claim protected enforcement prematurely.

First single-operator delivery does not require existing items to be backfilled with
owners, group-admin UI, public enrollment, or protected chat/service credentials. It
does require verified web sign-in, one designated account, consistent session/epoch
revocation, exact command exposure, audit linkage and no hidden fallback. Unsupported
new commands remain unavailable. Shipping M requires resolving every authority decision
below, complete ownership/group adoption, authorized projections, delivery/derivation
contracts and concurrency/security tests; a partial M implementation is not an access mode.

## 13. Explicit Decisions and Remaining Design Work

**Ratified: group-owned item transfer.** Only the source group's eligible designated
owner may authorize moving a group-owned item to another owner/scope. Group admins
may administer within their group, not perform this boundary-changing transfer.
Destination authority/acceptance remains required; old grants and delivery mandates
do not automatically carry across. Sections 4 and 8 define the proposed enforcement.

**Ratified: ordinary-member route use.** Admins/owners explicitly approve group-owned
routes for member use. A member may use an approved route only for that group's items
they are authorized to act on. Item edit alone grants no arbitrary content release;
route creation, configuration, approval and administration remain admin/owner powers.
This decision does not itself choose the dynamic-audience policy below.

The following product policies remain unresolved:

1. **Deferred verified web method and recovery:** choose authentication and recovery
   before enabling `verified_identity`. This does not block the immediate trusted web
   interface, which uses manual host administration for recovery.
2. **Dynamic audiences:** explicitly choose whether transport-group endpoints may accept
   changing membership for this release, or only fixed recipients. Private-item release
   into a group needs an explicit accepted policy, not chat context.
3. **Persistent cross-owner derivation:** define source disclosure after creator/grant
   revocation before enabling M follow-source bindings. No automatic access inheritance.

Next, define the trusted multi-operator web interface's supported commands, identity
selection, ownership/role provisioning, wire schemas and budgets. Authentication remains
deferred. Dynamic-audience and cross-owner derivation decisions gate those future
protected features, not the immediate supported subset.
These decisions are not permission to implement, deploy, send an external audit, or
change the existing staging trust model. This document intentionally records disabled
outcomes at unresolved boundaries instead of inventing broader authority.
