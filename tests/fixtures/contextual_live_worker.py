"""Independent Impetus subprocess fixture. No network or credential access."""

import argparse
import json
import os
import socket
import sys
from datetime import datetime

from impetus.adapters.openai_responses import Model
from impetus.adapters.sqlite import Store
from impetus.services.live_worker import LiveWorker


def forbidden(*args, **kwargs):
    raise AssertionError("network forbidden in synthetic fixture")


socket.socket = forbidden


class Clock:
    elapsed = 0

    def __init__(self, now):
        self.now = datetime.fromisoformat(now.replace("Z", "+00:00")).timestamp()

    def wall(self):
        return self.now + self.elapsed

    def monotonic(self):
        return self.elapsed


class Transport:
    def __init__(self, scenario, config, clock):
        self.scenario, self.config, self.clock = scenario, config, clock

    def count(self, body, key, seconds):
        if self.scenario == "die-count":
            os._exit(86)
        if self.scenario == "count-failure":
            raise TimeoutError()
        count = self.config["input_token_upper_bound"] + 1 if self.scenario == "over-limit" else 50
        return json.dumps(dict(object="response.input_tokens", input_tokens=count)).encode()

    def post(self, body, key, seconds):
        if self.scenario == "die-generation":
            os._exit(86)
        if self.scenario == "generation-unknown":
            raise TimeoutError()
        if self.scenario == "late":
            self.clock.elapsed = 21
        kind = "no_addition" if self.scenario == "no-addition" else "addendum"
        proposal = dict(kind=kind, text="Hope it goes well!" if kind == "addendum" else "", review_note="Synthetic context only.")
        inputs = 51 if self.scenario == "mismatch" else 50
        value = dict(
            id="response_synthetic", model=self.config["model"], status="completed",
            usage=dict(input_tokens=inputs, output_tokens=30, total_tokens=inputs + 30,
                       output_tokens_details={"reasoning_tokens": None}),
            output=[dict(type="message", role="assistant", status="completed",
                         content=[dict(type="output_text", text=json.dumps(proposal))])],
        )
        return json.dumps(value).encode()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True)
    parser.add_argument("--now", required=True)
    parser.add_argument("--scenario", default="context")
    parser.add_argument("--namespace")
    parser.add_argument("--provider-config")
    parser.add_argument("--enable-live", action="store_true")
    parser.add_argument("operation", choices=("init", "invoke", "read", "recover"))
    args = parser.parse_args()
    if args.operation == "init":
        Store.initialize(args.state, args.namespace)
        return
    if args.operation in ("read", "recover") and any(name in os.environ for name in (
        "IMPETUS_OPENAI_API_KEY", "IMPETUS_OPENAI_API_KEY_FILE", "OPENAI_API_KEY"
    )):
        raise AssertionError("readback must receive no credential environment")
    store = Store(args.state)
    try:
        clock = Clock(args.now)

        def factory():
            if not args.enable_live or not args.provider_config:
                raise AssertionError("fixture invocation must be explicitly enabled")
            with open(args.provider_config) as stream:
                config = json.load(stream)
            return Model(config, "synthetic-key-never-real", Transport(args.scenario, config, clock))

        worker = LiveWorker(store, clock, factory if args.operation == "invoke" else None)
        if args.scenario == "die-after-count":
            original_save = store.save

            def save(key, snapshot):
                original_save(key, snapshot)
                if len(snapshot["calls"]) == 1 and snapshot["calls"][0]["certainty"] == "complete":
                    os._exit(87)

            store.save = save
        if args.operation == "recover":
            value = worker.recover()
        else:
            raw = sys.stdin.buffer.read(65537)
            if args.operation == "invoke":
                value = worker.invoke(raw)
            else:
                request = json.loads(raw)
                value = worker.read((request["ledger_instance_id"], request["work_id"]), request["request_sha256"])
        print(json.dumps(value))
    finally:
        store.close()


if __name__ == "__main__":
    main()
