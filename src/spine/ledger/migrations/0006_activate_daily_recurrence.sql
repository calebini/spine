CREATE TRIGGER IF NOT EXISTS event_details_recurrence_contract_insert
BEFORE INSERT ON event_details
FOR EACH ROW
WHEN (
  (
    (SELECT recurrence_rule FROM temporal_anchors WHERE anchor_id = NEW.start_anchor_id)
      IS NOT NULL
    AND (SELECT anchor_kind FROM temporal_anchors WHERE anchor_id = NEW.start_anchor_id)
      NOT IN ('local_date', 'local_instant')
  )
  OR (
    NEW.end_anchor_id IS NOT NULL
    AND (SELECT recurrence_rule FROM temporal_anchors WHERE anchor_id = NEW.end_anchor_id)
      IS NOT NULL
  )
)
BEGIN
  SELECT RAISE(ABORT, 'event recurrence is valid only on a local start anchor');
END;

CREATE TRIGGER IF NOT EXISTS task_details_recurrence_contract_insert
BEFORE INSERT ON task_details
FOR EACH ROW
WHEN (
  (
    NEW.due_anchor_id IS NOT NULL
    AND (SELECT recurrence_rule FROM temporal_anchors WHERE anchor_id = NEW.due_anchor_id)
      IS NOT NULL
    AND (SELECT anchor_kind FROM temporal_anchors WHERE anchor_id = NEW.due_anchor_id)
      NOT IN ('local_date', 'local_instant')
  )
  OR (
    NEW.defer_until_anchor_id IS NOT NULL
    AND (SELECT recurrence_rule FROM temporal_anchors WHERE anchor_id = NEW.defer_until_anchor_id)
      IS NOT NULL
  )
)
BEGIN
  SELECT RAISE(ABORT, 'task recurrence is valid only on a local due anchor');
END;

CREATE TRIGGER IF NOT EXISTS notification_policies_recurrence_contract_insert
BEFORE INSERT ON notification_policies
FOR EACH ROW
WHEN (
  SELECT recurrence_rule
  FROM temporal_anchors
  WHERE anchor_id = NEW.trigger_anchor_id
) IS NOT NULL
BEGIN
  SELECT RAISE(ABORT, 'notification trigger anchors cannot carry recurrence');
END;
