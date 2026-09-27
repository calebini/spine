# Facet web admission v1

Status: implementation contract for SPINE-029. Updated: 2026-09-27.
Logical authority: [archetype facets](archetype-facets.md), Sections 6 and 11.
Storage authority: [facet storage](archetype-facet-storage.md); access semantics:
[permissions](permissions.md). This leaf defines transport and migration details,
not new permissions, shared-location rules, or stronger authentication.

## Closed additive interface

`spine.trusted-web-facets.v1` is a dedicated family on the existing trusted-network
web service. Its immutable manifest is `spine.trusted-web-facet-registry.v1`.
Each of the eleven canonical commands maps to exactly one POST route at
`/api/v1/facets/commands/<canonical-command>`. Existing v1 command and v2 read
registries, wrappers and schedule projections remain unchanged. Unknown routes
fail `operation_unavailable`; no generic handler dispatch is exposed.

All requests use the existing exact Host, Origin, JSON content type, selected account
and selection-ID headers. Responses remain explicitly `identity_basis=self_selected`;
this is honest identification, not verified authentication. Selected identity is
resolved from current ledger facts, never from an actor or subject header. Write
`actor_subject_id` must match the selected subject.

The closed body contains `request` with its unchanged canonical facet pin. Writes
also require `expected_access_epoch` (decimal string). This guard applies only to
fresh execution, not compatible replay; changing it does not change command semantics.
Transport dry-run is not exposed: bounded previews remain the CLI invocation option.
The closed success wrapper carries family version, ok, identity basis, account,
subject, selection, access epoch, exact result contract and canonical command result.
Errors contain only a stable web error code and fixed generic message, correlation
ID and nullable selection ID. No domain payload, SQL, resource ID or reference value
is included. Status mappings remain logical Section 6.1.

GET `/api/v1/facets/capabilities` requires an eligible selection and returns this
family's version, exact closed registry and `pagination_configured` boolean. It does
not list data, keys, grants or accessible resources. This is an additional discovery
surface, not a mutation of frozen `/api/v1/info` or v2 read-capabilities contracts.
Runtime admission checks packaged schema digests, exact compiled resolver/command
mappings and required runtime pins before registering these routes.

## Execution, replay and release

The adapter owns one write transaction through canonical item/catalog mutation,
audit, receipt, protected `web_receipt_links` attribution and precommit permission
revalidation. It invokes the shared facet normalization and write functions; it
does not duplicate mutation logic or open a trusted-local bypass. Failures roll back
the complete transaction. Fresh no-ops also receive protected attribution.

Replay privately resolves the existing receipt after identity/shape admission.
The original account, subject, binding identity and facet API attribution must match;
changing only selection/session ID is permitted. Local or foreign receipts return
`command_id_unavailable`. Current resource-read checks follow the exact six-write
matrix in the logical spec before canonical semantic comparison. No fresh write,
admin, reference or active-binding check is substituted for replay disclosure.
Every replay path is read-only even though the write endpoint acquires the writer lock.
No replay updates protected links, audits, receipts or access epochs.

Read snapshots release before a fresh authority/source fence. Page construction
happens exactly once; source and access proof revalidation shares the original
budget. Revocation, gained visibility, temporal access transitions or source drift
fail without results/cursors or durable read evidence. Show is complete-or-deny;
item authorization publishes its pinned definition without requiring live catalog
access, while nested references still require current visibility. Queries do not
dereference non-predicate values. Current scalar and self-subject support does not
authorize shared airport/location or other-person references.

The separately provisioned cursor config is the same protected-file shape as the
CLI, passed through trusted service configuration. Web tokens use permission-enforced
principal and complete bounded row proofs from logical Section 11, not OS identity.
Missing configuration denies all paginated reads, including first pages, without
preventing non-paginated commands. No ephemeral/generated fallback key is permitted.
Clones require distinct key/context; restores rotate generation. Request/response
ceilings are 1 MiB/4 MiB, 5 seconds, 100000 SQL VM steps, 100 resolved resources,
100 candidates and 100 combined access-proof rows; configured runtime ceilings may
lower these. A capacity failure never returns an incomplete page.

## Grant storage and provisioning successor

Schema 17 adds `facet_schema` to `access_grants.resource_kind`, with immutable
`resource_owner_revision=1`, existing catalog.read/catalog.use operations, and
resource-existence/deletion protection. It introduces no catalog-admin grant.
All existing grant rows, revision/operation history, IDs and unrelated tables are
preserved. No accounts, owners, memberships or default grants are inferred or created.

The offline 16-to-17 migration verifies the pinned predecessor, copies the grant
table to its successor, preserves indexes/triggers, checks row parity and foreign
keys, and activates the version in one transaction. FK enforcement is restored on
both success and failure. Failure restores the predecessor without partial DDL/data.
Post-commit rollback requires restoring a consistent schema-16 backup with its
matching binary; there is no destructive down-migration.

`spine.trusted-web-provisioning.v2` is an additive successor of the trusted-local
web_access.plan/apply contract, adding only facet_schema grant targets. All nested
plan/request/response pins must be v2 together. V1 remains accepted unchanged and
cannot express the new resource kind. Both reuse existing plan-hash, epoch, audit,
receipt, reference-state and revocation rules. Neither is a web endpoint. Closed
v2 schemas are published alongside v1 rather than editing v1's enum or digests.

## Verification

Required real-ledger coverage: self/group/member/admin and explicit grants; all six
write receipt branches; read-retained/write-revoked and lost-read replay; hidden
references; historical item read without catalog use; foreign-owner candidate subsets;
grant starts/expiry/revocation and source-release races; key/context/selection changes;
no receipt or cursor persistence on reads; atomic denied writes; exact HTTP registry/
schema pins; schema-16 migration preservation, rollback and fresh/migrated DDL parity.
Existing scheduling, local facet commands, web v1/v2 and worker tests remain required.
