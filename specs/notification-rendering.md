# Spine Deterministic Notification Rendering

Status: Implemented v1 (introduced on schema 9; active on schema 11)
Scope: Deterministic, concise, natural-language rendering of ordinary notification-reminder work at attempt start
Authority: Normative design target for notification prose and its per-attempt evidence; scheduling, work, delivery, and item truth remain owned by their existing contracts

## 1. Purpose

Spine already knows why a reminder exists, which item and occurrence it targets, when
delivery becomes eligible, where the scheduled item occurs, and whether delivery work
is still actionable. The delivery adapter currently needs a trustworthy way to turn
those facts into concise prose such as:

```text
Reminder: Tee time @ Lakeridge at 2 PM tomorrow
Reminder: Tee time @ Lakeridge in 1 hour
```

Natural wording does not require nondeterministic generation. This contract defines a
versioned pure renderer whose inputs, phrase selection, time quantization, formatting,
and persisted output are reproducible and auditable.

The renderer is downstream of canonical scheduling. It does not alter item state,
recurrence, notification policy, opportunity, work, route, or attempt eligibility. It
does not use a model, tool, network lookup, geocoder, or channel history.

## 2. Authority and Boundary

The following authorities remain unchanged:

- `specs/notifications.md` owns notification intent, opportunities, materialized work,
  reconciliation, and attempt-start freshness.
- `specs/recurrence.md` owns occurrence selection and occurrence provenance.
- `specs/schedule-primary-location.md` and `specs/ontology.md` own current primary
  location facts.
- `side_effect_attempts` remains Spine's only adapter-result/send ledger.
- A delivery adapter owns transport encoding and the external send, but MUST send the
  exact persisted rendered body supplied by Spine.

This contract introduces one logical immutable rendering artifact for an ordinary
notification attempt. That artifact is request evidence linked one-to-one to a
`side_effect_attempts` row; it is not an attempt ledger, delivery result, policy,
notification intent, or reusable item description.

Rendering MUST occur only after the existing work, policy, occurrence, binding,
lifecycle, route, and late-handling gates grant attempt-start admission.
`attempt-start admission` is the transient pre-persistence decision that the start may
be prepared; it is not an attempt status or durable ledger fact. No rendered body
authorizes a send by itself.

## 3. Versioned Profile

The first profile has these constants:

- `rendering_contract=spine.notification-rendering.v1`
- `rendering_profile=spine.notification-rendering.concise-en-ca.v1`
- `input_normalization_version=spine.notification-rendering-input.v1`
- `canonical_json_version=spine.canonical-json.v1`

The v1 capability is atomic. A runtime MUST NOT advertise
`spine.notification-rendering.v1` unless it implements the input resolver, pure
renderer, immutable rendering evidence, attempt-envelope binding, readback, failure
semantics, and conformance vectors together.

The schema-11 runtime implements and advertises all four constants, persists rendering
evidence in `notification_renderings`, binds OpenClaw request envelopes to that
evidence, and exposes it through `schedule.show` attempt readback.

The v1 authoring surfaces do not accept a rendering profile or template. Advertising
the capability selects the single profile above for every supported ordinary reminder.
A later contract may add explicit locale or profile selection without changing the v1
meaning.

## 4. Supported Work and Required Source Facts

The v1 renderer accepts only an actionable `work_instances` row with
`work_kind=notification_reminder`. It renders the item target, not the reminder's
nominal eligibility instant. For a reminder eligible one hour before a 2 PM event, the
target is 2 PM and the phrase may be `in 1 hour`.

The normalized rendering source input contains exactly:

- `attempt_id`, `attempted_at_utc`, `work_instance_id`,
  `notification_opportunity_id`, and `notification_intent_id`;
- `item_id`, current decimal-string `rendered_item_version`, and
  `item_type=event|task`;
- normalized current `title`;
- `anchor_role=event_start|task_due`;
- canonical `target_scheduled_fact` and resolved `target_at_utc` when the target has an
  instant;
- `display_time_basis=local_date|local_instant|instant_utc`;
- `display_timezone` and `timezone_database_version` under Section 5;
- current recurrence revision, occurrence key, and occurrence-provenance identities
  when the target is occurrence-bound;
- current relative-temporal-binding identity and revision when the target task due
  anchor is governed by an active `follow_source` binding;
- current primary-location identity, item-location identity, `location_kind`, and
  normalized `location_label`, or explicit `primary_location=null`.

The four Section 3 constants bind every rendering hash and identity but are not
duplicated inside the normalized source-input object. The resolved rendering evidence
adds `delta_seconds` when applicable, `phrase_kind`, and the exact derived phrase facts
from Sections 6 through 8. Derived values are never inputs to their own derivation.

`attempted_at_utc` is the proposed start time selected during attempt-start admission
and persisted if the atomic start commit succeeds. It is the rendering reference
instant. The nominal reminder time MUST NOT be substituted for it: a late but still
permitted attempt must describe the target truthfully at the time the send is actually
started.

For recurring items, the renderer uses the selected current occurrence's expressed
target and active provenance, never the recurrence seed or another occurrence. For a
task with a current `follow_source` binding, it uses the current concrete task due
anchor after binding freshness succeeds; it does not render directly from an
unmaterialized source expression.

## 5. Display Time Authority

Calendar language is evaluated in the scheduled target's time basis, never in the
primary location's timezone and never in an adapter-local timezone.

- `local_instant` uses the target timezone and its pinned concrete timezone database
  version.
- `local_date` uses the target timezone and pinned concrete timezone database version
  for calendar-date comparison, but renders no clock time.
- `instant_utc` uses `display_timezone=UTC` and
  `timezone_database_version=null`.

The target and `attempted_at_utc` are converted into `display_timezone` before local
date comparisons. A named timezone conversion MUST use the pinned database version;
the runtime MUST NOT silently substitute its current system version. Unavailable
pinned timezone data fails closed.

`today`, `tomorrow`, and `yesterday` compare local calendar dates. They do not mean
elapsed 24-hour periods. This keeps wording stable across daylight-saving transitions.

## 6. Input Normalization

The renderer applies these rules before phrase selection:

1. Parse all instants as canonical UTC `Z` instants under Spine's existing rules.
2. Normalize `title` and `location_label` by trimming leading and trailing Unicode
   whitespace and replacing each non-empty run of Unicode whitespace with one ASCII
   space.
3. Reject an empty normalized title. A location whose current label normalizes to an
   empty value fails closed; the renderer does not fall back to a raw address.
4. Reject any remaining Unicode control character in either value. The renderer does
   not interpret markup, mentions, URLs, or adapter escape sequences.
5. Compute `delta_seconds = target_at_utc - attempted_at_utc` as an exact signed integer
   for instant-bearing targets.
6. Derive all remaining phrase facts using Sections 7 and 8.

The output is plain Unicode text. It MUST NOT exceed 1,024 Unicode scalar values. An
oversized result fails closed; v1 never silently truncates canonical item or location
facts.

## 7. Temporal Phrase Selection

The v1 constants are:

- `near_now_seconds=30`
- `relative_window_seconds=21600` (six hours)

For an instant-bearing future target, apply the first matching branch:

1. `delta_seconds <= 30`: `now`.
2. `30 < delta_seconds <= 21600`: `future_relative`.
3. otherwise: `future_calendar`.

For a past target, use `absolute(delta_seconds)` and apply the first matching branch:

1. `absolute(delta_seconds) <= 30`: `now`.
2. `30 < absolute(delta_seconds) <= 21600`: `past_relative`.
3. otherwise: `past_calendar`.

For a `local_date` target, the phrase kind is always `date_calendar`; no duration or
clock time is invented.

The relative branch takes precedence over local-date labels. An event one hour away
across midnight renders `in 1 hour`, while an event 24 hours away renders with
`tomorrow` when its target local date is the next calendar date.

### 7.1 Relative-duration quantization

For a relative branch, compute:

```text
display_minutes = floor((absolute(delta_seconds) + 30) / 60)
```

`display_minutes` is therefore nearest-minute, half-up. It is at least `1` because the
relative branch excludes the near-now range. Render:

- fewer than 60 minutes as `{minutes} minute|minutes`;
- an exact multiple of 60 as `{hours} hour|hours`; or
- otherwise as `{hours} hour|hours {minutes} minute|minutes`.

No seconds are displayed. This quantization affects presentation only; it does not
round or mutate the scheduled anchor, opportunity, eligibility time, or work identity.

### 7.2 Calendar labels

Let `reference_date` be the local calendar date of `attempted_at_utc` and
`target_date` the target's local calendar date:

- same date: `today`;
- one date later: `tomorrow`;
- one date earlier: `yesterday`;
- two through six dates later: the full weekday name;
- two through six dates earlier: the full weekday name;
- any other date in the reference year: `on {full month} {day}`; or
- a date in another year: `on {full month} {day}, {four-digit year}`.

Weekday and month names are the fixed English names defined by the profile, not host
locale output.

### 7.3 Clock formatting

`concise-en-ca.v1` uses a 12-hour clock with uppercase `AM` or `PM`, one ASCII space
before the marker, and no leading zero. Exact hours omit `:00`; other times include
two-digit minutes. Examples are `2 PM`, `9:05 AM`, and `12:30 PM`. Seconds are never
shown and do not alter the underlying scheduled fact.

## 8. Deterministic Templates

The optional location clause is:

- empty when there is no current primary location;
- ` via {location_label}` when `location_kind=virtual`; or
- ` @ {location_label}` for every other supported location kind.

The renderer does not geocode, infer a venue, select among non-primary locations, or
use location timezone as time authority.

For events, the exact templates are:

- `future_relative`: `Reminder: {title}{location_clause} in {duration}`
- `future_calendar`: `Reminder: {title}{location_clause} at {clock} {calendar_label}`
- `now`: `Reminder: {title}{location_clause} is starting now`
- `past_relative`: `Reminder: {title}{location_clause} started {duration} ago`
- `past_calendar`: `Reminder: {title}{location_clause} started at {clock} {calendar_label}`
- `date_calendar`: `Reminder: {title}{location_clause} {calendar_label}`

For tasks, the exact templates are:

- `future_relative`: `Reminder: {title}{location_clause} is due in {duration}`
- `future_calendar`: `Reminder: {title}{location_clause} is due at {clock} {calendar_label}`
- `now`: `Reminder: {title}{location_clause} is due now`
- `past_relative`: `Reminder: {title}{location_clause} was due {duration} ago`
- `past_calendar`: `Reminder: {title}{location_clause} was due at {clock} {calendar_label}`
- `date_calendar`: `Reminder: {title}{location_clause} is due {calendar_label}`

No punctuation is appended after the template. An adapter MAY perform transport-level
escaping required to preserve these characters as plain text, but it MUST NOT rewrite,
summarize, embellish, translate, or add contextual facts to `body_text`.

## 9. Rendering Identity and Durable Evidence

One started notification attempt has exactly one immutable notification rendering. A
conforming storage model persists at least:

- `notification_rendering_id` and `attempt_id` with a one-to-one uniqueness rule;
- all four Section 3 version constants;
- `rendering_input_hash` and `rendered_content_hash`;
- exact `body_text`;
- all source, target, location, occurrence, binding, reference-time, delta, phrase,
  and display facts listed in Section 4; and
- `created_at_utc`, equal to the attempt's `attempted_at_utc`.

`rendered_item_version` is the current coordination-item version whose title, target,
and location facts were used to construct the body. It MUST be revalidated as current
inside the atomic start transaction. It is not an alias for
`side_effect_attempts.source_item_version`; that existing field retains the narrower
projection-version meaning defined by `specs/ontology.md` and remains absent for an
ordinary non-projection notification attempt. The rendering's `work_instance_id` MUST
equal the linked attempt's `work_instance_id`. `rendered_item_version` MAY differ from
that work row's `item_version` when existing notification rules legitimately retained
the work across an item-version change; the former identifies the current facts used
for prose and the latter retains the work's scheduling provenance.

`rendering_input_hash` is the lowercase SHA-256 digest of Spine canonical JSON. Its
preimage contains exactly
`derivation_version=spine.notification-rendering-input-hash.v1`, the four Section 3
constants, and `source_input` containing the normalized Section 4 source-input object.

`rendered_content_hash` is the lowercase SHA-256 digest of Spine canonical JSON
containing exactly `derivation_version=spine.notification-rendering-content-hash.v1`,
the four Section 3 constants, `rendering_input_hash`, `phrase_kind`, the derived phrase
facts, and exact `body_text`.

`notification_rendering_id` uses prefix `notification_rendering` over Spine canonical
JSON containing exactly `derivation_version=spine.notification-rendering-id.v1`, the
four Section 3 constants, `attempt_id`, `rendering_input_hash`, and
`rendered_content_hash`.

The adapter request envelope bound by `side_effect_attempts.request_payload_hash` MUST
contain `notification_rendering_id`, `rendered_content_hash`, and exact `body_text`.
The immutable rendering row and the `attempt_status=started` row MUST commit in one
transaction before the external send starts. Failure to persist either commits
neither and permits no send. Attempt-start admission is not durable and no side-effect
attempt exists until this atomic commit succeeds.

Compatible replay of the same `attempt_id` reuses the byte-identical stored rendering
and MUST NOT create a second rendering or rerender against a later clock or newer item
facts. Whether the existing attempt lifecycle permits another transport call remains
governed by that lifecycle; this contract does not authorize one. A genuine retry is a
new side-effect attempt and receives a fresh `attempted_at_utc`, freshness check,
rendering, and rendering identity; its natural time phrase may therefore differ from
the prior attempt while retaining the same work and opportunity identities.

## 10. Processing Order and Fail-Closed Semantics

For a runtime advertising this contract, ordinary notification processing is ordered:

1. load the selected work and canonical route;
2. apply existing work, lifecycle, policy, opportunity, occurrence, temporal-binding,
   routing, and late-handling gates;
3. resolve the current target, item version, title, and current primary location;
4. grant attempt-start admission and assign the proposed `attempt_id` and
   `attempted_at_utc`;
5. normalize and render;
6. persist the immutable rendering and started side-effect attempt atomically;
7. invoke the adapter with the exact stored body; and
8. persist the ordinary attempt outcome.

The renderer is not invoked when an earlier gate skips, cancels, or rejects the work.
Rendering failures occur before external contact and use one of these closed codes:

- `notification_rendering_unsupported_work`
- `notification_rendering_source_unresolved`
- `notification_rendering_timezone_database_unavailable`
- `notification_rendering_invalid_text`
- `notification_rendering_output_too_large`
- `notification_rendering_persistence_conflict`

A rendering failure does not change the notification policy or work identity and does
not claim delivery. Retry eligibility remains governed by the existing work/attempt
lifecycle rather than by this renderer.

## 11. Readback and Operator Evidence

Canonical schedule readback with delivery attempts included MUST expose the rendering
linked to each notification attempt created under this capability. Historical attempts
that predate capability activation retain their existing attempt evidence and MUST NOT
be assigned reconstructed prose. The rendering view includes at least rendering
identity, profile, exact body, content hash, phrase kind, attempt reference time, target
UTC/local facts, display timezone and timezone database version, rendered item version,
and current-location snapshot used for that attempt.

Rendering evidence is nested on the corresponding attempt projection under the
existing `include=attempts` behavior defined by `specs/schedule-show.md`; it does not
add an `include=renderings` value or a parallel top-level collection. The matching
response-schema extension is part of the atomic rendering capability and MUST be
declared before these fields are emitted.

Readback never regenerates old prose. It projects the immutable stored rendering.
Compact operator receipts MAY omit the body and detailed phrase evidence; compact
receipt design remains owned by `specs/schedule-operator-tools.md` and MUST NOT be
conflated with outbound reminder prose.

Rendered bodies may contain private item and location facts. They inherit the access,
retention, export, and audit controls of the attempt evidence to which they are bound.

## 12. Relationship to Contextual Advisories

This renderer produces ordinary deterministic reminder prose. A contextual advisory
may later produce useful generated content from governed tools and model reasoning,
but that is a separate work family and authority chain defined by
`specs/contextual-advisories.md`.

An advisory outage, timeout, rejection, or stale result MUST NOT cause an ordinary
reminder to become model-dependent. Where a product flow requests both, this profile
is the reliable fallback body unless a separately accepted advisory outcome has
already produced authorized derivative notification work. Generated advisory prose
must never be smuggled into this renderer's inputs.

## 13. Non-Goals

The v1 profile does not define:

- LLM-written, tool-enriched, or weather-aware prose;
- per-user templates, arbitrary format strings, tone controls, or additional locales;
- channel-specific markdown, mentions, reactions, or rich cards;
- operator/chat mutation receipts;
- geocoding, location inference, travel-time estimates, or venue enrichment;
- schedule-authoring rounding or confirmation behavior;
- delivery batching or aggregation;
- rendered text as policy, work, opportunity, or item identity; or
- production-adapter enablement or a real send.

## 14. Required Conformance Vectors

The first machine-readable contract family MUST publish exact normalized inputs,
preimages, hashes, bodies, and failure oracles for at least:

- an event at Lakeridge 24 hours away rendering `at 2 PM tomorrow`;
- the same event one hour away rendering `in 1 hour`;
- a 10-minute repeat-window opportunity rendering `in 10 minutes`;
- a task rendering `is due in 1 hour`;
- a target within the near-now boundary;
- future and past relative half-minute quantization boundaries;
- today, tomorrow, yesterday, weekday, same-year date, and cross-year date labels;
- a daylight-saving transition proving calendar-label use of pinned target timezone;
- an `instant_utc` target using UTC;
- a local-date event and task with no invented clock;
- no location, physical location using `@`, and virtual location using `via`;
- a retained work row rendered with the current location after a location-only update;
- an occurrence-bound reminder using the selected occurrence rather than the seed;
- a current follow-source task and a stale binding rejected before rendering;
- permitted late execution rendering from `attempted_at_utc` rather than nominal time;
- compatible replay returning the identical stored rendering;
- a new retry receiving a new rendering while retaining work identity;
- request-envelope binding of rendering id, content hash, and exact body;
- unavailable pinned timezone data, invalid text, oversized output, and atomic
  persistence failure; and
- readback returning stored prose without rerendering.

Two conforming implementations given the same normalized input and version constants
MUST produce byte-identical `body_text`, hashes, rendering identity, and phrase facts.

## 15. Acceptance Criteria

This draft is ready for implementation planning only when:

1. the pure renderer can be implemented without consulting adapter, model, network,
   geocoder, system locale, wall clock, or unstored timezone defaults;
2. time wording is derived from the persisted attempt reference and canonical current
   target under a pinned display-time authority;
3. rendering has no effect on schedule, opportunity, work, route, or delivery outcome
   identity;
4. every attempted send is bound to exactly one immutable, readable rendering and
   request hash before external contact;
5. replay and retry behavior are distinct and deterministic;
6. readback exposes enough evidence to verify exactly what was sent without raw SQL;
7. ordinary reminder delivery remains useful without an LLM or contextual-advisory
   subsystem; and
8. the Section 14 vectors prove byte-for-byte agreement and every closed failure.
