# Spine Runtime Compatibility Contract

Status: Implemented v0.1.0 on Spine runtime 0.2.0
Scope: Exact cross-repository runtime admission and generic safety-stop mapping
Authority: Normative Spine consumer requirements for supported Tickerd installations

## 1. Purpose

Spine owns coordination truth, work eligibility, storage-pressure policy, and domain
failure classification. Tickerd owns generic cadence, ownership, health/readiness,
event mechanics, and the pre-cycle safety-stop lifecycle. This contract binds those
authorities without copying Tickerd implementation into Spine or teaching Tickerd
Spine-specific concepts.

The machine-readable companion is
`contracts/spine-tickerd-compatibility.v1.json`. Its contract identity is:

```text
spine.tickerd-compatibility.v1
```

The runtime packages this machine contract, validates it against the installed Tickerd
distribution during worker admission and `system.info`, and supplies the storage safety
gate and durability latch described below.

## 2. Exact Provider Baseline

The initial compatible provider baseline is:

| Fact | Required value |
|---|---|
| Distribution name | `tickerd` |
| Package version | `0.2.0` |
| Audited source revision | `ffe613c65ea3d6fc70a1dc3603c32068f06350df` |
| Capability id | `tickerd.runtime-capabilities.v1` |
| Descriptor package | `tickerd` |
| Descriptor resource | `contracts/tickerd.runtime-capabilities.v1.json` |
| Descriptor SHA-256 | `215f9aa6b54e6c0e6186796a55d78e1c5a270adc9b3ccefb433df5a3bb87b58b` |

Package version, capability id, and descriptor hash are exact, case-sensitive runtime
admission facts. Semver range inference, prefix matching, "latest" selection, or
acceptance of an altered descriptor under the same capability id is forbidden.
Additional Tickerd capabilities do not satisfy a missing required fact and do not
invalidate this contract unless they alter behavior claimed by the required identity.

The source revision is deployment provenance. A deployment installing from a checkout
MUST verify that checkout's exact Git revision before installation. A wheel or other
artifact MUST carry build provenance binding it to that revision. Spine runtime does
not invent a source revision when the installed distribution does not expose one.

An arbitrary sibling source directory placed on `PYTHONPATH` is not deployment proof.
The runtime requires importable distribution metadata for `tickerd`; editable
installation is permitted only when deployment separately verifies the checkout
revision and the runtime checks below still pass.

## 3. Required Provider Claims and API

The required claim ids are the exact sorted set:

- `bounded_durable_event_file_storage`
- `collapsed_reconciliation_cadence`
- `failure_propagation_and_fatal_threshold`
- `generic_pre_cycle_safety_stop`
- `health_and_readiness_transitions`
- `meaningful_or_verbose_event_summaries`
- `runtime_modes`
- `singleton_ownership_heartbeat`
- `tick_cadence_no_burst_catchup`

Spine admission verifies the descriptor's declared claim ids against that set. It does
not infer a claim from the presence of a similarly named class or configuration field.

The descriptor-declared capability API module is exactly `tickerd.capabilities`. It
MUST expose `RUNTIME_CAPABILITY_ID`, `RUNTIME_CAPABILITY_DESCRIPTOR`, and
`require_runtime_capability`. Tickerd's consumer-facing top-level module is exactly
`tickerd` and MUST expose those same three names plus `SafetyAction`, `SafetyContext`,
and `SafetyDecision`. The three capability objects exported from `tickerd` MUST be the
same Python objects exported from `tickerd.capabilities`, not copies or independently
loaded values. The protocol module is exactly `tickerd.protocols` and MUST expose
`SafetyGate`.

Both capability-module and top-level `require_runtime_capability` references therefore
name the same function. Calling it with `tickerd.runtime-capabilities.v1` MUST succeed
and return the installed descriptor. A different exact id MUST fail closed through
Tickerd's capability error rather than selecting a nearby version. The machine contract
records all three module locations and their required exports; implementations MUST NOT
choose one location while silently ignoring a mismatch at another.

## 4. Runtime Admission

Worker admission adds Tickerd dependency validation after Spine's required runtime-
contract comparison and before effective-budget validation. The complete ordering is:

1. database availability and SQLite open;
2. exact ledger schema version;
3. schema-object manifest;
4. Spine required runtime contracts;
5. Tickerd distribution, public API, capability, descriptor, and claims; and
6. Spine effective-budget catalog.

The Tickerd check is bounded by installed package metadata and one constant-size
packaged descriptor. It MUST NOT inspect domain rows, search arbitrary source trees,
contact a package registry, or fetch a repository during worker startup.

Validation performs all of the following:

1. resolve installed distribution metadata for exact name `tickerd`;
2. exact-match package version `0.2.0`;
3. import and verify the required public API;
4. call `require_runtime_capability` with the required id;
5. resolve package `tickerd` through the runtime resource API, hash the raw bytes of
   relative resource `contracts/tickerd.runtime-capabilities.v1.json`, and exact-match
   the required SHA-256;
6. parse that same resource and verify its capability id, schema version, case-
   sensitivity declaration, incompatible-change rule, public-API declaration, exact
   claim-id set, safety outcomes, governed-operation vocabulary, and terminal-reporting
   bounds; and
7. compare the parsed resource with the public descriptor by value after recursively
   converting immutable mappings/tuples into ordinary JSON objects/arrays.

Any failure uses the worker admission branch in Section 5.4 of
`specs/agent-command-contract.md`. No failed process starts Tickerd, discovers or
reconciles work, creates an attempt, or contacts an adapter.

## 5. Failure Diagnostic

Tickerd incompatibility emits the single worker diagnostic:

```text
event=ledger_runtime_preflight_failed
reason=runtime_dependency_mismatch
dependency=tickerd
compatibility_contract=spine.tickerd-compatibility.v1
```

It also contains the required package version, capability id, and descriptor hash;
nullable installed values when safely discoverable; and `mismatch_fields`, a sorted,
unique, non-empty array drawn from:

- `package_import`
- `package_version`
- `public_api`
- `capability_id`
- `descriptor_sha256`
- `descriptor_shape`
- `required_claims`

The schema marks that array with `x-spine-order=lexicographic`. Draft 2020-12 validators
may treat that extension as an annotation, so Spine's diagnostic serializer and the
executable contract test MUST enforce the ordering after ordinary schema validation.
Accepting an unsorted array is non-conforming even when a generic JSON Schema validator
accepts it.

When distribution metadata or import is unavailable, installed facts that cannot be
proven are `null`; they are never guessed. Exceptions are reduced to the stable
mismatch vocabulary and MUST NOT expose environment secrets or arbitrary traceback
text. The ordinary worker `DOWN`/not-ready, one-diagnostic, stderr-fallback, nonzero-
exit, supervisor-only-retry, and no-processing requirements still apply.

## 6. System Readback Transition

The containment implementation promotes `system.info` from
`spine.system-info.v1` to `spine.system-info.v2`. The v2 shape is defined by
`contracts/schemas/system-info-response-v2.schema.json`. It retains all v1 facts and
adds `runtime_dependencies`, sorted lexicographically by `name`.

The Tickerd element contains:

- `name=tickerd`;
- installed `package_version`;
- `capability_id`;
- raw-resource `descriptor_sha256`;
- `compatibility_contract=spine.tickerd-compatibility.v1`; and
- `status=compatible`.

`system.info` returns success only after the resolved dependency is compatible. The
`system.info` registry entry requires `spine.tickerd-compatibility.v1`, and the v2
`implemented_contract_versions` contains both `spine.system-info.v2` and
`spine.tickerd-compatibility.v1`. Spine runtime `0.2.0` implements that atomic
transition: the command registry, implemented-contract declarations, handler, schema,
documentation, and tests all name v2. A v1 response remains historical and MUST NOT be
emitted by this runtime.

## 7. Spine Safety-Gate Mapping

Spine supplies a service-owned implementation of `tickerd.protocols.SafetyGate`.
Tickerd remains unaware of SQLite, ledger paths, storage thresholds, notifications,
delivery targets, or Spine reason codes.

The Spine gate returns:

- `SafetyDecision.allow()` when no latched durability failure exists and every measured
  authoritative filesystem is above its critical threshold;
- `SafetyDecision.suspend("storage_safety_stop", facts)` when pressure is critical and
  `critical_storage_action=suspend`; or
- `SafetyDecision.terminate_nonzero("storage_safety_stop", facts)` when pressure is
  critical and `critical_storage_action=exit_nonzero`.

An expected measurement failure returns
`SafetyDecision.terminate_nonzero("storage_measurement_failed", facts)`; it is not
raised as an exception. An unexpected gate exception follows Tickerd's audited
`safety_gate_exception` fail-closed behavior.

Tickerd's durable terminal envelope remains generic:

```text
event=safety_stop
reason=storage_safety_stop | storage_measurement_failed
```

The Spine domain diagnostic is the bounded `reason_facts` object. It carries
`reason_facts_contract=spine.storage-safety-facts.v1`, the selected
`critical_storage_action`, `measured_at_utc`, and a closed `primary_reason`.
`storage_safety_stop` uses `critical_storage_pressure` or
`ledger_durability_failure`; `storage_measurement_failed` uses
`storage_measurement_failure`. Critical pressure has `pressure_state=critical` and
requires one or two deterministically ordered filesystem measurements. A latched
durability failure or measurement failure may contain zero, one, or two measurements
because the worker may not be able to obtain a trustworthy filesystem sample. A
measurement contains sorted unique roles from `ledger` and `worker_state`, a
non-secret stable filesystem identity, and decimal-string free, warning, critical,
and reserve byte facts. Paths are omitted. Measurements sharing one filesystem
identity collapse into one element. Measurement failure additionally carries a stable
non-secret `measurement_error_category`. The reason facts MUST fit Tickerd's configured
`safety_reason_max_bytes`; truncation is a non-conforming Spine configuration, not
permission to lose the storage decision facts.

Tickerd owns the envelope's trace, safety-check identity, timestamps, outcome,
`DOWN`/not-ready facts, reporting-failure list, and bounded stderr fallback.

## 8. Mid-Cycle Durability Latch

The Tickerd gate is evaluated before a cycle. A ledger durability failure may still be
discovered while Spine processes an item. Spine therefore owns one process-local,
monotonic safety latch shared by its work source, reconciler, processor, and safety
gate.

Within one process:

- a canonical-ledger `SQLITE_FULL`, failed commit, or failed fsync latches
  `ledger_durability_failure` before the failing boundary returns;
- the failing operation cannot report success;
- every later Spine processor or reconciler boundary checks the latch before mutation
  or adapter invocation and fails/blocks without further external effects;
- the latch cannot be cleared in process;
- the next Tickerd safety evaluation returns the configured stop outcome with
  `primary_reason=ledger_durability_failure`; and
- operator or supervisor recovery requires a new process and fresh admission.

The latch is containment evidence, not canonical ledger truth, and does not replace
the durable attempt record for an external operation already started. Ambiguous
provider outcomes remain governed by the future recovery contract.

## 9. Installation and Deployment Proof

A deployment records or verifies, before starting Spine worker services:

- Spine release identity;
- Tickerd distribution version;
- Tickerd source revision or artifact provenance;
- capability id;
- packaged descriptor SHA-256; and
- the successful bounded worker admission result.

Installing from the known checkout and installing a wheel built from the known revision
are both allowed. Importing an unverified working tree through `PYTHONPATH` alone is not.
No deployment may rewrite the required capability or descriptor hash to accommodate a
locally modified provider without a new reviewed compatibility contract.

## 10. Acceptance Criteria

1. The machine contract validates against its schema and agrees byte-for-byte with the
   constants in this document.
2. A real Tickerd `0.2.0` installation from the audited revision passes the cross-repo
   contract test.
3. Missing distribution metadata, wrong version, missing API, wrong capability,
   descriptor drift, malformed descriptor, or missing claims each fail admission with
   the deterministic dependency diagnostic and zero runtime cycles.
4. `system.info.v2` reports the exact compatible dependency facts without mutating the
   ledger or reading domain rows.
5. Critical pressure stops before governed work, and mid-cycle durability failure
   prevents every later external effect in that process.
6. Tickerd retains generic runtime authority; Spine retains storage measurement,
   thresholds, domain reason facts, ledger behavior, and side-effect authorization.
7. `system.info.v2` and worker admission advertise the compatibility contract only
   after exact validation succeeds.
