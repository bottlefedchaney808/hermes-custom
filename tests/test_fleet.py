"""Tests for the fleet engine.

These run against temporary directories, never the real profiles. The point is
to lock the three guarantees FLEET.md makes, because all three are the kind of
thing that silently stops being true:

1. sync is idempotent (a second run is a clean no-op),
2. a config edit touches only `plugins.enabled` and nothing else in the file,
3. a staged SKILL surface is withheld rather than installed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fleet import config_edit, links, manifest as manifest_mod, port, sync  # noqa: E402


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A miniature hermes-custom checkout with one linkable plugin and a skill pack."""
    plugin = tmp_path / "demo-plugin"
    plugin.mkdir()
    (plugin / "plugin.yaml").write_text("name: demo\nversion: '1.0.0'\n", encoding="utf-8")
    (plugin / "__init__.py").write_text("def register(ctx): pass\n", encoding="utf-8")

    pack = tmp_path / "demo-skills" / "alpha"
    pack.mkdir(parents=True)
    (pack / "SKILL.md").write_text("---\nname: alpha\ndescription: d\n---\n\nbody\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def homes(tmp_path: Path) -> dict:
    homes = {}
    for name in ("default", "alt"):
        home = tmp_path / "homes" / name
        for sub in ("plugins", "skills", "skins"):
            (home / sub).mkdir(parents=True)
        homes[name] = home
    return homes


def build_manifest(repo: Path, homes: dict, packages: list) -> manifest_mod.Manifest:
    profiles = {
        name: manifest_mod.Profile(name=name, home=home, role="test")
        for name, home in homes.items()
    }
    parsed = []
    for body in packages:
        surfaces = [manifest_mod._surface(s, body["name"]) for s in body["surfaces"]]
        parsed.append(
            manifest_mod.Package(
                name=body["name"],
                summary=body.get("summary", ""),
                source=repo / body["source"] if body.get("source") else None,
                surfaces=surfaces,
                profiles=body.get("profiles", []),
                is_global=body.get("global", False),
            )
        )
    return manifest_mod.Manifest(
        profiles=profiles,
        packages=parsed,
        default_mode="link",
        claude_home=repo / "claude",
        claude_skills_dir=repo / "claude" / "skills",
        claude_source=repo / "skills",
    )


# ── the idempotence contract ────────────────────────────────────────────────

def test_sync_is_idempotent(repo, homes):
    man = build_manifest(repo, homes, [{
        "name": "demo",
        "source": "demo-plugin",
        "profiles": ["default", "alt"],
        "surfaces": [{"kind": "agent-plugin", "install_as": "demo", "enable": True}],
    }])

    first = sync.plan(man)
    assert len(first.pending) == 2, "both profiles should need the plugin"
    assert {a.verdict for a in first.pending} == {sync.CREATE}

    sync.ensure_dirs(man)
    sync.apply(first, manifest=man)

    second = sync.plan(man)
    assert second.pending == [], "a second sync must be a clean no-op"
    assert all(a.verdict == sync.OK for a in second.actions)

    # A third run, after nothing changed, still no-ops.
    assert sync.plan(man).pending == []


def test_sync_detects_a_copy_where_a_link_belongs(repo, homes):
    """The exact drift that motivated this whole system."""
    man = build_manifest(repo, homes, [{
        "name": "demo",
        "source": "demo-plugin",
        "profiles": ["default"],
        "surfaces": [{"kind": "agent-plugin", "install_as": "demo"}],
    }])
    links.copy_dir(repo / "demo-plugin", homes["default"] / "plugins" / "demo")

    plan = sync.plan(man)
    assert [a.verdict for a in plan.actions] == [sync.CONVERT]

    sync.apply(plan, manifest=man)
    assert links.inspect(homes["default"] / "plugins" / "demo").is_link
    assert sync.plan(man).pending == []


def test_link_survives_the_windows_extended_length_prefix(repo, homes):
    """`os.readlink` returns \\\\?\\C:\\... on Windows; a naive comparison makes a
    correct link look wrong and relinks it on every single run."""
    target = homes["default"] / "plugins" / "demo"
    links.link_dir(repo / "demo-plugin", target)

    state = links.inspect(target)
    assert state.is_link
    assert state.target is not None
    assert not str(state.target).startswith("\\\\?\\")
    assert state.target.resolve() == (repo / "demo-plugin").resolve()


def test_removing_a_link_does_not_touch_the_source(repo, homes):
    target = homes["default"] / "plugins" / "demo"
    links.link_dir(repo / "demo-plugin", target)

    assert links.remove(target)
    assert not target.exists()
    assert (repo / "demo-plugin" / "plugin.yaml").is_file(), "source must survive"


# ── staging ─────────────────────────────────────────────────────────────────

def test_a_staged_skill_pack_is_withheld_not_installed(repo, homes):
    """Skills have no allow-list, so installing one IS loading it. Staging a
    skill surface must mean not putting it on disk at all."""
    man = build_manifest(repo, homes, [{
        "name": "heavy",
        "source": "demo-skills",
        "profiles": ["default"],
        "surfaces": [{"kind": "skill-pack", "category": "heavy", "enable": "staged"}],
    }])

    plan = sync.plan(man)
    assert [a.verdict for a in plan.actions] == [sync.STAGED]
    assert plan.pending == [], "staged work is not pending work"

    sync.ensure_dirs(man)
    sync.apply(plan, manifest=man)
    assert not (homes["default"] / "skills" / "heavy").exists()


def test_a_staged_plugin_is_installed_but_left_off(repo, homes):
    """A plugin CAN stage honestly, because plugins.enabled is a real gate."""
    man = build_manifest(repo, homes, [{
        "name": "demo",
        "source": "demo-plugin",
        "profiles": ["default"],
        "surfaces": [{"kind": "agent-plugin", "install_as": "demo", "enable": "staged"}],
    }])

    plan = sync.plan(man)
    assert [a.verdict for a in plan.actions] == [sync.CREATE]

    sync.ensure_dirs(man)
    sync.apply(plan, manifest=man)
    assert (homes["default"] / "plugins" / "demo").exists()


# ── config editing ──────────────────────────────────────────────────────────

CONFIG = """# A hand-tuned config with comments that must survive.
model:
  default: some-model   # trailing comment
plugins:
  enabled:
    - alpha
    - zeta
  disabled: []
  entries:
    alpha:
      allow_tool_override: false

# A trailing comment block.
display:
  skin: neon-ghost
"""


def test_enable_inserts_sorted_and_changes_nothing_else(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG, encoding="utf-8")

    config_edit.set_enabled(path, "mid", on=True, apply=True)
    after = path.read_text(encoding="utf-8")

    assert config_edit.read_enabled(path) == ["alpha", "mid", "zeta"]
    assert "# A hand-tuned config" in after
    assert "# trailing comment" in after
    assert "# A trailing comment block." in after
    assert "skin: neon-ghost" in after

    # Exactly one line added, nothing reflowed.
    assert after.splitlines()[:2] == CONFIG.splitlines()[:2]
    assert len(after.splitlines()) == len(CONFIG.splitlines()) + 1

    # And the file is still valid YAML meaning the same thing elsewhere.
    parsed = yaml.safe_load(after)
    assert parsed["display"]["skin"] == "neon-ghost"
    assert parsed["plugins"]["entries"]["alpha"] == {"allow_tool_override": False}


def test_enable_and_disable_round_trip(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG, encoding="utf-8")

    config_edit.set_enabled(path, "mid", on=True, apply=True)
    config_edit.set_enabled(path, "mid", on=False, apply=True)
    assert path.read_text(encoding="utf-8") == CONFIG


def test_enable_is_idempotent(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG, encoding="utf-8")

    first = config_edit.set_enabled(path, "mid", on=True, apply=True)
    body = path.read_text(encoding="utf-8")
    second = config_edit.set_enabled(path, "mid", on=True, apply=True)

    assert "enable" in first
    assert "already on" in second
    assert path.read_text(encoding="utf-8") == body


def test_dry_run_writes_nothing(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG, encoding="utf-8")

    config_edit.set_enabled(path, "mid", on=True, apply=False)
    assert path.read_text(encoding="utf-8") == CONFIG


def test_backups_never_collide(tmp_path):
    """Four enables finish inside the same second; each pre-image must survive."""
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG, encoding="utf-8")

    for name in ("b", "c", "d", "e"):
        config_edit.set_enabled(path, name, on=True, apply=True)

    backups = sorted(tmp_path.glob("config.yaml.fleet-bak-*"))
    assert len(backups) == 4, f"expected one backup per write, got {len(backups)}"
    assert backups[0].read_text(encoding="utf-8") == CONFIG, "the ORIGINAL must be recoverable"


# ── porting ─────────────────────────────────────────────────────────────────

def test_port_maps_tools_and_paths(tmp_path):
    source = tmp_path / "claude" / "demo"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "---\nname: demo\ndescription: d\n---\n\n"
        "Use the Read tool, then Bash. Config lives in ~/.claude/skills.\n",
        encoding="utf-8",
    )

    result = port.port_skill(source, tmp_path / "hermes" / "demo", apply=True)
    ported = (tmp_path / "hermes" / "demo" / "SKILL.md").read_text(encoding="utf-8")

    assert "read_file tool" in ported
    assert "$HERMES_HOME/skills" in ported
    assert "~/.claude" not in ported
    assert "PORTED FROM CLAUDE CODE" in ported
    assert result.clean


def test_port_header_lands_after_the_frontmatter(tmp_path):
    """A comment above the `---` block breaks the frontmatter parse, so the
    ported skill would load with no name or description at all."""
    source = tmp_path / "claude" / "demo"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("---\nname: demo\ndescription: d\n---\n\nbody\n", encoding="utf-8")

    port.port_skill(source, tmp_path / "hermes" / "demo", apply=True)
    ported = (tmp_path / "hermes" / "demo" / "SKILL.md").read_text(encoding="utf-8")

    assert ported.startswith("---\n")
    front, _, rest = ported.partition("\n---\n")
    assert "name: demo" in front
    assert "PORTED FROM" in rest
    assert yaml.safe_load(front.lstrip("-\n"))["name"] == "demo"


def test_port_respects_skip_regions(tmp_path):
    """A skill that documents the port must not be rewritten by it."""
    source = tmp_path / "claude" / "demo"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "---\nname: demo\ndescription: d\n---\n\n"
        "Bash runs commands.\n\n"
        "<!-- port:skip -->\n`Read` maps to `read_file`.\n<!-- port:endskip -->\n",
        encoding="utf-8",
    )

    port.port_skill(source, tmp_path / "hermes" / "demo", apply=True)
    ported = (tmp_path / "hermes" / "demo" / "SKILL.md").read_text(encoding="utf-8")

    assert "terminal runs commands." in ported, "outside the region, port normally"
    assert "`Read` maps to `read_file`." in ported, "inside the region, leave it alone"


def test_port_flags_what_it_cannot_map(tmp_path):
    source = tmp_path / "claude" / "demo"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "---\nname: demo\ndescription: d\n---\n\nCall ExitPlanMode when done.\n",
        encoding="utf-8",
    )

    result = port.port_skill(source, tmp_path / "hermes" / "demo", apply=False)
    assert not result.clean
    assert any("ExitPlanMode" in w for w in result.warnings)


# ── manifest validation ─────────────────────────────────────────────────────

def test_the_real_manifest_loads():
    man = manifest_mod.load()
    # 2026-10-03: reconciled to this box. `jason` (phantam) removed, `coder` added
    # (the active coding profile), tiferet+gork retained but marked worker-managed.
    # each box loads only the profiles it owns (managed: local|worker)
    expected = {"default", "coder"} if os.name == "nt" else {"default", "tiferet"}
    assert set(man.profiles) == expected
    assert man.package("hermes-fleet").surfaces


def test_unknown_surface_kind_is_fatal(tmp_path):
    bad = tmp_path / "fleet.yaml"
    bad.write_text(
        yaml.safe_dump({
            "version": 1,
            "profiles": {"default": {"home": str(tmp_path)}},
            "packages": [{"name": "x", "surfaces": [{"kind": "not-a-kind"}]}],
        }),
        encoding="utf-8",
    )
    with pytest.raises(manifest_mod.ManifestError, match="unknown surface kind"):
        manifest_mod.load(bad)


def test_per_profile_surface_without_profiles_is_fatal(tmp_path):
    (tmp_path / "src").mkdir()
    bad = tmp_path / "fleet.yaml"
    bad.write_text(
        yaml.safe_dump({
            "version": 1,
            "profiles": {"default": {"home": str(tmp_path)}},
            "packages": [{"name": "x", "source": "src", "surfaces": [{"kind": "agent-plugin"}]}],
        }),
        encoding="utf-8",
    )
    # `source` resolves against the real repo root, so point the check at the
    # part we care about: a per-profile surface with no profiles list.
    with pytest.raises(manifest_mod.ManifestError):
        manifest_mod.load(bad)
