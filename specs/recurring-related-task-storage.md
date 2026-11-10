# Recurring Related Tasks: Storage, Identity and Lineage

Status: Accepted v1.0.0 — ratified physical contract; not implemented

Ratified: 2026-11-09

## 1. Authority and chosen layout

[Recurring related tasks](recurring-related-tasks.md) owns product semantics and
D-01–05. [Storage and atomicity](STORAGE_ATOMICITY_SPEC.md) owns Spine-wide
transactions, migration and admission. This leaf owns only this family's physical
records, identities, source-continuity proofs and access paths. The
[command companion](recurring-related-task-commands.md) owns wire shapes,
limits, effects, clocks and pagination. No schema number or runtime registration
is allocated by ratification of these source contracts.

Use a **relational header/history layout with canonical JSON payloads**. Relational
keys enforce reservations, generations, current pointers and source/target joins;
immutable canonical payloads retain exact configuration and proof bytes. A receipt
is not the storage owner for assignments. Reject a single JSON rule-with-all-tasks
blob (unbounded rewrite and no per-slot uniqueness), generic EAV (weak domain
constraints and excessive joins), and a parallel task store (competing task truth).
Existing items, relations, bindings, policies, work and attempts keep their tables.

## 2. Representation and identity registry

All hashed/wire payloads use `spine.canonical-json.v1` exactly as defined by the
[ontology](ontology.md), including forbidden JSON numbers, preserved permitted
nulls, Unicode handling and explicit array order. SQLite integer columns below
use signed 64-bit INTEGER; wire/preimage integers are canonical decimal strings
(`0` or positive digits without leading zeros; signed offsets also allow a leading
minus, never `-0`). Overflow fails before mutation. Timestamps are whole-second
`YYYY-MM-DDTHH:MM:SSZ`; no floats, fractions or implicit local zones. JSON columns
contain UTF-8 TEXT with canonical bytes, not SQLite's arbitrary JSON re-encoding.
`*_hash` means lowercase 64-character SHA-256 hexadecimal.

An ID is `<prefix>_<sha256(canonical_preimage)>`. Every new-family preimage contains exactly
the listed fields plus `canonical_json_version=spine.canonical-json.v1`,
`contract_version=spine.recurring-related-tasks.v1` and the stated
`derivation_version`. Unless the table says otherwise, its value is `spine.` plus
the prefix with every underscore replaced by a hyphen, plus `-id.v1` (for example,
`spine.related-task-rule-id.v1`). An absent optional is omitted, never null. All references
are full stable IDs, not display labels. `owner` is the existing canonical
profile-owner union: `{owner_kind:"subject",owner_subject_id}`,
`{owner_kind:"subject_group",owner_group_id}` or `{owner_kind:"system"}`.

| Prefix / artifact | Additional preimage fields |
| --- | --- |
| `related_task_rule` | `owner`, `rule_key` |
| Configuration hash (no prefix; `derivation_version=spine.related-task-rule-configuration.v1`) | `configuration` |
| `related_task_rule_revision` | `related_task_rule_id`, `revision_index`, optional `prior_revision_id`, `configuration_hash` |
| `related_task_assignment` | `related_task_rule_id`, `initial_selector` |
| `related_task_generation` | `assignment_id`, `generation_index` |
| `related_task_proof` | `related_task_rule_id`, `proof_kind`, `proof_payload` |
| `related_task_assignment_revision` | `assignment_id`, `change_version`, optional `prior_assignment_revision_id`, `state_hash` |
| Assignment state hash (no prefix; `derivation_version=spine.related-task-assignment-state.v1`) | `state` |
| `related_task_intent` | `related_task_rule_id`, `rule_change_version`, `intent_kind`, `intent_payload` |
| `related_task_suppression` | `assignment_id`, `target_generation_id` |

`initial_selector` is the complete canonical recurrence target selector, not its
row reference, revision, expressed start or ordinal. `state_hash` hashes the exact
closed state object in Section 3.4. `proof_payload` and `intent_payload` are closed
below. Command IDs, observation times and page position do not enter assignment,
generation or suppression identity. Suppression attribution is immutable evidence,
not part of its identity; a fresh request cannot replace that attribution.

Ordinary child IDs remain **ontology-owned**, including their existing preimage
versions, which are not retroactively extended by the preceding registry. Use an internal deterministic
creation token equal to `generation_id` for the ordinary task creation's
identity seed in place of an arbitrary enclosing reconcile command ID. Apply the
existing item/anchor/relation/binding/policy identity algorithms to that seed and
the exact normalized child inputs; do not redefine their preimages here or submit
synthetic public commands/receipts. The real outer command remains causation and
audit attribution. Computed fixtures must publish that seed and every delegated
preimage. Updates keep the ordinary item and logical binding IDs; restoration
alone allocates the next generation and new ordinary child identities. A collision
with non-equivalent stored preimages fails `semantic_conflict`, never upsert.

For the existing `spine.command-id.v1` derivation specifically, fix
`command=schedule.related_task_rule.reconcile`, `command_id=generation_id`.
Use these role/path pairs: task `item` at `/task`; due anchor `due_anchor` at
`/temporal_binding/resolved_target`; relation `relation` at `/relationship`;
binding `temporal_binding` at `/temporal_binding`; first binding revision
`temporal_binding_revision` at `/temporal_binding/revisions/0`. Prefixes remain
`item`, `anchor`, `relation`, `temporal_binding`, `temporal_binding_revision`.
This is an internal seed, never a second actual command/receipt. Existing
notification intent/policy derivations then consume the resulting task and exact
policy facts. In particular, each effective reminder uses its canonical composed
`policy_key`: `profile_` plus template key for a profile template/replacement, or
the explicit custom policy key, under the notification-profile composition owner.
Initial/restored task intent creation uses exactly `generation_id + ":" + policy_key`
as `intent_created_by_command_id` and the initial policy's `created_by_command_id`.
This is the registered [notifications Section 3.1](notifications.md#31-registered-multi-policy-creation-token-mapping)
creation-token convention, not another public command or new intent preimage.
Reject invalid/colliding composed keys before any generation/policy writes.

The family receipt records, in policy-key order, each task/generation, policy key,
creation token, intent and active current family-composed policy IDs plus the
**real** outer command ID; independent custom policies are preserved/read through
their existing owner, not relabelled with an invented family key;
task-generation/owner/audit/receipt rows use real outer attribution, not the token.
Copy-forward/revision preserves each existing intent and original creation token.
New intents introduced during adoption use the real outer reconcile command ID
plus `":" + policy_key`, under ordinary fresh-policy edit rules; they are not
created again on an already adopted task or merely because a page is retried.
Distinct generations have distinct task and intent identities, while one policy
with several schedule offsets retains one intent and several slots. Equal-token/
different-preimage conflicts roll back the page, never replace a historical intent.
Later task/binding revisions use their existing update derivations
under the real outer operation and retain the created root IDs.

Rule revisions are contiguous positive integers. Rule `change_version` also
advances on retirement and semantic progress, so it is not a configuration index.
Assignment `change_version`, task `generation_index`, per-rule `assignment_seq`
and the global catalog generation are four different counters. No counter wraps
or resets; reaching its maximum fails closed.

## 3. Physical records and constraints

All new tables use foreign keys enabled, `ON DELETE NO ACTION`, and deferred
pointer FKs where a transaction creates both sides. Historical records are
append-only. Current headers/progress are the only mutable records, updated by
compare-and-swap under the outer writer transaction. Unless explicitly nullable,
columns below are NOT NULL. Existing `(item_id, version)` references target
`coordination_item_versions`; source revisions target `recurrence_revisions`;
selectors target `recurrence_target_occurrence_selectors`; binding IDs/revisions
target the existing relative-temporal-binding tables. Every cross-record same-rule,
same-assignment, same-set and exact item-version relationship is checked before
commit; FKs alone do not prove those semantic relationships.

The exact selector key, normalized children and producer are the **existing**
[recurrence Section 5.1](recurrence.md#51-existing-normalized-selector-persistence)
contract. Use its recurrence persistence service inside this page, before selector
FK insertion, and reconstruct/compare canonical selector/key/set on reuse. This
feature's migration verifies that dependency; it does not create a competing
selector table. The `initial_selector_json`/`selector_json` fields below are
immutable comparison/evidence snapshots validated against those relational facts,
not an alternative opaque selector authority. Notification policies use their
separate bridge only when actually targeting a selected recurrence occurrence;
generated-task item-scoped reminders do not require it.

### 3.1 Rule headers and immutable configurations

`related_task_rules`:

- `related_task_rule_id TEXT PRIMARY KEY`;
- `owner_kind TEXT CHECK IN ('subject','subject_group','system')`, nullable
  `owner_subject_id TEXT` FK `subjects(subject_id)`, nullable
  `owner_group_id TEXT` FK `subject_groups(group_id)`; exactly one matching
  non-null reference for subject/group and neither for system;
- `owner_key TEXT`, the canonical owner JSON, checked equal to those columns;
- `rule_key TEXT`, `source_item_id TEXT` FK `coordination_items(item_id)`,
  `recurrence_set_id TEXT` FK `recurrence_sets(recurrence_set_id)`;
- `enrolled_source_version INTEGER`, `enrolled_recurrence_revision_id TEXT`,
  `enrolled_at_utc TEXT`, `enrollment_json TEXT`;
- `current_revision_id TEXT` FK rule revisions, `change_version INTEGER >= 1`,
  `next_assignment_seq INTEGER >= 1`;
- `status TEXT CHECK IN ('active','retired')`, nullable `retirement_intent_id TEXT`
  FK intents; active iff that reference is null;
- `created_by_subject_id TEXT` FK subjects, `created_by_command_id TEXT`,
  `created_at_utc TEXT`.

UNIQUE `(owner_key,rule_key)` applies across active and retired history. Source,
set, owner, key and enrollment columns never change. The enrolled source version
has an exact composite item-version FK. Set and revision must belong to that
source. Source role is fixed `event_start`, child role fixed `task_due`; no
redundant mutable role columns. Enrollment JSON has exactly `kind`, and, for
`selected_occurrence`, `occurrence_key`, complete `selector`, and
`recurrence_revision_id`; for `upcoming`, no further fields. Enrollment time is
server execution time recorded once, not caller-selected history.

`related_task_rule_revisions`:
`related_task_rule_revision_id TEXT PRIMARY KEY`, `related_task_rule_id TEXT` FK
root, `revision_index INTEGER >= 1`, nullable `prior_revision_id TEXT` FK self,
`configuration_json TEXT`, `configuration_hash TEXT`, `created_by_subject_id TEXT`
FK subjects, `created_by_command_id TEXT`, `created_at_utc TEXT`.
UNIQUE `(related_task_rule_id,revision_index)`; revision 1 has no predecessor,
later revisions have exactly the preceding index in the same root. The JSON
shape and normalization are defined by command Section 3. Equivalent normalized
configuration does not allocate another revision. Requested policy/profile and
rendering revisions are resolved and snapshotted here, never followed live.

### 3.2 Assignments, reservations and source evidence

`related_task_assignments`:
`assignment_id TEXT PRIMARY KEY`, `related_task_rule_id TEXT` FK root,
`assignment_seq INTEGER >= 1`, `initial_selector_ref TEXT` FK selectors,
`initial_selector_json TEXT`, `initial_occurrence_key TEXT`,
`created_rule_revision_id TEXT` FK configurations, `created_at_utc TEXT`,
`created_by_command_id TEXT`, `current_assignment_revision_id TEXT` FK assignment
revisions, `change_version INTEGER >= 1`, `current_generation_id TEXT` FK
generations. UNIQUE `(related_task_rule_id,assignment_seq)`; the sequence is
allocated in the page's deterministic result order and never recycled.

`related_task_selector_reservations`:
`related_task_rule_id TEXT` FK root, `selector_ref TEXT` FK selectors,
`selector_json TEXT`, `occurrence_key TEXT`, `assignment_id TEXT` FK assignments,
`proof_id TEXT` FK proofs. PRIMARY KEY `(related_task_rule_id,selector_ref)`;
UNIQUE `(related_task_rule_id,occurrence_key)`; FK assignment's rule must match.
The selector row's canonical bytes/key must equal the stored snapshot. Initial
and successor reservations persist after terminal status, suppression and
retirement. A selector may never be transferred to a different assignment.

`related_task_source_proofs`:
`proof_id TEXT PRIMARY KEY`, `related_task_rule_id TEXT` FK root,
`proof_kind TEXT CHECK IN ('enrollment','identity','carry_forward','new_rdate',
'component_candidate','excluded','occurrence_cancelled','source_cancelled')`,
`source_item_version INTEGER >= 1` (composite source item-version FK through root),
`recurrence_revision_id TEXT` FK source revision, nullable
`prior_recurrence_revision_id TEXT` FK source revision, `proof_json TEXT`,
`proof_hash TEXT`, `created_by_command_id TEXT`, `created_at_utc TEXT`.
Proof hash is the digest suffix of `proof_id`, over the complete registered
proof-ID preimage, not a second incompatible JSON hashing convention.
Proof JSON is the exact `proof_payload` in Section 4. Source-reason observations
do not mutate recurrence facts. The corresponding actual immutable recurrence
rows and lineage IDs must exist; a receipt string supplied by a caller is not
proof. Store referenced lineage IDs in `related_task_proof_lineage` with columns
`proof_id TEXT` FK proofs, `lineage_id TEXT` FK `recurrence_lineage(lineage_id)`,
PRIMARY KEY both. Missing dependencies prevent the page, not a guessed mapping.

### 3.3 Child generations and source-only cancellation

`related_task_generations`:
`generation_id TEXT PRIMARY KEY`, `assignment_id TEXT` FK assignments,
`generation_index INTEGER >= 1`, nullable `predecessor_generation_id TEXT` FK self,
`task_item_id TEXT UNIQUE` FK coordination items, `created_task_version INTEGER`,
`relationship_id TEXT UNIQUE` FK `coordination_item_relations(relation_id)`,
`temporal_binding_id TEXT UNIQUE` FK relative bindings,
`item_access_owner_id TEXT UNIQUE` FK `item_access_owners(item_access_owner_id)`,
`created_rule_revision_id TEXT` FK configurations, `creation_proof_id TEXT` FK
proofs, `created_by_command_id TEXT`, `created_at_utc TEXT`.
UNIQUE `(assignment_id,generation_index)`, UNIQUE non-null
`predecessor_generation_id`. Generation 1 has no predecessor; every later row
references exactly index minus one in the same assignment. Exact task-version FK
and task type `task`, no target recurrence, relation direction/type and binding
source/target/selector equality are validated in the same commit. Only the current
assignment pointer may advance; no older generation becomes current again.

The relation is `part_of` from child task to source event. Bindings are
`follow_source`, `source_scope=selected_occurrence`, source role `event_start`,
target role `task_due`, `offset_basis=elapsed`. Store the existing closed binding
`source_terminal_behavior=require_decision`; generated-assignment guards then
authorize confirmed source cancellation under this family's stronger proof.
Neither an old v1 archived-source branch nor root retirement may bypass that
guard. No new value is inserted into the frozen binding enum.

#### 3.3.1 Explicit generated-item ownership

`configuration.task_owner` is an explicit **item** owner, exactly subject or
subject_group under [permissions Section 3](permissions.md#3-resource-ownership).
System is legal for the separate rule/catalog owner, never for this child field.
The child owner is fixed at enrollment; update cannot transfer it through a task
template. Each first/restored generation creates its ordinary task **and** its
existing `item_access_owners` header/current revision 1 atomically. No new owner
table, membership, access grant, account or ownership model is introduced.

Owner ID uses existing `spine.command-id.v1`: prefix/role `item_access_owner`,
command `schedule.related_task_rule.reconcile`, identity seed `generation_id`,
path `/task_owner`. This keeps the header stable across concurrent generation
attempts. Header fields are exact task `item_id`, that owner ID,
`current_revision=1`, configured `owner_kind` and its matching subject/group FK
(other FK null), `creator_entitlement_subject_id=NULL`,
`created_by_command_id=real outer command_id`. Do not infer a human creator from
the local agent, rule actor, participants, source owner or recipient.

Insert the complete `item_access_owner_revisions` row in the same transaction:
the exact header fields except `current_revision` becomes `revision=1`, plus
`changed_at_utc=page execution time`, `changed_by_subject_id=real local actor`,
`command_receipt_id=real outer receipt ID`. Its deferred FKs permit the header/
history/receipt cycle; all must exist before commit. Validate actual owner refs
and their current eligibility again under the writer lock. Readback exposes this
owner ID/revision; a preexisting conflicting owner fails closed, never transfers.

When a page creates one or more owner headers, increment
`ledger_access_state.access_epoch` once in that same transaction and invalidate
the relevant catalogs. Existing-task following, replay, no-op and dry run create
no owner history or epoch change solely for observation. Configuration adoption
and target item-version copy-forward retain the same owner header/revision, not
another owner row per task version. Owner changes/missing or contradictory
ownership evidence invalidate assignment freshness and require explicit resolution,
not automatic restoration of a different owner or grants.

The unconfigured-ledger epoch initialization seam is the subject of the separate
[trusted-local ownership bootstrap](local-ownership-bootstrap.md). The
operator selected realm-independent initialization on 2026-11-10. That amendment
was ratified on 2026-11-10; its state/migration/provisioning machine package is
ratified and implemented behind the internal R2 candidate boundary. Public-family
activation and the remaining R2/R3/R4 proofs are still separate gates.

The ordering is task/owner/history, then concrete child profile/presentation
validation and policy/application rows, then selected work, audit/receipt, one
commit. An exact pre-authorized reusable disclosure may be applied only after
checking the actual newly established child owner, item and destination inside
that transaction. Rule configuration is not itself an item owner or disclosure
grant. Failure leaves no task, owner, policy, work, audit or receipt residue.
This explicit-owner family is distinct from the existing owner-less
trusted-local `schedule.create`; [rendering Section 3.3](notification-rendering-integration.md#33-fresh-trusted-local-creation-and-explicit-adoption)
keeps that command's ordinary-only fresh-create rule unchanged.

`related_task_source_cancellations`:
`generation_id TEXT PRIMARY KEY` FK generations,
`cancelled_task_version INTEGER >= 1`, `proof_id TEXT` FK proofs,
`assignment_revision_id TEXT UNIQUE` FK assignment revisions,
`command_id TEXT`, `cancelled_at_utc TEXT`.
The exact cancelled task/version must be an ordinary `task_status=cancelled`
successor, produced solely by the proof's confirmed source cause. Manual or mixed
causes cannot insert this row. It is necessary, not sufficient, for restoration.
Old cancellation rows never change when the occurrence returns.

`related_task_restoration_suppressions`:
`suppression_id TEXT PRIMARY KEY`, `assignment_id TEXT UNIQUE` FK assignments,
`target_generation_id TEXT UNIQUE` FK generations,
`actor_subject_id TEXT` FK subjects, `command_id TEXT`, `suppressed_at_utc TEXT`.
The generation must be current and have a source-cancellation row and no successor
when committed. No deletion/release is supported. Ordinary done/manual-cancel/
detach instead persists the veto through the assignment state below, with the
ordinary mutation's own audit evidence. These are separate from source-only causes.

### 3.4 Immutable assignment states

`related_task_assignment_revisions`:
`assignment_revision_id TEXT PRIMARY KEY`, `assignment_id TEXT` FK assignments,
`change_version INTEGER >= 1`, nullable `prior_assignment_revision_id TEXT` FK self,
`state_json TEXT`, `state_hash TEXT`, `source_item_version INTEGER >= 1`,
`recurrence_revision_id TEXT` FK source revision, `task_item_id TEXT`,
`task_item_version INTEGER >= 1`, `adopted_rule_revision_id TEXT` FK configurations,
`generation_id TEXT` FK generations, `selector_ref TEXT` FK selectors,
`temporal_binding_revision_id TEXT` FK binding revisions,
`proof_id TEXT` FK proofs, `command_id TEXT`, `created_at_utc TEXT`.
UNIQUE `(assignment_id,change_version)`; contiguous predecessor, exact target
version FK and same-source/set checks apply. Extracted typed columns must equal
the JSON, not independently editable caches.

`state` has exactly `generation_id`, `selector`, `occurrence_key`,
`source_item_version`, `recurrence_revision_id`, `proof_id`, `task_item_id`,
`task_item_version`, `temporal_binding_revision_id`, `adopted_rule_revision_id`,
`managed_baseline`, `disposition`, `restoration_veto`, `reason`, and optional
`pending_intent_id`. The binding revision is an exact existing FK reference.
`managed_baseline` is the normalized configuration subset last actually applied
to this task (including resolved reminder set), not its current customizations.
Disposition is closed: `governed`, `source_cancelled`, `done`, `manual_cancelled`,
`detached`, `suppressed`, `decision_required`. `restoration_veto` is a JSON boolean;
it is monotone false→true on done/manual cancel/detach/explicit suppression.
`reason` uses command Section 8. No separate task status is inferred from this
state; task details remain authoritative. Target writes must refresh this exact
witness or invalidate it atomically under Section 6 before any next admission.

### 3.5 Edit/retirement intents and bounded progress

`related_task_intents`:
`intent_id TEXT PRIMARY KEY`, `related_task_rule_id TEXT` FK root,
`rule_change_version INTEGER >= 1`, `intent_kind TEXT CHECK IN ('adopt','retire')`,
`intent_json TEXT`, `status TEXT CHECK IN ('pending','complete','superseded')`,
`created_by_command_id TEXT`, `created_at_utc TEXT`.
UNIQUE `(related_task_rule_id,rule_change_version)` and partial UNIQUE root for
`intent_kind='adopt' AND status='pending'`. Intent JSON is immutable; only status
may advance. Adoption payload: exactly `configuration_revision_id`,
`assignment_high_water`, `scope=upcoming_open`; retirement payload: exactly
`disposition`, `assignment_high_water`, optionally `superseded_adoption_intent_id`.
Disposition is `keep_following|detach_open|cancel_open`. High water is the largest
assignment sequence present in the authoring transaction (`0` if none).

`related_task_intent_outcomes`:
`intent_id TEXT` FK intents, `assignment_id TEXT` FK assignments,
`assignment_revision_id TEXT` FK states, `outcome TEXT CHECK IN
('applied','skipped_terminal','skipped_overdue','skipped_independent',
'retained_equal','conflict')`, `reason TEXT`, `command_id TEXT`, `created_at_utc TEXT`,
PRIMARY KEY `(intent_id,assignment_id)`. An outcome is append-only. A conflict
resolution appends a new assignment state; effective resolution is proved by the
current state referencing the intent and its adopted configuration, not by
rewriting the old conflict fact. A later exact terminal/overdue/independent skip
state referencing that intent also resolves its conflict without adopting it.
A still-unresolved conflict does not complete the intent. Completion requires
an indexed bounded sweep proving an outcome/resolution for every assignment
through high water; a partial page or a row count alone is not proof.

An upcoming-open adoption selects existing assignments through the immutable high
water. Eligibility (current open/governed, unsuppressed, strictly future due) is
evaluated at each committing page. New assignments above high water already use
the current configuration. A pending candidate blocks material-changing old work
until its eligibility/outcome is resolved; becoming overdue does not bypass the
gate. A bounded page may record `skipped_overdue`, explicitly preserve the prior
adopted configuration and release that intent's gate without backfilling work.
The automatic planner only dispatches that semantic transition once.

`related_task_rule_progress`:
`related_task_rule_id TEXT PRIMARY KEY` FK root, `progress_version INTEGER >= 0`,
`source_scan_version INTEGER >= 1`, `recurrence_revision_id TEXT` FK source revision,
`coverage_json TEXT`, nullable `assignment_after_seq INTEGER`, nullable
`pending_intent_id TEXT` FK intents. Coverage JSON has exactly `range_start_utc`,
`range_end_utc`, `source_after` (null or command ordering tuple), `complete` boolean.
It certifies only committed selected source work under that source snapshot and
range, not permanent coverage of a moving horizon or global convergence. It
changes only with actual coverage advancement, invalidation or disposition work;
no last-polled/heartbeat/time-observed column. Retained/blocked idle observations
alone do not advance it. Clocks can make a fresh read-only plan eligible later.

In particular, advancing evaluation time or an otherwise empty horizon is not
semantic progress and MUST NOT write this row. Coverage-only writes may discharge
an already-queued invalidation/intent or record a newly proved finite exhaustion
once; repeatedly observing that same result cannot write another progress state,
audit or receipt. Waiting for a future clock boundary is an in-memory/read-only
scheduler fact, not a durable tick log.

### 3.6 Catalog and invalidation queue

`related_task_catalog_state`: singleton `singleton_id INTEGER PRIMARY KEY CHECK=1`,
`catalog_generation INTEGER >= 0` (initial 0).

`related_task_dirty_rules`: `related_task_rule_id TEXT PRIMARY KEY` FK root,
`dirty_generation INTEGER >= 1`, `source_dirty INTEGER CHECK IN (0,1)`,
`target_dirty INTEGER CHECK IN (0,1)`, `intent_dirty INTEGER CHECK IN (0,1)`,
`assignment_after_seq INTEGER >= 0`. At least one flag is 1. This is a derived
coalescing work queue, not historical truth. Mark affected roots once per semantic
transaction, never append one row per tick. Clearing a page uses compare-and-swap
on `dirty_generation`; a later invalidation cannot be lost by an older worker.
Round-robin root-ID continuation and separate source/assignment/intent budgets
prevent one blocked or dense root monopolizing a sweep.

## 4. Source proof and continuity algorithm

The source [recurrence identity](recurrence.md#5-identity-and-occurrence-keys) and
target carry-forward contract stay authoritative. Neither a new family hash nor
a source-to-copy child map alone proves arbitrary occurrence correspondence.
Validation is read-only until the enclosing page commits its accepted proof.

Every proof payload has `source_item_id`, `source_item_version`,
`recurrence_set_id`, `recurrence_revision_id`, `normalized_recurrence_set_hash`,
`selector`, `occurrence_key`, `lineage_ids` (sorted unique array), plus the
kind-specific fields below. For source-wide cancellation, omit selector/key,
include exact `cancelled_event_version`, and use an empty lineage array. Complete
selectors, not hashes alone, are available for historical decoding. A prior proof
reference is included only for continuity and has both `prior_proof_id` and
`prior_selector`. FKs and canonical bytes are checked before admission.

1. **`enrollment`:** a current pre-exclusion candidate proved under the enrolled
   revision inside the effective boundary. Store `enrolled_recurrence_revision_id`.
   It authorizes initial reservation only if no existing alias claims that slot.
2. **`identity`:** exact selector equality with an existing reservation plus current
   selector-local membership proof. No prior source revision equality is needed;
   expressed overrides and exdates do not redefine the original slot.
3. **`carry_forward`:** exact prior/current selectors and prior proof, with an
   unbroken ordered revision path. Every hop must be either an authoritative
   target-key retarget map, or a segment/child copy map whose candidate stream is
   unchanged at the same original scheduled fact. Copied seed, selector defaults,
   phase, COUNT subtraction, raised bounds and segment membership must validate
   under recurrence Section 7. Include `hops`, each exactly
   `{prior_revision_id,new_revision_id,prior_selector,selector,lineage_ids}`.
   Retarget maps must resolve one-to-one. No two reserved assignments may claim
   the same result; no split or merge of assignments is supported.
4. **`component_candidate`:** a missing slot under a component present at enrollment
   or explicitly copied with the unchanged-candidate predicate above. Include
   `basis_revision_id`, `component_selector`, `hops`. Candidate membership and
   duplicate-collapsed union must be proved. Every contributing component must
   have proved continuity or positive addition; an unproved changed contributor
   makes the union unresolved, even when another contributor is unchanged.
5. **`new_rdate`:** a genuinely added rdate, its `rdate_id`, predecessor source
   revision and actual add/copy lineage. Prove it was not a prior included slot,
   alias, or unresolved old slot now at a different time. Duplicate add and union
   with a reserved slot retain that assignment if correspondence is unique; they
   are not new-generation entitlements.
6. **`excluded` / `occurrence_cancelled`:** an already reserved selector, the
   previous proof and exact current `exdate_id` or lifecycle `override_id`, after
   any proved continuity, plus current inactive/actionability facts. These alone
   authorize occurrence-caused cancellation. `source_cancelled` requires actual
   cancelled event detail/version, not an archived shell or ended COUNT.

The same proof may establish continuity and then observe exclusion; persist both
proofs with the exclusion referencing the accepted current identity proof. A
restored selector is proved as identity/carry-forward and checked against the
generation's independent source-cancellation evidence. No new proof kind silently
reopens a task.

**Unsupported topology is explicit.** Replacing frequency, seed, phase, selectors
or original time is not an unchanged-component proof, even if the resulting times
look similar. A generic series time shift without authoritative per-occurrence
retarget evidence may therefore be decision-required; ordinary move overrides do
follow automatically. Distinct original facts cannot be paired by equal ordinal,
nearest time, title or calendar day. If the bounded path, union, uniqueness or
membership proof fails, report `source_continuity_unresolved`, block obsolete work
and neither cancel an assignment nor create a replacement. A whole-set revision
does not make every new unmatched selector novel.

There is no caller-supplied mapping/cancellation certificate or manual arbitrary
rebind API in v1. Operators can inspect exact proof gaps and use ordinary explicit
task cancellation/detach, or author a separate enrollment; the per-rule alias
reservation remains. Broadening automatic correspondence requires an amendment
to the recurrence proof owner, not a best-effort scheduler heuristic. This is a
technical support limit, not a new restoration or cancellation policy.

## 5. Atomic writes, managed fields and history

A page's outer `BEGIN IMMEDIATE` rechecks source/root/assignment/target versions,
replay, intent and reservation uniqueness; validates proofs; creates ordinary
child truth and exact supporting sets; writes states/proofs/generation links;
reconciles ordinary work; advances current/progress/catalog; stores the real audit
and command receipt; commits once. Any error rolls back the complete page. No
helper commits or separate receipts for internal compositions. Unique collision
races become stale/conflict results with no partial loser rows. Never use
`INSERT OR REPLACE` to erase history.

For adoption use a three-way comparison per normalized managed field: baseline
`B`, current child `C`, desired `D`. If `D=B`, preserve `C`; if `C=B` or `C=D`,
apply `D`; otherwise record conflict and change none of that task's managed
content, adopted revision or work. Managed fields are task title, summary, source_ref, priority,
archetype selection, assignee set, primary location, elapsed offset,
complete reminder/delivery/presentation set and materialization configuration.
Each people set is sorted unique IDs; absent summary/priority/location is normalized
to null; each reminder is keyed by immutable template key and order is canonical.
The reminder/delivery/presentation set is one comparison field: no implicit
partial policy merge. Due time itself is derived, not compared as a manual field;
an ordinary source-follow move is not a manual offset override.
Item ownership is instead an invariant under Section 3.3.1, not a three-way
template field or an ownership-transfer operation.

To resolve an overlap, explicitly edit the ordinary task to the baseline or desired
value, or explicitly cancel/detach it, then reconcile against new expected facts.
No force-overwrite flag exists. Pending intents are serialized: a second material
configuration update fails while adoption is pending, including conflicts; an
identical configuration request may continue that same intent. A new-only edit
does not displace it. Retirement keep-following preserves it, whereas detach/cancel
supersedes it with retained historical evidence.

Target item versions remain contiguous ordinary versions and copy forward every
supporting set under existing owners. Apply successor policies before advancing
the item pointer and materialize against the successor due, never predecessor
time. Unrelated task edits preserve rule/generation links; they update the current
witness or mark the exact assignment dirty in the same transaction. Restoration
copies current permitted customizations from its predecessor using the adopted
baseline/configuration, not root-latest or a live catalog lookup. Invalid current
routes/disclosure still fail closed; copied evidence is not a new approval.

## 6. All-writer freshness and notification boundary

All source item/version, recurrence, relation, target task/binding/ownership and relevant
policy changes must invalidate affected rules/assignments and catalog generation
in the same canonical transaction. Use indexed joins from source to roots and
target to generation; do not scan all tasks/history. Source fan-out queues roots,
not unbounded per-assignment updates inside the source command. An unrefreshed
assignment witness is already sufficient to refuse work until current proof is
resolved. Catalog triggers may conservatively invalidate related reads but must
not emit audit/receipts on observation. Migration tests enumerate all writers,
including low-level commands, rather than assuming only these new composites write.

At **each actual attempt start**, inside the existing attempt admission boundary,
recheck current task, active binding/relation, latest generation, veto, root
disposition, actual item owner/revision, pending material adoption/cleanup and
source proof/actionability.
Root retired/keep-following permits maintenance, never new generations. Pending
cancel/detach prevents obsolete source-governed sends until cleanup commits;
pending material adoption or unresolved continuity also blocks. Source version
changes require current proof even if the old work's due is unchanged. A bounded
proof failure or resource limit is refusal, not cancellation or permission.
Ordinary tasks outside this family keep existing v1 behavior.

No reconciliation may rewrite in-progress/retry-with-attempts/terminal delivery
history. Cancel eligible zero-attempt rows, preserve protected stale rows, and
gate their next attempt against current truth. Persist the canonical
`side_effect_attempts` record before an external send. A send already admitted
cannot be retracted. Planning/readback never opens an attempt.

## 7. Required indexes, plans and finite work

In addition to PK/unique indexes, require these named B-tree indexes (column order
is normative; names participate in the schema manifest):

| Name | Table and ordered columns / predicate |
| --- | --- |
| `related_task_rules_owner_idx` | rules `(owner_key,status,related_task_rule_id)` |
| `related_task_rules_source_idx` | rules `(source_item_id,related_task_rule_id)` |
| `related_task_assignments_page_idx` | assignments `(related_task_rule_id,assignment_seq)` |
| `related_task_generations_assignment_idx` | generations `(assignment_id,generation_index)` |
| `related_task_assignment_revisions_history_idx` | states `(assignment_id,change_version)` |
| `related_task_reservations_assignment_idx` | reservations `(assignment_id,selector_ref)` |
| `related_task_proofs_revision_idx` | proofs `(related_task_rule_id,recurrence_revision_id,proof_id)` |
| `related_task_intents_pending_idx` | intents `(related_task_rule_id,intent_kind,intent_id)` WHERE status='pending' |
| `related_task_outcomes_assignment_idx` | outcomes `(assignment_id,intent_id)` |

Target lookup uses the generation task UNIQUE index; latest state/current generation
uses direct PKs, not MAX over all history. Assignment pages use sequence keysets,
not OFFSET. Intent outcomes use high-water range plus indexed anti-join/current
resolution lookup. Source membership/lineage uses bounded selector-local recurrence
proof, never expansion from seed just to find an old assignment. Generation pages
use source original-fact/selector ordering, not expressed-time offset paging.
No whole-history scan or full integrity check belongs in routine startup/cycles.

Command budgets bound candidates, proof hops, assignments, mutations, generated
work and bytes separately; source editing can queue a root without visiting all
its children. Budget exceedance inside one indivisible task/proof fails the page;
between units returns continuation. Never silently truncate reminder sets or
proof evidence. Bound historical readback too. Total historical storage is not
capped by this feature; no deferred ledger-retention policy is invented here.

## 8. Migration, rollback and verification oracles

Use the next ordinary ordered migration chosen at implementation, atomic DDL,
matching packaged expected-object fingerprints, declared family prerequisites
and newer-schema refusal by old writers. Start all new tables empty with catalog
generation 0. Do not infer enrollment/adoption from titles, relations, old
single-occurrence bindings or similar schedules. Existing rows/receipts retain
their bytes and identities. New constraints/triggers and backfill-free indexes
must be tested against both an existing ledger fixture and a fresh initialization.

The migration may verify required source tables/columns and duplicates before
DDL, but must not rewrite recurrence selectors/history or repair ambiguous data.
Any incompatibility rolls the migration back. Transaction rollback removes one
failed page; it does not undo earlier committed pages. Binary rollback is not
permission for an older writer to use the new schema. An approved pre-migration
backup restore loses subsequent writes; no automatic down migration deletes
assignments or generations. Release procedures remain outside this leaf.

Before implementation activation, publish computed fixture families for:

- canonical configuration/IDs including Unicode, absent/null, array order,
  signed offsets, owner distinction, all derivation preimages and delegated IDs;
- existing recurrence-selector dependency/producer/reuse with exact bytes,
  zero-reminder child without notification bridge, conflicting/missing children;
- two-reminder profile/custom-key tokens, input reordering, replacement intent
  carry-forward, distinct restored-generation intents and real outer attribution;
- explicit subject/group owner header/history/epoch, no creator entitlement,
  rejected system child owner/transfer, actual owner/disclosure validation and
  rollback after owner creation but before policy/work/receipt completion;
- fresh/changed source selectors, copies/COUNT split, union contributor changes,
  exact retarget maps and unsupported topology without heuristic novelty;
- reservation collisions, generation predecessor uniqueness, suppression races,
  stale current pointers, source-only versus mixed/manual cancellation;
- adoption baseline equality/non-overlap/conflict, serialized pending intents,
  retirement precedence and outside-horizon assignments;
- same-command replay, new-command races, failures after every write stage,
  all-writer invalidation, attempt-before/after-source-change interleavings;
- migration fingerprint/constraint failures, immutable historical decoding and
  `EXPLAIN QUERY PLAN` proving indexed root/target/selector/keyset paths.

The [machine companion](recurring-related-task-machine-contract.md) and retained
corpus supply the offline representations and finite witnesses. Actual database,
transaction, concurrency, migration and attempt-start oracles remain unexecuted
runtime obligations. DDL and runtime tests must mechanically verify this leaf's names,
constraints and extracted canonical bytes before advertising the family.
