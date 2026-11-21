"""Trusted-local, single-reminder preview and explicitly approved capture."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sqlite3
import stat
from contextlib import closing
from datetime import UTC, datetime, timedelta
from importlib.resources import files
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry, Resource

from spine.adapters.contextual_experiment import digest, dump, require
from spine.adapters.contextual_live import LiveLauncher, decode
from spine.adapters.enrichment import open_source
from spine.adapters.enrichment_pilot import PilotStore
from spine.core import SpineError
from spine.services.contextual_experiment import instant, utc
from spine.services.contextual_live import SCHEMA as WIRE_SCHEMA
from spine.services.contextual_live import LiveExperiment
from spine.services.enrichment import SCHEMA

CONTRACT = "spine.notification-enrichment-pilot.v1"
PREVIEW = "preview.json"
STORE = "capture.sqlite3"
PROVIDER = "provider.json"
MAX_INPUT = 65536
MAX_PREVIEW = 4 * MAX_INPUT
MIN_REMAINING = timedelta(seconds=30)
PILOT_SCHEMA = decode(files("spine.contracts").joinpath("contextual_notification/enrichment-pilot-v1.schema.json").read_bytes())
PILOT_REGISTRY = Registry().with_resources((schema["$id"], Resource.from_contents(schema)) for schema in (PILOT_SCHEMA, WIRE_SCHEMA))


def validator(kind):
    return Draft202012Validator({"$ref": f"{PILOT_SCHEMA['$id']}#/$defs/{kind}"}, registry=PILOT_REGISTRY)


class CaptureOnlyExperiment(LiveExperiment):
    capture_contract = CONTRACT
    hypothetical_selection = False
    objective = ("Make this reminder more helpful or more personable using only the supplied context. "
                 "Avoid repetition, invented facts and inferred preferences. No addition is fine.")

    def __init__(self, source, config, clock, store=None):
        self.source, self.config, self.clock, self.store = source, config, clock, store

    def snapshot(self):
        work = self.config["work_instance_id"]
        db = self.source.ledger
        with db.atomic_command(write=False):
            snapshot = self.source.preview(work, self.config)
            require(db.execute("SELECT status FROM work_instances WHERE work_instance_id=?", (work,)).fetchone()[0] == "eligible",
                    "pilot_work_not_eligible")
            require(not db.execute("SELECT 1 FROM side_effect_attempts WHERE work_instance_id=? LIMIT 1", (work,)).fetchone(),
                    "pilot_work_already_attempted")
        require(snapshot["context"]["notification"]["seconds_before_event"] > 0, "pilot_not_before_event")
        return snapshot


def _bounded_read(path, maximum=MAX_INPUT):
    with path.open("rb") as handle:
        raw = handle.read(maximum + 1)
    require(len(raw) <= maximum, "pilot_input_size")
    return raw


def _private(path, kind):
    info = path.lstat()
    require(kind(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o077, "pilot_private_state_required")


def _write_private(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _config(path, provider):
    config = decode(_bounded_read(path))
    require(isinstance(config, dict) and not {"approved_context_sha256", "provider_configuration_json"} & config.keys(),
            "pilot_config_fields")
    config.update(approved_context_sha256="0" * 64, provider_configuration_json=provider)
    Draft202012Validator(SCHEMA["$defs"]["config"]).validate(config)
    require(config["facet_fields"] == {}, "pilot_structured_facets_disabled")
    require(30 < config["lead_seconds"] <= 300, "pilot_lead_seconds")
    require(0 < len(config["retention_reference"].strip().encode()) <= 512, "pilot_retention_reference_required")
    return config


def _preview(args, source, clock):
    require(source.namespace == args.ledger_id, "pilot_ledger_mismatch")
    require(args.impetus_python.is_absolute() and args.impetus_state.is_absolute(), "pilot_absolute_impetus_paths_required")
    state = args.state_dir
    owner_state = args.impetus_state.resolve()
    require(not owner_state.is_relative_to(state.resolve()) and not state.resolve().is_relative_to(owner_state),
            "pilot_separate_impetus_state_required")
    config = _config(args.config, _bounded_read(args.provider_config).decode())
    experiment = CaptureOnlyExperiment(source, config, clock)
    snapshot = experiment.snapshot()
    config["approved_context_sha256"] = digest(snapshot["context"])
    captured_at = utc(clock())
    raw, fingerprint, binding = experiment.build_export(snapshot | {"config_hash": digest(config)}, captured_at)
    request = decode(raw)
    _check_entry(request, clock, config["lead_seconds"])
    preview = dict(
        contract=CONTRACT, request=request, request_sha256=hashlib.sha256(raw).hexdigest(),
        work_instance_id=config["work_instance_id"], actor_subject_id=config["actor_subject_id"],
        retention_reference=config["retention_reference"], approved_context_sha256=config["approved_context_sha256"],
        source_fingerprint=fingerprint, binding=binding,
        state_dir=str(state.resolve()), impetus_python=str(args.impetus_python), impetus_state=str(owner_state),
    )
    validator("preview").validate(preview)
    state.mkdir(mode=0o700)
    PilotStore.initialize(state / STORE, source.namespace)
    with closing(PilotStore(state / STORE, source.namespace)) as store:
        store.put(snapshot["opportunity"], config["work_instance_id"], raw, fingerprint, binding)
    _write_private(state / PROVIDER, config["provider_configuration_json"].encode())
    _write_private(state / PREVIEW, dump(preview) + b"\n")
    return _receipt(preview, "preview_ready")


def _read_preview(state):
    _private(state, stat.S_ISDIR)
    _private(state / PREVIEW, stat.S_ISREG)
    _private(state / STORE, stat.S_ISREG)
    preview = decode(_bounded_read(state / PREVIEW, MAX_PREVIEW))
    validator("preview").validate(preview)
    require(preview["contract"] == CONTRACT and preview["state_dir"] == str(state.resolve()), "pilot_profile")
    return preview


def _receipt(preview, status, record=None):
    return dict(contract=CONTRACT, status=status, approval_sha256=digest(preview),
                request_sha256=preview["request_sha256"],
                cutoff_utc=preview["request"]["selection_cutoff_utc"],
                capture_reason=None if record is None else record["reason"], selected=False, sent=False)


def _stored(store, preview):
    opportunity = preview["request"]["source_refs"]["notification_opportunity_id"]
    exported = store.get(opportunity)
    require(exported is not None and exported["work_instance_id"] == preview["work_instance_id"] and
            exported["request"] == dump(preview["request"]) + b"\n" and
            hashlib.sha256(exported["request"]).hexdigest() == preview["request_sha256"] and
            exported["binding"] == preview["binding"] and exported["fingerprint"] == preview["source_fingerprint"],
            "pilot_store_mismatch")
    CaptureOnlyExperiment.validate_binding(exported["binding"])
    if exported["launched"]:
        require(store.approval_digest() == digest(preview), "pilot_store_mismatch")
    return opportunity, exported


def _local_status(store, opportunity, preview):
    records = store.history(opportunity)
    if records:
        return _receipt(preview, "capture_recorded", records[-1])
    return _receipt(preview, "launch_consumed_no_local_result" if store.approval_digest() else "preview_ready")


def _check_entry(request, clock, lead_seconds):
    now = clock()
    cutoff = instant(request["selection_cutoff_utc"])
    require(cutoff - timedelta(seconds=lead_seconds) <= now < cutoff - MIN_REMAINING, "pilot_outside_entry_window")


def _capture(args, preview, source, store, clock):
    require(re.fullmatch(r"[0-9a-f]{64}", args.approve_preview_sha256) and
            args.approve_preview_sha256 == digest(preview), "pilot_exact_approval_required")
    require(0 < len(args.impetus_approval_ref.strip().encode()) <= 512, "pilot_impetus_approval_required")
    require(source.namespace == preview["request"]["source_refs"]["ledger_instance_id"], "pilot_ledger_mismatch")
    opportunity, exported = _stored(store, preview)
    if exported["launched"]:
        return _local_status(store, opportunity, preview)
    provider = args.state_dir / PROVIDER
    _private(provider, stat.S_ISREG)
    config = _config(args.config, _bounded_read(provider).decode())
    config["approved_context_sha256"] = preview["approved_context_sha256"]
    experiment = CaptureOnlyExperiment(source, config, clock, store)
    request = preview["request"]
    _check_entry(request, clock, config["lead_seconds"])
    worker_state = Path(preview["impetus_state"])
    _private(worker_state, stat.S_ISDIR)
    _private(worker_state / "state.sqlite3", stat.S_ISREG)
    launcher = LiveLauncher([preview["impetus_python"], "-I", "-m", "impetus", "--state", str(worker_state)],
                            provider_configuration_path=provider.absolute(), enabled=True)
    launcher.prepare(exported["binding"])
    snapshot = experiment.snapshot()
    require(digest(snapshot["context"]) == config["approved_context_sha256"], "pilot_source_drift")
    raw, fingerprint, binding = experiment.build_export(snapshot, request["captured_at_utc"])
    require((raw, fingerprint, binding) == (exported["request"], exported["fingerprint"], exported["binding"]), "pilot_source_drift")
    _check_entry(request, clock, config["lead_seconds"])
    if not store.approve_and_mark(opportunity, args.approve_preview_sha256, args.impetus_approval_ref, experiment._observed_at_utc()):
        return _local_status(store, opportunity, preview)
    _check_entry(request, clock, config["lead_seconds"])
    response = launcher.exchange("invoke", exported["request"])
    record = experiment.capture(opportunity, response, experiment._observed_at_utc(), "invoke")
    return _receipt(preview, "capture_recorded", record)


def _parser():
    parser = argparse.ArgumentParser(description="Trusted-local, no-tools, capture-only enrichment for one staging reminder.")
    sub = parser.add_subparsers(dest="action", required=True)
    preview = sub.add_parser("preview", help="Freeze a private local preview in a new, designated pilot directory")
    capture = sub.add_parser("capture", help="Invoke once after exact preview approval and Impetus owner signoff")
    show = sub.add_parser("show", help="Inspect retained Spine state without invoking or contacting Impetus")
    for command in (preview, capture, show):
        command.add_argument("--state-dir", required=True, type=Path, help="Designated private Spine pilot directory; never reset it")
    for command in (preview, capture):
        command.add_argument("--db", type=Path, required=True, help="Existing staging ledger (read-only)")
        command.add_argument("--config", type=Path, required=True, help="Local pilot input JSON; see the operator guide")
    preview.add_argument("--ledger-id", required=True, help="Exact staging ledger identity verified out of band")
    preview.add_argument("--provider-config", type=Path, required=True, help="Non-secret model and accounting configuration")
    preview.add_argument("--impetus-python", type=Path, required=True, help="Absolute path to the pinned Impetus venv's Python")
    preview.add_argument("--impetus-state", type=Path, required=True, help="Absolute path to the agreed continuous Impetus worker state")
    capture.add_argument("--approve-preview-sha256", required=True, help="Digest explicitly approved by the operator after private review")
    capture.add_argument("--impetus-approval-ref", required=True, help="Reference to Impetus owner signoff on real source and retention")
    show.add_argument("--private", action="store_true", help="Print retained content to a private terminal only; not for chat or logs")
    return parser


def main(argv=None, *, clock=None):
    args = _parser().parse_args(argv)
    clock = clock or (lambda: datetime.now(UTC))
    try:
        if args.action == "preview":
            source = open_source(args.db)
            with closing(source.ledger):
                result = _preview(args, source, clock)
        else:
            preview = _read_preview(args.state_dir)
            with closing(PilotStore(args.state_dir / STORE, preview["request"]["source_refs"]["ledger_instance_id"])) as store:
                if args.action == "show":
                    opportunity, _ = _stored(store, preview)
                    result = _local_status(store, opportunity, preview)
                    if args.private:
                        result.update(preview=preview, captures=store.history(opportunity))
                else:
                    source = open_source(args.db)
                    with closing(source.ledger):
                        result = _capture(args, preview, source, store, clock)
        print(dump(result).decode())
        return 0
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError, SpineError, ValidationError) as exc:
        code = exc.args[0] if type(exc) is ValueError and re.fullmatch(r"pilot_[a-z_]+", str(exc)) else "pilot_input_or_state_unavailable"
        print(dump(dict(contract=CONTRACT, status="refused", reason=code, selected=False, sent=False)).decode())
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
