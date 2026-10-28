"""Verify an installed 0.11.2 wheel outside the checkout, using disposable data only.

Run with a fresh virtual environment's installed-wheel Python and no PYTHONPATH:
    /absolute/venv/bin/python -I /absolute/checkout/scripts/verify_people_wheel.py

No source-tree imports, internal command handlers, existing ledgers, workers,
delivery adapters, or real network sends are used. The HTTP checks use Flask's
public-route test client, not an externally listening service.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
from importlib import metadata, resources
from pathlib import Path

import spine
from spine.commands.people_runtime import API, CONTRACT, PeopleContracts, load_cursor_config
from spine.runtime.compatibility import resolve_tickerd_compatibility
from spine.web.contracts import registry as frozen_web_registry
from spine.web.facet_service import registry as frozen_facet_registry
from spine.web.http import PEOPLE_PATHS, create_app
from spine.web.read_contracts import ReadContracts
from spine.web.service import WebConfig

AT = "2026-10-24T10:00:00Z"
LEDGER_ID = "installed-wheel-fixture"
GROUP = {"owner_kind": "subject_group", "owner_group_id": "wheel-group"}
SUBJECT = {"owner_kind": "subject", "owner_subject_id": "owner"}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def run(module, arguments, request=None, *, environment=None, success=True):
    child_environment = dict(os.environ)
    child_environment.pop("PYTHONPATH", None)
    child_environment.pop("SPINE_DB", None)
    child_environment.pop("SPINE_PEOPLE_CURSOR_CONFIG", None)
    child_environment.update(environment or {})
    result = subprocess.run([sys.executable, "-I", "-m", module, *arguments],
        input=json.dumps(request) if request is not None else None, text=True, capture_output=True,
        env=child_environment, timeout=30, check=False)
    require((result.returncode == 0) == success,
            f"Public subprocess failed: {module} {arguments}: {result.returncode}, {result.stdout}, {result.stderr}")
    return json.loads(result.stdout)


def command(database, name, request=None, *, environment=None, flags=(), success=True):
    result = run("spine.commands.cli", ["--db", str(database), *flags, *name.split(".")], request,
                 environment=environment, success=success)
    require(result.get("ok") is success, f"Unexpected public command result: {name}: {result}")
    return result


def event_request(command_id, *, version="v4", participants=None):
    result = {
        "contract_version": "spine.schedule-create." + version,
        "command_id": command_id, "actor_subject_id": "owner", "created_at_utc": AT,
        "item": {"item_type": "event", "title": "Disposable wheel appointment", "event_detail": {"all_day": False}},
        "scheduled_time": {"time_basis": "local_instant", "local_date": "2035-01-02", "local_time": "10:00:00",
                           "timezone": "UTC", "timezone_database_version": {"kind": "system_current"}},
        "delivery": {"recipient_kind": "subject", "recipient_subject_id": "owner", "channel": "whatsapp",
                     "target": {"resolution": "explicit", "delivery_target_id": "wheel-route"}},
        "notification_plan": {"mode": "none", "custom_additions": [{"policy_key": "before",
            "schedule": {"kind": "once", "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-3600"}},
            "late_handling": {"kind": "skip"}}]},
        "materialization": {"mode": "none"},
    }
    if participants is not None:
        result["people"] = {"participants": participants}
    return result


def people_update(item_id, version, command_id, participants):
    return {"contract_version": CONTRACT, "command_id": command_id, "actor_subject_id": "owner",
            "item_id": item_id, "target_version": version, "updated_at_utc": AT, "people": {"participants": participants}}


def schedule_update(item_id, version, command_id, participants):
    return {"contract_version": "spine.schedule-update.v4", "command_id": command_id,
            "actor_subject_id": "owner", "item_id": item_id, "target_version": version, "updated_at_utc": AT,
            "patch": {"people": {"participants": participants}}, "materialization": {"mode": "none"}}


def provision(database, item):
    proposed = command(database, "web_access.plan", {"contract_version": "spine.trusted-web-provisioning.v2",
        "ledger_id": LEDGER_ID, "expected_access_epoch": "0",
        "operators": [{"operation": "create", "subject_id": person, "display_name": person.title(),
                       "activation_basis": "trusted_local_approval"} for person in ("owner", "bob")],
        "memberships": [{"operation": "create", "group_id": GROUP["owner_group_id"], "subject_id": person,
            "role": "owner" if person == "owner" else "member", "starts_at_utc": "2026-01-01T00:00:00Z"}
            for person in ("owner", "alice", "bob")],
        "item_adoptions": [{"operation": "create", "item_id": item["item_id"],
                            "expected_item_version": item["current_version"], "owner_scope": GROUP}]})
    require(proposed["can_apply"], f"Disposable provisioning plan rejected: {proposed}")
    applied = command(database, "web_access.apply", {"contract_version": "spine.trusted-web-provisioning.v2",
        "command_id": "wheel-provision", "actor_subject_id": "owner", "action_timestamp_utc": AT,
        "expected_access_epoch": "0", "plan": proposed})
    require(applied["effect"] == "web_access_applied", "Public provisioning did not commit")


def http_checks(database, cursor_path, item, timezone_version):
    config = WebConfig(str(database), LEDGER_ID)
    app = create_app(config, people_cursor_config=load_cursor_config(str(cursor_path)))
    client = app.test_client()
    response = client.get("/health/ready", headers={"Host": config.host})
    require(response.status_code == 200 and response.json["is_ready"], "Installed HTTP readiness failed")
    operators = client.get("/api/v1/operators", headers={"Host": config.host})
    require(operators.status_code == 200, f"Public operator discovery failed: {operators.json}")
    accounts = {row["subject_id"]: row["account_id"] for row in operators.json["operators"]}
    headers = {"Host": config.host, "Origin": config.origin, "Content-Type": "application/json",
               "X-Spine-Account-ID": accounts["owner"], "X-Spine-Selection-ID": "wheel-selection"}
    contracts = PeopleContracts.packaged()

    def post(path, body):
        result = client.post(path, data=json.dumps(body), headers=headers)
        require(result.status_code == 200 and result.json.get("ok"), f"Public HTTP failed: {path}: {result.status_code} {result.json}")
        require(result.headers["Cache-Control"] == "no-store", "Missing HTTP cache boundary")
        return result.json

    def people(name, body):
        response = post(PEOPLE_PATHS[name], {"contract_version": API, **body})
        contracts.validate("web-responses", response, definition=name, output=True)
        return response

    roster_request = {"contract_version": CONTRACT, "owner": GROUP, "limit": "1"}
    first = people("people.list", {"request": roster_request})
    next_page = people("people.list", {"request": roster_request | {"cursor": first["result"]["next_cursor"]}})
    require(first["result"]["subjects"][0]["subject_id"] != next_page["result"]["subjects"][0]["subject_id"],
            "Installed protected roster pagination repeated a row")
    shown = people("item.people.show", {"request": {"contract_version": CONTRACT, "item_id": item["item_id"]}})
    local = command(database, "item.people.show", {"contract_version": CONTRACT, "item_id": item["item_id"]})
    require(shown["result"] == local, "Public CLI/HTTP managed-role projection differs")
    changed = people("item.people.update", {"expected_access_epoch": shown["access_epoch"],
        "request": people_update(item["item_id"], local["current_version"], "wheel-http-people", ["alice"])})
    require(changed["result"]["work_changed"] is False, "Protected people update changed work")
    created = people("schedule.create", {"create_owner_scope": SUBJECT,
        "expected_access_epoch": changed["access_epoch"],
        "request": event_request("wheel-http-create", participants=["owner"])})
    updated = people("schedule.update", {"expected_access_epoch": created["access_epoch"],
        "request": schedule_update(created["result"]["item_id"], "1", "wheel-http-schedule-update", [])})
    require(updated["result"]["changed_dimensions"] == ["people"], "Protected scheduling did not use people-only semantics")
    detail = people("schedule.show", {"request": {"item_id": item["item_id"], "include": ["people"]}})
    require(detail["result"]["sections"]["people"]["availability"] == "available", "Protected optional people section unavailable")
    agenda = {"evaluated_at_utc": AT, "range_start_local": "2035-01-02T00:00:00", "range_end_local": "2035-01-03T00:00:00",
              "timezone": "UTC", "timezone_database_version": timezone_version, "item_ids": [item["item_id"]],
              "person_filter": {"subject_id": "alice"}, "include": ["people"]}
    require(len(people("agenda.show", {"request": agenda})["result"]["entries"]) == 1, "Protected person-filtered agenda failed")
    occurrence = {"item_id": item["item_id"], "range_basis": "original_schedule",
        "range_start": "2035-01-02T00:00:00", "range_end": "2035-01-05T00:00:00", "person_filter": {"subject_id": "bob"}}
    excluded = people("item.occurrences", {"request": occurrence})
    require(excluded["result"]["occurrences"] == [], "Nonmatching person did not narrow occurrences")
    occurrence["person_filter"] = {"subject_id": "alice"}
    occurrence["limit"] = "1"
    first_occurrence = people("item.occurrences", {"request": occurrence})["result"]
    next_occurrence = people("item.occurrences", {"request": occurrence | {"cursor": first_occurrence["next_cursor"]}})["result"]
    require(first_occurrence["occurrences"][0]["occurrence_id"] != next_occurrence["occurrences"][0]["occurrence_id"],
            "Installed occurrence continuation repeated a row")
    frozen = post("/api/v2/commands/schedule.show", {"contract_version": "spine.trusted-web-api.v2",
        "request": {"item_id": item["item_id"], "include": []}})
    require(frozen["result_contract"] == "spine.trusted-web-schedule-view.v1", "Frozen v2 result contract drifted")
    require("people" not in frozen["result"]["sections"], "Frozen v2 section envelope broadened")
    return created["result"]["item_id"]


def main():
    require("PYTHONPATH" not in os.environ, "Unset PYTHONPATH before installed-wheel verification")
    require(Path(spine.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()),
            "Spine is not imported from this installed environment")
    require(spine.__version__ == metadata.version("spine-ledger") == "0.11.2", "Expected exact installed release 0.11.2")
    dependency = resolve_tickerd_compatibility()
    require(dependency.descriptor_sha256 == "215f9aa6b54e6c0e6186796a55d78e1c5a270adc9b3ccefb433df5a3bb87b58b",
            "Tickerd does not match the pinned capability descriptor")
    contracts = PeopleContracts.packaged()
    require(len(contracts.schemas) == 36 and len(contracts.companion["commands"]) == 8, "Incomplete installed people family")
    packaged = resources.files("spine.contracts").joinpath("people")
    pins = json.loads(packaged.joinpath("pins.v1.json").read_bytes())
    for name, digest in pins["files"].items():
        require(hashlib.sha256(packaged.joinpath(*name.split("/")).read_bytes()).hexdigest() == digest, "Packaged people asset mismatch")
    frozen_web_registry()
    frozen_facet_registry()
    ReadContracts.packaged()
    with tempfile.TemporaryDirectory(prefix="spine-people-installed-") as temporary:
        root = Path(temporary)
        database = root / "disposable.sqlite"
        run("spine.ledger.migrate", ["--db", str(database), "--initialize-if-empty"])
        info = command(database, "system.info", {})
        require(info["ledger_schema_version"] == "19", "Unexpected fresh ledger schema")
        for person in ("owner", "alice", "bob"):
            command(database, "subject.upsert", {"command_id": "wheel-person-" + person, "actor_subject_id": "owner",
                "subject_id": person, "subject_kind": "person", "display_name": person.title(), "updated_at_utc": AT})
        command(database, "subject_group.upsert", {"command_id": "wheel-group", "actor_subject_id": "owner",
            "group_id": GROUP["owner_group_id"], "display_name": "Arbitrary wheel group", "updated_at_utc": AT})
        command(database, "delivery_target.upsert", {"command_id": "wheel-route", "actor_subject_id": "owner",
            "delivery_target_id": "wheel-route", **SUBJECT, "channel": "whatsapp", "adapter_name": "openclaw",
            "target_ref": "wheel-fixture-never-send", "updated_at_utc": AT})
        initial_request = event_request("wheel-v4-create", participants=["bob", "alice"])
        initial_request["scheduled_time"]["recurrence"] = {"rules": [{"frequency": "DAILY", "interval": "1",
            "seed": "2035-01-02T10:00:00", "start_bound": "2035-01-02T10:00:00", "end_condition": {"kind": "count", "count": "3"}}]}
        item = command(database, "schedule.create", initial_request)
        require(item["phases"]["delivery"] == "not_attempted" and item["materialization"]["work_instance_count"] == "0",
                "Authoring unexpectedly attempted delivery/materialized work")
        preview = command(database, "item.people.update", people_update(item["item_id"], "1", "wheel-preview", ["owner"]),
                          flags=("--dry-run",))
        require(preview["dry_run"] and preview["current_version"] == "2", "Standalone dry-run did not preview next version")
        current = command(database, "item.people.show", {"contract_version": CONTRACT, "item_id": item["item_id"]})
        require(current["current_version"] == "1", "Dry-run persisted its item version")
        request = people_update(item["item_id"], "1", "wheel-people-change", ["alice"])
        changed = command(database, "item.people.update", request)
        replay = command(database, "item.people.update", request)
        require(changed["receipt"] == replay["receipt"] and replay["effect"] == "item_people_replay", "Standalone replay changed evidence")
        noop = command(database, "item.people.update", people_update(item["item_id"], "2", "wheel-people-noop", ["alice"]))
        require(noop["effect"] == "item_people_noop" and noop["associations"] == changed["associations"], "No-op replaced supporting rows")
        history = command(database, "item.people.show", {"contract_version": CONTRACT, "item_id": item["item_id"], "version": "1"})
        require([row["subject_id"] for row in history["people"]["associations"]] == ["alice", "bob"], "Historical role decoding drifted")
        item = command(database, "schedule.update", schedule_update(item["item_id"], "2", "wheel-v4-update", ["alice", "bob"]))
        require(item["changed_dimensions"] == ["people"] and item["current_version"] == "3",
                "Scheduling v4 did not use one people-only version")
        for version in ("v2", "v3"):
            old = command(database, "schedule.create", event_request("wheel-" + version, version=version))
            require(old["response_contract"] == "spine.schedule-create-response." + version, "Frozen scheduling result changed")
        for version in ("v1", "v2"):
            shown = command(database, "schedule.show", {"contract_version": "spine.schedule-show." + version,
                "item_id": item["item_id"], "include": ["attempts"]})
            require(shown["response_contract"] == "spine.schedule-show." + version and not shown["side_effect_attempts"],
                    "Frozen read result changed or delivery occurred")
            require("people" not in shown, "Frozen local read broadened")
        provision(database, item)
        cursor_path = root / "people-cursor.json"
        cursor = {"contract_version": "spine.people-cursor-config.v1", "key_id": "wheel", "key_generation": "1",
                  "ledger_instance_id": info["ledger_instance_id"], "secret_hex": secrets.token_hex(32)}
        with os.fdopen(os.open(cursor_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
            json.dump(cursor, stream)
        environment = {"SPINE_PEOPLE_CURSOR_CONFIG": str(cursor_path)}
        request = {"contract_version": CONTRACT, "owner": GROUP, "limit": "1"}
        names, token = [], None
        for _ in range(4):
            page = command(database, "people.list", request | ({"cursor": token} if token else {}), environment=environment)
            names.extend(row["subject_id"] for row in page["subjects"])
            token = page["next_cursor"]
            if token is None:
                break
            require(token.startswith("pc1."), "Wrong roster cursor family")
        require(token is None and names == ["alice", "bob", "owner"], "Installed roster continuation lost/duplicated subjects")
        http_item = http_checks(database, cursor_path, item, info["timezone_database_version"])
        for identity in (item["item_id"], http_item):
            shown = command(database, "schedule.show", {"item_id": identity, "include": ["work", "attempts"]})
            require(not shown["work_instances"] and not shown["side_effect_attempts"], "Installed checks generated work or delivery")
        run("spine.ledger.migrate", ["--db", str(database), "--verify-only"])
    print(json.dumps({"result": "PASS", "version": spine.__version__, "schema": "19", "packaged_schema_documents": 36,
        "public_cli": True, "public_http_routes": 8, "historical_noop_replay_dry_run": True, "pc1_pagination": True,
        "frozen_interfaces": True, "deep_disposable_verification": True, "real_sends": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
