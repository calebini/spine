# R4 recurring-task release integration

Status: in progress, first increment uncommitted (2026-11-14).
Authority: [SPINE-095](../BACKLOG.md#spine-095--r4-recurring-task-activation-and-release-verification)
and the [R4 plan](../IMPLEMENTATION_PLAN.md#r4--public-activation-and-release-verification-spine-095).
R3 is committed as `c90f27d`. The unrelated agent-instructions and R2 restoration
edits remain outside this work.

## Offline package first

The [sync script](../../scripts/sync_recurring_task_contracts.py) copies the
ratified descriptor, closure manifest, and all 30 declared schemas byte-for-byte.
Nested schema paths are preserved to avoid basename collisions. Its `--check`
mode detects missing, modified and extra packaged JSON files. It rejects source
hash drift, duplicate paths/identities and incomplete transitive references.
No fixture, source contract, web bundle or runtime declaration is rewritten.

The [loader](../../src/spine/commands/recurring_task_package.py) checks the
compiled SHA-256 of the pin manifest, every asset, closure identity, transitive
references, command schema membership and exact existing runtime prerequisites.
Reads are size-bounded; all resolution is offline, with no source-directory or
network fallback and no cache that can conceal resource loss after a prior load.
Loading resources does not register or activate commands. The source descriptor
correctly still says `runtime_implemented=false` at this intermediate checkpoint.

Package pins SHA-256:
`ee9dd3d44fd4b3504e75da27cdfa255f7ac8dbbcaec7e076b88e8f7ba9504842`.

## Verification boundary

[Package tests](../../tests/test_recurring_task_package.py) cover source parity,
every required missing/corrupt asset, existing prerequisite loss, offline schema
validation, resource loss following success, sync parity, and the unchanged public
registry/schema boundary. The reusable
[wheel check](../../scripts/verify_recurring_task_wheel.py) requires an isolated,
non-editable virtual-environment installation and reports package-only scope.
It loaded 33 resources / 30 schemas / seven command entries outside the checkout;
`pip check` passed. Build and runtime environments were disposable and no
ledger, worker or delivery adapter was opened. This is not the full pinned
Tickerd/worker/public-CLI release qualification required by R4.

Final focused verification: **63 tests in 25.689 seconds, OK** (package,
recurring commands, machine fixtures, implemented declarations, architecture
boundaries and agent documentation). Repository Ruff, loader Mypy, compilation,
401 local documentation link paths, synchronization and diff hygiene pass.
The final locally built test wheel SHA-256 is
`bfa2886bc90875044296fdce7f0e5e7061dba883cebe6dd1e724e8ed6010f093`;
this is a disposable verification artifact, not a published release.

## Remaining R4

Promote the normal migration/preflight path to schema 20, expose the seven
trusted-local commands with exact prerequisites, supply protected cursor and
scheduler configuration at worker startup, and reconcile source-only assertions
and public documentation in the same activation change. Then execute all named
RRT acceptance obligations, synthetic migration/race coverage and the installed
public science-class scenario, followed by the complete regression suite.
No new HTTP allowlist, live migration, deployment, real-send test or release
publication is authorized by this checkpoint.
