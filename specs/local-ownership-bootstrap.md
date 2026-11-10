# Trusted-Local Ownership Bootstrap

Status: Draft v0.1.0 — operator-selected direction; not ratified or implemented
Created: 2026-11-10

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
continues to own generated task/owner/history ordering. This draft proposes a
narrow amendment to their ownership-epoch initialization seam, not a second owner
model, a second epoch authority or activation of a new command family.

Existing implemented declarations, schema versions, source machine contracts and
runtime behavior remain unchanged until this amendment's machine/migration gates
are complete. The current internal recurring-task prototype still fails closed
when access state is absent. Draft acceptance must not be inferred from its tests.

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
with a closed conditional CHECK for the two implemented postures:

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

Use the next unpublished, coherent migration chosen at activation; this draft
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

This draft closes the selected design direction, not runtime R2 or public-family
activation. Its source review/machine contract and the remaining R2 exit tests
must precede replacing the prototype's current fail-closed bootstrap behavior.
