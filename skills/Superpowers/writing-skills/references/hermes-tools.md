# Hermes adaptation — writing-skills

This skill's SKILL.md is runtime-agnostic; on Hermes the actions it names
resolve to these tools. The full mapping lives in [../using-superpowers/references/hermes-tools.md](../using-superpowers/references/hermes-tools.md).

| Action this skill uses | Hermes equivalent |
|---|---|
| Write the skill's `SKILL.md` / supporting files | `write_file` |
| Run baseline / pressure scenarios with subagents | `delegate_task` |
| Run `render-graphs.js` / `wc -w` | `terminal` |

## Model / subagent-type note

Hermes children inherit the parent model — there is no per-call model name,
no `model:`, and no `subagent_type`. Any model-pinning in the original skill
does not apply and is ignored on Hermes.
