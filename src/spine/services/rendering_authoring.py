"""Candidate presentation resolution over existing timing and composition authority."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from spine.core import rendering_definitions as codec
from spine.ledger import facet_continuity
from spine.ledger.notification_profiles import current_application
from spine.ledger.rendering_definitions import invariant, load_disclosure, load_presentation, load_revision, root_owner, select_presentation


def policy_origin(db, policy):
    stored = load_presentation(db, policy["notification_policy_id"])
    if stored["kind"] == "definition":
        return stored["origin"]
    application = db.execute(
        "SELECT a.notification_profile_id,a.notification_profile_revision_id,p.policy_origin,p.source_key "
        "FROM notification_profile_application_policies p "
        "JOIN notification_profile_applications a USING(notification_profile_application_id) "
        "WHERE p.notification_policy_id=?",
        (policy["notification_policy_id"],),
    ).fetchone()
    if application is None:
        receipt = db.execute(
            "SELECT command FROM command_receipts WHERE command_id=?", (policy["intent_created_by_command_id"],)
        ).fetchone()
        return {"kind": "custom_addition" if receipt and receipt[0] in {"schedule.create", "schedule.update"} else "direct"}
    if application["policy_origin"] == "custom_addition":
        return {"kind": "custom_addition"}
    return {
        "kind": application["policy_origin"],
        "notification_profile_id": application["notification_profile_id"],
        "notification_profile_revision_id": application["notification_profile_revision_id"],
        "template_key": application["source_key"],
    }


def destination(db, policy):
    route = db.execute("SELECT * FROM delivery_targets WHERE delivery_target_id=?", (policy["delivery_target_id"],)).fetchone()
    if route is None or route["status"] != "active":
        codec.fail("rendering_disclosure_unavailable", "presentation")
    recipient = {"kind": policy["recipient_kind"]}
    recipient["subject_id" if policy["recipient_kind"] == "subject" else "group_id"] = policy.get("recipient_subject_id") or policy.get(
        "recipient_group_id"
    )
    return {
        "recipient": recipient,
        "delivery_target_id": policy["delivery_target_id"],
        "channel": policy["channel"],
        "adapter_name": route["adapter_name"],
        "destination_source": "delivery_target",
        "target_ref": route["target_ref"],
    }


def resolve(db, selection, *, policy, item_type, origin, permissions=None, budget=None):
    selected = codec.normalize_selection(selection)
    if selected["kind"] == "ordinary":
        return selected
    ref = selected["definition"]
    root = db.execute(
        "SELECT * FROM notification_rendering_definitions WHERE notification_rendering_definition_id=?",
        (ref["notification_rendering_definition_id"],),
    ).fetchone()
    if permissions:
        permissions.rendering(ref["notification_rendering_definition_id"], use=True)
        permissions.item(policy["item_id"], edit=True)
    if root is None:
        codec.fail("referenced_row_not_found", "presentation.definition")
    if root["status"] != "active":
        codec.fail("rendering_definition_retired", "presentation.definition")
    revision = load_revision(db, ref["notification_rendering_definition_revision_id"])
    if (
        revision["notification_rendering_definition_id"] != ref["notification_rendering_definition_id"]
        or item_type not in revision["revision"]["compatible_item_types"]
    ):
        codec.fail("rendering_definition_invalid", "presentation.definition")
    owner = db.execute("SELECT * FROM item_access_owners WHERE item_id=?", (policy["item_id"],)).fetchone()
    if owner is None and permissions is not None and hasattr(permissions, 'prospective_owner_for'):
        # A protected create can admit its exact command-derived item owner
        # before insertion. This is service context, never a request-mode bypass;
        # the adapter must persist that same owner in the canonical transaction.
        owner = permissions.prospective_owner_for(policy['item_id'])
    if owner is None:
        codec.fail("rendering_disclosure_unavailable", "presentation", "explicit item owner adoption is required before detail selection")
    own = root_owner(owner)
    if root_owner(root) != own:
        codec.fail("rendering_disclosure_scope_mismatch", "presentation")
    if permissions and any(
        s["projection"] == "location_label" and s["selection_key"] in selected["effective_selection_keys"]
        for s in revision["revision"]["selections"]
    ):
        codec.fail("permission_denied", "presentation")
    expected = {"item_owner": own, "definition": ref, "use_scope": codec.use_scope(origin), "destination": destination(db, policy)}
    if permissions:
        permissions.route(policy["delivery_target_id"], release_owner=own)
        for source in revision["revision"]["selections"]:
            permissions.schema(source["facet_schema_revision_id"], use=True)
    authorization = selected["authorization"]
    if authorization["resolution"] == "exact":
        ids = [authorization["disclosure_authorization_id"]]
        if db.execute("SELECT 1 FROM notification_rendering_disclosures WHERE disclosure_authorization_id=?", (ids[0],)).fetchone() is None:
            codec.fail("rendering_disclosure_unavailable", "presentation.authorization")
    else:
        ids = [
            r[0]
            for r in db.execute(
                "SELECT disclosure_authorization_id FROM notification_rendering_disclosures "
                "WHERE match_hash=? AND status='active' ORDER BY disclosure_authorization_id LIMIT 101",
                (codec.match_hash(expected),),
            )
        ]
        if len(ids) > 100:
            codec.fail("environment_failure", "capacity")
    matches = []
    for identity in ids:
        if budget:
            budget.resolve("notification_rendering_disclosures", identity)
        grant = load_disclosure(db, identity)
        if (
            grant["status"] == "active"
            and all(grant["scope"][k] == v for k, v in expected.items())
            and set(selected["effective_selection_keys"]) <= set(grant["scope"]["approved_selection_keys"])
        ):
            matches.append(grant)
    if not matches:
        codec.fail(
            "rendering_disclosure_scope_mismatch" if authorization["resolution"] == "exact" else "rendering_disclosure_unavailable",
            "presentation.authorization",
        )
    if len(matches) != 1:
        codec.fail("rendering_disclosure_ambiguous", "presentation.authorization")
    grant = matches[0]
    return {
        "kind": "definition",
        "definition": ref,
        "disclosure_authorization_id": grant["disclosure_authorization_id"],
        "disclosure_scope_hash": grant["scope_hash"],
        "effective_selection_keys": selected["effective_selection_keys"],
        "origin": origin,
    }


def application_projection(db, item_id, version):
    application = current_application(db, item_id=item_id, item_version=version)
    if application is None:
        return None
    policies = []
    for policy in application["policies"]:
        value = {k: policy[k] for k in ("policy_origin", "source_key", "notification_intent_id", "notification_policy_id")}
        presentation = load_presentation(db, policy["notification_policy_id"])
        policies.append(value | {"presentation": presentation, "presentation_hash": codec.presentation_hash(presentation)})
    return {
        "application_contract": "spine.notification-profile-application.v2",
        **{
            k: application[k]
            for k in (
                "notification_profile_application_id",
                "notification_profile_id",
                "notification_profile_revision_id",
                "selection_mode",
                "notification_profile_binding_id",
                "scope_chain",
                "suppress_template_keys",
                "replacements",
                "normalized_effective_policy_set_hash",
            )
        },
        "custom_additions": application["additions"],
        "normalized_profile_revision_hash": application["profile"]["revision"]["normalized_revision_hash"],
        "policies": policies,
        "effective_presentation_set_hash": codec.presentation_set_hash(
            [{"notification_policy_id": p["notification_policy_id"], "presentation_hash": p["presentation_hash"]} for p in policies]
        ),
    }


class RenderingAuthoring:
    """Private context hook; never construct from CLI/web request fields."""

    def __init__(self, db: Any, command: str, request: Any, permissions: Any, budget: Any) -> None:
        self.db, self.command, self.request, self.permissions, self.budget = db, command, request, permissions, budget
        self.pending = {}
        self.changes = []
        self.source_selections = {}
        self.before = None

    def plan(self, plan):
        if plan is None:
            return None
        value = dict(plan)
        value.pop("rendering_applications", None)
        return value

    def direct_notification(self, notification, *, edit=False):
        value = codec.exact(
            notification,
            {"authoring_contract"} if edit else {"authoring_contract", "target", "schedule", "late_handling"},
            {"target", "schedule", "late_handling", "presentation"} if edit else {"presentation"},
            field="notification",
        )
        if value["authoring_contract"] != "spine.notification-schedule-authoring.v2":
            codec.fail("unsupported_contract_version", "notification.authoring_contract")
        self.direct_selection = codec.normalize_selection(value.pop("presentation")) if "presentation" in value else None
        value["authoring_contract"] = "spine.notification-schedule-authoring.v1"
        return value

    def prepare_direct(self, policy, item_type, current=None):
        if current is None:
            selected = self.direct_selection or {"kind": "ordinary"}
            origin = {"kind": "direct"}
        else:
            prior = load_presentation(self.db, current["notification_policy_id"])
            origin = policy_origin(self.db, current)
            if self.direct_selection is None:
                if destination(self.db, policy) == destination(self.db, current):
                    # Copy-forward is not new use: retiring a catalog definition
                    # cannot silently strip or prevent retention of an old pin.
                    self.pending[policy["notification_policy_id"]] = prior
                    return False
                selected = (
                    {"kind": "ordinary"}
                    if prior["kind"] == "ordinary"
                    else {
                        "kind": "definition",
                        "definition": prior["definition"],
                        "effective_selection_keys": prior["effective_selection_keys"],
                        "authorization": {"resolution": "exact", "disclosure_authorization_id": prior["disclosure_authorization_id"]},
                    }
                )
            else:
                selected = self.direct_selection
        value = resolve(
            self.db, selected, policy=policy, item_type=item_type, origin=origin, permissions=self.permissions, budget=self.budget
        )
        self.pending[policy["notification_policy_id"]] = value
        return current is None or value != load_presentation(self.db, current["notification_policy_id"])

    def direct_facts(self, facts, policy_id):
        value = self.pending.get(policy_id) or load_presentation(self.db, policy_id)
        facts.update(presentation=value, presentation_hash=codec.presentation_hash(value))

    def prepare(self, prepared, policies, item_id, item_type, *, current=None):
        plan = (
            self.request.get("notification_plan") if self.command == "schedule.create" else self.request["patch"].get("notification_plan")
        )
        if self.command == "schedule.update" and "policy_presentations" in self.request["patch"]:
            self.prepare_edit(current, item_id, item_type)
            return
        if self.command == "schedule.update" and not prepared["replace_application"]:
            return
        apps = (plan or {}).get("rendering_applications", [])
        if not isinstance(apps, list) or len(apps) > 32:
            codec.fail("invalid_request", "rendering_applications")
        by_address = {}
        for entry in apps:
            entry = codec.exact(entry, {"source_kind", "source_key", "selection"}, field="rendering_applications")
            address = (entry["source_kind"], entry["source_key"])
            if address[0] not in {"profile_template", "custom_addition"} or address in by_address:
                codec.fail("semantic_conflict", "rendering_applications")
            by_address[address] = codec.normalize_selection(entry["selection"])
        application = prepared.get("application", prepared.get("desired_application"))
        profile = application.get("profile") if isinstance(application, Mapping) else None
        projection = prepared.get("projection") or {}
        origins = {o["policy_key"]: o for o in projection.get("policy_origins", [])}
        used = set()
        for key, normalized in policies:
            policy = normalized.value
            origin_fact = origins.get(key, {"policy_origin": "custom_addition", "source_key": key})
            kind = origin_fact["policy_origin"]
            origin = {"kind": kind}
            pinned = {"kind": "ordinary"}
            if kind in {"profile_template", "profile_replacement"}:
                invariant(profile is not None)
                origin |= {
                    "notification_profile_id": profile["notification_profile_id"],
                    "notification_profile_revision_id": profile["revision"]["notification_profile_revision_id"],
                    "template_key": origin_fact["source_key"],
                }
                template = next(t for t in profile["revision"]["templates"] if t["template_key"] == origin_fact["source_key"])
                pinned = template.get("rendering", {"kind": "ordinary"})
            address = (
                "profile_template" if kind in {"profile_template", "profile_replacement"} else "custom_addition",
                origin_fact["source_key"],
            )
            selection = by_address.get(address, {"kind": "ordinary"})
            if address in by_address:
                used.add(address)
            elif pinned["kind"] == "definition":
                codec.fail("missing_required_field", "rendering_applications")
            if kind == "profile_template" and selection["kind"] == "definition" and selection["definition"] != pinned.get("definition"):
                codec.fail("semantic_conflict", "rendering_applications")
            value = resolve(
                self.db, selection, policy=policy, item_type=item_type, origin=origin, permissions=self.permissions, budget=self.budget
            )
            self.pending[policy["notification_policy_id"]] = value
            if current is not None:
                source = policy.get("source_notification_policy_id")
                if source:
                    prior = load_presentation(self.db, source)
                    if prior != value:
                        self.changes.append(
                            {
                                "source_policy_id": source,
                                "before_hash": codec.presentation_hash(prior),
                                "after_hash": codec.presentation_hash(value),
                            }
                        )
        if used != set(by_address):
            codec.fail("semantic_conflict", "rendering_applications")

    def prepare_edit(self, current, item_id, item_type):
        patch = self.request["patch"]
        if set(patch) != {"policy_presentations"} or self.request["materialization"] != {"mode": "none"}:
            codec.fail("invalid_request", "patch.policy_presentations")
        entries = patch["policy_presentations"]
        if not isinstance(entries, list) or not 1 <= len(entries) <= 32:
            codec.fail("invalid_request", "patch.policy_presentations")
        by_id = {p["notification_policy_id"]: p for p in current if p["status"] == "active"}
        for entry in entries:
            entry = codec.exact(entry, {"notification_policy_id", "selection"}, field="patch.policy_presentations")
            identity = entry["notification_policy_id"]
            if identity not in by_id or identity in self.source_selections:
                codec.fail("semantic_conflict", "patch.policy_presentations")
            prior = load_presentation(self.db, identity)
            origin = policy_origin(self.db, by_id[identity])
            selected = resolve(
                self.db,
                entry["selection"],
                policy=by_id[identity],
                item_type=item_type,
                origin=origin,
                permissions=self.permissions,
                budget=self.budget,
            )
            self.source_selections[identity] = selected
            if selected != prior:
                self.changes.append(
                    {
                        "source_policy_id": identity,
                        "before_hash": codec.presentation_hash(prior),
                        "after_hash": codec.presentation_hash(selected),
                    }
                )
        if self.changes:
            self.before = facet_continuity.capture(self.db, item_id, int(self.request["target_version"]))

    def persist(self, item_id, version):
        rows = self.db.execute(
            "SELECT policy_id,source_notification_policy_id FROM notification_policies "
            "WHERE item_id=? AND version=? ORDER BY policy_id LIMIT 101",
            (item_id, version),
        ).fetchall()
        if len(rows) > 100:
            codec.fail("environment_failure", "capacity")
        for row in rows:
            identity, source = row
            if identity in self.pending:
                select_presentation(self.db, identity, self.pending[identity])
            elif source in self.source_selections:
                select_presentation(self.db, identity, self.source_selections[source])
            for change in self.changes:
                if change["source_policy_id"] == source:
                    change["policy_id"] = identity

    def verify_successor(self, item_id: str, version: int) -> None:
        # The item allocator advances its current pointer after the extension
        # callback returns. Verify against the committed-in-transaction successor,
        # not the still-current predecessor seen inside persist().
        if self.before is not None:
            facet_continuity.verify(self.before, facet_continuity.capture(self.db, item_id, version))

    def augment(self, facts, item_id, version):
        for policy in facts.get("policies", []):
            value = load_presentation(self.db, policy["notification_policy_id"])
            policy.update(presentation=value, presentation_hash=codec.presentation_hash(value))
        facts["notification_profile"] = application_projection(self.db, item_id, version)
        if self.command == "schedule.create":
            facts.setdefault("archetype", None)
        else:
            facts["presentation_changes"] = sorted(self.changes, key=lambda v: v["source_policy_id"]) if facts["truth_changed"] else []
