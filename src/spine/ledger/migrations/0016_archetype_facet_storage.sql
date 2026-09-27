-- Schema 16: facet storage foundation. Applied inside the migration-owned transaction.

CREATE TABLE facet_schemas (
  facet_schema_id TEXT NOT NULL CHECK ((typeof(facet_schema_id)='text' AND length(facet_schema_id)>0)) PRIMARY KEY,
  owner_kind TEXT NOT NULL CHECK ((typeof(owner_kind)='text' AND length(owner_kind)>0)),
  owner_subject_id TEXT CHECK (owner_subject_id IS NULL OR (typeof(owner_subject_id)='text' AND length(owner_subject_id)>0)),
  owner_group_id TEXT CHECK (owner_group_id IS NULL OR (typeof(owner_group_id)='text' AND length(owner_group_id)>0)),
  schema_key TEXT NOT NULL CHECK ((typeof(schema_key)='text' AND length(schema_key)>0)) CHECK (length(schema_key) BETWEEN 1 AND 64 AND substr(schema_key,1,1) GLOB '[a-z]' AND schema_key NOT GLOB '*[^a-z0-9_]*'),
  status TEXT NOT NULL CHECK ((typeof(status)='text' AND length(status)>0)),
  current_revision_id TEXT NOT NULL CHECK ((typeof(current_revision_id)='text' AND length(current_revision_id)>0)),
  created_command_receipt_id TEXT NOT NULL CHECK ((typeof(created_command_receipt_id)='text' AND length(created_command_receipt_id)>0)),
  retired_command_receipt_id TEXT CHECK (retired_command_receipt_id IS NULL OR (typeof(retired_command_receipt_id)='text' AND length(retired_command_receipt_id)>0)),
  CHECK ((owner_kind='system' AND owner_subject_id IS NULL AND owner_group_id IS NULL) OR (owner_kind='subject' AND owner_subject_id IS NOT NULL AND owner_group_id IS NULL) OR (owner_kind='subject_group' AND owner_subject_id IS NULL AND owner_group_id IS NOT NULL)),
  CHECK ((status='active' AND retired_command_receipt_id IS NULL) OR (status='retired' AND retired_command_receipt_id IS NOT NULL)),
  FOREIGN KEY (owner_subject_id) REFERENCES subjects (subject_id) ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (owner_group_id) REFERENCES subject_groups (group_id) ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (facet_schema_id, current_revision_id) REFERENCES facet_schema_revisions (facet_schema_id, facet_schema_revision_id) ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (created_command_receipt_id) REFERENCES command_receipts (command_receipt_id) ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (retired_command_receipt_id) REFERENCES command_receipts (command_receipt_id) ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE facet_schema_revisions (
  facet_schema_revision_id TEXT NOT NULL CHECK ((typeof(facet_schema_revision_id)='text' AND length(facet_schema_revision_id)>0)) PRIMARY KEY,
  facet_schema_id TEXT NOT NULL CHECK ((typeof(facet_schema_id)='text' AND length(facet_schema_id)>0)),
  revision_number INTEGER NOT NULL CHECK ((typeof(revision_number)='integer' AND revision_number >= 1)),
  definition_contract_version TEXT NOT NULL CHECK ((typeof(definition_contract_version)='text' AND length(definition_contract_version)>0)) CHECK (definition_contract_version='spine.facet-schemas.v1'),
  canonical_json_version TEXT NOT NULL CHECK ((typeof(canonical_json_version)='text' AND length(canonical_json_version)>0)) CHECK (canonical_json_version='spine.canonical-json.v1'),
  definition_json TEXT NOT NULL CHECK ((typeof(definition_json)='text' AND length(definition_json)>0)) CHECK (length(CAST(definition_json AS BLOB))<=32768 AND json_valid(definition_json) AND json_type(definition_json)='object'),
  definition_hash TEXT NOT NULL CHECK ((typeof(definition_hash)='text' AND length(definition_hash)>0)) CHECK (length(definition_hash)=64 AND definition_hash NOT GLOB '*[^0-9a-f]*'),
  created_command_receipt_id TEXT NOT NULL CHECK ((typeof(created_command_receipt_id)='text' AND length(created_command_receipt_id)>0)),
  UNIQUE (facet_schema_id,revision_number),
  UNIQUE (facet_schema_id,facet_schema_revision_id),
  FOREIGN KEY (facet_schema_id) REFERENCES facet_schemas (facet_schema_id) ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (created_command_receipt_id) REFERENCES command_receipts (command_receipt_id) ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE facet_schema_fields (
  facet_schema_revision_id TEXT NOT NULL CHECK ((typeof(facet_schema_revision_id)='text' AND length(facet_schema_revision_id)>0)),
  field_key TEXT NOT NULL CHECK ((typeof(field_key)='text' AND length(field_key)>0)) CHECK (length(field_key) BETWEEN 1 AND 64 AND substr(field_key,1,1) GLOB '[a-z]' AND field_key NOT GLOB '*[^a-z0-9_]*'),
  value_type TEXT NOT NULL CHECK ((typeof(value_type)='text' AND length(value_type)>0)) CHECK (value_type IN ('text','enum','boolean','integer','date','reference')),
  required INTEGER NOT NULL CHECK ((typeof(required)='integer' AND required IN (0,1))),
  queryable INTEGER NOT NULL CHECK ((typeof(queryable)='integer' AND queryable IN (0,1))),
  target_kind TEXT NOT NULL CHECK ((typeof(target_kind)='text' AND length(target_kind)>0)),
  CHECK ((value_type='reference' AND target_kind IN ('subject','location')) OR (value_type!='reference' AND target_kind='none')),
  PRIMARY KEY (facet_schema_revision_id,field_key),
  UNIQUE (facet_schema_revision_id,field_key,value_type,queryable),
  UNIQUE (facet_schema_revision_id,field_key,value_type,target_kind),
  FOREIGN KEY (facet_schema_revision_id) REFERENCES facet_schema_revisions (facet_schema_revision_id) ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE archetype_facet_bindings (
  facet_binding_id TEXT NOT NULL CHECK ((typeof(facet_binding_id)='text' AND length(facet_binding_id)>0)) PRIMARY KEY,
  item_archetype_id TEXT NOT NULL CHECK ((typeof(item_archetype_id)='text' AND length(item_archetype_id)>0)),
  facet_key TEXT NOT NULL CHECK ((typeof(facet_key)='text' AND length(facet_key)>0)) CHECK (length(facet_key) BETWEEN 1 AND 64 AND substr(facet_key,1,1) GLOB '[a-z]' AND facet_key NOT GLOB '*[^a-z0-9_]*'),
  facet_schema_revision_id TEXT NOT NULL CHECK ((typeof(facet_schema_revision_id)='text' AND length(facet_schema_revision_id)>0)),
  status TEXT NOT NULL CHECK ((typeof(status)='text' AND length(status)>0)),
  created_command_receipt_id TEXT NOT NULL CHECK ((typeof(created_command_receipt_id)='text' AND length(created_command_receipt_id)>0)),
  ended_command_receipt_id TEXT CHECK (ended_command_receipt_id IS NULL OR (typeof(ended_command_receipt_id)='text' AND length(ended_command_receipt_id)>0)),
  CHECK ((status='active' AND ended_command_receipt_id IS NULL) OR (status IN ('superseded','retired') AND ended_command_receipt_id IS NOT NULL)),
  UNIQUE (facet_binding_id,item_archetype_id,facet_key,facet_schema_revision_id),
  FOREIGN KEY (item_archetype_id) REFERENCES item_archetypes (item_archetype_id) ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (facet_schema_revision_id) REFERENCES facet_schema_revisions (facet_schema_revision_id) ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (created_command_receipt_id) REFERENCES command_receipts (command_receipt_id) ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (ended_command_receipt_id) REFERENCES command_receipts (command_receipt_id) ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE item_facet_snapshots (
  item_id TEXT NOT NULL CHECK ((typeof(item_id)='text' AND length(item_id)>0)),
  item_version INTEGER NOT NULL CHECK ((typeof(item_version)='integer' AND item_version>=1)),
  entry_count INTEGER NOT NULL CHECK ((typeof(entry_count)='integer' AND entry_count BETWEEN 0 AND 8)),
  values_bytes INTEGER NOT NULL CHECK ((typeof(values_bytes)='integer' AND values_bytes BETWEEN 2 AND 65536)),
  PRIMARY KEY (item_id,item_version),
  FOREIGN KEY (item_id,item_version) REFERENCES coordination_item_versions (item_id,version) ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE item_facet_entries (
  item_id TEXT NOT NULL CHECK ((typeof(item_id)='text' AND length(item_id)>0)),
  item_version INTEGER NOT NULL CHECK ((typeof(item_version)='integer' AND item_version>=1)),
  facet_key TEXT NOT NULL CHECK ((typeof(facet_key)='text' AND length(facet_key)>0)) CHECK (length(facet_key) BETWEEN 1 AND 64 AND substr(facet_key,1,1) GLOB '[a-z]' AND facet_key NOT GLOB '*[^a-z0-9_]*'),
  facet_schema_revision_id TEXT NOT NULL CHECK ((typeof(facet_schema_revision_id)='text' AND length(facet_schema_revision_id)>0)),
  facet_binding_id TEXT NOT NULL CHECK ((typeof(facet_binding_id)='text' AND length(facet_binding_id)>0)),
  item_archetype_id TEXT NOT NULL CHECK ((typeof(item_archetype_id)='text' AND length(item_archetype_id)>0)),
  item_archetype_revision_id TEXT NOT NULL CHECK ((typeof(item_archetype_revision_id)='text' AND length(item_archetype_revision_id)>0)),
  archetype_selection_source TEXT NOT NULL CHECK ((typeof(archetype_selection_source)='text' AND length(archetype_selection_source)>0)) CHECK (archetype_selection_source IN ('operator_explicit','agent_selected','imported')),
  archetype_source_ref TEXT CHECK (archetype_source_ref IS NULL OR (typeof(archetype_source_ref)='text' AND length(archetype_source_ref)>0)),
  value_contract_version TEXT NOT NULL CHECK ((typeof(value_contract_version)='text' AND length(value_contract_version)>0)) CHECK (value_contract_version='spine.item-facets.v1'),
  values_json TEXT NOT NULL CHECK ((typeof(values_json)='text' AND length(values_json)>0)) CHECK (length(CAST(values_json AS BLOB))<=16384 AND json_valid(values_json) AND json_type(values_json)='object'),
  source_command_receipt_id TEXT NOT NULL CHECK ((typeof(source_command_receipt_id)='text' AND length(source_command_receipt_id)>0)),
  PRIMARY KEY (item_id,item_version,facet_key),
  UNIQUE (item_id,item_version,facet_key,facet_schema_revision_id),
  FOREIGN KEY (item_id,item_version) REFERENCES item_facet_snapshots (item_id,item_version) ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (facet_schema_revision_id) REFERENCES facet_schema_revisions (facet_schema_revision_id) ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (facet_binding_id,item_archetype_id,facet_key,facet_schema_revision_id) REFERENCES archetype_facet_bindings (facet_binding_id,item_archetype_id,facet_key,facet_schema_revision_id) ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (item_archetype_id,item_archetype_revision_id) REFERENCES item_archetype_revisions (item_archetype_id,item_archetype_revision_id) ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (source_command_receipt_id) REFERENCES command_receipts (command_receipt_id) ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE item_facet_references (
  item_id TEXT NOT NULL CHECK ((typeof(item_id)='text' AND length(item_id)>0)),
  item_version INTEGER NOT NULL CHECK ((typeof(item_version)='integer' AND item_version>=1)),
  facet_key TEXT NOT NULL CHECK ((typeof(facet_key)='text' AND length(facet_key)>0)) CHECK (length(facet_key) BETWEEN 1 AND 64 AND substr(facet_key,1,1) GLOB '[a-z]' AND facet_key NOT GLOB '*[^a-z0-9_]*'),
  field_key TEXT NOT NULL CHECK ((typeof(field_key)='text' AND length(field_key)>0)) CHECK (length(field_key) BETWEEN 1 AND 64 AND substr(field_key,1,1) GLOB '[a-z]' AND field_key NOT GLOB '*[^a-z0-9_]*'),
  facet_schema_revision_id TEXT NOT NULL CHECK ((typeof(facet_schema_revision_id)='text' AND length(facet_schema_revision_id)>0)),
  value_type TEXT NOT NULL CHECK ((typeof(value_type)='text' AND length(value_type)>0)) CHECK (value_type='reference'),
  target_kind TEXT NOT NULL CHECK ((typeof(target_kind)='text' AND length(target_kind)>0)),
  subject_id TEXT CHECK (subject_id IS NULL OR (typeof(subject_id)='text' AND length(subject_id)>0)),
  location_id TEXT CHECK (location_id IS NULL OR (typeof(location_id)='text' AND length(location_id)>0)),
  CHECK ((target_kind='subject' AND subject_id IS NOT NULL AND location_id IS NULL) OR (target_kind='location' AND location_id IS NOT NULL AND subject_id IS NULL)),
  PRIMARY KEY (item_id,item_version,facet_key,field_key),
  FOREIGN KEY (item_id,item_version,facet_key,facet_schema_revision_id) REFERENCES item_facet_entries (item_id,item_version,facet_key,facet_schema_revision_id) ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (facet_schema_revision_id,field_key,value_type,target_kind) REFERENCES facet_schema_fields (facet_schema_revision_id,field_key,value_type,target_kind) ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (subject_id) REFERENCES subjects (subject_id) ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (location_id) REFERENCES locations (location_id) ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE item_facet_current_values (
  item_id TEXT NOT NULL CHECK ((typeof(item_id)='text' AND length(item_id)>0)),
  facet_key TEXT NOT NULL CHECK ((typeof(facet_key)='text' AND length(facet_key)>0)) CHECK (length(facet_key) BETWEEN 1 AND 64 AND substr(facet_key,1,1) GLOB '[a-z]' AND facet_key NOT GLOB '*[^a-z0-9_]*'),
  field_key TEXT NOT NULL CHECK ((typeof(field_key)='text' AND length(field_key)>0)) CHECK (length(field_key) BETWEEN 1 AND 64 AND substr(field_key,1,1) GLOB '[a-z]' AND field_key NOT GLOB '*[^a-z0-9_]*'),
  item_version INTEGER NOT NULL CHECK ((typeof(item_version)='integer' AND item_version>=1)),
  facet_schema_revision_id TEXT NOT NULL CHECK ((typeof(facet_schema_revision_id)='text' AND length(facet_schema_revision_id)>0)),
  value_type TEXT NOT NULL CHECK ((typeof(value_type)='text' AND length(value_type)>0)),
  queryable INTEGER NOT NULL CHECK ((typeof(queryable)='integer' AND queryable=1)),
  value_text TEXT CHECK (value_text IS NULL OR (typeof(value_text)='text' AND length(value_text)>0)),
  value_integer INTEGER CHECK (value_integer IS NULL OR (typeof(value_integer)='integer' AND 1=1)),
  CHECK ((value_type IN ('text','enum','date','reference') AND value_text IS NOT NULL AND value_integer IS NULL) OR (value_type='integer' AND value_text IS NULL AND value_integer IS NOT NULL) OR (value_type='boolean' AND value_text IS NULL AND value_integer IS NOT NULL AND value_integer IN (0,1))),
  PRIMARY KEY (item_id,facet_key,field_key),
  FOREIGN KEY (item_id) REFERENCES coordination_items (item_id) ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (item_id,item_version,facet_key,facet_schema_revision_id) REFERENCES item_facet_entries (item_id,item_version,facet_key,facet_schema_revision_id) ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (facet_schema_revision_id,field_key,value_type,queryable) REFERENCES facet_schema_fields (facet_schema_revision_id,field_key,value_type,queryable) ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED
);

CREATE UNIQUE INDEX item_archetype_revisions_root_revision_uq ON item_archetype_revisions (item_archetype_id,item_archetype_revision_id);
CREATE UNIQUE INDEX facet_schemas_system_key_uq ON facet_schemas (schema_key) WHERE owner_kind='system';
CREATE UNIQUE INDEX facet_schemas_subject_key_uq ON facet_schemas (owner_subject_id,schema_key) WHERE owner_kind='subject';
CREATE UNIQUE INDEX facet_schemas_group_key_uq ON facet_schemas (owner_group_id,schema_key) WHERE owner_kind='subject_group';
CREATE UNIQUE INDEX archetype_facet_bindings_active_uq ON archetype_facet_bindings (item_archetype_id,facet_key) WHERE status='active';
CREATE INDEX facet_schemas_owner_list_idx ON facet_schemas (owner_kind,owner_subject_id,owner_group_id,status,facet_schema_id);
CREATE INDEX archetype_facet_bindings_list_idx ON archetype_facet_bindings (item_archetype_id,status,facet_key);
CREATE INDEX archetype_facet_bindings_revision_idx ON archetype_facet_bindings (facet_schema_revision_id,facet_binding_id);
CREATE INDEX item_facet_entries_revision_idx ON item_facet_entries (facet_schema_revision_id,item_id,item_version,facet_key);
CREATE INDEX item_facet_entries_binding_idx ON item_facet_entries (facet_binding_id,item_id,item_version,facet_key);
CREATE INDEX item_facet_entries_archetype_revision_idx ON item_facet_entries (item_archetype_id,item_archetype_revision_id,item_id,item_version);
CREATE INDEX item_facet_references_subject_idx ON item_facet_references (subject_id,item_id,item_version) WHERE subject_id IS NOT NULL;
CREATE INDEX item_facet_references_location_idx ON item_facet_references (location_id,item_id,item_version) WHERE location_id IS NOT NULL;
CREATE INDEX item_facet_current_text_idx ON item_facet_current_values (item_id,facet_schema_revision_id,field_key,value_type,value_text,facet_key) WHERE value_text IS NOT NULL;
CREATE INDEX item_facet_current_integer_idx ON item_facet_current_values (item_id,facet_schema_revision_id,field_key,value_type,value_integer,facet_key) WHERE value_integer IS NOT NULL;
CREATE INDEX facet_schemas_created_command_receipt_id_idx ON facet_schemas (created_command_receipt_id);
CREATE INDEX facet_schemas_retired_command_receipt_id_idx ON facet_schemas (retired_command_receipt_id);
CREATE INDEX facet_schema_revisions_created_command_receipt_id_idx ON facet_schema_revisions (created_command_receipt_id);
CREATE INDEX archetype_facet_bindings_created_command_receipt_id_idx ON archetype_facet_bindings (created_command_receipt_id);
CREATE INDEX archetype_facet_bindings_ended_command_receipt_id_idx ON archetype_facet_bindings (ended_command_receipt_id);
CREATE INDEX item_facet_entries_source_command_receipt_id_idx ON item_facet_entries (source_command_receipt_id);

CREATE TRIGGER facet_schema_revisions_immutable_update BEFORE UPDATE ON facet_schema_revisions
BEGIN SELECT RAISE(ABORT,'immutable facet history'); END;

CREATE TRIGGER facet_schema_revisions_immutable_delete BEFORE DELETE ON facet_schema_revisions
BEGIN SELECT RAISE(ABORT,'immutable facet history'); END;

CREATE TRIGGER facet_schema_fields_immutable_update BEFORE UPDATE ON facet_schema_fields
BEGIN SELECT RAISE(ABORT,'immutable facet history'); END;

CREATE TRIGGER facet_schema_fields_immutable_delete BEFORE DELETE ON facet_schema_fields
BEGIN SELECT RAISE(ABORT,'immutable facet history'); END;

CREATE TRIGGER item_facet_snapshots_immutable_update BEFORE UPDATE ON item_facet_snapshots
BEGIN SELECT RAISE(ABORT,'immutable facet history'); END;

CREATE TRIGGER item_facet_snapshots_immutable_delete BEFORE DELETE ON item_facet_snapshots
BEGIN SELECT RAISE(ABORT,'immutable facet history'); END;

CREATE TRIGGER item_facet_entries_immutable_update BEFORE UPDATE ON item_facet_entries
BEGIN SELECT RAISE(ABORT,'immutable facet history'); END;

CREATE TRIGGER item_facet_entries_immutable_delete BEFORE DELETE ON item_facet_entries
BEGIN SELECT RAISE(ABORT,'immutable facet history'); END;

CREATE TRIGGER item_facet_references_immutable_update BEFORE UPDATE ON item_facet_references
BEGIN SELECT RAISE(ABORT,'immutable facet history'); END;

CREATE TRIGGER item_facet_references_immutable_delete BEFORE DELETE ON item_facet_references
BEGIN SELECT RAISE(ABORT,'immutable facet history'); END;

CREATE TRIGGER facet_schemas_identity_update BEFORE UPDATE ON facet_schemas
WHEN NEW.facet_schema_id IS NOT OLD.facet_schema_id OR NEW.owner_kind IS NOT OLD.owner_kind OR NEW.owner_subject_id IS NOT OLD.owner_subject_id OR NEW.owner_group_id IS NOT OLD.owner_group_id OR NEW.schema_key IS NOT OLD.schema_key OR NEW.created_command_receipt_id IS NOT OLD.created_command_receipt_id
BEGIN SELECT RAISE(ABORT,'immutable facet identity'); END;
CREATE TRIGGER facet_schemas_terminal_update BEFORE UPDATE ON facet_schemas
WHEN OLD.status='retired'
BEGIN SELECT RAISE(ABORT,'terminal facet lifecycle'); END;
CREATE TRIGGER facet_schemas_no_delete BEFORE DELETE ON facet_schemas
BEGIN SELECT RAISE(ABORT,'facet history cannot be deleted'); END;

CREATE TRIGGER archetype_facet_bindings_identity_update BEFORE UPDATE ON archetype_facet_bindings
WHEN NEW.facet_binding_id IS NOT OLD.facet_binding_id OR NEW.item_archetype_id IS NOT OLD.item_archetype_id OR NEW.facet_key IS NOT OLD.facet_key OR NEW.facet_schema_revision_id IS NOT OLD.facet_schema_revision_id OR NEW.created_command_receipt_id IS NOT OLD.created_command_receipt_id
BEGIN SELECT RAISE(ABORT,'immutable facet identity'); END;
CREATE TRIGGER archetype_facet_bindings_terminal_update BEFORE UPDATE ON archetype_facet_bindings
WHEN OLD.status!='active' OR NEW.status NOT IN ('superseded','retired')
BEGIN SELECT RAISE(ABORT,'terminal facet lifecycle'); END;
CREATE TRIGGER archetype_facet_bindings_no_delete BEFORE DELETE ON archetype_facet_bindings
BEGIN SELECT RAISE(ABORT,'facet history cannot be deleted'); END;

CREATE TRIGGER facet_schema_revisions_contiguous_insert BEFORE INSERT ON facet_schema_revisions
WHEN NEW.revision_number != COALESCE((SELECT MAX(revision_number)+1 FROM facet_schema_revisions WHERE facet_schema_id=NEW.facet_schema_id),1)
BEGIN SELECT RAISE(ABORT,'noncontiguous facet revision'); END;

CREATE TABLE coordination_catalog_audit_log_new (
  catalog_audit_id TEXT PRIMARY KEY,
  resource_kind TEXT NOT NULL CHECK (resource_kind IN ('item_archetype','notification_profile','notification_profile_binding','facet_schema','archetype_facet_binding')),
  resource_id TEXT NOT NULL,
  action TEXT NOT NULL,
  reason_code TEXT NOT NULL,
  actor_subject_id TEXT NOT NULL,
  command_id TEXT NOT NULL,
  payload_json TEXT NOT NULL CHECK (length(payload_json)>0),
  payload_hash TEXT NOT NULL CHECK (length(payload_hash)=64 AND payload_hash NOT GLOB '*[^0-9a-f]*'),
  created_at_utc TEXT NOT NULL,
  FOREIGN KEY (actor_subject_id) REFERENCES subjects(subject_id) DEFERRABLE INITIALLY DEFERRED
);
INSERT INTO coordination_catalog_audit_log_new SELECT * FROM coordination_catalog_audit_log;
DROP TABLE coordination_catalog_audit_log;
ALTER TABLE coordination_catalog_audit_log_new RENAME TO coordination_catalog_audit_log;
CREATE INDEX coordination_catalog_audit_resource_idx ON coordination_catalog_audit_log (resource_kind,resource_id,created_at_utc,catalog_audit_id);

INSERT INTO item_facet_snapshots (item_id,item_version,entry_count,values_bytes)
SELECT item_id,version,0,2 FROM coordination_item_versions;
