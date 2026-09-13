# Advisory Extensibility: Three-Case Gap Analysis

Status: Non-normative design assessment; proposed follow-up, not an implementation commitment

Date: 2026-09-13

Method: Contract walkthroughs and targeted storage/runtime inspection; no simulated or real external execution

## 1. Executive assessment

The current design does not require a return to the drawing board. Its separation of
coordination truth, authorization, execution, evidence acceptance, and delivery is a
sound foundation. However, notification enrichment is not yet a demonstrated reusable
automation interface. Several relationships would become expensive constraints if
promoted unchanged into a shared execution contract.

The most important finding is that there are **two different kinds of coupling**:

1. The new advisory draft binds activation, work, context, and consumption to an event
   notification. This can remain a deliberately narrow capability profile.
2. Existing Spine work and candidate-action storage require a single item and version.
   This is an actual structural constraint, independent of the advisory draft. A new
   trigger enum alone would not support a genuinely group-scoped, multi-item run.

Before freezing machine contracts, identify which facts belong to this advisory
profile and which belong to a reusable cross-system boundary. Do not broaden the
running product or implement a workflow engine to accomplish that separation.

| Future case | First hard stop today | Expected extension if boundaries are preserved | Relative redesign exposure if generalized from today's advisory shape |
| --- | --- | --- | --- |
| Research a location-free renewal task | Advisory v1 rejects tasks and missing location | A new task-research profile and activation/consumption contract | Low to moderate |
| Review upcoming commitments without a reminder | Notification-owned activation and single-item work parent | Explicit planning scope, bounded multi-item snapshot, independent activation identity | High |
| Prepare a booking change, await approval, then act | Read-only outputs, terminal unsupported approval, one reminder-bound run | External resumable workflow, separately authorized steps and side-effect reconciliation | High |

These are qualitative assessments of affected relationships, not time estimates.
None of the three future cases is currently supported by the advisory contract.

## 2. Evidence and limits

The assessment uses the current working copy of `specs/contextual-advisories.md`,
Draft v0.3.1, including the approved but uncommitted privacy/configurable-budget
changes. Spine HEAD is `22807976bd5b33289d85c5e6fb5dee18da55431c`.
The previous bounded audit reviewed v0.3.0; it neither reviewed these later defaults
nor established general-purpose extensibility.

Source keys used below:

| Key | Local source and relevant sections |
| --- | --- |
| S1 | `specs/contextual-advisories.md`: §§3–7, 8.1–8.2, 9–10, 13, 15 |
| S2 | `specs/ontology.md`: §§4.1, 4.4, 9.1–9.3 |
| S3 | `specs/architecture.md`: §§3–6, 9 |
| S4 | `specs/operational-resilience.md`: §§4–7 |
| S5 | `specs/archetype-facets.md`: §§1–2 |
| S6 | `specs/permissions.md`: resource permissions and disclosure boundaries |
| S7 | `docs/IMPLEMENTATION_PLAN.md`: Notification-Activated Contextual Advisories horizon |
| S8 | `docs/design-notes/scheduled-agent-autonomy.md`: exploratory autonomy spectrum and trigger models |
| C1 | `src/spine/ledger/schema.sql`: work_instances and candidate_actions; `src/spine/ledger/migrations/0007_canonical_scheduling_notifications.sql`: rebuilt work_instances |
| C2 | `src/spine/services/scheduling.py`: notification candidate selection and reminder-only work filters |
| G1 | `../foreman/docs/HLD.md`: §§2.1, 6.2; `../foreman/docs/WORKFLOW_BOUNDARY_SPEC.md`: §§2, 4–5, 11–16 |
| G2 | `../foreman/docs/DISPATCH_SKILL_INVOCATION_SPEC.md`: §§11–12, 18 |
| G3 | `../foreman/docs/APPROVAL_PERSISTENCE_SPEC.md`: §4 |

The governance checkout is at `8afa61f` and has unrelated working-tree changes.
Only selected source contracts were inspected; its deployed runtime and integration
conformance were not tested. Its workflow boundary is explicitly a draft. Existing
native concepts are evidence for reuse, not proof that a ready-to-use integration
already exists. Concrete repository names here identify evidence, not proposed public
protocol vocabulary. Native domain specifications take precedence over their boundary
summary where they differ.

Key source SHA-256 values:

```text
S1 advisory v0.3.1: 09afcef354c59309a33e1cc0efedc866c676d617ef85a410ce769aa96f7f6905
S2 ontology: b9b827db5740ab40695f30593227b01dd01efb4db9d673ecc377daab7dc066e0
G1 workflow boundary: fc78acf1353074876fe2e9504d16935b8c63c92ec61afd472c9df670775cda64
G2 dispatch: 8c666e54e7185e8f32818553dfe9f285fb4870f8d12abdc155aea70d11aef026
G3 approval: 0c43ead26a7e22def305fd083531b4840d7bce0aae1505bfb2fda7c498c75fec
```

This report distinguishes an observed restriction from its predicted consequence and
a proposed extension. It adds no schemas, command names, entity kinds, permissions,
or runtime support. A successful tabletop extension is not an executable test pass.

## 3. Simulation A — Research a renewal task without a location

### Representative request

“Look into what I need to complete this passport renewal. Identify missing information
and give me a preparation checklist. Do not submit anything or contact anyone.”

Assume an existing open task, possibly with a date-only due anchor, no primary
location, and no reminder. The operator explicitly requests this investigation.
No passport number, scan, or unrelated personal history is implicitly disclosed.

### Walkthrough

1. **Select source truth.** Spine can represent the task without a due time or location
   (S2 §4.4). This is not a deficiency in the coordination-item model.
2. **Activate research.** The request cannot be authored under advisory v1: S1 §4
   requires an event, local-instant start, location, and notification-template trigger.
   The correct current behavior is rejection, not fabricating an appointment or reminder.
3. **Build context in a future profile.** Bind the task/version and a narrowly permitted
   context snapshot. A task-oriented profile would specify its own required context.
   Missing eligibility facts can produce a clarification; location is not universally
   meaningful. Access to a task is not permission to disclose all attached documents.
4. **Authorize and investigate.** The objective, bounded read-only capabilities,
   finite budget, immutable request, and native authorization/evidence references are
   reusable concepts. They do not intrinsically depend on an event or a delivery route.
5. **Consume the result.** A checklist can be returned to the requesting surface as a
   result without creating reminder work. Persisting new preparation tasks would be
   a separate authorized mutation, not a side effect of accepting the checklist.
6. **Race test.** If the task is completed or changed during research, keep the result
   as evidence but revalidate before presenting it as current actionable advice or
   applying any proposal. A new investigation is distinct from replaying the old result.

### Gap and verdict

Event/location requirements are safe profile limits. The risk is exporting them into
shared submission, source-reference, or runtime interfaces, where S1 §§6–7 currently
require notification and event facts throughout.

The result taxonomy also needs profile scope: `advisory`, `no_action`, and
`request_clarification` are suitable for this first experiment, not a universal output
model for every future execution. A returned question is currently a terminal result,
not an implemented conversational pause/resume protocol.

**Verdict:** likely an additive profile/integration change if the common boundary is
kept independent of event, location, and notification consumption. No new general
workflow engine is needed for this case. A new supported contract would still be
required; simply removing validation checks is not a safe extension.

## 4. Simulation B — Planning sweep without a reminder

### Representative request

“Review the next two weeks of commitments I can access in this group. Suggest missing
preparation tasks. Save the suggestions for review; do not create tasks or message anyone.”

Assume an explicit operator request first; a periodic schedule would be an additional
activation contract. The scope can contain many items or no items at all.

### Walkthrough

1. **Establish scope and authority.** Bind the initiating caller, permitted group/scope,
   query window, purpose, and bounded read budget. Group membership alone cannot grant
   access to every item or permission to disclose it to an external runtime (S6).
2. **Create an activation identity.** No notification opportunity exists. A future
   explicit-request identity must replay without rediscovering a different set of
   items. A later periodic sweep needs a distinct scheduled activation identity, not
   repeated anonymous scanner ticks.
3. **Choose the durable parent.** Today's work and candidate-action rows require one
   `item_id` and `item_version` (S2, C1). `generation_source_kind=schedule_tick` does not
   remove those requirements. Binding to the first event fails when that event is
   removed or the set is empty and incorrectly makes it the authority for the sweep.
4. **Capture a bounded input set.** A future snapshot needs the selection scope/window,
   actual item/version references, field-level disclosure choices, and completeness
   evidence. A paged or capped partial view cannot claim to have reviewed everything.
   The event-minimal privacy default must remain intact; a sweep needs its own explicit
   multi-item disclosure policy, not a blanket relaxation of the advisory profile.
5. **Investigate.** One bounded runtime invocation could return multiple typed
   suggestions; this case does not necessarily require fan-out or multiple agents.
   Any future fan-out must also respect an aggregate budget, not multiply a per-run
   budget without limit.
6. **Consume results.** Save an accepted suggestion set without delivery. Turning a
   suggestion into canonical preparation tasks requires permission-checked Spine
   commands and their own receipt/replay semantics. Existing candidate-action kinds
   do not already include arbitrary task creation (S2 §9.2, C1).
7. **Race test.** Move event A, remove access to B, and add event C while the sweep runs.
   A list of old item-version references can detect changes to A/B but cannot establish
   that no new matching C exists. A claim about the whole current set requires defined
   query-membership freshness; alternatively the result must explicitly claim only
   the captured as-of set. Recheck disclosure before readback after access revocation.
8. **Empty/replay test.** A complete empty result is valid without a dummy event or
   delivery target. Replaying the request returns its recorded outcome, rather than
   starting new research because the current query now returns different items.

### Gap and verdict

This exposes the strongest structural constraint: **one owning item is not the same
thing as a set of source dependencies or an authorization scope**.

Two possible future designs remain legitimate:

- A genuine user-visible planning task can own a sweep when that task actually exists
  in the product model; a separate snapshot still records all relevant dependencies.
- A scope-owned operation can use an independently specified Spine record or an
  externally owned process identity with validated correlation back to Spine.

The report does not select or implement either storage design. It recommends explicitly
allowing the architectural distinction now. A hidden synthetic task/event created
solely to satisfy a foreign key is not an adequate substitute.

**Verdict:** a new trigger/profile alone is insufficient. Scope-level identity,
multi-source context, freshness/completeness, and result consumption need explicit
contracts. Existing item-bound reminder tables can remain unchanged if they are not
declared to be the universal storage model for all execution.

## 5. Simulation C — Booking change with approval and a durable wait

### Representative request

“Find a suitable alternative for this flight. Show me the price and conditions, wait
for my approval, and then change the booking if the approved conditions still hold.”

Assume explicit authority to research only at the start. Approval for an exact change,
vendor access, and any canonical Spine update are separate later authorities.

### Walkthrough

1. **Prepare.** Read a permitted flight snapshot and investigate alternatives under a
   read-only grant. Facets can eventually carry canonical booking facts; live quotes
   and availability remain external observations, not automatic facet replacements (S5).
2. **Produce a proposal.** A structured change proposal is not one of advisory v1's
   allowed outputs. Smuggling a command into advisory prose violates S1 §7.4. A future
   proposal profile must preserve the distinction between evidence and execution power.
3. **Request approval.** Advisory v1 treats `approval_required` as a terminal unsupported
   path and cannot later resume that work (S1 §7.2). Its clarification question is not
   an approval mechanism. This is intentional and should remain true for that profile.
4. **Wait durably.** A process coordinator can wait for hours or days without keeping
   a model call, Spine transaction, or reminder work lease open. The governance design
   already separates durable workflow mechanics from approval validity and authorized
   transitions (G1). Actual runtime qualification is still needed.
5. **Revalidate.** When approval arrives, verify its exact action/terms, current source,
   vendor quote validity, and authorization expiry. G3 binds approvals to immutable
   decision material and invalidates them when relevant bindings change. A different
   quote cannot silently reuse approval for the earlier quote.
6. **Execute a separate authorized step.** Use a new governed write dispatch only if
   still permitted. The earlier read-only grant is never upgraded in place. Link the
   process, proposal, approval, dispatch, and attempts; their identities are not the
   notification's single-send identity. The external executor remains outside Spine's
   model-planning responsibilities.
7. **Crash test.** The provider accepts the change but the response is lost. An unknown
   result is not ordinary failure and must not cause a second booking change. Reconcile
   the same operation or use proven provider idempotency. S4 §7 gives this requirement;
   the adapter-specific and cross-ledger mapping is not yet defined.
8. **Commit coordination truth.** If the booking changed, update Spine through an
   authorized version-checked command based on verified evidence. If a concurrent user
   edit makes that command fail, preserve the real provider outcome and reconcile;
   the external effect cannot be rolled back by a local transaction.
9. **Notify separately if requested.** A completion message is a new explicitly
   authorized result-consumption action, not permission to reopen a previously sent
   advisory reminder. The existing reminder still gets its ordinary fallback by its
   deadline; it does not wait days for the booking workflow.

### Gap and verdict

Workflow identity, invocation lifetime, approval lifetime, evidence validity, and
notification delivery lifetime cannot be represented by one run/deadline/status.

The governance specifications already contain workflow, approval, dispatch, receipt,
and retry concepts (G1–G3). Spine should integrate with these, not reproduce a general
workflow graph or approval engine. The gap is a qualified mapping and clear lifecycle
ownership, not evidence that a new orchestration platform must be written.

Both systems also record attempts. These can describe different facts—a governed
dispatch versus a concrete vendor operation—but must not independently authorize
retrying the same real-world effect. Spine's current architecture requires its attempt
gate for external writes in its adapter path, while the native governance system owns
dispatch attempts and retry policy (S3 §4; S2 §9.3; G2 §12). The future write integration
must assign one effect executor and one retry decision path, with immutable cross-links
between distinct records. No single-writer or receipt model provides a distributed
transaction or exactly-once external effect by itself.

**Verdict:** substantial new workflow capability is unavoidable, but a rewrite of
Spine coordination truth is not. It becomes a redesign if the advisory run is forced
to be the process root, or if reminder retry/expiry becomes workflow retry/expiry.

## 6. Gap register and decision timing

“Before freeze” means before claiming the new machine family is reusable, not before
every future capability is implemented. These are extension risks, not findings that
the intentionally narrow advisory v1 must accept unsupported requests.

| ID | Load-bearing assumption / evidence | Consequence | Minimum action before machine-contract freeze | What can wait |
| --- | --- | --- | --- | --- |
| G-01 | Notification/event/location references required throughout S1 §§4, 6, 7 | All future requests need artificial notification facts if this becomes the shared interface | Explicitly separate the advisory-specific binding from native execution request/correlation; keep strict v1 validation | Task and non-notification activation implementations |
| G-02 | One item/version parent in S2 §9 and C1 | No natural representation for empty or scope-wide sweeps; wrong lifecycle/permission inheritance | State that execution scope, coordination parent, and source dependencies are distinct; do not make current work rows the universal process root | Scope-owned storage/API choice until sweep design |
| G-03 | Advisory definition contains silence/deadline; outcomes and acceptance consumption target delivery (S1 §§4.1, 7.4–8) | Planning artifacts and proposals must masquerade as notification text | Keep outcome contracts and notification fallback/selection profile-specific; separate evidence acceptance from permission to consume/apply it | New typed proposal/result families and consumers |
| G-04 | One logical run, terminal unsupported approval, reminder-bound usefulness (S1 §§7.2, 8–10) | Long waits require fake retries, extended deadlines, or overloaded run state | Name distinct process, dispatch/run, attempt, evidence-validity, and delivery lifetimes; put future waiting/step mechanics outside Spine | Durable workflow implementation and approval-resume profile |
| G-05 | Spine attempt gate plus native dispatch retries; read/model attempt ownership still open (S1 §10, S2 §9.3, G2) | Duplicated accounting or two retry authorities; real duplicate effects | Close read-only attempt/reference ownership in the first native mapping; document dispatch versus effect accounting | Full write adapter/provider reconciliation protocol, mandatory before write support |
| G-06 | One-event context and all-bound-source freshness (S1 §§6.3, 9) | Multi-item completeness, empty-set identity, changing membership and permission revocation lack semantics | Reserve explicit versioned scope/dependency/context contracts rather than arbitrary JSON; preserve privacy and closed fields | Exact query-membership freshness algorithm before sweeps |
| G-07 | Configurable per-definition budget does not itself bound a workflow or fleet (S1 §4.2, S4) | Fan-out/retries multiply cost; many bounded runs still exhaust shared resources | State budget scope and owner, count retries in effective run limits, and specify bounded admission for the first slice | Workflow aggregate budgets before introducing fan-out/continuations |

## 7. Recommended architectural reservation

The proposed conceptual separation is:

```text
activation + authorized coordination context
                    |
          bounded execution request
                    |
      native governance and dispatch
                    |
          runtime result / evidence
                    |
           native acceptance
                    |
       authorized result consumer
```

This is an ownership sketch, not a new schema or a replacement governance pipeline.
For advisory v1, activation is the selected notification; context is one eligible
event; the runtime is read-only; the consumer is that notification's content-selection
path. Its ordinary fallback does not wait for or require native acceptance.

The native governance system may already supply much of the middle. Map to its exact
published artifacts; do not invent a parallel generalized intent, dispatch, or
acceptance ledger in Spine merely to make the picture symmetrical.

For future profiles, different activation/context/result contracts can use the same
qualified middle without editing v1 payload meanings. Versioned closed profiles are
preferable to making every field optional or admitting an unrestricted payload bag.
Unknown profiles and unsupported source kinds must fail closed.

Three ownership qualifications matter:

- Spine's canonical task status and dependencies describe coordination truth.
  Governance intent-graph dependencies describe authorization prerequisites. Neither
  can silently become the authority for the other's graph.
- Spine schedule semantics, Tickerd polling cadence, and external workflow waiting/
  retry timers are different clocks with different owners. Sharing an implementation
  must not create competing schedules or retry decisions.
- Facets store typed canonical facts. They are not a place to hide workflow checkpoints,
  executable recipes, grants, or live unaccepted vendor observations.

## 8. Minimal recommended next sequence

1. Add a short architecture decision and targeted advisory clarifications separating
   the restricted advisory profile from reusable execution boundaries. Preserve all
   approved fallback, single-delivery, privacy and boundedness behavior.
2. Resolve the first slice's exact native mapping, especially submission/dispatch/run
   correlation, attempt ownership, freshness handoff, and budget enforcement. Determine
   whether native supported reference fields can carry Spine correlation without
   changing the native artifact's identity or acceptance semantics.
3. Author only the closed advisory machine contracts needed now. Do not advertise
   general workflow support. Where common types are genuinely shared, keep their
   profile-independent meaning explicit; otherwise keep an advisory-local type.
4. Carry the following design checks into the contract review:
   - A future task profile need not invent a location or notification.
   - A zero-item, scope-bound request has a coherent future identity/permission model.
   - Replaying a captured query does not silently select newer source facts.
   - A result may be accepted without a delivery target or mutation authority.
   - A reminder deadline can expire without changing a separately authorized workflow's
     lifetime; a stopped advisory itself remains stopped.
   - A later write step has its own authorization and effect identity; two schedulers
     cannot independently retry it.
   - Unsupported cases still reject under advisory v1; no generic extension bypasses it.
5. Audit the resulting boundary and mapping, then proceed with the bounded read-only
   implementation. Implement and test each future profile only when it is commissioned.

Do not add a workflow DSL, general engine, generic nullable work table, reserved domain
taxonomy, new platform repository, or all three future profiles as part of this step.
Do not weaken the current notification scanner's reminder-only filtering; that filter
is correct for its existing responsibility, not the mechanism for general activation.

## 9. Bottom line and verification

The first-version restrictions are not the principal danger. The danger is treating
an advisory's notification parent, single source item, output type, or deadline as a
universal execution abstraction. That would reproduce the structural trap the user
experienced in the original family scheduler.

The least expensive prevention is to reserve the boundaries now and qualify the
native execution/governance mapping before persistence contracts are frozen. Some
future schemas, migrations, profiles and operational services will still be needed;
this assessment does not promise zero retrofit cost.

Verification performed for this report: source/spec inspection, three documented
tabletop traces, inspection of the existing required-item storage constraints and
notification-only discovery path, and report diff hygiene. No runtime simulation,
model/tool execution, approval request, external send, migration, or integration test
was performed. No normative specification or existing runtime file was changed.
