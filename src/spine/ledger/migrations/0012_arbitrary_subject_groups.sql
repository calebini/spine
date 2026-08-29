BEGIN IMMEDIATE;

DROP TRIGGER subject_groups_owner_scope_update;
DROP INDEX subject_groups_owner_scope_list_idx;

ALTER TABLE subject_groups DROP COLUMN group_kind;

CREATE INDEX subject_groups_owner_scope_list_idx
ON subject_groups (status, group_id);

CREATE TRIGGER subject_groups_owner_scope_update
AFTER UPDATE OF display_name, status ON subject_groups
WHEN OLD.display_name IS NOT NEW.display_name
  OR OLD.status IS NOT NEW.status
BEGIN
  UPDATE owner_scope_catalog_state
  SET owner_scope_generation = owner_scope_generation + 1
  WHERE singleton_id = 1;
END;

COMMIT;
