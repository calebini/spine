-- Internal R1 candidate. Normal migration/initialization remains schema 19 until R4.
CREATE TABLE related_task_rules (
 related_task_rule_id TEXT NOT NULL PRIMARY KEY,
 owner_kind TEXT NOT NULL CHECK(owner_kind IN ('subject','subject_group','system')),
 owner_subject_id TEXT REFERENCES subjects(subject_id) DEFERRABLE INITIALLY DEFERRED,
 owner_group_id TEXT REFERENCES subject_groups(group_id) DEFERRABLE INITIALLY DEFERRED,
 owner_key TEXT NOT NULL CHECK(json_valid(owner_key)),
 rule_key TEXT NOT NULL,
 source_item_id TEXT NOT NULL REFERENCES coordination_items(item_id) DEFERRABLE INITIALLY DEFERRED,
 recurrence_set_id TEXT NOT NULL REFERENCES recurrence_sets(recurrence_set_id) DEFERRABLE INITIALLY DEFERRED,
 enrolled_source_version INTEGER NOT NULL CHECK(typeof(enrolled_source_version)='integer' AND enrolled_source_version>=1),
 enrolled_recurrence_revision_id TEXT NOT NULL REFERENCES recurrence_revisions(recurrence_revision_id) DEFERRABLE INITIALLY DEFERRED,
 enrolled_at_utc TEXT NOT NULL,
 enrollment_json TEXT NOT NULL CHECK(json_valid(enrollment_json) AND json_type(enrollment_json)='object'),
 current_revision_id TEXT NOT NULL,
 change_version INTEGER NOT NULL CHECK(typeof(change_version)='integer' AND change_version>=1),
 next_assignment_seq INTEGER NOT NULL CHECK(typeof(next_assignment_seq)='integer' AND next_assignment_seq>=1),
 status TEXT NOT NULL CHECK(status IN ('active','retired')),
 retirement_intent_id TEXT REFERENCES related_task_intents(intent_id) DEFERRABLE INITIALLY DEFERRED,
 created_by_subject_id TEXT NOT NULL REFERENCES subjects(subject_id) DEFERRABLE INITIALLY DEFERRED,
 created_by_command_id TEXT NOT NULL,
 created_at_utc TEXT NOT NULL,
 UNIQUE(owner_key,rule_key),
 CHECK((owner_kind='subject' AND owner_subject_id IS NOT NULL AND owner_group_id IS NULL)
    OR (owner_kind='subject_group' AND owner_group_id IS NOT NULL AND owner_subject_id IS NULL)
    OR (owner_kind='system' AND owner_group_id IS NULL AND owner_subject_id IS NULL)),
 CHECK((status='active')=(retirement_intent_id IS NULL)),
 FOREIGN KEY(source_item_id,enrolled_source_version) REFERENCES coordination_item_versions(item_id,version) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(current_revision_id,related_task_rule_id) REFERENCES related_task_rule_revisions(related_task_rule_revision_id,related_task_rule_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE related_task_rule_revisions (
 related_task_rule_revision_id TEXT NOT NULL PRIMARY KEY,
 related_task_rule_id TEXT NOT NULL REFERENCES related_task_rules(related_task_rule_id) DEFERRABLE INITIALLY DEFERRED,
 revision_index INTEGER NOT NULL CHECK(typeof(revision_index)='integer' AND revision_index>=1),
 prior_revision_id TEXT,
 configuration_json TEXT NOT NULL CHECK(json_valid(configuration_json) AND json_type(configuration_json)='object' AND length(CAST(configuration_json AS BLOB))<=65536),
 configuration_hash TEXT NOT NULL,
 created_by_subject_id TEXT NOT NULL REFERENCES subjects(subject_id) DEFERRABLE INITIALLY DEFERRED,
 created_by_command_id TEXT NOT NULL,
 created_at_utc TEXT NOT NULL,
 UNIQUE(related_task_rule_id,revision_index),
 UNIQUE(related_task_rule_revision_id,related_task_rule_id),
 CHECK((revision_index=1)=(prior_revision_id IS NULL)),
 FOREIGN KEY(prior_revision_id,related_task_rule_id) REFERENCES related_task_rule_revisions(related_task_rule_revision_id,related_task_rule_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE related_task_assignments (
 assignment_id TEXT NOT NULL PRIMARY KEY,
 related_task_rule_id TEXT NOT NULL REFERENCES related_task_rules(related_task_rule_id) DEFERRABLE INITIALLY DEFERRED,
 assignment_seq INTEGER NOT NULL CHECK(typeof(assignment_seq)='integer' AND assignment_seq>=1),
 initial_selector_ref TEXT NOT NULL REFERENCES recurrence_target_occurrence_selectors(target_occurrence_selector_ref) DEFERRABLE INITIALLY DEFERRED,
 initial_selector_json TEXT NOT NULL CHECK(json_valid(initial_selector_json) AND json_type(initial_selector_json)='object'),
 initial_occurrence_key TEXT NOT NULL,
 created_rule_revision_id TEXT NOT NULL,
 created_at_utc TEXT NOT NULL,
 created_by_command_id TEXT NOT NULL,
 current_assignment_revision_id TEXT NOT NULL,
 change_version INTEGER NOT NULL CHECK(typeof(change_version)='integer' AND change_version>=1),
 current_generation_id TEXT NOT NULL,
 UNIQUE(related_task_rule_id,assignment_seq),
 UNIQUE(assignment_id,related_task_rule_id),
 FOREIGN KEY(created_rule_revision_id,related_task_rule_id) REFERENCES related_task_rule_revisions(related_task_rule_revision_id,related_task_rule_id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(current_assignment_revision_id,assignment_id) REFERENCES related_task_assignment_revisions(assignment_revision_id,assignment_id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(current_generation_id,assignment_id) REFERENCES related_task_generations(generation_id,assignment_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE related_task_source_proofs (
 proof_id TEXT NOT NULL PRIMARY KEY,
 related_task_rule_id TEXT NOT NULL REFERENCES related_task_rules(related_task_rule_id) DEFERRABLE INITIALLY DEFERRED,
 proof_kind TEXT NOT NULL CHECK(proof_kind IN ('enrollment','identity','carry_forward','new_rdate','component_candidate','excluded','occurrence_cancelled','source_cancelled')),
 source_item_version INTEGER NOT NULL CHECK(typeof(source_item_version)='integer' AND source_item_version>=1),
 recurrence_revision_id TEXT NOT NULL REFERENCES recurrence_revisions(recurrence_revision_id) DEFERRABLE INITIALLY DEFERRED,
 prior_recurrence_revision_id TEXT REFERENCES recurrence_revisions(recurrence_revision_id) DEFERRABLE INITIALLY DEFERRED,
 proof_json TEXT NOT NULL CHECK(json_valid(proof_json) AND json_type(proof_json)='object'),
 proof_hash TEXT NOT NULL,
 created_by_command_id TEXT NOT NULL,
 created_at_utc TEXT NOT NULL,
 UNIQUE(proof_id,related_task_rule_id)
);
CREATE TABLE related_task_proof_lineage (
 proof_id TEXT NOT NULL REFERENCES related_task_source_proofs(proof_id) DEFERRABLE INITIALLY DEFERRED,
 lineage_id TEXT NOT NULL REFERENCES recurrence_lineage(lineage_id) DEFERRABLE INITIALLY DEFERRED,
 PRIMARY KEY(proof_id,lineage_id)
);
CREATE TABLE related_task_selector_reservations (
 related_task_rule_id TEXT NOT NULL REFERENCES related_task_rules(related_task_rule_id) DEFERRABLE INITIALLY DEFERRED,
 selector_ref TEXT NOT NULL REFERENCES recurrence_target_occurrence_selectors(target_occurrence_selector_ref) DEFERRABLE INITIALLY DEFERRED,
 selector_json TEXT NOT NULL CHECK(json_valid(selector_json) AND json_type(selector_json)='object'),
 occurrence_key TEXT NOT NULL,
 assignment_id TEXT NOT NULL,
 proof_id TEXT NOT NULL,
 PRIMARY KEY(related_task_rule_id,selector_ref),
 UNIQUE(related_task_rule_id,occurrence_key),
 FOREIGN KEY(assignment_id,related_task_rule_id) REFERENCES related_task_assignments(assignment_id,related_task_rule_id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(proof_id,related_task_rule_id) REFERENCES related_task_source_proofs(proof_id,related_task_rule_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE related_task_generations (
 generation_id TEXT NOT NULL PRIMARY KEY,
 assignment_id TEXT NOT NULL REFERENCES related_task_assignments(assignment_id) DEFERRABLE INITIALLY DEFERRED,
 generation_index INTEGER NOT NULL CHECK(typeof(generation_index)='integer' AND generation_index>=1),
 predecessor_generation_id TEXT UNIQUE,
 task_item_id TEXT NOT NULL UNIQUE REFERENCES coordination_items(item_id) DEFERRABLE INITIALLY DEFERRED,
 created_task_version INTEGER NOT NULL CHECK(typeof(created_task_version)='integer' AND created_task_version>=1),
 relationship_id TEXT NOT NULL UNIQUE REFERENCES coordination_item_relations(relation_id) DEFERRABLE INITIALLY DEFERRED,
 temporal_binding_id TEXT NOT NULL UNIQUE REFERENCES relative_temporal_bindings(temporal_binding_id) DEFERRABLE INITIALLY DEFERRED,
 item_access_owner_id TEXT NOT NULL UNIQUE REFERENCES item_access_owners(item_access_owner_id) DEFERRABLE INITIALLY DEFERRED,
 created_rule_revision_id TEXT NOT NULL REFERENCES related_task_rule_revisions(related_task_rule_revision_id) DEFERRABLE INITIALLY DEFERRED,
 creation_proof_id TEXT NOT NULL REFERENCES related_task_source_proofs(proof_id) DEFERRABLE INITIALLY DEFERRED,
 created_by_command_id TEXT NOT NULL,
 created_at_utc TEXT NOT NULL,
 UNIQUE(assignment_id,generation_index),
 UNIQUE(generation_id,assignment_id),
 CHECK((generation_index=1)=(predecessor_generation_id IS NULL)),
 FOREIGN KEY(predecessor_generation_id,assignment_id) REFERENCES related_task_generations(generation_id,assignment_id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(task_item_id,created_task_version) REFERENCES coordination_item_versions(item_id,version) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE related_task_assignment_revisions (
 assignment_revision_id TEXT NOT NULL PRIMARY KEY,
 assignment_id TEXT NOT NULL REFERENCES related_task_assignments(assignment_id) DEFERRABLE INITIALLY DEFERRED,
 change_version INTEGER NOT NULL CHECK(typeof(change_version)='integer' AND change_version>=1),
 prior_assignment_revision_id TEXT,
 state_json TEXT NOT NULL CHECK(json_valid(state_json) AND json_type(state_json)='object'),
 state_hash TEXT NOT NULL,
 source_item_version INTEGER NOT NULL CHECK(typeof(source_item_version)='integer' AND source_item_version>=1),
 recurrence_revision_id TEXT NOT NULL REFERENCES recurrence_revisions(recurrence_revision_id) DEFERRABLE INITIALLY DEFERRED,
 task_item_id TEXT NOT NULL REFERENCES coordination_items(item_id) DEFERRABLE INITIALLY DEFERRED,
 task_item_version INTEGER NOT NULL CHECK(typeof(task_item_version)='integer' AND task_item_version>=1),
 adopted_rule_revision_id TEXT NOT NULL REFERENCES related_task_rule_revisions(related_task_rule_revision_id) DEFERRABLE INITIALLY DEFERRED,
 generation_id TEXT NOT NULL,
 selector_ref TEXT NOT NULL REFERENCES recurrence_target_occurrence_selectors(target_occurrence_selector_ref) DEFERRABLE INITIALLY DEFERRED,
 temporal_binding_revision_id TEXT NOT NULL REFERENCES relative_temporal_binding_revisions(temporal_binding_revision_id) DEFERRABLE INITIALLY DEFERRED,
 proof_id TEXT NOT NULL REFERENCES related_task_source_proofs(proof_id) DEFERRABLE INITIALLY DEFERRED,
 command_id TEXT NOT NULL,
 created_at_utc TEXT NOT NULL,
 UNIQUE(assignment_id,change_version),
 UNIQUE(assignment_revision_id,assignment_id),
 CHECK((change_version=1)=(prior_assignment_revision_id IS NULL)),
 FOREIGN KEY(prior_assignment_revision_id,assignment_id) REFERENCES related_task_assignment_revisions(assignment_revision_id,assignment_id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(generation_id,assignment_id) REFERENCES related_task_generations(generation_id,assignment_id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(task_item_id,task_item_version) REFERENCES coordination_item_versions(item_id,version) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE related_task_source_cancellations (
 generation_id TEXT NOT NULL PRIMARY KEY REFERENCES related_task_generations(generation_id) DEFERRABLE INITIALLY DEFERRED,
 cancelled_task_version INTEGER NOT NULL CHECK(typeof(cancelled_task_version)='integer' AND cancelled_task_version>=1),
 proof_id TEXT NOT NULL REFERENCES related_task_source_proofs(proof_id) DEFERRABLE INITIALLY DEFERRED,
 assignment_revision_id TEXT NOT NULL UNIQUE REFERENCES related_task_assignment_revisions(assignment_revision_id) DEFERRABLE INITIALLY DEFERRED,
 command_id TEXT NOT NULL,
 cancelled_at_utc TEXT NOT NULL
);
CREATE TABLE related_task_restoration_suppressions (
 suppression_id TEXT NOT NULL PRIMARY KEY,
 assignment_id TEXT NOT NULL UNIQUE,
 target_generation_id TEXT NOT NULL UNIQUE,
 actor_subject_id TEXT NOT NULL REFERENCES subjects(subject_id) DEFERRABLE INITIALLY DEFERRED,
 command_id TEXT NOT NULL,
 suppressed_at_utc TEXT NOT NULL,
 FOREIGN KEY(target_generation_id,assignment_id) REFERENCES related_task_generations(generation_id,assignment_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE related_task_intents (
 intent_id TEXT NOT NULL PRIMARY KEY,
 related_task_rule_id TEXT NOT NULL REFERENCES related_task_rules(related_task_rule_id) DEFERRABLE INITIALLY DEFERRED,
 rule_change_version INTEGER NOT NULL CHECK(typeof(rule_change_version)='integer' AND rule_change_version>=1),
 intent_kind TEXT NOT NULL CHECK(intent_kind IN ('adopt','retire')),
 intent_json TEXT NOT NULL CHECK(json_valid(intent_json) AND json_type(intent_json)='object'),
 status TEXT NOT NULL CHECK(status IN ('pending','complete','superseded')),
 created_by_command_id TEXT NOT NULL,
 created_at_utc TEXT NOT NULL,
 UNIQUE(related_task_rule_id,rule_change_version)
);
CREATE UNIQUE INDEX related_task_single_pending_adoption ON related_task_intents(related_task_rule_id) WHERE intent_kind='adopt' AND status='pending';
CREATE TABLE related_task_intent_outcomes (
 intent_id TEXT NOT NULL REFERENCES related_task_intents(intent_id) DEFERRABLE INITIALLY DEFERRED,
 assignment_id TEXT NOT NULL REFERENCES related_task_assignments(assignment_id) DEFERRABLE INITIALLY DEFERRED,
 assignment_revision_id TEXT NOT NULL REFERENCES related_task_assignment_revisions(assignment_revision_id) DEFERRABLE INITIALLY DEFERRED,
 outcome TEXT NOT NULL CHECK(outcome IN ('applied','skipped_terminal','skipped_overdue','skipped_independent','retained_equal','conflict')),
 reason TEXT NOT NULL,
 command_id TEXT NOT NULL,
 created_at_utc TEXT NOT NULL,
 PRIMARY KEY(intent_id,assignment_id)
);
CREATE TABLE related_task_rule_progress (
 related_task_rule_id TEXT NOT NULL PRIMARY KEY REFERENCES related_task_rules(related_task_rule_id) DEFERRABLE INITIALLY DEFERRED,
 progress_version INTEGER NOT NULL CHECK(typeof(progress_version)='integer' AND progress_version>=0),
 source_scan_version INTEGER NOT NULL CHECK(typeof(source_scan_version)='integer' AND source_scan_version>=1),
 recurrence_revision_id TEXT NOT NULL REFERENCES recurrence_revisions(recurrence_revision_id) DEFERRABLE INITIALLY DEFERRED,
 coverage_json TEXT NOT NULL CHECK(json_valid(coverage_json) AND json_type(coverage_json)='object'),
 assignment_after_seq INTEGER CHECK(assignment_after_seq IS NULL OR (typeof(assignment_after_seq)='integer' AND assignment_after_seq>=0)),
 pending_intent_id TEXT REFERENCES related_task_intents(intent_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE related_task_catalog_state (
 singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1),
 catalog_generation INTEGER NOT NULL CHECK(typeof(catalog_generation)='integer' AND catalog_generation>=0)
);
INSERT INTO related_task_catalog_state VALUES(1,0);
CREATE TABLE related_task_dirty_rules (
 related_task_rule_id TEXT NOT NULL PRIMARY KEY REFERENCES related_task_rules(related_task_rule_id) DEFERRABLE INITIALLY DEFERRED,
 dirty_generation INTEGER NOT NULL CHECK(typeof(dirty_generation)='integer' AND dirty_generation>=1),
 source_dirty INTEGER NOT NULL CHECK(source_dirty IN (0,1)),
 target_dirty INTEGER NOT NULL CHECK(target_dirty IN (0,1)),
 intent_dirty INTEGER NOT NULL CHECK(intent_dirty IN (0,1)),
 assignment_after_seq INTEGER NOT NULL CHECK(typeof(assignment_after_seq)='integer' AND assignment_after_seq>=0),
 CHECK(source_dirty OR target_dirty OR intent_dirty)
);
CREATE INDEX related_task_rules_owner_idx ON related_task_rules(owner_key,status,related_task_rule_id);
CREATE INDEX related_task_rules_source_idx ON related_task_rules(source_item_id,related_task_rule_id);
CREATE INDEX related_task_assignments_page_idx ON related_task_assignments(related_task_rule_id,assignment_seq);
CREATE INDEX related_task_generations_assignment_idx ON related_task_generations(assignment_id,generation_index);
CREATE INDEX related_task_assignment_revisions_history_idx ON related_task_assignment_revisions(assignment_id,change_version);
CREATE INDEX related_task_reservations_assignment_idx ON related_task_selector_reservations(assignment_id,selector_ref);
CREATE INDEX related_task_proofs_revision_idx ON related_task_source_proofs(related_task_rule_id,recurrence_revision_id,proof_id);
CREATE INDEX related_task_intents_pending_idx ON related_task_intents(related_task_rule_id,intent_kind,intent_id) WHERE status='pending';
CREATE INDEX related_task_outcomes_assignment_idx ON related_task_intent_outcomes(assignment_id,intent_id);
-- Bounded source-copy lookup; avoid scanning unrelated recurrence lineage.
CREATE INDEX related_task_source_lineage_copy_idx ON recurrence_lineage(prior_recurrence_revision_id,new_recurrence_revision_id,prior_child_id,effect,lineage_id);

CREATE TRIGGER related_task_assignment_revisions_immutable_update BEFORE UPDATE ON related_task_assignment_revisions
BEGIN SELECT RAISE(ABORT,'immutable recurring-task history'); END;
CREATE TRIGGER related_task_assignment_revisions_immutable_delete BEFORE DELETE ON related_task_assignment_revisions
BEGIN SELECT RAISE(ABORT,'immutable recurring-task history'); END;
CREATE TRIGGER related_task_generations_immutable_update BEFORE UPDATE ON related_task_generations
BEGIN SELECT RAISE(ABORT,'immutable recurring-task history'); END;
CREATE TRIGGER related_task_generations_immutable_delete BEFORE DELETE ON related_task_generations
BEGIN SELECT RAISE(ABORT,'immutable recurring-task history'); END;
CREATE TRIGGER related_task_intent_outcomes_immutable_update BEFORE UPDATE ON related_task_intent_outcomes
BEGIN SELECT RAISE(ABORT,'immutable recurring-task history'); END;
CREATE TRIGGER related_task_intent_outcomes_immutable_delete BEFORE DELETE ON related_task_intent_outcomes
BEGIN SELECT RAISE(ABORT,'immutable recurring-task history'); END;
CREATE TRIGGER related_task_proof_lineage_immutable_update BEFORE UPDATE ON related_task_proof_lineage
BEGIN SELECT RAISE(ABORT,'immutable recurring-task history'); END;
CREATE TRIGGER related_task_proof_lineage_immutable_delete BEFORE DELETE ON related_task_proof_lineage
BEGIN SELECT RAISE(ABORT,'immutable recurring-task history'); END;
CREATE TRIGGER related_task_restoration_suppressions_immutable_update BEFORE UPDATE ON related_task_restoration_suppressions
BEGIN SELECT RAISE(ABORT,'immutable recurring-task history'); END;
CREATE TRIGGER related_task_restoration_suppressions_immutable_delete BEFORE DELETE ON related_task_restoration_suppressions
BEGIN SELECT RAISE(ABORT,'immutable recurring-task history'); END;
CREATE TRIGGER related_task_rule_revisions_immutable_update BEFORE UPDATE ON related_task_rule_revisions
BEGIN SELECT RAISE(ABORT,'immutable recurring-task history'); END;
CREATE TRIGGER related_task_rule_revisions_immutable_delete BEFORE DELETE ON related_task_rule_revisions
BEGIN SELECT RAISE(ABORT,'immutable recurring-task history'); END;
CREATE TRIGGER related_task_selector_reservations_immutable_update BEFORE UPDATE ON related_task_selector_reservations
BEGIN SELECT RAISE(ABORT,'immutable recurring-task history'); END;
CREATE TRIGGER related_task_selector_reservations_immutable_delete BEFORE DELETE ON related_task_selector_reservations
BEGIN SELECT RAISE(ABORT,'immutable recurring-task history'); END;
CREATE TRIGGER related_task_source_cancellations_immutable_update BEFORE UPDATE ON related_task_source_cancellations
BEGIN SELECT RAISE(ABORT,'immutable recurring-task history'); END;
CREATE TRIGGER related_task_source_cancellations_immutable_delete BEFORE DELETE ON related_task_source_cancellations
BEGIN SELECT RAISE(ABORT,'immutable recurring-task history'); END;
CREATE TRIGGER related_task_source_proofs_immutable_update BEFORE UPDATE ON related_task_source_proofs
BEGIN SELECT RAISE(ABORT,'immutable recurring-task history'); END;
CREATE TRIGGER related_task_source_proofs_immutable_delete BEFORE DELETE ON related_task_source_proofs
BEGIN SELECT RAISE(ABORT,'immutable recurring-task history'); END;
CREATE TRIGGER related_task_rules_guard_update BEFORE UPDATE ON related_task_rules
WHEN NEW.related_task_rule_id IS NOT OLD.related_task_rule_id OR NEW.owner_kind IS NOT OLD.owner_kind OR NEW.owner_subject_id IS NOT OLD.owner_subject_id OR NEW.owner_group_id IS NOT OLD.owner_group_id OR NEW.owner_key IS NOT OLD.owner_key OR NEW.rule_key IS NOT OLD.rule_key OR NEW.source_item_id IS NOT OLD.source_item_id OR NEW.recurrence_set_id IS NOT OLD.recurrence_set_id OR NEW.enrolled_source_version IS NOT OLD.enrolled_source_version OR NEW.enrolled_recurrence_revision_id IS NOT OLD.enrolled_recurrence_revision_id OR NEW.enrolled_at_utc IS NOT OLD.enrolled_at_utc OR NEW.enrollment_json IS NOT OLD.enrollment_json OR NEW.created_by_subject_id IS NOT OLD.created_by_subject_id OR NEW.created_by_command_id IS NOT OLD.created_by_command_id OR NEW.created_at_utc IS NOT OLD.created_at_utc OR NEW.change_version!=OLD.change_version+1 OR NEW.next_assignment_seq<OLD.next_assignment_seq OR (OLD.status='retired' AND NEW.status!='retired')
BEGIN SELECT RAISE(ABORT,'invalid recurring-task state transition'); END;
CREATE TRIGGER related_task_rules_guard_delete BEFORE DELETE ON related_task_rules
BEGIN SELECT RAISE(ABORT,'immutable recurring-task header'); END;
CREATE TRIGGER related_task_assignments_guard_update BEFORE UPDATE ON related_task_assignments
WHEN NEW.assignment_id IS NOT OLD.assignment_id OR NEW.related_task_rule_id IS NOT OLD.related_task_rule_id OR NEW.assignment_seq IS NOT OLD.assignment_seq OR NEW.initial_selector_ref IS NOT OLD.initial_selector_ref OR NEW.initial_selector_json IS NOT OLD.initial_selector_json OR NEW.initial_occurrence_key IS NOT OLD.initial_occurrence_key OR NEW.created_rule_revision_id IS NOT OLD.created_rule_revision_id OR NEW.created_at_utc IS NOT OLD.created_at_utc OR NEW.created_by_command_id IS NOT OLD.created_by_command_id OR NEW.change_version!=OLD.change_version+1
BEGIN SELECT RAISE(ABORT,'invalid recurring-task state transition'); END;
CREATE TRIGGER related_task_assignments_guard_delete BEFORE DELETE ON related_task_assignments
BEGIN SELECT RAISE(ABORT,'immutable recurring-task header'); END;
CREATE TRIGGER related_task_intents_guard_update BEFORE UPDATE ON related_task_intents
WHEN NEW.intent_id IS NOT OLD.intent_id OR NEW.related_task_rule_id IS NOT OLD.related_task_rule_id OR NEW.rule_change_version IS NOT OLD.rule_change_version OR NEW.intent_kind IS NOT OLD.intent_kind OR NEW.intent_json IS NOT OLD.intent_json OR NEW.created_by_command_id IS NOT OLD.created_by_command_id OR NEW.created_at_utc IS NOT OLD.created_at_utc OR OLD.status!='pending' OR NEW.status NOT IN ('complete','superseded')
BEGIN SELECT RAISE(ABORT,'invalid recurring-task state transition'); END;
CREATE TRIGGER related_task_intents_guard_delete BEFORE DELETE ON related_task_intents
BEGIN SELECT RAISE(ABORT,'immutable recurring-task header'); END;
CREATE TRIGGER related_task_rule_progress_guard_update BEFORE UPDATE ON related_task_rule_progress
WHEN NEW.related_task_rule_id IS NOT OLD.related_task_rule_id OR NEW.progress_version!=OLD.progress_version+1
BEGIN SELECT RAISE(ABORT,'invalid recurring-task state transition'); END;
CREATE TRIGGER related_task_catalog_state_guard_update BEFORE UPDATE ON related_task_catalog_state
WHEN NEW.singleton_id IS NOT OLD.singleton_id OR NEW.catalog_generation!=OLD.catalog_generation+1
BEGIN SELECT RAISE(ABORT,'invalid recurring-task state transition'); END;
CREATE TRIGGER related_task_catalog_state_guard_delete BEFORE DELETE ON related_task_catalog_state
BEGIN SELECT RAISE(ABORT,'immutable recurring-task header'); END;
