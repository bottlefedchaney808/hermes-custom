# Hermes Tool Mapping

Skills speak in actions ("dispatch a subagent", "create a todo", "read a file"). On Hermes these resolve to the tools below.

## Tools

| Action skills request | Hermes equivalent |
|----------------------|------------------|
| Read a file | `read_file` |
| Create a new file | `write_file` |
| Edit a file (targeted find-and-replace) | `patch` |
| Run a shell command | `terminal` |
| Search file contents | `search_files` with `target: "content"` |
| Find files by name | `search_files` with `target: "files"` |
| Fetch a URL | `web_extract` |
| Search the web | `web_search` |
| Invoke a skill | Skills load natively — `skill_view(name=...)` to load a skill's content, `skills_list()` to discover them. There is no `Skill` tool; just load the matching skill and follow it. |
| Dispatch a subagent (`Subagent (general-purpose):` template) | `delegate_task` — pass the full, self-contained prompt as the task. There is no `general-purpose` type to name. |
| Multiple parallel dispatches | Multiple `delegate_task` calls in one response |
| Task tracking ("create a todo", "mark complete") | the todo tool (`todo_list`) |

## Model / subagent-type note

Hermes children **inherit the parent model** — there is no per-call model name, no `model:`, and no `subagent_type`. Any Claude/Codex model-pinning in a skill (`model: inherit`, `model: sonnet`, `gpt-5.6-sol`, `reasoning_effort`, a named `Explore`/`Plan`/`general-purpose` subagent type) does **not apply** on Hermes and should be ignored or removed. To get a stronger pass, delegate to a capable provider rather than naming a model.

## Instructions file

When a skill mentions "your instructions file", on Hermes this is **`AGENTS.md`** (Hermes also reads `CLAUDE.md` for compatibility). The active profile's data lives under the profile directory (`~/.hermes/profiles/<profile>/`).

## Personal skills directory

User-level skills live in the active profile's skills directory (e.g. `~/.hermes/profiles/<profile>/skills/`). Each skill is a subdirectory containing a `SKILL.md` with `name` and `description` frontmatter. Skills are discovered with `skills_list()` and loaded with `skill_view(name=...)`.

## Environment Detection

Skills that create worktrees or finish branches should detect their environment with read-only git commands (via `terminal`) before proceeding:

```bash
git rev-parse --git-dir
git rev-parse --git-common-dir
git branch --show-current
```

- git-dir != git-common-dir → already in a linked worktree (skip creation)
- branch empty → detached HEAD (cannot branch/push/PR from that checkout)
