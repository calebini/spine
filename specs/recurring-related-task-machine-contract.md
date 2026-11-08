# Recurring Related Tasks: Machine Companion

Status: Draft v0.1.0-draft.2 — source-only codification; not ratified or implemented

Date: 2026-11-08

## 1. Authority and activation

The [logical leaf](recurring-related-tasks.md), [storage/identity leaf](recurring-related-task-storage.md)
and [command leaf](recurring-related-task-commands.md) retain their authorities.
This companion binds their closed machine representations, offline reference
closure and computed corpus. It does not add another task model or execution
engine. D-01–05, explicit subject/group child ownership, source proof, no-op
suppression and existing notification/attempt rules remain unchanged.

The proposed capability manifest is
[recurring-related-tasks.v1.json](../contracts/recurring-related-tasks.v1.json).
It declares exact proposed versions, seven local commands, request/response paths,
prerequisites, bounds, identity conventions and pending runtime obligations.
It is **not** the compiled runtime registry. No handler, HTTP allowlist, installed
schema closure, package version or ledger schema is activated by this corpus.

The [fixture manifest](../contracts/recurring-related-task-fixture-manifest.json)
separates valid/invalid wire fixtures, computed hash/cursor vectors and pure
decision witnesses. Evidence examples include mutually exclusive branches,
explicitly labelled as alternatives rather than one consistent ledger snapshot.
Every runtime obligation remains pending. A passing offline
test cannot prove actual SQL transactions, locking, attempt races, migration or
worker behavior; those remain implementation acceptance requirements.

## 2. Representation closure

Schemas use Draft 2020-12, closed objects and offline resolvable `$id`/`$ref`
resources. Root IDs are under
`https://cortext.local/spine/contracts/schemas/recurring-related-tasks/`.
Inherited definitions stay in their existing owners; their wire shapes and hashes
are not rewritten. The explicit schema-closure manifest records exact source
files/hashes, including transitive dependencies; resolution must never fetch them
over the network. The new nested source directory is not copied into the frozen
web package or advertised through runtime declarations.

Integer strings are bounded to signed-64-bit nonnegative/positive domains or the
narrower declared cap. Signed offsets exclude `-0`, plus signs, leading zeros,
newlines and exponents. UTC strings require whole seconds and `Z`; calendar/date
validity is checked in addition to syntax. Canonical JSON rejects numbers,
duplicate object keys and invalid surrogates; allowed strings are not normalized.
JSON booleans remain booleans. Object field order is immaterial to canonical
hashes; meaningful array order is retained. Schema default annotations do not
perform normalization: the normalizer must explicitly materialize those values.
The delegated `occurrence_key` is not a bare digest: retain its exact
recurrence-owned unpadded base64url canonical-preimage payload, dot and lowercase
hex digest. The digest remains a separate computed-vector field. Decoding and
independent canonical-byte/digest comparison are required offline checks.

The following names close descriptive facts already required by the prose:

- Rule readback includes `source_snapshot` with current source item/version,
  recurrence set/revision/hash, so clients can form exact expected facts. It is
  not a source mutation or a read-time assignment repair.
- Reads and fresh dry-run previews require top-level
  `commit_cutoff_recheck_required=true`. Committed successes omit it. Compatible
  stored replay keeps the original result rather than fabricating a new preview.
- Reconcile `result.future_generation` is required alongside the four coverage
  objects. It describes eligible/waiting/exhausted/retired/blocked state, not a
  promise of additional selected rows; `has_more` retains its page-selection meaning.
- Selection is `{evaluation_at_utc,execution_at_utc,limits,lane_start,lane_end,
  intent_id,assignment_high_water}`. The last two are both null when no intent is
  selected. A lane position is `{assignment_after_seq,source_after}`; source-after
  is null or `{scheduled_fact,selector}`. Compare selector canonical UTF-8 bytes
  for its total-order tie-breaker, not JSON display order or an occurrence ordinal.
- Assignment readback separates its stored witness from current observations:
  `task_status`, `freshness`, `observed_source_item_version`,
  `observed_recurrence_revision_id`, `observed_task_item_version`, and nullable
  `source_cancellation`. The latter is the exact latest generation's source-only
  cancellation record, not inferred from task status.
- A normal page entry's before/after uses closed child/version/binding/adoption/
  ownership references. An ambiguous before may instead contain exactly
  `conflicting_assignment_ids` and `conflicting_occurrence_keys`; after never
  substitutes such a conflict object for a resolved child. This conveys the
  already-required conflicting references without fabricating a successor.
- State/generation/proof row reads retain their storage column names. `*_json`
  payload columns are decoded objects, not nested JSON strings. SQL-null optional
  record columns project explicit null; optional fields inside canonical hash
  payloads remain omitted unless that payload explicitly permits null.

## 3. Configuration and evidence projections

Initial input may omit `generation_horizon_seconds`; normalization stores
`4838400`. Complete update configuration requires the concrete value. Limits
default individually and normalize to the complete seven-field limits object.
Read page limit defaults to `50`, status to `active`, show view to `rule`.
Raw assignee inputs may repeat IDs within the 100-entry input cap; stored
configuration uses the sorted unique set. The distinct raw and normalized schemas
must not reject an input whose duplication the contract promises to normalize.
Absent list owner/source filters normalize to explicit null **in query facts**,
not to inferred group/sender ownership. Null remains invalid where authoring
requires an object or a missing optional. Exactly one owner FK matches its kind.

Normalized task optional summary/source-ref/location/archetype/priority become
the declared nulls; any archetype selection is pinned to an exact revision before
storage. Effective templates retain closed template fields `template_key`,
`schedule`, `late_handling`, `rendering` (ordinary explicitly materialized when
defaulted), plus separate resolved presentation evidence in the effective entry.
They are not complete task-specific profile application rows and do not include
future policy IDs. `policy_key` is derived by the reviewed existing composition
rule. Unknown/colliding keys fail rather than being renamed. No live catalog
pointer can mutate a stored configuration.

The state `managed_baseline` contains exactly normalized `task_template`,
`offset_basis`, `offset_seconds`, `notification_plan`, `delivery`, `materialization`.
The immutable child owner and rule-only horizon are not three-way adoption fields.
The comparison algorithm still operates on each declared managed field, treating
the complete reminder/delivery/presentation set atomically.

Proof records carry `proof_kind` separately from canonical `proof_json`. Its
payload has the common source snapshot, selector/key and sorted unique
`lineage_ids`, subject to storage Section 4's source-wide exception:

| Kind | Kind-specific payload facts |
| --- | --- |
| enrollment | `enrolled_recurrence_revision_id` |
| identity | Optional paired `prior_proof_id`, `prior_selector` |
| carry_forward | Required prior pair and nonempty chronological `hops` |
| component_candidate | `basis_revision_id`, `component_selector`, `hops` |
| new_rdate | `rdate_id`, `prior_recurrence_revision_id` |
| excluded | Prior pair, `exdate_id`, `exclusion_active=true`, `actionable=false` |
| occurrence_cancelled | Prior pair, `override_id`, `lifecycle=cancelled`, `actionable=false` |
| source_cancelled | No selector/key; empty lineage, `cancelled_event_version`, `event_status=cancelled` |

`component_selector` is `{source_kind:rule|rdate,selector}` with the corresponding
closed recurrence rule/rdate semantic selector. Hop shape is the storage leaf's
five-field object. These are immutable evidence facts produced and checked by
Spine, never caller-supplied cancellation/remapping authority. Shape acceptance
does not prove referenced lineage exists or justifies one-to-one correspondence.

## 4. Cursor and semantic checks

Cursor purpose selects a closed payload/query/after union. Normalized query
contains `contract_version`, `ledger_instance_id`, then exactly its command's
selection fields: list filters/limit; show view/root/assignment when applicable;
or reconcile root/complete limits. Exclude cursor, actor, command ID/time and
expected facts. Reconcile payload carries exact rule/source snapshot, evaluation
and range endpoints; optional `intent_id`/`assignment_high_water` appear together.
Post-commit freshness replaces the old counters, not original evaluation/expiry.

HMAC input is the exact UTF-8 purpose domain plus NUL plus canonical payload bytes.
Wire is unpadded base64url payload, dot, unpadded base64url tag. Expiry is exactly
3600 elapsed seconds; equality is expired. Verification checks tag/canonical
encoding/query/ledger/purpose before freshness/expiry classification. Test key
material is public fixture data, never deployment configuration or an authority
token; the corpus does not choose a new operational secret-management system.

Schema acceptance is only one gate. Contract tests separately check canonical
preimages/digests, recursive closed references, exact error/effect declarations,
sorted/disjoint results, reference equality, nullable/omitted distinctions, source
proof variants and model decision boundaries. They include negative mutations
which remain schema-shaped but violate semantic invariants. No request bypasses
current versions, authority, transaction checks or the future-due commit cutoff.

## 5. Verification and next gate

The offline fixture builder is deterministic, has no clock/network/ledger/send
dependency, and emits an artifact bundle rather than editing sources. Its check
mode compares the retained corpus with recomputation. Independent tests recompute
canonical bytes, digests and HMACs and validate model expectations. Existing pure
notification identity functions are delegated, not replaced by a second ledger
implementation. Published immutable inputs and complete expected output facts
make the examples reproducible rather than assertions about deployed state.

Review this machine corpus before ratification/implementation planning. Runtime
advertisement requires the pending obligations to be implemented and verified
against actual constraints, transactions, concurrent writes, migration and
attempt-start admission. No source-only schema or passing witness waives that gate.

## 6. Bounded independent witness scope

The fixture manifest additionally names complete offline `source-proofs.json`
and `composed-policies.json` corpora. Source snapshots retain the existing
normalizers' full values and exact set/revision/hash/child preimages. Successor
ancestry is checked independently alongside the delegated value-schema
projection, without changing that existing schema. Lineage retains exact identity
preimages/payloads, explicit component-copy maps, COUNT subtraction and one-to-one
retarget facts; positive rdate novelty must exclude prior included/reserved or
unresolved slots. The finite WEEKLY witness checker rejects unsupported fixture
shapes and caps candidate generation at 64 steps; it is not an arbitrary-recurrence
resolver or a substitute for actual provenance/transaction admission.

The source corpus includes valid normalized successors with deliberately
insufficient copy claims. Tests must reject changed seed/phase or unproved union
contributors even when a lineage row's own hash is correct. Missing lineage,
wrong COUNT subtraction, duplicate retargets and alias-blocked novelty have
independent negative checks. Timezone facts are explicit synthetic inputs; these
original-schedule membership witnesses do not qualify a timezone provider.

The composition corpus retains a profile plus custom reminder, reordered inputs,
replacement/copy-forward, complete mappings and every delegated identity
preimage. Existing intent-creation preimages remain unchanged on copy rather than
inventing an empty preimage. The three-way adoption oracle checks D=B first,
preserving C even when it is an individual exception.

Cursor cases retain exact wire bytes, public test keys, expected request/freshness
context and expected `invalid_request`/`stale_cursor`/`stale_version` precedence.
They include noncanonical/duplicate JSON, bad tags, unknown keys, cross-purpose/
ledger/query/limit mismatches, overflow, invalid Unicode, expiry equality and
combined cursor/expected-fact failures. No cursor test creates a service endpoint
or authorizes a write. Read watermarks and blocked-child policy mappings are
checked against concrete creation evidence; selected-but-unresolved units may
advance selection without falsely certifying resolution or durable no-op change.
