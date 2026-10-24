# People and responsibility — private runtime evidence

Updated: 2026-10-24. Slice 2 integration follows directory/standalone checkpoint `c937661`.

This is implementation evidence, not a specification or public capability declaration.
The [logical spec](../specs/people-and-responsibility.md) and
[machine companion](../contracts/people-and-responsibility.v1.json) remain authoritative.
The companion's `pending_runtime` obligations remain whole-feature gates; none is
globally closed by the partial evidence below. The accepted A/B/C review is not
reopened. Operator production is stable; this work does not touch it.

## Executed boundary

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

"Partial" means executable evidence for the named private/local portion, not
acceptance of the complete obligation. Test files below contain real-ledger tests;
the offline contract witnesses remain separate.

| Obligation | Current runtime evidence | Still required / owner |
| --- | --- | --- |
| PR-01 — independent dimensions | Partial: standalone and v4 role changes preserve adopted ownership, access state, memberships, routes, work and attempts; notification intents/recipients do not change. | Protected admission/noninterference and complete-family parity; Slices 2/4. |
| PR-02 — event/task sets | Private local/protected event and task authoring plus protected read integration: omission, replacement, clear, no-op, inactive facts, wrong-role refusal, unscheduled tasks and accountless subjects. | Complete installed parity/remaining matrix qualification; Slice 4. |
| PR-03 — atomic version/copy/rollback | Partial: local one-version composites/writer matrix plus private protected standalone/composite version/role/owner/audit/receipt/link rollback on failed release or owner persistence. | Complete concurrent-writer coverage and installed parity; Slices 3/4. |
| PR-04 — no-op/replay/preview/identity | Partial: local canonical receipts/real preview; private protected standalone/composite replay checks initiator and current disclosure, retains original IDs after newer versions/reference inactivity, and refuses after read revocation. | Complete preview/permission matrix and installed parity; Slice 4. |
| PR-05 — roster/fresh-reference privacy | Partial private evidence now includes protected scheduling-v4 owner admission, atomic owner/people creation and rollback in addition to standalone selection/retention/removal. | Complete cost/noninterference/race and installed qualification; Slices 3/4. |
| PR-06 — history/current labels | Partial private evidence: shared protected labels/history, closed nondisclosure, optional independent-read sections with SQL/byte/resource degradation, hidden-label noninterference and release checks. | Remaining concurrent/installed qualification; Slices 3/4. |
| PR-07 — authorized person filters | Private implementation: authority before exact current role filter, no person lookup, OR roles, inactive-subject active-row match, before-expansion nonmatch, unrelated-role edit/source exclusion, unavailable/unplaced cases. | Complete matrix and public/installed parity; Slice 4. |
| PR-08 — cursors/release races | Private roster/read successors: MAC vectors, source/query/identity/key/expiry, both occurrence bases, section/agenda paging, membership transitions without epoch write and fresh release checks. | Complete concurrent/timed-grant matrix and installed parity; Slices 3/4. |
| PR-09 — continuity/mixed edges | Partial: distinct role proof, exact immediate policy bijection, strict facet/presentation proofs, mixed histories, tampered/skipped-edge refusal and 100-version limit. | Full mixed lifecycle/ordinary-edit/lease race acceptance; Slice 3. |
| PR-10 — work states | Partial: actual queued/start/retry/terminal/attempt-history preservation and independently stale-route refusal. | Complete queued/leased/retry/started/terminal/absent cross-product and races; Slice 3. |
| PR-11 — recurring/relative freshness | Partial: recurring authoring, target binding retention and source-event people edits invalidating follow-source snapshots. | Full recurrence occurrence/provenance and relative-source race matrix; Slice 3. |
| PR-12 — bounded indexed reads | Partial: exact-version/roster/candidate sentinels, request-global SQL/time/byte/resource caps, actual indexed selection plans, hidden dense growth and optional SQL/byte/resource degradation while retaining core/time. | Remaining sparse/dense/grant plan/VM matrices and concurrency/installed qualification; Slices 3/4. |
| PR-13 — writers/finalizers | Local: all 25 inventoried producers exercised, exact role copy/replacement and historical rows checked, shared facet/rendering finalizer paths and failures tested. | Protected service writer parity, full work matrix and installed successor execution; Slices 3/4. |
| PR-14 — installed closure | Activation guard only: source contracts remain unadvertised. | Installed schema/registry synchronization, frozen bundle, package/capability declarations; Slice 4. |
| PR-15 — public equivalence | Not implemented; public dispatch intentionally rejects this candidate family. | CLI and protected HTTP successor parity; Slice 4. |
| PR-16 — concurrency | Partial: local CAS rollback, source/membership/identity changes between private protected evaluation and fresh release, failed in-transaction fresh-reference release rollback, read-successor label/role/source/selection fences. | Complete simultaneous writers, lease/temporal-source races and installed parity; Slices 3/4. |

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

Private scheduling/read integration is implemented and locally verified, not
publicly activated. It remains uncommitted; the unrelated `AGENTS.md` edit is
preserved. Slice 3 retains work/lease/mixed-lineage/temporal-source races and
remaining cost/concurrency qualification; Slice 4 retains installed/frozen/public
activation. No audit, push, migration, deployment, operator-ledger access or send
occurred.
