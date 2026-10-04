---
name: carl
description: Portable Convergent Adversarial Review Loop. Use for second opinions, adversarial review, specs, plans, code audits, brainstorms, discrete decisions, migrations, cross-repo changes, and other high-blast-radius work.
version: 1.0.0
metadata:
  portable: true
  package: portable-carl
---

# CARL — Convergent Adversarial Review Loop

CARL is a review protocol, not a model name. The driver creates or identifies an artifact, obtains an independent critique, verifies each finding, revises selectively, and repeats sequentially until the result converges or requires human judgment.

## Invocation

```text
/carl [spec|code|ideate|consult] [artifact, range, path, or question]
```

Infer the mode when omitted:

| Mode | Use | Deliverable |
|---|---|---|
| `A / SPEC` | plan, design, architecture, rollout, migration | converged artifact and open decisions |
| `B / CODE` | diff, branch, PR, files, bugfix, audit | verified findings and fix disposition |
| `C / IDEATE` | option generation and narrowing | 3–5 viable options with failure modes |
| `D / CONSULT` | one discrete decision | reconciled answer or explicit disagreement |

If intent is ambiguous, choose the narrowest mode that answers the request. Do not turn a discrete decision into a sprawling architecture exercise.

## Core invariants

1. **The driver owns the answer.** Reviewer output is evidence, not authority.
2. **Rounds are sequential.** Round N+1 must receive Round N’s findings and dispositions. Parallel independent reviews are a panel, not CARL.
3. **Independent context is mandatory.** Never present inline self-reflection as an independent review.
4. **Inspect before judging.** A reviewer that cannot read the artifact cannot issue a code- or artifact-level verdict.
5. **Verify before patching.** Every finding is a hypothesis until checked against source, tests, docs, data, or a reproducible observation.
6. **Preserve artifact identity.** Review immutable content where possible and record what was actually inspected.
7. **Do not relitigate locked decisions.** Review implementation and framing; escalate changes to explicitly locked decisions.
8. **Stop at four rounds.** More review is not automatically more truth. Cycles and stalemates go to a human.

## Reviewer selection

At preflight, inventory the reviewer adapters available in the environment: fresh subagent, alternate local model CLI, MCP reviewer, remote API, or human.

Preferred routing:

| Round | Reviewer |
|---|---|
| R1 | Fresh context in the author’s model family, same or higher capability |
| R2–R3 | Different model family for genuinely different priors |
| R4 | Strongest independent reviewer available; final ship-check only |

Rules:

- A same-family R1 is valid only in a fresh process, session, or subagent.
- If only one model family exists, use fresh contexts and state `diversity: reduced` in the summary.
- If no independent reviewer can be invoked, stop with `INFRA_BLOCKED`; do not fabricate a peer verdict.
- Do not silently replace a failed cross-family reviewer with inline self-review.
- Do not run R1 and R2 in one tool batch. R2’s prompt must be written after R1 returns.

## Preflight

Before dispatching R1, record:

```yaml
mode: SPEC | CODE | IDEATE | CONSULT
subject: <path, diff range, artifact name, or question>
author_family: <known family or unknown>
artifact_identity: <sha256, commit SHA, immutable URL, or explicit inline version>
scope:
  in: [<items>]
  out: [<items>]
locked_decisions: [<decisions reviewers may not silently change>]
acceptance_gates: [<what success means>]
reviewer_plan:
  r1: <adapter>
  r2_r3: <adapter>
  r4: <adapter or not planned>
```

For code, prefer an immutable base/head pair or an exported patch. For prose, hash the exact reviewed bytes when practical. If hashing is unavailable, use a clear version label and include the full artifact in the packet.

## Reviewer adapter contract

Every reviewer dispatch must provide:

1. the mode and exact task,
2. the artifact or a readable immutable locator,
3. scope and non-goals,
4. locked decisions and relevant invariants,
5. acceptance gates,
6. prior findings and dispositions for R2+,
7. the artifact identity to quote back,
8. the required response schema below.

Required reviewer response:

```yaml
artifact_quote_back: <identity supplied by driver>
access_proof: <path:line, diff hunk, byte hash, or exact section citation>
verdict: SHIP | SHIP_WITH_CAVEATS | NEEDS_REVISION | BLOCK | INFRA_BLOCKED
findings:
  - id: R1-F1
    severity: critical | major | minor
    claim: <what is wrong>
    evidence: <specific citation or reproduction>
    consequence: <why it matters>
    replacement: <concrete correction, if applicable>
confidence: low | medium | high
```

If artifact identity does not match, discard the verdict. If access proof is absent, the only valid verdict is `INFRA_BLOCKED`.

## Sequential round loop

For each round:

1. Build the packet from the current artifact.
2. Add the prior-round ledger for R2+.
3. Dispatch exactly one reviewer.
4. Validate identity and access proof.
5. Independently evaluate every finding.
6. Patch only agreed findings.
7. Record rejected and escalated findings with evidence.
8. Recompute artifact identity after changes.
9. Decide whether another round is warranted.

Do not call a round complete merely because the reviewer produced fluent prose.

## Adversarial-back evaluation

The common failure mode is rubber-stamping the reviewer. For every finding, use:

```text
Finding: <reviewer claim>
Independent check: <source/test/doc/observation>
Disposition: AGREE | DISAGREE | NEEDS_HUMAN
Action: PATCHED | LEFT_UNCHANGED | ESCALATED
Evidence: <locator>
```

Apply these five checks:

1. **Substance vs wordsmithing** — Does the change alter correctness, safety, clarity needed for execution, or an acceptance gate? If not, keep defensible original wording.
2. **Locked-decision boundary** — Is the reviewer changing a ratified constraint rather than finding an implementation defect? Escalate instead of silently editing it.
3. **Conflict with observed truth** — Does a test, trace, benchmark, or current source contradict the finding? Prefer observed evidence and reply with it.
4. **Confidence conflict** — If driver and reviewer are both high-confidence and disagree, do not hide the split. Escalate cleanly.
5. **Cycle detection** — If the same issue returns after a claimed fix, first verify the reviewer received the new artifact. Then decide whether the fix was incomplete or the reviewer is stale.

Zero pushback across many findings is a calibration warning, not a badge of cooperation. Conversely, rejecting every finding is ego wearing a lab coat. Verify both directions.

## Findings ledger

Maintain one ledger across rounds:

| ID | Round | Severity | Finding | Evidence | Disposition | Resolution |
|---|---:|---|---|---|---|---|
| R1-F1 | 1 | major | ... | `path:line` | AGREE | patched in artifact v2 |
| R1-F2 | 1 | minor | ... | `section 3` | DISAGREE | test proves current behavior |
| R2-F1 | 2 | major | ... | ... | NEEDS_HUMAN | decision required |

Never delete old findings when revising. Mark them resolved, rejected, superseded, or escalated.

## Mode A — SPEC

Use for plans, designs, migrations, architecture, and rollout procedures.

Review dimensions:

- factual correctness,
- missing dependencies,
- ordering and rollback hazards,
- stale or unverifiable claims,
- hidden assumptions,
- acceptance gates,
- security and privacy boundaries,
- mathematical or statistical errors,
- operational failure modes,
- testability and observability.

Reviewer prompt core:

```text
Review this artifact adversarially. Find where it is wrong, overstated,
missing, unsafe, or untestable. Disagreement is useful; politeness is not the
goal. Cite exact sections. Give replacement language or a concrete design
change for material findings. Do not relitigate the locked decisions. If the
artifact is largely correct, say so instead of inventing issues.
```

Converged means no unresolved load-bearing defect remains, or remaining disagreements are explicitly accepted or escalated.

## Mode B — CODE

Use for diffs, branches, bugfixes, regressions, and correctness audits.

Priority order:

1. correctness and data loss,
2. security and authorization,
3. money, pricing, units, and aggregation,
4. concurrency and shared state,
5. API and schema contracts,
6. error handling and rollback,
7. tests that fail to prove the claim,
8. performance on actual hot paths,
9. maintainability only where it creates concrete risk.

Rules:

- Read the concrete handler/body, not only names, decorators, types, or comments.
- Cite specific `path:line` references or diff hunks.
- Reproduce or trace a reported bug before prescribing a fix.
- For a bugfix verdict, state the root cause and evidence connecting the patch to it.
- Classify candidates as `CONFIRMED`, `SUSPICIOUS`, or `VERIFIED_CORRECT` before final triage.
- Do not fix reviewer findings until the driver verifies them.

If the reviewer cannot read the code or diff, return:

```yaml
verdict: INFRA_BLOCKED
blocker: artifact_inaccessible
attempted: [<methods tried>]
```

A metadata-only review cannot produce `SHIP`, `NEEDS_REVISION`, or `BLOCK` about the code.

## Mode C — IDEATE

Use to widen and then narrow an option space.

Process:

1. Driver proposes initial candidates with rationale.
2. Reviewer adds orthogonal options and attacks every candidate.
3. Driver removes dominated options and merges duplicates.
4. Return 3–5 viable options with explicit trade-offs.

Reviewer prompt core:

```text
Propose options the initial list missed, including counter-approaches and
unconventional but viable alternatives. For every existing option, name one
failure mode. Flag any option that dominates another. Do not select a winner
unless one option is strictly dominant under the stated constraints.
```

CARL IDEATE does not auto-pick. The human chooses, or the selected option proceeds to SPEC mode.

## Mode D — CONSULT

Use for one discrete decision.

Driver packet:

```yaml
question: <one sentence>
driver_position: <A or B>
confidence: low | medium | high
rationale: [<up to three load-bearing reasons>]
rejected_options: [<option and reason>]
constraints: [<facts that control the decision>]
```

Require the reviewer to pick a side. Reconcile as follows:

- both agree: proceed,
- reviewer disagrees and survives verification: revise,
- defensible high-confidence disagreement: escalate,
- both remain ambiguous: move to SPEC,
- missing evidence controls the choice: identify the exact check required.

## Convergence and stopping rules

Stop with `convergence: yes` when all critical and major findings are resolved, rejected with evidence, or explicitly accepted; no new load-bearing issue appears in the latest round; and artifact identity/access proof are valid.

Stop with `convergence: partial` when only minor accepted debt remains, a human-owned decision remains, or reviewer diversity was unavailable but the completed review is still useful.

Stop with `convergence: no` when a critical issue remains, the same finding cycles, reviewers have a defensible stalemate, artifact access is blocked, or four rounds complete without convergence.

Do not run a fifth round automatically.

## Final output

```markdown
## CARL summary

**Mode:** SPEC | CODE | IDEATE | CONSULT
**Subject:** <artifact or question>
**Artifact identity:** <hash/ref/version>
**Reviewers:** <round → adapter/family>
**Diversity:** full | reduced | unavailable
**Rounds:** N
**Convergence:** yes | partial | no
**Verdict:** SHIP | SHIP_WITH_CAVEATS | NEEDS_REVISION | BLOCK | INFRA_BLOCKED
**Access proof:** <locator>

### Findings
- Agreed and changed: N
- Rejected with evidence: N
- Escalated to human: N
- Remaining minor debt: N

### Material changes
- <change and why>

### Pushback
- <reviewer finding rejected and evidence>

### Open decisions / blockers
- <item or none>

### Final artifact / answer
<path, ref, or concise answer>
```

If many findings were accepted and none rejected, add: `Calibration warning: no reviewer pushback recorded; recheck for rubber-stamping.`

## Anti-patterns

- Asking “is this good?” instead of “where is this wrong?”
- Dispatching multiple CARL rounds in parallel
- Treating same-session self-reflection as independent review
- Patching every reviewer suggestion
- Dismissing findings because they are inconvenient
- Letting a reviewer relitigate locked decisions silently
- Accepting a verdict without artifact access proof
- Reviewing a stale artifact after it changed
- Hiding unresolved disagreement behind a blended non-answer
- Continuing past four rounds because another pass feels safer
- Spending review effort on style while correctness remains unverified

Iteration is the point. Blind deference is not.
