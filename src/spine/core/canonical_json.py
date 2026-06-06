"""Canonical JSON encoding boundary.

The full MVP canonicalization rules are specified in ``specs/ontology.md`` and
will be implemented in Stage 2.
"""

from typing import NoReturn


def canonical_json_bytes(_value: object) -> bytes:
    """Return canonical JSON UTF-8 bytes for a hash payload.

    Stage 1 only establishes the importable module boundary. The deterministic
    encoder itself belongs to Stage 2 because it carries normative behavior.
    """

    _raise_stage_2()


def _raise_stage_2() -> NoReturn:
    raise NotImplementedError("canonical JSON encoding is scheduled for Stage 2")
