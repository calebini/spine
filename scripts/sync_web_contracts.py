"""Generate the offline wheel copy of web contracts; --check never writes."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = root / "contracts"
    target = root / "src/spine/contracts/web"
    files = sorted(source.glob("trusted-web-*.json")) + [
        source / "spine.trusted-web-command-registry.v1.json", source / "spine.trusted-web-read-registry.v1.json",
    ]
    files += sorted((source / "schemas").glob("*.schema.json"))
    expected = {target / p.relative_to(source): p.read_bytes() for p in files}
    if args.check:
        mismatched = [str(p.relative_to(root)) for p, value in expected.items() if not p.exists() or p.read_bytes() != value]
        extra = set(target.rglob("*.json")) - set(expected)
        for p in mismatched + sorted(str(p.relative_to(root)) for p in extra):
            print(p)
        return int(bool(mismatched or extra))
    for path, value in expected.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
