DROP TRIGGER IF EXISTS side_effect_attempts_staleness_insert;

CREATE TRIGGER side_effect_attempts_staleness_insert
BEFORE INSERT ON side_effect_attempts
FOR EACH ROW
WHEN (
  NEW.work_instance_id IS NOT NULL
  AND EXISTS (
    SELECT 1
    FROM work_instances AS w
    JOIN coordination_items AS i ON i.item_id = w.item_id
    WHERE w.work_instance_id = NEW.work_instance_id
      AND (
        (
          (w.work_kind != 'notification_reminder' OR w.notification_policy_id IS NULL)
          AND i.current_version != w.item_version
        )
        OR (
          w.work_kind = 'notification_reminder'
          AND w.notification_policy_id IS NOT NULL
          AND (
            i.status != 'active'
            OR NOT EXISTS (
              SELECT 1
              FROM notification_policies AS p
              WHERE p.policy_id = w.notification_policy_id
                AND p.item_id = w.item_id
                AND p.version = w.notification_policy_item_version
                AND p.status = 'active'
            )
            OR (
              i.item_type = 'event'
              AND NOT EXISTS (
                SELECT 1
                FROM event_details AS ed
                WHERE ed.item_id = i.item_id
                  AND ed.version = i.current_version
                  AND ed.event_status = 'scheduled'
              )
            )
            OR (
              i.item_type = 'task'
              AND NOT EXISTS (
                SELECT 1
                FROM task_details AS td
                WHERE td.item_id = i.item_id
                  AND td.version = i.current_version
                  AND td.task_status = 'open'
              )
            )
          )
        )
      )
  )
)
OR (
  NEW.candidate_action_id IS NOT NULL
  AND EXISTS (
    SELECT 1
    FROM candidate_actions AS c
    JOIN coordination_items AS i ON i.item_id = c.item_id
    WHERE c.candidate_action_id = NEW.candidate_action_id
      AND i.current_version != c.item_version
  )
)
OR (
  NEW.projection_id IS NOT NULL
  AND EXISTS (
    SELECT 1
    FROM coordination_items AS i
    WHERE i.item_id = NEW.item_id
      AND i.current_version != NEW.source_item_version
  )
)
BEGIN
  SELECT RAISE(ABORT, 'side_effect_attempts source item version is stale');
END;
