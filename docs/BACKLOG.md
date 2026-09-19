# Spine Backlog

Last updated: 2026-09-18

This is the single work queue for Spine development. The
[implementation plan](IMPLEMENTATION_PLAN.md) explains roadmap direction and delivery
history; [specs](../specs/README.md) and [contracts](../contracts/) remain authoritative
for behavior. An entry here does not accept a draft contract or authorize deployment.

## How to use this backlog

Focus on concrete items the operator brings to the backlog. Do not prescribe or
start gap analyses, general evidence reviews, or qualification campaigns unless the
operator requests them. Existing roadmap-derived entries are retained as candidates,
not selected work or automatic priorities. Dependencies and relevant verification
requirements still apply when a concrete task is selected.

- **Ready:** the stated task is bounded and can begin; this can be a preparation or
  design task without implying its eventual runtime feature is ready.
- **Needs decision:** scope or contract choices must be settled before implementation.
- **In progress:** record the responsible person or agent and current evidence here.
- **Blocked:** record the unmet dependency or external condition and how to clear it.
- **Done:** acceptance criteria are met and completion evidence is linked.
- **Deferred:** retained for later; no work or review is scheduled until the operator
  explicitly reactivates it.
- **Closed — withdrawn:** removed from planned work by the operator; does not claim
  implementation or verification was completed.

Keep each task's status in its entry, not in duplicate roadmap checklists. Keep IDs
stable when reordering. Split near-term initiatives into independently verifiable
outcomes; leave later horizons coarse. Before promoting a horizon, define its scope,
dependencies, acceptance criteria, and required decisions. When finishing a task,
record evidence and move it to Completed. Update affected orientation and contract
status labels in the same change. Routine task updates do not change spec authority.

## Next work

### SPINE-015 — Read authorized activities independently of unavailable linked resources

**Status:** In progress — initiative selected on 2026-09-15; specification and
machine-contract phases complete. Both focused rechecks passed without findings;
the manual machine-contract fixes and preceding checkpoints are pushed through
`4d16670`. Runtime delivery planning completed on 2026-09-18; the operator then
authorized the first implementation slice. Shared read-contract validation,
normalization, bounded read-only context, authorized selection and core/time
assembly are implemented and locally tested. The subsequent internal slice adds all
eleven detail-section projections, four agenda summaries, canonical occurrence and
resolved/unplaced agenda assembly, plus an index-only schema-15 migration. Public
routes and consumer adoption remain later steps; no implemented v2 capability is
advertised. The internal release-fence and authorized source-hashing slice is
committed at `629c7a4`. The subsequent operator-selected internal cursor/identity
encoding and pagination slice is implemented and locally verified below. Public
HTTP/package activation, consumer acceptance, commit/push and deployment remain
outside this subsequent slice.
**Dependencies:** Existing trusted web permissions, canonical recurrence/agenda and
temporal-binding engines, and the accepted read/machine contracts. No further broad
specification pass is scheduled. Query/index migration assessment and behavioral
verification are implementation tasks, not already satisfied by static fixtures.
This concrete item is independent of the withdrawn SPINE-001–003 review tasks and
the deferred resilience initiatives.

**Observed failure (operator report, not reproduced against staging):** A recurring
Science class has web ownership under `stage-whatsapp-group`. “Drive Callan to Science
class” follows one occurrence through an active `follow_source` binding, has Caleb
assigned, and has no web-access ownership. `schedule.show` of the authorized class
returns `resource_unavailable` because `bound_items` traverses the linked task.
Kinflow isolates the failed detail read and shows an explicitly incomplete calendar,
but the generic denial cannot safely identify the cause. Local code inspection
confirms this traversal also applies to `item.occurrences` and scoped agenda reads.

**Outcome:** Authorized event facts and canonical occurrences remain readable
independently of inaccessible followers. Related reads remain separately authorized;
public structured availability distinguishes usable activity facts from optional
context without revealing hidden resources or guessing temporal facts.

**Runtime delivery scope:** One cohesive backend slice implementing the complete
independent-read registry: v2 schedule detail, occurrences, agenda and capability
discovery. Shared authorized projection, own-time freshness, bounded queries,
source/release fences, cursor codec, packaged contract admission, runtime tests and
operator/consumer documentation ship together. See the
[delivery sequence](IMPLEMENTATION_PLAN.md#planned-fat-slice-independent-authorized-activity-reads-spine-015).
Deployment and Kinflow adoption follow separately with explicit evidence and approval;
this planning change performs neither.

**Non-goals:** Repairing ownership, granting access from assignment, weakening
cross-resource writes, changing v1/CLI semantics, v2 writes, client recurrence
calculation, family-facing copy in Spine, new authentication, facets, advisory
execution or reopening deferred resilience work. Atomic provisioning of intended
ownership at task creation is a separate companion requirement; this item must
also handle legitimate access differences after correct creation.

**Acceptance:** The accepted IR-01–IR-16 matrix in the supporting spec covers:
authorized events with unowned or inaccessible followers; normally visible authorized
relations; disclosure-safe empty/incomplete context; generic direct denial; unavailable
task time without a fabricated deadline; epoch/version/pagination races; unchanged
cross-resource write protection; and Kinflow rendering from public canonical facts.
The machine-contract review is complete; implement the behavioral oracles before
advertising v2. Backend acceptance requires IR-01–IR-15 runtime/HTTP evidence,
exact packaged pins and registry, query/index migration assessment, unchanged v1/CLI
and write regression tests, and no durable read effects. IR-16 and the consumer side
of IR-15 require separate Kinflow integration evidence. Documentation alone does
not close the feature.

**Delivery checkpoints (in order):**

1. Shared bounded authorized selection, projection and own-time resolution — internal
   implementation complete.
2. All detail sections and resolved/unplaced agenda assembly — internal implementation
   complete.
3. Authorization/source fences, authorized source hashes, v2 cursor codec/identity
   encoding and actual first/next-page pagination — internal implementation complete,
   including retained private-proof revalidation. Public HTTP integration is pending.
4. Complete HTTP/packaging/capability integration and behavioral regression suite.
5. Host-neutral operator documentation and precise Kinflow release handoff.
6. Separately approved deployment/canaries, then Kinflow adoption and end-to-end
   acceptance. Do not report backend completion as consumer completion.

**Internal release-fence/source-hash checkpoint (2026-09-19):** Added
`web/read_release.py`, `read_authorization.py`, and `read_proof.py`. The internal
`read_authorized` path assembles in one read-only transaction, closes it, and opens
a fresh read-only transaction for mandatory identity/authorization/source checks.
A single outer clock/SQL/byte budget spans both; optional evidence and its rechecks
retain the optional SQL reserve. Unavailable sections discard their partial proof
and authorization fragments. Revalidation failure never silently downgrades an
already assembled result. These are unpaged internal objects, not HTTP responses.

Private checks include selected account/selection, account and account-subject
binding revisions, operator/subject state, ledger/realm/recovery/access epochs,
owner/catalog/route permissions, checked grants, active memberships, previously
denied necessary sources, and discovered candidate membership. Prospective grant
activation/expiry and membership activation bound validity without requiring an
epoch write; the deadline is also checked after fresh proof work. Subjects have no
numeric revision column: this slice fences the full canonical selected-subject row,
without inventing or exposing a cursor `subject_revision`. Its numeric wire mapping
must be implemented explicitly with cursor integration.

Public source digests use the exact `spine.trusted-web-read-snapshot.v1` preimage,
with unique `(kind,id)`-sorted records hashing closed authorized candidate cores,
canonical recurrence sets, required authorized temporal source cores/binding
revisions, and only requested projected section rows. Agenda summaries hash their
underlying authorized rows, not only counts; off-range candidates remain covered.
Unsupported/protected canonical proof references make time unavailable and never
enter the public digest as a substitute for authorization. Independent hidden
follower mutations leave the event proof unchanged. Canonical occurrence identities
and all v1/write/replay/worker/delivery behavior are reused unchanged.

Fresh direct source changes return `version_changed`; agenda or retained private
proof changes return `access_changed`. Root admission still precedes version guards;
invalid selected identity retains `identity_unavailable`. The internal retained-proof
path preserves the original authorization evaluation time and deadline. It is not a
wire cursor implementation and rejects cursor transport fields.

**Query/index evidence:** Actual `EXPLAIN QUERY PLAN` inspection on SQLite **3.53.2**
shows `SEARCH g USING INDEX access_grants_subject` for grantee/status/resource-kind
candidate transition scans, and `SEARCH g USING INDEX access_grants_group` with the
additional resource-ID equality for dependency probes. Correlated owner and operation
checks use `sqlite_autoindex_item_access_owners_1` and covering
`sqlite_autoindex_access_grant_operations_1`. Membership transition checks use
`subject_memberships_subject_status_idx`, with primary/covering group and adoption
lookups. The focused tests assert both grantee paths and the membership path. These
added paths need no index or schema migration; schema 15 remains unchanged.

**Verification:** Python **3.14.6**, pytest **9.1.1**, Ruff **0.16.2**. Test commands
used `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:../tickerd/src` and the existing local
Tickerd checkout; no dependency installation or Tickerd qualification was performed.

```sh
.venv/bin/python -m pytest -o addopts='' -q tests/test_independent_activity_read_release.py tests/test_independent_activity_read_foundation.py tests/test_independent_activity_read_assembly.py tests/test_independent_activity_read_contracts.py tests/test_web_contract_sync.py --tb=short
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m pytest -o addopts='' -q
```

Results: focused **95 tests and 160 subtests passed in 13.33s**; full unittest
**590 tests in 34.325s, OK**; full pytest **590 passed, 572 subtests passed in
34.77s**, with no skips. The 31 new release tests cover real-ledger identity/source
races, selected-occurrence proof hashes, timed grants/memberships, protected proof
references, requested section evidence, first-read agenda/off-range candidates,
retained-proof checks, optional-budget isolation, no durable read effects, and
indexed query plans. Hooks and clocks are deterministic; no timing sleeps are used.

All four strict commands passed **37 source files** with incremental caching disabled
(configured target Python 3.12):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/spine-mypy-1.20.2-validation-20260918 .venv/bin/python -m mypy --strict --no-incremental --python-executable /opt/homebrew/bin/python3 --cache-dir /tmp/spine-read-release-120-source src/spine/core src/spine/ledger
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/spine-mypy-1.20.2-validation-20260918 .venv/bin/python -m mypy --strict --no-incremental --cache-dir /tmp/spine-read-release-120-editable src/spine/core src/spine/ledger
PYTHONDONTWRITEBYTECODE=1 .venv/bin/mypy --strict --no-incremental --python-executable /opt/homebrew/bin/python3 --cache-dir /tmp/spine-read-release-230-source src/spine/core src/spine/ledger
PYTHONDONTWRITEBYTECODE=1 .venv/bin/mypy --strict --no-incremental --cache-dir /tmp/spine-read-release-230-editable src/spine/core src/spine/ledger
```

The first pair uses mypy **1.20.2**, the second **2.3.0**; `--python-executable`
selects discovery without an installed Spine distribution. `.venv/bin/ruff check .`,
`git diff --check`, and
`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/sync_web_contracts.py --check`
passed. `PYTHONPYCACHEPREFIX=/tmp/spine-read-release-compile-cache .venv/bin/python -m compileall -q src tests examples`
passed with bytecode outside the repository.

**Environment limitation:** An additional offline wheel smoke attempt used
`.venv/bin/python -m pip wheel --no-deps --no-build-isolation --no-index <temporary-source> --wheel-dir <temporary-dist>`
on a temporary copy. It exited **2**, `BackendUnavailable: Cannot import
'setuptools.build_meta'`: the local environment lacks the build backend. No wheel was
produced and the subsequent installed-wheel checks did not run. This is not a claim
of fresh cloud/package acceptance for this slice; the synchronization gate remains
passing with deferred v2 assets excluded.

**Next implementation at that checkpoint:** v2 cursor codec/computed vectors, identity encoding,
fixed-expiry transport continuation, and section/combined-stream pagination using
these fences. Then complete HTTP/package/capability activation and its behavioral
gates, followed by separate Kinflow acceptance and deployment authorization. No v2
route, packaged capability or runtime declaration was activated. The operator
subsequently authorized a local commit of this slice; no push, staging migration,
deployment, or real-ledger access is included in that authorization.

**Internal cursor/pagination checkpoint (2026-09-19):** Implemented from clean
`629c7a450e4f63d11edd1953b777cf51eb8f776f`. Added `web/read_cursor.py` and
`web/read_pages.py`, with trusted paging callbacks inside the existing shared
release path. Page projection, signing, schema validation and response-size checks
precede the fresh release fence and share its original request deadline and SQL
budget. Invalid selected identity is admitted before cursor decoding. Every page
reassembles authorized data and rechecks retained private authority/source proof;
there is no public route or cached-response shortcut.

The independent HMAC-SHA256 codec computes the exact published wire vector. It
rejects wrong versions/signatures, padding, noncanonical base64url/JSON, duplicate
keys, unknown fields, invalid calendars, oversized tokens, wrong stream/root/query,
and changed identity. MAC verification precedes JSON parsing. All child pages retain
original issuance, expiry, authorization evaluation time and transition deadline.
Expiry is checked again after fresh proof work, including at the exact boundary.

`subject_revision` now has a pinned, tested positive-decimal content-fingerprint
encoding for the selected subject's six canonical fields. It is an equality token,
not a chronological counter. Private fences still compare the full subject row.
The account-subject binding maps directly from persisted `binding_revision` and
remains distinct from canonical temporal-binding revisions. The cursor artifact,
computed vectors, schema pins, contract companion and consumer handoff document
these rules; no v1 pin or runtime capability declaration changed.

Private proofs remain only in service-local memory, bounded to at most **128
families / 8 MiB serialized proof bytes** (configurable downward). They expire at
the original deadline; continuation never renews retention. Missing proof returns
`access_changed`, a full store returns `capacity_exceeded`, and an existing family
cannot be overwritten with different private evidence. Only closed projected
responses escape the pager; private checks, grant references and full assemblies
never enter tokens. No ledger/session/cache tables or durable read effects exist.

Detail collections page independently, with common-family enforcement across
supplied section cursors and first-page behavior for other included collections.
Occurrence pages retain the canonical engine's ordering and identities for both
range bases. Agenda pages emit resolved entries followed by item-ID-ordered
unplaced cores under one limit; whole-query temporal coverage is retained even
on a resolved-only page. Empty/exhausted results have no continuation.

**Query/index evidence:** Paging adds no SQL selection or OFFSET scans; it pages
the existing bounded authorized assembly. Actual SQLite **3.53.2** plans for the
selected-identity reads are `SEARCH subjects USING INDEX sqlite_autoindex_subjects_1
(subject_id=?)` and `SEARCH web_operators USING INDEX sqlite_autoindex_web_operators_1
(account_id=?)`. New tests assert those plans; prior grantee/membership/endpoint
plan tests also pass. No migration is necessary; ledger schema remains **15**.

**Verification:** New suite **31 tests / 36 subtests passed in 14.90s**. Combined
focused suites **126 tests / 196 subtests passed in 28.20s**. Tests cover all 13
closed cursor shapes, computed vectors, malformed signed payloads, fixed expiry,
identity switches, real-ledger section/occurrence/agenda continuation, mixed section
families, lost/bounded proofs, off-page source changes, timed grant and membership
transitions without epoch changes, hidden followers, denied/stale temporal sources,
DST exclusions/overrides, terminal lifecycle, optional failure, shared deadlines,
and byte-identical ledger dumps before/after successful paging.

Focused commands used `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:../tickerd/src`:

```sh
.venv/bin/python -m pytest -o addopts='' -q tests/test_independent_activity_read_pages.py --tb=short
.venv/bin/python -m pytest -o addopts='' -q tests/test_independent_activity_read_pages.py tests/test_independent_activity_read_release.py tests/test_independent_activity_read_foundation.py tests/test_independent_activity_read_assembly.py tests/test_independent_activity_read_contracts.py tests/test_web_contract_sync.py --tb=short
```

Full unittest **621 tests in 47.980s, OK**; full pytest **621 passed / 608 subtests
passed in 48.48s**, without skips. Commands used the same bytecode/PYTHONPATH
environment above and the existing sibling Tickerd checkout; no Tickerd installation
or separate qualification was performed:

```sh
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m pytest -o addopts='' -q
```

Python **3.14.6**, pytest **9.1.1**, Ruff **0.16.2**. All four strict checks passed
**37 source files**, with target Python 3.12 and incremental caching disabled:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/mypy --strict --no-incremental --python-executable /opt/homebrew/bin/python3 --cache-dir /tmp/spine-read-pages-mypy-source src/spine/core src/spine/ledger
PYTHONDONTWRITEBYTECODE=1 .venv/bin/mypy --strict --no-incremental --cache-dir /tmp/spine-read-pages-mypy-editable src/spine/core src/spine/ledger
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/spine-mypy-1.20.2-validation-20260918 .venv/bin/python -m mypy --strict --no-incremental --python-executable /opt/homebrew/bin/python3 --cache-dir /tmp/spine-read-pages-120-source src/spine/core src/spine/ledger
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/spine-mypy-1.20.2-validation-20260918 .venv/bin/python -m mypy --strict --no-incremental --cache-dir /tmp/spine-read-pages-120-editable src/spine/core src/spine/ledger
```

The first pair uses mypy **2.3.0**, the second **1.20.2**. Metadata discovery under
`/opt/homebrew/bin/python3` confirms Spine is absent for source-only checks. Ruff,
contract synchronization, compilation and diff hygiene pass:

```sh
.venv/bin/ruff check .
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/sync_web_contracts.py --check
PYTHONPYCACHEPREFIX=/tmp/spine-read-pages-compile .venv/bin/python -m compileall -q src tests examples
git diff --check
```

All **71** local file links in the four changed documentation/specification files
resolve. The synchronization gate still excludes deferred v2 assets. A fresh
offline wheel attempt copied packaging inputs/source to a temporary directory and
ran `.venv/bin/python -m pip wheel --no-deps --no-build-isolation --no-index
<temporary-source> --wheel-dir <temporary-dist>`. Pip exited **2** with
`BackendUnavailable: Cannot import 'setuptools.build_meta'`; no wheel was produced
and installed-wheel checks could not run. Both local Python environments lack
setuptools. Temporary build inputs were removed; no dependency installation or
network access was attempted. This is an environment limitation, not fresh
packaging or cloud acceptance for this slice.

**Next implementation:** Complete the four-route HTTP integration, packaged contract
admission and runtime capability declarations with the behavioral/compatibility
gates. Then finalize operator documentation and Kinflow release handoff, followed
by separately authorized deployment and consumer acceptance. Internal paged-read
tests are not HTTP or Kinflow acceptance. No commit, push, deployment, staging
change, v2 activation, real-ledger access or Whetstone audit occurred in this slice.

**Specification evidence:** [Independent activity reads](../specs/independent-activity-reads.md)
defines read boundaries, completeness, availability, consistency, compatibility,
and proposed contract tests. [Kinflow handoff](INDEPENDENT_READS_KINFLOW_HANDOFF.md)
defines consumer migration and rendering behavior. Local Markdown link and consistency
checks cover this specification delivery; no staging verification is claimed.

**Audit evidence and next step:**
`whetstone_runs/independent-activity-reads-contract-audit-001/audit-notes.md` lists
the ten-file reviewer inventory and focused consistency questions. The approved review
returned `needs_revision` on 2026-09-15 (0 blockers, 1 major, 2 minors, 0 nits).
Findings: scope singular expected-version guards to direct reads versus multi-item
agenda; distinguish selected account-subject identity binding revisions from temporal
binding revisions; clarify the v2 authoring-receipt projection's source/include semantics
without silently adding a v1 include option. Cited passages were checked locally.
Recommended manual choices: direct-read singular guards, agenda snapshot/cursor fencing;
explicit identity-binding terminology; independently specified v2 receipt evidence.
The operator-approved manual patch was completed on 2026-09-15 in Draft v0.2 and the
Kinflow handoff. Direct reads accept singular expected item/recurrence guards; agenda
rejects them and uses candidate-snapshot/cursor fences. V2 explicitly distinguishes
`account_subject_binding_revision` from `temporal_binding_revision_id`. The requested
v2 authoring-receipt singleton projects authorized creation evidence; absent and
undisclosable evidence both yield null, without adding v1 includes or creating receipts.
IR-11/12/14 now include matching future behavioral oracles. Seven documentation and
two implemented-declaration tests passed; `git diff --check` passed. No v1 schema,
runtime, canonical spec, or other-repository edits. The subsequent focused re-audit
passed; it does not ratify the complete contract or authorize runtime work.

Report, feedback, brief and manifest are retained under that root's `change_audit/`.
Invocation/manifest pin Sol, bundled CLI `0.154.0-alpha.6.2`, consistency and launcher
medium reasoning. Returned model-authored reviewer metadata says `gpt-5`, inconsistent
with the invocation/manifest; it is not independent model attestation. All ten raw
input hashes remained unchanged and all normalized manifest hashes matched.
`boundary_preserved=false` is the findings-based major verdict, not independent proof
of a runtime leak; no staging verification or convergence claim. No source specs,
runtime, shared defaults, commits or pushes changed during this audit.

Follow review with targeted clarification/ratification, then machine schemas,
registry/cursor and field-authority mappings plus IR-01–IR-16 fixtures before runtime.
The focused recheck inventory and questions are in
`whetstone_runs/independent-activity-reads-contract-audit-002/audit-notes.md`.
It used Sol and bundled CLI `0.154.0-alpha.6.2`, consistency profile and launcher
medium reasoning. Report: `pass`, zero blocker/major/minor/nit findings,
`boundary_preserved=true`, next action `none`. The three prior findings were not
raised again; empty feedback provides no per-finding explanation or exhaustive
coverage proof. All seven raw input hashes remained unchanged and normalized
manifest hashes matched; source specs matched checkpoint `354ed7e` before review.
Report, feedback, manifest and brief are under that root's `change_audit/`.
No source edits, Editor, runtime changes, commit or push occurred during recheck.
Nine documentation/declaration checks passed before checkpointing. Next selected
step remains contract ratification/codification, not a claim of runtime conformance.
Local pickup inspection reconfirmed the read-side `bound_items` calls and existing
connected-item checks; no runtime or source-spec change was made for preparation.

**Machine-contract delivery (2026-09-16):** Read design ratified as v1. The
[companion](../specs/independent-activity-read-contracts.md) and separate
`spine.trusted-web-read-registry.v1` codify two v2 command projections, agenda,
capability discovery, explicit temporal/section unions, field-authority mappings,
route-specific guards, authorized-only summaries and creation-receipt selection.
Eleven JSON schemas, independent schema/artifact pins, fixed-expiry cursor protocol,
five computed normalization vectors, one MAC vector and 53 schema fixtures are
provided. The IR-01–IR-16 behavioral matrix remains explicitly `runtime_pending`.
Offline semantic tests do not certify privacy, domain expansion, races or deployment.
No v1 contract/pin, runtime module, installed registry or packaged capability changed.
Verification: 73 tests and 202 subtests passed across the new offline contracts,
existing trusted-web contracts/runtime, implemented declarations, agent documentation,
and recurrence/schedule-operation/temporal-binding fixtures. Ruff, Markdown file-target
checks and `git diff --check` passed. These are local checks, not staging or a new audit.
Next step: bounded machine-contract audit, then separately authorized implementation
and Kinflow migration. No audit, commit or push was performed in this delivery.

**Checkpoint and audit preparation (2026-09-16):** Committed the contract-only
codification as `f9a301b` (`Codify independent activity read contracts`); pre-commit
verification again passed 73 tests and 202 subtests. Staged reviewer-only bounded
`audit-change` at `whetstone_runs/independent-activity-read-machine-contract-audit-001/`.
Its `audit-notes.md` enumerates the exact 39-file approval inventory (including notes),
review boundaries and goals. `preparation.json` records the source checkpoint/hashes
and supported invocation: Sol, consistency profile, bundled CLI, 900-second timeout.
The included 14 fixture files are a declared representative subset, not all 53.
Five existing authority documents are supplied as one verbatim excerpt artifact
with checkpoint, line-range and hash provenance, rather than sending their unrelated
sections. All eleven new schemas and new rule/vector/pin artifacts remain in scope.
Source files matched the committed checkpoint. Preparation did not invoke a reviewer,
Editor, source rewrite, convergence workflow or push.

**Machine-contract audit 001 (2026-09-16):** The operator approved the exact 39-file
inventory, built-in consistency profile and generated copies. Reviewer-only
`audit-change` completed with Sol, bundled CLI `0.154.0-alpha.6.2`, 900-second timeout.
Verdict `needs_revision`: 0 blockers, 3 majors, 0 minors/nits; all findings in scope.
`boundary_preserved=false` is the report's contract-gap assessment, not a finding
of an implemented runtime leak. Findings: available agenda summaries incorrectly
allow null instead of zero buckets; impossible local Gregorian date-times pass
machine validation; end-only available events and defer-only agenda tasks pass
required-primary-anchor validation. Read-only counterexamples reproduced each gap
against the checked-in schemas/static oracles. Sources were not patched.
All 38 raw source hashes stayed unchanged; all 39 normalized input hashes matched
the manifest, including notes. The manifest confirms the exact approved inventory,
Sol and consistency; no convergence or exhaustive coverage is claimed. Report and
feedback are under the run root's `change_audit/`. Next step: targeted manual schema/
semantic-oracle fixes with negative fixtures, updated new-contract pins, then focused
recheck. Runtime implementation remains pending. No Editor, commit or push was run.

**Manual audit patch (2026-09-16):** Addressed all three audit-001 findings without
runtime or v1 changes. Available agenda summary values are now non-null objects;
location and creation-receipt singletons retain valid null absence. Shared local
date-times use mandatory `spine-local-date-time` format assertion, with a specified
Gregorian/leap-year/clock domain and an executable offline checker. The test checker
also explicitly asserts the existing UTC `date-time` format without relying on an
optional validator dependency. Calendar checks cover requests, response range and
occurrence facts, and cursor ordering facts. Available event cores/occurrences require
`event_start`; agenda requires its matching primary anchor, including `task_due` for
tasks. Defer-only task detail and unavailable/unscheduled states remain valid.
Added 15 positive/negative fixtures (68 total) and semantic regression checks; refreshed
only the new v2 shared-schema pin. This is a manual contract patch, not a clean audit
verdict or runtime conformance result. Focused re-audit remains pending.
Verification: 77 tests and 266 subtests passed across new contract checks and the
existing web/runtime/domain fixture suites. Ruff, companion Markdown links and
`git diff --check` passed. No new audit, commit or push was performed.

**Focused machine-contract recheck staged (2026-09-17):** At operator request,
prepared `whetstone_runs/independent-activity-read-machine-contract-audit-002/` for
reviewer-only Sol/consistency verification of the three audit-001 fixes and directly
introduced regressions. Notes enumerate 32 exact outgoing inputs, including prior
feedback, affected schemas, parent/companion authority, test/pin/manifest evidence,
all 15 new fixtures and one unchanged baseline response. The approved manual patch
remains uncommitted; preparation records its actual source hashes against base
`f9a301b`, not a clean-checkpoint claim. Local preflight: 15 focused tests and 144
subtests passed; diff hygiene passed; bundled CLI `0.154.0-alpha.6.2` verified.
At preparation, outgoing approval was pending; no nested reviewer, source patch,
commit or push was run during preparation.

**Focused machine-contract recheck completed (2026-09-17):** After explicit
approval of the exact inventory, ran reviewer-only `audit-change` with
`gpt-5.6-sol`, built-in consistency profile and bundled CLI `0.155.0-alpha.2.6`.
Audit-002 returned `pass`, `boundary_preserved=true`, with zero blockers, majors,
minors or nits. The three prior findings were not raised again; no further action
was recommended within the focused scope. Report:
`whetstone_runs/independent-activity-read-machine-contract-audit-002/change_audit/change_audit_report.json`.
All 31 source files remained byte-identical to preparation, and all 32 manifest
input hashes matched, including the approved notes. Local focused verification
again passed 15 tests and 144 subtests. Review assessed the supplied contract,
schemas and oracle evidence, not runtime implementation or unsupplied fixtures;
it is not a convergence or deployment claim. No Editor, source patch, commit or
push was performed. The manual fixes remain ready to checkpoint before runtime
implementation.

**Runtime planning checkpoint (2026-09-18):** Updated this live task and the existing
implementation plan against the ratified read spec, machine companion, registry,
projection/normalization/cursor/pin artifacts, IR matrix and Kinflow handoff. The plan
keeps one backend delivery, with explicit verification and later deployment/consumer
gates; it does not add a new normative contract. No runtime, schema or fixture changes,
staging action, commit or push were performed by this planning update.
Verification: agent-documentation and independent-read contract suites passed
22 tests and 223 subtests; both planning documents' local links/heading anchors
and `git diff --check` passed. README still points to the authoritative read spec
and companion and correctly labels runtime implementation as pending.

**First runtime foundation slice (2026-09-18):** Added internal
`src/spine/web/read_contracts.py`, `read_context.py` and `read_projection.py`.
They load an explicitly supplied offline pinned bundle, assert Gregorian formats,
match normalization vectors, open dedicated read-only SQLite assembly snapshots,
enforce separate core/optional budgets, select owner/grant-authorized candidates,
and assemble closed current core/time projections. Source time is authorized before
follow-binding resolution; stale or denied source facts expose only unavailable time.
Snapshot-mode tasks retain independently readable time. This is not a public response
boundary: fresh release authorization/source fences are intentionally still required.

**Query/index assessment for this slice:** Existing owner/grantee indexes support
candidate admission; detail primary keys, unique seed-anchor lookup and the recurrence
revision index support rooted recurrence-header selection. Factored the canonical
recurrence header loader to traverse only the requested item's indexed detail history
instead of scanning all recurrence sets. Canonical revision precedence is unchanged,
including after item-version edits; both new projection and existing canonical loads
use that shared reader. `EXPLAIN QUERY PLAN` and old/new selection comparisons cover
the lookup. No DDL, schema version or migration is needed for these primitives.
Optional-section and complete agenda/source-fence query paths still need their own
task-local query assessment as they are implemented; this is not a whole-slice
no-migration claim.

**Boundary:** No v1 permission, route, registry or schema-pin changes; no v2 routes or
implemented-version declarations; no new packaged contract advertisement. Tests use
the checked-in source bundle explicitly. No live data repair, deployment, commit or
push. Existing uncommitted planning updates are preserved.

**Second internal assembly slice (2026-09-18):** Added `read_sections.py` and
`read_assembly.py`. All eleven fixed detail states and all four agenda singleton
states now assemble authorized rows before sorting/counting. Available null/empty,
not-requested, and generic incomplete optional failures remain distinct. Collection
assembly retains the whole bounded authorized set for later pagination; it does not
issue cursors or pretend a truncated set is exhausted. Agenda summaries retain their
underlying authorized rows for subsequent source hashing. Optional permission traversal
uses a separate resource reserve and does not consume root admission capacity.

Relations probe authorized endpoint pairs, including mixed owners with explicit read
grants; opaque relation metadata is fail-closed. Bindings expose current revision
headers only after both endpoints and the relation are disclosable. Profiles require
catalog/pinned-revision/application authority. Policies, historical work and attempts
share recipient/route/catalog predicates; only attempt evidence counts toward attempt
status. Approved current targets, self subject roles, proven item-local inline places
(including replacements), and authorized creation receipts use closed allowlists.
Undefined shared-place/foreign-subject authority and unknown protected receipt
references yield null/empty authorized subsets, not inventories of hidden resources.
No provider, rendering, raw receipt, source provenance or owner payload is returned.

Canonical occurrence expansion and overlays reuse the existing engine and decorator;
IDs/keys remain byte-for-byte canonical. Agenda reuses canonical recurrence ranges,
anchor resolution and ordering, without the v1 helper's binding hydration. It prepares
resolved entries first and separately ordered unplaced cores with whole-candidate
coverage; no last-known deadline is used. Non-temporal filters precede expansion.
Read-only ledger snapshots remain the only execution context; reads create no receipts,
work, provenance, repairs or other durable effects.

**Query/index evidence:** Actual `EXPLAIN QUERY PLAN` showed an all-status relation
scan and broader target/route probes for bindings/work. Schema 15 adds four indexes:
`independent_read_relation_endpoints_idx`, `independent_read_binding_endpoints_idx`,
`independent_read_work_policy_idx`, and `independent_read_creation_receipt_idx`.
Fresh initialization, normal migration, version declaration and the generated DDL
manifest are updated. A schema-14 upgrade test preserves every domain/evidence row
and ledger identity. Actual optional and agenda/recurrence SQL plans are regression
checked. Agenda inspection also exposed SQLite selecting the resource-kind grant
index; candidate discovery now uses explicit subject/group grantee probes through
existing indexes. Canonical recurrence child reads remain revision-indexed.

**Unadvertised contract correction:** Real engine occurrence keys exceed the generic
256-character resource-ID limit. Added a dedicated opaque key type to the projection
and matching cursor ordering slots, and updated only the v2 schema pins. Canonical
identities are neither shortened nor re-derived; response/cursor byte ceilings remain.
V1 pins, registry, HTTP routes, CLI/write authorization, replay and delivery semantics
are unchanged. This checkout requires schema 15 locally; no staging database was
migrated, and no push, deployment or public capability activation was performed.
The operator subsequently authorized a local commit of this completed internal slice.

**Next implementation:** Add fresh source/authorization release fences and authorized
snapshot hashing, then integrate the v2 cursor protocol and combined stream/section
pagination. Full HTTP/package/capability activation and IR-01–IR-16 HTTP/Kinflow
acceptance remain subsequent work. Internal assembly tests do not close those gates.

**Second-slice verification:** The new assembly suite adds 26 real-ledger tests for
mixed ownership, hidden graph growth, the recurring-event/unowned selected-occurrence
follower, protected catalog/route/receipt evidence, all section states, independent
optional failures/budgets, stale/denied source time, resolved/unplaced candidates,
recurrence exceptions, canonical identities, DST, date/windows, terminal/archive
lifecycle, read-only behavior, actual query plans, and index-only migration. Combined
assembly/foundation/contracts/migration/identity command:
`PYTHONPATH=src:../tickerd/src .venv/bin/python -m pytest -o addopts='' -q tests/test_independent_activity_read_assembly.py tests/test_independent_activity_read_foundation.py tests/test_independent_activity_read_contracts.py tests/test_ledger_migrations.py tests/test_ledger_identity.py`
passed **80 tests and 158 subtests**. The final full command
`PYTHONPATH=src:../tickerd/src .venv/bin/python -m pytest -o addopts='' -q` passed
**552 tests and 567 subtests**. `.venv/bin/ruff check .`, `git diff --check`, and
changed-document local-link checks passed. No implementation blocker remains for
this internal slice; public release authorization and HTTP/Kinflow acceptance are
explicitly not claimed.

**Foundation verification:** `tests/test_independent_activity_read_foundation.py`
adds 19 tests covering exact vectors and calendar rejection, pin failure, budget
separation, read-only snapshots, root-first guards, the unowned-follower regression,
stale/denied source time, snapshot independence, unscheduled/defer-only tasks, grant
time boundaries, canonical recurrence lookup parity/query plans, DST/window projection,
v2 error mapping and non-advertisement. Full command
`PYTHONPATH=src:../tickerd/src .venv/bin/python -m pytest -o addopts='' -q` passed
526 tests and 567 subtests. `.venv/bin/ruff check .`, `git diff --check`, and planning
document link/heading checks passed. No new Whetstone run or staging claim.

## Roadmap candidates — not selected work

These retained entries require operator selection. They do not schedule a gap analysis.

### SPINE-008 — Close the focused facet machine-contract recheck

**Status:** Ready. **Dependencies:** None for the focused contract review.

**Acceptance:** Recheck the manually patched replay-response alignment and
test-dependency scope findings against the current facet bundle; retain the result and
resolve any resulting concrete findings. Update the facet draft's recheck status
without representing static fixtures as runtime proof. This task does not start an
additional broad audit campaign or authorize facet implementation.

**Sources:** [Facet draft and machine-contract status](../specs/archetype-facets.md),
[facet roadmap](IMPLEMENTATION_PLAN.md#future-horizon-archetype-facets-and-workflow-recipes).

### SPINE-009 — Settle facet implementation gates

**Status:** Needs decision. **Dependencies:** SPINE-008 and the facet-specific
contract gates below. The deferred resilience campaign is not a blanket prerequisite.

**Acceptance:** Resolve Decision 0004, migration/index design, permission resolver
mappings, authenticated cursor semantics, and exact notification-work freshness on
facet-only item edits. Add the required contracts and behavioral oracles, then create
bounded implementation tasks for the flight-details proof. Keep workflow recipes and
external observations separate; do not advertise runtime facets from draft schemas.

**Sources:** [Facet gates](../specs/archetype-facets.md),
[Decision 0004](../specs/decisions/0004-versioned-item-facets.md).

## Later horizons

These entries preserve roadmap intent. Their acceptance criteria describe the next
planning outcome; each needs decomposition before executable work is selected.

### SPINE-011 — Prepare notification-activated contextual advisories

The narrow protection-amendment drafting task is completed separately as SPINE-017.
Its proposed decision and manual checklist do not close this horizon's remaining
native mapping, machine-contract, or implementation decisions.

**Status:** Needs decision. **Dependencies:** Confirm the roadmap's Version 1 pack
publication/proof prerequisite with its owning component before the advisory delivery
slice. The deferred resilience campaign is not a blanket prerequisite; the advisory
contract's own bounds and acceptance requirements still apply.

**Acceptance:** Review the current activation/fallback direction and settle immutable
definitions, privacy/context bounds, configurable budgets, silence permission,
selection/recovery races, evidence ownership, and cross-system contracts. Define
timing/race/replay fixtures and a bounded read-only proof routed through ordinary
notification delivery. Split contract and runtime work only after those choices are
settled; record the external pack dependency rather than assuming it is complete.

**Sources:** [Current advisory draft](../specs/contextual-advisories.md),
[autonomy exploration](design-notes/scheduled-agent-autonomy.md),
[advisory roadmap](IMPLEMENTATION_PLAN.md#future-horizon-notification-activated-contextual-advisories).

### SPINE-012 — Define workflow recipes and external observations

**Status:** Needs decision. **Dependencies:** SPINE-009 for canonical facet integration;
explicit external runner and pack ownership.

**Acceptance:** Separate volatile provenance/expiry-bearing observations from canonical
facets; define declarative recipe versions, deterministic plan/apply/verify behavior,
owner activation preferences, and authorization boundaries. Produce separate bounded
tasks for observations and recipes before implementation.

**Source:** [Facets and recipes horizon](IMPLEMENTATION_PLAN.md#future-horizon-archetype-facets-and-workflow-recipes).

### SPINE-013 — Select the next protected identity and admission slice

**Status:** Needs decision. **Dependencies:** A selected product need and enforcement
scope beyond the trusted web delivery.

**Acceptance:** Choose and bound the next protected feature, such as verified web
sign-in, recovery, protected executor/chat admission, or delivery mandates. Reconcile
its preserved draft, cross-component ownership, and qualification oracles before
creating implementation tasks. These features do not gate the current trusted GUI.

**Sources:** [Identity architecture](../specs/identity-and-access.md),
[enforcement draft](../specs/permission-enforcement-and-web-admission.md),
[OpenClaw admission](../specs/openclaw-admission.md).

### SPINE-014 — Triage the remaining deferred roadmap ideas

**Status:** Needs decision. **Dependencies:** An explicit selected use case.

**Acceptance:** When calendar/vendor projections, broader dashboards, governance
integration, or freeze-manifest promotion become a priority, create a bounded task
with component ownership, dependencies, and acceptance evidence. Preserve Tickerd's
runtime ownership and structured canonical ingest; those boundaries are not features
to implement in Spine.

**Source:** [Deferred roadmap](IMPLEMENTATION_PLAN.md#deferred-beyond-this-delivery).

## Deferred resilience, containment, and storage work

Deferred on 2026-09-13 at the operator's request. The operator is satisfied with the
resilience and containment achieved when the event-emission issues were fixed.
SPINE-004–007 and the related storage-lifecycle horizon SPINE-010 are retained for
later, with no assessment, implementation, or qualification work scheduled. Reactivate
only on explicit operator request. This changes work priority, not implemented safety
behavior or the verification required for a separately selected concrete change.

### SPINE-004 — Reconcile and finish the remaining containment slice

**Status:** Deferred (2026-09-13, operator direction). **Dependencies if reactivated:** Operator selection of a concrete containment
task; any gap assessment requires an explicit request. Resolve relevant draft
requirements before implementing uncovered behavior.

**Acceptance if reactivated:** Map current code and tests to the resilience containment requirements,
credit already implemented Tickerd admission, event bounds, storage stops, and durability
latching, and identify exact remaining work. Confirm the status of retry-budget
validation, the transitional dry-run ceiling, and storage readback; define bounded
implementation tasks and their failure oracles. Close those tasks with matching tests
and declarations before marking this item done.

**Sources:** [Resilience spec](../specs/operational-resilience.md),
[compatibility](../specs/compatibility.md),
[resilience roadmap](IMPLEMENTATION_PLAN.md#next-initiative-operational-resilience-and-boundedness).

### SPINE-005 — Specify and implement bounded failure recovery

**Status:** Deferred (2026-09-13, operator direction). **Dependencies if reactivated:** SPINE-004 for delivery ordering;
accepted recovery semantics before runtime work.

**Acceptance if reactivated:** Settle poison-item isolation, bounded backoff/circuit breaking and
retry exhaustion, in-progress lease recovery, and ambiguous external outcomes. Add
the required decision, ontology/migration changes, readback, and operator workflow;
split implementation into bounded tasks with crash/replay/failure tests. Preserve
durable attempt evidence and prove recovery does not silently duplicate effects.

**Source:** [Resilience spec](../specs/operational-resilience.md).

### SPINE-006 — Deliver bounded traversal and continuation

**Status:** Deferred (2026-09-13, operator direction). **Dependencies if reactivated:** SPINE-004 and SPINE-005 for delivery
ordering; settle traversal and budget contracts before runtime work.

**Acceptance if reactivated:** Specify and implement fair keyset traversal for automatic discovery,
continuation-complete notification materialization, bounded agenda/readback, and core
request/text/collection/expansion budgets. Split by executable boundary and retain
large-ledger, continuation, fairness, and overflow evidence.

**Source:** [Resilience spec](../specs/operational-resilience.md).

### SPINE-007 — Qualify operational resilience

**Status:** Deferred (2026-09-13, operator direction). **Dependencies if reactivated:** SPINE-004–006.

**Acceptance if reactivated:** Run the required idle, persistent backlog, provider outage, crash,
timezone-data, WAL, disk-pressure, and large-ledger campaigns against exact release
versions. Record bounded resource behavior, recovery outcomes, and remaining gaps;
claim conformance only for requirements exercised by retained evidence.

**Source:** [Resilience qualification requirements](../specs/operational-resilience.md).

### SPINE-010 — Establish the ledger storage lifecycle

**Status:** Deferred (2026-09-13, operator direction). **Dependencies if reactivated:** SPINE-004 storage readback; post-fix
staging growth evidence before choosing retention behavior.

**Acceptance if reactivated:** Establish a measured growth baseline; classify durable fact families;
settle replay retention; specify verified archival/compaction, manifests, restore,
budgets, and stop conditions. Create bounded delivery tasks. Storage pressure alone
never authorizes deletion of canonical evidence.

**Source:** [Storage lifecycle horizon](IMPLEMENTATION_PLAN.md#future-horizon-bounded-ledger-storage-lifecycle).

## Completed

### SPINE-024 — Seed the Impetus HLD from the shared architecture

**Status:** Done (2026-09-15; proposed HLD drafting, not audited or implemented).
**Dependencies:** Shared checkpoint `082dc7f`, SPINE-019–023.
**Outcome:** Wrote `../impetus/specs/architecture.md`, `0.1.0-draft.1`, directly
in the operator-selected repository. It references shared architecture
`cortext.cross-system-execution` at exact Spine commit
`082dc7fbed4895d93314d0d331ea3874c74dc640`. It defines execution/controller/backend/
capability boundaries, native evidence and governance ownership, limits and uncertain
call recovery, source-freshness and advisory preservation, and future-profile boundaries.
Provider/backend, transport, native mappings, storage and numeric budgets remain open.

**Handoff:** Updated Impetus overview and README and added the HLD to its existing
scaffold verifier's required files. Preserved the otherwise uncommitted seed scaffold;
no runtime folders or machine-contract placeholders were created. The Impetus project
thread can refine/review the HLD and select the bounded first-slice choices before
machine contracts. No automatic adoption or runtime compatibility is claimed.

**Verification:** Impetus `python3 scripts/verify_repo.py` passed (structure/local
links/template checks only). New/edited Impetus files have no trailing whitespace;
all five pinned Spine source paths exist at the stated local commit. Remote availability
was not tested or implied. Spine `git diff --check` passed. No nested audit, external
execution, deployment, commit or push; Spine source specifications were unchanged.

### SPINE-023 — Focused re-audit of advisory authority/freshness clarifications

**Status:** Done (2026-09-15, reviewer-only focused recheck).
**Dependencies:** SPINE-021 findings and SPINE-022 manual patch.
**Outcome:** `cross-system-execution-contract-audit-003` returned `pass`, zero
blocker/major/minor/nit findings, `boundary_preserved=true`, next action `none`.
The two prior findings were not raised again; the manual patch addresses their
specific passages. Empty feedback supplies no per-finding closure explanation or
exhaustive coverage proof. This is bounded consistency evidence, not convergence,
cross-repo adoption or runtime-readiness certification.

**Evidence:** Local ignored artifacts under
`whetstone_runs/cross-system-execution-contract-audit-003/change_audit/` include
the report, feedback, manifest and brief. Explicit invocation and manifest pin
`gpt-5.6-sol`, bundled CLI `0.154.0-alpha.6.2`, profile `consistency`; launcher
reasoning remains `medium`. Returned model metadata also identifies Sol this time.
All four raw hashes remained unchanged and all four normalized manifest hashes
matched; `git diff --check` passed. No source spec edits, Editor, additional model
calls, shared-default changes, commit or push were performed.

### SPINE-022 — Clarify advisory consumption and staged freshness checks

**Status:** Done (2026-09-15, manual specification patch; subsequent re-audit passed in SPINE-023).
**Dependencies:** Operator-approved findings from SPINE-021 retry 002.
**Outcome:** [Contextual advisories](../specs/contextual-advisories.md) Draft v0.3.4
reserves native evidence acceptance for governance; Spine refuses local consumption
when stale. Initial stale work creates/sends no submission; a later failed dispatch
recheck preserves the immutable submission/native references and blocks execution.
Replay resolves that preserved state without new execution or snapshot replacement,
including an incomplete native handoff. Lifecycle, failure distinctions and future
fixture obligations align with those rules; exact native mappings remain deferred.

**Verification:** 7 agent-documentation tests and 2 implemented-contract-declaration
tests passed; `git diff --check` passed. Acceptance-reference §7.5, fallback/branch
selection §8.1, explicit recovery §8.2 and idempotency/attempt accounting §10 remained
byte-identical to their pre-patch contents. README still routes to the authoritative
spec index. Only the advisory source spec and this tracker were edited for this task;
earlier uncommitted work was preserved. No runtime, machine-contract, other-repository,
editor workflow, nested audit, commit or push changes.

### SPINE-021 — Bounded audit of the shared execution architecture

**Status:** Done (2026-09-15, reviewer-only audit; findings patched in SPINE-022 and rechecked in SPINE-023).
**Dependencies:** SPINE-020 draft; no downstream adoption or runtime implementation implied.

**Outcome:** Retry 002 completed with `needs_revision`: 0 blockers, 2 majors,
0 minors, 0 nits. Both findings are in `specs/contextual-advisories.md`:
`fb_acceptance_consumption_terms` separates governance evidence acceptance from
Spine consumption/freshness checks (§3 invariant 7 and §9);
`fb_freshness_submission_sequence` separates initial pre-submission refusal from
post-submission dispatch prevention, preserving immutable submission/replay evidence (§§8–9).
The cited passages were checked locally. No source-spec patch was made.

**Evidence:** `whetstone_runs/cross-system-execution-contract-audit-002/change_audit/`
contains the report, feedback, brief and manifest (local ignored artifacts).
Invocation and manifest pin `gpt-5.6-sol`, bundled CLI `0.154.0-alpha.6.2`,
consistency profile and launcher reasoning `medium`. The feedback's model-authored
reviewer metadata incorrectly says `gpt-5`; it is inconsistent with the explicit
invocation/manifest and is not independent model attestation.

**Verification and limits:** All ten raw input hashes remained unchanged and all ten
normalized manifest hashes matched. `git diff --check` passed. Report
`boundary_preserved=false` follows the major-finding verdict; this is not an
independent preservation/coverage test or a convergence claim. No Editor, native
repository source expansion, shared default change, commit or push occurred.
Attempt 001 is retained separately as `audit_failed`: CLI `0.142.0` was rejected
before semantic review. No installation upgrade was needed for retry 002.

### SPINE-020 — Draft the versioned shared execution architecture

**Status:** Done (2026-09-15, Codex; proposed specification drafting only).
**Dependencies:** SPINE-017–019 protection and native-handoff findings.

**Outcome:** Added [Cross-System Execution Architecture](../specs/cross-system-execution.md),
ID `cortext.cross-system-execution`, document version `0.1.0-draft.1`. It separates
coordination, governance, execution, capabilities and result consumption, with explicit
budget/evidence/freshness and retry boundaries. Downstream exact references identify
the version, source repository/path and containing Git commit; design reference,
adoption and runtime conformance remain distinct. Checkpointed revisions are immutable;
further drafts increment the draft revision. No freeze manifest or hash gate was added.

**Preservation:** Added links in orientation, architecture and advisory specs and
recorded the Impetus handoff sequence in the roadmap. Original architecture/advisory
body lines remain verbatim and in order; only declared status/date headers changed.
The full advisory profile remains authoritative for its required behavior. No other
repository, runtime, machine schema, registry, package version or migration changed.
The separate native-handoff report from SPINE-019 is included in the same checkpoint.

**Verification:** Seven agent-documentation tests and two implemented-contract
declaration tests passed; 87 local links resolved, whitespace and diff checks passed.
These checks do not establish semantic preservation or cross-system conformance.
At drafting completion the shared document was not yet audited; see SPINE-021–023
for the subsequent audit, patch and passing focused recheck. It remains proposed,
not ratified. Other components have not
adopted it; exact downstream checkpoint references can be made after its commit exists.
The Impetus HLD, native contracts, backend selection and runtime work remain separate.

### SPINE-019 — Investigate native advisory execution handoff

**Status:** Done (2026-09-15, Codex; operator-selected investigation).
**Dependencies:** Protection amendment and bounded review, SPINE-017–018.

**Outcome:** The [native handoff investigation](design-notes/advisory-native-handoff-investigation.md)
maps Spine's first advisory profile to native drafts, actual code and focused tests.
Intent admission, pinned policy, evidence persistence, approvals and replay are real;
the current dispatch path records local success without research execution. Native
scoped authorization, a bounded runner, advisory evidence validation and Spine freshness
handoff still need contract/runtime work. A field-only adapter cannot close that gap.
The note recommends a bounded native execution extension paired with the Spine bridge,
not completion of a general workflow platform. Runner and transport choices remain open.

**Evidence:** Spine base `560ecc4`, native base `8afa61f`; 55 focused native tests
passed using temporary databases, covering runtime API, evidence, replay, arbitration
and intake. All 19 report links and diff hygiene passed. Native pre-existing dirty
files remained untouched. No normative specifications, runtime code, deployments,
provider calls, or audits changed. This is not native full-spec or live integration
qualification; see the report's evidence boundary and declared Tickerd-version mismatch.

### SPINE-018 — Bounded review of the advisory protection amendment

**Status:** Done — reviewer-only audit completed on 2026-09-14 (Codex); the operator-
authorized minor wording clarification was applied on 2026-09-15.
**Dependencies:** SPINE-017 draft and explicit approval of the eleven-file inventory.

**Outcome:** `pass_with_minor_clarification`: zero blockers, zero majors, one minor,
zero nits. Finding `fb_0001` identifies the ambiguous architecture §9.1 phrase
“general workflow support does not.” Recommendation: explicitly say that general
workflow support remains outside this slice and is not a prerequisite for advisory v1.
No source specs were patched during the audit; no Editor, convergence, or
implementation run occurred.

**Manual follow-up:** Addressed `fb_0001` in architecture §9.1 using the recommended
wording, consistent with Decision 0005 and contextual advisories §15. This is a
specification-only clarification, not new workflow capability. The original audit
artifacts remain unchanged and describe the pre-patch inputs; no re-audit is claimed.
Verification: all seven agent-documentation tests and `git diff --check` passed;
README links still point to the authoritative spec index and architecture document.

**Evidence:** Local ignored run `whetstone_runs/advisory-protection-contract-audit-001/`:
`change_audit/change_audit_feedback.json`, `change_audit/change_audit_report.json`,
and `input-verification.md`. All eleven inputs retained their pre-run hashes and
match the manifest; all three baseline copies match git objects at `706b499`.
Feedback and report bind to the generated audit brief hash. The approved review
compared the baseline with candidate `6077bf3`, using P-01–P-20 and E-01–E-06.

**Limit:** Whetstone reports `boundary_preserved=true`, derived from severity counts,
not independent objective assessments. The report does not establish complete
checklist coverage, semantic equivalence, convergence, decision ratification, or
advisory implementation readiness. Its objective-assessment enhancement remains
unimplemented. Further manual changes or review runs require operator authorization.

### SPINE-017 — Draft the advisory architectural protection amendment

**Status:** Done (2026-09-13, Codex; specification drafting only, selected by the operator).
**Dependencies:** Existing advisory draft and the completed three-case extensibility
analysis; no outstanding product decision blocked this narrow amendment.

**Outcome:** Added proposed [Decision 0005](../specs/decisions/0005-profile-scoped-advisory-execution.md),
additive advisory/architecture/ontology clarifications, and the baseline-bound
[preservation checklist](design-notes/advisory-protection-preservation-checklist.md).
The amendment separates advisory-specific requirements from future execution scope,
dependencies, native run/evidence, and result-consumption boundaries. It adds no
general automation support and leaves the broader SPINE-011 horizon unselected.

**Preservation evidence:** Against baseline `706b499665add9e15a041f2c26dd20c2446f5139`,
all original body lines of the three amended specs remain verbatim and in order;
only the advisory status line changes. P-01–P-20 record manual obligation correspondence
and E-01–E-06 identify future review objectives. No runtime, machine schema, migration,
fixture, package version, registry, native governance spec, or deferred initiative was
changed. Local link and diff-hygiene checks passed. Relevant unittest suites passed:
agent documentation (7), implemented contract declarations (2), and notification
rendering fixtures (3). HEAD and index stayed unchanged.

**Limit:** Manual comparison and tests are not independent semantic preservation proof.
Decision ratification and a later approved bounded reviewer audit remain separate;
no audit was run and no advisory implementation-readiness claim is made.

### SPINE-000 — Establish work tracking and reconcile orientation

**Status:** Done (2026-09-13). **Dependencies:** None.

**Outcome and evidence:** Added this ordered backlog with stable IDs, statuses,
dependencies, and acceptance criteria. Linked it from the
[README](../README.md), [agent instructions](../AGENTS.md), and
[implementation plan](IMPLEMENTATION_PLAN.md); separated live task status from roadmap
snapshots. Reconciled the seed-spec label, README schema boundary, and specs index's
web implementation label against [package metadata](../pyproject.toml),
[ledger identity](../specs/ledger-instance-identity.md), and
[web implementation status](../specs/trusted-multi-operator-web-api.md).
Documentation links and diff whitespace were checked; runtime behavior is unchanged.

Earlier delivered slices remain in the implementation plan's delivery history;
they are not recreated as retrospective tasks here.

## Closed — withdrawn

### SPINE-001 — Reconcile existing web staging evidence and remaining gaps

**Status:** Closed — withdrawn (2026-09-13). **Dependencies:** None; no follow-up required.

**Closure:** Withdrawn at the operator's request. This assistant-created evidence
review was not tied to a confirmed defect. The frontend and staging deployment already
exist; no gap analysis is requested. No qualification or verification completion is
claimed. SPINE-015 separately tracks the reported linked-resource read failure.

### SPINE-002 — Close evidenced gaps in the existing staging setup

**Status:** Closed — withdrawn (2026-09-13). **Dependencies:** None; no follow-up required.

**Closure:** Withdrawn at the operator's request with SPINE-001. No specific remaining
staging work had been established for this placeholder. This closure neither schedules
new staging checks nor claims all possible deployment checks have passed.

### SPINE-003 — Reconcile existing Kinflow frontend coverage and follow-ons

**Status:** Closed — withdrawn (2026-09-13). **Dependencies:** None; no follow-up required.

**Closure:** Withdrawn at the operator's request. Kinflow's connected frontend is
already under operator testing; no general frontend gap analysis is requested.
Future work will follow concrete operator-supplied items, not this broad review.

## Completed — cloud validation repair

### SPINE-016 — Reconcile clean cloud validation findings

**Status:** Done (2026-09-13, Codex). **Dependencies:** None.

**Scope:** Restore the five packaged archetype-facet schema copies through the
existing synchronization script and enforce its check in CI; repair strict core/ledger
typing without semantic changes; correct the trusted-web test helper import for both
pytest and documented unittest discovery. Keep unrelated specification work intact.

**Confirmed locally:** The sync check reports exactly five missing copies; strict
mypy reports 26 errors in notification rendering and ledger transactions; pytest
collection fails on the top-level `test_schedule_create_command` import.

**Acceptance:** Complete documented unittest discovery, pytest, repository-wide Ruff,
strict core/ledger mypy, compileall with bytecode outside the repository, and the
packaged-contract sync check. Preserve pre-existing local work; no deployment, real
ledger access, runtime internet changes, commits, or pushes.

**Outcome and evidence:** Regenerated only the five missing packaged schemas with
[sync_web_contracts.py](../scripts/sync_web_contracts.py); added its `--check` invocation
to [CI](../.github/workflows/ci.yml). Corrected renderer non-returning validation and
timezone annotations, and matched the SQLite context-manager type signature; executable
logic and public contract versions are unchanged. The web test now imports its helper
through the existing `tests` package. Added renderer rejection cases and isolated
in-memory transaction commit/rollback/exception tests.

Verified with the existing virtual environment (Python 3.14.6, mypy 2.3.0, Ruff 0.16.2,
pytest 9.1.1): `python -m unittest discover -s tests` ran 492 tests in 20.474s, OK;
`pytest -q` completed successfully with 492 passing test result markers;
`ruff check .` passed; `mypy --strict src/spine/core src/spine/ledger` reported no
issues in 35 source files; `python -m compileall -q src tests examples` passed with
`PYTHONPYCACHEPREFIX` in a cleaned temporary directory and repository bytecode unchanged;
`python scripts/sync_web_contracts.py --check` and `git diff --check` passed. Unittest
remains the documented and CI validation path. CI's Python 3.12 job was not run remotely.

The final preservation check confirms HEAD/index unchanged, all ten other pre-existing
modified/untracked files byte-for-byte intact, and the entire prior backlog preserved
before this separately appended entry. No out-of-scope work was performed.

## SPINE-015 cloud validation repair

### SPINE-025 — Reconcile deferred packaging and source-only strict typing

**Status:** Done (2026-09-19). Local verification and the subsequent operator-reported
Python 3.12 cloud validation passed. Synchronization repair preserved; bounded
shared-helper dependency repair passes source-only and editable-install strict
checking with both locally tested mypy versions, plus the full regression suites.
**Dependencies:** Existing SPINE-015 package-activation boundary; no new spec decision
or v2 activation. The operator subsequently supplied clean Python 3.12 cloud evidence;
public v2 activation, HTTP/Kinflow acceptance and deployment remain separate.

**Confirmed baseline:** Clean checkout `f575af5c059c6a9cdeed4de7319a713ea7a17760`.
The synchronization gate expected 17 deferred read-family mirrors. Both mypy 1.20.2
and 2.3.0 pass in the editable-install environment but fail with 308 diagnostics in
seven transitive modules when using an interpreter without an installed Spine package
for import discovery (the cloud reported 307 with its installed dependencies). The
ledger imports the command layer through both a pure ID helper and late temporal
binding/occurrence helpers. Moving only the ID helper did not resolve the gate; that
experiment was fully reverted before the handoff. The earlier core renderer repair
is separate from the service renderer errors in this report.

**Completed synchronization repair:** Exclude the source-only `trusted-web-read-*`
family until the already-planned HTTP/package/capability activation checkpoint;
retain the existing v1 registry and current schema synchronization. The checker still
rejects missing, changed, unexpected and prematurely packaged assets. Four focused
regressions include future non-read schemas, read-only check behavior and deferred
registry/schema rejection. No canonical or packaged JSON, runtime declarations,
dependency versions, or strict typing settings changed.

**Synchronization-stage verification (2026-09-18):** Python 3.14.6;
`python -m unittest discover -s tests` passed **556 tests in 29.217s**; `pytest -o addopts='' -q` passed **556 tests and 572 subtests
in 29.63s**. All test invocations used the existing `.venv` and disabled repository
bytecode writes. `ruff check .`, `python scripts/sync_web_contracts.py --check`, and
`git diff --check` passed. `python -m compileall -q src tests examples` passed with
bytecode redirected to a cleaned temporary directory; existing repository bytecode
was unchanged. At that checkpoint, these passes did not supersede the unresolved
source-only mypy failure; the completed typing repair follows below.

**Typing repair (2026-09-19):** Reproduced the source-only failure before editing
with the handoff's mypy 1.20.2 command: **308 errors in seven transitive modules,
35 explicitly checked files**. Moved the unchanged command-ID derivation to
`core/hashing.py`, six pure occurrence-detail/scheduled-fact helpers to
`core/occurrence_details.py`, and historical item/detail/anchor hydration to
`ledger/item_reads.py`. Notification profiles and temporal bindings now depend on
these shared lower-layer implementations rather than importing the command package.
The command module retains aliases for all nine moved private helpers, and both
public command-ID import paths remain available. An AST comparison against HEAD
confirmed that all ten extracted helper bodies are identical apart from renamed
shared-helper references. Canonical identities, SQL, validation errors, recurrence
and binding behavior are unchanged. No mypy configuration, tool pin, ignore,
import-skipping rule, contract, schema version, or activation declaration changed.
This repairs the strict core/ledger dependency boundary; it does not claim full
strict typing of the command/service/web modules outside that target.

Regression coverage adds a fixed command-ID preimage/public-export check, historical
hydration and stable-error checks, and extends the selected-occurrence binding test
with a fresh subprocess that rejects command-layer imports. The subprocess restores
only a synthetic fixture, checks foreign keys, resolves the binding under SQLite
query-only mode, compares canonical source/provenance evidence, and verifies no writes.
The pre-existing synchronization repair, its four tests, and the
[historical handoff](SPINE_015_CLOUD_TYPING_HANDOFF.md) remain byte-for-byte intact.

**Strict verification:** Python **3.14.6**, configured mypy target **3.12**;
mypy **1.20.2** and **2.3.0**. The alternate discovery interpreter
`/opt/homebrew/bin/python3` was verified to have no installed `spine-ledger`
distribution. All four commands below exited 0 with **“Success: no issues found
in 37 source files”**; incremental caching was disabled in every run:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/spine-mypy-1.20.2-validation-20260918 .venv/bin/python -m mypy --strict --no-incremental --python-executable /opt/homebrew/bin/python3 --cache-dir /tmp/spine-typing-repair-120-source src/spine/core src/spine/ledger
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/spine-mypy-1.20.2-validation-20260918 .venv/bin/python -m mypy --strict --no-incremental --cache-dir /tmp/spine-typing-repair-120-editable src/spine/core src/spine/ledger
PYTHONDONTWRITEBYTECODE=1 .venv/bin/mypy --strict --no-incremental --python-executable /opt/homebrew/bin/python3 --cache-dir /tmp/spine-typing-repair-230-source src/spine/core src/spine/ledger
PYTHONDONTWRITEBYTECODE=1 .venv/bin/mypy --strict --no-incremental --cache-dir /tmp/spine-typing-repair-230-editable src/spine/core src/spine/ledger
```

**Regression verification:** pytest **9.1.1**, Ruff **0.16.2**. All test commands
used `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:../tickerd/src` with the existing
local environment; no Tickerd installation or qualification was performed.

```sh
.venv/bin/python -m pytest -o addopts='' -q tests/test_hashing.py tests/test_ledger_item_workflows.py tests/test_relative_temporal_bindings_command.py tests/test_recurrence_commands.py tests/test_agent_command_contract_mvp.py tests/test_command_response_fixtures.py tests/test_independent_activity_read_assembly.py tests/test_independent_activity_read_foundation.py tests/test_web_contract_sync.py
```

The focused selection passed **135 tests and 150 subtests in 10.22s**. After making
the child process explicitly select checkout source, the temporal-binding file
was rerun: `.venv/bin/python -m pytest -o addopts='' -q tests/test_relative_temporal_bindings_command.py`
passed **10 tests in 0.62s**.

Final full checks (all exited 0, no tests skipped):

- `.venv/bin/python -m unittest discover -s tests`: **559 tests in 30.141s, OK**.
- `.venv/bin/python -m pytest -o addopts='' -q`: **559 passed, 572 subtests passed
  in 30.65s**.
- `.venv/bin/ruff check .`: **All checks passed**.
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/sync_web_contracts.py --check`:
  **passed**; deferred read-family packaging remains excluded.
- `PYTHONPYCACHEPREFIX=/tmp/spine-025-compile-cache .venv/bin/python -m compileall -q src tests examples`:
  **passed**, bytecode directed outside the repository.
- `git diff --check`: **passed**.

Final preservation checks confirmed the pre-existing sync script, sync tests and
handoff hashes unchanged, and all backlog content preceding SPINE-025 unchanged.
HEAD remains `f575af5c059c6a9cdeed4de7319a713ea7a17760`; the index remains empty.
There are no local validation blockers. This is not a fresh Linux/Python 3.12 cloud
run or completed SPINE-015 HTTP/Kinflow acceptance. Release fences, cursor integration
and HTTP/package/capability activation remain subsequent SPINE-015 work.

No commits, pushes, runtime internet enablement, deployment, real-ledger access,
Tickerd work or subsequent SPINE-015 feature implementation occurred.

**Operator-reported cloud follow-up (2026-09-19):** Both SPINE-025 failures are
resolved. Source-only mypy 1.20.2 passed all 37 files on Python 3.12 with Spine
uninstalled and strict rules unchanged. Contract synchronization and wheel inspection
passed, with deferred v2 assets excluded. The cloud run reported **526 passed + 33
Tickerd skips = 559 tests**, plus **572 passing subtests**; packaging, installed-wheel,
migration, lint, compilation and documentation checks passed and the checkout stayed
unchanged. No actionable Spine failures were reported. Unavailable Tickerd coverage
and inability to provision a second mypy version in cloud are environment limitations;
both mypy versions were already verified locally. This is supplied operator evidence,
not a cloud run performed by the implementation agent, and precedes the subsequent
SPINE-015 release-fence slice recorded above.
