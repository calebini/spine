# R2 restoration and ordinary policy-successor follow-up

Date: 2026-11-11. Internal recurring-task candidate only; **R2 remains in progress**.

The operator requested committing the verified page/lifecycle increment and
continuing R2. That checkpoint is `fa16c98`; the unrelated `AGENTS.md` change was
excluded. The operator subsequently requested committing this verified
restoration follow-up before continuing R2. That checkpoint is not activation.

## Runtime changes

Restoration now takes the cancelled generation's actual current task facts rather
than reconstructing every detail from its original rule configuration:

- Copy title/summary/source reference/priority, actual assignees, explicit other
  roles, primary and other location references, exact archetype selection source
  and source reference, and the binding's actual adopted elapsed offset.
- Retain the original managed baseline and adopted rule revision separately. New
  rule configuration, newer profile revisions and changed defaults do not silently
  replace the assignment's selected configuration or individual exceptions.
- Copy exact facet entries into the new task's **first** version through the
  shared item-creation producer. Decode immutable definitions and revalidate fresh
  binding/reference availability; reject changed/superseded bindings or retired
  schemas instead of migrating, coercing, dropping values or allocating a repair
  item version. Rebuild the ordinary reference and typed-value projections using
  the existing facet storage authority and finalizer.
- Re-author the predecessor's complete active reminder set on the new item,
  preserving individual timing, late handling, recipient/destination and selected
  presentation. Disabled reminders are not reintroduced from the template.
  Revalidate each current route and exact disclosure selection after the actual
  owner header exists; create no approval or grant. Include independent policies'
  grace windows in bounded work materialization.
- Preserve family policy keys and the ratified `generation_id + ':' + policy_key`
  creation convention. Independently authored reminders are not assigned an
  invented family key or included in family `policy_mappings`. Their fresh intent
  seed delegates to existing `spine.command-id.v1`: prefix/role `notification`,
  command `schedule.related_task_rule.reconcile`, command ID equal to the new
  generation, path `/restored/independent/` plus the predecessor intent ID. Existing
  notification normalization derives the new item-scoped intent/policy identities.
  A regression checks the actual seed independently through the owning derivation.
- Copy the exact predecessor application/profile revision and immutable composition
  provenance onto the new item, linking only its newly authored active policies.
  The real outer command remains actor/audit/receipt attribution. Predecessor task,
  policy, application, work and historical records are not rewritten.
- A blocked existing-assignment unit now retains its assignment/generation and
  before/after references after its tentative writes roll back; it no longer
  presents that existing assignment as an unassigned missing candidate.

No new public command fields, family contracts, schema objects or migrations are
introduced. `TaskDraft`/the internal task creation primitive accept an explicit
initial facet snapshot; ordinary callers still default to an empty snapshot, and
public request schemas continue to reject undeclared fields.

## Narrow shared-writer prerequisite

The new real-policy tests exposed an existing direct edit/disable seam: ordinary
copy-forward creates this successor version's profile-application links, then
direct policy mutation replaces the copied policy row without retargeting those
links. Commit fails its FK check. The existing successor helper now retargets only
the **uncommitted successor version's** application links to its replacement policy
while retaining the logical intent. It does not update any historical version.

This is covered both by the recurring candidate and a separate ordinary schema-19
profile create → direct edit → direct disable test, which checks every historical
application link and FK integrity. It is not R3's broader all-writer integration.

## Actual verification

- Seven new restoration tests cover repeated generations with changed family and
  independent reminders; independent grace eligibility; disabled reminder
  retention; older rule/profile pins; exact roles/location/archetype/facet copying;
  unavailable facet decisions; eight-facet first-version typed indexes; and
  rollback after task, ownership-state, owner, binding, policy, work, audit and
  receipt stages. Tests use disposable ledgers, no adapter invocation or sends.
- A separate released-schema profile test proves the narrow direct-writer fix.
- Final affected command/page/bootstrap/notification/profile selection: **82 tests,
  OK**, 29.174 seconds. Shared producer/finalizer parity: **one test, OK**, 2.445
  seconds. Five touched modules pass focused strict typing; touched runtime/tests
  pass Ruff. Initial full regression: **1,389 tests, one inventory failure and one
  skipped**. Its strict equality test correctly required registering the new
  restoration policy caller in the compiled writer inventory. The caller and its
  proof-test module are now registered; no test/verifier was weakened. Strict
  inventory plus producer parity recheck: **two tests, OK**, 2.460 seconds.
- Final full regression after the inventory correction: **1,389 tests, OK
  (one skipped)**, 337.050 seconds. Known non-fatal read-budget finalization and
  timezone-substitution diagnostics appeared, as in preceding full runs.
- Frozen web-contract copies, 361 local documentation targets and diff hygiene
  pass. The unrelated `AGENTS.md` SHA-256 is unchanged. No wheel qualification or
  public activation is claimed by these source-tree tests.

## Remaining R2 work

This closes selected restoration behavior, not the complete R2 contract family.
Continue the remaining proof/hop/candidate and read-budget adversaries; exact
reference/cursor/error precedence; intent selection/coverage and adoption races;
historical replay after later changes; wider continuity/novelty and lifecycle
cases; and broader provable calendar-day reminder lead support. Additional
ordinary task-detail customization and individual offset/disclosure/reference
invalidation cases still require explicit implementation/coverage assessment.
Do not count these selected passing tests as closing an entire RRT obligation.

Public registry/package/schema activation stays in R4, and automatic generation
and all-writer/attempt safety stay in R3. No live ledger, deployment, push, adapter
execution or external audit was performed.
