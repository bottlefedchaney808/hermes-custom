"""The explicit vault door: 'put this in the brain'.

The second and last vault writer (spec section 5). A leg is mandatory —
refusing beats guessing, because a wrong leg is exactly the cross-leg mixing
the vault rule exists to prevent.
"""
from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path
from typing import Any, Callable

from brain_rag.leg import LEGS


def _run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


def _safe_title(title: str) -> str:
    cleaned = "".join(ch for ch in title if ch not in '\\/:*?"<>|').strip()
    return cleaned or "Untitled"


def remind(
    vault_dir: str | Path,
    *,
    leg: str,
    title: str,
    body: str,
    runner: Callable[[list[str], Path], None] | None = None,
) -> dict[str, Any]:
    """Write or append a thin note in one leg, then commit it."""
    vault = Path(vault_dir)
    git = runner or _run_git
    if leg not in LEGS:
        return {"error": f"A leg is required; expected one of {LEGS}, got {leg!r}."}
    if not body or not body.strip():
        return {"error": "Empty body; nothing to remember."}
    if not vault.is_dir():
        return {"error": f"vault clone not found: {vault}"}

    rel = f"{leg}/{_safe_title(title)}.md"
    target = vault / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()

    if target.exists():
        with target.open("a", encoding="utf-8") as fh:
            fh.write(f"\n\n## {stamp}\n\n{body.strip()}\n")
    else:
        target.write_text(
            "\n".join([
                "---", "type: note", f"leg: {leg}", f"created: {stamp}", "---",
                "", f"# {_safe_title(title)}", "", f"## {stamp}", "", body.strip(), "",
            ]),
            encoding="utf-8",
        )

    try:
        git(["add", rel], vault)
        git(["commit", "-m", f"docs(vault): remind — {_safe_title(title)}"], vault)
    except Exception as exc:  # noqa: BLE001
        return {"path": rel, "committed": False, "error": f"commit failed: {exc}"}
    return {"path": rel, "committed": True, "error": None}
