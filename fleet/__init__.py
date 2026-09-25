"""fleet — declarative install management for a multi-profile Hermes setup.

`fleet.yaml` at the repo root declares what belongs where; this package makes
the disk agree with it. See FLEET.md for the model and the reasoning.
"""

__all__ = ["manifest", "links", "sync", "state", "config_edit", "cli"]
