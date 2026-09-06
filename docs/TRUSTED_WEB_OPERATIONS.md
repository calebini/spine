# Trusted multi-operator backend

Spine 0.4.0 / schema 13 adds an optional backend, not a browser GUI or an
authentication system. Operators select an account honestly; anyone who can reach
the interface can select any offered account. Keep access restricted to trusted
devices. Do not expose it publicly or describe selection as verified sign-in.

The CLI and worker remain trusted local tools with full scope. The backend calls
the same domain handlers directly; it never invokes a CLI subprocess or sends a
notification while authoring. Existing scheduling agents need no change.

## Install and migrate

Install the checkout with the `web` extra in its existing virtual environment:
`python -m pip install -e '.[web]'`. The extra contains Flask, Waitress,
ItsDangerous, and offline JSON Schema validation. No external identity provider,
schema service, or network lookup is used during admission.

Before upgrading the ledger, stop the existing worker and other writers, take a
consistent SQLite backup, and run the normal checkout-local
`spine-ledger-migrate --db <ledger>` procedure. Migration and explicit
`--verify-only` remain potentially expensive deep verification paths. Routine web
readiness uses bounded schema-object verification, not integrity scans.

Schema 13 preserves existing coordination, receipt, route, and membership IDs.
Historical items do not acquire owners or web visibility automatically. Accounts
and memberships are not inferred from participants, transport groups, or titles.
The old runtime cannot operate schema 13: rollback requires a compatible code and
ledger backup pair, not simply checking out old code against the migrated ledger.

## Provision locally, deliberately

Provisioning is available only through the trusted local command surface:

- `web_access.plan` is a bounded read, with no receipt or mutation.
- `web_access.apply` applies that complete plan atomically with one audit/receipt.

Use the generic CLI form `spine-command --db <ledger> --input <request.json>
--pretty web_access plan` (or `web_access apply`). The plan request contract is
`spine.trusted-web-provisioning.v1`. Supply a chosen stable `ledger_id`, expected
access epoch (`"0"` only before bootstrap), and explicit operations. Examples and
closed shapes are in `tests/fixtures/trusted_web/contracts/request_provisioning.json`
and `contracts/schemas/trusted-web-provisioning-plan-request.schema.json`.

Create an operator using an existing active subject, display name, and
`activation_basis=trusted_local_approval`. The command generates stable account and
binding IDs; it does not prove the subject's identity. Keep the returned IDs.

Supported operations cover operator eligibility, direct member/admin/owner
memberships, initial ownership adoption of existing items, item/catalog grants,
and same-group route member-use approval. Each adopted group must have exactly one
designated owner in the resulting batch. Historical creator rights are not guessed.
Plan/apply cannot transfer already-owned items or administer authentication methods.

Inspect `can_apply`, conflicts, references, and warnings. Apply takes the **complete
plan response** in `plan`, plus its expected access epoch, a fresh command ID,
local administrative actor, and explicit timestamp. Retry an uncertain apply with
the same request and ID; do not generate a new one. A changed reference or epoch
requires re-planning. Empty/no-change applies still follow explicit receipt rules.
Set `SPINE_WEB_REALM_ID` for provisioning if using a realm other than `local`.

Grant edits require expected revisions. Ended memberships and revoked grants are
terminal; renewed authority gets a new row. Route approval pins its security
revision, not merely the route's display label. Revoking approval blocks new web
authoring/use; it does **not** recall existing reminder work. Cancel or update the
schedule explicitly when future delivery must stop.

## Start and inspect

Run `spine-web --db <ledger> --ledger-id <provisioned-id>` from the checkout-local
environment. Default listener, Host, and Origin are `127.0.0.1:8090` and
`http://127.0.0.1:8090`. Startup refuses an unprovisioned or incompatible ledger.
The service does not initialize or migrate storage automatically.

For remote use configure `--listen`, exact `--host`, HTTPS `--origin`, and
`--trusted-network-confirmed`, with a trusted network boundary and TLS termination.
The flag acknowledges deployment responsibility; it does not configure a firewall.
If using a proxy, preserve the exact Host/Origin and strip forwarded identity
headers. Spine does not trust proxy identity assertions. Configure bounded proxy
and supervisor logs; the app does not persist request payloads, idle-read receipts,
or per-request last-seen records.

Readiness: `GET /health/ready` returns only readiness. `/api/v1/info` reports the
trust warning, versions, and limits. `/api/v1/operators` supplies eligible account
and subject IDs. All POSTs require exact Host/Origin, `application/json`, and
`X-Spine-Account-ID` plus a client-generated `X-Spine-Selection-ID`. A client must
discard a response for a selection ID that is no longer current.

Use `/api/v1/context`, `/items`, and `/agenda` for scoped reads. The closed
`/api/v1/commands/{command}` registry exposes thirteen commands, not arbitrary CLI
dispatch. New creates/builds require an explicit outer `create_owner_scope`;
writes require `expected_access_epoch`. The inner request stays canonical.

The service limits bodies to 1 MiB, responses to 4 MiB, candidate/resolved resources
to 100, selectable operators to 32, SQL work to 100,000 VM steps, and elapsed
request work to five seconds including at most two seconds of lock wait. These
are deliberate fail-closed ceilings. An agenda/item query whose authorized
candidate set exceeds 100 returns capacity rather than silently omitting rows;
explicit bounded agenda item selection can narrow that set. No whole-ledger agenda
is evaluated and then filtered. This first backend is for bounded operator use,
not an unrestricted large-catalog search service.

Cursors are signed using ItsDangerous and a process-local random key. They bind
identity, query, snapshot, epochs, and a fixed fifteen-minute expiry. Restart or
restore invalidates them; start a fresh query. They are not login credentials.

## Canary and interpretation

Before enabling the listener for real operators, verify both an allowed device and
a disallowed device at the network boundary. Exercise two account selections, a
private item denial, same-group member/admin behavior, and an explicitly approved
route. Create a non-sending/policy-only canary, inspect it, update it, retry the same
command ID, and cancel it. Actual delivery remains a separate approved worker test.

Interpret receipts literally: authored, expanded, materialized, attempted, and
delivered are separate facts. `task.complete` returns outer
`work_reconciliation=not_performed_by_this_command`; completion is not a claim that
all queued work was cancelled or an attempted delivery recalled.

An unavailable/denied nested route, catalog, binding, or related item denies the
whole readback, not a partial invented response. Existing-location attachment and
cross-owner temporal derivation are deliberately unavailable here. Inline location
creation remains supported. Local tools retain their existing capabilities.

After an interrupted or post-commit-denied write, the outcome can be unknown.
Resolve with same-ID replay or authorized readback. Do not rebase stale versions
or create another ID automatically. Stop deployment on migration, readiness,
authorization, or transaction failures and preserve the ledger for diagnosis.
