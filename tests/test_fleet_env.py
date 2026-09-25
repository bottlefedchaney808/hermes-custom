"""Tests for `fleet env` — credential sync across profile .env files.

These run against temporary directories with fake values, never the real
profiles. This module writes CREDENTIALS, so the guarantees it locks are the
ones whose failure is expensive rather than annoying:

1. no value ever reaches stdout, a plan, or fleet.yaml — only fingerprints,
2. a rewrite touches only the declared keys and preserves everything else
   byte-for-byte, because this file is the only copy of some of these secrets,
3. a pre-image backup exists before any write,
4. exclusive collisions are reported and NEVER auto-resolved,
5. sync is idempotent — a second run is a clean no-op.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fleet import env_sync  # noqa: E402
from fleet.manifest import Manifest, Profile  # noqa: E402


SECRET = "sk-super-secret-value-do-not-print"


# ── fixtures ────────────────────────────────────────────────────────────────

def _manifest(tmp_path: Path, homes: dict) -> Manifest:
    profiles = {}
    for name, body in homes.items():
        home = tmp_path / name
        home.mkdir(parents=True, exist_ok=True)
        if body is not None:
            (home / ".env").write_text(body, encoding="utf-8")
        profiles[name] = Profile(name=name, home=home)
    return Manifest(profiles=profiles, packages=[], default_mode="link",
                    claude_home=tmp_path, claude_skills_dir=tmp_path,
                    claude_source=tmp_path)


@pytest.fixture
def fleet(tmp_path: Path) -> Manifest:
    return _manifest(tmp_path, {
        "default": (
            "# a comment that must survive\n"
            f"SHARED_KEY={SECRET}\n"
            "\n"
            "export EXPORTED_KEY=exported-value\n"
            "BOT_TOKEN=default-bot\n"
            "PRIVATE_TO_DEFAULT=only-here\n"
        ),
        "local": (
            "# local's own header\n"
            "SHARED_KEY=stale-divergent-value\n"
            "BOT_TOKEN=default-bot\n"          # collision: same as default
            "LOCAL_ONLY=local-value\n"
        ),
    })


POLICY = env_sync.EnvPolicy(
    source="default",
    shared=("SHARED_KEY", "EXPORTED_KEY"),
    per_profile=("PRIVATE_TO_DEFAULT", "LOCAL_ONLY"),
    exclusive=("BOT_TOKEN",),
)


# ── 1. secrets never leak ───────────────────────────────────────────────────

def test_fingerprint_is_not_reversible_and_is_stable():
    assert env_sync.fingerprint(SECRET) == env_sync.fingerprint(SECRET)
    assert env_sync.fingerprint(SECRET) != env_sync.fingerprint(SECRET + "x")
    assert len(env_sync.fingerprint(SECRET)) == 8
    assert SECRET not in env_sync.fingerprint(SECRET)


def test_no_value_appears_anywhere_in_a_plan(fleet):
    plan = env_sync.plan(fleet, POLICY)
    blob = "\n".join(
        f"{a.key} {a.profile} {a.verdict} {a.detail} {a.applied}" for a in plan.actions)
    for leaked in (SECRET, "stale-divergent-value", "exported-value", "default-bot"):
        assert leaked not in blob, f"value leaked into the plan: {leaked}"


def test_propose_emits_names_only(fleet):
    text = env_sync.propose(fleet, "default")
    for leaked in (SECRET, "stale-divergent-value", "exported-value", "local-value"):
        assert leaked not in text, f"value leaked into the fleet.yaml proposal: {leaked}"
    assert "SHARED_KEY" in text


# ── 2. surgical rewrite ─────────────────────────────────────────────────────

def test_rewrite_preserves_comments_blank_lines_and_untouched_keys(fleet):
    path = fleet.profiles["local"].home / ".env"
    before = path.read_text(encoding="utf-8")

    env_sync._rewrite(path, {"SHARED_KEY": SECRET})
    after = path.read_text(encoding="utf-8")

    assert "# local's own header" in after
    assert "LOCAL_ONLY=local-value" in after       # untouched key survives
    assert "BOT_TOKEN=default-bot" in after
    assert f"SHARED_KEY={SECRET}" in after
    assert "stale-divergent-value" not in after
    # only the one line changed
    assert len(after.splitlines()) == len(before.splitlines())


def test_rewrite_preserves_the_export_prefix(fleet):
    path = fleet.profiles["default"].home / ".env"
    env_sync._rewrite(path, {"EXPORTED_KEY": "new-value"})
    assert "export EXPORTED_KEY=new-value" in path.read_text(encoding="utf-8")


def test_rewrite_appends_missing_keys_under_a_managed_header(fleet):
    path = fleet.profiles["local"].home / ".env"
    env_sync._rewrite(path, {"EXPORTED_KEY": "exported-value"})
    text = path.read_text(encoding="utf-8")
    assert env_sync._MANAGED_HEADER in text
    assert "EXPORTED_KEY=exported-value" in text
    assert "# local's own header" in text


def test_rewrite_does_not_duplicate_the_managed_header(fleet):
    path = fleet.profiles["local"].home / ".env"
    env_sync._rewrite(path, {"EXPORTED_KEY": "v1"})
    env_sync._rewrite(path, {"ANOTHER_KEY": "v2"})
    assert path.read_text(encoding="utf-8").count(env_sync._MANAGED_HEADER) == 1


# ── 3. a pre-image always exists ────────────────────────────────────────────

def test_apply_backs_up_before_writing(fleet):
    path = fleet.profiles["local"].home / ".env"
    original = path.read_text(encoding="utf-8")

    plan = env_sync.plan(fleet, POLICY)
    env_sync.apply(plan, manifest=fleet, policy=POLICY)

    backups = list(path.parent.glob(".env.fleet-bak-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == original


def test_backup_never_clobbers_within_the_same_second(fleet):
    path = fleet.profiles["local"].home / ".env"
    first = env_sync._backup(path)
    second = env_sync._backup(path)
    assert first != second
    assert first.exists() and second.exists()


# ── 4. collisions are reported, never resolved ──────────────────────────────

def test_exclusive_collision_is_reported_as_manual(fleet):
    plan = env_sync.plan(fleet, POLICY)
    manual = [a for a in plan.actions if a.verdict == env_sync.MANUAL]
    assert [a.key for a in manual] == ["BOT_TOKEN"]
    assert "default" in manual[0].profile and "local" in manual[0].profile


def test_apply_never_writes_an_exclusive_key(fleet):
    local = fleet.profiles["local"].home / ".env"
    plan = env_sync.plan(fleet, POLICY)
    env_sync.apply(plan, manifest=fleet, policy=POLICY)
    # still colliding -- fleet refused to pick a winner
    assert "BOT_TOKEN=default-bot" in local.read_text(encoding="utf-8")


def test_apply_never_writes_an_undeclared_key(fleet):
    local = fleet.profiles["local"].home / ".env"
    plan = env_sync.plan(fleet, POLICY)
    env_sync.apply(plan, manifest=fleet, policy=POLICY)
    assert "PRIVATE_TO_DEFAULT" not in local.read_text(encoding="utf-8")


# ── 5. idempotence ──────────────────────────────────────────────────────────

def test_second_run_is_a_clean_no_op(fleet):
    first = env_sync.plan(fleet, POLICY)
    assert first.writes, "fixture should start out of sync"
    env_sync.apply(first, manifest=fleet, policy=POLICY)

    second = env_sync.plan(fleet, POLICY)
    assert not second.writes, [
        (a.key, a.profile, a.verdict) for a in second.writes]


# ── policy validation ───────────────────────────────────────────────────────

def test_source_missing_a_shared_key_is_reported_not_written(tmp_path):
    fleet = _manifest(tmp_path, {
        "default": "OTHER=1\n",
        "local": "WANTED=has-a-value\n",
    })
    policy = env_sync.EnvPolicy(source="default", shared=("WANTED",))
    plan = env_sync.plan(fleet, policy)
    assert [a.verdict for a in plan.actions if a.key == "WANTED"] == [env_sync.MISSING]
    assert not plan.writes


def test_unknown_source_profile_is_an_error(fleet):
    plan = env_sync.plan(fleet, env_sync.EnvPolicy(source="nope", shared=("SHARED_KEY",)))
    assert plan.errors and "nope" in plan.errors[0]
    assert not plan.actions


def test_a_key_in_two_buckets_is_fatal(tmp_path):
    manifest_file = tmp_path / "fleet.yaml"
    manifest_file.write_text(
        "version: 1\nenv:\n  source: default\n  shared:\n    - DUP\n"
        "  per_profile:\n    - DUP\n", encoding="utf-8")
    with pytest.raises(Exception) as exc:
        env_sync.load_policy(manifest_file)
    assert "DUP" in str(exc.value)


def test_absent_env_block_returns_none(tmp_path):
    manifest_file = tmp_path / "fleet.yaml"
    manifest_file.write_text("version: 1\npackages: []\n", encoding="utf-8")
    assert env_sync.load_policy(manifest_file) is None


def test_missing_env_file_parses_as_empty(tmp_path):
    assert env_sync.parse_env(tmp_path / "nope.env") == {}


def test_propose_leaves_single_profile_keys_undeclared(fleet):
    """The bucket that matters: 'only in default' is ambiguous, so it must not
    be silently filed as per_profile (which would hide a profile missing an
    account-wide key)."""
    text = env_sync.propose(fleet, "default")
    declared = text.split("NEEDS A DECISION")[0]
    assert "PRIVATE_TO_DEFAULT" not in declared
    assert "PRIVATE_TO_DEFAULT" in text  # present, but in the review block


# ── confined: the only verdict that deletes ─────────────────────────────────

CONFINED = env_sync.EnvPolicy(
    source="default",
    shared=("SHARED_KEY",),
    confined=(("BOT_*", ("default",)), ("LOCAL_ONLY", ("local",))),
)


def test_confined_key_is_removed_from_disallowed_profiles(fleet):
    plan = env_sync.plan(fleet, CONFINED)
    removes = {(a.key, a.profile) for a in plan.actions if a.verdict == env_sync.REMOVE}
    assert removes == {("BOT_TOKEN", "local")}


def test_confined_pattern_matches_by_glob(fleet):
    policy = env_sync.EnvPolicy(source="default", confined=(("*_TOKEN", ("default",)),))
    assert policy.confined_to("BOT_TOKEN") == ("default",)
    assert policy.confined_to("SHARED_KEY") is None


def test_apply_deletes_the_line_and_leaves_the_rest_intact(fleet):
    path = fleet.profiles["local"].home / ".env"
    plan = env_sync.plan(fleet, CONFINED)
    env_sync.apply(plan, manifest=fleet, policy=CONFINED)
    text = path.read_text(encoding="utf-8")

    assert "BOT_TOKEN" not in text                 # gone, not commented out
    assert "# local's own header" in text          # comments survive
    assert "LOCAL_ONLY=local-value" in text        # allowed here, untouched
    assert f"SHARED_KEY={SECRET}" in text          # shared sync still applied


def test_confine_is_idempotent(fleet):
    first = env_sync.plan(fleet, CONFINED)
    assert first.writes
    env_sync.apply(first, manifest=fleet, policy=CONFINED)
    assert not env_sync.plan(fleet, CONFINED).writes


def test_confined_key_is_never_also_reported_undeclared(fleet):
    plan = env_sync.plan(fleet, CONFINED)
    undeclared = {a.key for a in plan.actions if a.verdict == env_sync.UNDECLARED}
    assert "BOT_TOKEN" not in undeclared


def test_confined_beats_shared_when_a_policy_contradicts_itself(fleet):
    """load_policy rejects this, but plan() must still fail safe: the key is
    removed rather than copied into a profile told it may not have it."""
    contradictory = env_sync.EnvPolicy(
        source="default", shared=("BOT_TOKEN",), confined=(("BOT_TOKEN", ("default",)),))
    plan = env_sync.plan(fleet, contradictory)
    verdicts = {a.verdict for a in plan.actions if a.key == "BOT_TOKEN"}
    assert verdicts == {env_sync.REMOVE}


def test_confined_overlapping_shared_is_fatal_in_the_manifest(tmp_path):
    manifest_file = tmp_path / "fleet.yaml"
    manifest_file.write_text(
        "version: 1\nenv:\n  source: default\n  shared:\n    - PHOTON_ID\n"
        '  confined:\n    "PHOTON_*": [default]\n', encoding="utf-8")
    with pytest.raises(Exception) as exc:
        env_sync.load_policy(manifest_file)
    assert "PHOTON_ID" in str(exc.value)


def test_empty_confine_allow_list_is_fatal(tmp_path):
    manifest_file = tmp_path / "fleet.yaml"
    manifest_file.write_text(
        "version: 1\nenv:\n  source: default\n  confined:\n    FOO: []\n", encoding="utf-8")
    with pytest.raises(Exception) as exc:
        env_sync.load_policy(manifest_file)
    assert "FOO" in str(exc.value)


def test_removal_takes_a_backup_first(fleet):
    path = fleet.profiles["local"].home / ".env"
    original = path.read_text(encoding="utf-8")
    plan = env_sync.plan(fleet, CONFINED)
    env_sync.apply(plan, manifest=fleet, policy=CONFINED)
    backups = list(path.parent.glob(".env.fleet-bak-*"))
    assert len(backups) == 1
    assert "BOT_TOKEN=default-bot" in backups[0].read_text(encoding="utf-8")


def test_per_profile_overlapping_confined_is_fatal(tmp_path):
    """"never touch this" and "delete it there" are contradictory instructions;
    the clash check originally covered only shared/exclusive."""
    manifest_file = tmp_path / "fleet.yaml"
    manifest_file.write_text(
        "version: 1\nenv:\n  source: default\n  per_profile:\n    - CHAT_ID\n"
        '  confined:\n    "CHAT_*": [tiferet]\n', encoding="utf-8")
    with pytest.raises(Exception) as exc:
        env_sync.load_policy(manifest_file)
    assert "CHAT_ID" in str(exc.value)


def test_mutual_secrets_are_not_classified_as_identity(tmp_path):
    """A2A_PEER_TOKENS is a peer->token allow-list every agent must hold
    IDENTICALLY. Calling it `exclusive` inverted the requirement."""
    fleet = _manifest(tmp_path, {
        "default": "A2A_PEER_TOKENS=alice:t1,bob:t2\nA2A_AGENT_NAME=one\n",
        "local": "A2A_PEER_TOKENS=alice:t1,bob:t2\nA2A_AGENT_NAME=two\n",
    })
    text = env_sync.propose(fleet, "default")
    # propose() emits no `confined` block, so bound the slice on the review
    # header or it runs to end-of-output and swallows it.
    exclusive_block = text.split("exclusive:")[1].split("NEEDS A DECISION")[0]
    assert "A2A_PEER_TOKENS" not in exclusive_block, (
        "a mutual allow-list every peer must match is not an identity")
    assert "A2A_AGENT_NAME" in exclusive_block, "agent name IS a real identity"
    # It lands in review instead: identical-and-secret is exactly the case the
    # tool must hand to a human rather than guess at.
    assert "A2A_PEER_TOKENS" in text.split("NEEDS A DECISION")[1]
