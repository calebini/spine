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
