"""Named executable witnesses for R4, separate from the source-only wire corpus.

Each reference is module:test_method. Resolution must find exactly one real test;
missing, ambiguous, failed or skipped evidence cannot close an obligation.
"""

import importlib
import unittest

OBLIGATIONS = {
    "RRT-01": [
        "release_migration:test_all_faults_restore_old_schema_rows_fk_and_version",
        "release_migration:test_existing_ownership_and_scheduling_history_retains_exact_values",
        "release_migration:test_normal_migration_activates_twenty_and_old_runtime_refuses_it",
        "storage:test_immutable_history_cas_and_historical_decoding_after_config_change",
        "storage:test_source_proof_fk_and_positive_counter_constraints",
    ],
    "RRT-02": [
        "package:test_missing_or_changed_each_required_asset_fails_closed",
        "package:test_missing_exact_existing_runtime_contract_denies_loading",
        "public:test_public_family_never_admits_web_context_or_missing_assets",
        "public:test_worker_missing_configuration_stops_before_processor_and_can_restart_configured",
    ],
    "RRT-03": [
        "reconcile:test_generation_faults_rollback_every_child_stage_and_preview",
        "commands:test_replay_precedes_fresh_actor_source_and_clock_checks",
        "reconcile:test_real_generation_ownership_identity_epoch_replay_and_no_duplicates",
        "attempts:test_joined_attempt_does_not_commit_caller_and_rolls_back_with_it",
    ],
    "RRT-04": [
        "storage:test_selector_reuse_checks_children_and_full_candidate_union",
        "storage:test_source_proofs_require_actual_membership_snapshot_and_budgets",
        "sources:test_selector_local_membership_all_frequencies_and_old_seed_without_history_walk",
        "invalidation:test_merge_restart_and_once_per_transaction",
        "invalidation:test_invalidation_failure_rolls_back_source_write",
        "invalidation:test_source_item_and_recurrence_coalesce_without_child_fanout",
        "invalidation:test_target_edit_invalidates_old_expected_catalog_and_preserves_replay",
        "invalidation:test_binding_retirement_invalidates_current_generation_only",
    ],
    "RRT-05": [
        "sources:test_correct_copy_and_count_split_use_stored_children_and_lineage",
        "sources:test_union_requires_every_contributor_and_duplicate_dates_collapse",
        "sources:test_missing_lineage_and_budget_exhaustion_fail_closed",
        "sources:test_equal_ordinal_or_shifted_original_fact_is_not_continuity",
        "sources:test_public_following_split_emits_valid_remaining_count_copy",
    ],
    "RRT-06": [
        "r2_preservation:test_late_enrollment_includes_started_source_only_while_due_is_future",
        "r2_preservation:test_selected_enrollment_boundary_is_inclusive_and_survives_source_copy",
        "r2_edges:test_delayed_new_rdate_after_copy_revisions_creates_one_assignment",
        "horizon:test_future_rdate_and_moved_override_prevent_premature_exhaustion",
        "sources:test_selector_local_membership_all_frequencies_and_old_seed_without_history_walk",
        "calendar_leads:test_create_reconcile_materializes_calendar_reminders_and_replays_without_duplicates",
        "calendar_leads:test_local_source_materialization_spans_dst_with_calendar_labels_preserved",
        "calendar_leads:test_calendar_repeat_window_produces_expected_work",
    ],
    "RRT-07": [
        "reconcile:test_committing_at_first_due_rolls_back_whole_page",
        "reconcile:test_restoration_and_adoption_recheck_exact_due_at_commit",
        "commands:test_backward_commit_clock_rolls_back_and_preview_requires_no_second_sample",
        "automatic:test_finalizer_cutoff_rolls_back_all_children",
    ],
    "RRT-08": [
        "reconcile:test_real_generation_ownership_identity_epoch_replay_and_no_duplicates",
        "reconcile:test_generation_bootstraps_epoch_without_inventing_access_realm",
        "r2_preservation:test_group_task_owner_does_not_change_assignee_destination_or_create_grants",
        "restoration:test_restoration_faults_roll_back_policies_owner_epoch_and_profile_application",
    ],
    "RRT-09": [
        "reconcile:test_profile_multiple_tasks_have_distinct_intents_and_real_attribution",
        "reconcile:test_adoption_replaces_complete_reminder_set_with_new_intents_once",
        "restoration:test_custom_family_and_independent_reminders_survive_repeated_generations_without_relabeling",
        "restoration:test_disabled_family_policy_is_not_silently_reintroduced",
    ],
    "RRT-10": [
        "reconcile:test_exclusion_and_restoration_make_one_linked_successor",
        "reconcile:test_two_connection_suppression_and_restoration_interleavings_fail_stale_without_retargeting",
        "r2_preservation:test_whole_event_cancellation_cancels_each_open_assignment_without_reopening",
        "r2_preservation:test_manual_cancel_and_detach_remain_consumed_across_source_return",
    ],
    "RRT-11": [
        "reconcile:test_three_way_adoption_preserves_d_equals_b_individual_exception",
        "reconcile:test_overlap_conflict_is_non_destructive_and_explicit_edit_resolves_it",
        "intent_lifecycle:test_new_assignments_above_adoption_high_water_do_not_inflate_intent_coverage",
        "intent_lifecycle:test_overdue_skip_is_final_for_that_intent_even_if_source_moves_future",
        "intent_lifecycle:test_existing_adoption_conflict_resolves_when_source_cancels",
    ],
    "RRT-12": [
        "reconcile:test_all_retirement_dispositions_cleanup_existing_outside_generation_horizon",
        "intent_lifecycle:test_cancel_retirement_cannot_complete_over_an_ownership_conflict",
        "intent_lifecycle:test_keep_following_reports_both_retirement_and_preserved_adoption_coverage",
        "attempts:test_keep_following_retirement_still_admits_current_work",
    ],
    "RRT-13": [
        "attempts:test_current_work_is_admitted_under_write_transaction",
        "attempts:test_source_change_between_optimistic_service_read_and_attempt_is_caught",
        "attempts:test_retry_attempt_rechecks_but_already_started_outcome_can_complete",
        "attempts:test_rendered_attempt_is_guarded_and_replay_cannot_send_twice",
        "automatic:test_lease_after_observation_invalidates_cancellation_plan_without_touching_protected_work",
    ],
    "RRT-14": [
        "automatic:test_create_retained_idle_and_manual_noop",
        "automatic:test_unchanged_adoption_conflict_never_receipt_churns_and_edit_releases_it",
        "scheduler:test_competing_roots_each_reach_the_tail",
        "scheduler:test_clean_short_horizon_does_not_walk_assignments_then_rolls_forward",
        "scheduler:test_generation_restart_and_readonly_continuations",
        "acknowledgement:test_complete_retained_page_discharges_queue_once_and_idle_does_not_advance",
        "acknowledgement:test_blocked_assignment_prefix_cannot_be_cleared_by_later_cursor_page",
    ],
    "RRT-15": [
        "admission_reads:test_all_cursor_purposes_reject_signed_noncanonical_or_rebound_payloads",
        "admission_reads:test_cross_ledger_cursor_and_missing_key_are_nonmutating",
        "commands:test_catalog_stale_cursor_missing_key_and_wrong_purpose_are_read_only",
        "admission_reads:test_actual_history_pages_are_complete_and_cross_root_targets_are_rejected",
        "storage:test_named_indexes_support_keyset_source_target_and_history_plans",
        "automatic:test_signed_continuation_and_expiry",
        "admission_reads:test_actor_and_rule_references_then_cursor_then_expected_facts",
    ],
    "RRT-16": [
        "r2_preservation:test_group_task_owner_does_not_change_assignee_destination_or_create_grants",
        "r2_preservation:test_revoked_disclosure_blocks_restoration_without_regrant_or_ordinary_substitution",
        "r2_preservation:test_inactive_individual_participant_blocks_restoration",
        "r2_preservation:test_inactive_route_blocks_restoration_without_creating_replacement",
        "commands:test_missing_disclosure_does_not_fabricate_an_owner_or_grant",
    ],
    "RRT-17": [
        "reconcile:test_combined_candidate_mutation_work_and_byte_limits_preserve_complete_reminder_sets",
        "reconcile:test_response_cap_counts_receipt_envelope_and_oversized_unit_rolls_back",
        "r2_edges:test_exact_shared_proof_step_budget_and_one_step_under_are_atomic",
        "r2_edges:test_lineage_limit_is_path_depth_not_sum_of_rechecks_or_other_tasks",
        "admission_reads:test_mid_page_proof_exhaustion_rolls_back_earlier_unit_writes",
        "scheduler:test_over_budget_root_does_not_starve_another_series",
    ],
    "RRT-18": [
        "storage:test_separate_connections_serialize_duplicate_reservation_and_stale_cas",
        "storage:test_sql_predecessor_uniqueness_race_with_real_foreign_keys",
        "r2_edges:test_physical_first_generation_race_has_one_reservation_set_and_replay",
        "r2_edges:test_same_command_first_generation_race_returns_one_creation_and_one_replay",
        "reconcile:test_physical_connection_restoration_race_has_one_successor_and_replay",
        "intent_lifecycle:test_physical_adoption_retirement_race_serializes_and_replays_only_winner",
        "automatic:test_competing_writer_cannot_change_plan_between_recheck_and_commit",
    ],
}


def flatten(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from flatten(test)
        else:
            yield test


def resolved_obligations():
    """Return fresh executable suites and exact IDs, refusing stale references."""
    result = {}
    for obligation, references in OBLIGATIONS.items():
        tests = []
        for reference in references:
            module, method = reference.split(":")
            imported = importlib.import_module("tests.test_recurring_task_" + module)
            matches = [t for t in flatten(unittest.defaultTestLoader.loadTestsFromModule(imported))
                       if t.id().rsplit(".", 1)[-1] == method]
            if len(matches) != 1:
                raise ValueError(f"{obligation}: expected exactly one executable witness for {reference}: {len(matches)}")
            tests.extend(matches)
        result[obligation] = tests
    return result
