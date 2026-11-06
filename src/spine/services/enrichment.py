"""Once-only opted-in research and nonblocking immutable delivery content choices."""

import hashlib
import json
import sqlite3
from contextlib import suppress
from datetime import UTC, datetime
from importlib.resources import files

from jsonschema import Draft202012Validator, ValidationError

from spine.adapters.contextual_experiment import digest, dump, require
from spine.adapters.contextual_live import decode
from spine.adapters.enrichment import CONTRACT, EnrichmentSource, EnrichmentStore
from spine.core.errors import SpineValidationError
from spine.core.hashing import side_effect_request_payload_hash
from spine.services.contextual_experiment import instant
from spine.services.contextual_live import LiveExperiment

CHOICE = "spine.notification-enrichment-choice.v1"
_schema_bytes = files("spine.contracts").joinpath("contextual_notification/enrichment-v1.schema.json").read_bytes()
_pins = json.loads(files("spine.contracts").joinpath("contextual_notification/enrichment-pins.v1.json").read_bytes())
require(hashlib.sha256(_schema_bytes).hexdigest() == _pins["schema_sha256"], "enrichment_schema_pin")
SCHEMA = json.loads(_schema_bytes)


class EnrichmentExperiment(LiveExperiment):
    capture_contract = CONTRACT

    def __init__(self, source, store, launcher, config, *, clock=None, enabled=False):
        Draft202012Validator(SCHEMA["$defs"]["config"]).validate(config)
        require(isinstance(source, EnrichmentSource) and isinstance(store, EnrichmentStore), "enrichment_profile")
        require(source.namespace == store.namespace, "capture_namespace")
        require(type(enabled) is bool, "enrichment_enablement")
        self.source, self.store, self.client = source, store, launcher
        self.config = decode(dump(config))
        self.clock = clock or (lambda: datetime.now(UTC))
        self.enabled = enabled

    def run(self, opportunity, now_utc=None):
        exported = self.store.get(opportunity)
        require(exported is not None, "export_absent")
        if exported["launched"]:
            return self.readback(opportunity, now_utc)
        work = exported["work_instance_id"]
        row = self.source.ledger.execute("SELECT status FROM work_instances WHERE work_instance_id=?", (work,)).fetchone()
        attempted = self.source.ledger.execute("SELECT 1 FROM side_effect_attempts WHERE work_instance_id=? LIMIT 1", (work,)).fetchone()
        if not self.enabled or row is None or row[0] != "eligible" or attempted or self.store.choice(work):
            return self.capture(opportunity, None, now_utc or self._observed_at_utc(), "not_invoked")
        return super().run(opportunity, now_utc)

    def current(self, connection, exported):
        """Read current source inside an existing attempt transaction if present."""
        source = EnrichmentSource(connection)
        return source.namespace == self.source.namespace and self.fingerprint(
            source.snapshot(exported["work_instance_id"], self.config)
        ) == exported["fingerprint"]

    def candidate(self, exported):
        request = decode(exported["request"])
        expected = dict(ledger_instance_id=self.source.namespace, work_id=request["work_id"],
                        request_sha256=hashlib.sha256(exported["request"]).hexdigest())
        records = self.store.history(request["source_refs"]["notification_opportunity_id"])
        for record in reversed(records):
            if not record["usable_for_hypothetical_selection"] or record["contract"] != CONTRACT:
                continue
            require(all(record[k] == v for k, v in expected.items()), "capture_binding")
            require(record["binding"] == exported["binding"] and record["source_fingerprint"] == exported["fingerprint"], "capture_binding")
            execution = record["execution"]
            self.validate_execution(execution, request, exported["binding"])
            require(execution["status"] == "succeeded" and
                    instant(execution["completed_at_utc"]) <= instant(record["observed_at_utc"]) <=
                    instant(request["selection_cutoff_utc"]), "capture_time")
            return record
        return None

    def content_choice(self, connection, work, ordinary_body):
        """No worker/provider I/O; missing private state always permits ordinary fallback."""
        try:
            require(self.enabled, "enrichment_disabled")
            known = self.store.for_work(work)
            require(known is not None, "export_absent")
            opportunity, exported = known
            previous = connection.execute("SELECT attempt_id,request_payload_hash FROM side_effect_attempts "
                                          "WHERE work_instance_id=? ORDER BY attempted_at_utc,attempt_id", (work,)).fetchall()
            for attempt, payload_hash in previous:
                receipt = self.store.receipt(attempt)
                if receipt is None or receipt[1] != payload_hash:
                    self.store.disable(work)
                    return None
            existing = self.store.choice(work)
            if existing is None:
                current = self.current(connection, exported)
                record = self.candidate(exported) if current and not previous else None
                result = None if record is None else record["execution"]["result"]
                addendum = result["text"] if result and result["kind"] == "addendum" else None
                valid = bool(addendum and addendum.strip() and len(addendum.encode()) <= 512 and
                             not any(ord(c) < 32 and c not in "\n\t" for c in addendum) and
                             len(ordinary_body + "\n\n" + addendum) <= 1024)
                reason = "ready" if valid else ("source_stale" if not current else
                                               "no_addition" if result and result["kind"] == "no_addition" else
                                               "composition_rejected" if addendum else "no_usable_capture")
                choice = dict(contract=CHOICE, work_instance_id=work, opportunity_id=opportunity,
                              kind="enriched" if valid else "ordinary", reason=reason,
                              request_sha256=hashlib.sha256(exported["request"]).hexdigest(),
                              source_fingerprint=exported["fingerprint"], capture_sha256=None if record is None else digest(record),
                              addendum=addendum if valid else None)
                Draft202012Validator(SCHEMA["$defs"]["choice"]).validate(choice)
                existing = self.store.choose(work, choice)
            choice, disabled = existing
            Draft202012Validator(SCHEMA["$defs"]["choice"]).validate(choice)
            require(choice["work_instance_id"] == work and choice["opportunity_id"] == opportunity and
                    choice["source_fingerprint"] == exported["fingerprint"] and
                    choice["request_sha256"] == hashlib.sha256(exported["request"]).hexdigest(), "choice_binding")
            if disabled or choice["kind"] != "enriched":
                return None
            require(self.current(connection, exported) and len(ordinary_body + "\n\n" + choice["addendum"]) <= 1024,
                    "enrichment_stale")
            capture = next((r for r in self.store.history(opportunity) if digest(r) == choice["capture_sha256"]), None)
            require(capture is not None and capture["execution"]["result"]["kind"] == "addendum" and
                    capture["execution"]["result"]["text"] == choice["addendum"], "choice_capture")
            return choice
        except (OSError, sqlite3.Error, ValueError, KeyError, TypeError, ValidationError, SpineValidationError):
            with suppress(OSError, sqlite3.Error):
                self.store.disable(work)
            return None

    def check_choice(self, connection, work, choice):
        try:
            existing = self.store.choice(work)
            require(self.enabled and existing == (choice, False), "enrichment_stale")
            known = self.store.for_work(work)
            require(known is not None and self.current(connection, known[1]), "enrichment_stale")
        except (OSError, sqlite3.Error, ValueError, KeyError, TypeError, ValidationError, SpineValidationError) as exc:
            with suppress(OSError, sqlite3.Error):
                self.store.disable(work)
            raise SpineValidationError("notification_enrichment_stale", "enrichment changed before attempt") from exc

    def delivery_evidence(self, connection, attempt_id):
        """Distinguish prepared sidecar data from an actual hash-bound canonical attempt."""
        row = connection.execute("SELECT work_instance_id,request_payload_hash,attempt_status,provider_ref "
                                 "FROM side_effect_attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
        receipt = self.store.receipt(attempt_id)
        if row is None or receipt is None or receipt[1] != row[1]:
            return None
        Draft202012Validator(SCHEMA["$defs"]["outbound"]).validate(receipt[0])
        require(receipt[0]["delivery_id"] == row[0], "receipt_work")
        require(side_effect_request_payload_hash(adapter_name="openclaw", request_envelope=receipt[0]) == row[1], "receipt_hash")
        evidence = dict(contract="spine.notification-enrichment-evidence.v1", attempt_id=attempt_id,
                        attempt_status=row[2], provider_ref=row[3], request_payload_hash=row[1], envelope=receipt[0])
        Draft202012Validator(SCHEMA["$defs"]["evidence"]).validate(evidence)
        return evidence
