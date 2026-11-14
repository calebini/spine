"""Internal manual recurring-task reconciliation. No scheduler/public activation."""

from __future__ import annotations

import copy
import sys
from collections.abc import Callable, Sequence
from datetime import timedelta
from functools import partial
from typing import Any, Protocol

from spine.core import temporal_bindings as binding_facts
from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.core.recurring_task_runtime import cursor_payload, fail, instant, sign_cursor, verify_cursor, wire
from spine.core.recurring_tasks import CONTRACT, derive, occurrence_key, payload_hash
from spine.ledger import item_reads
from spine.ledger.identity import read_ledger_instance_id
from spine.ledger.recurring_task_sources import ProofBudget
from spine.ledger.recurring_tasks import compare_and_swap, ensure_selector, insert_record, read_record, reserve_selector, row
from spine.ledger.temporal_bindings import target_from_source
from spine.services import recurring_task_children as children
from spine.services import recurring_task_proofs as proofs
from spine.services.recurring_task_leads import validate_reminder_lead
from spine.services.recurring_task_operations import (
    ChangeChild,
    ChildDisposition,
    ChildInvocation,
    ChildWorkOverflow,
    CreateChild,
    LocalAuthority,
    RestoreChild,
    WorkEvidence,
)
from spine.services.recurring_task_page_state import PageBoundary as _PageBoundary
from spine.services.recurring_task_page_state import PageState
from spine.services.recurring_task_source_window import SourceWindow


class ResponseSizer(Protocol):
    """Command-owned canonical envelope sizing, with no persistence or dispatch."""

    def __call__(
        self, *, result: dict[str, Any], effect: str, changed: bool, audit_ids: Sequence[str]
    ) -> int: ...


def continuation(db: Any, request: dict[str, Any], root: dict[str, Any], context: Any, contracts: Any, now: str) -> dict[str, Any] | None:
    from spine.ledger.recurring_task_catalog import catalog, source_snapshot

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
        from spine.ledger.recurring_task_catalog import source_snapshot

        self.db, self.context, self.request, self.contracts, self.now = db, context, request, contracts, now
        self.state = PageState(root=root, runtime=runtime)
        self.fault = fault
        # The internal command adapter has already admitted trusted-local CLI
        # transport. Authority is selected here, never from client JSON.
        self.invocation = ChildInvocation(
            authority=LocalAuthority.TRUSTED_LOCAL, command_id=request["command_id"],
            actor_subject_id=request["actor_subject_id"], now=now,
            delivery_target_defaults=context.delivery_target_defaults, fault=fault,
        )
        self.snapshot = source_snapshot(db, root)
        dirty = db.execute("SELECT * FROM related_task_dirty_rules WHERE related_task_rule_id=?",
                           (root["related_task_rule_id"],)).fetchone()
        self.dirty = dict(dirty) if dirty is not None else None
        # Read-only evidence about the cursor's skipped source prefix. It is not
        # changed by retained-unit rollback or final receipt-sizing trials.
        self.source_prefix_unproved = False
        self.config = read_record(db, "related_task_rule_revisions", root["current_revision_id"])["configuration_json"]
        self.limits = {k: int(v) for k, v in request["limits"].items()}
        self.budget = ProofBudget(
            self.limits["proof_steps"],
            self.limits["lineage_hops"],
            lambda hop: fail("capacity_exceeded", "limits.lineage_hops" if hop else "limits.proof_steps"),
        )
        self.source_window = SourceWindow.load(db, root, self.config, self.snapshot, now, self.budget)
        self.recurrence = self.source_window.recurrence
        self.source_item = item_reads.hydrated_item(db, root["source_item_id"])

    def unit(self, operation: Callable[[], dict[str, Any]], selector: dict[str, Any], *,
             assignment: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Try a complete unit; a page boundary rolls back that unit and its trackers."""
        prior_work = sum(len(values) for values in self.state.work.values())
        unit_work = 0
        self.unit_oversized = False
        unit = self.state.begin_unit(self.db)
        try:
            before = self.db.total_changes
            value = operation()
            self.state.mutations = unit.checkpoint.mutations + int(self.db.total_changes != before)
            unit_work = sum(len(values) for values in self.state.work.values()) - prior_work
            if self.state.mutations > self.limits["mutations"]:
                fail("capacity_exceeded", "limits.mutations")
            if prior_work + unit_work > self.limits["work_rows"]:
                fail("capacity_exceeded", "limits.work_rows")
        except SpineValidationError as error:
            self.unit_oversized = self.unit_oversized or isinstance(error, ChildWorkOverflow)
            self.state.rollback(unit, sys.exc_info())
            # The caller still owns one outer transaction. Never restore SQL by
            # deleting history or clear trackers for already-accepted units.
            if (
                error.code == "capacity_exceeded:limits.work_rows"
                and self.state.results
                and not self.unit_oversized
                and unit_work <= self.limits["work_rows"]
            ):
                return None
            if error.code == "capacity_exceeded:limits.mutations" and self.state.results:
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
                # Persist only the blocked-state evidence after rolling back the
                # failed child operation. It remains a whole, budgeted unit and
                # is rolled back together with page state on a byte boundary.
                fallback = self.state.begin_unit(self.db)
                before = self.db.total_changes
                value = self.blocked(selector, assignment, reason)
                self.state.mutations = fallback.checkpoint.mutations + int(self.db.total_changes != before)
            else:
                raise
        except BaseException:
            self.state.rollback(unit, sys.exc_info())
            raise
        return value

    def blocked(self, selector: dict[str, Any], assignment: dict[str, Any] | None, reason: str) -> dict[str, Any]:
        from spine.ledger.recurring_task_catalog import intent_view
        from spine.services import recurring_task_adoption as adoption
        from spine.services.recurring_task_states import append_state

        if assignment is None:
            return entry(selector, "decision_required", reason)
        before = references(self.db, assignment)
        original = read_record(
            self.db, "related_task_assignment_revisions", assignment["current_assignment_revision_id"]
        )["state_json"]
        state = copy.deepcopy(original)
        state.update(disposition="decision_required", reason=reason)
        intent = adoption.selected(self.db, self.state.root["related_task_rule_id"], assignment, budget=self.budget)
        retirement = intent_view(self.db, self.state.root["retirement_intent_id"])
        if retirement and (retirement["status"] != "pending" or assignment["assignment_seq"] > int(retirement["assignment_high_water"])):
            retirement = None
        # Cancel/detach supersedes adoption; keep-following does not require a
        # child mutation and must not borrow the adoption's blocked outcome.
        cleanup = retirement if retirement and retirement["disposition"] != "keep_following" else None
        selected = intent or cleanup
        if selected:
            state["pending_intent_id"] = selected["intent_id"]
        state_id = assignment["current_assignment_revision_id"]
        if state != original:
            state_id = append_state(self.db, assignment, state, self.request, self.now)
            self.state.changed = True
        for pending in (intent, retirement):
            if pending:
                recorded = adoption.outcome(
                    self.db, self.invocation, pending, assignment["assignment_id"], state_id,
                    "retained_equal" if pending is retirement and cleanup is None else "conflict", reason,
                )
                self.state.changed = self.state.changed or recorded
        generation = read_record(self.db, "related_task_generations", assignment["current_generation_id"])
        config = read_record(self.db, "related_task_rule_revisions", original["adopted_rule_revision_id"])["configuration_json"]
        self.state.mappings.extend(children.mappings(self.db, assignment["assignment_id"], generation, config))
        return entry(
            selector, "decision_required", reason, assignment=assignment["assignment_id"], generation=generation["generation_id"],
            before=before, after=references(self.db, read_record(self.db, "related_task_assignments", assignment["assignment_id"])),
        )

    def apply_work(self, work: WorkEvidence) -> None:
        for kind in ("created", "cancelled", "retained", "protected_stale"):
            self.state.work[kind].extend(getattr(work, kind))
        self.state.changed = self.state.changed or work.changed

    def change(
        self, assignment: dict[str, Any], generation: dict[str, Any], binding: dict[str, Any],
        current: dict[str, Any], source: dict[str, Any], config: dict[str, Any], *,
        target: dict[str, Any] | None = None, disposition: ChildDisposition = ChildDisposition.FOLLOW,
        managed: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        result = children.change(self.db, self.invocation, ChangeChild(
            assignment_id=assignment["assignment_id"], generation=generation, binding=binding,
            current=current, source=source, configuration=config, work_limit=self.limits["work_rows"],
            target=target, disposition=disposition, managed=managed,
        ))
        self.apply_work(result.work)
        self.state.runtime["audit_ids"].extend(result.audit_ids)
        self.state.mappings.extend(result.policy_mappings)
        self.state.changed = True
        self.state.mutations += 1
        return {"task_item_version": result.task_item_version,
                "temporal_binding_revision_id": result.temporal_binding_revision_id}

    def expand(self, start: str, end: str, *, basis: str) -> list[dict[str, Any]]:
        return self.source_window.expand(start, end, basis=basis)

    def occurrence(self, selector: dict[str, Any]) -> dict[str, Any] | None:
        return self.source_window.occurrence(selector)

    def candidates(self, start: str, end: str) -> list[dict[str, Any]]:
        return self.source_window.candidates(start, end)

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
        config, config_id = config or self.config, config_id or self.state.root["current_revision_id"]
        birth: tuple[str, dict[str, Any]] | None = None
        selector = occurrence["target_occurrence_selector"]
        source = children.source_facts(
            self.db, self.state.root, self.recurrence, occurrence, self.now, persist=False, command_id=self.request["command_id"]
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
        if assignment is None:
            # A source revision may change timezone after rule admission. Never
            # create a newly selected task using a now-insufficient lead proof.
            # Existing-task maintenance/restoration does not depend on a rolling
            # generation horizon, and must not be blocked by this admission check.
            try:
                validate_reminder_lead(config, self.recurrence)
            except SpineValidationError as exc:
                if exc.code.startswith("semantic_conflict:configuration."):
                    return entry(selector, "decision_required", "configuration_invalid")
                raise
        if proof_id is None:
            kind, proof = proofs.initial(self.db, self.state.root, self.snapshot, selector, self.budget)
            if kind == "component_candidate":
                basis_selector = proof["hops"][0]["prior_selector"] if proof["hops"] else selector
                reserved = self.db.execute(
                    "SELECT assignment_id,occurrence_key FROM related_task_selector_reservations "
                    "WHERE related_task_rule_id=? AND occurrence_key=?",
                    (self.state.root["related_task_rule_id"], occurrence_key(basis_selector)),
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
            proof_id = proofs.persist(self.db, self.state.root, kind, proof, self.request, self.now, self.budget)
            if proof["recurrence_revision_id"] != self.snapshot["recurrence_revision_id"]:
                birth = (proof_id, proof)
                # A delayed addition first proves its historical birth. Its
                # current membership must then have an independently verified
                # copy chain, inside this same whole-unit savepoint.
                path = proofs.hops(self.db, proof["recurrence_revision_id"], self.snapshot["recurrence_revision_id"],
                                   proof["selector"], self.budget)
                if not path or path[-1]["selector"] != selector:
                    fail("source_continuity_unresolved", "source")
                carried = proofs.payload(self.snapshot, selector, prior_proof_id=proof_id, prior_selector=proof["selector"],
                                         hops=path, lineage_ids=sorted({line for hop in path for line in hop["lineage_ids"]}))
                proof_id = proofs.persist(self.db, self.state.root, "carry_forward", carried, self.request, self.now, self.budget)
        reference = ensure_selector(self.db, revision_id=self.snapshot["recurrence_revision_id"], selector=selector, budget=self.budget)
        first = assignment is None
        assignment_id = (
            assignment["assignment_id"]
            if assignment
            else derive("assignment", {"related_task_rule_id": self.state.root["related_task_rule_id"], "initial_selector": selector})[0]
        )
        prior = read_record(self.db, "related_task_generations", assignment["current_generation_id"]) if assignment is not None else None
        index = prior["generation_index"] + 1 if prior is not None else 1
        generation_id = derive("generation", {"assignment_id": assignment_id, "generation_index": str(index)})[0]
        source = children.source_facts(
            self.db, self.state.root, self.recurrence, occurrence, self.now, persist=True, command_id=self.request["command_id"]
        )
        creation = CreateChild(
            source_item_id=self.state.root["source_item_id"], configuration=config,
            assignment_id=assignment_id, generation_id=generation_id, source=source,
            work_limit=self.limits["work_rows"],
        )
        child = (
            children.create(self.db, self.invocation, creation)
            if restoration is None
            else children.restore(self.db, self.invocation, RestoreChild(creation=creation, predecessor=restoration))
        )
        self.state.runtime["cutoffs"].append(due)
        self.state.runtime["audit_ids"].append(child["audit_id"])
        self.state.work["created"].extend(child["work"])
        self.state.mappings.extend(child["policy_mappings"])
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
        if assignment is not None:
            predecessor_state = read_record(
                self.db, "related_task_assignment_revisions", assignment["current_assignment_revision_id"]
            )["state_json"]
            if "pending_intent_id" in predecessor_state:
                state["pending_intent_id"] = predecessor_state["pending_intent_id"]
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
                    "related_task_rule_id": self.state.root["related_task_rule_id"],
                    "assignment_seq": self.state.root["next_assignment_seq"],
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
            self.state.root["next_assignment_seq"] += 1
        else:
            from spine.services.recurring_task_states import append_state

            assert assignment is not None
            append_state(self.db, assignment, state, self.request, self.now)
        if birth is not None:
            # Reserve the positively proved original alias for this assignment
            # too. When unchanged, the first reservation keeps the birth proof;
            # state/generation still pin the fully verified current proof.
            reserve_selector(self.db, rule_id=self.state.root["related_task_rule_id"], assignment_id=assignment_id,
                             proof_id=birth[0], selector=birth[1]["selector"],
                             revision_id=birth[1]["recurrence_revision_id"], budget=self.budget)
        reserve_selector(
            self.db,
            rule_id=self.state.root["related_task_rule_id"],
            assignment_id=assignment_id,
            proof_id=proof_id,
            selector=selector,
            revision_id=self.snapshot["recurrence_revision_id"],
            budget=self.budget,
        )
        self.state.changed = self.state.owners = True
        self.state.mutations += 1
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
    db: Any, request: dict[str, Any], root: dict[str, Any], context: Any, contracts: Any, now: str, runtime: dict[str, Any], fault: Any,
    *, response_size: ResponseSizer,
) -> tuple[dict[str, Any], str, bool]:
    page = Page(db, context, root, request, contracts, now, runtime, fault)
    try:
        return _reconcile(page, response_size=response_size)
    finally:
        page.state.close(sys.exc_info())


def _reconcile(page: Page, *, response_size: ResponseSizer) -> tuple[dict[str, Any], str, bool]:
    from spine.ledger.recurring_task_catalog import intent_view, pending_adoption

    db, request, root = page.db, page.request, page.state.root
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
    page.state.position = position
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
        if page.state.mutations >= page.limits["mutations"]:
            break
        page.budget.hops = page.limits["lineage_hops"]
        assignment = read_record(db, "related_task_assignments", selected["assignment_id"])
        stored = read_record(db, "related_task_assignment_revisions", assignment["current_assignment_revision_id"])["state_json"]
        value = page.unit(partial(process_existing, page, assignment), stored["selector"], assignment=assignment)
        if value is None:
            break
        page.state.results.append(value)
        position["assignment_after_seq"] = str(selected["assignment_seq"])
        processed_assignments += 1
    existing_more = len(assignments) > processed_assignments
    source_more = False
    page.state.lane = "source"
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
            cursor_key = (key["scheduled_fact"], canonical_json_bytes(key["selector"]))
            # A prior page may have returned decision_required without reserving
            # the slot. A cursor is not proof that such a slot was discharged.
            for value in candidates:
                if (value["original_scheduled_fact"], canonical_json_bytes(value["target_occurrence_selector"])) > cursor_key:
                    break
                source = children.source_facts(db, root, page.recurrence, value, now,
                                               persist=False, command_id=request["command_id"])
                if target_from_source(source, int(page.config["offset_seconds"]))["utc_instant"] > now:
                    page.source_prefix_unproved = True
                    break
            candidates = [
                v
                for v in candidates
                if (v["original_scheduled_fact"], canonical_json_bytes(v["target_occurrence_selector"]))
                > (key["scheduled_fact"], canonical_json_bytes(key["selector"]))
            ]
        for index, occurrence in enumerate(candidates):
            if index >= page.limits["source_candidates"] or page.state.mutations >= page.limits["mutations"]:
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
                    page.state.results.append(value)
                except SpineValidationError as error:
                    if error.code != "source_continuity_unresolved":
                        raise
                    page.state.results.append(entry(selector, "decision_required", "source_continuity_unresolved"))
            position["source_after"] = {"scheduled_fact": selector["scheduled_fact"], "selector": selector}
    # Hold whole-unit savepoints until the *complete receipt* fits. Rolling back
    # a suffix never reruns accepted work, mints another ID or refunds proof work.
    while True:
        try:
            with page.state.trial(db):
                result, effect, _ = finish(
                    page, token, selected_intent, evaluation, start, end, original,
                    processed_assignments, existing_more, source_more,
                )
                if response_size(
                    result=result, effect=effect, changed=page.state.changed, audit_ids=tuple(page.state.runtime["audit_ids"]),
                ) > page.limits["response_bytes"]:
                    raise _PageBoundary()
            return result, effect, page.state.changed
        except _PageBoundary:
            if len(page.state.results) <= 1 or not page.state.has_units:
                fail("capacity_exceeded", "limits.response_bytes")
            lane = page.state.rollback_last()
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
    from spine.ledger.recurring_task_catalog import advance_catalog, catalog, intent_view, pending_adoption, rule_view
    from spine.services.recurring_task_acknowledgement import acknowledge_page
    from spine.services.recurring_task_adoption import complete, coverage_status
    from spine.services.recurring_task_horizon import source_exhausted

    db, request, root = page.db, page.request, page.state.root
    context, contracts, now, position = page.context, page.contracts, page.now, page.state.position
    for intent in (pending_adoption(db, root["related_task_rule_id"]), intent_view(db, root["retirement_intent_id"])):
        if intent and intent["status"] == "pending":
            completed = complete(
                db, page.invocation, rule_id=page.state.root["related_task_rule_id"], budget=page.budget, intent=intent,
            )
            page.state.changed = page.state.changed or completed
    acknowledged = acknowledge_page(
        db, root["related_task_rule_id"], page.dirty, original=original, position=position,
        results=page.state.results, processed_assignments=processed_assignments,
        existing_more=existing_more, source_more=source_more,
        source_prefix_unproved=page.source_prefix_unproved,
    )
    page.state.changed = page.state.changed or acknowledged
    if page.state.changed:
        coverage_json = {
            "range_start_utc": start,
            "range_end_utc": end,
            "source_after": position["source_after"],
            "complete": not existing_more and not source_more and not any(v["outcome"] == "decision_required" for v in page.state.results),
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
    if page.state.changed:
        compare_and_swap(
            db,
            "related_task_rules",
            root["related_task_rule_id"],
            root["change_version"],
            {"next_assignment_seq": root["next_assignment_seq"]},
        )
        root = read_record(db, "related_task_rules", root["related_task_rule_id"])
        advance_catalog(db)
    more, blocked = existing_more or source_more, any(v["outcome"] == "decision_required" for v in page.state.results)
    adoption = pending_adoption(db, root["related_task_rule_id"])
    intent = intent_view(db, selected_intent["intent_id"]) if selected_intent else None
    adoption_coverage = intent if intent and intent["kind"] == "adopt" else adoption
    retirement_coverage = intent_view(db, root["retirement_intent_id"])
    assignment_blocked = any(v["outcome"] == "decision_required" for v in page.state.results[:processed_assignments])
    generation_blocked = any(v["outcome"] == "decision_required" for v in page.state.results[processed_assignments:])
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

    def intent_coverage(selected: dict[str, Any] | None) -> dict[str, Any]:
        # Assignment sequences are gapless immutable reservations. Intersect the
        # retained page's existing lane with this intent's finite high water; new
        # source allocations and assignments above it are not adoption work.
        high_water = int(selected["assignment_high_water"]) if selected else 0
        count = min(int(position["assignment_after_seq"]), high_water) - min(int(original["assignment_after_seq"]), high_water)
        return coverage(coverage_status(db, root["related_task_rule_id"], selected), count)

    unique_mappings = {(p["task_item_id"], p["policy_key"]): p for p in page.state.mappings}
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
        "results": page.state.results,
        "policy_mappings": [unique_mappings[key] for key in sorted(unique_mappings)],
        "work": {k: sorted(set(v)) for k, v in page.state.work.items()},
        "coverage": {
            "generation": coverage(
                "not_applicable"
                if root["status"] != "active"
                else "partial"
                if source_more
                else "decision_required"
                if generation_blocked
                else "complete",
                len(page.state.results) - processed_assignments,
            ),
            "assignments": coverage(
                "partial" if existing_more else "decision_required" if assignment_blocked else "complete",
                processed_assignments,
            ),
            "adoption": intent_coverage(adoption_coverage),
            "retirement": intent_coverage(retirement_coverage),
        },
        "future_generation": "rule_retired"
        if root["status"] != "active"
        else "blocked"
        if blocked
        else "eligible"
        if source_more
        else "source_exhausted"
        if not more and source_exhausted(page.recurrence, evaluation, page.budget)
        else "waiting",
        "has_more": more,
        "next_cursor": cursor,
        "delivery": "not_attempted_by_command",
    }
    effect = "rule_page_applied" if page.state.changed else "rule_page_decision_required" if blocked else "rule_page_noop"
    return result, effect, page.state.changed


def process_existing(page: Page, assignment: dict[str, Any]) -> dict[str, Any]:
    """Maintain an existing reservation independently of new-generation coverage."""
    from spine.ledger.recurring_task_catalog import intent_view
    from spine.ledger.temporal_bindings import load_temporal_binding
    from spine.services import recurring_task_adoption as adoption
    from spine.services.recurring_task_states import append_state

    db, request = page.db, page.request
    state = read_record(db, "related_task_assignment_revisions", assignment["current_assignment_revision_id"])["state_json"]
    state = copy.deepcopy(state)
    gen = read_record(db, "related_task_generations", assignment["current_generation_id"])
    config = read_record(db, "related_task_rule_revisions", state["adopted_rule_revision_id"])["configuration_json"]
    current = item_reads.hydrated_item(db, gen["task_item_id"])
    binding: dict[str, Any] = load_temporal_binding(db, gen["temporal_binding_id"])
    prior = binding["latest_revision"]
    refs = references(db, assignment)
    original = copy.deepcopy(state)
    cause = row(db, "related_task_source_cancellations", gen["generation_id"])
    owned = refs["item_access_owner_id"] == gen["item_access_owner_id"] and refs["item_access_owner_revision"] == "1"
    retirement = intent_view(db, page.state.root["retirement_intent_id"])
    intent = adoption.selected(db, page.state.root["related_task_rule_id"], assignment, budget=page.budget)
    intent_result, intent_reason, adopting, managed = None, None, False, None
    reason, outcome, actions = "already_current", "retained", []
    source = binding_facts.source_from_prior(prior)
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
            change = page.change(
                assignment,
                gen,
                binding,
                current,
                source,
                config,
                disposition=ChildDisposition.CANCEL if retirement["disposition"] == "cancel_open" else ChildDisposition.DETACH,
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
                proof_id = proofs.persist(db, page.state.root, kind, proof, request, page.now, page.budget)
                cancel_reason = "source_cancelled"
                source["source_target_version"] = page.snapshot["source_item_version"]
            else:
                kind, proof = proofs.existing(db, page.state.root, page.snapshot, state, page.budget)
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
                    proofs.persist(db, page.state.root, kind, proof, request, page.now, page.budget)
                    if changed_source or exclusion or cancelled or source_only
                    else state["proof_id"]
                )
                reserve_selector(
                    db,
                    rule_id=page.state.root["related_task_rule_id"],
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
                    proof_id = proofs.persist(db, page.state.root, kind, value, request, page.now, page.budget)
                elif occurrence is None:
                    raise SpineValidationError("source_continuity_unresolved", "missing current expressed occurrence")
                else:
                    source = children.source_facts(
                        db, page.state.root, page.recurrence, occurrence, page.now, persist=True, command_id=request["command_id"]
                    )
            if cancel_reason:
                if current["detail"]["task_status"] == "open":
                    source.update(
                        source_recurrence_revision_id=page.snapshot["recurrence_revision_id"],
                        source_occurrence_key=state["occurrence_key"],
                        source_occurrence_selector_ref="recurrence_target_selector_" + hash_canonical_json(state["selector"]),
                        target_occurrence_selector=state["selector"],
                    )
                    state.update(page.change( assignment, gen, binding, current, source, config, disposition=ChildDisposition.CANCEL))
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
                if page.state.root["status"] == "retired":
                    outcome, reason = "retained", "rule_retired_keep_following"
                else:
                    assert occurrence is not None
                    from spine.services.recurring_task_restoration import prepare

                    restoration = prepare(
                        db, command_id=page.request["command_id"], budget=page.budget, assignment_id=assignment["assignment_id"],
                        generation=gen, current=current, binding=binding, config=config,
                    )
                    restored = page.create(
                        occurrence, assignment=assignment, config=restoration.configuration,
                        config_id=state["adopted_rule_revision_id"], proof_id=proof_id,
                        managed_baseline=state["managed_baseline"], restoration=restoration,
                    )
                    if intent:
                        # This page selected a cancelled predecessor, outside
                        # upcoming-open adoption. Restoration copies its choices;
                        # it is not implicit consent to the pending new template.
                        latest = read_record(db, "related_task_assignments", assignment["assignment_id"])
                        retained = read_record(
                            db, "related_task_assignment_revisions", latest["current_assignment_revision_id"]
                        )["state_json"]
                        retained["pending_intent_id"] = intent["intent_id"]
                        retained_id = append_state(db, latest, retained, request, page.now)
                        adoption.outcome(db, page.invocation, intent, assignment["assignment_id"], retained_id,
                                         "skipped_terminal", original["reason"])
                        page.state.changed = True
                        restored["after"] = references(db, read_record(db, "related_task_assignments", assignment["assignment_id"]))
                        restored["actions"] = sorted(set(restored["actions"]) | {"intent_skipped"})
                    return restored
            else:
                target = target_from_source(source, int(prior["offset_seconds"]))
                moved = target["utc_instant"] != binding_facts.scheduled_for_target(current)["utc_instant"]
                if intent and (
                    state["adopted_rule_revision_id"] != intent["configuration_revision_id"]
                    or state.get("pending_intent_id") != intent["intent_id"]
                ):
                    desired = read_record(db, "related_task_rule_revisions", intent["configuration_revision_id"])["configuration_json"]
                    state["pending_intent_id"] = intent["intent_id"]
                    if binding_facts.scheduled_for_target(current)["utc_instant"] <= page.now:
                        intent_result, intent_reason = "skipped_overdue", "due_not_future"
                        outcome, reason, actions = "skipped_due", "due_not_future", ["intent_skipped"]
                        moved = False
                    else:
                        managed, conflict = adoption.comparison(db, gen, state, current, binding, desired)
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
                                page.state.runtime["cutoffs"].append(target["utc_instant"])
                                moved = target["utc_instant"] != binding_facts.scheduled_for_target(current)["utc_instant"]
                                state.update(
                                    adopted_rule_revision_id=intent["configuration_revision_id"], managed_baseline=baseline(desired)
                                )
                                intent_result, intent_reason = ("applied" if managed else "retained_equal"), "configuration_adopted"
                if outcome in {"decision_required", "skipped_due"}:
                    pass
                elif moved or changed_source or adopting or int(state["task_item_version"]) != int(current["current_version"]):
                    state.update(
                        page.change( assignment, gen, binding, current, source, config, target=target if moved else None, managed=managed
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
                    page.apply_work(children.reconcile_work(
                        db, page.invocation, gen["task_item_id"], int(current["current_version"]), config,
                        work_limit=page.limits["work_rows"],
                    ))
        except SpineValidationError as error:
            if error.code != "source_continuity_unresolved":
                raise
            outcome, reason = "decision_required", "source_continuity_unresolved"
    if outcome == "decision_required":
        state = copy.deepcopy(original)
        state.update(disposition="decision_required", reason=reason)
        if intent:
            state["pending_intent_id"] = intent["intent_id"]
    elif intent_result == "skipped_overdue":
        state.update(disposition="governed", reason=reason)
    elif state != original:
        state["reason"] = reason
    if intent:
        if intent_result is None and outcome == "decision_required":
            intent_result, intent_reason = "conflict", reason
        elif intent_result is None and (state["restoration_veto"] or state["disposition"] == "source_cancelled" or source_only):
            terminal = current["detail"]["task_status"] != "open" or state["disposition"] == "source_cancelled"
            intent_result, intent_reason = ("skipped_terminal" if terminal else "skipped_independent"), reason
        if intent_result:
            state["pending_intent_id"] = intent["intent_id"]
    retirement_selected = retirement is not None and assignment["assignment_seq"] <= int(retirement["assignment_high_water"])
    if retirement is not None and retirement_selected and retirement["disposition"] != "keep_following":
        state["pending_intent_id"] = retirement["intent_id"]
    # A manually advanced task needs an exact binding witness even for a terminal veto.
    if outcome != "decision_required" and int(state["task_item_version"]) < int(current["current_version"]):
        state.update(page.change( assignment, gen, binding, current, source, config))
    state_id = None
    if state != original:
        state_id = append_state(db, assignment, state, request, page.now)
        page.state.changed = True
    if intent and intent_result:
        recorded = adoption.outcome(
            db, page.invocation, intent, assignment["assignment_id"],
            state_id or assignment["current_assignment_revision_id"], intent_result, intent_reason or reason
        )
        page.state.changed = page.state.changed or recorded
    if retirement is not None and retirement_selected:
        recorded = adoption.outcome(
            db, page.invocation,
            retirement,
            assignment["assignment_id"],
            state_id or assignment["current_assignment_revision_id"],
            "conflict"
            if outcome == "decision_required" and retirement["disposition"] != "keep_following"
            else "skipped_terminal"
            if current["detail"]["task_status"] != "open"
            else "applied"
            if outcome in {"cancelled", "detached"}
            else "retained_equal",
            reason,
        )
        page.state.changed = page.state.changed or recorded
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
    page.state.mappings.extend(children.mappings(db, assignment["assignment_id"], gen, config))
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
