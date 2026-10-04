# Hermes adaptation — subagent-driven-development

This skill's SKILL.md is runtime-agnostic; on Hermes the actions it names
resolve to these tools. The full mapping lives in [../using-superpowers/references/hermes-tools.md](../using-superpowers/references/hermes-tools.md).

| Action this skill uses | Hermes equivalent |
|---|---|
| Dispatch implementer / task-reviewer / fix subagents | `delegate_task` (pass `implementer-prompt.md` / `task-reviewer-prompt.md` / `final-review-prompt.md` as the task) |
| Create todos for all tasks | `todo_list` |
| Run the `review-package` / `task-brief` helper scripts | `terminal` |
| Read the plan / diff / report files | `read_file` |

## Model / subagent-type note

Hermes children inherit the parent model — there is no per-call model name,
no `model:`, and no `subagent_type`. Any model-pinning in the original skill
does not apply and is ignored on Hermes.
The `gpt-5.6-sol` / `reasoning_effort` model-pinning in this skill does NOT apply on Hermes — delegated children inherit the parent model; there is no per-call model name or `subagent_type`.
