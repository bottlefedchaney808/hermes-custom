# Reviewer adapters

CARL separates **review policy** from **review transport**. `SKILL.md` defines the policy. An adapter only needs to deliver a review packet to a fresh reviewer and return its response.

## Adapter contract

An adapter should accept:

```yaml
repo_or_workspace: <readable path>
mode: SPEC | CODE | IDEATE | CONSULT
artifact_identity: <hash or immutable ref>
packet: <prompt text or file path>
timeout_seconds: <bounded timeout>
read_only: true
```

It should return:

```yaml
status: ok | timeout | error | artifact_inaccessible
reviewer_family: <family or unknown>
reviewer_model: <model or unknown>
response: <verbatim reviewer response>
```

The driver, not the adapter, validates `artifact_quote_back`, access proof, verdict shape, and findings.

## Integration patterns

### Fresh subagent

Use an agent/subagent tool with a clean context. This is the easiest same-family R1, but it is not cross-family diversity.

### Alternate local CLI

Write the packet to a temporary file and invoke a second model CLI in read-only mode. Exact flags vary by version; verify current CLI help rather than copying stale flags.

```bash
reviewer-cli --working-directory "$REPO" --read-only --prompt-file "$PACKET"
```

Require a bounded timeout, no write approval, the reviewed checkout as working directory, immutable artifact identity, and verbatim stdout.

### MCP reviewer

Pass `cwd`, a read-only sandbox, no write approval, a concise prompt with a packet file reference, and an explicit timeout. Do not send R2 until R1 has been evaluated.

### Human reviewer

Export `examples/review-packet.md`, attach the artifact, and ask the reviewer to preserve the response schema. CARL is a protocol, not an automation requirement.

## Fallback order

1. preferred independent reviewer,
2. alternate reviewer family,
3. fresh same-family reviewer with `diversity: reduced`,
4. human reviewer,
5. `INFRA_BLOCKED`.

Never downgrade an artifact-access failure into a substantive code verdict.

## Timeouts

| Review shape | Timeout |
|---|---:|
| discrete consult | 3–5 minutes |
| small diff or short spec | 5–10 minutes |
| multi-file review | 10–20 minutes |
| deep audit | explicitly budgeted; split by subsystem |

After two transport failures on the same reviewer and artifact, switch adapters instead of repeatedly increasing the timeout.

## Security

- Default to read-only.
- Never grant a reviewer write access merely because review is inconvenient otherwise.
- Confirm whether a CLI uses local inference or uploads prompts.
- Do not include secrets, tokens, `.env` contents, credential files, or unrelated private context.
- Clean temporary packet files according to the project’s data-retention policy.

## Adapter quality checklist

- [ ] Fresh context, not the author’s active conversation
- [ ] Artifact bytes or immutable locator are readable
- [ ] Artifact identity is included
- [ ] Read-only execution
- [ ] Bounded timeout
- [ ] Verbatim response returned
- [ ] Errors distinguish timeout, transport failure, and inaccessible artifact
- [ ] No hidden fallback to inline self-review
