# Final Whole-Branch Review Prompt Template

Use this adapter for the final broad review after all task reviews pass. It
applies the requesting-code-review rubric while binding independent runtime and
artifact evidence.

This verdict is authoritative only from a fresh, distinct non-forked reviewer
surface that can select and attest the contract's model, effort, reviewer role,
read-only sandbox, and context. Generic Codex `spawn_agent` v2 is advisory only.
If no qualified reviewer surface is available, stop SDD and continue with a
qualified root outside this skill.

```text
Review workload contract: [REVIEW_CONTRACT_FILE]
Review contract ID: [REVIEW_CONTRACT_ID]
Whole-branch integration implementation contract: [IMPLEMENTATION_CONTRACT_FILE]
Implementation lineage: whole_branch_integration
Accepted whole-branch integration attestation: [IMPLEMENTATION_ATTESTATION_FILE]
Whole-branch integration session evidence: [IMPLEMENTATION_SESSION_LOG]
Review session evidence: [REVIEW_SESSION_LOG]
Controller-known artifact SHA-256: [ARTIFACT_SHA256]

Base SHA: [BASE_SHA]
Head SHA: [HEAD_SHA]
Review package: [DIFF_FILE]
Requirements or plan: [PLAN_FILE]

You are the final whole-branch reviewer. Use the rubric in
../requesting-code-review/code-reviewer.md. Review the complete package against
the requirements, identify merge-blocking correctness or maintainability
issues, and cite exact path:line or diff-hunk evidence for every finding.

Your terminal assistant handback must contain one complete line in the form
`VERDICT: SHIP | SHIP-WITH-CAVEATS | NEEDS_REVISION | BLOCK` using exactly one
value, plus an exact `Artifact: <declared-path>` line for at least one declared
artifact path even when the verdict has no findings.

Remain read-only. Do not edit, commit, push, review, or merge. Stop if the
implementation evidence, artifact hash, independence, fresh context, or your
effective runtime cannot be attested. The controller will run
codex-workload-contract attest and accept against the exact artifact and
both session logs before consuming your verdict.
```

The whole-branch integration and review sessions must be distinct non-forked
threads. Their contracts must bind the same repository, base SHA, artifact
kind, `whole_branch_integration` implementation lineage, and complete path
manifest. The implementation attestation must come from the qualified-root
surface with effective role `root`. A task-scoped worker attestation is not a
whole-branch integration attestation.
The controller owns the contract files, artifact hash, acceptance gate, and any
Git commit after accepted fixes.
