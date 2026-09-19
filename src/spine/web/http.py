"""Bounded HTTP adapter; trusted identity selection is not authentication."""

from __future__ import annotations

import argparse
import ipaddress
import logging
import secrets
import threading
import time
from urllib.parse import urlsplit

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from spine.web.contracts import API, json_object, validate
from spine.web.errors import WebError
from spine.web.read_contracts import READ_API, read_error
from spine.web.read_service import ReadService
from spine.web.service import WebConfig, WebService, _id


def create_app(config: WebConfig, *, cursor_key: str | None = None) -> Flask:
    service = WebService(config, cursor_key=cursor_key)
    reads = ReadService(config)
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=1048576, PROPAGATE_EXCEPTIONS=False)
    app.extensions["spine_service"] = service
    app.extensions["spine_read_service"] = reads
    slots = threading.BoundedSemaphore(4)

    def failure(error: WebError):
        selection = request.headers.get("X-Spine-Selection-ID")
        if request.path.startswith("/api/v2/"):
            codes = reads.contracts.schemas["trusted-web-read-error.schema.json"]["properties"]["error"]["properties"]["code"]["enum"]
            code = error.code if error.code in codes else "admission_unavailable"
            value = {
                "contract_version": READ_API, "ok": False,
                "error": {"code": code, "message": "Read unavailable."},
                "correlation_id": secrets.token_hex(16), "selection_id": selection if _id(selection) else None,
            }
            reads.contracts.validate("trusted-web-read-error.schema.json", value, output=True)
            status = error.status if code == "invalid_request" and error.status in {403, 413} else read_error(code).status
            return jsonify(value), status
        return jsonify(
            {
                "contract_version": API,
                "ok": False,
                "error": {"code": error.code, "message": error.code.replace("_", " "), **error.details},
                "correlation_id": secrets.token_hex(16),
                "selection_id": selection if _id(selection) else None,
            }
        ), error.status

    @app.before_request
    def boundary():
        if request.host != config.host:
            raise WebError("invalid_request", status=403)
        if any(
            name.lower().startswith(("x-forwarded-", "x-spine-subject", "x-spine-actor")) or name.lower() == "forwarded"
            for name, _value in request.headers
        ):
            raise WebError("invalid_request")
        if request.method == "POST":
            if any("," in request.headers.get(k, "") for k in ("X-Spine-Account-ID", "X-Spine-Selection-ID")):
                raise WebError("invalid_request")
            if request.headers.get("Origin") != config.origin:
                raise WebError("invalid_request", status=403)
            if request.headers.get("Content-Type") != "application/json":
                raise WebError("invalid_request")
            validate(
                "trusted-web-http.schema.json",
                {k: request.headers.get(k) for k in ("Host", "Origin", "Content-Type", "X-Spine-Account-ID", "X-Spine-Selection-ID")},
                "#/$defs/selectionHeaders",
            )
        if request.query_string:
            raise WebError("invalid_request")
        if request.path == "/api/v2/read-capabilities":
            if (any("," in request.headers.get(k, "") for k in ("X-Spine-Account-ID", "X-Spine-Selection-ID"))
                    or not all(_id(request.headers.get(k)) for k in ("X-Spine-Account-ID", "X-Spine-Selection-ID"))
                    or request.get_data(cache=False)):
                raise WebError("invalid_request")
            if request.headers.get("Origin") not in (None, config.origin):
                raise WebError("invalid_request", status=403)

    @app.after_request
    def no_store(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.errorhandler(WebError)
    def known(error):
        return failure(error)

    @app.errorhandler(Exception)
    def unexpected(error):
        if isinstance(error, HTTPException):
            return failure(WebError("invalid_request" if error.code == 413 else "operation_unavailable", status=error.code))
        # Never serialize exception reprs: they may contain SQL or private values.
        return failure(WebError("admission_unavailable"))

    def run(operation):
        if not slots.acquire(blocking=False):
            raise WebError("capacity_exceeded")
        try:
            return jsonify(operation())
        finally:
            slots.release()

    @app.get("/health/ready")
    def ready():
        try:
            return run(lambda: service.public("ready"))
        except Exception:
            return jsonify({"is_ready": False}), 503

    @app.get("/api/v1/info")
    def info():
        return run(lambda: service.public("info"))

    @app.get("/api/v1/operators")
    def operators():
        return run(lambda: service.public("operators"))

    def selected(target):
        return run(
            lambda: service.execute(
                target,
                json_object(request.get_data(cache=False)),
                request.headers["X-Spine-Account-ID"],
                request.headers["X-Spine-Selection-ID"],
            )
        )

    @app.post("/api/v1/context")
    def context():
        return selected("context")

    @app.post("/api/v1/items")
    def items():
        return selected("items")

    @app.post("/api/v1/agenda")
    def agenda():
        return selected("agenda")

    @app.post("/api/v1/commands/<command>")
    def command(command):
        return selected(command)

    def selection():
        return request.headers.get("X-Spine-Account-ID"), request.headers.get("X-Spine-Selection-ID")

    def encode_read(value):
        return (app.json.dumps(value) + "\n").encode("utf-8")

    def run_read(operation):
        if not slots.acquire(blocking=False):
            raise read_error("capacity_exceeded")
        try:
            started = time.monotonic()
            encoded = operation()
            if time.monotonic() - started >= min(config.request_seconds, reads.contracts.bounds["request_milliseconds"] / 1000):
                raise read_error("capacity_exceeded")
            return app.response_class(encoded, mimetype="application/json")
        finally:
            slots.release()

    @app.get("/api/v2/read-capabilities")
    def read_capabilities():
        return run_read(lambda: reads.capabilities(selection=selection, encode=encode_read))

    def selected_read(route):
        return run_read(lambda: reads.execute(route, json_object(request.get_data(cache=False)), selection=selection, encode=encode_read))

    @app.post("/api/v2/commands/schedule.show")
    def read_schedule():
        return selected_read("schedule.show")

    @app.post("/api/v2/commands/item.occurrences")
    def read_occurrences():
        return selected_read("item.occurrences")

    @app.post("/api/v2/agenda")
    def read_agenda():
        return selected_read("agenda")

    registry = reads.contracts.artifacts["spine.trusted-web-read-registry.v1.json"]
    expected = {(e["path"], e["method"]) for e in [*registry["commands"], registry["agenda"], registry["discovery"]]}
    actual = {(rule.rule, method) for rule in app.url_map.iter_rules() if rule.rule.startswith("/api/v2/")
              for method in rule.methods - {"HEAD", "OPTIONS"}}
    if actual != expected:
        raise read_error("admission_unavailable")
    return app


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--ledger-id", required=True)
    parser.add_argument("--realm-id", default="local")
    parser.add_argument("--listen", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--host", default="127.0.0.1:8090")
    parser.add_argument("--origin", default="http://127.0.0.1:8090")
    parser.add_argument("--timezone", default="UTC")
    parser.add_argument("--trusted-network-confirmed", action="store_true")
    args = parser.parse_args()
    origin = urlsplit(args.origin)
    local = ipaddress.ip_address(args.listen).is_loopback
    if origin.netloc != args.host or origin.path or origin.query or origin.fragment or origin.username:
        parser.error("Origin must exactly identify the configured Host, without a path")
    if origin.scheme not in {"http", "https"}:
        parser.error("Origin must use HTTP or HTTPS")
    if not local and (origin.scheme != "https" or not args.trusted_network_confirmed):
        parser.error("remote use requires an explicitly confirmed trusted network and TLS termination")
    app = create_app(WebConfig(args.db, args.ledger_id, args.realm_id, args.host, args.origin, args.timezone))
    app.extensions["spine_service"].public("ready")
    from waitress import serve

    logging.getLogger("waitress").setLevel(logging.WARNING)
    serve(
        app,
        host=args.listen,
        port=args.port,
        threads=4,
        connection_limit=16,
        max_request_body_size=1048576,
        max_request_header_size=16384,
        channel_timeout=10,
        clear_untrusted_proxy_headers=True,
    )
    return 0
