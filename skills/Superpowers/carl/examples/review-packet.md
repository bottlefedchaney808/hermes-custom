# CARL review packet

Copy this file, fill the fields, and send it to the selected reviewer.

## Identity

```yaml
mode: CODE
round: 1
subject: <artifact name or diff range>
artifact_identity: <sha256, commit SHA, or version>
author_family: <family or unknown>
reviewer_family_requested: <family or any>
```

## Scope

**In scope**

- <item>

**Out of scope**

- <item>

## Context and invariants

- <fact the reviewer needs>
- <contract that must remain true>

## Locked decisions

- <decision and human authority; write “none” if none>

## Acceptance gates

- <observable success criterion>

## Prior findings

For R1: `none`.

For R2+:

| ID | Finding | Driver disposition | Resolution/evidence |
|---|---|---|---|
| R1-F1 | ... | AGREE | patched in v2 |
| R1-F2 | ... | DISAGREE | test X proves ... |

## Artifact access

```yaml
workspace: <path or repository>
artifact: <path, diff command, immutable URL, or inline body>
```

## Review task

Review adversarially. Find material defects, missing assumptions, contract violations, unsafe behavior, and unproven claims. Cite exact evidence. Give concrete replacements. Do not invent issues merely to appear thorough, and do not relitigate locked decisions.

For code, prioritize correctness, data loss, security, money/units, concurrency, schema/API contracts, rollback, and tests. If this is a bugfix, identify the root cause and verify the patch addresses it.

## Required response

```yaml
artifact_quote_back: <repeat artifact_identity exactly>
access_proof: <path:line, diff hunk, hash, or section citation>
verdict: SHIP | SHIP_WITH_CAVEATS | NEEDS_REVISION | BLOCK | INFRA_BLOCKED
findings:
  - id: R1-F1
    severity: critical | major | minor
    claim: <specific problem>
    evidence: <specific locator or reproduction>
    consequence: <why it matters>
    replacement: <concrete correction or null>
confidence: low | medium | high
```

If you cannot inspect the artifact, do not infer a code-level verdict from metadata. Return:

```yaml
verdict: INFRA_BLOCKED
blocker: artifact_inaccessible
attempted: [<what you tried>]
```
