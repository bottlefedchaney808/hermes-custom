---
name: hygiene-audit
description: >-
  Use whenever the operator says hygiene-audit, janitor, cleanup, drain the worklog,
  clean up handoffs, boring cleanup, what's stale, check freshness, update all
  workstreams, stale sweep, or whenever /pickup's Phase A envelope crosses a
  hygiene-debt threshold.
model: inherit
---

<!-- BLOCKED: depends on /pickup, keel, the worklog (pa.workstreams / knowledge.handoffs / pa.review_loops), mcp__pa-bridge, and mcp__knowledge-base, none of which exist in Hermes. The `model: inherit` frontmatter and the `Agent`/`sonnet` distiller fan-out are also Claude-Code-only. Defer or exclude — do not fake an adaptation. -->


# /hygiene-audit — drain bookkeeping debt

`/pickup` SURFACES open work and the debt around it. `/hygiene-audit` DRAINS the debt. Both are stateless re-entry primitives — invoke either at any time.

**Why this exists.** Repeated /pickup + /improve + /autowork cycles accumulate stale rows faster than ad-hoc cleanup drains them. By the time keel writes "do not start more build lanes yet — the worklog bloat is …", every session has been writing past the issue for days. This skill is the forcing function: an explicit, reproducible drain pass with named tiers, named thresholds, and a durable handoff at the end.

**Default behavior.** Auto-mode with no arguments runs **the full pass**: Step 3 Phase B autopilot + Step 3F freshness sweep + Step 3G autowork-hydration sweep in the autopilot tier, then surfaces the Step 4 surface tier for per-item operator approval. Never silent on the surface tier. Operator directive 2026-07-24: default = do everything; opt-out via the `--no-*` flags below.

| Mode | Trigger | Autopilot tier | Surface tier |
|---|---|---|---|
| default (full pass) | `/hygiene-audit`, `/janitor`, `/cleanup` | execute B + 3F + 3G | surface for approval |
| `--autopilot` | `/hygiene-audit --autopilot` | execute B + 3F + 3G | skip (defer to next pass) |
| `--surface` | `/hygiene-audit --surface` | skip | surface only (read-only) |
| `--dry-run` | `/hygiene-audit --dry-run` | report intent (B + 3F + 3G) | report intent |
| `--freshness` | `/hygiene-audit --freshness [--cutoff-days=N]`, "check freshness / update all workstreams (most→least stale)" | execute Step 3F ONLY (skip B, 3G) | close candidates + needs-operator items |
| `--hydrate-autowork` | `/hygiene-audit --hydrate-autowork [--max=N]`, "hydrate autowork scope / unstuck the selector / fix `selector_stale_state_only`" | execute Step 3G ONLY (skip B, 3F) | low-confidence candidates + operator-input rows |
| `--no-freshness` | any pass mode | skip Step 3F | unaffected |
| `--no-hydrate-autowork` | any pass mode | skip Step 3G | unaffected |

**Flag-composition precedence** (defined 2026-07-24 to close the R1 F1 ambiguity):
- `--no-freshness` / `--no-hydrate-autowork` ALWAYS override `--freshness` / `--hydrate-autowork` for the same tier (opt-out wins).
- `--freshness` and `--hydrate-autowork` singleton flags are mutually exclusive; when both are passed together, reject with `error: --freshness and --hydrate-autowork are singleton-tier isolators; pass neither for a full pass or one at a time`.
- `--surface` (surface-only, read-only) surfaces the Step 4 traditional set PLUS 3F `close_candidate` / `needs_operator` items PLUS 3G medium/low-confidence C.5 items — same superset the default pass would surface — but skips every autopilot mutation.

**Full-pass cost note.** 3F + 3G each fan out read-only distillers (`Agent`, `sonnet`, waves ≤8) across the eligible enumerated set (F.1 caps at 300 stale rows, G.1 caps at `--max` default 100 ineligible rows). Distiller dispatch derivation: F.2 batches to ~8 rows per Agent → ≤~37 subagents; G.2 batches to ~8 rows per Agent → ≤~12 subagents; combined ~50 subagents peak on a heavily-drifted worklog. The 50-mutation autopilot safety cap applies **per tier** (B, 3F, 3G each have their own cap) — a full pass can therefore make up to ~150 autopilot mutations before halting for the next pass. `--no-freshness` / `--no-hydrate-autowork` skip a tier when the operator wants a cheaper drain.

**Thresholds** (auto-trigger from `/pickup` Step 7 — see § Threshold escalation in `/pickup`; the two WIP-cap rows are operator-ratified per pa.notes #1639 + decision #4877, 2026-07-02):
- `active_handoffs > 15` (WIP cap)
- `active_workstreams > 40` (WIP cap)
- `active_review_loops > 10`
- `proposed_workstreams > 30`
- `terminal-backed handoffs > 3` (handoff with `ws.status` in `done` / `abandoned` / `superseded` / `archived`)
- `stale active parents > 5` (active workstream with `updated_at < now() - 7d` AND no recent `pa.workstream_events`)
- `orphan handoffs > 15` (active handoff with no live ws-key match)
- `autowork-ineligible active workstreams > 40` (non-terminal workstream with `source_ref` missing any of `repo` / `base_branch` / `target_files` — starves keel `assign_work` per Step 3G rationale)

Any one threshold breach → `/pickup` Step 7 prints a one-line `🧹 HYGIENE DEBT: <counts> — run /hygiene-audit` banner above the work groups.

---

## Step 1 — Peer pre-flight (mandatory)

Delegate to `~/.claude/skills/pickup/SKILL.md` Step 1 verbatim. Same multi-signal ladder, same mutation-boundary recheck cache, same asymmetric-visibility caveat. **DB mutations on `pa.workstreams` / `pa.review_loops` are mutation boundaries** — every batch in this skill is preceded by ladder + worktree-local checks per the table in `/pickup` Step 1.

**Carve-outs (don't mutate):**
- Workstreams with an active `pa.workstream_claims` row → skip; the claim-holder owns mutation. Surface in the post-run summary as "skipped (claimed by `<owner>`)".
- Handoffs whose `working_directory` matches an active peer's worktree → skip even if backing ws looks stale; the peer's checkpoint may be live.
- Handoffs cited as a `kb_handoff` ref on a claimed parent workstream → skip; the orchestrator depends on them.

---

## Step 2 — Phase A: inventory

ONE direct PA Bridge MCP call (cheap, typed, no fan-out):

```
mcp__pa-bridge__triage_digest(
  max_workstreams=60,
  max_handoffs=60,
  max_inbox=15,
  max_recommendations=15,
  max_routine_failures=15,
  max_freshness_top=10,
  max_bytes=30000)
```

Then ONE batch of focused SELECTs (do not fan out — these are tight indexed queries):

```sql
-- terminal-backed active handoffs
-- Prefer the workstream_id FK; fall back to label/id-as-text only when FK is
-- NULL (legacy pre-backfill rows). A label-only join has the same false-
-- positive shape as the orphan query bug filed as pa.notes#1992: it silently
-- misses handoffs whose label ≠ ws.key when the parent has since gone terminal.
SELECT h.id, h.label, h.timestamp, w.status AS ws_status, w.key AS ws_key
FROM knowledge.handoffs h
LEFT JOIN pa.workstreams w ON (
      w.id = h.workstream_id
   OR (h.workstream_id IS NULL AND (w.key = h.label OR w.id::text = h.label))
)
WHERE h.status = 'active' AND w.status IN ('done','abandoned','superseded','archived')
ORDER BY h.timestamp ASC;

-- orphan handoffs (no workstream_id FK match AND no label-key match)
-- Two join branches required: knowledge.handoffs.workstream_id is the canonical
-- FK to pa.workstreams(id) (save_handoff enforces it), but legacy rows and
-- key-shaped labels also need the label-key branch to avoid double-counting
-- properly linked handoffs. A label-only join produces false-positive orphans
-- (verified 2026-07-10 hygiene pass on session 032a369b: 12 false-positive
-- orphans, 0 true orphans — see pa.notes#1992).
SELECT h.id, h.label, h.timestamp, h.working_directory, h.summary
FROM knowledge.handoffs h
LEFT JOIN pa.workstreams wid  ON wid.id = h.workstream_id
LEFT JOIN pa.workstreams wkey ON (wkey.key = h.label OR wkey.id::text = h.label)
WHERE h.status = 'active' AND wid.id IS NULL AND wkey.id IS NULL
ORDER BY h.timestamp ASC;

-- multi-handoff workstreams (Session Conventions invariant: "≤1 active handoff per workstream")
-- Detects the common failure mode the label-only orphan query missed:
-- multiple sessions saving handoffs against the same workstream_id without
-- archiving the previous one. Surface in Phase C for per-workstream operator
-- disposition (some are legitimate parallel sub-work; others are stale progress
-- checkpoints that should collapse to the newest handoff).
--
-- The `AND h.workstream_id IS NOT NULL` filter is load-bearing: standard SQL
-- GROUP BY treats all NULLs as equal, so any active handoffs with NULL
-- workstream_id (legacy pre-backfill rows per the column's schema comment)
-- would silently collapse into one bogus group with ws_key=NULL.
--
-- Residual coverage gap (accepted): two active handoffs with `workstream_id
-- IS NULL` that both resolve to the same live workstream via label-key would
-- violate the ≤1-per-workstream invariant AND be missed by both the orphan
-- query above (they'd be filtered out since wkey.id is not null) AND this
-- detector (filtered by the NOT NULL guard). Empirical rate on db1-prod
-- 2026-07-10: 0 active NULL-FK rows / 113 active total. If that rate rises,
-- extend the detector to COALESCE(h.workstream_id, wkey.id) and group by the
-- resolved id.
--
-- `summaries` is included so the Phase C.1b classifier can spot obviously-
-- superseded label patterns without a second round-trip; `data.cited_refs`
-- lives in JSONB and is fetched via `get_handoff(id)` per candidate row.
-- Order tie-break on `h.id` because equal `now()` timestamps are possible
-- (rare in prod, deterministic behavior mandatory).
SELECT h.workstream_id, w.key AS ws_key, COUNT(*) AS active_handoff_count,
       array_agg(h.label             ORDER BY h.timestamp, h.id) AS labels,
       array_agg(h.id                ORDER BY h.timestamp, h.id) AS ids,
       array_agg(h.timestamp         ORDER BY h.timestamp, h.id) AS timestamps,
       array_agg(h.working_directory ORDER BY h.timestamp, h.id) AS working_directories,
       array_agg(COALESCE(LEFT(h.summary, 240), '') ORDER BY h.timestamp, h.id) AS summaries
FROM knowledge.handoffs h
LEFT JOIN pa.workstreams w ON w.id = h.workstream_id
WHERE h.status = 'active' AND h.workstream_id IS NOT NULL
GROUP BY h.workstream_id, w.key
HAVING COUNT(*) > 1
ORDER BY COUNT(*) DESC, w.key;

-- stale orphan review loops
SELECT id, title, mode, status, current_round, max_rounds,
       scope->>'workstream_id' AS ws_id, scope->>'workstream_key' AS ws_key,
       created_at, updated_at,
       EXTRACT(EPOCH FROM (now() - updated_at))/86400 AS days_stale
FROM pa.review_loops
WHERE status IN ('open','in_progress','blocked','waiting')
  AND (
    (status = 'in_progress' AND current_round >= max_rounds AND updated_at < now() - INTERVAL '14 days') OR
    (status = 'open' AND scope->>'workstream_id' IS NULL AND scope->>'workstream_key' IS NULL AND updated_at < now() - INTERVAL '30 days') OR
    (updated_at < now() - INTERVAL '21 days')
  )
ORDER BY updated_at ASC;

-- stale active parent workstreams
SELECT id, key, title, status, updated_at,
       EXTRACT(EPOCH FROM (now() - updated_at))/86400 AS days_stale
FROM pa.workstreams
WHERE status = 'active' AND updated_at < now() - INTERVAL '7 days'
ORDER BY updated_at ASC;

-- proposed queue overflow
SELECT id, key, title, status, created_at, updated_at,
       EXTRACT(EPOCH FROM (now() - updated_at))/86400 AS days_stale
FROM pa.workstreams
WHERE status = 'proposed'
ORDER BY created_at DESC;

-- autowork-ineligible non-terminal count (Step 3G threshold row)
-- Excludes claimed, container, orphan-intake, and non-eligible gate_state per G.0.
-- Missing = neither P#2 (source_ref.autowork.*) nor P#3 (top-level source_ref.*)
-- has valid non-empty scope — matches G.1's shape (including refresh_objective
-- for refresh-shaped rows) so hydrations decrement the count as expected.
-- jsonb_array_length CASE-guarded against scalar shape.
SELECT count(*) FILTER (
  WHERE (NULLIF(w.source_ref->'autowork'->>'repo','') IS NULL AND
         NULLIF(w.source_ref->>'repo','') IS NULL)
     OR (NULLIF(w.source_ref->'autowork'->>'base_branch','') IS NULL AND
         NULLIF(w.source_ref->>'base_branch','') IS NULL)
     OR ((CASE WHEN jsonb_typeof(w.source_ref->'autowork'->'target_files') = 'array'
              THEN jsonb_array_length(w.source_ref->'autowork'->'target_files') = 0
              ELSE TRUE END) AND
         (CASE WHEN jsonb_typeof(w.source_ref->'target_files') = 'array'
              THEN jsonb_array_length(w.source_ref->'target_files') = 0
              ELSE TRUE END))
     OR (NULLIF(w.source_ref->'autowork'->>'refresh_objective','') IS NULL AND
         NULLIF(w.source_ref->>'refresh_objective','') IS NULL AND
         (w.workstream_kind = 'refresh' OR w.key ILIKE '%refresh%'
          OR w.key ILIKE '%backfill%' OR w.key ILIKE '%sync%'
          OR w.key ILIKE '%regen%'))
) AS autowork_ineligible_count,
count(*) AS eligible_denominator
FROM pa.workstreams w
WHERE w.status IN ('proposed','active','blocked','waiting_approval','waiting_external')
  AND COALESCE(w.workstream_kind,'') <> 'container'
  AND w.key <> 'orphan-intake'
  AND w.autowork_gate_state = 'eligible'
  AND NOT EXISTS (SELECT 1 FROM pa.workstream_claims c
                  WHERE c.workstream_id = w.id AND c.released_at IS NULL
                    AND c.lease_expires_at > now());
```

Cap inventory at the canonical thresholds above; don't enumerate forever. If counts exceed envelope budget, surface a warning and recommend `--surface` mode for a triage-only pass.

### A.6 — Model-substitution scan (read-only, report-only)

```bash
# from the claude-config checkout this skill was loaded from:
bin/model-substitution-scan.py --since-days 30 --exit-zero
```

Repo-relative, matching every other `bin/` reference across the skills (14 of them). `/hygiene-audit` runs from arbitrary cwd, so `cd` to the checkout first — or invoke through the tree the skill itself resolves from, since `~/.claude/skills` symlinks to `claude-config.worktrees/main-stable/skills` and the script is that repo's sibling `bin/`.

Do **not** hardcode `/home/rj/git/claude-config/bin/...`: that checkout sits at a pinned detached HEAD and lags `main`, so the absolute form resolved to a non-existent file the day this step shipped.

Claude Code can re-run a refused turn on a different model. In the lanes that matter here the switch is silent by construction: subagents get no system record, and headless / no-dialog-host sessions are never prompted. The substitution is durably recorded in the transcript, so it is detectable after the fact — it just needs something to look.

Reads every `*.jsonl` under `~/.claude/projects/**` (parent transcripts **and** `<session>/subagents/**`). ~4.4s over 2,012 files on the authoring host. Never writes; there is no autopilot action here.

Exit **1** means one or more transcripts could not be read — the tree was not fully scanned, so a clean result is unproven. Treat that as a coverage failure, not a pass.

**Report-only — do NOT auto-remediate.** Whether a substituted round taints an artifact is a judgement call about that artifact, not a bookkeeping fact, so findings go to the operator with their locators. Surface each incident with `from → to`, surface (`main` / `subagent`), and the post-switch served count.

Two fields decide how much to trust the taint boundary:

- `taint_boundary_precise: true` — a main-thread system record supplied `retractedMessageUuids`; the boundary is exact.
- `taint_boundary_precise: false` — subagent incidents (no system record exists) **and** main-thread records that omitted the field. The boundary is inferred from served-model drift; report it as approximate rather than implying precision the data does not have.

Escalate to the operator in the same turn when a finding lands on an adversarial-review or durable-artifact lane — a `/carl` round or a Workflow reviewer panel whose declared model was substituted has an unverifiable premise, not merely a degraded one.

`--json` for machine consumption. Exit 3 signals findings for a gating caller; `--exit-zero` (used above) keeps the hygiene run non-fatal.

#### A.6a — Subagent→parent taint propagation (STUB — manual triage only)

**The gap** (KB `provenance-vs-effective-author` § untraced lane): a substituted
subagent's output folded into a parent Workflow/Agent synthesis carries the
taint, but the **scanner performs no parent-side correlation and emits no
parent anchor** — subagent fallback blocks carry no `retractedMessageUuids`
counterpart, and the scanner does not resolve which parent turn consumed the
subagent's return. (Parent transcripts DO carry linkage records in the Agent
lane — the `task-notification` record naming the agent id; the Workflow lane's
per-`agent()` returns never reach the parent transcript at all.) A finding
with `surface: subagent` therefore identifies a tainted SOURCE, not the
tainted CONSUMERS.

**Stub disposition rule.** Until propagation tracing exists, treat as
**tainted-by-default** every parent-session synthesis that postdates the
flagged subagent's completion and plausibly consumed its return — the parent
turn that received the Task/Workflow result, and anything that turn's output
fed (review verdicts, ideation syntheses, artifacts). Steps 2–3 below narrow
that scope to the consuming turn onward; where the consuming turn cannot be
located, the whole post-completion parent tail stays in scope. The operator
disposes per artifact, same as A.6 main-thread findings; the default just
flips from "clean unless implicated" to "implicated unless separated,"
because the separation evidence is exactly what the scanner cannot show — and
an EMPTY grep in step 2 means "locator failed," never "no parent consumed it."

**Manual triage steps** for a `surface: subagent` finding:

1. Parent session id: `--json` findings carry it directly as `session_id`;
   the text emitter does not, so parse the path — for findings under
   `<session>/subagents/**/agent-*.jsonl`, `<session>` IS the parent
   transcript stem in the same project directory. Caveat (NESTED subagents,
   #605 R1): the path layout flattens nesting depth, so a subagent spawned
   BY a subagent still sits under the top-level `<session>` while its true
   consumer is a sibling `agent-*.jsonl` — if step 2's grep misses in the
   session transcript, grep the sibling agent files before concluding
   locator failure. If the finding's transcript is NOT under a `subagents/`
   directory (the scanner derives `surface` from row fields, not the path),
   the finding's own transcript is the parent.
2. Locate the consuming parent turn — **lane-split, the methods do not
   transfer**:
   - **Agent lane** (`subagents/agent-*.jsonl`): grep the parent `*.jsonl`
     for the agent id — empirically 149/150 in sampled transcripts (the id
     rides the `task-notification` record in most, and the spawn-time
     `tool_result` "agentId:" record in the rest — grep the id, not a
     record type; the 1 miss was the nested-subagent class in step 1's
     caveat). Note the hit's timestamp.
   - **Workflow lane** (`subagents/workflows/wf_*/agent-*.jsonl`): no
     harness-emitted linkage reaches the parent (returns are consumed
     in-process by the workflow script; only the script's final return
     reaches the parent). ~11% of sampled workflow agent ids DO appear in
     parents, but only incidentally — a parent-side `ls`/`Read` of the
     workflow dir — so an id hit there is NOT a consuming-turn locator.
     Grep the parent for the `wf_<id>` directory name instead (100/100 in
     sampled transcripts) to find the turn that ran the Workflow, then read
     `journal.jsonl` in that `wf_*` directory (`agentId` → `result` rows)
     to see exactly what the flagged agent contributed to the script's
     synthesis.
3. Everything the parent emitted from the consuming turn onward is in taint
   scope until the operator separates it.
4. Escalate same-turn if any in-scope parent output was a `/carl` round,
   reviewer-panel synthesis, or durable artifact (same escalation clause as
   A.6).

**Explicitly out of scope for this stub** (future work, tracked on workstream
`model-substitution-detection-2026-07-24`): automated parent-turn↔subagent
linkage, taint tags on artifacts, and any autopilot action. Report-only, like
all of A.6. (The previously-queued `AGENTS.md` § Provenance rescope landed
alongside this text — the doctrine bullet now states the lane asymmetry with
its sampling evidence.)

---

## Step 3 — Phase B: autopilot tier

Execute safe mutations without asking. Each mutation is reversible (un-archive, re-open, re-create) or a missing-path git metadata prune that has same-turn structured proof that only dead local-host registry entries are affected. Every mutation is bounded in blast radius.

### Pre-archive supersession check (shared procedure)

Run this before EVERY `archive_handoff` call — B.1, B.4, C.1, and C.1b here, plus `skills/pickup/SKILL.md` Step 10, its quick-decision archives, and the orchestration save-and-archive contract (`commands/pickup-orchestration-reference.md`), which reference this section as canonical. Semantics: **superseded** (a newer handoff replaces this one as the live pointer for the same label/workstream) is distinct from **archived without successor** (terminal closeout or checkpoint folding — archival only flips `knowledge.handoffs.status` and the row stays retrievable, so it remains authoritative historical evidence; never write supersession metadata for it).

1. **Find referencing loops** (per-handoff, at archive time — the Phase A inventory queries deliberately do not carry `context`):
   ```sql
   SELECT id, status, context->'handoffs' AS handoffs
   FROM pa.review_loops
   WHERE status NOT IN ('concluded','cancelled')
     AND context->'handoffs' @> to_jsonb('<handoff_uuid>'::text);
   ```
   The NOT-terminal filter matches the live `review_loops_status_check` CHECK (non-terminal set: `open`/`in_progress`/`waiting`, verified 2026-07-19); a status whitelist here would silently skip loops if a new non-terminal status lands. No rows → archive directly; done.
2. **Determine the successor** — from `pa.workstream_refs`, the handoff payload's `supersedes`/`workstream.supersedes` metadata, or the newest active same-label handoff.
   - Unambiguous successor → step 3.
   - No successor (terminal closeout / checkpoint fold) → the loop's reference remains valid historical evidence; archive without review-loop context edits.
   - Ambiguous → do NOT archive; leave the handoff active and surface the blocker (Phase C here; "say why" in pickup).
3. **Repair each referencing loop before archiving** — one **single-statement** `UPDATE pa.review_loops` per loop that (a) replaces the stale ID inside `context->'handoffs'` with the successor ID, (b) appends a `{handoff_id, superseded_by, reason}` object under `context.superseded_handoffs` (the canonical supersession-metadata key; create the array if absent via `COALESCE(context->'superseded_handoffs','[]'::jsonb) || <obj>` — live exemplar: loop `998f0b40`), and (c) bumps `updated_at`. Compose (a)+(b) with nested `jsonb_set` inside the one UPDATE — never SELECT-then-rewrite `context` from the client, which races a concurrent repair of the same loop (two sessions archiving different handoffs referenced by one loop would clobber each other's append).
4. **Write the locator** — a `pa.review_events` note on the loop or a `pa.workstream_refs` row naming the old ID(s) and the replacement.
5. **Then archive** the handoff by `id`.

A review loop whose context still points only at superseded (not merely archived) handoffs is not authoritative review input until repaired.

### B.1 — Archive terminal-backed handoffs

For each handoff from inventory query #1:
- Confirm `ws.status` is currently terminal (re-query before mutating; status may have flipped).
- Skip if handoff is younger than 30 minutes (the closing session may still be wrapping up).
- Skip if `working_directory` matches an active peer worktree.
- Run the **Pre-archive supersession check** (shared procedure above). Terminal-backed handoffs usually take its no-successor branch — archive without review-loop context edits; when referencing loops exist and the replacement is ambiguous, skip the archive and surface the loop-context blocker in Phase C.
- Call `mcp__knowledge-base__archive_handoff(id=<uuid>)`.

### B.2 — Conclude review loops past max rounds

For each loop where `status='in_progress' AND current_round >= max_rounds AND days_stale > 14`:
- `UPDATE pa.review_loops SET status='concluded', final_decision='inconclusive', concluded_at=now(), updated_at=now(), final_summary='Concluded during /hygiene-audit YYYY-MM-DD: at max round N/N for Md days with no fresh activity; scope subsumed by <parent_workstream or null>.' WHERE id=<uuid>;`

### B.3 — Cancel ancient orphan review loops

For each loop where `status='open' AND no workstream binding AND days_stale > 30`:
- `UPDATE pa.review_loops SET status='cancelled', final_decision='inconclusive', concluded_at=now(), updated_at=now(), final_summary='Cancelled during /hygiene-audit YYYY-MM-DD: 30+ days at round 1 with no workstream binding and no fresh activity; surface displaced by current parent programs.' WHERE id=<uuid>;`

### B.4 — Link orphan checkpoint handoffs to existing workstreams

When a handoff label matches the **PREFIX** `autowork:default:<key>` and `<key>` is an active workstream, file a `pa.workstream_refs` row linking the handoff into the parent (relation=`kb_handoff`, ref_kind=`kb_handoff`, relation=`checkpoint`), then archive the handoff — running the **Pre-archive supersession check** first (checkpoint folds normally take its no-successor branch). This pattern catches autowork cycle artifacts that have already served their purpose.

### B.5 — Prune missing-path worktree registry entries

Only act on entries where the registered worktree path no longer exists on the current host. Missing-path means the git registry still points at a directory that is gone; do not use this branch for stale, detached, dirty, remote/offline, or merely old worktrees.

Command shapes: `git worktree prune --dry-run --verbose` and `git worktree prune --verbose`, run as `git -C <repo> ...` for the target repo.

`bin/worktree-hygiene-scan.sh` may identify candidate repos, but its `ORPHAN-CAND` lines are not sufficient authority for mutation. Before autopilot may prune, build a structured candidate row for every dry-run line:
- `repo`
- `repo_common_dir`
- `metadata_dir` (`<repo_common_dir>/worktrees/<id>`, parsed from the dry-run line)
- `registered_gitdir` (contents of `<metadata_dir>/gitdir`)
- `registered_worktree_path` (`dirname(registered_gitdir)`)
- `dry_run_reason`
- `host`
- `metadata_mtime`

If any field is missing or ambiguous, defer that repo to the surface tier.

For each candidate repo from the scan or an equivalent current inventory:
- Re-run `git -C <repo> worktree prune --dry-run --verbose` immediately before mutating and parse it into the structured candidate set above.
- Continue only when every dry-run line for the repo is a missing-path registry prune, every candidate has `metadata_dir` and `registered_worktree_path`, and the count fits under the remaining 50-mutation pass cap.
- Require the immediate dry-run candidate-set match to the approved structured candidate rows before mutation; no extra, missing, or changed candidate is allowed.
- Skip if the repo root, candidate path, registered worktree metadata path, or `registered_worktree_path` matches an active peer worktree, active handoff working directory, workstream ref, or active claim.
- Apply a local-host guard: `realpath(repo)`, `repo_common_dir`, every `metadata_dir`, and every `registered_worktree_path` must be under the current host's declared git/worktree roots and must not be under known remote, offline, removable, or mounted roots. Record the declared-root source in handoff evidence.
- Require the same full structured identity (`repo_common_dir`, `metadata_dir`, `registered_gitdir`, `registered_worktree_path`, `dry_run_reason`, stable `metadata_mtime`) to be observed in two durable scan records >=24h apart, unless the operator explicitly authorizes the repo in the current turn. Accepted persisted sources are `knowledge.handoffs.data.worktree_prune_candidates[]`, `knowledge.handoffs.data.prune_preflight_scans[]`, or a host-path scan artifact cited by `data.durability_locators[]`; each source must include `observed_at`, `repo`, the full candidate row, and a durable locator (`db_row` for handoff rows or `host_path_mtime` for host-path artifacts). Compare `observed_at` timestamps, not file mtimes alone.
- Acquire an exclusive repo/common-dir worktrees lock at `${repo_common_dir}/worktrees/.hygiene-prune.lock` with `flock -n` spanning immediate dry-run -> prune -> post-dry-run. If the lock cannot be acquired, defer that repo to the surface tier.
- Run `git -C <repo> worktree prune --verbose`.
- The actual prune output must match the approved candidate IDs exactly. If it reports any unapproved entry, stop and surface the repo for manual audit.
- After mutation, rerun `git worktree prune --dry-run --verbose` as `git -C <repo> worktree prune --dry-run --verbose`; the target lines must be gone and any remaining lines must be outside the approved candidate set.
- Record repo, structured candidate rows, pre/post dry-run output, actual prune output, lock evidence (`lock_path`, `acquired_at`, `released_at`), persisted scan source locators, declared-root source, host, cwd, UTC timestamp, and a `host_path_mtime` locator for `${repo_common_dir}/worktrees` in the Step D handoff.

Do not run `git worktree remove` from autopilot. Existing but stale or clean worktrees stay in the surface tier or a dedicated operator-approved cleanup.

### B.6 — Log decision row

After autopilot tier completes, ONE `log_decision()` call summarizing N handoffs archived, M loops closed, K orphan checkpoints folded, P missing-path worktree registry prunes. Category `change`, tag `hygiene-audit`.

**Stop criteria:**
- Any mutation returns an error → halt autopilot tier, surface error to operator, drop to surface tier.
- Cumulative mutations exceed 50 in one pass → halt; surface "autopilot tier reached safety cap" and continue with surface tier.

---

## Step 3F — Workstream freshness sweep (default; also `--freshness` singleton; skip via `--no-freshness`)

Runs by default in a bare `/hygiene-audit` pass (operator directive 2026-07-24). Verifies every **eligible** non-terminal workstream (unclaimed, non-container, within the 300-row enumeration cap) — summary/status against ground truth (GitHub PR states, event trails, newest active handoff, live hosts) and refreshes drifted rows, **most-stale first**. Origin: operator directive 2026-07-16 ("deep check freshness / update all workstreams from most to least stale"), first executed ad-hoc in a /pickup deep session and codified here as the repeatable form.

**Authorization scope.** The default pass, `--autopilot`, `--freshness`, and any pass without `--no-freshness` all authorize the Step F.4 **non-terminal** `project_update_workstream` mutations (summary refresh, non-terminal status change) for unclaimed workstreams in the stale set. Terminal transitions (`close_candidate`) and ambiguous items (`needs_operator`) always drop to the surface tier. Auto-mode permission classifiers may still deny individual mutations — skip and surface, never retry verbatim.

### F.1 — Enumerate (orchestrator, serial)

```sql
SELECT w.id, w.key, w.status, w.priority,
       GREATEST(w.updated_at, COALESCE((SELECT max(e.created_at)
         FROM pa.workstream_events e WHERE e.workstream_id = w.id), w.updated_at)) AS last_touch,
       GREATEST(w.updated_at, COALESCE((SELECT max(e.created_at)
         FROM pa.workstream_events e WHERE e.workstream_id = w.id), w.updated_at))
         < now() - INTERVAL '2 days' AS is_stale,   -- replace 2 with the --cutoff-days value
       count(*) OVER () AS total
FROM pa.workstreams w
WHERE w.status IN ('proposed','active','blocked','waiting_approval','waiting_external')
  AND w.key <> 'orphan-intake'                       -- system container, report-only
  AND NOT EXISTS (SELECT 1 FROM pa.workstream_claims c
                  WHERE c.workstream_id = w.id AND c.released_at IS NULL
                    AND c.lease_expires_at > now())  -- claim-holder owns mutation
ORDER BY last_touch ASC
LIMIT 300;
```

Staleness = `GREATEST(updated_at, newest event)` — `updated_at` alone misses event-only touches, and events alone miss summary edits. The **stale set** is rows with `is_stale=true` (cutoff computed in-SQL; default `--cutoff-days=2`); fresher rows are timestamp-fresh by construction — leave untouched and say so in the report. `total` is evaluated pre-LIMIT: if `total > 300`, report coverage as `300 of <total>`, never as complete. Run the Step 1 peer ladder anyway (the SQL claim filter is point-in-time; F.4 re-checks). Claimed workstreams and `orphan-intake` are excluded in the WHERE clause; re-verify both at F.4 apply time.

### F.2 — Fan out read-only distillers

Batch the stale set into groups of ~8, ordered most→least stale, one `Agent` (model `sonnet`) per batch, launched in **bounded waves of ≤8 concurrent batches**. If the stale set exceeds ~100 workstreams (>12 batches), confirm scope with the operator before launching — the fan-out is read-only (not a worker-orchestration ASK-gate trigger), but the token cost is real. Each distiller MUST report back the exact `version` it observed per workstream — F.4's compare-and-set depends on it. Prefer a read-restricted subagent type (e.g. `Explore`, which blocks Edit/Write) when available — but note the residual risk: MCP mutation tools remain callable from any subagent type, so the read-only boundary still rests on prompt discipline. Distillers are **STRICTLY READ-ONLY** (`execute_query`, `gh pr view`/`gh pr list`, `git log`; never `execute_sql`, `project_*` mutations, save/archive/edit). Per workstream they gather: the `pa.workstreams` row (including `version`), `pa.workstream_refs`, last ~5 `pa.workstream_events`, newest active handoff (capped excerpt ~1200 chars), and `gh pr view --json state,isDraft,mergedAt,title,headRefName` on ≤3 load-bearing PR refs. Return schema per workstream:

```json
{"key": "…", "version": 0, "db_status": "…", "priority": "…",
 "reality": "≤3 sentences with evidence tokens (PR# + state + date)",
 "stale_claims": ["claim → reality", "…"],
 "proposal": {"action": "none|refresh_summary|status_change|close_candidate|needs_operator",
              "new_status": null,
              "draft_summary": "≤70 words; preserves still-accurate durable locators",
              "reason": "1 line"},
 "evidence": ["compact locators"]}
```

Unverifiable claims are marked UNVERIFIED, never guessed. Claim Contract Rule 1a applies inside the distiller: a PR state cited in `evidence`/`draft_summary` must come from a `gh` call the distiller ran in its own session, not from the stale summary being audited.

### F.3 — Fold + orchestrator verification

- A `needs_operator` on an externally checkable fact (e.g. "is host process X still running") MAY be resolved by the orchestrator directly (ssh/gh/DB per KB-first doctrine) and upgraded to a concrete proposal — cite the check inline in the new summary.
- Cross-check proposals against same-day peer activity: today's orch handoffs, deliberate keep-active `reconcile_finding` events, and hygiene "verified as deliberate parks" lists. An operator's explicit keep-active decision is NOT drift — those rows stay `action=none`.
- Future-dated by-design waits (key or summary names a trigger date not yet reached) are `action=none`.

### F.4 — Apply (mutation boundary)

Re-run the Step 1b ladder, then mutate row-by-row: immediately before EACH row's pre-image event + update, re-query that row's `key, status, version, summary` AND its live claim state (claims do NOT bump `version`, so a claim acquired mid-batch is invisible to CAS — the per-row claim recheck is the only guard). **Stale-draft guard (CAS discipline):** the re-queried `version` must EQUAL the version the distiller observed — a higher version means the row changed after the audit (peer edit, event, status change), and applying the draft would clobber the newer state with stale conclusions. On version mismatch or a fresh claim: skip the row, surface it, and re-distill in a later pass. Never adopt the re-queried version as the new `expected_version` for an unchanged draft. Then for each surviving `refresh_summary` / `status_change` proposal:

- **Summary overwrite is one-way** — `project_update_workstream` replaces the summary column and the prior text is not otherwise recoverable. For EVERY rewrite, first record the complete pre-image: `project_record_event(workstream_key_or_id=<key>, event_type='reconcile_finding', payload={"reason": "freshness_sweep_pre_image", "old_summary": <full re-queried summary text>})`. The re-queried summary (not the distiller's copy) is the authoritative pre-image. This event also satisfies the "touch + keep active requires BOTH calls" hard rule.
- `project_update_workstream(workstream_key_or_id=<key>, expected_version=<distiller-observed, CAS-verified>, [status=<new>], summary=<draft>)` — status changes auto-append `status_change` events; the update itself bumps `updated_at`, resetting the staleness clock.
- Tag every rewritten summary with `[Freshness sweep YYYY-MM-DD]` (+ `old→new` status note when changed) and preserve still-valid durable locators (PR#, SHA, migration N).
- `close_candidate` → surface tier; terminal transitions are never applied from this step.
- `needs_operator` → surface tier.
- Optimistic-lock conflict or permission-classifier denial → skip that row, surface it, do not retry verbatim.

**Stop criteria (mirrors Step 3):** any unexpected mutation error (not a lock conflict or classifier denial) → halt Step 3F, surface, drop remaining proposals to the surface tier. Cumulative Step 3F mutations exceed **50 in one pass** → halt and surface "freshness tier reached safety cap"; the remainder re-surfaces next pass by construction (their `last_touch` stays stale).

### F.5 — Report

Extend the D.2 post-run report (defined below in Step 5) with a freshness block: `assessed A of eligible E (cutoff=Nd, enumeration cap 300) · no-change K · refreshed R · status-changed S · close candidates C · operator items O · CAS/claim-skipped X`. `E` is F.1's `count(*) OVER ()` (post-exclusion, pre-LIMIT); do not report a total-non-terminal figure — F.1 doesn't compute one. Validate `--cutoff-days` as a positive integer (sane bound ≤30) before substituting it into the F.1 interval. One line per mutated/surfaced workstream with key + evidence token. Phase D handoff carries per-updated-workstream locators in the validator-accepted `db_row_full` shape (`kb_mcp/db.py` `_DURABLE_STRUCTURED_LOCATOR_FORMS`): `{type: 'db_row', table: 'pa.workstreams', key: 'id', value: '<uuid>', timestamp: '<iso>', host: 'db1-prod'}`.

---

## Step 3G — Autowork eligibility hydration sweep (default; also `--hydrate-autowork` singleton; skip via `--no-hydrate-autowork`)

Runs by default in a bare `/hygiene-audit` pass (operator directive 2026-07-24). Enumeration always runs; distiller fan-out + hydration apply now runs unless `--no-hydrate-autowork` is passed.

**Why this exists.** keel `assign_work` selector requires `pa.workstreams.source_ref.{repo, base_branch, target_files}` (and `refresh_objective` for periodic-refresh work) to compile an executable slice. Historical rows accreted before the typed contract landed have `source_ref` skeletons or nothing at all, so the selector reports `selector_stale_state_only` / `selector_no_executable_slice` even when the work is real and unblocked. Baseline 2026-07-22 on db1-prod: 155 non-terminal workstreams, 100% missing `base_branch` / `target_files` / `refresh_objective`, 138/155 missing `repo`. Autowork is starved until hygiene hydrates.

**Scope of authorization.** The default pass, `--autopilot`, `--hydrate-autowork`, and any pass without `--no-hydrate-autowork` all authorize `project_update_workstream(source_ref=<merged jsonb>)` mutations for unclaimed, non-terminal workstreams whose linked evidence (below) unambiguously entails the values. High-confidence rows are applied; low-confidence rows go to surface tier C.5. **Never overwrites** existing populated fields — only merges missing keys. Terminal transitions and status changes are out of scope for this tier.

**Cost note (prior opt-in rationale).** Distiller fan-out is the expensive part of this tier and the reason it was opt-in through 2026-07-23. The 2026-07-24 directive makes it default anyway; callers who need a cheaper pass use `--no-hydrate-autowork`, which reverts to enumeration-only (`/pickup` Step 7's `autowork-ineligible > 40` threshold row still fires).

### G.0 — Ineligibility carve-outs (SKIP; do NOT mutate `source_ref`)

Compute the exclusion set BEFORE enumeration. Adding scope fields to any of these silently promotes work the operator has already flagged not-yet-ready:

- Workstreams with an active `pa.workstream_claims` row (claim-holder owns mutation — same rule as Step 1 peer pre-flight).
- Workstreams whose `autowork_gate_state <> 'eligible'` (respect the typed gate column). The live CHECK constraint permits `eligible` + five `ineligible_*` values (`ineligible_design_pending`, `ineligible_operator_approval`, `ineligible_carl_pending`, `ineligible_budget_policy`, `ineligible_other`); any non-`eligible` value is a hard skip. **Verified against `describe_table('pa.workstreams') workstreams_autowork_gate_state_check` 2026-07-22.** Prior draft used invalid literals `paused` / `blocked_by_gate` / `operator_hold` — those are not in the enum and produce a silent no-op carve-out. Do not resurrect them.
- Workstreams whose `summary`, `title`, or a **sibling workstream's `summary` that cites this workstream's id or key** matches the ineligibility markers from `~/.claude/skills/autowork/SKILL.md` §4.5b (canonical §4.5b is TWO-PASS: self + siblings-citing-target; single-pass is insufficient). Case-insensitive:
  - `Not autowork-eligible`
  - `DO NOT auto-pick up`
  - `(Route via|Pending|Gated on|Needs|Awaits|Requires|Routed to) .* /carl Mode A`
  - `Requires .* design work across`
  - `before any code implementation`
- Workstreams whose `status IN ('waiting_approval','waiting_external')` AND whose summary names a specific external dependency (operator, upstream fix, vendor response) — surface to C.5, do not autopilot.
- Workstreams with `workstream_kind='container'` or `key='orphan-intake'` (never autowork-executable).

### G.1 — Enumerate (orchestrator, serial)

**Selector alignment note.** The autowork selector's `readScope()` (`potato-brain/src/workstreams/autoworkCandidateSlices.ts:240`) checks four priority layers: **P#1 `pa.workstream_refs.metadata.autowork`** (typed ref metadata), **P#2 `pa.workstreams.source_ref.autowork`** (canonical current-spec path), **P#3 `pa.workstreams.source_ref` top-level** (backward-compat legacy pre-PR-3 rows), **P#4 `acceptance_evidence`**. G.1's SQL below detects rows where BOTH P#2 and P#3 are empty for a required key (SQL cannot cheaply join P#1 across a scan; see caveat). If P#1 or P#4 is populated the selector already sees scope — the row is not truly ineligible; the SQL's false-positive is corrected by G.3 verification (JOIN P#1 refs per candidate before autopilot). Prior draft only checked P#3 and wrote to P#3; that leaves P#2-canonical hydration path unused. **G.4 writes canonical P#2 `source_ref.autowork.{repo,base_branch,target_files,refresh_objective}` for new hydrations; legacy P#3 top-level keys are preserved (never overwritten) if present.**

```sql
SELECT w.id, w.key, w.title, w.summary, w.status, w.priority, w.version, w.source_ref,
       w.workstream_kind, w.autowork_gate_state,
       -- Missing = neither P#2 nor P#3 has a valid non-empty value.
       (NULLIF(w.source_ref->'autowork'->>'repo','') IS NULL AND
        NULLIF(w.source_ref->>'repo','') IS NULL)                             AS missing_repo,
       (NULLIF(w.source_ref->'autowork'->>'base_branch','') IS NULL AND
        NULLIF(w.source_ref->>'base_branch','') IS NULL)                      AS missing_base_branch,
       -- target_files: CASE-guard jsonb_array_length against scalar values.
       ((CASE WHEN jsonb_typeof(w.source_ref->'autowork'->'target_files') = 'array'
              THEN jsonb_array_length(w.source_ref->'autowork'->'target_files') = 0
              ELSE TRUE END) AND
        (CASE WHEN jsonb_typeof(w.source_ref->'target_files') = 'array'
              THEN jsonb_array_length(w.source_ref->'target_files') = 0
              ELSE TRUE END))                                                 AS missing_target_files,
       -- refresh_objective: only material for refresh-shaped workstreams.
       (NULLIF(w.source_ref->'autowork'->>'refresh_objective','') IS NULL AND
        NULLIF(w.source_ref->>'refresh_objective','') IS NULL AND
        (w.workstream_kind = 'refresh' OR w.key ILIKE '%refresh%'
         OR w.key ILIKE '%backfill%' OR w.key ILIKE '%sync%'
         OR w.key ILIKE '%regen%'))                                            AS missing_refresh_objective,
       -- Malformed-but-populated signals (populated but wrong JSON shape):
       (jsonb_typeof(w.source_ref->'target_files') NOT IN ('array','null')
        AND jsonb_typeof(w.source_ref->'target_files') IS NOT NULL)            AS malformed_target_files_toplevel,
       (jsonb_typeof(w.source_ref->'repo') NOT IN ('string','null')
        AND jsonb_typeof(w.source_ref->'repo') IS NOT NULL)                    AS malformed_repo_toplevel,
       (jsonb_typeof(w.source_ref->'base_branch') NOT IN ('string','null')
        AND jsonb_typeof(w.source_ref->'base_branch') IS NOT NULL)             AS malformed_base_branch_toplevel,
       count(*) OVER () AS total_ineligible
FROM pa.workstreams w
WHERE w.status IN ('proposed','active','blocked','waiting_approval','waiting_external')
  AND COALESCE(w.workstream_kind,'') <> 'container'
  AND w.key <> 'orphan-intake'
  AND w.autowork_gate_state = 'eligible'   -- ONLY truly-eligible; 5 ineligible_* states are hard-skip.
  AND NOT EXISTS (SELECT 1 FROM pa.workstream_claims c
                  WHERE c.workstream_id = w.id AND c.released_at IS NULL
                    AND c.lease_expires_at > now())
  AND (
        (NULLIF(w.source_ref->'autowork'->>'repo','') IS NULL AND
         NULLIF(w.source_ref->>'repo','') IS NULL)
     OR (NULLIF(w.source_ref->'autowork'->>'base_branch','') IS NULL AND
         NULLIF(w.source_ref->>'base_branch','') IS NULL)
     OR ((CASE WHEN jsonb_typeof(w.source_ref->'autowork'->'target_files') = 'array'
              THEN jsonb_array_length(w.source_ref->'autowork'->'target_files') = 0
              ELSE TRUE END) AND
         (CASE WHEN jsonb_typeof(w.source_ref->'target_files') = 'array'
              THEN jsonb_array_length(w.source_ref->'target_files') = 0
              ELSE TRUE END))
     -- Refresh-shaped rows: enumerate when scope OK but refresh_objective missing.
     OR (NULLIF(w.source_ref->'autowork'->>'refresh_objective','') IS NULL AND
         NULLIF(w.source_ref->>'refresh_objective','') IS NULL AND
         (w.workstream_kind = 'refresh' OR w.key ILIKE '%refresh%'
          OR w.key ILIKE '%backfill%' OR w.key ILIKE '%sync%'
          OR w.key ILIKE '%regen%'))
      )
ORDER BY (w.status='active') DESC, w.priority DESC NULLS LAST, w.updated_at DESC
LIMIT COALESCE(NULLIF(:max_arg::int, 0), 100);
```

Bare-pass ONLY runs the `count(*)` projection (no per-row body); `--hydrate-autowork` runs the full SELECT with `--max=N` default 100. `total_ineligible` is pre-LIMIT — report coverage as `hydrated H of ineligible T`, never as complete when H<T.

**Post-SELECT code-side filter (mandatory for hydrate mode; not just marker regex).** SQL alone cannot do §4.5b's two-pass check. In code:
1. **Self-summary/title pass** — regex-match the returned `summary` and `title` against the G.0 marker list; drop hits to a `g0_summary_marker_skipped` bucket.
2. **Sibling-cite pass** — for each surviving candidate id/key, query `pa.workstreams w2` where `w2.summary ~* <candidate.key>` OR `w2.summary ~* <candidate.id::text>`; regex-match the sibling summary against the G.0 marker list; drop hits to a `g0_sibling_marker_skipped` bucket.
3. **Waiting-dependency pass** — for `status IN ('waiting_approval','waiting_external')`, extract external-dependency prose from the summary; surface to C.5 (do not autopilot).
4. **Priority-1 JOIN pass** — for each surviving candidate, `SELECT count(*) FROM pa.workstream_refs r WHERE r.workstream_id = w.id AND (r.metadata->'autowork'->>'repo' IS NOT NULL OR r.metadata->'autowork'->>'base_branch' IS NOT NULL OR jsonb_typeof(r.metadata->'autowork'->'target_files') = 'array')`; if any hit, the selector already reads scope from P#1 — mark `p1_shadowed` (canonical bucket name matches G.5 conservation equation) and drop from hydration set.
5. **Priority-4 acceptance_evidence pass** — for each surviving candidate, check `pa.workstreams.acceptance_evidence.{repo,base_branch,target_files,tests}` — the selector's P#4 layer reads workstream `acceptance_evidence` before falling through to `source_layer: 'none'` (per `readScope()` P#4 branch). If any of those keys is populated on the workstream row (`NULLIF(acceptance_evidence->>'repo','') IS NOT NULL` OR base_branch OR non-empty target_files array OR non-empty tests array), mark `p4_shadowed` and drop from hydration set. (Item-level `acceptance_evidence` is per-work-item and not visible to the hydration doctrine's workstream scope — that path is handled by the selector's item resolver, not by hygiene hydration.)

Every code-side skip lands in a **named G.5 bucket** so the operator can distinguish `correct-skip` from `silent-loss`.

### G.2 — Fan out read-only distillers (Agent, sonnet, waves ≤8)

Same shape as F.2. Distillers are STRICTLY READ-ONLY. Per workstream, the distiller gathers:

- The `pa.workstreams` row (including `version`, current `source_ref`).
- `pa.workstream_refs` — the linked handoff / PR / KB entry / commit refs (the primary evidence source; refs are typed).
- Newest active `knowledge.handoffs` for this workstream — its `working_directory` (→ repo path), `data.cited_refs` (→ PR#s / commits), and summary excerpt.
- For each cited PR: `gh pr view <ref> --json baseRefName,headRefName,url,files,state,isDraft` — `baseRefName` is `base_branch`; `files[].path` seeds `target_files`; `url` gives `owner/repo`.
- If handoff `working_directory` matches a local git worktree AND no PR link exists: `git -C <path> config --get remote.origin.url` + `git -C <path> log --stat -n5 HEAD` to infer repo + target_files from recent commits.

Return schema per workstream (note: `proposed_merge.autowork` is a sub-object matching selector's Priority #2 canonical path):

```json
{"key": "…", "version": 0, "confidence": "high|medium|low",
 "current_source_ref": {…},
 "proposed_merge": {
   "autowork": {
     "repo":              {"value": "owner/repo",      "evidence": "gh pr view PR#123 · url", "confidence": "high"},
     "base_branch":       {"value": "main",            "evidence": "gh pr view PR#123 · baseRefName", "confidence": "high"},
     "target_files":      {"value": ["path/a.py","path/b.py"], "evidence": "gh pr view PR#123 · files[].path", "confidence": "high"},
     "refresh_objective": {"value": null,              "evidence": "N/A — not a refresh workstream", "confidence": "n/a"}
   }
 },
 "unset_keys": ["refresh_objective"],   // deliberately not proposing
 "reason": "1-line why this is safe to autopilot / why it needs operator"}
```

**Confidence rules (distiller):**
- `high` — every proposed field is entailed by a single canonical PR ref the distiller opened this session (`gh pr view` succeeded). Autopilot-eligible.
- `medium` — some fields entailed by a PR; others inferred from handoff `working_directory` + `git log`. Surface to C.5 with the distiller's evidence.
- `low` — no PR link; scope guessed from summary text or KB entry. Surface to C.5; operator input.

Field-level confidence overrides row-level: any field marked `medium`/`low` demotes the whole row to `medium`/`low`. **Never overwrite an existing populated key** at any priority layer (P#1 metadata, P#2 `source_ref.autowork.<key>`, or P#3 top-level `source_ref.<key>`) even at `high` confidence — only merge into keys currently missing under G.1's boolean shape (which validates both P#2 and P#3 emptiness) AND unpopulated at P#1.

**Malformed-populated values are NOT overwritable.** If G.1 reports `malformed_target_files_toplevel = true` (e.g. current `source_ref.target_files` is a scalar string), do NOT overwrite — surface to C.5 with a `malformed_evidence_skipped` bucket. Distiller reports the malformed shape verbatim under `current_source_ref` for evidence; orchestrator never merges when malformed-populated.

**Distiller framing note.** The specific harness — Claude Code's `Agent, model:sonnet, ≤8 concurrent` — reflects claude-config's operator-ratified Claude-Code subagent-tiering policy (see `feedback_subagent_model_tiering.md`). Concretely for Claude Code, the read-only-capable subagent types that satisfy this doctrine are **`Explore`** and **`Plan`** — both are documented by the Claude Code session-start Agent tool schema as excluding `Edit`, `Write`, and `NotebookEdit` from their tool allowlist. That listing is the operative surface (Claude Code built-ins do not ship an on-disk `~/.claude/agents/*.md` file); implementers MUST re-check the session-start Agent schema before spawning, since the registry can change between Claude Code releases. Do NOT substitute `code-reviewer`, `senior-code-reviewer`, or `general-purpose` here — those grant write-capable tools that violate the read-only invariant. Other harnesses invoking this doctrine substitute an equivalent read-only-verified capability primitive (read tools only, cwd-scoped, PR/git/gh-visible). The invariants that MUST hold across harnesses: (1) tool-allowlist empirically verified `Edit`/`Write`/`NotebookEdit`-free at spawn, (2) capability to run `gh pr view` + `git log/config`, (3) per-workstream isolation. Any harness that cannot verify (1) at spawn time falls back to a manual per-workstream operator gate instead of autopilot.

Claim & Response Contract Rule 1a applies inside the distiller: every `evidence` token must come from a tool call the distiller ran in its own session (not paraphrased from the audited summary).

### G.3 — Fold + orchestrator verification

- Cross-check every `high`-confidence proposal against Step 1 peer-detection ladder output — a workstream whose target_files intersect an active peer's uncommitted diff or worktree is NOT autopilot-eligible even with a PR link; demote to `medium` and surface.
- Verify the proposed `owner/repo` string against **both** a stricter shape regex `^[a-z0-9][a-z0-9._-]{0,38}/[a-zA-Z0-9._-]{1,100}$` (rejects `../..`, empty tokens, and leading punctuation) **and** an existence check via `gh repo view <owner/repo> --json nameWithOwner`. The existence check must return exactly `<owner/repo>` (case-preserving canonical form). Rows failing either check are demoted to `medium` and surfaced to C.5 — the regex alone is insufficient; a syntactically valid `owner/repo` may still be a stale or malicious pointer.
- Deduplicate `target_files` (case-preserving); cap to first 50 entries and mark `target_files_truncated: true` alongside `target_files_pr_total: <N>` inside `source_ref.autowork` when the PR touched more.
- Re-verify PR freshness immediately before apply — refetch `gh pr view <PR> --json headRefOid,state,isDraft,updatedAt`; if `headRefOid` changed since distiller observation, demote to `medium` (source data races the mutation).

### G.4 — Apply (mutation boundary)

Re-run Step 1b ladder. Then per row (high-confidence set only in autopilot):

- Re-query `pa.workstreams` for `version, source_ref` immediately before the update — a peer edit that bumped `version` invalidates the distiller's `expected_version` and the row is skipped + surfaced (bucket `cas_skipped`). Do NOT adopt the re-queried version as new `expected_version`.
- Re-query `pa.workstream_claims` for this row — a fresh claim (invisible to version) means skip + surface (bucket `claim_skipped`).
- **Claim TOCTOU narrowing.** `project_update_workstream` does NOT bind to claim absence — so a claim can land in the window between the check and the update. **Canonical mitigation: self-claim, narrowed by scope-awareness.** Orchestrator acquires a short `execute` claim via `project_claim_workstream` (TTL 60s), performs the update, releases with `disposition='released'`. Turns the race into a claim-collision surface visible to peers via `pa.workstream_claims`. On `claim_contended` → skip, bucket `claim_toctou_skipped`.

  **Scope-exclusivity caveat.** The exclusivity index `idx_ws_claims_exclusive` on `pa.workstream_claims` is `(workstream_id, claim_scope)` UNIQUE WHERE `claim_scope IN ('execute','orch','assignment_reservation')` (verified via `describe_table` 2026-07-22). This means an `execute` self-claim only excludes other `execute` claims on the same workstream — it does NOT exclude a concurrent `assignment_reservation` (autowork's own claim shape) or `orch` claim. A parallel autowork run can land its `assignment_reservation` on the same workstream during hygiene hydration; the two claims coexist without collision. **Any check-then-write against `pa.workstream_claims` remains TOCTOU** — the cross-scope claim can land in the window between check and write no matter how tight. Doctrine defaults:

    - **(a) DEFAULT — narrowed self-claim + cross-scope re-query** (only currently-runnable path): self-claim via `project_claim_workstream` (`execute` scope, TTL 60s), then re-query `pa.workstream_claims` for cross-scope claims (`assignment_reservation`/`orch` non-released) immediately before update, then `project_record_event` + `project_update_workstream` (both write via the canonical helper that does `SET updated_at = NOW(), version = version + 1`; the CAS UPDATE catches concurrent workstream mutations). On post-check cross-scope claim discovery → skip, bucket `claim_cross_scope_skipped`. On `claim_contended` on the self-claim → skip, bucket `claim_toctou_skipped`. **Residual race window (not closed):** between the cross-scope re-query and the `project_update_workstream` call, a peer can INSERT a fresh `assignment_reservation`/`orch` row — nothing in this path row-locks the workstream. The CAS UPDATE still succeeds because that peer insert doesn't bump `pa.workstreams.version`; the hydration commits *concurrently* with the newly-landed peer claim. This is accepted as a documented narrowing, not a closure. Hydration is idempotent-on-key (never overwrites existing `source_ref.autowork.*` keys — G.4 build-merged step), so the worst case is a benign double-write of the same missing scope on the next pass; no data corruption.
    - **(b) FUTURE — server-side row-locking helper** (not currently available): the fully-race-free path requires a new pg_mcp helper or SECURITY DEFINER function that inside ONE server-side transaction `SELECT ... FOR UPDATE`s the `pa.workstreams` row, checks `pa.workstream_claims` for cross-scope collisions, records the pre-image event, and performs the CAS UPDATE. Naïve `execute_sql` from a client cannot substitute: `execute_sql` already wraps input in `conn.transaction()` and calls `conn.execute()` (`mcp-servers/postgres/pg_mcp/queries.py:364-401`), so explicit `BEGIN`/`COMMIT`/`ROLLBACK` inside the block is a contract violation; and `execute_sql` rejects read-only `SELECT`/`WITH` entrypoints (`mcp-servers/postgres/pg_mcp/tools.py:114-120`; `queries.py:367-390`), so a claim-branching SELECT-then-UPDATE cannot be expressed as a single input. Tracked as follow-up workstream `pg-mcp-hygiene-hydration-locked-write-helper` (out-of-scope for this doctrine PR).

  **Do not use `pg_try_advisory_xact_lock` here**: `project_record_event` and `project_update_workstream` are separate MCP RPCs, each opens its own server-side transaction, so a client-side `_xact_lock` is released before the next call — no protection. Option (a) is a documented narrowing with a residual TOCTOU window on cross-scope claim landing; only the future server-side helper (option b) closes it.
- Build the merged `source_ref`: start from the re-queried current `source_ref` (JSON object; default to `{}` if null); **write missing keys into the `autowork` sub-object** (P#2 canonical path — matches selector `readScope()`). Concretely: `merged = current | { "autowork": (current.autowork ?? {}) | { <missing_keys> } }`. Never overwrite an existing key inside `autowork` even if the distiller proposed a different value. Never overwrite an existing P#3 top-level key; if a legacy P#3 top-level `repo`/`base_branch`/`target_files` exists and P#2 lacks it, the top-level key is preserved as-is and G.5 records bucket `legacy_p3_only_preserved` (the selector still reads it via P#3 backward-compat; hydration is a no-op there).
- **Malformed-populated skip.** If G.1 reported `malformed_target_files_toplevel = true`, this row is NOT autopilot-eligible — bucket `malformed_populated_skipped`, surface to C.5.
- `project_record_event(workstream_key_or_id=<key>, event_type='reconcile_finding', payload={"reason": "autowork_hydration_pre_image", "old_source_ref": <re-queried source_ref>, "hydrated_keys": ["autowork.repo","autowork.base_branch","autowork.target_files"], "target_path": "source_ref.autowork.*", "evidence": {"pr": "…", "handoff_id": "…", "pr_head_sha": "…"}})` — pre-image for reversibility, mirrors the F.4 pattern.
- `project_update_workstream(workstream_key_or_id=<key>, expected_version=<distiller-observed CAS>, source_ref=<merged jsonb>)`.
- On `expected_version` conflict, `project_claim_workstream` `claim_contended`, or permission-classifier denial → skip that row, surface it in the appropriate bucket, do not retry verbatim.

`medium` / `low` confidence rows drop to surface tier C.5 unmutated.

**Stop criteria** (mirror Step 3): any unexpected mutation error (not a lock conflict or classifier denial) → halt G.4, drop remaining `high` proposals to surface. **Cap is inclusive-of-51st: stop before the write that would make cumulative G.4 mutations ≥51 in one pass.** Wording: `if (mutations_so_far + 1) > 50: halt`. On halt: surface `cap_remainder_deferred` with the count of remaining high-confidence rows; the remainder re-surfaces next pass by construction (`source_ref` gap stays visible to G.1).

### G.5 — Report

Extend the D.2 post-run report with a hydration block reporting **all outcome buckets** over the enumerated set `E`, plus separate SQL-excluded counts. The conservation equation:

```
E = A + M + L + S_g0_summary + S_g0_sibling + S_g0_waiting + S_p1_shadowed + S_p4_shadowed
    + S_malformed + S_cas + S_claim + S_claim_toctou + S_claim_cross_scope
    + S_regex + S_gh_repo_missing + S_pr_head_changed + S_distiller_failed
    + S_permission_denied + S_legacy_p3_only_preserved_partial
    + halted_cap_remainder + halted_fatal_error
```

- `E` = candidates returned by G.1 SQL post-LIMIT.
- **SQL-excluded** rows (never in `E`, reported separately) — parallel `count(*) FILTER (WHERE …)` predicates against `pa.workstreams` restricted to `status IN ('proposed','active','blocked','waiting_approval','waiting_external')`:
  - `Q_g0_gate` = `autowork_gate_state <> 'eligible'`
  - `Q_claimed` = `EXISTS (SELECT 1 FROM pa.workstream_claims c WHERE c.workstream_id = w.id AND c.released_at IS NULL AND c.lease_expires_at > now())`
  - `Q_container` = `COALESCE(workstream_kind,'') = 'container'`
  - `Q_orphan_intake` = `key = 'orphan-intake'`
  These are correct-skips at the SQL layer; they document the doctrine's SQL WHERE-clause exclusions and are NOT summed into `E`. Categories may overlap (a claimed container counts once against each predicate); the report notes it.
- **`S_legacy_p3_only_preserved_partial`** — fires ONLY when the row has PARTIAL P#3 top-level scope (some autowork keys populated, others missing). Fully-P#3-populated rows short-circuit the G.1 WHERE and never enter `E`. Fully-P#3-empty rows are the normal hydration target.
- **`S_distiller_failed`** — G.2 distiller must catch its own tool-call failures and return `{"key": "…", "confidence": "low", "reason": "distiller_failed: <cause>"}`; orchestrator maps that to this bucket.

Concrete shape:

```
enumerated E of ineligible T · autopiloted A · surfaced M+L
sql-excluded: g0_gate=… claimed=… container=… orphan_intake=…
skips: g0_summary=… g0_sibling=… g0_waiting=… p1_shadowed=… p4_shadowed=…
       malformed=… cas=… claim=… claim_toctou=… claim_cross_scope=…
       regex=… gh_repo_missing=… pr_head_changed=…
       distiller_failed=… permission_denied=… legacy_p3_only_preserved_partial=…
halted: cap_remainder=… (deferred to next pass) fatal_error=… (halt on Nth row)
sum-check: A + M + L + sum(skips) + halted_cap_remainder + halted_fatal_error == E   [PASS|FAIL]
```

Both halt outcomes (`cap_remainder` and `fatal_error`) are inside the sum — a fatal error on row N means `halted_fatal_error=1` (the N-th row itself) and any G.4-untouched rows N+1..E land in `halted_cap_remainder` (unprocessed by construction). If the sum-check still fails, halt the report and dump raw per-row outcomes — a mismatch is a doctrine gap (rows lost between enumerate and report).

Default pass, `--autopilot`, and `--hydrate-autowork` all emit the full line above and per-row locators in `db_row_full` shape (G.4 ran). `--no-hydrate-autowork` emits only `ineligible T (>threshold=40)` — enumeration ran, hydration did not.

---

## Step 4 — Phase C: surface tier (operator approval per item)

Surface tier never mutates without explicit operator answer. Use a single `AskUserQuestion` when items are well-bounded; otherwise a numbered list with explicit per-item options.

### C.1 — Orphan handoff triage

For each orphan handoff (no ws-key match), classify:
- **Session summary** (e.g. `pickup-low-hanging-fruit-2026-MM-DD-NNZ`) → archive (work it captured already shipped via cited PRs/commits).
- **Orchestration label** (e.g. `orch-improve-2026-MM-DD-wave-N-recovery-needed`) → archive if superseded by newer orch handoff; else keep.
- **Cross-cutting initiative** (e.g. `information-schema-permissions-blindspot-eradication`) → ask whether to create-workstream or archive.
- **Legitimate parent without ws row** (e.g. early SPEC drafts) → ask whether to `project_create_workstream` and link.

Surface as:

```
🗂  ORPHAN HANDOFFS — N items, ~M sec to clear

[1] pickup-low-hanging-fruit-2026-06-19-22Z (1d old, summary)
    → archive (work shipped via cited PRs)?  [Y/n]
[2] cron-schedules-full-refresh (3d, cross-cutting)
    Summary excerpt: "Dedicated session needed: cron-schedules KB entry full reconciliation. …"
    → archive | create-workstream "cron-schedules-full-refresh" | keep
[3] …
```

Apply each via `archive_handoff` or `project_create_workstream` + `save_handoff` (carry summary forward) + `archive_handoff` — run the **Pre-archive supersession check** before each `archive_handoff` (the create-workstream path names the carried-forward handoff as successor; plain orphan archives normally take the no-successor branch).

### C.1b — Multi-handoff-per-workstream cleanup

The Session Conventions invariant is "Keep at most one active handoff per workstream; archive superseded handoffs." The Step 2 multi-handoff detector query surfaces workstreams currently violating it. Prior /hygiene-audit passes silently missed this because the orphan query was label-only (see pa.notes#1992).

Do NOT bulk-archive by age. Older handoffs on the same workstream come in two shapes:

- **Progressive same-context updates.** Newer handoff summarizes the same work at a later moment (e.g., `<key>` base + `<key>-envelope-v1` + `<key>-envelope-v2`; base + summary of downstream shipment; earlier round + later round of the same audit). Older row's context is subsumed by the newer. Archiving the older is safe — the newer will resume anyone who picks up.
- **Distinct sub-work in progress.** Older handoff points at a **different worktree** or names a **separate active PR / sub-task** that the newer handoff does not cover. Archiving the older drops the resume pointer to that sub-work. The invariant still applies to the parent workstream — the correct durable resolution is to `project_create_workstream(parent_workstream_ref=<parent>)` for the sub-work, then `save_handoff(workstream_id=<child>)` + `archive_handoff(<old id on parent>)`. "Keep on parent" is only acceptable as an explicit, single-pass deferral (see disposition options below).

Signals for classification. The Step 2 detector returns each row's `working_directory` + first 240 chars of `summary` in parallel arrays. Before making the final call, fetch each candidate id's `data.cited_refs` and full `summary` via `get_handoff(id=<uuid>)` (`data.cited_refs` lives in JSONB and is not in the detector row). Cross-reference:
- Does the older row cite a PR / commit / worktree the newer row does not?
- Does the older row's `working_directory` still exist and contain unmerged local commits (`git status` in that path)?
- Does the older row's cited PR still show `state=OPEN` on GitHub?

Any "yes" → distinct sub-work → prefer the child-workstream move; falling back to "defer" is a re-surface obligation, not durable state.

Surface as one batch with a per-workstream disposition:

```
🔁  MULTI-HANDOFF WORKSTREAMS — N workstreams, K older-handoff candidates

[1] strategy-registry-4-surface-reconciliation-gate (3 active)
    older: 4a21d3e0 (2026-07-05, /home/rj/git/trading_research.worktrees/…) — base
    older: 903743d9 (2026-07-09, /home/rj/git) — envelope v1
    newer: 68fcd550 (2026-07-09, /home/rj/git) — envelope v2 (subsumes v1)
    → [A] archive both older (same-context progression, subsumed by newer)
    → [B] archive envelope-v1 only, keep base
    → [C] drill in

[2] keel-modular-os-program (2 active)
    older: 54549bec (2026-07-10 06:05, /home/rj/git/potato-brain/.worktrees/W-keel-modular-os-portfolio-conversion) — distinct sub-work
    newer: 45bcf77a (2026-07-10 20:48, /home/rj/git/potato-brain.worktrees/W-autowork-supervisor-v1-substrate)
    → [A] move-to-child-workstream (create `keel-modular-os-portfolio-conversion` under parent + re-anchor older handoff; invariant preserved)
    → [B] archive older (accept the drop of the resume pointer to the older worktree)
    → [C] defer to next pass (LEAVES INVARIANT VIOLATED — older handoff re-surfaces on the next /hygiene-audit; only use when the distinction is <24h from resolving)
    → [D] drill in
```

Skip carve-outs (do NOT surface for archive; note them in the batch as "skipped (protected)"):
- Any handoff on a workstream with an active `pa.workstream_claims` row.
- Any handoff whose `working_directory` matches an active peer's worktree (Step 1 ladder).
- Any handoff cited as a `kb_handoff` ref on a claimed parent workstream.
- Any handoff younger than 30 minutes.

Apply operator's per-workstream answer — run the **Pre-archive supersession check** before every `archive_handoff` below (same-workstream archives name the newer same-workstream handoff as successor; the move-to-child path names the carried-forward child handoff as successor):
- **archive** older row → `archive_handoff(id=<uuid>)`
- **move-to-child-workstream** → `project_create_workstream(key=<child_key>, parent_workstream_ref=<parent>, source_kind='hygiene_audit', acceptance_schema_id='legacy-unclassified/v1')` + `save_handoff(workstream_id=<child_id>, label=<child_key>, data=<carry summary+cited_refs forward>)` + `archive_handoff(<old parent-linked id>)`
- **defer** → no mutation, but the pass MUST include the deferred `(ws_key, older_id)` in the Phase D handoff `data.deferred_multi_handoff[]` and the D-report so the next /hygiene-audit invocation re-surfaces without re-triage

Log evidence per authorized mutation: the Session Conventions invariant citation, count reduction, and for preserved/deferred rows the specific sub-work signal (worktree path / PR number / commit SHA) that justified the disposition.

### C.2 — Stale active parent reconciliation

For each stale parent workstream Step 2 surfaced (`status='active' AND days_stale > 7`; event recency is NOT part of the filter — see touch-pattern gotcha below), surface:

```
🌿 STALE ACTIVE PARENTS — N items

[1] kb-pa-orphan-scan-and-cron-migration (15d stale)
    Summary: "KB/PA orphan scan and PH_API cron migration"
    Recent events: none in 15d
    → close=done (cite evidence) | close=superseded (cite by) | update-summary + new event | keep
[2] svi-sabr-vol-surface (13d stale, low priority)
    → close=abandoned | keep low | keep
```

Apply via `project_close_workstream` + `acceptance_schema_id` (use `legacy-unclassified/v1` + `status=archived` + `closeout_reason` for legacy rows lacking schemas) OR `project_update_workstream` + `project_record_event` (BOTH calls required for the "update-summary + new event | keep" disposition — see touch-pattern gotcha below).

> **Touch-pattern gotcha — both calls still required (evidence + clock).** [Corrected 2026-07-16: `project_record_event` NOW bumps `pa.workstreams.updated_at` — the handler runs `UPDATE pa.workstreams SET updated_at = NOW()` after the event insert (`pg_mcp/project_queries.py`, `project_record_event`). The pre-2026-06-30 behavior described below no longer holds; the both-calls rule stands for evidence-trail + summary-refresh reasons, not clock mechanics.] Historically, `project_record_event` alone did NOT bump `pa.workstreams.updated_at`, so an event-only touch left the row re-surfacing as stale (the Step 2 stale-parent query keys off the parent timestamp, not `MAX(pa.workstream_events.created_at)`); that clock defect was the original reason both calls were required, and it no longer exists. Current practice for an "update-summary + new event | keep" disposition: still call BOTH `project_update_workstream(workstream_key_or_id, expected_version=N, summary=...)` (bumps `updated_at` and `version`) AND `project_record_event(... event_type='reconcile_finding' ...)` in the same operator turn — the update refreshes the summary, the event carries the evidence. The two MCP calls are not DB-atomic — but ordering is safe in either direction (`project_record_event` doesn't touch `version`, so it doesn't compete with the update's optimistic lock); the only failure mode is partial state if one call errors, which the operator should re-try. Original clock-defect discovery (2026-06-30): `pa.notes#1589` + `pa.workstream_events#10759` (FCSM workstream `47b36865`: event recorded successfully but `updated_at` remained 7.1d stale until the follow-up `project_update_workstream` bumped it).

### C.3 — Proposed queue triage

Group proposed rows into four buckets, surface ONE block per bucket:

```
📋 PROPOSED QUEUE — N items, target ≤20

═══ ACTIVATE (real next-action ready) ═══
[A1] ticker-floors-pr-2-5-read-path-gates — production correctness gate
[A2] pg-cron-watchdog-v3-window-transition-regression — false-positive RCA
[A3] keel-retry-stop-decision-tree — directly attacks wasted sessions
...

═══ MERGE INTO PARENT ═══
[M1] g1-r3b-* (4 items) → fold under g1-r3b-observability-followon-program umbrella?
[M2] keel/bus reliability mini-lanes → fold under agent-substrate-program?
...

═══ PARK (waiting external) ═══
[P1] keel-claude-sdk-integration — waiting OAuth + allowlist
[P2] hedge-flow-integration-engine — waiting approval
...

═══ ABANDON / ARCHIVE (superseded) ═══
[X1] autowork-permissive-default — superseded by PR cluster shipped
[X2] tool-registry-implementation — superseded by pa-pm-reconciliation-layer PR-1
...
```

Bucket answers via numbered choice OR per-block `AskUserQuestion`. Apply each via `project_update_workstream(status='active'|'blocked'|'waiting_external')`, `project_create_workstream(parent_workstream_ref=...)` + folding refs, or `project_close_workstream(status='abandoned'|'superseded')`.

### C.4 — Open KB proposals + open PA recommendations

Surface counts only; defer the drill-down to `mcp__knowledge-base__list_proposals()` and a dedicated review pass. Do not auto-clear PA-authored recommendations (per `/pickup` Step 6 hard rule).

### C.5 — Autowork scope hydration (medium/low-confidence rows)

Only surfaced when `--hydrate-autowork` ran and G.4 handed down `medium`/`low` confidence rows. Never runs in bare mode.

Per row surface the distiller's `proposed_merge` plus its evidence trail. Group by workstream_kind (execute-shaped vs refresh-shaped) so the operator can batch-answer where the mode is the same. Confidence tier drives the default:

```
🔧  AUTOWORK SCOPE HYDRATION — N rows (M medium · L low)

[1] carl-review-sync-escalation-terminal-result  (medium)
    current: {}
    proposed:
      repo:         "potatohedge/claude-config"   ← handoff.working_directory + git remote (medium)
      base_branch:  "main"                        ← git symbolic-ref (high)
      target_files: ["mcp-servers/carl-review/…"] ← git log --stat (medium — no PR)
    → apply-as-proposed | edit | skip

[2] svi-sabr-vol-surface  (low — no PR, no handoff)
    current: {}
    proposed:
      repo:         null (unknown)
      target_files: ["research/svi_sabr/*"]       ← summary text only (low)
    → operator-fills(repo=?, base_branch=?, target_files=?) | mark-ineligible | skip
```

Apply operator's answer via the appropriate primitive:

- **`operator-fills(...)`** and other `source_ref` edits use `project_record_event` pre-image + `project_update_workstream(source_ref=<merged>)` — `source_ref` is a mutable field on that tool.
- **`mark-ineligible`** cannot use `project_update_workstream` — that tool's schema (`mcp-servers/postgres/pg_mcp/tools.py:399`) exposes only `status/priority/summary/owner_kind/owner_id/source_ref/acceptance_schema_id/acceptance_evidence`, NOT `autowork_gate_state` or `autowork_gate_detail`. Use `execute_sql` directly with a full optimistic-lock UPDATE that **matches the canonical helper's write shape** (`mcp-servers/postgres/pg_mcp/project_queries.py:1060` shows the canonical helper does `SET updated_at = NOW(), version = version + 1` on every workstream write):
    ```sql
    UPDATE pa.workstreams
      SET autowork_gate_state = 'ineligible_operator_approval',
          autowork_gate_detail = jsonb_build_object(
            'reason','hygiene_C5_operator_gated',
            'source','hygiene-audit YYYY-MM-DD'),
          autowork_gate_updated_at = now(),
          updated_at = now(),                  -- mirror canonical helper
          version = version + 1                -- optimistic-lock invariant
      WHERE id = :ws_id AND version = :expected_version;
    ```
    Missing `version = version + 1` breaks the optimistic-lock invariant — a later writer holding the same stale `expected_version` would still succeed under a CAS check that only reads-but-doesn't-bump. **Verifying CAS outcome via `execute_sql`:** UPDATEs go through `conn.execute()` and expose the command status/`rows_affected` in the tool response envelope, NOT `RETURNING` rows (`mcp-servers/postgres/pg_mcp/queries.py:384-399`). Therefore `RETURNING id, version AS new_version` is unusable to read back the new row — check `rows_affected == 0` for CAS mismatch (skip + surface), and treat `rows_affected == 1` as success (post-write `version` is `expected_version + 1` by construction; do not depend on a returned `new_version` value). Pair with a `project_record_event(event_type='reconcile_finding', payload={"reason":"C5_mark_ineligible_pre_image", ...})` for reversibility. Do NOT touch `source_ref`. Canonical enum value is `ineligible_operator_approval` per live CHECK constraint (NOT `operator_hold` — that literal is not in the enum).
- Follow-up: adding `autowork_gate_state`/`autowork_gate_detail` to `project_update_workstream`'s mutable-field allowlist is a separate PR against pg_mcp; until then, the `execute_sql` path is the only supported one and it MUST mirror the canonical write shape above.

---

## Step 5 — Phase D: durable handoff + post-run report

### D.1 — Save handoff

ONE `save_handoff()` call with structured `data.durability_locators[]` per the **Durability Locators** contract (see CLAUDE.md). Required locator forms:
- per archived handoff: `{type: 'db_row', table: 'knowledge.handoffs', key: 'id', value: '<uuid>', timestamp: '<iso>', host: 'db1-prod', purpose: 'archived during hygiene pass'}`
- per closed loop: the string `"db_row://pa.review_loops/<uuid>"` as a direct element of `data.durability_locators[]` (the array accepts URL-form strings — `kb_mcp/db.py` `_has_structured_durability_locator`; `pa.review_loops` is NOT in the structured `db_row_full` allowlist, only in `_DURABLE_DB_ROW_URL_TABLES`; inline locators in summary prose are IGNORED by `save_handoff`)
- per workstream closure: `{type: 'db_row', table: 'pa.workstreams', key: 'id', value: '<uuid>', timestamp: '<iso>', host: 'db1-prod', purpose: 'closed during hygiene pass'}`
- per autowork-hydrated workstream (Step 3G): `{type: 'db_row', table: 'pa.workstreams', key: 'id', value: '<uuid>', timestamp: '<iso>', host: 'db1-prod', purpose: 'source_ref hydrated during hygiene pass — keys: repo,base_branch,target_files'}`
  (Shape per `kb_mcp/db.py` `_DURABLE_STRUCTURED_LOCATOR_FORMS` `db_row_full`: required keys `type, table, key, value, timestamp, host`. The prior `{kind: 'db_row', ...}` examples matched no accepted form — corrected 2026-07-16.)
- per missing-path worktree registry prune: `{type: 'host_path_mtime', path: '${repo_common_dir}/worktrees', mtime: '<iso>', host: '<host>', purpose: 'missing-path worktree registry prune during hygiene pass', timestamp: '<iso>'}`
- per skill/code change shipped: `{type: 'commit_sha', commit: '<sha>', repo: '<owner/repo>'}` (required key is `commit` per `db.py` `_DURABLE_STRUCTURED_LOCATOR_FORMS`; the prior `{kind, value}` shape is rejected)

Label: `hygiene-audit-<YYYY-MM-DD-NNZ>`. Working_directory: cwd at time of pass.

### D.2 — Post-run report (to operator, terse)

```
🧹 HYGIENE PASS COMPLETE — Δ counts

Surface              | Before | After | Δ
---------------------|--------|-------|----
Active handoffs      |   52   |   N   | -K
Open review loops    |   12   |   N   | -K
Proposed workstreams |   42   |   N   | -K
Stale active parents |    9   |   N   | -K
Autowork-ineligible  |  155   |   N   | -K   (default/--autopilot applies hydration; --no-hydrate-autowork = reported only)
Stale workstreams    |  120   |   N   | -K   (freshness sweep — default/--autopilot; --no-freshness = skipped)
Open KB proposals    |    6   |   6   |  0  (deferred)

Autopilot tier B:   K archivals · M loop closes · L checkpoint folds · P missing-path prunes
Autopilot tier 3F:  R refreshed · S status-changed · X CAS/claim-skipped   (or "skipped: --no-freshness")
Autopilot tier 3G:  A hydrated · S skipped-by-bucket                        (or "skipped: --no-hydrate-autowork")
Surface tier:  K decided · M deferred to next pass
Skipped (claimed): 4 workstreams (orch peer 49100208) · 1 handoff

Durable handoff: <uuid>  (label: hygiene-audit-YYYY-MM-DD-NNZ)
Deferred items: <list of operator decisions punted to next pass>
```

### D.3 — Log decision

ONE `log_decision(category='change', summary='Hygiene pass YYYY-MM-DD: <Δ counts>', reasoning='<tier results + skipped + deferred>')`.

---

## Step 6 — Auto-suggested follow-on work

If ANY autopilot tier hit its 50-mutation safety cap (B, 3F, or 3G each track separately), recommend re-running `/hygiene-audit --autopilot` in a fresh session before any new build work — the worklog still has debt. Name the tier(s) that capped so the operator can scope the follow-up (e.g. `--freshness` or `--hydrate-autowork` alone if only one capped).

If surface tier surfaced >10 items deferred to operator, recommend `/hygiene-audit --surface` next session to focus the operator's attention.

If proposed queue >30, note that v1 `/autowork triage` was removed in PR-D cutover; the v2 selector ranks candidates per cycle server-side, so backlog drainage now happens by running `/autowork --budget=N` (each cycle pulls one candidate). Operator may manually triage proposed workstreams via `/pickup` Phase A surfaces if v2 selector ordering doesn't prioritize correctly.

---

## Hard rules

- **Never silent on surface tier.** Every operator-approved mutation goes through explicit answer.
- **Re-query before mutating.** Surface state may change between inventory and mutation; re-read the row.
- **"Touch + keep active" requires BOTH `project_update_workstream` + `project_record_event`.** The update refreshes the summary + version; the event carries the evidence trail. (Clock-mechanics rationale corrected 2026-07-16: `project_record_event` now bumps `updated_at` itself — see § C.2 touch-pattern gotcha. The both-calls rule stands.) Discovery evidence: `pa.notes#1589` + `pa.workstream_events#10759`.
- **Skip claimed workstreams + their handoffs + their cited refs.** Claim-holder owns mutation.
- **Skip handoffs younger than 30 min** — closing session may still be wrapping.
- **No bulk-archive by age alone** — backing-ws status + claim status + peer scope must all clear first.
- **No auto-clear of PA-authored `pa.notes(kind='recommendation')`** — surface, draft, wait per `/pickup` Step 6.
- **Stop on first mutation error.** Autopilot tier halts; don't silently route around a failing primitive. (Step 3F exception, by design: optimistic-lock conflicts and permission-classifier denials are expected per-row outcomes there — skip + surface those; any OTHER mutation error still halts.)
- **One durable handoff per pass.** Never split a hygiene pass across multiple handoffs.
- **Never overwrite existing `source_ref` keys during hydration.** Step 3G merges missing keys only; a re-queried populated `source_ref.<key>` is treated as ground truth even when the distiller proposed a different value. Overwriting silently rewrites intentional operator state.
- **Autowork hydration respects G.0 carve-outs first.** Claimed workstreams, `autowork_gate_state <> 'eligible'` (any of the five `ineligible_*` states), containers, `orphan-intake`, and rows with self-declared ineligibility markers are enumerated separately for reporting but never mutated. Adding scope fields to these silently promotes work the operator has already parked.

---

## Reference & related

- **`/pickup`** — surfaces hygiene counts (including `autowork_ineligible`) in Phase A envelope; emits hygiene-debt banner when thresholds breach.
- **`/autowork`** — Step 3G exists because keel's `assign_work` selector needs `pa.workstreams.source_ref.{repo, base_branch, target_files}` typed. When `/autowork` returns `selector_stale_state_only` with a large `missing_scope_counts` block, the fix is a `--hydrate-autowork` pass, not a retry.
- **`/autowork triage`** — REMOVED in PR-D cutover (claude-config#254). v2 selector ranks server-side per cycle; no separate triage classifier. To drain proposed queue: `/autowork --budget=N` cycles through candidates per the v2 selector. Manual triage via `/pickup` Phase A.
- **`state-hygiene-janitor-routine` workstream** (pa.workstreams:9e91767b) — detector code that surfaces drift (PR #562); this skill is the executor that drains what the detector finds.
- **`review-loop-hygiene-cleanup-policy` workstream** (pa.workstreams:98f94c0a) — PA-owned policy SPEC for review-loop cleanup; this skill executes the policy.
- **`workstream-summary-status-drift-followup` workstream** (pa.workstreams:74059c6a) — PR #563 detector for summary drift; complementary surface.
- **KB `workstream-hygiene`** — canonical mutation contract for `pa.notes` / `pa.note_reviews` / `knowledge.handoffs` / `knowledge.proposals` coordination.
