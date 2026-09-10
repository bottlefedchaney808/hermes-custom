# tests/test_desktop_plugin_shape.py
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PLUGIN_JS = Path(__file__).resolve().parents[1] / "plugin" / "desktop" / "plugin.js"


def test_no_jsx_syntax_only_jsx_calls():
    """The disk plugin loads uncompiled; JSX syntax would fail to parse."""
    source = PLUGIN_JS.read_text(encoding="utf-8")
    assert not re.search(r"<[A-Za-z][A-Za-z0-9]*\s*[/>]", source)
    assert "jsx(" in source


def test_only_allowed_specifiers_are_imported():
    source = PLUGIN_JS.read_text(encoding="utf-8")
    imports = set(re.findall(r"from\s+['\"]([^'\"]+)['\"]", source))
    assert imports <= {"@hermes/plugin-sdk", "react", "react/jsx-runtime"}


def test_declares_the_brain_rag_id():
    assert "id: 'brain-rag'" in PLUGIN_JS.read_text(encoding="utf-8")


def test_no_hardcoded_colors():
    source = PLUGIN_JS.read_text(encoding="utf-8")
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", source)
    assert "rgb(" not in source


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_node_syntax_check_passes():
    result = subprocess.run(["node", "--check", str(PLUGIN_JS)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
