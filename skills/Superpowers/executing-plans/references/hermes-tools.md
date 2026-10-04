# Hermes adaptation — executing-plans

This skill's SKILL.md is runtime-agnostic; on Hermes the actions it names
resolve to these tools. The full mapping lives in [../using-superpowers/references/hermes-tools.md](../using-superpowers/references/hermes-tools.md).

| Action this skill uses | Hermes equivalent |
|---|---|
| Read the plan file | `read_file` |
| Create todos for the plan items | `todo_list` |
| Run verifications / the test suite | `terminal` |
| Invoke the finishing-a-development-branch sub-skill | `skill_view(name='finishing-a-development-branch')` |

## Model / subagent-type note

Hermes children inherit the parent model — there is no per-call model name,
no `model:`, and no `subagent_type`. Any model-pinning in the original skill
does not apply and is ignored on Hermes.
