PRAGMA foreign_keys = OFF;

CREATE TABLE IF NOT EXISTS subject_groups (
  group_id TEXT PRIMARY KEY,
  group_kind TEXT NOT NULL CHECK (group_kind IN ('household', 'team', 'project', 'transport_group')),
  display_name TEXT NOT NULL CHECK (length(display_name) > 0),
  status TEXT NOT NULL CHECK (status IN ('active', 'inactive')),
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subject_memberships (
  membership_id TEXT PRIMARY KEY,
  group_id TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('member', 'owner')),
  status TEXT NOT NULL CHECK (status IN ('active', 'ended')),
  starts_at_utc TEXT NOT NULL,
  ends_at_utc TEXT,
  CHECK (
    (status = 'active' AND ends_at_utc IS NULL)
    OR (status = 'ended' AND ends_at_utc IS NOT NULL AND ends_at_utc >= starts_at_utc)
  ),
  FOREIGN KEY (group_id)
    REFERENCES subject_groups (group_id)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (subject_id)
    REFERENCES subjects (subject_id)
    DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX IF NOT EXISTS subject_memberships_group_status_idx
ON subject_memberships (group_id, status, subject_id);

CREATE INDEX IF NOT EXISTS subject_memberships_subject_status_idx
ON subject_memberships (subject_id, status, group_id);

CREATE TABLE IF NOT EXISTS delivery_targets (
  delivery_target_id TEXT PRIMARY KEY,
  owner_kind TEXT NOT NULL CHECK (owner_kind IN ('subject', 'subject_group')),
  owner_subject_id TEXT,
  owner_group_id TEXT,
  channel TEXT NOT NULL CHECK (length(channel) > 0),
  adapter_name TEXT NOT NULL CHECK (length(adapter_name) > 0),
  account_id TEXT,
  target_ref TEXT NOT NULL CHECK (length(target_ref) > 0),
  display_name TEXT,
  status TEXT NOT NULL CHECK (status IN ('active', 'inactive')),
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  CHECK (
    (
      owner_kind = 'subject'
      AND owner_subject_id IS NOT NULL
      AND owner_group_id IS NULL
    )
    OR (
      owner_kind = 'subject_group'
      AND owner_group_id IS NOT NULL
      AND owner_subject_id IS NULL
    )
  ),
  FOREIGN KEY (owner_subject_id)
    REFERENCES subjects (subject_id)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (owner_group_id)
    REFERENCES subject_groups (group_id)
    DEFERRABLE INITIALLY DEFERRED
);

CREATE UNIQUE INDEX IF NOT EXISTS delivery_targets_active_no_account_unique
ON delivery_targets (adapter_name, channel, target_ref)
WHERE status = 'active' AND account_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS delivery_targets_active_account_unique
ON delivery_targets (adapter_name, account_id, channel, target_ref)
WHERE status = 'active' AND account_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS delivery_targets_owner_status_idx
ON delivery_targets (owner_kind, owner_subject_id, owner_group_id, status);

DROP TRIGGER IF EXISTS work_instances_notification_policy_binding_insert;
DROP TRIGGER IF EXISTS notification_policies_delivery_target_owner_insert;
DROP INDEX IF EXISTS notification_policies_item_version_status_idx;
DROP INDEX IF EXISTS notification_policies_recipient_status_idx;
DROP INDEX IF EXISTS notification_policies_subject_unique;
DROP INDEX IF EXISTS notification_policies_group_unique;
DROP INDEX IF EXISTS notification_policies_group_status_idx;
DROP INDEX IF EXISTS notification_policies_delivery_target_idx;

ALTER TABLE notification_policies RENAME TO notification_policies_v3;

CREATE TABLE notification_policies (
  policy_id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  recipient_kind TEXT NOT NULL DEFAULT 'subject' CHECK (recipient_kind IN ('subject', 'subject_group')),
  recipient_subject_id TEXT,
  recipient_group_id TEXT,
  channel_preference_ref TEXT,
  delivery_target_id TEXT,
  trigger_anchor_id TEXT NOT NULL,
  quiet_hours_policy_ref TEXT,
  status TEXT NOT NULL CHECK (status IN ('active', 'disabled')),
  created_at_utc TEXT NOT NULL,
  CHECK (
    (
      recipient_kind = 'subject'
      AND recipient_subject_id IS NOT NULL
      AND recipient_group_id IS NULL
    )
    OR (
      recipient_kind = 'subject_group'
      AND recipient_group_id IS NOT NULL
      AND recipient_subject_id IS NULL
    )
  ),
  FOREIGN KEY (item_id, version)
    REFERENCES coordination_item_versions (item_id, version)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (recipient_subject_id)
    REFERENCES subjects (subject_id)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (recipient_group_id)
    REFERENCES subject_groups (group_id)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (delivery_target_id)
    REFERENCES delivery_targets (delivery_target_id)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (trigger_anchor_id)
    REFERENCES temporal_anchors (anchor_id)
    DEFERRABLE INITIALLY DEFERRED
);

INSERT INTO notification_policies (
  policy_id, item_id, version, recipient_kind, recipient_subject_id, recipient_group_id,
  channel_preference_ref, delivery_target_id, trigger_anchor_id, quiet_hours_policy_ref,
  status, created_at_utc
)
SELECT
  policy_id, item_id, version, 'subject', recipient_subject_id, NULL,
  channel_preference_ref, NULL, trigger_anchor_id, quiet_hours_policy_ref,
  status, created_at_utc
FROM notification_policies_v3;

DROP TABLE notification_policies_v3;

CREATE UNIQUE INDEX IF NOT EXISTS notification_policies_subject_unique
ON notification_policies (item_id, version, recipient_subject_id, trigger_anchor_id)
WHERE recipient_kind = 'subject';

CREATE UNIQUE INDEX IF NOT EXISTS notification_policies_group_unique
ON notification_policies (item_id, version, recipient_group_id, trigger_anchor_id)
WHERE recipient_kind = 'subject_group';

CREATE INDEX IF NOT EXISTS notification_policies_item_version_status_idx
ON notification_policies (item_id, version, status, policy_id);

CREATE INDEX IF NOT EXISTS notification_policies_recipient_status_idx
ON notification_policies (recipient_subject_id, status, item_id, version);

CREATE INDEX IF NOT EXISTS notification_policies_group_status_idx
ON notification_policies (recipient_group_id, status, item_id, version)
WHERE recipient_kind = 'subject_group';

CREATE INDEX IF NOT EXISTS notification_policies_delivery_target_idx
ON notification_policies (delivery_target_id, status, item_id, version)
WHERE delivery_target_id IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS notification_policies_delivery_target_owner_insert
BEFORE INSERT ON notification_policies
FOR EACH ROW
WHEN NEW.delivery_target_id IS NOT NULL
AND NOT EXISTS (
  SELECT 1
  FROM delivery_targets AS dt
  WHERE dt.delivery_target_id = NEW.delivery_target_id
    AND dt.status = 'active'
    AND dt.channel = NEW.channel_preference_ref
    AND (
      (
        NEW.recipient_kind = 'subject'
        AND dt.owner_kind = 'subject'
        AND dt.owner_subject_id = NEW.recipient_subject_id
      )
      OR (
        NEW.recipient_kind = 'subject_group'
        AND dt.owner_kind = 'subject_group'
        AND dt.owner_group_id = NEW.recipient_group_id
      )
    )
)
BEGIN
  SELECT RAISE(ABORT, 'notification_policies delivery target binding is invalid');
END;

ALTER TABLE work_instances
ADD COLUMN delivery_target_id TEXT;

CREATE INDEX IF NOT EXISTS work_instances_delivery_target_idx
ON work_instances (delivery_target_id, status, work_instance_id)
WHERE delivery_target_id IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS work_instances_notification_policy_binding_insert
BEFORE INSERT ON work_instances
FOR EACH ROW
WHEN NEW.notification_policy_id IS NOT NULL
AND NOT EXISTS (
  SELECT 1
  FROM notification_policies
  WHERE policy_id = NEW.notification_policy_id
    AND item_id = NEW.item_id
    AND version = NEW.notification_policy_item_version
    AND version = NEW.item_version
    AND (
      delivery_target_id IS NULL
      OR delivery_target_id = NEW.delivery_target_id
    )
    AND (
      NEW.delivery_target_id IS NULL
      OR delivery_target_id = NEW.delivery_target_id
    )
)
BEGIN
  SELECT RAISE(ABORT, 'work_instances notification policy binding is invalid');
END;

PRAGMA foreign_keys = ON;
