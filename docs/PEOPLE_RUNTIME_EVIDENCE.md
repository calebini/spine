# People and responsibility — private Slice 1 evidence

Updated: 2026-10-24. S1d follows S1c checkpoint `d050ca3`.

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
full-ledger policy, not protected owner-scope admission. Protected reference and
replay permissions, directory label disclosure, admission/release fences and
public successor routing are still required before activation.

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
| PR-02 — event/task sets | Local foundation: omission, replacement, clear, multiple roles, inactive facts, wrong-role refusal, unscheduled tasks, active agents and accountless people. | Admitted protected create/update/read parity; Slices 2/4. |
| PR-03 — atomic version/copy/rollback | Local: one-version composites; all-role identity/copy matrix; policy/audit/receipt/finalizer failures and CAS/FK rollback. | Protected service's outer admission/release transaction and actual races; Slices 2/4. |
| PR-04 — no-op/replay/preview/identity | Local: exact canonical vectors, original no-op IDs, changed replay after later edits, no readmission, conflict/corrupt evidence refusal, real preview rollback and deterministic IDs. | Same initiating account/subject and current receipt/item disclosure, permission changes and installed parity; Slices 2/4. |
| PR-05 — roster/fresh-reference privacy | Only local active-ID admission and mandatory fresh-add callback are implemented. | Owner-scope eligibility, scoped directory authority, hidden-reference indistinguishability and access checks inside the write; Slice 2. |
| PR-06 — history/current labels | Local: exact old associations and current catalog metadata; labels never enter receipts. | Shared protected self/roster label resolver, closed nondisclosure, current permission/release fences; Slice 2. |
| PR-07 — authorized person filters | Not implemented. | Authorize before filter/expansion, hidden-row noninterference, unavailable/unplaced cases; Slice 2. |
| PR-08 — cursors/release races | Not implemented. | MAC-bound source/access snapshots, stale cursors, identity/access/source release races; Slice 2. |
| PR-09 — continuity/mixed edges | Partial: distinct role proof, exact immediate policy bijection, strict facet/presentation proofs, mixed histories, tampered/skipped-edge refusal and 100-version limit. | Full mixed lifecycle/ordinary-edit/lease race acceptance; Slice 3. |
| PR-10 — work states | Partial: actual queued/start/retry/terminal/attempt-history preservation and independently stale-route refusal. | Complete queued/leased/retry/started/terminal/absent cross-product and races; Slice 3. |
| PR-11 — recurring/relative freshness | Partial: recurring authoring, target binding retention and source-event people edits invalidating follow-source snapshots. | Full recurrence occurrence/provenance and relative-source race matrix; Slice 3. |
| PR-12 — bounded indexed reads | Partial: exact-version over-limit sentinel, 100 total role-row cap and no truncated people set. | Full roster/filter plans, sparse/dense/hidden EXPLAIN/VM/byte/resource budgets and release checks; Slice 2. |
| PR-13 — writers/finalizers | Local: all 25 inventoried producers exercised, exact role copy/replacement and historical rows checked, shared facet/rendering finalizer paths and failures tested. | Protected service writer parity, full work matrix and installed successor execution; Slices 3/4. |
| PR-14 — installed closure | Activation guard only: source contracts remain unadvertised. | Installed schema/registry synchronization, frozen bundle, package/capability declarations; Slice 4. |
| PR-15 — public equivalence | Not implemented; public dispatch intentionally rejects this candidate family. | CLI and protected HTTP successor parity; Slice 4. |
| PR-16 — concurrency | Partial: local CAS-loss rollback and freshness/proof failure cases. | Actual writer, identity/access, roster, lease and temporal-source concurrent races; Slices 2–4. |

Primary evidence:

- [Core normalization tests](../tests/test_people_core.py): normalization, set/hash and replacement identity.
- [Exact-version tests](../tests/test_people_ledger.py): bounded current/history projection and terminal reads.
- [Private authoring tests](../tests/test_people_authoring.py): transaction rollback and shared continuity/freshness.
- [Actual command tests](../tests/test_people_commands.py): standalone/v4 receipts, preview, identity and independence.
- [Writer parity tests](../tests/test_people_writer_parity.py): actual inventory and copy/replacement verification.

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
