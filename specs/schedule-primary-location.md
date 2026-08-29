# Spine Primary-Location Schedule Support

Status: Implemented v0.1.0 (introduced on schema 9; active on schema 12)
Scope: Additive primary-location authoring, mutation, readback, builder pass-through, and operator projections for scheduled events and tasks
Created: 2026-08-18

## 1. Purpose

Spine already stores first-class immutable canonical locations and version-scoped
`item_locations` rows. Lower-level ledger workflows can create and read those facts,
but the public schedule surface cannot author or change them. An operator can create an
event with time and reminders yet cannot say where it occurs without bypassing the
schedule contract.

This specification activates one intentionally narrow location capability:

- create a scheduled event or task with zero or one primary location;
- either create that canonical location inline or reference an existing location;
- replace, clear, or retain the primary location through `schedule.update`;
- read one clean primary-location projection through `schedule.show` or `agenda.show`;
- pass primary-location authoring through `schedule.build`; and
- include the same clean projection in compact output when it was requested or authored.

The capability composes the existing location ontology. It does not introduce a
schedule-local location entity, geocoder, address book, venue catalog, or inference
engine.

## 2. Authority and Contract Family

`specs/ontology.md` remains authoritative for `locations`, `item_locations`, immutable
canonical location fields, item-version supporting-set materialization, and the unique
`(item_id, version, role)` constraint.

The additive capability constants are:

- `location_contract=spine.schedule-primary-location.v1`;
- `authoring_contract=spine.schedule-primary-location-authoring.v1`;
- `view_contract=spine.schedule-primary-location-view.v1`;
- `normalization_version=spine.schedule-primary-location-normalization.v1`; and
- `canonical_json_version=spine.canonical-json.v1`.

The machine-readable shared type contract is
`contracts/schemas/schedule-primary-location-types.schema.json`.

The current schema-11 runtime may advertise this complete family only when the request schemas,
response schemas, fixtures, command handlers, builder, readback, compact projection,
version-copy behavior, replay verification, and behavioral tests all conform. No
ledger migration is required: schema 8 already has the canonical tables, enums,
foreign keys, uniqueness constraint, and immutability trigger needed by Version 1.

This family is additive to the existing schedule contracts. Requests that omit the new
fields retain their previous semantics and response shape. New primary-location fields
are returned only on the conditional surfaces defined below.

## 3. Foundational Invariants

1. **One authority.** A schedule primary location is the current version's ordinary
   `item_locations.role=primary` row joined to its ordinary `locations` row.
2. **At most one.** Schema uniqueness continues to enforce at most one primary role for
   one item version.
3. **Immutable history.** Replacing location meaning creates a new canonical
   `locations` row and a new item version. Historical location and item-location rows
   are never rewritten.
4. **Explicit reference or creation.** The command never searches for a likely venue,
   geocodes text, deduplicates against unrelated locations, or infers identity.
5. **Location time is not schedule time.** A location's optional `timezone` is
   descriptive canonical location data. It never supplies, overrides, or re-resolves
   the scheduled anchor's timezone or timezone-database version.
6. **Location is not routing.** A physical or virtual location never selects a
   notification channel, recipient, delivery target, or adapter destination.
7. **No hidden work invalidation.** Under this capability, a primary-location-only
   change does not stale existing recurrence provenance or notification work because
   those contracts do not bind location facts. A later contextual-advisory work family
   may define its own location-snapshot freshness.
8. **Conditional additive output.** Existing callers that do not author, patch, or
   explicitly request a primary-location projection receive the prior response shape.
9. **Granularity remains available.** The clean primary-location projection does not
   replace `item.show` or the complete version-scoped `locations` collection.
10. **Replay is environmental-state free.** Compatible replay returns stored receipt
    evidence and never rechecks a referenced location or searches current location
    state.

## 4. Version 1 Authoring Shape

`primary_location` uses exactly one of two closed forms.

### 4.1 Inline creation

```json
{
  "mode": "create",
  "label": "Lakeside Golf Club",
  "kind": "place",
  "address_text": "123 Fairway Road, Toronto, ON",
  "latitude": "43.7001",
  "longitude": "-79.4163",
  "timezone": "America/Toronto",
  "provider_ref": "maps:place:example"
}
```

Required fields are `mode=create`, non-empty `label`, and `kind`. `kind` is exactly one
of `address`, `place`, `virtual`, `relative`, or `unknown`.

Optional canonical fields are `address_text`, `latitude`, `longitude`, `timezone`, and
`provider_ref`. When present, each is a non-empty string. Latitude and longitude must
be supplied together. They use ordinary non-exponent decimal strings; latitude must be
in `-90..90` and longitude in `-180..180`. Their exact accepted decimal spellings are
canonical facts; the command does not round, reformat, or infer precision.

Inline creation forbids `location_id`, `item_location_id`, `role`, `metadata_json`, and
caller-supplied timestamps. Spine derives identities and timestamps.

### 4.2 Existing-location reference

```json
{
  "mode": "reference",
  "location_id": "location_..."
}
```

This form requires exactly `mode=reference` and a non-empty `location_id`. The row must
already exist. All inline canonical fields are forbidden. The referenced row's current
canonical fields become the item version's primary-location truth; after the new
`item_locations` row references it, the existing ontology immutability trigger
prevents canonical in-place changes.

The referenced row must also be representable by the Section 5 view: `label` and every
present optional string are non-empty and non-whitespace, coordinates are either both
absent or both present, and present coordinates satisfy the Section 4.1 decimal and
range rules. A row that exists but violates those facts fails `semantic_conflict` at
the request `location_id`; the command does not repair or reinterpret it.

Referencing a location does not copy it, claim ownership of it, or make its
`metadata_json` canonical.

### 4.3 Normalized authoring value

The normalized authoring value includes `location_contract`, `authoring_contract`,
`normalization_version`, and `canonical_json_version` plus:

- for `create`: `mode`, `label`, `kind`, and every supplied optional canonical field;
- for `reference`: `mode` and `location_id`.

Absent optional fields remain absent. JSON `null`, unknown fields, empty strings,
whitespace-only strings, JSON numbers for coordinates, exponent coordinates, and a
single unpaired coordinate fail validation. Request order has no semantic meaning.

## 5. Clean Primary-Location View

The `spine.schedule-primary-location-view.v1` object contains:

- `location_contract=spine.schedule-primary-location.v1`;
- `view_contract=spine.schedule-primary-location-view.v1`;
- `location_id`;
- version-scoped `item_location_id`;
- `role=primary`;
- `label` and `kind`;
- optional `address_text`, `latitude`, `longitude`, `timezone`, and `provider_ref` when
  stored;
- `item_location_created_at_utc`;
- `location_created_at_utc`; and
- `location_updated_at_utc`.

The view omits `metadata_json`, item identity, and item version. Its containing response
already binds the item and version; non-canonical metadata is not advisory or schedule
truth. Missing optional fields are omitted rather than returned as JSON `null`.

When an explicitly requested read finds no primary location, it returns
`primary_location=null`. This distinguishes “requested and absent” from “projection
not requested,” where the property is omitted.

## 6. `schedule.create`

`schedule.create.item` accepts optional `primary_location` using Section 4.

### 6.1 Inline-create identity

For `mode=create`:

- `location_id` is derived with ordinary row role `location` and request path
  `/item/primary_location/location`;
- `item_location_id` is derived with row role `item_location` and request path
  `/item/primary_location`; and
- both location timestamps and the item-location timestamp equal the accepted
  `created_at_utc`.

### 6.2 Reference identity

For `mode=reference`, the supplied `location_id` is retained and only
`item_location_id` is derived from `/item/primary_location`. The referenced row is
resolved after compatible replay and schema/contract preflight, inside the same
transactional snapshot used for insertion and receipt snapshotting, and before any row
is inserted. This prevents validation and the persisted reference from observing
different canonical-location states.

### 6.3 Atomic result

The primary location is inserted inside the existing one-transaction schedule bundle.
Failure in location validation or persistence rolls back the item, anchors, recurrence,
policies, provenance, work, audit, and receipt.

When `item.primary_location` was supplied, fresh success, dry run, and compatible
replay return `primary_location` using Section 5. The stored receipt binds the normalized
authoring request, resolution mode, canonical location snapshot, both location
identities, and timestamps. Requests that omit the field omit the response property and
retain the prior schedule-create response shape.

## 7. `schedule.update`

`schedule.update.patch` accepts optional `primary_location`:

- omission retains the current primary location;
- JSON `null` clears it;
- `mode=reference` replaces it with an existing location; and
- `mode=create` replaces it with a newly created canonical location.

The update remains valid for both active scheduled events and open scheduled tasks
under the existing local-instant Version 1 command boundary.

### 7.1 Semantic comparison

Before mutation, the command loads the current version's primary location.

- `null` is a no-op when none exists.
- `reference` is a no-op when its `location_id` equals the current location ID.
- `create` is a no-op when every requested/absent canonical field exactly equals the
  current canonical location fields. Timestamps, metadata, and item-location identity
  do not participate.
- Otherwise the patch changes canonical item truth.

Inline `create` never searches other global location rows for equal content. If it does
not match the current primary location, a fresh canonical location is created even if
an unrelated equal location happens to exist.

When a location patch is semantically equal but another patch dimension creates a new
item version, the current primary location is copied forward normally; no new canonical
location is created and `primary_location` is not a changed dimension.

### 7.2 Replacement and clearing

Every truth-changing location update creates exactly one next item version. Existing
non-primary location roles are copied forward unchanged. The copied primary role is
removed from the successor set before the replacement is inserted or the clear is
finalized.

For an inline replacement:

- new `location_id` derives from row role `location` at
  `/patch/primary_location/location`; and
- new `item_location_id` derives from row role `item_location` at
  `/patch/primary_location`.

For a reference replacement, only the new item-location identity is derived. Clearing
creates neither identity.

The fixed changed-dimension order becomes `item`, `primary_location`,
`scheduled_time`, `recurrence`, `delivery`, `reminders`. Location-only truth change
uses the existing `schedule_updated` receipt effect unless work also changes for an
independent existing reason.

### 7.3 Conditional response

When the patch includes `primary_location`, fresh success, dry run, no-op, and replay
return:

```json
{
  "primary_location_change": {
    "effect": "created|replaced|cleared|retained",
    "requested_mode": "create|reference|clear",
    "previous_location_id": null,
    "current": null
  }
}
```

`previous_location_id` is a string or `null`. `current` is the Section 5 view or
`null`. `created` means no primary location existed and one now does; `replaced` means
the location ID changed; `cleared` means one existed and none remains; `retained` is a
semantic no-op. The receipt binds this complete result. When the patch omits
`primary_location`, the property is omitted from the response and receipt result.

## 8. Read and Operator Projections

### 8.1 `schedule.show`

The `include` enum gains `primary_location`. When selected, the top-level response
contains `primary_location` as the Section 5 view or `null`, and `included` contains
`primary_location`. When not selected, the top-level property is omitted. The complete
legacy `item.locations` collection remains available and retains its existing catalog
shape.

### 8.2 `agenda.show`

The agenda `include` enum gains `primary_location`. When selected, every returned entry
contains `primary_location` as the current item-version Section 5 view or `null`.
Recurring entries for one item repeat the same current primary-location view; location
does not become occurrence identity. The include choice remains bound into the agenda
query hash and cursor through existing request normalization.

### 8.3 `schedule.build`

The countdown builder accepts optional `primary_location` using Section 4, validates
it without resolving or writing, and copies its public authoring JSON value unchanged to generated
`schedule_create_request.item.primary_location`. It does not resolve a reference,
derive location IDs, geocode, or write. The eventual `schedule.create` command owns
those effects and binds the Section 4.3 internal normalization/version facts.

### 8.4 Compact projection

Compact schedule-create output includes optional `primary_location` exactly when the
full create response contains it. Compact schedule-show includes it exactly when the
underlying read requested it. The value is the complete Section 5 view or `null`; a
compact renderer must not reduce it to an unbound label.

## 9. Interaction With Existing Schedule Semantics

- Primary-location authoring does not alter `scheduled_time`, recurrence seed, timezone,
  timezone-database version, UTC resolution, reminder boundaries, or materialization
  range.
- Location changes do not cause occurrence-provenance regeneration.
- Existing notification work remains retained or otherwise classified solely by the
  current notification freshness contract. Location difference is not a Version 1
  notification cancellation reason.
- Schedule cancellation and every unrelated version-creating mutation copy the current
  primary location forward under the ordinary supporting-set rule.
- Archiving does not create a new item version or rewrite location rows.
- A future governed advisory may bind a location snapshot and define its own stale-work
  behavior; this capability does not anticipate that behavior in current reminder work.
- Delivery targets, `target_ref`, and location `provider_ref` are unrelated facts.

## 10. Validation and Failure Ordering

Primary-location validation fits the existing command order:

1. closed request shape and authoring-form validation;
2. command identity and compatible replay;
3. schema/runtime capability preflight;
4. actor and target-item validation;
5. update lifecycle and target-version freshness;
6. reference resolution and canonical inline-field validation;
7. complete successor normalization and no-op detection;
8. ordinary recurrence, notification, work, audit, and receipt derivation; and
9. one atomic commit plus receipt-bound readback verification.

Compatible replay occurs before a referenced location is resolved again. Fresh
reference to a missing row fails `referenced_row_not_found` on the exact
`item.primary_location.location_id` or `patch.primary_location.location_id` field.
An existing referenced row that cannot satisfy the clean view fails
`semantic_conflict` on that same exact field.

Malformed mode, fields, coordinates, coordinate pairing, enum, or string content fails
`invalid_request` at the narrowest primary-location field. A field valid only for the
other mode fails `unsupported_field` at its narrowest path. Storage constraint or
receipt/readback contradiction fails `runtime_failure` and cannot leave a partial
bundle.

## 11. Receipt, Audit, and Replay

The canonical schedule request semantic facts include the normalized primary-location
authoring or patch value when supplied. They omit it when absent.

Fresh create audit evidence adds `location_id` and `item_location_id` when authored.
Fresh truth-changing update audit evidence adds previous/current location IDs and the
location effect. A location no-op writes no item version or audit under existing
schedule-update rules, but the command receipt records `primary_location_change` with
`effect=retained`.

Dry run derives the same would-be identities, snapshots, effects, and receipt facts as
fresh commit and writes nothing. Compatible replay returns stored identities and
snapshots byte-for-byte; it does not recompute inline identity, re-read a referenced
location, or substitute later metadata.

## 12. Explicit Non-Goals

Version 1 does not provide:

- free-text place resolution, geocoding, reverse geocoding, or timezone inference;
- global semantic location deduplication or an address-book search command;
- mutation of an existing canonical location;
- public authoring of non-primary roles;
- occurrence-specific location overrides;
- automatic location inheritance across `part_of` or temporal bindings;
- deriving event time from location timezone;
- travel-time, route, map, weather, or proximity computation;
- delivery routing from physical or virtual location facts;
- non-canonical metadata authoring; or
- contextual-advisory execution.

## 13. Contract and Implementation Acceptance

Before runtime implementation, the schemas and fixtures must prove:

1. closed create/reference authoring forms;
2. paired, bounded decimal-string coordinates;
3. create, reference, replace, clear, retained, and missing-reference examples;
4. conditional create/update/read/projection response properties;
5. unchanged legacy request validity when location fields are absent; and
6. exact cross-file references under Draft 2020-12.

Implementation acceptance additionally requires executable proof that:

1. inline create atomically persists one canonical location and one primary item role;
2. reference create links an existing row without copying or mutating it;
3. replacement and clear create exactly one item version and preserve non-primary roles;
4. exact semantic create/reference no-ops create no location, item version, or audit;
5. unrelated item/schedule mutations copy the primary location forward;
6. create/update failure injection leaves no partial location or schedule bundle;
7. dry run and replay return deterministic location evidence without writes or
   environmental re-resolution;
8. `schedule.show`, `agenda.show`, builder output, and compact output honor their
   conditional projection rules;
9. location-only change does not regenerate recurrence provenance or cancel otherwise
   current notification work;
10. schedule anchor timezone remains unchanged when location timezone differs; and
11. `system.info` advertises the complete capability family only with all schemas,
    fixtures, handlers, projections, and tests present.
