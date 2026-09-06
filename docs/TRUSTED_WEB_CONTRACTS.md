# Trusted Web Contract Bundle

Status: implemented backend bundle, Spine 0.4.0 / schema 13. Local contract/runtime
verification accompanies it; network deployment and browser GUI acceptance are separate.
Authentication, executor tokens and protected chat admission remain deferred.

The normative entry point is [the web API spec](../specs/trusted-multi-operator-web-api.md).

## Artifacts and Verification

- `contracts/spine.trusted-web-command-registry.v1.json`: closed thirteen-command
  mapping, exact version fields, required runtime families, permission resolver and
  complete-or-deny response policy.
- `contracts/trusted-web-schema-pins.v1.json`: SHA-256 of the transitive inner schema
  dependencies. A deliberate dependency change requires reviewing the affected web
  mapping, updating pins and rerunning tests; never regenerate pins just to hide drift.
- `contracts/schemas/trusted-web-*.schema.json`: command envelopes, scoped queries,
  errors, header context, provisioning, cursor payload and receipt linkage.
- `contracts/trusted-web-normalization.v1.json` and `trusted-web-id-vectors.v1.json`:
  plan/envelope hashing facts, normalized operation paths and canonical ID vectors.
- `contracts/trusted-web-fixture-manifest.json`: positive and negative wire fixtures.
- `contracts/trusted-web-acceptance.v1.json`: concrete `WEB-01`–`WEB-15` scenarios;
  backend test mappings are explicit; deployment/browser checks remain separate.
- `contracts/trusted-web-budgets.v1.json`: implemented ceilings, exercised with 1,000 idle reads and 100,000 unrelated receipts.

Run the static checks with the repository test environment:

```sh
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_trusted_web_contracts.py
```

## Pinning Without Changing Existing Commands

Select the request/response schema definition by the exact route command, not by
trying schema branches to discover an operation. Unknown commands deny. The registry
is validated by the backend; its HTTP allowlist does not restrict the local CLI.

`schedule.show`, `item.occurrences` and `task.complete` have no inner request version
field. Their registry entry therefore uses null for `request_version_field` and
`request_contract_version`; this is an explicitly untagged request, not a wildcard.
Their pinned schemas and required runtime contracts still apply. Do not inject a new
version field into these existing CLI payloads.

`task.complete` also has no response version field. Its outer `result_contract` label,
`spine.trusted-web-task-complete-result.v1`, names the web bundle's captured shape;
it is not a new implemented CLI response family. Existing catalog read responses keep
their actual domain response tags, rather than being relabeled with the supporting
readback capability. Their existing general response schema remains intentionally broad;
version checks and complete nested-resource authorization are separate required gates.

## Checks That Schemas Do Not Perform

JSON Schema alone does not enforce UTF-8 byte limits, duplicate JSON object keys,
cross-field subject binding, reference existence, freshness, scope permissions, response
redaction or actual resource budgets. IDs are capped at 256 characters structurally;
the backend must additionally enforce the normative 256 UTF-8 byte limit. It must check
timestamps, plan/grant intervals and agenda elapsed duration after timezone resolution.

An error shape cannot guarantee its free-text message is safe. Backend errors must use
generic allowlisted messages and disclosure-checked domain details. Header schema names
describe parsed values; HTTP header lookup remains case-insensitive, duplicate identity
headers deny, and Host/Origin must match deployment configuration exactly.

Provisioning checks include the aggregate 100-operation limit across arrays, no duplicate
resolved targets, existence/status of references, one designated owner per adopted group,
and denial of already-owned item adoption. Warnings never grant creator entitlement.
This initial adoption payload deliberately omits creator entitlement; omission is safe
and does not guess it from historical agent actors. Existing membership/grant IDs cannot
be revived by create. Apply recomputes the plan and its reference facts; a supplied hash
or `can_apply=true` is not authorization. Epoch 0 denotes absent/bootstrap access state;
the first committed state has epoch 1. Thereafter only authorization-relevant changes
advance the epoch; no-op and replay do not create false access changes.

The cursor schema specifies the signed payload, not a license to accept unsigned JSON.
The backend binds it with ItsDangerous SHA-256 signing; the public test-only vector is
`trusted-web-cursor-vectors.v1.json`. Restart/restore changes the key and invalidates it. Query hashes cover
normalized request fields including defaults and limit, excluding the cursor itself.
The snapshot hash covers only bounded authorized source facts. Issuance/expiry are exactly
900 seconds apart; continued pagination must preserve the original expiry.

## Verification and Remaining Gates

`tests/test_trusted_web_runtime.py` exercises real temporary SQLite ledgers, every
allowlisted command, roles/grants/route approvals, late rollback, replay, two concurrent
web writers, local-writer contention, revisioned history, bounded reads and schema
admission. `scripts/sync_web_contracts.py --check` verifies packaged offline assets.

The GUI is not part of this release. Client identity-switch UX and actual allowed/
disallowed network reachability still require browser/deployment acceptance. Follow
[TRUSTED_WEB_OPERATIONS.md](TRUSTED_WEB_OPERATIONS.md); tests do not prove a firewall
or TLS termination was configured correctly.
