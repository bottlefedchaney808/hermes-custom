"""Map a working directory or vault path to exactly one leg.

One note, one leg (spec section 6). Unknown work is Development, never a
fourth bucket and never a guess that lands trading notes in Construction.
"""
from __future__ import annotations

LEGS: tuple[str, ...] = ("Construction", "Development", "Trading")

# Checked in order; first match wins. Construction and Trading are the
# narrow, high-confidence cases — everything else is Development.
_CWD_MARKERS: tuple[tuple[str, str], ...] = (
    ("tiferet", "Construction"),
    ("constructiondevelopment", "Construction"),
    ("financialdevelopment", "Trading"),
    ("vol_suite", "Trading"),
    ("eventtrading", "Trading"),
)

DEFAULT_LEG = "Development"


def leg_for_cwd(cwd: str | None) -> str:
    """Leg for a session's working directory. Unknown -> Development."""
    if not cwd:
        return DEFAULT_LEG
    haystack = str(cwd).replace("\\", "/").lower()
    for marker, leg in _CWD_MARKERS:
        if marker in haystack:
            return leg
    return DEFAULT_LEG


def leg_for_vault_path(rel_path: str) -> str | None:
    """Leg from a vault-relative path's first segment; None when not in a leg."""
    if not rel_path:
        return None
    first = str(rel_path).replace("\\", "/").split("/")[0]
    return first if first in LEGS else None
