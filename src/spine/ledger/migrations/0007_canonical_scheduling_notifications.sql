BEGIN IMMEDIATE;

DROP TRIGGER IF EXISTS event_details_recurrence_contract_insert;
DROP TRIGGER IF EXISTS task_details_recurrence_contract_insert;
DROP TRIGGER IF EXISTS notification_policies_recurrence_contract_insert;
DROP TRIGGER IF EXISTS notification_policies_delivery_target_owner_insert;
DROP TRIGGER IF EXISTS work_instances_notification_policy_binding_insert;
DROP TRIGGER IF EXISTS side_effect_attempts_origin_binding_insert;
DROP TRIGGER IF EXISTS side_effect_attempts_staleness_insert;

ALTER TABLE temporal_anchors DROP COLUMN recurrence_rule;
ALTER TABLE temporal_anchors ADD COLUMN timezone_database_version TEXT;

DROP TABLE work_instances;
DROP TABLE notification_policies;

CREATE TABLE recurrence_sets (
  recurrence_set_id TEXT PRIMARY KEY,
  source_item_id TEXT NOT NULL,
  created_item_version INTEGER NOT NULL CHECK (created_item_version >= 1),
  seed_anchor_id TEXT NOT NULL UNIQUE,
  time_basis TEXT NOT NULL CHECK (time_basis IN ('local_date', 'local_instant', 'instant_utc')),
  timezone TEXT,
  timezone_database_version TEXT,
  contract_version TEXT NOT NULL CHECK (contract_version = 'spine.recurrence.contract.v1'),
  normalization_version TEXT NOT NULL CHECK (normalization_version = 'spine.recurrence.normalization.v1'),
  canonical_json_version TEXT NOT NULL CHECK (canonical_json_version = 'spine.canonical-json.v1'),
  CHECK (
    (time_basis IN ('local_date', 'local_instant') AND timezone IS NOT NULL AND timezone_database_version IS NOT NULL)
    OR (time_basis = 'instant_utc' AND timezone IS NULL AND timezone_database_version IS NULL)
  ),
  FOREIGN KEY (source_item_id, created_item_version)
    REFERENCES coordination_item_versions (item_id, version) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (seed_anchor_id)
    REFERENCES temporal_anchors (anchor_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE recurrence_revisions (
  recurrence_revision_id TEXT PRIMARY KEY,
  recurrence_set_id TEXT NOT NULL,
  revision_number INTEGER NOT NULL CHECK (revision_number >= 1),
  source_item_version INTEGER NOT NULL CHECK (source_item_version >= 1),
  normalized_recurrence_set_hash TEXT NOT NULL CHECK (
    length(normalized_recurrence_set_hash) = 64
    AND normalized_recurrence_set_hash NOT GLOB '*[^0-9a-f]*'
  ),
  prior_recurrence_revision_id TEXT,
  command_id TEXT,
  created_at_utc TEXT NOT NULL,
  UNIQUE (recurrence_set_id, revision_number),
  UNIQUE (recurrence_set_id, source_item_version),
  CHECK (
    (revision_number = 1 AND prior_recurrence_revision_id IS NULL)
    OR (revision_number > 1 AND prior_recurrence_revision_id IS NOT NULL)
  ),
  FOREIGN KEY (recurrence_set_id) REFERENCES recurrence_sets (recurrence_set_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (prior_recurrence_revision_id) REFERENCES recurrence_revisions (recurrence_revision_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX recurrence_revisions_current_idx
ON recurrence_revisions (recurrence_set_id, source_item_version, revision_number);

CREATE TABLE recurrence_segments (
  segment_id TEXT PRIMARY KEY,
  recurrence_revision_id TEXT NOT NULL,
  segment_index INTEGER NOT NULL CHECK (segment_index >= 0),
  active_start TEXT NOT NULL,
  active_end TEXT,
  source_revision_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('active', 'superseded', 'retired')),
  lineage_parent_segment_id TEXT,
  created_by_command_id TEXT,
  reason_code TEXT,
  UNIQUE (recurrence_revision_id, segment_index),
  CHECK (active_end IS NULL OR active_end > active_start),
  FOREIGN KEY (recurrence_revision_id) REFERENCES recurrence_revisions (recurrence_revision_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (lineage_parent_segment_id) REFERENCES recurrence_segments (segment_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX recurrence_segments_active_idx
ON recurrence_segments (recurrence_revision_id, status, active_start, active_end);

CREATE TABLE recurrence_rules (
  rule_id TEXT PRIMARY KEY,
  recurrence_revision_id TEXT NOT NULL,
  segment_id TEXT NOT NULL,
  segment_ref INTEGER NOT NULL CHECK (segment_ref >= 0),
  frequency TEXT NOT NULL CHECK (frequency IN ('DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY')),
  interval_value INTEGER NOT NULL CHECK (interval_value BETWEEN 1 AND 2147483647),
  seed TEXT NOT NULL,
  start_bound TEXT NOT NULL,
  end_kind TEXT NOT NULL CHECK (end_kind IN ('unbounded', 'count', 'until')),
  end_count INTEGER CHECK (end_count >= 1),
  end_until TEXT,
  week_start TEXT CHECK (week_start IN ('MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU')),
  status TEXT NOT NULL CHECK (status IN ('active', 'superseded')),
  rule_duplicate_index INTEGER CHECK (rule_duplicate_index >= 0),
  CHECK (
    (end_kind = 'unbounded' AND end_count IS NULL AND end_until IS NULL)
    OR (end_kind = 'count' AND end_count IS NOT NULL AND end_until IS NULL)
    OR (end_kind = 'until' AND end_count IS NULL AND end_until IS NOT NULL)
  ),
  FOREIGN KEY (recurrence_revision_id) REFERENCES recurrence_revisions (recurrence_revision_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (segment_id) REFERENCES recurrence_segments (segment_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX recurrence_rules_revision_status_idx
ON recurrence_rules (recurrence_revision_id, status, segment_ref, rule_id);

CREATE TABLE recurrence_rule_selectors (
  rule_id TEXT NOT NULL,
  selector_kind TEXT NOT NULL CHECK (selector_kind IN ('by_month', 'by_month_day', 'by_weekday', 'by_set_position')),
  selector_index INTEGER NOT NULL CHECK (selector_index >= 0),
  selector_value TEXT NOT NULL,
  PRIMARY KEY (rule_id, selector_kind, selector_index),
  UNIQUE (rule_id, selector_kind, selector_value),
  FOREIGN KEY (rule_id) REFERENCES recurrence_rules (rule_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE recurrence_rdates (
  rdate_id TEXT PRIMARY KEY,
  recurrence_revision_id TEXT NOT NULL,
  segment_id TEXT NOT NULL,
  segment_ref INTEGER NOT NULL CHECK (segment_ref >= 0),
  scheduled_fact TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('active', 'superseded')),
  rdate_duplicate_index INTEGER CHECK (rdate_duplicate_index >= 0),
  FOREIGN KEY (recurrence_revision_id) REFERENCES recurrence_revisions (recurrence_revision_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (segment_id) REFERENCES recurrence_segments (segment_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX recurrence_rdates_revision_status_idx
ON recurrence_rdates (recurrence_revision_id, status, segment_ref, scheduled_fact, rdate_id);

CREATE TABLE recurrence_target_occurrence_selectors (
  target_occurrence_selector_ref TEXT PRIMARY KEY,
  occurrence_key TEXT NOT NULL UNIQUE,
  recurrence_set_id TEXT NOT NULL,
  segment_ref INTEGER NOT NULL CHECK (segment_ref >= 0),
  scheduled_fact TEXT NOT NULL,
  origin_kind TEXT NOT NULL CHECK (origin_kind IN ('rule', 'rdate', 'union')),
  FOREIGN KEY (recurrence_set_id) REFERENCES recurrence_sets (recurrence_set_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE recurrence_target_rule_sources (
  target_occurrence_selector_ref TEXT NOT NULL,
  source_index INTEGER NOT NULL CHECK (source_index >= 0),
  frequency TEXT NOT NULL CHECK (frequency IN ('DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY')),
  interval_value INTEGER NOT NULL CHECK (interval_value >= 1),
  seed TEXT NOT NULL,
  start_bound TEXT NOT NULL,
  end_kind TEXT NOT NULL CHECK (end_kind IN ('unbounded', 'count', 'until')),
  end_count INTEGER,
  end_until TEXT,
  week_start TEXT,
  status TEXT NOT NULL CHECK (status IN ('active', 'superseded')),
  rule_duplicate_index INTEGER,
  PRIMARY KEY (target_occurrence_selector_ref, source_index),
  FOREIGN KEY (target_occurrence_selector_ref)
    REFERENCES recurrence_target_occurrence_selectors (target_occurrence_selector_ref) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE recurrence_target_rule_source_selectors (
  target_occurrence_selector_ref TEXT NOT NULL,
  source_index INTEGER NOT NULL,
  selector_kind TEXT NOT NULL CHECK (selector_kind IN ('by_month', 'by_month_day', 'by_weekday', 'by_set_position')),
  selector_index INTEGER NOT NULL CHECK (selector_index >= 0),
  selector_value TEXT NOT NULL,
  PRIMARY KEY (target_occurrence_selector_ref, source_index, selector_kind, selector_index),
  FOREIGN KEY (target_occurrence_selector_ref, source_index)
    REFERENCES recurrence_target_rule_sources (target_occurrence_selector_ref, source_index) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE recurrence_target_rdate_sources (
  target_occurrence_selector_ref TEXT NOT NULL,
  source_index INTEGER NOT NULL CHECK (source_index >= 0),
  scheduled_fact TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('active', 'superseded')),
  rdate_duplicate_index INTEGER,
  PRIMARY KEY (target_occurrence_selector_ref, source_index),
  FOREIGN KEY (target_occurrence_selector_ref)
    REFERENCES recurrence_target_occurrence_selectors (target_occurrence_selector_ref) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE recurrence_exdates (
  exdate_id TEXT PRIMARY KEY,
  recurrence_revision_id TEXT NOT NULL,
  segment_id TEXT NOT NULL,
  segment_ref INTEGER NOT NULL CHECK (segment_ref >= 0),
  target_occurrence_selector_ref TEXT NOT NULL,
  target_occurrence_key TEXT NOT NULL,
  prior_target_occurrence_key TEXT,
  scheduled_fact TEXT NOT NULL,
  reason_code TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('active', 'superseded')),
  FOREIGN KEY (recurrence_revision_id) REFERENCES recurrence_revisions (recurrence_revision_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (segment_id) REFERENCES recurrence_segments (segment_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (target_occurrence_selector_ref)
    REFERENCES recurrence_target_occurrence_selectors (target_occurrence_selector_ref) DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX recurrence_exdates_revision_status_idx
ON recurrence_exdates (recurrence_revision_id, status, segment_ref, scheduled_fact, exdate_id);

CREATE TABLE recurrence_overrides (
  override_id TEXT PRIMARY KEY,
  recurrence_revision_id TEXT NOT NULL,
  segment_id TEXT NOT NULL,
  segment_ref INTEGER NOT NULL CHECK (segment_ref >= 0),
  target_occurrence_selector_ref TEXT NOT NULL,
  target_occurrence_key TEXT NOT NULL,
  prior_target_occurrence_key TEXT,
  override_kind TEXT NOT NULL CHECK (override_kind IN ('move', 'detail_patch', 'lifecycle', 'move_detail_patch', 'move_lifecycle', 'detail_patch_lifecycle', 'move_detail_patch_lifecycle')),
  revision_key TEXT NOT NULL,
  expressed_scheduled_fact TEXT,
  common_detail_patch_json TEXT,
  event_detail_patch_json TEXT,
  task_detail_patch_json TEXT,
  lifecycle TEXT CHECK (lifecycle IN ('active', 'cancelled', 'completed')),
  reason_code TEXT,
  status TEXT NOT NULL CHECK (status IN ('active', 'superseded')),
  UNIQUE (recurrence_revision_id, revision_key),
  FOREIGN KEY (recurrence_revision_id) REFERENCES recurrence_revisions (recurrence_revision_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (segment_id) REFERENCES recurrence_segments (segment_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (target_occurrence_selector_ref)
    REFERENCES recurrence_target_occurrence_selectors (target_occurrence_selector_ref) DEFERRABLE INITIALLY DEFERRED
);

CREATE UNIQUE INDEX recurrence_overrides_active_target_unique
ON recurrence_overrides (recurrence_revision_id, segment_ref, target_occurrence_key)
WHERE status = 'active';

CREATE TABLE recurrence_lineage (
  lineage_id TEXT PRIMARY KEY,
  command_id TEXT NOT NULL,
  recurrence_set_id TEXT NOT NULL,
  prior_recurrence_revision_id TEXT NOT NULL,
  new_recurrence_revision_id TEXT NOT NULL,
  lineage_role TEXT NOT NULL,
  prior_segment_id TEXT,
  new_segment_id TEXT,
  prior_child_id TEXT,
  new_child_id TEXT,
  effect TEXT NOT NULL,
  lineage_index INTEGER NOT NULL CHECK (lineage_index >= 0),
  payload_hash TEXT NOT NULL,
  UNIQUE (command_id, lineage_index),
  FOREIGN KEY (recurrence_set_id) REFERENCES recurrence_sets (recurrence_set_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (prior_recurrence_revision_id) REFERENCES recurrence_revisions (recurrence_revision_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (new_recurrence_revision_id) REFERENCES recurrence_revisions (recurrence_revision_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE occurrence_provenance (
  occurrence_provenance_id TEXT PRIMARY KEY,
  occurrence_provenance_slot_key TEXT NOT NULL,
  producer TEXT,
  consumer TEXT NOT NULL,
  item_id TEXT NOT NULL,
  source_item_version INTEGER NOT NULL,
  shell_status TEXT NOT NULL CHECK (shell_status IN ('active', 'archived')),
  archived_at_utc TEXT,
  recurrence_set_id TEXT NOT NULL,
  recurrence_revision_id TEXT NOT NULL,
  normalized_recurrence_set_hash TEXT NOT NULL,
  target_occurrence_selector_ref TEXT NOT NULL,
  occurrence_id TEXT NOT NULL,
  occurrence_key TEXT NOT NULL,
  range_basis TEXT NOT NULL CHECK (range_basis IN ('original_schedule', 'expressed_time')),
  range_start TEXT NOT NULL,
  range_end TEXT NOT NULL,
  original_scheduled_fact TEXT NOT NULL,
  expressed_scheduled_fact TEXT NOT NULL,
  timezone TEXT,
  timezone_database_version TEXT,
  timezone_resolution_kind TEXT,
  timezone_utc_instant TEXT,
  timezone_offset_seconds INTEGER,
  override_id TEXT,
  lifecycle TEXT NOT NULL CHECK (lifecycle IN ('active', 'cancelled', 'completed')),
  actionable INTEGER NOT NULL CHECK (actionable IN (0, 1)),
  content_hash TEXT NOT NULL,
  contract_version TEXT NOT NULL,
  normalization_version TEXT NOT NULL,
  canonical_json_version TEXT NOT NULL,
  management_status TEXT NOT NULL CHECK (management_status IN ('active', 'superseded')),
  superseded_by_command_id TEXT,
  superseded_at_utc TEXT,
  replacement_occurrence_provenance_id TEXT,
  created_at_utc TEXT NOT NULL,
  CHECK (
    (management_status = 'active' AND superseded_by_command_id IS NULL AND superseded_at_utc IS NULL AND replacement_occurrence_provenance_id IS NULL)
    OR (management_status = 'superseded' AND superseded_by_command_id IS NOT NULL AND superseded_at_utc IS NOT NULL)
  ),
  FOREIGN KEY (item_id, source_item_version) REFERENCES coordination_item_versions (item_id, version) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (recurrence_set_id) REFERENCES recurrence_sets (recurrence_set_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (recurrence_revision_id) REFERENCES recurrence_revisions (recurrence_revision_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (target_occurrence_selector_ref) REFERENCES recurrence_target_occurrence_selectors (target_occurrence_selector_ref) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (replacement_occurrence_provenance_id) REFERENCES occurrence_provenance (occurrence_provenance_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE UNIQUE INDEX occurrence_provenance_active_slot_unique
ON occurrence_provenance (occurrence_provenance_slot_key)
WHERE management_status = 'active';

CREATE INDEX occurrence_provenance_item_consumer_range_idx
ON occurrence_provenance (item_id, consumer, range_basis, range_start, range_end, management_status);

CREATE TABLE occurrence_provenance_rule_sources (
  occurrence_provenance_id TEXT NOT NULL,
  source_index INTEGER NOT NULL CHECK (source_index >= 0),
  rule_id TEXT NOT NULL,
  rule_local_index INTEGER NOT NULL CHECK (rule_local_index >= 0),
  PRIMARY KEY (occurrence_provenance_id, source_index),
  FOREIGN KEY (occurrence_provenance_id) REFERENCES occurrence_provenance (occurrence_provenance_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE occurrence_provenance_rdate_sources (
  occurrence_provenance_id TEXT NOT NULL,
  source_index INTEGER NOT NULL CHECK (source_index >= 0),
  rdate_id TEXT NOT NULL,
  PRIMARY KEY (occurrence_provenance_id, source_index),
  FOREIGN KEY (occurrence_provenance_id) REFERENCES occurrence_provenance (occurrence_provenance_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE recurrence_provenance_block_reports (
  block_report_id TEXT PRIMARY KEY,
  report_version TEXT NOT NULL CHECK (report_version IN ('spine.recurrence.provenance-block.v1', 'spine.recurrence.provenance-block.unresolved-range.v1')),
  item_id TEXT NOT NULL,
  consumer TEXT NOT NULL,
  operation TEXT NOT NULL,
  recurrence_set_id TEXT NOT NULL,
  range_basis TEXT,
  range_start TEXT,
  range_end TEXT,
  stale_occurrence_provenance_id TEXT,
  occurrence_provenance_slot_key TEXT,
  source_item_version INTEGER NOT NULL,
  contract_version TEXT NOT NULL,
  normalization_version TEXT NOT NULL,
  canonical_json_version TEXT NOT NULL,
  recurrence_revision_id TEXT NOT NULL,
  normalized_recurrence_set_hash TEXT NOT NULL,
  reason_code TEXT NOT NULL CHECK (reason_code IN ('stale_occurrence_provenance', 'provenance_range_unresolved')),
  handoff TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('open', 'superseded', 'resolved')),
  block_count INTEGER NOT NULL CHECK (block_count >= 1),
  first_blocked_at_utc TEXT NOT NULL,
  last_blocked_at_utc TEXT NOT NULL,
  resolved_by_command_id TEXT,
  closed_at_utc TEXT,
  closure_kind TEXT CHECK (closure_kind IN ('canonical_range_derived', 'canonical_range_derived_no_stale_provenance')),
  successor_block_report_id TEXT,
  resulting_occurrence_provenance_id TEXT,
  FOREIGN KEY (item_id) REFERENCES coordination_items (item_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (recurrence_set_id) REFERENCES recurrence_sets (recurrence_set_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (recurrence_revision_id) REFERENCES recurrence_revisions (recurrence_revision_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (stale_occurrence_provenance_id) REFERENCES occurrence_provenance (occurrence_provenance_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (successor_block_report_id) REFERENCES recurrence_provenance_block_reports (block_report_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (resulting_occurrence_provenance_id) REFERENCES occurrence_provenance (occurrence_provenance_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX recurrence_provenance_reports_open_idx
ON recurrence_provenance_block_reports (item_id, consumer, recurrence_set_id, status, block_report_id);

CREATE TABLE notification_policies (
  policy_id TEXT PRIMARY KEY,
  notification_intent_id TEXT NOT NULL,
  intent_created_item_version INTEGER NOT NULL CHECK (intent_created_item_version >= 1),
  intent_created_by_command_id TEXT NOT NULL,
  item_id TEXT NOT NULL,
  version INTEGER NOT NULL CHECK (version >= 1),
  recipient_kind TEXT NOT NULL CHECK (recipient_kind IN ('subject', 'subject_group')),
  recipient_subject_id TEXT,
  recipient_group_id TEXT,
  channel TEXT NOT NULL,
  delivery_target_id TEXT NOT NULL,
  schedule_id TEXT NOT NULL UNIQUE,
  target_anchor_role TEXT NOT NULL CHECK (target_anchor_role IN ('event_start', 'task_due')),
  application_scope TEXT NOT NULL CHECK (application_scope IN ('item', 'each_occurrence', 'selected_occurrence')),
  target_occurrence_key TEXT,
  target_occurrence_selector_ref TEXT,
  normalized_notification_schedule_hash TEXT NOT NULL CHECK (length(normalized_notification_schedule_hash) = 64),
  late_handling_kind TEXT NOT NULL CHECK (late_handling_kind IN ('skip', 'deliver_within')),
  late_grace_seconds INTEGER,
  status TEXT NOT NULL CHECK (status IN ('active', 'disabled')),
  created_at_utc TEXT NOT NULL,
  created_by_command_id TEXT NOT NULL,
  source_notification_policy_id TEXT,
  disabled_at_utc TEXT,
  CHECK (
    (recipient_kind = 'subject' AND recipient_subject_id IS NOT NULL AND recipient_group_id IS NULL)
    OR (recipient_kind = 'subject_group' AND recipient_group_id IS NOT NULL AND recipient_subject_id IS NULL)
  ),
  CHECK (
    (application_scope = 'selected_occurrence' AND target_occurrence_key IS NOT NULL AND target_occurrence_selector_ref IS NOT NULL)
    OR (application_scope != 'selected_occurrence' AND target_occurrence_key IS NULL AND target_occurrence_selector_ref IS NULL)
  ),
  CHECK (
    (late_handling_kind = 'skip' AND late_grace_seconds IS NULL)
    OR (late_handling_kind = 'deliver_within' AND late_grace_seconds IS NOT NULL AND late_grace_seconds >= 0)
  ),
  CHECK ((status = 'active' AND disabled_at_utc IS NULL) OR (status = 'disabled' AND disabled_at_utc IS NOT NULL)),
  FOREIGN KEY (item_id, version) REFERENCES coordination_item_versions (item_id, version) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (recipient_subject_id) REFERENCES subjects (subject_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (recipient_group_id) REFERENCES subject_groups (group_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (delivery_target_id) REFERENCES delivery_targets (delivery_target_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (source_notification_policy_id) REFERENCES notification_policies (policy_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE notification_schedules (
  schedule_id TEXT PRIMARY KEY,
  policy_id TEXT NOT NULL UNIQUE,
  schedule_kind TEXT NOT NULL CHECK (schedule_kind IN ('once', 'offsets', 'repeat_window')),
  once_boundary_kind TEXT CHECK (once_boundary_kind IN ('absolute_utc', 'target_offset')),
  once_at_utc TEXT,
  stop_inclusive INTEGER CHECK (stop_inclusive IN (0, 1)),
  cadence_kind TEXT CHECK (cadence_kind IN ('fixed_elapsed', 'local_calendar')),
  interval_seconds INTEGER,
  frequency TEXT CHECK (frequency IN ('DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY')),
  interval_value INTEGER,
  seed_local_date TEXT,
  local_time TEXT,
  timezone TEXT,
  timezone_database_version TEXT,
  week_start TEXT CHECK (week_start IN ('MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU')),
  normalized_notification_schedule_hash TEXT NOT NULL CHECK (length(normalized_notification_schedule_hash) = 64),
  CHECK (
    (schedule_kind = 'once' AND once_boundary_kind IS NOT NULL AND cadence_kind IS NULL AND stop_inclusive IS NULL)
    OR (schedule_kind = 'offsets' AND once_boundary_kind IS NULL AND cadence_kind IS NULL AND stop_inclusive IS NULL)
    OR (schedule_kind = 'repeat_window' AND once_boundary_kind IS NULL AND cadence_kind IS NOT NULL AND stop_inclusive IS NOT NULL)
  ),
  CHECK (
    cadence_kind IS NULL
    OR (cadence_kind = 'fixed_elapsed' AND interval_seconds BETWEEN 1 AND 31557600 AND frequency IS NULL)
    OR (cadence_kind = 'local_calendar' AND interval_seconds IS NULL AND frequency IS NOT NULL AND interval_value >= 1 AND seed_local_date IS NOT NULL AND local_time IS NOT NULL AND timezone IS NOT NULL AND timezone_database_version IS NOT NULL)
  ),
  FOREIGN KEY (policy_id) REFERENCES notification_policies (policy_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE notification_schedule_offsets (
  schedule_id TEXT NOT NULL,
  boundary_role TEXT NOT NULL CHECK (boundary_role IN ('at', 'start', 'stop')),
  offset_index INTEGER NOT NULL CHECK (offset_index >= 0),
  boundary_kind TEXT NOT NULL CHECK (boundary_kind IN ('absolute_utc', 'target_offset')),
  at_utc TEXT,
  offset_basis TEXT CHECK (offset_basis IN ('elapsed', 'calendar_days')),
  offset_seconds INTEGER,
  offset_days INTEGER,
  local_time TEXT,
  timezone TEXT,
  timezone_database_version TEXT,
  PRIMARY KEY (schedule_id, boundary_role, offset_index),
  CHECK (
    (boundary_kind = 'absolute_utc' AND at_utc IS NOT NULL AND offset_basis IS NULL AND offset_seconds IS NULL AND offset_days IS NULL AND local_time IS NULL)
    OR (boundary_kind = 'target_offset' AND at_utc IS NULL AND (
      (offset_basis = 'elapsed' AND offset_seconds IS NOT NULL AND offset_days IS NULL AND local_time IS NULL)
      OR (offset_basis = 'calendar_days' AND offset_seconds IS NULL AND offset_days IS NOT NULL AND local_time IS NOT NULL)
    ))
  ),
  FOREIGN KEY (schedule_id) REFERENCES notification_schedules (schedule_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE notification_schedule_selectors (
  schedule_id TEXT NOT NULL,
  selector_kind TEXT NOT NULL CHECK (selector_kind IN ('by_month', 'by_month_day', 'by_weekday', 'by_set_position')),
  selector_index INTEGER NOT NULL CHECK (selector_index >= 0),
  selector_value TEXT NOT NULL,
  PRIMARY KEY (schedule_id, selector_kind, selector_index),
  UNIQUE (schedule_id, selector_kind, selector_value),
  FOREIGN KEY (schedule_id) REFERENCES notification_schedules (schedule_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE notification_target_occurrence_selectors (
  target_occurrence_selector_ref TEXT PRIMARY KEY,
  recurrence_target_occurrence_selector_ref TEXT NOT NULL UNIQUE,
  occurrence_key TEXT NOT NULL UNIQUE,
  FOREIGN KEY (recurrence_target_occurrence_selector_ref)
    REFERENCES recurrence_target_occurrence_selectors (target_occurrence_selector_ref) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE notification_target_rule_sources (
  target_occurrence_selector_ref TEXT NOT NULL,
  source_index INTEGER NOT NULL CHECK (source_index >= 0),
  recurrence_target_occurrence_selector_ref TEXT NOT NULL,
  recurrence_source_index INTEGER NOT NULL,
  PRIMARY KEY (target_occurrence_selector_ref, source_index),
  FOREIGN KEY (target_occurrence_selector_ref)
    REFERENCES notification_target_occurrence_selectors (target_occurrence_selector_ref) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (recurrence_target_occurrence_selector_ref, recurrence_source_index)
    REFERENCES recurrence_target_rule_sources (target_occurrence_selector_ref, source_index) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE notification_target_rule_source_selectors (
  target_occurrence_selector_ref TEXT NOT NULL,
  source_index INTEGER NOT NULL,
  selector_kind TEXT NOT NULL,
  selector_index INTEGER NOT NULL,
  selector_value TEXT NOT NULL,
  PRIMARY KEY (target_occurrence_selector_ref, source_index, selector_kind, selector_index),
  FOREIGN KEY (target_occurrence_selector_ref, source_index)
    REFERENCES notification_target_rule_sources (target_occurrence_selector_ref, source_index) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE notification_target_rdate_sources (
  target_occurrence_selector_ref TEXT NOT NULL,
  source_index INTEGER NOT NULL CHECK (source_index >= 0),
  recurrence_target_occurrence_selector_ref TEXT NOT NULL,
  recurrence_source_index INTEGER NOT NULL,
  PRIMARY KEY (target_occurrence_selector_ref, source_index),
  FOREIGN KEY (target_occurrence_selector_ref)
    REFERENCES notification_target_occurrence_selectors (target_occurrence_selector_ref) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (recurrence_target_occurrence_selector_ref, recurrence_source_index)
    REFERENCES recurrence_target_rdate_sources (target_occurrence_selector_ref, source_index) DEFERRABLE INITIALLY DEFERRED
);

CREATE UNIQUE INDEX notification_policies_subject_unique
ON notification_policies (item_id, version, recipient_subject_id, delivery_target_id, normalized_notification_schedule_hash)
WHERE recipient_kind = 'subject';

CREATE UNIQUE INDEX notification_policies_group_unique
ON notification_policies (item_id, version, recipient_group_id, delivery_target_id, normalized_notification_schedule_hash)
WHERE recipient_kind = 'subject_group';

CREATE INDEX notification_policies_item_version_status_idx
ON notification_policies (item_id, version, status, policy_id);
CREATE INDEX notification_policies_recipient_status_idx
ON notification_policies (recipient_subject_id, status, item_id, version);
CREATE INDEX notification_policies_group_status_idx
ON notification_policies (recipient_group_id, status, item_id, version) WHERE recipient_kind = 'subject_group';
CREATE INDEX notification_policies_delivery_target_idx
ON notification_policies (delivery_target_id, status, item_id, version);

CREATE TABLE work_instances (
  work_instance_id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  item_version INTEGER NOT NULL,
  notification_policy_id TEXT,
  notification_policy_item_version INTEGER,
  notification_intent_id TEXT,
  notification_opportunity_id TEXT,
  normalized_notification_schedule_hash TEXT,
  occurrence_provenance_id TEXT,
  target_anchor_role TEXT CHECK (target_anchor_role IN ('event_start', 'task_due')),
  application_scope TEXT CHECK (application_scope IN ('item', 'each_occurrence', 'selected_occurrence')),
  target_scheduled_fact TEXT,
  target_at_utc TEXT,
  occurrence_key TEXT,
  delivery_target_id TEXT,
  source_work_instance_id TEXT,
  generation_source_kind TEXT CHECK (generation_source_kind IN ('work_instance', 'notification_policy', 'schedule_tick', 'user_action', 'item_version')),
  generation_source_ref TEXT,
  work_subject_ref TEXT,
  work_kind TEXT NOT NULL CHECK (work_kind IN ('notification_reminder')),
  purpose_detail_ref TEXT,
  policy_basis_ref TEXT,
  eligible_at_utc TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('eligible', 'in_progress', 'succeeded', 'failed', 'cancelled')),
  attempt_count INTEGER NOT NULL CHECK (attempt_count >= 0),
  next_attempt_at_utc TEXT,
  reason_code TEXT,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  CHECK (
    (notification_opportunity_id IS NULL AND notification_intent_id IS NULL AND normalized_notification_schedule_hash IS NULL AND occurrence_provenance_id IS NULL)
    OR (notification_opportunity_id IS NOT NULL AND notification_intent_id IS NOT NULL AND normalized_notification_schedule_hash IS NOT NULL AND delivery_target_id IS NOT NULL AND target_anchor_role IS NOT NULL AND application_scope IS NOT NULL AND target_scheduled_fact IS NOT NULL)
  ),
  CHECK ((notification_policy_id IS NULL AND notification_policy_item_version IS NULL) OR (notification_policy_id IS NOT NULL AND notification_policy_item_version IS NOT NULL)),
  FOREIGN KEY (item_id, item_version) REFERENCES coordination_item_versions (item_id, version) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (notification_policy_id) REFERENCES notification_policies (policy_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (delivery_target_id) REFERENCES delivery_targets (delivery_target_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (occurrence_provenance_id) REFERENCES occurrence_provenance (occurrence_provenance_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (source_work_instance_id) REFERENCES work_instances (work_instance_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE UNIQUE INDEX work_instances_notification_opportunity_unique
ON work_instances (notification_opportunity_id, delivery_target_id)
WHERE notification_opportunity_id IS NOT NULL;
CREATE INDEX work_instances_eligible_due_idx
ON work_instances (eligible_at_utc, work_instance_id, next_attempt_at_utc) WHERE status = 'eligible';
CREATE INDEX work_instances_item_version_status_idx
ON work_instances (item_id, item_version, status, work_instance_id);
CREATE INDEX work_instances_source_work_idx
ON work_instances (source_work_instance_id, work_instance_id) WHERE source_work_instance_id IS NOT NULL;
CREATE INDEX work_instances_delivery_target_idx
ON work_instances (delivery_target_id, status, work_instance_id) WHERE delivery_target_id IS NOT NULL;

CREATE TRIGGER event_details_recurrence_contract_insert
BEFORE INSERT ON event_details
FOR EACH ROW
WHEN (
  NEW.end_anchor_id IS NOT NULL
  AND EXISTS (SELECT 1 FROM recurrence_sets WHERE seed_anchor_id = NEW.end_anchor_id)
)
OR EXISTS (
  SELECT 1 FROM recurrence_sets
  WHERE seed_anchor_id = NEW.start_anchor_id
    AND time_basis != (SELECT anchor_kind FROM temporal_anchors WHERE anchor_id = NEW.start_anchor_id)
)
BEGIN
  SELECT RAISE(ABORT, 'event recurrence is valid only on a matching start anchor');
END;

CREATE TRIGGER task_details_recurrence_contract_insert
BEFORE INSERT ON task_details
FOR EACH ROW
WHEN (
  NEW.defer_until_anchor_id IS NOT NULL
  AND EXISTS (SELECT 1 FROM recurrence_sets WHERE seed_anchor_id = NEW.defer_until_anchor_id)
)
OR EXISTS (
  SELECT 1 FROM recurrence_sets
  WHERE seed_anchor_id = NEW.due_anchor_id
    AND time_basis != (SELECT anchor_kind FROM temporal_anchors WHERE anchor_id = NEW.due_anchor_id)
)
BEGIN
  SELECT RAISE(ABORT, 'task recurrence is valid only on a matching due anchor');
END;

CREATE TRIGGER notification_policies_delivery_target_owner_insert
BEFORE INSERT ON notification_policies
FOR EACH ROW
WHEN NOT EXISTS (
  SELECT 1 FROM delivery_targets AS dt
  WHERE dt.delivery_target_id = NEW.delivery_target_id
    AND dt.status = 'active'
    AND dt.channel = NEW.channel
    AND (
      (NEW.recipient_kind = 'subject' AND dt.owner_kind = 'subject' AND dt.owner_subject_id = NEW.recipient_subject_id)
      OR (NEW.recipient_kind = 'subject_group' AND dt.owner_kind = 'subject_group' AND dt.owner_group_id = NEW.recipient_group_id)
    )
)
BEGIN
  SELECT RAISE(ABORT, 'notification_policies delivery target binding is invalid');
END;

CREATE TRIGGER notification_policies_structured_contract_insert
BEFORE INSERT ON notification_policies
FOR EACH ROW
WHEN (
  (NEW.target_anchor_role = 'event_start' AND (SELECT item_type FROM coordination_items WHERE item_id = NEW.item_id) != 'event')
  OR (NEW.target_anchor_role = 'task_due' AND (SELECT item_type FROM coordination_items WHERE item_id = NEW.item_id) != 'task')
)
BEGIN
  SELECT RAISE(ABORT, 'notification target anchor role does not match item type');
END;

CREATE TRIGGER work_instances_notification_policy_binding_insert
BEFORE INSERT ON work_instances
FOR EACH ROW
WHEN NEW.notification_policy_id IS NOT NULL
AND NOT EXISTS (
  SELECT 1 FROM notification_policies AS p
  WHERE p.policy_id = NEW.notification_policy_id
    AND p.item_id = NEW.item_id
    AND p.version = NEW.notification_policy_item_version
    AND p.version = NEW.item_version
    AND p.notification_intent_id = NEW.notification_intent_id
    AND p.normalized_notification_schedule_hash = NEW.normalized_notification_schedule_hash
    AND p.delivery_target_id = NEW.delivery_target_id
    AND p.status = 'active'
)
BEGIN
  SELECT RAISE(ABORT, 'work_instances notification policy binding is invalid');
END;

CREATE TRIGGER side_effect_attempts_origin_binding_insert
BEFORE INSERT ON side_effect_attempts
FOR EACH ROW
WHEN (
  NEW.work_instance_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM work_instances
    WHERE work_instance_id = NEW.work_instance_id
      AND item_id = NEW.item_id
      AND (NEW.projection_id IS NULL OR item_version = NEW.source_item_version)
  )
)
OR (
  NEW.candidate_action_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM candidate_actions
    WHERE candidate_action_id = NEW.candidate_action_id
      AND item_id = NEW.item_id
      AND (NEW.projection_id IS NULL OR item_version = NEW.source_item_version)
  )
)
OR (
  NEW.projection_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM external_projections WHERE projection_id = NEW.projection_id AND item_id = NEW.item_id)
)
BEGIN
  SELECT RAISE(ABORT, 'side_effect_attempts origin binding is invalid');
END;

CREATE TRIGGER side_effect_attempts_staleness_insert
BEFORE INSERT ON side_effect_attempts
FOR EACH ROW
WHEN (
  NEW.work_instance_id IS NOT NULL
  AND EXISTS (
  SELECT 1
  FROM work_instances AS w
  JOIN coordination_items AS i ON i.item_id = w.item_id
  WHERE w.work_instance_id = NEW.work_instance_id
    AND (
      w.status != 'in_progress'
      OR i.status != 'active'
      OR NOT EXISTS (
        SELECT 1
        FROM notification_policies AS p
        JOIN delivery_targets AS dt ON dt.delivery_target_id = p.delivery_target_id
        WHERE p.item_id = w.item_id
          AND p.version = i.current_version
          AND p.status = 'active'
          AND p.notification_intent_id = w.notification_intent_id
          AND p.normalized_notification_schedule_hash = w.normalized_notification_schedule_hash
          AND p.delivery_target_id = w.delivery_target_id
          AND dt.status = 'active'
          AND dt.channel = p.channel
          AND p.target_anchor_role = w.target_anchor_role
          AND p.application_scope = w.application_scope
          AND (
            (p.recipient_kind = 'subject' AND dt.owner_kind = 'subject' AND dt.owner_subject_id = p.recipient_subject_id)
            OR (p.recipient_kind = 'subject_group' AND dt.owner_kind = 'subject_group' AND dt.owner_group_id = p.recipient_group_id)
          )
      )
      OR (w.occurrence_provenance_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
        FROM occurrence_provenance AS op
        WHERE op.occurrence_provenance_id = w.occurrence_provenance_id
          AND op.management_status = 'active'
          AND op.actionable = 1
          AND op.occurrence_key = w.occurrence_key
          AND op.expressed_scheduled_fact = w.target_scheduled_fact
          AND op.recurrence_revision_id = (
            SELECT rr.recurrence_revision_id
            FROM recurrence_sets AS rs
            JOIN recurrence_revisions AS rr ON rr.recurrence_set_id = rs.recurrence_set_id
            WHERE rs.source_item_id = w.item_id
              AND rr.source_item_version <= i.current_version
            ORDER BY rr.source_item_version DESC, rr.revision_number DESC
            LIMIT 1
          )
      ))
    )
  )
)
OR (
  NEW.candidate_action_id IS NOT NULL
  AND EXISTS (
    SELECT 1
    FROM candidate_actions AS c
    JOIN coordination_items AS i ON i.item_id = c.item_id
    WHERE c.candidate_action_id = NEW.candidate_action_id
      AND i.current_version != c.item_version
  )
)
OR (
  NEW.projection_id IS NOT NULL
  AND EXISTS (
    SELECT 1
    FROM coordination_items AS i
    WHERE i.item_id = NEW.item_id
      AND i.current_version != NEW.source_item_version
  )
)
BEGIN
  SELECT RAISE(ABORT, 'side_effect_attempts source truth is stale or ineligible');
END;

COMMIT;
