from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[1] / "scripts" / "deploy.cmd"


def test_deploys_to_the_default_profile_root():
    text = DEPLOY.read_text(encoding="utf-8")
    assert r"%LOCALAPPDATA%\hermes\plugins\brain-rag" in text


def test_deploys_to_named_profile_roots():
    """The 2026-09-09 silent-drift bug: global-only copy leaves profiles stale."""
    text = DEPLOY.read_text(encoding="utf-8")
    assert r"profiles\local-agent\plugins\brain-rag" in text


def test_vendors_the_engine_next_to_the_plugin():
    text = DEPLOY.read_text(encoding="utf-8")
    assert "vendor" in text


def test_prints_the_plugins_enabled_reminder():
    text = DEPLOY.read_text(encoding="utf-8").lower()
    assert "plugins.enabled" in text
