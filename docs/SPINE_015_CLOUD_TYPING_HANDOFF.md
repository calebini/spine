# SPINE-015 cloud typing repair handoff

Prepared 2026-09-18 for the **implementation agent**. Tracking: SPINE-025 in
[BACKLOG.md](BACKLOG.md). No specification decision or additional SPINE-015 feature
delivery is needed for this validation repair.

## Baseline and work already completed

The cloud and local baseline is the clean commit
`f575af5c059c6a9cdeed4de7319a713ea7a17760`, “Add authorized activity sections and
canonical agenda assembly.” Inspect the working tree before proceeding; the local
repair described below is intentionally uncommitted and must be preserved.

The synchronization failure is repaired locally in `scripts/sync_web_contracts.py`:
the `trusted-web-read-*` family remains source-only until the accepted
HTTP/package/capability activation checkpoint. The existing v1 registry stays
packaged; the separate v2 read registry stays absent. The checker still rejects
missing, changed, unexpected, or prematurely packaged assets. Four focused tests
in `tests/test_web_contract_sync.py` cover these properties. No canonical or
packaged JSON, runtime module, dependency declaration, or type-checking rule changed.

See [the accepted activation boundary](../specs/independent-activity-reads.md) and
[delivery sequence](IMPLEMENTATION_PLAN.md#planned-fat-slice-independent-authorized-activity-reads-spine-015).
Do not run a blanket sync that packages v2, advertise its capabilities, or advance
the remaining release-fence/cursor/HTTP/Kinflow work as part of this repair.

## Important correction to the cloud diagnosis

This is **not established as a mypy-version regression**. On unchanged source:

| Import-discovery environment | mypy 1.20.2 | mypy 2.3.0 |
| --- | --- | --- |
| Existing local editable installation | Pass, 35 explicit files | Pass, 35 explicit files |
| Interpreter without an installed Spine distribution | Fail, 308 errors in 7 transitive files | Fail, 308 errors in 7 transitive files |

All comparison runs disabled incremental caching. The cloud reported 307 errors
on Python 3.12.13; local reproduction used Python 3.14.6 with mypy's configured
Python 3.12 target. Local source-only discovery additionally lacks `referencing`;
the same seven Spine modules fail. Exact counts depend on available dependencies.

The original repaired renderer was `src/spine/core/notification_rendering.py`.
The new renderer diagnostics concern `src/spine/services/notification_rendering.py`.
Do not describe these as a regression of the original core annotation repair.

## Reproduction

The existing local environment contains an editable Spine installation. Running
only `.venv/bin/mypy --strict src/spine/core src/spine/ledger` is insufficient to
reproduce the cloud gate.

The cloud's mypy version has been installed separately under
`/private/tmp/spine-mypy-1.20.2-validation-20260918`; the repository venv is unchanged.
From the repository root, the local reproduction is:

```sh
PYTHONPATH=/private/tmp/spine-mypy-1.20.2-validation-20260918 \
  .venv/bin/python -m mypy --strict --no-incremental \
  --python-executable /opt/homebrew/bin/python3 \
  --cache-dir /tmp/spine-typing-recheck-cache \
  src/spine/core src/spine/ledger
```

The alternate interpreter affects installed-package discovery. It does not change
the configured target Python version. Repeat with `.venv/bin/mypy` to test 2.3.0.
Without `--python-executable`, both versions pass in the existing editable setup.
Retained baseline output: `/tmp/spine-mypy-120-source-only-final.log` and
`/tmp/spine-mypy-230-clean.log`. These temporary paths are conveniences; reproduce
the commands if they are gone.

For a portable clean-room reproduction, provision the declared tool and web
dependencies into an isolated Python 3.12 environment **without an editable Spine
installation**, then run the strict command from the checkout. Keep dependency
provisioning separate from runtime network access. Do not infer a fix from an
editable-install-only pass.

## Dependency paths and observed diagnostics

Ledger reaches the command package through all three of these existing imports:

- `ledger/notification_profiles.py`: `commands.receipts.command_derived_id`.
- `ledger/temporal_bindings.py`, inside `resolve_binding_source`: command-core
  `_decorate_occurrence` and `_next_scheduled_fact`.
- `ledger/temporal_bindings.py`, inside `_source_item_for_occurrence`:
  command-core `_hydrated_item_at_version`.

Importing the command package also loads its `handle` export. The late imports
are visible to mypy even when they do not execute during module import.
A local experiment moving only the ID helper into core hashing did **not** fix
the gate; it was fully reverted. No runtime edits from that experiment remain.

Local diagnostic counts and representative categories:

| File under `src/spine` | Count | Examples |
| --- | ---: | --- |
| `commands/core.py` | 254 | Optional ledger narrowing, optional row access, collection types, implicit re-exports |
| `commands/temporal_bindings.py` | 37 | Optional ledger use, `int(object)`, argument types, implicit re-export |
| `web/provisioning.py` | 6 | Optional dictionary access; `Connection` lacks `atomic_command` |
| `services/notification_rendering.py` | 4 | `int(object)`, duplicate annotation, return narrowing |
| `runtime/compatibility.py` | 3 | JSON return typing and optional iteration/sorting |
| `web/contracts.py` | 3 | JSON return typing and dependency/stub discovery |
| `services/projections.py` | 1 | Object-typed item version passed as integer |

## Requested implementation work

Repair the strict validation gate with the smallest justified changes. Inspect the
remaining diagnostics and choose between accurate typing corrections and a bounded
dependency-boundary correction. Preserve canonical recurrence, binding freshness,
hydration, command IDs, public imports, validation errors, and transaction behavior.
Do not redesign temporal semantics merely to avoid imported diagnostics.

Do not suppress errors, weaken strictness, skip imports, or pin to a newer mypy just
to obtain a pass. Both tested versions expose the problem with source-only discovery.
If a real public semantic decision is unavoidable, isolate that specific question
before changing it; no broad spec review is requested.

Add meaningful tests wherever a correction could affect behavior. Verify both
source-only and editable-install strict runs, retain complete unittest discovery,
run pytest with explicit summary output, Ruff, temporary-prefix compileall, the
contract sync check, and focused temporal/recurrence/command regressions as relevant.
Record exact tool versions and results in SPINE-025. Do not call the complete cloud
gate repaired while source-only strict checking still fails.

Preserve all pre-existing work. No commits, pushes, deployment changes, staging or
real-ledger access, runtime internet enablement, Tickerd installation/qualification,
or unrelated refactoring is authorized by this handoff.
