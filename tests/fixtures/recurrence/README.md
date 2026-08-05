# Recurrence Contract Fixtures

The JSON documents under `contracts/` are initial structural examples for the
flexible recurrence contract family. They demonstrate representative authoring,
normalized-set, mutation-command, provenance-command, and occurrence-response
shapes and are indexed by `contracts/recurrence-fixture-manifest.json`.

These examples do not claim digest conformance. Hash-like values are structural
placeholders until the computed preimage-and-digest vector corpus required by
Section 11 of `specs/recurrence.md` is implemented. Runtime fixtures are added
separately, slice by slice, only when the corresponding behavior exists.
