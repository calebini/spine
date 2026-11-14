"""Package the ratified ownership/provisioning closure separately from frozen web contracts."""

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from sync_people_contracts import references

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "src/spine/contracts/ownership"


def expected():
    descriptor = (ROOT / "contracts/local-ownership-bootstrap.v1.json").read_bytes()
    files = {"local-ownership-bootstrap.v1.json": descriptor}
    pending = list(json.loads(descriptor)["schemas"]) + ["contracts/schemas/trusted-web-error.schema.json"]
    while pending:
        relative = pending.pop()
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or path.parts[:2] != ("contracts", "schemas"):
            raise ValueError("nonlocal ownership schema")
        name = path.relative_to("contracts").as_posix()
        if name in files:
            continue
        raw = (ROOT / path).read_bytes()
        schema = json.loads(raw)
        files[name] = raw
        for uri in references(schema, schema["$id"]):
            pending.append("contracts/" + str(Path(urlparse(uri).path).relative_to("/spine/contracts")))
    pins = {"contract_version": "spine.ownership-package-pins.v1",
            "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in sorted(files.items())}}
    files["pins.v1.json"] = (json.dumps(pins, indent=2) + "\n").encode()
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files = expected()
    if args.check:
        actual = {p.relative_to(DEST).as_posix(): p.read_bytes() for p in DEST.rglob("*.json")}
        if actual != files:
            raise SystemExit("ownership package drift")
    else:
        for name, raw in files.items():
            path = DEST / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    print(f"{len(files)} ownership resources; pins SHA-256 {hashlib.sha256(files['pins.v1.json']).hexdigest()}")


if __name__ == "__main__":
    main()
