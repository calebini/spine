"""Authorized optional evidence, prepared before counting or public pagination.

Family mappings are deliberately narrow: ordinary relations need both endpoints
and no opaque metadata; subjects are self only; shared locations with no supported
authority are omitted. Inline locations require persisted creation evidence.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from spine.core.errors import SpineValidationError
from spine.web.errors import WebError
from spine.web.read_context import OptionalReadUnavailable, ReadSnapshot, optional_snapshot
from spine.web.read_contracts import read_error
from spine.web.read_projection import candidate_ids, core

PROJECTION = "trusted-web-read-projection.v1.json"
TYPES = "trusted-web-read-types.schema.json"


@dataclass
class SectionAssembly:
    """Internal state plus the full authorized evidence, not a wire page.

    Collections may contain up to the optional budget. The later cursor service
    must page them; complete_value is only usable for an exhausted <=100 row set.
    """

    state: dict[str, Any]
    collection: bool = False
    rows: list[dict[str, Any]] = field(default_factory=list)
    value: Any = None

    def complete_value(self) -> dict[str, Any]:
        if self.state["availability"] != "available":
            return dict(self.state)
        if self.collection:
            if len(self.rows) > 100:
                raise ValueError("public pagination required")
            return {**self.state, "entries": self.rows, "has_more": False, "next_cursor": None}
        return {**self.state, "value": self.value}


def _state(availability):
    value = {"availability": availability, "scope": "authorized_only"}
    if availability != "not_requested":
        value["coverage"] = "complete" if availability == "available" else "incomplete"
    if availability == "unavailable":
        value["reason_code"] = "context_unavailable"
    return value


def _allowed(operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs) is not False
    except WebError as exc:
        if exc.code in {"resource_unavailable", "operation_unavailable"}:
            return False
        raise


class Evidence:
    def __init__(self, snapshot, activity):
        self.s, self.db, self.p, self.activity = snapshot, snapshot.db, snapshot.permissions, activity
        self.item_id, self.version = activity["item_id"], int(activity["current_version"])

    def rows(self, sql, params=()):
        for row in self.db.execute(sql, params):
            self.s.budget.check()
            yield dict(row)

    def visible_relations(self):
        # Drive equality probes from authorized IDs, never scan the root's hidden graph.
        for identity in candidate_ids(self.s, {"include_terminal": True}):
            for source, target in {(self.item_id, identity), (identity, self.item_id)}:
                for row in self.rows(
                    """SELECT * FROM coordination_item_relations
                    INDEXED BY independent_read_relation_endpoints_idx
                    WHERE source_item_id=? AND target_item_id=?""",
                    (source, target),
                ):
                    if row["metadata_json"] not in (None, "{}"):
                        continue  # No authority mapping for opaque relation metadata.
                    if _allowed(self.p.item, source) and _allowed(self.p.item, target):
                        yield row

    def relations(self):
        yield from self.visible_relations()

    def related_items(self):
        identities = set()
        for relation in self.visible_relations():
            identities.update((relation["source_item_id"], relation["target_item_id"]))
        for identity in sorted(identities - {self.item_id}):
            yield core(self.s, identity)

    def temporal_bindings(self):
        for relation in self.visible_relations():
            # Binding direction need not equal relation direction.
            for source, target in {
                (relation["source_item_id"], relation["target_item_id"]),
                (relation["target_item_id"], relation["source_item_id"]),
            }:
                yield from self.rows(
                    """SELECT b.*,r.temporal_binding_revision_id
                    FROM relative_temporal_bindings b INDEXED BY independent_read_binding_endpoints_idx
                    JOIN relative_temporal_binding_revisions r ON r.temporal_binding_revision_id=(
                      SELECT temporal_binding_revision_id FROM relative_temporal_binding_revisions
                      WHERE temporal_binding_id=b.temporal_binding_id ORDER BY revision_index DESC LIMIT 1)
                    WHERE b.source_item_id=? AND b.target_item_id=? AND b.relationship_id=?""",
                    (source, target, relation["relation_id"]),
                )

    def subject_roles(self):
        yield from self.rows(
            """SELECT subject_id,role FROM item_subject_roles
            WHERE item_id=? AND version=? AND subject_id=? AND status='active'""",
            (self.item_id, self.version, self.p.subject),
        )

    def route_rows(self):
        scopes = [("subject", self.p.subject, None)] + [("subject_group", None, g) for g in sorted(self.p.groups)]
        for kind, subject, group in scopes:
            for row in self.rows(
                """SELECT * FROM delivery_targets
                WHERE owner_kind=? AND owner_subject_id IS ? AND owner_group_id IS ?""",
                (kind, subject, group),
            ):
                if _allowed(self.p.route, row["delivery_target_id"]):
                    yield row

    def application(self, version):
        row = self.db.execute(
            "SELECT * FROM notification_profile_applications WHERE item_id=? AND item_version=?", (self.item_id, version)
        ).fetchone()
        if row is None:
            return None
        row = dict(row)
        if not _allowed(self.p.catalog, "notification_profile", row["notification_profile_id"]):
            return False
        if any(not self.p.scope(scope) for scope in json.loads(row["scope_chain_json"])):
            return False
        if row["item_archetype_assignment_id"]:
            assignment = self.db.execute(
                "SELECT * FROM item_archetype_assignments WHERE item_archetype_assignment_id=?", (row["item_archetype_assignment_id"],)
            ).fetchone()
            if assignment is None or not _allowed(self.p.catalog, "item_archetype", assignment["item_archetype_id"]):
                return False
        if row["notification_profile_binding_id"]:
            binding = self.db.execute(
                "SELECT * FROM notification_profile_bindings WHERE notification_profile_binding_id=?",
                (row["notification_profile_binding_id"],),
            ).fetchone()
            if binding is None or not self.p.scope(dict(binding)):
                return False
        revision = self.db.execute(
            """SELECT 1 FROM notification_profile_revisions
            WHERE notification_profile_revision_id=? AND notification_profile_id=?""",
            (row["notification_profile_revision_id"], row["notification_profile_id"]),
        ).fetchone()
        return row if revision else False

    def notification_profiles(self):
        application = self.application(self.version)
        if application:
            profile = self.db.execute(
                "SELECT display_name FROM notification_profiles WHERE notification_profile_id=?", (application["notification_profile_id"],)
            ).fetchone()
            yield {
                "notification_profile_id": application["notification_profile_id"],
                "revision_id": application["notification_profile_revision_id"],
                "display_name": profile[0],
            }

    def authorized_policies(self, *, history=False):
        versions = (
            [self.version]
            if not history
            else [
                r[0]
                for r in self.db.execute("SELECT version FROM coordination_item_versions WHERE item_id=? ORDER BY version", (self.item_id,))
            ]
        )
        routes = list(self.route_rows())
        recipients = [("subject", "recipient_subject_id", self.p.subject)] + [
            ("subject_group", "recipient_group_id", group) for group in sorted(self.p.groups)
        ]
        for version in versions:
            for kind, column, recipient in recipients:
                for route in routes:
                    # Existing recipient unique indexes cover all four equality keys.
                    index = "notification_policies_subject_unique" if kind == "subject" else "notification_policies_group_unique"
                    for row in self.rows(
                        f"""SELECT * FROM notification_policies INDEXED BY {index}
                        WHERE item_id=? AND version=? AND recipient_kind='{kind}'
                        AND {column}=? AND delivery_target_id=?""",
                        (self.item_id, version, recipient, route["delivery_target_id"]),
                    ):
                        origin = self.db.execute(
                            """SELECT a.item_version FROM notification_profile_application_policies p
                            JOIN notification_profile_applications a USING(notification_profile_application_id)
                            WHERE p.notification_policy_id=?""",
                            (row["policy_id"],),
                        ).fetchone()
                        if origin is not None and self.application(origin[0]) is False:
                            continue
                        yield row

    def policies(self):
        for row in self.authorized_policies():
            yield {
                "notification_policy_id": row["policy_id"],
                "notification_intent_id": row["notification_intent_id"],
                "item_version": str(row["version"]),
                "status": row["status"],
            }

    def authorized_work(self):
        for policy in self.authorized_policies(history=True):
            for row in self.rows(
                """SELECT * FROM work_instances INDEXED BY independent_read_work_policy_idx
                WHERE notification_policy_id=? AND item_id=? AND delivery_target_id=?""",
                (policy["policy_id"], self.item_id, policy["delivery_target_id"]),
            ):
                if (
                    row["notification_intent_id"] != policy["notification_intent_id"]
                    or row["notification_policy_item_version"] != policy["version"]
                    or row["purpose_detail_ref"] is not None
                ):
                    continue
                yield row

    def work(self):
        yield from self.authorized_work()

    def attempts(self):
        for work in self.authorized_work():
            for row in self.rows("SELECT * FROM side_effect_attempts WHERE work_instance_id=?", (work["work_instance_id"],)):
                if row["item_id"] not in (None, self.item_id) or row["candidate_action_id"] or row["projection_id"]:
                    continue
                # Rendering/provider payloads are neither loaded nor copied.
                yield row

    def delivery_targets(self):
        identities = {row["delivery_target_id"] for row in self.authorized_policies()}
        identities.update(row["delivery_target_id"] for row in self.authorized_work())
        for identity in sorted(identities):
            route = self.p.route(identity)
            if _allowed(self.p.route, identity, release_owner=route):
                yield route

    def creation_receipts(self):
        effects = {
            "schedule.create": "schedule_created",
            "schedule.related_task.create": "related_task_schedule_created",
            "event.create": "event_created",
            "task.create": "task_created",
        }
        for command, effect in effects.items():
            for row in self.rows(
                """SELECT * FROM command_receipts INDEXED BY independent_read_creation_receipt_idx
                WHERE item_id=? AND command=? AND actor_subject_id=? ORDER BY created_at_utc,command_receipt_id""",
                (self.item_id, command, self.p.subject),
            ):
                facts = json.loads(row["result_identity_facts_json"])
                created = facts.get("task", {}) if command == "schedule.related_task.create" else facts
                if (
                    row["effect"] == effect
                    and row["target_version"] == "0"
                    and created.get("item_id") == self.item_id
                    and str(created.get("current_version", created.get("version"))) == "1"
                ):
                    yield row, facts

    def evidence_reference(self, key, identity):
        if key in {"work_instance_id", "work_instance_ids"}:
            identities = identity if isinstance(identity, list) else [identity]
            for work_id in identities:
                work = self.db.execute("SELECT * FROM work_instances WHERE work_instance_id=?", (work_id,)).fetchone()
                if work is None or work["item_id"] != self.item_id:
                    return False
                if not self.evidence_reference("notification_policy_id", work["notification_policy_id"]):
                    return False
                if not _allowed(self.p.route, work["delivery_target_id"]):
                    return False
            return True
        if key == "notification_policy_id":
            row = self.db.execute("SELECT * FROM notification_policies WHERE policy_id=?", (identity,)).fetchone()
            if row is None or row["item_id"] != self.item_id:
                return False
            recipient = (
                row["recipient_subject_id"] == self.p.subject
                if row["recipient_kind"] == "subject"
                else (row["recipient_group_id"] in self.p.groups)
            )
            return recipient and _allowed(self.p.route, row["delivery_target_id"]) and self.application(row["version"]) is not False
        if key in {"relation_id", "relationship_id"}:
            row = self.db.execute("SELECT * FROM coordination_item_relations WHERE relation_id=?", (identity,)).fetchone()
            return bool(
                row is not None
                and row["metadata_json"] in (None, "{}")
                and _allowed(self.p.item, row["source_item_id"])
                and _allowed(self.p.item, row["target_item_id"])
            )
        if key in {"temporal_binding_id", "temporal_binding_revision_id"}:
            if key == "temporal_binding_revision_id":
                revision = self.db.execute(
                    "SELECT temporal_binding_id FROM relative_temporal_binding_revisions WHERE temporal_binding_revision_id=?", (identity,)
                ).fetchone()
                if revision is None:
                    return False
                identity = revision[0]
            row = self.db.execute("SELECT * FROM relative_temporal_bindings WHERE temporal_binding_id=?", (identity,)).fetchone()
            return bool(
                row is not None
                and _allowed(self.p.item, row["source_item_id"])
                and _allowed(self.p.item, row["target_item_id"])
                and self.evidence_reference("relationship_id", row["relationship_id"])
            )
        return True

    def safe_references(self, value):
        """Closed reference vocabulary for receipt identity disclosure, recursively.

        Unknown identity/reference keys omit the whole receipt, including its digest.
        Internal IDs identify facts owned by the admitted root/explicit endpoints;
        they are never independently treated as permission for foreign resources.
        """
        local_ids = {
            "command_id",
            "command_receipt_id",
            "audit_id",
            "anchor_id",
            "start_anchor_id",
            "end_anchor_id",
            "due_anchor_id",
            "recurrence_set_id",
            "recurrence_revision_id",
            "segment_id",
            "rule_id",
            "rdate_id",
            "exdate_id",
            "override_id",
            "source_revision_id",
            "prior_recurrence_revision_id",
            "notification_intent_id",
            "notification_policy_id",
            "notification_schedule_id",
            "schedule_id",
            "notification_opportunity_id",
            "work_instance_id",
            "work_instance_ids",
            "occurrence_id",
            "temporal_binding_id",
            "temporal_binding_revision_id",
            "relationship_id",
            "relation_id",
            "target_anchor_id",
            "source_anchor_id",
            "source_recurrence_revision_id",
            "revision_id",
            "notification_profile_revision_id",
            "notification_profile_application_id",
            "item_archetype_revision_id",
            "item_archetype_assignment_id",
            "notification_profile_binding_id",
        }
        if isinstance(value, list):
            return all(self.safe_references(v) for v in value)
        if not isinstance(value, dict):
            return True
        for key, v in value.items():
            if v is None:
                continue
            if not self.evidence_reference(key, v):
                return False
            if key.endswith(("_id", "_ids", "_ref")) and isinstance(v, (dict, list)) and key != "work_instance_ids":
                return False  # A nested value cannot bypass the closed reference vocabulary.
            if key == "scope_chain":
                if any(not self.p.scope(scope) for scope in v):
                    return False
            elif key in {"location_id", "item_location_id"}:
                if not any(location.get(key) == v for location in self.primary_location()):
                    return False
            elif isinstance(v, (dict, list)) and key not in {"work_instance_ids"}:
                if not self.safe_references(v):
                    return False
            elif key in {"item_id", "source_item_id", "target_item_id", "related_item_id"}:
                if not _allowed(self.p.item, v):
                    return False
            elif key.endswith("subject_id"):
                if v != self.p.subject:
                    return False
            elif key.endswith("group_id"):
                if v not in self.p.groups:
                    return False
            elif key == "delivery_target_id":
                if not _allowed(self.p.route, v):
                    return False
            elif key in {"notification_profile_id", "item_archetype_id"}:
                if not _allowed(self.p.catalog, key.removesuffix("_id"), v):
                    return False
            elif key == "scope_chain":
                if any(not self.p.scope(scope) for scope in v):
                    return False
            elif key == "target_ref":
                route = value.get("delivery_target_id")
                if not route or not _allowed(self.p.route, route) or self.p.route(route)["target_ref"] != v:
                    return False
            elif key.endswith(("_id", "_ids", "_ref")) and key not in local_ids:
                return False
        return True

    def authoring_receipt(self):
        values = []
        for row, facts in self.creation_receipts():
            if self.safe_references(facts) and self.safe_references(json.loads(row["semantic_facts_json"])):
                values.append(row)
        if values:
            yield min(values, key=lambda r: (r["created_at_utc"], r["command_receipt_id"]))

    def primary_location(self):
        row = self.db.execute(
            """SELECT l.*,il.item_location_id,il.role FROM item_locations il
            JOIN locations l USING(location_id) WHERE il.item_id=? AND il.version=? AND il.role='primary'""",
            (self.item_id, self.version),
        ).fetchone()
        if row is None:
            return
        # Sharing authority for reference-mode locations is undefined. Only inline
        # authoring evidence for this item permits a location projection.
        from spine.commands.receipts import command_derived_id

        for command, path in (
            ("schedule.create", "/item/primary_location/location"),
            ("schedule.update", "/patch/primary_location/location"),
        ):
            for receipt in self.rows(
                """SELECT command_id,result_identity_facts_json,semantic_facts_json
                FROM command_receipts INDEXED BY independent_read_creation_receipt_idx
                WHERE item_id=? AND command=?""",
                (self.item_id, command),
            ):
                identity = command_derived_id(
                    prefix="location", command=command, command_id=receipt["command_id"], row_role="location", request_path=path
                )
                if identity != row["location_id"]:
                    continue
                semantic, facts = json.loads(receipt["semantic_facts_json"]), json.loads(receipt["result_identity_facts_json"])
                if command == "schedule.create":
                    authored = semantic.get("item", {}).get("primary_location", {})
                    location = facts.get("primary_location", {})
                else:
                    authored = semantic.get("normalized_primary_location") or {}
                    location = facts.get("primary_location_change", {}).get("current") or {}
                if (
                    facts.get("item_id") == self.item_id
                    and authored.get("mode") == "create"
                    and location.get("location_id") == row["location_id"]
                ):
                    yield dict(row)
                    return


def assemble_sections(snapshot: ReadSnapshot, item_id: str, include=(), *, agenda=False) -> dict[str, SectionAssembly]:
    # Root/core admission is outside every optional catch.
    activity = core(snapshot, item_id)
    rules = snapshot.contracts.artifacts[PROJECTION]["sections"]
    names = tuple(snapshot.contracts.artifacts[PROJECTION]["agenda"]["sections"]) if agenda else tuple(rules)
    if len(set(include)) != len(include) or set(include) - set(names):
        raise read_error("invalid_request")
    result = {}
    for name in names:
        collection = not agenda and rules[name]["shape"] == "collection"
        if name not in include:
            result[name] = SectionAssembly(_state("not_requested"), collection)
            continue
        try:
            with optional_snapshot(snapshot) as optional:
                evidence = Evidence(optional, activity)
                rows = {}
                for raw in getattr(evidence, name)():
                    value = {k: raw[k] for k in rules[name]["fields"] if k in raw and (raw[k] is not None or name == "related_items")}
                    if name == "attempts":
                        value["completed_at_utc"] = raw["completed_at_utc"]
                    snapshot.contracts.validate(TYPES, value, definition=rules[name]["definition"])
                    key = tuple(value[k] for k in rules[name]["ordering"])
                    if key not in rows:
                        snapshot.budget.charge(value, authorized_rows=1)
                        rows[key] = value
                ordered = [rows[k] for k in sorted(rows)]
                section = SectionAssembly(_state("available"), collection, ordered)
                if agenda and name != "primary_location":
                    definition = "attempt" if name == "attempts" else rules[name]["definition"]
                    status_field = "attempt_status" if name == "attempts" else "status"
                    statuses = snapshot.contracts.schemas[TYPES]["$defs"][definition]["properties"][status_field]["enum"]
                    counts = Counter(row[status_field] for row in ordered)
                    section.value = {"count": str(len(ordered)), "status_counts": {s: str(counts[s]) for s in statuses}}
                elif not collection:
                    section.value = ordered[0] if ordered else None
                result[name] = section
        except OptionalReadUnavailable:
            result[name] = SectionAssembly(_state("unavailable"), collection)
        except (SpineValidationError, ValueError, KeyError, TypeError, sqlite3.DatabaseError):
            result[name] = SectionAssembly(_state("unavailable"), collection)
        except WebError as exc:
            if exc.code not in {"invalid_request", "admission_unavailable"}:
                raise
            result[name] = SectionAssembly(_state("unavailable"), collection)
    return result


def assemble_detail(snapshot: ReadSnapshot, item_id: str, include=(), *, guards=None):
    activity = core(snapshot, item_id, guards=guards)
    return activity, assemble_sections(snapshot, item_id, include)
