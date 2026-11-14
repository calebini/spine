"""Read-only semantic observation of one exact recurring reconcile request.

Shares the writer's selection order and lifecycle precedence. Stop before each
effect, not after a dry run: no children, reservations, provenance or receipts
are provisionally written. The normal writer still owns all final validation.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.core.notification_targets import target_from_anchor
from spine.core.recurring_task_runtime import fail
from spine.core.recurring_tasks import derive, occurrence_key
from spine.ledger import schedule_work
from spine.ledger.identity import read_ledger_instance_id
from spine.ledger.recurring_task_catalog import catalog, intent_view, pending_adoption
from spine.ledger.recurring_task_sources import require_candidate, verify_planned_proof
from spine.ledger.recurring_tasks import read_record, row, validate_selector
from spine.ledger.temporal_bindings import target_from_source
from spine.ledger.transactions import LedgerConnection
from spine.services import recurring_task_children as children
from spine.services import rendering_authoring, schedule_delivery, schedule_materialization
from spine.services.recurring_task_acknowledgement import coverage_action
from spine.services.recurring_task_adoption import can_complete
from spine.services.recurring_task_operations import ChildDisposition, ChildWorkOverflow
from spine.services.recurring_task_reconcile import Page, blocked_reason, continuation, page_bounds, select_units
from spine.services.recurring_task_restoration import Restoration, pinned_selection, restored_policy, restored_policy_inputs


@dataclass(frozen=True)
class Unit:
    identity: str
    action: str
    changed: bool
    evidence: str
    reason: str | None


@dataclass(frozen=True)
class PagePlan:
    ledger_id: str
    observed_at: str = field(compare=False)
    request_hash: str
    catalog_generation: str
    units: tuple[Unit, ...]
    progress: tuple[str, ...]
    has_more: bool

    @property
    def dispatchable(self) -> bool:
        return bool(self.progress) or any(unit.changed for unit in self.units)


class _Effect(Exception):
    def __init__(self, action: str, evidence: object):
        self.action, self.evidence = action, evidence


@contextmanager
def read_only(db: LedgerConnection) -> Iterator[None]:
    """Also protect the observation phase inside BEGIN IMMEDIATE."""
    prior = db.execute("PRAGMA query_only").fetchone()[0]
    if not prior:
        db.execute("PRAGMA query_only=ON")
    try:
        yield
    finally:
        if not prior:
            db.execute("PRAGMA query_only=OFF")


class _Observer(Page):
    observations: list[Unit]
    proofs: dict[str, dict[str, Any]]
    aliases: dict[str, str]
    unit_aliases: dict[str, str]
    observed_work_rows: int
    unit_work_rows: int

    def unit(self, operation: Callable[[], dict[str, Any]], selector: dict[str, Any], *,
             assignment: dict[str, Any] | None = None) -> dict[str, Any] | None:
        identity = assignment["assignment_id"] if assignment else occurrence_key(selector)
        changed = False
        self.proofs = {}
        self.unit_aliases = {}
        self.unit_work_rows = 0
        reason = None
        try:
            try:
                result = operation()
            except SpineValidationError as exc:
                reason = blocked_reason(exc)
                if reason is None:
                    raise
                self.unit_aliases.clear()
                result = self.blocked(selector, assignment, reason)
            action, evidence = result["outcome"], result["reason"]
            reason = result["reason"]
        except _Effect as found:
            action, evidence, changed = found.action, found.evidence, True
            if isinstance(evidence, dict) and "reason" in evidence:
                reason = evidence["reason"]
        if self.unit_work_rows > self.limits["work_rows"]:
            raise ChildWorkOverflow()
        if self.observed_work_rows + self.unit_work_rows > self.limits["work_rows"]:
            return None
        self.observed_work_rows += self.unit_work_rows
        self.aliases.update(self.unit_aliases)
        self.observations.append(Unit(identity, action, changed, hash_canonical_json({
            "evidence": evidence, "assignment_revision": assignment["current_assignment_revision_id"] if assignment else None,
            "generation": assignment["current_generation_id"] if assignment else None,
        }), reason))
        self.state.mutations += int(changed)
        return {"outcome": action}

    def proof(self, kind: str, value: dict[str, Any]) -> str:
        verify_planned_proof(self.db, self.state.root, kind, value, self.budget, predecessors=self.proofs,
                             verified_reservations=frozenset(self.unit_aliases))
        identity = derive("proof", {"related_task_rule_id": self.state.root["related_task_rule_id"],
                                    "proof_kind": kind, "proof_payload": value})[0]
        self.proofs[identity] = value
        return identity

    def reserve(self, assignment: dict[str, Any], proof_id: str, selector: dict[str, Any]) -> None:
        key = occurrence_key(selector)
        require_candidate(self.db, self.snapshot["recurrence_revision_id"], selector, self.budget)
        prior = self.db.execute("SELECT assignment_id FROM related_task_selector_reservations "
                                "WHERE related_task_rule_id=? AND occurrence_key=?",
                                (self.state.root["related_task_rule_id"], key)).fetchone()
        if prior:
            validate_selector(self.db, "recurrence_target_selector_" + hash_canonical_json(selector), selector, key,
                              selector["recurrence_set_id"])
        owner = assignment["assignment_id"]
        if (prior and prior[0] != owner) or self.aliases.get(key, owner) != owner:
            raise SpineValidationError("source_continuity_unresolved", "reserved by another assignment")
        if not prior:
            self.unit_aliases[key] = assignment["assignment_id"]

    def reserved(self, key: str) -> bool:
        return key in self.aliases or super().reserved(key)

    def current_source(self, occurrence: dict[str, Any]) -> dict[str, Any]:
        return children.source_facts(self.db, self.source_item, self.recurrence, occurrence, self.now,
                                     persist=False, command_id=self.request["command_id"])

    def before_creation(self, config: dict[str, Any], source: dict[str, Any], generation_id: str, restoration: Restoration | None) -> None:
        children.check_creation_references(self.db, config)
        task_id = children.child_id(generation_id, "item", "/task")
        normalized = []
        if restoration is None:
            route = self.check_delivery(config)
            if route:
                normalized = [dict(p.value) for _, p in children.configured_policies(config, route, task_id, generation_id, self.now)]
        else:
            for policy in restoration.current["notification_policies"]:
                if policy["status"] == "active":
                    restored_route, selection, origin = restored_policy_inputs(self.db, policy, self.context.delivery_target_defaults)
                    rendering_authoring.resolve(self.db, selection, policy={**restored_route, "item_id": None},  # type: ignore[no-untyped-call]
                                                item_type="task", origin=origin, prospective_owner=config["task_owner"])
                    normalized.append(dict(restored_policy(policy, restored_route, generation_id=generation_id, task_id=task_id,
                        key=restoration.family_keys.get(policy["notification_intent_id"]), now=self.now).value))
        target = target_from_source(source, int(config["offset_seconds"]))
        work_ids = []
        bounds = children.materialization(config, self.now, policies=normalized)
        if normalized and bounds["mode"] != "none":
            anchor = target_from_anchor({**target, "anchor_kind": "local_instant"})
            targets = {str(p["notification_intent_id"]): [anchor] for p in normalized}
            work_ids = [schedule_materialization.opportunity_work_id(o)
                        for o in schedule_materialization.actionable_opportunities(normalized, targets, bounds)]
        self.unit_work_rows = len(work_ids)
        raise _Effect("restore" if restoration else "create", {"due": target["utc_instant"], "generation": generation_id, "work": work_ids})

    def check_delivery(self, config: dict[str, Any]) -> schedule_delivery.ResolvedDelivery | None:
        if config["notification_plan"] is None:
            return None
        route = schedule_delivery.resolve_delivery(config["delivery"]["requested"], ledger=self.db,
                                                   defaults=self.context.delivery_target_defaults)
        if {k: v for k, v in route["snapshot"].items() if k != "delivery_state"} != config["delivery"]["resolved"]:
            fail("semantic_conflict", "configuration.delivery")
        for e in config["notification_plan"]["resolved"]["effective_templates"]:
            presentation = e["presentation"]
            if presentation["kind"] != "ordinary":
                rendering_authoring.resolve(self.db, pinned_selection(presentation),  # type: ignore[no-untyped-call]
                    policy={**route, "item_id": None}, item_type="task", origin=presentation["origin"],
                    prospective_owner=config["task_owner"])
        return route

    def change(self, assignment: dict[str, Any], generation: dict[str, Any], binding: dict[str, Any],
               current: dict[str, Any], source: dict[str, Any], config: dict[str, Any], *,
               target: dict[str, Any] | None = None, disposition: ChildDisposition = ChildDisposition.FOLLOW,
               managed: dict[str, Any] | None = None) -> dict[str, str]:
        policies = [p for p in current["notification_policies"] if p["status"] == "active"]
        if managed and "reminders" in managed:
            if (config["notification_plan"] or {}).get("resolved", {}).get("effective_templates"):
                self.check_delivery(config)
            family, desired = children.adoption_policies(self.db, self.invocation, assignment["assignment_id"], generation,
                                                         current, int(current["current_version"]) + 1, config)
            family_ids = {p["notification_intent_id"] for p in family}
            policies = [p for p in policies if p["notification_intent_id"] not in family_ids] + [dict(p.value) for _, p in desired]
        work = self.work_effects(generation, current, config, policies, target=target, disposition=disposition)
        raise _Effect(disposition.value, {"binding_revision": binding["latest_revision"]["temporal_binding_revision_id"],
                                         "task_version": str(current["current_version"]), "target": target,
                                         "source": source, "managed": managed, "work": work})

    def before_state(self, state: dict[str, Any], original: dict[str, Any], outcome: str, reason: str) -> None:
        if state != original:
            raise _Effect(outcome, {"state": state, "reason": reason})

    def record_outcome(self, intent: dict[str, Any], assignment_id: str, state_id: str, outcome: str, reason: str) -> bool:
        if not row(self.db, "related_task_intent_outcomes", intent["intent_id"], assignment_id):
            raise _Effect("record_outcome", [intent["intent_id"], outcome, reason])
        return False

    def retained_work(self, gen: dict[str, Any], current: dict[str, Any], config: dict[str, Any]) -> None:
        policies = [p for p in current["notification_policies"] if p["status"] == "active"]
        work = self.work_effects(gen, current, config, policies)
        if work["missing"] or work["cancel"]:
            raise _Effect("repair_work", work)

    def work_effects(self, gen: dict[str, Any], current: dict[str, Any], config: dict[str, Any], policies: list[dict[str, Any]],
                     *, target: dict[str, Any] | None = None, disposition: ChildDisposition = ChildDisposition.FOLLOW
                     ) -> dict[str, list[str]]:
        db, task = self.db, gen["task_item_id"]
        limit = self.limits["work_rows"]
        self.unit_work_rows = len(db.execute("SELECT 1 FROM work_instances WHERE item_id=? LIMIT ?", (task, limit + 1)).fetchall())
        if self.unit_work_rows > limit:
            raise ChildWorkOverflow()
        terminal = disposition is ChildDisposition.CANCEL or current["detail"]["task_status"] != "open"
        cancels, kept, protected, _ = schedule_work.reconcile_work_plan(
            db, item_id=task, active_policies=policies, target_changed=target is not None, recurrence_changed=False,
            temporal_binding_stale=disposition is ChildDisposition.DETACH, parent_terminal=terminal)
        bounds = children.materialization(config, self.now)
        missing = []
        if bounds["mode"] != "none" and not terminal and disposition is ChildDisposition.FOLLOW:
            anchor = target_from_anchor({**target, "anchor_kind": "local_instant"} if target else current["detail"]["due_anchor"])
            targets = {p["notification_intent_id"]: [anchor] for p in policies}
            opportunities = schedule_materialization.actionable_opportunities(policies, targets, bounds)
            for opportunity in opportunities:
                identity = schedule_materialization.opportunity_work_id(opportunity)
                if not schedule_work.work_exists(db, identity):
                    missing.append(identity)
        self.unit_work_rows += len(missing)
        return {"missing": missing, "cancel": cancels, "keep": kept, "protected": protected}


def observe(db: LedgerConnection, request: dict[str, Any], context: Any, contracts: Any, now: str) -> PagePlan:
    """Caller owns a snapshot. Request is the admitted, normalized reconcile request."""
    if not db.in_transaction or not getattr(db, "_recurring_tasks_enabled", False):
        fail("environment_failure", "transaction")
    with read_only(db):
        root_id = request["related_task_rule_id"]
        root = read_record(db, "related_task_rules", root_id)
        page = _Observer(db, context, root, request, contracts, now, {"audit_ids": [], "cutoffs": []}, None)
        page.observations = []
        page.aliases = {}
        page.observed_work_rows = 0
        token = continuation(db, request, root, context, contracts, now)
        position = dict(token["after"]) if token else {"assignment_after_seq": "0", "source_after": None}
        original = dict(position)
        _, start, end = page_bounds(page, token)
        processed, existing_more, source_more = select_units(page, position, start, end)
        progress = []
        # A changed unit may invalidate coverage or resolve an intent. Do not
        # predict its downstream writes; the writer finalizes the actual prefix.
        if not any(unit.changed for unit in page.observations):
            for intent in (pending_adoption(db, root_id), intent_view(db, root["retirement_intent_id"])):
                if intent and intent["status"] == "pending" and can_complete(db, root_id, intent, page.budget):
                    progress.append(intent["intent_id"])
            ack, seq = coverage_action(db, root_id, page.dirty, original=original, position=position, results=page.state.results,
                                      processed_assignments=processed, existing_more=existing_more, source_more=source_more,
                                      source_prefix_unproved=page.source_prefix_unproved)
            if ack and page.dirty:
                progress.append(f"coverage:{page.dirty['dirty_generation']}:{seq}")
        return PagePlan(read_ledger_instance_id(db), now, hash_canonical_json(request), catalog(db), tuple(page.observations),
                        tuple(progress), existing_more or source_more)
