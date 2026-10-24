"""Synchronize the manifest-declared people contract closure without changing older bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urldefrag, urljoin

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "src/spine/contracts/people"
ARTIFACTS = ("people-and-responsibility.v1.json", "people-and-responsibility-fixture-manifest.json")


def references(value, base):
    if isinstance(value, dict):
        base = urljoin(base, value.get("$id", ""))
        for key, child in value.items():
            if key == "$ref":
                yield urldefrag(urljoin(base, child))[0]
            else:
                yield from references(child, base)
    elif isinstance(value, list):
        for child in value:
            yield from references(child, base)


def expected():
    files = {name: (ROOT / "contracts" / name).read_bytes() for name in ARTIFACTS}
    manifest = json.loads(files[ARTIFACTS[1]])
    paths = manifest["schemas"] + manifest["schema_dependencies"]
    if len(paths) != len(set(paths)):
        raise ValueError("duplicate declared schema")
    ids = set()
    schemas = []
    for relative in paths:
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or path.parts[:2] != ("contracts", "schemas"):
            raise ValueError("nonlocal schema path")
        name = "schemas/" + path.name
        if name in files:
            raise ValueError("colliding schema basename")
        raw = (ROOT / path).read_bytes()
        schema = json.loads(raw)
        if schema["$id"] in ids:
            raise ValueError("duplicate schema identity")
        ids.add(schema["$id"])
        schemas.append(schema)
        files[name] = raw
    if any(reference and reference not in ids for schema in schemas for reference in references(schema, schema["$id"])):
        raise ValueError("manifest does not declare complete schema closure")
    pins = {
        "contract_version": "spine.people-package-pins.v1",
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
            raise SystemExit("people contract resources are stale; run scripts/sync_people_contracts.py")
    else:
        for name, raw in files.items():
            path = DEST / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    digest = hashlib.sha256(files["pins.v1.json"]).hexdigest()
    print(f"{'Verified' if args.check else 'Packaged'} {len(files)} people contract resources; pin manifest SHA-256 {digest}")


if __name__ == "__main__":
    main()
