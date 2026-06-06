# Spine Spec Versioning and Freeze Policy

Status: Accepted v1.1  
Scope: Spec versions, runtime compatibility declarations, and freeze-manifest use  
Ratified: 2026-06-04

## 1. Doctrine

Spine adopts lightweight Cortext1 compatibility discipline:

- Versions communicate compatibility.
- Hashes prove exact reviewed artifacts.
- Tests prove behavior.
- The freeze manifest is one-way authoritative for release-critical public artifacts only.

This policy intentionally adopts Kinflow's contract-pinning doctrine without copying Kinflow's full hash-locking ceremony.

## 2. Scope

This policy applies to Spine public behavior and compatibility surfaces, including:

- public behavior specs
- public protocols
- cross-component contracts
- adapter boundaries
- event schemas
- persistence and migration contracts
- runtime compatibility declarations
- externally consumed APIs or interfaces

This policy does not apply to ordinary explanatory docs, planning docs, checklists, draft notes, status reports, troubleshooting notes, or non-authoritative implementation notes.

## 3. Policy

Public behavior MUST have an explicit spec or contract version before it is treated as stable.

Runtime code that implements stable public behavior MUST declare the implemented spec or contract version before that behavior is treated as stable.

Draft, exploratory, or internal-only runtime code does not require an implemented-version declaration.

Release-critical public artifacts MAY be pinned by path, version, and `sha256` in a freeze manifest.

The freeze manifest is the sole authoritative hash source for pinned public artifacts.

Specs, docs, reports, and checklists MUST NOT create reciprocal hash gates with each other. An artifact may be pinned by the freeze manifest, but it MUST NOT be required to carry the manifest hash, and the manifest MUST NOT be hash-locked by ordinary downstream docs.

Downstream docs MAY reference freeze entries by artifact path or `manifest_id`. Copied hashes outside the freeze manifest are informational only and MUST NOT be treated as authoritative gates.

## 4. Freeze Manifest Semantics

When Spine introduces a freeze manifest, it SHOULD be small, reviewable, and one-way:

- The manifest points to pinned artifacts.
- Pinned artifacts do not point back to the manifest by hash.
- Each manifest entry has a stable `manifest_id`.
- Each manifest entry records `manifest_id`, `path`, `version`, `sha256`, and a short non-empty `reason` explaining why the artifact is release-critical.
- Rebinding the manifest means intentionally updating a pinned entry after reviewing the artifact change.

When the freeze manifest is introduced, Spine MUST declare exactly one authoritative manifest artifact path. That path MUST itself be a normalized repository-root-relative POSIX path. The declared manifest artifact is the only manifest input the MVP verifier reads for pinned entries.

At MVP depth, the verifier interface treats the authoritative manifest artifact path declaration as a required invocation or configuration input. A verifier run is given repository root context and the declared authoritative manifest artifact path. The verifier MUST NOT discover alternative manifests from downstream docs, pinned artifacts, or repository scans.

The declared manifest artifact path MUST obey the same minimum path-shape constraints as pinned artifact paths: absolute paths, empty paths, parent-directory traversal, and platform-specific path separators are invalid. The verifier MUST validate the declared manifest artifact path before any filesystem resolution, manifest read, or pinned artifact read. An invalid declared manifest artifact path MUST fail deterministically with a clear manifest-path-invalid outcome, MUST report the checked manifest path, and MUST NOT attempt any pinned artifact reads.

At MVP depth, the manifest artifact MUST contain one machine-readable collection of entries. Each entry in that collection MUST carry `manifest_id`, `path`, `version`, `sha256`, and `reason`. The `reason` MUST be a non-empty string explaining why the artifact is release-critical. The `version` MUST be a non-empty string identifying the reviewed artifact's declared spec or contract version. Non-empty string presence is the only MVP validation rule for `version`; broader version syntax is deferred. This policy does not define a complete manifest container format or JSON schema; a later contract may choose the exact encoding, top-level field names, and additional metadata.

Pinned artifact paths MUST be normalized repository-root-relative POSIX paths. Absolute paths, empty paths, parent-directory traversal, and platform-specific path separators are invalid.

Pinned artifact `sha256` values are lowercase SHA-256 hex digests over the exact raw bytes of the artifact at the pinned path. The hash computation MUST NOT normalize line endings, character encoding, whitespace, Markdown, JSON, or any parsed representation.

Manifest IDs MUST be unique within the freeze manifest. For MVP verification, a well-formed `manifest_id` is a non-empty lowercase ASCII identifier using only `a-z`, `0-9`, `.`, `_`, and `-`. A `manifest_id` SHOULD remain stable when an existing pinned artifact is intentionally rebound, but a verifier MUST NOT pretend it can prove ID derivation or historical rebinding stability from a single manifest snapshot.

The manifest SHOULD be introduced only when Spine has release-critical public artifacts whose drift would create real compatibility or release risk.

## 5. What Gets Pinned

Pin only artifacts that are release-critical or cross-component authoritative, such as:

- public protocol specs
- event schemas
- adapter contracts
- durable persistence or migration contracts
- cross-component compatibility specs
- externally consumed API or interface contracts

Do not pin:

- planning docs
- checklists
- status reports
- exploratory notes
- troubleshooting docs
- implementation notes unless explicitly promoted to public contract status

Draft specs SHOULD NOT be pinned merely because they are important. A draft becomes a pin candidate when another component, runtime declaration, migration, contract test, or release process depends on its exact reviewed content.

## 6. Change Rules

A public behavior or contract change requires:

- updating the relevant spec or contract version
- updating runtime implemented-version declarations when required by Section 3
- updating tests, contract tests, or golden fixtures where relevant
- rebinding the freeze manifest only if a pinned artifact changed

Version changes SHOULD communicate compatibility intent. Patch-level changes may clarify behavior without changing compatibility. Minor-level changes may add compatible behavior. Major-level changes may break existing public behavior or contract expectations.

Hash rebinding MUST NOT be used as a substitute for tests. A matching hash proves only that the reviewed artifact has not drifted; it does not prove that runtime behavior still satisfies the artifact.

## 7. Intended Verification

Spine does not yet have a freeze verifier.

Introducing the first freeze manifest with at least one pinned artifact justifies and requires a lightweight verifier. The initial verifier MAY be small, but it MUST take only repository root context and the declared authoritative manifest artifact path as its required inputs. It MUST read only that declared authoritative manifest artifact for pinned entries and MUST check pinned artifact existence, manifest entry version non-emptiness, pinned path validity, and `sha256`.

The verifier MUST validate the declared authoritative manifest artifact path against the Section 4 path constraints before any filesystem resolution or manifest read. If the declared manifest artifact path is invalid, the verifier MUST fail deterministically with a clear manifest-path-invalid outcome, MUST NOT attempt pinned artifact reads, and MUST report the checked manifest path.

If the declared authoritative manifest artifact is missing, unreadable, or cannot be parsed as the single machine-readable collection of entries, the verifier MUST fail deterministically, MUST NOT attempt pinned artifact reads, and MUST report the checked manifest path with a clear manifest-read or manifest-parse outcome.

For MVP manifest entries, the verifier MUST check that each entry has string fields for `manifest_id`, `path`, `version`, `sha256`, and `reason`; that `version` and `reason` are non-empty; that each `manifest_id` is present, unique, and well-formed; that each pinned path satisfies the Section 4 path constraints; and that `sha256` is a lowercase SHA-256 hex digest matching the exact raw bytes of the resolved pinned artifact path.

The verifier MUST validate each pinned path before any filesystem resolution, existence check, or hash read for that entry. A malformed path MUST fail the manifest entry with a clear malformed-path outcome, and the verifier MUST NOT resolve or read any path outside the repository root.

The first non-empty manifest verifier MUST produce deterministic observable outcomes. If all required checks pass, the verifier MUST produce a deterministic success status. Any missing artifact, missing or unreadable manifest artifact, unparseable manifest collection, malformed required field, empty `version`, empty `reason`, duplicate or malformed `manifest_id`, malformed pinned path, invalid manifest artifact path, invalid `sha256`, or `sha256` mismatch MUST produce a deterministic failure status.

If the verifier is exposed as a process, it MUST exit `0` only when all required checks pass and MUST exit nonzero for any deterministic failure listed in this section. If the verifier is exposed only as a library surface, it MUST return an equivalent structured pass/fail status. This policy does not define an exhaustive error-code registry.

Every verifier run MUST emit a human-readable report to stdout, stderr, or a named report artifact. The report MUST include the checked manifest path and MUST identify each failing `manifest_id` and pinned `path` when those fields are present enough to report.

The verifier MUST NOT fail a manifest merely because it cannot prove whether a `manifest_id` was derived from mutable fields or stayed stable across prior rebindings. Those are authoring rules and review expectations unless a later manifest-history contract makes them machine-checkable.

When Spine's pinned surface grows, the verifier SHOULD:

- detect missing pinned artifacts
- detect `sha256` mismatches for pinned artifacts
- detect missing, duplicate, or malformed `manifest_id` values
- detect runtime/spec version mismatches where declarations exist
- detect missing tests, contract tests, or golden fixtures for pinned public contracts where practical
- report dirty pinned artifacts clearly with actionable next steps

Verifier output SHOULD distinguish between:

- an artifact missing from disk
- an artifact present but hash-mismatched
- a runtime declaration that names an unknown or incompatible spec version
- a public contract that is pinned but lacks relevant behavioral evidence
- a manifest entry whose `manifest_id`, path, version, `sha256`, or reason is malformed

The intended next steps SHOULD be explicit: update the artifact, update the version declaration, add or update tests, or intentionally rebind the manifest after review.

## 8. Ergonomics Requirement

This policy MUST avoid making ordinary development painful.

Hash pinning is reserved for artifacts whose drift would create real compatibility or release risk. It MUST NOT turn routine editing of draft specs, explanatory docs, planning notes, or status material into a hash ceremony.

Spine should prefer small, meaningful pin sets over broad repository snapshots. Compatibility discipline should make release review clearer, not make every doc edit feel release-critical.

## 9. Spine-Specific Ratification

As of this ratification, Spine is seed/spec-only.

Current orientation and normative surfaces are: `README.md` for orientation, and `specs/` plus `specs/decisions/` for normative design and compatibility promises. There is no runtime package, public importable protocol directory, machine-readable contract directory, migration set, contract test suite, or freeze manifest in this repository.

No artifacts should be pinned immediately.

The first freeze manifest should be introduced when at least one of the following becomes true:

- Spine promotes a public protocol, schema, adapter contract, migration contract, or compatibility spec to a release-critical public contract intended to become Canonical through version pinning and matching contracts or tests.
- A runtime implementation declares compatibility with a specific public spec or contract version.
- Another Cortext1 component consumes a Spine artifact as an authoritative compatibility input.
- A release process needs exact reviewed artifact identity for a public contract.

The current `specs/ontology.md` is a detailed draft data-contract sketch, but it is not yet backed by runtime declarations, migrations, or contract tests. It should become a pin candidate only when promoted to a release-critical public contract or when executable behavior starts depending on its exact versioned content.