# Spine Owner-Scope Discovery

Status: Draft v1; not implemented
Scope: Bounded, read-only discovery of canonical subject, subject-group, and system owner scopes
Created: 2026-08-29

## 1. Purpose

Spine allows item archetypes, notification profiles, profile bindings, delivery
targets, and other reusable definitions to be owned by an exact system, subject, or
subject-group scope. An operator choosing an owner therefore needs a supported way to
discover which canonical scopes exist before authoring a reusable definition.

The current runtime can create or update exact identities through `subject.upsert`
and `subject_group.upsert`, but it has no canonical read command that enumerates those
identities. Operators must otherwise rely on host configuration, an independently
preserved bootstrap bundle, or a read-only SQLite diagnostic. That is an operator-
surface gap: routine agents should not need table knowledge to choose a valid owner.

This specification defines one bounded read projection, `owner_scope.list`. It does
not add a new identity authority, infer group membership, or change ownership.

## 2. Authority and Version Facts

This specification depends on:

- `specs/ontology.md` for canonical subject and subject-group identity;
- `specs/notification-profiles.md` for exact owner scopes and scoped catalogs;
- `specs/agent-command-contract.md` for common response, error, transport, and runtime
  admission rules; and
- `specs/architecture.md` for ledger authority and projection boundaries.

The planned contract family is:

- `contract_version=spine.owner-scope-discovery.v1`;
- `response_contract=spine.owner-scope-list-response.v1`; and
- `cursor_contract=spine.owner-scope-list-cursor.v1`.

These identifiers are not implemented and MUST NOT appear in
`system.info.implemented_contract_versions` or the compiled command registry until
the request/response schemas, fixtures, runtime behavior, and tests land atomically.

## 3. Boundary

`owner_scope.list` is a read-only projection over canonical identity rows. It:

- enumerates exact owner values legal for owner-scoped commands;
- distinguishes people, agents, and other subject kinds from group kinds;
- exposes stable IDs, display names, and lifecycle status;
- supports bounded deterministic filtering and pagination; and
- creates no audit, command receipt, item version, profile, binding, delivery target,
  work row, or side-effect attempt.

It does not:

- create, revise, activate, deactivate, merge, or delete an identity;
- infer group membership or household relationships;
- claim that a subject is authorized to administer another owner;
- enumerate delivery addresses, adapter targets, or credentials;
- enumerate the archetypes, profiles, or bindings owned by a returned scope;
- make a transport group equivalent to a household group; or
- replace the existing per-owner `item_archetype.list`,
  `notification_profile.list`, or `notification_profile.binding.list` commands.

The returned owner is a catalog and governance scope. It is not an item participant,
notification recipient, delivery destination, or command actor unless another
request explicitly uses the same identity in that separate role.

## 4. Command Request

The transport-neutral command identifier is `owner_scope.list`.

The request is a closed JSON object with:

- required `contract_version`, exactly `spine.owner-scope-discovery.v1`;
- optional `owner_kinds`, a non-empty unique subset of
  `system|subject|subject_group`, defaulting to all three in that order;
- optional `statuses`, a non-empty unique subset of `active|inactive`, defaulting to
  `active`;
- optional `subject_kinds`, a non-empty unique subset of `person|agent`, applicable
  only when `subject` is selected;
- optional `group_kinds`, a non-empty unique subset of
  `household|project|team|transport_group`, applicable only when `subject_group` is
  selected;
- required decimal-string `limit` in `1..500`; and
- optional non-empty opaque `cursor`.

Unknown fields fail with `unsupported_field`. A `subject_kinds` filter when `subject`
is absent, or a `group_kinds` filter when `subject_group` is absent, fails with
`invalid_request` at the filter field. Filters are sets: their input order is not
semantic. Normalization orders subject kinds as `person`, `agent` and group kinds as
`household`, `project`, `team`, `transport_group`.

The request has no `command_id`, actor, or evaluation timestamp because it is a
bounded read that consumes no idempotency key and depends on no ambient time.
Deployment authorization for identity discovery remains outside this data contract;
the command itself MUST NOT silently filter results by inferred group membership.

## 5. Entry Shape

Every result entry is a closed object containing:

- `owner_scope_key`, the canonical display-safe key described below;
- `owner`, using the exact owner union from `specs/notification-profiles.md`;
- `identity_kind`;
- `display_name`;
- `status=active|inactive`; and
- `source=derived_system|subjects|subject_groups`.

For `owner_kind=system`:

- `owner={"owner_kind":"system"}`;
- `owner_scope_key=system`;
- `identity_kind=system`;
- `display_name=Spine system`;
- `status=active`; and
- `source=derived_system`.

The system entry is derived protocol truth, not a synthetic database row. It appears
only when `system` is selected and `active` is included. Ordinary operators cannot
create, revise, or retire it.

For `owner_kind=subject`:

- `owner={"owner_kind":"subject","owner_subject_id":"<subject_id>"}`;
- `owner_scope_key=subject:<subject_id>`;
- `identity_kind` is the stored `subject_kind`;
- `display_name` and `status` are current stored subject facts; and
- `source=subjects`.

For `owner_kind=subject_group`:

- `owner={"owner_kind":"subject_group","owner_group_id":"<group_id>"}`;
- `owner_scope_key=subject_group:<group_id>`;
- `identity_kind` is the stored `group_kind`;
- `display_name` and `status` are current stored group facts; and
- `source=subject_groups`.

IDs and display names are returned exactly as canonical ledger facts. The command
does not rewrite a `transport_group` as a `household`, infer that two similarly named
owners are equivalent, or select a recommended owner.

## 6. Ordering, Generation, and Pagination

The total result order is:

1. owner-kind order `system`, `subject`, `subject_group`;
2. canonical owner ID byte order, with the system entry using an empty ID; and
3. `owner_scope_key` as the final deterministic tie-breaker.

The normalized `query_hash` is the Spine canonical-JSON hash of:

- contract version;
- normalized owner-kind, status, subject-kind, and group-kind filters; and
- requested limit excluded, so callers may reduce or increase page size between pages
  without changing selection semantics.

The implementation MUST maintain one ledger-local `owner_scope_generation` decimal
counter. The schema migration initializes it once after existing subjects and groups
are admitted. Every fresh subject or subject-group insert and every change to identity
kind, display name, or status increments it exactly once in the same transaction.
No-op upserts and compatible replay do not increment it. The derived system entry does
not increment it because its facts are protocol constants.

The first page reads one `source_generation` under the same SQLite read snapshot as
selection. Continuation requires the current generation to equal the cursor-bound
value. This gives deterministic stale-page detection without hashing or scanning the
complete identity catalog on every page.

Implementations MUST provide schema-versioned indexes capable of selecting the next
`limit+1` matching subject and group rows by status, identity kind, and ID. Work and
memory are bounded by the fixed filter count and requested page size rather than total
ledger size.

The opaque cursor binds:

- `cursor_contract=spine.owner-scope-list-cursor.v1`;
- `query_hash`;
- `source_generation`; and
- the last emitted ordering tuple.

A cursor whose query facts differ fails with `invalid_request`, `field=cursor`. A
matching query whose source generation changed fails with `stale_cursor`,
`field=cursor`. The command MUST NOT silently continue across changed identity truth.

## 7. Success Response

Success returns a closed object containing:

- `ok=true`;
- `command=owner_scope.list`;
- `response_contract=spine.owner-scope-list-response.v1`;
- normalized `owner_kinds`, `statuses`, `subject_kinds`, and `group_kinds`; absent kind
  filters expand to the complete closed set when their owner kind is selected and to
  an empty array otherwise;
- accepted decimal-string `limit`;
- `query_hash` and decimal-string `source_generation`;
- ordered `entries`;
- `has_more`; and
- required nullable `next_cursor`.

`next_cursor` is non-empty exactly when `has_more=true` and JSON `null` otherwise.
The response does not include a redundant `truncated` field. An empty matching result
is successful and returns `entries=[]`, `has_more=false`, and `next_cursor=null`.

The response intentionally omits catalog counts. After selecting an owner, callers
use the existing bounded per-owner list commands to inspect:

- item archetypes;
- notification profiles; and
- notification-profile bindings.

This preserves the granularity and authority of those catalogs while removing raw-SQL
identity discovery.

## 8. Validation and Failure Ordering

Evaluation order is:

1. parse a JSON object and reject missing, malformed, or unsupported fields;
2. validate the exact contract version and filter combinations;
3. verify ledger schema and exact runtime contract admission;
4. decode and validate an optional cursor and query binding;
5. read and compare the source generation for a continuation request;
6. select and normalize at most `limit+1` matching identity facts through required
   indexes;
7. paginate in total order; and
8. construct and validate the closed response.

Expected errors use the shared command contract and CLI mapping:

- unsupported or malformed request facts: `invalid_request` or
  `unsupported_field`, CLI exit `2`;
- unavailable or mismatched runtime/schema contract: `environment_failure`, CLI exit
  `7`;
- changed continuation source: `stale_cursor`, CLI exit `6`; and
- internal projection or response-invariant failure: `runtime_failure`, CLI exit `7`.

Every failure writes nothing and returns no partial page.

## 9. Transitional Operator Posture

Until `owner_scope.list` is implemented, an operator may use this bounded fallback:

1. run `system.info` and verify runtime/schema compatibility;
2. prefer the independently preserved provisioning or bootstrap bundle;
3. when that bundle is incomplete, inspect only the `subjects` and `subject_groups`
   table schemas;
4. open the ledger explicitly read-only;
5. select only the identity, kind, display-name, and status columns needed for owner
   choice; and
6. order results deterministically.

This fallback is diagnostic, not an alternate public contract. It authorizes no raw
SQLite write, schema mutation, hidden membership inference, or reuse of SQL as routine
agent choreography. Once the runtime advertises `spine.owner-scope-discovery.v1`,
agents MUST prefer `owner_scope.list` for ordinary owner discovery.

## 10. Conformance Requirements

Implementation requires matching request and response JSON Schemas, fixtures, and
contract tests covering:

- the derived system entry;
- active subjects and groups in deterministic order;
- inactive inclusion and default active filtering;
- subject-kind and group-kind filters;
- empty results;
- pagination and page-size changes;
- query-mismatched and stale cursors;
- display-name, status, kind, and set-change generation invalidation;
- transactional generation increments, with no increment for no-op or replay;
- indexed `limit+1` selection without a complete identity-catalog scan;
- closed request and response fields;
- no receipt, audit, domain row, or side effect; and
- exact parity between the compiled registry, implemented-version declaration, and
  `system.info` before the command is advertised.

## 11. Acceptance Criteria

The capability is ready when:

1. An agent can discover every canonical owner scope needed for catalog authoring
   without raw SQL or prior knowledge of subject/group IDs.
2. Results distinguish subject and group kinds without conflating ownership,
   participation, notification recipient, delivery route, or command actor roles.
3. The read is bounded, deterministically ordered, snapshot-bound, and replay-free.
4. Existing per-owner archetype, profile, and binding lists remain the granular catalog
   read surfaces.
5. The runtime does not advertise the family before schemas, fixtures, behavior, and
   tests land together.
