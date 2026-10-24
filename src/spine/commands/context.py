"""Transport-neutral command context."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CommandContext:
    """Normalized context passed to command handlers by every adapter."""

    ledger: sqlite3.Connection | None = None
    ledger_path: str | None = None
    dry_run: bool = False
    transport_metadata: Mapping[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
    adapter_bindings: Mapping[str, Any] = field(default_factory=dict)
    delivery_target_defaults: Mapping[str, Any] = field(default_factory=dict)
    facet_cursor_config: Any = None  # Protected adapter configuration, never request JSON.
    rendering_cursor_config: Any = None  # Separate protected rendering cursor key configuration.
    rendering_authoring: Any = None  # Internal candidate hook; public adapters do not populate it.
    people_authoring: Any = None  # Internal people successor hook; never request-selectable.
    people_cursor_config: Any = None  # Protected adapter-only people cursor key configuration.
