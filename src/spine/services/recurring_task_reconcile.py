"""Internal manual recurring-task reconciliation. No scheduler/public activation."""

from __future__ import annotations

import copy
import sys
from collections.abc import Callable
from datetime import timedelta
from functools import partial
from typing import Any

from spine.commands import core as c
from spine.commands.recurring_task_runtime import PREFIX, cursor_payload, fail, instant, sign_cursor, verify_cursor, wire
from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.core.occurrences import expand_recurrence_set
from spine.core.recurring_tasks import CONTRACT, derive, occurrence_key, payload_hash
from spine.ledger.identity import read_ledger_instance_id
from spine.ledger.recurrence import load_current_recurrence_set
from spine.ledger.recurring_task_sources import ProofBudget, _calendar_cost
from spine.ledger.recurring_tasks import compare_and_swap, ensure_selector, insert_record, read_record, reserve_selector, row
from spine.ledger.temporal_bindings import target_from_source
from spine.services import recurring_task_children as children
from spine.services import recurring_task_proofs as proofs


class _PageBoundary(Exception):
    """Rollback a tentative whole unit or final response projection."""


def continuation(db: Any, request: dict[str, Any], root: dict[str, Any], context: Any, contracts: Any, now: str) -> dict[str, Any] | None:
    from spine.commands.recurring_tasks import catalog, source_snapshot

    if "cursor" not in request:
        return None
    query = {
        "contract_version": CONTRACT,
        "ledger_instance_id": read_ledger_instance_id(db),
        "related_task_rule_id": root["related_task_rule_id"],
        "limits": request["limits"],
    }
    value = verify_cursor(
        context.facet_cursor_config, request["cursor"], purpose="reconcile", query=query, catalog=catalog(db), now=now, contracts=contracts
    )
    snapshot = source_snapshot(db, root)
    expected = {
        "rule_change_version": str(root["change_version"]),
        "rule_revision_id": root["current_revision_id"],
        **{k: snapshot[k] for k in ("source_item_version", "recurrence_revision_id", "normalized_recurrence_set_hash")},
    }
    if any(value[k] != v for k, v in expected.items()):
        fail("stale_cursor", "cursor")
    return value


def references(db: Any, assignment: dict[str, Any], desired: str | None = None) -> dict[str, Any]:
    state = read_record(db, "related_task_assignment_revisions", assignment["current_assignment_revision_id"])["state_json"]
    gen = read_record(db, "related_task_generations", assignment["current_generation_id"])
    owner = db.execute("SELECT * FROM item_access_owners WHERE item_id=?", (gen["task_item_id"],)).fetchone()
    if owner is None:
        fail("environment_failure", "assignment")
    return {
        "assignment_id": assignment["assignment_id"],
        "generation_id": gen["generation_id"],
        "task_item_id": gen["task_item_id"],
        "task_item_version": state["task_item_version"],
        "temporal_binding_id": gen["temporal_binding_id"],
        "temporal_binding_revision_id": state["temporal_binding_revision_id"],
        "adopted_rule_revision_id": state["adopted_rule_revision_id"],
        "desired_rule_revision_id": desired,
        "predecessor_generation_id": gen["predecessor_generation_id"],
        "item_access_owner_id": owner["item_access_owner_id"],
        "item_access_owner_revision": str(owner["current_revision"]),
    }


def entry(
    selector: dict[str, Any],
    outcome: str,
    reason: str,
    *,
    assignment: str | None = None,
    generation: str | None = None,
    actions: tuple[str, ...] = (),
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    proof_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "outcome": outcome,
        "reason": reason,
        "selector": selector,
        "occurrence_key": occurrence_key(selector),
        "assignment_id": assignment,
        "generation_id": generation,
        "actions": sorted(set(actions)),
        "before": before,
        "after": after,
        "proof_ids": sorted(set(proof_ids)),
    }


def baseline(config: dict[str, Any]) -> dict[str, Any]:
    return {k: copy.deepcopy(v) for k, v in config.items() if k not in {"task_owner", "generation_horizon_seconds"}}


class Page:
    def __init__(
        self,
        db: Any,
        context: Any,
        root: dict[str, Any],
        request: dict[str, Any],
        contracts: Any,
        now: str,
        runtime: dict[str, Any],
        fault: Any,
    ) -> None:
        from spine.commands.recurring_tasks import source_snapshot

        self.db, self.context, self.root, self.request, self.contracts, self.now = db, context, root, request, contracts, now
        self.runtime, self.fault = runtime, fault
        self.snapshot = source_snapshot(db, root)
        self.config = read_record(db, "related_task_rule_revisions", root["current_revision_id"])["configuration_json"]
        self.limits = {k: int(v) for k, v in request["limits"].items()}
        self.budget = ProofBudget(
            self.limits["proof_steps"],
            self.limits["lineage_hops"],
            lambda hop: fail("capacity_exceeded", "limits.lineage_hops" if hop else "limits.proof_steps"),
        )
        self.results: list[dict[str, Any]] = []
        self.work: dict[str, list[str]] = {k: [] for k in ("created", "retained", "cancelled", "protected_stale")}
        self.mappings: list[dict[str, Any]] = []
        self.changed = False
        self.owners = False
        self.mutations = 0
        self.units: list[tuple[Any, dict[str, Any], int, dict[str, Any], str]] = []
        self.position: dict[str, Any] = {}
        self.lane = "assignments"
        # Bound loading before the existing recurrence projection constructs lists.
        for table in ("recurrence_rules", "recurrence_segments", "recurrence_rdates", "recurrence_exdates", "recurrence_overrides"):
            rows = db.execute(
                f"SELECT 1 FROM {table} WHERE recurrence_revision_id=? LIMIT ?",
                (self.snapshot["recurrence_revision_id"], self.budget.steps + 1),
            ).fetchall()
            self.budget.spend(len(rows))
        recurrence = load_current_recurrence_set(db, item_id=root["source_item_id"])
        if recurrence is None:
            fail("environment_failure", "source")
        self.recurrence: dict[str, Any] = recurrence
        self.source_item = c._hydrated_item(db, root["source_item_id"])

    def unit(self, operation: Callable[[], dict[str, Any]], selector: dict[str, Any], *,
             assignment: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Try a complete unit; a page boundary rolls back that unit and its trackers."""
        snapshot = copy.deepcopy(
            {key: getattr(self, key) for key in ("root", "work", "mappings", "changed", "owners", "mutations", "runtime")}
        )
        prior_work = sum(len(values) for values in self.work.values())
        unit_work = 0
        self.unit_oversized = False
        scope = self.db.command_unit(nested=True)
        scope.__enter__()
        try:
            before = self.db.total_changes
            value = operation()
            self.mutations = snapshot["mutations"] + int(self.db.total_changes != before)
            unit_work = sum(len(values) for values in self.work.values()) - prior_work
            if self.mutations > self.limits["mutations"]:
                fail("capacity_exceeded", "limits.mutations")
            if prior_work + unit_work > self.limits["work_rows"]:
                fail("capacity_exceeded", "limits.work_rows")
        except SpineValidationError as error:
            scope.__exit__(*sys.exc_info())
            # The caller still owns one outer transaction. Never restore SQL by
            # deleting history or clear trackers for already-accepted units.
            for key, value in snapshot.items():
                current = getattr(self, key)
                if isinstance(current, dict):
                    current.clear()
                    current.update(value)
                else:
                    setattr(self, key, value)
            if (
                error.code == "capacity_exceeded:limits.work_rows"
                and self.results
                and not self.unit_oversized
                and unit_work <= self.limits["work_rows"]
            ):
                return None
            if error.code == "capacity_exceeded:limits.mutations" and self.results:
                return None
            code, _, field = error.code.partition(":")
            reason = None
            if code.startswith("rendering_"):
                reason = "disclosure_unavailable"
            elif field == "configuration.delivery" or code in {"delivery_target_not_found", "delivery_target_inactive"}:
                reason = "route_unavailable"
            elif code == "semantic_conflict" and field == "configuration.task_template":
                reason = "configuration_invalid"
            elif code == "source_continuity_unresolved":
                reason = "source_continuity_unresolved"
            if reason:
                scope = self.db.command_unit(nested=True)
                scope.__enter__()
                refs = references(self.db, assignment) if assignment else None
                value = entry(selector, "decision_required", reason,
                              assignment=assignment["assignment_id"] if assignment else None,
                              generation=assignment["current_generation_id"] if assignment else None,
                              before=refs, after=refs)
            else:
                raise
        except BaseException:
            scope.__exit__(*sys.exc_info())
            raise
        self.units.append((scope, snapshot, len(self.results), copy.deepcopy(self.position), self.lane))
        return value

    def rollback_unit(self) -> str:
        scope, snapshot, count, position, lane = self.units.pop()
        scope.__exit__(_PageBoundary, _PageBoundary(), None)
        for key, value in snapshot.items():
            current = getattr(self, key)
            if isinstance(current, dict):
                current.clear()
                current.update(value)
            else:
                setattr(self, key, value)
        del self.results[count:]
        self.position.clear()
        self.position.update(position)
        return lane

    def spend(self) -> None:
        try:
            self.budget.spend()
        except SpineValidationError:
            fail("capacity_exceeded", "limits.proof_steps")

    def expand(self, start: str, end: str, *, basis: str) -> list[dict[str, Any]]:
        for rule in self.recurrence["rules"]:
            if rule["status"] == "active":
                self.budget.spend(_calendar_cost(self.recurrence, rule, end))
        return list(
            expand_recurrence_set(self.recurrence, range_start=start, range_end=end, range_basis=basis, spend_work=self.spend).occurrences
        )

    def occurrence(self, selector: dict[str, Any]) -> dict[str, Any] | None:
        fact = selector["scheduled_fact"]
        values = self.expand(fact, c._next_scheduled_fact(fact, time_basis=self.recurrence["time_basis"]), basis="original_schedule")
        matched = [v for v in values if v["target_occurrence_selector"] == selector]
        return matched[0] if len(matched) == 1 else None

    def candidates(self, start: str, end: str) -> list[dict[str, Any]]:
        from spine.timezones import timezone_for_version

        zone = None
        if self.recurrence["time_basis"] == "local_instant":
            zone = timezone_for_version(self.recurrence["timezone"], self.recurrence["timezone_database_version"])

        def fact(value: str) -> str:
            return instant(value).astimezone(zone).isoformat(timespec="seconds").split("+")[0] if zone else value

        # UTC-to-local endpoints need a conservative envelope around offset changes.
        lower, upper = fact(wire(instant(start) - timedelta(days=2))), fact(wire(instant(end) + timedelta(days=2)))
        if zone:
            lower, upper = lower[:19], upper[:19]
        values = self.expand(lower, upper, basis="expressed_time")
        result = []
        for occurrence in values:
            source = children.source_facts(
                self.db, self.root, self.recurrence, occurrence, self.now, persist=False, command_id=self.request["command_id"]
            )
            if not start <= source["resolved_source_utc"] < end:
                continue
            selector = occurrence["target_occurrence_selector"]
            boundary = self.root["enrollment_json"].get("selector")
            if boundary is not None and (selector["scheduled_fact"], canonical_json_bytes(selector)) < (
                boundary["scheduled_fact"],
                canonical_json_bytes(boundary),
            ):
                continue
            if boundary is None and instant(source["resolved_source_utc"]) + timedelta(
                seconds=int(self.config["offset_seconds"])
            ) <= instant(self.root["enrolled_at_utc"]):
                continue
            result.append(occurrence)
        return sorted(result, key=lambda v: (v["original_scheduled_fact"], canonical_json_bytes(v["target_occurrence_selector"])))

    def create(
        self,
        occurrence: dict[str, Any],
        *,
        assignment: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        config_id: str | None = None,
        proof_id: str | None = None,
        managed_baseline: dict[str, Any] | None = None,
        restoration: Any = None,
    ) -> dict[str, Any]:
        config, config_id = config or self.config, config_id or self.root["current_revision_id"]
        selector = occurrence["target_occurrence_selector"]
        source = children.source_facts(
            self.db, self.root, self.recurrence, occurrence, self.now, persist=False, command_id=self.request["command_id"]
        )
        due = target_from_source(source, int(config["offset_seconds"]))["utc_instant"]
        if due <= self.now:
            return entry(
                selector,
                "skipped_due",
                "due_not_future",
                assignment=assignment["assignment_id"] if assignment else None,
                generation=assignment["current_generation_id"] if assignment else None,
            )
        if (
            occurrence["lifecycle"] != "active"
            or self.source_item["status"] != "active"
            or self.source_item["detail"]["event_status"] != "scheduled"
        ):
            return entry(selector, "decision_required", "source_evidence_unavailable")
        if proof_id is None:
            kind, proof = proofs.initial(self.db, self.root, self.snapshot, selector, self.budget)
            if kind == "component_candidate":
                basis_selector = proof["hops"][0]["prior_selector"] if proof["hops"] else selector
                reserved = self.db.execute(
                    "SELECT assignment_id,occurrence_key FROM related_task_selector_reservations "
                    "WHERE related_task_rule_id=? AND occurrence_key=?",
                    (self.root["related_task_rule_id"], occurrence_key(basis_selector)),
                ).fetchone()
                if reserved is not None:
                    return entry(
                        selector,
                        "decision_required",
                        "source_continuity_unresolved",
                        before={
                            "conflicting_assignment_ids": [reserved["assignment_id"]],
                            "conflicting_occurrence_keys": [reserved["occurrence_key"]],
                        },
                    )
            proof_id = proofs.persist(self.db, self.root, kind, proof, self.request, self.now, self.budget)
        reference = ensure_selector(self.db, revision_id=self.snapshot["recurrence_revision_id"], selector=selector, budget=self.budget)
        first = assignment is None
        assignment_id = (
            assignment["assignment_id"]
            if assignment
            else derive("assignment", {"related_task_rule_id": self.root["related_task_rule_id"], "initial_selector": selector})[0]
        )
        prior = read_record(self.db, "related_task_generations", assignment["current_generation_id"]) if assignment is not None else None
        index = prior["generation_index"] + 1 if prior is not None else 1
        generation_id = derive("generation", {"assignment_id": assignment_id, "generation_index": str(index)})[0]
        source = children.source_facts(
            self.db, self.root, self.recurrence, occurrence, self.now, persist=True, command_id=self.request["command_id"]
        )
        child = children.create(
            self.db, self.context, self.root, config, assignment_id, generation_id, source, self.request, self.now, self.fault,
            restoration=restoration,
        )
        self.runtime["cutoffs"].append(due)
        self.runtime["audit_ids"].append(child["audit_id"])
        self.work["created"].extend(child["work"])
        self.mappings.extend(child["policy_mappings"])
        state = {
            "generation_id": generation_id,
            "selector": selector,
            "occurrence_key": occurrence["occurrence_key"],
            "source_item_version": self.snapshot["source_item_version"],
            "recurrence_revision_id": self.snapshot["recurrence_revision_id"],
            "proof_id": proof_id,
            "task_item_id": child["task_item_id"],
            "task_item_version": "1",
            "temporal_binding_revision_id": child["temporal_binding_revision_id"],
            "adopted_rule_revision_id": config_id,
            "managed_baseline": copy.deepcopy(managed_baseline) if managed_baseline is not None else baseline(config),
            "disposition": "governed",
            "restoration_veto": False,
            "reason": "new_source_slot" if first else "source_restored",
        }
        before = references(self.db, assignment) if assignment else None
        insert_record(
            self.db,
            "related_task_generations",
            {
                "generation_id": generation_id,
                "assignment_id": assignment_id,
                "generation_index": index,
                "predecessor_generation_id": prior["generation_id"] if prior else None,
                "task_item_id": child["task_item_id"],
                "created_task_version": 1,
                "relationship_id": child["relationship_id"],
                "temporal_binding_id": child["temporal_binding_id"],
                "item_access_owner_id": child["item_access_owner_id"],
                "created_rule_revision_id": config_id,
                "creation_proof_id": proof_id,
                "created_by_command_id": self.request["command_id"],
                "created_at_utc": self.now,
            },
        )
        if first:
            digest = payload_hash("state", state)[0]
            state_id = derive("assignment_revision", {"assignment_id": assignment_id, "change_version": "1", "state_hash": digest})[0]
            insert_record(
                self.db,
                "related_task_assignments",
                {
                    "assignment_id": assignment_id,
                    "related_task_rule_id": self.root["related_task_rule_id"],
                    "assignment_seq": self.root["next_assignment_seq"],
                    "initial_selector_ref": reference,
                    "initial_selector_json": selector,
                    "initial_occurrence_key": occurrence["occurrence_key"],
                    "created_rule_revision_id": config_id,
                    "created_at_utc": self.now,
                    "created_by_command_id": self.request["command_id"],
                    "current_assignment_revision_id": state_id,
                    "change_version": 1,
                    "current_generation_id": generation_id,
                },
            )
            insert_record(
                self.db,
                "related_task_assignment_revisions",
                {
                    "assignment_revision_id": state_id,
                    "assignment_id": assignment_id,
                    "change_version": 1,
                    "prior_assignment_revision_id": None,
                    "state_json": state,
                    "state_hash": digest,
                    "selector_ref": reference,
                    **{
                        k: int(state[k]) if k in {"task_item_version", "source_item_version"} else state[k]
                        for k in (
                            "source_item_version",
                            "recurrence_revision_id",
                            "task_item_id",
                            "task_item_version",
                            "adopted_rule_revision_id",
                            "generation_id",
                            "temporal_binding_revision_id",
                            "proof_id",
                        )
                    },
                    "command_id": self.request["command_id"],
                    "created_at_utc": self.now,
                },
            )
            self.root["next_assignment_seq"] += 1
        else:
            from spine.services.recurring_task_states import append_state

            assert assignment is not None
            append_state(self.db, assignment, state, self.request, self.now)
        reserve_selector(
            self.db,
            rule_id=self.root["related_task_rule_id"],
            assignment_id=assignment_id,
            proof_id=proof_id,
            selector=selector,
            revision_id=self.snapshot["recurrence_revision_id"],
            budget=self.budget,
        )
        self.changed = self.owners = True
        self.mutations += 1
        after = references(self.db, read_record(self.db, "related_task_assignments", assignment_id))
        return entry(
            selector,
            "created" if first else "restored",
            state["reason"],
            assignment=assignment_id,
            generation=generation_id,
            actions=("assignment_created", "task_created") if first else ("task_restored",),
            before=before,
            after=after,
            proof_ids=(proof_id,),
        )


def reconcile(
    db: Any, request: dict[str, Any], root: dict[str, Any], context: Any, contracts: Any, now: str, runtime: dict[str, Any], fault: Any
) -> tuple[dict[str, Any], str, bool]:
    page = Page(db, context, root, request, contracts, now, runtime, fault)
    try:
        return _reconcile(page)
    finally:
        error = sys.exc_info()
        while page.units:
            page.units.pop()[0].__exit__(*error)


def _reconcile(page: Page) -> tuple[dict[str, Any], str, bool]:
    from spine.commands.recurring_tasks import intent_view, pending_adoption, success_response

    db, request, root = page.db, page.request, page.root
    context, contracts, now = page.context, page.contracts, page.now
    token = continuation(db, request, root, context, contracts, now)
    selected_intent = (
        intent_view(db, token["intent_id"])
        if token and "intent_id" in token
        else (pending_adoption(db, root["related_task_rule_id"]) or intent_view(db, root["retirement_intent_id"]))
    )
    evaluation = token["evaluation_at_utc"] if token else now
    start = token["range_start_utc"] if token else wire(instant(evaluation) - timedelta(seconds=max(0, int(page.config["offset_seconds"]))))
    end = token["range_end_utc"] if token else wire(instant(evaluation) + timedelta(seconds=int(page.config["generation_horizon_seconds"])))
    position: dict[str, Any] = copy.deepcopy(token["after"] if token else {"assignment_after_seq": "0", "source_after": None})
    page.position = position
    original = copy.deepcopy(position)
    assignments = db.execute(
        "SELECT assignment_id,assignment_seq FROM related_task_assignments WHERE related_task_rule_id=? "
        "AND assignment_seq>? ORDER BY assignment_seq LIMIT ?",
        (root["related_task_rule_id"], int(position["assignment_after_seq"]), page.limits["assignments"] + 1),
    ).fetchall()
    # The existing lane is intentionally completed before allocating any new child.
    # Each selected assignment is a whole unit, never a horizon-based omission.
    processed_assignments = 0
    for selected in assignments[: page.limits["assignments"]]:
        if page.mutations >= page.limits["mutations"]:
            break
        page.budget.hops = page.limits["lineage_hops"]
        assignment = read_record(db, "related_task_assignments", selected["assignment_id"])
        stored = read_record(db, "related_task_assignment_revisions", assignment["current_assignment_revision_id"])["state_json"]
        value = page.unit(partial(process_existing, page, assignment), stored["selector"], assignment=assignment)
        if value is None:
            break
        page.results.append(value)
        position["assignment_after_seq"] = str(selected["assignment_seq"])
        processed_assignments += 1
    existing_more = len(assignments) > processed_assignments
    source_more = False
    page.lane = "source"
    if root["status"] == "active":
        candidates = page.candidates(start, end)
        candidates = [
            value
            for value in candidates
            if db.execute(
                "SELECT 1 FROM related_task_selector_reservations WHERE related_task_rule_id=? AND occurrence_key=?",
                (root["related_task_rule_id"], value["occurrence_key"]),
            ).fetchone()
            is None
        ]
        if position["source_after"]:
            key = position["source_after"]
            candidates = [
                v
                for v in candidates
                if (v["original_scheduled_fact"], canonical_json_bytes(v["target_occurrence_selector"]))
                > (key["scheduled_fact"], canonical_json_bytes(key["selector"]))
            ]
        for index, occurrence in enumerate(candidates):
            if index >= page.limits["source_candidates"] or page.mutations >= page.limits["mutations"]:
                source_more = True
                break
            selector = occurrence["target_occurrence_selector"]
            reserved = db.execute(
                "SELECT assignment_id FROM related_task_selector_reservations WHERE related_task_rule_id=? AND occurrence_key=?",
                (root["related_task_rule_id"], occurrence["occurrence_key"]),
            ).fetchone()
            if reserved is None:
                try:
                    page.budget.hops = page.limits["lineage_hops"]
                    value = page.unit(partial(page.create, occurrence), selector)
                    if value is None:
                        source_more = True
                        break
                    page.results.append(value)
                except SpineValidationError as error:
                    if error.code != "source_continuity_unresolved":
                        raise
                    page.results.append(entry(selector, "decision_required", "source_continuity_unresolved"))
            position["source_after"] = {"scheduled_fact": selector["scheduled_fact"], "selector": selector}
    # Hold whole-unit savepoints until the *complete receipt* fits. Rolling back
    # a suffix never reruns accepted work, mints another ID or refunds proof work.
    while True:
        changed = page.changed
        try:
            with db.command_unit(nested=True):
                result, effect, _ = finish(
                    page, token, selected_intent, evaluation, start, end, original,
                    processed_assignments, existing_more, source_more,
                )
                response = success_response(
                    PREFIX + "reconcile",
                    request, result, effect, page.changed, now, page.runtime, dry_run=context.dry_run,
                )
                if len(canonical_json_bytes(response)) > page.limits["response_bytes"]:
                    raise _PageBoundary()
            return result, effect, page.changed
        except _PageBoundary:
            page.changed = changed
            if len(page.results) <= 1 or not page.units:
                fail("capacity_exceeded", "limits.response_bytes")
            lane = page.rollback_unit()
            if lane == "assignments":
                processed_assignments -= 1
                existing_more = True
            else:
                source_more = True


def finish(
    page: Page, token: dict[str, Any] | None, selected_intent: dict[str, Any] | None,
    evaluation: str, start: str, end: str, original: dict[str, Any],
    processed_assignments: int, existing_more: bool, source_more: bool,
) -> tuple[dict[str, Any], str, bool]:
    from spine.commands.recurring_tasks import advance_catalog, catalog, intent_view, pending_adoption, rule_view
    from spine.services.recurring_task_adoption import complete

    db, request, root = page.db, page.request, page.root
    context, contracts, now, position = page.context, page.contracts, page.now, page.position
    for intent in (pending_adoption(db, root["related_task_rule_id"]), intent_view(db, root["retirement_intent_id"])):
        if intent and intent["status"] == "pending":
            complete(page, intent)
    if page.changed:
        coverage_json = {
            "range_start_utc": start,
            "range_end_utc": end,
            "source_after": position["source_after"],
            "complete": not existing_more and not source_more and not any(v["outcome"] == "decision_required" for v in page.results),
        }
        progress = row(db, "related_task_rule_progress", root["related_task_rule_id"])
        pending = pending_adoption(db, root["related_task_rule_id"])
        values = {
            "source_scan_version": int(page.snapshot["source_item_version"]),
            "recurrence_revision_id": page.snapshot["recurrence_revision_id"],
            "coverage_json": coverage_json,
            "assignment_after_seq": int(position["assignment_after_seq"]),
            "pending_intent_id": pending["intent_id"] if pending else None,
        }
        if progress is None:
            insert_record(
                db, "related_task_rule_progress", {"related_task_rule_id": root["related_task_rule_id"], "progress_version": 0, **values}
            )
        else:
            compare_and_swap(db, "related_task_rule_progress", root["related_task_rule_id"], progress["progress_version"], values)
    if page.changed:
        compare_and_swap(
            db,
            "related_task_rules",
            root["related_task_rule_id"],
            root["change_version"],
            {"next_assignment_seq": root["next_assignment_seq"]},
        )
        root = read_record(db, "related_task_rules", root["related_task_rule_id"])
        advance_catalog(db)
    more, blocked = existing_more or source_more, any(v["outcome"] == "decision_required" for v in page.results)
    adoption = pending_adoption(db, root["related_task_rule_id"])
    intent = intent_view(db, selected_intent["intent_id"]) if selected_intent else None
    query = {
        "contract_version": CONTRACT,
        "ledger_instance_id": read_ledger_instance_id(db),
        "related_task_rule_id": root["related_task_rule_id"],
        "limits": request["limits"],
    }
    cursor = None
    if more:
        payload = cursor_payload(
            context.facet_cursor_config,
            purpose="reconcile",
            query=query,
            catalog=catalog(db),
            after=position,
            now=token["issued_at_utc"] if token else now,
        )
        payload.update(
            rule_change_version=str(root["change_version"]),
            rule_revision_id=root["current_revision_id"],
            source_item_id=page.snapshot["source_item_id"],
            recurrence_set_id=page.snapshot["recurrence_set_id"],
            **{k: page.snapshot[k] for k in ("source_item_version", "recurrence_revision_id", "normalized_recurrence_set_hash")},
            evaluation_at_utc=evaluation,
            range_start_utc=start,
            range_end_utc=end,
        )
        if intent:
            payload.update(intent_id=intent["intent_id"], assignment_high_water=intent["assignment_high_water"])
        cursor = sign_cursor(context.facet_cursor_config, payload, contracts)

    def coverage(status: str, count: int) -> dict[str, Any]:
        return {
            "status": status,
            "processed_count": str(count),
            "remaining_known_count": "0" if status in {"complete", "not_applicable"} else None,
        }

    unique_mappings = {(p["task_item_id"], p["policy_key"]): p for p in page.mappings}
    result = {
        "rule": rule_view(db, root),
        "source_snapshot": page.snapshot,
        "selection": {
            "evaluation_at_utc": evaluation,
            "execution_at_utc": now,
            "limits": request["limits"],
            "lane_start": original,
            "lane_end": position,
            "intent_id": intent["intent_id"] if intent else None,
            "assignment_high_water": intent["assignment_high_water"] if intent else None,
        },
        "results": page.results,
        "policy_mappings": [unique_mappings[key] for key in sorted(unique_mappings)],
        "work": {k: sorted(set(v)) for k, v in page.work.items()},
        "coverage": {
            "generation": coverage(
                "not_applicable"
                if root["status"] != "active"
                else "partial"
                if source_more
                else "decision_required"
                if blocked
                else "complete",
                len(page.results) - processed_assignments,
            ),
            "assignments": coverage(
                "partial" if existing_more else "decision_required" if blocked else "complete",
                processed_assignments,
            ),
            "adoption": coverage(
                "complete"
                if intent and intent["kind"] == "adopt" and intent["status"] == "complete"
                else "partial"
                if adoption
                else "not_applicable",
                processed_assignments if selected_intent and selected_intent["kind"] == "adopt" else 0,
            ),
            "retirement": coverage(
                "complete"
                if intent and intent["kind"] == "retire" and intent["status"] == "complete"
                else "partial"
                if intent and intent["kind"] == "retire"
                else "not_applicable",
                processed_assignments if selected_intent and selected_intent["kind"] == "retire" else 0,
            ),
        },
        "future_generation": "rule_retired"
        if root["status"] != "active"
        else "blocked"
        if blocked
        else "eligible"
        if source_more
        else "waiting",
        "has_more": more,
        "next_cursor": cursor,
        "delivery": "not_attempted_by_command",
    }
    return result, "rule_page_applied" if page.changed else "rule_page_decision_required" if blocked else "rule_page_noop", page.changed


def process_existing(page: Page, assignment: dict[str, Any]) -> dict[str, Any]:
    """Maintain an existing reservation independently of new-generation coverage."""
    from spine.commands import temporal_bindings as bindings
    from spine.commands.recurring_tasks import intent_view, pending_adoption
    from spine.ledger.temporal_bindings import load_temporal_binding
    from spine.services import recurring_task_adoption as adoption
    from spine.services.recurring_task_states import append_state

    db, request = page.db, page.request
    state = read_record(db, "related_task_assignment_revisions", assignment["current_assignment_revision_id"])["state_json"]
    state = copy.deepcopy(state)
    gen = read_record(db, "related_task_generations", assignment["current_generation_id"])
    config = read_record(db, "related_task_rule_revisions", state["adopted_rule_revision_id"])["configuration_json"]
    current = c._hydrated_item(db, gen["task_item_id"])
    binding: dict[str, Any] = load_temporal_binding(db, gen["temporal_binding_id"])
    prior = binding["latest_revision"]
    refs = references(db, assignment)
    original = copy.deepcopy(state)
    cause = row(db, "related_task_source_cancellations", gen["generation_id"])
    owned = refs["item_access_owner_id"] == gen["item_access_owner_id"] and refs["item_access_owner_revision"] == "1"
    retirement = intent_view(db, page.root["retirement_intent_id"])
    intent = pending_adoption(db, page.root["related_task_rule_id"])
    if intent and assignment["assignment_seq"] > int(intent["assignment_high_water"]):
        intent = None
    intent_result, intent_reason, adopting, managed = None, None, False, None
    reason, outcome, actions = "already_current", "retained", []
    source = bindings._source_from_prior(prior)
    source["target_occurrence_selector"] = state["selector"]
    source_only = (
        cause is not None
        and current["detail"]["task_status"] == "cancelled"
        and int(current["current_version"]) == cause["cancelled_task_version"]
    )
    # Terminal and manual independence always beat restoration, cleanup and following.
    if state["restoration_veto"]:
        outcome = "suppressed" if state["disposition"] == "suppressed" else "consumed"
        reason = state["reason"]
    elif current["detail"]["task_status"] == "done":
        state.update(disposition="done", restoration_veto=True)
        outcome, reason, actions = "consumed", "task_done", ["assignment_consumed", "veto_recorded"]
    elif current["detail"]["task_status"] == "cancelled" and not source_only:
        state.update(disposition="manual_cancelled", restoration_veto=True)
        outcome, reason, actions = "consumed", "task_manually_cancelled", ["assignment_consumed", "veto_recorded"]
    elif binding["binding_status"] != "active" and not source_only:
        state.update(disposition="detached", restoration_veto=True)
        outcome, reason, actions = "consumed", "binding_detached", ["assignment_consumed", "veto_recorded"]
    elif (
        db.execute("SELECT relation_status FROM coordination_item_relations WHERE relation_id=?", (gen["relationship_id"],)).fetchone()[0]
        != "active"
    ):
        state.update(disposition="detached", restoration_veto=True)
        outcome, reason, actions = "consumed", "relationship_inactive", ["assignment_consumed", "veto_recorded"]
    elif not owned:
        outcome, reason = "decision_required", "configuration_invalid"
    elif source_only and retirement and retirement["disposition"] == "keep_following":
        outcome, reason = "retained", "rule_retired_keep_following"
    elif retirement and retirement["disposition"] in {"cancel_open", "detach_open"}:
        reason = "rule_retired_cancel" if retirement["disposition"] == "cancel_open" else "rule_retired_detach"
        if current["detail"]["task_status"] == "open":
            change = children.change(
                page,
                assignment,
                gen,
                binding,
                current,
                source,
                config,
                cancel=retirement["disposition"] == "cancel_open",
                detach=retirement["disposition"] == "detach_open",
            )
            state.update(
                change, disposition="manual_cancelled" if retirement["disposition"] == "cancel_open" else "detached", restoration_veto=True
            )
            outcome = "cancelled" if retirement["disposition"] == "cancel_open" else "detached"
            actions = ["task_cancelled" if outcome == "cancelled" else "binding_retired", "veto_recorded"]
        else:
            outcome = "skipped_independent"
    elif page.source_item["status"] != "active":
        outcome, reason = "decision_required", "source_archived"
    else:
        try:
            if page.source_item["detail"]["event_status"] == "cancelled":
                kind, proof = (
                    "source_cancelled",
                    proofs.payload(page.snapshot, cancelled_event_version=page.snapshot["source_item_version"], event_status="cancelled"),
                )
                proof_id = proofs.persist(db, page.root, kind, proof, request, page.now, page.budget)
                cancel_reason = "source_cancelled"
                source["source_target_version"] = page.snapshot["source_item_version"]
            else:
                kind, proof = proofs.existing(db, page.root, page.snapshot, state, page.budget)
                selector = proof["selector"]
                exclusion = next(
                    (
                        v
                        for v in page.recurrence["exdates"]
                        if v["status"] == "active" and v["target_occurrence_key"] == proof["occurrence_key"]
                    ),
                    None,
                )
                cancelled = next(
                    (
                        v
                        for v in page.recurrence["overrides"]
                        if v["status"] == "active"
                        and v["target_occurrence_key"] == proof["occurrence_key"]
                        and v.get("lifecycle") == "cancelled"
                    ),
                    None,
                )
                occurrence = page.occurrence(selector)
                changed_source = (
                    state["source_item_version"] != page.snapshot["source_item_version"]
                    or state["recurrence_revision_id"] != page.snapshot["recurrence_revision_id"]
                    or state["selector"] != selector
                )
                proof_id = (
                    proofs.persist(db, page.root, kind, proof, request, page.now, page.budget)
                    if changed_source or exclusion or cancelled or source_only
                    else state["proof_id"]
                )
                reserve_selector(
                    db,
                    rule_id=page.root["related_task_rule_id"],
                    assignment_id=assignment["assignment_id"],
                    proof_id=proof_id,
                    selector=selector,
                    revision_id=page.snapshot["recurrence_revision_id"],
                    budget=page.budget,
                )
                state.update(selector=selector, occurrence_key=proof["occurrence_key"])
                cancel_reason = None
                if exclusion or cancelled:
                    cancel_reason = "source_excluded" if exclusion else "source_occurrence_cancelled"
                    kind = "excluded" if exclusion else "occurrence_cancelled"
                    value = proofs.payload(
                        page.snapshot,
                        selector,
                        prior_proof_id=proof_id,
                        prior_selector=selector,
                        **(
                            {"exdate_id": exclusion["exdate_id"], "exclusion_active": True}
                            if exclusion
                            else {
                                "override_id": cancelled["override_id"] if cancelled is not None else fail("environment_failure", "source"),
                                "lifecycle": "cancelled",
                            }
                        ),
                        actionable=False,
                    )
                    proof_id = proofs.persist(db, page.root, kind, value, request, page.now, page.budget)
                elif occurrence is None:
                    raise SpineValidationError("source_continuity_unresolved", "missing current expressed occurrence")
                else:
                    source = children.source_facts(
                        db, page.root, page.recurrence, occurrence, page.now, persist=True, command_id=request["command_id"]
                    )
            if cancel_reason:
                if current["detail"]["task_status"] == "open":
                    source.update(
                        source_recurrence_revision_id=page.snapshot["recurrence_revision_id"],
                        source_occurrence_key=state["occurrence_key"],
                        source_occurrence_selector_ref="recurrence_target_selector_" + hash_canonical_json(state["selector"]),
                        target_occurrence_selector=state["selector"],
                    )
                    state.update(children.change(page, assignment, gen, binding, current, source, config, cancel=True))
                    state.update(
                        disposition="source_cancelled",
                        reason=cancel_reason,
                        proof_id=proof_id,
                        source_item_version=page.snapshot["source_item_version"],
                        recurrence_revision_id=page.snapshot["recurrence_revision_id"],
                    )
                    outcome, reason, actions = "cancelled", cancel_reason, ["task_cancelled", "binding_retired"]
                else:
                    outcome, reason = "retained", state["reason"]
            elif source_only:
                if page.root["status"] == "retired":
                    outcome, reason = "retained", "rule_retired_keep_following"
                else:
                    assert occurrence is not None
                    from spine.services.recurring_task_restoration import prepare

                    restoration = prepare(page, assignment, gen, current, binding, config)
                    return page.create(
                        occurrence, assignment=assignment, config=restoration.configuration,
                        config_id=state["adopted_rule_revision_id"], proof_id=proof_id,
                        managed_baseline=state["managed_baseline"], restoration=restoration,
                    )
            else:
                target = target_from_source(source, int(prior["offset_seconds"]))
                moved = target["utc_instant"] != bindings._scheduled_for_target(current)["utc_instant"]
                if intent and (
                    state["adopted_rule_revision_id"] != intent["configuration_revision_id"]
                    or state.get("pending_intent_id") != intent["intent_id"]
                ):
                    desired = read_record(db, "related_task_rule_revisions", intent["configuration_revision_id"])["configuration_json"]
                    state["pending_intent_id"] = intent["intent_id"]
                    if bindings._scheduled_for_target(current)["utc_instant"] <= page.now:
                        intent_result, intent_reason = "skipped_overdue", "due_not_future"
                        outcome, reason, actions = "skipped_due", "due_not_future", ["intent_skipped"]
                        moved = False
                    else:
                        managed, conflict = adoption.comparison(page, assignment, gen, state, current, binding, desired)
                        if conflict:
                            intent_result, intent_reason = "conflict", "configuration_conflict"
                            outcome, reason = "decision_required", "configuration_conflict"
                            moved = False
                        else:
                            config = copy.deepcopy(desired)
                            if "offset_seconds" not in managed:
                                config["offset_seconds"] = prior["offset_seconds"]
                            target = target_from_source(source, int(config["offset_seconds"]))
                            if target["utc_instant"] <= page.now:
                                intent_result, intent_reason = "skipped_overdue", "due_not_future"
                                outcome, reason, actions = "skipped_due", "due_not_future", ["intent_skipped"]
                                moved = False
                            else:
                                adopting = True
                                page.runtime["cutoffs"].append(target["utc_instant"])
                                moved = target["utc_instant"] != bindings._scheduled_for_target(current)["utc_instant"]
                                state.update(
                                    adopted_rule_revision_id=intent["configuration_revision_id"], managed_baseline=baseline(desired)
                                )
                                intent_result, intent_reason = ("applied" if managed else "retained_equal"), "configuration_adopted"
                if outcome in {"decision_required", "skipped_due"}:
                    pass
                elif moved or changed_source or adopting or int(state["task_item_version"]) != int(current["current_version"]):
                    state.update(
                        children.change(
                            page, assignment, gen, binding, current, source, config, target=target if moved else None, managed=managed
                        )
                    )
                    state.update(
                        proof_id=proof_id,
                        source_item_version=page.snapshot["source_item_version"],
                        recurrence_revision_id=page.snapshot["recurrence_revision_id"],
                        disposition="governed",
                    )
                    outcome, reason = (
                        ("adopted", "configuration_adopted")
                        if adopting
                        else ("followed", "source_moved")
                        if moved
                        else ("refreshed", "source_refreshed")
                    )
                    actions = (["configuration_adopted"] if adopting else []) + (["task_rescheduled"] if moved else ["witness_refreshed"])
                else:
                    children.reconcile_work(page, gen["task_item_id"], int(current["current_version"]), config)
        except SpineValidationError as error:
            if error.code != "source_continuity_unresolved":
                raise
            outcome, reason = "decision_required", "source_continuity_unresolved"
    if outcome == "decision_required":
        state = copy.deepcopy(original)
        state.update(disposition="decision_required", reason=reason)
        if intent:
            state["pending_intent_id"] = intent["intent_id"]
    elif state != original:
        state["reason"] = reason
    # A manually advanced task needs an exact binding witness even for a terminal veto.
    if outcome != "decision_required" and int(state["task_item_version"]) < int(current["current_version"]):
        state.update(children.change(page, assignment, gen, binding, current, source, config))
    state_id = None
    if state != original:
        state_id = append_state(db, assignment, state, request, page.now)
        page.changed = True
    if intent:
        if intent_result is None and (state["restoration_veto"] or source_only):
            intent_result = "skipped_terminal" if current["detail"]["task_status"] != "open" else "skipped_independent"
            intent_reason = reason
            if state.get("pending_intent_id") != intent["intent_id"]:
                current_assignment = read_record(db, "related_task_assignments", assignment["assignment_id"])
                state["pending_intent_id"] = intent["intent_id"]
                state_id = append_state(db, current_assignment, state, request, page.now)
                page.changed = True
        if intent_result:
            adoption.outcome(
                page, intent, assignment, state_id or assignment["current_assignment_revision_id"], intent_result, intent_reason or reason
            )
    if retirement and assignment["assignment_seq"] <= int(retirement["assignment_high_water"]):
        adoption.outcome(
            page,
            retirement,
            assignment,
            state_id or assignment["current_assignment_revision_id"],
            "skipped_terminal"
            if current["detail"]["task_status"] != "open"
            else "applied"
            if outcome in {"cancelled", "detached"}
            else "retained_equal",
            reason,
        )
    if outcome == "cancelled" and reason in {"source_excluded", "source_occurrence_cancelled", "source_cancelled"} and cause is None:
        insert_record(
            db,
            "related_task_source_cancellations",
            {
                "generation_id": gen["generation_id"],
                "cancelled_task_version": int(state["task_item_version"]),
                "proof_id": state["proof_id"],
                "assignment_revision_id": state_id,
                "command_id": request["command_id"],
                "cancelled_at_utc": page.now,
            },
        )
    after = references(db, read_record(db, "related_task_assignments", assignment["assignment_id"]))
    page.mappings.extend(children.mappings(db, assignment["assignment_id"], gen, config))
    return entry(
        state["selector"],
        outcome,
        reason,
        assignment=assignment["assignment_id"],
        generation=gen["generation_id"],
        actions=tuple(actions),
        before=refs,
        after=after,
        proof_ids=(state["proof_id"],),
    )
