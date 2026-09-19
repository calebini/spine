"""Authorized source facts for internal reads; never a hash of hidden evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from spine.core.canonical_json import canonical_json_text
from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.ledger.recurrence import load_current_recurrence_set
from spine.ledger.temporal_bindings import active_binding_for_target
from spine.web.errors import WebError

SNAPSHOT = "spine.trusted-web-read-snapshot.v1"


@dataclass
class SourceFacts:
    values: dict[tuple[str, str], Any] = field(default_factory=dict)
    cores: dict[str, dict[str, Any]] = field(default_factory=dict)
    collecting: set[str] = field(default_factory=set)

    def add(self, kind, identity, value):
        self.values[kind, identity] = value

    def capture(self, snapshot, activity):
        """Capture canonical proofs in the same transaction as the projected core.

        A protected reference must pass its own authority check before even its
        digest is eligible. Unsupported proof references make time unavailable.
        """
        from spine.web.read_projection import UNAVAILABLE_TIME, core

        identity = activity["item_id"]
        if identity in self.collecting:
            activity["time"] = dict(UNAVAILABLE_TIME)
            return
        self.collecting.add(identity)
        staged = {}
        try:
            recurrence = load_current_recurrence_set(snapshot.db, item_id=identity)
            if recurrence is not None:
                if not proof_references(snapshot, recurrence):
                    activity["time"] = dict(UNAVAILABLE_TIME)
                else:
                    staged["recurrence", recurrence["recurrence_revision_id"]] = recurrence
            if activity["item_type"] == "task":
                binding = active_binding_for_target(snapshot.db, item_id=identity)
                if binding is not None and binding["binding_mode"] == "follow_source":
                    revision = binding["latest_revision"]
                    try:
                        snapshot.permissions.item(str(binding["source_item_id"]))
                        authorized = proof_references(snapshot, revision)
                    except WebError as exc:
                        if exc.code != "resource_unavailable":
                            raise
                        authorized = False
                    if not authorized:
                        activity["time"] = dict(UNAVAILABLE_TIME)
                    else:
                        try:
                            source = core(snapshot, str(binding["source_item_id"]))
                        except WebError as exc:
                            if exc.code not in {"resource_unavailable", "admission_unavailable", "invalid_request"}:
                                raise
                            source = None
                        if source is not None:
                            staged["temporal_source", source["item_id"]] = source
                            staged["temporal_binding", binding["temporal_binding_id"]] = revision
                        if source is None or source["time"]["availability"] != "available":
                            activity["time"] = dict(UNAVAILABLE_TIME)
            for key, value in staged.items():
                if key not in self.values:
                    snapshot.budget.charge(value)
                self.values[key] = value
        except (SpineValidationError, ValueError, KeyError, TypeError):
            activity["time"] = dict(UNAVAILABLE_TIME)
        finally:
            self.cores[identity] = activity
            self.collecting.remove(identity)

    def records(self):
        return [
            {"kind": kind, "id": identity, "value_hash": hash_canonical_json(value)}
            for (kind, identity), value in sorted(self.values.items())
        ]

    def digest(self, route, query_hash):
        return hash_canonical_json({"contract_version": SNAPSHOT, "route": route, "query_hash": query_hash, "facts": self.records()})

    def section(self, root, name, section, rules):
        if section.state["availability"] != "available":
            return
        for row in section.rows:
            identity = (
                canonical_json_text([row[k] for k in rules[name]["ordering"]])
                if rules[name]["shape"] == "collection" else root
            )
            self.add(name, identity, row)


def proof_references(snapshot, value):
    """Closed canonical proof reference vocabulary; unknown references fail closed."""
    local = {
        "recurrence_set_id", "recurrence_revision_id", "seed_anchor_id", "segment_id", "rule_id",
        "rdate_id", "exdate_id", "override_id", "source_revision_id", "lineage_parent_segment_id",
        "created_by_command_id", "segment_ref", "source_anchor_id", "target_anchor_id",
        "source_recurrence_revision_id", "source_occurrence_provenance_id", "source_occurrence_selector_ref",
        "temporal_binding_id", "temporal_binding_revision_id",
    }
    if isinstance(value, list):
        return all(proof_references(snapshot, v) for v in value)
    if not isinstance(value, dict):
        return True
    for key, v in value.items():
        if v is None:
            continue
        try:
            if key.endswith(("_id", "_ids", "_ref")):
                if isinstance(v, (dict, list)):
                    return False
                if key in {"item_id", "source_item_id", "target_item_id"}:
                    snapshot.permissions.item(v)
                elif key.endswith("subject_id"):
                    if v != snapshot.permissions.subject:
                        return False
                elif key.endswith("group_id"):
                    if v not in snapshot.permissions.groups:
                        return False
                elif key in {"notification_profile_id", "item_archetype_id"}:
                    snapshot.permissions.catalog(key.removesuffix("_id"), v)
                elif key == "delivery_target_id":
                    snapshot.permissions.route(v)
                elif key not in local:
                    return False
            elif not proof_references(snapshot, v):
                return False
        except WebError as exc:
            if exc.code not in {"resource_unavailable", "operation_unavailable"}:
                raise
            return False
    return True
