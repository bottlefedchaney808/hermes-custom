---
name: multimodel-review
description: Use when auditing codebases for bugs, validating critical code paths across repos, or when the user asks for cross-model review, code audit, or multi-agent validation. Prefer this when correctness matters more than speed.
source: codex-skills-local@2026-06-21
migrated_at: '2026-06-21'
note: previously codex-only at ~/.codex/skills/; migrated to claude-config SSOT
---

# Multimodel Review

Use Codex sub-agents to separate initial audit from verification. The main purpose is to reduce false positives before making fixes.

## Workflow

1. Identify a narrow review scope with the highest risk code paths.
2. Ask focused reviewer agents to inspect disjoint domain slices in parallel.
3. Verify each non-trivial finding with a second pass before acting on it.
4. Triage by real-world impact, not just code smell.
5. Fix only confirmed issues.

## Review Targets

Prioritize:

- Money-at-risk logic: formulas, pricing, order execution, position sizing
- Data integrity: aggregation pipelines, sync scripts, sign conventions
- Concurrency: shared mutable state, cache races, connection pools
- User-facing correctness: display logic, formatting, signal presentation

## Agent Pattern

### Audit pass

Spawn worker or explorer agents in parallel for separate clusters of files. Give each agent:

- A bounded file set
- The exact correctness question to answer
- Instructions to report bugs, regressions, or missing tests only
- A requirement to cite file paths and line numbers

Keep each audit batch small. More than about 6 to 8 files per agent usually gets shallow.

### Verification pass

For every meaningful finding, run a second agent to cross-check it. The verifier should:

- Read the same code directly
- Trace callers and downstream consumers
- Look for guards or invariants the first pass may have missed
- Classify the finding as `confirmed`, `partially correct`, `false positive`, or `needs more context`

Do not skip verification for "obvious" bugs in unfamiliar code.

## Triage

When presenting results, order by severity and lead with findings. For each item include:

- What is wrong
- Where it is
- Why it matters in behavior or business terms
- Whether it is confirmed or still uncertain

## Fix Phase

Before editing:

1. Re-read the relevant code directly.
2. Make the smallest change that resolves the confirmed issue.
3. Run targeted validation.
4. Report residual risk if verification was incomplete.

## Common False Positives

- Misread data flow: validation or filtering happened upstream
- Missing guards: reviewer ignored a nearby check
- Wrong target: bug is on a different code path
- Stale assumption: reviewer relied on outdated architecture

## Codex Notes

- Use `spawn_agent` only when the user explicitly asks for sub-agents, delegation, or parallel agent work.
- If the user did not grant that, still follow the same two-pass mindset locally: audit first, then verify before changing code.
