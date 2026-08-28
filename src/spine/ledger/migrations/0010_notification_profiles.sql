BEGIN IMMEDIATE;

CREATE TABLE item_archetypes (
  item_archetype_id TEXT PRIMARY KEY,
  owner_kind TEXT NOT NULL CHECK (owner_kind IN ('system', 'subject', 'subject_group')),
  owner_subject_id TEXT,
  owner_group_id TEXT,
  archetype_key TEXT NOT NULL CHECK (length(archetype_key) BETWEEN 1 AND 64),
  status TEXT NOT NULL CHECK (status IN ('active', 'retired')),
  current_revision_id TEXT NOT NULL,
  created_by_subject_id TEXT NOT NULL,
  created_by_command_id TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  retired_by_subject_id TEXT,
  retired_by_command_id TEXT,
  retired_at_utc TEXT,
  retirement_reason TEXT,
  CHECK (
    (owner_kind = 'system' AND owner_subject_id IS NULL AND owner_group_id IS NULL)
    OR (owner_kind = 'subject' AND owner_subject_id IS NOT NULL AND owner_group_id IS NULL)
    OR (owner_kind = 'subject_group' AND owner_subject_id IS NULL AND owner_group_id IS NOT NULL)
  ),
  CHECK (
    (status = 'active' AND retired_by_subject_id IS NULL AND retired_by_command_id IS NULL AND retired_at_utc IS NULL)
    OR (status = 'retired' AND retired_by_subject_id IS NOT NULL AND retired_by_command_id IS NOT NULL AND retired_at_utc IS NOT NULL)
  ),
  UNIQUE (owner_kind, owner_subject_id, owner_group_id, archetype_key),
  FOREIGN KEY (owner_subject_id) REFERENCES subjects (subject_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (owner_group_id) REFERENCES subject_groups (group_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (created_by_subject_id) REFERENCES subjects (subject_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (retired_by_subject_id) REFERENCES subjects (subject_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE item_archetype_revisions (
  item_archetype_revision_id TEXT PRIMARY KEY,
  item_archetype_id TEXT NOT NULL,
  revision_number INTEGER NOT NULL CHECK (revision_number >= 1),
  display_name TEXT NOT NULL CHECK (length(display_name) BETWEEN 1 AND 160),
  description TEXT,
  compatible_item_types_json TEXT NOT NULL CHECK (length(compatible_item_types_json) > 0),
  normalized_content_hash TEXT NOT NULL CHECK (
    length(normalized_content_hash) = 64 AND normalized_content_hash NOT GLOB '*[^0-9a-f]*'
  ),
  created_by_subject_id TEXT NOT NULL,
  created_by_command_id TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  UNIQUE (item_archetype_id, revision_number),
  FOREIGN KEY (item_archetype_id) REFERENCES item_archetypes (item_archetype_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (created_by_subject_id) REFERENCES subjects (subject_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX item_archetypes_owner_status_idx
ON item_archetypes (owner_kind, owner_subject_id, owner_group_id, status, archetype_key);

CREATE TABLE item_archetype_assignments (
  item_archetype_assignment_id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  item_version INTEGER NOT NULL CHECK (item_version >= 1),
  item_archetype_id TEXT NOT NULL,
  item_archetype_revision_id TEXT NOT NULL,
  selection_source TEXT NOT NULL CHECK (selection_source IN ('operator_explicit', 'agent_selected', 'imported')),
  source_ref TEXT,
  created_by_subject_id TEXT NOT NULL,
  created_by_command_id TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  UNIQUE (item_id, item_version),
  FOREIGN KEY (item_id, item_version) REFERENCES coordination_item_versions (item_id, version) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (item_archetype_id) REFERENCES item_archetypes (item_archetype_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (item_archetype_revision_id) REFERENCES item_archetype_revisions (item_archetype_revision_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (created_by_subject_id) REFERENCES subjects (subject_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX item_archetype_assignments_archetype_idx
ON item_archetype_assignments (item_archetype_id, item_id, item_version);

CREATE TABLE notification_profiles (
  notification_profile_id TEXT PRIMARY KEY,
  owner_kind TEXT NOT NULL CHECK (owner_kind IN ('system', 'subject', 'subject_group')),
  owner_subject_id TEXT,
  owner_group_id TEXT,
  profile_key TEXT NOT NULL CHECK (length(profile_key) BETWEEN 1 AND 64),
  display_name TEXT NOT NULL CHECK (length(display_name) BETWEEN 1 AND 160),
  description TEXT,
  status TEXT NOT NULL CHECK (status IN ('active', 'retired')),
  current_revision_id TEXT NOT NULL,
  created_by_subject_id TEXT NOT NULL,
  created_by_command_id TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  retired_by_subject_id TEXT,
  retired_by_command_id TEXT,
  retired_at_utc TEXT,
  retirement_reason TEXT,
  CHECK (
    (owner_kind = 'system' AND owner_subject_id IS NULL AND owner_group_id IS NULL)
    OR (owner_kind = 'subject' AND owner_subject_id IS NOT NULL AND owner_group_id IS NULL)
    OR (owner_kind = 'subject_group' AND owner_subject_id IS NULL AND owner_group_id IS NOT NULL)
  ),
  CHECK (
    (status = 'active' AND retired_by_subject_id IS NULL AND retired_by_command_id IS NULL AND retired_at_utc IS NULL)
    OR (status = 'retired' AND retired_by_subject_id IS NOT NULL AND retired_by_command_id IS NOT NULL AND retired_at_utc IS NOT NULL)
  ),
  UNIQUE (owner_kind, owner_subject_id, owner_group_id, profile_key),
  FOREIGN KEY (owner_subject_id) REFERENCES subjects (subject_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (owner_group_id) REFERENCES subject_groups (group_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (created_by_subject_id) REFERENCES subjects (subject_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (retired_by_subject_id) REFERENCES subjects (subject_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE notification_profile_revisions (
  notification_profile_revision_id TEXT PRIMARY KEY,
  notification_profile_id TEXT NOT NULL,
  revision_number INTEGER NOT NULL CHECK (revision_number >= 1),
  compatible_item_types_json TEXT NOT NULL CHECK (length(compatible_item_types_json) > 0),
  normalized_revision_hash TEXT NOT NULL CHECK (
    length(normalized_revision_hash) = 64 AND normalized_revision_hash NOT GLOB '*[^0-9a-f]*'
  ),
  created_by_subject_id TEXT NOT NULL,
  created_by_command_id TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  UNIQUE (notification_profile_id, revision_number),
  FOREIGN KEY (notification_profile_id) REFERENCES notification_profiles (notification_profile_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (created_by_subject_id) REFERENCES subjects (subject_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE notification_profile_templates (
  notification_profile_template_id TEXT PRIMARY KEY,
  notification_profile_revision_id TEXT NOT NULL,
  template_key TEXT NOT NULL CHECK (length(template_key) BETWEEN 1 AND 64),
  template_index INTEGER NOT NULL CHECK (template_index >= 0),
  schedule_json TEXT NOT NULL CHECK (length(schedule_json) > 0),
  late_handling_json TEXT NOT NULL CHECK (length(late_handling_json) > 0),
  normalized_template_hash TEXT NOT NULL CHECK (
    length(normalized_template_hash) = 64 AND normalized_template_hash NOT GLOB '*[^0-9a-f]*'
  ),
  UNIQUE (notification_profile_revision_id, template_key),
  UNIQUE (notification_profile_revision_id, template_index),
  FOREIGN KEY (notification_profile_revision_id) REFERENCES notification_profile_revisions (notification_profile_revision_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX notification_profiles_owner_status_idx
ON notification_profiles (owner_kind, owner_subject_id, owner_group_id, status, profile_key);

CREATE INDEX notification_profile_templates_revision_idx
ON notification_profile_templates (notification_profile_revision_id, template_index);

CREATE TABLE notification_profile_bindings (
  notification_profile_binding_id TEXT PRIMARY KEY,
  owner_kind TEXT NOT NULL CHECK (owner_kind IN ('system', 'subject', 'subject_group')),
  owner_subject_id TEXT,
  owner_group_id TEXT,
  item_archetype_id TEXT NOT NULL,
  notification_profile_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('active', 'retired')),
  created_by_subject_id TEXT NOT NULL,
  created_by_command_id TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  retired_by_subject_id TEXT,
  retired_by_command_id TEXT,
  retired_at_utc TEXT,
  CHECK (
    (owner_kind = 'system' AND owner_subject_id IS NULL AND owner_group_id IS NULL)
    OR (owner_kind = 'subject' AND owner_subject_id IS NOT NULL AND owner_group_id IS NULL)
    OR (owner_kind = 'subject_group' AND owner_subject_id IS NULL AND owner_group_id IS NOT NULL)
  ),
  CHECK (
    (status = 'active' AND retired_by_subject_id IS NULL AND retired_by_command_id IS NULL AND retired_at_utc IS NULL)
    OR (status = 'retired' AND retired_by_subject_id IS NOT NULL AND retired_by_command_id IS NOT NULL AND retired_at_utc IS NOT NULL)
  ),
  FOREIGN KEY (owner_subject_id) REFERENCES subjects (subject_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (owner_group_id) REFERENCES subject_groups (group_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (item_archetype_id) REFERENCES item_archetypes (item_archetype_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (notification_profile_id) REFERENCES notification_profiles (notification_profile_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (created_by_subject_id) REFERENCES subjects (subject_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (retired_by_subject_id) REFERENCES subjects (subject_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE UNIQUE INDEX notification_profile_bindings_active_scope_unique
ON notification_profile_bindings (
  owner_kind, ifnull(owner_subject_id, ''), ifnull(owner_group_id, ''), item_archetype_id
)
WHERE status = 'active';

CREATE INDEX notification_profile_bindings_profile_status_idx
ON notification_profile_bindings (notification_profile_id, status, notification_profile_binding_id);

CREATE TABLE notification_profile_applications (
  notification_profile_application_id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  item_version INTEGER NOT NULL CHECK (item_version >= 1),
  notification_profile_id TEXT NOT NULL,
  notification_profile_revision_id TEXT NOT NULL,
  selection_mode TEXT NOT NULL CHECK (selection_mode IN ('explicit', 'archetype_default')),
  scope_chain_json TEXT NOT NULL CHECK (length(scope_chain_json) > 0),
  item_archetype_assignment_id TEXT,
  notification_profile_binding_id TEXT,
  suppress_template_keys_json TEXT NOT NULL CHECK (length(suppress_template_keys_json) > 0),
  replacements_json TEXT NOT NULL CHECK (length(replacements_json) > 0),
  additions_json TEXT NOT NULL CHECK (length(additions_json) > 0),
  normalized_effective_policy_set_hash TEXT NOT NULL CHECK (
    length(normalized_effective_policy_set_hash) = 64
    AND normalized_effective_policy_set_hash NOT GLOB '*[^0-9a-f]*'
  ),
  created_by_subject_id TEXT NOT NULL,
  created_by_command_id TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  UNIQUE (item_id, item_version),
  FOREIGN KEY (item_id, item_version) REFERENCES coordination_item_versions (item_id, version) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (notification_profile_id) REFERENCES notification_profiles (notification_profile_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (notification_profile_revision_id) REFERENCES notification_profile_revisions (notification_profile_revision_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (item_archetype_assignment_id) REFERENCES item_archetype_assignments (item_archetype_assignment_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (notification_profile_binding_id) REFERENCES notification_profile_bindings (notification_profile_binding_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (created_by_subject_id) REFERENCES subjects (subject_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE notification_profile_application_policies (
  notification_profile_application_policy_id TEXT PRIMARY KEY,
  notification_profile_application_id TEXT NOT NULL,
  policy_origin TEXT NOT NULL CHECK (policy_origin IN ('profile_template', 'profile_replacement', 'custom_addition')),
  source_key TEXT NOT NULL CHECK (length(source_key) BETWEEN 1 AND 64),
  notification_profile_template_id TEXT,
  notification_intent_id TEXT NOT NULL,
  notification_policy_id TEXT NOT NULL,
  UNIQUE (notification_profile_application_id, policy_origin, source_key),
  FOREIGN KEY (notification_profile_application_id) REFERENCES notification_profile_applications (notification_profile_application_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (notification_profile_template_id) REFERENCES notification_profile_templates (notification_profile_template_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (notification_policy_id) REFERENCES notification_policies (policy_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX notification_profile_applications_profile_idx
ON notification_profile_applications (notification_profile_id, item_id, item_version);

CREATE INDEX notification_profile_application_policies_policy_idx
ON notification_profile_application_policies (notification_policy_id, notification_profile_application_id);

CREATE TABLE coordination_catalog_audit_log (
  catalog_audit_id TEXT PRIMARY KEY,
  resource_kind TEXT NOT NULL CHECK (resource_kind IN ('item_archetype', 'notification_profile', 'notification_profile_binding')),
  resource_id TEXT NOT NULL,
  action TEXT NOT NULL,
  reason_code TEXT NOT NULL,
  actor_subject_id TEXT NOT NULL,
  command_id TEXT NOT NULL,
  payload_json TEXT NOT NULL CHECK (length(payload_json) > 0),
  payload_hash TEXT NOT NULL CHECK (
    length(payload_hash) = 64 AND payload_hash NOT GLOB '*[^0-9a-f]*'
  ),
  created_at_utc TEXT NOT NULL,
  FOREIGN KEY (actor_subject_id) REFERENCES subjects (subject_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX coordination_catalog_audit_resource_idx
ON coordination_catalog_audit_log (resource_kind, resource_id, created_at_utc, catalog_audit_id);

COMMIT;
