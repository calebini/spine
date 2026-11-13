"""Candidate R3 derived queue: indexed invalidation, no child fan-out or receipts.

Generation tokens come from the monotonic catalog, not a deleted queue row, so
an old page cannot clear a later delete/reinsert incarnation (ABA).
"""

from enum import IntFlag

from spine.core.mutation_effects import MutationEffects
from spine.core.recurring_tasks import invariant
from spine.ledger.recurring_task_catalog import advance_catalog
from spine.ledger.transactions import LedgerConnection


class DirtyReason(IntFlag):
    SOURCE = 1
    TARGET = 2
    INTENT = 4


def mark(db: LedgerConnection, rule_id: str, reason: DirtyReason) -> None:
    invariant(db.in_transaction and getattr(db, "_recurring_tasks_enabled", False), "recurring invalidation requires candidate transaction")
    invariant(bool(reason) and not int(reason) & ~7, "invalid dirty reason")
    state = db.mutation_state.recurring
    seen = state.invalidations.get(rule_id, 0)
    merged = seen | int(reason)
    if merged == seen:
        return
    advance_catalog(db)
    if not seen:
        # At most one new token per root per semantic transaction. Existing flags
        # survive; restart assignment coverage because earlier rows may be stale.
        db.execute("""INSERT INTO related_task_dirty_rules
            (related_task_rule_id,dirty_generation,source_dirty,target_dirty,intent_dirty,assignment_after_seq)
            SELECT ?,catalog_generation,?,?,?,0 FROM related_task_catalog_state WHERE singleton_id=1
            ON CONFLICT(related_task_rule_id) DO UPDATE SET
              dirty_generation=excluded.dirty_generation,
              source_dirty=MAX(source_dirty,excluded.source_dirty),
              target_dirty=MAX(target_dirty,excluded.target_dirty),
              intent_dirty=MAX(intent_dirty,excluded.intent_dirty),assignment_after_seq=0""",
            (rule_id, int(bool(reason & DirtyReason.SOURCE)), int(bool(reason & DirtyReason.TARGET)),
             int(bool(reason & DirtyReason.INTENT))))
    else:
        db.execute("""UPDATE related_task_dirty_rules SET
            source_dirty=MAX(source_dirty,?),target_dirty=MAX(target_dirty,?),intent_dirty=MAX(intent_dirty,?)
            WHERE related_task_rule_id=?""", (int(bool(reason & DirtyReason.SOURCE)),
                int(bool(reason & DirtyReason.TARGET)), int(bool(reason & DirtyReason.INTENT)), rule_id))
    state.invalidations[rule_id] = merged


def acknowledge(db: LedgerConnection, rule_id: str, generation: int, *, assignment_after_seq: int | None = None) -> bool:
    """CAS after a proven page: None clears; a larger sequence advances coverage.

    Proof/planning is the caller's responsibility. This helper never certifies it.
    A page cannot clear a canonical mutation made in its own transaction either.
    """
    invariant(db.in_transaction and getattr(db, "_recurring_tasks_enabled", False),
              "recurring acknowledgement requires candidate transaction")
    invariant(type(generation) is int and generation > 0, "invalid dirty generation")
    invariant(assignment_after_seq is None or type(assignment_after_seq) is int and assignment_after_seq >= 0,
              "invalid dirty continuation")
    if rule_id in db.mutation_state.recurring.invalidations:
        return False
    if assignment_after_seq is None:
        return db.execute("DELETE FROM related_task_dirty_rules WHERE related_task_rule_id=? AND dirty_generation=?",
                          (rule_id, generation)).rowcount == 1
    return db.execute("""UPDATE related_task_dirty_rules SET assignment_after_seq=?
        WHERE related_task_rule_id=? AND dirty_generation=? AND assignment_after_seq<?""",
        (assignment_after_seq, rule_id, generation, assignment_after_seq)).rowcount == 1


def invalidate_item(db: LedgerConnection, item_id: str) -> None:
    if not getattr(db, "_recurring_tasks_enabled", False):
        return
    for row in db.execute("SELECT related_task_rule_id FROM related_task_rules WHERE source_item_id=?", (item_id,)).fetchall():
        mark(db, row[0], DirtyReason.SOURCE)
    _target(db, "task_item_id", item_id)


def _target(db: LedgerConnection, column: str, identity: str) -> None:
    invariant(column in {"task_item_id", "temporal_binding_id", "relationship_id"})
    # UNIQUE generation lookup followed by the assignment PK, never a history scan.
    row = db.execute(f"""SELECT a.related_task_rule_id FROM related_task_generations g
        JOIN related_task_assignments a ON a.assignment_id=g.assignment_id
        WHERE g.{column}=? AND a.current_generation_id=g.generation_id""", (identity,)).fetchone()
    if row is not None:
        mark(db, row[0], DirtyReason.TARGET)


def invalidate_effects(db: LedgerConnection, effects: MutationEffects) -> None:
    if not getattr(db, "_recurring_tasks_enabled", False):
        return
    created = {e.after.item_id for e in effects.items if e.before is None}
    db.mutation_state.recurring.new_items.update(created)
    items = {e.after.item_id for e in effects.items if e.before is not None}
    items.update(e.item_id for e in effects.policies)
    items.update(e.after.item_id for e in effects.owners
                 if e.before is not None or e.after.item_id not in db.mutation_state.recurring.new_items)
    items.update(e.after.source_item_id for e in effects.recurrences)
    # Initial children have no generation until the caller installs its immutable
    # link. Their new policies cannot stale an existing generation either.
    for identity in sorted(items - created):
        invalidate_item(db, identity)
    for binding in effects.bindings:
        if binding.before is not None:
            _target(db, "temporal_binding_id", binding.after.binding_id)
    for relation in effects.relations:
        if relation.before is not None:
            _target(db, "relationship_id", relation.after.relation_id)
