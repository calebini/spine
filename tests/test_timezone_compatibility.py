"""Real TZif and CLI regressions for the automatic authored-zone evidence boundary."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from jsonschema import Draft202012Validator

from spine import timezones
from spine.commands import handle
from spine.core.errors import SpineValidationError
from spine.core.notification_rendering import render_notification
from spine.core.schedule import expand_rule, resolve_local_instant
from spine.ledger import connect
from spine.ledger.temporal_bindings import target_from_source
from spine.runtime.timezone_baselines import main, provision
from tests import test_notification_rendering as rendering_examples
from tests import test_schedule_operations_command as schedule_examples

FIXTURES = Path(__file__).parent / "fixtures/timezones"
ROOT = Path(__file__).parents[1]
ZONES = ["Europe/Paris", "America/Chicago", "America/Toronto", "America/Winnipeg", "Europe/Dublin"]


@pytest.fixture
def provider(tmp_path, monkeypatch):
    root = tmp_path / "provider"
    shutil.copytree(FIXTURES / "2026c", root)
    catalog = tmp_path / "baseline.json"
    provision(
        root=root,
        expected_version="2026c",
        zones=ZONES,
        catalog=catalog,
        build_id="fixture-zic-2022g-fat",
        origin="authenticated synthetic test fixture",
        artifact_sha256="e4a178a4477f3d0ea77cc31828ff72aa38feff8d61aa13e7e99e142e9d902be4",
    )
    monkeypatch.setattr(timezones, "TZPATH", (str(root),))
    monkeypatch.setenv("SPINE_TIMEZONE_BASELINES", str(catalog))
    timezones._logged.clear()
    return root, catalog


def install(root, version="2026e"):
    shutil.copytree(FIXTURES / "2026e", root, dirs_exist_ok=True)
    (root / "tzdata.zi").write_text(f"# version {version}\n")


def resolve(zone, local="2026-10-25T02:30:00", version="2026c"):
    return resolve_local_instant(local, timezone=zone, timezone_database_version=version)


@pytest.mark.parametrize("version", ["2026e", "2027z", "2025a", "2026c-rearguard"])
def test_unknown_forward_reverse_and_suffix_runtime_labels_admit_identical_bytes(provider, version, caplog):
    root, catalog = provider
    before = catalog.read_bytes()
    exact = {zone: resolve(zone) for zone in ZONES[:3]}
    install(root, version)
    for zone in ZONES[:3]:
        assert resolve(zone) == exact[zone]
        assert resolve(zone).timezone_database_version == "2026c"
        resolve(zone)
    assert catalog.read_bytes() == before
    records = [json.loads(row.message) for row in caplog.records]
    assert len(records) == 3
    assert {row["runtime_version"] for row in records} == {version}
    assert all(row["requested_version"] == "2026c" and row["diagnostic_code"] == "timezone_compatible_substitution" for row in records)
    assert records[0]["tzif_sha256"] == hashlib.sha256((root / "Europe/Paris").read_bytes()).hexdigest()


@pytest.mark.parametrize("zone", ["America/Winnipeg", "Europe/Dublin"])
def test_changed_zones_fail_after_upgrade(provider, zone):
    root, _ = provider
    resolve(zone)
    install(root)
    with pytest.raises(SpineValidationError, match="do not match"):
        resolve(zone)


@pytest.mark.parametrize(
    "local",
    [
        "1800-01-01T12:00:00",
        "1911-03-10T23:55:00",
        "1945-09-30T02:30:00",
        "2026-03-29T02:30:00",
        "2026-10-25T02:30:00",
        "2026-03-08T02:30:00",
        "2026-11-01T01:30:00",
        "2500-03-28T02:30:00",
        "9998-07-01T12:00:00",
    ],
)
def test_historical_gap_fold_and_footer_resolution_preserve_pins(provider, local):
    root, _ = provider
    reference = [resolve(zone, local) for zone in ZONES[:3]]
    install(root)
    assert [resolve(zone, local) for zone in ZONES[:3]] == reference


def test_count_seek_uses_verified_gap_bytes_and_earliest_fold(provider):
    root, _ = provider
    rule = {
        "frequency": "DAILY",
        "seed": "2026-03-27T02:30:00",
        "start_bound": "2026-03-27T02:30:00",
        "end_condition": {"kind": "count", "count": "4"},
    }
    args = dict(
        time_basis="local_instant",
        timezone="Europe/Paris",
        timezone_database_version="2026c",
        range_start="2026-03-30T00:00:00",
        range_end="2026-04-04T00:00:00",
    )
    reference = expand_rule(rule, **args)
    install(root)
    assert expand_rule(rule, **args) == reference
    assert [row.scheduled_fact for row in reference.candidates] == ["2026-03-30T02:30:00", "2026-03-31T02:30:00"]
    assert resolve("Europe/Paris", "2026-03-29T02:30:00") is None
    assert resolve("Europe/Paris").utc_instant == "2026-10-25T00:30:00Z"


def test_missing_baseline_and_later_modification_fail_without_enrollment(provider, monkeypatch):
    root, catalog = provider
    before = catalog.read_bytes()
    install(root)
    resolve("Europe/Paris")
    data = bytearray((root / "Europe/Paris").read_bytes())
    data[data.index(b"CEST")] = ord("X")  # valid TZif, different complete bytes
    (root / "Europe/Paris").write_bytes(data)
    with pytest.raises(SpineValidationError, match="do not match"):
        resolve("Europe/Paris")
    with pytest.raises(SpineValidationError, match="do not match"):
        resolve("Europe/Paris", version="2026c-rearguard")
    monkeypatch.delenv("SPINE_TIMEZONE_BASELINES")
    with pytest.raises(SpineValidationError, match="unavailable"):
        resolve("America/Chicago")
    assert catalog.read_bytes() == before
    assert resolve("America/Chicago", version="2026e")


def test_warm_global_zoneinfo_and_live_provider_cache_cannot_override_bytes(provider):
    root, _ = provider
    ZoneInfo("Europe/Paris")
    assert timezones.system_timezone_database_version() == "2026c"
    original = resolve("Europe/Paris")
    install(root)
    assert timezones.system_timezone_database_version() == "2026e"
    assert resolve("Europe/Paris") == original
    shutil.copyfile(root / "America/Chicago", root / "Europe/Paris")
    with pytest.raises(SpineValidationError, match="do not match"):
        resolve("Europe/Paris")


def test_selected_provider_never_borrows_metadata_or_zone_from_other_root(provider, monkeypatch, tmp_path):
    root, _ = provider
    other = tmp_path / "other"
    shutil.copytree(FIXTURES / "2026e", other)
    (root / "tzdata.zi").unlink()
    monkeypatch.setattr(timezones, "TZPATH", (str(root), str(other)))
    with pytest.raises(SpineValidationError, match="capture failed"):
        resolve("Europe/Paris")
    with pytest.raises(SpineValidationError):
        timezones.system_timezone_database_version()


def test_provider_update_during_capture_fails(provider, monkeypatch):
    root, _ = provider
    original = timezones._capture_file

    def racing(path, limit):
        result = original(path, limit)
        if path.name == "Paris":
            (root / "tzdata.zi").write_text("# version 2027a\n")
        return result

    monkeypatch.setattr(timezones, "_capture_file", racing)
    with pytest.raises(SpineValidationError, match="changed during capture"):
        resolve("Europe/Paris")


@pytest.mark.parametrize("malformation", ["unknown", "duplicate", "digest", "size", "method", "text", "empty"])
def test_closed_catalog_rejects_invalid_evidence(provider, malformation):
    root, catalog = provider
    install(root)
    payload = json.loads(catalog.read_bytes())
    entry = payload["baselines"][0]
    if malformation == "unknown":
        entry["approved_runtime"] = "2026e"
    elif malformation == "duplicate":
        payload["baselines"].append({**entry, "build_id": "other-build", "evidence_id": "other-id"})
    elif malformation == "digest":
        entry["tzif_sha256"] = "not-a-hash"
    elif malformation == "size":
        entry["tzif_size"] = True
    elif malformation == "method":
        entry["method"] = "semantic_sample"
    elif malformation == "text":
        entry["build_id"] = "   "
    else:
        payload["baselines"] = []
    catalog.write_text(json.dumps(payload))
    with pytest.raises(SpineValidationError):
        resolve("Europe/Paris")


@pytest.mark.parametrize("payload", [b'{"contract_version":1,"contract_version":2}', b"{", b"[" * 2000, b"x" * (timezones.MAX_BYTES + 1)])
def test_invalid_json_is_closed(payload):
    with pytest.raises(SpineValidationError):
        timezones.parse_catalog(payload)


@pytest.mark.parametrize("change", [lambda b: b[:40], lambda b: b[:-1], lambda b: b + b"garbage"])
def test_malformed_complete_tzif_fails_even_with_exact_version(provider, change):
    root, _ = provider
    path = root / "Europe/Paris"
    path.write_bytes(change(path.read_bytes()))
    with pytest.raises(SpineValidationError):
        resolve("Europe/Paris")


def test_provisioning_refuses_relabel_and_overwrite_and_packages_closed_schema(provider):
    root, catalog = provider
    original = catalog.read_bytes()
    schema = json.loads((ROOT / "contracts/timezone-compatibility.schema.json").read_bytes())
    Draft202012Validator(schema).validate(json.loads(original))
    packaged = files("spine.contracts").joinpath("timezone-compatibility.schema.json").read_bytes()
    assert packaged == (ROOT / "contracts/timezone-compatibility.schema.json").read_bytes()
    args = [
        "--root",
        str(root),
        "--expected-version",
        "2026c",
        "--zone",
        "Europe/Paris",
        "--catalog",
        str(catalog),
        "--build-id",
        "different-build",
        "--origin",
        "test",
        "--artifact-sha256",
        "a" * 64,
    ]
    assert main(args) == 1
    assert catalog.read_bytes() == original
    install(root)
    assert main(args) == 1
    assert catalog.read_bytes() == original


def test_rendering_hashes_and_temporal_binding_conversion_remain_authored(provider):
    root, _ = provider
    source = rendering_examples.NotificationRenderingTests()._source(
        attempted_at_utc="2026-08-23T18:00:00Z", target_scheduled_fact="2026-08-24T14:00:00", target_at_utc="2026-08-24T18:00:00Z"
    )
    source["timezone_database_version"] = "2026c"
    source["display_timezone"] = "America/Toronto"
    bound = {"resolved_source_utc": "2026-10-25T00:30:00Z", "timezone": "Europe/Paris", "timezone_database_version": "2026c"}
    exact_rendering = render_notification(source)
    exact_binding = target_from_source(bound, 7200)
    install(root)
    assert render_notification(source) == exact_rendering
    assert target_from_source(bound, 7200) == exact_binding
    assert exact_binding["timezone_database_version"] == "2026c"


def test_cli_agenda_and_notification_projection_preserve_canonical_facts(provider, tmp_path):
    root, catalog = provider
    helper = schedule_examples.ScheduleOperationsCommandTests()
    helper.setUp()
    try:
        for request in (helper.event_request("timezone-single"), helper.task_request("timezone-recurring")):
            request["scheduled_time"]["timezone_database_version"] = {"kind": "explicit", "version": "2026c"}
            result = handle("schedule.create", request, helper.context)
            assert result["ok"], result
        db = tmp_path / "spine.sqlite"
        disk = connect(db)
        helper.connection.backup(disk)
        disk.close()
    finally:
        helper.tearDown()
    request = helper.agenda_request(limit="100")
    request["timezone_database_version"] = {"kind": "explicit", "version": "2026c"}
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request))
    env = {**os.environ, "PYTHONTZPATH": str(root), "PYTHONPATH": str(ROOT / "src"), "SPINE_TIMEZONE_BASELINES": str(catalog)}
    command = [sys.executable, "-m", "spine.commands.cli", "--db", str(db), "--input", str(request_path), "agenda", "show"]
    with connect(db) as connection:
        before = list(connection.iterdump())
    exact = subprocess.run(command, env=env, capture_output=True, text=True, check=True)
    expected = json.loads(exact.stdout)
    assert expected["ok"] and len(expected["entries"]) == 2
    install(root)
    compatible = subprocess.run(command, env=env, capture_output=True, text=True, check=True)
    assert json.loads(compatible.stdout) == expected
    assert "timezone_compatible_substitution" in compatible.stderr
    assert all(row["source_timezone_database_version"] == "2026c" for row in expected["entries"])
    with connect(db) as connection:
        assert list(connection.iterdump()) == before
    catalog.unlink()
    rejected = subprocess.run(command, env=env, capture_output=True, text=True)
    assert rejected.returncode != 0
    assert json.loads(rejected.stdout)["ok"] is False


def test_local_calendar_opportunities_preserve_hashes_across_upgrade(provider):
    from spine.core.notifications import expand_notification_policy
    from tests import test_notification_engine as examples

    root, _ = provider
    policy = examples.NotificationScheduleEngineTests()._policy(
        schedule={
            "kind": "repeat_window",
            "start": {"kind": "absolute_utc", "at_utc": "2026-03-27T00:00:00Z"},
            "stop": {
                "kind": "target_offset",
                "offset_basis": "calendar_days",
                "offset_days": "-1",
                "local_time": "12:00:00",
                "timezone": "Europe/Paris",
                "timezone_database_version": "2026c",
            },
            "stop_inclusive": False,
            "cadence": {
                "kind": "local_calendar",
                "frequency": "DAILY",
                "seed_local_date": "2026-03-27",
                "local_time": "02:30:00",
                "timezone": "Europe/Paris",
                "timezone_database_version": "2026c",
            },
        },
        late={"kind": "skip"},
    )
    args = dict(
        targets=[{"target_scheduled_fact": "2026-04-04T12:00:00Z", "target_utc_instant": "2026-04-04T12:00:00Z"}],
        evaluated_at_utc="2026-03-01T00:00:00Z",
        range_start_utc="2026-03-27T00:00:00Z",
        range_end_utc="2026-04-04T00:00:00Z",
    )
    exact = expand_notification_policy(policy.value, **args)
    install(root)
    assert expand_notification_policy(policy.value, **args) == exact
    assert len(exact.opportunities) == 7


def test_worker_processor_renders_and_persists_before_fake_transport(provider, caplog):
    from spine.adapters import NormalizedOpenClawResult, OpenClawNotificationProcessor, build_openclaw_outbound_message
    from spine.ledger import get_notification_rendering, get_side_effect_attempt, get_work_instance
    from spine.services import start_work
    from tests.test_openclaw_adapter import FakeEnvelope

    root, _ = provider
    helper = schedule_examples.ScheduleOperationsCommandTests()
    helper.setUp()
    try:
        request = helper.event_request("timezone-worker", materialize=True)
        request["scheduled_time"]["timezone_database_version"] = {"kind": "explicit", "version": "2026c"}
        result = handle("schedule.create", request, helper.context)
        assert result["ok"], result
        row = helper.connection.execute("SELECT work_instance_id FROM work_instances ORDER BY eligible_at_utc LIMIT 1").fetchone()
        work_id = row["work_instance_id"]
        work = get_work_instance(helper.connection, work_id)
        at = work["eligible_at_utc"]
        start_work(helper.connection, work_instance_id=work_id, started_at_utc=at)
        work = get_work_instance(helper.connection, work_id)
        exact = build_openclaw_outbound_message(
            helper.connection, work_row=work, trace_id="tz-test", causation_id="ROOT:tz-test", created_at_utc=at
        )
        install(root)
        compatible = build_openclaw_outbound_message(
            helper.connection, work_row=work, trace_id="tz-test", causation_id="ROOT:tz-test", created_at_utc=at
        )
        assert compatible == exact
        sent = []

        def fake_sender(message):
            assert get_side_effect_attempt(helper.connection, message.attempt_id)["attempt_status"] == "started"
            rendered = get_notification_rendering(helper.connection, attempt_id=message.attempt_id)
            assert rendered["body_text"] == message.body_text
            assert message.notification_rendering.source_input["timezone_database_version"] == "2026c"
            sent.append(message)
            return NormalizedOpenClawResult(status="delivered", provider_ref="fake-tz-test", reason_code="openclaw_delivered")

        outcome = OpenClawNotificationProcessor(sender=fake_sender)(
            helper.connection, work, FakeEnvelope(actual_start_ts=datetime.fromisoformat(at.replace("Z", "+00:00")))
        )
        assert outcome.status == "succeeded"
        assert len(sent) == 1
        assert any("timezone_compatible_substitution" in row.message for row in caplog.records)
    finally:
        helper.tearDown()
