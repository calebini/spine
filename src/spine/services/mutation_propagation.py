"""Synchronous application-owned propagation of existing consequences only.

No dispatch, repair queue, new history, child commit or implicit work policy.
Selected families are items/policies, bindings, relations, recurrence and item ownership.
"""

import sqlite3
from dataclasses import replace

from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.mutation_effects import (
    ConfiguredOwnerPropagation,
    LocalOwnerPropagation,
    MutationEffects,
    OwnershipPropagationResult,
    ProvisionedOwnerPropagation,
)
from spine.ledger.mutation_effects import binding_snapshot, require_transaction
from spine.ledger.owner_mutations import access_epoch, advance_configured_epoch, verify_item_owner
from spine.ledger.ownership import advance_ownership_epoch
from spine.ledger.recurrence_effects import verify_recurrence
from spine.ledger.relations import relation_snapshot
from spine.ledger.temporal_bindings import binding_catalog_generation, increment_binding_catalog_generation


def reserve_local_owner_epoch(db: sqlite3.Connection) -> int:
    """Retain local bootstrap's before-owner-write reservation and failure order."""
    return advance_ownership_epoch(require_transaction(db))


def propagate(
    db: sqlite3.Connection, *, binding_id: str | None = None, relation_id: str | None = None,
    recurrence_revision_id: str | None = None,
    item_id: str | None = None,
    ownership: LocalOwnerPropagation | ConfiguredOwnerPropagation | ProvisionedOwnerPropagation | None = None,
) -> MutationEffects:
    connection = require_transaction(db)
    if sum(value is not None for value in (binding_id, relation_id, ownership, recurrence_revision_id, item_id)) != 1:
        raise SpineValidationError("environment_failure:propagation", "one exact mutation family is required")
    if ownership is not None:
        return _owners(connection, ownership)
    if item_id is not None:
        state = connection.mutation_state.propagation
        item = state.items.get(item_id)
        if item is None:
            raise SpineValidationError("environment_failure:propagation", "missing or already propagated item mutation")
        if getattr(connection, "_renderings_enabled", False) and any(
            p.policy_id not in connection.mutation_state.renderings.pending
            for p in state.policies.values() if p.item_id == item_id
        ):
            raise SpineValidationError("environment_failure:rendering", "unregistered policy writer or missing presentation")
        policies = tuple(replace(p, after_presentation=canonical_json_bytes(connection.mutation_state.renderings.pending[p.policy_id]))
                         if getattr(connection, "_renderings_enabled", False) else p
                         for p in state.policies.values() if p.item_id == item_id)
        if any(p.item_version != item.after.version for p in policies):
            raise SpineValidationError("environment_failure:propagation", "policy mutation belongs to another item version")
        # The native allocator has completed CAS, audit and cross-row invariants.
        # Rendering/facet finalizers retain supporting-set/continuity proof and
        # audit triggers retain catalog ownership. Do not apply them twice.
        del state.items[item_id]
        for policy in policies:
            del state.policies[policy.policy_id]
        return MutationEffects(items=(item,), policies=policies)
    if recurrence_revision_id is not None:
        pending_recurrences = connection.mutation_state.propagation.recurrences
        recurrence = pending_recurrences.get(recurrence_revision_id)
        if recurrence is None:
            raise SpineValidationError("environment_failure:propagation", "missing or already propagated recurrence mutation")
        verify_recurrence(db, recurrence)
        # Existing item audits/finalizers retain catalog and freshness ownership.
        del pending_recurrences[recurrence_revision_id]
        return MutationEffects(recurrences=(recurrence,))
    if relation_id is not None:
        pending_relations = connection.mutation_state.propagation.relations
        relation = pending_relations.get(relation_id)
        if relation is None:
            raise SpineValidationError("environment_failure:propagation", "missing or already propagated relation mutation")
        if relation_snapshot(db, relation_id) != relation.after:
            raise SpineValidationError("environment_failure:propagation", "relation mutation incomplete or changed")
        # SQL owns relation indexes/constraints. The existing family audit owns
        # conditional binding-catalog invalidation; do not increment it here.
        del pending_relations[relation_id]
        return MutationEffects(relations=(relation,))
    assert binding_id is not None
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


def _owners(
    db: sqlite3.Connection, plan: LocalOwnerPropagation | ConfiguredOwnerPropagation | ProvisionedOwnerPropagation,
) -> MutationEffects:
    connection = require_transaction(db)
    pending = connection.mutation_state.propagation.owners
    identities = plan.owner_ids if isinstance(plan, ProvisionedOwnerPropagation) else (plan.owner_id,)
    if not identities or len(identities) != len(set(identities)) or any(identity not in pending for identity in identities):
        raise SpineValidationError("environment_failure:propagation", "missing or already propagated ownership mutation")
    effects = tuple(pending[identity] for identity in identities)
    for effect in effects:
        verify_item_owner(db, effect)
    if isinstance(plan, LocalOwnerPropagation):
        reservation = connection.mutation_state.ownership
        if not reservation.epoch_consumed or reservation.epoch_before is None or reservation.epoch_after is None:
            raise SpineValidationError("environment_failure:propagation", "local ownership epoch not reserved")
        before, after = reservation.epoch_before, reservation.epoch_after
    elif isinstance(plan, ConfiguredOwnerPropagation):
        before, after = plan.expected_epoch, plan.expected_epoch + 1
        advance_configured_epoch(db, before)
    else:
        # Explicit provisioning owns its whole-batch promotion/epoch transition.
        before, after = plan.before_epoch, plan.after_epoch
    if after != before + 1 or access_epoch(db) != after:
        raise SpineValidationError("environment_failure:propagation", "ownership epoch consequence differs")
    for identity in identities:
        del pending[identity]
    return MutationEffects(owners=effects, ownership_epoch=OwnershipPropagationResult(before, after))
