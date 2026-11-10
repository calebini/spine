# Trusted-Local Ownership Bootstrap

Status: Accepted v1.0.0 — ratified design; source-only, not implemented
Created: 2026-11-10
Ratified: 2026-11-10, following the bounded consistency review

## 1. Purpose and authority

An ordinary owned item must be creatable through an authorized trusted-local
command without first configuring web accounts or an identity realm. The operator
selected this direction while implementing recurring related tasks. This leaf
closes the bootstrap dependency; it does not add authentication, change local host
privilege or authorize a web session.

[Permissions](permissions.md) owns resource access. [Storage and atomicity](STORAGE_ATOMICITY_SPEC.md)
owns transactions and migration. [Web admission](permission-enforcement-and-web-admission.md)
and the [trusted web API](trusted-multi-operator-web-api.md) own configured realm
admission and explicit provisioning. The [recurring-task storage leaf](recurring-related-task-storage.md)
continues to own generated task/owner/history ordering. This accepted leaf defines a
narrow amendment to their ownership-epoch initialization seam, not a second owner
model, a second epoch authority or activation of a new command family.

Existing implemented declarations, schema versions, source machine contracts and
runtime behavior remain unchanged until this amendment's machine/migration gates
are complete. The current internal recurring-task prototype still fails closed
when access state is absent. Ratification does not activate its replacement.

## 2. Invariants

- Trusted-local item ownership is coordination truth, not web account enrollment.
- Use the existing `ledger_access_state.access_epoch` as the single canonical
  authorization-relevant epoch. Do not create a competing local owner epoch or
  require two counters to be synchronized.
- An initialized ownership epoch does not mean a web realm, identity posture,
  account, operator, membership, grant or session exists.
- Preserve explicit owner inputs, owner history and no inferred creator
  entitlement. Rule owner, task owner, assignees and delivery destination remain
  independent.
- Only an actual authorized mutation can bootstrap or advance state. Reads,
  preflight, planning, replay and idle reconciliation cannot initialize it.
- Bootstrap, item/owner/history, policies/work, audit and the real outer receipt
  commit together or roll back together. No bootstrap subcommand or sub-receipt.
- Never synthesize an identity realm from a group name, actor, channel, recipient,
  environment variable or sentinel string such as `local`.

## 3. One existing state table, two explicit postures

Retain `ledger_access_state`, its singleton key, `ledger_id`, `access_epoch` and
`recovery_epoch`. The migration must allow nullable `realm_id` and `identity_mode`,
with a closed conditional CHECK for the two accepted postures:

| Stored posture | `mode` | `realm_id` | `identity_mode` |
| --- | --- | --- | --- |
| Local ownership initialized; web not configured | `trusted_local` | SQL NULL | SQL NULL |
| Explicit trusted multi-operator web configuration | `multi_user` | Existing explicit nonempty realm ID | `trusted_identity` |

This is storage/admission posture, not a caller-selectable authorization mode.
The local row cannot be interpreted as a full-scope web operator or a trusted
human identity. Proposed verified-identity/single-operator modes in other drafts
are not activated by widening this table. Any future posture requires its own
accepted contract, migration and tests.

Keep one row at `singleton_id=1`, unique nonempty `ledger_id`, and signed-64-bit
positive epochs. New local bootstrap starts both epochs at `1`; the initial
`access_epoch` represents the first committing owner mutation (not an extra
observation increment). `recovery_epoch` has no web recovery/admission meaning
while no realm exists. Preserve every already-configured field/counter byte for
byte at migration; no mode switch, number reset or account backfill.

For a new local row, set `ledger_id` to the already-persisted
`spine.ledger-instance.v1` `ledger_instance_id`, validated through its owning
read-only identity contract. Do not generate another identity or scan ledger
contents to derive one. An existing configured `ledger_id` may differ from that
instance ID and remains unchanged. The physical instance ID continues to bind
cursors independently; the two fields are not retroactively equated.

An invalid existing row or invalid/missing instance metadata fails closed. Missing
access state is the sole bootstrap case, not permission to repair corrupt state.

## 4. Internal mutation boundary

Provide one internal ownership-state primitive used under the existing owning
`BEGIN IMMEDIATE`, after compatible command replay and before inserting the first
new owner header. Its inputs are protected command context and already-validated
explicit ownership, not model-authored realm/bootstrap flags.

If access state is absent, the first eligible owner mutation inserts the exact
local row from Section 3. If state exists in either supported posture, retain its
identity/posture and advance `access_epoch` exactly once for the whole committing
transaction, regardless of the number of owner rows. Check overflow before writes.
The initial insert counts as that transaction's one advance from uninitialized
state; do not insert at `1` and then increment to `2` for the same transaction.

This transaction-local once marker must participate in rollback, including the
recurring-task engine's bounded unit savepoints. If a proposed task cannot fit
and its unit is rolled back, neither bootstrap state nor its once marker survives
unless an earlier accepted unit already created ownership in that transaction.
No-op/replay consumes no epoch; a dry-run can report would-be evidence but leaves
no row or counter change. No helper commits independently.

The actual generated owner/history rules are unchanged: configured subject/group,
matching FK, immutable owner ID, revision `1`, null creator entitlement and real
outer actor/receipt. Validate those references under the writer lock. Bootstrap
does not grant disclosure approval or validate a route by itself.

Routine checks read the singleton and instance identity by bounded indexed keys.
No owner/history scan, `integrity_check`, `foreign_key_check` or read-time repair
belongs in bootstrap. Existing historical records are neither adopted nor rewritten.
The epoch starts tracking subsequent canonical mutations; it does not certify
that earlier unconfigured history was permissioned.

## 5. Explicit later web configuration

`web_access.plan`/`web_access.apply` remain the explicit configuration authority.
Their successor implementation must distinguish absent state, local initialized
state and already-configured state. Planning a local-to-web transition is read-only
and must carry the current `expected_access_epoch`, retained `ledger_id`, explicit
realm and the ordinary operator/provisioning inputs. An already-initialized local
ledger cannot be assigned a different logical ledger identity during promotion.

Applying an approved, fresh plan can atomically promote `trusted_local` to
`multi_user` with the explicit realm and `trusted_identity`, alongside its
authorized provisioning operations. Existing eligible-operator and no-lockout
rules still apply. This is one epoch advance, not a counter reset. The local
bootstrap alone does not satisfy those rules or implicitly select an operator.

Existing configured deployments retain their current provisioning/replay behavior.
No automatic downgrade, realm replacement, operator selection or grant inference
is added. A local bootstrap race versus web provisioning serializes under the
same canonical writer transaction: the loser replans against the changed epoch.

Protected service admission must refuse an unconfigured/local posture even if a
caller names a subject/account or presents stale realm evidence. Health, preflight
and configuration diagnostics may identify it as not configured; they must not
mint a session or silently fall back to unrestricted local permissions. Existing
trusted-local CLI privileges remain outside that service admission boundary.

Do not extend frozen web/system-info wire enums implicitly. Before implementation,
close any required successor response/admission schemas and fixtures, or retain
their existing not-configured refusal shape. Do not return `trusted_local` in a
field whose implemented contract permits only web modes.

## 6. Migration and compatibility

Use the next unpublished, coherent migration chosen at activation; this leaf
allocates no schema number. It may be folded into an unactivated candidate only
with updated manifests/tests and deliberate recreation of disposable old candidates.
Do not silently reinterpret an already-deployed schema marker or weaken old-writer
newer-schema refusal.

Widen only the necessary existing state-column nullability and conditional CHECKs,
retaining table/column names and existing FK targets. Verify the actual ordered
copy/rebuild path against referencing account-subject bindings and other indexes/
triggers. Migration is atomic; incompatible/corrupt facts abort it. Preserve
existing configured rows, accounts, bindings, owners, memberships, grants, routes,
receipts and immutable history. Unconfigured ledgers remain row-absent until an
actual authorized ownership mutation. No deployment-specific data belongs here.

Rollback before commit restores the predecessor schema/data. After release
activation, preserve ordinary newer-schema refusal and explicit approved backup
restore policy; there is no destructive automatic down migration. Do not create
a maintenance fork or require running a web service merely to schedule local tasks.

## 7. Required machine contracts and fixtures

Before implementing/activating this amendment, close the exact internal state
union, bounded failure mapping, migration manifest, once-per-transaction behavior
and any provisioning/admission successor wire impacts. Keep existing public
responses unchanged where no successor is needed. No bootstrap secret, login
token, external identity provider or new public bootstrap command is required.

Required computed/actual cases include:

1. Empty access state plus existing instance identity: one owned task commits
   local state/epoch `1`, owner/history and outer receipt, with zero realm/accounts/
   operators/memberships/grants created.
2. Several tasks in one page: one initial epoch; later owner-creating pages advance
   once, while no-op/read/replay leave it unchanged.
3. Dry-run and failures after bootstrap, owner, presentation, work, audit and receipt:
   no residue. A rolled-back last unit restores SQL and the transaction-local marker.
4. Existing configured realm: identical identity/configuration/authorization after
   migration and one normal epoch increment on owner mutation.
5. Explicit promotion from local state: exact existing ledger ID and expected
   epoch; no inferred operator/grant, and stale plans/replays have defined behavior.
6. Protected admission refuses local posture; no frozen response emits an
   unsupported mode. No raw CLI trust is reinterpreted as a browser session.
7. Concurrent first owner creators and provisioning interleavings: one singleton,
   monotone epochs, no lost invalidation, no half-configured realm.
8. Missing/malformed instance metadata, corrupt state, overflow, migration/FK/object
   drift and old-writer refusal: fail closed without full-ledger routine scans.

Ratification closes the selected design direction, not runtime R2 or public-family
activation. The new machine package below is a source-only candidate, not a claim
that migration, locking, savepoint or admission tests have executed against it.

## 8. Machine package and exact representations

[local-ownership-bootstrap.v1.json](../contracts/local-ownership-bootstrap.v1.json)
indexes the source-only candidate, its schemas, migration contract and required
runtime obligations. The [fixture manifest](../contracts/local-ownership-bootstrap-fixture-manifest.json)
separates positive/negative wire examples from finite transition witnesses.
Schemas live in `contracts/schemas/local-ownership-bootstrap/`; they are not
copied into the frozen web package or added to implemented declarations yet.
The accepted Sections 1–7 own product policy; Sections 8–11 close its proposed
machine representation pending review. No extra approval, executor or login model
is introduced.

`spine.ownership-access-state.v1` is an internal projection, not a new command:
`{contract_version,state}`, where `state` is null for row-absent or the complete
seven-column row. All seven fields are required; SQL integers project as canonical
unpadded decimal strings, SQL NULL as JSON null. `singleton_id` is `"1"`;
epochs are in `1..9223372036854775807`. No float, boolean, empty string, sentinel
realm or partially configured row is valid. The two posture branches are closed.
Existing configured logical ledger IDs are preserved; only a new local row must
equal the valid existing physical instance ID. Canonical JSON is
`spine.canonical-json.v1`, without Unicode normalization or omitted nulls.

Only an owner-creating trusted-local transaction may call the internal primitive.
Validate actor, explicit owner references and command semantics using the owning
command's precedence, resolve compatible replay, then validate identity/state and
reserve the one epoch advance before writing an owner header. Failure rolls back
the entire outer command. The primitive must not grant web privilege or be called
from protected admission to repair missing state. The enclosing command's access
finalizer and this primitive share the same transaction-owned once marker whenever
they compose: a page cannot increment again because both observe its new owners.
This does not silently replace unrelated standalone access writers or their
existing subject/group/route-security triggers. Existing configured-only commands
remain configured-only until their deliberately integrated successor is enabled.

The marker records whether this outer transaction has already consumed its one
advance. At each unit savepoint capture both state and marker; rollback restores
both, release keeps both, outer rollback or dry-run discards both. A compatible
replay/no-op/read is not an owner mutation, even if it returns an earlier changed
receipt. At the maximum epoch a fresh owner mutation fails before any write;
a replay/no-op at that value remains valid. A writer serializes via BEGIN IMMEDIATE,
rereads current state after acquiring the lock, and never performs an unchecked
read-increment-write from a prior snapshot.

## 9. Explicit provisioning successor and unchanged admission

The proposed `spine.trusted-web-provisioning.v3` is trusted-local only. It retains
the two existing command names and v2 operation definitions, normalization, bounds,
reference checks, registered row-ID derivations, audit and receipt ownership.
It does not enter the HTTP command registry. V1/v2 wire shapes and hashes remain
frozen; they cannot promote local state and return `admission_unavailable` for it.
Existing configured v1/v2 requests/replays keep their existing interpretation.

V3 plan adds a required explicit `realm_id` to the request (no environment/default
substitution), and a required `access_state_before` row-or-null to the response.
All operation arrays are materialized and sorted by canonical bytes just as in v2;
total operations and references remain at most 100 and eligible operators at most
32. For absent state, expected epoch is `"0"`; the supplied nonempty ledger ID
becomes the explicitly configured logical namespace. For local state, ledger ID
must equal the existing row and expected epoch must equal its current epoch.
For configured state, ledger and realm must both match. No caller-selected identity
mode, recovery epoch, implicit account, or grant is accepted.

The resulting configured state must retain at least one active eligible operator
with an active account and matching active subject binding in the selected realm.
This is the existing eligible-operator/no-lockout policy, not full-scope authority.
A plan that fails it has `can_apply=false`, conflict
`eligible_operator_required`, `operation_path=/operators`. Other operation conflicts
retain v2 codes/paths. Plans never mutate. Local posture alone supplies no operator.

V3 `plan_hash` is SHA-256 of canonical JSON of exactly
`{contract_version,access_state_before,normalized_plan,references}`. The version is
`spine.trusted-web-provisioning.v3`; `normalized_plan` includes explicit realm and
all five arrays. References retain v2 ordering and state-hash preimages. A state
posture, ledger, realm, epoch or recovery change invalidates a fresh apply, even
when the requested operation arrays are identical. This does not hash whole history.

Apply carries the complete plan and the ordinary command/actor/time/expected-epoch
fields. Its semantic hash preimage is exactly the existing apply fields
`{contract_version,actor_subject_id,action_timestamp_utc,expected_access_epoch,
normalized_plan,plan_hash,realm_id}`, with realm taken from the explicit plan.
It excludes command ID and observed execution-time state. Replay lookup follows
actor validation but precedes current epoch/state comparison; an exact stored replay
returns the original response plus `replayed=true`, creates nothing and never
re-promotes a realm. An incompatible command ID fails `command_id_unavailable`.
No other caller may interpret a v1/v2 receipt under v3.

For fresh apply: validate state/identity, check ledger and realm, then expected epoch;
recompute plan under the writer lock and compare its full state witness, references
and hash before mutation. Explicit promotion changes only realm/mode/identity_mode
and the one transaction epoch advance; it retains ledger ID and recovery epoch.
Absent-state web provisioning starts at epoch 1. Configured no-op stays at the same
epoch, but retains ordinary explicit-command audit/receipt semantics. Promotion is
a change even with zero item adoptions; all authorized operations and the single
outer receipt commit together. Result schemas reuse v2 fields with the v3 version
constant; no extra transition receipt or account history is invented.

Protected web readiness, chooser, reads and writes continue to require configured
`multi_user/trusted_identity`, exact configured ledger and realm. Local or absent
state yields `admission_unavailable` (HTTP 503), including before account selection.
Do not return local mode in any frozen web or system-info enum. Public failures
contain no state witness, private IDs or inferred operator. No new public health
shape or authentication claim is required for this change.

## 10. Failure mapping and migration contract

After the owning command's shape/actor/replay gates, check existing bounded schema
and instance-identity admission, then the single state row, then overflow only if
a real advance is needed. Missing state is eligible only for the internal owner
mutation or explicit web provisioning. Multiple/malformed states are never repaired.
For recurring-task owner creation, invalid state or overflow maps to the existing
`environment_failure`, `field=ownership`, CLI exit 7; invalid instance metadata
retains the earlier identity-preflight failure. No new recurring-task wire enum.
Local provisioning keeps its existing local failure envelope. V3 state/identity
failure and ledger/realm mismatch map to `admission_unavailable`; stale expected
epoch to `access_changed`; changed plan witness/references/hash or non-applicable
plan to `domain_conflict`. V3 overflow maps to `admission_unavailable` only when
the fresh change/promotion requires an advance; configured no-op/replay at the
maximum epoch retains it. No failure writes audit/receipt/bootstrap residue.
Schema/object failure precedes row decoding; no-op/replay does not certify corruption
or bypass ordinary startup admission. Busy/timeout retains the owning command's
existing mapping and transaction rollback. JSON Schema error iteration is not
command validation precedence.

[The migration contract](../contracts/local-ownership-bootstrap-migration.v1.json)
defines the exact successor state DDL and unchanged referencing objects. It is not
an executable migration or an assigned schema number. Migration must validate the
predecessor object manifest, valid row count/values and instance metadata, then
rebuild the parent table without changing any FK target to a temporary name:

1. With writers stopped and no transaction open, record connection FK enforcement,
   disable it only on this explicit migration connection, then BEGIN IMMEDIATE.
2. Create the specified temporary successor table, copy the seven columns by name,
   preserving configured rows byte-for-byte; an empty table stays empty. Invalid
   rows abort rather than being normalized or backfilled.
3. Temporarily drop the three manifest-owned subject/group/route-security triggers
   that reference the parent (preserve their validated SQL verbatim). Drop the old
   parent and rename the replacement to `ledger_access_state` without first
   renaming the old parent. Recreate those triggers verbatim after rename, so
   SQLite never validates their SQL against a missing parent during ALTER TABLE.
   Referencing account bindings keep their canonical
   FK target; do not cascade/delete/reinsert them. Recreate any manifest-owned
   dependent object affected by the rebuild; reject unsupported extra dependent
   objects rather than guessing how to rewrite them. Unrelated extra objects remain
   untouched. Validate all names/types/definition
   fingerprints and absence of temporary artifacts against the successor manifest.
4. Explicit migration-only full FK verification, instance validation and deep
   verification must pass before committing the schema/history change. Existing
   triggers/indexes and every unrelated canonical/history row remain unchanged.
5. Rollback on any error and restore FK enforcement in finally, then verify it is
   ON before returning a usable writer connection. It is never disabled in routine
   commands, worker startup or the ownership primitive. Runtime preflight uses only
   indexed singleton/metadata lookups and fixed object-manifest checks.

The implementation must choose a coherent unpublished migration boundary and
publish exact object fingerprints then. It may fold this into candidate 20 only
if that candidate remains unactivated and disposable candidates are deliberately
recreated. Do not modify published migration 13 or the current schema-19 manifests.
Fresh initialization and the rebuilt table must produce byte-identical
`sqlite_schema.sql` and hence the same exact UTF-8 DDL fingerprints (including
SQLite's quoting after rename), not merely logically equivalent constraints.
After activation, old writers refuse the newer schema; binary rollback alone is
not data rollback, and no automatic down-migration is defined.

## 11. Verification and implementation gates

Offline witnesses prove only representation, finite epoch arithmetic, normalization,
preimages and expected branch selection. The fixture manifest enumerates pending
actual SQL obligations: both posture migrations with real account bindings,
fault-injected rebuild/outer/savepoint rollback, configured preservation, explicit
promotion and no-lockout, replay and no-op, old-writer refusal, bounded routine SQL,
and physical two-connection first-owner/provisioning races. Each needs real
implementation evidence; the wire corpus cannot close them.

Before activation publish packaged state/provisioning schemas and matching compiled
contract requirements, coherent DDL/object fingerprints, actual runtime tests and
all remaining R2 gates. The source-only v3 and internal state identifiers must not
appear in implemented versions merely because offline tests pass. No public
bootstrap command, service requirement, sending authorization or R3/R4 activation.
