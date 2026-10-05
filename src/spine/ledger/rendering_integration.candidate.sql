-- Internal candidate only. No schema version or production migration activation.
-- Kept outside numbered migrations so ordinary migration discovery is unchanged.
CREATE TRIGGER rendering_profile_revision_no_update BEFORE UPDATE ON notification_profile_revisions BEGIN SELECT RAISE(ABORT,'immutable profile revision'); END;
CREATE TRIGGER rendering_profile_revision_no_delete BEFORE DELETE ON notification_profile_revisions BEGIN SELECT RAISE(ABORT,'immutable profile revision'); END;
CREATE TRIGGER rendering_profile_template_no_update BEFORE UPDATE ON notification_profile_templates BEGIN SELECT RAISE(ABORT,'immutable profile template'); END;
CREATE TRIGGER rendering_profile_template_no_delete BEFORE DELETE ON notification_profile_templates BEGIN SELECT RAISE(ABORT,'immutable profile template'); END;
CREATE TABLE notification_rendering_definitions (
 notification_rendering_definition_id TEXT NOT NULL COLLATE BINARY PRIMARY KEY,
 definition_key TEXT NOT NULL COLLATE BINARY, status TEXT NOT NULL COLLATE BINARY CHECK(status IN ('active','retired')),
 current_revision_id TEXT NOT NULL COLLATE BINARY, created_receipt_id TEXT NOT NULL COLLATE BINARY, retired_receipt_id TEXT COLLATE BINARY, retired_reason_code TEXT COLLATE BINARY,
 owner_kind TEXT NOT NULL COLLATE BINARY CHECK(owner_kind IN ('system','subject','subject_group')), owner_subject_id TEXT COLLATE BINARY, owner_group_id TEXT COLLATE BINARY,
 CHECK ((owner_kind='system' AND owner_subject_id IS NULL AND owner_group_id IS NULL) OR (owner_kind='subject' AND owner_subject_id IS NOT NULL AND owner_group_id IS NULL) OR (owner_kind='subject_group' AND owner_subject_id IS NULL AND owner_group_id IS NOT NULL)),
 FOREIGN KEY (owner_subject_id) REFERENCES subjects (subject_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED, FOREIGN KEY (owner_group_id) REFERENCES subject_groups (group_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
 CHECK((status='active' AND retired_receipt_id IS NULL AND retired_reason_code IS NULL) OR (status='retired' AND retired_receipt_id IS NOT NULL AND retired_reason_code IS NOT NULL)),
 FOREIGN KEY (created_receipt_id) REFERENCES command_receipts (command_receipt_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED, FOREIGN KEY (retired_receipt_id) REFERENCES command_receipts (command_receipt_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY (notification_rendering_definition_id,current_revision_id) REFERENCES notification_rendering_definition_revisions (notification_rendering_definition_id,notification_rendering_definition_revision_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE notification_rendering_definition_revisions (
 notification_rendering_definition_revision_id TEXT NOT NULL COLLATE BINARY PRIMARY KEY, notification_rendering_definition_id TEXT NOT NULL COLLATE BINARY,
 revision_number INTEGER NOT NULL CHECK(typeof(revision_number)='integer' AND revision_number BETWEEN 1 AND 9223372036854775807), contract_version TEXT NOT NULL COLLATE BINARY CHECK(contract_version='spine.notification-rendering-definitions.v1'),
 canonical_json_version TEXT NOT NULL COLLATE BINARY CHECK(canonical_json_version='spine.canonical-json.v1'),
 revision_json TEXT NOT NULL COLLATE BINARY CHECK(json_valid(revision_json) AND length(CAST(revision_json AS BLOB))<=8192), definition_hash TEXT NOT NULL COLLATE BINARY CHECK(length(definition_hash)=64 AND definition_hash NOT GLOB '*[^0-9a-f]*'), created_receipt_id TEXT NOT NULL COLLATE BINARY,
 UNIQUE(notification_rendering_definition_id,revision_number), UNIQUE(notification_rendering_definition_id,notification_rendering_definition_revision_id),
 FOREIGN KEY (notification_rendering_definition_id) REFERENCES notification_rendering_definitions (notification_rendering_definition_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED, FOREIGN KEY (created_receipt_id) REFERENCES command_receipts (command_receipt_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE notification_rendering_definition_fields (
 definition_revision_id TEXT NOT NULL COLLATE BINARY, selection_index INTEGER NOT NULL CHECK(typeof(selection_index)='integer' AND selection_index BETWEEN 0 AND 7),
 selection_key TEXT NOT NULL COLLATE BINARY, facet_key TEXT NOT NULL COLLATE BINARY, facet_schema_revision_id TEXT NOT NULL COLLATE BINARY, field_key TEXT NOT NULL COLLATE BINARY, projection TEXT NOT NULL COLLATE BINARY CHECK(projection IN ('value','location_label')), label TEXT NOT NULL COLLATE BINARY,
 PRIMARY KEY(definition_revision_id,selection_index), UNIQUE(definition_revision_id,selection_key), UNIQUE(definition_revision_id,facet_key,facet_schema_revision_id,field_key),
 FOREIGN KEY (definition_revision_id) REFERENCES notification_rendering_definition_revisions (notification_rendering_definition_revision_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY (facet_schema_revision_id,field_key) REFERENCES facet_schema_fields (facet_schema_revision_id,field_key) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE notification_rendering_disclosures (
 disclosure_authorization_id TEXT NOT NULL COLLATE BINARY PRIMARY KEY, definition_root_id TEXT NOT NULL COLLATE BINARY, definition_revision_id TEXT NOT NULL COLLATE BINARY,
 scope_contract_version TEXT NOT NULL COLLATE BINARY CHECK(scope_contract_version='spine.notification-rendering-disclosures.v1'),
 canonical_json_version TEXT NOT NULL COLLATE BINARY CHECK(canonical_json_version='spine.canonical-json.v1'), scope_json TEXT NOT NULL COLLATE BINARY CHECK(json_valid(scope_json) AND length(CAST(scope_json AS BLOB))<=24576), scope_hash TEXT NOT NULL COLLATE BINARY CHECK(length(scope_hash)=64 AND scope_hash NOT GLOB '*[^0-9a-f]*'), match_hash TEXT NOT NULL COLLATE BINARY CHECK(length(match_hash)=64 AND match_hash NOT GLOB '*[^0-9a-f]*'),
 status TEXT NOT NULL COLLATE BINARY CHECK(status IN ('active','revoked')), created_receipt_id TEXT NOT NULL COLLATE BINARY, revoked_receipt_id TEXT COLLATE BINARY, revoked_reason_code TEXT COLLATE BINARY,
 delivery_target_id TEXT NOT NULL COLLATE BINARY, recipient_subject_id TEXT COLLATE BINARY, recipient_group_id TEXT COLLATE BINARY,
 owner_kind TEXT NOT NULL COLLATE BINARY CHECK(owner_kind IN ('system','subject','subject_group')), owner_subject_id TEXT COLLATE BINARY, owner_group_id TEXT COLLATE BINARY,
 CHECK ((owner_kind='system' AND owner_subject_id IS NULL AND owner_group_id IS NULL) OR (owner_kind='subject' AND owner_subject_id IS NOT NULL AND owner_group_id IS NULL) OR (owner_kind='subject_group' AND owner_subject_id IS NULL AND owner_group_id IS NOT NULL)),
 FOREIGN KEY (owner_subject_id) REFERENCES subjects (subject_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED, FOREIGN KEY (owner_group_id) REFERENCES subject_groups (group_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
 CHECK(owner_kind!='system'), CHECK((recipient_subject_id IS NULL)!=(recipient_group_id IS NULL)),
 CHECK((status='active' AND revoked_receipt_id IS NULL AND revoked_reason_code IS NULL) OR (status='revoked' AND revoked_receipt_id IS NOT NULL AND revoked_reason_code IS NOT NULL)),
 FOREIGN KEY (definition_root_id,definition_revision_id) REFERENCES notification_rendering_definition_revisions (notification_rendering_definition_id,notification_rendering_definition_revision_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY (created_receipt_id) REFERENCES command_receipts (command_receipt_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED, FOREIGN KEY (revoked_receipt_id) REFERENCES command_receipts (command_receipt_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY (delivery_target_id) REFERENCES delivery_targets (delivery_target_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED, FOREIGN KEY (recipient_subject_id) REFERENCES subjects (subject_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED, FOREIGN KEY (recipient_group_id) REFERENCES subject_groups (group_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE notification_rendering_disclosure_locations (
 disclosure_authorization_id TEXT NOT NULL COLLATE BINARY, location_id TEXT NOT NULL COLLATE BINARY, PRIMARY KEY(disclosure_authorization_id,location_id),
 FOREIGN KEY (disclosure_authorization_id) REFERENCES notification_rendering_disclosures (disclosure_authorization_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED, FOREIGN KEY (location_id) REFERENCES locations (location_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE notification_rendering_disclosure_profiles (
 disclosure_authorization_id TEXT NOT NULL COLLATE BINARY PRIMARY KEY, notification_profile_id TEXT NOT NULL COLLATE BINARY,
 FOREIGN KEY (disclosure_authorization_id) REFERENCES notification_rendering_disclosures (disclosure_authorization_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED, FOREIGN KEY (notification_profile_id) REFERENCES notification_profiles (notification_profile_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE notification_profile_rendering_revisions (
 notification_profile_revision_id TEXT NOT NULL COLLATE BINARY PRIMARY KEY, profile_contract_version TEXT NOT NULL COLLATE BINARY CHECK(profile_contract_version='spine.notification-profiles.v2'),
 FOREIGN KEY (notification_profile_revision_id) REFERENCES notification_profile_revisions (notification_profile_revision_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE notification_profile_template_renderings (
 notification_profile_template_id TEXT NOT NULL COLLATE BINARY PRIMARY KEY, kind TEXT NOT NULL COLLATE BINARY CHECK(kind IN ('ordinary','definition')),
 definition_root_id TEXT COLLATE BINARY, definition_revision_id TEXT COLLATE BINARY,
 CHECK((kind='ordinary' AND definition_root_id IS NULL AND definition_revision_id IS NULL) OR (kind='definition' AND definition_root_id IS NOT NULL AND definition_revision_id IS NOT NULL)),
 FOREIGN KEY (notification_profile_template_id) REFERENCES notification_profile_templates (notification_profile_template_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY (definition_root_id,definition_revision_id) REFERENCES notification_rendering_definition_revisions (notification_rendering_definition_id,notification_rendering_definition_revision_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE notification_policy_presentations (
 notification_policy_id TEXT NOT NULL COLLATE BINARY PRIMARY KEY, item_id TEXT NOT NULL COLLATE BINARY, item_version INTEGER NOT NULL CHECK(typeof(item_version)='integer' AND item_version BETWEEN 1 AND 9223372036854775807),
 presentation_contract_version TEXT NOT NULL COLLATE BINARY CHECK(presentation_contract_version='spine.notification-rendering-presentation.v1'),
 canonical_json_version TEXT NOT NULL COLLATE BINARY CHECK(canonical_json_version='spine.canonical-json.v1'), presentation_json TEXT NOT NULL COLLATE BINARY CHECK(json_valid(presentation_json) AND length(CAST(presentation_json AS BLOB))<=8192), presentation_hash TEXT NOT NULL COLLATE BINARY CHECK(length(presentation_hash)=64 AND presentation_hash NOT GLOB '*[^0-9a-f]*'),
 definition_root_id TEXT COLLATE BINARY, definition_revision_id TEXT COLLATE BINARY, disclosure_authorization_id TEXT COLLATE BINARY, source_policy_id TEXT COLLATE BINARY,
 CHECK((json_extract(presentation_json,'$.kind')='ordinary' AND definition_root_id IS NULL AND definition_revision_id IS NULL AND disclosure_authorization_id IS NULL) OR
 (json_extract(presentation_json,'$.kind')='definition' AND definition_root_id IS NOT NULL AND definition_revision_id IS NOT NULL AND disclosure_authorization_id IS NOT NULL)),
 FOREIGN KEY (notification_policy_id) REFERENCES notification_policies (policy_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED, FOREIGN KEY (item_id,item_version) REFERENCES coordination_item_versions (item_id,version) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY (definition_root_id,definition_revision_id) REFERENCES notification_rendering_definition_revisions (notification_rendering_definition_id,notification_rendering_definition_revision_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY (disclosure_authorization_id) REFERENCES notification_rendering_disclosures (disclosure_authorization_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED, FOREIGN KEY (source_policy_id) REFERENCES notification_policies (policy_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE notification_rendering_catalog_state (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1), generation INTEGER NOT NULL CHECK(typeof(generation)='integer' AND generation BETWEEN 1 AND 9223372036854775807)
);
INSERT INTO notification_rendering_catalog_state VALUES(1,1);
CREATE TRIGGER notification_policy_presentation_binding BEFORE INSERT ON notification_policy_presentations
WHEN NOT EXISTS(SELECT 1 FROM notification_policies p WHERE p.policy_id=NEW.notification_policy_id AND p.item_id=NEW.item_id AND p.version=NEW.item_version AND p.source_notification_policy_id IS NEW.source_policy_id)
BEGIN SELECT RAISE(ABORT,'notification presentation policy mismatch'); END;
CREATE TRIGGER notification_rendering_definition_revisions_immutable_update BEFORE UPDATE ON notification_rendering_definition_revisions BEGIN SELECT RAISE(ABORT,'immutable rendering fact'); END;
CREATE TRIGGER notification_rendering_definition_revisions_immutable_delete BEFORE DELETE ON notification_rendering_definition_revisions BEGIN SELECT RAISE(ABORT,'immutable rendering fact'); END;
CREATE TRIGGER notification_rendering_definition_fields_immutable_update BEFORE UPDATE ON notification_rendering_definition_fields BEGIN SELECT RAISE(ABORT,'immutable rendering fact'); END;
CREATE TRIGGER notification_rendering_definition_fields_immutable_delete BEFORE DELETE ON notification_rendering_definition_fields BEGIN SELECT RAISE(ABORT,'immutable rendering fact'); END;
CREATE TRIGGER notification_rendering_disclosure_locations_immutable_update BEFORE UPDATE ON notification_rendering_disclosure_locations BEGIN SELECT RAISE(ABORT,'immutable rendering fact'); END;
CREATE TRIGGER notification_rendering_disclosure_locations_immutable_delete BEFORE DELETE ON notification_rendering_disclosure_locations BEGIN SELECT RAISE(ABORT,'immutable rendering fact'); END;
CREATE TRIGGER notification_rendering_disclosure_profiles_immutable_update BEFORE UPDATE ON notification_rendering_disclosure_profiles BEGIN SELECT RAISE(ABORT,'immutable rendering fact'); END;
CREATE TRIGGER notification_rendering_disclosure_profiles_immutable_delete BEFORE DELETE ON notification_rendering_disclosure_profiles BEGIN SELECT RAISE(ABORT,'immutable rendering fact'); END;
CREATE TRIGGER notification_profile_rendering_revisions_immutable_update BEFORE UPDATE ON notification_profile_rendering_revisions BEGIN SELECT RAISE(ABORT,'immutable rendering fact'); END;
CREATE TRIGGER notification_profile_rendering_revisions_immutable_delete BEFORE DELETE ON notification_profile_rendering_revisions BEGIN SELECT RAISE(ABORT,'immutable rendering fact'); END;
CREATE TRIGGER notification_profile_template_renderings_immutable_update BEFORE UPDATE ON notification_profile_template_renderings BEGIN SELECT RAISE(ABORT,'immutable rendering fact'); END;
CREATE TRIGGER notification_profile_template_renderings_immutable_delete BEFORE DELETE ON notification_profile_template_renderings BEGIN SELECT RAISE(ABORT,'immutable rendering fact'); END;
CREATE TRIGGER notification_policy_presentations_immutable_update BEFORE UPDATE ON notification_policy_presentations BEGIN SELECT RAISE(ABORT,'immutable rendering fact'); END;
CREATE TRIGGER notification_policy_presentations_immutable_delete BEFORE DELETE ON notification_policy_presentations BEGIN SELECT RAISE(ABORT,'immutable rendering fact'); END;
CREATE TRIGGER notification_renderings_immutable_update BEFORE UPDATE ON notification_renderings BEGIN SELECT RAISE(ABORT,'immutable rendering fact'); END;
CREATE TRIGGER notification_renderings_immutable_delete BEFORE DELETE ON notification_renderings BEGIN SELECT RAISE(ABORT,'immutable rendering fact'); END;
CREATE TRIGGER notification_rendering_definitions_no_delete BEFORE DELETE ON notification_rendering_definitions BEGIN SELECT RAISE(ABORT,'immutable rendering root'); END;
CREATE TRIGGER notification_rendering_definitions_guard BEFORE UPDATE ON notification_rendering_definitions WHEN OLD.notification_rendering_definition_id IS NOT NEW.notification_rendering_definition_id OR OLD.status='retired' OR OLD.owner_kind IS NOT NEW.owner_kind OR OLD.owner_subject_id IS NOT NEW.owner_subject_id OR OLD.owner_group_id IS NOT NEW.owner_group_id OR OLD.definition_key IS NOT NEW.definition_key OR OLD.created_receipt_id IS NOT NEW.created_receipt_id BEGIN SELECT RAISE(ABORT,'immutable rendering root or terminal lifecycle'); END;
CREATE TRIGGER notification_rendering_disclosures_no_delete BEFORE DELETE ON notification_rendering_disclosures BEGIN SELECT RAISE(ABORT,'immutable rendering root'); END;
CREATE TRIGGER notification_rendering_disclosures_guard BEFORE UPDATE ON notification_rendering_disclosures WHEN OLD.disclosure_authorization_id IS NOT NEW.disclosure_authorization_id OR OLD.status='revoked' OR OLD.owner_kind IS NOT NEW.owner_kind OR OLD.owner_subject_id IS NOT NEW.owner_subject_id OR OLD.owner_group_id IS NOT NEW.owner_group_id OR OLD.definition_root_id IS NOT NEW.definition_root_id OR OLD.definition_revision_id IS NOT NEW.definition_revision_id OR OLD.scope_contract_version IS NOT NEW.scope_contract_version OR OLD.canonical_json_version IS NOT NEW.canonical_json_version OR OLD.scope_json IS NOT NEW.scope_json OR OLD.scope_hash IS NOT NEW.scope_hash OR OLD.match_hash IS NOT NEW.match_hash OR OLD.created_receipt_id IS NOT NEW.created_receipt_id OR OLD.delivery_target_id IS NOT NEW.delivery_target_id OR OLD.recipient_subject_id IS NOT NEW.recipient_subject_id OR OLD.recipient_group_id IS NOT NEW.recipient_group_id BEGIN SELECT RAISE(ABORT,'immutable rendering root or terminal lifecycle'); END;
CREATE UNIQUE INDEX rendering_definition_system_key ON notification_rendering_definitions(definition_key) WHERE owner_kind='system';
CREATE UNIQUE INDEX rendering_definition_subject_key ON notification_rendering_definitions(owner_subject_id,definition_key) WHERE owner_kind='subject';
CREATE UNIQUE INDEX rendering_definition_subject_group_key ON notification_rendering_definitions(owner_group_id,definition_key) WHERE owner_kind='subject_group';
CREATE INDEX notification_rendering_definitions_owner_kind_owner_subject_id_owner_group_id_status_notification_rendering_definition_id_idx ON notification_rendering_definitions(owner_kind,owner_subject_id,owner_group_id,status,notification_rendering_definition_id);
CREATE INDEX notification_rendering_definitions_current_revision_id_idx ON notification_rendering_definitions(current_revision_id);
CREATE INDEX notification_rendering_disclosures_owner_kind_owner_subject_id_owner_group_id_status_disclosure_authorization_id_idx ON notification_rendering_disclosures(owner_kind,owner_subject_id,owner_group_id,status,disclosure_authorization_id);
CREATE INDEX notification_rendering_disclosures_match_hash_status_disclosure_authorization_id_idx ON notification_rendering_disclosures(match_hash,status,disclosure_authorization_id);
CREATE INDEX notification_rendering_disclosures_definition_root_id_definition_revision_id_idx ON notification_rendering_disclosures(definition_root_id,definition_revision_id);
CREATE INDEX notification_rendering_disclosures_delivery_target_id_idx ON notification_rendering_disclosures(delivery_target_id);
CREATE INDEX notification_rendering_disclosures_recipient_subject_id_idx ON notification_rendering_disclosures(recipient_subject_id);
CREATE INDEX notification_rendering_disclosures_recipient_group_id_idx ON notification_rendering_disclosures(recipient_group_id);
CREATE INDEX notification_rendering_definition_fields_facet_schema_revision_id_field_key_idx ON notification_rendering_definition_fields(facet_schema_revision_id,field_key);
CREATE INDEX notification_rendering_disclosure_locations_location_id_idx ON notification_rendering_disclosure_locations(location_id);
CREATE INDEX notification_rendering_disclosure_profiles_notification_profile_id_idx ON notification_rendering_disclosure_profiles(notification_profile_id);
CREATE INDEX notification_profile_template_renderings_definition_root_id_definition_revision_id_idx ON notification_profile_template_renderings(definition_root_id,definition_revision_id);
CREATE INDEX notification_policy_presentations_item_id_item_version_notification_policy_id_idx ON notification_policy_presentations(item_id,item_version,notification_policy_id);
CREATE INDEX notification_policy_presentations_disclosure_authorization_id_idx ON notification_policy_presentations(disclosure_authorization_id);
CREATE INDEX notification_policy_presentations_source_policy_id_idx ON notification_policy_presentations(source_policy_id);
CREATE INDEX notification_policy_presentations_definition_root_id_definition_revision_id_idx ON notification_policy_presentations(definition_root_id,definition_revision_id);
CREATE INDEX notification_rendering_definitions_created_receipt_id_idx ON notification_rendering_definitions(created_receipt_id);
CREATE INDEX notification_rendering_definitions_retired_receipt_id_idx ON notification_rendering_definitions(retired_receipt_id);
CREATE INDEX notification_rendering_definition_revisions_created_receipt_id_idx ON notification_rendering_definition_revisions(created_receipt_id);
CREATE INDEX notification_rendering_disclosures_created_receipt_id_idx ON notification_rendering_disclosures(created_receipt_id);
CREATE INDEX notification_rendering_disclosures_revoked_receipt_id_idx ON notification_rendering_disclosures(revoked_receipt_id);
