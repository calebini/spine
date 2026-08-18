# Spine Canonical Schedule Readback

Status: Implemented command contract
Contract version: `spine.schedule-show.v1`

## 1. Purpose

`schedule.show` is the canonical operator-facing verification view for one scheduled event or task. It joins current coordination truth, scheduled anchors, recurrence identity, notification policies and intents, materialized work, delivery routes, and side-effect attempts without requiring an agent to know Spine's relational schema or issue raw SQL.

The command is read-only. It creates no item version, policy, work row, audit row, receipt, projection, or side-effect attempt and invokes no adapter.

This command remains the canonical deep readback for one known item. The implemented cross-item `agenda.show` range view is specified separately in `specs/schedule-operations.md` and does not replace this evidence surface.

## 2. Request

The request requires `item_id`. Optional fields are:

- `include`: a unique array containing any of `policies`, `work`, `attempts`, `relations`, `temporal_bindings`, and, when the runtime advertises `spine.schedule-primary-location.v1`, `primary_location`; omission includes policies, work, and attempts;
- `notification_policies_limit`: integer or decimal string in `0..100`, default `100`;
- `work_instances_limit`: integer or decimal string in `0..1000`, default `1000`; and
- `side_effect_attempts_limit`: integer or decimal string in `0..1000`, default `1000`.

The exact request shape is `contracts/schemas/schedule-show-request.schema.json`. An unsupported include value, duplicate include value, invalid limit, or extra field fails closed with `invalid_request` or `unsupported_field` and no partial effect.

The CLI accepts the ordinary JSON request transport. It also accepts the equivalent convenience form:

```bash
"$SPINE_COMMAND" --db "$SPINE_DB" \
  --item-id "$ITEM_ID" \
  --include policies,work,attempts \
  --pretty schedule show
```

`--item-id` and `--include` are transport projections into the same canonical request. They are valid only for `schedule.show` and conflict with the same field supplied in an input object.

CLI `--compact` applies the additive `spine.schedule-compact.v1` projection defined by `specs/schedule-operator-tools.md`. Compact mode ensures policy and work detail are included so its required identity fields are populated. Omitting the option returns this contract's unchanged full response.

## 3. Current Item and Time View

The response embeds the current `item.show` shell, common version, event/task detail, locations, and subject-role view under `item`, excluding the separately returned notification-policy collection. It does not return a historical item version as current.

When `primary_location` was explicitly included, the response additionally returns the
clean top-level view or JSON `null` defined by `specs/schedule-primary-location.md`.
The property is omitted otherwise. This projection does not remove or rewrite the
granular `item.locations` collection.

`scheduled_times` is ordered by the closed anchor-role order:

1. `event_start`;
2. `event_end`;
3. `task_due`; and
4. `task_defer_until`.

Every element returns the stored anchor identity and canonical fields. A local instant additionally returns its timezone, concrete stored timezone-database version, and UTC resolution evidence when available.

For an item authored by `schedule.create`, the matching initial start/due anchor uses the persisted authoring receipt's UTC instant, offset, and resolution kind and reports `resolution_source=authoring_receipt`. This remains readable if the host later installs a different timezone database. Other local instants resolve only against the exact stored timezone-database version and report `resolution_source=pinned_timezone_database`. If that version is not available, readback preserves the stored local facts and reports `resolution_state=unavailable` with a stable reason; it MUST NOT silently resolve with different timezone data. Fixed UTC anchors report `resolution_source=stored_anchor`.

When current recurrence exists, `recurrence` is the complete normalized current recurrence-set revision under `spine.recurrence.contract.v1`. `schedule.show` does not expand virtual occurrences; callers use `item.occurrences` for bounded occurrence expansion.

## 4. Policy, Work, Attempt, and Route Evidence

`notification_policies` contains the complete current-version policy objects up to the accepted limit. Each policy carries its stable `notification_intent_id`, version-scoped public `notification_policy_id` alias, normalized schedule, routing identity, and lifecycle status. The canonical table primary key remains `notification_policies.policy_id`; `notification_policy_id` is the intentional public alias and is also the canonical foreign-key column name on `work_instances`.

`work_instances` contains item-linked durable work across item versions, ordered by `eligible_at_utc` and `work_instance_id`. `side_effect_attempts` contains attempts bound to those work rows, ordered by `attempted_at_utc` and `attempt_id`; unrelated candidate-action or projection attempts for the same item are outside this schedule-delivery view. Counts and lifecycle summaries cover all matching rows even when a requested detail collection is omitted or truncated.

Every included collection returns its accepted limit, total count, and truncation boolean. A zero limit returns no elements while retaining the total count and lifecycle summary. Work and attempt detail queries fetch at most the requested limit plus one truncation sentinel; aggregate counts are computed in the ledger. Public work/attempt detail limits are at most 1000.

`delivery_targets` contains one entry per distinct target referenced by current policies or item work, ordered by `delivery_target_id`. `current_snapshot` is the current canonical delivery-target row. When the item was authored by `schedule.create`, `authored_snapshot` is the immutable routing snapshot stored in that receipt, and `routing_facts_match_authored` compares delivery target id, channel, adapter, and target reference. The command never substitutes the current route for historical authoring evidence.

When requested, `relations` returns ordinary stored rows touching the item and `temporal_bindings` returns binding headers, latest immutable revisions, computed state, source evidence, and exact reconciliation inputs. These are granular readback facts; the concrete scheduled anchor remains present independently.

The optional `authoring_receipt` summary identifies the persisted `schedule.create`, `schedule.related_task.create`, `event.create`, or `task.create` receipt that created the item. It is receipt evidence, not delivery evidence.

## 5. Explicit Lifecycle Model

The response always returns four separate lifecycle dimensions:

- `authored.state=committed` means the item exists as canonical ledger truth; it does not imply opportunity expansion, work, or delivery.
- `opportunities.state` is `expanded`, `expanded_zero_selected`, `not_requested`, or `evidence_not_persisted`.
- `work.state` is `materialized`, `completed_zero_selected`, `not_requested`, or `none`, with complete status counts for `eligible`, `in_progress`, `succeeded`, `failed`, and `cancelled`.
- `delivery.attempt_state` is `not_attempted` or `attempted`; `delivery.outcome_state` is independently `none`, `pending`, `succeeded`, `failed`, `rejected`, or `mixed`, with complete attempt-status counts.

`schedule.create` continues to author only. Its response and receipt report delivery as not attempted by that command. A later `schedule.show` may report worker-created attempt and outcome evidence without rewriting the authoring receipt.

Notification opportunities are virtual and are not independently persisted. Readback may prove expansion from a `schedule.create` materialization receipt or from materialized work's stable opportunity identities. If neither durable source exists, `opportunities.state=evidence_not_persisted`; the command MUST NOT infer that expansion never occurred.

Delivery outcome is derived only from `side_effect_attempts`:

- no attempts: `attempt_state=not_attempted`, `outcome_state=none`;
- only started attempts: `attempt_state=attempted`, `outcome_state=pending`;
- exactly one populated terminal status and no started attempt: that terminal status is the outcome; and
- multiple populated terminal statuses, or started plus terminal evidence: `outcome_state=mixed`.

Work status and delivery outcome are reported separately. A succeeded work row does not substitute for a missing side-effect attempt, and an attempt does not by itself rewrite work state.

## 6. Determinism and Failure

The exact response shape is `contracts/schemas/schedule-show-response.schema.json`. Arrays use the deterministic order specified above. Integer counts and versions are returned as canonical decimal strings.

Unknown items fail through the shared structured item-not-found path. Missing referenced route or invalid stored lifecycle evidence fails closed as invalid readback state. Readback never repairs inconsistent evidence and never writes while handling failure.

## 7. Acceptance

The contract is accepted when executable tests prove that:

1. one `schedule.create` item can be verified without SQL, including current item facts, resolved local and UTC time, concrete timezone-database version, policy/intent identity, work identity/status, and delivery route snapshots;
2. invoking `schedule.show` creates no canonical or evidence rows;
3. included collections are bounded and deterministic while total counts remain complete;
4. authoring, opportunity expansion, work materialization, delivery attempt, and delivery outcome remain distinct;
5. a started attempt reads as pending and a later succeeded attempt reads as succeeded;
6. the direct CLI `--item-id` and `--include` form maps to the same request; and
7. request and runtime response validate under Draft 2020-12 schemas; and
8. a runtime advertising the primary-location family returns its clean view only when
   explicitly included, while leaving `item.locations` intact.
