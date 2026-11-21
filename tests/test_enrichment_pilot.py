"""Trusted-local one-reminder pilot: no credentials, network or real ledger."""

import hashlib
import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import UTC, datetime, timedelta
from importlib.resources import files
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from spine.adapters.contextual_experiment import dump
from spine.adapters.contextual_live import LiveLauncher
from spine.adapters.enrichment import EnrichmentStore
from spine.adapters.enrichment_pilot import PilotStore
from spine.ledger.identity import read_ledger_instance_id
from spine.runtime.contextual_experiment_demo import seed
from spine.runtime.enrichment_pilot import PREVIEW, PROVIDER, STORE, main, validator
from spine.services.contextual_experiment import utc
from spine.services.work import start_work
from spine.web.provisioning import apply, plan

OWNER = Path(__file__).parents[2] / "impetus/src"
FIXTURE = Path(__file__).parent / "fixtures/contextual_live_worker.py"


class Trial:
    def command(self, action, *args):
        return main([action, "--state-dir", str(self.state), *args], clock=lambda: self.now)

    def preview(self, namespace=None):
        result = self.command("preview", "--db", str(self.path), "--config", str(self.configuration),
                              "--ledger-id", namespace or self.namespace, "--provider-config", str(self.provider),
                              "--impetus-python", sys.executable, "--impetus-state", str(self.owner_state))
        receipt = json.loads(self.capsys.readouterr().out)
        return result, receipt

    def capture(self, approval, owner_ref="agreed-offline-test-policy"):
        result = self.command("capture", "--db", str(self.path), "--config", str(self.configuration),
                              "--approve-preview-sha256", approval, "--impetus-approval-ref", owner_ref)
        return result, json.loads(self.capsys.readouterr().out)

    def show(self, *args):
        result = self.command("show", *args)
        return result, json.loads(self.capsys.readouterr().out)


@pytest.fixture
def trial(tmp_path, capsys):
    run = Trial()
    run.capsys = capsys
    run.now = datetime(2060, 1, 1, 10, tzinfo=UTC)
    run.path = tmp_path / "source.sqlite3"
    run.state = tmp_path / "spine-pilot"
    run.owner_state = tmp_path / "impetus-pilot"
    run.configuration = tmp_path / "pilot.json"
    run.provider = tmp_path / "model.json"
    run.db, run.work, config = seed(run.path, run.now)
    run.namespace = read_ledger_instance_id(run.db)
    with closing(run.db):
        row = run.db.execute("SELECT access_epoch FROM ledger_access_state WHERE singleton_id=1").fetchone()
        epoch = str(row[0]) if row else "0"
        item = config["opted_in_item_ids"][0]
        proposed = plan(run.db, dict(
            contract_version="spine.trusted-web-provisioning.v1", ledger_id="pilot-test-audience", expected_access_epoch=epoch,
            item_adoptions=[dict(operation="create", item_id=item, owner_scope={"owner_kind": "subject", "owner_subject_id": "owner"},
                                 expected_item_version="1")],
        ))
        assert proposed["can_apply"]
        apply(run.db, dict(contract_version="spine.trusted-web-provisioning.v1", command_id="pilot-adopt", actor_subject_id="owner",
                           action_timestamp_utc=utc(run.now), expected_access_epoch=epoch, plan=proposed))
        config.update(contract="spine.notification-enrichment-config.v1", synthetic_only=False,
                      work_instance_id=run.work, actor_subject_id="owner", retention_reference="fictional-private-test-policy")
        run.configuration.write_text(json.dumps(config))
        run.provider.write_bytes(files("spine.contracts").joinpath("contextual_notification/live-configuration.json").read_bytes())
        run.owner_state.mkdir(mode=0o700)
        (run.owner_state / "state.sqlite3").touch(mode=0o600)
        yield run


def test_preview_refusals_and_local_metadata_only(trial):
    before = list(trial.db.iterdump())
    with patch("spine.runtime.enrichment_pilot.LiveLauncher", side_effect=AssertionError("no worker entry")):
        assert trial.preview("another-ledger") == (
            1, dict(contract="spine.notification-enrichment-pilot.v1", status="refused",
                    reason="pilot_ledger_mismatch", selected=False, sent=False),
        )
        assert not trial.state.exists()
        result, receipt = trial.preview()
        assert result == 0 and receipt["status"] == "preview_ready"
        assert "Synthetic" not in json.dumps(receipt)
        private = json.loads((trial.state / PREVIEW).read_text())
        validator("preview").validate(private)
        validator("receipt").validate(receipt)
        assert private["request"]["context"]["event"]["title"] == "Synthetic lesson"
        assert "Do not disclose" not in json.dumps(private)
        assert "synthetic@example.invalid" not in json.dumps(private)
        assert private["request"]["allowed_tools"] == []
        assert private["request"]["limits"]["tool_calls"] == 0
        assert private["request"]["context"]["facets"] == []
        assert trial.capture("0" * 64)[1]["reason"] == "pilot_exact_approval_required"
        assert trial.capture(receipt["approval_sha256"], " ")[1]["reason"] == "pilot_impetus_approval_required"
        assert trial.show() == (0, receipt)
        assert trial.preview()[0] == 1  # Never rewrite or implicitly reset the designated state.
    assert list(trial.db.iterdump()) == before
    for name in (PREVIEW, STORE, PROVIDER):
        assert (trial.state / name).stat().st_mode & 0o077 == 0
    with pytest.raises(sqlite3.OperationalError, match="no such table: enrichment_profile"):
        EnrichmentStore(trial.state / STORE, trial.namespace)


def test_drift_expiry_and_missing_owner_store_fail_before_entry(trial):
    _, receipt = trial.preview()
    approval = receipt["approval_sha256"]
    before = trial.configuration.read_text()
    with patch("spine.runtime.enrichment_pilot.LiveLauncher") as launcher:
        trial.configuration.write_text(json.dumps(json.loads(before) | {"retention_reference": "changed-agreement"}))
        assert trial.capture(approval)[1]["reason"] == "pilot_source_drift"
        launcher.return_value.exchange.assert_not_called()
        trial.configuration.write_text(before)
        (trial.owner_state / "state.sqlite3").unlink()
        assert trial.capture(approval)[0] == 1
        trial.now += timedelta(seconds=90)
        assert trial.capture(approval)[1]["reason"] == "pilot_outside_entry_window"
        assert launcher.call_count == 1
    assert trial.show()[1]["status"] == "preview_ready"


def test_work_claimed_after_preview_refuses_before_entry(trial):
    _, receipt = trial.preview()
    start_work(trial.db, work_instance_id=trial.work, started_at_utc=utc(trial.now))
    with patch("spine.runtime.enrichment_pilot.LiveLauncher") as launcher:
        assert trial.capture(receipt["approval_sha256"])[1]["reason"] == "pilot_work_not_eligible"
        launcher.return_value.exchange.assert_not_called()
    assert trial.show()[1]["status"] == "preview_ready"


def test_lost_spawn_and_restart_do_not_contact_impetus_again(trial):
    _, receipt = trial.preview()
    approval = receipt["approval_sha256"]
    before = list(trial.db.iterdump())
    launcher = Mock()
    launcher.exchange.side_effect = OSError("private details should not be printed")
    with patch("spine.runtime.enrichment_pilot.LiveLauncher", return_value=launcher):
        assert trial.capture(approval)[1]["reason"] == "pilot_input_or_state_unavailable"
        launcher.exchange.assert_called_once()
        assert launcher.exchange.call_args.args[0] == "invoke"
        request = launcher.exchange.call_args.args[1]
        assert hashlib.sha256(request).hexdigest() == receipt["request_sha256"]
        assert request == dump(json.loads((trial.state / PREVIEW).read_text())["request"]) + b"\n"
        assert trial.capture(approval)[1]["status"] == "launch_consumed_no_local_result"
        assert trial.show()[1]["status"] == "launch_consumed_no_local_result"
        launcher.exchange.assert_called_once()
    assert list(trial.db.iterdump()) == before


def test_atomic_once_marker_across_connections(trial):
    _, receipt = trial.preview()
    with closing(PilotStore(trial.state / STORE, trial.namespace)) as first, \
            closing(PilotStore(trial.state / STORE, trial.namespace)) as second:
        opportunity, _ = first.for_work(trial.work)
        assert first.approve_and_mark(opportunity, receipt["approval_sha256"], "first", utc(trial.now))
        assert not second.approve_and_mark(opportunity, receipt["approval_sha256"], "second", utc(trial.now))
        assert second.conn.execute("SELECT owner_approval_ref FROM pilot_approval").fetchone()[0] == "first"


@pytest.mark.skipif(not (OWNER / "impetus").is_dir(), reason="Independent Impetus checkout required")
def test_connected_capture_records_mock_count_and_generation_but_never_selects(trial):
    # The independent fixture blocks socket calls, uses a fake clock and has no real credentials.
    trial.owner_state = trial.owner_state.parent / "independent-state"
    command = [sys.executable, str(FIXTURE), "--state", str(trial.owner_state), "--now", utc(trial.now)]
    env = {"PYTHONPATH": str(OWNER)}
    subprocess.run([*command, "init", "--namespace", trial.namespace], env=env, check=True, capture_output=True)

    _, receipt = trial.preview()
    before = list(trial.db.iterdump())
    with patch("spine.runtime.enrichment_pilot.LiveLauncher", side_effect=lambda _, **kw: LiveLauncher(command, environment=env, **kw)):
        result, captured = trial.capture(receipt["approval_sha256"])
    assert result == 0 and captured["capture_reason"] == "succeeded"
    assert not captured["selected"] and not captured["sent"]
    result, private = trial.show("--private")
    assert result == 0
    [record] = private["captures"]
    assert not record["usable_for_hypothetical_selection"]
    assert record["execution"]["result"]["text"] == "Hope it goes well!"
    assert len(record["execution"]["calls"]) == 2
    assert list(trial.db.iterdump()) == before


def test_pilot_schema_resource_matches_source():
    name = "contextual_notification/enrichment-pilot-v1.schema.json"
    assert files("spine.contracts").joinpath(name).read_bytes() == (Path(__file__).parents[1] / "contracts" / name).read_bytes()
    assert not validator("preview").is_valid({"contract": "spine.notification-enrichment-pilot.v1"})
