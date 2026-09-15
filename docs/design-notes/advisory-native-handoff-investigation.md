# Advisory native handoff: implementation investigation

Date: 2026-09-15  
Status: Investigation complete; recommendations, not accepted contracts or implementation authorization  
Tracking: SPINE-019

## Conclusion

There is a real, reusable governance kernel, but no ready-to-connect advisory execution
service. The missing work is **a bounded native execution capability plus the Spine
bridge**, not merely translating field names. It does not require completing a general
workflow platform, multi-step approvals, or all of the governance roadmap.

The sibling checkout is still named `foreman`; that name below identifies inspected
source, not a new public Spine protocol dependency. Public contracts should retain
the `governance_authority` and `agent_runtime` roles. Selection of a production
implementation and execution engine remains separate from this investigation.

## Evidence boundary

- Spine base: `560ecc4367fb9095709b184cd0b6a04e5a919a11`.
- Governance base: `8afa61f26bd227b383907824fe656aa52ddc8831`, package `0.1.0`.
- The governance checkout has existing modified explanatory documentation and
  untracked container/demo material. Those changes were not edited or used as proof
  of a released capability. Runtime conclusions below follow tracked source and tests.
- No deployment, provider call, network service, external audit, or live ledger was
  exercised. Tests used temporary databases. No normative specs or runtime code changed.
- The internal runtime API specification is labelled Draft v1.0 and lags code in
  places: it describes root-only creation and defers intake, while code implements
  child creation and `submit_intake`. Neither draft status nor a broad README claim
  alone determines runtime support.

## What exists, and what it means for the bridge

| Boundary | Existing evidence | Fit and remaining gap |
| --- | --- | --- |
| Admission and immutable identity | `RuntimeService.create_intent`, `submit_intake`; ingestion, intake canonical hashes and replay/conflict receipts | Reusable foundation. Register a bounded-research intent/evidence family and define exact advisory submission correlation. No existing advisory admission contract. |
| Pinned policy and state transitions | Registry loader, `NextTransitionArbiter.decide`, policy evaluator, atomic transition/audit storage | Real deterministic gates, not a general capability-grant engine. Model/tool subsets, budgets, expiry and advisory outcome permissions need explicit native enforcement. |
| Dispatch authorization | Draft dispatch §6 defines `foreman.dispatch.authorization.v1` | Not emitted by the inspected runtime as that artifact. A `dispatchable` state and a successful `advance_intent` response are not substitutes for the scoped authorization Spine requires. |
| Invocation and logical run | Draft dispatch §§8–12 define request core, invocation, dispatch and attempts | The general contract exists in prose; a real bounded agent invocation and logical-run correlation are missing from the implemented path. |
| Attempt recording | `send_dispatch` and `record_dispatch_attempt` persist deterministic attempt/receipt evidence, with replay and freshness-of-intent checks | Reusable persistence discipline, but `build_record_dispatch_attempt_request` hardcodes `status=sent` and defaults to `skill:send_message`. No model/tool execution occurs. Do not present this as research execution or delivery proof. |
| Research and budgets | Governance/agent responsibilities in Spine §§5 and 7; dispatch draft timeout/retry fields | No research runner, model/tool attempt ledger, aggregate usage enforcement, or advisory outcome validator found in the inspected native runtime. These are not supplied by Tickerd. |
| Produced evidence | `produce_evidence`, canonical payload/evidence hashes, registered evidence types | Real pending evidence and immutable integrity checks. Production accepts an object payload; type registration does not itself validate an advisory's complete semantic contract. |
| Accepted evidence | `accept_evidence_by_id`, acceptance lifecycle rows and audit; tamper/replay tests | Current acceptance checks stored integrity and registry presence, then records local acceptance. It does not validate the advisory grant, run, allowed outcome set, usage or information freshness. The stored acceptance reason is null on this path. |
| Native readback | Intent, dispatch-attempt, evidence and audit read methods | Useful references exist, but not the complete verifiable authorization/run/acceptance bundle needed by Spine. `show_evidence` alone omits some canonical producer/registry/lifecycle material needed for independent verification. |
| Approval | Real request/response/normalization and gating; broader draft approval lifecycle | Reuse classification where appropriate, not the demo's approval flow. Advisory v1 must stop on `approval_required`, preserve ordinary fallback, and never auto-grant or silently resume. |
| Freshness and consumption | Spine advisory §§8–10 specify freshness, selection, recovery and delivery rules | No implemented cross-system freshness handshake or advisory consumer. Native evidence acceptance is neither permission to deliver nor proof the Spine source is still current. |

### Admission is promising, but must be mapped deliberately

`submit_intake` is more relevant than the customer-message filesystem adapter:
the core accepts a registered intent type and one registered initial evidence object.
That object could hold a precisely defined submission snapshot or reference bundle;
there is no need to pretend a golf event is a customer-support message.

However, creation, evidence production, and intake receipt persistence are separate
steps with partial-result handling. The bridge must handle interruption after native
creation without inventing a fresh request or claiming a cross-database atomic commit.
An admitted intake receipt does not authorize execution or accept initial evidence.

Native intake `request_metadata` is excluded from its canonical identity preimage.
Do not put authoritative grant/context/correlation facts there and assume replay
protects them. The mapping must specify hash-bearing native material, namespaced
idempotency keys, the frozen Spine request, and recovery/readback after ambiguous responses.

### Dispatch and acceptance are the decisive gaps

The native dispatch specification is substantially richer than the implemented demo:

- §6 defines a persisted authorization tied to policy, registry, decision, selected
  skill and retry limits.
- §§8–12 distinguish immutable invocation/request hash, logical dispatch, individual
  attempts, timeout, and retry scheduling.
- §§14 and 17 define execution receipts and acceptance outcomes including rejected,
  stale and conflicting evidence, with reason codes and decision binding.

Those are useful design inputs. They must not be advertised as implemented merely
because `dispatch_attempts` and `evidence_lifecycle_facts` tables already exist.
The current local API can record success and accept evidence, but it cannot supply
the full contract required by Spine §§7.2–7.5. A bridge that simply calls these
methods and stamps the result `allowed`/`accepted` would invent authority.

The current policy evaluator supports a small predicate set (constant, accepted
evidence/integrity, and direct-child completion/routing). The advisory's effective
capability subset and hard budgets cannot be enforced by prompt text or inferred
from that limited predicate support.

## Proposed ownership mapping to specify next

These are recommendations to resolve the open mapping, not new contract declarations.

1. **Spine owns activation and consumption.** Persist the exact submission once;
   retain canonical source versions, privacy decisions, notification identity and
   selection cutoff. Preserve ordinary fallback and the existing delivery attempt gate.
2. **Native governance owns admission and dispatch permission.** Bind one submission
   to native intent/evidence, determine an effective grant no wider than requested,
   persist verifiable authorization, and accept/reject returned evidence with reasons.
3. **One bounded runner owns research execution records.** It consumes the authorized
   invocation, records a logical run and concrete model/tool calls, enforces the grant,
   and returns immutable usage/outcome evidence. It cannot write Spine or deliver text.
4. **Retry ownership is explicit at each level.** Reuse native dispatch retry authority
   rather than a second Spine retry loop. Same-request transport resubmission means
   resolve/read back the original dispatch, not launch fresh intelligence. The runner
   may retry individual tool/model calls only under separately specified counters and
   the same aggregate grant. SDK retries must be disabled or accounted for, not hidden.
   Logical-run identity across native attempts and uncertain-start recovery still need
   exact rules; no exactly-once model-call claim follows from deterministic request IDs.
5. **Spine verifies source freshness separately.** Define the pre-dispatch check and
   its race semantics, plus acceptance/selection and pre-delivery checks. An event edit
   after a check does not retroactively erase incurred execution; stale results cannot
   reopen fallback, suppression or an already attempted delivery branch.

The first proof can use a single bounded invocation with no dispatch retries, if
explicitly selected, while preserving configurable finite model/tool/time/cost limits.
That is a proposed simplification, not a change to the accepted budget policy.
Read-only research means no business-state mutation: external model/search calls can
still disclose data and incur cost. Do not automatically label them effect-free.

## Walkthrough: golf preparation

1. Spine selects the event's configured advisory activation and freezes the permitted
   title/time/location context, effective privacy choices, limits and deadline.
2. A bridge submits those same bytes through a versioned native admission mapping.
   Existing intent/evidence/idempotency machinery is reusable after the mapping exists.
3. Governance admits or denies the requested research capability. **This is the first
   substantive missing runtime handoff:** the current local dispatch success recorder
   does not provide the required scoped authorization and real execution.
4. A bounded runner researches and produces one of the three allowed outcomes with
   citations, validity facts and actual usage. **The real runner/tool boundary is missing.**
5. Governance validates the run/result against the authorization and accepts or rejects
   it. **Current generic evidence acceptance is insufficient for this step.**
6. Spine verifies native references and its own freshness, then atomically selects
   advisory content, permitted silence, or the ordinary reminder. No execution-system
   outbox sends the reminder. Failures preserve ordinary fallback when independently
   eligible, and explicit materialization recovery does not rerun research.

This is one read-only outcome, not an approval-bearing workflow or an autonomous
business action. No facet substrate or new people model is needed for this minimal
event-based proof; consuming either later requires its own authoritative contract.

## Transport and dependency caution

`RuntimeService` is an internal, path-based Python API, not a stable network service.
Do not let a Spine-facing request choose native database paths or registry files.
The adapter's deployment configuration owns those resources; caller correlation is
not authentication, and hashes alone do not authenticate a remote producer.

Do not casually install the native package into Spine's worker environment:
`foreman/pyproject.toml` and its Tickerd compatibility artifact require `>=0.1,<0.2`,
while Spine exact-pins runtime capability support to Tickerd `0.2.0`. This is a
declared dependency incompatibility, not proof the underlying code cannot interoperate.
Separate environments with a bounded local protocol avoid forcing a dependency upgrade;
alternatively, compatibility can be explicitly updated in the owning project. Neither
choice requires changing Tickerd here. The local unit tests below do not qualify a
co-installed or deployed runtime.

## Recommended next specification batch

Use the native implementation as a **candidate reference integration**, not an already
qualified execution provider. No new general-purpose platform or repo is justified yet.

1. In the governance project, scope the smallest native bounded-execution extension:
   persisted authorization, a real registered executor, attempt start/result/timeout
   behavior, enforceable grant/usage accounting, and typed evidence acceptance. Reconcile
   the relevant dispatch/API draft with actual code; do not attempt the whole roadmap.
2. In Spine, specify the exact submission/native-artifact mapping, reference retrieval
   and verification, freshness handoff, interruption/replay behavior, and existing
   fallback/selection integration. Keep public terminology role-based.
3. Agree the actual runner adapter and trusted transport before freezing machine
   contracts. Produce matching schemas and cross-system oracles: duplicate submission,
   crash after admission, expiry before start, narrowed/widened grants, budget exhaustion,
   disallowed outcome, changed source, late result, and fallback/result race.
4. Audit that bounded contract pair, then implement the smallest real research proof.
   Fixture-backed tests remain useful, but fake `sent` receipts cannot close the proof.

Decision needed before that implementation: which runner will execute the governed
invocation, and how its calls/evidence are enforced and observed. Foreman can be the
governance candidate without also being the reasoning runtime. No runner selection,
new service deployment, retry-policy default, or component change is approved by this report.

## Verification and source references

Executed with Spine's existing test interpreter, native source on `PYTHONPATH`, bytecode
and pytest cache disabled, using temporary test databases:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <spine>/.venv/bin/python -m pytest -q -p no:cacheprovider
  tests/unit/test_runtime_service_api.py
  tests/unit/test_evidence_lifecycle.py
  tests/unit/test_replay_verification.py
  tests/unit/test_arbiter_transition.py
  tests/unit/test_intake_submission.py
Result: 55 passed in 1.11s
```

This proves the selected existing local tests pass; it is not a new advisory oracle,
full native-spec conformance, release certification, or staging evidence.

Key sources (paths relative to this note):

- [Spine advisory requirements](../../specs/contextual-advisories.md), §§5, 7–10, 15;
  [Decision 0005](../../specs/decisions/0005-profile-scoped-advisory-execution.md).
- [Native runtime API draft](../../../foreman/docs/RUNTIME_SERVICE_API_SPEC.md), §§2–5, 8;
  [implemented API](../../../foreman/foreman/api/runtime.py), `create_intent`,
  `submit_intake`, `send_dispatch`, `produce_evidence`, `accept_evidence`, readbacks.
- [Dispatch draft](../../../foreman/docs/DISPATCH_SKILL_INVOCATION_SPEC.md), §§6–18;
  [local dispatch builder](../../../foreman/foreman/dispatch/__init__.py).
- [Intake validation](../../../foreman/foreman/intake/validation.py) and
  [service](../../../foreman/foreman/intake/service.py).
- [Arbiter](../../../foreman/foreman/arbiter/next_transition.py),
  [policy evaluator](../../../foreman/foreman/policy/evaluator.py),
  [native store](../../../foreman/foreman/storage/sqlite.py), especially
  `record_dispatch_attempt` and `accept_evidence_by_id`.
- [Evidence production](../../../foreman/foreman/evidence/accept.py) and
  [read projections](../../../foreman/foreman/evidence/projection.py).
- [Workflow boundary](../../../foreman/docs/WORKFLOW_BOUNDARY_SPEC.md), §§2, 8, 10–11;
  [approval persistence](../../../foreman/docs/APPROVAL_PERSISTENCE_SPEC.md).
- [Native dependency declaration](../../../foreman/pyproject.toml),
  [native Tickerd contract](../../../foreman/contracts/compatibility/tickerd-v0.1.json),
  [Spine Tickerd contract](../../contracts/spine-tickerd-compatibility.v1.json).

The existing [three-case gap analysis](advisory-extensibility-gap-analysis.md) remains
architectural background; this report adds code-level evidence and does not replace
or weaken the protection checklist or current advisory requirements.
