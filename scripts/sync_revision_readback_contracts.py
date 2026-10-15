"""Package only the trusted-local revision readback contract and schema closure."""

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from sync_rendering_contracts import references

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "src/spine/contracts/revision_readback"
REGISTRY = "facet-schema-revision-readback.v1.json"


def expected():
    files = {REGISTRY: (ROOT / "contracts" / REGISTRY).read_bytes()}
    pending = list(references(json.loads(files[REGISTRY])))
    while pending:
        name = Path(urlparse(pending.pop()).path).name
        if not name or "schemas/" + name in files:
            continue
        raw = (ROOT / "contracts/schemas" / name).read_bytes()
        files["schemas/" + name] = raw
        pending.extend(references(json.loads(raw)))
    pins = {
        "contract_version": "spine.local-revision-readback-package-pins.v1",
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
        actual = {str(p.relative_to(DEST)): p.read_bytes() for p in DEST.rglob("*.json")}
        if actual != files:
            raise SystemExit("local revision readback resources are stale; run scripts/sync_revision_readback_contracts.py")
    else:
        for name, raw in files.items():
            path = DEST / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    print(f"{'Verified' if args.check else 'Packaged'} {len(files)} local revision readback resources")


if __name__ == "__main__":
    main()
