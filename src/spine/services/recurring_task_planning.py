"""Internal read-only automatic discovery; not authority to dispatch a write.

The caller retains the root keyset position in memory. A discovered maintenance
candidate still needs a complete semantic page plan before command dispatch;
dirty markers alone are deliberately NOT exposed as a dispatchable boolean.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.core.recurring_task_runtime import instant, wire
from spine.ledger.recurring_task_catalog import catalog, intent_view, pending_adoption, source_snapshot
from spine.ledger.recurring_task_sources import ProofBudget
from spine.ledger.recurring_tasks import read_record
from spine.ledger.transactions import LedgerConnection
from spine.services.recurring_task_source_window import SourceWindow


@dataclass(frozen=True)
class DiscoveryLimits:
    roots: int = 8
    assignments: int = 32
    source_candidates: int = 256
    proof_steps: int = 10000
    lineage_hops: int = 64

    def validate(self) -> None:
        for name, maximum in (("roots", 128), ("assignments", 128), ("source_candidates", 2048),
                              ("proof_steps", 50000), ("lineage_hops", 256)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise SpineValidationError("invalid_scheduler_limits", name)


@dataclass(frozen=True)
class RootDiscovery:
    rule_id: str
    fingerprint: str
    assignment_ids: tuple[str, ...]
    occurrence_keys: tuple[str, ...]
    assignments_more: bool
    sources_more: bool
    dirty_generation: int | None
    diagnostic: str | None


@dataclass(frozen=True)
class DiscoveryCycle:
    roots: tuple[RootDiscovery, ...]
    next_root_after: str | None


DEFAULT_LIMITS = DiscoveryLimits()


def discover(
    db: LedgerConnection, *, evaluated_at_utc: str, after_root: str | None = None,
    limits: DiscoveryLimits = DEFAULT_LIMITS,
) -> DiscoveryCycle:
    """Separate bounded maintenance/generation lanes and round-robin root seeks.

    No receipts, progress, acknowledgement, saved continuations or other writes.
    The next root advances even on an unresolved/budget-exhausted source.
    """
    limits.validate()
    instant(evaluated_at_utc)
    if not getattr(db, "_recurring_tasks_enabled", False):
        raise SpineValidationError("environment_failure", "recurring candidate runtime is not enabled")
    if db.in_transaction:
        raise SpineValidationError("environment_failure", "discovery requires its own read snapshot")
    with db.atomic_command(write=False):
        # Bound visited roots, not merely returned eligible roots. A filtered
        # LIMIT could scan an arbitrarily large retired catalog before yielding.
        rows = db.execute(
            "SELECT related_task_rule_id,status,retirement_intent_id FROM related_task_rules "
            "WHERE related_task_rule_id>? ORDER BY related_task_rule_id LIMIT ?", (after_root or "", limits.roots),
        ).fetchall()
        if after_root and len(rows) < limits.roots:
            rows += db.execute(
                "SELECT related_task_rule_id,status,retirement_intent_id FROM related_task_rules "
                "WHERE related_task_rule_id<=? ORDER BY related_task_rule_id LIMIT ?", (after_root, limits.roots - len(rows)),
            ).fetchall()
        roots = []
        for row in rows:
            if row[1] != "active":
                dirty = db.execute("SELECT 1 FROM related_task_dirty_rules WHERE related_task_rule_id=?", (row[0],)).fetchone()
                intent = intent_view(db, row[2])
                if not dirty and not (intent and intent["status"] == "pending"):
                    continue
            roots.append(discover_root(db, row[0], evaluated_at_utc=evaluated_at_utc, limits=limits))
        return DiscoveryCycle(tuple(roots), rows[-1][0] if rows else after_root)


def discover_root(db: LedgerConnection, rule_id: str, *, evaluated_at_utc: str, limits: DiscoveryLimits) -> RootDiscovery:
    """A transaction-local bounded snapshot; reusable by a future dispatch fence."""
    if not db.in_transaction:
        raise SpineValidationError("environment_failure", "discovery root requires a read snapshot")
    limits.validate()
    root = read_record(db, "related_task_rules", rule_id)
    dirty_row = db.execute("SELECT * FROM related_task_dirty_rules WHERE related_task_rule_id=?", (rule_id,)).fetchone()
    dirty = dict(dirty_row) if dirty_row else None
    adoption, retirement = pending_adoption(db, rule_id), intent_view(db, root["retirement_intent_id"])
    assignment_ids: tuple[str, ...] = ()
    assignments_more = False
    if dirty or adoption or retirement and retirement["status"] == "pending":
        rows = db.execute(
            "SELECT assignment_id FROM related_task_assignments WHERE related_task_rule_id=? AND assignment_seq>? "
            "ORDER BY assignment_seq LIMIT ?", (rule_id, dirty["assignment_after_seq"] if dirty else 0, limits.assignments + 1),
        ).fetchall()
        assignment_ids = tuple(r[0] for r in rows[:limits.assignments])
        assignments_more = len(rows) > limits.assignments
    keys: list[str] = []
    sources_more, diagnostic = False, None
    snapshot = None
    try:
        snapshot = source_snapshot(db, root)
        source = db.execute(
            "SELECT i.status,e.event_status FROM coordination_items i JOIN event_details e "
            "ON e.item_id=i.item_id AND e.version=i.current_version WHERE i.item_id=?", (root["source_item_id"],),
        ).fetchone()
        if root["status"] == "active" and source and tuple(source) == ("active", "scheduled"):
            config = read_record(db, "related_task_rule_revisions", root["current_revision_id"])["configuration_json"]
            budget = ProofBudget(limits.proof_steps, limits.lineage_hops)
            window = SourceWindow.load(db, root, config, snapshot, evaluated_at_utc, budget)
            evaluated = instant(evaluated_at_utc)
            start = wire(evaluated - timedelta(seconds=max(0, int(config["offset_seconds"]))))
            end = wire(evaluated + timedelta(seconds=int(config["generation_horizon_seconds"])))
            for occurrence in window.candidates(start, end):
                budget.spend()
                if occurrence["lifecycle"] != "active":
                    continue
                # Expanding a window is not permission to recreate consumed
                # slots, including terminal/detached historical assignments.
                if db.execute(
                    "SELECT 1 FROM related_task_selector_reservations WHERE related_task_rule_id=? AND occurrence_key=?",
                    (rule_id, occurrence["occurrence_key"]),
                ).fetchone():
                    continue
                from spine.services.recurring_task_children import source_facts

                source_value = source_facts(db, root, window.recurrence, occurrence, evaluated_at_utc,
                                           persist=False, command_id="read-only-discovery")
                if instant(source_value["resolved_source_utc"]) + timedelta(seconds=int(config["offset_seconds"])) <= evaluated:
                    continue
                if len(keys) == limits.source_candidates:
                    sources_more = True
                    break
                keys.append(occurrence["occurrence_key"])
    except SpineValidationError as error:
        # Retain independent assignment maintenance selection even when source
        # enumeration cannot be proved. No absence/cancellation inference.
        keys, sources_more, diagnostic = [], False, error.code
    facts: dict[str, Any] = {
        "rule_id": rule_id, "change_version": str(root["change_version"]), "revision_id": root["current_revision_id"],
        "catalog": catalog(db), "source": snapshot,
        "dirty": {k: str(v) if type(v) is int else v for k, v in dirty.items()} if dirty else None,
        "adoption": adoption, "retirement": retirement,
        "assignment_ids": list(assignment_ids), "occurrence_keys": keys, "assignments_more": assignments_more,
        "sources_more": sources_more, "diagnostic": diagnostic,
    }
    return RootDiscovery(rule_id, hash_canonical_json(facts), assignment_ids, tuple(keys), assignments_more,
                         sources_more, dirty["dirty_generation"] if dirty else None, diagnostic)
