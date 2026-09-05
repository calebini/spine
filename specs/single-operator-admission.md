# Spine Single-Operator Admission

Status: Draft v0.1.0; proposed contract; not implemented or audited
Created: 2026-09-05
Scope: Protected admission for one operator, delegated chat commands, local administration, and service work

## Revised Delivery Position

[accounts-and-chat-attribution.md](accounts-and-chat-attribution.md) defines the immediate
staging scope. This protected service remains future work, not a staging prerequisite.
Mappings below resolve a login account and then its explicit subject binding. The
receiving `account_id` in an issuer tuple is a channel account, distinct from the login
account ID. Exact schemas must distinguish them. The guarantees below are not weakened.

## 1. Outcome and Authority

This first slice admits authenticated requests to one configured ledger without
turning the existing agent's operating-system privileges into permission for every
chat sender. It establishes the interface that later web authentication and per-user
authorization will reuse. It does not implement a web API or per-user isolation.

[identity-and-access.md](identity-and-access.md) owns the architecture.
[agent-command-contract.md](agent-command-contract.md) owns command payloads, effects,
and replay; [operational-resilience.md](operational-resilience.md) owns resource bounds.
[openclaw-admission.md](openclaw-admission.md) owns qualification of the first chat
bridge. Existing notification, recurrence, profile, and Tickerd contracts remain
authoritative for domain work. MUST describes proposed behavior, not today's runtime.

The proposed family name is `spine.admission.v1`. It is reserved by this draft, not
an implemented capability. Section 12 lists the artifacts needed before implementation
readiness can be claimed. The Python command core must not import OpenClaw types.

## 2. First-Slice Policy

One active human subject is the configured operator. Explicit mappings may associate
several external identities with that subject. Other senders fail closed: neither
membership in a transport group nor acceptance by an ingress allowlist maps them to
the operator. Multiple humans and subject/group resource grants belong to a later slice.

The operator receives ledger-wide domain access. This does not authorize every
executor, command, delivery target, or response audience. Access is the intersection of
operator authority, authenticated executor grant, message-specific delegation where
applicable, and explicitly configured disclosure/delivery restrictions.

Configuration is a protected, versioned policy snapshot outside model-controlled
files. It has one authoritative ledger identity, operator subject, mapping registry,
executor grants, allowed response audiences, permitted delivery targets, and generation.
It contains references to credential material, not credentials in ledger rows. Atomic
replacement is an administrative action; a new generation invalidates cached allows.
No parallel mutable permission registry is introduced into coordination tables in this
slice. Physical configuration shape and its administrative lifecycle need schemas.

An existing valid ledger needs no guessed item ownership backfill for this mode.
Archetype/profile owners, subject groups, recipient facts, IDs, and existing history
remain unchanged. An operator mapping is not item ownership or an archetype default.

## 3. Admission Interface and Trust Roots

The logical interface accepts a canonical command, its existing domain request, and
an immutable authenticated context. Only trusted transport code can construct context.
Passing an ordinary JSON object called `trusted_context` to a public handler is not
authentication. The protected boundary validates the actual peer and its permissions.

The proposed first deployment uses a local protected admission service with
authenticated local IPC. The service owns ledger access. Peer identity is established
by an operating-system mechanism qualified on the supported deployment platform, not
a caller-supplied process ID, username, socket pathname, or HTTP header. Remote
assertion signing, browser authentication, and a portable network protocol are deferred.
If a platform cannot enforce the separation in Section 9, it is not qualified.

Trusted context includes these logical facts:

| Fact | Source and invariant |
|---|---|
| Context family/version | Exact supported admission family, not newest-version inference |
| Ledger identity | Service configuration; never a client-selected filesystem path |
| Initiating subject | Active mapping result, or explicitly configured service subject |
| Executing subject | Authenticated peer grant; separate from the human initiator |
| Mode | Exactly `direct`, `delegated`, or `service`; no fallback between modes |
| Mapping and executor grant revisions | Current protected policy facts |
| Origin reference | Issuer, account, conversation, sender, and event identity for delegated chat |
| Delegation reference | Message-specific operation scope, originating run, and expiry |
| Response audience reference | Independently admitted destination and execution-context audience |
| Issued and expiry times | Trusted service time; bounded lifetime, never a command timestamp |
| Policy generation | Generation used for the access decision |

Mapping keys are exact `(issuer, account_id, external_principal_id)` tuples, unique
among active mappings. Provider-specific alias normalization is explicitly qualified;
the model cannot merge a phone number and another identifier because they look related.
Spine re-resolves the mapping rather than trusting a claimed subject from the bridge.
The channel issuer includes its identity namespace; deployment display names do not.

For writes, trusted orchestration supplies `actor_subject_id` equal to the initiator
(the service subject for service mode). A proposed different actor is rejected, not
silently accepted. Existing domain payload validation remains unchanged after that
binding. Reads are authenticated even where their existing payload has no actor field.

## 4. Command and Effect Admission

The implementation must publish one versioned permission/effect registry covering
every entry in the existing compiled command registry. It adds admission requirements;
it does not replace runtime contract matching or infer permission from read/write mode.
Each entry names its canonical command, allowed modes, required executor capability,
resource/disclosure inspection, and security-sensitive embedded effects. Missing entries
prevent protected startup; new commands never inherit exposure by prefix or wildcard.

The following is the proposed classification, not a second executable registry:

| Class | Existing commands covered | Required check |
|---|---|---|
| Domain reads/builders | `item.show`, `item.list`, `item.occurrences`, `relation.list`, `agenda.show`, `schedule.show`, `schedule.build`, `schedule.binding.list`, `notification.opportunities` | Read/build grant and approved result audience |
| Catalog/discovery reads | `owner_scope.list`, `item_archetype.show`, `item_archetype.list`, `notification_profile.show`, `notification_profile.list`, `notification_profile.resolve`, `notification_profile.binding.list` | Read grant, full inventory disclosure, explicit resolution scopes |
| Runtime inspection | `system.info` | Inspection grant; no unauthenticated environment inventory |
| Item and relationship writes | `event.create`, `event.update`, `event.reschedule`, `event.cancel`, `task.create`, `task.update`, `task.complete`, `task.cancel`, `item.archive`, `relation.create` | Domain mutation grant and nested route/disclosure checks |
| Recurrence/reminder writes | `recurrence.instance.add`, `recurrence.instance.remove`, `recurrence.instance.override`, `recurrence.series.edit`, `reminder.create`, `reminder.edit`, `reminder.disable` | Domain mutation grant and delivery-target policy |
| Composite schedule writes | `schedule.create`, `schedule.update`, `schedule.cancel`, `schedule.related_task.create` | Domain mutation grant and all embedded security-sensitive effects |
| Catalog writes | `item_archetype.create`, `item_archetype.revise`, `item_archetype.retire`, `notification_profile.create`, `notification_profile.revise`, `notification_profile.retire`, `notification_profile.metadata.update`, `notification_profile.binding.set`, `notification_profile.binding.remove` | Explicit catalog-management grant; existing system-owner restrictions remain |
| Identity/routing administration | `subject.upsert`, `subject_group.upsert`, `delivery_target.upsert` | Administrative grant, unavailable to the ordinary delegated chat executor by default |
| Reconciliation | `notification_work.materialize`, `occurrence_provenance.regenerate`, `schedule.binding.reconcile` | Explicit reconciliation grant; service or operator maintenance path |

Existing lower-level commands remain legitimate interfaces under admission. They do
not have to be rewritten as `schedule.*` calls. The release registry must enumerate
them exactly and test parity with dispatch, including nested effects and dry runs.

A composite authoring request that embeds route creation/update requires the same
administrative authority as the direct route command. Ordinary chat scheduling uses
already provisioned permitted targets. The system must reject unauthorized effects
before any composite mutation; it cannot silently drop an embedded field or partially
commit. Internal reconciliation required by an authorized composite is part of that
effect, not an opportunity to obtain an autonomous worker grant.

Service grants may allow only the three reconciliation commands above and the specific
internal work-selection, attempt, and delivery functions they require. These internal
functions also need explicit registry coverage; they are not public command aliases.
Worker read access must not expose a general read endpoint to the chat executor.

## 5. Admission Ordering and Revocation

1. Enforce bounded framing, authenticate the IPC peer, and bind the configured ledger.
2. Verify exact context version, current executor grant, mode, mapping, origin binding,
   delegation lifetime, and response audience. Invalid or missing facts deny access.
3. Require normal bounded runtime preflight and the exact command-registry entry.
4. Validate the request and inspect required effects, routes, and output scope. Resolve
   current policy before revealing resource existence or stored receipt contents.
5. For an existing command ID, authorize receipt disclosure and apply Section 6.
6. For a new write, run normal domain validation and commit the mutation, receipt, and
   immutable authorization linkage atomically under a current policy generation.
7. Return the domain result only through its admitted response context. No authoring
   operation acquires permission to send an external notification directly.

The service serializes policy publication with final write authorization/commit. A
revocation published first blocks the write; a committed write remains history.
Stale policy generations require re-evaluation, never cached permission inheritance.
Read responses require a final current-generation check before release; generation
change discards an unreleased result or retries within the original request budget.
Information already released cannot be recalled.

Malformed policy or a failed reload closes admission instead of silently continuing
indefinitely with stale permissions. Operator session expiry and mapping revocation
block new human requests; accepted background work uses its independent service grant.

## 6. Replay and Evidence

Existing global `command_id` uniqueness and command-specific normalized replay rules
remain canonical. Authentication freshness and current disclosure permission are
checked before returning a receipt, including a successful no-op receipt. A stale or
forbidden caller cannot use replay to recover private results.

The protected bridge assigns a stable operation reference under the original event.
A message may yield several operations: message ID alone cannot be the command ID.
For each operation, preserve the exact prepared domain request, actor, timestamps, and
command ID. Delivery retries must not ask the model to regenerate them. Edited messages
are new requests only under a qualified edit policy; they cannot overwrite old intent.

The service binds the first accepted write to its initiating subject and stable origin/
operation reference in immutable receipt-linked evidence. A different initiating
subject or different origin cannot reuse that ID through ordinary delegated replay.
A fresh authenticated envelope may renew expiry for the same authorized operation;
session tokens, expiry, and policy generation do not enter domain identity preimages.
Replay preserves the original authorization evidence and produces no new command row.

Earlier receipts lacking admission evidence remain readable by this ledger-wide
operator through existing read surfaces. Ordinary delegated replay cannot claim them
as newly authenticated human actions. A separately authorized local maintenance path
may replay them under existing actor semantics with an explicit historical-evidence
exception; it must never backfill a guessed human origin. This exception is not exposed
to chat and requires a declared machine contract before release.

Successful writes, including command-defined no-ops, gain one authorization linkage
per existing receipt, in the same transaction. This is not a second replay ledger.
No additional durable success rows are created for reads, denial, or idle checks.
The physical evidence schema, migration, and readback projection are release gates.

## 7. Response and Delivery Audiences

Ledger-wide operator read access is not permission to disclose the whole ledger to
every conversation in which that operator speaks. The baseline response route is a
provisioned private operator audience with isolated execution history. Group-origin
requests may be routed there only by an explicit configured rule; absent a safe route,
deny before private retrieval and return only a generic no-data response.

This slice has no field-level filtering or private/group item ACLs. Therefore admitting
full ledger results to a shared agent session requires an explicit operator policy
accepting that entire session audience as a ledger-wide disclosure audience. Do not
silently enable that policy from a transport allowlist, group membership, route label,
or an LLM instruction. Without it, shared-history execution receives no ledger results.

Approval of a response audience and approval of a notification delivery target are
separate policy facts. Explicitly provisioned target references are checked on new
authoring and before each external attempt; no inference from subject-group naming.
Archetypes/profile use and their unchanged snapshots do not grant target permissions.

## 8. Workers and Failure Surface

Workers authenticate through a distinct service grant. No chat sender can activate
service mode or borrow its credential. Before processing, workers require both existing
runtime/storage safety admission and the service authorization check. Failure leaves
them not ready and starts no work or external contact; startup terminates nonzero with
one bounded diagnostic and supervisor-owned retry, consistent with existing preflight.

At runtime, grant, target-policy, or authorization availability failures stop new
processing through the existing safety-stop boundary. A target-specific denial blocks
that target's attempt without fabricating success or cancelling unrelated work. The
concrete blocked-state/reconciliation mapping must be specified before implementation.
Previously admitted in-flight sends record actual outcomes; no later retry inherits
their expired authorization. Browser logout is unrelated to worker authorization.

Admission failures use a separate proposed envelope, not added fields in existing
command responses. Its closed logical reason set is: `unauthenticated`,
`identity_unmapped`, `context_invalid`, `context_expired`, `forbidden`,
`audience_denied`, `authorization_unavailable`, and `admission_limit_exceeded`.
Exactly the first failed admission step wins; ties within context validation follow
the field order in Section 3. Authentication failures reveal no ledger facts. Detailed
mapping failures are for an authenticated trusted peer; chat receives generic denials.
After admission, domain failures keep existing error semantics. Transport envelopes,
field paths, exit mappings, and precedence fixtures require publication before release.

## 9. Deployment Enforcement and Recovery

The admission service, ingress evidence broker, and service workers are trusted code;
the LLM and its general execution sandbox are not. The agent must not have filesystem
access to the ledger or sidecars/backups, permission to become the ledger service user,
admission policy write access, or credentials allowing it to impersonate the broker.
Restricting a tool name while the same agent can import handlers or run SQLite is not
enforcement. A shell prohibition written in Markdown is not a security boundary.

Existing CLI syntax can be retained by an authenticated client facade, but protected
deployments route it through admission. Direct handlers and migration/maintenance
entrypoints remain accessible only to trusted host administration. The model cannot
select an unprotected mode with a flag, environment variable, database path, or older
binary. OS/sandbox deployment qualification is mandatory, not an optional hardening task.

Before activation, an administrator provisions the existing operator subject, identity
mappings, executor separation, service grants, audiences, and target inventory. New
ledger first-subject bootstrap is out-of-band administration, not anonymous chat access.
Preview which commands/routes will be denied; require explicit operator acceptance of
the loss of ad-hoc identity/routing administration from ordinary chat. Keep existing
schedules unless the operator explicitly changes target authorization.

Policy recovery requires authenticated host administration and bounded audit evidence.
Rollback must not restore a bypassable public agent path: stop external admission,
preserve the ledger and backups, and either restore a qualified release or remain
unavailable. No database reset is required or authorized by this spec.

## 10. Boundedness

Authentication checks perform no network calls or ledger-wide scans on the request
path. They use bounded protected policy snapshots and indexed subject/receipt lookups.
The release budget catalog must bound context bytes, mappings, executor grants,
audiences, target references, operations per event, context lifetime, authorization
deadline, queues, in-flight contexts, and diagnostic storage. Missing/invalid budgets
fail protected startup; overload rejects work rather than growing queues indefinitely.

Reads have no durable event journal. A bridge retry spool may retain prepared writes
only with byte/count/time bounds and crash recovery; capacity exhaustion fails before
new dispatch. Eviction cannot turn an old duplicate into a new operation: beyond the
supported ingress replay window, reject/redemand a new request instead of regenerating.
Detailed spool and duplicate-window contracts belong to the bridge qualification.

## 11. Required Proofs

These are future acceptance tests, not evidence of implemented behavior:

| ID | Oracle |
|---|---|
| SA-01 | Unknown sender or caller-authored identity cannot invoke a handler |
| SA-02 | Two senders in one group never share authenticated context |
| SA-03 | Delegated requests cannot select service/local-admin mode or another actor |
| SA-04 | Command/effect registry exactly covers runtime dispatch; new unclassified commands fail startup |
| SA-05 | Direct and embedded route mutation receive identical permission checks and atomic rejection |
| SA-06 | All authorized lower-level and composite commands retain their existing domain behavior |
| SA-07 | Duplicate prepared writes, lost replies, and refreshed auth envelopes create one effect/receipt/linkage |
| SA-08 | Reused command ID from another origin or lost permission reveals no receipt |
| SA-09 | Policy revocation races writes/reads/attempts at the declared admission boundary |
| SA-10 | Private output never enters an unapproved shared session, history, log, or reply |
| SA-11 | Agent shell, alternate CLI, raw DB, policy edits, and broker impersonation cannot bypass admission |
| SA-12 | Human logout leaves accepted authorized work running; revoked worker grant stops new processing |
| SA-13 | Failed preflight and overloaded/idle/denied paths cause no unbounded durable growth |
| SA-14 | Existing schedules, catalog snapshots, receipts, and domain IDs survive activation and safe rollback |
| SA-15 | Historical replay exception is local-admin-only and never invents human attribution |

## 12. Next Gates

This batch specifies the target and proof obligations. Before runtime implementation:

1. Qualify the actual OpenClaw ingress, tool-runtime context, process isolation, and
   response-history behavior using the companion spec. Unknown facts remain blockers.
2. Ratify local protected IPC, private-response defaults, ordinary-chat administrative
   restrictions, and the historical replay exception as deployment/product choices.
3. Publish exact admission/context/policy/failure/receipt-linkage schemas; the complete
   command and internal-effect registry; numeric budgets; and executable fixtures.
4. Specify the authorization-evidence migration, policy generation/locking protocol,
   service blocked-state mapping, CLI facade, and bootstrap/recovery commands.
5. Run a bounded contract audit, then implement and verify on an isolated ledger before
   deployment. No per-user ACLs, web adapter, or new scheduling behavior is required.
