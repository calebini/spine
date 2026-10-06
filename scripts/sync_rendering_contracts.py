"""Package the local rendering contracts and their exact transitive schema closure."""

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "src/spine/contracts/rendering"
REGISTRIES = (
    "notification-rendering-definition-contract-registry.v1.json",
    "notification-rendering-integration-contract-registry.v1.json",
    "notification-rendering-integration.v1.json",
)


def references(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"$ref", "request_schema", "response_schema", "failure_schema"} and isinstance(child, str):
                yield child
            else:
                yield from references(child)
    elif isinstance(value, list):
        for child in value:
            if isinstance(child, str) and child.startswith("contracts/schemas/"):
                yield child
            else:
                yield from references(child)
    elif isinstance(value, str) and value.startswith("contracts/schemas/"):
        yield value


def expected():
    files = {name: (ROOT / "contracts" / name).read_bytes() for name in REGISTRIES}
    pending = [ref for raw in files.values() for ref in references(json.loads(raw))]
    while pending:
        ref = pending.pop()
        name = Path(urlparse(ref).path).name
        if not name:
            continue
        relative = "schemas/" + name
        if relative in files:
            continue
        raw = (ROOT / "contracts/schemas" / name).read_bytes()
        files[relative] = raw
        pending.extend(references(json.loads(raw)))
    pins = {
        "contract_version": "spine.local-rendering-package-pins.v1",
        "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in sorted(files.items())},
    }
    files["pins.v1.json"] = (json.dumps(pins, indent=2) + "\n").encode()
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files = expected()
    if args.check:
        actual = {str(path.relative_to(DEST)): path.read_bytes() for path in DEST.rglob("*.json")}
        if actual != files:
            raise SystemExit("local rendering contract resources are stale; run scripts/sync_rendering_contracts.py")
    else:
        # No pruning: an obsolete resource must be explicitly reviewed/removed.
        for name, raw in files.items():
            path = DEST / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    print(
        f"Verified {len(files)} local rendering contract resources"
        if args.check
        else f"Packaged {len(files)} local rendering contract resources"
    )


if __name__ == "__main__":
    main()
