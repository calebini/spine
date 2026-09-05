# Accounts and Trusted-Agent Chat Attribution

Status: Draft v0.3.0; account lifecycle and attribution contract; not implemented or audited
Created: 2026-09-05

## 1. Decision and Scope

The immediate direction is lower-assurance trusted-agent attribution, not deployment
of the protected admission service. Observed sender metadata may help an agent resolve
an account, but is not independently verified authentication. The stronger designs in
[single-operator-admission.md](single-operator-admission.md) and
[openclaw-admission.md](openclaw-admission.md) remain future qualification targets.
They are not weakened or claimed satisfied by this staging approach.

This draft adds an account abstraction separate from the coordination subject defined
in [ontology.md](ontology.md). It records onboarding and linking requirements, not new
runtime commands, an implemented account schema, or permission to enroll real users.

[permissions.md](permissions.md) owns the full multi-user access model. Single-operator
mode admits only its configured operator with ledger-wide application access; multi-user
mode admits authenticated active accounts with per-resource permissions. An unbound
account has account self-service only, not coordination access. Group roles do not change
account identity, and signup grants no resource rights. Both modes use these same records.
The first implementation may support only single-operator mode without claiming
multi-user enforcement.

## 2. Identity Layers

| Layer | Responsibility |
|---|---|
| Login identifier | User-facing way to find an account; initially a phone number |
| Account | Stable internal account ID, login identifiers, authentication-method references, lifecycle and assurance evidence |
| Account-to-subject binding | Explicit, deployment-scoped connection between an account and a coordination subject |
| Spine subject | Coordination identity used for participation, attribution, and later permissions; may exist without an account |

An account ID MUST be opaque and stable, independent of its phone number, provider,
display name, and subject ID. Changing a number must not require replacing the account
or rewriting coordination history. A phone number is the initial user-facing account
identifier, not an immutable primary key or proof of the human holding the device.

A subject may exist without any login account, such as a child represented in family
scheduling. Account creation does not imply that all existing subjects need accounts.
An account may have multiple login methods. Initially, each account has at most one
active subject binding per deployment, and each subject at most one active account
binding there; additional methods attach to that account rather than create duplicates.
Multi-account representation of one subject and account switching between subjects
require later explicit semantics, not inferred merging.

The account-management component owns account lifecycle and authentication-method references.
Spine owns canonical subject facts and the binding used for attribution. Their physical
hosting may be colocated or separate; no new repository or service is mandated here.
Passwords, provider sessions, and bearer credentials do not belong in coordination rows.

## 3. Phone-Identifier Rules

Phone identifiers use an explicitly defined international normalization contract before
lookup. The model must not guess a country code or equate ambiguous strings. The exact
normalization library/version and validation fixtures are implementation prerequisites.
Issuer/account namespaces remain part of channel evidence even when two channels
present the same normalized number.

Within an account realm, one normalized active phone identifier resolves to at most
one account. Conflicts require reconciliation, not overwrite. Matching a number can
locate a candidate account; it never alone authorizes login, merges subjects, transfers
ownership, or proves that a new channel is controlled by the same human.

Observed and verified evidence are distinguished by method, issuer, timestamp, and
status. An identifier seen in prompt metadata stays observed unless an independent
verification step succeeds. A second observation, including in another chat, does not
upgrade its assurance.

## 4. Trusted-Agent Staging Mode

The user reported stable `sender_id` observations across direct and group chats.
The supplied sample identifies the source as supplied prompt metadata; trusted
runtime sender identity was unavailable to the observing agent. This supports an
identifier-stability hypothesis, not cryptographic provenance or spoof resistance.

In this explicitly declared mode, the deployment trusts OpenClaw and the agent to
attribute requests correctly. A configured observed identifier may resolve an account
and its bound subject. The agent must not infer identity from names, quotes, message
claims, or conversation history. Unknown, missing, or conflicting metadata triggers
clarification or enrollment; it must not fall back to the operator or executing agent.

`sender_id` is an account-resolution hint. `chat_id` and chat type are conversation
and routing context, not group membership, ownership, or permission. Chat-specific
identifiers and sender aliases require explicit normalization; no shared-session identity.

This mode does not protect against fabricated actor arguments, prompt injection,
model misattribution, compromised accounts, or privileged shell/database bypass.
It MUST NOT advertise verified caller authentication or per-user isolation. Existing
operator privileges remain a staging trust decision, not permissions granted by the
observed ID. General multi-user access is not safe merely because accounts exist.

## 5. Chat-First Enrollment

The desired user experience is to begin in chat and obtain an account immediately.
A deployment may explicitly enable first-use provisional enrollment. It creates or
resolves a provisional account with the observed phone identifier; it does not verify
phone possession. Enrollment is idempotent for the same qualified realm/identifier
and must handle concurrent first use without duplicate accounts.

Creating a corresponding new subject and binding is a separate explicit enrollment
effect, which may be bundled atomically by a future command. Linking an existing
subject requires authorized reconciliation; name or number similarity is insufficient.
Without an active subject binding and the required access/attribution approval, the
account cannot supply an actionable Spine subject. A binding alone is not authentication.
Account IDs are never inserted into `actor_subject_id` as if they were subject IDs.

Enrollment grants no membership in existing groups, no access to existing records,
no notification-profile ownership, and no administrative authority. A provisional
account is not automatically enabled to act through the existing privileged operator
agent. Group join and access provisioning remain separate explicit decisions.

Automatic enrollment needs rate, count, storage, and retry bounds before implementation;
repeated observations must not create durable rows per message. The current staging
operator flow may continue with manually provisioned mappings until those commands exist.

## 6. Continue on the Web

Entering the phone number locates an account candidate without disclosing whether it
exists. Web access requires a verification challenge or another accepted authentication
method before data is released. Merely typing a number never logs someone in.

A successful proof can establish control of the number at that time, not historical
ownership of the account. Claiming a provisional account with no existing protected
data/grants requires a defined enrollment policy. Linking to an established account,
recovering access, or upgrading a provisional account already linked to sensitive data
requires an existing trusted factor or authorized recovery review. Do not silently
unlock historical data solely because a recycled number now passes a challenge.

After authorized linking, web and chat resolve the same stable account and its subject
binding. Additional methods, such as a passkey, attach to the same account. Adding or
removing a method requires authorized account management, not a chat assertion.
Exact provider, challenge, session, and recovery contracts remain to be selected.

## 7. Lifecycle and Audit

Phone replacement, identifier revocation, account suspension, binding changes, and
recovery require explicit lifecycle operations and evidence. No automatic merge or
transfer is performed because a number is reused. Revoking an identifier prevents its
future use but preserves the account ID, subject ID, and historical attribution.

Account suspension prevents new account-originated actions; it does not delete the
subject or silently cancel scheduled work. Background delivery continues only under
its separately defined service/route authority. These rules must compose with later
protected admission rather than retrofit historical observations as verified proof.

Evidence and diagnostics must retain assurance distinctions and be bounded. Do not
record full phone numbers in public docs, shared diagnostic reports, or per-message
durable logs. No existing receipt or actor is rewritten by publication of this draft.

## 8. Proposed Logical Records

These are logical contracts, not SQLite table declarations or new public commands.
All identifiers below are opaque stable IDs. Exact encodings and schema names must
be published before implementation.

| Record | Required logical facts |
|---|---|
| Account | Account ID, realm ID, lifecycle state, revision, creation/change evidence |
| Login identifier | Identifier ID, account ID, kind, normalized value, active/revoked status, revision |
| Identity evidence | Evidence ID, identifier reference, source/method, observed or verified classification, acquisition time, expiry where applicable, revocation state |
| Subject binding | Binding ID, account ID, deployment ID, subject ID, active/revoked status, revision, authorizing evidence |
| Authentication method | Method reference, account ID, method kind, active/revoked status; secrets stay in the authentication subsystem |
| Staging attribution registration | Account and subject binding, approved source namespace, active/disabled state, operator authorization and revision |

The account realm is one explicitly configured identity namespace. It is not a subject
group, chat ID, phone-country prefix, or caller-selected database path. The initial
deployment uses one realm. Moving between realms, account merging, and realm federation
are deferred; identical phone strings in separate realms do not establish a shared account.

Account lifecycle, identifier status, evidence assurance, subject status, and access
grants are independent. An active account may receive an observed chat request and,
separately, a verified web session. The latter does not upgrade the former. There is no
global account boolean that makes every channel "verified."

A staging attribution registration is explicit operator approval to use an existing
binding through a specified lower-assurance source. It is not a general resource ACL
or an enforceable executor grant. Creating an account or binding does not create this
registration automatically. The current privileged local agent remains trusted; stronger
enforcement is not implied by these records.

## 9. Account Lifecycle

The proposed closed lifecycle is `provisional`, `active`, `suspended`, or `closed`.

| Transition | Requirement and consequence |
|---|---|
| Absent -> provisional | Explicitly enabled first-use enrollment; reserve one identifier; no existing access or groups |
| Provisional -> active | Authorized account activation following verification/claim policy or explicit staging administrator approval |
| Provisional/active -> suspended | Authorized suspension; reject new account-originated attribution and authentication |
| Suspended -> provisional/active | Authorized restoration to the recorded previous state; recheck current bindings and credentials |
| Provisional/active/suspended -> closed | Authorized closure; disable new login and attribution, preserve history |
| Closed -> any state | Not supported in this slice; no silent reopening on a new message |

A suspended record retains its pre-suspension state. Restoration does not resurrect
revoked identifiers, methods, or bindings. Activation by staging administrator approval
records that basis; it does not assert phone possession or establish a web session.
Verified evidence alone does not automatically activate, restore, or authorize an account.

Closure is not deletion of the subject, item history, or receipts. Identifier reservation
history remains available for authorized conflict checks. A revoked/closed identifier
must not be automatically claimed for a new account by first-use enrollment. Number
reassignment requires explicit recovery/reassignment review and does not transfer old data.

## 10. Enrollment, Linking, and Attribution Outcomes

The following proposed operations need versioned request/response schemas before they
become commands. They reuse the existing command and receipt discipline where they
mutate Spine-managed records; they do not introduce another replay authority.

- **Observe/resolve:** bounded read of an explicitly supplied realm and normalized
  identifier. Returns a candidate, no match, or a restricted conflict/status result.
  It creates no account, refreshes no evidence row, and writes no receipt.
- **Enroll:** reserve an unclaimed identifier and create a provisional account.
  An optional explicit mode may atomically create a new subject and binding. It must
  not attach an existing subject by inferred similarity or reactivate a blocked account.
- **Bind existing subject:** privileged operation with explicit account, subject,
  expected revisions, and authorizing evidence. Reject conflicting active bindings.
- **Activate or register staging attribution:** explicit administrative operations;
  neither can be obtained by presenting the same number again.
- **Manage lifecycle/identifier/method:** dedicated revision-checked operations.
  Generic display-metadata edits cannot change binding, assurance, or lifecycle.
- **Inspect:** authorized readback of account, identifiers, binding state, assurance
  provenance, and blocking reason without secret material.

Enrollment checks existing identifier reservations before creating anything. Repeating
the same command ID and compatible normalized payload returns its existing receipt.
A new command ID for an already-enrolled identifier returns an explicit unchanged outcome
to an authorized caller; it does not modify evidence, display fields, or status. Concurrent
enrollment must produce exactly one account/reservation through a uniqueness constraint
and one transaction; the losing operation resolves to the unchanged or conflict branch.

Mutations bind to expected revisions and commit their evidence/receipt atomically.
A failed bundled subject creation leaves no partial account/binding. IDs and historical
subjects must not depend on the phone string. The chosen deterministic/random identifier
scheme and complete unchanged/conflict precedence remain machine-contract requirements.

An observation resolves an account candidate, not an actionable actor. Staging command
attribution additionally requires an active account, active identifier, active subject
and binding, and an active operator-approved staging registration for the observed
source. Missing or conflicting facts produce no command execution and no operator
fallback. During provisional onboarding, the administrator/executor is the actor for
enrollment itself; the provisional user is the enrollment subject, not an authenticated
authorizer of their own grants.

Existing `actor_subject_id` remains a coordination subject ID. New attribution evidence
must distinguish the initiating account/bound subject from the executing agent and its
observed assurance. Where current receipt schemas cannot express that distinction,
publish an explicit extension before claiming durable account-origin evidence.
Existing receipts and historical agent actors are never relabeled as human-authenticated.

## 11. Validation and Non-Disclosure

Account-managed operations validate in this order: bounded input and supported operation;
caller authority for that operation; realm/identifier syntax; current lifecycle and
binding constraints; authorized replay compatibility; expected revisions; atomic write.
Replay disclosure requires current authority and cannot be used as an account lookup oracle.
Suspension blocks user-originated operations, not an administrator's suspension/recovery work.

Exact error codes belong in the machine contract, but outcomes must distinguish, for
authorized operators, invalid identifier, no match, account blocked, binding conflict,
identifier reserved, stale revision, verification required, and capacity exhausted.
Public web entrypoints must not expose those distinctions where they enumerate accounts.
Rate limits must apply to failed lookup, enrollment, and verification as well as success.

Observation source labels are evidence claims with provenance, not inputs that any caller
may freely promote to `verified`. Verification evidence can be accepted only from the
configured authentication component. Staging observation does not bypass this rule.

## 12. First-Party Web Boundary

The intended initial web design is first-party account authentication using established
authentication/session components hosted with the application. It does not require a
separate identity provider, an OAuth authorization server, federation, or a custom
signed-token protocol. Session management and the particular password/passkey/challenge
method are specified with the later web contract, not invented here.

A session binds to a stable account and authentication evidence, not merely to the
phone-number lookup string. Each admitted action resolves the current active subject
binding and current permissions. Authentication identifies the account; it does not
grant access based on chat presence or profile ownership.

Suspension, method revocation, and binding changes must invalidate affected future
session use under the eventual session contract. They never invalidate historical
coordination truth. The selection of local credentials versus a delivered challenge
remains an explicit product decision; the observed WhatsApp ID does not decide it.

This account work does not require changing today's direct CLI into a network client.
The CLI remains a trusted-local administrative path, and the worker remains a trusted
local service. The future web backend calls shared command handlers; routing the CLI
through that backend is a later enforcement decision. Token checks alone cannot constrain
a process that retains unrestricted ledger access.

## 13. Adoption and Boundedness

Existing subjects and schedules do not need accounts retroactively. Adoption proposes
explicit account-to-subject bindings for operator review; it must not sweep subject
names, participant lists, groups, or routes and auto-create login identities. Existing
archetypes, profiles, facets, schedules, and delivery targets keep their domain IDs.

Enrollment, recovery, and identity evidence require configured count/byte/time limits
and retention classification before implementation. Repeated reads or messages must
not append observation records or update a last-seen field on every tick. Enrollment
capacity exhaustion rejects creation instead of growing indefinitely.

Backups, restore, and recovery must preserve realm identity, identifier uniqueness,
binding revisions, and revocation evidence. Restoring an older database/configuration
must not silently restore revoked authentication access. The final recovery contract
must specify the fail-closed reconciliation procedure before serving logins again.

## 14. Acceptance Scenarios

These are future behavioral oracles, not tests already run:

| ID | Expected result |
|---|---|
| ACCT-01 | A subject with no account remains usable for coordination |
| ACCT-02 | Number replacement preserves account, subject, and historical item identities |
| ACCT-03 | Concurrent first-use enrollment creates one provisional account, no automatic group/access grant |
| ACCT-04 | Duplicate enrollment/replay adds no identifier or evidence duplicates |
| ACCT-05 | Provisional, suspended, closed, conflicting, or unbound accounts cannot silently become an actionable staging subject |
| ACCT-06 | Staging activation/registration never upgrades observed metadata to verified authentication |
| ACCT-07 | Group/direct observations of an approved identifier resolve consistently without deriving membership from chat ID |
| ACCT-08 | Web number entry reveals no protected account data and creates no authenticated session |
| ACCT-09 | Proof of a recycled number cannot claim an established account or historical data without recovery review |
| ACCT-10 | Account/method/binding revocation blocks affected new access while leaving prior domain receipts unchanged |
| ACCT-11 | Recovery restores only expressly approved state; revoked identifiers and bindings do not revive automatically |
| ACCT-12 | Failed bundled enrollment leaves no partial subject/account/binding |
| ACCT-13 | Repeated observations/denials and capacity exhaustion meet bounded storage/latency requirements |
| ACCT-14 | Same account using chat and web retains distinct per-request assurance |
| ACCT-15 | Direct CLI operation is described as trusted administration, not verified user authentication |

## 15. Remaining Decisions Before Implementation

Publish account/identifier/binding and attribution schemas, exact operation names and
response/error enums, identifier derivation, transaction placement, normalization rules,
budget values, evidence migration/readback, and provisioning/recovery commands.
These specifications are still required; this logical draft is not implementation-ready.

Product decisions to ratify are optional new-subject creation during enrollment,
operator approval for staging activation/registration, closed-account recovery posture,
and the first web authentication method. Initial account management may be a module
within the application; a separate identity service is not required.

Audit this bounded account contract before implementation. Broader group/resource
authorization and web transport/session details are separate subsequent specs.
