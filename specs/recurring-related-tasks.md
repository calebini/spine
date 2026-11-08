# Spine Recurring-Source Related Tasks

Status: Draft v0.1.0-draft.7 — specification only; not ratified or implemented

Created: 2026-11-07

Scope: One ordinary task per selected occurrence of a recurring source event, with explicit temporal following, bounded generation and per-task reminders

## 1. Purpose and approved direction

The representative intent is:

> For each occurrence of Joe's Science Class, create a Pick up Joe task due 90
> minutes after the class starts. Follow that occurrence if it moves, and remind
> me ten minutes before pickup is due.

The class remains one recurring event. Each pickup is a separate, independently
completable **task**, not another event, a second recurrence stream, a virtual
task or a notification masquerading as a task.

The operator has approved this lifecycle rule: a **confirmed exclusion or
cancellation of a class occurrence automatically cancels its still-open,
rule-governed pickup task**, including eligible unattempted reminder work. A
confirmed cancellation of the source event applies the same rule to its governed
open tasks. Completed tasks and attempted/delivered history remain preserved.

The operator also approved **automatic reinstatement without a confirmation
exchange** when the same source occurrence is proven restored and the pickup was
cancelled solely because of its source. Section 8.1 defines the eligibility guard
and linked-successor behavior. Operator completion, cancellation, detach and
explicit suppression are never undone by this automation.

Enrollment starts with upcoming source occurrences by default, with an optional
explicit starting occurrence. Task generation uses a configurable eight-week
rolling horizon by default. D-02 is approved; Section 7.1 records these choices.
D-03 is approved: bounded catch-up may create missing tasks while their derived
due time is still ahead, including when the class has already started. It never
automatically manufactures a newly overdue task or bypasses reminder late handling.

D-04 is approved: rule configuration edits have an explicit scope. The normal
operator choice updates upcoming open governed tasks and future generation; a
narrower choice affects only newly generated assignments. Existing individual
exceptions and terminal history remain protected under Section 7.6.

D-05 is approved: retirement requires an explicit choice to keep existing tasks
following, detach them or cancel outstanding open governed tasks. It always stops
new generation and reinstatement successors. Section 8.2 defines the distinction.

The selected product decisions in Section 14 are approved, but the full draft
still requires contract closure and review. MUST and MUST NOT below express
proposed contract requirements, not an implemented runtime
claim. This draft does not reserve a ledger schema number, register a runtime
family, add machine schemas or expose a command or HTTP route.

## 2. Authority and preservation

This leaf owns series-rule enrollment, generated-task assignment, generation
coverage and series-scoped lifecycle reconciliation. It delegates:

| Owner | Preserved authority |
| --- | --- |
| [Ontology](ontology.md) | Ordinary items, task status, anchors, relations and their identities |
| [Recurrence](recurrence.md) | Source occurrences, original/expressed time, exceptions, selectors, lineage and provenance |
| [Relative temporal bindings](relative-temporal-bindings.md) | Concrete due derivation and one-task following, snapshot and detach behavior |
| [Schedule creation](schedule-create.md) and [operations](schedule-operations.md) | Item authoring, version copy-forward and notification-work classification |
| [Notifications](notifications.md) | Policy, opportunity and work identities, late handling and attempt-start eligibility |
| [Notification profiles](notification-profiles.md) | Reusable configuration and explicit snapshot application |
| [People and responsibility](people-and-responsibility.md) and [permissions](permissions.md) | Ownership, participation, assignment, authority and disclosure |
| [Command contract](agent-command-contract.md) | Validation, dry run, replay, audit and receipt conventions |
| [Storage and atomicity](STORAGE_ATOMICITY_SPEC.md) | Ledger transactions, schema admission and migration discipline |

The new family MUST NOT silently broaden the implemented one-task binding v1
contract. In particular, ordinary v1 `source_unresolved` remains decision-required;
the new automatic exclusion behavior needs the positive proof defined here.
No external executor, calendar, agent or transport becomes schedule authority.

## 3. Scope

The proposed first family supports:

- one existing recurring, scheduled event as each rule's source;
- one named task template per rule, producing at most one current governed task
  per resolved source-occurrence assignment, with linked historical generations
  when automatic reinstatement is eligible;
- signed elapsed-seconds derivation from expressed `event_start` to `task_due`;
- selected-occurrence `follow_source` bindings on ordinary nonrecurring tasks;
- zero or more independently authored rules on the same event: pickup and
  preparation, for example, are different rules, not duplicates;
- optional per-task reminders using the existing policy/delivery machinery;
- bounded automatic generation and lifecycle reconciliation;
- complete task-level completion, cancellation, detach, readback and history; and
- explicit source-lineage handling without heuristic remapping.

Non-goals are independent target recurrence, general workflow execution, event-end
or date-only derivation, business/calendar-day offsets, arbitrary nesting of
generation rules, adopting existing tasks by title, implicit assignment/routing,
bulk mutation inside a source edit, and any new sending or enrichment mechanism.
The initial surface is trusted-local. No web-registry expansion, authenticated
admission design or access-control bypass is introduced by this draft.

## 4. Model and invariants

### 4.1 Series rule

A logical rule names exactly one source event and recurrence set. Minimum facts:

- stable `related_task_rule_id`, explicit owner scope and caller-chosen rule key;
- immutable source item ID, source role `event_start` and recurrence-set ID;
- immutable creation actor, command and timestamp;
- lifecycle `active` or `retired`, with immutable explicit retirement disposition
  and completion/progress evidence when retired; and
- a current immutable configuration revision.

An owner-local rule key identifies the operator's intended rule independently of
its title. Reusing an occupied key is a conflict, not a second rule. Retired keys
and historical assignments are not silently recycled. Distinct explicit keys may
describe similar tasks; the engine MUST NOT merge operator intentions by prose.

The configuration revision records a concrete task template, `offset_basis=elapsed`,
canonical decimal `offset_seconds`, a reminder/delivery snapshot, an effective
generation boundary, finite generation-window configuration and their version facts.
The template omits due anchors and recurrence: the source supplies due time and
the child does not acquire a recurrence set. Initial task state is `open`.

Every revision is immutable. Configuration changes are explicit and versioned,
with an explicit adoption scope under Section 7.6. Advancing the rule's current
revision does not itself rewrite a child's adopted revision or ordinary item facts.
No mutable catalog pointer may silently rewrite the meaning of an existing child.

### 4.2 Generated assignment

One durable assignment connects the rule to one semantic source-occurrence slot.
It owns:

- stable assignment ID and rule ID;
- original source selector/key and original scheduled fact;
- every accepted successor selector/key with explicit continuity evidence;
- ordered task generations, each naming its task ID, `part_of` relation ID and
  logical temporal-binding ID, with at most one current generation;
- exact source-caused cancellation evidence and any linked restoration successor;
- explicit assignment-level restoration-suppression evidence, including actor,
  command, timestamp and the task generation against which it was recorded;
- the rule revision and source item/recurrence/provenance facts used to create it;
- later immutable observations and source/target version references; and
- retained disposition evidence for a completed, cancelled, detached or unresolved
  assignment, including whether cancellation came from the source or the operator.

Assignment disposition is not a second task-status authority. Current task truth
still comes from ordinary task details: `open`, `done` or `cancelled`. Source
resolution and binding state still come from their owning contracts. Assignment
evidence says why a slot was generated, followed or suppressed, not whether an
ordinary task is secretly complete.

### 4.3 Core guarantees

1. The source recurrence is the only recurrence authority. Never copy its rules
   into a pickup recurrence and attempt to keep two recurrence streams aligned.
2. A generated task owns an ordinary immutable due anchor. A source move becomes
   a new task version, not a read-time join changing historical due time.
3. Structure alone never causes behavior: `part_of` is not a generation rule.
4. A rule cannot acquire a second assignment for an already reserved source slot
   merely because a command ID, recurrence revision, page or generation window changed.
5. Terminal or detached assignments retain their reservation. Scanning again does
   not recreate a pickup the operator has completed, cancelled or detached.
   A proved source-caused cancellation may instead receive one linked successor
   generation under Section 8.1; it does not acquire a new assignment.
6. Child creation and its assignment are atomic. There is no committed child with
   an unrecorded generation origin, or reservation claiming a missing child.
7. Authored rule, generated tasks, expanded opportunities, materialized work and
   delivery are separate evidence. None of these commands sends a notification.
8. A source edit never performs unbounded synchronous fan-out. Stale work is gated
   immediately; bounded reconciliation subsequently repairs canonical child truth.

## 5. Source-occurrence identity and continuity

Generation consumes canonical, duplicate-collapsed source occurrences. If several
recurrence sources union into one occurrence, this rule generates one task, not
one task for each contributing rule or rdate.

An `occurrence_key` is revision-independent **only while its complete selector
remains equal**. The selector includes original scheduled facts, segment reference
and semantic rule/rdate sources. A move override can preserve the original slot
while changing expressed time; a rule edit, segment split or replacement can
change the selector. Neither the current expressed time nor ordinal is a safe
assignment identity.

The required resolution order is:

1. Resolve an exact retained selector/alias to its existing assignment.
2. Otherwise consume only explicit, current, unambiguous recurrence lineage that
   proves a predecessor-to-successor occurrence correspondence.
3. Reserve the accepted successor selector as another alias of the **same**
   assignment before changing a task or creating work.
4. If no prior assignment or conflicting predecessor exists, a positively proven
   new occurrence may create an assignment under the generation boundary.
5. If continuity is ambiguous, missing or contradictory, report decision-required.
   Do not pair by nearest time, weekday, title, page position or ordinal.

After a source-rule edit, an unmatched selector is not by itself a new occurrence.
Candidates that might continue an existing assignment must remain decision-required
until explicit lineage or positive novelty evidence settles that question. A
proven new rdate or an unchanged rule's newly reached future slot can establish
novelty; missing correspondence after a changed rule cannot. Do not create a new
task merely because the old selector was not found in a reservation lookup.

Recurrence's existing key/child lineage is not a claim that every series edit
already carries a complete per-occurrence correspondence. Before runtime
activation, the contracts MUST define which edits provide sufficient evidence and
any required recurrence-owned extension. Unsupported continuity remains explicit;
it must not silently cancel the old pickup and manufacture another one.

Selector reservations are unique per rule across current and historical aliases.
Two assignments cannot claim the same selector. One-to-many or many-to-one lineage
does not authorize automatic task merging, splitting, cancellation or recreation.
Conflicting alias claims fail atomically. Replacing the source recurrence set or
turning the source into a nonrecurring event requires explicit resolution; there
is no automatic enrollment in a different source series.

## 6. Time and reminder derivation

For each current resolved occurrence:

`task_due_utc = expressed_source_start_utc + offset_seconds`

Elapsed arithmetic, offset bounds, local due expression, DST behavior and concrete
timezone-database pinning follow relative bindings Section 5.5. An unresolved or
unsupported source time basis is rejected rather than interpreted in host timezone.
There is no caller-supplied replacement due timestamp and no rounding of seconds.

The task reminder targets that task's own `task_due`, not an anchor on the class.
For the representative template:

| Fact | Value |
| --- | --- |
| Source start | Saturday 11:30 in the source's authored timezone |
| Task offset | `5400` elapsed seconds |
| Task due | 13:00 for this occurrence |
| Reminder offset | `-600` elapsed seconds from the task due |
| Reminder opportunity | 12:50 |
| Source moved to 12:00 | Same open task due 13:30; reminder at 13:20 |

Generation selection is defined over source occurrences; notification selection
is defined over the derived task opportunities. The implementation MUST account
for both offsets when translating a delivery horizon into source coverage. A
reminder after a class starts is not exhausted merely because that start is past.
Likewise a negative task offset or early reminder may need source occurrences
beyond the current notification horizon.

Task generation horizon and work-materialization horizon are independent finite
facts. Materializing no work outside the selected work range must not erase the
task or falsely mark its reminder as delivered. Existing policy `late_handling`
and grace windows remain authoritative; this family creates no catch-up send bypass.

Copied notification policies must be the exact successor task version's policies
before replacement work is created. Materialization against predecessor due times
or predecessor policy IDs is nonconforming. Profiles/rendering selections are
explicit snapshots under their current owners; rule creation or generation does
not grant disclosure approval or upgrade existing tasks to a newer catalog revision.

## 7. Generation and reconciliation

### 7.1 Enrollment and boundaries

Creating a rule does not enumerate all past or infinite future occurrences. It
records an explicit effective boundary and a finite rolling generation policy.

The approved enrollment choices are:

- **Default, upcoming from enrollment:** Persist the enrollment UTC instant once.
  An unassigned source occurrence qualifies for the start boundary when its
  currently resolved expressed start is at or after that instant. A class later
  today qualifies if it has not started. Do not replace the recorded enrollment
  instant with each scheduler evaluation or require an original scheduled fact
  to be future when an occurrence was explicitly moved into the future.
- **Explicit starting occurrence:** Resolve and record the exact selected source
  occurrence, its selector and original scheduled fact. This sets an inclusive
  `original_schedule` lower bound for generation. Later source edits use the
  continuity rules rather than guessing a replacement starting occurrence.

The boundary controls first-time enrollment, not the identity of a generated
assignment. Already-generated tasks remain governed if a source move crosses
that boundary. An explicit past starting occurrence is not, by itself, authority
for historical task backfill.

The default rolling horizon is eight weeks: 56 elapsed 24-hour days, with an
exclusive upper bound measured from the current reconciliation evaluation instant.
It is configurable within explicit finite hard limits. Resolve and persist the
concrete chosen horizon in the rule revision, including when the default is used.
As evaluation advances, bounded reconciliation replenishes the window; it does
not wait for all currently generated tasks to complete. Task generation beyond
the window remains pending rather than creating an infinite future upfront.

Current expressed source time determines membership in the rolling generation
window; stable original identity still determines assignment uniqueness. Moving
an assigned occurrence out of the window or shortening the configured horizon
does not delete, cancel or stop following its existing task. Readback must report
the configured horizon, evaluated coverage and incomplete/pending generation so
an operator can distinguish a future class from an already-generated pickup.

The accepted horizon must allow tasks to be generated before their earliest
configured reminder becomes due, accounting for both source-to-task and
task-to-reminder offsets. An incompatible configuration must be surfaced, not
silently widened beyond its bound or accepted with silently missed reminders.
Exact cadence/budget admission checks belong in the machine contract.

Section 7.5 defines the approved catch-up exception for an already-started class
with a future task due. It does not reset the recorded enrollment boundary or
authorize historical overdue-task backfill.

A rule may legitimately have no children in its current window. Readback reports
whether that means no selected occurrences, incomplete coverage, exhausted source,
retired rule or a decision-required gap. It must not collapse these into success
meaning all future pickups exist.

The generation scheduler discovers active rules independently of source reminder
policies. A class with no notifications can still generate pickup tasks with
notifications. The scheduler reuses the existing Spine reconciliation path under
Tickerd; no second daemon kernel is introduced.
Retired rules with outstanding disposition work and retained follow bindings are
also discoverable for bounded maintenance under Section 8.2; they are never
eligible for new assignments or reinstatement successors.

### 7.2 Two sets must be considered

Each bounded plan considers:

1. currently eligible source occurrences in the generation range, to find missing
   assignments or eligible source-cancelled assignments needing reinstatement; and
2. existing assignments affected by source, rule or target changes, regardless
   of whether their occurrences still fall inside that generation range.

Absence from one range, page, budget-limited expansion or completed source stream
is **not** evidence of exclusion. A task moved beyond the horizon is still the
same task and must not be cancelled for leaving the window. Cancellation of a
series must eventually visit all its governed open assignments, including distant
ones already generated by an earlier, longer horizon.

Existing assignment validation must use selector-local recurrence proof rather
than expanding every occurrence since the series seed. If required continuity or
timezone evidence cannot be resolved within the budget, fail closed and expose
the gap; do not interpret the budget failure as source removal.

### 7.3 Bounded pages and coverage

Every operation has explicit finite source-range, source-candidate, assignment,
mutation and expansion-work limits. The accepted hard maxima and deployment-neutral
default recommendations must be closed in the machine-contract step; a date range
alone is not a work bound for a dense or old recurrence.

An explicit reconcile command applies **one bounded page for one rule**. The page
is atomic; the complete series is not. Selection and ordering must be deterministic,
and incomplete coverage must return a continuation with `has_more` and the covered
range/selection. No successful page may hide an over-limit partial child, omit a
conflict, or claim global convergence. Failure before commit changes no row in
that page; previously committed pages remain valid historical facts.

Continuation semantics must bind the rule revision, source item/recurrence
freshness, original selection/evaluation facts, limits and assignment generation.
A committing page returns a continuation based on its **post-commit** generation,
so its own writes do not immediately invalidate the next page. Concurrent relevant
changes invalidate continuation; restart fresh discovery without discarding prior
assignments. The exact format and expiry are machine-contract requirements, not
an invitation to use unsigned client-authored proof or offset pagination.

New-task generation, affected-assignment reconciliation and cancellation progress
must be separately observable and fairly scheduled. A dense series or repeatedly
blocked assignment may not permanently starve another enrolled rule. Existing
completed/detached assignments are retained but are not rescanned every tick solely
because their history exists.

### 7.4 No-op suppression

Discovery and planning are read-only. A stable automatic cycle with no missing
assignment, stale binding, lifecycle transition or work repair writes nothing
durable: no zero-selected receipt, audit, heartbeat row or coverage timestamp.
Coverage is derived from stable evidence or advanced only when semantic coverage
actually changes, not on every observation.

Before dispatching a receipt-bearing mutation, automatic scheduling rechecks the
complete bounded plan against current facts. Explicit operator reconciliation
retains existing command no-op/replay receipt semantics. A race can cause a valid
explicit command to become a no-op, but it cannot justify repeated idle dispatch.
Failures and unresolved decisions remain observable without receipt churn.

### 7.5 Catch-up while the task is still ahead (D-03 approved)

Late enrollment and scheduler downtime use the same missing-task eligibility rule:
create a first task, or an otherwise eligible restoration successor, only while
its derived due instant is **strictly later** than the current evaluation instant.
At equality or after the due instant, do not automatically create a new task.
This predicate also applies to a future class with a negative offset whose task
due has already passed. Existing task/assignment suppression and source-actionability
checks still apply; a future due alone is not enough to authorize creation.

For default upcoming-from-enrollment rules, a started source occurrence whose
task due is still future is an explicit bounded exception to the source-start
boundary in Section 7.1. For example, enrollment at 12:15 can create a 13:00 pickup
for an 11:30 class. An explicit selected starting occurrence still limits the
eligible original slots: catch-up does not include occurrences preceding it.

Derive the finite source lookback needed from the source-to-task offset and
current task-due selection, subject to the accepted range/candidate/work budgets.
Do not scan back to the series seed or create an unlimited historical backlog.
Budget exhaustion is incomplete coverage or a structured capacity failure, not
permission to claim the skipped tasks were created. A task missed because its
due passed is distinguishable from a completed, cancelled or suppressed task;
recording or observing that fact must preserve idle no-op suppression.

Notification creation/materialization remains independent from task creation.
After a missing task is created, an already-passed reminder is eligible only if
its existing policy's `late_handling` and grace window permit it. Otherwise omit
that expired opportunity under the notification contract, while retaining the
future-due task and any other eligible reminders. No forced immediate send,
extended grace window, altered reminder offset or claim of delivery is allowed.

For a class at 11:30, pickup at 13:00 and reminder at 12:50:

| Evaluation | Missing-task result |
| --- | --- |
| 12:15 | Create the future-due pickup; the 12:50 reminder follows ordinary materialization rules |
| 12:55 | Create the pickup; the past 12:50 reminder qualifies only under its existing late policy |
| 13:00 or 13:15 | Do not automatically create a new pickup or its historical reminder |

The committing transaction must revalidate future-due eligibility against current
execution time. A stale caller timestamp or a preview taken before the cutoff
cannot authorize task creation after the due time. Exact clock/freshness validation
and deterministic preview/cutoff fixtures must be closed in the machine contract.
Compatible replay still returns the original receipt and never re-executes creation.

This policy applies to **missing generations**, not existing overdue tasks. An
already-created pickup remains an ordinary open overdue task until an explicit
supported completion/cancellation action or a proved source lifecycle transition.
Do not delete it, complete it, cancel it or create a duplicate merely because
catch-up would now refuse first creation. Its existing reminder/retry eligibility
continues to follow the notification owner's late-handling and attempt rules.

### 7.6 Explicitly scoped template changes (D-04 approved)

An edit creates a new immutable rule configuration revision. Its request MUST
state one of two adoption scopes, using final enum names defined by the machine
contract:

- **Upcoming open governed tasks and future generation:** New assignments use
  the new revision. Existing current task generations are selected for bounded
  adoption only when still open, still governed and due strictly after the
  current evaluation instant. Completed, cancelled, detached, suppressed and
  already-overdue tasks are outside this scope.
- **Newly generated assignments only:** New assignments use the new revision;
  existing assignments keep their adopted revision and configuration. They still
  follow source moves using that adopted offset. This scope does not silently
  cancel an earlier, explicitly recorded pending adoption.

The first is the recommended operator/agent choice for an instruction such as
"make all future pickups 105 minutes after class and remind 20 minutes before."
It is not an omitted-field runtime default: the normalized write must explicitly
name the intended scope. Choosing the second scope must be reported honestly,
including that already-generated tasks may retain old settings for the entire
current generation horizon. Clear operator intent can select a scope directly;
no asynchronous approval exchange or conversation engine is required.

The edit records the exact new configuration, old/new revision IDs and adoption
intent atomically, not an unbounded mutation of all generated tasks. Bounded
reconciliation creates ordinary successor item/binding/policy versions for each
eligible existing task and records its actual adopted revision. Until then,
readback distinguishes requested configuration from applied configuration,
pending coverage, skipped tasks and conflicts. Selection and future-due/governed
eligibility are revalidated at each committing page; tasks becoming terminal or
overdue before adoption are preserved and reported as skipped, not overwritten.

Per-assignment desired revisions must be explicit and replay-safe. Later edits
cannot silently replace an earlier pending adoption or apply a task against the
wrong expected adopted revision. Exact ordering/conflict and continuation rules
must be closed in the machine contract; no inference from the root's latest
pointer is sufficient to authorize a child mutation.

Use the task's last adopted configuration as the comparison baseline for explicit
individual edits. Compare normalized rule-managed fields against both current
child truth and the requested change. Preserve non-conflicting customizations;
if a rule edit overlaps a different individual value, surface a conflict and
leave that task's content/adopted revision unchanged. Equality with the requested
new value is not a conflicting override. Do not guess from actor labels or treat
an ordinary source-follow reschedule as a manual override. The field comparison,
complete reminder-set semantics and exact override-resolution path must be
defined before implementation; there is no implicit force-overwrite mode.

When a selected pending edit affects due time, reminders or delivery authority,
attempt-start checks must account for the desired-versus-adopted configuration
so obsolete work cannot send merely because the old binding remains source-fresh.
Conflicts in such changes remain visible and fail closed until explicitly
resolved. Assignments deliberately excluded by the new-only scope retain their
valid adopted configuration; they are not made stale by a newer root revision.

Successful adoption reconciles eligible unattempted work under the existing
notification rules and preserves all attempted/in-progress/terminal evidence.
It does not send, extend grace windows or rewrite old receipts. Task identities
and assignment identities remain stable; a template edit is not reinstatement
and does not create a replacement task generation. A configuration-only no-op
does not create a revision; an explicit scope request to converge existing tasks
must still distinguish required adoption from an actual no-op.

Editing a reusable notification profile or rendering definition does not itself
update the rule or its tasks. Adopting an exact new catalog revision is an explicit
configuration edit with these scopes and the existing route/disclosure checks.
Source item, recurrence-set and enrollment identities cannot be changed through
a template-edit convenience. A restored successor continues its assignment's
adopted configuration under Section 8.1; it is not an unassigned new task that
automatically receives the latest root revision.

## 8. Lifecycle behavior and exception proof

Apply target terminal/detach state before deciding what a source change may do.
An unrelated title or people edit is not a detach; a generated open task remains
governed unless an explicit binding/relationship lifecycle action relinquishes it.

| Current fact | Proposed required disposition |
| --- | --- |
| Same source occurrence, different expressed start | Move the same open task, record a new due/binding revision and reconcile work |
| Newly added, positively identified occurrence | Create one task if inside the effective boundary and selected generation window |
| Confirmed exdate or occurrence lifecycle cancellation | Cancel the governed open task and reconcile eligible unattempted work |
| Source event explicitly cancelled | Stop new generation and cancel governed open tasks through bounded reconciliation |
| Same source occurrence proven restored after source-only task cancellation | Automatically create one linked successor under Section 8.1 if eligible; otherwise expose why no restoration occurred |
| Source time has simply passed, rule ended or COUNT exhausted | No automatic cancellation; this alone says nothing about an existing task's lifecycle |
| Task `done` | Preserve task and history, consume its assignment; do not move or regenerate it |
| Task `cancelled` by the operator | Preserve cancellation and suppress regeneration for its assignment |
| Explicitly detached binding or inactive governing relation | Preserve the independent task and its concrete due; retain assignment suppression evidence |
| Source identity missing/ambiguous, inaccessible or unprovable | Decision-required; block stale work and do not guess cancellation or a replacement |
| Source shell archived without a proved cancellation | Non-actionable/decision-required, not silently equivalent to cancellation |
| Source recurrence ends before any further occurrences | Mark generation exhausted without repeatedly issuing no-op commands |

A **confirmed exclusion** requires current recurrence evidence that the exact
assigned original slot is excluded, or a current explicit occurrence cancellation
fact. An empty expansion, a missing selector, provider failure, access denial or
the absence of lineage is not that evidence. A whole-rule edit removing candidates
does not automatically prove an individually assigned occurrence was cancelled;
the continuity/cancellation result must be explicit.

Cancellation uses an ordinary next task version with `task_status=cancelled`, not
row deletion or shell archival. Binding retirement, assignment disposition, eligible
work cancellation, audit and receipt occur in the same page transaction. A new
source-reason diagnostic must be introduced only with matching owning schemas and
closed reason/effect declarations; existing stored enums are not extended by prose.

No restoration may reopen a terminal task. Manual task completion, cancellation
or detach must update assignment freshness atomically or be derived reliably from
current canonical truth before generation; a delayed observer is not permission
to create a duplicate.

Rule retirement is separate from source cancellation. It stops future generation
and selects the approved disposition in Section 8.2; it must not accidentally
remove the existing children's freshness protection.

Assignment-aware lifecycle validation must run at the shared domain boundary for
both the ordinary automatic binding sweep and direct binding-reconcile calls on
generated children. For example, the existing v1 `source_terminal/cancel_target`
branch is not sufficient proof that an archived source was cancelled. A caller
cannot bypass this leaf by addressing only the child's ordinary binding. Runtimes
advertising the new family must route these generated targets through its proof
and disposition rules, rejecting an incompatible branch without mutation. This
does not change v1 reconciliation for tasks outside the new family or remove an
operator's existing explicit task cancellation/detach capabilities.

### 8.1 Automatic reinstatement (D-01 approved)

Restoration is normal bounded reconciliation, not a user-approval workflow. It
requires all of these facts to be revalidated in the committing transaction:

1. The rule is active, and the same original source occurrence or an explicitly
   proved one-to-one successor is current, scheduled and actionable again.
2. The assignment's latest task generation was cancelled by this family's
   source-exclusion/cancellation transition, with immutable evidence identifying
   that task/version, source cause and cancellation operation. Task status
   `cancelled` alone is insufficient; unknown or mixed causes do not qualify.
3. No operator completion, manual cancellation, detach or explicit suppression
   overrides restoration, and no successor already exists for that cancelled
   generation. Historical generations never become new restoration candidates
   after a later generation has consumed or suppressed the assignment.
   The assignment-level veto in Section 8.3 remains available after the source-
   cancelled task's binding has retired; it does not require another task cancel.
4. The effective boundary, generation/catch-up policy and bounded operation permit
   restoration at the current occurrence time, including the strictly future-due
   check in Section 7.5. This does not authorize historical overdue restoration or
   an expired reminder.
5. The intended child ownership, template, route and reminder configuration remain
   valid under their owners. Restoration does not select a newer catalog/profile
   revision, grant disclosure or broaden delivery authority.

A restored pickup is a new ordinary task linked to the **same assignment** and
its immediately preceding source-cancelled task generation. The old task remains
`cancelled`; its binding, policies, work, attempts, audit and receipts are immutable
history. Create the successor task, new relation/binding, eligible reminder work,
generation linkage and receipt atomically. Derive its due from the current source
occurrence. Preserve the predecessor's adopted configuration and explicit child
customizations under their existing copy-forward rules, subject to current
validation; the latest rule/catalog revision does not silently replace them.

Task-generation indexes are positive contiguous decimal integers within the
assignment, distinct from the catalog/change generation used for cursor freshness.
Each cancelled generation can have at most one restoration successor, and only
one generation is current. The successor identity is assignment/generation-based,
not reconcile-command-based. Repeated scans, different command IDs, overlap,
replay or concurrent workers must retain the same successor and its work. A later
exclude/restore cycle may produce the next generation with the same safeguards.

If the source returns before its open pickup has actually been cancelled, reconcile
that existing task; do not create a successor. If no pickup was generated before
the exclusion, ordinary first-generation rules apply when the occurrence returns.
Ambiguous continuity or cancellation evidence is decision-required, not permission
to restore by guessing. A retired rule or explicit suppression blocks automatic
restoration; a failed bound or configuration check is surfaced distinctly.

Readback and receipts must identify the predecessor and successor task IDs, stable
assignment ID, generation index and source proof. No confirmation exchange or new
conversation engine is required for the eligible path. This does not add a source
lifecycle reopening operation: the recurrence/event owner must already permit the
source change establishing reinstatement. Prior reminder attempts are preserved;
new work must obey ordinary current opportunity identity and late-handling rules.

### 8.2 Retirement with explicit disposition (D-05 approved)

Retirement stops the rule, not its source event. The write request must explicitly
select one of the following dispositions; final enum names belong in the machine
contract. There is no omitted-field default or silent interpretation of "stop."

| Disposition | Existing-task behavior |
| --- | --- |
| Keep following | Existing governed open tasks keep their adopted configuration, follow source moves and retain their reminders. Confirmed source exclusion/cancellation still cancels them. No new assignment or restoration successor is created. |
| Detach | Explicitly detach each still-open governed task at its current concrete due value. Its ordinary reminders remain subject to normal task/work eligibility, but future class moves or cancellations no longer govern it. Preserve the structural `part_of` relation unless separately changed. |
| Cancel outstanding open tasks | Cancel all still-open governed tasks, including overdue ones, and reconcile eligible unattempted reminder work. Do not convert cancellation into completion. |

All dispositions preserve completed tasks, already-cancelled tasks, previously
detached/suppressed assignments and all historical delivery evidence. No operation
deletes the rule or its assignments, changes the source event, reopens a terminal
task or retracts an already-started send. Agent guidance may select a disposition
from clear operator intent; ambiguity is resolved before submitting the normalized
write, not by inventing an asynchronous approval workflow.

The retirement transaction records the disposition and immediately stops new-task
creation. Concurrent generation/reinstatement must recheck rule lifecycle before
commit and cannot cross that boundary. Existing-task dispositions run through
bounded atomic reconciliation pages, including assignments outside the current
horizon. Receipts/readback distinguish "generation stopped" from "all selected
existing tasks disposed" and expose pending coverage/conflicts. Returning a rule
retirement receipt is not evidence that an unbounded fan-out already completed.

Keep-following is a deliberate exception to any root-active check for **existing**
task maintenance. Its retained bindings still reconcile source changes and enforce
attempt-start freshness even though generation is retired. A task cancelled after
retirement remains cancelled if its class is later reinstated: no successor may
be created. Source cancellation and task terminal handling take precedence over
unapplied configuration edits. Previously authorized adoption intents may converge
only on still-eligible existing tasks; root retirement authorizes no new edit.

For cancel/detach dispositions, pending configuration adoption is superseded by the
explicit retirement disposition, with retained history. Work admission must account
for pending cancellation or detachment: it cannot send against obsolete governing
truth while the bounded cleanup catches up. After detachment commits, reminders
use the now-independent task's ordinary current truth, not the class's freshness.
Do not leave a stale desired-configuration gate that can never be resolved after
the binding is retired. Exact precedence/progress facts must be closed together
with the machine contracts and all-writer validation.

Compatible retirement replay returns its original disposition and evidence.
Different command IDs do not restart completed cleanup or change the selected
disposition. No reactivation or disposition-switching surface is implied. Any
later new rule is a separate explicit enrollment; it does not automatically adopt
old tasks or bypass the per-rule duplicate/adoption boundary in Section 11.

### 8.3 Individual restoration suppression after source cancellation

Provide a supported trusted-local assignment-level suppression action, proposed
as `schedule.related_task_rule.assignment.suppress`. It records the operator intent
"do not automatically restore this pickup assignment" without retiring the entire
rule or mutating a terminal task. This makes the existing Section 8.1 suppression
safeguard exercisable; it is not a different reinstatement policy.

The action targets an exact rule/assignment and its latest source-cancelled task
generation, with expected assignment-change version and task-generation identity.
It remains legal when the task is already `cancelled` solely by the source
transition and its binding is retired, provided no restoration successor has
committed. It does not require the source still to be excluded; the current
generation/successor facts decide the race. Missing or contradictory cancellation
evidence fails closed. A task title, date or retired binding ID is not a substitute
for exact assignment targeting. Use the family's existing trusted-local actor and
write-authority posture; do not add an access or delivery grant.

Suppression has assignment scope: it vetoes automatic successor creation for that
same source slot through later source revisions, moves and reinstatement cycles.
It does not delete the reservation or cause the generator to treat the slot as
new. Other assignments and future unrelated class occurrences are unaffected.
This action does not create, cancel, reopen, detach or alter a task, policy, work
row or side-effect attempt. A request addressing an open successor must instead
use its ordinary explicit task cancellation/detach capabilities when desired.
No suppression-release or terminal-reopening operation is introduced here.

Recheck expected assignment facts, the latest generation, existing successor and
veto inside the same outer write transaction as the immutable suppression fact,
assignment-change invalidation, audit and receipt. Restoration transactions must
check that veto and the same assignment freshness before creating a successor:

- **Suppression commits first:** the fresh veto prevents successor creation.
  A restoration mutation prepared before it fails stale without writes; it
  cannot silently switch the branch under the old expected facts. Fresh read-only
  planning then reports suppression without dispatching another no-op mutation
  or creating any task, reminder or work.
- **Restoration commits first:** the old suppression request fails with a
  structured stale-version conflict and no mutation. It must not report that
  restoration was prevented, set a veto against a different generation, or
  implicitly cancel the existing successor. The operator rereads current state
  and may explicitly cancel/detach the now-current task through supported surfaces.

Compatible command replay returns the original suppression receipt, before fresh
stale checks, with no additional assignment/audit facts. A fresh request with
current matching facts and an already-recorded identical veto is a semantic
no-op; a new command ID does not excuse stale inputs. Dry run previews the same
eligible branch without writing. Page/automatic planning remains read-only and
must not receipt-churn a suppressed assignment.

Rule/assignment readback and the suppression receipt expose at least the stable
assignment ID, targeted task generation and terminal task ID, veto state,
suppression actor/time/command/receipt evidence, current change-version facts and
whether a successor already exists. Generation/reconciliation reports distinguish
explicit suppression from unresolved source identity, retired rule or missing
work. Use the new family's versioned surfaces, not extra fields on frozen reads.
Exact wire fields, error/effect enums and suppression identity preimages remain
part of machine-contract closure, but the operation and precedence above are
required. The historical task status, source-cancellation cause and prior receipts
remain unchanged.

## 9. Notification safety and granularity

Source mutations may commit before all child tasks have reconciled. Attempt-start
eligibility therefore checks the current source/binding/assignment truth, including
confirmed exclusions and unresolved continuity, independently of scheduler timing.
Work that was fresh at materialization is not automatically fresh at send time.

The existing boundary for an eligible zero-attempt row with no side-effect attempt
is preserved. In-progress work, retry work with attempts and terminal work are
protected evidence under composite reconciliation. A stale retry must fail its
next attempt-start gate; the reconciler does not erase or relabel prior attempts.
An already-started external send cannot be retracted by cancelling its source.

New and copied policies, opportunity keys, work uniqueness, lineage and ordinary
late handling remain notification-owned. The new family must not generate a second
logical delivery by wrapping existing work in another notification system. Each
task gets its own reminder identity, while re-expanding that task's unchanged
opportunity retains the same work identity and creates no duplicate delivery.
A later reschedule can produce a distinct current opportunity under the existing
notification rules; this is not a promise that a pickup can receive at most one
message throughout all of its schedule history.

`schedule.show`, `agenda.show`, task completion and granular binding/reminder
commands continue to operate on ordinary tasks. New readback must let an operator
follow rule -> assignment -> task -> binding -> policy -> work -> attempt without
requiring SQL. Existing frozen read contracts are not extended in place; any
additional fields or includes need an explicit supported successor or new surface.

## 10. Command and readback design

Provisional trusted-local command names, **not registered commands**:

| Candidate | Responsibility |
| --- | --- |
| `schedule.related_task_rule.create` | Author the rule, explicit configuration snapshot and effective generation boundary |
| `schedule.related_task_rule.update` | Author an immutable configuration revision with explicit existing-task adoption scope |
| `schedule.related_task_rule.show` | Read one rule, configuration, bounded coverage and assignment summaries |
| `schedule.related_task_rule.list` | Discover bounded rules and reconcile/decision-required status |
| `schedule.related_task_rule.reconcile` | Preview or atomically apply one bounded generation/reconciliation page |
| `schedule.related_task_rule.retire` | Stop generation with the explicitly resolved outstanding-task disposition |
| `schedule.related_task_rule.assignment.suppress` | Record an individual restoration veto against an exact source-cancelled assignment/generation without changing its terminal task |

Creating a rule is not a claim that children or work have been generated. A caller
may then reconcile bounded pages or let the configured automatic loop do so.
There is no hidden recursive submission of unrelated public commands producing
fabricated subreceipts. Any future initial-generation convenience remains bounded
and must enumerate actual committed child evidence.

Writes carry exact contract selectors, `command_id`, actor, command-specific
timestamp and relevant expected rule/source/recurrence/assignment version facts.
Supported reads remain non-mutating and may never opportunistically generate tasks.
Before ratification, machine contracts must close the request/response fields,
normalization, hash preimages, validation order, closed error/effect sets, limits,
cursor bytes, and exact runtime-family advertisement. Candidate names here do
not change the implemented-command list or imply web support.

A reconcile receipt separates at least:

- current rule revision, per-assignment requested/adopted revisions and source
  version/recurrence snapshot;
- page selection, limits, processed coverage and remaining continuation;
- created assignments/tasks, restored task generations with predecessor links,
  followed/refreshed tasks and retained assignments;
- cancelled, terminal-consumed, detached and decision-required assignments;
- per-task prior/current versions, relation/binding/provenance references;
- created, retained, cancelled and protected-stale work IDs;
- actual audit and receipt identities; and
- delivery `not_attempted_by_command`.

These classifications must be exhaustive for the selected page and disjoint at
the applicable task/work level; work created for one task cannot appear as retained
for another. An empty page, future generation pending, decision-required and source
exhaustion are distinguishable results. Short human receipts can summarize these
facts but cannot assert generation or delivery beyond the actual evidence.

## 11. Persistence, concurrency and replay

The logical minimum is durable rule headers, immutable configuration revisions,
assignments, task-generation/successor records, explicit restoration-suppression
facts, selector reservations/continuity evidence and assignment observations.
Exact physical tables and indexes must be specified before implementation under
the Spine-wide storage owner; do not hide these facts in command JSON receipts or
an agent's memory. References point to actual canonical source/target items,
versions, recurrence facts, bindings, routes and receipts as applicable.

Required constraints include owner-local rule-key uniqueness, unique per-rule
selector reservations across all history, one initial task per assignment, unique
assignment/generation indexes and predecessor-to-restoration-successor links, one
current task generation per assignment, one active governing due binding per
target, and foreign keys preventing orphaned
assignments. Indexes support active-rule discovery, source-to-rule invalidation,
rule-to-assignment pages, selector/alias lookup and affected nonterminal assignment
reconciliation without rereading all historical children on every cycle.

The assignment's generation identity is derived from the rule identity and initial
canonical source slot, not the reconcile command, expressed start, current recurrence
revision, task title or page boundary. Accepted continuity adds aliases without
changing assignment/current-task identity. Only proved reinstatement creates a
linked successor task generation under Section 8.1; old task identities never
change. Exact derivation versions and bytes belong in the forthcoming machine
companion and computed fixture corpus.

For each selected page, one outer transaction rechecks replay, authority, source
freshness, reservations and target versions; creates/updates ordinary child truth;
records assignment/continuity changes; reconciles notification work; and stores the
audit/receipt. There is no independent helper commit. A constraint conflict from
two generators cannot leave duplicate tasks or a half-created page. A retry must
read the winning assignment; it cannot use a new command ID to bypass uniqueness.

Compatible replay returns the original immutable page result before fresh stale
checks and does not re-expand against a later source. Incompatible command reuse
fails. A new command ID means a new current-state reconciliation, not a second
entitlement to generate the same source slot. Dry run uses one coherent read
snapshot, returns branch-equivalent would-be evidence and writes nothing.

If required tables/constraints or family contracts are missing, the feature fails
closed. An additive migration does not infer rules from matching titles, existing
`part_of` relations or independently recurring tasks. Existing explicit single-
occurrence tasks are not automatically adopted. Duplicate prevention is per
enrolled rule and its reservations, not semantic deduplication against ad-hoc
tasks or different rules. Enrollment must disclose that boundary; callers cannot
assume an existing manually created pickup will satisfy the new rule. Deliberate
adoption is outside the first family. Migration/binary rollback/history requirements follow
the storage owner. No schema number, environment or rollout procedure is selected
here.

## 12. Ownership, roles, routes and authority

Rule ownership, generated-item ownership, task assignment and delivery destination
are separate explicit facts. The source event's participants do not automatically
become task assignees, and a group label or interaction channel is not a route.

Enrollment must name the intended child owner scope and concrete task/reminder
configuration. Any reuse of source ownership or a default route is a visible,
recorded authoring choice under the existing contracts, not an ambient read-time
inheritance. Source/child cross-scope authority must be checked rather than assumed.
Changing the source's people or ownership does not silently grant child access,
change assignees or redirect deliveries.

The first surface retains current trusted-local privileges; it does not pretend
to authenticate a chat sender. Before any protected/API successor, admission must
cover source reads, rule management, child creation/mutation, subject selection,
route use, disclosure and replay visibility under their existing owners. Internal
scheduler execution cannot invent a privilege exemption for such a future surface.

## 13. Verification and machine-contract readiness

The following are required fixture/test families, not fixtures delivered by this
draft. They must publish normalized inputs, exact selectors/assignments and
expected receipts/work evidence, not merely final clock times.

| Family | Required proof |
| --- | --- |
| Basic pickup | Multiple Saturdays -> distinct ordinary tasks, +5400 due and -600 reminder, no target recurrence |
| Source overrides | Same task after earlier/later move, including movement outside the generation window |
| Added/union occurrence | Rdate generation once; duplicate-collapsed source creates only one assignment |
| Exclusion/cancellation | Confirmed occurrence and whole-source cancellation affect open governed tasks, never `done` history |
| Missing evidence | Empty range, stale cursor, unresolved selector, unavailable timezone and ambiguous lineage do not masquerade as cancellation |
| Series edits/splits | Proven one-to-one continuity retains task IDs; unsupported or conflicting mappings fail closed |
| Terminal/manual control | Completion, cancellation, detach and inactive relation preserve slot reservation across restarts |
| Reinstatement | Source-only cancellation restores automatically without confirmation; same assignment/new linked task; no terminal reopening, manual override or duplicate successor; restore-before-cancel and repeated cycles; retired rule, bounds and ambiguous proof controls |
| Assignment suppression | Source-cancelled task with retired binding; exact assignment/generation targeting; suppression-first versus restoration-first interleavings; visible persistent veto; no changes to task/work/attempt history; other occurrences unaffected; fresh no-op, replay, stale/new command, dry run and transaction rollback; no idle receipt churn |
| Effective start/horizon | Enrollment instant retained across scans; upcoming same-day occurrence included; explicit inclusive starting occurrence; original-past/expressed-future move; eight-week default and bounded override; rolling replenishment; assigned move outside window; incompatible early reminder surfaced |
| Catch-up | Late enrollment and downtime; started source/future due; negative offset/past due; exact due equality; pre-cutoff preview/late commit; eligible versus expired reminder grace; explicit-start boundary; offset-bounded lookback; existing overdue task retained; no duplicate/restored overdue task |
| Time | DST, source timezone/version changes where permitted by owning contracts, signed offsets, precision and multiple reminder horizons |
| Template edits | Both explicit scopes; eight-week pre-generated tasks; pending/applied coverage; concurrent edits; source following under old adopted offset; normalized individual-edit conflict versus equal/non-overlapping changes; completion/overdue race; no profile auto-adoption; no-op and replay |
| Rule retirement | All three explicit dispositions; source unchanged; generation/retirement race; bounded out-of-horizon cleanup; overdue cancellation; terminal/detached/history preservation; retained follow freshness with retired root; no reinstatement successor; pending-edit precedence; replay and no idle churn |
| Notification lineage | Successor due and successor policy IDs; pending configuration freshness and conflict gates; work uniqueness across unchanged pages, replacement and retries |
| Attempt race | Source edit before/after attempt admission, protected retry/in-progress/terminal evidence and no false unsend claim |
| Transactions | Injected failure after assignment, child, policy, work and receipt stages rolls the entire page back |
| Concurrent generation | Same slot from different commands/processes/windows creates one task and one logical reminder per opportunity |
| Replay/dry run | Lost response, later source edits, conflicting reuse, no dry-run writes and stable original receipt |
| Bounds/continuation | Dense/old source, finite COUNT, exhausted source, partial pages, own-commit continuation and concurrent invalidation |
| Idle cycles | Repeated unchanged/exhausted/terminal scans create zero durable no-op receipts or heartbeat writes |
| Authority/separation | Explicit owner/roles/route, no participation-derived permission and no disclosure grant by installation/generation |
| Compatibility | Old binding commands and frozen reads unchanged; no accidental new API route or runtime-family declaration |
| Migration | Existing items/receipts unchanged, no inferred adoption, required constraints/indexes, unsupported older writer refusal |

Readiness requires approved decisions below, a closed logical/storage/command
contract, machine schemas and computed fixtures, plus a subsequent implementation
plan. A clean prose review alone is not runtime implementation or release evidence.

## 14. Product decisions

Automatic cancellation on confirmed source exclusion/cancellation is approved.
D-01 is also approved (2026-11-07): automatic linked-successor restoration after
source-only cancellation, with the Section 8.1 eligibility checks and no user
confirmation. Completed, manually cancelled, detached or explicitly suppressed
assignments are not restored. This resolves the prior explicit-restoration
recommendation; it does not ratify the complete draft.

D-02 is approved (2026-11-07): default to upcoming occurrences from enrollment,
allow an explicit starting occurrence, and use a configurable eight-week rolling
generation horizon. Section 7.1 defines the boundary and coverage semantics.
Already-generated tasks remain governed outside the window. D-02 alone does not
authorize historical backfill; the permitted catch-up exception is D-03 below.

D-03 is approved (2026-11-07): automatically catch up missing tasks only while
their derived due time is still strictly ahead, including for an already-started
source occurrence. Use ordinary reminder late handling; do not force late sends
or automatically backfill newly overdue tasks. Existing overdue tasks remain
unchanged. Section 7.5 defines the boundary and its bounded discovery requirements.

D-04 is approved (2026-11-07): require an explicit edit scope, normally upcoming
open governed tasks plus future generation, with a newly-generated-only alternative.
Use bounded adoption, preserve terminal/overdue/detached tasks and individual edits,
surface conflicts and retain attempted history. Editing a reusable profile is not
implicit rule/task adoption. Section 7.6 defines the requirements.

D-05 is approved (2026-11-07): retirement requires an explicit disposition to
keep existing tasks following, detach them or cancel outstanding open governed
tasks, including overdue ones. New assignments and reinstatement successors stop
under every disposition; terminal/manual exceptions and attempted history remain
preserved. Section 8.2 defines bounded completion and freshness behavior.

No selected product decision D-01–05 remains open. This does not ratify the draft
or claim implementation readiness: exact storage, lineage proofs, command schemas,
limits, reason/effect values, concurrency/clock rules and computed fixtures still
require closure and review before the implementation plan and runtime work.

Independent of these choices, manually completed/cancelled/detached assignments
cannot be silently regenerated. Any restoration or bulk-update extension must
preserve the same assignment, replay and attempted-history invariants.
