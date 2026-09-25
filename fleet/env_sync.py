"""Keep credentials consistent across the profiles' ``.env`` files.

WHY THIS EXISTS
---------------
``hermes_cli/env_loader.py`` loads exactly ONE dotenv per run —
``<profile home>/.env``. There is no root fallback, and the line right after
the load actively deletes inherited keys::

    _clear_known_keys_missing_from_dotenv(user_env)  # inherited keys must not leak

That isolation is deliberate: a profile boundary that leaks secrets is not a
boundary. But the consequence is that every profile needs its OWN full copy of
every shared credential, maintained by hand — and nothing keeps them in step.
When this module was written, ``default`` and ``local`` held 27 byte-identical
keys plus 4 that had already diverged, and Hermes was warning that the two
shared a photon credential (a bot can only belong to one profile).

This is the same drift fleet.yaml already solves for plugins, skills and skins,
applied to the one surface it did not cover.

VALUES NEVER ENTER THIS REPO
----------------------------
fleet.yaml is committed to git. It declares KEY NAMES ONLY. Values live in the
``.env`` files and move directly between them; nothing here writes a value to
stdout, to fleet.yaml, or to any file inside the checkout. Two profiles are
compared by a truncated SHA-256 of the value, so drift is visible without
either value being shown. `fleet env` output is safe to paste into a bug
report.

THE THREE POLICIES
------------------
``shared``      must be identical everywhere. Fleet copies ``source`` -> others.
``per_profile`` each profile owns its own. Fleet never reads or writes these.
``exclusive``   per-profile AND must NOT match — two profiles holding the same
                value is the bug (the photon-token case). Reported, never
                auto-fixed: only a human can decide which profile keeps it.
``confined``    ``pattern: [profiles]`` — this credential belongs ONLY to the
                listed profiles, and fleet DELETES it from the others. The one
                place fleet removes rather than copies, so it always takes a
                backup and never runs without ``--apply``.

A key on disk that appears in none of the four is reported as ``undeclared``,
so the policy cannot rot silently as new credentials appear.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .manifest import Manifest, ManifestError, Profile

# Verdicts. Deliberately the same vocabulary as sync.py so the CLI can render
# both with one set of glyphs.
OK = "ok"
CREATE = "create"        # declared shared, absent in this profile -> append
REFRESH = "refresh"      # declared shared, value differs -> overwrite from source
REMOVE = "remove"        # confined elsewhere -> delete from this profile
MISSING = "missing"      # declared shared, absent in the SOURCE -> cannot sync
MANUAL = "manual"        # exclusive key collision -> a human decides
UNDECLARED = "undeclared"  # on disk, in no policy list -> policy is stale

# REMOVE ranks highest: it is the only verdict that destroys something.
SEVERITY = {OK: 0, UNDECLARED: 1, MANUAL: 2, MISSING: 3, REFRESH: 4, CREATE: 5, REMOVE: 6}

# `export FOO=bar` and `FOO=bar` are both valid dotenv. Capture either.
_ASSIGN = re.compile(r"^(\s*)(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")

# Appended keys land under this marker so a human reading the file knows who
# wrote them and can find the policy that did it.
_MANAGED_HEADER = "# ── fleet-managed (shared keys from fleet.yaml `env.shared`) ──"


def fingerprint(value: str) -> str:
    """Short, stable, non-reversible tag for a secret.

    Eight hex chars of SHA-256 over the value. Enough to tell "these two
    profiles disagree" from "these two agree" in a status table, useless to
    anyone who reads the table. Never log the value itself.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


@dataclass(frozen=True)
class EnvPolicy:
    """The ``env:`` block of fleet.yaml. Key names only — never values."""

    source: str
    shared: Tuple[str, ...] = ()
    per_profile: Tuple[str, ...] = ()
    exclusive: Tuple[str, ...] = ()
    # (glob pattern, profiles allowed to hold it). A pattern rather than a bare
    # key because these are named by system, not by variable: "photon does not
    # belong on local" is one decision about five keys.
    confined: Tuple[Tuple[str, Tuple[str, ...]], ...] = ()

    def confined_to(self, key: str) -> Optional[Tuple[str, ...]]:
        """Profiles allowed to hold *key*, or ``None`` if it is not confined.

        First matching pattern wins, so an exact key can be listed above a
        wildcard to carve an exception out of it.
        """
        for pattern, allowed in self.confined:
            if fnmatch(key, pattern):
                return allowed
        return None

    def classify(self, key: str) -> str:
        if self.confined_to(key) is not None:
            return "confined"
        if key in self.shared:
            return "shared"
        if key in self.exclusive:
            return "exclusive"
        if key in self.per_profile:
            return "per_profile"
        return "undeclared"


@dataclass
class EnvAction:
    """One key, in one profile, and what it needs."""

    key: str
    profile: str
    verdict: str
    detail: str = ""
    applied: Optional[str] = None

    @property
    def needs_work(self) -> bool:
        return self.verdict in (CREATE, REFRESH, REMOVE)

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "profile": self.profile,
            "verdict": self.verdict,
            "detail": self.detail,
            "applied": self.applied,
        }


@dataclass
class EnvPlan:
    actions: List[EnvAction] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def pending(self) -> List[EnvAction]:
        return [a for a in self.actions if a.verdict != OK]

    @property
    def writes(self) -> List[EnvAction]:
        return [a for a in self.actions if a.needs_work]


# ── reading ──────────────────────────────────────────────────────────────────


def parse_env(path: Path) -> Dict[str, str]:
    """``KEY -> value`` for one dotenv file. Last assignment wins, as dotenv does.

    Values are returned raw (quotes and all): this module only ever compares
    them to each other and copies them verbatim, so normalizing would risk
    changing a credential that happens to contain quoting.
    """
    if not path.is_file():
        return {}
    out: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _ASSIGN.match(line)
        if match:
            out[match.group(2)] = match.group(3).strip()
    return out


def read_all(manifest: Manifest) -> Dict[str, Dict[str, str]]:
    """``profile name -> {KEY: value}`` for every profile in the manifest."""
    return {name: parse_env(prof.home / ".env") for name, prof in manifest.profiles.items()}


# ── planning ─────────────────────────────────────────────────────────────────


def plan(manifest: Manifest, policy: EnvPolicy, *, profiles: Optional[List[str]] = None) -> EnvPlan:
    """What would change. Touches nothing.

    Idempotence is the contract, same as sync.plan: running twice must give an
    all-``ok`` plan the second time.
    """
    result = EnvPlan()
    envs = read_all(manifest)

    if policy.source not in envs:
        result.errors.append(
            f"env.source {policy.source!r} is not a profile in fleet.yaml")
        return result

    source_env = envs[policy.source]
    wanted = [n for n in envs if profiles is None or n in profiles]

    # 0. confined keys: delete from every profile not on the allow-list. Runs
    #    FIRST so a key that is both confined and (wrongly) shared is removed
    #    rather than propagated — the safe direction when the policy disagrees
    #    with itself. load_policy rejects that overlap, so this is a backstop.
    for name in wanted:
        for key in sorted(envs[name]):
            allowed = policy.confined_to(key)
            if allowed is None or name in allowed:
                continue
            result.actions.append(EnvAction(
                key=key, profile=name, verdict=REMOVE,
                detail=f"confined to {', '.join(allowed)} -- will be deleted here"))

    # 1. shared keys: propagate source -> every other profile.
    for key in policy.shared:
        if policy.confined_to(key) is not None:
            continue
        if key not in source_env:
            result.actions.append(EnvAction(
                key=key, profile=policy.source, verdict=MISSING,
                detail="declared shared but absent in the source profile"))
            continue
        want = source_env[key]
        for name in wanted:
            if name == policy.source:
                continue
            have = envs[name].get(key)
            if have is None:
                result.actions.append(EnvAction(
                    key=key, profile=name, verdict=CREATE,
                    detail=f"absent; will copy {policy.source} [{fingerprint(want)}]"))
            elif have != want:
                result.actions.append(EnvAction(
                    key=key, profile=name, verdict=REFRESH,
                    detail=f"{fingerprint(have)} -> {fingerprint(want)} (from {policy.source})"))
            else:
                result.actions.append(EnvAction(key=key, profile=name, verdict=OK))

    # 2. exclusive keys: two profiles holding the SAME value is the bug.
    for key in policy.exclusive:
        holders = {n: e[key] for n, e in envs.items() if key in e}
        by_value: Dict[str, List[str]] = {}
        for name, value in holders.items():
            by_value.setdefault(value, []).append(name)
        for value, names in by_value.items():
            if len(names) > 1:
                result.actions.append(EnvAction(
                    key=key, profile=", ".join(sorted(names)), verdict=MANUAL,
                    detail=f"same value [{fingerprint(value)}] in {len(names)} profiles "
                           f"-- must be unique; fleet will not choose for you"))

    # 3. anything on disk we have no policy for. Not an error, but the policy
    #    is now stale and someone should say which bucket it belongs in.
    declared = set(policy.shared) | set(policy.per_profile) | set(policy.exclusive)
    for name in wanted:
        for key in sorted(set(envs[name]) - declared):
            if policy.confined_to(key) is not None:
                continue
            result.actions.append(EnvAction(
                key=key, profile=name, verdict=UNDECLARED,
                detail="present on disk, in no fleet.yaml env list"))

    result.actions.sort(key=lambda a: (-SEVERITY.get(a.verdict, 0), a.key, a.profile))
    return result


# ── writing ──────────────────────────────────────────────────────────────────


def _backup(path: Path) -> Path:
    """Snapshot before writing. Never clobbers an existing backup.

    Same shape and the same reasoning as config_edit._backup: several writes in
    a row finish inside the same second, and a plain second-resolution name
    would leave only the pre-image of the LAST edit — the one state you least
    need. The counter makes every write's pre-image survivable.
    """
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.fleet-bak-{stamp}")
    counter = 2
    while backup.exists():
        backup = path.with_name(f"{path.name}.fleet-bak-{stamp}-{counter}")
        counter += 1
    backup.write_bytes(path.read_bytes())
    return backup


def _rewrite(path: Path, updates: Dict[str, str], removals: Iterable[str] = ()) -> None:
    """Apply ``KEY -> value`` to a dotenv, surgically, and delete ``removals``.

    An existing key is replaced ON ITS OWN LINE, preserving indentation, an
    ``export`` prefix, and every comment and blank line in the file. New keys
    are appended under a single managed header. Removed keys have their whole
    line dropped — a commented-out tombstone would leave the credential sitting
    in a profile that was just told it may not have it.

    The file is never regenerated from the parse, because a round-trip through
    a parser is exactly how comments and ordering get lost — and this file is
    the only copy of some of these credentials.
    """
    original = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    newline = "\r\n" if "\r\n" in original else "\n"
    lines = original.splitlines()
    remaining = dict(updates)
    drop = set(removals)
    kept: List[str] = []

    for line in lines:
        match = _ASSIGN.match(line)
        if not match:
            kept.append(line)
            continue
        key = match.group(2)
        if key in drop:
            continue  # delete the line outright
        if key in remaining:
            indent = match.group(1)
            prefix = "export " if line.lstrip().startswith("export ") else ""
            kept.append(f"{indent}{prefix}{key}={remaining.pop(key)}")
        else:
            kept.append(line)

    lines = kept

    if remaining:
        if lines and lines[-1].strip():
            lines.append("")
        if _MANAGED_HEADER not in original:
            lines.append(_MANAGED_HEADER)
        for key in sorted(remaining):
            lines.append(f"{key}={remaining[key]}")

    path.write_text(newline.join(lines) + newline, encoding="utf-8")


def apply(plan_obj: EnvPlan, manifest: Manifest, policy: EnvPolicy) -> None:
    """Execute a plan's CREATE/REFRESH actions. Everything else is report-only.

    MANUAL (exclusive collisions) and UNDECLARED are never written: the first
    needs a human to pick a winner, the second needs a policy decision. Writing
    either one automatically would be fleet guessing about credentials.
    """
    envs = read_all(manifest)
    source_env = envs[policy.source]

    updates_by: Dict[str, Dict[str, str]] = {}
    removals_by: Dict[str, List[str]] = {}
    for action in plan_obj.writes:
        if action.verdict == REMOVE:
            removals_by.setdefault(action.profile, []).append(action.key)
        else:
            updates_by.setdefault(action.profile, {})[action.key] = source_env[action.key]

    for name in sorted(set(updates_by) | set(removals_by)):
        profile: Profile = manifest.profiles[name]
        path = profile.home / ".env"
        if path.is_file():
            backup = _backup(path)
            note = f"backed up to {backup.name}"
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            note = "created"
        _rewrite(path, updates_by.get(name, {}), removals_by.get(name, ()))
        for action in plan_obj.writes:
            if action.profile == name:
                action.applied = note


# ── manifest loading ─────────────────────────────────────────────────────────


def load_policy(manifest_path: Path) -> Optional[EnvPolicy]:
    """Read the ``env:`` block out of fleet.yaml. ``None`` when absent.

    Validates loudly, like manifest.load: a key listed in two buckets is a
    contradiction, and silently picking one would make the policy a lie.
    """
    import yaml

    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    block = raw.get("env")
    if not block:
        return None

    source = block.get("source")
    if not source:
        raise ManifestError("env: block has no `source:` profile")

    shared = tuple(block.get("shared") or ())
    per_profile = tuple(block.get("per_profile") or ())
    exclusive = tuple(block.get("exclusive") or ())

    for label_a, bucket_a, label_b, bucket_b in (
        ("shared", shared, "per_profile", per_profile),
        ("shared", shared, "exclusive", exclusive),
        ("per_profile", per_profile, "exclusive", exclusive),
    ):
        overlap = sorted(set(bucket_a) & set(bucket_b))
        if overlap:
            raise ManifestError(
                f"env: {', '.join(overlap)} listed in both `{label_a}` and `{label_b}`")

    raw_confined = block.get("confined") or {}
    if not isinstance(raw_confined, dict):
        raise ManifestError("env.confined must be a mapping of `pattern: [profiles]`")
    confined: List[Tuple[str, Tuple[str, ...]]] = []
    for pattern, allowed in raw_confined.items():
        if isinstance(allowed, str):
            allowed = [allowed]
        if not allowed:
            raise ManifestError(
                f"env.confined[{pattern!r}] lists no profiles. An empty allow-list would "
                f"delete the key everywhere, which is never what a confine means; drop the "
                f"entry instead.")
        confined.append((str(pattern), tuple(str(a) for a in allowed)))

    # A key that is both confined and declared elsewhere is a contradiction:
    # one list says "copy this around", the other says "delete it from there".
    # plan() resolves it safely (remove wins), but a policy that needs a
    # tie-break is a policy someone should fix.
    policy = EnvPolicy(source=source, shared=shared, per_profile=per_profile,
                       exclusive=exclusive, confined=tuple(confined))
    for label, bucket in (("shared", shared), ("exclusive", exclusive),
                          ("per_profile", per_profile)):
        clash = sorted(k for k in bucket if policy.confined_to(k) is not None)
        if clash:
            raise ManifestError(
                f"env: {', '.join(clash)} is in `{label}` but also matches a `confined` "
                f"pattern — pick one")

    return policy


# ── proposing a policy from what is already on disk ──────────────────────────


def propose(manifest: Manifest, source: str) -> str:
    """Draft an ``env:`` block from the CURRENT state of the .env files.

    Classification is a starting point, not a verdict. It can only reason from
    agreement between profiles, and agreement is ambiguous:

      * identical in 2+ profiles -> `shared` (they already agree; keep them so)
      * differs between profiles -> `per_profile` (someone set them apart)
      * bot/channel identity     -> `exclusive` (for these, identical IS the bug)
      * present in only ONE      -> REVIEW. Nothing to compare, and the two
                                    explanations are opposites: an account-wide
                                    key the other profiles are MISSING, or a
                                    credential that is genuinely private.
      * identical AND secret-ish -> REVIEW. Two profiles holding the same secret
                                    can be deliberate sharing or the accident
                                    Hermes warns about ("the bot can only belong
                                    to one profile").

    The review bucket is emitted commented-out, with the owning profile noted,
    so nothing lands in a policy by default that the tool had to guess at.

    Emits KEY NAMES ONLY. The output is a draft to read, not to paste blind.
    """
    # Narrow on purpose, and narrowed twice. A bare `TOKEN` match swept up
    # HF_TOKEN (an account-wide API key, not a per-bot identity). `PEER_TOKENS`
    # was worse: A2A_PEER_TOKENS is a MUTUAL allow-list ("alice:tok1,bob:tok2")
    # that every peer must hold identically to authenticate the others, so
    # calling it exclusive inverted the requirement. `HOME_CHANNEL` came out
    # too -- where an agent reports is a choice, not an identity.
    identity_hint = re.compile(
        r"(BOT_TOKEN|AGENT_NAME|_PORT$|PUBLIC_URL"
        r"|SERVICE_ACCOUNT|SUBSCRIPTION_NAME|DASHBOARD_HOST|WEBHOOK)")
    # "Identical" is not proof of intent for these; make a human confirm.
    secretish = re.compile(r"(SECRET|_TOKEN|PRIVATE_KEY)")

    envs = read_all(manifest)
    every_key = sorted({k for env in envs.values() for k in env})

    shared: List[str] = []
    per_profile: List[str] = []
    exclusive: List[str] = []
    review: List[Tuple[str, str]] = []

    for key in every_key:
        holders = {n: e[key] for n, e in envs.items() if key in e}
        distinct = set(holders.values())
        if identity_hint.search(key):
            exclusive.append(key)
        elif len(holders) == 1:
            owner = next(iter(holders))
            review.append((key, f"only in {owner} — shared-but-missing, or private?"))
        elif len(distinct) == 1 and secretish.search(key):
            review.append((key, f"identical in {len(holders)} profiles — "
                                f"deliberate, or an accidental share?"))
        elif len(distinct) == 1 and source not in holders:
            # Agreed-on everywhere it appears, but the authoritative profile is
            # not one of them -- declaring it shared would plan a guaranteed
            # MISS on every run. Either the source needs the key or it is not
            # really fleet-wide; both are decisions, not guesses.
            review.append((key, f"agreed in {len(holders)} profiles but absent "
                                f"in source ({source})"))
        elif len(distinct) == 1:
            shared.append(key)
        else:
            per_profile.append(key)

    def block(name: str, keys: List[str], comment: str) -> str:
        body = "\n".join(f"    - {k}" for k in keys) or "    []"
        return f"  # {comment}\n  {name}:\n{body}\n"

    return (
        "# ── credentials ─────────────────────────────────────────────────────────────\n"
        "# hermes_cli/env_loader.py loads ONE dotenv per run (<profile home>/.env) and\n"
        "# deletes inherited keys on purpose, so every profile needs its own copy of\n"
        "# every shared credential. Nothing upstream syncs them; `fleet env` does.\n"
        "#\n"
        "# KEY NAMES ONLY. This file is committed -- no value ever belongs here.\n"
        "env:\n"
        f"  # Whose value wins for a `shared` key.\n  source: {source}\n\n"
        + block("shared", shared,
                "Must be identical everywhere. `fleet env sync --apply` propagates these.")
        + "\n"
        + block("per_profile", per_profile,
                "Each profile owns its own. Fleet never reads or writes these.")
        + "\n"
        + block("exclusive", exclusive,
                "Per-profile AND must not match: two profiles sharing one is the bug.\n"
                "  # Reported, never auto-fixed -- only a human picks which profile keeps it.")
        + "\n"
        + "  # ── NEEDS A DECISION ──────────────────────────────────────────────────────\n"
          "  # These could not be classified from the disk, so they are left OUT of every\n"
          "  # list above -- `fleet env` will report each as `undeclared` until you move it\n"
          "  # into one. Guessing here would either leak a private credential into another\n"
          "  # profile or leave a profile silently missing an account-wide key.\n"
        + ("".join(f"  #   {key:<38} {why}\n" for key, why in review) or "  #   (none)\n")
    )
