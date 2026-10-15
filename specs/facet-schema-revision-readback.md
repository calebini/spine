# Facet Schema Revision Readback

Status: Ratified v1.0.0 — implemented trusted-local in runtime 0.10.0/schema 19
Created: 2026-10-13
Ratified: 2026-10-15, by explicit operator authorization after bounded review and manual minor correction
Wire contract: `spine.facet-schema-revision-readback.v1`
Baseline inspected: `57cda1c2d5589360ee8efe7155fd20b503034c2a`, runtime 0.9.1/schema 19

## 1. Purpose and authority

Add one read-only public command, `facet_schema.revision.show`, to resolve an exact
facet-schema revision ID to its owning root and complete immutable definition.
This closes the historical-pin observation gap for clients such as Spine Packs:
bindings and rendering selections carry revision IDs, while existing
`facet_schema.show` requires a root ID that current catalog pointers cannot recover.

[Archetype facets](archetype-facets.md) remains the logical owner of schema identity,
definitions, lifecycle and permissions. [Facet storage](archetype-facet-storage.md)
remains the physical owner; [Storage atomicity](STORAGE_ATOMICITY_SPEC.md) owns
Spine-wide persistence. This leaf owns only the additive lookup contract. The
[agent command contract](agent-command-contract.md) owns transport and preflight.

The machine companion is
[facet-schema-revision-readback.v1.json](../contracts/facet-schema-revision-readback.v1.json).
Its separate registry does not extend the existing facet or HTTP registries.
Ratification does not itself advertise the command, add a migration, grant access,
or qualify a runtime. Runtime activation requires the acceptance proof below.

## 2. Scope and rationale

The command is **trusted-local only** for this slice. It has no HTTP/MCP route or
permission-enforced admission path. Existing trusted-local full-scope privileges
are unchanged; transport reachability is not verified human identity.

Use a revision-addressed lookup instead of:

- Guessing a root from a pack key, facet key, ID spelling or current revision pointer.
- Scanning revision history or searching every root through rejected show requests.
- Adding derived root IDs to multiple existing closed binding/rendering wire shapes.

The latter would require several successor projections and careful separation from
hash-bearing rendering content. One indexed lookup serves all revision-pin consumers
without changing their existing formats. The old root-addressed show remains useful
for current selection and explicit root/revision membership checks.

Non-goals: catalog history enumeration, batch lookup, owner discovery, schema
publication, item values, reference dereferencing, disclosure, work or delivery,
executor authentication, and a new authorization or catalog-sharing model.

## 3. Request and transport

Canonical command: `facet_schema.revision.show`.
Local CLI spelling: `spine-command --db <ledger> --input - facet_schema revision show`.

```json
{
  "contract_version": "spine.facet-schema-revision-readback.v1",
  "facet_schema_revision_id": "<exact-revision-id>"
}
```

The request is a closed object with exactly those two required fields. Revision IDs
are opaque nonempty strings using the existing facet ID domain: preserve bytes,
reject invalid Unicode, and never infer or normalize an identity. There is no root
ID, owner filter, current-revision default, command ID, actor, timestamp, cursor,
limit, destination or approval input. Missing fields, extra fields and invalid types
fail; no fallback to another command or revision is allowed.

CLI `--dry-run` remains a context flag, not a request field. This command is already
read-only; if the context flag is set, the returned envelope adds only `dry_run=true`.
Omitted dry_run is the normal projection; false is not a valid emitted marker.

The request schema is
[facet-schema-revision-show-request.schema.json](../contracts/schemas/facet-schema-revision-show-request.schema.json).
Runtime 0.10.0 registers this as a read-only trusted-local command. Older inspected
runtimes do not implement it; clients must adopt an exact implemented release pin.

## 4. Resolution, success and history

After normal bounded runtime preflight and request validation, a successful operation
MUST resolve the exact revision by its primary key, obtain its stored root ID, load
that root and decode the selected definition using the **stored** definition and
canonical-JSON version markers. Root/revision identity, definition bytes/hash and
derived declaration parity must satisfy the existing facet-storage invariants.
Do not synthesize a missing root, rewrite history or decode it through a newer schema.

Read all result facts in one read-only SQLite transaction. Return a complete result
or a structured failure, never partial root/definition evidence. No writes, audit
entries, receipts, replay records, durable no-op summaries or item-version changes
are permitted. Repeated reads need no idempotency key.

Success has exactly the normal `ok`, `command`, `response_contract`, `root`, and
`revision` fields, plus optional `dry_run=true`. The result tag is
`spine.facet-schema-revision-readback.v1`. Reuse the existing facet v1 representations:

| Field | Meaning |
| --- | --- |
| root.facet_schema_id | Actual root of the selected revision, not a desired pack root |
| root.owner / schema_key | Immutable catalog owner and owner-local key |
| root.current_revision_id / status | Current root metadata at the read snapshot |
| revision.facet_schema_id | MUST equal root.facet_schema_id |
| revision.facet_schema_revision_id | MUST equal the requested ID |
| revision.revision_number | Original positive decimal-string ordinal |
| revision.definition / definition_hash | Complete normalized stored definition and original verified hash |

The success schema is
[facet-schema-revision-show-response.schema.json](../contracts/schemas/facet-schema-revision-show-response.schema.json).
JSON Schema cannot prove cross-field identity, persistence, hash correctness or
authorization. Those are semantic obligations with separate model/runtime proofs.

Historical lookup does not require the selected revision to be current or its root
to be active. Retired roots remain readable in trusted-local mode. Retirement does
not erase revisions or revive fresh schema use. Reading an old B1 when B's current
pointer is B2 returns B1's unchanged definition and B's current root metadata.

Concurrent publish/retire can change subsequent root metadata, but never B1's root
membership, definition, hash or revision number. A successful snapshot may precede
a later catalog change; this command is not a whole-catalog consistency token.
Clients still obey their multi-read plan/source revalidation and concurrency rules.

Definition reference declarations are metadata only. Do not dereference subjects,
locations, items or external services; no facet values or delivery authorization
are returned. Clients compare the actual returned owner/root with their approved
installation scope and desired graph, rather than coercing foreign pins into it.

## 5. Failure contract and precedence

Keep normal database/runtime preflight before handler execution. Handler ordering is
closed request shape, exact selector, ID validity, exact revision resolution,
root/invariant/definition validation, then complete result release. Capacity checks
may fail any stage; never reset budgets or retry through alternative roots.

For a parsed request object, shape validation MUST report exactly one error in
this order, independent of JSON member order or a validator's error iteration:

1. If any key is not an allowed request field, return `unsupported_field` for
   the lexicographically smallest extra field, **before** checking missing fields.
2. Otherwise, if a required key is absent, return `missing_required_field` for
   the lexicographically smallest missing field.
3. Only after both shape checks pass, check the exact `contract_version`, then
   the validity of `facet_schema_revision_id`, then perform revision resolution.

Field-name comparison is case-sensitive Unicode code-point lexicographic order;
do not normalize, case-fold or use locale ordering. Presence means key existence,
even if the value is null or the wrong type. Thus `{}` reports missing
`contract_version`; `{unexpected:null}` reports unsupported `unexpected`, not a
missing field. A missing revision key wins over an invalid selector, while an
invalid selector wins over an invalid revision ID when both keys are present.
These are command error-selection rules, not JSON Schema keyword-order semantics.

| Condition | error.code | error.field | CLI exit |
| --- | --- | --- | --- |
| Required request field absent | missing_required_field | Missing field | 2 |
| Extra request field | unsupported_field | Extra field | 2 |
| Selector not exactly supported | unsupported_contract_version | contract_version | 2 |
| Empty/non-string/invalid-Unicode revision ID | invalid_request | facet_schema_revision_id | 2 |
| Exact revision absent | referenced_row_not_found | facet_schema_revision_id | 4 |
| Broken root membership, missing stored root, corrupt hash/definition/declaration parity or unsupported historical decoder | environment_failure | facets | 7 |
| Resource, SQL-step, wall-clock, lock or handler byte budget exhausted | environment_failure | capacity | 7 |

Malformed transport JSON and routine preflight failures retain the existing owning
contracts; this leaf does not reclassify them as an absent revision. The
[failure schema](../contracts/schemas/facet-schema-revision-show-failure.schema.json)
covers normalized command handler outcomes, not all transport diagnostics.

Failure messages are safe explanatory prose, not byte-exact constants. Do not echo
revision/root IDs, owners or definition content in errors. No missing-revision
failure proves that a whole catalog lacks a desired schema. Capacity/corruption/
preflight failures are never not-found evidence. Existing `facet_schema.show`
membership-mismatch failures and missing/inaccessible protections stay unchanged.

## 6. Bounds and authority boundary

Reuse the existing facet-family ceilings in one shared per-operation budget:
1 MiB request, 4 MiB successful response, 32 KiB canonical definition, at most 32
field declarations, 100 distinct resolved resources, 100,000 SQLite VM steps and
5 seconds wall-clock. SQL lock waiting consumes that same time budget. Reject
over-budget work without partial output or durable records.

Use existing revision/root primary-key indexes and bounded declaration verification
(the existing LIMIT 33 parity check). Do not enumerate roots/revisions, scan JSON,
inspect ledger-wide invariants or run integrity/foreign-key/quick checks at startup.
No cursor configuration or pagination key is required for this non-paginated read.

Trusted-local access remains deliberately full scope. This leaf introduces no
request-authored subject and no protected API authorization claim. A future protected
exposure MUST explicitly register the command and resolve current `catalog.read`
(or read implied by `catalog.use`) on the actual root before releasing any facts.
Missing and inaccessible resources must remain indistinguishable there; current
identity/grants must be rechecked under the protected adapter's release rules.
Knowledge of a revision ID or permission to read a binding is not such authorization.
No HTTP route is added now, even though existing facets already have dedicated HTTP
admission. Its frozen registry and packaged schemas are unchanged.

## 7. Compatibility and client handoff

No migration, index, constraint, trigger, data rewrite, identity derivation or current
definition hash change is required. Reuse the stored v1 definition decoder. A future
decoder version needs its own owning-family contract; do not reinterpret old bytes.

Activation requires an additive runtime release and new exact release pin, an explicit
read-only compiled registry entry and declaration of this contract plus the existing
`spine.facet-schemas.v1`, `spine.canonical-json.v1`, and
`spine.notification-rendering-integration.v1` prerequisites. Update local schema
packaging/dependency closure deliberately; do not leak the command into current web
registries. Neither runtime 0.9.1 nor the inspected commit implements this reservation.

Spine Packs must separately adopt the repaired/additive baseline, refresh its command
inventory, full transitive schema closure and planning fixtures, then qualify old
cross-root pins. For A2/B2 current roots and an existing B1 pin, lookup returns actual
root B plus B1. Packs compares that evidence with desired root A; it does not infer
that B1 belongs to A or silently suppress read failures. Deduplicate exact revision
lookups within its global observation budget. This document neither changes Packs
nor qualifies FR-2; it removes the need to design a probing protocol.

## 8. Fixtures and implementation acceptance

The [fixture manifest](../contracts/facet-schema-revision-readback-fixture-manifest.json)
indexes structural fixtures and a pure historical-state witness. Contract/model tests
are offline checks, **not** completed runtime/admission/concurrency proofs.
It also indexes a pure validation-precedence witness for combined malformed inputs;
expected code/field/exit facts are normative, not the JSON validator's first error.

| ID | Required proof before implementation is complete |
| --- | --- |
| RR-01 | Public CLI accepts revision-only request; current and historical success match schemas and requested identity |
| RR-02 | A2/B2 roots with old B1 binding/selection return root B and B1, independent of desired A |
| RR-03 | Retired root remains readable; exact stored definition/hash/ordinal do not change on publish/retire |
| RR-04 | Missing revision returns the exact not-found field/exit; no current/default fallback |
| RR-05 | Broken stored root/decoder/hash/projection fails environment, not not-found or partial success |
| RR-06 | Empty/type/extra/selector failures, including combined missing/extra/value failures, follow Section 5's exact order and field tie-break; dry-run adds only the true marker |
| RR-07 | Reads and all failures leave ledger rows, receipts/audits, versions, work and external attempts unchanged |
| RR-08 | Indexed point lookup and every byte/resource/SQL/time/lock ceiling fail closed; no enumeration/deep scans |
| RR-09 | Concurrent publish/retire yields a coherent read snapshot while preserving selected immutable evidence |
| RR-10 | Existing facet commands, closed binding/rendering shapes and frozen HTTP/web/package surfaces are unchanged |
| RR-11 | Installed package includes deliberate local contract closure; advertised prerequisites exactly match compiled registry |

Executable RR-01–11 evidence is recorded in
[test_facet_schema_revision_readback.py](../tests/test_facet_schema_revision_readback.py)
and [SPINE-058](../docs/BACKLOG.md#spine-058--deliver-trusted-local-facet-revision-readback).
The separate pure models above remain offline examples, not runtime proof by
themselves. Protected exposure/authorization tests are not part of this trusted-local
slice and need a separately approved successor. Deployment and consumer adoption
remain separate from local release verification.
