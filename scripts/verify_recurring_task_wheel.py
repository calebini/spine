"""R4 package-only proof: run with an installed-wheel Python using -I.

This preliminary check does not assert public command activation, migrate a
ledger, invoke internal handlers, or send notifications. R4's complete release
scenario remains a separate gate after runtime activation.
"""

import json
import sys
from importlib import metadata, resources
from pathlib import Path

import spine
from spine.commands.recurring_task_package import packaged


def main():
    prefix = Path(sys.prefix).resolve()
    installed = Path(spine.__file__).resolve()
    if prefix == Path(sys.base_prefix).resolve() or not installed.is_relative_to(prefix):
        raise RuntimeError("use a separate virtual environment with a non-editable installed wheel")
    distribution = metadata.distribution("spine-ledger")
    direct = distribution.read_text("direct_url.json")
    if direct is None or json.loads(direct).get("dir_info", {}).get("editable"):
        raise RuntimeError("non-editable local wheel evidence required")
    contracts = packaged()
    for entry in contracts.descriptor["commands"].values():
        for field in ("request_schema", "response_schema", "failure_schema"):
            if entry[field] not in contracts.documents:
                raise RuntimeError("incomplete command closure")
    raw_pins = resources.files("spine.contracts").joinpath("recurring_tasks", "pins.v1.json").read_bytes()
    print(json.dumps({"scope": "recurring-task-package-only", "package_version": spine.__version__,
                      "schema": str(spine.IMPLEMENTED_LEDGER_SCHEMA_VERSION), "installed_module": str(installed),
                      "resource_count": str(len(json.loads(raw_pins)["files"]) + 1),
                      "schema_count": str(len(contracts.documents)), "command_count": str(len(contracts.descriptor["commands"])),
                      "public_activation_verified": False, "ok": True}, indent=2))


if __name__ == "__main__":
    main()
