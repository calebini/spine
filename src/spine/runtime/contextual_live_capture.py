"""Fresh synthetic live-profile preparation only; this module makes no provider call."""

from pathlib import Path

from spine.adapters.contextual_experiment import Source
from spine.adapters.contextual_live import LiveCaptureStore
from spine.runtime.contextual_experiment_demo import seed
from spine.services.contextual_live import configuration_binding


def initialize(directory, now, provider_configuration_json):
    """Create new synthetic source and format-2 state; never repurpose a ledger."""
    configuration_binding(provider_configuration_json)
    directory = Path(directory)
    directory.mkdir(mode=0o700, exist_ok=False)
    ledger, work, config = seed(directory / "spine.sqlite3", now)
    try:
        source = Source(ledger)
        path = directory / "capture.sqlite3"
        LiveCaptureStore.initialize(path, source.namespace)
        store = LiveCaptureStore(path, source.namespace)
        config["provider_configuration_json"] = provider_configuration_json
        return ledger, work, config, store
    except BaseException:
        ledger.close()
        raise
