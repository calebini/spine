"""Coherent TZif capture and evidence-bound, version-aware timezone resolution."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import struct
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any, NoReturn
from zoneinfo import TZPATH, ZoneInfo

from spine.core.errors import SpineValidationError

CONTRACT_VERSION = "spine.timezone-compatibility.v1"
METHOD = "identical_tzif_bytes.v1"
MAX_BYTES = 1_048_576
MAX_BASELINES = 4096
_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}\Z")
_ZONE = re.compile(r"[A-Za-z0-9_+-]+(?:/[A-Za-z0-9_+-]+)*\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_LOG = logging.getLogger(__name__)
_logged: OrderedDict[tuple[object, ...], None] = OrderedDict()
_log_lock = Lock()


def _fail(message: str) -> NoReturn:
    raise SpineValidationError("environment_failure:timezone_database_version", message)


def _identity(path: Path) -> tuple[int, int, int, int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


@lru_cache(maxsize=64)
def _read_file(path: Path, identity: tuple[int, ...], limit: int) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit or len(data) != identity[2] or _identity(path) != identity:
        _fail("timezone provider changed during capture or exceeds the size limit")
    return data


def _capture_file(path: Path, limit: int) -> tuple[bytes, tuple[int, ...]]:
    identity = _identity(path)
    if identity[2] > limit:
        _fail("timezone provider exceeds the size limit")
    data = _read_file(path, identity, limit)
    if _identity(path) != identity:
        _fail("timezone provider changed during capture")
    return data, identity


def _version(metadata: bytes) -> str:
    first = metadata.split(b"\n", 1)[0]
    try:
        text = first.decode("ascii")
    except UnicodeError:
        _fail("timezone provider version metadata is malformed")
    version = text.removeprefix("# version ")
    if not text.startswith("# version ") or not _VERSION.fullmatch(version):
        _fail("timezone provider does not expose an exact IANA version")
    return version


def _check_zone(timezone: str) -> None:
    if len(timezone) > 255 or not _ZONE.fullmatch(timezone):
        raise SpineValidationError("invalid_request:timezone", f"invalid IANA timezone: {timezone}")


@dataclass(frozen=True)
class CapturedZone:
    zone: ZoneInfo
    data: bytes
    version: str
    provider: str
    metadata_sha256: str
    sha256: str


def capture_zone(timezone: str, *, root: Path | None = None) -> CapturedZone:
    """Capture version metadata and a complete TZif from the same provider."""
    _check_zone(timezone)
    roots = (str(root),) if root is not None else TZPATH
    for value in roots:
        provider = Path(value)
        path = provider / timezone
        if not path.exists():
            continue
        try:
            metadata_path = provider / "tzdata.zi"
            metadata, metadata_identity = _capture_file(metadata_path, MAX_BYTES * 4)
            data, data_identity = _capture_file(path, MAX_BYTES)
            version = _version(metadata)
            zone = _decode_zone(timezone, data)
            if _identity(metadata_path) != metadata_identity or _identity(path) != data_identity:
                _fail("timezone provider changed during capture")
            return CapturedZone(zone, data, version, str(provider), _sha(metadata), _sha(data))
        except (OSError, ValueError, EOFError, IndexError, OverflowError, AssertionError, struct.error) as exc:
            _fail(f"timezone provider capture failed: {type(exc).__name__}")
    raise SpineValidationError("invalid_request:timezone", f"unknown IANA timezone: {timezone}")


def system_timezone_database_version() -> str:
    """Read live provider metadata; never retain a process-global version string."""
    for root in TZPATH:
        path = Path(root)
        if not path.is_dir():
            continue
        try:
            metadata, _ = _capture_file(path / "tzdata.zi", MAX_BYTES * 4)
            return _version(metadata)
        except OSError:
            _fail("selected timezone provider does not expose an exact IANA version")
    _fail("no timezone provider is available")


@lru_cache(maxsize=256)
def _decode_zone(timezone: str, data: bytes) -> ZoneInfo:
    # Check complete block lengths and footer, which ZoneInfo alone may ignore.
    offset = 0
    for block in range(2):
        if len(data) < offset + 44 or data[offset : offset + 4] != b"TZif":
            _fail("timezone provider contains malformed TZif data")
        version = data[offset + 4 : offset + 5]
        if version not in (b"\0", b"2", b"3", b"4"):
            _fail("timezone provider contains an unsupported TZif encoding")
        isut, isstd, leap, count, types, chars = struct.unpack(">6I", data[offset + 20 : offset + 44])
        if not 1 <= types <= 256 or isut not in (0, types) or isstd not in (0, types):
            _fail("timezone provider contains invalid TZif counts")
        width = 4 if block == 0 else 8
        offset += 44 + count * (width + 1) + types * 6 + chars + leap * (width + 4) + isstd + isut
        if offset > len(data):
            _fail("timezone provider contains truncated TZif data")
        if version == b"\0":
            if block or offset != len(data):
                _fail("timezone provider contains invalid TZif trailing data")
            break
        if block:
            footer = data[offset:]
            if len(footer) < 2 or not footer.startswith(b"\n") or not footer.endswith(b"\n") or b"\n" in footer[1:-1]:
                _fail("timezone provider contains an incomplete TZif footer")
    return ZoneInfo.from_file(io.BytesIO(data), key=timezone)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("timezone baseline catalog contains duplicate JSON members")
        result[key] = value
    return result


@lru_cache(maxsize=8)
def parse_catalog(data: bytes) -> dict[tuple[str, str], dict[str, Any]]:
    """Validate the closed catalog without a mandatory JSON Schema dependency."""
    try:
        if len(data) > MAX_BYTES:
            _fail("timezone baseline catalog exceeds the size limit")
        catalog = json.loads(data, object_pairs_hook=_unique_object)
        if not isinstance(catalog, dict) or set(catalog) != {"contract_version", "baselines"}:
            _fail("invalid timezone baseline catalog fields")
        entries = catalog["baselines"]
        if catalog["contract_version"] != CONTRACT_VERSION or not isinstance(entries, list) or not 1 <= len(entries) <= MAX_BASELINES:
            _fail("invalid timezone baseline catalog version or count")
        result: dict[tuple[str, str], dict[str, Any]] = {}
        fields = {
            "authored_version",
            "timezone",
            "build_id",
            "evidence_id",
            "method",
            "origin",
            "artifact_sha256",
            "metadata_sha256",
            "tzif_sha256",
            "tzif_size",
        }
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != fields:
                _fail("invalid timezone baseline entry fields")
            for field in fields - {"tzif_size"}:
                value = entry[field]
                if not isinstance(value, str) or not value.strip() or len(value) > 2048 or any(ord(c) < 32 for c in value):
                    _fail("invalid timezone baseline text")
            valid_zone = len(entry["timezone"]) <= 255 and _ZONE.fullmatch(entry["timezone"])
            if not _VERSION.fullmatch(entry["authored_version"]) or not valid_zone:
                _fail("invalid timezone baseline version or zone")
            hashes = ("artifact_sha256", "metadata_sha256", "tzif_sha256")
            if entry["method"] != METHOD or any(not _HASH.fullmatch(entry[key]) for key in hashes):
                _fail("invalid timezone baseline method or digest")
            if type(entry["tzif_size"]) is not int or not 44 <= entry["tzif_size"] <= MAX_BYTES:
                _fail("invalid timezone baseline byte length")
            identity = entry["authored_version"], entry["timezone"]
            if identity in result or any(row["evidence_id"] == entry["evidence_id"] for row in result.values()):
                _fail("duplicate or conflicting timezone baseline identity")
            result[identity] = entry
        return result
    except (ValueError, UnicodeError, RecursionError) as exc:
        _fail(f"malformed timezone baseline catalog: {type(exc).__name__}")


def resolve_timezone(timezone: str, requested_version: str) -> CapturedZone:
    captured = capture_zone(timezone)
    if captured.version == requested_version:
        return captured
    failure = f"requested timezone database {requested_version!r}; installed {captured.version!r}"
    location = os.environ.get("SPINE_TIMEZONE_BASELINES")
    if not location:
        _fail(failure + "; trusted authored-zone baseline is unavailable")
    path = Path(location)
    if not path.is_absolute():
        _fail("SPINE_TIMEZONE_BASELINES must be an absolute path")
    try:
        data, _ = _capture_file(path, MAX_BYTES)
    except OSError:
        _fail("timezone baseline catalog is unavailable")
    reference = parse_catalog(data).get((requested_version, timezone))
    if reference is None or reference["tzif_sha256"] != captured.sha256 or reference["tzif_size"] != len(captured.data):
        _fail(failure + "; complete TZif bytes do not match a trusted authored-zone baseline")
    identity = (
        captured.provider,
        captured.metadata_sha256,
        requested_version,
        captured.version,
        timezone,
        reference["evidence_id"],
        captured.sha256,
    )
    with _log_lock:
        if identity not in _logged:
            _LOG.warning(
                json.dumps(
                    {
                        "diagnostic_code": "timezone_compatible_substitution",
                        "requested_version": requested_version,
                        "runtime_version": captured.version,
                        "timezone": timezone,
                        "evidence_id": reference["evidence_id"],
                        "tzif_sha256": captured.sha256,
                    },
                    sort_keys=True,
                )
            )
            _logged[identity] = None
            if len(_logged) > 1024:
                _logged.popitem(last=False)
        _logged.move_to_end(identity)
    return captured


def timezone_for_version(timezone: str, requested_version: str) -> ZoneInfo:
    return resolve_timezone(timezone, requested_version).zone
