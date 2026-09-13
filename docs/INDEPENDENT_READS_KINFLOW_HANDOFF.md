# Kinflow Handoff: Independent Activity Reads

Status: Proposed integration contract; not available in the current Spine runtime
Tracking: [SPINE-015](BACKLOG.md#spine-015--read-authorized-activities-independently-of-unavailable-linked-resources)
Authority: [Independent authorized activity reads](../specs/independent-activity-reads.md)

## Current behavior

The reported Science-class failure is consistent with Spine's current binding-graph
read admission. `resource_unavailable` does not identify an ownership gap: absent,
unowned, and inaccessible resources deliberately share the generic denial. Keep
Kinflow's current isolated failure and incomplete-calendar behavior until the new
capability is actually advertised. No staging repair or deployment is part of this work.

## Proposed consumer behavior

1. Negotiate the exact read capability and result versions in spec Section 9. The new
   `/api/v2` read surface is proposed; do not call it based only on this document or
   treat an unsupported version as an empty agenda. Writes continue through v1.
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
5. Key views/cursors by identity, selection, query, access epoch, item version and
   recurrence revision. Discard old selections and late query generations. On
   `access_changed` or `version_changed`, invalidate affected cached views/pages and
   restart with fresh context. On generic denial, do not continue displaying cached
   content as currently authorized. Do not mix old pages with new source snapshots.
6. Treat item-level edit hints as advisory. Submit writes with their existing version,
   epoch and command-ID rules; read success does not authorize connected-item effects.

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

Ship Spine's exact schemas, registry, capability declarations and behavior first;
enable Kinflow only for supported versions. Preserve old-client behavior during
migration. On server rollback/loss of capability, discard new read caches and cursors
and use explicit legacy failure handling. Ownership provisioning at task creation
remains an independent companion change, not a prerequisite or substitute for these
legitimate mixed-access cases.
