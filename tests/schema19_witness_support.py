"""Keep pre-R4 byte witnesses on their original schema; never rewrite baselines."""

from contextlib import ExitStack, contextmanager
from unittest.mock import patch


def schema19():
    return historical_schema(19)


@contextmanager
def historical_schema(version):
    with ExitStack() as stack:
        for target in ("spine.ledger.sqlite.IMPLEMENTED_LEDGER_SCHEMA_VERSION",
                       "spine.commands.core.IMPLEMENTED_LEDGER_SCHEMA_VERSION",
                       "spine.commands.temporal_bindings.IMPLEMENTED_LEDGER_SCHEMA_VERSION",
                       "spine.ledger.preflight.CURRENT_SCHEMA_VERSION"):
            stack.enter_context(patch(target, version))
        yield
