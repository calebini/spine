# Kinflow Handoff: Independent Activity Reads

Status: Spine 0.6.0 backend implemented; deployment and Kinflow acceptance pending
Updated: 2026-09-19; aligned with independent-read v1 and cursor v2
Tracking: [SPINE-015](BACKLOG.md#spine-015--read-authorized-activities-independently-of-unavailable-linked-resources)
Authority: [Independent authorized activity reads](../specs/independent-activity-reads.md)

## Current behavior

The reported Science-class failure is consistent with Spine's v1 binding-graph
read admission. `resource_unavailable` does not identify an ownership gap: absent,
unowned, and inaccessible resources deliberately share the generic denial. Keep
Kinflow's current isolated failure and incomplete-calendar behavior until the new
capability is actually advertised. No staging repair or deployment is part of this work.

Machine artifacts: [read registry](../contracts/spine.trusted-web-read-registry.v1.json),
[contract companion](../specs/independent-activity-read-contracts.md), and
[fixtures](../contracts/independent-activity-read-fixture-manifest.json).
Spine 0.6.0 implements the selected-identity `GET /api/v2/read-capabilities` route.
This checkout is not evidence that the staged backend has been upgraded. Negotiate
the deployed capability before adoption; the v1 behavior remains unchanged.
Agenda exposes singleton `primary_location`, `policies`, `work`, and `attempts`
sections; detail exposes all eleven sections. Examples are wire fixtures, not proof
of canonical occurrence derivation or authorization behavior.

## Consumer behavior after runtime delivery

1. Negotiate the exact read capability and result versions in spec Section 9. The new
   `/api/v2` read surface is implemented in Spine 0.6.0; do not assume the deployed
   server has it or treat an unsupported version as an empty agenda. Discovery needs
   the same selected account and selection headers as the reads. Writes continue through v1.
2. Render the canonical agenda and occurrence results returned by Spine. Use the
   supplied item/version, occurrence ID/key, recurrence revision, effective status,
   and dates/start/end. Do not expand recurrence, infer duration, use task dates to
   reconstruct events, or fill missing times from an earlier response.
3. Keep successfully read core events visible if optional detail is unavailable.
   `time.availability=unavailable` means no current date/deadline is safe to display.
   Agenda `unplaced_items` belong outside the dated grid; their membership in the
   requested date range is unknown. `coverage=incomplete` and `has_more` mean different
   things: unresolved candidate time versus additional pages.
4. Interpret section availability explicitly. `not_requested` is not empty;
   `unavailable` permits a generic optional-context limitation; an available empty
   `authorized_only` section means no visible results, not proof that no linked tasks
   exist. Never say a task is hidden, unowned, assigned to someone, or withheld based
   on this result. Spine does not return those facts to explain omissions.
5. Key all views/cursors by identity, selected account-subject binding revision,
   selection, query and access epoch. Direct item views additionally bind their
   item/recurrence versions and may submit `expected_item_version` and
   `expected_recurrence_revision_id`. Agenda uses its authorized candidate snapshot
   and opaque cursor, not a single item version or per-item guard map; do not submit
   either singular guard to agenda, even when selecting one item. All new read routes
   may supply `expected_access_epoch`. The v2 identity-binding field
   `account_subject_binding_revision` is distinct from `temporal_binding_revision_id`;
   do not interpret cursor payloads or substitute a temporal revision for identity.
   `subject_revision` is a positive-decimal content fingerprint, not a counter or
   JavaScript number; compare its string value for equality only. Continuation has
   a fixed original expiry. A server losing its volatile private proof also returns
   `access_changed`; it must not be interpreted as evidence of a particular grant
   change or hidden resource.
   Discard old selections and late query generations. On
   `access_changed` or `version_changed`, invalidate affected cached views/pages and
   restart with fresh context. On generic denial, do not continue displaying cached
   content as currently authorized. Do not mix old pages with new source snapshots.
   Server restart/key rotation invalidates signatures; an `invalid_request` on
   continuation also requires discarding that cursor before an explicit fresh query.
   Do not retry an invalid cursor indefinitely or reinterpret failure as empty data.
6. Treat item-level edit hints as advisory. Submit writes with their existing version,
   epoch and command-ID rules; read success does not authorize connected-item effects.
7. Request `authoring_receipt` only through the new schedule-view include contract.
   It is an authorized-only summary of persisted creation evidence, not a new v1
   include option. Not requested is distinct from available null; null does not
   prove that no creation receipt exists. Never expect full receipt payloads or
   interpret missing receipt evidence as failed item creation.

Kinflow owns family-facing copy. Safe concepts include “additional details could not
be loaded” for a disclosed unavailable section and “time unavailable” for an authorized
item's unavailable temporal view. Do not infer or name the cause. Authorized-only
filtering by itself does not justify an incomplete-calendar warning; actual temporal
coverage or request failure does.

## Integration acceptance and rollout

Use IR-01–IR-16 in the supporting spec, especially IR-15/16, for shared fixtures.
Prove that the class remains visible with an unowned or differently authorized
following task, authorized tasks still appear, unresolved task time is never placed
using a stale deadline, and identity switches cannot reveal late responses.

Spine's exact schemas, registry, capability declarations and backend behavior are
implemented and verified locally; cloud validation and deployment remain separate.
Enable Kinflow only for supported deployed versions. Preserve old-client behavior during
migration. On server rollback/loss of capability, discard new read caches and cursors
and use explicit legacy failure handling. Ownership provisioning at task creation
remains an independent companion change, not a prerequisite or substitute for these
legitimate mixed-access cases.
