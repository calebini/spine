CREATE INDEX IF NOT EXISTS item_locations_location_idx
ON item_locations (location_id, item_id, version);

CREATE INDEX IF NOT EXISTS item_subject_roles_subject_idx
ON item_subject_roles (subject_id, status, item_id, version);

CREATE INDEX IF NOT EXISTS notification_policies_item_version_status_idx
ON notification_policies (item_id, version, status, policy_id);

CREATE INDEX IF NOT EXISTS notification_policies_recipient_status_idx
ON notification_policies (recipient_subject_id, status, item_id, version);

CREATE INDEX IF NOT EXISTS coordination_item_relations_active_source_idx
ON coordination_item_relations (source_item_id, relation_type, relation_id)
WHERE relation_status = 'active';

CREATE INDEX IF NOT EXISTS coordination_item_relations_active_target_idx
ON coordination_item_relations (target_item_id, relation_type, relation_id)
WHERE relation_status = 'active';

CREATE INDEX IF NOT EXISTS work_instances_eligible_due_idx
ON work_instances (eligible_at_utc, work_instance_id, next_attempt_at_utc)
WHERE status = 'eligible';

CREATE INDEX IF NOT EXISTS work_instances_item_version_status_idx
ON work_instances (item_id, item_version, status, work_instance_id);

CREATE INDEX IF NOT EXISTS work_instances_source_work_idx
ON work_instances (source_work_instance_id, work_instance_id)
WHERE source_work_instance_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS candidate_actions_item_status_idx
ON candidate_actions (item_id, item_version, status, candidate_action_id);

CREATE INDEX IF NOT EXISTS candidate_actions_open_kind_idx
ON candidate_actions (action_kind, urgency, created_at_utc, candidate_action_id)
WHERE status = 'open';

CREATE INDEX IF NOT EXISTS external_projections_item_adapter_status_idx
ON external_projections (item_id, adapter_name, projection_status, projection_id);

CREATE INDEX IF NOT EXISTS external_projections_status_updated_idx
ON external_projections (projection_status, updated_at_utc, projection_id);

CREATE INDEX IF NOT EXISTS side_effect_attempts_work_instance_idx
ON side_effect_attempts (work_instance_id, attempted_at_utc, attempt_id)
WHERE work_instance_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS side_effect_attempts_candidate_action_idx
ON side_effect_attempts (candidate_action_id, attempted_at_utc, attempt_id)
WHERE candidate_action_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS side_effect_attempts_projection_idx
ON side_effect_attempts (projection_id, attempted_at_utc, attempt_id)
WHERE projection_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS side_effect_attempts_item_adapter_status_idx
ON side_effect_attempts (item_id, adapter_name, attempt_status, attempted_at_utc, attempt_id);

CREATE INDEX IF NOT EXISTS audit_log_item_created_idx
ON audit_log (item_id, created_at_utc, audit_id);

CREATE INDEX IF NOT EXISTS audit_log_causation_idx
ON audit_log (causation_id, created_at_utc, audit_id)
WHERE causation_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS audit_log_correlation_idx
ON audit_log (correlation_id, created_at_utc, audit_id)
WHERE correlation_id IS NOT NULL;
