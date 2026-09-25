"""Sticky `hermes profile use` must win before cli.py caches CLI_CONFIG.

The classic CLI loads config at import time (`cli.py: CLI_CONFIG = load_cli_config()`).
Hermes's real entry point (`hermes_cli.main`) applies `_apply_profile_override()`
*before* that import so a sticky `active_profile` re-homes HERMES_HOME first.

The wrapper must do the same. Importing `cli` first stacks default's model/skills
on top of the local-agent prompt — the screenshot bug.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

CUSTOM = Path(__file__).resolve().parents[1]


def _checkout() -> Path:
    """Where hermes-agent actually lives.

    Derived, never hardcoded: this test used to pin ``C:/Users/bottl/dev/
    hermes-agent``, the checkout moved to ``~/.hermes/hermes-agent``, and the
    test failed with a bare ``FileNotFoundError`` that said nothing about why.
    hermes-custom.cmd carries the one authoritative path (its own comment calls
    it "the ONE line to update"), so read it from there and the two cannot
    drift apart again.
    """
    env = os.environ.get("HERMES_CHECKOUT", "").strip()
    if env:
        return Path(env)
    cmd = CUSTOM / "hermes-custom.cmd"
    if cmd.is_file():
        match = re.search(r'set\s+"HERMES_CHECKOUT=([^"]+)"', cmd.read_text(encoding="utf-8"))
        if match:
            return Path(match.group(1))
    return Path.home() / ".hermes" / "hermes-agent"


CHECKOUT = _checkout()
VENV_PY = CHECKOUT / "venv" / "Scripts" / "python.exe"

pytestmark = pytest.mark.skipif(
    not VENV_PY.is_file(),
    reason=f"hermes-agent venv not found at {VENV_PY} — set HERMES_CHECKOUT")

PROBE = r"""
import json
import os
from pathlib import Path

import my_cli  # noqa: F401
import cli
from hermes_cli.profiles import get_active_profile_name
from hermes_constants import get_hermes_home

print(json.dumps({
    "env": os.environ.get("HERMES_HOME"),
    "home": str(get_hermes_home()),
    "name": get_active_profile_name(),
    "cli_model": (cli.CLI_CONFIG.get("model") or {}).get("default"),
}))
"""


def test_importing_wrapper_rebases_home_to_sticky_profile(tmp_path: Path) -> None:
    root = tmp_path / "hermes"
    worker = root / "profiles" / "worker"
    worker.mkdir(parents=True)
    (root / "config.yaml").write_text("model:\n  default: grok-from-root\n", encoding="utf-8")
    (worker / "config.yaml").write_text("model:\n  default: qwen-from-worker\n", encoding="utf-8")
    (root / "active_profile").write_text("worker\n", encoding="utf-8")

    env = os.environ.copy()
    env["HERMES_HOME"] = str(root)
    env["PYTHONPATH"] = os.pathsep.join([str(CHECKOUT), str(CUSTOM)])
    env.pop("HERMES_PROFILE", None)

    result = subprocess.run(
        [str(VENV_PY), "-c", PROBE],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(CUSTOM),
        timeout=180,
    )
    assert result.returncode == 0, result.stderr + "\n" + result.stdout
    data = json.loads(result.stdout.strip().splitlines()[-1])
    assert data["name"] == "worker", data
    assert Path(data["home"]).resolve() == worker.resolve(), data
    assert data["cli_model"] == "qwen-from-worker", data
