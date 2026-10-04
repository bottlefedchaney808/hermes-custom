# Hermes adaptation — brainstorming

This skill's SKILL.md is runtime-agnostic; on Hermes the actions it names
resolve to these tools. The full mapping lives in [../using-superpowers/references/hermes-tools.md](../using-superpowers/references/hermes-tools.md).

| Action this skill uses | Hermes equivalent |
|---|---|
| Create a todo for each checklist item | `todo_list` |
| Write the design doc to `docs/superpowers/specs/...` | `write_file` (then `terminal` for `git commit`), |
| Explore project files, docs, recent commits | `read_file` / `terminal` (`git log`), |

## Model / subagent-type note

Hermes children inherit the parent model — there is no per-call model name,
no `model:`, and no `subagent_type`. Any model-pinning in the original skill
does not apply and is ignored on Hermes.
