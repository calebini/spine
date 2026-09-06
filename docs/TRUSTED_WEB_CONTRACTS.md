# Trusted Web Contract Bundle

Status: contract codification; no HTTP backend, provisioning commands or web capability
is implemented by this bundle. The restricted, honestly selected identity posture is
unchanged. Authentication, executor tokens and protected chat admission remain deferred.

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
  backend execution is explicitly pending, not inferred from schema validation.
- `contracts/trusted-web-budgets.v1.json`: proposed ceilings, not benchmark results.

Run the static checks with the repository test environment:

```sh
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_trusted_web_contracts.py
```

## Pinning Without Changing Existing Commands

Select the request/response schema definition by the exact route command, not by
trying schema branches to discover an operation. Unknown commands deny. The registry
is data for the future service; adding it does not register commands in the local CLI.

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
Before backend release, bind it to an established integrity-protection library, publish
wire/tamper/expiry vectors, and invalidate it on recovery/key change. Query hashes cover
normalized request fields including defaults and limit, excluding the cursor itself.
The snapshot hash covers only bounded authorized source facts. Issuance/expiry are exactly
900 seconds apart; continued pagination must preserve the original expiry.

## Next Runtime Gate

Implement the minimal account/access migration and indexes using the existing authority
drafts, atomically attached to domain transactions. Implement registry validation, resolvers,
bounded queries and provisioning; enforce schema pins and required versions before readiness.
Then execute the pending acceptance scenarios, differential canonical-command readback tests,
rollback/replay/concurrency tests and budget benchmarks. Static tests are not evidence that
two users are isolated, the network is restricted, or the service is ready to deploy.
