# Decision 0006: Evidence-bound timezone compatibility

Status: Accepted logical policy v1.0.0 — implemented by SPINE-062 in runtime
0.10.1/schema 19 and maintenance 0.6.0+tzdb.1/schema 15.
Machine contract: [timezone-compatibility.md](../timezone-compatibility.md).
Date: 2026-10-21
Accepted policy: 2026-10-22

## Problem and inspected behavior

The operator reports production runtime 0.6.0/schema 15 failing agenda resolution
after host tzdata changed from 2026c to 2026e. Authored pins remain intact.
The inspected 0.10.0 mainline baseline also rejects the mismatch in `resolve_local_instant`, recurrence
timezone-context validation, and notification rendering's `_display_zone`.
Changing only an agenda adapter would leave other resolution paths inconsistent.

The reported incident is distinct from the deferred SPINE-004–007/010 work. This
decision neither activates those initiatives nor authorizes deployment. The inspected mainline baseline
was runtime 0.10.0/schema 19 with unrelated people-authoring work in
progress; installing mainline is not a schema-15 hotfix.

## Accepted policy: automatic per-zone equivalence

Keep the authored timezone version as canonical intent. A resolver from another
release MUST be admitted automatically when its complete TZif bytes for the exact
requested IANA zone match a trusted reference for that zone in the authored
release. No release-pair allowlist, per-upgrade operator approval, or prior
registration of the runtime release is required. Paris and Chicago are incident
examples, not the boundary of this rule: it applies to every zone with trusted
authored-release evidence.

The comparison is direct against the authored baseline on each admission. Do not
infer compatibility from release order, regional proximity, zone aliases, suffix
normalization or a chain of previous substitutions. A previously unseen runtime
version is acceptable when its actual bytes match; an unknown authored baseline
is not. `2026c` and `2026c-rearguard` remain distinct baseline keys. Different
runtime labels, including suffixes, do not themselves require rejection if direct
byte identity is established and provider metadata is valid.

Evidence method `identical_tzif_bytes.v1` compares the complete, unmodified TZif
file, including all historical transitions, offsets, abbreviations and the
future-rule footer. Equality can be checked directly when reference bytes are
retained, or by matching their trusted SHA-256 digest and byte length. Do not
normalize bytes or discard historical sections or footers to obtain a match.
Same compiler/version/options are useful when generating comparison evidence but
are not a runtime admission condition when the resulting bytes are identical.

Different bytes do not establish incompatibility of meaning, but they do not pass
this rule. They require the original data or a separately specified semantic
equivalence method. A human release-pair waiver cannot override the byte check.
Missing or untrusted baselines, malformed evidence/data and inconsistent provider
metadata fail closed. Sampling dates and release notes are not equivalence proofs.

| Authored-zone evidence | Actual candidate data | Decision |
| --- | --- | --- |
| Trusted complete reference | Identical bytes, any identifiable runtime release | Automatically admit and emit substitution diagnostic when release differs |
| Trusted complete reference | Different bytes | Reject substitution; use original data or separately established semantic equivalence |
| Missing, invalid or untrusted reference | Any data from another release | Reject substitution |

This augments exact authored-release availability; it does not remove that existing
path. A version string by itself cannot establish cross-release equivalence. The
[local evidence](../../docs/TZDB_COMPATIBILITY_EVIDENCE.md) illustrates baseline
generation and comparison, not an activated release-pair allowlist or proof of the
production host's actual bytes.

## Trusted baseline lifecycle

Retain immutable reference bytes or fingerprints for the exact authored version
and zone before those provider bytes are replaced. Baselines may be captured by
trusted authoring/deployment machinery from an authenticated versioned provider,
or provisioned from a verified archive of the authored release. Reference
provenance must bind version, zone, artifact/build identity, digest and byte length.
Only complete, validated, untruncated zone data qualifies. Retain references while
schedules still require them; a host upgrade must not overwrite the old evidence.

This is approval of the admission rule, not trust-on-first-use of arbitrary files.
Do not synthesize an old baseline from the new installed data, relabel a new digest
as the authored version, or enroll reference evidence as a side effect of readback.
For legacy schedules without retained fingerprints, establish the reference from
trusted original-release artifacts; otherwise cross-release resolution stays
unavailable. Existing canonical receipts must not be rewritten to backfill evidence.

A baseline catalog may contain multiple independently evidenced builds of an
authored release/zone, such as fat and slim. Each build needs its own complete
reference and provenance; one encoding's fingerprint does not authorize another.
When the authored provider/build or captured fingerprint is known, that reference
controls admission: matching a different catalog build must not bypass it. For
legacy version-only pins, baseline provisioning must establish which original
provider/build evidence applies. If available original-release artifacts disagree
and the applicable reference cannot be established, fail cross-release admission;
do not choose whichever artifact happens to match the new installed bytes. Adding
another catalog build must not silently replace an existing schedule's baseline.
Baseline ingestion is a trusted operation, not manual approval of every subsequent
database release. The [runtime contract](../timezone-compatibility.md) implements one immutable build
per authored version/zone in a deployment catalog. Multiple builds for the same
key are rejected; no ledger migration is introduced.

## Machine agreement

Contract identifier: `spine.timezone-compatibility.v1`. The closed schema and trusted
ingestion interface are defined by [the runtime contract](../timezone-compatibility.md).
The catalog contains authored-zone references, not approved requested/runtime
version pairs. It is a resolver trust input, not environment free text or a cache
automatically populated from the current provider during reads.

Each entry should identify:

- Exact `authored_version`, `timezone`, and reference build identity.
- Evidence method `identical_tzif_bytes.v1` and a stable `evidence_id`.
- Authenticated authored-release artifact origin and SHA-256, internal version
  label, and source/compiler or trusted provider-capture provenance.
- Complete reference TZif SHA-256 and byte length, encoding/build options, and
  untruncated coverage including the footer.

Runtime version, provider identity and candidate digest belong to the observed
resolution decision, not the baseline catalog's eligibility key. No catalog edit
is needed for a new runtime release whose candidate bytes already match.

Admission must reject duplicate or conflicting reference identities, invalid hashes, unknown
methods and incomplete evidence. No semantic transition parser or interval-limited
substitution is proposed for the first version. Supporting either later requires
its own precise equivalence and range contract.

## Resolution boundary

Use one version-aware resolver for schedule validation, local-to-UTC resolution,
recurrence gap enumeration, UTC-to-local range conversion, notification calendar
boundaries, temporal bindings, and notification display. Audit direct `ZoneInfo`
calls with a persisted pin; otherwise unverified conversions can affect range
selection before the final version check. Unpinned presentation zones remain a
separate concern and do not acquire authority over canonical schedules.

Version metadata and TZif bytes must come from the same selected provider/root.
The resolver must use the exact bytes it verified, e.g. by constructing `ZoneInfo`
from the captured bytes, rather than validating a file and then loading a cached
`ZoneInfo(key)` from another source. Gap enumeration must consume those same bytes.
Prevent version-cache/zone-cache mixing during a host update. Missing per-provider
version metadata or a detected update during capture must fail closed, not fall
through to another directory or package with unrelated version metadata.

An implementation must define bounded read/cache behavior and invalidation using
provider identity and data fingerprints. A cache keyed only by timezone name or
by the installed release string is insufficient. These are requirements of the
selected fix, not a request for general storage or resilience qualification.

## Canonical facts and observability

Keep stored `timezone_database_version`, receipts, recurrence and occurrence
identity preimages, hashes, and persisted provenance pinned to the authored
release. Do not rewrite schedules, regenerate identities, or place incidental
runtime-release metadata inside an existing canonical hash preimage.

The minimum observable surface is a structured operational diagnostic
`timezone_compatible_substitution` with requested version, runtime version, zone,
evidence ID and loaded TZif SHA-256. Emit it when a compatible resolver is admitted;
bound repetition by the admitted provider/evidence identity. Do not include item,
recipient or schedule content. CLI JSON stdout remains machine-readable and
unchanged; diagnostics use the operational logging channel. Deployment verification
must demonstrate that both CLI and worker operators can actually see the diagnostic.

Public response metadata is optional for this first slice. Adding it would require
an explicit response contract amendment, including web projection/permission rules;
it must not silently alter frozen canonical envelopes or receipt replay.

## Contract alignment and implementation boundary

The accepted recurrence and rendering contracts promise pinned-version semantics.
Rendering prohibits silent system-version substitution. The 2026-10-22 policy
amendments to recurrence, schedule creation/operations, rendering and the draft
operational-resilience Sections 8.2/10 recognize this equivalent-resolution path
and the required diagnostic. The runtime contract declares implementation in the two maintenance lines; existing
canonical envelopes and identity contracts remain unchanged. Immutable pinned and side-by-side deployments remain
valid strategies; this decision does not claim side-by-side support is implemented.

Version the runtime independently on mainline and any production backport. No ledger
migration is expected for this resolver-only design. A 0.6.0 backport needs an exact
deployed source/dependency baseline and separate schema-15 installed-package checks;
do not assume a version string identifies all locally deployed changes.

## Required executable acceptance

1. Preserve existing exact-version behavior. Automatically admit matching actual
   bytes for previously unseen runtime releases and for a zone beyond Paris/Chicago,
   without catalog edits or approval. Reject mismatches, absent/untrusted authored
   references, modified data, invalid catalogs and inferred alias/suffix equivalence.
   Reverse/downgrade and suffix-labelled runtime releases are subject to the same
   direct authored-baseline comparison; prior pair approval is neither needed nor
   sufficient. A later runtime that differs from the authored reference must fail
   even if an earlier substitution passed.
2. Compare full reference TZif bytes and run local-time probes through the actual
   Spine resolver: historical offsets/folds, current gaps/folds, ordinary times,
   future transitions and footer extrapolation. Preserve earliest-UTC fold choice
   and gap omission/COUNT semantics.
3. Exercise one-off agenda reads, recurring expansion, notification opportunities,
   temporal bindings and rendering/worker preparation with fake transport. Cover
   conversions that select query bounds before occurrence expansion.
4. Verify canonical pins, receipts, hashes and occurrence/work identities are
   unchanged versus an exact requested-release reference. Read paths must not write
   ledger state. Assert that substitution diagnostics identify the actual resolver.
5. Exercise provider precedence, missing metadata, warmed `ZoneInfo` caches,
   process-local version caching, and a provider update during capture. No mixture
   of two datasets may be admitted as one verified resolver.
6. On an approved disposable production backup, prove the reported agenda works
   for both routes and verify the actual installed zone fingerprints. Synthetic
   or macOS compiler evidence does not establish production acceptance.
7. Exercise trusted reference retention across multiple upgrades, missing legacy
   evidence, independently evidenced encoding variants, reference-ingestion failure
   and attempts to derive an old reference from new bytes. Readback cannot mutate
   or silently enroll baseline evidence. A candidate matching only another catalog
   build cannot override a captured authored fingerprint; unresolved legacy-build
   disagreement must fail rather than select a matching candidate opportunistically.

Whole-agenda failure isolation for genuinely incompatible schedules is a separate
behavior change. This decision prevents rejection caused solely by a global
release change when the required zone bytes match; it does not authorize silently
omitting incompatible schedules or presenting an incomplete agenda as complete.

## Agenda wrapper boundary

The reported OpenClaw daily-agenda wrapper was not found in this checkout or by
filename search in sibling Cortext repositories. Its location/owner is needed
before editing it. It must preserve a nonzero child exit status and also reject an
`ok: false` application envelope, malformed output or execution failure. Failed
agenda reads must not be rendered as a successful agenda or successful cron run.
Test those cases against the actual wrapper; do not add a replacement wrapper to
Spine without identifying the deployed integration.

## Remaining deployment work

- Authenticate and provision the original production build fingerprints.
- Verify both route agendas on an approved disposable production backup.
- Identify and correct the deployed agenda wrapper. The operator confirmed production
  source `a28bdf0e20cdb671e4a3862572d85c952f354056`; both patch lines are selected.

Side-by-side immutable bundles remain an alternative for zones that differ and for
stronger historical reproducibility. Restoring access to the exact authored release
through an established deployment procedure is a separate operational recovery
option, not an automatic OS downgrade or an authorization in this document.
