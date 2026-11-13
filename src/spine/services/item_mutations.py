"""Closed application adapters for existing guarded item allocators.

These wrappers retain each allocator's signature, result and error behavior.
They add no intent normalization, SQL, work mode, receipt or public command.
"""

import sqlite3
from collections.abc import Callable
from functools import wraps
from typing import Concatenate

from spine.ledger import items
from spine.ledger.mutation_effects import require_transaction
from spine.services import mutation_propagation


def _owned[**P, T: (items.CreatedItem, items.MutatedItem, str)](
    operation: Callable[Concatenate[sqlite3.Connection, P], T],
) -> Callable[Concatenate[sqlite3.Connection, P], T]:
    @wraps(operation)
    def apply(db: sqlite3.Connection, /, *args: P.args, **kwargs: P.kwargs) -> T:
        require_transaction(db)
        result = operation(db, *args, **kwargs)
        identity = str(kwargs["item_id"]) if isinstance(result, str) else result.item_id
        mutation_propagation.propagate(db, item_id=identity)
        return result
    return apply


create_event_v1 = _owned(items.create_event_v1)
create_task_v1 = _owned(items.create_task_v1)
create_next_item_version = _owned(items.create_next_item_version)
create_item_version_from_draft = _owned(items.create_item_version_from_draft)
cancel_event = _owned(items.cancel_event)
cancel_task = _owned(items.cancel_task)
complete_task = _owned(items.complete_task)
archive_item = _owned(items.archive_item)
