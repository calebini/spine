# Trusted Multi-Operator Web API

Status: v0.1.2; trusted-identity backend implemented in Spine 0.4.0 / schema 13; browser and deployment qualification remain separate
Created: 2026-09-06
Proposed capability: `spine.trusted-web-api.v1`

Related proposal: [independent-activity-reads.md](independent-activity-reads.md)
defines a separate future web read projection for authorized activities with unavailable
linked resources. It does not amend this implemented v1 surface's complete-or-deny
responses, binding admission, or write authorization. Track its status in SPINE-015.

## 1. Outcome and Authority

Provide a useful first web backend for several trusted operators, initially two:
choose an identity, see its permitted agenda, create and inspect schedules, update or
cancel them, and complete tasks. Existing recurrence, profiles, notifications, location,
receipts and delivery evidence remain Spine truth. The browser is a projection.

[permissions.md](permissions.md) owns resource policy;
[accounts-and-chat-attribution.md](accounts-and-chat-attribution.md) owns accounts and
honest attribution. Section 1 of
[permission-enforcement-and-web-admission.md](permission-enforcement-and-web-admission.md)
owns the immediate `access_mode=multi_user`, `identity_mode=trusted_identity` decision.
Its later protected session/executor/mandate design remains deferred. This document
owns the immediate HTTP surface, provisioning subset and release gates, not a second
scheduling engine or an authentication system. [ontology.md](ontology.md),
[agent-command-contract.md](agent-command-contract.md), [schedule-create.md](schedule-create.md),
[schedule-show.md](schedule-show.md), [schedule-operations.md](schedule-operations.md),
[schedule-operator-tools.md](schedule-operator-tools.md), and
[notification-profiles.md](notification-profiles.md) retain their domain authority.

The implemented backend declares `spine.trusted-web-api.v1` and the pinned supporting
families. Its optional `web` package extra supplies HTTP and schema libraries. Local
`web_access.plan` / `web_access.apply` are additive; existing CLI contracts are unchanged.

## 2. Deliberate Trust and Release Boundaries

An operator chooses an account; this does not prove who they are. Anyone who can reach
the interface can choose another offered identity. Display "Trusted identification —
identity is not verified" persistently, including the chosen account/subject. Permissions
prevent ordinary wrong-scope operations, not impersonation or malicious host access.

Reachability MUST be restricted to trusted devices/operators. Default bind is loopback;
remote browser use requires an explicitly configured trusted network boundary, exact
allowed Host/Origin and TLS termination. The service cannot prove that a firewall is
correct: deployment verification must test both allowed and disallowed reachability.
An obscure URL, CORS, or a private-address bind alone is not authentication. Do not
expose this service as an unrestricted Internet application.

The service binds one configured ledger. No request selects a filesystem path, adapter,
shell command, account realm, access mode, or identity posture. It calls shared Python
command/domain services, never a subprocess CLI. The existing local CLI, WhatsApp agent
and worker retain their current privileged paths; they are not constrained by web
permissions. Ordinary domain constraints, transactions and attempt accounting remain.

Required first surface: account selection; owner/route/catalog choices; permitted agenda
and item listing; schedule build/create/show/update/cancel; task completion; explicit
local provisioning; and current permission/readback evidence. Dynamic profile *use*,
recurrence and primary location use existing contracts rather than new web semantics.

Deferred: verified sign-in and recovery, public signup, executor tokens, protected chat
admission, full delivery mandates, account/role/grant administration UI, ownership
transfer UI, occurrence-edit UI, graph/related-task authoring, facet schemas, advisories,
bulk operations, live push subscriptions and a general arbitrary-command endpoint.
Deferred does not mean existing local capabilities are removed. A later API revision
can expose additional commands after their permission and projection rules are specified.

## 3. Identity Selection Without Authentication Machinery

The backend keeps a bounded, explicitly provisioned eligible-account set. Accounts have
stable IDs and explicit one-to-one active subject bindings within the configured realm
and ledger; they are not created or merged from display names, participants or phone text.
Both operators may belong to the same arbitrary group with different roles. No account
automatically becomes an owner/admin or a full-scope operator because it is selectable.

`GET /api/v1/operators` returns only eligible account IDs, bound subject IDs and their
display labels, sorted by account ID. This intentional local chooser is not a public
phone directory; it returns no identifiers, credentials or authentication evidence.
The list and service metadata are the only application reads allowed before selection.

All other calls require `X-Spine-Account-ID` with one current eligible account ID.
It is an openly selectable identifier, not a bearer secret, login proof or token grant.
The backend resolves the subject independently and rejects unknown, suspended, closed,
inactive or unbound accounts. It never defaults to the first account or executing agent.
Inner `actor_subject_id`, where required by a command including the builder, MUST equal
that resolved subject; disagreement fails rather than silently impersonating it.

The browser stores the chosen account in tab-scoped interaction state and sends a fresh
`X-Spine-Selection-ID` on selection/switch. This opaque client-generated correlation ID
is echoed on responses but is not trusted evidence or authorization. The UI discards
responses belonging to an older selection, clears private cached views/cursors/drafts,
and does not resubmit an in-flight command under the new identity. Different tabs may
select different accounts without an ambient server-global active-user variable.

Every request rechecks eligibility, account/subject binding and resource permissions.
No authentication session store, password, OTP, signed identity assertion or refresh
token is required for this selection flow. Same-origin JSON and request-integrity checks
remain mandatory; they protect browser request mechanics, not the identity assertion.
Evidence records `identity_basis=self_selected`, never `verified`. Existing agent
attribution is `agent_observed` only where its evidence extension actually exists; this
API must not relabel old command receipts as account-authenticated.

## 4. Bounded Local Provisioning and Adoption

Provisioning is a trusted-local operation, not a web route. The proposed local command
family is `web_access.plan` / `web_access.apply`, under
`spine.trusted-web-provisioning.v1`; these names are not implemented today. Reuse the
owner/membership/grant authorities of the enforcement draft, not a JSON identity blob
or an alternative permission store maintained by the UI.

The closed plan request contains contract version, one target ledger identity,
`expected_access_epoch`, and explicit arrays of operators, group memberships,
item-owner adoptions, optional item/catalog grants and route-member approvals. Each
array is a complete *batch of operations*, not replacement of the whole ledger. Omission
does nothing. Each operation is explicitly `create`, `set`, or `revoke` where supported;
unknown operations and duplicate targets within one batch are rejected. Existing
subjects/groups/routes are referenced by stable IDs and must already exist. No transport
group is automatically treated as a membership or access owner.

- Operator creation names an existing subject; it creates an administratively activated
  account and binding with `activation_basis=trusted_local_approval`, never verified
  phone possession. Existing account registration names its exact ID and binding revision.
- Membership operations name exact group/subject, `member|admin|owner`, lifecycle and
  expected current revision. Rejoins use a new membership ID. An adopted active group
  ends the transaction with one designated owner; the plan lists all conflicts explicitly.
- Item adoption names exact item/current version and subject/group owner. Only unowned
  items may be adopted; ownership transfer is not smuggled through adoption. Creator
  entitlement is omitted unless existing evidence proves the initiating subject; an old
  agent actor is insufficient. Private items must not be swept into a shared group.
- Grants use only the item read/edit or catalog read/use operations in the permissions
  draft. Granting edit never grants sharing, catalog or route administration.
- Route approval names a group-owned route/security revision and explicit member-use
  approval status. It grants no membership, private-item release, or arbitrary send.

Plan is a bounded read: return normalized operations, referenced versions, warnings,
blocking conflicts and `plan_hash` over canonical JSON. It writes nothing. Apply requires
the full identical normalized plan, hash, expected access epoch, `command_id`, local
administrative `actor_subject_id` and timestamp; it verifies current references and
commits the entire batch with one audit/receipt, or commits none. No approval inference
from a prior plan. Replay follows global command-ID rules; changing facts under the
same ID conflicts. Failed applies do not consume the ID. No-op fresh apply still follows
explicit-command receipt semantics, not daemon no-op suppression.

Account/binding and new permission IDs use explicit registered command-derived row
roles and stable normalized operation paths before implementation; existing IDs never
change. The machine schema must publish those row roles and exact paths. The versioned
plan schema must also define each operation's fields and closed effect/failure enums.
This is a release prerequisite, not permission to invent a backfill during deployment.

Apply advances the canonical persisted `access_epoch` defined by the enforcement
draft. Web response/evidence `access_epoch` and request `expected_access_epoch` refer
to that same singleton epoch, not a separate web revision or alias. Current-state/history
constraints follow that draft; mode and subject
bindings are not duplicated. Bootstrap creates the singleton access epoch explicitly.
Access-relevant changes through supported local commands update the same epoch while
web service is running. Raw administrative writes require quiescing/revalidating the
service; unrestricted host access remains outside application isolation.

Adoption is incremental and bounded. Unadopted items are absent from web lists and deny
web detail/mutation; they stay available to local tools. Newly created local items without
access owners require later adoption. Startup does not scan the entire ledger looking
for them. Only configured/adopted groups and selected referenced facts must satisfy this
slice's constraints; no requirement to migrate all historical items before first use.

## 5. HTTP and Envelope Contract

Proposed envelope version is `spine.trusted-web-api.v1`. JSON uses UTF-8; request objects
reject unknown fields and duplicate keys. Existing inner request schemas retain their
number/string, optional/null, timestamp and normalization rules. New revision/limit
fields use canonical unsigned decimal strings. IDs/correlation values are nonempty,
at most 256 UTF-8 bytes, no control characters. New timestamps are UTC second precision.

| Method and path | Input / output |
|---|---|
| `GET /health/ready` | No ledger details; 200 ready or 503 not ready |
| `GET /api/v1/info` | Capability/registry versions, fixed trust/access modes, public limits, timezone default/version, server time and warning; no DB path, host secrets or raw system inventory |
| `GET /api/v1/operators` | Section 3 chooser plus current access epoch |
| `POST /api/v1/context` | Empty body; selected account/subject, accessible owner scopes, usable route choices, per-scope operations and current access epoch |
| `POST /api/v1/agenda` | Section 7 access-scoped agenda |
| `POST /api/v1/items` | Section 7 access-scoped item list, including unscheduled tasks |
| `POST /api/v1/commands/{command}` | Closed dispatch in Section 6, not arbitrary commands |

Read POSTs have no canonical side effects or command receipts. All browser POSTs require
`Content-Type: application/json`, exact configured Origin/Host, both selection headers,
and a body within budget. Reject missing/foreign Origin rather than allowing a simple
cross-site form to mutate the ledger. Disable credentialed cross-origin access, arbitrary
proxy identity headers and state-changing GET. These rules may be implemented with
ordinary framework protections; they do not introduce a user-authentication credential.

Command body is `{contract_version, request, create_owner_scope?, expected_access_epoch?}`.
Contract version is the outer API version; `request` is exactly the existing command
payload. `create_owner_scope` is required for `schedule.build` and `schedule.create`
and forbidden otherwise. It is a canonical subject/group owner discriminator; no system
owner for an item. `expected_access_epoch` is required for writes, optional for reads
and builder; mismatches fail before a fresh mutation, with replay exceptions in Section 8.
Do not inject these fields into the current inner command schema.

Success contains outer contract version, `ok=true`, identity basis, selected account
and subject, selection ID, evaluated access epoch, `result_contract`, and `result`.
For ordinary commands, `result` is the unmodified canonical command response; outer
metadata is not another receipt. Original historical actor fields remain historical.
For the new scoped reads, result contract is explicitly separate, per Section 7.
Response headers include `Cache-Control: no-store`; the browser cannot share content
across identities or reuse old permission decisions.

Errors contain outer version, `ok=false`, a stable `error.code`, generic message and
correlation/selection IDs, without foreign resource IDs or protected content. Known
identity need not be echoed when selection itself fails. Success is HTTP 200, including
domain creations; `ok` is never assumed from network completion alone.

| Code | HTTP | Semantics |
|---|---|---|
| `invalid_request` | 400 | Syntax, unsupported field or invalid selection header format |
| `identity_unavailable` | 403 | Unknown/ineligible/unbound selection; never maps to another user |
| `operation_unavailable` | 404 | Command/feature not on this release's allowlist |
| `resource_unavailable` | 404 | Missing or unauthorized resource, same outward response |
| `access_changed` | 409 | Supplied access epoch or cursor context no longer current |
| `command_id_unavailable` | 409 | Existing command ID cannot be used/disclosed by this identity |
| `capacity_exceeded` | 429 | Configured work/rate budget exceeded, no partial result |
| `admission_unavailable` | 503 | Required authority, runtime or storage unavailable; no fallback |
| `domain_failure` | 422 | Authorized domain validation failed; include original bounded error code/field after disclosure check |
| `domain_conflict` | 409 | Authorized domain stale-version or semantic conflict; preserve inner error facts |

Oversize bodies use HTTP 413 with `invalid_request`. Foreign Origin/Host uses HTTP 403
with generic `invalid_request`. Raw stack traces, SQL, private titles, paths, credentials
and unselected-account grant details must not appear in errors. This posture does not
promise constant-time cryptographic non-enumeration, but uses the same public missing/
forbidden response and bounded lookup path.

## 6. Closed First Command Surface and Permissions

The runtime publishes `spine.trusted-web-command-registry.v1` with each exact identifier,
inner request/response versions, required runtime contracts, read/write designation,
resource/effect resolver and result projection. It is separate from both the full CLI
runtime registry and the deferred protected admission registry. New runtime commands
gain no HTTP route by installation alone. Startup rejects missing or mismatched entries.

| Exact command | Required application authority / additional restrictions |
|---|---|
| `schedule.build` | Create in explicit owner scope; use/read every referenced catalog/route; read only, no ID consumption |
| `schedule.create` | Create item in explicit scope; all profile/route/content checks below; atomic item owner and attribution |
| `schedule.show` | Read target and every separately governed returned reference; bounded canonical response |
| `schedule.update` | Edit target plus all nested catalog, route and content-release effects; cannot transfer ownership |
| `schedule.cancel` | Edit target; preserve canonical stale-work reconciliation and attempted history |
| `task.complete` | Edit task; current target-version guard; preserve existing completion behavior, not synthetic schedule cancellation |
| `item.occurrences` | Read recurrence root and returned content; bounded expansion, no provenance writes |
| `item_archetype.list`, `item_archetype.show` | Read exact permitted catalog scope/resource |
| `notification_profile.list`, `notification_profile.show` | Read exact permitted catalog scope/resource |
| `notification_profile.binding.list`, `notification_profile.resolve` | Read/use all requested owner scopes/definitions; preserve caller-supplied resolution order |

All other current commands deny at this HTTP endpoint. In particular, raw `system.info`,
`owner_scope.list`, `agenda.show`, `item.list`, public route upsert, graph authoring,
profile mutation, work materialization and worker execution are not generic web escape
hatches. Local counterparts remain valid. The dedicated scoped reads below replace
whole-ledger API projections, not their CLI contracts.

Owners/roles/grants follow the accepted permissions model. Members read/create group
items and edit their own proven creations while membership remains active; editing
another member's item requires a valid explicit edit grant. Admins manage group items
but not private subject items. Item edit does not grant catalog/route administration.
Group-owned item transfers remain owner-only; no transfer endpoint ships here.

New items must be owned by the selected subject or a group in which it can create.
Scope is never inferred from a profile, route, archetype, participant or chat name.
Profile application requires permitted explicit scope chain and exact definition
read/use; denied scope must not silently fall through to another default. Use preserves
existing snapshots, custom additions and recurrence semantics.

Fresh/retargeted reminder delivery requires current usable-route and content-release
checks. A member uses an explicitly admin/owner-approved group route only for that same
group's items they may act on. Group admins/owners may use that group's route for that
group's items; a subject may use its own route for its own item. This first surface
does not authorize private-to-group, cross-group, or arbitrary external destinations.
New delivery to another audience fails `operation_unavailable`, not an inferred grant.
Ordinary edits with retained existing routes still check resulting release eligibility;
cancel/complete may stop intent without acquiring permission to release it anew.

The existing trusted-local delivery engine continues after canonical authoring. Route
member approval here governs web authoring; full per-attempt mandates and protection
against subsequent channel-member changes remain deferred and must not be advertised.
Revoke approval to block future web authoring/use; explicitly cancel/revise existing
schedules through current commands if delivery must stop. Do not imply this release
automatically recalls work or enforces the future mandate revocation contract.

Known follow-source tasks remain inspectable/mutable only when all required source and
target content is readable. Never copy or expose an inaccessible source through target
fields. Unsupported cross-owner derivation is unavailable in the web slice; it remains
a local capability pending the stronger disclosure contract. Existing same-owner
bindings and their domain freshness rules are preserved.

Resolvers inspect normalized resulting state, implicit defaults and all returned
references before commit. Tentative in-transaction rows are never released and roll
back entirely if resultant-state authorization fails. A new inline location is part of item authoring; attaching
an existing location whose sharing authority is undefined denies. Relation/subject-role
changes embedded in a supported command cannot bypass applicable reference checks.
No partial composite commits and no automatic route creation. Missing resolver/effect
coverage denies the operation even if its outer command is allowlisted.

## 7. Access-Scoped Reads, Pagination and Evidence

`/context` returns only the selected subject's accessible owner scopes and readable/usable
catalog and route choices. Route entries include canonical ID, display name, owner,
channel and member-approval revision where relevant, not adapter credentials. A route
choice is not independent release permission; every write re-evaluates its item/route
pair. Allowed operations include read/create/edit where justified, never a blanket admin
flag. No durable read receipt or per-request last-seen update is created.

`/items` uses `spine.trusted-web-items.v1`: request outer version, optional owner scope,
`item_types` (unique event/task subset, default both), `include_terminal` (default false),
decimal-string `limit` (default 50, max 100), optional cursor. Response entries contain
item ID/type/current version/title, shell/detail status, owner scope, and allowed
operations. Sort by item ID. Unscheduled tasks are included; agenda alone is insufficient
for the task list. Return `has_more` and nullable next cursor; no global totals.

`/agenda` uses `spine.trusted-web-agenda.v1`: accept the canonical agenda request fields
from [schedule-operations.md](schedule-operations.md), but require this new result/input
family and limit at most 100. The local range ceiling is 31 elapsed days for this first
web endpoint; domain handling of timezone, boundaries, recurrence and all-day entries
is unchanged. `item_ids`, when supplied, must each be readable or the entire request
denies. Exclude unowned/unreadable items before expansion, counts, sorting or diagnostics.

Reuse canonical agenda entry fields, ordering and summary meaning. The new scoped result
adds owner scope and allowed operations per entry and binds its snapshot to the selected
identity/access epoch. It is not labeled `spine.schedule-agenda-response.v1` because
selection and cursor semantics differ. Authorize candidate items using indexed owner/
membership/grant predicates, then invoke shared expansion/projection helpers. Do not
run whole-ledger `agenda.show` then hide rows in the browser or inject a guessed item
list after unbounded enumeration. Unavailable timezone data in an unreadable item's
history must not cause an authorized query to disclose or process that item.

All scopes, catalogs, items, summaries and related evidence share configured row/byte/
deadline limits. Canonical schedule-show counts are not permission to perform an
unbounded history scan: use indexed bounded computation or fail capacity. If requested
full output contains an unauthorized nested resource, return no result. Do not invent
an omission shape inside an unchanged canonical response. Historical route/attempt
content is checked too; private data is not made readable by requesting `attempts`.

Scoped cursor payloads bind API/query version, ledger/realm, account/subject/binding
revision, access epoch, normalized query including limit, authorized source snapshot,
last ordering key and expiry. Use an integrity-protected opaque cursor through an
established library; its key protects pagination integrity, not user authentication.
Publish encoding/normalization fixtures before implementation. Cursor expiry is 15
minutes, never renewed by a read. Actor/query/revision mismatch returns `access_changed`.
Changed authorized agenda facts return the same stale outcome; never silently continue
against a changed snapshot. Snapshot construction processes only bounded authorized
facts. Repeated scans, offset pagination, hidden-item counts and full-ledger hashes
are forbidden. Overflow fails, not false `has_more=false` or partial evidence.

Use one bounded read snapshot and recheck account/binding/access epoch before response
release. A change requires retry from a fresh context. The UI must also discard late
responses after identity switch. A later revocation cannot retract bytes already released.

## 8. Writes, Replay and Concurrency

The browser generates and preserves a globally unique command ID per intended mutation.
It supplies explicit domain timestamps, timezones, timezone-database directives and
target versions. `/info` supplies server time for deliberate relative-builder requests;
retrying never resamples time or recompiles a different request under the same ID.
Builder output goes unchanged into the inner `schedule.create` request, with the same
outer owner scope, unless the user deliberately creates a new request/ID.

Fresh mutation obtains a writer transaction, resolves current selected identity and
access state, normalizes complete effects, checks permissions and expected revisions,
executes shared domain behavior, and commits ownership/attribution plus the existing
domain audit/receipt atomically. Existing handlers must be adapted to transaction-owned
services where necessary; calling independently committing handlers sequentially is
not sufficient. No network calls, rendering model or external delivery occurs inside
authoring. Bounded dry-run support is deferred at this HTTP surface, not silently
implemented by copying the whole database.

Persist a nonsecret one-to-one web receipt linkage: existing receipt ID, account and
subject, binding revision, `identity_basis=self_selected`, access epoch at acceptance,
outer API/registry version, create-owner scope when present and canonical semantic
envelope hash. Linkage is access/attribution evidence, not a second replay ledger.
Exclude selection ID, network address, Origin, browser metadata and read-evaluation time
from semantic hashing. Existing inner request/hash and row-ID derivations remain intact.
Exact sidecar schema and registered ID derivation must ship with the implementation.

After current identity and disclosure checks, same-account compatible replay precedes
fresh expected-access-epoch/domain-version checks. It returns the original domain receipt,
not another effect, with current outer access metadata labeled separately. A foreign
account command ID or local historical receipt without web attribution yields
`command_id_unavailable` without leaking its contents. It may still be viewed through
separate authorized item readback. Reusing an ID with different command/owner/payload
conflicts. Deleted/expired browser context is no authority to execute as someone else.

A permission revocation committed before a write prevents that write; a write committed
first remains historical fact. Busy/timeout before commit rolls back. Disconnect or
permission change after commit may hide the response but cannot undo the mutation;
the UI reports outcome unknown and resolves it by same-ID replay/readback, not a new ID.
Do not rebase a stale target version automatically. Show current state and let the
operator decide whether to retry as a new intent.

`schedule.update` and `schedule.cancel` retain their canonical atomic work reconciliation.
`task.complete` retains its current completion transaction and does not gain an implied
new work-cancellation composite. Its web result explicitly adds only outer
`work_reconciliation=not_performed_by_this_command`. Show completed state separately
from historical/queued work evidence; perform a subsequent authorized schedule readback
when needed. Fresh attempts remain subject to current task lifecycle/freshness checks;
already-started attempts can still finish. Never say all reminders were cancelled or
already-sent messages recalled solely because completion succeeded.

## 9. Service, Budgets and Recovery

Use one bounded backend service and request-local ledger connections. SQLite still
serializes writers; the web API does not remove contention with CLI or worker. Set busy
and request deadlines, enforce SQL/work budgets, cancel abandoned read work and roll
back failed writes. Never hold transactions across browser interaction or adapter sends.

Proposed first-release ceilings, to be published in the existing operational-budget
catalog and tested on a production-sized fixture: 1 MiB request, 4 MiB response, 100
list rows, 100 resolved resources per command, 32 selectable accounts, 100 memberships/
grant matches per selected account, 100 operations per provisioning batch, 5 seconds
request deadline including at most 2 seconds SQLite busy wait, and 100,000 SQL VM steps
per request across its statements. Existing stricter domain limits win. These are
draft ceilings, not claims of measured performance; benchmark and adjust explicitly
before ratification if canonical readback cannot meet them. No hidden unbounded defaults.

Readiness checks bounded schema/runtime requirements, configured modes, required
indexes/contracts, provisioning revision, network configuration and budgets, not a
full integrity/foreign-key/invariant scan. It may validate the bounded operator set;
it cannot scan all items or receipts at startup. Failure leaves readiness false and
returns service-unavailable without opening a permissive route.

Routine reads and rejected/idle requests write no canonical receipts. Logs omit
command payloads/private titles and use bounded retention and aggregation. Explicit
successful mutations retain normal receipts, including compatible no-op outcomes.
No garbage collection of canonical evidence is introduced by this slice. Session/login
machinery is absent; there is no per-second identity heartbeat or last-seen write.

Operational recovery is a trusted-local backup/repair/reprovision/restart procedure.
Backup ledger and provisioning evidence before migration; preserve accounts/bindings,
owner revisions and global command IDs. Restore starts with new service context and
invalid cursors; do not silently reuse a browser's old selection without rechecking
current eligibility. Rollback requires schema-compatible code or explicit backup restore;
do not start old binaries against a newer schema. Existing worker service boundaries
and Tickerd responsibilities remain unchanged.

## 10. Acceptance and Publication Gates

| ID | Required future oracle |
|---|---|
| WEB-01 | Two selected accounts map to different subjects and receive their actual member/admin/owner operations, never automatic full scope |
| WEB-02 | Unknown/blocked/unbound identity denies; a late response after switching cannot populate the new account's UI |
| WEB-03 | Same-role allowed/denied decisions match for create/update/cancel/complete; item edit never permits catalog or route administration |
| WEB-04 | Provisioning plan is read-only; concurrent/stale/conflicting apply is atomic; existing item IDs/history are preserved and unknown owners stay hidden |
| WEB-05 | Approved member route works for editable same-group items; missing approval/private/cross-group destination denies before any partial schedule bundle |
| WEB-06 | Profile-default resolution, custom reminders, recurrence, timezone pinning and primary-location authoring match canonical command results |
| WEB-07 | Agenda filters before expansion/count/diagnostics; private corrupt/unsupported timezone facts do not leak through an authorized range |
| WEB-08 | Unscheduled tasks appear in item lists; whole-ledger CLI reads remain unchanged; all scoped cursors detect account/query/access/source changes |
| WEB-09 | Current/nested/historical readback obeys permissions and budgets; overflow returns no partial or falsely complete result |
| WEB-10 | Same-ID retry after timeout has one canonical effect/receipt; foreign-ID and changed-owner/payload reuse fail without disclosure |
| WEB-11 | Concurrent CLI/web/worker writes honor stale versions and transaction fences; local actor and worker semantics do not change |
| WEB-12 | Completion is not claimed to cancel all work; update/cancel keep canonical reconciliation and in-flight delivery history |
| WEB-13 | No read/no-op polling flood, bounded SQL/response/log growth, no routine full-ledger preflight scan |
| WEB-14 | Invalid Origin/Host, oversized requests, unregistered commands and mode mismatch fail; no route permits arbitrary SQL/shell/path selection |
| WEB-15 | Restricted deployment reachability and visible unverified-identity warning are tested; no authentication/executor-security capability is advertised |

Before implementation, publish machine-readable HTTP/envelope, operator/context/scoped
read, provisioning, evidence and registry schemas plus positive/negative/concurrency
fixtures for these families. Pin the exact inner contract versions already implemented
at the chosen release, not floating versions; new API families remain undeclared until
their behavior ships. Align the ontology/migration with the minimal account/access state
used here, not the entire deferred identity-provider/mandate design.

The logical draft and manual corrections passed bounded consistency recheck
`trusted-multi-operator-web-api-contract-audit-002`. This does not certify subsequent
machine artifacts or runtime behavior. No external audit, deployment or
runtime implementation is authorized merely by this document. The future GUI's visual
design is separate; this slice specifies the service it can safely and honestly consume.

### 10.1 Contract Codification

The first machine bundle is `contracts/spine.trusted-web-command-registry.v1.json`,
`contracts/schemas/trusted-web-*.schema.json`, and the associated normalization, schema-pin,
fixture and acceptance artifacts indexed in [TRUSTED_WEB_CONTRACTS.md](../docs/TRUSTED_WEB_CONTRACTS.md).
The bundle is implemented by the optional backend; `system.info` declares the supported families, not verified authentication.

Registry null request-version fields denote the existing untagged `schedule.show`,
`item.occurrences` and `task.complete` payloads, not acceptance of any supplied version.
For the untagged task-completion result only, the outer result label is
`spine.trusted-web-task-complete-result.v1`; the inner response remains unchanged.
Schema fingerprints and required runtime versions pin these shapes without inventing
new inner CLI fields. Route-specific definitions, not schema inference, select commands.

`contracts/trusted-web-normalization.v1.json` defines the plan/envelope hash preimages,
array normalization and registered ID paths for this slice. Provisioning epoch 0 means
no access-state row yet, never a live epoch; bootstrap creates epoch 1. Unchanged fresh
apply retains the epoch while still producing the normal explicit-command receipt.
Compatible replay advances nothing. This refines "apply advances" to the canonical
authorization-relevant-change rule; ordinary non-access edits retain item versions.
Initial item adoption omits creator entitlement rather than fabricating proof. Total
provisioning operations, reference checks and commit-time owner invariants remain
semantic checks in addition to schemas.

Cursor schemas capture the protected payload and include recovery epoch. They do not
make plain JSON a valid cursor. Preserve the original 15-minute expiry across pages;
publish signed wire/tamper vectors with the chosen established library before release.
Schema 13, executable backend tests, and signed vectors now accompany the bundle.
Network reachability and actual browser identity-switch behavior remain deployment/GUI
gates; local backend tests do not certify those external boundaries.


### 10.2 Implemented service profile

`spine-web` uses Flask and Waitress; `spine.web.service` owns request-local connections,
permission decisions and the outer transaction. Existing helper context managers cannot
commit independently inside that transaction. Local CLI/worker connections preserve
normal SQLite behavior. No model, subprocess, transport send, or network schema fetch
runs in web authoring. Both read snapshots share one elapsed/SQL budget; current
resource rights are rechecked before release, including time-expiring grants.

The private deployment has four request slots and at most sixteen server connections,
with bounded headers, bodies and socket inactivity. Exact Host/Origin is mandatory;
forwarded identity headers are not authority. Public readiness/info/operator reads
write nothing. Returned JSON numbers retain existing inner response types; canonical
hashes retain Spine's number-free preimages. Persisted integer reference facts are
encoded as decimal strings before plan hashing.

Schema 13 stores the deliberately small account/operator/access subset in the ontology.
Only adopted groups are subject to the resulting one-owner/unique-active-membership
checks: provisioning validates the bounded final set under the writer lock, including
atomic handoff. Historical unadopted groups do not prevent migration. This is the
immediate subset's application-level final-state check, not the deferred protected
model's proposed global partial-unique-index rollout. Raw administration requires
quiescing and revalidating the service as already specified.

Signed cursors use ItsDangerous URLSafeSerializer, salt `spine.trusted-web-cursor.v1`,
SHA-256 signing, and a random process-local key. New web ownership IDs use the
existing command derivation with prefix/row role `item_access_owner`, command
`schedule.create`, and path `/create_owner_scope`; no second item identity is introduced. The public test vector uses a known
**test-only** key. Restart/restore rotates the runtime key; old cursors fail. Agenda
cursors additionally bind an opaque canonical `domain_cursor`, preserving its exact
ordering and source-snapshot fence without reimplementing recurrence pagination.

The initial candidate ceiling is 100, not just a page-size limit. Exceeding it returns
`capacity_exceeded`; explicit readable `item_ids` can narrow agenda candidates before
expansion. Items are enumerated through ownership/grantee indexes, not the entire
coordination ledger. This bounded first profile must not be represented as unbounded
search over a large personal catalog. Future scalable indexed paging can extend this
profile without widening current budgets silently.

See [TRUSTED_WEB_OPERATIONS.md](../docs/TRUSTED_WEB_OPERATIONS.md) for provisioning,
network restrictions, error/retry interpretation, backup and paired rollback.
