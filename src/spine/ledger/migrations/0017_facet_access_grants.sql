CREATE TABLE access_grants_new (
  grant_id TEXT PRIMARY KEY,
  current_revision INTEGER NOT NULL CHECK (current_revision >= 1),
  resource_kind TEXT NOT NULL CHECK (resource_kind IN ('item','item_archetype','notification_profile','facet_schema')),
  resource_id TEXT NOT NULL,
  resource_owner_revision INTEGER NOT NULL CHECK (resource_owner_revision >= 1),
  grantee_kind TEXT NOT NULL CHECK (grantee_kind IN ('subject','subject_group')),
  grantee_subject_id TEXT REFERENCES subjects(subject_id),
  grantee_group_id TEXT REFERENCES subject_groups(group_id),
  status TEXT NOT NULL CHECK (status IN ('active','revoked')),
  starts_at_utc TEXT NOT NULL,
  ends_at_utc TEXT,
  created_by_command_id TEXT NOT NULL,
  grantor_subject_id TEXT NOT NULL REFERENCES subjects(subject_id),
  CHECK (ends_at_utc IS NULL OR ends_at_utc > starts_at_utc),
  CHECK ((grantee_kind='subject' AND grantee_subject_id IS NOT NULL AND grantee_group_id IS NULL)
      OR (grantee_kind='subject_group' AND grantee_group_id IS NOT NULL AND grantee_subject_id IS NULL)),
  CHECK (resource_kind!='facet_schema' OR resource_owner_revision=1),
  FOREIGN KEY (grant_id,current_revision) REFERENCES access_grant_revisions(grant_id,revision) DEFERRABLE INITIALLY DEFERRED
);
INSERT INTO access_grants_new SELECT * FROM access_grants;
DROP TABLE access_grants;
ALTER TABLE access_grants_new RENAME TO access_grants;
CREATE TRIGGER web_grant_facet_schema_delete BEFORE DELETE ON facet_schemas
WHEN EXISTS(SELECT 1 FROM access_grants WHERE resource_kind='facet_schema' AND resource_id=OLD.facet_schema_id)
BEGIN SELECT RAISE(ABORT,'access grant retains resource'); END;
CREATE TRIGGER web_grant_facet_schema_insert BEFORE INSERT ON access_grants
WHEN NEW.resource_kind='facet_schema' AND NOT EXISTS(SELECT 1 FROM facet_schemas WHERE facet_schema_id=NEW.resource_id)
BEGIN SELECT RAISE(ABORT,'facet grant requires resource'); END;
CREATE TRIGGER web_grant_facet_schema_update BEFORE UPDATE ON access_grants
WHEN NEW.resource_kind='facet_schema' AND NOT EXISTS(SELECT 1 FROM facet_schemas WHERE facet_schema_id=NEW.resource_id)
BEGIN SELECT RAISE(ABORT,'facet grant requires resource'); END;
