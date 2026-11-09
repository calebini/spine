"""Read-only, bounded source membership and one-to-one continuity for R1.

Database lineage is evidence to verify, never caller-provided mapping authority.
No item, selector or provenance repair is performed by these proof functions.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.recurrence_set import generated_id
from spine.core.recurring_tasks import invariant, occurrence_key
from spine.core.schedule import _valid_candidate_count_between, expand_rule, normalize_rule, parse_scheduled_fact


@dataclass
class ProofBudget:
    steps: int = 10000
    hops: int = 64

    def spend(self, amount: int = 1, *, hop: bool = False) -> None:
        if amount < 0 or amount > self.steps or (hop and self.hops < 1):
            raise SpineValidationError("source_continuity_unresolved", "bounded source proof exhausted")
        self.steps -= amount
        if hop:
            self.hops -= 1


def _rows(db: sqlite3.Connection, sql: str, args: tuple[object, ...], budget: ProofBudget) -> list[dict[str, Any]]:
    budget.spend()
    rows = db.execute(sql + " LIMIT ?", (*args, budget.steps + 1)).fetchall()
    budget.spend(len(rows))
    return [dict(row) for row in rows]


def revision(db: sqlite3.Connection, revision_id: str, budget: ProofBudget) -> dict[str, Any]:
    invariant(db.in_transaction, "source proof requires a pinned read/write transaction")
    rows = _rows(
        db,
        "SELECT s.*,r.* FROM recurrence_revisions r JOIN recurrence_sets s USING(recurrence_set_id) WHERE r.recurrence_revision_id=?",
        (revision_id,),
        budget,
    )
    if len(rows) != 1:
        raise SpineValidationError("source_continuity_unresolved", "missing source revision")
    return rows[0]


def _rule(db: sqlite3.Connection, row: dict[str, Any], budget: ProofBudget) -> dict[str, Any]:
    end: dict[str, str] = {"kind": row["end_kind"]}
    if row["end_count"] is not None:
        end["count"] = str(row["end_count"])
    if row["end_until"] is not None:
        end["until"] = row["end_until"]
    result: dict[str, Any] = {
        "frequency": row["frequency"],
        "interval": str(row["interval_value"]),
        "seed": row["seed"],
        "start_bound": row["start_bound"],
        "end_condition": end,
        "status": row["status"],
    }
    if row["week_start"] is not None:
        result["week_start"] = row["week_start"]
    if row["rule_duplicate_index"] is not None:
        result["rule_duplicate_index"] = str(row["rule_duplicate_index"])
    for child in _rows(
        db,
        "SELECT selector_kind,selector_value FROM recurrence_rule_selectors WHERE rule_id=? ORDER BY selector_kind,selector_index",
        (row["rule_id"],),
        budget,
    ):
        result.setdefault(child["selector_kind"], []).append(child["selector_value"])
    return result


def _calendar_cost(header: dict[str, Any], rule: dict[str, Any], fact: str) -> int:
    # Bound provider transition/count preparation as well as output candidates.
    # Gregorian selector cycles are finite; old/local histories may conservatively
    # exhaust a caller's proof budget rather than silently doing unbounded work.
    years = max(0, int(fact[:4]) - int(rule["seed"][:4]))
    return 1 + (4800 if rule["frequency"] in {"MONTHLY", "YEARLY"} else 0) + (366 * years if header["time_basis"] == "local_instant" else 0)


def candidate(db: sqlite3.Connection, revision_id: str, fact: str, budget: ProofBudget) -> dict[str, Any] | None:
    """Pre-exclusion duplicate-collapsed membership at one original fact only."""
    head = revision(db, revision_id, budget)
    if head["time_basis"] not in {"local_instant", "instant_utc"}:
        raise SpineValidationError("source_continuity_unresolved", "unsupported source time basis")
    point = parse_scheduled_fact(fact, time_basis=head["time_basis"], field="scheduled_fact")
    assert isinstance(point, datetime)
    finish = (point + timedelta(seconds=1)).isoformat(timespec="seconds")
    if head["time_basis"] == "instant_utc":
        finish = finish.replace("+00:00", "Z")
    segments = _rows(
        db,
        "SELECT * FROM recurrence_segments WHERE recurrence_revision_id=? AND status='active' "
        "AND active_start<=? AND (active_end IS NULL OR active_end>?) ORDER BY segment_index",
        (revision_id, fact, fact),
        budget,
    )
    if len(segments) > 1:
        raise SpineValidationError("source_continuity_unresolved", "ambiguous source segment")
    if not segments:
        return None
    segment = segments[0]
    segment_fields = {
        k: (str(v) if k == "segment_index" else v)
        for k, v in segment.items()
        if k not in {"segment_id", "recurrence_revision_id"} and v is not None
    }
    expected_segment, _ = generated_id(
        "recurrence_segment", "spine.recurrence-segment-id.v1", {"recurrence_revision_id": revision_id, **segment_fields}
    )
    invariant(expected_segment == segment["segment_id"], "source segment preimage mismatch")
    rules: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for row in _rows(
        db,
        "SELECT * FROM recurrence_rules WHERE recurrence_revision_id=? AND segment_ref=? AND status='active' ORDER BY rule_id",
        (revision_id, segment["segment_index"]),
        budget,
    ):
        invariant(row["segment_id"] == segment["segment_id"], "rule belongs to a different source segment")
        semantic = _rule(db, row, budget)
        expected_rule, _ = generated_id(
            "recurrence_rule",
            "spine.recurrence-rule-id.v1",
            {"recurrence_revision_id": revision_id, "segment_ref": str(segment["segment_index"]), **semantic},
        )
        invariant(expected_rule == row["rule_id"], "source rule preimage mismatch")
        budget.spend(_calendar_cost(head, semantic, fact))
        normalized = normalize_rule(
            {k: v for k, v in semantic.items() if k not in {"status", "rule_duplicate_index"}}, time_basis=head["time_basis"]
        )
        values = expand_rule(
            normalized,
            time_basis=head["time_basis"],
            range_start=fact,
            range_end=finish,
            timezone=head.get("timezone"),
            timezone_database_version=head.get("timezone_database_version"),
            segment_start=segment["active_start"],
            segment_end=segment["active_end"],
        )
        if values.candidates:
            rules.append((row, semantic))
    dates = _rows(
        db,
        "SELECT * FROM recurrence_rdates WHERE recurrence_revision_id=? AND status='active' AND segment_ref=? "
        "AND scheduled_fact=? ORDER BY rdate_id",
        (revision_id, segment["segment_index"], fact),
        budget,
    )
    if not rules and not dates:
        return None
    date_semantics = [
        {
            "scheduled_fact": r["scheduled_fact"],
            "status": r["status"],
            **({"rdate_duplicate_index": str(r["rdate_duplicate_index"])} if r["rdate_duplicate_index"] is not None else {}),
        }
        for r in dates
    ]
    for row, semantic in zip(dates, date_semantics, strict=True):
        invariant(row["segment_id"] == segment["segment_id"], "rdate belongs to a different source segment")
        expected_date, _ = generated_id(
            "recurrence_rdate",
            "spine.recurrence-rdate-id.v1",
            {"recurrence_revision_id": revision_id, "segment_ref": str(segment["segment_index"]), **semantic},
        )
        invariant(expected_date == row["rdate_id"], "source rdate preimage mismatch")
    selector = {
        "derivation_version": "spine.recurrence-target-occurrence-selector.v1",
        "contract_version": head["contract_version"],
        "normalization_version": head["normalization_version"],
        "canonical_json_version": head["canonical_json_version"],
        "recurrence_set_id": head["recurrence_set_id"],
        "segment_ref": str(segment["segment_index"]),
        "scheduled_fact": fact,
        "origin_kind": "union" if len(rules) + len(dates) > 1 else "rule" if rules else "rdate",
        "source_rule_selectors": sorted([v for _, v in rules], key=canonical_json_bytes),
        "source_rdate_selectors": sorted(date_semantics, key=canonical_json_bytes),
    }
    return {
        "selector": selector,
        "occurrence_key": occurrence_key(selector),
        "header": head,
        "segment": segment,
        "rules": rules,
        "rdates": list(zip(dates, date_semantics, strict=True)),
    }


def require_candidate(db: sqlite3.Connection, revision_id: str, selector: dict[str, Any], budget: ProofBudget) -> dict[str, Any]:
    result = candidate(db, revision_id, str(selector["scheduled_fact"]), budget)
    if result is None or result["selector"] != selector:
        raise SpineValidationError("source_continuity_unresolved", "selector is not the complete current candidate")
    return result


def _lineage(db: sqlite3.Connection, identity: str, budget: ProofBudget) -> dict[str, Any]:
    rows = _rows(db, "SELECT * FROM recurrence_lineage WHERE lineage_id=?", (identity,), budget)
    if len(rows) != 1:
        raise SpineValidationError("source_continuity_unresolved", "missing lineage fact")
    row = rows[0]
    fields = {
        k: (str(v) if k == "lineage_index" else v) for k, v in row.items() if k not in {"lineage_id", "payload_hash"} and v is not None
    }
    expected, _ = generated_id("recurrence_lineage", "spine.recurrence-lineage-id.v1", fields)
    invariant(expected == identity, "lineage identity/preimage mismatch")
    # payload_hash contains the source command effect, which is not independently
    # present in this table. Authority is the registered row plus verified child/
    # revision facts, never a caller's hash or an invented command effect.
    return row


def continuity(
    db: sqlite3.Connection, prior_revision: str, prior_selector: dict[str, Any], hops: list[dict[str, Any]], budget: ProofBudget
) -> dict[str, Any]:
    """Verify every stored hop and every contributing component, not just one."""
    old = require_candidate(db, prior_revision, prior_selector, budget)
    for hop in hops:
        budget.spend(hop=True)
        if hop["prior_revision_id"] != prior_revision or hop["prior_selector"] != prior_selector:
            raise SpineValidationError("source_continuity_unresolved", "disconnected source proof")
        new = require_candidate(db, hop["new_revision_id"], hop["selector"], budget)
        if (
            new["header"]["prior_recurrence_revision_id"] != prior_revision
            or new["header"]["recurrence_set_id"] != old["header"]["recurrence_set_id"]
        ):
            raise SpineValidationError("source_continuity_unresolved", "wrong source revision chain")
        if new["segment"]["source_revision_id"] != prior_revision:
            raise SpineValidationError("source_continuity_unresolved", "copied source segment has incorrect ancestry")
        lines = [_lineage(db, identity, budget) for identity in hop["lineage_ids"]]
        if not lines or any(
            r["prior_recurrence_revision_id"] != prior_revision or r["new_recurrence_revision_id"] != hop["new_revision_id"] for r in lines
        ):
            raise SpineValidationError("source_continuity_unresolved", "lineage revision mismatch")
        if not any(
            r["prior_segment_id"] == old["segment"]["segment_id"] and r["new_segment_id"] == new["segment"]["segment_id"] for r in lines
        ):
            raise SpineValidationError("source_continuity_unresolved", "missing segment correspondence")
        if prior_selector["scheduled_fact"] != hop["selector"]["scheduled_fact"]:
            raise SpineValidationError("source_continuity_unresolved", "no authoritative per-occurrence retarget fact")
        for kind, key in [("rules", "rule_id"), ("rdates", "rdate_id")]:
            matched = []
            for child, semantic in new[kind]:
                links = [r for r in lines if r["new_child_id"] == child[key] and r["effect"] == "copied"]
                if len(links) != 1:
                    raise SpineValidationError("source_continuity_unresolved", "unproved union contributor")
                candidates = [(r, s) for r, s in old[kind] if r[key] == links[0]["prior_child_id"]]
                if len(candidates) != 1:
                    raise SpineValidationError("source_continuity_unresolved", "child correspondence is not one-to-one")
                before, original = candidates[0]
                matched.append(before[key])
                if kind == "rules":
                    excluded = {"start_bound", "end_condition"}
                    equal = {k: v for k, v in semantic.items() if k not in excluded} == {
                        k: v for k, v in original.items() if k not in excluded
                    }
                    if semantic["start_bound"] == original["start_bound"]:
                        equal = equal and semantic["end_condition"] == original["end_condition"]
                    else:
                        equal = (
                            equal
                            and semantic["start_bound"] >= original["start_bound"]
                            and semantic["start_bound"] == new["segment"]["active_start"]
                        )
                        if original["end_condition"]["kind"] == "count":
                            rule = normalize_rule(
                                {k: v for k, v in original.items() if k not in {"status", "rule_duplicate_index"}},
                                time_basis=old["header"]["time_basis"],
                            )
                            budget.spend(_calendar_cost(old["header"], original, semantic["start_bound"]))
                            produced = _valid_candidate_count_between(
                                rule,
                                start=max(rule.seed, rule.start_bound),
                                end=semantic["start_bound"],
                                time_basis=old["header"]["time_basis"],
                                timezone=old["header"].get("timezone"),
                                timezone_database_version=old["header"].get("timezone_database_version"),
                            )
                            remaining = int(original["end_condition"]["count"]) - produced
                            equal = equal and remaining > 0 and semantic["end_condition"] == {"kind": "count", "count": str(remaining)}
                        else:
                            equal = equal and semantic["end_condition"] == original["end_condition"]
                else:
                    equal = semantic == original
                if not equal:
                    raise SpineValidationError("source_continuity_unresolved", "changed candidate stream")
            if len(matched) != len(set(matched)) or set(matched) != {r[key] for r, _ in old[kind]}:
                raise SpineValidationError("source_continuity_unresolved", "missing or merged contributor")
        prior_revision = hop["new_revision_id"]
        prior_selector = hop["selector"]
        old = new
    return old


def _addition_history(db: sqlite3.Connection, root: dict[str, Any], head: dict[str, Any], budget: ProofBudget) -> None:
    """Conservatively rule out a removed/retimed older slot, back to enrollment.

    This is bounded by the same hop/row budget, never a scan of unrelated history.
    Changed stream/topology requires stronger continuity evidence, not novelty.
    """
    while head["recurrence_revision_id"] != root["enrolled_recurrence_revision_id"]:
        budget.spend(hop=True)
        prior_id = head["prior_recurrence_revision_id"]
        if prior_id is None:
            raise SpineValidationError("source_continuity_unresolved", "addition history does not reach enrollment")
        prior = revision(db, prior_id, budget)
        invariant(prior["recurrence_set_id"] == root["recurrence_set_id"], "foreign addition history")
        for table, key, role, ordering in [
            ("recurrence_rules", "rule_id", "rule_revision", "segment_ref,rule_id"),
            ("recurrence_rdates", "rdate_id", "rdate_revision", "segment_ref,scheduled_fact,rdate_id"),
        ]:
            old = _rows(
                db, f"SELECT * FROM {table} WHERE recurrence_revision_id=? AND status='active' ORDER BY {ordering}", (prior_id,), budget
            )
            copied = set()
            for child in old:
                links = _rows(
                    db,
                    "SELECT lineage_id FROM recurrence_lineage WHERE prior_recurrence_revision_id=? AND new_recurrence_revision_id=? "
                    "AND prior_child_id=? AND effect='copied'",
                    (prior_id, head["recurrence_revision_id"], child[key]),
                    budget,
                )
                if len(links) != 1:
                    raise SpineValidationError("source_continuity_unresolved", "unresolved old component prevents novelty")
                link = _lineage(db, links[0]["lineage_id"], budget)
                invariant(link["lineage_role"] == role, "wrong addition-history lineage role")
                targets = _rows(
                    db,
                    f"SELECT * FROM {table} WHERE {key}=? AND recurrence_revision_id=? AND status='active'",
                    (link["new_child_id"], head["recurrence_revision_id"]),
                    budget,
                )
                invariant(len(targets) == 1 and link["new_child_id"] not in copied, "ambiguous addition-history copy")
                target = targets[0]
                copied.add(target[key])
                before = _rule(db, child, budget) if key == "rule_id" else {k: child[k] for k in ("scheduled_fact", "status")}
                after = _rule(db, target, budget) if key == "rule_id" else {k: target[k] for k in ("scheduled_fact", "status")}
                if before != after:
                    raise SpineValidationError("source_continuity_unresolved", "changed component prevents novelty")
                segments = _rows(db, "SELECT * FROM recurrence_segments WHERE segment_id=?", (target["segment_id"],), budget)
                if (
                    len(segments) != 1
                    or segments[0]["source_revision_id"] != prior_id
                    or segments[0]["lineage_parent_segment_id"] != child["segment_id"]
                ):
                    raise SpineValidationError("source_continuity_unresolved", "unproved copied segment ancestry")
            if key == "rule_id":
                new = _rows(
                    db,
                    "SELECT rule_id FROM recurrence_rules WHERE recurrence_revision_id=? AND status='active' ORDER BY segment_ref,rule_id",
                    (head["recurrence_revision_id"],),
                    budget,
                )
                if copied != {v["rule_id"] for v in new}:
                    raise SpineValidationError("source_continuity_unresolved", "unproved new rule prevents novelty")
        head = prior


def verify_proof(db: sqlite3.Connection, root: dict[str, Any], kind: str, payload: dict[str, Any], budget: ProofBudget) -> None:
    """Validate a pinned proof against actual immutable source rows, read-only."""
    from spine.core.recurring_tasks import decode, validate_proof

    validate_proof(kind, payload)
    head = revision(db, payload["recurrence_revision_id"], budget)
    invariant(
        head["recurrence_set_id"] == root["recurrence_set_id"] == payload["recurrence_set_id"]
        and head["source_item_id"] == root["source_item_id"] == payload["source_item_id"]
        and head["normalized_recurrence_set_hash"] == payload["normalized_recurrence_set_hash"],
        "proof source snapshot mismatch",
    )
    details = _rows(
        db,
        "SELECT * FROM event_details WHERE item_id=? AND version=?",
        (root["source_item_id"], int(payload["source_item_version"])),
        budget,
    )
    bound = db.execute(
        "SELECT recurrence_revision_id FROM recurrence_revisions WHERE recurrence_set_id=? AND source_item_version<=? "
        "ORDER BY source_item_version DESC LIMIT 1",
        (root["recurrence_set_id"], int(payload["source_item_version"])),
    ).fetchone()
    budget.spend()
    invariant(len(details) == 1 and bound is not None and bound[0] == payload["recurrence_revision_id"], "proof item-version mismatch")
    if kind == "source_cancelled":
        invariant(details[0]["event_status"] == "cancelled" and payload["cancelled_event_version"] == payload["source_item_version"])
        return
    current = require_candidate(db, payload["recurrence_revision_id"], payload["selector"], budget)
    if kind in {"identity", "excluded", "occurrence_cancelled"}:
        reservations = _rows(
            db,
            "SELECT assignment_id FROM related_task_selector_reservations WHERE related_task_rule_id=? AND occurrence_key=?",
            (root["related_task_rule_id"], payload["occurrence_key"]),
            budget,
        )
        invariant(len(reservations) == 1, "identity requires an existing selector reservation")
    for lid in payload["lineage_ids"]:
        row = _lineage(db, lid, budget)
        invariant(row["recurrence_set_id"] == root["recurrence_set_id"], "foreign proof lineage")
    if "prior_proof_id" in payload:
        prior_rows = _rows(
            db,
            "SELECT * FROM related_task_source_proofs WHERE proof_id=? AND related_task_rule_id=?",
            (payload["prior_proof_id"], root["related_task_rule_id"]),
            budget,
        )
        invariant(len(prior_rows) == 1, "missing preceding proof")
        prior = prior_rows[0]
        previous = decode(prior["proof_json"])
        invariant(previous.get("selector") == payload["prior_selector"], "prior proof selector mismatch")
        if kind == "carry_forward":
            invariant(bool(payload["hops"]), "carry-forward requires source hops")
            resolved = continuity(db, prior["recurrence_revision_id"], payload["prior_selector"], payload["hops"], budget)
            invariant(
                resolved["header"]["recurrence_revision_id"] == payload["recurrence_revision_id"]
                and resolved["selector"] == payload["selector"]
            )
            invariant(sorted({lid for hop in payload["hops"] for lid in hop["lineage_ids"]}) == payload["lineage_ids"])
        elif kind in {"excluded", "occurrence_cancelled"}:
            invariant(
                prior["recurrence_revision_id"] == payload["recurrence_revision_id"] and payload["prior_selector"] == payload["selector"],
                "inactive proof must reference accepted current identity",
            )
        elif kind == "identity":
            invariant(payload["prior_selector"] == payload["selector"], "identity cannot retarget a selector")
    if kind == "enrollment":
        invariant(
            payload["enrolled_recurrence_revision_id"] == root["enrolled_recurrence_revision_id"] == payload["recurrence_revision_id"]
        )
    if kind == "component_candidate":
        invariant(payload["basis_revision_id"] == root["enrolled_recurrence_revision_id"], "component basis is not enrollment")
        basis = candidate(db, payload["basis_revision_id"], payload["selector"]["scheduled_fact"], budget)
        invariant(basis is not None, "missing component basis")
        assert basis is not None
        component = payload["component_selector"]
        invariant(component.get("source_kind") in {"rule", "rdate"}, "unknown component source kind")
        field = "source_rule_selectors" if component["source_kind"] == "rule" else "source_rdate_selectors"
        invariant(component["selector"] in basis["selector"][field], "component not present at basis")
        if payload["hops"]:
            resolved = continuity(db, payload["basis_revision_id"], basis["selector"], payload["hops"], budget)
            invariant(
                resolved["selector"] == payload["selector"]
                and resolved["header"]["recurrence_revision_id"] == payload["recurrence_revision_id"]
            )
        else:
            invariant(
                payload["basis_revision_id"] == root["enrolled_recurrence_revision_id"] == payload["recurrence_revision_id"]
                and basis["selector"] == payload["selector"],
                "unproved component continuity",
            )
    if kind == "new_rdate":
        prior_revision = payload["prior_recurrence_revision_id"]
        invariant(
            head["prior_recurrence_revision_id"] == prior_revision and payload["rdate_id"] in {r["rdate_id"] for r, _ in current["rdates"]}
        )
        prior_candidate = candidate(db, prior_revision, payload["selector"]["scheduled_fact"], budget)
        if prior_candidate is not None:
            raise SpineValidationError("source_continuity_unresolved", "added date aliases an included old slot")
        _addition_history(db, root, head, budget)
        lines = [_lineage(db, lid, budget) for lid in payload["lineage_ids"]]
        invariant(
            any(
                r["new_child_id"] == payload["rdate_id"]
                and r["prior_child_id"] is None
                and r["effect"] == "created"
                and r["new_recurrence_revision_id"] == head["recurrence_revision_id"]
                for r in lines
            ),
            "unproved positive addition",
        )
        reserved = _rows(
            db,
            "SELECT proof_id FROM related_task_selector_reservations WHERE related_task_rule_id=? AND occurrence_key=?",
            (root["related_task_rule_id"], payload["occurrence_key"]),
            budget,
        )
        from spine.core.recurring_tasks import derive

        identity = derive("proof", {"related_task_rule_id": root["related_task_rule_id"], "proof_kind": kind, "proof_payload": payload})[0]
        invariant(not reserved or all(r["proof_id"] == identity for r in reserved), "added date is already reserved by other evidence")
    if kind in {"excluded", "occurrence_cancelled"}:
        table, key = ("recurrence_exdates", "exdate_id") if kind == "excluded" else ("recurrence_overrides", "override_id")
        rows = _rows(
            db,
            f"SELECT * FROM {table} WHERE {key}=? AND recurrence_revision_id=? AND status='active'",
            (payload[key], payload["recurrence_revision_id"]),
            budget,
        )
        invariant(len(rows) == 1 and rows[0]["target_occurrence_key"] == payload["occurrence_key"], "missing source cancellation evidence")
        if kind == "occurrence_cancelled":
            invariant(rows[0]["lifecycle"] == "cancelled")
