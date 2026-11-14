# Recurring Related Tasks: Detailed Command Contract

Status: Accepted v1.0.0 — trusted-local commands implemented in runtime 0.12.0/schema 20; release verification tracked separately

Ratified: 2026-11-09

## 1. Scope, versions and compatibility

This companion defines the ratified trusted-local family under
[recurring related tasks](recurring-related-tasks.md). Its
[storage/identity companion](recurring-related-task-storage.md) owns physical
records, ID bytes and positive source proof. Existing [command conventions](agent-command-contract.md),
[relative bindings](relative-temporal-bindings.md), [notifications](notifications.md)
and [schedule operations](schedule-operations.md) retain their authority.

The exact request selector and runtime family are
`spine.recurring-related-tasks.v1`; normalization is
`spine.recurring-related-tasks.normalization.v1`; canonical JSON is
`spine.canonical-json.v1`. Response selector is
`spine.recurring-related-tasks-response.v1`. These are accepted constants, not current
compiled declarations. Implementation activation requires schemas, computed
fixtures, installed closure, schema admission and tests in a later step.

The closed command set is:

- `schedule.related_task_rule.create`
- `schedule.related_task_rule.update`
- `schedule.related_task_rule.show`
- `schedule.related_task_rule.list`
- `schedule.related_task_rule.reconcile`
- `schedule.related_task_rule.retire`
- `schedule.related_task_rule.assignment.suppress`

CLI tokenization follows the existing dotted identifiers. These are **local-only**:
no HTTP route, web allowlist entry or authenticated sender claim is implied.
Frozen reads, old request selectors and unrelated one-task binding behavior are
unchanged. Existing ordinary task reads/completion/cancellation/detach remain valid.
Generated bindings use the shared assignment-aware guard even through old direct
binding commands; a caller cannot bypass source proof by addressing the binding.

Before advertising this family, its compiled dependency closure must exact-match
the implemented command families actually delegated here: scheduling creation v4,
schedule operations/people, recurrence contract/normalization v1, relative binding
v1, notification scheduling/work, profiles v2 and rendering integration v1, plus
canonical JSON. The machine manifest must enumerate the concrete installed
identifiers from the current registry, not wildcard `latest` or invented aliases.
This paragraph does not change existing registry rows or mark this family implemented.

## 2. Shared scalar and envelope rules

All objects are closed: only fields specified here or in an explicitly delegated
schema are accepted. Reject unknown fields as `unsupported_field` at their full
JSON path. No caller-supplied generated ID, proof, source-to-target mapping, due
timestamp or status override is accepted unless expressly identified below as an
existing target reference. Strings/IDs retain their owning schema's length and
character rules; `rule_key` matches `[a-z][a-z0-9_-]{0,63}`. No trimming/case-folding
or label-based identity resolution. Integers/UTC follow storage Section 2.

Every request has `contract_version`. Every write also requires `command_id`,
`actor_subject_id`, `requested_at_utc`; those are ordinary attribution, not
verified chat identity. The timestamp is recorded and replay-bearing but never
authorizes creation after a real cutoff. `--dry-run` is the existing execution
option, not an extra JSON field and not part of stored command comparison.
Reads do not require an actor/command ID and never create receipts/audit/progress.

Writes targeting an existing rule require `related_task_rule_id` and
`expected` containing exactly `rule_change_version`, `rule_revision_id`,
`source_item_version`, `recurrence_revision_id`, `catalog_generation`. Each is an
exact current fact, including after a retired root. Suppression additionally
requires `assignment_change_version` in `expected`; reconcile carries the exact
snapshot inside its continuation too. Global generation may conservatively stale
an unrelated-root request; this is a safety tradeoff, not permission to ignore it.

Success envelope: required `ok=true`, `response_contract`, `command`, `changed`
(JSON boolean), `effect`, `evaluated_at_utc`, `result`; writes additionally return
`command_id`, `command_receipt_id`, `audit_ids` and `replayed` (JSON boolean).
`audit_ids` is a sorted unique array, empty for no-op. Fresh dry-run previews return
`command_receipt_id=null`, `audit_ids=[]`, `replayed=false`, `dry_run=true` and
would-be IDs/results, not a claim of commitment; ordinary success omits `dry_run`.
Compatible stored receipt replay takes precedence even if `--dry-run` was supplied:
return the original committed result with `replayed=true`, not a fabricated
null-receipt preview. Reads always have `changed=false` and no command receipt/audit/replay fields.
All results carry `delivery=not_attempted_by_command`.

The source-only [machine companion](recurring-related-task-machine-contract.md)
closes the descriptive projection/tuple names used below. In particular, reads
and fresh previews require `commit_cutoff_recheck_required=true`, rule readback
includes `source_snapshot`, and reconcile requires `future_generation` in its
result. These source-only representations do not activate the command family.

Receipt identity uses the existing `spine.command-id.v1` derivation with the real
command/command ID, role `command_receipt`, path `/command_receipt`; root audit
uses role `audit`, path `/audit`. Child audit rows use role `audit`, path
`/assignments/<assignment_id>/audit`, with that child's real task as audit item.
The root audit/receipt references the rule's source item without changing it.
The existing receipt semantic-facts hash binds the normalized request, result,
family/normalization/canonical versions and accepted source/configuration proof
facts. Store the exact success body and comparison hash in the existing receipt
ledger; do not add a second receipt table. Timestamps/actor are causation evidence,
not alternative assignment identity. All IDs and rows are in the page transaction.

Failure envelope: required `ok=false`, `response_contract`, `command`,
`error={code,field,message}`, `changed=false`; optional `current` contains only
already-visible exact freshness facts, never an invented receipt. Failure writes
no canonical domain/audit/receipt row. Existing environment diagnostics remain
allowed outside the ledger. Error vocabulary/precedence is closed in Section 8.

## 3. Configuration and enrollment

Create's `source` is exactly `{item_id,item_version,recurrence_set_id,
recurrence_revision_id}`. It must identify the current scheduled, non-archived
event, its `event_start` recurrence and a supported instant-bearing source.
Selected-occurrence binding v1's supported source-time rules apply; reject date-only
sources. No event-end or implicit host timezone. Ownership and delivery are never
inferred from source participants or the current chat.

`enrollment` is exactly `{kind:"upcoming"}` or
`{kind:"selected_occurrence",occurrence_key}`. Resolve the latter against the
exact current source revision and persist the complete original selector.
Record server execution time once. The explicit start is inclusive in original
source order `(scheduled_fact,canonical_selector_bytes)`; following aliases retain
that boundary through proved lineage, not through expressed-time guesses.

`configuration` requires exactly `task_owner`, `task_template`, `offset_basis`,
`offset_seconds`, `notification_plan`, `delivery`, `materialization`,
`generation_horizon_seconds`. `task_owner` uses the existing **item-owner** union:
`{owner_kind:"subject",owner_subject_id}` or
`{owner_kind:"subject_group",owner_group_id}` with exactly the matching ID.
`owner_kind=system` fails `invalid_request`,
`field=configuration.task_owner.owner_kind`. The referenced subject/group must
exist and satisfy current ownership validation. The separate rule `owner` retains
the catalog-owner union, including system; no rule owner implies a child owner.

This explicit field authorizes creation of the generated item's existing owner
header/revision in the same bounded transaction as the task, before policy/
presentation/work creation, as closed by
[storage Section 3.3.1](recurring-related-task-storage.md#331-explicit-generated-item-ownership).
It grants no creator entitlement, group membership or disclosure approval. The
child owner is immutable for this rule: update must carry the same normalized
`task_owner`; a different value fails `semantic_conflict`,
`field=configuration.task_owner`, even for `new_assignments_only`. This family
does not transfer ownership or adopt existing unrelated tasks.

`task_template` contains required `item`, `people`. `item` is the task branch of
the existing scheduling-v4 `item` schema: `item_type=task`, required `title` and
`task_detail`, optional `summary`, `source_ref`, `primary_location`, `archetype`.
Forbid `event_detail`, `task_detail.subject_roles`, due/start/end anchors, recurrence,
caller IDs/versions and status. `task_detail` may contain `priority` only under its
existing schema. `people` is exactly `{assignees:[subject IDs]}`, including empty
to mean no assignees. The bounded raw authoring array may repeat exact IDs;
normalization sorts and deduplicates it into the stored complete set. The raw
array still has the declared 100-entry cap; normalization does not allow an
unbounded duplicate stream. Normalized stored arrays require unique IDs. Resolve
the existing people continuity/visibility requirements, not family membership
inference. No facet-value or generalized workflow authoring is added in v1.

`offset_basis` is exactly `elapsed`. `offset_seconds` lies in
`[-31622400,31622400]`. The concrete due is current expressed source UTC plus that
offset, converted with the source's authored timezone/pin and admitted resolver.
An existing assigned task is not removed for moving outside generation coverage.

`notification_plan` is either explicit null (zero policies) or exactly the existing
notification-profile-v2 `createPlan` shape. Resolve explicit/current/archetype
selection, overlays and rendering applications **once** during authoring, retaining
the requested input and exact resolved profile/archetype/template/presentation
facts. Subsequent generation/adoption/restoration uses that immutable snapshot;
current route/disclosure/eligibility still must validate. Never auto-grant approval.
Rule authoring checks the explicit prospective child owner and reusable disclosure
scope; it does not fabricate item ownership or task-specific application evidence.
Each actual generation first establishes the real child owner and then validates
the selected presentation against that exact item/owner/destination before commit.
Missing or mismatching disclosure fails authoring with the existing
`rendering_disclosure_unavailable` code at `configuration.notification_plan`;
an existing assignment reports `disclosure_unavailable` without unauthorized work.
The existing owner-less local `schedule.create` remains ordinary-only on fresh
creation; this is a separate explicit-owner contract, not an amendment to its request.
`delivery` is null iff the resolved reminder set is empty; otherwise it is the
existing scheduling `delivery` shape. Resolve a context default at authoring and
persist the concrete target/destination snapshot. No route upsert is implicit.

Normalized stored `configuration` has the same top-level fields, but non-null
`notification_plan` contains exactly `{requested,resolved}` and `delivery` is
either null or `{requested,resolved}`. `requested` is the fully defaulted normalized
delegated input. Notification `resolved` has exactly `selection_mode`, `profile`,
`notification_profile_binding_id`, `scope_chain`, `effective_templates`:

- Selection mode is the requested plan's mode (`none|explicit|archetype_default`).
  `profile` is null for custom-only/no-match, otherwise exactly
  `{notification_profile_id,notification_profile_revision_id,normalized_profile_revision_hash}`.
- Binding ID is null unless archetype-default resolution used one; scope chain
  is the exact ordered resolved owner chain (empty for explicit/custom-only).
- Effective templates are a sorted array of exactly
  `{policy_origin,source_key,policy_key,template,presentation}`. Origin is
  `profile_template|profile_replacement|custom_addition`; `template` is the closed
  normalized profile-v2 template schema, with concrete schedule/late handling and
  exact rendering revision. `presentation` is the existing closed
  `policyPresentation` union, with exact resolved disclosure reference, or ordinary.
  No task-specific policy/intent/application ID is fabricated at rule authoring.
  Derive `policy_key` by the existing composition rule: `profile_` plus template
  key for profile templates/replacements, unchanged custom policy key otherwise.
  Sort by final policy key; reject invalid keys or post-composition collisions.
  Initial generated/restored task intents use the registered generation-ID/key
  token from storage Section 2; current policy copies retain their existing intent.

Delivery `resolved` is exactly the existing schedule-create-v3 response
`$defs/delivery`, excluding only `delivery_state`: concrete delivery target,
resolution source/default key, recipient kind/matching recipient ID, channel,
adapter and target ref with its existing conditional field rules. Exact delegated
selectors and snapshot facts remain included. A missing optional
item `summary`, `source_ref`, `primary_location`, `archetype` or task `priority`
normalizes to null in this stored template only; runtime child inputs omit those
nulls where the owning authoring schema requires absence. No legacy wire schema
is amended. The machine companion must give these projections closed named schemas,
not an unconstrained JSON object or a complete item-specific profile application.

Profile templates are ordered by template key, custom policies by their normalized
key, sets by exact ID. Do not reorder genuinely ordered nested arrays under an
owning contract. Reject duplicate keys before hashing. Equivalent request field
order does not change configuration; profile metadata-only changes do not change
the resolved scheduling snapshot. Historical revisions decode without consulting
the current catalog. Configuration hash and ID preimages are storage-owned.

`generation_horizon_seconds` is a canonical positive integer in `[1,31622400]`,
default `4838400` (56 elapsed days) when omitted on initial input. Normalize the
default into the stored configuration. It is measured from evaluation over
expressed source starts with upper bound exclusive. Reject configuration whose
horizon is shorter than the earliest enabled reminder's source-relative lead;
compute that lead from the task offset plus the earliest bounded template offset.
Unbounded repeat windows or unprovable earliest reminders fail configuration
validation, not silently partial generation. This does not promise materialization
outside the separately configured work range.

`materialization` is `{mode:"none"}` or
`{mode:"bounded",lookback_seconds,horizon_seconds,opportunity_limit}`. Each bound
is explicit: lookback `0..31622400`, horizon `1..31622400`, opportunity limit
`1..1000`. The actual page work range is
`[execution_now-max(lookback,max_enabled_grace),execution_now+horizon)`; use the
current successor due/policies to expand within it, not the prior task time.
Existing notification handling determines expired/late eligibility. There is no
`delivered` claim, forced immediate send or manually calculated UTC range.

## 4. Authoring, update, retirement and suppression

These tables list command-specific fields in addition to Section 2. No omitted
field means an implicit mutation scope. Caller inputs are normalized before
comparison; compatible replay precedes current-state checks.

| Command | Required specific fields | Optional specific fields |
| --- | --- | --- |
| create | `owner`, `rule_key`, `source`, `enrollment`, `configuration` | none |
| update | `related_task_rule_id`, `expected`, `configuration`, `adoption_scope` | none |
| retire | `related_task_rule_id`, `expected`, `disposition` | none |
| assignment.suppress | `related_task_rule_id`, `expected`, `assignment_id`, `target_generation_id`, `target_task_item_id` | none |

Create compares current source versions inside the write. The root key is unique
across active/retired history. Same-command replay returns the original root; a
different command on an occupied key fails `semantic_conflict`, even if similar.
It creates the root/configuration/enrollment/audit/receipt and empty progress only;
no tasks, work or hidden reconcile. Result contains the complete rule projection
defined in Section 6, `generation_started=false`, `materialized_work_count="0"`.

Update replaces the **complete** configuration, not a merge patch. Source, root
owner/key and enrollment are immutable; their presence fails `unsupported_field`.
`adoption_scope` is `upcoming_open` or `new_assignments_only`. Unequal normalized
configuration allocates exactly the next revision. `upcoming_open` atomically
records one adoption intent/high water without fan-out. `new_assignments_only`
allocates no adoption intent; existing assignments keep their adopted settings.
Do not infer per-assignment desired configuration just from root-latest.

An equal configuration with `upcoming_open` can create an intent for existing
different adopted revisions; it reports changed even without a new configuration
revision. Otherwise equal normalized input is `rule_update_noop`. Only one pending
adoption intent exists per root. A matching request retains that intent (no second
intent); a different configuration while one is pending fails `semantic_conflict`,
`field=configuration`. An equal new-only request is a no-op, not cancellation of
the pending intent. Report old/new revision, scope, intent/high water and pending
coverage. Conflicts are resolved by ordinary explicit task edits/cancel/detach
followed by fresh reconciliation, never force overwrite (storage Section 5).

Retire requires `disposition=keep_following|detach_open|cancel_open`. Stop creation
atomically and persist the exact cleanup intent/high water. Keep-following can
finish an already-authorized adoption; detach/cancel supersede it with evidence.
Root source and existing children are not bulk edited in this authoring command.
Result includes `generation_stopped=true`, `cleanup_status=pending|complete`,
intent ID, high water and disposition. `complete` is allowed immediately only
when no child cleanup remains; never infer it merely from successful retirement.
Fresh same-disposition retirement on a current retired root is `rule_retire_noop`;
a different disposition fails `semantic_conflict`. No reactivation/switch surface.

Suppression exactly targets the current latest source-only cancelled generation.
Revalidate current assignment version, terminal task, cancellation proof, no
successor and veto atomically. Persist one immutable assignment-wide suppression
and next assignment state; touch no task, relation, policy, work or attempt. Result
includes suppression ID/attribution, assignment/generation/task, current assignment
change version and `successor_generation_id=null`. Fresh identical veto with current
facts is `assignment_suppress_noop`. If restoration won first, return stale without
veto or implicit successor cancellation; if suppression won first, a stale
restoration plan cannot change branches under its old expected facts. Ordinary
completion/manual cancellation/detach independently consume/veto assignments.

The closed `result` shapes for these writes are:

- create: `{rule,generation_started,materialized_work_count,delivery}`;
- update: `{rule,prior_rule_revision_id,new_rule_revision_id,adoption_scope,
  intent_id,assignment_high_water,delivery}`; intent/high water are null if none;
- retire: `{rule,generation_stopped,cleanup_status,retirement_intent_id,
  assignment_high_water,disposition,delivery}`;
- suppress: `{assignment,suppression,successor_generation_id,delivery}`.

All referenced projections are defined in Section 6. No-op/replay uses the same
result shape as its command, with the actually retained IDs and progress.

## 5. One-page reconciliation, budgets and execution time

Required specific fields: `related_task_rule_id`, `expected`, `limits`.
Optional: `cursor`. No explicit unbounded range, arbitrary mappings, per-task due,
force flag or client source proof. First-page evaluation and coverage range are
chosen by the server; later pages retain those exact selection facts in the cursor.
The current execution clock still controls new-generation/adoption cutoffs.

`limits` is a closed object with these canonical decimal fields; omitted fields
within it take these declared defaults and are hashed/bound as concrete values:

| Field | Default | Hard maximum |
| --- | --- | --- |
| `source_candidates` | 256 | 2048 |
| `assignments` | 32 | 128 |
| `mutations` | 32 | 128 |
| `proof_steps` | 10000 | 50000 |
| `lineage_hops` per proof | 64 | 256 |
| `work_rows` | 128 | 4096 |
| `response_bytes` | 262144 | 1048576 |

All limits have minimum 1. Normalized configuration at most 65536 UTF-8 bytes,
at most 32 effective reminder templates, 100 assignees. Every selector membership
test, generated candidate (including omitted/duplicate candidates) and traversed
lineage row consumes proof work; no hidden unbounded COUNT-from-seed loop. Existing
stricter owning caps win. A page work row is counted whether created, retained,
cancelled or protected-stale; no unbounded work-history array escapes the budget.
These are initial contract caps, not measured performance claims or new product
policies; changing maxima requires a versioned contract amendment.

Maintain two independent selection lanes per page:

1. Existing affected assignments/intent cleanup, ascending `assignment_seq`,
   regardless of horizon; bounded by `assignments` and global mutation/work limits.
2. Missing source candidates, ordered by original `(scheduled_fact,
   canonical_selector_bytes)`, bounded by `source_candidates` and remaining limits.

Always reserve capacity for the existing-assignment lane; a dense source cannot
prevent stale cleanup. Within a lane, blocked units are returned once under that
snapshot and advance the selection key without claiming they are resolved.
Conflicts remain indexed pending facts for a later changed-state plan; automatic
unchanged rescans do not dispatch new no-op writes. Across roots use the storage
queue's fair root continuation. No global convergence claim from a completed page.

Source selection uses expressed starts in `[evaluation,evaluation+horizon)`, plus
the bounded positive-offset catch-up interval where due is strictly future, plus
indexed moved overrides whose original slot falls outside that original interval.
The original enrollment predicate still applies, except the approved upcoming
catch-up rule. Explicit-start original lower bound always applies. Seek and
merge recurrence/rdate/override candidates under the total original ordering;
duplicate collapse happens before assignment reservation, not after task creation.
Range absence is never an exclusion proof. Detect unmatched slots after changed
components under the storage proof algorithm before creation.

If another whole unit fits, process it; if not, stop **between units** and return
`has_more=true` with exact covered/remaining selection. If a single task, proof or
its complete work evidence cannot fit the hard/requested limits, fail
`capacity_exceeded` at the narrow limit with no page writes. Do not commit a partial
task, discard a reminder, emit oversized results or return an unchanged cursor
as if progress occurred. A closed conflict/decision result is not a page error;
it may coexist with other successful units, but does not count as resolved coverage.

Read server UTC when entering the transaction and again immediately before commit.
The second reading revalidates every proposed first/restored task due and every
upcoming-open adoption (`due > commit_now`). If eligibility crossed the cutoff,
abort the page as `stale_evaluation`, no writes; a fresh plan skips the elapsed
missing generation or records a skipped adoption. A clock moving backwards within
the page also fails `environment_failure`, `field=clock`. Client `requested_at_utc`
cannot override either check. Reads/dry run use one coherent DB snapshot and one
evaluation time, and advertise `commit_cutoff_recheck_required=true`; they are not
reservations or permission to execute after expiry. No deterministic ID depends
on the later commit-clock sample. Compatible replay never samples it again.

Reconcile result requires: `rule`, `source_snapshot`, `selection`, `results`,
`policy_mappings`, `work`, `coverage`, `has_more`, `next_cursor`, `delivery`. Source snapshot contains
source item/version, recurrence set/revision/hash. Selection contains original
evaluation, current execution time, normalized limits, both lane start/end keys
and any intent high water. Every processed assignment/candidate has exactly one
`results` entry; use this branch precedence:

1. terminal/manual veto handling (`consumed`, `suppressed`);
2. explicit retirement cleanup (`cancelled`, `detached`);
3. confirmed source cancellation (`cancelled`);
4. unresolved proof/configuration/authority (`decision_required`);
5. initial or restoration generation (`created`, `restored`);
6. explicit adoption and/or source following (`adopted`, then `followed`);
7. freshness-only change (`refreshed`);
8. no mutation (`retained`, `skipped_due`, `skipped_independent`).

Entry shape: required `outcome`, `reason`, complete `selector`, `occurrence_key`,
`assignment_id` (null for unassigned/skipped/blocked candidate),
`generation_id` (likewise nullable), `actions`, `before`, `after`, `proof_ids`.
`actions` is a sorted unique enum array: `assignment_created`, `alias_reserved`,
`task_created`, `task_restored`, `task_rescheduled`, `configuration_adopted`,
`task_cancelled`, `binding_retired`, `assignment_consumed`, `veto_recorded`,
`witness_refreshed`, `intent_skipped`. An adopted-and-followed task has outcome
`adopted` and both applicable actions. `before/after` are null or exact assignment,
generation, task/version, binding/revision, adopted/desired revision and predecessor
references. No action claims a mutation merely observed from another command.
Before/after child references also carry actual `item_access_owner_id` and
`item_access_owner_revision`, never a catalog owner substituted for item evidence.
Task IDs and proof arrays must identify actual rows or explicitly marked dry-run
would-be rows; ambiguous candidates report the conflicting reference IDs in
`before`, not guessed after facts.

`policy_mappings` is an array of exactly `{assignment_id,generation_id,task_item_id,
policy_key,creation_token,notification_intent_id,notification_policy_id}` for the
complete active current **family-composed** policy set on processed existing/new
child tasks. Preserve independently authored policies under ordinary adoption/
copy-forward rules; inspect them through existing policy reads rather than invent
a composed key or creation token for them. Order by task ID then policy key; no
duplicate task/key pair among active mapped intents. Empty for no such policies. Tokens come
from actual immutable intent creation facts, not the current outer command unless
it created that intent. The real invoking command is the envelope `command_id`;
the mappings do not fabricate subcommand receipts. Count all mapping bytes under
the page response cap; never silently truncate the reminder set.

`work` has exactly `created`, `retained`, `cancelled`, `protected_stale` arrays of
existing work IDs, each unique, pairwise disjoint and sorted lexicographically.
Work classification follows schedule operations and successor policy/due rules.
`coverage` has separate `generation`, `assignments`, `adoption`, `retirement`
objects, each `{status,processed_count,remaining_known_count}`. Status is
`complete|partial|decision_required|not_applicable`; counts are decimal strings,
remaining count null when not knowable within the budget. Also return
`future_generation=eligible|waiting|source_exhausted|rule_retired|blocked`.
None of these mean the reminder was attempted or delivered.

`has_more` means additional bounded **selection** remains for this evaluation,
not that a future week exists or a blocked decision can be solved by polling.
Return terminal `next_cursor=null` when false. Stable empty/exhausted/retained
automatic plans write nothing; explicit reconcile may store its ordinary no-op
receipt. A semantic progress advance is changed work, not an idle coverage timestamp.

## 6. Read projections

`show` requires `related_task_rule_id`; optional `view` defaults `rule`.
The closed view union is:

- `rule`: no other fields; root/current configuration, immutable enrollment,
  source snapshot, rule/catalog freshness, intent/retirement and bounded progress
  metadata only. No hidden embedded history/assignment array or exact total count.
- `assignments`: optional `limit` (default 50, max 200) and `cursor`; ascending
  assignment sequence. No status filter in v1. Each row is the current assignment
  projection below, including terminal/suppressed history reservations.
- `assignment`: requires `assignment_id`, no cursor/limit; one current projection,
  exact suppression evidence and latest source-cancellation evidence, no history array.
- `generations`: requires `assignment_id`, optional `limit`/`cursor`; ascending
  generation index, with immutable predecessor/task/relation/binding and cancellation
  references. Ordinary task state and historical generation identity are separated.
- `proof`: requires `proof_id`, no cursor/limit; returns exactly that rule's
  immutable proof kind, complete payload and registered hash/ID, with referenced
  source revision/lineage IDs. Never follows an arbitrary caller mapping.
- `states`: requires `assignment_id`, optional `limit`/`cursor`; ascending
  assignment change version with complete immutable state/hash and attribution.

Paged reads use a fixed 1048576-byte maximum success envelope. Stop between rows
when the next complete row would exceed it, returning a nonterminal cursor even
before `limit` rows. A single oversized row fails `capacity_exceeded`,
`field=response_bytes`; never truncate a selector/configuration/proof. Single rule,
assignment and proof reads have the same bound. There is no implicit all-history
include. The `states` cursor purpose is separately named `states` and its after
key is the assignment change version.

An assignment projection has `assignment_id`, `assignment_seq`, `change_version`,
`assignment_revision_id`, `initial_selector`, `current_selector`, `occurrence_key`,
`generation_id`, `generation_index`, `task_item_id`, `task_item_version`,
`temporal_binding_id`, `temporal_binding_revision_id`, `relationship_id`,
`task_owner`, `item_access_owner_id`, `item_access_owner_revision`,
`adopted_rule_revision_id`, `desired_rule_revision_id` (null if none),
`disposition`, `reason`, `restoration_veto`, `suppression` (null or immutable
ID/actor/time/command evidence), `source_proof_id`, `source_snapshot`,
`predecessor_generation_id` (null for first), `successor_generation_id` (null if none).
Current source/task truth may be newer than the stored witness: report
`freshness=current|needs_reconcile|decision_required` and the observed versions,
not a read-time repaired state. Current task status is read from ordinary details.

Rule projection has exactly `related_task_rule_id`, `owner`, `rule_key`,
`source_item_id`, `recurrence_set_id`, `status`, `rule_revision_id`, `revision_index`,
`configuration`, `configuration_hash`, `change_version`, `catalog_generation`,
`enrollment`, `enrolled_at_utc`, `retirement_disposition`, `retirement_intent`,
`adoption_intent`, `progress`. Retirement/adoption properties are null if absent.
Intent projection has exactly `intent_id`, `status`, `kind`, `assignment_high_water`,
`scope`, `disposition`, `configuration_revision_id`; non-applicable scope/disposition/
revision values are explicit null. Progress is exactly the storage progress row's
non-root columns, including its closed coverage object, or null before any progress
row exists. Suppression projection is exactly `suppression_id`, `assignment_id`,
`target_generation_id`, `actor_subject_id`, `command_id`, `command_receipt_id`,
`suppressed_at_utc`; receipt ID must resolve to the original real receipt.
No unbounded aggregate recomputation; progress is snapshot-labelled, not asserted
as current whole-series completion. All read results identify their read snapshot.

`list` optional fields: `owner`, `source_item_id`, `status=active|retired|all`
(default active), `limit` (default 50/max 200), `cursor`. Owner omission means all
scopes under current trusted-local privilege, not the chat sender's groups. Sort
by full rule ID bytewise. Rows are rule summary projections: rule/owner/key/source,
status,current revision/change version,intent/progress freshness, not configurations.
Both paged reads return `catalog_generation`, normalized query, `has_more`,
`next_cursor`; no exact total. A different root/assignment target fails rather than
leaking a row from another rule. Missing target is `referenced_row_not_found`.
Successful reads use effects `rule_shown`, `rules_listed` respectively.

Single-view show result is exactly `{rule,read_at_utc,delivery}`,
`{assignment,read_at_utc,delivery}` or `{proof,read_at_utc,delivery}`. Paged show/list
result is exactly `{rows,query,catalog_generation,has_more,next_cursor,read_at_utc,
delivery}`. State/generation/proof rows expose the exact typed and canonical
payload columns defined in storage Section 3, rendering integers as decimal
strings and nullable SQL fields as explicit null; JSON payload TEXT is decoded
to its canonical object, not double-encoded. Rule-list summary fields are exactly
`related_task_rule_id`, `owner`, `rule_key`, `source_item_id`, `recurrence_set_id`,
`status`, `rule_revision_id`, `change_version`, `adoption_intent`,
`retirement_intent`, `progress`; no omitted configuration body is reconstructed.

## 7. Continuation, replay and freshness

Use purpose-separated HMAC-SHA256 cursors, not unsigned client-authored proof.
The existing configured cursor-key facility may supply key bytes, but the domain
is exactly `spine.recurring-related-tasks.cursor.v1`; no use of a facet cursor
as this family's token. `key_id` is non-secret. No new secret enters ledger rows.
Wire bytes are unpadded base64url canonical JSON, `.`, then unpadded base64url of
HMAC over UTF-8 domain, one zero byte, and the exact JSON bytes. Constant-time tag
comparison; reject noncanonical encoding, duplicates, overflow or unknown fields.
HMAC provides integrity, not encryption or caller authorization; do not put route
secrets or model-authored authority in a cursor.

Closed payload: `cursor_version` (the domain above), `canonical_json_version`,
`key_id`, `purpose` (`list|assignments|generations|states|reconcile`), `query` (all
normalized request selection fields/limits excluding cursor, command/actor/time
and expected), `catalog_generation`, `issued_at_utc`, `expires_at_utc`, `after`.
Reconcile additionally has `rule_change_version`, `rule_revision_id`, source
version/revision/hash, `evaluation_at_utc`, both source-range endpoints, immutable
intent/high water when selected. `after` is the exact rule ID, assignment sequence,
generation index or the two lane positions (sequence and original source tuple).
Expiry is issued time +3600 elapsed seconds; expiry equality is expired. Reconcile
expiry/evaluation remain the original first-page values, not sliding renewal.

Use the existing ledger instance ID in `query` for every purpose to prevent a
same-key token crossing ledgers. The key facility must exist before issuing a
nonterminal cursor; no random per-process key or silently unsigned fallback.
Missing key/configuration is `environment_failure`, `field=cursor_configuration`.
Key rotation may retain explicitly configured verification keys until expiry;
unknown retired key is invalid cursor and a fresh first-page read is supported.

Query/target/limit changes, tag or shape errors fail `invalid_request`,
`field=cursor`; expiration or changed bound generations/source/rule fail
`stale_cursor`. After a successful committing page, next cursor binds the **resulting**
catalog/rule freshness, not pre-commit counters; concurrent other changes still
invalidate it. Prior page successes remain committed. A successful page may
advance its selection key past a blocked unit reported under that snapshot,
without claiming that unit is resolved. A whole-page failure commits no key or
coverage advancement. No cursor itself authorizes any mutation.

Write comparison uses the existing command receipt model with this exact normalized
request and command identifier, including actor, requested time, expected facts,
configuration scope and cursor bytes. Do not compare freshly resolved current
catalog/route/source values before compatible replay; the original request and
stored resolution evidence determine replay. Incompatible reuse is
`command_id_conflict`. Fresh state/expiry checks follow compatible replay; old
receipt results remain immutable even after source edits, restoration or retirement.
Fresh command IDs require fresh expectations; they do not allocate another task
for a reserved slot or another successor for a predecessor.

Rule/assignment/version/progress changes and relevant source/target/route/policy
changes invalidate the catalog in the canonical transaction. Reads use one snapshot;
write pages use one transaction with cutoffs rechecked. SQLite contention returns
the existing environment/locking failure, not success or a partial page. Retry
with the **same command ID** after uncertain commit; after an explicit stale
response, reread/replan and submit a new command identity. Do not blindly resubmit
the old state with a different command ID.

## 8. Closed effects, reasons and error precedence

Successful terminal write effects are closed:

| Command | Changed effects | No-change effects |
| --- | --- | --- |
| create | `rule_created` | none (compatible replay retains original effect) |
| update | `rule_configuration_updated`, `rule_adoption_requested` | `rule_update_noop` |
| retire | `rule_retired` | `rule_retire_noop` |
| assignment.suppress | `assignment_restoration_suppressed` | `assignment_suppress_noop` |
| reconcile | `rule_page_applied`, `rule_progress_advanced` | `rule_page_decision_required`, `rule_page_noop` |

For update choose configuration-updated whenever a new revision is created,
otherwise adoption-requested when a new intent is written. For reconcile any
domain/assignment/intent outcome mutation yields page-applied; only coverage/queue
advancement yields progress-advanced; otherwise any decision-required result yields
decision-required, else noop. `changed` describes actual durable change except
would-be change in explicitly marked dry run. Replay keeps original changed/effect
with `replayed=true` and does not create another audit/receipt.

The closed per-entry `reason` enum is: `new_source_slot`, `source_restored`,
`source_moved`, `source_refreshed`, `source_excluded`, `source_occurrence_cancelled`,
`source_cancelled`, `source_archived`, `source_continuity_unresolved`,
`source_evidence_unavailable`, `task_done`, `task_manually_cancelled`,
`binding_detached`, `relationship_inactive`, `restoration_suppressed`,
`rule_retired_keep_following`, `rule_retired_detach`, `rule_retired_cancel`,
`configuration_adopted`, `configuration_conflict`, `configuration_invalid`,
`route_unavailable`, `disclosure_unavailable`, `due_not_future`,
`outside_enrollment`, `already_current`. Multiple issues use the branch precedence
in Section 5, then this enum's order for a tie; supplemental diagnostics use sorted
`{code,field,assignment_id?}` tuples, deduplicated exactly. These new names belong
only to this family; they do not extend frozen binding/work/attempt enums by prose.

First failure wins in this order:

1. Existing bounded runtime/schema/compiled-family admission:
   `environment_failure` (missing/mismatched installed dependency/schema).
2. Exact command/selector support: `unsupported_command` or
   `unsupported_contract_version` under existing envelope dispatch.
3. Request syntax, scalar/domain/closed-field validation: `invalid_request`,
   `unsupported_field`; first path by command field order in Sections 2–6, then
   lexicographic nested path. No lookup required for these checks.
4. Existing compatible replay / incompatible `command_id_conflict`.
5. Trusted-local write actor and referenced row resolution:
   `referenced_row_not_found` at the narrow reference field. No new privileged
   bypass or protected-web visibility rule is introduced.
6. Cursor integrity/query/expiry and cursor-bound generations: `invalid_request`
   or `stale_cursor`, `field=cursor`.
7. Explicit expected facts: `stale_version` at first mismatched field in the
   order rule change, rule revision, source version, recurrence revision, catalog
   generation, assignment version, then target generation/task identity.
8. Semantic validation: `semantic_conflict` for occupied key, retired-root update,
   incompatible pending intent/disposition, wrong target/cancellation cause,
   changed child owner, unsupported source basis/configuration or conflicting stored preimages;
   use its exact input field. A valid page's per-assignment proof/conflict outcome
   is decision-required, not this whole-page failure. Authoring an unavailable/
   mismatching detail selection uses delegated `rendering_disclosure_unavailable`
   at `configuration.notification_plan`, without task/owner/policy residue.
9. Complete-unit budget and source resolution/environment failure:
   `capacity_exceeded` at `limits.<name>`; `environment_failure` at
   `timezone_database_version`, `cursor_configuration`, `clock` or underlying
   storage field as applicable. No required unavailable proof becomes cancellation.
10. Commit-time eligibility/version recheck: `stale_evaluation` at
    `evaluated_at_utc` or `stale_version` at changed expected fact, rollback page.

Error message text is explanatory, not a hash-bearing compatibility fact. Code,
field, exact current-version evidence and no-write outcome are fixture oracles.
No-op writes do not bypass validation/expected facts merely because their desired
configuration or veto already exists.

## 9. Machine corpus and next gate

The source-only [machine companion](recurring-related-task-machine-contract.md),
[capability manifest](../contracts/recurring-related-tasks.v1.json) and
[fixture manifest](../contracts/recurring-related-task-fixture-manifest.json) now
codify the accepted shapes and offline examples, ratified on 2026-11-09 after the
bounded review chain. The corpus must retain closed request/response/shared types,
exact prerequisite manifest, canonical configuration/proof/state/ID and cursor
schemas, command capability declarations kept source-only until activation, and
computed fixtures. Do not advertise placeholders as implemented or publish broad
`additionalProperties:true` projections for unresolved delegated shapes.

Minimum computed oracles pair this file's wire receipts with storage Section 8:

1. Rule creation followed by multiple pickup tasks, distinct assignments, ordinary
   task/binding/policy identities, zero duplicate work on fresh reconcile IDs.
2. Moved selected occurrence, COUNT split copy, changed union, unsupported topology
   and missing evidence; same task only with positive one-to-one proof.
3. Source exclude/restore, suppression-first/restoration-first, exact due equality,
   pre-cutoff preview/late commit, retired keep-following without restoration.
4. Both edit scopes, root-equal/child-different adoption, complete reminder-set
   overlap/equal/non-overlap, pending-intent conflict, skip-overdue and gate release.
5. All retirement dispositions outside the horizon, completed/detached preservation,
   attempted work protection and independent post-detach reminders.
6. Every closed effect/reason and error-precedence branch; explicit empty/no-op,
   replay after cursor expiry/state changes, incompatible command reuse.
7. Every page budget, one-unit overflow rollback, post-commit continuation,
   concurrent invalidation, forged/cross-ledger/wrong-purpose/expired cursors.
8. Exact read views/history and SQL-free task→binding→policy→work→attempt traversal,
   no read repairs, no idle receipt/progress churn and finite old/dense recurrence work.
9. Exact recurrence-selector producer/reuse, multi-template/custom policy-key/token
   mappings, actual owner header/history/epoch before detail application, no
   creator/grant inference, rejected system child owner and ownership-transfer
   updates, owner-creation/presentation/work-stage rollback with unchanged old
   owner-less schedule-create behavior.

This accepted contract and its source-only corpus define representations, not runtime
behavior. Offline examples do not satisfy the actual transaction/concurrency/
migration/attempt-start proof families above. Ratification is the operator's
acceptance of this design; it is not a runtime test result, implemented-version
declaration or permission to deploy. The separately selected implementation plan
allocates these obligations; runtime execution still requires its own authorization.
