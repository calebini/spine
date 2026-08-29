BEGIN IMMEDIATE;

CREATE TABLE owner_scope_catalog_state (
  singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
  owner_scope_generation INTEGER NOT NULL CHECK (owner_scope_generation >= 0)
);

INSERT INTO owner_scope_catalog_state (singleton_id, owner_scope_generation)
VALUES (1, 0);

CREATE INDEX subjects_owner_scope_list_idx
ON subjects (status, subject_kind, subject_id);

CREATE INDEX subject_groups_owner_scope_list_idx
ON subject_groups (status, group_kind, group_id);

CREATE TRIGGER subjects_owner_scope_insert
AFTER INSERT ON subjects
BEGIN
  UPDATE owner_scope_catalog_state
  SET owner_scope_generation = owner_scope_generation + 1
  WHERE singleton_id = 1;
END;

CREATE TRIGGER subjects_owner_scope_update
AFTER UPDATE OF subject_kind, display_name, status ON subjects
WHEN OLD.subject_kind IS NOT NEW.subject_kind
  OR OLD.display_name IS NOT NEW.display_name
  OR OLD.status IS NOT NEW.status
BEGIN
  UPDATE owner_scope_catalog_state
  SET owner_scope_generation = owner_scope_generation + 1
  WHERE singleton_id = 1;
END;

CREATE TRIGGER subject_groups_owner_scope_insert
AFTER INSERT ON subject_groups
BEGIN
  UPDATE owner_scope_catalog_state
  SET owner_scope_generation = owner_scope_generation + 1
  WHERE singleton_id = 1;
END;

CREATE TRIGGER subject_groups_owner_scope_update
AFTER UPDATE OF group_kind, display_name, status ON subject_groups
WHEN OLD.group_kind IS NOT NEW.group_kind
  OR OLD.display_name IS NOT NEW.display_name
  OR OLD.status IS NOT NEW.status
BEGIN
  UPDATE owner_scope_catalog_state
  SET owner_scope_generation = owner_scope_generation + 1
  WHERE singleton_id = 1;
END;

COMMIT;
