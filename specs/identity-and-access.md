# Spine Identity and Access

Status: Draft v0.5.0; protected authentication/delegation deferred; current revision not implemented or audited
Created: 2026-09-05
Scope: Authentication adapters, subject mapping, ownership, group roles, delegated requests, and authorization across Spine surfaces

## Revised Staging Direction

[accounts-and-chat-attribution.md](accounts-and-chat-attribution.md) defines the immediate
trusted multi-operator scope: stable accounts distinct from subjects, honest web identity
selection, and observed rather than verified chat attribution. Authentication and
automated recovery are deferred. The protected
rules below remain a future target. References to first delivery below mean the first
protected delivery. Principal-to-subject mappings are composed through a stable account
and its explicit subject binding; the account draft owns this refinement. Account IDs
never substitute for subject IDs. Observation does not satisfy verified authentication.

[permissions.md](permissions.md) owns the multi-user resource/role model and the
explicit single-operator and multi-user deployment modes. Specification targets
multi-user behavior even when implementation first enables single-operator full access.
The direct CLI remains trusted-local and full-scope. Protected executor enforcement
and OpenClaw qualification remain separate future work.

[permission-enforcement-and-web-admission.md](permission-enforcement-and-web-admission.md)
is the successor enforcement draft. It specifies proposed persistence, command/effect
dispositions, session/epoch semantics and delivery gates. Its Section 1 now prioritizes
`multi_user` plus `trusted_identity`; the protected web/session and chat-first paths
below are deferred, not prerequisites for that trusted web interface. The audited
role policy in `permissions.md` remains authoritative, including catalog/route admin
rights being separate from item edit grants.

## 1. Purpose and Delivery Boundary

Spine needs to identify the caller and enforce that caller's authority consistently
whether a request arrives through a web GUI, local command, service, or natural-language
message. Authentication methods may change without changing canonical subject IDs,
group IDs, item ownership, notification profiles, or scheduling semantics.

This document specifies a proposed architecture. MUST and MUST NOT describe the target
behavior once the relevant capability is implemented; they do not assert that today's
runtime enforces it. Exact machine envelopes, permission mappings, migrations, and
adapter qualification remain implementation prerequisites in Section 17.

The first delivery is authenticated single-operator access to one configured ledger.
The later delivery adds subject/group resource access. The first MUST establish the
same trusted-context and authorization interfaces, but need not implement sharing,
group administration, or ownership backfill for every existing item.

This is not an HTTP routing specification, identity-provider implementation, password
store, general policy language, or replacement for external-action governance. It does
not add facets, contextual-advisory execution, or new scheduling behavior.

The first-slice proposal is now developed in
[single-operator-admission.md](single-operator-admission.md), with the initial chat
provider qualification in [openclaw-admission.md](openclaw-admission.md). Chat/agent
admission is prioritized; a web adapter later reuses the same trusted-context boundary.
These leaf drafts do not implement or ratify the later group-role/access model below.

## 2. Authority and Current Baseline

Related authorities are [ontology.md](ontology.md),
[agent-command-contract.md](agent-command-contract.md),
[notification-profiles.md](notification-profiles.md),
[owner-scope-discovery.md](owner-scope-discovery.md),
[notifications.md](notifications.md), [architecture.md](architecture.md),
[operational-resilience.md](operational-resilience.md).

[contextual-advisories.md](contextual-advisories.md) is background context for future
consumers, not a normative dependency of this identity/access proposal.
Contextual-advisory behavior is outside this draft's scope.

The implemented baseline has canonical subjects, arbitrary subject groups,
subject memberships with `member` and `owner` roles, versioned item subject roles,
and explicit ownership on archetypes, notification profiles, bindings, and delivery
targets. Item subject roles include `owner`, but are not an implemented access policy.
Actor existence checks establish attribution, not authentication. Owner discovery is
not permission discovery. No current principal mapping or per-user enforcement is
implied by those records.

This draft proposes an `admin` group role and an explicit item access-owner record.
It does not change existing enums, command envelopes, schema versions, or implemented
contract declarations. Conflicts with implemented contracts require explicit successor
contracts before rollout; prose here MUST NOT silently reinterpret stored facts.

## 3. Roles and Trust Boundaries

| Role | Responsibility |
|---|---|
| Authentication adapter | Verify credentials or trusted transport evidence; produce an authenticated external principal |
| Identity mapper | Resolve that external principal to exactly one active Spine subject |
| Spine authorization service | Evaluate access using canonical owners, memberships, grants, service limits, and current policy |
| Agent runtime | Interpret user intent and propose commands within a verified delegated context |
| Governance authority | Authorize governed capabilities and consequential external actions when required |
| Delivery adapter | Execute admitted notification work through the existing attempt boundary |

Authentication establishes the caller's identity, not permissions. Spine owns canonical
resource-access decisions over its own records. This does not move external-action
approval policy or execution-evidence acceptance out of the governance authority. When
both apply, both decisions are required; neither can grant the other's authority.

Public contracts name these roles, not deployment brands. Provider names, endpoints,
trust keys, credentials, and verification mechanisms belong in adapter configuration.
Spine MUST NOT store passwords, bearer tokens, or authentication-provider sessions as
canonical coordination facts.

## 4. Authentication Interface and Identity Mapping

An authentication adapter produces a verified assertion through an authenticated
service channel or an equivalently protected in-process interface. A JSON object from
a browser, LLM, or arbitrary local client is not a trusted assertion merely because
its fields have the expected names.

The logical assertion contains:

- configured issuer identity and external principal identifier;
- intended deployment/ledger audience;
- verification evidence reference, issue time, and expiry;
- authentication method and verified assurance facts;
- unique assertion/request correlation reference; and
- for message-origin requests, the verified message and conversation references.

An adapter's accepted proof, subject-identifier semantics, signature or channel checks,
freshness window, duplicate handling, and maximum sizes MUST be defined in its versioned
trust profile before admission. Unsupported issuers, missing proofs, expired assertions,
wrong audiences, and unverified assurance claims fail closed. Untrusted proxy headers
cannot supply authenticated identity.

Mappings are explicit bindings of `(issuer, external_principal_id)` to `subject_id`
within the configured deployment. Exactly one active mapping is permitted for that
pair. Several external identities may map to the same subject. Names, email text,
phone-number appearance, profile descriptions, and group titles MUST NOT be used to
merge subjects implicitly. Normalization belongs to the issuer's declared contract.

A mapping has status, revision, creation/change evidence, and revocation history.
Disabled mappings and inactive subjects cannot initiate new authorized requests.
Unmapped senders require an explicit enrollment/linking operation by an authorized
identity administrator; they MUST NOT be silently treated as the operator or agent.
Account relinking requires proof under the configured adapter/enrollment policy and
revokes the previous binding. A recycled phone number is not permanent proof of the
same human. Mapping revisions participate in request invalidation.

Authentication methods are interchangeable when they implement this interface. Web
login, service credentials, a verified local credential, and messaging-origin evidence
need no separate subject namespaces inside Spine.

## 5. Trusted Request Context and Agent Delegation

The admission layer constructs an immutable context outside the model-controlled
command payload. Its minimum logical facts are:

| Fact | Meaning |
|---|---|
| Initiating subject | Human or autonomous service whose authority is requested |
| Executing subject | Agent/service submitting the operation, or the initiating subject for direct use |
| Identity binding and assertion references | Proof of subject mapping and authentication freshness |
| Execution mode | Direct, delegated, or autonomous service; never inferred from missing human context |
| Ledger audience and access-policy revision | Target deployment and policy used for admission |
| Delegation reference, scope, expiry | Allowed executor, operations, resource scope, and request provenance |
| Origin and response audience | Trusted source context and permitted destination for returned information |
| Correlation reference | Links admission, command, receipt, and relevant delivery evidence |

For delegated requests, effective authority is the intersection of the initiating
subject's current permissions, the executor's allowed operations, and the delegation
scope. It is never the union of the human and service permissions. One-hop delegation
is the initial model; delegation chains are deferred.

The same agent may have an autonomous worker role and a delegated chat role. These
MUST be distinct grants. It cannot fall back to its autonomous grant when a chat sender
is unknown or forbidden. Origin metadata and an instruction saying "act as Caleb" do
not constitute a delegation.

In the proposed command integration, `actor_subject_id` is the initiating subject for
direct or delegated authoring and the service subject for autonomous work. The admission
layer MUST verify equality; an executor cannot choose another actor. Execution identity
and origin remain separate linked evidence. Historical actors and receipts are not
rewritten. The exact binding to existing command/audit shapes requires a versioned
extension before implementation.

A delegated request may authorize a bounded set of commands for one message, but every
command still receives independent resource authorization. A trusted orchestration
layer assigns stable per-operation command IDs and preserves the exact normalized
request for retries. Message identity alone is not a command ID when a request contains
several operations. Retries MUST NOT regenerate authoring timestamps or recompile a
different request under an already consumed command ID.

## 6. Messaging Authentication and Response Audience

Routine chat scheduling need not require another login when a qualified messaging
adapter verifies the sender. A qualifying adapter establishes both the authenticity of
the gateway event and its sender semantics; authenticating the gateway alone does not
prove which human originated a message.

For example, a trusted WhatsApp adapter may supply a verified sender identifier and
conversation identifier. The former maps to a subject. A separately configured
conversation binding may suggest a subject-group context and a permitted reply target.
It grants no membership, role, catalog precedence, or item ownership by itself.

Display names, quoted or forwarded messages, model-generated tool arguments, and
user-written sender fields MUST NOT authenticate a caller. Bot/system messages without
a verifiable human origin use a separately authorized service path or are rejected.
Provider message edits and duplicate delivery need explicit adapter rules and MUST NOT
silently mutate a previously accepted command.

Permission to read privately is not permission to disclose into the originating group.
Before private context is supplied to an agent that will answer in a shared channel,
the system MUST constrain retrieval to the authorized response audience or establish a
separate private response channel. This check cannot depend solely on the LLM remembering
not to disclose sensitive text. Detailed receipts and error messages are disclosures
too. An unrecognized or ambiguous audience does not default to the sender's full access.

An authorized release of item information to a delivery target is distinct from giving
that audience API access to the entire item. The actor must be allowed to release the
requested content and use that target. Merely being able to edit an item or use a route
does not permit arbitrary cross-owner disclosure.

The authentication policy may require stronger proof for identity linking, access
administration, ownership transfer, or routing changes. A confirmation in the same
chat does not inherently increase assurance. Exact assurance requirements and step-up
methods belong to the deployment's qualified authentication policy, not archetypes.

## 7. Ownership and Resource Access

[permissions.md](permissions.md) Sections 2-4 own access modes, item/canonical-catalog
ownership, and operation-level permissions. One item owner is a subject or group;
participation, assignment, profile use, and chat context are not ownership. Existing
storage requires explicit adoption before multi-user enforcement. This architectural
document does not maintain a competing permission table.

## 8. Group Roles

[permissions.md](permissions.md) Section 5 owns the proposed member/admin/owner matrix,
creator-entitlement limits, designated ownership, handoff, and suspension/recovery.
Roles are scoped memberships, not global account types or a separate identity system.
The matrix remains draft; current membership enums are not extended by this reference.

## 9. Permissions and Explicit Grants

[permissions.md](permissions.md) Sections 4-10 own additive grants, evaluation,
revocation, mode transitions, and inspection. Ownership, group roles, and grants produce
resource authority; authenticated executor/delegation and response-audience limits can
restrict it, never expand it. External-action governance remains a separate gate.

## 10. Archetypes, Profiles, and Existing Schedules

Archetype classification and profile resolution retain their existing deterministic
semantics. Authorization MUST NOT infer an archetype, reorder a scope chain, silently
skip an unauthorized scope, substitute a different profile, or stack defaults.

The caller must be allowed to read/use every explicitly requested resolution scope and
the selected archetype/profile. An inaccessible requested scope fails authorization
before resolution; it must not appear as "no matching profile" and activate a custom
fallback. Existing current/exact revision selection, suppression, replacement, and
custom-addition rules remain domain authority.

Applying a profile to an item creates the existing immutable snapshot. Losing future
catalog-use access, changing a binding, or retiring the source profile does not erase
the item's authored notification policies. Authorized item readers can inspect the
effective policies and application evidence already committed with that item. This
does not authorize fetching additional current or historical catalog content beyond
that stored snapshot.

System catalog entries are not implicitly public merely because their owner is
`system`. The configured policy declares read/use availability; ordinary catalog
commands still cannot mutate system-owned entries.

The authorization layer MUST preserve the distinction between policy authoring,
opportunity expansion, materialization, attempted delivery, and delivered outcome.
Changes in access MUST NOT fabricate a cancellation, successful send, or modified
historical attempt.

## 11. Admission, Replay, and Consistency

All exposed transports use the same command admission boundary. Enforcement cannot
exist only in HTTP middleware while an agent-facing command path bypasses it. Direct
database access remains an operator/system privilege outside this application boundary;
arbitrary shell or database access cannot be made safe by API authorization alone.

Admission proceeds as follows:

1. Apply transport size limits and resolve the exposed operation without disclosing
   ledger contents. Require a configured ledger and admitted runtime contracts.
2. Verify the assertion, current mapping, initiating/executing subjects, audience,
   delegation, and required assurance.
3. Parse the bounded request and establish the operation's complete resource set,
   including owner scopes, profiles, routes, relation endpoints, and output audience.
4. Evaluate current access and any required governance evidence. Deny by default.
5. For replay, authorize access to the stored operation and its receipt before returning
   evidence. Preserve original command compatibility and replay-before-domain-staleness
   rules after this access check. Replay never performs a fresh effect.
6. For a fresh mutation, validate domain preconditions and commit mutation, receipt,
   and accepted authorization linkage consistently. A changed access revision requires
   re-evaluation or a structured conflict before commit.
7. Return only information authorized for the caller and the declared response audience.

Authentication and access revision changes cannot be hidden behind a cached allow
decision. A write's authorization linearizes with its canonical mutation: a revocation
committed first prevents that mutation; a mutation committed first remains evidence.
Read results use one consistent, bounded snapshot with its access revision. Requests
admitted after a revocation must not receive previously cached protected content.

Permission to replay does not require a currently writable item: authorized readback of
an original operation may survive completion or archival. The caller must still be the
original initiating subject or an explicitly permitted receipt auditor, remain allowed
to invoke that replay path, and have current access to all returned evidence. Unrelated
callers cannot probe globally unique command IDs to discover another user's operations.

Public failures distinguish unauthenticated, unmapped, expired/revoked, insufficient
assurance, forbidden, and unavailable-authorization conditions at the appropriate
trusted interface. Resource existence and access failures share a non-enumerating
public response where disclosure is not authorized. Richer internal reasons remain
available only to permitted administrators. Exact error identifiers, HTTP/CLI mappings,
and existing-command precedence require closed machine contracts before release.

## 12. Reads, Cursors, and Information Boundaries

List filtering occurs before counts, ordering, pagination, and expansion. Fetching the
whole ledger and hiding unauthorized rows in the GUI is non-conforming. Detail views,
relations, notification routes, histories, receipts, diagnostics, and search results
must obey the same resource policy. Cross-owner nested data needs an explicit permitted
projection or a versioned omission/redaction shape; it cannot leak through an include flag.

Cursors and caches bind to ledger, effective subject, relevant executor/delegation
scope, authorized response audience, query, and access revision. Current authentication
is checked on every use. Membership, sharing, ownership, or mapping changes invalidate
affected pages; conservative generation invalidation is allowed. Snapshot hashing must
not expose or scan unauthorized records merely to derive a cursor.

Existing `owner_scope.list` remains identity discovery, not authorization truth. A
future access-scoped discovery contract may return only visible scopes and available
operations, but cannot silently change the existing complete-inventory contract.
The single operator's ledger-wide view can reuse today's complete inventory.

The initial per-user model is whole-resource access. Selectively revealing only the
time of a private medical appointment requires a separate projection contract and is
deferred. A view denial must not leak its title, location, recipient, or existence in
counts or errors.

## 13. Background Work, Revocation, and Delivery

Workers use their own authenticated service identities and narrowly scoped grants.
They do not depend on a human browser session staying alive. Acceptance of a schedule
creates durable coordination intent; human logout does not undo that intent.

The proposed later model records a durable delivery mandate linking authorized content
release, item owner, permitted destination, and scheduling intent. Each attempt rechecks
the service grant, mandate status, current ownership/access revision where relevant,
route validity, existing freshness rules, and any required governance decision before
external contact. A service grant alone does not authorize delivery of every item.

The default proposed revocation semantics are:

- Session expiry blocks new interactive requests, not accepted background schedules.
- Catalog-access revocation leaves applied item snapshots intact.
- Ending the creator's group membership blocks their new group actions; group-owned
  schedules continue under group authority unless the delivery mandate is revoked.
- Revoking a delivery mandate or route-use grant blocks subsequent attempts and produces
  inspectable blocked/reconciliation state without rewriting prior attempts.
- Ownership transfer requires reauthorization of future delivery mandates. Destination
  membership changes must follow the explicit audience policy, not an inferred reroute.

A dynamic transport group cannot prove that every future group member was individually
approved at schedule creation. Its mandate must explicitly authorize the group endpoint
as a changing audience or require separately verified recipient membership. This choice
must be visible when private content is released to that group.

Revocation does not recall a message already sent. If an attempt was admitted before a
revocation and external contact is in progress, the system records its actual outcome;
it does not claim to retract the effect. No retry may use the prior admission as a new
grant after revocation. Exact attempt admission and mandate lifecycle contracts are
required before per-user delivery enforcement.

## 14. Evidence and Resource Bounds

Access-state mutations and accepted domain mutations retain auditable references to
initiator, executor, mapping/delegation revisions, policy/access revision, evaluated
operations, and command/receipt identity. This supplements existing audit and receipt
authorities; it must not create a second command replay ledger.

Routine authorized reads and idle worker checks MUST NOT create durable command
receipts or an unbounded permission-decision row per request. Security diagnostics use
configured bounds and aggregation; sensitive contents, credentials, tokens, and full
chat transcripts are excluded. Mapping/grant history and necessary mutation evidence
require explicit retention classification under operational-resilience work.

Membership/grant lookup, resource expansion, delegation size, and authorization caches
have declared bounds and indexes. Unavailable or timed-out authorization denies the
affected operation; retry/health behavior must avoid a polling or diagnostic flood.
Required evidence failure prevents a fresh mutation or side effect from proceeding.

## 15. Single-Operator Delivery and Later Adoption

The first capability provides one configured operator subject with explicit ledger-wide
application access, qualified authentication adapter(s), subject mappings, delegated
request admission, and scoped worker identities. It declares its single-operator mode;
it MUST NOT advertise per-user privacy or granular group permissions. Multiple verified
external identities can map to this operator, but other senders are not automatically
admitted. An API service does not select an arbitrary ledger from a client-supplied path.

CLI authentication may use a configured local credential or a qualified operating-system
identity binding. Mere process locality is not authentication. Unconfigured access fails
closed once enforcement is enabled; a server or agent cannot select a hidden trusted
mode. Explicit administrative recovery remains an out-of-band host privilege with
documented backup, recovery, and audit procedures.

Before per-user activation, an authorized adoption plan must inventory existing items,
owner roles, memberships, catalogs, routes, and work; propose explicit item owners and
resolve missing/conflicting owners; preserve historical domain IDs and receipts; and
establish delivery mandates for existing schedules. Ambiguous owners are decisions for
the operator, not guesses from title, creator, profile, recipient, or conversation.
Existing multiple/missing group owners also require explicit resolution.

Migration, preview, acceptance, backup/restore, and rollback tests precede enforcement.
Single-operator access can remain available while adoption is incomplete, but the
runtime must not claim isolation. No migration is required merely to publish this draft.

## 16. Acceptance Scenarios for the Future Contract Suite

These are required future behavioral tests, not claims of existing coverage:

| ID | Scenario and expected outcome |
|---|---|
| IA-01 | Two qualified authentication methods mapped to the same subject produce the same effective domain permissions |
| IA-02 | Forged sender headers, wrong audience, expired proof, unmapped origin, and inactive mappings fail before domain mutation |
| IA-03 | Changing payload actor, owner, or an agent's claimed delegation cannot elevate authority |
| IA-04 | A known chat sender schedules without repeated login; unknown senders never inherit the bot's service grant |
| IA-05 | A private read requested in a group chat exposes no private content or receipt to that group without explicit release |
| IA-06 | Members create/edit their own group items but cannot edit others, administer catalogs/routes, or promote themselves without the required grant |
| IA-07 | Admins manage group resources but cannot inspect private member items or transfer group ownership |
| IA-08 | A private item uses a shared profile without changing owner; use permission cannot revise the source profile |
| IA-09 | An unauthorized resolution scope fails before fallback; authorized profile selection keeps the same deterministic semantics |
| IA-10 | Profile-access revocation preserves applied policies; later profile edits do not rewrite snapshots |
| IA-11 | Cross-user lists, includes, counts, cursors, histories, relation targets, and receipt-ID probes disclose no unauthorized resource |
| IA-12 | Revocation racing a mutation observes the defined commit boundary; a changed scope invalidates pages and cached decisions |
| IA-13 | Compatible authorized replay returns stored evidence without a second effect; lost access prevents receipt disclosure |
| IA-14 | Logout leaves accepted schedules running; revoked delivery authority prevents new attempts while preserving actual past outcomes |
| IA-15 | Ending membership removes group-derived and creator permissions; explicitly independent grants are reported accurately |
| IA-16 | Ownership handoff requires an explicit successor; suspension blocks access without automatic promotion, and related resources retain their owners |
| IA-17 | Repeated reads, denials, and idle checks meet latency/storage bounds without unbounded durable evidence growth |
| IA-18 | CLI, HTTP, agent, and worker adapters enforce equivalent access for equivalent contexts; unavailable authorization fails closed |
| IA-19 | Adoption leaves existing authorized schedules, recurrence, profiles, bindings, receipts, and delivery semantics unchanged except explicitly approved access changes |

## 17. Work Required Before Implementation

The next specification pass must close these concrete dependencies:

1. Ratify the proposed role matrix, creator entitlement, single group-owner rule, and
   permission to use catalog snapshots after source-access revocation.
2. Select the first authentication adapters and define trust, enrollment/relinking,
   assurance, expiry/revocation, shared-response-audience, and private-reply contracts.
3. Publish versioned assertion, mapping, delegation, decision, failure, and readback
   schemas, with field domains, limits, privacy rules, and identifiers. No adapter may
   advertise conformance from this logical field list alone.
4. Publish the closed command-to-permission/resource registry and transport parity
   tests. Include creation, catalog resolution, cross-owner relations, route use,
   output disclosure, replay, and required governance evidence.
5. Amend ontology and migrations for mappings, explicit item access owners, roles,
   grants, access generations, and durable delivery mandates as the slice requires.
   Specify concurrency, historical owner-role reconciliation, and recovery semantics.
6. Define supported provisioning and administration commands, effective-access
   inspection, successor access-scoped queries, schema versions, and exact runtime
   capability declarations. Provide adoption fixtures for existing staging records.
7. Define bounded cross-process revocation, read snapshots, caches, attempt-start
   authorization, and evidence storage before claiming per-user isolation.

Qualify the chat-origin path, complete the single-operator machine contracts, and audit
that trust boundary first. Implement the protected chat/agent path over existing command
services; an HTTP adapter subsequently reuses it. Qualify the group/resource extension
separately. This document authorizes no runtime change, identity-provider selection,
deployment, or external audit by itself.
