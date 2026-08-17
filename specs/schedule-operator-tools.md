# Spine Schedule Operator Tools

Status: Implemented command and transport contracts

Contract versions:

- `spine.schedule-countdown-builder.v1`
- `spine.schedule-countdown-builder-response.v1`
- `spine.schedule-compact.v1`

## 1. Purpose

This contract defines two additive operator conveniences over the canonical scheduling surfaces:

1. `schedule.build` deterministically compiles the common intent “event after a relative delay, then remind me repeatedly until it starts” into an ordinary `spine.schedule-create.v1` request.
2. CLI `--compact` projects successful `schedule.create` and `schedule.show` responses into one stable, audit-complete chat/operator shape.

Neither feature creates a new scheduling ontology. `schedule.create` remains the only writer in this flow, `schedule.show` remains the canonical aggregate readback, and their full JSON responses remain the default.

## 2. Relative Countdown Builder

`schedule.build` is read-only. It may verify an actor and resolve an existing active delivery target, but it creates no item, policy, opportunity, work, attempt, audit, or command-receipt row and invokes no adapter.

The exact request is `contracts/schemas/schedule-countdown-builder-request.schema.json`. It requires:

- `contract_version=spine.schedule-countdown-builder.v1`;
- the `command_id` and `actor_subject_id` that the generated `schedule.create` request will use;
- an explicit canonical `reference_time_utc` rather than an ambient clock;
- event title, timezone, timezone-database directive, positive event delay, positive reminder cadence, and delivery request.

`tests/fixtures/schedule_operator/countdown_builder_request.json` is the checked-in starting request for the two-hour/30-minute profile; `contracts/schedule-operator-fixture-manifest.json` binds it to the request schema.

Optional fields are `summary`, `source_ref`, event detail, `policy_key`, `reminder_start_before_seconds`, and `materialization_limit`. Event detail defaults to `all_day=false`; policy key defaults to `countdown`; reminder start defaults to the complete event delay; and materialization limit defaults to `1000`.

The reminder start MUST NOT exceed the event delay and MUST fit Spine's 366-day materialization-range bound. This ensures that the generated countdown does not begin before `reference_time_utc` and that its output is accepted by `schedule.create`. The complete stop-exclusive countdown opportunity count MUST fit the requested limit and the platform maximum of 1000. Invalid timezone, unavailable pinned timezone data, ambiguous or unrepresentable resulting time, invalid cadence, invalid route, or insufficient limit fails closed before any write.

The builder resolves `system_current` to the concrete installed timezone-database version and returns an explicit version directive in the generated request. A context-default route is likewise resolved to an explicit existing `delivery_target_id`. The generated local date/time, UTC event instant, route, bounded item-relative materialization range, and `created_at_utc` are therefore inspectable and stable before authoring.

The generated policy is a stop-exclusive `repeat_window` from `-reminder_start_before_seconds` through the event boundary with a `fixed_elapsed` cadence and `late_handling=skip`. Materialization uses `evaluated_at_utc=reference_time_utc`, the same item-relative window, and the accepted limit. For “event in two hours; every 30 minutes until the event,” the generated set contains four opportunities: now, +30 minutes, +60 minutes, and +90 minutes.

The exact response is `contracts/schemas/schedule-countdown-builder-response.schema.json`. `effect=schedule_create_request_built` means only that a valid request was compiled. It does not mean the item was authored or any work was materialized. The caller authors it by passing `schedule_create_request` unchanged to `schedule.create`.

## 3. Compact Operator Projection

The CLI option `--compact` is valid only for `schedule.create` and `schedule.show`. It is a deterministic projection of the already-produced canonical success response and performs no additional write. Failures retain the normal structured failure response. Omitting `--compact` returns the unchanged full command response.

The exact success shape is `contracts/schemas/schedule-compact-response.schema.json`. It always includes:

- item identity, type, current shell status, action, effect, authoring command ID, and command-receipt ID;
- scheduled time facts plus primary timezone and concrete timezone-database version;
- notification intent and policy IDs;
- complete work count, returned work IDs, and an explicit truncation flag;
- separate authored, opportunity, work, delivery-attempt, and delivery-outcome states; and
- delivery target ID, channel, destination source reference, and destination target reference.

`dry_run` is always explicit. A compact schedule-create preview reports `dry_run=true` and `lifecycle.authored=preview`; its returned IDs and work states are deterministic preview facts, not persisted evidence. Committed create/replay and all readback responses report `dry_run=false`.

`destination_source_ref` is the canonical delivery target's `adapter_name`; `destination_target_ref` is its `target_ref`. These names are projection labels and do not create alternate stored identities.

Compact `schedule.show` requires policy and work detail to populate its audit fields. The CLI therefore adds `policies` and `work` to the read request even when the operator's explicit `--include` contains only another collection. Canonical response limits still apply. `notification_policy_ids_truncated` and `work_instance_ids_truncated` explicitly identify bounded ID lists; their corresponding complete counts remain authoritative.

## 4. Lifecycle Meaning

The compact lifecycle is a projection of existing evidence, not a collapsed “done” boolean:

- `authored=committed` means canonical item/policy authoring exists and may be rendered as **saved**;
- `opportunities` reports expansion evidence and may be rendered as **calculated** or **expanded**;
- `work` reports durable materialization evidence and may be rendered as **queued** or **materialized**;
- `delivery_attempt` reports whether a worker wrote an attempt and may be rendered as **attempted** only when that evidence exists; and
- `delivery_outcome` reports no outcome, pending, succeeded, failed, rejected, or mixed evidence, and may be rendered as **delivered** only for a successful terminal outcome.

Operator projections MUST preserve the ordering of these meanings: saved is not queued, queued is not attempted, and attempted is not delivered. A renderer may produce concise prose such as `Saved; 4 reminders queued; delivery not attempted`, but it MUST derive every clause from the corresponding structured field and MUST NOT replace the canonical response or promote an earlier phase into a later one.

Fresh `schedule.create --compact` always reports `delivery_attempt=not_attempted` and `delivery_outcome=none`. Only later readback can expose worker delivery evidence.

Compact output is intended for routine acknowledgement and quick current-state inspection. Full `schedule.create` remains the inspection surface for normalized policy, opportunity, provenance, and work evidence. Full `schedule.show` with requested policies, work, and attempts remains the inspection surface for delivery claims, failures, cancellation, staleness, and any truncated compact identity list. Channel-specific prose, including WhatsApp formatting, is a renderer or adapter concern and does not create another Spine receipt contract.

## 5. Acceptance

This contract is accepted when executable tests prove that:

1. the two-hour/30-minute builder output validates as `schedule.create`, uses a concrete timezone-data version and explicit route, and creates exactly four bounded work rows when submitted;
2. repeated builder calls with identical input return identical output and write nothing;
3. ambiguous resulting local time, pre-reference countdown start, and insufficient materialization limit fail closed;
4. compact create and show responses validate under Draft 2020-12 and retain every required audit field;
5. compact readback preserves separate delivery attempt and outcome evidence; and
6. full JSON behavior remains unchanged when `--compact` is absent.
