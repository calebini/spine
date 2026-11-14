"""Keep pre-R4 byte witnesses on their original schema; never rewrite baselines."""

from contextlib import ExitStack, contextmanager
from unittest.mock import patch


@contextmanager
def schema19():
    with ExitStack() as stack:
        for target in ("spine.ledger.sqlite.IMPLEMENTED_LEDGER_SCHEMA_VERSION",
                       "spine.commands.core.IMPLEMENTED_LEDGER_SCHEMA_VERSION",
                       "spine.commands.temporal_bindings.IMPLEMENTED_LEDGER_SCHEMA_VERSION",
                       "spine.ledger.preflight.CURRENT_SCHEMA_VERSION"):
            stack.enter_context(patch(target, 19))
        yield
