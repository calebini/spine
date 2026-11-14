"""Read-only bounded source window shared by explicit pages and automatic discovery."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from spine.core import occurrence_details
from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.occurrences import expand_recurrence_set
from spine.core.recurring_task_runtime import fail, instant, wire
from spine.ledger import item_reads
from spine.ledger.recurrence import load_current_recurrence_set
from spine.ledger.recurring_task_sources import ProofBudget, _calendar_cost
from spine.services import recurring_task_children as children


@dataclass
class SourceWindow:
    db: Any
    root: dict[str, Any]
    config: dict[str, Any]
    recurrence: dict[str, Any]
    now: str
    budget: ProofBudget
    source_item: dict[str, Any]

    @classmethod
    def load(cls, db: Any, root: dict[str, Any], config: dict[str, Any],
             snapshot: dict[str, Any], now: str, budget: ProofBudget) -> "SourceWindow":
        for table in ("recurrence_rules", "recurrence_segments", "recurrence_rdates", "recurrence_exdates", "recurrence_overrides"):
            rows = db.execute(
                f"SELECT 1 FROM {table} WHERE recurrence_revision_id=? LIMIT ?",
                (snapshot["recurrence_revision_id"], budget.steps + 1),
            ).fetchall()
            budget.spend(len(rows))
        recurrence = load_current_recurrence_set(db, item_id=root["source_item_id"])
        if recurrence is None:
            fail("environment_failure", "source")
        # Generation writes target tasks, never the source event. Bind its facts
        # once to this transaction, not once per proof/candidate/child.
        return cls(db, root, config, recurrence, now, budget, item_reads.hydrated_item(db, root["source_item_id"]))

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
        values = self.expand(
            fact, occurrence_details.next_scheduled_fact(fact, time_basis=self.recurrence["time_basis"]), basis="original_schedule"
        )
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
                self.db, self.source_item, self.recurrence, occurrence, self.now, persist=False, command_id="read-only-source-window"
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
