# Recurring-source related tasks

Runtime 0.12.0 / schema 20, trusted-local CLI only. Full release qualification
is tracked in [SPINE-095](BACKLOG.md#spine-095--r4-recurring-task-activation-and-release-verification).
The [command specification](../specs/recurring-related-task-commands.md) and
[machine descriptor](../contracts/recurring-related-tasks.v1.json) own exact shapes.

## Pick the right operation

For “Pick up Joe 90 minutes after every science class,” enroll a
`schedule.related_task_rule.create` rule. Each source occurrence gets a normal
task, a `part_of` relation, its own follow-source binding and optional reminders.
The rule is not another event and is not an instruction to clone the event.
Use `schedule.related_task.create` when only one selected occurrence needs a task.
Existing item, schedule, relation, facet, profile and people commands remain valid.

## Local workflow

The CLI resource is `schedule related_task_rule`; its subcommands are `create`,
`update`, `retire`, `reconcile`, `list`, `show`, and `assignment suppress`.
Use `contract_version=spine.recurring-related-tasks.v1` in every request.
Writes require a fresh unique `command_id`, active `actor_subject_id` and
`requested_at_utc`. Preserve the entire original request when retrying a command.

Discover the source through public readback. `item.occurrences` supplies current
source version, recurrence set/revision and exact selectors. Creation names the
rule owner and generated-task owner explicitly. The example uses
`offset_basis=elapsed`, `offset_seconds=5400` and an ordinary task template;
one custom policy with `offset_seconds=-600` supplies the reminder.
Delivery recipient and destination are independent of the task owner/assignee.
Supply an explicit bounded materialization range or `mode=none` deliberately.

Creation authors the rule; it does not synchronously create all pickups.
Use the configured worker, or call bounded `reconcile` pages explicitly.
Read `show` before a fresh mutation and copy the exact rule change/revision,
source item version, recurrence revision and catalog generation into `expected`.
For suppression also pin the assignment change version and current generation/task.
Never substitute occurrence ordinal or task title for these identities.

When `has_more=true`, carry `next_cursor` and the same limits into the next page.
After a committing page, read fresh expected facts. A stale/expired cursor means
start a fresh walk; it does not mean recreate tasks or forget reservations.
Use `show` views for assignments, individual assignment, generations, states and
proofs; all history is bounded and no read silently repairs an assignment.
Stable manual no-ops have receipts; idle automatic observations do not.

## Lifecycle and decisions

Moving a class updates its still-governed pickup. Excluding/cancelling a class
cancels its still-open pickup. Reinstatement may create a linked successor only
when source-only cancellation and all restoration conditions are proved.
Completion, manual cancellation, detach, suppression and changed ownership remain
independent operator intent. Inspect `decision_required`; do not force an overwrite.
`assignment suppress` vetoes restoration without deleting the existing task/history.
Individual customizations are preserved by three-way rule adoption.

Rule edits declare their adoption scope. Retirement stops new generation and
requires `keep_following`, `detach_open` or `cancel_open` for existing tasks.
Follow the returned intent/coverage state; one page is not global completion.
Protected leased/attempted work and historical sends cannot be undone. Fresh
attempt admission checks current source, task, assignment and policy evidence.

## Worker configuration and safe receipts

Use `spine-worker --scheduler-actor-subject-id SUBJECT --facet-cursor-config PATH`,
or the corresponding `SPINE_SCHEDULER_ACTOR_SUBJECT_ID` and
`SPINE_FACET_CURSOR_CONFIG` environment variables. The actor must already be active;
there is no fallback to the first person/owner. The cursor file is the existing
private, operator-owned facet-key configuration, bound to this ledger instance.
Recurring cursors use a separate authenticated domain, not interchangeable facet
tokens. Never put secrets in requests, receipts or chat.

If authoring used named delivery defaults, give the worker the same explicit
`--delivery-target-default KEY=DELIVERY_TARGET_ID` mappings. A changed/inaccessible
route blocks that generation rather than silently choosing another destination.

A worker with rules but no valid recurring configuration fails startup DOWN/not-ready
before processor construction. Invalid actor/key pairs likewise fail closed.
An ordinary worker with no rules may still run without this configuration; if
rules are enrolled later, configure/restart it before expecting generation.
The unconfigured adapter refuses a recurring reconcile cycle rather than silently
skipping it. No new public HTTP endpoint or web permission bypass is provided.

Generating an owned task can initialize native `trusted_local` ownership state;
this creates no realm, login account, membership or access grant. If web access is
later wanted, the existing local `web_access.plan` / `web_access.apply` commands
accept `spine.trusted-web-provisioning.v3` with explicit realm, current epoch and
operator choices. Inspect `can_apply` before applying. The actor and target
operator subjects must already exist. V3 preview is nonpersistent; no scheduling
command silently promotes a ledger to web access. Existing v1/v2 requests retain
their original shapes and do not implicitly perform this promotion.

Receipts distinguish authored rule, generated tasks, materialized reminder work,
and actual delivery attempts. `delivery=not_attempted_by_command` is not “sent.”
Use `schedule.show` on generated tasks and `agenda.show` for the ordinary evidence
surfaces; never repair a missing reminder by duplicating the task.
