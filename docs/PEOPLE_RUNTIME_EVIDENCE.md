# People and responsibility — runtime evidence

Updated: 2026-10-24. Runtime 0.11.0/schema 19 public family follows Slice 3 checkpoint `17b3d3e`.

This is implementation evidence, not a specification or public capability declaration.
The [logical spec](../specs/people-and-responsibility.md) and
[machine companion](../contracts/people-and-responsibility.v1.json) remain authoritative.
The accepted A/B/C machine reviews are not reopened. The current acceptance map
combines the foundation evidence below with public transport, bounded-query,
installed-artifact and frozen-compatibility checks. This is not a deployment,
consumer adoption or general production qualification claim. Operator production
is stable; this work does not touch it.

## Executed boundary

Runtime 0.11.0 registers the three standalone local commands, additive local
scheduling v4 and exactly eight protected v3 operations. All use the existing
transaction/version/receipt owners below. The complete 36-schema people closure
is separately packaged with file hashes and a compiled pin; missing/tampered
assets/declarations fail closed without source fallback. New v3 cursor configuration
is protected context, never request JSON; absent/bad configuration disables the
whole v3 family but leaves valid frozen v1/v2 interfaces usable. No DDL or migration
is introduced, and Tickerd's exact dependency remains unchanged.

The following foundation/integration sections retain historical private-checkpoint
evidence. Their former unadvertised boundary was deliberate; the final public
delivery is qualified separately in the Slice 4 record below.

### Initial private foundation

The private candidate executes standalone people reads/writes and scheduling v4
directly through the same `LedgerConnection.atomic_command`, item allocator,
supporting-set persistence, audit/receipt writers and touched-state finalizers used
by existing local commands. It is not registered in public dispatch or either web
registry. It refuses transport metadata instead of treating a protected caller as
trusted local. No package/runtime/schema version or migration is introduced.

Trusted-local fresh references require exact active subject IDs. Existing active
associations can be retained or removed without readmission; inactive rows count
in equality and replacing them is a change. This is the already-approved local
full-ledger policy, not a protected bypass. Slice 2's standalone protected
candidate now supplies owner-scoped fresh reference and replay/disclosure checks.
Protected scheduling/read integration is now privately implemented below; public
routing and complete applicable qualification are still required before activation.

## Slice 2 — directory and standalone protected foundation

This first Slice 2 increment is private executable behavior, not completion of
Slice 2 or a compiled/packaged capability. The shared
[directory resolver](../src/spine/services/people_directory.py) implements approved
D-01/D-02 from current subject/group/membership facts. Every active member role can
read its own current group roster; item grants never substitute for directory
authority. Fresh references use the actual item owner, not a supplied unrelated
group. A subject-owned private item cannot acquire another assignee just because
both people share a group. Exact retained references and removals bypass fresh-add
admission, preserving item-grantee use without private roster probing.

The private [protected service](../src/spine/web/people_service.py) reuses existing
account/selection, ownership/grant checks and the canonical standalone mutation's
transaction body. Fresh writes require item-edit authority and expected access
evidence; compatible replay requires the initiating account/subject and current
item/receipt disclosure, not fresh edit/selection eligibility. All role/version,
audit, receipt and protected receipt-link facts commit or roll back together. The
existing transaction inventory records this additional outer entrypoint, not a
new allocator. It is not registered in HTTP or either public command registry.

Historical role identities remain immutable; current labels are resolved separately
through self or a shared current roster. Labels never enter receipts. Otherwise the
projection is exactly `not_disclosed`, without a reason. Hidden label metadata is
not read into source/proof facts, and its rename does not break a redacted read.
Integrity/capacity failures are not converted into label nondisclosure. Old self-only
`subject_roles` and all released read handlers are unchanged.

Private local and protected `people.list` implement authenticated `pc1` paging with
explicit protected cursor configuration. The codec matches the reviewed MAC vectors,
binds ledger instance/key generation/query/source/identity/access and the next relevant
membership transition, preserves original issue/expiry across pages, and rejects
noncanonical JSON/base64, cross-family tokens and tampering. Reads recompute the full
bounded authorized source and fence it in a fresh read transaction before release;
no receipt, cursor row, audit or durable cache is written. A single SQL/time/resource
budget spans assembly and release. Protected read transactions are query-only.

**Foundation checkpoint's remaining Slice 2 work:** integrate this shared authority/label resolver into protected
scheduling-v4 composites; implement the people optional section, person filtering
before temporal expansion, successor agenda/occurrence paging and its source/authority
proofs, optional core-reserve degradation, dense/hidden cost matrices and remaining
concurrent-writer cases. No whole PR-05–08/12/16 acceptance is claimed by this foundation.

## Slice 2 integration — protected scheduling and independent reads

The private [scheduling adapter](../src/spine/web/people_schedule_service.py) uses
the existing core scheduling handler plus shared people/rendering hooks inside one
outer transaction. Explicit creation ownership/history, people, policies, work,
audit, receipt and protected attribution commit together. Definition rendering can
resolve the exact admitted prospective owner before insertion; the same owner is
persisted after item creation and before presentation selection. No disclosure
approval is provisioned. Wrong owner scope/fresh references, failed release and a
failure immediately after owner insertion roll back all proposed facts. Equal people
updates retain original row IDs; omission preserves and empty arrays clear only the
managed kind. People-only updates leave work rows unchanged; full work qualification
is still Slice 3, not inferred from this regression.

The private [read service](../src/spine/web/people_read_service.py) uses existing
read-only snapshots, permission predicates, temporal assembly, optional evidence and
ordering. The released owners gained narrow default-preserving internal seams for
bounded candidate admission, preselected roots/nonmatching occurrences, optional
permission clones and unhashed authority facts. No request can select a permission
implementation. Existing contract hashes/registries and released read behavior remain
unchanged. All eight candidate commands are privately dispatched, not public routes.

Exact active role matching follows item admission, without resolving filter subjects.
For agenda, nonmatches are excluded before core/time expansion and source collection.
Direct nonmatching occurrences retain activity/time with an empty complete stream;
unavailable time remains incomplete. Matching tasks with unavailable sources remain
unplaced. The complete optional people section distinguishes nondisclosure from service
failure, shares optional budgets and cannot silently become a partial people list.
Legacy `subject_roles` stays self-only. Labels and metadata never enter mutation receipts.

`pc1` cursors now cover collection sections, both occurrence bases, and resolved/unplaced
agenda ordering using the existing ordering owners. Continuations are stateless:
recompute the bounded authorized source and access proofs, compare the signed bindings,
then fence a fresh snapshot before returning buffered output. No public data/proof cache,
cursor table, receipt, audit or generation write. Tests exercise shared budget accounting,
actual indexed selection plans, hidden growth, nonmatching edits, label/role/identity
changes, optional SQL/byte/resource failure and hard outer expiry. These are selected
runtime cases, not a claim that every density/grant/concurrency cross-product is closed.

## Writer parity and the identity correction

The existing [writer inventory](../src/spine/ledger/facet_writer_inventory.v1.json)
remains the one complete allocation inventory, covering 25 producers. Its AST
guard detects omitted/new allocation call sites. The new runtime matrix in
[test_people_writer_parity.py](../tests/test_people_writer_parity.py) executes every
inventoried producer, including ordinary event/task edits, completion/cancellation,
recurrence edits, reminders, scheduling, relative binding reconciliation, explicit
facet writes and the new people writer. It observes actual allocator returns and
compares complete role rows to the selected replacement plus exact copy-forward
result. Every old role version must remain byte-identical. The matrix also requires
nonempty role evidence for the selected successor producers.

Selected legacy scenarios receive active/inactive person/agent fixtures for all five
role kinds at v1. This prevents empty-set copy tests from passing vacuously. The
scenario's real command, allocator result, CAS and finalizers are not replaced.
Other scenarios retain their own exact-output fixtures. Existing
[facet writer tests](../tests/test_facet_writers.py) also run the people handlers
with empty and eight-entry facet snapshots. This is local writer evidence, not
HTTP admission or concurrent-writer qualification.

S1d found and reproduced a real mismatch: S1c's omitted roles still inherited legacy
`copy_id(prior_id, next_version)` IDs, while the reviewed people contract specifies
command-derived `/copy_forward/item_subject_role/<prior_id>` identities. The exact
ID regression failed against S1c before correction. An internal, explicit
`subject_role_copy_command` operand now opts only `item.people.update` and scheduling
v4 into those identities. The owning command ID is mandatory; unsupported ownership
or missing command identity refuses before allocation. Legacy callers retain their
original IDs. New replacement rows, no-op retention and historical rows are unchanged.
The spec's misleading word "existing" was clarified; paths/hash domains and legacy
compatibility promises did not change. No existing row is rewritten.

## PR obligation map

Current family acceptance combines real-ledger foundation tests with the public
CLI/HTTP and installed-wheel evidence. Offline witnesses remain separate and do
not independently close a runtime obligation. "Verified" is bounded to the specified
0.11.0 family, not arbitrary production load, deployment or consumer adoption.

| Obligation | Current runtime evidence | Acceptance boundary |
| --- | --- | --- |
| PR-01 — independent dimensions | Standalone/v4 edits retain ownership, memberships, policies, routes, work and attempts; public transport/installed paths share those owners. | Verified; no implicit access or delivery. |
| PR-02 — event/task sets | Omit/replace/clear/no-op, inactive/opposite/unmanaged roles, wrong types, unscheduled tasks, agents/accountless people and terminal refusal; public/installed history. | Verified managed-set semantics. |
| PR-03 — atomic version/copy/rollback | All-writer matrix, protected composite/owner/link rollback, public serialization failure rollback and real two-connection loser exclusion. | Verified existing atomic boundary; no second writer. |
| PR-04 — no-op/replay/preview/identity | Actual local/installed previews, exact canonical IDs and original replay; protected initiator/current-read checks after edit/reference eligibility loss. | Verified; replay is not a fresh edit. |
| PR-05 — roster/fresh-reference privacy | D-01 scope/member versus item-grantee admission, no fresh outsider probing, retention/removal, public denied errors and roster/resource caps. | Verified; no implicit grant/provisioning. |
| PR-06 — history/current labels | D-02 tuples versus current authorized labels, closed nondisclosure, optional fallback, hidden-label changes, release fences and public/installed history. | Verified; labels never enter receipts. |
| PR-07 — authorized person filters | Authority then exact active-role predicate before expansion/page; no subject lookup, hidden/nonmatch source exclusion, inactive-subject matches and unavailable/unplaced time; public routes. | Verified; series-level only. |
| PR-08 — cursors/release races | MAC/canonical vectors, query/source/identity/key/ledger bindings, both occurrence bases, roster/section/agenda pages, timed grants/membership and fresh release; installed roster/occurrence pagination. | Verified; no durable read cache. |
| PR-09 — continuity/mixed edges | Separate role/facet/presentation edge proofs, immediate policy bijection, same-intent distinct presentations/disabled siblings, invalid/skipped-edge refusal and 100-edge cap. | Verified; ordinary semantic changes not blessed. |
| PR-10 — work states | Eligible/selected/in-progress/retry/started/succeeded/failed/cancelled/absent matrix, exact evidence/provider/backoff, no reopening/materialization, old Tickerd selection and real attempt lock. | Verified; no real-send qualification inferred. |
| PR-11 — recurring/relative freshness | Exact recurring provenance retained; real recurrence edits stale old work; item/selected-occurrence follow-source invalidation and explicit refresh, target people non-refresh and snapshot independence. | Verified existing temporal owner. |
| PR-12 — bounded indexed reads | Exact 100/101 roles, 1000/1001 candidate/roster sentinels; actual owner/group/grant/role plans and VM costs, optional fallback/global limits across snapshots; +3000 hidden roots/grants leaves cost/output unchanged. | Verified bounded matrices, not sustained-load qualification. |
| PR-13 — writers/finalizers | All 25 actual producers, exact role/history copy, shared finalizer failures, protected/public composites and installed successor execution. | Verified; inventory guard remains active. |
| PR-14 — installed closure | Separate 36-schema/39-asset pinned closure, missing/tampered/declaration failures, synchronization, actual noneditable wheel, deep disposable verify and unchanged frozen bundles. | Verified package boundary; no migration. |
| PR-15 — public equivalence | Three standalone and v4 local selectors, all eight HTTP routes; decoded mutation/replay result parity, correct errors/identity, installed CLI/HTTP and old v2/v3/read/compact behavior. | Verified; no new local person-filtered read selector. |
| PR-16 — concurrency | Real version/attempt/roster writer exclusion, source/access/label/selection fences, timed access without epoch writes, edit-loss versus read-loss replay, source change before attempt and request-global transport deadlines. | Verified selected concurrency contracts, not general resilience campaigns. |

Primary evidence:

- [Core normalization tests](../tests/test_people_core.py): normalization, set/hash and replacement identity.
- [Exact-version tests](../tests/test_people_ledger.py): bounded current/history projection and terminal reads.
- [Private authoring tests](../tests/test_people_authoring.py): transaction rollback and shared continuity/freshness.
- [Actual command tests](../tests/test_people_commands.py): standalone/v4 receipts, preview, identity and independence.
- [Writer parity tests](../tests/test_people_writer_parity.py): actual inventory and copy/replacement verification.
- [Directory tests](../tests/test_people_directory.py): scoped discovery/fresh admission, labels, lifecycle, integrity/capacity and indexed probes.
- [Cursor tests](../tests/test_people_cursors.py): reviewed vectors, protected files, tampering, local paging/source/release/transition fences.
- [Protected standalone tests](../tests/test_people_web.py): real file-ledger admission, labels, mutation/replay, paging and transactional release rollback.
- [Protected scheduling integration](../tests/test_people_schedule_integration.py): event/task composites, ordinary/definition presentation, owner/people rollback, no-op/replay and work preservation.
- [Read integration](../tests/test_people_read_integration.py): filters, optional people sections, source/privacy/cursor fences, bounded degradation and actual selection plans.
- [Work states](../tests/test_people_work_states.py): real selected/in-progress/retry/attempt/terminal/absent evidence and shared-intent presentation bijection.
- [Continuity races](../tests/test_people_continuity_races.py): actual independent SQLite writers, prepared/started attempt fences and recurring/relative-source freshness.
- [Protected release races](../tests/test_people_release_races.py): exact successor external grant, timed access and roster/replay transitions.
- [Public CLI/package tests](../tests/test_people_public_cli.py): exact public selectors, previews, local history/pagination, complete pinned closure and fault injection.
- [Public HTTP tests](../tests/test_people_http.py): all eight routes, privacy, atomic buffering/deadlines, decoded CLI/HTTP parity and frozen route preservation.
- [Capacity tests](../tests/test_people_read_capacity.py): actual sparse/dense/hidden VM costs, index plans, sentinels and optional/hard budget distinctions.
- [Installed-wheel exercise](../scripts/verify_people_wheel.py): isolated public CLI and all eight Flask routes on disposable data; no source imports or sends.

## Verification and next gate

S1c checkpoint evidence: 1,128 tests, one skipped; its 26 handler tests were rechecked
before commit. S1d's selected regression run passes **198 tests in 41.860 seconds**,
including the complete local handler and writer matrix. Focused Ruff, strict typing
of six touched runtime owners, diff hygiene and 214 affected local link targets
pass. Full regression: **1,133 tests, one skipped, 186.307 seconds; passed**.
The operator authorized S1d's focused checkpoint on 2026-10-24. Its 31 people
command/writer-parity tests, focused Ruff, strict typing of six runtime owners
and staged diff hygiene were rechecked. The pre-existing `AGENTS.md` amendment
is excluded. No push, public activation or next-slice implementation is included.

Commands:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest \
  test_people_commands test_people_writer_parity test_people_authoring \
  test_people_core test_people_ledger test_facet_writers \
  test_schedule_create_command test_schedule_operations_command \
  test_rendering_successor_authoring test_rendering_delivery \
  test_notification_commands test_people_and_responsibility_contracts \
  test_ledger_transactions -q
.venv/bin/mypy --strict --follow-imports=silent \
  src/spine/ledger/item_drafts.py src/spine/ledger/supporting.py \
  src/spine/ledger/items.py src/spine/ledger/people_authoring.py \
  src/spine/commands/people_candidate.py src/spine/services/people_authoring.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python \
  -m unittest discover -s tests -q
```

### Slice 4 — public transport, package and bounded-read completion

The operator authorized the cohesive final implementation after `17b3d3e`.
Runtime 0.11.0 exposes the complete family on schema 19 without DDL, a migration,
or Tickerd changes. The standalone local commands and explicit schedule v4 selectors
reuse the same core as the eight protected HTTP operations. Local schedule/agenda/
occurrence reads, older selectors, compact projections and frozen self-only
readbacks retain their existing behavior. The public request/result decoders use
the installed package, not source-tree paths. `jsonschema>=4.23` is consequently a
declared base runtime dependency; web dependencies remain optional extras.

The [public CLI/package tests](../tests/test_people_public_cli.py) cover public
registration, current/history/preview/no-op/replay, scheduling v4, roster paging,
legacy selectors/compact output, exact manifest pins and missing/corrupt assets
or required response declarations. The [HTTP tests](../tests/test_people_http.py)
exercise all eight real Flask routes, trusted identity/Host/Origin/headers, closed
errors and envelopes, history and filtering. They verify serialized-result and
request-global deadline failures roll back protected mutations before commit,
and compare decoded inner CLI/HTTP result objects rather than transport whitespace.
The HTTP timer includes parsing, normalization, encoding and release fences.

The [capacity matrix](../tests/test_people_read_capacity.py) verifies exact 100/101
all-role limits (including inactive/unmanaged rows), 1,000/1,001 candidate and roster
sentinels, bounded indexed owner/group/grant/role queries, one request budget across
both snapshots, optional disclosure fallback versus hard limits, and filtering
before expansion/page selection without subject existence probes. A candidate
allowance does not promise every allowed candidate can be fully expanded: the
separate resource/VM/deadline limits still apply and refuse rather than truncate.
Measured sparse four-root work is 25,800 VM steps/four resources; dense sixteen-root
work is 44,800/sixteen. Adding 3,000 hidden roots and 3,000 unrelated grants leaves
the latter cost, decoded output and cursor unchanged. These are bounded matrices,
not a general production-load or resilience qualification.

All four package synchronization checks pass. Frozen web, rendering and
revision-readback bundle bytes are unchanged. The new people package contains
39 JSON assets including the complete 36-schema closure. Its compiled pin-manifest
SHA-256 is
`739c10fe26b17e0c684c2b37a36e655138a90e548a1758d098911c9795210d76`.
All PR-01–16 obligations above now have bounded runtime evidence, without treating
offline fixture/model witnesses as runtime proof.

#### Installed artifact

A prepared temporary build environment produced a noneditable
`spine_ledger-0.11.0-py3-none-any.whl` with SHA-256
`9be0c0b5411d8851ad7fc785ef2747899c587e562ee026e406ad628c054e6a96`.
A separate fresh runtime installed that wheel, declared web dependencies and the
cached exact Tickerd 0.2.0 wheel. `pip check` passes; the runtime capability/descriptor
pin is verified. No package was published. Temporary build directories are not
durable externally available release artifacts.

[Installed verifier](../scripts/verify_people_wheel.py) runs with isolated Python,
no `PYTHONPATH`, and an installed-path assertion outside the checkout. Only public
CLI provisioning/commands and actual Flask routes operate on synthetic temporary
ledgers. It verifies history/no-op/replay/dry-run, schedule v4, `pc1` roster/occurrence
pagination, all eight HTTP routes, frozen interfaces and explicit deep verification.
It returns `PASS`, version `0.11.0`, schema `19`, 36 packaged schema documents and
`real_sends=0`. No HTTP listener or delivery processor is started.

```sh
env -u PYTHONPATH /tmp/spine-people-release.ZPVOz8/runtime/bin/python -I \
  /Users/Shared/Agent-Workspace/repos/personal/cortext1/spine/scripts/verify_people_wheel.py
```

#### Final verification and handoff

Final full discovery passes **1,263 tests, one skipped (260.364 seconds)**. The
existing revision-readback wheel test skips because the repository interpreter
lacks setuptools; that test is not claimed as executed. The separately prepared
installed-artifact check above supplies actual installed public-family evidence.
The earlier full run had only two stale runtime-0.10.0 assertions, corrected before
the final run. The final selected public/contract/documentation group passes
**67 tests (39.635 seconds)**. Focused Ruff, strict typing of six people runtime
owners, all four synchronization checks, 371 local documentation link targets and
diff hygiene pass. A final documentation/declaration/scaffold check passes 12 tests
(0.252 seconds). No project-wide strict-typing claim is made.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python \
  -m unittest discover -s tests -q
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/sync_people_contracts.py --check
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/sync_web_contracts.py --check
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/sync_rendering_contracts.py --check
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/sync_revision_readback_contracts.py --check
```

The [operator leaf](PEOPLE_COMMANDS.md) covers exact commands, managed replacement,
disclosure and paging, keeping access, participation, assignment and routing
separate. Local roster discovery needs protected `SPINE_PEOPLE_CURSOR_CONFIG`;
web startup explicitly takes `--people-cursor-config`. Bad/missing web cursor
configuration disables all v3 operations while valid v1/v2 remain usable. Packaged
contract corruption is a separate fail-closed application-construction error.
No secret, config path or identity override belongs in request JSON.

This closes local implementation acceptance, not deployment, staging/UI/Packs
adoption or permission to send. Slice 4 remains uncommitted; the unrelated
pre-existing `AGENTS.md` amendment is preserved. No Whetstone review, operator ledger,
migration, external send, commit, push or deployment occurred.

The operator subsequently authorized the focused Slice 4 local checkpoint on
2026-10-24. The unrelated `AGENTS.md` amendment remains excluded. This checkpoint
does not authorize a push, deployment, operator-ledger operation or consumer adoption.

Checkpoint revalidation: 58 selected public CLI/HTTP, read-capacity, contract and
scaffold tests pass (38.403 seconds). All four package synchronization checks,
focused Ruff, strict typing of the six existing people authoring owners and
staged diff hygiene pass. This is a focused rerun, not a new full-suite or
installed-wheel qualification run; the recorded complete results above remain
the basis for those claims.

After this private checkpoint, Slice 2 is scoped discovery, protected reference
admission, shared label disclosure, filtering and cursors. It must supply actual
protected permission/release evidence; the local-only implementation cannot substitute
for it. Slice 3 retains the full work-state/race matrix and Slice 4 public/installed
activation. No external audit, operator ledger, notification send, migration,
deployment or push is part of S1d.

### Slice 2 foundation verification (2026-10-24)

The initial people-focused run passes **126 tests (16.361 seconds)**. The broader
full regression run passes **1,167 tests, one skipped (202.126 seconds)**. After two
additional key-rotation/actor guards and final defensive refinements, the focused
directory/cursor/protected service, existing people command/writer and facet-writer
run passes **69 tests (29.042 seconds)**. Focused Ruff, strict typing of six runtime
owners, local documentation link validation and diff hygiene pass. No broader
project-wide strict typing or installed public-family acceptance is claimed.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest \
  test_people_directory test_people_cursors test_people_web \
  test_people_commands test_people_writer_parity test_facet_writers -q
.venv/bin/python -m mypy --strict --follow-imports=silent \
  src/spine/commands/people_candidate.py src/spine/commands/people_runtime.py \
  src/spine/services/people_directory.py src/spine/services/people_reads.py \
  src/spine/ledger/people_authoring.py src/spine/services/people_authoring.py
```

At that foundation verification, all changes were uncommitted. The foundation was
subsequently checkpointed as `c937661`, excluding the pre-existing `AGENTS.md` edit;
its 69 focused tests passed again (28.962 seconds). No push occurred.

### Slice 2 integration verification (2026-10-24)

The selected cross-feature run passed **206 tests (79.066 seconds)**, including
frozen independent reads and rendering authoring. Full regression passed
**1,203 tests, one skipped (211.483 seconds)**. After the additional future
label-roster activation test and final structural typing refinements, the focused
integration run passed **35 tests (13.822 seconds)**. That final test proves the
original cursor expires at the relevant membership transition even without an
access-epoch change; it was added after full-suite discovery and is covered by the
final focused run rather than the recorded full-suite count.

Focused Ruff and diff hygiene pass. Strict typing of the six people runtime owners
listed above passes. The two new web orchestration modules pass a structural mypy
check allowing untyped definitions/calls/globals; a broader strict web/rendering
check is not clean, so no project-wide strict-typing claim is made.
The final documentation/declaration run passes **9 tests (0.251 seconds)**;
all **215 local link targets** in the three updated tracking documents resolve.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest \
  test_people_read_integration test_people_schedule_integration -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python \
  -m unittest discover -s tests -q
.venv/bin/python -m mypy --follow-imports=silent \
  --allow-untyped-defs --allow-untyped-calls --allow-untyped-globals \
  src/spine/web/people_read_service.py src/spine/web/people_schedule_service.py
```

Private scheduling/read integration was implemented and locally verified, not
publicly activated. It was subsequently committed as `1e5abf9` after 71 focused
tests passed (17.328 seconds), with lint and staged hygiene. The unrelated
`AGENTS.md` edit is preserved. No push occurred.

### Slice 3 work-state and race verification

The new [work-state tests](../tests/test_people_work_states.py) exercise real
private standalone/composite people commands, policy resolution, scheduler and
attempt owners across eligible, selected, in-progress/unstarted, retry, started,
succeeded, failed, cancelled and absent work. Selection-to-processing uses the
actual Tickerd adapter with a deterministic in-process no-send processor, not a
fabricated lease store or real sender. Exact work/attempt/rendering rows, retry
backoff/count, provider idempotency and immutable started replay are compared.
Same-intent sibling policies deliberately have different ordinary/definition
presentations, plus a disabled policy, before the people-only bijection is tested.

The new [freshness/race tests](../tests/test_people_continuity_races.py) use actual
independent SQLite connections to compete for the version writer and attempt-start
transaction. The loser has no partial version/receipt, and retry after the winner
commits is stale. A prepared rendering after an item-version change must be rebuilt;
its body can remain the same but input evidence changes. Already-started evidence
remains replay-only and exact.

Recurring work/provenance stays byte-identical through role/facet edges; real
recurrence changes invalidate old work independently. Item-level and selected-
occurrence `follow_source` tasks go stale after source people changes. Target
people edits do not refresh that source pin; explicit binding reconciliation can
refresh it without changing the due time or allocating another target version.
Snapshot bindings remain independent. Tests use disposable ledgers only, never
operator data or external sends.

The [protected release races](../tests/test_people_release_races.py) add real
second-connection item-grant revocation between read snapshots, grant expiry and
future activation at cursor deadlines without access-epoch writes, and roster
revocation ordered after the atomic people transaction. Loss of fresh edit/roster
eligibility still permits exact initiating replay with retained read; revoking
that read permission refuses replay. No weaker replay bypass or implicit roster
authority is added.

The **168-test** work/authoring/writer/rendering/temporal/worker owner run passes in
**30.921 seconds**. Full discovery passes **1,224 tests, one skipped (221.161
seconds)**. The final **86-test** people work/race/protected/read/scheduling/writer/
documentation/declaration group passes in **29.380 seconds**. That final group includes
the four permission-race cases added after full discovery began; these are not
included in the recorded full-suite count. There are **24 new Slice 3 regressions**
across the three new modules.

Focused Ruff, strict typing of six unchanged people runtime owners, all **223 local
link targets** and diff hygiene pass. No new runtime code was required: the selected
cases confirm the existing owners' behavior rather than masking a known defect.
No project-wide strict-typing or installed public-family claim is made. Remaining
cost/concurrency matrices and installed/frozen/public qualification are explicit
Slice 4 gates, not globally closed by this selected evidence. At verification,
Slice 3 was uncommitted; the existing `AGENTS.md` edit was preserved. No audit, push, migration, deployment,
operator-ledger access or external send occurred.

The operator subsequently authorized a focused Slice 3 checkpoint. All 24 new
work-state/continuity/release-race tests passed again in **7.442 seconds**, with
focused Ruff and diff hygiene. The checkpoint excludes `AGENTS.md`; no push or
Slice 4 implementation is part of this authorization.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest \
  test_people_work_states test_people_continuity_races test_people_release_races \
  test_people_read_integration test_people_schedule_integration test_people_web \
  test_people_writer_parity test_agent_documentation \
  test_implemented_contract_declarations -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python \
  -m unittest discover -s tests -q
```
