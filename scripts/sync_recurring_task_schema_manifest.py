"""Publish the schema-20 expected-object closure without changing the default schema.

The candidate's pinned delta overlays schema 19, including its ownership-state
table replacement. This script never opens a ledger or applies a migration.
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src/spine/ledger"


def expected():
    predecessor = json.loads((ROOT / "schema_object_manifest.v1.json").read_bytes())
    # At final promotion the old current manifest becomes the historical one.
    if "19" not in predecessor["schemas"]:
        predecessor = json.loads((ROOT / "schema_object_manifest.schema19.json").read_bytes())
    delta = json.loads((ROOT / "schema_object_manifest.recurring-tasks-candidate.json").read_bytes())
    if (predecessor["manifest_version"] != "spine.sqlite-schema-object-manifest.v1"
            or delta["predecessor_schema_version"] != "19" or delta["candidate_schema_version"] != "20"):
        raise ValueError("schema manifest version mismatch")
    objects = {o["name"]: o for o in predecessor["schemas"]["19"]["objects"]}
    objects.update({o["name"]: o for o in delta["objects"]})
    result = {"manifest_version": "spine.sqlite-schema-object-manifest.v1",
              "schemas": {"20": {"objects": sorted(objects.values(), key=lambda o: (o["object_type"], o["name"]))}}}
    return (json.dumps(result, indent=2) + "\n").encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = ROOT / "schema_object_manifest.schema20.json"
    value = expected()
    if args.check:
        if path.read_bytes() != value:
            raise SystemExit("schema-20 expected-object manifest is stale")
    else:
        path.write_bytes(value)
    print("Verified schema-20 expected-object manifest" if args.check else "Wrote schema-20 expected-object manifest")


if __name__ == "__main__":
    main()
