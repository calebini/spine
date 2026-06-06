"""Hashing boundary for deterministic Spine payloads."""

from spine.core.canonical_json import canonical_json_bytes


def hash_canonical_json(value: object) -> str:
    """Hash a canonical JSON payload.

    Stage 2 will implement the canonical encoder and SHA-256 contract together.
    This Stage 1 function exists so imports and module boundaries are stable.
    """

    canonical_json_bytes(value)
    raise NotImplementedError("canonical JSON hashing is scheduled for Stage 2")
