"""`fleet` — the command line over fleet.yaml.

    fleet status                 what is installed where, and what has drifted
    fleet sync                   DRY RUN: what would change
    fleet sync --apply           make the disk match fleet.yaml
    fleet sync --apply -p local  ...for one profile only
    fleet sync --apply -k takeoff-lens ...for one package only
    fleet enable  <package>      add its plugin ids to plugins.enabled
    fleet disable <package>      take them back out
    fleet env                    credential drift across profile .env files
    fleet env --propose          draft the env: block from what is on disk
    fleet json                   the whole state as JSON (what the UI reads)

Dry run is the default everywhere. Nothing writes without ``--apply``.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from . import env_sync, state, sync
from .config_edit import set_enabled
from .manifest import MANIFEST_PATH, Manifest, ManifestError, load

# Verdict -> (glyph, ANSI colour). Plain ASCII glyphs: this runs in cmd.exe too.
MARK = {
    sync.OK: ("ok  ", "32"),
    sync.CREATE: ("NEW ", "36"),
    sync.RELINK: ("LINK", "33"),
    sync.CONVERT: ("CONV", "33"),
    sync.REFRESH: ("SYNC", "36"),
    sync.MANUAL: ("man ", "35"),
    sync.MISSING: ("MISS", "31"),
    sync.STAGED: ("HELD", "34"),
    # env_sync reuses this vocabulary; only `undeclared` is its own.
    env_sync.REMOVE: ("DEL ", "31"),
    env_sync.UNDECLARED: ("????", "35"),
}


def _color(text: str, code: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"


def _tag(verdict: str) -> str:
    glyph, code = MARK.get(verdict, ("?   ", "37"))
    return _color(glyph, code)


def cmd_status(manifest: Manifest, args) -> int:
    snap = state.snapshot(manifest)

    print()
    print(_color("PROFILES", "1"))
    header = f"  {'profile':<10} {'skills':>6} {'plugins':>8} {'skins':>6} {'prompt':>9}  role"
    print(_color(header, "2"))
    for profile in snap["profiles"]:
        marker = "*" if profile["active"] else " "
        kb = f"{profile['prompt_snapshot_bytes'] / 1024:.0f}K" if profile["prompt_snapshot_bytes"] else "-"
        role = (profile["role"] or "").split(".")[0][:52]
        print(
            f" {marker}{profile['name']:<10} {profile['skills']:>6} "
            f"{profile['plugins_installed']:>8} {profile['skins']:>6} {kb:>9}  {role}"
        )

    print()
    print(_color("PACKAGES", "1"))
    for pkg in snap["packages"]:
        scope = "global" if pkg["global"] else ",".join(pkg["profiles"]) or "-"
        print(f"  {_tag(pkg['verdict'])} {pkg['name']:<24} {_color(scope, '2')}")
        if args.verbose:
            for action in pkg["actions"]:
                if action["verdict"] == sync.OK and not args.all:
                    continue
                where = action["profile"] or "global"
                detail = f"  {action['detail']}" if action["detail"] else ""
                print(f"       {_tag(action['verdict'])} {where:<10} {action['target']}{detail}")

    print()
    if snap["errors"]:
        print(_color("ERRORS", "31"))
        for err in snap["errors"]:
            print(f"  {err}")
        print()
    pending = snap["pending"]
    if pending:
        print(f"  {pending} action(s) pending — run {_color('fleet sync --apply', '1')}")
    else:
        print(f"  {_color('in sync', '32')} with fleet.yaml")
    print()
    return 1 if snap["errors"] else 0


def cmd_sync(manifest: Manifest, args) -> int:
    if args.apply:
        sync.ensure_dirs(manifest)
    plan = sync.plan(manifest, only=args.package, profiles=args.profile)

    if args.apply:
        sync.apply(plan, manifest=manifest)

    shown = plan.actions if args.all else plan.pending
    if not shown:
        print(f"\n  {_color('nothing to do', '32')} — disk matches fleet.yaml\n")
        return 0

    print()
    for action in shown:
        where = action.profile or "global"
        applied = f"  -> {_color(action.applied, '32')}" if action.applied else ""
        detail = f"  {_color(action.detail, '2')}" if action.detail else ""
        print(f"  {_tag(action.verdict)} {action.package:<22} {where:<9} {action.target}{detail}{applied}")

    print()
    if not args.apply:
        print(f"  dry run — {len(plan.pending)} change(s). Re-run with {_color('--apply', '1')}.")
    for err in plan.errors:
        print(_color(f"  error: {err}", "31"))
    print()
    return 1 if plan.errors else 0


def _enable_ids(manifest: Manifest, package: str, *, on: bool) -> List[tuple]:
    """(profile, plugin_id) pairs this command may touch.

    Turning something ON is gated on the manifest asking for it: a surface with
    `enable: false` is a capability someone decided stays off, and
    `fleet enable <package>` must not quietly flip it because it happens to live
    in the same package. `bot-kit-agent` is the case that matters —
    `texting-style` is a style tweak, `orgo-computer` gives bots shell and
    click/type control of a real machine, and they ship together.

    Turning something OFF has no such gate. Disabling more than asked is safe;
    enabling more than asked is not.
    """
    pkg = manifest.package(package)
    out = []
    for surface in pkg.surfaces:
        if surface.kind != "agent-plugin":
            continue
        if on and surface.enable is not True:
            continue
        name = surface.install_as or (surface.from_ or pkg.name).split("/")[-1]
        for profile in manifest.targets(pkg):
            out.append((profile, name))
    return out


def cmd_toggle(manifest: Manifest, args, *, on: bool) -> int:
    pkg = manifest.package(args.package_name)
    pairs = _enable_ids(manifest, args.package_name, on=on)
    # Surfaces that `sync` is deliberately withholding. Flipping the config does
    # NOT release these, because skills have no enable gate — the only way to
    # commit them is to change the manifest, which keeps fleet.yaml the single
    # source of truth instead of growing a second, hidden one.
    held = [s for s in pkg.surfaces if s.enable == "staged" and s.kind != "agent-plugin"]

    if not pairs and not held:
        print(f"  {args.package_name} has nothing to toggle")
        return 1

    print()
    for profile, plugin_id in pairs:
        line = set_enabled(profile.config_path, plugin_id, on=on, apply=args.apply)
        print(f"  {profile.name:<10} {line}")

    if held and on:
        print()
        print(_color("  still withheld:", "34"))
        for surface in held:
            print(f"    {surface.kind} from {surface.from_ or '.'}")
        print(
            "\n  Skills have no allow-list — a skill that exists is a skill that is\n"
            "  loaded and paid for on every turn, so there is nothing for this command\n"
            "  to switch. To commit them, edit fleet.yaml:\n"
            f"    packages: - name: {pkg.name} -> surfaces: -> change `enable: staged` to `enable: true`\n"
            "  then run `fleet sync --apply`. The git diff is the record of the decision."
        )

    print()
    if not args.apply:
        print(f"  dry run — re-run with {_color('--apply', '1')}. "
              f"Restart the gateway afterwards ({_color('hermes gateway restart', '1')}).")
        print()
    return 0


def cmd_json(manifest: Manifest, args) -> int:
    print(json.dumps(state.snapshot(manifest), indent=2))
    return 0


def cmd_port(manifest: Manifest, args) -> int:
    """Regenerate the Hermes twins of the Claude-authored skills."""
    from . import port as port_mod
    from .manifest import REPO_ROOT

    source_root = REPO_ROOT / "skills" / "claude"
    target_root = REPO_ROOT / "skills" / "hermes"

    if args.skill:
        source = source_root / args.skill
        if not source.is_dir():
            print(_color(f"  no such Claude skill: {source}", "31"))
            return 1
        results = [port_mod.port_skill(source, target_root / args.skill, apply=args.apply)]
    else:
        results = port_mod.port_tree(source_root, target_root, apply=args.apply)

    if not results:
        print(f"\n  nothing to port — {source_root} holds no skills\n")
        return 0

    print()
    dirty = 0
    for result in results:
        mark = _color("ok  ", "32") if result.clean else _color("WARN", "33")
        print(f"  {mark} {result.name:<32} {result.files} file(s), {len(result.substitutions)} substitution(s)")
        if args.verbose:
            for line in result.substitutions:
                print(f"         {_color(line, '2')}")
        for warning in result.warnings:
            dirty += 1
            print(f"         {_color(warning, '33')}")

    print()
    if not args.apply:
        print(f"  dry run — re-run with {_color('--apply', '1')} to write {target_root}")
    if dirty:
        print(f"  {dirty} item(s) need a human decision — see skills/PORTING.md")
    print()
    return 0


def cmd_docs(manifest: Manifest, args) -> int:
    """Regenerate each package's HERMES.md from the manifest."""
    from . import docs as docs_mod

    results = docs_mod.generate(manifest, apply=args.apply)
    print()
    for name, path, changed in results:
        if path is None:
            print(f"  {_color('skip', '2')} {name:<24} no source directory in this repo")
        elif changed:
            print(f"  {_color('WRITE', '36')} {name:<24} {path}")
        else:
            print(f"  {_color('ok   ', '32')} {name:<24} up to date")
    print()
    if not args.apply:
        print(f"  dry run — re-run with {_color('--apply', '1')}")
        print()
    return 0


def cmd_env(manifest: Manifest, args) -> int:
    """Credential drift across the profiles' .env files.

    Never prints a value. Drift is shown as truncated SHA-256, so this output is
    safe to paste into a bug report; see fleet/env_sync.py for why that matters.
    """
    if args.propose:
        print(env_sync.propose(manifest, args.source or "default"))
        return 0

    try:
        policy = env_sync.load_policy(MANIFEST_PATH)
    except ManifestError as exc:
        print(_color(f"fleet.yaml env: {exc}", "31"), file=sys.stderr)
        return 2

    if policy is None:
        print("\n  fleet.yaml has no `env:` block — credentials are unmanaged.")
        print(f"  Draft one from what is on disk:  {_color('fleet env --propose', '1')}\n")
        return 1

    plan = env_sync.plan(manifest, policy, profiles=args.profile)
    if args.apply:
        env_sync.apply(plan, manifest=manifest, policy=policy)

    shown = plan.actions if args.all else plan.pending
    if not shown:
        print(f"\n  {_color('nothing to do', '32')} — every declared key agrees\n")
        return 0

    print()
    for action in shown:
        applied = f"  -> {_color(action.applied, '32')}" if action.applied else ""
        detail = f"  {_color(action.detail, '2')}" if action.detail else ""
        print(f"  {_tag(action.verdict)} {action.key:<34} {action.profile:<22}{detail}{applied}")

    print()
    if not args.apply and plan.writes:
        print(f"  dry run — {len(plan.writes)} write(s). Re-run with {_color('--apply', '1')}.")
    manual = [a for a in plan.actions if a.verdict == env_sync.MANUAL]
    if manual:
        print(f"  {len(manual)} collision(s) need a human — fleet never picks "
              f"which profile keeps a secret.")
    for err in plan.errors:
        print(_color(f"  error: {err}", "31"))
    print()
    return 1 if plan.errors else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fleet", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="what is installed where")
    status.add_argument("-v", "--verbose", action="store_true", help="show every surface")
    status.add_argument("-a", "--all", action="store_true", help="include in-sync surfaces")
    status.set_defaults(func=cmd_status)

    sync_cmd = sub.add_parser("sync", help="make the disk match fleet.yaml")
    sync_cmd.add_argument("--apply", action="store_true", help="actually write (default: dry run)")
    sync_cmd.add_argument("-p", "--profile", action="append", help="limit to a profile")
    sync_cmd.add_argument("-k", "--package", action="append", help="limit to a package")
    sync_cmd.add_argument("-a", "--all", action="store_true", help="list in-sync surfaces too")
    sync_cmd.set_defaults(func=cmd_sync)

    for verb, on in (("enable", True), ("disable", False)):
        toggle = sub.add_parser(verb, help=f"{verb} a package's plugins in every target profile")
        toggle.add_argument("package_name", metavar="package")
        toggle.add_argument("--apply", action="store_true", help="actually write (default: dry run)")
        toggle.set_defaults(func=lambda m, a, on=on: cmd_toggle(m, a, on=on))

    env_cmd = sub.add_parser("env", help="credential drift across profile .env files")
    env_cmd.add_argument("--apply", action="store_true", help="actually write (default: dry run)")
    env_cmd.add_argument("-p", "--profile", action="append", help="limit to a profile")
    env_cmd.add_argument("-a", "--all", action="store_true", help="list in-sync keys too")
    env_cmd.add_argument("--propose", action="store_true",
                         help="draft an env: block from the current .env files (names only)")
    env_cmd.add_argument("--source", help="with --propose: the authoritative profile")
    env_cmd.set_defaults(func=cmd_env)

    js = sub.add_parser("json", help="full state as JSON (what the desktop pane reads)")
    js.set_defaults(func=cmd_json)

    port_cmd = sub.add_parser("port", help="regenerate skills/hermes/ from skills/claude/")
    port_cmd.add_argument("skill", nargs="?", help="one skill name (default: all)")
    port_cmd.add_argument("--apply", action="store_true", help="actually write (default: dry run)")
    port_cmd.add_argument("-v", "--verbose", action="store_true", help="list every substitution")
    port_cmd.set_defaults(func=cmd_port)

    docs_cmd = sub.add_parser("docs", help="regenerate each package's HERMES.md from fleet.yaml")
    docs_cmd.add_argument("--apply", action="store_true", help="actually write (default: dry run)")
    docs_cmd.set_defaults(func=cmd_docs)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = load()
    except ManifestError as exc:
        print(_color(f"fleet.yaml: {exc}", "31"), file=sys.stderr)
        return 2
    return args.func(manifest, args)


if __name__ == "__main__":
    raise SystemExit(main())
