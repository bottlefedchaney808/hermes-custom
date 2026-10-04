# Grok Build Tool Mapping

Skills speak in actions ("dispatch a subagent", "create a todo", "read a file"). On Grok Build these resolve to the tools below.

| Action skills request | Grok equivalent |
|----------------------|-----------------|
| Read a file | `read_file` |
| Create a file | `write` |
| Edit a file | `search_replace` |
| Run a shell command | `run_terminal_command` |
| Search file contents | `grep` |
| Find files by name / list directories | `list_dir` |
| Fetch a URL | `web_fetch` or `open_page` |
| Search the web | `web_search` |
| Invoke a skill | Skills load natively — read the matching `SKILL.md` (or the user runs `/name`) and follow it |
| Dispatch a subagent (`Subagent (general-purpose):` template) | `spawn_subagent` with `subagent_type` (`general-purpose`, `explore`, `plan`, or a named agent) |
| Multiple parallel dispatches | Multiple `spawn_subagent` calls in one response |
| Wait for subagent result | `get_command_or_subagent_output` with the returned subagent id |
| Task tracking ("create a todo", "mark complete") | `todo_write` |
| Ask the user a structured question | `ask_user_question` |

## Instructions file

When a skill mentions "your instructions file", on Grok this is **`AGENTS.md`** (also `Agents.md`, `AGENT.md`). Grok also loads `CLAUDE.md` / `Claude.md` / `CLAUDE.local.md` for Claude compatibility. Home-level rules live in `$GROK_HOME/rules/` (default `~/.grok/rules/`). Project rules also load from `<dir>/.grok/rules/`.

## Personal skills directory

User-level skills live at **`$GROK_HOME/skills/`** (default `~/.grok/skills/`). Grok also scans `~/.claude/skills/` and `~/.cursor/skills/` when those compatibility cells are on (the default). Extra libraries can be added with `[skills].paths` in `~/.grok/config.toml`. Each skill is a subdirectory containing a `SKILL.md` with `name` and `description` frontmatter. A same-named user skill overrides a bundled copy.

## Subagents

`spawn_subagent` is available by default. Disable with `GROK_SUBAGENTS=0` or `[subagents] enabled = false`. Built-in types: `general-purpose` (full tools), `explore` (read-only research), `plan` (read-only planning). Pass a complete, self-contained `prompt`; children do not inherit parent conversation context.

## Environment Detection

Skills that create worktrees or finish branches should detect their environment with read-only git commands before proceeding:

```bash
git rev-parse --git-dir
git rev-parse --git-common-dir
git branch --show-current
```

- git-dir != git-common-dir → already in a linked worktree (skip creation)
- branch empty → detached HEAD (cannot branch/push/PR from that checkout)
