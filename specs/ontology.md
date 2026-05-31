# Spine Ontology

Status: Draft v0.1.0  
Scope: First durable ontology and data model sketch for Spine

## 1. Ontology Goal

This document defines the first durable ontology for Spine.

It is intentionally a conceptual data model, not a migration. The goal is to make ownership, entity boundaries, and near-term compatibility clear before implementation.

## 2. Design Principles

The schema MUST be local-first, auditable, deterministic, and replayable.

The schema MUST prefer explicit records over hidden inference.

The schema MUST support family scheduling and task management over one shared coordination core.

The schema MUST treat external systems as projections or side-effect targets.

The schema MUST make locations and item relationships first-class.

## 3. Core Tables

### 3.1 coordination_items

Owns shared item identity and lifecycle shell.

Suggested fields:

- `item_id`
- `item_type`
- `current_version`
- `status`
- `created_at_utc`
- `updated_at_utc`
- `archived_at_utc`

Near-term `item_type` values:

- `event`
- `task`
- `project`
- `collection`

Anticipated values:

- `deadline`
- `routine`
- `reminder`
- `availability_block`

### 3.2 coordination_item_versions

Owns versioned canonical item facts common across item types.

Suggested fields:

- `item_id`
- `version`
- `title`
- `summary`
- `intent_hash`
- `normalized_fields_hash`
- `source_ref`
- `created_at_utc`
- `created_by_subject_id`

The pair `(item_id, version)` SHOULD be the primary identity for versioned facts.

### 3.3 event_details

Owns event-specific facts that do not generalize cleanly to tasks.

Suggested fields:

- `item_id`
- `version`
- `event_status`
- `all_day`
- `start_anchor_id`
- `end_anchor_id`
- `visibility`
- `attendance_policy_ref`

### 3.4 task_details

Owns task-specific facts that do not generalize cleanly to events.

Suggested fields:

- `item_id`
- `version`
- `task_status`
- `completion_state`
- `priority`
- `due_anchor_id`
- `defer_until_anchor_id`
- `completed_at_utc`
- `completed_by_subject_id`

### 3.5 coordination_item_relations

Owns the coordination graph.

Suggested fields:

- `relation_id`
- `source_item_id`
- `target_item_id`
- `relation_type`
- `relation_status`
- `created_at_utc`
- `created_by_subject_id`
- `metadata_json`

Likely `relation_type` values:

- `contains`
- `depends_on`
- `blocks`
- `related_to`
- `duplicates`
- `follows`
- `part_of`
- `causes`
- `satisfies`

`blocks` and `part_of` MAY be derived rather than stored if a future implementation can preserve deterministic query behavior.

## 4. Subjects and Groups

### 4.1 subjects

Owns canonical actors, people, agents, and durable identity anchors.

Suggested fields:

- `subject_id`
- `subject_kind`
- `display_name`
- `status`
- `created_at_utc`
- `updated_at_utc`

### 4.2 subject_groups

Owns households, teams, and other actor groupings.

Suggested fields:

- `group_id`
- `group_kind`
- `display_name`
- `status`
- `created_at_utc`
- `updated_at_utc`

### 4.3 subject_memberships

Owns subject-to-group membership history.

Suggested fields:

- `membership_id`
- `group_id`
- `subject_id`
- `role`
- `status`
- `starts_at_utc`
- `ends_at_utc`

Family scheduler mapping:

- household = subject group
- family member = subject with household membership
- event attendees = participation rows
- notification recipients = policy rows

## 5. Time Model

Time MUST be explicit and deterministic.

Not every item has the same relationship to time. The first epoch should support:

- exact start/end event
- all-day event
- due date/time
- due window
- defer or snooze until
- recurrence
- timeless task
- generated reminder or work instance
- timezone semantics

### 5.1 temporal_anchors

Suggested fields:

- `anchor_id`
- `anchor_kind`
- `local_date`
- `local_time`
- `timezone`
- `utc_instant`
- `window_start_utc`
- `window_end_utc`
- `recurrence_rule`
- `source`
- `created_at_utc`

Historical UTC values generated from temporal anchors MUST NOT be recomputed on read/replay.

## 6. Location Model

Locations MUST be first-class entities.

### 6.1 locations

Suggested fields:

- `location_id`
- `label`
- `kind`
- `address_text`
- `latitude`
- `longitude`
- `timezone`
- `provider_ref`
- `metadata_json`
- `created_at_utc`
- `updated_at_utc`

Likely `kind` values:

- `address`
- `place`
- `virtual`
- `relative`
- `unknown`

### 6.2 item_locations

Suggested fields:

- `item_location_id`
- `item_id`
- `location_id`
- `role`
- `created_at_utc`

Likely `role` values:

- `primary`
- `pickup`
- `dropoff`
- `meeting_link`
- `context`

## 7. Participation, Assignment, and Notification Policy

### 7.1 item_subject_roles

Owns subject roles on coordination items.

Suggested fields:

- `item_subject_role_id`
- `item_id`
- `subject_id`
- `role`
- `status`
- `created_at_utc`

Likely `role` values:

- `participant`
- `assignee`
- `watcher`
- `owner`
- `recipient`

### 7.2 notification_policies

Owns durable notification intent, not vendor delivery state.

Suggested fields:

- `policy_id`
- `item_id`
- `recipient_subject_id`
- `channel_preference_ref`
- `trigger_anchor_id`
- `quiet_hours_policy_ref`
- `status`
- `created_at_utc`

Generated reminders SHOULD become work instances rather than hidden scheduler state.

## 8. Work, Candidate Actions, and Attempts

### 8.1 work_instances

Owns generated domain work eligible for tickerd processing.

Suggested fields:

- `work_instance_id`
- `item_id`
- `work_kind`
- `eligible_at_utc`
- `status`
- `attempt_count`
- `next_attempt_at_utc`
- `reason_code`
- `created_at_utc`
- `updated_at_utc`

### 8.2 candidate_actions

Owns proposed action pressure before approval or execution.

Suggested fields:

- `candidate_action_id`
- `item_id`
- `action_kind`
- `urgency`
- `status`
- `evidence_ref`
- `requires_approval`
- `created_at_utc`
- `resolved_at_utc`

Spine MAY defer this table until automation pressure becomes real, but the ontology reserves the concept.

### 8.3 side_effect_attempts

Owns external write and delivery outcomes.

Suggested fields:

- `attempt_id`
- `work_instance_id`
- `candidate_action_id`
- `adapter_name`
- `projection_id`
- `idempotency_key`
- `attempt_status`
- `provider_ref`
- `request_hash`
- `response_hash`
- `reason_code`
- `attempted_at_utc`
- `completed_at_utc`

`delivery_attempts` MAY be used as the table name for notification delivery attempts if the implementation benefits from Kinflow continuity. A separate durable `adapter_results` store MUST NOT be introduced without an accepted decision.

## 9. Projections and Audit

### 9.1 external_projections

Owns external mirror state.

Suggested fields:

- `projection_id`
- `item_id`
- `adapter_name`
- `external_ref`
- `projection_status`
- `last_projected_version`
- `last_attempt_id`
- `stale_reason`
- `updated_at_utc`

### 9.2 audit_log

Owns append-only decision and lifecycle facts.

Suggested fields:

- `audit_id`
- `item_id`
- `stage`
- `action`
- `reason_code`
- `actor_ref`
- `causation_id`
- `correlation_id`
- `payload_hash`
- `created_at_utc`

## 10. Near-Term Open Questions

- Whether `side_effect_attempts` should be the generic table name or whether `delivery_attempts` should remain the canonical name for all adapter-result attempts.
- Whether `temporal_anchors` and `time_models` should be separate tables or one table with typed anchor kinds.
- Whether `blocks` and `part_of` should be stored relation types or deterministic derived views.
- How strict the first reason-code catalog should be before runtime implementation begins.
