-- Authorized endpoint/evidence probes must not scan hidden siblings.
CREATE INDEX independent_read_relation_endpoints_idx
ON coordination_item_relations (source_item_id, target_item_id, relation_id);
CREATE INDEX independent_read_binding_endpoints_idx
ON relative_temporal_bindings (source_item_id, target_item_id, temporal_binding_id);
CREATE INDEX independent_read_work_policy_idx
ON work_instances (notification_policy_id, item_id, delivery_target_id, work_instance_id);
CREATE INDEX independent_read_creation_receipt_idx
ON command_receipts (item_id, command, actor_subject_id, created_at_utc, command_receipt_id);
