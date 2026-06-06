"""Hashing helpers for deterministic Spine payloads."""

from hashlib import sha256

from spine.core.canonical_json import canonical_json_bytes


def hash_canonical_json(value: object) -> str:
    """Return SHA-256 hex over Spine canonical JSON UTF-8 bytes."""

    return sha256(canonical_json_bytes(value)).hexdigest()


def coordination_item_version_intent_hash(
    *, title: str, summary: str | None = None, source_ref: str | None = None
) -> str:
    """Hash ``coordination_item_versions.intent_hash`` payload."""

    return hash_canonical_json(
        _omit_absent(
            {
                "title": title,
                "summary": summary,
                "source_ref": source_ref,
            }
        )
    )


def coordination_item_version_normalized_fields_hash(*, title: str, summary: str | None = None) -> str:
    """Hash ``coordination_item_versions.normalized_fields_hash`` payload."""

    return hash_canonical_json(_omit_absent({"title": title, "summary": summary}))


def audit_log_payload_hash(payload: object) -> str:
    """Hash an ``audit_log.payload_hash`` payload."""

    return hash_canonical_json(payload)


def _omit_absent(payload: dict[str, object | None]) -> dict[str, object]:
    return {key: value for key, value in payload.items() if value is not None}
