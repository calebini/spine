# RF3 — synchronous mutation-effect propagation

Status: binding increment committed as `0135a68`; ownership increment implemented and verified, uncommitted
(2026-11-13).
This is implementation evidence, not a new normative contract or full RF3 closure.
The authoritative boundary is
[internal application operations §7](../../specs/internal-application-operations.md).
Current scope/status lives in [SPINE-101](../BACKLOG.md#spine-101--rf3-synchronous-mutation-effect-propagation).

## Baseline and preservation

The operator requested committing the verified manual R2 increment, then starting
RF3. The R2 checkpoint is `7f35d68`; R3 automatic scheduling/attempt integration,
public activation, deployment and push are not selected by this increment.

Two unrelated changes were excluded from that commit and remain untouched:

- `AGENTS.md`: SHA-256 `fa4b49c7fcad79cf0e94c70fd5ee4b7dc55ab8c6a3987371577214edbe8e4570`.
- `docs/design-notes/recurring-related-task-r2-restoration.md`: SHA-256
  `3fd7bee35e9834aaa9905aa70c2ed7f45dc8c6a9afccec39fc131bb768e26a76`.

The frozen RF1 catalog, RF2 child composition and explicit R2 amendment witnesses
are not recaptured or rewritten for RF3. Existing receipts, identities, work modes,
audit order and catalog increments must continue matching those witnesses.

## First increment: closed binding inventory

The three native persistence writers remain in `ledger/temporal_bindings.py`:
`insert_temporal_binding`, `insert_temporal_binding_revision`, and
`retire_temporal_binding`. Each now requires an owned transaction and records exact
before/after binding facts in the transaction's propagation component. Header plus
first revision, or successor revision plus retirement, coalesce into one logical
effect before propagation.

| Existing composer | Native writes | Existing consequence now centrally applied |
| --- | --- | --- |
| `commands/temporal_bindings.handle_related_task_create.insert_bundle` | Header + first revision | One binding catalog increment |
| `commands/temporal_bindings._manual_reconcile` | Revision, optional retirement | One increment only when truth changed |
| `commands/temporal_bindings._versioned_reconcile.extension` | Revision, optional retirement | One increment |
| `services/recurring_task_children._create.extension` | Header + first revision | One increment |
| `services/recurring_task_children.change.extension` | Revision, optional retirement | One increment |

`core/mutation_effects.py` defines frozen binding snapshots/effects and proven
`BINDING`/`TIME` categories. A revision or item-version advance alone does not prove
a time change. `ledger/mutation_effects.py` captures exact IDs, versions, revision,
status and temporal facts. Existing bindings use an indexed before-read; successful
native writes project their exact inserted values, coalescing intermediate writes
without rereading them. New header/revision pairs need only one persisted snapshot
read at propagation. The ledger never calls the application layer.
`services/mutation_propagation.py` validates the pending effect against persisted SQL,
applies the existing catalog primitive exactly once, checks its increment and only
then acknowledges the obligation. Effects are private transaction facts, not public
`changed_dimensions`, durable events or an extensible event bus.

The transaction owner checkpoints/restores/resets propagation obligations together
with existing state. Unacknowledged effects fail finalization. No-op/replay paths
produce no new obligation or consequence. Incomplete, stale, duplicate or omitted
propagation fails closed; failure later in the same transaction rolls back both
the binding and its consequence. Neither propagation nor its persistence helpers
commit, dispatch commands, materialize work, schedule repair or send notifications.

## Consequence ownership retained; remaining RF3 work

The new owner does **not** repeat consequences already applied elsewhere:

- `temporal_binding_catalog_related_item_audit` in migration
  `0008_relative_temporal_bindings.sql` advances the binding catalog on relevant
  source/target item audits. It excludes the named binding/related-task audits
  already paired with explicit increments. Ordinary source edits therefore still
  have their own catalog increment, separate from later binding reconciliation.
- `ledger/ownership.advance_ownership_epoch` retains its existing epoch ownership
  and transaction-local once-consumption rule. The ownership increment below
  routes recurring creation through the application owner while retaining explicit
  provisioning's whole-batch reservation.
- `ledger/facets` retains typed-index/continuity checks and finalization, including
  the existing temporary tracking machinery.
- `ledger/rendering_definitions.finalize` retains rendering, presentation and
  catalog consequences. The relative order of recurring, rendering and facet
  finalizers is unchanged.

These are retained owners, **not a claim that every remaining writer has been
inventoried or migrated**. Next RF3 work must close the ordinary item, recurrence,
relation and policy writer/effect inventory, then integrate their
existing consequences through the accepted typed boundary without duplicating
trigger/finalizer behavior. Include lower-level and recurring paths, exact
before/after witnesses and missed-propagation guards. No R3 dirty queue, new
attempt semantics or global eager reconciliation belongs in RF3.

## Verification

- Initial affected binding, recurring child, transaction-state and R2 preservation
  selection: 52 tests passed.
- Focused propagation/state/frozen-witness/dependency selection: 34 tests passed.
- New regressions cover exact categories, catalog cardinality, no-op/replay,
  omitted application propagation and omitted catalog consequence, duplicate
  propagation, nested rollback/retry, later finalizer failure, owned-transaction
  enforcement, context-manager commit checks, and raw commit rejection.
- AST inventories pin all native Python binding SQL writers and their composer
  call counts; dependency checks include the three new modules.
- Seven propagation/persistence/state/child-operation modules pass focused static
  typing. An expanded check including the legacy command module reports 37 typing
  errors; a `--shadow-file` check of the committed `7f35d68` command module confirms
  the same 37 diagnostics (the replaced increment call becomes the propagation
  call). This is retained command-module typing debt, not a clean whole-command
  typing claim or a new RF3 cleanup scope.
- Final focused propagation/dependency/operator-documentation/declaration/web-copy
  selection: 32 tests passed. Focused Ruff, 387 local documentation link targets,
  diff hygiene and preserved-file/frozen-witness hashes pass.
- The first full run found one real regression (1,546 tests, one failure, one
  skipped): redundant snapshot reads pushed delayed-rdate reconciliation beyond
  its unchanged 100,000-instruction budget. Native-value capture now eliminates
  those intermediate reads while preserving the final SQL equality check. No
  budget was increased or disabled. The 24-test edge/propagation/frozen-witness
  selection passes, including the original seven-task case, a one-snapshot-read
  assertion and deliberate captured-value mismatch rollback.
- After that optimization, the 35-test transaction/preservation/documentation/
  declaration/web-copy selection and seven-module static typing pass again.
- Final full suite: **1,548 tests, OK (one skipped)**, 415.285 seconds, using
  `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests`
  and installed pinned Tickerd (no sibling source import). Final focused Ruff,
  typing and diff checks pass. This binding increment is committed as `0135a68`;
  the remaining RF3 inventory/integration above is still open.

## Second increment: item ownership creation

The operator requested committing the first increment and continuing RF3. The
unchanged baseline for this extraction is `0135a68`; the same two unrelated edits
remain excluded. This increment covers **initial item ownership**, not new owner
transfer, access-policy changes, provisioning capabilities or public activation.

| Existing producer | Preserved epoch ownership/order | Preserved entitlement/history |
| --- | --- | --- |
| `services/recurring_task_children._create.extension` | Reserve before header; local bootstrap or configured state; once per outer transaction | No creator entitlement; generation-derived IDs and outer receipt |
| `web/service.WebService.command`, fresh `schedule.create` | Configured-only increment after owner history | Group creator entitlement only; ordinary command receipt |
| `web/people_schedule_service.ProtectedScheduleRendering.persist` | Same configured-only increment before continuing presentation persistence | Same entitlement; successor scheduling receipt |
| `web/provisioning._apply_operation`, `item_adoptions` | Existing whole-batch `apply` advancement, or v3 `prepare_change` pre-reservation | No creator entitlement; provisioning receipt and unchanged operation-path IDs |

All four headers now use `ledger/owner_mutations.insert_item_owner`; all initial
history rows use `record_item_owner_history`. `web/history.record` delegates its
owner case and retains all non-owner cases. These primitives register exact frozen
owner/history facts but never grant authority, choose bootstrap behavior, advance an
epoch or commit. The initial owner revision remains `1`; no transfer operation or
historical rewrite is added. AST checks pin the four callers and the two native
SQL writes, including the explicitly retained provisioning epoch primitive.

The existing `services/mutation_propagation.propagate` entrypoint takes a closed
typed ownership choice: local reserved, configured advancement, or provisioning
batch verification. It verifies exact header/history equality through indexed
identity reads, advances only the configured path, validates the existing epoch
transition and acknowledges the selected obligations. It returns immutable owner
identities/revisions, `OWNERSHIP` classification and before/after epoch evidence.
This is private evidence, never a new wire field or durable event.

Local reservation still calls `ledger/ownership.advance_ownership_epoch` before
the owner insert; the existing `ownership_state` fault boundary is retained.
The once marker now also retains its before/after epoch in the same checkpointed
component. Explicit v3 provisioning initializes that evidence when creating state,
so a composed local writer sees the same consumed epoch. Nested rollback restores
it, and commit/rollback/connection reuse clears it. Configured creation does not
call the local bootstrap primitive: absent or wrong-mode state cannot be repaired.

Legacy provisioning still creates or advances access state at its existing stage;
v3 promotion still keeps the existing ledger/recovery identity and explicit realm
choice. The shared propagation entrypoint verifies adoption consequences only
after the existing batch has established its epoch. It does not increment again
per adopted item. Batches without adoptions, no-op calls and replays add no owner
propagation call.

Retained access writers outside this extraction are explicit: operator, membership,
grant and route-approval changes stay in provisioning; subject/group status and
route-security epoch triggers remain in migration `0013_trusted_web_access.sql`.
Their existing consequence ownership is neither duplicated nor silently bypassed.
Ordinary trusted-local schedule creation remains ownerless unless its current
workflow explicitly creates/adopts ownership. No new account, membership, grant,
route, creator entitlement or notification work is inferred by this extraction.

### Ownership verification

- Initial affected bootstrap/protected scheduling/adoption/recurring edge/witness
  selection: 61 tests passed.
- Focused propagation/state/inventory/bootstrap selection: 58 tests passed.
- Final ownership/binding/edge/frozen-child selection: 36 tests passed, including
  unchanged bounded seven-task reconciliation.
- Eleven new owner regressions plus one exact witness check cover all four
  producers, replay, missing/duplicate propagation, missing history/epoch, incorrect
  captured values, two-owner batches, local promotion, absent-state refusal by the
  configured path, native-writer and context-manager bypass, and nested rollback.
- `rf3_owner_witness.json` was captured from an isolated `git archive 0135a68`
  checkout, not from the modified runtime. Fixed inputs/clocks/ledger identity
  produce six response/whole-ledger digests for configured creation/replay,
  adoption/replay and group people-create/replay. Current bytes match exactly.
  The existing recurring lifecycle witness supplies the local/restoration parity
  evidence without replacing or editing its goldens.
- Final transaction/boundary/operator-documentation/declaration/web-copy selection:
  32 tests passed. Seven affected core/ledger/service modules pass static typing.
  Changed-file Ruff, 388 local documentation link targets and diff hygiene pass;
  both unrelated-file hashes remain unchanged.
- Full regression: **1,560 tests, OK (one skipped)**, 424.062 seconds, using
  `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests`
  and installed pinned Tickerd. This ownership increment is verified but uncommitted;
  no RF3-wide closure or R3 kickoff is claimed.
