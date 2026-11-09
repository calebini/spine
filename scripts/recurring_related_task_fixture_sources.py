"""Finite synthetic source inputs for RRT offline proof witnesses, never a ledger.

Existing pure recurrence normalizers supply canonical snapshots/IDs. Explicit
copy/count/retarget facts below are test inputs required by the recurrence
contract, not claims that a command/worker persisted them. Tests independently
check membership and correspondence; no runtime RRT behavior is implemented here.
"""

from spine.core.canonical_json import canonical_json_bytes
from spine.core.hashing import hash_canonical_json
from spine.core.recurrence_mutations import build_successor_recurrence_revision, derive_recurrence_lineage
from spine.core.recurrence_set import generated_id, normalize_initial_recurrence_set

VERSIONS = {
    "contract_version": "spine.recurrence.contract.v1",
    "normalization_version": "spine.recurrence.normalization.v1",
    "canonical_json_version": "spine.canonical-json.v1",
}
SEED = "2026-11-14T11:30:00"


def successor_segments(before, supplied=None):
    """Explicit inputs for the fixture's newly copied/produced segment facts.

    All segments constructed here are new facts in this successor, including
    retired split facts. Do not use this as a general historical-row rewriter.
    """
    if supplied is not None:
        return [{**row, "source_revision_id": before["recurrence_revision_id"]} for row in supplied]
    return [
        {**row, "source_revision_id": before["recurrence_revision_id"], "lineage_parent_segment_id": row["segment_id"]}
        for row in before["segments"]
    ]


def selector_for(value, fact, *, rules=True, rdates=False):
    """Construct the declared candidate selector; independent tests prove it."""
    rule_rows = [r for r in value["rules"] if r["status"] == "active"] if rules else []
    rdate_rows = [r for r in value["rdates"] if r["status"] == "active" and r["scheduled_fact"] == fact] if rdates else []
    segments = {
        s["segment_id"]: s
        for s in value["segments"]
        if s["status"] == "active" and s["active_start"] <= fact and (s.get("active_end") is None or fact < s["active_end"])
    }
    rule_rows = [r for r in rule_rows if r["segment_id"] in segments]
    rdate_rows = [r for r in rdate_rows if r["segment_id"] in segments]
    segment_ids = {r["segment_id"] for r in rule_rows + rdate_rows}
    if len(segment_ids) != 1:
        raise ValueError("Fixture candidate must have one active segment")

    def semantic(row, field):
        return {k: v for k, v in row.items() if k not in {field, "segment_id"}}

    rs = sorted([semantic(r, "rule_id") for r in rule_rows], key=canonical_json_bytes)
    ds = sorted([semantic(r, "rdate_id") for r in rdate_rows], key=canonical_json_bytes)
    return {
        **VERSIONS,
        "derivation_version": "spine.recurrence-target-occurrence-selector.v1",
        "recurrence_set_id": value["recurrence_set_id"],
        "segment_ref": segments[next(iter(segment_ids))]["segment_index"],
        "scheduled_fact": fact,
        "origin_kind": "union" if len(rs) + len(ds) > 1 else "rule" if rs else "rdate",
        "source_rule_selectors": rs,
        "source_rdate_selectors": ds,
    }


def source_witnesses():
    snapshots, pairs, normalized = [], [], {}

    def retain(name, norm, root_preimage=None):
        normalized[name] = norm
        snapshots.append(
            {
                "case_id": name,
                "value": norm.value,
                "recurrence_set_id_preimage": root_preimage or norm.recurrence_set_id_preimage,
                "normalized_hash_preimage": norm.normalized_hash_preimage,
                "recurrence_revision_id_preimage": norm.recurrence_revision_id_preimage,
                "segment_id_preimages": list(norm.segment_id_preimages),
                "rule_id_preimages": list(norm.rule_id_preimages),
                "rdate_id_preimages": list(norm.rdate_id_preimages),
            }
        )
        return norm.value

    def initial(name, *, count=None, union=False):
        rule = {
            "frequency": "WEEKLY",
            "interval": "1",
            "seed": SEED,
            "start_bound": SEED,
            "end_condition": {"kind": "unbounded"} if count is None else {"kind": "count", "count": str(count)},
            "by_weekday": ["SA"],
            "week_start": "MO",
        }
        rules = [rule, {**rule, "interval": "2"}] if union else [rule]
        norm = normalize_initial_recurrence_set(
            {"time_basis": "local_instant", "timezone": "Etc/UTC", "timezone_database_version": "2026c", "rules": rules},
            source_item_id="item_fixture_science_class" if name == "main" else "item_fixture_" + name,
            seed_anchor_id="anchor_fixture_" + name,
            seed_scheduled_fact=SEED,
            created_item_version="1",
            source_item_version="1",
            command_id="fixture_source_" + name,
            require_available_timezone_data=False,
        )
        return retain(name, norm)

    def successor(name, prior_name="main", *, effect="series_edit_whole_applied", copies=None, **changes):
        before = normalized[prior_name].value
        command = "fixture_source_" + name
        changes["segments"] = successor_segments(before, changes.get("segments"))
        norm = build_successor_recurrence_revision(before, source_item_version="2", command_id=command, **changes)
        root = next(s["recurrence_set_id_preimage"] for s in snapshots if s["case_id"] == prior_name)
        after = retain(name, norm, root)
        rows = derive_recurrence_lineage(before, after, command_id=command, effect=effect)
        # COUNT splits change rule semantics. Explicit copy/count evidence is
        # supplied as an offline expected input, not inferred from equal times.
        for row in rows:
            if copies and row.get("new_child_id") in copies:
                row.update(prior_child_id=copies[row["new_child_id"]], effect="copied")
        facts = []
        for row in rows:
            identity = {k: v for k, v in row.items() if k not in {"lineage_id", "payload_hash"}}
            lid, preimage = generated_id("recurrence_lineage", "spine.recurrence-lineage-id.v1", identity)
            payload = {**identity, "command_effect": effect}
            facts.append(
                {
                    "row": {**identity, "lineage_id": lid, "payload_hash": hash_canonical_json(payload)},
                    "identity_preimage": preimage,
                    "payload": payload,
                }
            )
        pair = {"case_id": name, "prior_snapshot": prior_name, "snapshot": name, "lineage": facts, "copy_facts": [], "retarget_facts": []}
        for fact in facts:
            row = fact["row"]
            if row.get("effect") == "copied" and row.get("prior_child_id"):
                pair["copy_facts"].append(
                    {"prior_child_id": row["prior_child_id"], "new_child_id": row["new_child_id"], "lineage_id": row["lineage_id"]}
                )
        pairs.append(pair)
        return after, pair

    main = initial("main")
    selected = selector_for(main, SEED)
    copied, _ = successor("copied")
    added, _ = successor(
        "added",
        rdates=[{"segment_ref": "0", "scheduled_fact": "2026-11-15T11:30:00", "status": "active"}],
        effect="instance_add_rdate_created",
    )
    # Keys are independently checked by the contract tests after construction.
    import base64

    pre = {**VERSIONS, "derivation_version": "spine.recurrence-occurrence-key.v2", "target_occurrence_selector": selected}
    encoded = canonical_json_bytes(pre)
    key = base64.urlsafe_b64encode(encoded).rstrip(b"=").decode() + "." + hash_canonical_json(pre)
    successor(
        "excluded",
        exdates=[
            {
                "segment_ref": "0",
                "target_occurrence_selector": selected,
                "target_occurrence_key": key,
                "scheduled_fact": SEED,
                "reason_code": "class_cancelled",
                "status": "active",
            }
        ],
        effect="instance_remove_exdate_created",
    )
    override_path = {
        "path_version": "spine.recurrence-override-path.v1",
        "has_move": False,
        "detail_patch_fields": [],
        "has_lifecycle": True,
    }
    revision_key, _ = generated_id(
        "revkey",
        "spine.recurrence-override-revision-key.v2",
        {
            "command_id": "fixture_source_occurrence_cancelled",
            "recurrence_set_id": main["recurrence_set_id"],
            "prior_recurrence_revision_id": main["recurrence_revision_id"],
            "target_occurrence_selector": selected,
            "segment_ref": "0",
            "override_path": override_path,
        },
    )
    successor(
        "occurrence_cancelled",
        overrides=[
            {
                "segment_ref": "0",
                "target_occurrence_selector": selected,
                "target_occurrence_key": key,
                "override_kind": "lifecycle",
                "revision_key": revision_key,
                "lifecycle": "cancelled",
                "status": "active",
            }
        ],
        effect="instance_override_created",
    )
    successor("source_cancelled")
    counted = initial("counted", count=6)
    prior_segment = counted["segments"][0]
    split = "2026-11-28T11:30:00"
    segments = [
        {"segment_ref": "prefix", "active_start": SEED, "active_end": split, "status": "active"},
        {"segment_ref": "historical", "active_start": SEED, "status": "retired"},
        {"segment_ref": "following", "active_start": split, "status": "active"},
    ]
    for segment in segments:
        segment.update(lineage_parent_segment_id=prior_segment["segment_id"], reason_code="this_and_following_" + segment["segment_ref"])
    old_rule = counted["rules"][0]
    semantics = {k: v for k, v in old_rule.items() if k not in {"rule_id", "segment_id"}}
    rules = [
        {**semantics, "segment_ref": "prefix"},
        {**semantics, "segment_ref": "following", "start_bound": split, "end_condition": {"kind": "count", "count": "4"}},
    ]
    # Build once to obtain deterministic child IDs, then retain the complete
    # explicit copy relation with its exact COUNT subtraction facts.
    preview = build_successor_recurrence_revision(
        counted, source_item_version="2", command_id="fixture_source_split", segments=successor_segments(counted, segments), rules=rules
    )
    copies = {r["rule_id"]: old_rule["rule_id"] for r in preview.value["rules"]}
    following, split_pair = successor(
        "split", "counted", effect="series_edit_following_applied", copies=copies, segments=segments, rules=rules
    )
    for entry in split_pair["copy_facts"]:
        new_rule = next(r for r in following["rules"] if r["rule_id"] == entry["new_child_id"])
        if new_rule["start_bound"] == split:
            entry["count_subtraction"] = {
                "split_scheduled_fact": split,
                "original_count": "6",
                "produced_before_split": "2",
                "remaining_count": "4",
            }
    old_selector = selector_for(counted, split)
    new_selector = selector_for(following, split)
    split_pair["retarget_facts"] = [
        {
            "prior_selector": old_selector,
            "selector": new_selector,
            "lineage_ids": sorted(f["row"]["lineage_id"] for f in split_pair["lineage"]),
        }
    ]
    initial("union", count=6, union=True)
    successor("union_copied", "union")
    # Valid normalized successors plus deliberately insufficient copy claims:
    # a content-addressed lineage row is not itself semantic proof.
    changed = {k: v for k, v in main["rules"][0].items() if k not in {"rule_id", "segment_id"}}
    changed.update(segment_ref="0", seed="2026-11-07T11:30:00")
    dates = [{"segment_ref": "0", "scheduled_fact": "2026-11-15T11:30:00", "status": "active"}]
    preview = build_successor_recurrence_revision(
        main,
        source_item_version="2",
        command_id="fixture_source_changed_with_added",
        segments=successor_segments(main),
        rules=[changed],
        rdates=dates,
    )
    successor(
        "changed_with_added", rules=[changed], rdates=dates, copies={preview.value["rules"][0]["rule_id"]: main["rules"][0]["rule_id"]}
    )
    union = normalized["union"].value
    changed_rules = [
        {
            **{k: v for k, v in r.items() if k not in {"rule_id", "segment_id"}},
            "segment_ref": "0",
            "interval": "3" if r["interval"] == "2" else "1",
        }
        for r in union["rules"]
    ]
    preview = build_successor_recurrence_revision(
        union, source_item_version="2", command_id="fixture_source_union_changed", segments=successor_segments(union), rules=changed_rules
    )
    copy_claims = {
        r["rule_id"]: next(old["rule_id"] for old in union["rules"] if old["interval"] == ("2" if r["interval"] == "3" else "1"))
        for r in preview.value["rules"]
    }
    successor("union_changed", "union", rules=changed_rules, copies=copy_claims)
    cases = [
        {"case_id": "unchanged_copy", "pair": "copied", "fact": SEED, "mode": "copy", "expected": "same_assignment"},
        {"case_id": "count_split", "pair": "split", "fact": split, "mode": "copy", "expected": "same_assignment"},
        {"case_id": "exact_retarget", "pair": "split", "fact": split, "mode": "retarget", "expected": "same_assignment"},
        {"case_id": "all_union_contributors", "pair": "union_copied", "fact": SEED, "mode": "copy", "expected": "same_assignment"},
        {"case_id": "genuinely_added_rdate", "pair": "added", "fact": "2026-11-15T11:30:00", "mode": "novel", "expected": "new_slot"},
        {"case_id": "rule_slot_not_novel", "pair": "added", "fact": SEED, "mode": "novel", "expected": "not_novel"},
        {
            "case_id": "changed_seed_not_continuity",
            "pair": "changed_with_added",
            "fact": SEED,
            "mode": "copy",
            "expected": "decision_required",
        },
        {
            "case_id": "addition_does_not_bless_changed_component",
            "pair": "changed_with_added",
            "fact": "2026-11-15T11:30:00",
            "mode": "novel",
            "expected": "decision_required",
        },
        {
            "case_id": "one_changed_union_contributor",
            "pair": "union_changed",
            "fact": SEED,
            "mode": "copy",
            "expected": "decision_required",
        },
    ]
    return {
        "contract_version": "spine.recurring-related-task-source-witnesses.v1",
        "status": "offline_model_only",
        "runtime_verified": False,
        "scope": "finite_WEEKLY_fixture_proofs_not_runtime_resolver",
        "snapshots": snapshots,
        "pairs": pairs,
        "cases": cases,
        "event_details": [{"snapshot": "source_cancelled", "item_id": main["source_item_id"], "item_version": "2", "status": "cancelled"}],
    }
