"""Disposable synthetic source -> independent deterministic worker -> review capture."""

import argparse
import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from spine.adapters.contextual_experiment import CaptureStore, LocalImpetus, Source
from spine.commands import CommandContext, handle
from spine.ledger import connect, initialize_schema
from spine.services.contextual_experiment import Experiment, utc


def seed(path, now, *, archetype="lesson"):
    """Public authoring commands against a fresh isolated ledger; never send."""
    if Path(path).exists():
        raise ValueError("fresh_demo_ledger_required")
    ledger = connect(path)
    initialize_schema(ledger)
    context = CommandContext(ledger=ledger)
    counter = 0

    def call(name, value):
        nonlocal counter
        counter += 1
        response = handle(name, value, context)
        if not response["ok"]:
            raise ValueError(response)
        return response

    call(
        "subject.upsert",
        dict(
            command_id="synthetic-owner",
            actor_subject_id="owner",
            subject_id="owner",
            subject_kind="person",
            display_name="Synthetic Owner",
            updated_at_utc=utc(now),
        ),
    )
    call(
        "delivery_target.upsert",
        dict(
            command_id="synthetic-route",
            actor_subject_id="owner",
            delivery_target_id="synthetic-capture-route",
            owner_kind="subject",
            owner_subject_id="owner",
            channel="whatsapp",
            adapter_name="openclaw",
            target_ref="synthetic@example.invalid",
            updated_at_utc=utc(now),
        ),
    )
    kind = call(
        "item_archetype.create",
        dict(
            contract_version="spine.item-archetypes.v1",
            command_id="synthetic-archetype",
            actor_subject_id="owner",
            action_timestamp_utc=utc(now),
            owner={"owner_kind": "subject", "owner_subject_id": "owner"},
            archetype_key=archetype,
            revision={"display_name": archetype, "description": None, "compatible_item_types": ["event"]},
        ),
    )
    event_at = utc(now + timedelta(seconds=3720))
    event = call(
        "schedule.create",
        dict(
            contract_version="spine.schedule-create.v2",
            command_id="synthetic-event",
            actor_subject_id="owner",
            created_at_utc=utc(now),
            item={
                "item_type": "event",
                "title": "Synthetic " + archetype,
                "summary": "Do not disclose this summary",
                "event_detail": {"all_day": False},
                "archetype": {
                    "item_archetype_id": kind["item_archetype_id"],
                    "revision_resolution": "current",
                    "selection_source": "operator_explicit",
                },
            },
            scheduled_time={
                "time_basis": "local_instant",
                "local_date": event_at[:10],
                "local_time": event_at[11:19],
                "timezone": "UTC",
                "timezone_database_version": {"kind": "system_current"},
            },
            delivery={
                "recipient_kind": "subject",
                "recipient_subject_id": "owner",
                "channel": "whatsapp",
                "target": {"resolution": "explicit", "delivery_target_id": "synthetic-capture-route"},
            },
            notification_plan={
                "mode": "none",
                "custom_additions": [
                    {
                        "policy_key": "one-hour",
                        "schedule": {"kind": "once", "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-3600"}},
                        "late_handling": {"kind": "skip"},
                    }
                ],
            },
            materialization={
                "mode": "bounded",
                "evaluated_at_utc": utc(now),
                "range": {"kind": "item_relative", "start_offset_seconds": "-3600", "end_offset_seconds": "1"},
                "limit": "10",
            },
        ),
    )
    work = ledger.execute("SELECT work_instance_id FROM work_instances WHERE item_id=?", (event["item_id"],)).fetchone()[0]
    config = dict(
        synthetic_only=True,
        opted_in_item_ids=[event["item_id"]],
        permit_ordinary_text=True,
        facet_fields={},
        definition_revision="synthetic-helpful-personable.v1",
        disclosure_revision="synthetic-context-only.v1",
        lead_seconds=180,
        allowed_tools=[],
    )
    return ledger, work, config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True)
    parser.add_argument("--impetus-python", required=True)
    parser.add_argument("--impetus-source", required=True, help="Trusted Impetus src directory")
    args = parser.parse_args()
    directory = Path(args.directory)
    directory.mkdir(mode=0o700, exist_ok=False)
    now = datetime.now(UTC).replace(microsecond=0)
    ledger, work, config = seed(directory / "spine.sqlite3", now)
    source = Source(ledger)
    capture_path = directory / "capture.sqlite3"
    CaptureStore.initialize(capture_path, source.namespace)
    capture = CaptureStore(capture_path, source.namespace)
    env = dict(os.environ, PYTHONPATH=str(Path(args.impetus_source).resolve()))
    command = [args.impetus_python, "-m", "impetus", "--state", str(directory / "impetus")]
    try:
        subprocess.run([*command, "init", "--namespace", source.namespace], env=env, check=True, stdout=subprocess.DEVNULL)
        experiment = Experiment(source, capture, LocalImpetus(command, environment=env), config)
        opportunity, _ = experiment.export(work, utc(now))
        print(json.dumps(experiment.run(opportunity, utc(now)), indent=2))
    finally:
        capture.close()
        ledger.close()


if __name__ == "__main__":
    main()
