"""Synchronous application-owned propagation of existing consequences only.

No dispatch, repair queue, new history, child commit or implicit work policy.
The initial closed effect family is bindings; RF3's other writers remain tracked.
"""

import sqlite3

from spine.core.errors import SpineValidationError
from spine.core.mutation_effects import MutationEffects
from spine.ledger.mutation_effects import binding_snapshot, require_transaction
from spine.ledger.temporal_bindings import binding_catalog_generation, increment_binding_catalog_generation


def propagate(db: sqlite3.Connection, *, binding_id: str) -> MutationEffects:
    connection = require_transaction(db)
    pending = connection.mutation_state.propagation.bindings
    effect = pending.get(binding_id)
    if effect is None:
        raise SpineValidationError("environment_failure:propagation", "missing or already propagated binding mutation")
    if effect.after.revision_id is None or binding_snapshot(db, binding_id) != effect.after:
        raise SpineValidationError("environment_failure:propagation", "incomplete or changed binding mutation")
    # Exactly the existing once-per-logical-operation catalog consequence.
    # Trigger/finalizer-owned facet/rendering/access consequences are not repeated.
    before = binding_catalog_generation(connection)
    increment_binding_catalog_generation(connection)
    if binding_catalog_generation(connection) != before + 1:
        raise SpineValidationError("environment_failure:propagation", "binding catalog consequence missing or duplicated")
    del pending[binding_id]
    return MutationEffects(bindings=(effect,))
