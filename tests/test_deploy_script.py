import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

DEPLOY_CMD = Path(__file__).resolve().parents[1] / "scripts" / "deploy.cmd"
DEPLOY_PY = Path(__file__).resolve().parents[1] / "scripts" / "deploy.py"
REPO = Path(__file__).resolve().parents[1]
LIVE_HERMES = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\bottl\AppData\Local")) / "hermes"
HERMES_AGENT = Path(r"C:/Users/bottl/dev/hermes-agent")


def _load_deploy():
    spec = importlib.util.spec_from_file_location("brain_rag_deploy_script", DEPLOY_PY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mini_src(root: Path) -> Path:
    plugin = root / "plugin"
    engine = root / "src" / "brain_rag"
    plugin.mkdir(parents=True)
    engine.mkdir(parents=True)
    (plugin / "plugin.yaml").write_text("name: brain-rag\n", encoding="utf-8")
    (plugin / "brain.sqlite").write_bytes(b"do-not-copy-plugin")
    (engine / "__init__.py").write_text("# engine\n", encoding="utf-8")
    (root / "src" / "brain.sqlite").write_bytes(b"do-not-copy-src")
    return root


def test_deploys_to_the_default_profile_root():
    text = DEPLOY_CMD.read_text(encoding="utf-8")
    assert r"%LOCALAPPDATA%\hermes\plugins\brain-rag" in text


def test_deploys_to_named_profile_roots():
    """The 2026-09-09 silent-drift bug: global-only copy leaves profiles stale."""
    text = DEPLOY_CMD.read_text(encoding="utf-8")
    assert r"profiles\local-agent\plugins\brain-rag" in text


def test_vendors_the_engine_next_to_the_plugin():
    text = DEPLOY_CMD.read_text(encoding="utf-8")
    assert "vendor" in text


def test_prints_the_plugins_enabled_reminder():
    text = DEPLOY_CMD.read_text(encoding="utf-8").lower()
    assert "plugins.enabled" in text


def test_copies_plugin_and_vendor_into_injected_tmp_roots(tmp_path):
    src = _mini_src(tmp_path / "repo")
    default = tmp_path / "default" / "plugins" / "brain-rag"
    named = tmp_path / "profiles" / "local-agent" / "plugins" / "brain-rag"
    deploy = _load_deploy()

    deploy.deploy(src_root=src, dest_roots=[default, named])

    for dest in (default, named):
        assert (dest / "plugin.yaml").is_file()
        assert (dest / "vendor" / "src" / "brain_rag" / "__init__.py").is_file()
        assert dest.is_relative_to(tmp_path)
        assert LIVE_HERMES not in dest.parents and dest != LIVE_HERMES
        assert HERMES_AGENT not in dest.parents and dest != HERMES_AGENT


def test_does_not_copy_brain_sqlite(tmp_path):
    src = _mini_src(tmp_path / "repo")
    dest = tmp_path / "plugins" / "brain-rag"
    _load_deploy().deploy(src_root=src, dest_roots=[dest])

    assert not (dest / "brain.sqlite").exists()
    assert not (dest / "vendor" / "src" / "brain.sqlite").exists()


def test_copy_failure_does_not_print_deployed(tmp_path):
    dest = tmp_path / "plugins" / "brain-rag"
    deploy = _load_deploy()
    with pytest.raises(FileNotFoundError):
        deploy.deploy(src_root=tmp_path / "missing-repo", dest_roots=[dest])
    assert not dest.exists()


def test_cmd_honors_injected_roots_and_fails_closed_on_xcopy_error(tmp_path):
    """Invoke deploy.cmd only with tmp roots — never live LocalAppData hermes."""
    src = _mini_src(tmp_path / "repo")
    default = tmp_path / "default" / "plugins" / "brain-rag"
    named = tmp_path / "profiles" / "local-agent" / "plugins" / "brain-rag"
    env = os.environ.copy()
    env["BRAIN_RAG_DEPLOY_SRC"] = str(src)
    env["BRAIN_RAG_DEPLOY_ROOTS"] = f"{default};{named}"
    env.pop("PYTEST_CURRENT_TEST", None)

    ok = subprocess.run(
        ["cmd.exe", "/c", "call", str(DEPLOY_CMD)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "Deployed." in ok.stdout
    assert (default / "plugin.yaml").is_file()
    assert (named / "vendor" / "src" / "brain_rag" / "__init__.py").is_file()
    assert not (default / "brain.sqlite").exists()

    env["BRAIN_RAG_DEPLOY_SRC"] = str(tmp_path / "no-such-src")
    failed = subprocess.run(
        ["cmd.exe", "/c", "call", str(DEPLOY_CMD)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert failed.returncode != 0
    assert "Deployed." not in failed.stdout
