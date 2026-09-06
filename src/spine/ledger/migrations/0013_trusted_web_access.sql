BEGIN IMMEDIATE;

CREATE TABLE ledger_access_state (
  singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
  ledger_id TEXT NOT NULL UNIQUE,
  realm_id TEXT NOT NULL,
  mode TEXT NOT NULL CHECK (mode = 'multi_user'),
  identity_mode TEXT NOT NULL CHECK (identity_mode = 'trusted_identity'),
  access_epoch INTEGER NOT NULL CHECK (access_epoch >= 1),
  recovery_epoch INTEGER NOT NULL CHECK (recovery_epoch >= 1)
);

CREATE TABLE login_accounts (
  account_id TEXT PRIMARY KEY,
  realm_id TEXT NOT NULL,
  display_name TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('active','suspended','closed')),
  revision INTEGER NOT NULL CHECK (revision >= 1),
  activation_basis TEXT NOT NULL CHECK (activation_basis = 'trusted_local_approval'),
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  created_by_command_id TEXT NOT NULL,
  FOREIGN KEY (account_id,revision) REFERENCES login_account_revisions(account_id,revision) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE account_subject_bindings (
  binding_id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES login_accounts(account_id),
  ledger_id TEXT NOT NULL REFERENCES ledger_access_state(ledger_id),
  subject_id TEXT NOT NULL REFERENCES subjects(subject_id),
  revision INTEGER NOT NULL CHECK (revision >= 1),
  status TEXT NOT NULL CHECK (status IN ('active','revoked')),
  created_at_utc TEXT NOT NULL,
  created_by_command_id TEXT NOT NULL,
  FOREIGN KEY (binding_id,revision) REFERENCES account_subject_binding_revisions(binding_id,revision) DEFERRABLE INITIALLY DEFERRED
);
CREATE UNIQUE INDEX account_subject_bindings_active_account
ON account_subject_bindings(account_id, ledger_id) WHERE status = 'active';
CREATE UNIQUE INDEX account_subject_bindings_active_subject
ON account_subject_bindings(subject_id, ledger_id) WHERE status = 'active';
CREATE TABLE web_operators (
  account_id TEXT PRIMARY KEY REFERENCES login_accounts(account_id),
  eligible INTEGER NOT NULL CHECK (eligible IN (0,1)),
  revision INTEGER NOT NULL CHECK (revision >= 1),
  updated_by_command_id TEXT NOT NULL,
  FOREIGN KEY (account_id,revision) REFERENCES web_operator_revisions(account_id,revision) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE adopted_access_groups (
  group_id TEXT PRIMARY KEY REFERENCES subject_groups(group_id)
);

ALTER TABLE subject_memberships RENAME TO subject_memberships_pre_web;
CREATE TABLE subject_memberships (
  membership_id TEXT PRIMARY KEY,
  group_id TEXT NOT NULL REFERENCES subject_groups(group_id) DEFERRABLE INITIALLY DEFERRED,
  subject_id TEXT NOT NULL REFERENCES subjects(subject_id) DEFERRABLE INITIALLY DEFERRED,
  role TEXT NOT NULL CHECK (role IN ('member','admin','owner')),
  status TEXT NOT NULL CHECK (status IN ('active','ended')),
  starts_at_utc TEXT NOT NULL,
  ends_at_utc TEXT,
  current_revision INTEGER NOT NULL DEFAULT 1 CHECK (current_revision >= 1),
  CHECK ((status='active' AND ends_at_utc IS NULL) OR
         (status='ended' AND ends_at_utc IS NOT NULL AND ends_at_utc >= starts_at_utc))
);
INSERT INTO subject_memberships
SELECT membership_id,group_id,subject_id,role,status,starts_at_utc,ends_at_utc,1
FROM subject_memberships_pre_web;
DROP TABLE subject_memberships_pre_web;
CREATE INDEX subject_memberships_group_status_idx ON subject_memberships(group_id,status,subject_id);
CREATE INDEX subject_memberships_subject_status_idx ON subject_memberships(subject_id,status,group_id);
CREATE TABLE subject_membership_revisions (
  membership_id TEXT NOT NULL REFERENCES subject_memberships(membership_id),
  revision INTEGER NOT NULL,
  role TEXT NOT NULL,
  status TEXT NOT NULL,
  starts_at_utc TEXT NOT NULL,
  ends_at_utc TEXT,
  command_id TEXT,
  changed_at_utc TEXT,
  changed_by_subject_id TEXT REFERENCES subjects(subject_id),
  command_receipt_id TEXT REFERENCES command_receipts(command_receipt_id) DEFERRABLE INITIALLY DEFERRED,
  PRIMARY KEY (membership_id,revision)
);
INSERT INTO subject_membership_revisions
SELECT membership_id,1,role,status,starts_at_utc,ends_at_utc,NULL,NULL,NULL,NULL FROM subject_memberships;

CREATE TABLE item_access_owners (
  item_id TEXT PRIMARY KEY REFERENCES coordination_items(item_id),
  item_access_owner_id TEXT NOT NULL UNIQUE,
  current_revision INTEGER NOT NULL CHECK (current_revision >= 1),
  owner_kind TEXT NOT NULL CHECK (owner_kind IN ('subject','subject_group')),
  owner_subject_id TEXT REFERENCES subjects(subject_id),
  owner_group_id TEXT REFERENCES subject_groups(group_id),
  creator_entitlement_subject_id TEXT REFERENCES subjects(subject_id),
  created_by_command_id TEXT NOT NULL,
  CHECK ((owner_kind='subject' AND owner_subject_id IS NOT NULL AND owner_group_id IS NULL)
      OR (owner_kind='subject_group' AND owner_group_id IS NOT NULL AND owner_subject_id IS NULL)),
  FOREIGN KEY (item_access_owner_id,current_revision) REFERENCES item_access_owner_revisions(item_access_owner_id,revision) DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX item_access_owners_subject ON item_access_owners(owner_subject_id,item_id);
CREATE INDEX item_access_owners_group ON item_access_owners(owner_group_id,item_id);
CREATE TABLE access_grants (
  grant_id TEXT PRIMARY KEY,
  current_revision INTEGER NOT NULL CHECK (current_revision >= 1),
  resource_kind TEXT NOT NULL CHECK (resource_kind IN ('item','item_archetype','notification_profile')),
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
  FOREIGN KEY (grant_id,current_revision) REFERENCES access_grant_revisions(grant_id,revision) DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX access_grants_subject ON access_grants(grantee_subject_id,status,resource_kind,resource_id);
CREATE INDEX access_grants_group ON access_grants(grantee_group_id,status,resource_kind,resource_id);
CREATE INDEX access_grants_resource ON access_grants(resource_kind,resource_id,status);
CREATE TABLE access_grant_operations (
  grant_id TEXT NOT NULL REFERENCES access_grants(grant_id),
  revision INTEGER NOT NULL,
  operation TEXT NOT NULL CHECK (operation IN ('item.read','item.edit','catalog.read','catalog.use')),
  PRIMARY KEY(grant_id,revision,operation),
  FOREIGN KEY(grant_id,revision) REFERENCES access_grant_revisions(grant_id,revision) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE route_security_revisions (
  delivery_target_id TEXT PRIMARY KEY REFERENCES delivery_targets(delivery_target_id),
  revision INTEGER NOT NULL CHECK (revision >= 1)
);
CREATE TABLE route_member_use_approvals (
  delivery_target_id TEXT PRIMARY KEY REFERENCES delivery_targets(delivery_target_id),
  current_revision INTEGER NOT NULL CHECK (current_revision >= 1),
  owner_group_id TEXT NOT NULL REFERENCES subject_groups(group_id),
  approved_route_security_revision INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('approved','revoked')),
  updated_by_command_id TEXT NOT NULL,
  FOREIGN KEY (delivery_target_id,current_revision) REFERENCES route_member_use_approval_revisions(delivery_target_id,revision) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE access_audit_log (
  audit_id TEXT PRIMARY KEY,
  command_id TEXT NOT NULL UNIQUE,
  actor_subject_id TEXT NOT NULL REFERENCES subjects(subject_id),
  action_timestamp_utc TEXT NOT NULL,
  plan_hash TEXT NOT NULL CHECK (length(plan_hash)=64),
  access_epoch INTEGER NOT NULL CHECK (access_epoch >= 1)
);
CREATE TABLE web_receipt_links (
  command_receipt_id TEXT PRIMARY KEY REFERENCES command_receipts(command_receipt_id),
  command_id TEXT NOT NULL UNIQUE,
  account_id TEXT NOT NULL REFERENCES login_accounts(account_id),
  subject_id TEXT NOT NULL REFERENCES subjects(subject_id),
  binding_id TEXT NOT NULL REFERENCES account_subject_bindings(binding_id),
  binding_revision INTEGER NOT NULL,
  identity_basis TEXT NOT NULL CHECK (identity_basis='self_selected'),
  access_epoch INTEGER NOT NULL,
  api_version TEXT NOT NULL,
  registry_version TEXT NOT NULL,
  owner_kind TEXT,
  owner_subject_id TEXT REFERENCES subjects(subject_id),
  owner_group_id TEXT REFERENCES subject_groups(group_id),
  semantic_envelope_hash TEXT NOT NULL CHECK(length(semantic_envelope_hash)=64)
);

CREATE TRIGGER web_subject_status_changed AFTER UPDATE OF status ON subjects
WHEN OLD.status IS NOT NEW.status BEGIN
  UPDATE ledger_access_state SET access_epoch=access_epoch+1;
END;
CREATE TRIGGER web_group_status_changed AFTER UPDATE OF status ON subject_groups
WHEN OLD.status IS NOT NEW.status BEGIN
  UPDATE ledger_access_state SET access_epoch=access_epoch+1;
END;
CREATE TRIGGER web_route_security_changed
AFTER UPDATE OF owner_kind,owner_subject_id,owner_group_id,status,channel,adapter_name,account_id,target_ref ON delivery_targets
WHEN OLD.owner_kind IS NOT NEW.owner_kind OR OLD.owner_subject_id IS NOT NEW.owner_subject_id
 OR OLD.owner_group_id IS NOT NEW.owner_group_id OR OLD.status IS NOT NEW.status
 OR OLD.channel IS NOT NEW.channel OR OLD.adapter_name IS NOT NEW.adapter_name
 OR OLD.account_id IS NOT NEW.account_id OR OLD.target_ref IS NOT NEW.target_ref
BEGIN
  INSERT INTO route_security_revisions(delivery_target_id,revision) VALUES(NEW.delivery_target_id,2)
  ON CONFLICT(delivery_target_id) DO UPDATE SET revision=revision+1;
  UPDATE ledger_access_state SET access_epoch=access_epoch+1;
END;
CREATE TRIGGER web_membership_terminal BEFORE UPDATE ON subject_memberships
WHEN OLD.status='ended' BEGIN SELECT RAISE(ABORT,'ended membership is terminal'); END;
CREATE INDEX web_operators_eligible ON web_operators(eligible,account_id);
CREATE TABLE login_account_revisions (
  account_id TEXT NOT NULL,
  realm_id TEXT NOT NULL,
  display_name TEXT NOT NULL,
  status TEXT NOT NULL,
  revision INTEGER NOT NULL,
  activation_basis TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  created_by_command_id TEXT NOT NULL,
  changed_at_utc TEXT NOT NULL,
  changed_by_subject_id TEXT NOT NULL REFERENCES subjects(subject_id),
  command_receipt_id TEXT NOT NULL REFERENCES command_receipts(command_receipt_id) DEFERRABLE INITIALLY DEFERRED,
  PRIMARY KEY (account_id,revision),
  FOREIGN KEY (account_id) REFERENCES login_accounts(account_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TRIGGER login_account_revisions_update BEFORE UPDATE ON login_account_revisions BEGIN SELECT RAISE(ABORT,'access history is immutable'); END;
CREATE TRIGGER login_account_revisions_delete BEFORE DELETE ON login_account_revisions BEGIN SELECT RAISE(ABORT,'access history is immutable'); END;
CREATE TABLE account_subject_binding_revisions (
  binding_id TEXT NOT NULL,
  account_id TEXT NOT NULL,
  ledger_id TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  status TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  created_by_command_id TEXT NOT NULL,
  changed_at_utc TEXT NOT NULL,
  changed_by_subject_id TEXT NOT NULL REFERENCES subjects(subject_id),
  command_receipt_id TEXT NOT NULL REFERENCES command_receipts(command_receipt_id) DEFERRABLE INITIALLY DEFERRED,
  PRIMARY KEY (binding_id,revision),
  FOREIGN KEY (binding_id) REFERENCES account_subject_bindings(binding_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TRIGGER account_subject_binding_revisions_update BEFORE UPDATE ON account_subject_binding_revisions BEGIN SELECT RAISE(ABORT,'access history is immutable'); END;
CREATE TRIGGER account_subject_binding_revisions_delete BEFORE DELETE ON account_subject_binding_revisions BEGIN SELECT RAISE(ABORT,'access history is immutable'); END;
CREATE TABLE web_operator_revisions (
  account_id TEXT NOT NULL,
  eligible INTEGER NOT NULL,
  revision INTEGER NOT NULL,
  updated_by_command_id TEXT NOT NULL,
  changed_at_utc TEXT NOT NULL,
  changed_by_subject_id TEXT NOT NULL REFERENCES subjects(subject_id),
  command_receipt_id TEXT NOT NULL REFERENCES command_receipts(command_receipt_id) DEFERRABLE INITIALLY DEFERRED,
  PRIMARY KEY (account_id,revision),
  FOREIGN KEY (account_id) REFERENCES web_operators(account_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TRIGGER web_operator_revisions_update BEFORE UPDATE ON web_operator_revisions BEGIN SELECT RAISE(ABORT,'access history is immutable'); END;
CREATE TRIGGER web_operator_revisions_delete BEFORE DELETE ON web_operator_revisions BEGIN SELECT RAISE(ABORT,'access history is immutable'); END;
CREATE TABLE item_access_owner_revisions (
  item_id TEXT NOT NULL,
  item_access_owner_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  owner_kind TEXT NOT NULL,
  owner_subject_id TEXT,
  owner_group_id TEXT,
  creator_entitlement_subject_id TEXT,
  created_by_command_id TEXT NOT NULL,
  changed_at_utc TEXT NOT NULL,
  changed_by_subject_id TEXT NOT NULL REFERENCES subjects(subject_id),
  command_receipt_id TEXT NOT NULL REFERENCES command_receipts(command_receipt_id) DEFERRABLE INITIALLY DEFERRED,
  PRIMARY KEY (item_access_owner_id,revision),
  FOREIGN KEY (item_access_owner_id) REFERENCES item_access_owners(item_access_owner_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TRIGGER item_access_owner_revisions_update BEFORE UPDATE ON item_access_owner_revisions BEGIN SELECT RAISE(ABORT,'access history is immutable'); END;
CREATE TRIGGER item_access_owner_revisions_delete BEFORE DELETE ON item_access_owner_revisions BEGIN SELECT RAISE(ABORT,'access history is immutable'); END;
CREATE TABLE access_grant_revisions (
  grantor_subject_id TEXT NOT NULL REFERENCES subjects(subject_id),
  grant_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  resource_kind TEXT NOT NULL,
  resource_id TEXT NOT NULL,
  resource_owner_revision INTEGER NOT NULL,
  grantee_kind TEXT NOT NULL,
  grantee_subject_id TEXT,
  grantee_group_id TEXT,
  status TEXT NOT NULL,
  starts_at_utc TEXT NOT NULL,
  ends_at_utc TEXT,
  created_by_command_id TEXT NOT NULL,
  changed_at_utc TEXT NOT NULL,
  changed_by_subject_id TEXT NOT NULL REFERENCES subjects(subject_id),
  command_receipt_id TEXT NOT NULL REFERENCES command_receipts(command_receipt_id) DEFERRABLE INITIALLY DEFERRED,
  PRIMARY KEY (grant_id,revision),
  FOREIGN KEY (grant_id) REFERENCES access_grants(grant_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TRIGGER access_grant_revisions_update BEFORE UPDATE ON access_grant_revisions BEGIN SELECT RAISE(ABORT,'access history is immutable'); END;
CREATE TRIGGER access_grant_revisions_delete BEFORE DELETE ON access_grant_revisions BEGIN SELECT RAISE(ABORT,'access history is immutable'); END;
CREATE TABLE route_member_use_approval_revisions (
  delivery_target_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  owner_group_id TEXT NOT NULL,
  approved_route_security_revision INTEGER NOT NULL,
  status TEXT NOT NULL,
  updated_by_command_id TEXT NOT NULL,
  changed_at_utc TEXT NOT NULL,
  changed_by_subject_id TEXT NOT NULL REFERENCES subjects(subject_id),
  command_receipt_id TEXT NOT NULL REFERENCES command_receipts(command_receipt_id) DEFERRABLE INITIALLY DEFERRED,
  PRIMARY KEY (delivery_target_id,revision),
  FOREIGN KEY (delivery_target_id) REFERENCES route_member_use_approvals(delivery_target_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TRIGGER route_member_use_approval_revisions_update BEFORE UPDATE ON route_member_use_approval_revisions BEGIN SELECT RAISE(ABORT,'access history is immutable'); END;
CREATE TRIGGER route_member_use_approval_revisions_delete BEFORE DELETE ON route_member_use_approval_revisions BEGIN SELECT RAISE(ABORT,'access history is immutable'); END;
CREATE TRIGGER web_grant_item_delete BEFORE DELETE ON coordination_items WHEN EXISTS(SELECT 1 FROM access_grants WHERE resource_kind='item' AND resource_id=OLD.item_id) BEGIN SELECT RAISE(ABORT,'access grant retains resource'); END;
CREATE TRIGGER web_grant_item_archetype_delete BEFORE DELETE ON item_archetypes WHEN EXISTS(SELECT 1 FROM access_grants WHERE resource_kind='item_archetype' AND resource_id=OLD.item_archetype_id) BEGIN SELECT RAISE(ABORT,'access grant retains resource'); END;
CREATE TRIGGER web_grant_notification_profile_delete BEFORE DELETE ON notification_profiles WHEN EXISTS(SELECT 1 FROM access_grants WHERE resource_kind='notification_profile' AND resource_id=OLD.notification_profile_id) BEGIN SELECT RAISE(ABORT,'access grant retains resource'); END;
CREATE TRIGGER subject_membership_revisions_update BEFORE UPDATE ON subject_membership_revisions
BEGIN SELECT RAISE(ABORT,'access history is immutable'); END;
CREATE TRIGGER subject_membership_revisions_delete BEFORE DELETE ON subject_membership_revisions
BEGIN SELECT RAISE(ABORT,'access history is immutable'); END;
COMMIT;
