import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "nightly.py"


def _load(monkeypatch, home: Path):
    monkeypatch.setenv("HERMES_ROOT", str(home))
    # nightly.py appends the hermes-agent checkout to sys.path and imports
    # brain_rag from the repo's src; both must resolve without a real install.
    monkeypatch.syspath_prepend(str(SCRIPT.parents[1] / "src"))
    spec = importlib.util.spec_from_file_location("nightly_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["nightly_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


def test_sweeps_every_profile_database_default_first(monkeypatch, tmp_path):
    default = _touch(tmp_path / "state.db")
    names = ["tiferet", "blackhole", "clauud", "it", "ninja"]
    profile_dbs = {n: _touch(tmp_path / "profiles" / n / "state.db") for n in names}

    found = _load(monkeypatch, tmp_path).sweep_state_dbs()

    assert found[0] == default
    assert found[1:] == [profile_dbs[n] for n in sorted(names)]


def test_picks_up_a_profile_added_after_import(monkeypatch, tmp_path):
    _touch(tmp_path / "state.db")
    mod = _load(monkeypatch, tmp_path)
    assert len(mod.sweep_state_dbs()) == 1

    _touch(tmp_path / "profiles" / "newcomer" / "state.db")

    assert [p.parent.name for p in mod.sweep_state_dbs()] == [tmp_path.name, "newcomer"]


def test_ignores_profiles_without_a_database_and_stray_files(monkeypatch, tmp_path):
    _touch(tmp_path / "state.db")
    (tmp_path / "profiles" / "empty").mkdir(parents=True)
    _touch(tmp_path / "profiles" / "stray" / "notes.txt")
    (tmp_path / "profiles" / "dirnamed" / "state.db").mkdir(parents=True)  # a directory, not a file
    _touch(tmp_path / "profiles" / "real" / "state.db")

    found = _load(monkeypatch, tmp_path).sweep_state_dbs()

    assert [p.parent.name for p in found] == [tmp_path.name, "real"]


def test_missing_default_database_and_profiles_dir_is_not_an_error(monkeypatch, tmp_path):
    assert _load(monkeypatch, tmp_path).sweep_state_dbs() == []
