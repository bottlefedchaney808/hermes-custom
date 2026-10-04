# Hermes adaptation — test-driven-development

This skill's SKILL.md is runtime-agnostic; on Hermes the actions it names
resolve to these tools. The full mapping lives in [../using-superpowers/references/hermes-tools.md](../using-superpowers/references/hermes-tools.md).

| Action this skill uses | Hermes equivalent |
|---|---|
| Run the test command (watch RED, then GREEN) | `terminal` |
| Write the failing test / minimal implementation | `write_file` / `patch` |

## Model / subagent-type note

Hermes children inherit the parent model — there is no per-call model name,
no `model:`, and no `subagent_type`. Any model-pinning in the original skill
does not apply and is ignored on Hermes.
