# Facet API — consumer and operator handoff

Runtime 0.8.0, schema 17. Authoritative transport contract:
[facet web admission](../specs/facet-web-admission.md). This is the same restricted
trusted-network service as the scheduling API: **account selection is not authentication**.
Anyone with access to this trusted interface can select an eligible operator.
The trusted-local CLI remains full-scope. Kinflow adoption is a separate UI task.

## Discover and call

GET `/api/v1/facets/capabilities` with `X-Spine-Account-ID` and
`X-Spine-Selection-ID`. It returns `spine.trusted-web-facets.v1`, the exact
[eleven-command registry](../contracts/spine.trusted-web-facet-registry.v1.json),
and `pagination_configured`. It reveals no catalog or item data.

POST `/api/v1/facets/commands/<canonical-command>` with exact configured Host/Origin,
`Content-Type: application/json`, and the same selection headers. Use dotted command
identifiers, e.g. `item.facets.show`, not CLI word spacing. There is no generic dispatch.

Read body example:

```json
{
  "request": {
    "contract_version": "spine.item-facets.v1",
    "item_id": "<existing-item-id>"
  }
}
```

Write bodies additionally require outer `expected_access_epoch` as a decimal string.
Obtain the current epoch and selected subject through existing `/api/v1/context`.
The inner request uses the unchanged canonical facet command pin and fields,
including `command_id`, selected `actor_subject_id`, and `action_timestamp_utc`.
Do not put the API family version in the inner `contract_version`.

- Schema: `facet_schema.create`, `.publish`, `.retire`, `.show`, `.list`.
- Binding: `item_archetype.facet_binding.set`, `.remove`, `.list`.
- Values: `item.facets.update`, `.show`, `.query`.

Use [canonical command instructions](FACET_COMMANDS.md) for request meanings;
[closed HTTP schemas](../contracts/schemas/trusted-web-facet-request.schema.json)
and [wire fixtures](../contracts/trusted-web-facet-fixture-manifest.json) supply the
envelope. Success returns identity/selection/epoch, exact `result_contract`, and
canonical `result`. Discard responses for an old UI selection. Failure returns
only a fixed generic message, code and correlation/selection IDs—never private
domain details.

## Permissions and retry

Catalog creation/publication/binding administration requires the selected subject
owner, or an adopted group's admin/owner. Ordinary membership grants catalog
read/use, not administration—even if that member originally created the catalog.
System catalog writes stay local. Explicit `catalog.read`/`catalog.use` grants can
share a schema or archetype; they do not grant administration.

Values inherit current item read/edit rights. Every fresh set—including a same-value
no-op—also checks schema/archetype use and references. Removal does not renew those
catalog permissions. Item readers can decode their pinned historical definitions
without live catalog access. Entire shows deny if any nested reference is hidden.
This first protected subset supports scalar fields and self-subject references:
other subjects and all locations are unavailable. Reference-rich airport/flight
examples remain trusted-local. Typed queries return item IDs/versions, not values;
their predicate references are still checked even when there are no matches.

Retry an uncertain write with the same command ID and semantic request. Compatible
replay requires the original account/subject and current resource read rights,
not current edit/admin rights. A new selection ID is allowed. Replay returns no
facet values or reference contents and writes no evidence. IDs originating from a
different account or local CLI are unavailable through this API. On `access_changed`,
refresh context; on `domain_conflict`, read current state and deliberately form a new
request. Do not silently retry a changed mutation under the previous command ID.

## Bounded pagination and configuration

Schema list, binding list and item query require private cursor configuration,
including their first page. Start the service with
`--facet-cursor-config /absolute/private/facet-cursor.json`. Reuse the documented
[CLI config shape](FACET_COMMANDS.md#protected-cursor-configuration), with a random key of
at least 32 bytes, stable ledger ID and generation. The file must be regular,
non-symlink, owned by the service user (or readable root-owned), and have no
group/other permission bits. Never place it in request JSON or commit it.
No implicit key is generated. Without it, non-paginated commands still work but
facet pagination returns `admission_unavailable`.

Preserve the file across restarts. Clones need distinct key/context; restores rotate
generation. Tokens bind account/subject/selection, query, candidate source and bounded
access proof. Children retain the original 15-minute expiry and any earlier grant/
membership transition deadline. Use `next_cursor` unchanged; changed authority,
source, key/context or expiry invalidates continuation. Start a new first page.

Limits: 100 candidates/resources/access-proof rows, 1 MiB requests, 4 MiB responses,
5 seconds and 100000 SQL VM steps (service ceilings may be lower). Capacity failure
returns no partial data. Routine reads persist no receipts/cursors/access proofs.

## Upgrade and local grants

Stop all writers, take a consistent backup, migrate using the checkout-local
`spine-ledger-migrate`, then restart matching runtime 0.8.0 services. Schema 17
preserves all prior grant rows/history and adds facet-schema targets. Schema 16
is rejected by the new runtime until migration. Rollback means stopping writers
and restoring the matching old binary/backup pair—not downgrading a live schema.

For facet grants, use local `web_access.plan` / `web_access.apply` with
`spine.trusted-web-provisioning.v2` consistently in the plan, apply and nested plan.
Set `resource_kind=facet_schema`, the existing schema root ID,
`resource_owner_revision="1"`, explicit grantee and bounded grant times. The existing
operation rules apply: `catalog.use` is accompanied by `catalog.read`. Inspect
`can_apply` and the complete plan before applying. No defaults/memberships are inferred.
V1 provisioning remains accepted but cannot name facet-schema targets.

After upgrade verify readiness, facet discovery, an authorized show/list, a denied
foreign read, and unchanged scheduling/v2 read smoke tests. A real mutation canary
requires operator approval. No UI deployment or real notification send is part of
this feature's implementation checkpoint.
