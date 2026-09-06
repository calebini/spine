"""Bounded HTTP adapter; trusted identity selection is not authentication."""

from __future__ import annotations

import argparse
import ipaddress
import logging
import secrets
import threading
from urllib.parse import urlsplit

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from spine.web.contracts import API, json_object, validate
from spine.web.errors import WebError
from spine.web.service import WebConfig, WebService, _id


def create_app(config: WebConfig, *, cursor_key: str | None = None) -> Flask:
    service = WebService(config, cursor_key=cursor_key)
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=1048576, PROPAGATE_EXCEPTIONS=False)
    app.extensions["spine_service"] = service
    slots = threading.BoundedSemaphore(4)

    def failure(error: WebError):
        selection = request.headers.get("X-Spine-Selection-ID")
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
