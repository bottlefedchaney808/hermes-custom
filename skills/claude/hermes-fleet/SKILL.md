---
name: hermes-fleet
description: >-
  Use when installing, removing, enabling, updating, or auditing anything across
  the multi-profile Hermes setup — plugins, skills, skins, desktop panes, MCP
  servers — or when asked what is installed where, why a plugin is missing from
  one profile, or why a change on one profile did not appear on another. Covers
  the fleet.yaml manifest, the fleet CLI, and the per-profile vs global rules.
---

# Operating the Hermes fleet

There are three Hermes profiles on this machine and they are three separate
installations. Anything you install by hand reaches exactly one of them. This
skill is how you avoid discovering that six weeks later.

| Profile | Home | What it is |
|---|---|---|
| `default` | `~/.hermes` | Daily driver. Gets everything, including the lab. |
| `local` | `~/.hermes/profiles/local` | Local model on the GPU. Gets the lab. |
| `tiferet` | `~/.hermes/profiles/tiferet` | Construction only, company-facing. Deliberately narrow. |

## The rule that explains most confusion

**Agent plugins, skills and skins are per profile. Desktop plugins are global.**

Hermes resolves agent plugins from exactly one directory — `get_hermes_home()
/ "plugins"` — with no shared path and no search list
(`hermes_cli/plugins_discovery.py`). Skills and skins work the same way. So
"install it once" is not a thing that exists for those.

Desktop plugins are the opposite, and on purpose. `~/.hermes/desktop-plugins/`
is the one root, and the app actively migrates any profile-scoped copy up into
it, because a desktop plugin extends the *app*, not an agent — a pane that
vanished every time you switched profiles read as a bug. Never install a desktop
plugin into a profile folder; it will be moved out from under you.

## Do not install by hand

Everything is declared in `fleet.yaml` at the root of the `hermes-custom`
checkout, and materialized by the `fleet` CLI. Hand-installing is how the
machine got into the state this system exists to fix: `claude-code` was a live
symlink on one profile and a frozen copy on two others, and the skin pack was on
two profiles of three, with nothing anywhere able to report it.

```bash
fleet status              # what is installed where, and what drifted
fleet status -v           # every surface, not just the summary
fleet sync                # DRY RUN — what would change
fleet sync --apply        # make the disk match fleet.yaml
fleet sync --apply -p tiferet    # one profile
fleet sync --apply -k takeoff-lens  # one package
fleet enable  <package>   # add its plugin ids to plugins.enabled
fleet disable <package>
fleet json                # the whole state, machine-readable
```

Every command dry-runs by default. Nothing writes without `--apply`.

## Adding something new

1. Put the source in the `hermes-custom` checkout (a git submodule or a plain
   directory — both work; `fleet.yaml` just needs a path).
2. Add a `packages:` entry declaring its surfaces and which profiles get it.
3. `fleet sync` to see the plan, then `fleet sync --apply`.
4. `fleet enable <name> --apply` if it is a plugin that needs allow-listing.
5. Restart the gateway: `hermes gateway restart`.

Surface kinds: `agent-plugin`, `skill`, `skill-pack`, `skin-pack`,
`desktop-plugin`, `claude-skill`, `mcp-server`, `python-package`, `external`.

## When NOT to link

The default mode is a directory symlink back into the checkout, so one edit
reaches all three profiles. Two cases break that, and both have bitten already:

- **A package that writes inside its own folder.** Declare `mode: copy`.
  A symlinked package writing to itself dirties the checkout.
- **A package whose installer assembles a payload from elsewhere in its repo.**
  Declare `kind: external` and defer to the installer. `token-optimizer` is the
  worked example: its Hermes plugin imports three sibling modules that live in
  `skills/token-optimizer/scripts/`, so a bare symlink of `hermes/` produces a
  plugin whose imports are broken — a regression upstream has already shipped
  and fixed once. Fleet reports it and runs nothing.

## Answering "why isn't this working"

Work down this list; it is ordered by how often each one is the answer.

1. **Installed but not enabled.** Hermes does not auto-load plugins by directory
   presence. The id must be in `plugins.enabled` in *that profile's*
   `config.yaml`. `fleet status -v` shows installed state; `fleet enable` fixes
   the config. Backend API routes from a plugin are also gated on this, so an
   un-enabled dashboard plugin has a dead backend as well as no tab.
2. **Enabled but the gateway is stale.** `hermes gateway restart`.
3. **Installed on the wrong profile.** Check which one is actually live:
   `cat ~/.hermes/active_profile` (absent means `default`).
4. **Desktop pane missing.** Look in `~/.hermes/desktop-plugins/`, never in a
   profile. For a unified package, the desktop half is copied out of
   `plugins/<name>/desktop/` and re-copied only when `plugin.js` is *newer* —
   so rebuild the artifact, do not just edit the source.
5. **Skill not being picked up.** Skills are `SKILL.md` in a directory, either
   `skills/<name>/` or one category deep at `skills/<category>/<name>/`.
   Anything else is invisible.

## Context is the real budget

Every skill in a profile is serialized into the skills prompt and paid on every
turn. `fleet status` prints that number per profile. Before adding a skill pack
to a profile, ask whether that profile will actually use it — this is exactly
why `tiferet` stays narrow. A company-facing bot does not need 73 life-operating
skills, and the cost is not one-time.

<!-- port:skip -->
## Claude Code's own half

Some skills live on both sides. The file format is identical — a Claude skill
and a Hermes skill are literally the same `SKILL.md` with the same frontmatter —
so porting is never a format conversion. It is a content port: tool names
(`Read` → `read_file`, `Bash` → `terminal`, `Task` → `delegate_task`) and paths
(`~/.claude` → `$HERMES_HOME`, which is four different directories depending on
the active profile).

`skills/claude/` is the source of truth; `skills/hermes/` is generated:

```bash
fleet port             # dry run, lists every substitution
fleet port --apply     # regenerate skills/hermes/
```

Edit the Claude side and re-port. Never hand-edit a generated twin — it carries
a provenance header saying so, and your edit will be overwritten on the next
port.
<!-- port:endskip -->
