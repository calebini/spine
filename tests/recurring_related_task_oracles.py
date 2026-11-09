"""Independent, bounded offline witnesses; NOT an RRT runtime implementation.

The source checker deliberately supports only the retained single-weekday WEEKLY
fixtures (at most 64 generated candidates). It neither resolves arbitrary user
recurrences nor opens a database. The cursor checker operates on synthetic exact
snapshots/context; it is not an admission/CLI/service entrypoint.
"""

import base64
import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta

VERSIONS = {
    "contract_version": "spine.recurrence.contract.v1",
    "normalization_version": "spine.recurrence.normalization.v1",
    "canonical_json_version": "spine.canonical-json.v1",
}
CURSOR = "spine.recurring-related-tasks.cursor.v1"


def digest(value, encode):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def check_snapshot(record, encode):
    """Identity correctness does not waive the fixture's copied-segment ancestry."""
    value = check_snapshot_hashes(record, encode)
    prior = value.get("prior_recurrence_revision_id")
    if value["revision_number"] == "1":
        if prior is not None:
            raise ValueError("initial snapshot has a predecessor")
        expected_source = "initial"
    else:
        if not isinstance(prior, str) or not prior.startswith("recurrence_revision_"):
            raise ValueError("successor snapshot lacks a stable predecessor")
        expected_source = prior
    # These fixture segments are all newly produced/copied in their revision,
    # including the split's retired lineage facts. Historical rows are not edited.
    if any(row["source_revision_id"] != expected_source for row in value["segments"]):
        raise ValueError("fixture segment ancestry mismatch")
    return value


def check_snapshot_hashes(record, encode):
    """Check public rows against complete independent hash/ID preimages."""
    value, pre = record["value"], record["normalized_hash_preimage"]
    refs = {s["segment_id"]: s["segment_index"] for s in value["segments"]}
    expected = {
        "derivation_version": "normalized_recurrence_set_hash.v1",
        **VERSIONS,
        **{
            k: value[k]
            for k in [
                "recurrence_set_id",
                "revision_number",
                "source_item_id",
                "created_item_version",
                "source_item_version",
                "seed_anchor_id",
                "time_basis",
            ]
        },
    }
    for k in ["timezone", "timezone_database_version"]:
        if k in value:
            expected[k] = value[k]
    for collection, field in [
        ("segments", "segment_id"),
        ("rules", "rule_id"),
        ("rdates", "rdate_id"),
        ("exdates", "exdate_id"),
        ("overrides", "override_id"),
    ]:
        rows = []
        for row in value[collection]:
            item = {k: v for k, v in row.items() if k not in {field, "segment_id", "target_occurrence_key"}}
            if collection != "segments":
                item["segment_ref"] = refs[row["segment_id"]]
            rows.append(item)
        expected[collection] = rows
    if pre != expected or digest(pre, encode) != value["normalized_recurrence_set_hash"]:
        raise ValueError("snapshot/preimage/hash mismatch")
    set_pre = {
        "derivation_version": "spine.recurrence-set-id.v1",
        **VERSIONS,
        **{k: value[k] for k in ["source_item_id", "seed_anchor_id", "created_item_version", "time_basis"]},
    }
    for k in ["timezone", "timezone_database_version"]:
        if k in value:
            set_pre[k] = value[k]
    if record["recurrence_set_id_preimage"] != set_pre or value["recurrence_set_id"] != "recurrence_set_" + digest(set_pre, encode):
        raise ValueError("set identity mismatch")
    rev_pre = record["recurrence_revision_id_preimage"]
    expected_rev = {
        "derivation_version": "spine.recurrence-revision-id.v1",
        **VERSIONS,
        **{k: value[k] for k in ["recurrence_set_id", "revision_number", "normalized_recurrence_set_hash"]},
    }
    if "command_id" in rev_pre:
        expected_rev["command_id"] = rev_pre["command_id"]
    if "prior_recurrence_revision_id" in value:
        expected_rev["prior_recurrence_revision_id"] = value["prior_recurrence_revision_id"]
    if rev_pre != expected_rev or value["recurrence_revision_id"] != "recurrence_revision_" + digest(rev_pre, encode):
        raise ValueError("revision identity mismatch")
    for collection, field, prefix, version in [
        ("segments", "segment_id", "recurrence_segment", "spine.recurrence-segment-id.v1"),
        ("rules", "rule_id", "recurrence_rule", "spine.recurrence-rule-id.v1"),
        ("rdates", "rdate_id", "recurrence_rdate", "spine.recurrence-rdate-id.v1"),
        ("exdates", "exdate_id", "recurrence_exdate", "spine.recurrence-exdate-id.v2"),
        ("overrides", "override_id", "recurrence_override", "spine.recurrence-override-id.v2"),
    ]:
        computed = []
        for row, normalized in zip(value[collection], expected[collection], strict=True):
            identity = {
                k: v for k, v in normalized.items() if collection not in {"exdates", "overrides"} or k != "prior_target_occurrence_key"
            }
            child_pre = {"derivation_version": version, **VERSIONS, "recurrence_revision_id": value["recurrence_revision_id"], **identity}
            if row[field] != prefix + "_" + digest(child_pre, encode):
                raise ValueError("child identity mismatch")
            computed.append(child_pre)
        published = record.get(
            {"segments": "segment_id_preimages", "rules": "rule_id_preimages", "rdates": "rdate_id_preimages"}.get(collection, "")
        )
        if published is not None and published != computed:
            raise ValueError("published child preimage mismatch")
    return value


def weekly_candidates(rule, until):
    """Exactly the supported finite fixture shape, bounded even for unbounded rules."""
    if rule["frequency"] != "WEEKLY" or rule.get("by_weekday") != ["SA"] or rule.get("week_start") != "MO":
        raise ValueError("unsupported fixture rule")
    point = datetime.fromisoformat(rule["seed"])
    if point.weekday() != 5 or any(k in rule for k in ["by_month", "by_month_day", "by_set_position"]):
        raise ValueError("unsupported fixture selector")
    lower = datetime.fromisoformat(rule["start_bound"])
    upper = datetime.fromisoformat(until)
    step = timedelta(days=7 * int(rule["interval"]))
    end = rule["end_condition"]
    result = []
    for _ in range(64):
        if point > upper:
            return result
        if point >= lower:
            if end["kind"] == "count" and len(result) >= int(end["count"]):
                return result
            if end["kind"] == "until" and point > datetime.fromisoformat(end["until"]):
                return result
            result.append(point.isoformat(timespec="seconds"))
        point += step
    raise ValueError("finite fixture proof budget exceeded")


def candidate(value, fact, encode):
    buckets = []
    for segment in value["segments"]:
        if (
            segment["status"] != "active"
            or fact < segment["active_start"]
            or (segment.get("active_end") is not None and fact >= segment["active_end"])
        ):
            continue
        rows = [
            r
            for r in value["rules"]
            if r["status"] == "active" and r["segment_id"] == segment["segment_id"] and fact in weekly_candidates(r, fact)
        ]
        dates = [
            r
            for r in value["rdates"]
            if r["status"] == "active" and r["segment_id"] == segment["segment_id"] and r["scheduled_fact"] == fact
        ]
        if not rows and not dates:
            continue

        def semantic(row, field):
            return {k: v for k, v in row.items() if k not in {field, "segment_id"}}

        rs = sorted([semantic(r, "rule_id") for r in rows], key=encode)
        ds = sorted([semantic(r, "rdate_id") for r in dates], key=encode)
        selector = {
            "derivation_version": "spine.recurrence-target-occurrence-selector.v1",
            **VERSIONS,
            "recurrence_set_id": value["recurrence_set_id"],
            "segment_ref": segment["segment_index"],
            "scheduled_fact": fact,
            "origin_kind": "union" if len(rs) + len(ds) > 1 else "rule" if rs else "rdate",
            "source_rule_selectors": rs,
            "source_rdate_selectors": ds,
        }
        buckets.append((selector, rows + dates, segment))
    if len(buckets) > 1:
        raise ValueError("ambiguous fixture candidate")
    return buckets[0] if buckets else None


def source_case(corpus, case, encode):
    records = {s["case_id"]: s for s in corpus["snapshots"]}
    pair = next(p for p in corpus["pairs"] if p["case_id"] == case["pair"])
    before = check_snapshot(records[pair["prior_snapshot"]], encode)
    after = check_snapshot(records[pair["snapshot"]], encode)
    if (
        before["recurrence_set_id"] != after["recurrence_set_id"]
        or after.get("prior_recurrence_revision_id") != before["recurrence_revision_id"]
    ):
        return "decision_required"
    valid_rows = {}
    for fact in pair["lineage"]:
        row, pre, payload = fact["row"], fact["identity_preimage"], fact["payload"]
        identity = {k: v for k, v in row.items() if k not in {"lineage_id", "payload_hash"}}
        if pre != {"derivation_version": "spine.recurrence-lineage-id.v1", **VERSIONS, **identity}:
            return "decision_required"
        if row["lineage_id"] != "recurrence_lineage_" + digest(pre, encode) or row["payload_hash"] != digest(payload, encode):
            return "decision_required"
        if {k: v for k, v in payload.items() if k != "command_effect"} != identity:
            return "decision_required"
        if (
            row["prior_recurrence_revision_id"] != before["recurrence_revision_id"]
            or row["new_recurrence_revision_id"] != after["recurrence_revision_id"]
        ):
            return "decision_required"
        valid_rows[row["lineage_id"]] = row
    old, new = candidate(before, case["fact"], encode), candidate(after, case["fact"], encode)
    if new is None:
        return "decision_required"
    old_children = {r.get("rule_id", r.get("rdate_id")): r for r in before["rules"] + before["rdates"]}
    copies = {c["new_child_id"]: c for c in pair["copy_facts"]}

    def unchanged(child):
        child_id = child.get("rule_id", child.get("rdate_id"))
        link = copies.get(child_id)
        if link is None:
            return False
        prior = old_children.get(link["prior_child_id"])
        row = valid_rows.get(link["lineage_id"], {})
        if (
            prior is None
            or row.get("effect") != "copied"
            or row.get("prior_child_id") != link["prior_child_id"]
            or row.get("new_child_id") != child_id
        ):
            return False
        if "rule_id" not in child:
            return child["scheduled_fact"] == prior.get("scheduled_fact")
        excluded = {"rule_id", "segment_id", "start_bound", "end_condition"}
        if {k: v for k, v in child.items() if k not in excluded} != {k: v for k, v in prior.items() if k not in excluded}:
            return False
        if child["start_bound"] == prior["start_bound"]:
            return child["end_condition"] == prior["end_condition"]
        if child["start_bound"] < prior["start_bound"]:
            return False
        split = child["start_bound"]
        if split != new[2]["active_start"]:
            return False
        if prior["end_condition"]["kind"] != "count":
            return child["end_condition"] == prior["end_condition"]
        produced = len(weekly_candidates(prior, (datetime.fromisoformat(split) - timedelta(seconds=1)).isoformat()))
        remaining = int(prior["end_condition"]["count"]) - produced
        return (
            remaining > 0
            and child["end_condition"] == {"kind": "count", "count": str(remaining)}
            and link.get("count_subtraction")
            == {
                "split_scheduled_fact": split,
                "original_count": prior["end_condition"]["count"],
                "produced_before_split": str(produced),
                "remaining_count": str(remaining),
            }
        )

    if case["mode"] == "novel":
        if old is not None or new[0] in case.get("reserved_selectors", []):
            return "not_novel"
        # Prove no changed old component could represent an unresolved old slot
        # at a new time. The retained addition fixture has unchanged components.
        active_new = after["rules"] + after["rdates"]
        for prior_id, prior in old_children.items():
            if prior["status"] == "active" and not any(
                copies.get(r.get("rule_id", r.get("rdate_id")), {}).get("prior_child_id") == prior_id and unchanged(r) for r in active_new
            ):
                return "decision_required"
        for child in new[1]:
            cid = child.get("rdate_id")
            if cid is None or not any(
                r.get("new_child_id") == cid and r.get("effect") == "created" and "prior_child_id" not in r for r in valid_rows.values()
            ):
                return "decision_required"
        return "new_slot"
    if old is None or not all(unchanged(r) for r in new[1]):
        return "decision_required"
    # Every contributing child must have an old contributing counterpart. Do not
    # let one unchanged contributor bless an otherwise unproved union.
    old_ids = {r.get("rule_id", r.get("rdate_id")) for r in old[1]}
    mapped = [copies[r.get("rule_id", r.get("rdate_id"))]["prior_child_id"] for r in new[1]]
    if len(mapped) != len(set(mapped)) or set(mapped) != old_ids:
        return "decision_required"
    if not any(
        r.get("prior_segment_id") == old[2]["segment_id"] and r.get("new_segment_id") == new[2]["segment_id"] for r in valid_rows.values()
    ):
        return "decision_required"
    if case["mode"] == "retarget":
        targets = pair["retarget_facts"]
        if len({encode(t["prior_selector"]) for t in targets}) != len(targets) or len({encode(t["selector"]) for t in targets}) != len(
            targets
        ):
            return "decision_required"
        matching = [t for t in targets if t["prior_selector"] == old[0] and t["selector"] == new[0]]
        if len(matching) != 1 or not matching[0]["lineage_ids"] or any(i not in valid_rows for i in matching[0]["lineage_ids"]):
            return "decision_required"
    return "same_assignment"


def cursor_case(wire, context, encode, validate_payload):
    """Offline cursor/later-expected witness, after earlier admission/replay gates.

    This does not replace compatible replay, actor validation or request dispatch.
    """
    try:
        if not re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]{43}", wire):
            return "invalid_request"
        payload_part, tag_part = wire.split(".")

        def decode(value):
            return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

        raw, tag = decode(payload_part), decode(tag_part)
        if (
            base64.urlsafe_b64encode(raw).rstrip(b"=").decode() != payload_part
            or base64.urlsafe_b64encode(tag).rstrip(b"=").decode() != tag_part
        ):
            return "invalid_request"

        def pairs(values):
            result = {}
            for key, value in values:
                if key in result:
                    raise ValueError("duplicate key")
                result[key] = value
            return result

        payload = json.loads(raw, object_pairs_hook=pairs)
        if encode(payload).encode() != raw or not validate_payload(payload):
            return "invalid_request"
        key = context["keys"].get(payload["key_id"])
        if key is None or not hmac.compare_digest(
            tag, hmac.new(bytes.fromhex(key), CURSOR.encode() + b"\0" + raw, hashlib.sha256).digest()
        ):
            return "invalid_request"
        if payload["cursor_version"] != CURSOR or payload["purpose"] != context["purpose"] or payload["query"] != context["query"]:
            return "invalid_request"
        start = datetime.fromisoformat(payload["issued_at_utc"].replace("Z", "+00:00"))
        expiry = datetime.fromisoformat(payload["expires_at_utc"].replace("Z", "+00:00"))
        if expiry - start != timedelta(seconds=3600):
            return "invalid_request"
        if datetime.fromisoformat(context["now"].replace("Z", "+00:00")) >= expiry:
            return "stale_cursor"
        if any(payload.get(k) != v for k, v in context["freshness"].items()):
            return "stale_cursor"
        return "stale_version" if context["expected_mismatch"] else "accepted"
    except (ValueError, KeyError, TypeError, UnicodeError):
        return "invalid_request"
