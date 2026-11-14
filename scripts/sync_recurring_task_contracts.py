"""Package the ratified recurring-task closure verbatim; never activate commands."""

import argparse
import hashlib
import json
from pathlib import Path

from sync_people_contracts import references

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "src/spine/contracts/recurring_tasks"
DESCRIPTOR = "recurring-related-tasks.v1.json"
CLOSURE = "recurring-related-task-schema-closure.v1.json"


def expected():
    files = {name: (ROOT / "contracts" / name).read_bytes() for name in (DESCRIPTOR, CLOSURE)}
    schemas = {}
    for entry in json.loads(files[CLOSURE])["resources"]:
        path = Path(entry["path"])
        if path.is_absolute() or ".." in path.parts or path.parts[:2] != ("contracts", "schemas"):
            raise ValueError("nonlocal schema path")
        name = path.relative_to("contracts").as_posix()
        raw = (ROOT / path).read_bytes()
        schema = json.loads(raw)
        if name in files or schema["$id"] in schemas:
            raise ValueError("duplicate schema path or identity")
        if schema["$id"] != entry["uri"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ValueError("source closure identity/hash drift")
        schemas[schema["$id"]] = schema
        files[name] = raw
    if any(ref and ref not in schemas for uri, schema in schemas.items() for ref in references(schema, uri)):
        raise ValueError("incomplete offline schema closure")
    pins = {"contract_version": "spine.recurring-task-package-pins.v1",
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
            raise SystemExit("recurring-task packaged resources differ from the ratified closure")
    else:
        for name, raw in files.items():
            path = DEST / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    print(f"{'Verified' if args.check else 'Packaged'} {len(files)} recurring-task resources; "
          f"pins SHA-256 {hashlib.sha256(files['pins.v1.json']).hexdigest()}")


if __name__ == "__main__":
    main()
