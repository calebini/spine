# Advisory Protection Amendment — Preservation Checklist

Status: Manual amendment comparison; independent reviewer audit not run

Date: 2026-09-13

Tracked task: SPINE-017. This explanatory checklist does not override specifications,
ratify Decision 0005, or advertise runtime support.

## Baseline and allowed change surface

Baseline commit: `706b499665add9e15a041f2c26dd20c2446f5139`.
The worktree was clean when the amendment began. The baseline already includes the
approved privacy and configurable-budget decisions in advisory Draft v0.3.1.
Use that commit's complete documents as the baseline, not an older audit copy.

The proposal adds Decision 0005, advisory §§3.1 and 7/15 clarification paragraphs,
architecture §9.1, and an ontology §9 preamble. Existing advisory body requirements,
architecture paragraphs, and ontology rules are retained verbatim and in order;
the advisory status line alone changes to Draft v0.3.2. Backlog, roadmap, and the
spec index receive explanatory tracking/cross-reference updates.

Source specification paths:

- `specs/contextual-advisories.md`
- `specs/architecture.md`
- `specs/ontology.md`
- `specs/decisions/0005-profile-scoped-advisory-execution.md` (new proposal)

Frozen outside this amendment: runtime code, machine schemas and fixtures, migrations,
package/contract versions, CLI/web registries, notification/rendering/profile semantics,
native governance documents, facet and people contracts, and unrelated backlog work.
No files in those families are authorized for alteration by this checklist.

## Requirement correspondence

Each row identifies retained authoritative text and the additive boundary that must
not weaken it. “Retained” is the author's comparison result, not a Whetstone verdict.
Sections refer to `contextual-advisories.md` unless another document is named.

| ID | Protected obligation | Baseline and candidate location | Amendment interaction / manual result |
| --- | --- | --- | --- |
| P-01 | Event-only, local-instant start, canonical location, one notification activation | §4 | Retained; new §3.1 and Decision 0005 §1 explicitly prohibit bypass or optionalization |
| P-02 | Bounded read-only initiative; no writes, contacts, child workflows or multi-agent delegation | §§3–4 | Retained; future cases require separate contracts and are not new v1 modes |
| P-03 | A trigger/request grants no authority; capabilities cannot expand | §3 invariants 2–3; §7.2 | Retained; conceptual separation does not grant execution |
| P-04 | Ordinary fallback on failure or unavailable enrichment, subject to independent eligibility | §§8.1, 9, 11 | Retained; result-consumer separation does not make fallback depend on acceptance |
| P-05 | Accepted no_action defaults to fallback; silence requires explicit bound permission | §3 invariant 10; §8.1 | Retained; no new output or silence interpretation |
| P-06 | Shared delivery identity; no late alternate send; attempt-start branch freeze | §§4.1, 8.1, 10 | Retained; distinct future process identity cannot reopen this notification |
| P-07 | Pre-attempt stale accepted content can downgrade only to independently eligible fallback | §8.1 | Retained, including serialization and explicit recovery gate |
| P-08 | Failed materialization needs explicit recovery, not model rerun or automatic branch switch | §8.2 | Retained; native mapping addition expressly keeps recovery separate from redispatch |
| P-09 | Unsupported approval is terminal with no dispatch, automatic retry, or silent resumption | §7.2 | Retained; external future workflow waits do not resume this profile |
| P-10 | Accepted clarification uses the same policy-bound delivery target/profile | §8 | Retained; no new destination authority |
| P-11 | Minimized disclosure, explicit extra-detail permission, medical opt-in, no automatic taxonomy | §6.3 | Retained; scope/dependency distinctions do not infer wider access |
| P-12 | Finite configurable per-definition limits, snapshot-stable defaults, firm cutoff | §§4.1–4.2, 6.1, 7.2 | Retained; runtime/attempt accounting must map these limits rather than replace them |
| P-13 | Immutable submission replay, native hashes/identities, no duplicate intelligence on replay | §§7, 9–10 | Retained; added correlation boundary forbids a second native governance schema |
| P-14 | Freshness at dispatch, consumption and delivery; capture time alone is not source staleness | §§6.3, 7.5, 9 | Retained; future multi-source freshness requires its own contract |
| P-15 | Distinct Spine persistence, governance acceptance, runtime reasoning, and delivery authority | §§2–3, 5, 7; architecture §§4–6 | Retained; future workflow coordination does not acquire any of these authorities |
| P-16 | Existing item/version FKs, enums, work freshness, attempt origins and pre-effect evidence | ontology §§9.1–9.3 | Retained; new §9 preamble explicitly keeps all constraints; no generic work row introduced |
| P-17 | Evidence, failure, selection, materialization, attempts and delivery remain distinguishable | §§11–12 | Retained; native/external lifecycle distinction reinforces rather than collapses readback |
| P-18 | Real usefulness experiment and deterministic tests are distinct; no implementation claim | §§13–15 | Retained; future-case walkthroughs are not substituted for runtime proof |
| P-19 | Exact native mapping, schemas, fixtures, privacy enforcement and race details remain gates | §§7, 15 | Retained; amendment constrains their resolution but does not declare them settled |
| P-20 | Existing facets, permission semantics and deferred work remain outside this patch | Decision 0004; permissions; backlog deferred entries | Unchanged; references do not select those initiatives or grant new powers |

## Extension review objectives

| ID | Question for the later bounded review | Candidate evidence / expected boundary |
| --- | --- | --- |
| E-01 | Can a future task-research contract avoid a fabricated event, location or notification while advisory v1 still rejects it? | Decision 0005 §§1–2; advisory §3.1 and §7 additions |
| E-02 | Are owning item, permission scope and source dependencies distinguishable, including a future empty/multi-item sweep? | Decision 0005 §3; ontology §9 preamble; no current FK relaxation |
| E-03 | Can a future external workflow wait for approval without extending a reminder deadline or resuming stopped advisory work? | Decision 0005 §§3–4; advisory §7.2 and §8 unchanged |
| E-04 | Are native dispatch/run/attempt identity, effect accounting, budget ownership and retry authority explicitly left for exact mapping rather than duplicated? | Decision 0005 §4; advisory §7 and §15 additions |
| E-05 | Does accepted evidence remain distinct from permission to deliver or mutate? | Decision 0005 §2; advisory §§7.5–8 and current attempt gates retained |
| E-06 | Does the amendment leave all three future cases unsupported rather than implementing general automation by indirection? | Decision 0005 preservation boundary; unchanged runtime/contracts/registries |

## Local verification and audit limit

Verify original lines remain in order in the three amended source specs, except the
declared advisory status-line update. This is a mechanical loss check, not a proof
that additions cannot contradict or weaken retained text. Independently inspect the
additions against P-01–P-20 and E-01–E-06, check local links, run relevant documentation
and contract-declaration tests, and record completion in SPINE-017.

A later approved reviewer run should receive the exact baseline, candidate files,
this checklist, and any necessary references. Require explicit assessment of the
objectives if the configured Whetstone version supports it; do not invent unsupported
fields or infer coverage from an empty findings list. No nested audit has been run
for this amendment. Existing audit verdicts are not evidence for these new additions.
