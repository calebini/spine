"""Explicit provisioning of immutable authored-zone fingerprints from trusted data."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from spine.core.errors import SpineValidationError
from spine.timezones import CONTRACT_VERSION, MAX_BYTES, METHOD, capture_zone, parse_catalog


def provision(
    *, root: Path, expected_version: str, zones: list[str], catalog: Path, build_id: str, origin: str, artifact_sha256: str
) -> int:
    if not root.is_absolute() or not catalog.is_absolute():
        raise ValueError("provider root and catalog must be absolute paths")
    entries = []
    for timezone in sorted(set(zones)):
        captured = capture_zone(timezone, root=root)
        if captured.version != expected_version:
            raise ValueError(f"expected authored version {expected_version!r}; provider is {captured.version!r}")
        entry = {
            "authored_version": expected_version,
            "timezone": timezone,
            "build_id": build_id,
            "method": METHOD,
            "origin": origin,
            "artifact_sha256": artifact_sha256,
            "metadata_sha256": captured.metadata_sha256,
            "tzif_sha256": captured.sha256,
            "tzif_size": len(captured.data),
        }
        entry["evidence_id"] = "tzif_" + hashlib.sha256(json.dumps(entry, sort_keys=True).encode()).hexdigest()
        entries.append(entry)
    if len({entry["metadata_sha256"] for entry in entries}) != 1:
        raise ValueError("provider metadata changed during baseline capture")
    # This command is the only writer. Readers never create this file or its lock.
    with catalog.with_suffix(catalog.suffix + ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        existing = {}
        if catalog.exists():
            with catalog.open("rb") as stream:
                existing = dict(parse_catalog(stream.read(MAX_BYTES + 1)))
        for entry in entries:
            key = str(entry["authored_version"]), str(entry["timezone"])
            if key in existing and existing[key] != entry:
                raise ValueError("refusing to replace an immutable authored-zone baseline")
            existing[key] = entry
        output = (json.dumps({"contract_version": CONTRACT_VERSION, "baselines": list(existing.values())}, indent=2) + "\n").encode()
        parse_catalog(output)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=catalog.parent, prefix=catalog.name + ".", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(output)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o644)
            os.replace(temporary, catalog)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return len(entries)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="authenticated original provider root containing tzdata.zi")
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--zone", action="append", required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--origin", required=True, help="authenticated source artifact origin and build provenance")
    parser.add_argument("--artifact-sha256", required=True, help="SHA-256 of the authenticated source artifact")
    args = parser.parse_args(argv)
    try:
        count = provision(
            root=args.root,
            expected_version=args.expected_version,
            zones=args.zone,
            catalog=args.catalog,
            build_id=args.build_id,
            origin=args.origin,
            artifact_sha256=args.artifact_sha256,
        )
    except (OSError, ValueError, SpineValidationError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "catalog": str(args.catalog), "captured_count": count}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
