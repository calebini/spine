# People and responsibility contract evidence

This is source-only contract codification, not an implemented capability.
The authoritative logical owner is [people and responsibility](../../../specs/people-and-responsibility.md).
The [manifest](../../../contracts/people-and-responsibility-fixture-manifest.json)
enumerates structural fixtures and the explicit offline schema dependency closure.

- `contracts/`: independent positive/negative wire examples. Existing scheduling
  and independent-read shapes are deliberately reused to test additive successor
  structure. A request and response sharing part of a filename are **not** claimed
  to have been executed together, nor to describe a writable real ledger state.
- `semantic-witnesses.json`: small declared set/admission/disclosure/filter/edge
  cases checked by pure models in `tests/test_people_and_responsibility_contracts.py`.
  They are not production handlers, permission resolvers, SQLite queries or workers.
- `computed-vectors.json`: exact canonical preimages/bytes/digests and deterministic
  HMAC examples. Fixed cursor secrets are test-only and must never be deployed.

Run the offline checks from the repository root:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_people_and_responsibility_contracts.py -v
```

These checks establish schema closure, structural outcomes and the named pure-model
relationships only. PR-01–16 in the machine companion remain pending executable
runtime gates: no transaction, rollback, authorization race, installed transport,
query-plan, work-state or delivery guarantee has been proven by these fixtures.
No real people, operator ledger, delivery credentials or message destinations are
required. Current runtime declarations and frozen packaged web contracts stay unchanged.
