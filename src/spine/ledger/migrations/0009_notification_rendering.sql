BEGIN IMMEDIATE;

CREATE TABLE notification_renderings (
  notification_rendering_id TEXT PRIMARY KEY,
  attempt_id TEXT NOT NULL UNIQUE,
  work_instance_id TEXT NOT NULL,
  notification_opportunity_id TEXT NOT NULL,
  notification_intent_id TEXT NOT NULL,
  item_id TEXT NOT NULL,
  rendered_item_version INTEGER NOT NULL CHECK (rendered_item_version >= 1),
  rendering_contract TEXT NOT NULL CHECK (rendering_contract = 'spine.notification-rendering.v1'),
  rendering_profile TEXT NOT NULL CHECK (rendering_profile = 'spine.notification-rendering.concise-en-ca.v1'),
  input_normalization_version TEXT NOT NULL CHECK (input_normalization_version = 'spine.notification-rendering-input.v1'),
  canonical_json_version TEXT NOT NULL CHECK (canonical_json_version = 'spine.canonical-json.v1'),
  rendering_input_hash TEXT NOT NULL CHECK (
    length(rendering_input_hash) = 64 AND rendering_input_hash NOT GLOB '*[^0-9a-f]*'
  ),
  rendered_content_hash TEXT NOT NULL CHECK (
    length(rendered_content_hash) = 64 AND rendered_content_hash NOT GLOB '*[^0-9a-f]*'
  ),
  body_text TEXT NOT NULL CHECK (length(body_text) BETWEEN 1 AND 1024),
  phrase_kind TEXT NOT NULL CHECK (phrase_kind IN (
    'future_relative', 'future_calendar', 'now',
    'past_relative', 'past_calendar', 'date_calendar'
  )),
  attempted_at_utc TEXT NOT NULL,
  target_scheduled_fact TEXT NOT NULL,
  target_at_utc TEXT,
  display_time_basis TEXT NOT NULL CHECK (display_time_basis IN ('local_date', 'local_instant', 'instant_utc')),
  display_timezone TEXT NOT NULL,
  timezone_database_version TEXT,
  delta_seconds INTEGER,
  occurrence_provenance_id TEXT,
  recurrence_revision_id TEXT,
  occurrence_key TEXT,
  temporal_binding_id TEXT,
  temporal_binding_revision_id TEXT,
  location_id TEXT,
  item_location_id TEXT,
  location_kind TEXT CHECK (location_kind IN ('address', 'place', 'virtual', 'relative', 'unknown')),
  location_label TEXT,
  source_input_json TEXT NOT NULL,
  phrase_facts_json TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  CHECK (created_at_utc = attempted_at_utc),
  CHECK (
    (display_time_basis = 'instant_utc' AND display_timezone = 'UTC' AND timezone_database_version IS NULL AND target_at_utc IS NOT NULL)
    OR (display_time_basis = 'local_instant' AND timezone_database_version IS NOT NULL AND target_at_utc IS NOT NULL)
    OR (display_time_basis = 'local_date' AND timezone_database_version IS NOT NULL AND target_at_utc IS NULL AND delta_seconds IS NULL)
  ),
  CHECK (
    (occurrence_provenance_id IS NULL AND recurrence_revision_id IS NULL AND occurrence_key IS NULL)
    OR (occurrence_provenance_id IS NOT NULL AND recurrence_revision_id IS NOT NULL AND occurrence_key IS NOT NULL)
  ),
  CHECK (
    (temporal_binding_id IS NULL AND temporal_binding_revision_id IS NULL)
    OR (temporal_binding_id IS NOT NULL AND temporal_binding_revision_id IS NOT NULL)
  ),
  CHECK (
    (location_id IS NULL AND item_location_id IS NULL AND location_kind IS NULL AND location_label IS NULL)
    OR (location_id IS NOT NULL AND item_location_id IS NOT NULL AND location_kind IS NOT NULL AND location_label IS NOT NULL)
  ),
  FOREIGN KEY (attempt_id) REFERENCES side_effect_attempts (attempt_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (work_instance_id) REFERENCES work_instances (work_instance_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (item_id, rendered_item_version)
    REFERENCES coordination_item_versions (item_id, version) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (occurrence_provenance_id)
    REFERENCES occurrence_provenance (occurrence_provenance_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (recurrence_revision_id)
    REFERENCES recurrence_revisions (recurrence_revision_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (temporal_binding_id)
    REFERENCES relative_temporal_bindings (temporal_binding_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (temporal_binding_revision_id)
    REFERENCES relative_temporal_binding_revisions (temporal_binding_revision_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (location_id) REFERENCES locations (location_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (item_location_id) REFERENCES item_locations (item_location_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX notification_renderings_item_attempt_idx
ON notification_renderings (item_id, attempted_at_utc, attempt_id);

CREATE TRIGGER notification_renderings_attempt_binding_insert
BEFORE INSERT ON notification_renderings
FOR EACH ROW
WHEN NOT EXISTS (
  SELECT 1 FROM side_effect_attempts AS a
  WHERE a.attempt_id = NEW.attempt_id
    AND a.work_instance_id = NEW.work_instance_id
    AND a.item_id = NEW.item_id
    AND a.attempt_status = 'started'
    AND a.attempted_at_utc = NEW.attempted_at_utc
)
BEGIN
  SELECT RAISE(ABORT, 'notification rendering attempt binding is invalid');
END;

COMMIT;
