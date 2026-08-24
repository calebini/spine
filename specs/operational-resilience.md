# Spine Operational Resilience and Boundedness Contract

Status: Draft v0.1.1; post-audit requirements baseline, not an implementation declaration
Scope: Cross-cutting resource bounds, failure containment, recovery, dependency admission, and operational proof
Authority: Normative resilience target for Spine runtime, worker, adapter, and host integration

## 1. Purpose

Spine is an append-oriented canonical coordination ledger. That posture is useful only
if ordinary operation cannot exhaust the host, amplify one bad fact into a service-wide
failure, silently strand work, or repeat an ambiguous external effect.

This specification defines the cross-cutting operational guarantees that apply across
commands, scheduling, notification work, Tickerd integration, SQLite, adapters, and
host supervision. It centralizes invariants that would otherwise be duplicated across
domain specifications. It does not replace the semantic authorities for recurrence,
notification scheduling, command behavior, or ledger truth.

The initial resilience objective is:

> Repetition, backlog, history, partial failure, and resource pressure remain bounded,
> observable, and recoverable without weakening Spine's canonical evidence model.

## 2. Status, Authority, and Non-Goals

This document is a draft target for the next operational-hardening initiative. A
runtime MUST NOT advertise conformance merely because this document exists. Each
requirement becomes implemented only with matching runtime declarations, persistence
changes where required, focused tests, and the acceptance campaign in Section 12.

Authority remains divided as follows:

- `specs/ontology.md` owns canonical tables, identities, stored lifecycle values, and
  relational constraints.
- `specs/notifications.md` owns notification opportunity, materialization,
  reconciliation, and notification-work semantics.
- `specs/agent-command-contract.md` owns public requests, responses, failures, dry
  run, and bounded read behavior.
- `specs/architecture.md` owns component boundaries and runtime relationships.
- this document owns cross-cutting resource budgets, sustained-operation bounds,
  failure isolation, recovery requirements, and operational qualification.

When a resilience requirement needs a new stored state, field, command, error, or
machine-readable shape, its owning specification and contract MUST be amended before
implementation. This document does not silently extend a closed ontology enum.

This specification does not:

- authorize automatic deletion, archival, compaction, or truncation of canonical
  ledger evidence;
- make Tickerd, a supervisor, or an adapter authoritative for coordination truth;
- turn logs, metrics, caches, or health files into ledger facts;
- require full-ledger scans during routine command or worker admission;
- treat backups, WAL checkpointing, or `VACUUM` as retention policies; or
- define provider-specific retry rules that bypass the generic attempt boundary.

## 3. Responsibility Matrix

| Concern | Authority | Required boundary |
|---|---|---|
| Coordination truth, work eligibility, attempt evidence, recovery state | Spine | Persisted, deterministic, inspectable |
| Runtime cadence, ownership, health, readiness, event emission | Tickerd | Versioned capability consumed by Spine |
| Provider request mapping, idempotency support, outcome classification | Adapter | No hidden retry or evidence store |
| Process restart, filesystem quota, reserved capacity, external log rotation | Host or supervisor | Cannot redefine Spine lifecycle |
| Timezone-data installation and release compatibility | Deployment boundary | Exact versions available before affected work runs |
| Ledger archival or compaction | Future Spine lifecycle contract | Explicit, verified, never inferred from low disk |

Spine MUST declare the exact Tickerd runtime contract or capability family it requires.
Worker admission fails closed when the installed Tickerd release cannot prove those
capabilities. Loading an arbitrary sibling source tree through `PYTHONPATH` is not a
sufficient compatibility contract. Before implementation conformance is declared, this
cross-repository promise MUST be registered in a dedicated repository compatibility
specification with matching machine-readable capability and contract-test evidence.

Host controls provide defense in depth. A process-level storage bound remains required
even when external `logrotate`, a filesystem quota, or a dedicated volume is present.

### 3.1 Effective budget catalog

A conforming release publishes one versioned effective-budget catalog through supported
runtime readback. The catalog identity is `spine.operational-budget-catalog.v1`. The
catalog contains at least positive `max_request_bytes`, `event_log_max_bytes`, and
`event_log_backup_count`; warning, critical, and reserve free-space byte thresholds;
automatic work/reconciliation batch limits; retry initial delay, backoff kind, maximum
delay, and maximum attempts for each retry-capable adapter; any transitional dry-run
database-size ceiling; and `critical_storage_action`, exactly `suspend` or
`exit_nonzero`. The readback exposes the catalog identity and each safe effective value;
a value sourced from a secret is represented by `effective_value_redacted=true` and is
never returned by value.

The storage thresholds satisfy `warning_free_bytes > critical_free_bytes >=
reserve_bytes > 0`. Missing or invalid mandatory values, and zero or negative mandatory
numeric budgets, fail worker admission. Configuration bindings may use environment, files, or supervisor injection,
but the effective value and its catalog version are visible without exposing secrets.
A release may choose capacity-appropriate values; behavior is deterministic for the same
catalog and source facts. Hidden unbounded defaults are forbidden.

Budget admission failure uses the worker preflight boundary in
`specs/agent-command-contract.md` Section 5.4. Its single diagnostic has
`reason=runtime_budget_invalid`, `budget_catalog_version` equal to the catalog identity,
and `budget_violations`, a non-empty array sorted lexicographically by `budget_key`, then
`validation_category`, then `required_constraint`, with exact duplicates removed. Each
violation contains those three fields. `validation_category` is exactly `missing`,
`invalid_type`, `non_positive`, `unsupported_value`, or `constraint_violation`.
`required_constraint` is the stable catalog-declared constraint identifier. A missing
value uses `effective_value=null`; every other violation contains exactly one of a safe
canonical-JSON scalar `effective_value` or `effective_value_redacted=true`. Validation
and diagnostic construction occur before any runtime cycle starts.

## 4. Bounded Routine Work

### 4.1 Bound definition

A routine operation is bounded only when its maximum work and memory are determined by
accepted request limits, configured batch or horizon limits, and explicitly selected
source facts. Returning a bounded response after first loading, counting, sorting, or
copying the complete ledger is not bounded.

Routine operations include:

- interactive commands and dry runs;
- worker admission and startup;
- each Tickerd cycle and reconciliation invocation;
- eligible-work discovery;
- occurrence and notification expansion;
- agenda and schedule readback;
- stale-work discovery and repair; and
- adapter attempt preparation and result handling.

A bounded routine path MUST NOT require work, memory, or IO proportional to the complete
historical ledger merely to return or mutate a bounded selected set. Indexed lookup may
scale with index depth and the accepted batch, range, or page; it may not fall back to
full-ledger hydration, copying, counting, or sorting. Deep ledger verification,
migration, export, backup, and future archival are outside the routine path and MUST be
invoked explicitly.

### 4.2 Discovery, paging, and fairness

Every repeating discovery loop MUST use stable keyset paging, a durable or
deterministically reconstructable continuation, or an equivalent bounded fair
traversal. It MUST NOT use full-set `COUNT` plus growing `OFFSET` as its steady-state
fairness mechanism.

Applying a result limit after fetching all eligible rows is forbidden. Filtering stale
rows MUST make bounded forward progress; permanently stale rows MUST NOT remain ahead
of actionable rows forever. Repeated exhausted or non-dispatchable items MUST NOT
consume the dispatchable-work limit.

When an internal bounded read returns `has_more=true`, a mutating workflow that claims
complete materialization or reconciliation MUST continue through the required pages,
persist an explicit incomplete continuation, or fail before partial success. It MUST
NOT silently treat the first page as the complete eligible set.

### 4.3 Request and expansion budgets

Every public and internal request boundary MUST enforce:

- a maximum encoded request size before full JSON materialization;
- maximum text lengths for caller-controlled durable fields;
- maximum collection cardinality for policies, offsets, selectors, explicit ids, and
  related-item sets;
- a maximum normalized opportunity or occurrence density per request and per cycle;
  and
- a maximum response/evidence size or explicit pagination contract.

The core semantic boundary, not only a high-level convenience schema, owns these caps.
Lower-level commands MUST NOT permit a caller to bypass a composite-surface limit.

### 4.4 Dry run

Dry run MUST preserve validation, deterministic would-be identities, and no-mutation
semantics without copying the complete ledger into memory or creating a second
unbounded database image. Its resource use MUST be bounded by the command's selected
facts and output budget.

Until a bounded dry-run mechanism exists, a runtime MAY use a documented database-size
admission ceiling and fail closed before copying. Such containment is transitional and
does not satisfy final conformance.

## 5. Durable Growth and Storage Containment

### 5.1 Storage classes

Every persisted or file-backed output belongs to exactly one class:

1. **Canonical truth and safety evidence** — item/version truth, policy facts, work,
   attempts, audit, and replay evidence. These facts are never deleted automatically
   under this specification.
2. **Reconstructable derived state** — data that can be regenerated from canonical
   truth. Removal still requires an explicit owning lifecycle and verification rule.
3. **Operational telemetry** — events, diagnostic JSONL, debug traces, and fake-send
   artifacts. These require configured byte/count/time bounds and rotation or expiry.
4. **Ephemeral observation** — idle ticks, planned skips, cache entries, and transient
   counters that need no durable record.

An idle non-reconcile tick writes no durable telemetry. An unchanged automatic no-op
plan writes no ledger fact. Startup, shutdown, health transitions, reconciliation,
work activity, failures, and explicit operator commands remain observable and MUST NOT
be suppressed merely to reduce storage.

Every file-backed telemetry sink MUST enforce its configured bound itself. Defaulting
an optional sink limit to unbounded is forbidden for a long-running deployment.
Observe-only and suspended modes MUST aggregate or rate-limit repeated reports for the
same unchanged blocked work; safety observation MUST NOT become an amplification loop.

### 5.2 Ledger and WAL

Spine MUST expose a supported storage-health readback containing, at minimum, database
file size, WAL size, major durable-family counts or size estimates, configured budgets,
and current pressure state. The readback itself uses maintained metadata, bounded
sampling, or another bounded mechanism rather than scanning every durable row. Operators
MUST NOT need raw SQL to determine whether the ledger is approaching its operational
boundary.

The SQLite integration MUST define and observe WAL checkpoint behavior, checkpoint
failure, long-reader pressure, and journal-size expectations. A WAL threshold is not a
retention policy and MUST NOT cause canonical row deletion.

### 5.3 Disk pressure

Deployments MUST configure warning and critical free-space thresholds plus a reserved
capacity sufficient to record a final health transition and shut down safely. The
thresholds and measured filesystem MUST be visible in health/readback.

At critical pressure, the worker MUST become `DOWN` and not ready for new external
effects before attempt preparation or adapter invocation. It MUST preserve already
committed truth, emit the single bounded terminal report below when any channel remains
available, and perform the catalog's declared `critical_storage_action`. `suspend`
means the process performs no further runtime cycles, reconciliation, attempt creation,
or adapter calls until an operator or supervisor terminates it. `exit_nonzero` means it
terminates after the one report attempt; the supervisor MUST use bounded backoff and
MUST NOT restart it while critical pressure remains. Neither action permits repeated
failure-evidence writes into the remaining space.

For one operation or worker cycle, storage-stop precedence is deterministic:

1. A canonical-ledger `SQLITE_FULL`, failed commit, or failed fsync is
   `primary_reason=ledger_durability_failure`. The intended mutation is not proven
   durable, every command or cycle result is failure, and no response may claim
   success. This reason wins even when a pressure threshold or reporting sink also
   fails.
2. When no ledger-durability failure occurred, a measured critical-threshold breach is
   `primary_reason=critical_storage_pressure`.
3. Event-sink and health-sink failures never replace the primary reason and never
   reinterpret a committed canonical transaction. They appear only as the sorted,
   unique `reporting_failures` values `event_sink_unavailable` and
   `health_sink_unavailable`. A sink failure outside a storage-stop incident follows
   the owning Tickerd capability contract.

Either primary reason invokes the same `DOWN`/not-ready transition, prohibition on
further external effects, and declared `critical_storage_action`. An interactive
command encountering a ledger-durability failure returns its ordinary structured
environment failure after rollback or failed-commit handling; it does not claim or
mutate worker health.

The terminal diagnostic is one JSON object with `event=storage_safety_stop`, the
selected `primary_reason`, `state=DOWN`, `readiness=false`, the declared
`critical_storage_action`, and `reporting_failures` (an empty array when neither sink
failed). The worker first attempts to persist the not-ready health snapshot. It then
attempts to emit the diagnostic once to the configured event sink, including
`health_sink_unavailable` when the snapshot write failed. Only when the event sink
rejects that diagnostic may the worker make one fallback attempt to write it to stderr,
updated to include `event_sink_unavailable`. Stderr failure is terminal and triggers no
further write. Failure of any reporting channel MUST NOT recursively invoke that channel
or create canonical ledger evidence. The selected action and prohibition on further
external effects hold even when no diagnostic can be emitted.

## 6. Worker Failure Containment

One item, policy, recurrence, temporal binding, route, or adapter response is the
default failure-isolation unit. A deterministic domain failure for one unit MUST NOT
become a fatal runtime failure for unrelated eligible work.

The worker MUST distinguish:

- **item-scoped failure** — quarantine or defer that unit with structured identity and
  bounded retry/backoff while later units remain eligible;
- **dependency degradation** — pause affected bindings or adapters, expose degraded
  health, and apply a circuit breaker;
- **ledger/runtime invariant failure** — stop processing, become not ready, and require
  supervisor/operator recovery; and
- **resource exhaustion** — follow Section 5.3.

Reconciliation failure MUST preserve the responsible item/binding identity and reason;
reducing it to a generic `cycle_failed` result is insufficient. A failed reconciliation
boundary MUST NOT be retried every tick without backoff. Repeated identical failures
MUST be deduplicated or rate-limited while their health impact remains visible.

Worker startup MUST validate that a scheduler actor or other required canonical runtime
principal can be resolved before Tickerd reports ready. Absence is an admission failure,
not a repeating reconciliation failure.

Observe-only and suspended modes MUST inspect work without mutating it or invoking an
adapter. Their reports remain bounded even when the same eligible backlog persists.

## 7. Work, Attempt, and Retry Recovery

### 7.1 Retry policy

Every retry-capable adapter binding MUST declare validated positive values for initial
delay, backoff strategy, maximum delay, maximum automatic attempts, and deterministic
jitter policy when jitter is used. A fixed retry forever is forbidden.

Exhausting the automatic retry budget produces an operator-visible terminal or
quarantined condition. It MUST NOT return silently to ordinary eligibility. Retry
state remains attached to the original work instance and never becomes a new scheduled
notification opportunity.

Adapter-level circuit breaking MUST bound attempts during a shared provider outage.
The breaker affects execution eligibility only; it does not rewrite schedule or item
truth.

### 7.2 In-progress recovery

Starting work and preparing an attempt occur before an external boundary, so the
runtime MUST define recovery for process death at every intervening point. An
in-progress authorization requires a lease or equivalent durable owner and expiry
facts. After expiry, a recovery workflow—not ordinary discovery by accident—classifies
the work and attempt before further external contact.

No `in_progress` work may remain permanently undiscoverable. Recovery MUST handle at
least:

- work started but no attempt persisted;
- started attempt persisted but adapter not invoked;
- adapter invocation began but no outcome was recorded;
- attempt outcome recorded but work outcome not finalized; and
- process death while scheduling a retry.

The exact stored fields and transitions require an ontology amendment and migration
before this section can be implemented.

### 7.3 Ambiguous external outcomes

A transport timeout, connection loss, or process death after external invocation does
not prove failure. It is an ambiguous outcome. The runtime MUST NOT automatically issue
a new external operation with a different idempotency identity merely because the local
outcome is unknown.

Before automatic retry, the adapter contract MUST prove one of:

- the provider honors a stable operation-level idempotency identity across retries;
- the provider can be queried to reconcile that exact operation; or
- the prior operation is definitively known not to have been accepted.

Otherwise the work enters an explicit operator-visible unknown/quarantined condition
and requires reconciliation. The exact attempt/work enum changes and uniqueness rules
require an accepted decision and ontology amendment; until then, ambiguous real sends
MUST fail closed without automatic retry.

## 8. Runtime and Environment Compatibility

### 8.1 Tickerd capability admission

Worker preflight MUST exact-match a versioned Tickerd capability contract covering at
least event-summary filtering, event-storage bounds, runtime mode behavior,
reconciliation cadence, failure classification, health/readiness, and ownership lease
semantics. `system.info` and worker diagnostics expose the resolved Tickerd version and
capability id.

### 8.2 Timezone data

Every actionable local schedule remains bound to its concrete timezone-database
version. A deployment MUST either:

- run against an immutable pinned timezone-data release for the ledger; or
- provide side-by-side resolution for every version still referenced by actionable
  work and schedules.

Installing a new system timezone database MUST NOT silently make old canonical schedule
facts unresolvable. Deployment admission MUST prove availability through a bounded
version catalog or equivalent maintained index; it MUST NOT scan the complete ledger at
every worker start. Version migration or rebasing is an explicit command/lifecycle and
cannot occur as hidden read-time reinterpretation.

### 8.3 Adapter secrets

Adapter credentials MUST be supplied through a mechanism that does not expose them in
process argument listings, event records, receipts, or command output. Diagnostics may
name the credential source but never the credential value.

## 9. Readback and Operational Evidence

Bounded readback MUST make current failure evidence reachable. Where work or attempt
history can exceed one page, the surface MUST provide explicit ordering and cursors;
an oldest-first fixed limit without a route to recent evidence is insufficient.

The operational surface MUST distinguish:

- authored policy truth;
- expanded opportunity state;
- materialized work state;
- attempt state and retry budget;
- provider outcome, including ambiguity when implemented;
- reconciliation/quarantine state;
- storage pressure and worker readiness; and
- current runtime dependency versions.

Metrics and health SHOULD include bounded counters for eligible backlog, stale backlog,
in-progress age, retrying and exhausted work, reconciliation failures, event-log bytes,
database/WAL bytes, and remaining filesystem capacity. Metrics do not replace canonical
evidence.

## 10. Implementation and Migration Gates

Implementation may proceed in slices, but a slice MUST NOT weaken an existing safety
boundary while waiting for later work.

1. **Containment:** enforce telemetry bounds, low-disk observation/stop conditions,
   retry configuration validation, dependency version reporting, and transitional
   dry-run admission.
2. **Recovery:** add failure isolation, retry budgets, circuit breaking, in-progress
   recovery, and ambiguous-outcome handling with the required ontology migration.
3. **Scalability:** replace full-set discovery and hydration, make internal mutation
   paging complete, and enforce core request/density budgets.
4. **Storage lifecycle:** measure legitimate ledger growth and design archival only
   under a separately approved contract. This specification grants no deletion power.

Before the Recovery slice, an accepted architecture decision MUST settle operation-level
idempotency, ambiguous attempt outcome, work lease ownership/expiry, and operator
reconciliation. Before the timezone strategy changes, an accepted decision MUST settle
immutable single-version deployment versus side-by-side timezone bundles.

## 11. Required Failure and Soak Vectors

A conforming implementation publishes deterministic test fixtures or executable
scenarios for at least:

- 24 hours of idle ticks with zero ledger growth and bounded telemetry growth;
- a persistent observe-only backlog with bounded repeated reporting;
- more eligible and stale work than one cycle limit, proving fair progress;
- more than 1,000 actionable opportunities in one horizon, proving complete,
  continuation-aware materialization or explicit pre-mutation failure;
- one poison recurrence or binding while unrelated work continues;
- a missing scheduler actor failing admission before readiness;
- missing, malformed, non-positive, unsupported, and cross-threshold budget values,
  proving one sorted `runtime_budget_invalid` diagnostic and zero runtime cycles;
- a prolonged provider outage proving backoff, circuit breaking, retry exhaustion, and
  bounded evidence growth;
- process termination at every boundary listed in Section 7.2;
- a provider timeout after possible acceptance, proving no duplicate automatic send;
- an installed timezone-data change while old actionable schedules remain;
- a blocked WAL checkpoint or long reader;
- warning and critical disk thresholds plus `SQLITE_FULL` during a transaction;
- coincident ledger-durability, critical-threshold, health-sink, and event-sink failures,
  proving primary-reason precedence, one stderr fallback, and no recursive report;
- a production-sized ledger dry run with bounded memory and latency; and
- a large-ledger agenda/readback request whose work is bounded by accepted filters and
  page size.

Tests use fake adapters and disposable ledgers unless a separate operation explicitly
authorizes external effects. A short unit test that executes one cycle is not evidence
of sustained boundedness.

## 12. Acceptance Criteria

1. Idle automatic operation creates no ledger rows and cannot grow any telemetry file
   beyond its configured bound.
2. Routine command, worker, discovery, expansion, readback, and dry-run paths have
   explicit memory, row, and output bounds independent of total historical ledger size.
3. Every mutating workflow either processes its complete declared bounded set, exposes
   a deterministic continuation, or fails before partial success.
4. One item-scoped deterministic failure cannot crash-loop or starve unrelated work.
5. Provider outage cannot cause unbounded retry, attempt, rendering, receipt, or event
   growth.
6. Process death cannot leave work permanently undiscoverable or authorize an unsafe
   duplicate external effect.
7. Ambiguous external outcomes are reconciled or quarantined; they are never treated as
   proven failure solely to permit a new idempotency identity.
8. Disk pressure becomes observable before exhaustion and prevents new external effects
   at the critical threshold without deleting canonical evidence.
9. WAL growth, telemetry growth, backlog, retry exhaustion, and in-progress age are
   visible through supported operational readback or metrics.
10. Tickerd and timezone-data compatibility are exact, visible admission facts rather
    than deployment assumptions.
11. Existing transaction, foreign-key, replay, stale-work, provenance, and pre-write
    attempt gates remain intact.
12. The full failure and soak corpus in Section 11 passes before production conformance
    is declared.
