import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "weekly_sweep.py"


def _load():
    spec = importlib.util.spec_from_file_location("weekly_sweep", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_exposes_main():
    assert callable(_load().main)


def test_never_calls_prune():
    """Prune deletes transcripts; it is not an intake path."""
    assert "prune" not in SCRIPT.read_text(encoding="utf-8").lower()


def test_sweeps_before_reindexing():
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.index("sweep_sessions") < text.index("index_vault")
