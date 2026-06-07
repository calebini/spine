PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS subjects (
  subject_id TEXT PRIMARY KEY,
  subject_kind TEXT NOT NULL CHECK (subject_kind IN ('person', 'agent')),
  display_name TEXT NOT NULL CHECK (length(display_name) > 0),
  status TEXT NOT NULL CHECK (status IN ('active', 'inactive')),
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS temporal_anchors (
  anchor_id TEXT PRIMARY KEY,
  anchor_kind TEXT NOT NULL CHECK (
    anchor_kind IN ('instant_utc', 'local_instant', 'local_date', 'utc_window', 'local_window')
  ),
  local_date TEXT,
  local_time TEXT,
  timezone TEXT,
  utc_instant TEXT,
  window_start_utc TEXT,
  window_end_utc TEXT,
  recurrence_rule TEXT,
  source TEXT,
  created_at_utc TEXT NOT NULL,
  CHECK (
    (
      anchor_kind = 'instant_utc'
      AND utc_instant IS NOT NULL
      AND local_date IS NULL
      AND local_time IS NULL
      AND timezone IS NULL
      AND window_start_utc IS NULL
      AND window_end_utc IS NULL
    )
    OR (
      anchor_kind = 'local_instant'
      AND local_date IS NOT NULL
      AND local_time IS NOT NULL
      AND timezone IS NOT NULL
      AND utc_instant IS NULL
      AND window_start_utc IS NULL
      AND window_end_utc IS NULL
    )
    OR (
      anchor_kind = 'local_date'
      AND local_date IS NOT NULL
      AND local_time IS NULL
      AND timezone IS NOT NULL
      AND utc_instant IS NULL
      AND window_start_utc IS NULL
      AND window_end_utc IS NULL
    )
    OR (
      anchor_kind = 'utc_window'
      AND local_date IS NULL
      AND local_time IS NULL
      AND timezone IS NULL
      AND utc_instant IS NULL
      AND window_start_utc IS NOT NULL
      AND window_end_utc IS NOT NULL
      AND window_start_utc <= window_end_utc
    )
    OR (
      anchor_kind = 'local_window'
      AND local_date IS NOT NULL
      AND local_time IS NULL
      AND timezone IS NOT NULL
      AND utc_instant IS NULL
      AND window_start_utc IS NULL
      AND window_end_utc IS NULL
    )
  )
);

CREATE TABLE IF NOT EXISTS coordination_items (
  item_id TEXT PRIMARY KEY,
  item_type TEXT NOT NULL CHECK (item_type IN ('event', 'task', 'project', 'collection')),
  current_version INTEGER NOT NULL CHECK (current_version >= 1),
  status TEXT NOT NULL CHECK (status IN ('active', 'archived')),
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  archived_at_utc TEXT,
  CHECK (
    (status = 'active' AND archived_at_utc IS NULL)
    OR (status = 'archived' AND archived_at_utc IS NOT NULL)
  ),
  FOREIGN KEY (item_id, current_version)
    REFERENCES coordination_item_versions (item_id, version)
    DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS coordination_item_versions (
  item_id TEXT NOT NULL,
  version INTEGER NOT NULL CHECK (version >= 1),
  title TEXT NOT NULL CHECK (length(title) > 0),
  summary TEXT,
  intent_hash TEXT NOT NULL CHECK (
    length(intent_hash) = 64 AND intent_hash NOT GLOB '*[^0-9a-f]*'
  ),
  normalized_fields_hash TEXT NOT NULL CHECK (
    length(normalized_fields_hash) = 64 AND normalized_fields_hash NOT GLOB '*[^0-9a-f]*'
  ),
  source_ref TEXT,
  created_at_utc TEXT NOT NULL,
  created_by_subject_id TEXT NOT NULL,
  PRIMARY KEY (item_id, version),
  FOREIGN KEY (item_id)
    REFERENCES coordination_items (item_id)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (created_by_subject_id)
    REFERENCES subjects (subject_id)
    DEFERRABLE INITIALLY DEFERRED
);

CREATE TRIGGER IF NOT EXISTS coordination_item_versions_contiguous_insert
BEFORE INSERT ON coordination_item_versions
FOR EACH ROW
WHEN NEW.version != COALESCE(
  (SELECT MAX(version) + 1 FROM coordination_item_versions WHERE item_id = NEW.item_id),
  1
)
BEGIN
  SELECT RAISE(ABORT, 'coordination_item_versions.version must be contiguous per item');
END;

CREATE TABLE IF NOT EXISTS event_details (
  item_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  event_status TEXT NOT NULL CHECK (event_status IN ('scheduled', 'cancelled')),
  all_day INTEGER NOT NULL CHECK (all_day IN (0, 1)),
  start_anchor_id TEXT NOT NULL,
  end_anchor_id TEXT,
  visibility TEXT,
  attendance_policy_ref TEXT,
  PRIMARY KEY (item_id, version),
  FOREIGN KEY (item_id, version)
    REFERENCES coordination_item_versions (item_id, version)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (start_anchor_id)
    REFERENCES temporal_anchors (anchor_id)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (end_anchor_id)
    REFERENCES temporal_anchors (anchor_id)
    DEFERRABLE INITIALLY DEFERRED
);

CREATE TRIGGER IF NOT EXISTS event_details_item_type_insert
BEFORE INSERT ON event_details
FOR EACH ROW
WHEN (SELECT item_type FROM coordination_items WHERE item_id = NEW.item_id) != 'event'
BEGIN
  SELECT RAISE(ABORT, 'event_details requires coordination_items.item_type=event');
END;

CREATE TRIGGER IF NOT EXISTS event_details_time_shape_insert
BEFORE INSERT ON event_details
FOR EACH ROW
WHEN NOT (
  (
    NEW.all_day = 1
    AND (SELECT anchor_kind FROM temporal_anchors WHERE anchor_id = NEW.start_anchor_id) = 'local_date'
    AND (
      NEW.end_anchor_id IS NULL
      OR (
        (SELECT anchor_kind FROM temporal_anchors WHERE anchor_id = NEW.end_anchor_id) = 'local_date'
        AND (SELECT timezone FROM temporal_anchors WHERE anchor_id = NEW.end_anchor_id)
          = (SELECT timezone FROM temporal_anchors WHERE anchor_id = NEW.start_anchor_id)
        AND (SELECT local_date FROM temporal_anchors WHERE anchor_id = NEW.end_anchor_id)
          > (SELECT local_date FROM temporal_anchors WHERE anchor_id = NEW.start_anchor_id)
      )
    )
  )
  OR (
    NEW.all_day = 0
    AND (SELECT anchor_kind FROM temporal_anchors WHERE anchor_id = NEW.start_anchor_id)
      IN ('instant_utc', 'local_instant')
    AND (
      NEW.end_anchor_id IS NULL
      OR (
        (SELECT anchor_kind FROM temporal_anchors WHERE anchor_id = NEW.end_anchor_id)
          = (SELECT anchor_kind FROM temporal_anchors WHERE anchor_id = NEW.start_anchor_id)
        AND (
          (
            (SELECT anchor_kind FROM temporal_anchors WHERE anchor_id = NEW.start_anchor_id) = 'instant_utc'
            AND (SELECT utc_instant FROM temporal_anchors WHERE anchor_id = NEW.end_anchor_id)
              >= (SELECT utc_instant FROM temporal_anchors WHERE anchor_id = NEW.start_anchor_id)
          )
          OR (
            (SELECT anchor_kind FROM temporal_anchors WHERE anchor_id = NEW.start_anchor_id) = 'local_instant'
            AND (SELECT timezone FROM temporal_anchors WHERE anchor_id = NEW.end_anchor_id)
              = (SELECT timezone FROM temporal_anchors WHERE anchor_id = NEW.start_anchor_id)
            AND (
              (SELECT local_date FROM temporal_anchors WHERE anchor_id = NEW.end_anchor_id)
                > (SELECT local_date FROM temporal_anchors WHERE anchor_id = NEW.start_anchor_id)
              OR (
                (SELECT local_date FROM temporal_anchors WHERE anchor_id = NEW.end_anchor_id)
                  = (SELECT local_date FROM temporal_anchors WHERE anchor_id = NEW.start_anchor_id)
                AND (SELECT local_time FROM temporal_anchors WHERE anchor_id = NEW.end_anchor_id)
                  >= (SELECT local_time FROM temporal_anchors WHERE anchor_id = NEW.start_anchor_id)
              )
            )
          )
        )
      )
    )
  )
)
BEGIN
  SELECT RAISE(ABORT, 'event_details time shape is invalid');
END;

CREATE TABLE IF NOT EXISTS task_details (
  item_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  task_status TEXT NOT NULL CHECK (task_status IN ('open', 'done', 'cancelled')),
  completion_state TEXT,
  priority TEXT,
  due_anchor_id TEXT,
  defer_until_anchor_id TEXT,
  completed_at_utc TEXT,
  completed_by_subject_id TEXT,
  PRIMARY KEY (item_id, version),
  CHECK (task_status != 'done' OR completed_at_utc IS NOT NULL),
  FOREIGN KEY (item_id, version)
    REFERENCES coordination_item_versions (item_id, version)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (due_anchor_id)
    REFERENCES temporal_anchors (anchor_id)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (defer_until_anchor_id)
    REFERENCES temporal_anchors (anchor_id)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (completed_by_subject_id)
    REFERENCES subjects (subject_id)
    DEFERRABLE INITIALLY DEFERRED
);

CREATE TRIGGER IF NOT EXISTS task_details_item_type_insert
BEFORE INSERT ON task_details
FOR EACH ROW
WHEN (SELECT item_type FROM coordination_items WHERE item_id = NEW.item_id) != 'task'
BEGIN
  SELECT RAISE(ABORT, 'task_details requires coordination_items.item_type=task');
END;

CREATE TRIGGER IF NOT EXISTS task_details_time_shape_insert
BEFORE INSERT ON task_details
FOR EACH ROW
WHEN NOT (
  (
    NEW.due_anchor_id IS NULL
    OR (SELECT anchor_kind FROM temporal_anchors WHERE anchor_id = NEW.due_anchor_id)
      IN ('instant_utc', 'local_instant', 'local_date', 'utc_window', 'local_window')
  )
  AND (
    NEW.defer_until_anchor_id IS NULL
    OR (SELECT anchor_kind FROM temporal_anchors WHERE anchor_id = NEW.defer_until_anchor_id)
      IN ('instant_utc', 'local_instant', 'local_date')
  )
)
BEGIN
  SELECT RAISE(ABORT, 'task_details time shape is invalid');
END;

CREATE TABLE IF NOT EXISTS locations (
  location_id TEXT PRIMARY KEY,
  label TEXT NOT NULL CHECK (length(label) > 0),
  kind TEXT NOT NULL CHECK (kind IN ('address', 'place', 'virtual', 'relative', 'unknown')),
  address_text TEXT,
  latitude TEXT,
  longitude TEXT,
  timezone TEXT,
  provider_ref TEXT,
  metadata_json TEXT,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS locations_referenced_canonical_fields_update
BEFORE UPDATE OF label, kind, address_text, latitude, longitude, timezone, provider_ref ON locations
FOR EACH ROW
WHEN EXISTS (SELECT 1 FROM item_locations WHERE location_id = OLD.location_id)
BEGIN
  SELECT RAISE(ABORT, 'referenced location canonical fields are immutable');
END;

CREATE TABLE IF NOT EXISTS item_locations (
  item_location_id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  location_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('primary', 'pickup', 'dropoff', 'meeting_link', 'context')),
  created_at_utc TEXT NOT NULL,
  UNIQUE (item_id, version, role),
  FOREIGN KEY (item_id, version)
    REFERENCES coordination_item_versions (item_id, version)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (location_id)
    REFERENCES locations (location_id)
    DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS item_subject_roles (
  item_subject_role_id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  subject_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('participant', 'assignee', 'watcher', 'owner', 'recipient')),
  status TEXT NOT NULL CHECK (status IN ('active', 'inactive')),
  created_at_utc TEXT NOT NULL,
  UNIQUE (item_id, version, subject_id, role),
  FOREIGN KEY (item_id, version)
    REFERENCES coordination_item_versions (item_id, version)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (subject_id)
    REFERENCES subjects (subject_id)
    DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS notification_policies (
  policy_id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  recipient_subject_id TEXT NOT NULL,
  channel_preference_ref TEXT,
  trigger_anchor_id TEXT NOT NULL,
  quiet_hours_policy_ref TEXT,
  status TEXT NOT NULL CHECK (status IN ('active', 'disabled')),
  created_at_utc TEXT NOT NULL,
  UNIQUE (item_id, version, recipient_subject_id, trigger_anchor_id),
  FOREIGN KEY (item_id, version)
    REFERENCES coordination_item_versions (item_id, version)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (recipient_subject_id)
    REFERENCES subjects (subject_id)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (trigger_anchor_id)
    REFERENCES temporal_anchors (anchor_id)
    DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS coordination_item_relations (
  relation_id TEXT PRIMARY KEY,
  source_item_id TEXT NOT NULL,
  target_item_id TEXT NOT NULL,
  relation_type TEXT NOT NULL CHECK (relation_type IN ('depends_on', 'part_of')),
  relation_status TEXT NOT NULL CHECK (relation_status IN ('active', 'inactive')),
  created_at_utc TEXT NOT NULL,
  created_by_subject_id TEXT NOT NULL,
  metadata_json TEXT,
  FOREIGN KEY (source_item_id)
    REFERENCES coordination_items (item_id)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (target_item_id)
    REFERENCES coordination_items (item_id)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (created_by_subject_id)
    REFERENCES subjects (subject_id)
    DEFERRABLE INITIALLY DEFERRED
);

CREATE UNIQUE INDEX IF NOT EXISTS coordination_item_relations_active_unique
ON coordination_item_relations (source_item_id, target_item_id, relation_type)
WHERE relation_status = 'active';

CREATE TABLE IF NOT EXISTS work_instances (
  work_instance_id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  item_version INTEGER NOT NULL,
  notification_policy_id TEXT,
  notification_policy_item_version INTEGER,
  source_work_instance_id TEXT,
  generation_source_kind TEXT CHECK (
    generation_source_kind IN ('work_instance', 'notification_policy', 'schedule_tick', 'user_action', 'item_version')
  ),
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
    (
      generation_source_kind IS NULL
      AND source_work_instance_id IS NULL
    )
    OR (
      generation_source_kind = 'work_instance'
      AND source_work_instance_id IS NOT NULL
      AND work_subject_ref IS NOT NULL
      AND policy_basis_ref IS NOT NULL
    )
    OR (
      generation_source_kind IS NOT NULL
      AND generation_source_kind != 'work_instance'
      AND source_work_instance_id IS NULL
      AND generation_source_ref IS NOT NULL
      AND work_subject_ref IS NOT NULL
      AND policy_basis_ref IS NOT NULL
    )
  ),
  CHECK (
    (notification_policy_id IS NULL AND notification_policy_item_version IS NULL)
    OR (notification_policy_id IS NOT NULL AND notification_policy_item_version IS NOT NULL)
  ),
  FOREIGN KEY (item_id, item_version)
    REFERENCES coordination_item_versions (item_id, version)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (notification_policy_id)
    REFERENCES notification_policies (policy_id)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (source_work_instance_id)
    REFERENCES work_instances (work_instance_id)
    DEFERRABLE INITIALLY DEFERRED
);

CREATE TRIGGER IF NOT EXISTS work_instances_notification_policy_binding_insert
BEFORE INSERT ON work_instances
FOR EACH ROW
WHEN NEW.notification_policy_id IS NOT NULL
AND NOT EXISTS (
  SELECT 1
  FROM notification_policies
  WHERE policy_id = NEW.notification_policy_id
    AND item_id = NEW.item_id
    AND version = NEW.notification_policy_item_version
    AND version = NEW.item_version
)
BEGIN
  SELECT RAISE(ABORT, 'work_instances notification policy binding is invalid');
END;

CREATE TABLE IF NOT EXISTS candidate_actions (
  candidate_action_id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  item_version INTEGER NOT NULL,
  action_kind TEXT NOT NULL CHECK (
    action_kind IN ('deliver_notification', 'sync_projection', 'request_user_decision')
  ),
  urgency TEXT,
  status TEXT NOT NULL CHECK (status IN ('open', 'resolved', 'dismissed')),
  evidence_ref TEXT,
  requires_approval INTEGER NOT NULL CHECK (requires_approval IN (0, 1)),
  created_at_utc TEXT NOT NULL,
  resolved_at_utc TEXT,
  CHECK (
    (status = 'open' AND resolved_at_utc IS NULL)
    OR (status IN ('resolved', 'dismissed') AND resolved_at_utc IS NOT NULL)
  ),
  FOREIGN KEY (item_id, item_version)
    REFERENCES coordination_item_versions (item_id, version)
    DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS external_projections (
  projection_id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  adapter_name TEXT NOT NULL CHECK (length(adapter_name) > 0),
  external_ref TEXT NOT NULL CHECK (length(external_ref) > 0),
  projection_status TEXT NOT NULL CHECK (projection_status IN ('current', 'stale', 'failed')),
  last_projected_version INTEGER,
  last_attempt_id TEXT,
  stale_reason TEXT,
  updated_at_utc TEXT NOT NULL,
  UNIQUE (adapter_name, external_ref),
  CHECK (
    (projection_status = 'current' AND last_projected_version IS NOT NULL AND stale_reason IS NULL)
    OR (projection_status = 'stale' AND last_projected_version IS NOT NULL AND stale_reason IS NOT NULL)
    OR (projection_status = 'failed')
  ),
  FOREIGN KEY (item_id)
    REFERENCES coordination_items (item_id)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (item_id, last_projected_version)
    REFERENCES coordination_item_versions (item_id, version)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (last_attempt_id)
    REFERENCES side_effect_attempts (attempt_id)
    DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS side_effect_attempts (
  attempt_id TEXT PRIMARY KEY,
  work_instance_id TEXT,
  candidate_action_id TEXT,
  item_id TEXT,
  adapter_name TEXT NOT NULL CHECK (length(adapter_name) > 0),
  projection_id TEXT,
  source_item_version INTEGER,
  idempotency_key TEXT NOT NULL CHECK (length(idempotency_key) > 0),
  attempt_status TEXT NOT NULL CHECK (attempt_status IN ('started', 'succeeded', 'failed', 'rejected')),
  provider_ref TEXT,
  request_payload_hash TEXT NOT NULL CHECK (
    length(request_payload_hash) = 64 AND request_payload_hash NOT GLOB '*[^0-9a-f]*'
  ),
  request_hash TEXT NOT NULL CHECK (
    length(request_hash) = 64 AND request_hash NOT GLOB '*[^0-9a-f]*'
  ),
  response_hash TEXT CHECK (
    response_hash IS NULL OR (length(response_hash) = 64 AND response_hash NOT GLOB '*[^0-9a-f]*')
  ),
  reason_code TEXT,
  attempted_at_utc TEXT NOT NULL,
  completed_at_utc TEXT,
  UNIQUE (adapter_name, idempotency_key),
  CHECK (
    (work_instance_id IS NOT NULL OR candidate_action_id IS NOT NULL OR projection_id IS NOT NULL)
    AND NOT (work_instance_id IS NOT NULL AND candidate_action_id IS NOT NULL)
  ),
  CHECK (
    (attempt_status = 'started' AND completed_at_utc IS NULL)
    OR (attempt_status IN ('succeeded', 'failed', 'rejected') AND completed_at_utc IS NOT NULL)
  ),
  CHECK (
    (projection_id IS NULL)
    OR (item_id IS NOT NULL AND source_item_version IS NOT NULL)
  ),
  FOREIGN KEY (work_instance_id)
    REFERENCES work_instances (work_instance_id)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (candidate_action_id)
    REFERENCES candidate_actions (candidate_action_id)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (item_id)
    REFERENCES coordination_items (item_id)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (item_id, source_item_version)
    REFERENCES coordination_item_versions (item_id, version)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (projection_id)
    REFERENCES external_projections (projection_id)
    DEFERRABLE INITIALLY DEFERRED
);

CREATE TRIGGER IF NOT EXISTS side_effect_attempts_origin_binding_insert
BEFORE INSERT ON side_effect_attempts
FOR EACH ROW
WHEN (
  NEW.work_instance_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM work_instances
    WHERE work_instance_id = NEW.work_instance_id
      AND item_id = NEW.item_id
      AND (
        NEW.projection_id IS NULL
        OR item_version = NEW.source_item_version
      )
  )
)
OR (
  NEW.candidate_action_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM candidate_actions
    WHERE candidate_action_id = NEW.candidate_action_id
      AND item_id = NEW.item_id
      AND (
        NEW.projection_id IS NULL
        OR item_version = NEW.source_item_version
      )
  )
)
OR (
  NEW.projection_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM external_projections
    WHERE projection_id = NEW.projection_id
      AND item_id = NEW.item_id
  )
)
BEGIN
  SELECT RAISE(ABORT, 'side_effect_attempts origin binding is invalid');
END;

CREATE TRIGGER IF NOT EXISTS side_effect_attempts_staleness_insert
BEFORE INSERT ON side_effect_attempts
FOR EACH ROW
WHEN (
  NEW.work_instance_id IS NOT NULL
  AND EXISTS (
    SELECT 1
    FROM work_instances AS w
    JOIN coordination_items AS i ON i.item_id = w.item_id
    WHERE w.work_instance_id = NEW.work_instance_id
      AND i.current_version != w.item_version
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
  SELECT RAISE(ABORT, 'side_effect_attempts source item version is stale');
END;

CREATE TABLE IF NOT EXISTS audit_log (
  audit_id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  stage TEXT NOT NULL CHECK (length(stage) > 0),
  action TEXT NOT NULL CHECK (length(action) > 0),
  reason_code TEXT,
  actor_ref TEXT,
  causation_id TEXT,
  correlation_id TEXT,
  payload_hash TEXT NOT NULL CHECK (
    length(payload_hash) = 64 AND payload_hash NOT GLOB '*[^0-9a-f]*'
  ),
  created_at_utc TEXT NOT NULL,
  FOREIGN KEY (item_id)
    REFERENCES coordination_items (item_id)
    DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS ledger_schema (
  schema_version INTEGER PRIMARY KEY,
  applied_at_utc TEXT NOT NULL
);

INSERT OR IGNORE INTO ledger_schema (schema_version, applied_at_utc)
VALUES (1, '1970-01-01T00:00:00Z');
