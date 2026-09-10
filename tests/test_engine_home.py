import importlib.util
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1] / "plugin" / "_engine.py"


def _load():
    spec = importlib.util.spec_from_file_location("brain_rag_engine_home", ENGINE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_unset_hermes_home_index_path_uses_localappdata(monkeypatch, tmp_path):
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    path = _load().index_path()
    assert path == tmp_path / "Local" / "hermes" / "rag" / "brain.sqlite"
    assert ".hermes" not in path.as_posix()
