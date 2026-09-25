"""Find the hermes-custom checkout that owns ``fleet.yaml``, from anywhere.

This plugin is normally a symlink into the checkout, so walking up from
``__file__`` lands on the repo root and the import just works. But it can also
be a real copy (symlink privilege missing, or someone dragged the folder), and
the web server imports ``plugin_api.py`` by absolute path with its own module
name — so neither ``__package__`` nor a relative import can be relied on.

Resolution order, most explicit first:
  1. ``$HERMES_FLEET_REPO``
  2. the plugin's configured ``repo_root``, passed in by the caller
  3. walk up from this file looking for ``fleet.yaml``
  4. the well-known default, ``~/hermes-custom``

Every door returns a reason when it fails. A fleet UI that cannot find its
manifest should say exactly that, not render an empty grid that reads as
"nothing is installed".
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, Tuple

MARKER = "fleet.yaml"


def _has_marker(path: Path) -> bool:
    return (path / MARKER).is_file() and (path / "fleet" / "manifest.py").is_file()


def find_repo(configured: Optional[str] = None) -> Tuple[Optional[Path], str]:
    """(repo root, explanation). The root is None when nothing matched."""
    env = os.environ.get("HERMES_FLEET_REPO")
    if env:
        candidate = Path(os.path.expanduser(env)).resolve()
        if _has_marker(candidate):
            return candidate, "HERMES_FLEET_REPO"
        return None, f"HERMES_FLEET_REPO={env} has no {MARKER}"

    if configured:
        candidate = Path(os.path.expanduser(configured)).resolve()
        if _has_marker(candidate):
            return candidate, "config repo_root"
        return None, f"repo_root={configured} has no {MARKER}"

    here = Path(__file__).resolve()
    for parent in here.parents:
        if _has_marker(parent):
            return parent, "walked up from the plugin"

    fallback = Path(os.path.expanduser("~/hermes-custom")).resolve()
    if _has_marker(fallback):
        return fallback, "default ~/hermes-custom"

    return None, (
        f"no {MARKER} found above {here.parent} — set HERMES_FLEET_REPO or the "
        f"plugin's repo_root config to the hermes-custom checkout"
    )


def load_fleet(configured: Optional[str] = None):
    """Import the ``fleet`` package from the checkout. Raises RuntimeError with
    a usable message rather than an ImportError with none."""
    root, why = find_repo(configured)
    if root is None:
        raise RuntimeError(why)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    import fleet.manifest as manifest_mod  # noqa: PLC0415
    import fleet.state as state_mod  # noqa: PLC0415
    import fleet.sync as sync_mod  # noqa: PLC0415

    return root, why, manifest_mod, state_mod, sync_mod
