# RF3 — synchronous mutation-effect propagation

Status: RF3 complete; bindings committed as `0135a68`, ownership as `a4b3790`, relations/recurrence as `5a212a6`; final item/policy increment committed as `7e3983d`
(2026-11-13).
This is implementation evidence, not a new normative contract. Earlier sections
record incremental checkpoints; the fifth increment below closes IO-07/08 and RF3.
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

## Consequence ownership retained; remaining work at the first checkpoint

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
  and installed pinned Tickerd. This ownership increment is committed as `a4b3790`;
  no RF3-wide closure or R3 kickoff is claimed.

## Third increment: relation creation

The ownership checkpoint is `a4b3790`. This extraction covers the one native
Python relation INSERT and all three production composers:

| Composer | Existing write/audit ownership | Propagation placement |
| --- | --- | --- |
| `commands/core._handle_relation_create` | Explicit relation identity and `relation_created` audit/receipt | After the existing audit, before receipt |
| `commands/temporal_bindings.handle_related_task_create.insert_bundle` | Derived `part_of` row and outer related-task audit/receipt | After relation insertion, before the existing relation fault checkpoint |
| `services/recurring_task_children._create.extension` | Generation-derived `part_of` row and outer child/page evidence | After relation insertion, before binding insertion |

`RelationSnapshot` captures all eight stored fields, including raw nullable metadata;
`RelationMutation` reports only the proven `RELATION` category and an absent
predecessor. Relations have no version counter. This does not imply a time, lifecycle,
people, owner or policy change. There are no production Python relation UPDATE or
DELETE writers in this inventory; no new status-change API is introduced.

`ledger/relations.create_item_relation` retains validation, allocation, SQL and
error mapping. When composed in an outer command transaction (including with the
helper's default `manage_transaction=True`), or when passed `manage_transaction=False`,
it records a pending relation effect. The application propagation owner verifies
that effect against one indexed identity read and acknowledges it. Omitted,
duplicate or mismatched propagation aborts the whole operation. Pending relations
participate in the existing checkpoint/restore/reset/finalization component and
plain-context commit guard.

The exported helper's **standalone local-transaction path is intentionally retained**
under Section 6 of the internal operations contract. It performs its existing
local commit without importing services or requiring an application caller. This
is not an escape for composed callers: the actual outer-transaction state takes
precedence over the helper's default flag. Tests pin both behaviors. Moving that
standalone API to an application facade would be a separate selected migration,
not an inverted ledger-to-service import in this refactor.

Existing consequences remain explicit:

- SQLite retains foreign keys, active uniqueness and source/target indexes.
- The existing `temporal_binding_catalog_related_item_audit` trigger conditionally
  increments the catalog for the direct command's audit when its source participates
  in an active binding. The propagation service adds no relation catalog increment.
- Composite binding creation retains its separately owned explicit catalog advance;
  existing child/item audits retain their current trigger behavior and ordering.
- Relation-derived reads remain queries, not new persisted projections. Work and
  attempt freshness are unchanged; there is no eager reconcile or notification send.

### Relation verification

- Initial affected selection: 61 tests passed (exact relation/owner/child witnesses,
  binding/ownership/state tests, standalone helpers and bounded recurring edges).
- New regression/dependency selection: 51 tests passed. Ten new tests cover exact
  classification, replay, conditional audit-trigger cardinality, all three missing
  propagation paths, helper-default bypass, standalone behavior, duplicate and
  mismatched evidence, nested rollback/retry, later finalizer failure, raw commit,
  plain-context finalization and closed SQL/caller inventories.
- Six exact response/whole-ledger witnesses were captured from an isolated
  `git archive a4b3790` checkout before runtime edits. Direct creation/replay,
  related creation/replay and direct creation/replay on a bound source match the
  checkpoint, including receipt/audit bytes and existing catalog increments.
  Earlier frozen witnesses are unchanged. The new fixture SHA-256 is
  `1f40aad65129be8b8d7c5318edc83fdb1125ba90b086e8aa03ee3ef850b1d0eb`.
- Six affected core/ledger/service modules pass focused static typing. Changed-file
  Ruff and diff hygiene pass. The 21-test dependency/documentation/declaration/web
  synchronization selection passes, and 388 local documentation links resolve.
  Both unrelated files retain their original hashes.
- Full regression: **1,571 tests, OK (one skipped)**, 410.083 seconds, using
  `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests`
  with installed pinned Tickerd. No public contract/schema, migration, activation,
  live ledger, deployment or push is involved. This relation increment remains
  uncommitted. Remaining item/recurrence/policy integration keeps RF3 open.

## Fourth increment: recurrence aggregates and lineage

The operator selected continuing RF3 without a commit. The preceding relation
increment and both unrelated edits are preserved. `a4b3790` is the committed
pre-recurrence baseline; the separate relation witnesses still match it.

| Existing composer in `commands/core.py` | Existing recurrence write |
| --- | --- |
| `_handle_schedule_create.insert_schedule_bundle` | Initial schedule recurrence |
| `_handle_schedule_update.persist_bundle` | New/replacement recurrence, with lineage when replacing |
| `_handle_event_reschedule.insert_extension` | Initial recurrence attached during reschedule |
| `_handle_recurrence_instance_mutation.insert_revision` | Direct instance mutation successor and lineage |
| `_persist_series_edit_success.insert_revision` | Direct series-edit successor and lineage |
| `_recurrence_insert_callback.insert` | Initial event/task command recurrence |

The lexical names above were checked against the actual writer inventory.
There are six aggregate and three lineage calls, all in the command
adapter. The nine aggregate/lineage table INSERTs remain in `ledger/recurrence.py`;
there are no production UPDATE/DELETE writers for these tables. Target-selector
storage remains shared immutable persistence, not a new recurrence revision writer.

`RecurrenceSnapshot` pins exact set/revision, source identity/version, predecessor,
normalized hash, command and timestamp. `RecurrenceMutation` includes the exact
predecessor header where present, immutable definition bytes and typed lineage
rows. It proves only `RECURRENCE`: revision/hash changes do not by themselves
prove a time, lifecycle, people or policy change. The private comparison bytes
do not replace any public canonical preimage, identity or hash.

Native insertion records the aggregate obligation, then lineage insertion adds
the exact rows. The shared application propagation entrypoint verifies the header,
decoded full aggregate and supplied lineage through indexed revision/lineage reads,
and acknowledges only complete matching evidence. It does not scan historical
revisions or resolve the current item pointer. The existing decoder is shared with
an exact-revision read so successor verification works inside the allocator's
extension **before** the current-pointer CAS. Independent child collection order
is normalized solely for private comparison; selector order and nested null patch
values remain significant. Missing or duplicate propagation, incomplete aggregates,
missing successor lineage or changed lineage fail the owning transaction.

No catalog increment, policy/work invalidation, audit, receipt, materialization or
dirty queue is added. Existing item audits/SQL triggers and rendering/facet finalizers
retain their consequence ownership and ordering. All six adapters propagate at
their existing persistence stage. Two test-only native source composers now call
that same propagation step; their expected responses and historical golden files
are unchanged. The native recurrence helper already requires an owning item
transaction and has no standalone local-commit exception.

### Preservation findings and verification

- The first affected selection ran 65 tests and found one instruction-budget
  failure: delayed-rdate seven-child reconciliation interrupted at the unchanged
  100,000-step boundary. A disposable diagnostic comparison isolated a single
  100-instruction accounting step of headroom; no production limit was changed.
- Redundant owner/header-history equality predicates were moved from SQL to an
  exact Python comparison of **both complete rows**. The same identity/revision
  join and every captured-field equality remain required. A new fault-injection
  regression inserts mismatched history before its immutable boundary and proves
  rollback. A redundant new recurrence header read was also removed.
- The original delayed-rdate case passes with its real budget enforcement intact
  (observed create/read/reconcile/replay counters: 900, 600, 100000, 12100). It remains
  close to the existing limit; this is not a new capacity guarantee or permission
  to increase limits. Thirteen affected owner/budget tests passed after optimization.
- Seven new recurrence regressions cover exact before/after revisions and lineage,
  prospective pointer ordering, all six composer omission paths, creation replay,
  no-op suppression, child/selector/lineage mismatch, native omission/duplicate
  propagation, nested rollback/retry and closed SQL/caller inventories.
- One new witness captures 17 public command/read observations across instance
  add/remove/override, whole-series edit, COUNT-bounded split and initial recurrence
  attachment. Exact response and whole-ledger digests were obtained from an isolated
  `git archive a4b3790` checkout before the runtime extraction, not regenerated from
  the modified runtime. They pass unchanged. Fixture SHA-256:
  `c74aa98ed523d1ad41d4afeed4c37a250d686d60d1dcec4c0f0a467d2f8b122b`.
- **Pre-existing defect, outside this refactor:** after a successful direct
  `recurrence.instance.add`, submitting the identical request returns
  `semantic_conflict`, field `command_id`, message `command_id replay facts do not
  match`. This was reproduced independently on `a4b3790` and the working tree.
  The new preservation test pins that existing rejection and its zero-write behavior;
  it does not claim successful direct-add replay. Repair requires separately scoped
  command-contract work. Ordinary event-create replay remains successful and inert.
- Final focused recurrence/owner-fault/dependency/transaction/declaration/docs/web-sync
  selection: 41 tests passed. Seven affected modules pass static typing. Changed-file
  Ruff, all 388 local tracking-document links and diff hygiene pass. Both unrelated
  files retain their original hashes.
- Full regression: **1,580 tests, OK (one skipped)**, 446.138 seconds, using
  `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests`
  with installed pinned Tickerd. No public contract/schema, migration, activation,
  live ledger, deployment, commit or push is involved. This is not RF3 closure;
  item/policy work remains.

## Fifth increment: item and policy application boundary

The operator committed the relation/recurrence checkpoint as `5a212a6` and selected
the remaining item/policy work to close RF3. R3 remains unselected. The same two
unrelated files retain their recorded hashes and were excluded from the commit.

### Closed writer and consequence inventory

The existing machine inventory, `src/spine/ledger/facet_writer_inventory.v1.json`,
continues to name every item-version allocation caller; its AST and real SQLite
writer matrices remain unchanged. The following inventory adds the application
acknowledgement and retained consequence owners, not new public producers:

| Native writer | Application owner / callers | Existing consequences retained |
| --- | --- | --- |
| `ledger/items._create_item_v1` | Closed `services/item_mutations` event/task adapters; ordinary command and single/recurring related-task creation | Version/detail/supporting-set writes, allocator audit, facet snapshot/index, item-audit catalog triggers |
| `ledger/items.create_item_version_from_draft` | Same service adapters for ordinary update, reschedule, lifecycle, recurrence edits, direct policy commands, facets and recurring change/restore; `services/people_authoring.replace_people` acknowledges the existing ledger people composer | Existing copy/replace/clear choices, CAS, audit, people/facet continuity checks, policy/application/presentation history and explicit work mode |
| `ledger/items.archive_item` | Closed archive adapter | Shell-only lifecycle write and unchanged audit/trigger behavior; no version or policy allocation |
| `ledger/notifications.insert_notification_schedule_policy` | The owning item application, including copy-forward, direct policy authoring, ordinary related creation, recurring creation/restoration/adoption | Schedule/selector rows, staged exact presentation and existing rendering finalizer |
| `ledger/notifications.remove_copied_notification_policy` | The same item application before replacement | Deletes only its still-pending copied successor and discards that transient effect; the final replacement remains required |

All item SQL remains in `ledger/items.py`: three shell writes, one version INSERT,
two event-detail INSERTs and two task-detail INSERTs. Both policy INSERT/DELETE
statements remain in `ledger/notifications.py`. The eight application allocator
adapters form a closed, typed set; they preserve each existing callable signature,
result and failure mapping. They do not normalize requests or accept a new universal
mutation payload. The separate people adapter calls the existing ledger composer
and acknowledges only changed results, preserving no-op admission and receipts.

`ItemSnapshot` captures exact item/type/version/shell/detail and metadata facts.
The allocator records `ItemMutation` only after its existing CAS, audit and
cross-row invariant checks succeed. Native writes and those existing checks remain
the persistence proof owner; propagation does not duplicate their history scans.
Predecessor detail and role facts reuse existing reads. Explicit facet replacement
also decodes the predecessor snapshot; unchanged copies reuse the ordinary read.
People effects retain the opposite role and distinguish explicit empty clears.
Facet facts preserve exact schema/binding/history/value pins. Shell archive records
supporting facts as unaffected (`None`), not as fabricated empty snapshots.

Categories distinguish item allocation from actual lifecycle, temporal-reference,
people and facet changes. A new version alone proves none of the latter. This is
not a replacement for public `changed_dimensions` or recurrence time resolution.
Policy effects retain exact new/source policy IDs, item version, normalized
definition bytes and source/selected presentation bytes. `POLICIES` describes the
immutable row write (including copy-forward), not a claim that reminder semantics
changed. `PRESENTATIONS` is proven only by differing selections. Ordinary title
copy therefore does not masquerade as a presentation edit, and existing exclusive
presentation-only public responses are untouched.

The one `services/mutation_propagation.propagate` entrypoint consumes a complete
item plus its final policy set at the application return boundary. A copied policy
removed and replaced within the allocator extension is never reported as a final
successor. Policies for another item version, duplicate acknowledgement, missing
item acknowledgement or orphaned composed policy obligations fail closed.
The transaction's existing checkpoint/reset/finalization registration includes
both new dictionaries; rollback restores them alongside SQL.

### Explicit retained exceptions and preservation

- Standalone ledger item helpers still own their local transaction under §6. They
  finish their native item/policy obligations only on that local path, after the
  same allocator checks; composed calls cannot take this exception. The application
  adapters require an already-owned transaction and never commit. Standalone
  historical policy fixture authoring retains its checked local context and
  rendering finalizer; composed policy insertion requires item acknowledgement.
- `ledger/people_authoring.replace_people` retains its lower-level continuity proof
  and allocator composition; its service adapter is the propagation owner. No
  ledger-to-service dependency was added. Test-only composed native writers were
  updated to call that boundary; their domain expectations and golden artifacts
  were not relaxed.
- `ledger/rendering_definitions.finalize`, `ledger/facets.finalize`, existing
  allocator invariants, people/facet continuity decoders and persistent audit/access
  triggers retain their current proof/index/epoch/catalog ownership. The propagation
  seam acknowledges their ownership, not duplicates it. Catalog authoring for
  profiles, archetypes, definitions, disclosure and access provisioning remains
  under these named existing owners; it is not new scheduling mutation machinery.
- Work creation, stale-only reconciliation, current attempt admission, prior attempt
  replay, dry-run and all resource limits are unchanged. No R3 dirty queue, automatic
  generation, scheduler integration, public activation or deployment is included.

### Verification

- Initial recurrence/notification/schedule selection: 28 tests exposed two test-only
  native-composition omissions after correcting private native integer encoding.
  Updating those composers, not relaxing finalization, produced a passing 44-test
  lifecycle/budget/witness/dependency selection.
- A first full run against the initial extraction reported 1,580 tests, three
  failures, 39 errors and one skip. Failures were composed test-helper omissions,
  standalone historical-policy fixture ownership and ownership-only observers
  assuming all propagation results were ownership effects. Each was narrowed to
  its actual family/application boundary; expected SQL, response and work facts
  remain unchanged. One separate focused invocation needed the existing `tests`
  import path; no runtime workaround was added for that harness requirement.
- The final supporting-fact selection passes 47 tests, including the real facet and
  people writer matrices and the unchanged delayed-rdate instruction budget. A
  32-test new-regression/witness/transaction/dependency selection passes, plus the
  additional composed-policy omission/standalone test. Nine affected modules pass
  focused typing; changed-file Ruff and diff hygiene pass.
- Fourteen new propagation tests cover precise classification, opposite-role
  preservation/clears, facet-only and presentation-only edits, copy/replacement,
  no-op/replay, omission, duplicate consumption, policy-version mismatch, nested
  rollback/retry, late finalizer failure, standalone exceptions and closed writer
  inventory. The separate new witness compares 15 public envelopes and whole-ledger
  digests against a disposable `git archive 5a212a6` checkout, covering materializing
  replacement/replay, protected cancellation/replay, preview/commit and cursor
  invalidation. The fixture SHA-256 is
  `70293bfd6b47e1d052e518fd1fc3281b6b5173dcef212708f43dc794a8f96702`.
- The subsequent full run found two failures (1,594 tests, one skip): the same
  missing-staged-presentation test inherited by two rendering test classes.
  Evidence capture had raised `KeyError` before the existing rendering invariant,
  incorrectly mapping the failure to `invalid_request`. Explicit invariant guards
  now preserve `environment_failure:rendering` at both capture and propagation.
  A new fault-injection test removes staged presentation evidence between those
  boundaries and proves whole-ledger and transaction-state rollback. All 17 focused
  item/policy/witness and both inherited regression cases pass; a fresh complete
  run follows this correction. No expected response or golden was changed.
- Final full regression: **1,595 tests in 426.649 seconds, OK (one skipped)**.
  Nine-module typing, changed-file Ruff, 32 documentation/declaration/web-copy/
  transaction/dependency tests, 388 local links and diff hygiene pass. Both unrelated
  files and the frozen witness retain their recorded SHA-256 values. IO-07/08 and
  RF3 are closed; the final item/policy increment was subsequently committed as
  `7e3983d`. R3 was unselected at this checkpoint and is now separately tracked
  under SPINE-094. No push, migration, public activation, deployment or external
  sending occurred.
