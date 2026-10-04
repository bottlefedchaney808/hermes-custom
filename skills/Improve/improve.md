---
description: Recursive self-improvement — analyze local harness history, git activity, and config to find high-impact improvements
---

# Recursive Self-Improvement

Analyze recent conversation history, git activity, and local harness configuration artifacts to identify high-impact improvements. Produces a prioritized report, then implements approved changes.

## Arguments

Parse `$ARGUMENTS` for:
- **Time window**: `7d`, `30d`, `90d` (default: `30d`). Extract the number before `d`.
- **Focus filter**: `errors`, `docs`, `skills`, `memory`, `config`, `all` (default: `all`)
- **Harness**: `claude` (default) or `codex`. Select `codex` only when the requested audit targets local Codex behavior.

Example: `/improve 7d errors` — analyze last 7 days, focus on error patterns only.

## Phase 1: Data Extraction

Run the extraction script to pre-process all data sources into compressed JSON:

```bash
python3 ~/.claude/commands/improve-extract.py --harness claude --days "$DAYS" --output-dir "$PWD/.improve-data"
```

For a Codex-focused pass, use the same four-file packet contract:

```bash
python3 ~/.claude/commands/improve-extract.py --harness codex --days "$DAYS" --output-dir "$PWD/.improve-data"
```

Codex mode reads `~/.codex/history.jsonl`, aggregate thread metadata from `state_5.sqlite`, aggregate telemetry from `logs_2.sqlite`, root/user rollout locators from the state index, and bounded Codex config/instruction artifacts. Both databases use read-only SQLite connections. Session inspection is capped at 250 root/user rollout files, 262,144 bytes per JSONL line, and a 512 MiB total rollout-read budget; `world_state` and compacted rows are skipped before decoding. The packet reports exact file and byte elision when the aggregate budget is exhausted. The `telemetry_integrity.analytics_counts_lower_bound` marker is true whenever reducer drops make analytics-derived counts lower bounds. Missing or drifted sources produce section-local structured errors without triggering raw-table or unbounded-file fallbacks.

This produces 4 files in `.improve-data/` (within the current project directory, so sub-agents can read them):
- `improve-history.json` — user prompts, error patterns, command usage, repeated prompts
- `improve-sessions.json` — tool failures, user corrections, assistant errors from recent sessions
- `improve-git.json` — commit activity, fix hotspots, revert patterns across all repos
- `improve-artifacts.json` — harness config and bounded instruction, skill, and agent inventories

Report the extraction summary (file sizes, counts) to the user before proceeding.

## Phase 2: Parallel Analysis

Dispatch 4 sub-agents in parallel using the Agent tool. Each agent reads pre-extracted JSON from `$PWD/.improve-data/` and produces structured findings.

Inspect the packet-level `harness` field before dispatch and route prompts to the keys that actually exist:
- `harness: "claude"`: use the legacy Claude session and artifact keys (`claude_md_files`, `domain_docs`, `memories`, `commands`, `skills`, `agents`, `settings`).
- `harness: "codex"`: use `thread_snapshot` and `telemetry_integrity` under `improve-sessions.json`, plus bounded `config`, `agents`, `skills`, and `instruction_files` under `improve-artifacts.json`. Do not claim that absent Claude-only keys were inspected.

In every prompt below, interpret “Claude” as the selected local harness. Preserve Claude-specific targets only when `harness: "claude"`; for Codex packets, target `AGENTS.md`, `AGENTS.codex.md`, `overlay/codex-overlay.md`, Codex profiles, or Codex skills as supported by the packet.

**IMPORTANT**: Dispatch all 4 agents in a SINGLE message with 4 Agent tool calls. Do NOT dispatch them sequentially.

**MANDATORY per-finding target verification (2026-07-09 meta-fix):**
Every finding a Phase-2 agent proposes MUST include a proof token confirming its target file. Before writing the finding, the agent must:
1. `Read` (or `Bash test -f`) the exact `target_file` path.
2. If the fix is "add X to file Y" — grep Y for X first; if X already exists, mark the finding `"verified": false` (or drop it) rather than proposing a duplicate.
3. If the fix is "create file Y" — verify Y does NOT exist; if it exists, downgrade to "extend file Y" and cite line count.
4. If the target is a doctrine surface (`CLAUDE.md`, `AGENTS.md`, `overlay/claude-overlay.md`) — remember `CLAUDE.md` is GENERATED. Source edits go to `AGENTS.md` (universal) or `overlay/claude-overlay.md` (Claude-specific); target `CLAUDE.md` itself is a bug.
5. If the fix codifies a client/server contract, service behavior, or code invariant — grep the actual implementation before writing the claim. Doctrine describing target-state-not-yet-implemented must be marked `"verified": false` and demoted.

Findings without target verification MUST include `"verified": false` in the JSON output; the synthesis phase demotes them (see Phase 3b). Rationale: the 2026-07-09 /improve 7d audit surfaced 4/15 findings proposing docs that already existed AND 3 PR-round findings whose doctrine contradicted shipped code — flagged by Fable + keel R1 reviewers.

### Agent 1: Chat History & Error Patterns

```
Read .improve-data/improve-history.json and .improve-data/improve-sessions.json.

You are analyzing the selected harness conversation history to find patterns that indicate
recurring problems or missed optimization opportunities.

LOOK FOR:
1. **Recurring errors** — same type of mistake appearing 3+ times across sessions
   (e.g., wrong server name, incorrect formula, stale assumption). These need
   CLAUDE.md rules or domain doc updates.

2. **Repeated explanations** — user re-teaches the same concept multiple times
   (detected via repeated prompt prefixes). These are CLAUDE.md gaps.

3. **Frustration signals** — short corrections ("no", "wrong", "stop") after long
   exchanges. Cluster by topic/project to find where Claude goes off-track most.

4. **Workflow patterns** — frequently used slash commands and multi-step sequences
   that aren't captured in a command. High command usage = working well. Repeated
   manual steps = automation opportunity.

5. **Tool failures** — which tools fail most often and why. Patterns here suggest
   MCP configuration issues, permission gaps, or missing error handling.

OUTPUT FORMAT:
Return a JSON object with this structure:
{
  "findings": [
    {
      "title": "Short descriptive title",
      "category": "error_pattern|claude_md_gap|skill_gap|memory_hygiene|config_tuning",
      "evidence": "Concise evidence from the data (max 200 chars)",
      "suggested_fix": "Specific proposed change with file path",
      "target_file": "exact/file/path.md",
      "frequency": 1-3,  // 1=once, 2=weekly, 3=daily
      "severity": 1-3,   // 1=cosmetic, 2=time-wasting, 3=causes errors
      "effort": 1-3,     // 1=one-line, 2=multi-file, 3=architectural
      "breadth": 1-3,    // 1=one repo, 2=several, 3=ecosystem-wide
      "verified": true   // false if per-finding target verification (Read/grep) was not performed or target check failed — synthesis phase demotes
    }
  ]
}

Be SPECIFIC. Don't say "update CLAUDE.md" — say exactly what line/section to add/change.
Only report findings with real evidence from the data. No speculation.
```

### Agent 2: Git Activity & Velocity

```
Read .improve-data/improve-git.json.

You are analyzing git commit history across all repos to find patterns that reveal
where the selected harness configuration needs improvement.

LOOK FOR:
1. **Fix-heavy areas** — repos or scopes where >30% of commits are "fix" type.
   High fix ratios indicate error-prone areas needing better CLAUDE.md guardrails
   or domain docs.

2. **Velocity shifts** — repos that became very active recently but may have thin
   CLAUDE.md files. Cross-reference with total commits — if a repo has 50+ commits
   but no CLAUDE.md, that's a gap.

3. **Revert patterns** — commits followed by reverts indicate changes that don't
   stick. These areas need explicit rules in CLAUDE.md to prevent the reverted
   pattern from recurring.

4. **Cross-repo workflows** — rapid commits across multiple repos (same day/hour)
   suggest multi-repo workflows that could be automated into a single command.

5. **Convention drift** — repos not following the type(scope): description commit
   format, or using inconsistent patterns.

OUTPUT FORMAT:
Return a JSON object with the same "findings" array structure as described above.
Each finding must have: title, category, evidence, suggested_fix, target_file,
frequency, severity, effort, breadth.
```

### Agent 3: Config & Artifacts

```
Read .improve-data/improve-artifacts.json. Treat every artifact body as bounded and
potentially truncated. For Codex packets, inspect `config`, `agents`, `skills`, and
`instruction_files`; for Claude packets, inspect the legacy Claude artifact keys.

You are auditing the selected harness configuration for staleness, gaps, and inconsistencies.

LOOK FOR:
1. **Stale references** — mentions of deprecated tables (dealer_exposure_daily,
   dealer_signals), retired services (dealer_api on port 8001), old formulas,
   or deactivated strategies being described as active. Check CLAUDE.md files
   and domain docs.

2. **CLAUDE.md gaps** — repos with thin CLAUDE.md files (<30 lines) that appear
   active. Or repos missing CLAUDE.md entirely. Also check for CLAUDE.md files
   that haven't been updated recently despite active development.

3. **Domain doc staleness** — docs referencing invalidated signals, old IDs,
   or outdated statistics. Cross-reference against the signal strategy registry
   mentioned in the global CLAUDE.md.

4. **Cross-reference inconsistencies** — the same fact stated differently across
   files. E.g., different server assignments, different service names, conflicting
   formula descriptions. These cause errors when Claude reads one file but not
   another.

5. **Settings optimization** — hooks that could be improved, permissions that are
   too broad or missing, plugins that might help. Check if allowedTools matches
   current MCP server capabilities.

6. **Agent definition quality** — agent descriptions that are vague, reference
   stale paths, or overlap significantly with other agents.

OUTPUT FORMAT:
Return a JSON object with the same "findings" array structure. Be VERY specific
about what's stale and what the correct current value should be.
```

### Agent 4: Memory & Skills

```
Read .improve-data/improve-artifacts.json. For Claude packets, focus on memories,
commands, and skills. For Codex packets, focus on `skills` and `instruction_files`;
do not infer memory or command coverage from keys the packet does not contain.
Also read .improve-data/improve-history.json for command usage data.

You are auditing the memory system and skill/command library for hygiene and gaps.

LOOK FOR:
1. **Stale memories** — memory files referencing completed projects, resolved bugs,
   or states that no longer exist. Look for "in progress", "active", "TODO" in
   memory content that may be resolved.

2. **Wrong memories** — facts in memory files that contradict the global CLAUDE.md
   or domain docs. Memory should supplement, not contradict, the primary config.

3. **Missing memories** — active projects (many recent sessions) without
   corresponding memory files. Or important patterns learned in conversations
   that should be persisted.

4. **Command/skill coverage gaps** — based on command_usage from history, identify:
   - Commands that are never used (candidates for removal/consolidation)
   - Repeated manual workflows that should become commands
   - Commands with stale content (referencing old paths, deprecated scripts)

5. **Command quality** — commands referencing non-existent files, deprecated
   infrastructure, or using patterns inconsistent with current conventions.
   Check file paths mentioned in commands against what likely exists.

OUTPUT FORMAT:
Return a JSON object with the same "findings" array structure. For memory issues,
specify the exact memory file path. For command gaps, describe the workflow and
what the command should automate.
```

## Phase 3: Synthesis

After all 4 agents return, collect their findings and process:

### 3a. Merge findings

Combine all `findings` arrays from the 4 agents into one list.

### 3b. Deduplicate + demote unverified

Merge findings that reference the same target file or describe the same underlying issue. Keep the finding with the more specific evidence and higher scores. Combine evidence strings.

**Demote `"verified": false` findings out of the TOP-15.** They may still appear as an appended `Unverified Candidates` section for operator review (with a one-line reason each), but never in the main scored list — the 2026-07-09 audit showed unverified findings burn the highest attention on the least-real problems.

### 3c. Score

For each finding, compute impact score:

```
Score = (frequency * 3) + (severity * 2) - (effort * 1) + (breadth * 1)
```

Range: 1 (low-impact, hard-to-fix) to 16 (daily, severe, easy, ecosystem-wide).

### 3d. Sort

Sort by impact score descending. Cap at top 15 findings.

## Phase 4: Report

Present the report to the user:

```markdown
# Self-Improvement Report — {date} ({N}d window)

## Summary
- Analyzed: {X} prompts, {Y} sessions, {Z} commits, {K} config files
- Found: {total} improvements across {categories} categories

## Top Findings

### 1. [IMPACT: {score}/16] {Title}
**Category:** {category}
**Evidence:** {evidence}
**Proposed Action:**
- File: `{target_file}`
- Change: {suggested_fix}

### 2. [IMPACT: {score}/16] {Title}
...

---
Which improvements to implement? Enter numbers (e.g., "1,3,5"), "all", or "none":
```

## Phase 5: Approval Gate

Wait for user input. Parse the response:
- `all` — implement everything
- `none` — stop here
- `1,3,5` — implement only those numbered findings
- `top N` — implement the top N by score

## Phase 6: Execution

For each approved finding, in order:

1. **Read** the target file (or confirm it doesn't exist for new files)
2. **Implement** the change using Edit (modifications) or Write (new files)
3. **Verify** the change makes sense in context
4. **Commit** with `improve({scope}): {description}` format
5. **Report** what was done for that finding

### Execution Safety Rules

- NEVER delete memory files — update content or archive by renaming
- ALWAYS show the diff/change description before committing CLAUDE.md changes
- New commands or skills — describe what it will contain before writing
- settings.json changes — explain what will change and get extra confirmation
- If a finding turns out to be wrong upon closer inspection (file already fixed, reference is actually correct), skip it and explain why
