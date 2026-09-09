# Draft archetype facet contract fixtures

These examples describe proposed wire contracts; no facet command is implemented.
Use `contracts/archetype-facet-contract-registry.v1.json` to select a command's exact
request/response `$defs` fragment. The command itself is a route, not a request field.
An unselected schema-library root is not a request validator.

Run the structural and pure-semantic checks with:

```sh
PYTHONPATH=src:../tickerd/src .venv/bin/python -m unittest discover -s tests -p test_archetype_facet_contract_fixtures.py
```

The manifest tracks every JSON fixture and vector. `valid=false` means the JSON
document deliberately fails its selected structural schema. A `failure_*.json`
document is a valid example of an unsuccessful handler response, not an invalid
schema fixture or proof that a handler executed.

Each example is independent. Changed and no-op receipts illustrate alternative
states; their shared illustrative command IDs do not authorize replaying different
requests against one ledger. A changed item receipt here assumes no notification
policies or work, and makes no queued-work retention claim. The readback example
includes an inactive but readable historical location reference; new authoring
requires active, readable references.

Golden vectors contain explicit preimages, canonical text, SHA-256 digests and
generated IDs. Scalar vectors cover all six declared types. The test-only semantic
oracles exercise normalization and selected validation rules; they do not create
database rows, authorize real references, implement pagination, or emulate a worker.

Still required before runtime: the work-freshness/reconciliation rule and integration
fixtures, permission resolvers/adapter error mappings, cursor security and snapshot
semantics, migration/index design, and actual transaction/query-plan tests. Current
CLI, web, package capability and schedule contracts remain unchanged.
