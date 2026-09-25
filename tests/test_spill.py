from pathlib import Path

from brain_rag.spill import (
    ENTRY_DELIMITER, HIGH_WATER, LOW_WATER, POINTER_MARK, dedupe, parse, plan, size, spill,
)


import random

_WORDS = ("alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike "
          "november oscar papa quebec romeo sierra tango uniform victor whiskey xray").split()


def _entries(n, width=180):
    """Distinct prose-like entries (identical padding would dedupe into one)."""
    rng = random.Random(7)
    out = []
    for i in range(n):
        text = f"note {i}:"
        while len(text) < width:
            text += " " + rng.choice(_WORDS)
        out.append(text)
    return out


def test_below_high_water_moves_nothing():
    entries = _entries(3)
    p = plan(entries, 2200, "A")
    assert p["move"] == [] and p["keep"] == entries


def test_short_rules_stay_and_long_detail_moves_first():
    rule = "Never github-copilot."
    entries = [rule] + _entries(10) + ["note long: " + "detail " * 60]
    p = plan(entries, 2200, "A")
    assert p["move"][0].startswith("note long:")
    assert rule in p["keep"]


def test_above_high_water_trims_down_to_low_water():
    entries = _entries(11)  # ~2100 of 2200
    p = plan(entries, 2200, "A")
    assert size(p["keep"]) <= LOW_WATER * 2200
    assert any(POINTER_MARK in e for e in p["keep"])
    assert set(p["move"]) | set(p["keep"]) >= set(entries)


def test_vault_pointer_entries_are_pinned():
    pin = "Durable facts live in the vault; read [[Jason]] first."
    entries = [pin] + _entries(11)
    p = plan(entries, 2200, "A")
    assert pin in p["keep"] and pin not in p["move"]


def test_near_duplicates_keep_the_longer_wording():
    a = "Prefers MoA (model-of-artifact) over CARL for reviewing plans/specs."
    b = "Prefers MoA (model-of-artifact) to review implementation plans, not CARL."
    kept, dropped = dedupe(["other thing entirely", a, b])
    assert kept == ["other thing entirely", b] and dropped == [a]


def test_distinct_entries_are_not_merged():
    kept, dropped = dedupe(["Cell number is on the Gmail signature.", "Kalshi bankroll is separate from the desk."])
    assert len(kept) == 2 and dropped == []


def test_dry_run_touches_nothing(tmp_path):
    mem, vault = tmp_path / "mem", tmp_path / "vault"
    mem.mkdir(); vault.mkdir()
    raw = ENTRY_DELIMITER.join(_entries(11))
    (mem / "MEMORY.md").write_text(raw, encoding="utf-8")
    report = spill(mem, vault, apply=False, runner=lambda *a: None)
    assert report["files"]["MEMORY.md"]["move"]
    assert (mem / "MEMORY.md").read_text(encoding="utf-8") == raw
    assert not (vault / "Memory").exists()


def test_apply_archives_first_then_trims(tmp_path):
    mem, vault = tmp_path / "mem", tmp_path / "vault"
    mem.mkdir(); vault.mkdir()
    entries = _entries(11)
    (mem / "MEMORY.md").write_text(ENTRY_DELIMITER.join(entries), encoding="utf-8")
    calls = []
    report = spill(mem, vault, apply=True, runner=lambda args, cwd: calls.append(args[0]))
    assert calls[:3] == ["pull", "add", "commit"] and calls[-1] == "push"
    archive = (vault / "Memory" / "Hermes Memory Archive.md").read_text(encoding="utf-8")
    after = parse((mem / "MEMORY.md").read_text(encoding="utf-8"))
    for e in entries:
        assert e in after or e in archive  # nothing lost
    assert size(after) <= LOW_WATER * 2200
    assert report["committed"] and report["pushed"]


def test_failed_commit_leaves_memory_untouched(tmp_path):
    mem, vault = tmp_path / "mem", tmp_path / "vault"
    mem.mkdir(); vault.mkdir()
    raw = ENTRY_DELIMITER.join(_entries(11))
    (mem / "MEMORY.md").write_text(raw, encoding="utf-8")

    def runner(args, cwd):
        if args[0] == "commit":
            raise RuntimeError("nope")

    report = spill(mem, vault, apply=True, runner=runner)
    assert "memory untouched" in report["error"]
    assert (mem / "MEMORY.md").read_text(encoding="utf-8") == raw


def test_written_file_round_trips_for_hermes(tmp_path):
    """Hermes flags 'external drift' unless raw == delimiter.join(parsed)."""
    mem, vault = tmp_path / "mem", tmp_path / "vault"
    mem.mkdir(); vault.mkdir()
    (mem / "MEMORY.md").write_text(ENTRY_DELIMITER.join(_entries(11)), encoding="utf-8")
    spill(mem, vault, apply=True, runner=lambda *a: None)
    raw = (mem / "MEMORY.md").read_text(encoding="utf-8")
    assert raw.strip() == ENTRY_DELIMITER.join(parse(raw))
