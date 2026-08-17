BEGIN IMMEDIATE;

CREATE TABLE relative_temporal_bindings (
  temporal_binding_id TEXT PRIMARY KEY,
  binding_contract TEXT NOT NULL CHECK (binding_contract = 'spine.relative-temporal-binding.v1'),
  target_item_id TEXT NOT NULL,
  target_anchor_role TEXT NOT NULL CHECK (target_anchor_role = 'task_due'),
  source_item_id TEXT NOT NULL,
  source_anchor_role TEXT NOT NULL CHECK (source_anchor_role = 'event_start'),
  relationship_id TEXT NOT NULL,
  binding_mode TEXT NOT NULL CHECK (binding_mode IN ('snapshot', 'follow_source')),
  source_terminal_behavior TEXT CHECK (source_terminal_behavior IN ('cancel_target', 'detach_at_last_value', 'require_decision')),
  created_by_command_id TEXT NOT NULL,
  created_by_subject_id TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  binding_status TEXT NOT NULL CHECK (binding_status IN ('active', 'retired')),
  retired_at_utc TEXT,
  retired_by_command_id TEXT,
  CHECK (
    (binding_mode = 'snapshot' AND source_terminal_behavior IS NULL)
    OR (binding_mode = 'follow_source' AND source_terminal_behavior IS NOT NULL)
  ),
  CHECK (
    (binding_status = 'active' AND retired_at_utc IS NULL AND retired_by_command_id IS NULL)
    OR (binding_status = 'retired' AND retired_at_utc IS NOT NULL AND retired_by_command_id IS NOT NULL)
  ),
  FOREIGN KEY (target_item_id) REFERENCES coordination_items (item_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (source_item_id) REFERENCES coordination_items (item_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (relationship_id) REFERENCES coordination_item_relations (relation_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (created_by_subject_id) REFERENCES subjects (subject_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE UNIQUE INDEX relative_temporal_bindings_active_target_unique
ON relative_temporal_bindings (target_item_id, target_anchor_role)
WHERE binding_status = 'active';

CREATE INDEX relative_temporal_bindings_source_status_idx
ON relative_temporal_bindings (source_item_id, binding_status, temporal_binding_id);

CREATE INDEX relative_temporal_bindings_target_status_idx
ON relative_temporal_bindings (target_item_id, binding_status, temporal_binding_id);

CREATE TABLE relative_temporal_binding_revisions (
  temporal_binding_revision_id TEXT PRIMARY KEY,
  temporal_binding_id TEXT NOT NULL,
  revision_index INTEGER NOT NULL CHECK (revision_index >= 1),
  source_temporal_binding_revision_id TEXT,
  source_target_version INTEGER NOT NULL CHECK (source_target_version >= 1),
  source_scope TEXT NOT NULL CHECK (source_scope IN ('item', 'selected_occurrence')),
  source_anchor_id TEXT,
  source_recurrence_revision_id TEXT,
  source_occurrence_key TEXT,
  source_occurrence_selector_ref TEXT,
  source_occurrence_provenance_id TEXT,
  source_scheduled_fact TEXT NOT NULL,
  offset_basis TEXT NOT NULL CHECK (offset_basis = 'elapsed'),
  offset_seconds INTEGER NOT NULL CHECK (offset_seconds BETWEEN -31622400 AND 31622400),
  resolved_source_utc TEXT NOT NULL,
  resolved_target_utc TEXT NOT NULL,
  target_local_date TEXT NOT NULL,
  target_local_time TEXT NOT NULL,
  target_timezone TEXT NOT NULL,
  target_timezone_database_version TEXT NOT NULL,
  target_item_version INTEGER NOT NULL CHECK (target_item_version >= 1),
  target_anchor_id TEXT NOT NULL,
  resolution_kind TEXT NOT NULL CHECK (resolution_kind IN (
    'initial', 'target_rescheduled', 'source_refreshed', 'detached',
    'source_terminal', 'target_terminal', 'relationship_inactive'
  )),
  normalized_temporal_binding_revision_hash TEXT NOT NULL CHECK (
    length(normalized_temporal_binding_revision_hash) = 64
    AND normalized_temporal_binding_revision_hash NOT GLOB '*[^0-9a-f]*'
  ),
  created_by_command_id TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  CHECK (
    (source_scope = 'item'
      AND source_anchor_id IS NOT NULL
      AND source_recurrence_revision_id IS NULL
      AND source_occurrence_key IS NULL
      AND source_occurrence_selector_ref IS NULL
      AND source_occurrence_provenance_id IS NULL)
    OR
    (source_scope = 'selected_occurrence'
      AND source_anchor_id IS NULL
      AND source_recurrence_revision_id IS NOT NULL
      AND source_occurrence_key IS NOT NULL
      AND source_occurrence_selector_ref IS NOT NULL
      AND source_occurrence_provenance_id IS NOT NULL)
  ),
  UNIQUE (temporal_binding_id, revision_index),
  FOREIGN KEY (temporal_binding_id) REFERENCES relative_temporal_bindings (temporal_binding_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (source_temporal_binding_revision_id) REFERENCES relative_temporal_binding_revisions (temporal_binding_revision_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (source_anchor_id) REFERENCES temporal_anchors (anchor_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (source_recurrence_revision_id) REFERENCES recurrence_revisions (recurrence_revision_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (source_occurrence_selector_ref) REFERENCES recurrence_target_occurrence_selectors (target_occurrence_selector_ref) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (source_occurrence_provenance_id) REFERENCES occurrence_provenance (occurrence_provenance_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (target_anchor_id) REFERENCES temporal_anchors (anchor_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX relative_temporal_binding_revisions_binding_idx
ON relative_temporal_binding_revisions (temporal_binding_id, revision_index DESC);

CREATE TABLE temporal_binding_catalog_state (
  singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
  binding_catalog_generation INTEGER NOT NULL CHECK (binding_catalog_generation >= 0)
);

INSERT INTO temporal_binding_catalog_state (singleton_id, binding_catalog_generation) VALUES (1, 0);

-- Item/recurrence/relation commands already write one audit row for their canonical
-- mutation. Invalidate binding-list cursors only when that item participates in an
-- active binding. Binding-family commands increment the generation explicitly so
-- their multi-row atomic transaction advances it exactly once.
CREATE TRIGGER temporal_binding_catalog_related_item_audit
AFTER INSERT ON audit_log
WHEN NEW.action NOT IN (
  'related_task_schedule_created',
  'binding_reconciled',
  'binding_target_cancelled',
  'binding_target_rescheduled'
)
AND EXISTS (
  SELECT 1 FROM relative_temporal_bindings AS b
  WHERE b.binding_status = 'active'
    AND (b.source_item_id = NEW.item_id OR b.target_item_id = NEW.item_id)
)
BEGIN
  UPDATE temporal_binding_catalog_state
  SET binding_catalog_generation = binding_catalog_generation + 1
  WHERE singleton_id = 1;
END;

COMMIT;
