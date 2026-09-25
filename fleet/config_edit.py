"""Surgical edits to a profile's ``config.yaml``.

These files are hand-tuned and heavily commented — default's is 18 KB of
deliberate choices. Round-tripping them through PyYAML would reformat the whole
file and throw every comment away, so we do not parse-and-rewrite. We find the
exact list we care about as TEXT and touch only those lines. Everything else in
the file comes out byte-identical.

Only one key is ever edited: ``plugins.enabled``. Every write takes a timestamped
backup beside the original first.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

_TOP_KEY = re.compile(r"^(\w[\w.-]*):\s*(.*)$")
_ITEM = re.compile(r"^(\s*)-\s+(.+?)\s*$")


class ConfigEditError(RuntimeError):
    """The file isn't shaped the way we need. Never guess — stop and report."""


def _find_block(lines: List[str], key: str) -> Optional[Tuple[int, int]]:
    """[start, end) line range of a top-level ``key:`` block, body included."""
    start = None
    for i, line in enumerate(lines):
        match = _TOP_KEY.match(line)
        if match and match.group(1) == key:
            start = i
            break
    if start is None:
        return None
    for j in range(start + 1, len(lines)):
        line = lines[j]
        if line.strip() and not line[0].isspace() and not line.lstrip().startswith("#"):
            return start, j
    return start, len(lines)


def _find_list(lines: List[str], block: Tuple[int, int], key: str) -> Optional[Tuple[int, int, str]]:
    """(header line, end of items, item indent) for a nested ``key:`` list."""
    start, end = block
    header = None
    for i in range(start + 1, end):
        stripped = lines[i].strip()
        if stripped.startswith(f"{key}:"):
            header = i
            break
    if header is None:
        return None

    inline = lines[header].split(":", 1)[1].strip()
    if inline and inline != "[]":
        raise ConfigEditError(f"{key} is an inline list ({inline!r}); edit it by hand")

    indent = " " * (len(lines[header]) - len(lines[header].lstrip()) + 2)
    last = header + 1
    for i in range(header + 1, end):
        match = _ITEM.match(lines[i])
        if match and len(match.group(1)) >= len(indent):
            indent = match.group(1)
            last = i + 1
            continue
        if lines[i].strip() == "":
            continue
        break
    return header, last, indent


def read_enabled(config_path: Path) -> List[str]:
    """The plugin ids currently in ``plugins.enabled``. Empty when absent."""
    if not config_path.is_file():
        return []
    lines = config_path.read_text(encoding="utf-8").splitlines()
    block = _find_block(lines, "plugins")
    if block is None:
        return []
    found = _find_list(lines, block, "enabled")
    if found is None:
        return []
    header, last, _ = found
    out = []
    for i in range(header + 1, last):
        match = _ITEM.match(lines[i])
        if match:
            out.append(match.group(2).strip().strip("'\""))
    return out


def _backup(config_path: Path) -> Path:
    """Snapshot the file before writing. Never clobbers an existing backup.

    Several enables in a row finish inside the same second, and a plain
    second-resolution name meant the fourth write overwrote the snapshot of the
    original file — leaving only the state from just before the LAST edit, which
    is the one state you least need. The suffix counter makes each write's
    pre-image survivable.
    """
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = config_path.with_suffix(f".yaml.fleet-bak-{stamp}")
    counter = 2
    while backup.exists():
        backup = config_path.with_suffix(f".yaml.fleet-bak-{stamp}-{counter}")
        counter += 1
    backup.write_bytes(config_path.read_bytes())
    return backup


def set_enabled(config_path: Path, plugin_id: str, *, on: bool, apply: bool = False) -> str:
    """Add or remove `plugin_id` in ``plugins.enabled``.

    Returns a one-line description of what changed (or would change). The file
    is only written when ``apply`` is true; everything else is a dry run.
    """
    if not config_path.is_file():
        return f"skip: {config_path} does not exist"

    text = config_path.read_text(encoding="utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()

    block = _find_block(lines, "plugins")
    if block is None:
        if not on:
            return f"already off: no plugins block in {config_path.name}"
        addition = [f"plugins:{newline}", f"  enabled:{newline}", f"    - {plugin_id}{newline}"]
        if apply:
            _backup(config_path)
            with config_path.open("a", encoding="utf-8", newline="") as handle:
                handle.write(newline + "".join(addition))
        return f"create plugins.enabled with {plugin_id}"

    found = _find_list(lines, block, "enabled")
    if found is None:
        if not on:
            return f"already off: no plugins.enabled in {config_path.name}"
        insert_at = block[0] + 1
        indent = "  "
        lines[insert_at:insert_at] = [f"{indent}enabled:", f"{indent}  - {plugin_id}"]
        if apply:
            _backup(config_path)
            config_path.write_text(newline.join(lines) + newline, encoding="utf-8", newline="")
        return f"add plugins.enabled: [{plugin_id}]"

    header, last, indent = found
    current = []
    for i in range(header + 1, last):
        match = _ITEM.match(lines[i])
        if match:
            current.append((i, match.group(2).strip().strip("'\"")))

    present = [i for i, value in current if value == plugin_id]

    if on:
        if present:
            return f"already on: {plugin_id} in {config_path.name}"
        # Keep the list sorted so the diff is small and the file stays readable.
        insert_at = last
        for i, value in current:
            if value > plugin_id:
                insert_at = i
                break
        if lines[header].rstrip().endswith("[]"):
            lines[header] = lines[header].rstrip()[:-2].rstrip()
        lines.insert(insert_at, f"{indent}- {plugin_id}")
        verb = "enable"
    else:
        if not present:
            return f"already off: {plugin_id} not in {config_path.name}"
        for i in reversed(present):
            del lines[i]
        verb = "disable"

    if apply:
        _backup(config_path)
        config_path.write_text(newline.join(lines) + newline, encoding="utf-8", newline="")
    return f"{verb} {plugin_id} in {config_path.name}"
