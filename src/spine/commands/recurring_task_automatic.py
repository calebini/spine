"""Internal R3 automatic reconcile admission. No public dispatch registration."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from spine.commands.facet_runtime import FacetBudget, install_budget
from spine.commands.recurring_task_references import validate as validate_references
from spine.commands.recurring_task_runtime import PREFIX, RecurringTaskContracts
from spine.commands.recurring_tasks import execute, expected
from spine.core.recurring_task_runtime import fail, instant, wire
from spine.ledger.recurring_task_catalog import catalog
from spine.ledger.recurring_tasks import read_record
from spine.ledger.transactions import LedgerConnection
from spine.services.recurring_task_page_plan import PagePlan, observe


class PlanObsolete(Exception):
    """Internal non-dispatch outcome, not a new explicit command error."""


@dataclass(frozen=True)
class Dispatch:
    status: str
    response: dict[str, Any] | None = None


def _clock(now: str) -> None:
    try:
        if wire(instant(now)) != now:
            fail("environment_failure", "clock")
    except (TypeError, ValueError, AttributeError):
        fail("environment_failure", "clock")


def plan(request: dict[str, Any], context: Any, *, contracts: RecurringTaskContracts, now: str) -> PagePlan:
    """Evaluate an exact normalized page on one VM/time/proof-bounded read snapshot."""
    db = context.ledger
    if not (isinstance(db, LedgerConnection) and not db.in_transaction and getattr(db, "_recurring_tasks_enabled", False)
            and not context.dry_run and context.transport_metadata in ({}, {"adapter": "cli"})):
        fail("environment_failure", "admission")
    _clock(now)
    value = contracts.request(PREFIX + "reconcile", request)
    budget = FacetBudget()
    timeout = install_budget(db, budget)
    try:
        with db.atomic_command(write=False):
            validate_references(db, value, context)
            expected(db, value, read_record(db, "related_task_rules", value["related_task_rule_id"]))
            result = observe(db, value, context, contracts, now)
            budget.check()
            return result
    finally:
        db.set_progress_handler(None, 0)
        db.execute(f"PRAGMA busy_timeout={timeout}")


def recheck(db: LedgerConnection, value: dict[str, Any], context: Any, contracts: RecurringTaskContracts,
            now: str, prior: PagePlan) -> None:
    if not db.in_transaction or not db._command_write:
        fail("environment_failure", "transaction")
    _clock(now)
    if not prior.dispatchable or now < prior.observed_at or catalog(db) != prior.catalog_generation:
        raise PlanObsolete("stale_plan")
    if observe(db, value, context, contracts, now) != prior:
        raise PlanObsolete("stale_plan")


def dispatch(prior: PagePlan, request: dict[str, Any], context: Any, *, contracts: RecurringTaskContracts,
             clock: Callable[[], str]) -> Dispatch:
    if not prior.dispatchable:
        return Dispatch("observed")
    try:
        response = execute(PREFIX + "reconcile", request, context, contracts=contracts, clock=clock, automatic_plan=prior)
    except PlanObsolete as exc:
        return Dispatch(str(exc))
    if not response["ok"]:
        return Dispatch("failed", response)
    return Dispatch("replayed" if response["replayed"] else "applied", response)
