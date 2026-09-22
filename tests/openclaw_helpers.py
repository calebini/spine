"""Gateway double that delivers once per key even if the CLI loses its response."""

import json
import subprocess


class IdempotentGatewayRunner:
    def __init__(self, *, timeout_after_first_delivery=False):
        self.timeout_after_first_delivery = timeout_after_first_delivery
        self.receipts = {}
        self.visible_deliveries = []
        self.requests = []

    def __call__(self, cmd, **kwargs):
        params = json.loads(cmd[cmd.index("--params") + 1])
        self.requests.append(params)
        key = params["idempotencyKey"]
        if key not in self.receipts:
            self.visible_deliveries.append(params)
            self.receipts[key] = f"wamid.delivery-{len(self.visible_deliveries)}"
        if self.timeout_after_first_delivery and len(self.requests) == 1:
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs["timeout"])
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"messageId": self.receipts[key]}), stderr="")
