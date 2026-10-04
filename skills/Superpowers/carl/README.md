# Portable CARL

CARL is a **Convergent Adversarial Review Loop** for local AI coding and research environments. It turns “get a second opinion” into a disciplined protocol:

1. establish an artifact or decision,
2. send it to an independent reviewer,
3. verify every finding instead of blindly accepting it,
4. revise selectively,
5. re-review sequentially until the material disagreements are resolved.

The package is vendor-neutral. It does not require a particular model, MCP server, database, company environment, or hosted service. Reviewer invocation is an adapter: use a fresh subagent, another local CLI, an MCP tool, or a human reviewer.

## What survives from the full protocol

- Four modes: `SPEC`, `CODE`, `IDEATE`, and `CONSULT`
- Sequential rounds; later reviewers see earlier findings and resolutions
- Fresh-context and cross-family review when available
- Artifact identity and diff-access proof
- Per-finding `AGREE`, `DISAGREE`, or `NEEDS-HUMAN` disposition
- Explicit pushback against reviewer false positives and wordsmithing
- Fail-closed `INFRA_BLOCKED` verdict when the reviewer cannot inspect the artifact
- A four-round cap and cycle detection
- A compact, auditable final summary

## What was deliberately removed

- Private infrastructure, databases, knowledge bases, and project names
- Fixed model names and model-provider assumptions
- Organization-specific bridges, task systems, budgets, and telemetry
- Production topology and market-domain conventions
- Historical incident notes that are useful internally but noise for a portable install

## Install

User-level install for both Claude Code and Codex:

```bash
cd portable/carl
./bin/install.sh --target user --runtime both
```

Project-local install:

```bash
./bin/install.sh --target project --runtime both --project-dir /path/to/repo
```

The installer refuses to overwrite a different existing file unless `--force` is supplied. Forced replacement creates a timestamped backup.

### Manual install

Claude Code:

```bash
mkdir -p ~/.claude/skills/carl ~/.claude/commands
cp SKILL.md ~/.claude/skills/carl/SKILL.md
cp commands/carl.md ~/.claude/commands/carl.md
```

Codex:

```bash
mkdir -p ~/.codex/skills/carl
cp SKILL.md ~/.codex/skills/carl/SKILL.md
```

Restart the local agent runtime after installation if it does not hot-reload skills.

## Use

```text
/carl spec docs/design.md
/carl code HEAD~1..HEAD
/carl ideate "replace the current job queue"
/carl consult "SQLite or Postgres for this local tool?"
```

Mode can be omitted when the intent is obvious:

```text
/carl review this migration plan and do not miss rollout hazards
```

## Reviewer setup

CARL is useful with one model, but stronger with two independent model families.

Recommended order:

1. **Round 1:** fresh context in the author’s model family, at equal or greater capability.
2. **Rounds 2–3:** a different model family, if one is available.
3. **Round 4:** strongest independent reviewer available, used only as a final ship-check when the artifact warrants it.

If only one family is installed, use fresh processes or subagents and disclose that reviewer diversity was reduced. An inline “let me reconsider my own answer” is not an independent review.

See [`adapters/README.md`](adapters/README.md) for integration patterns.

## Expected behavior

CARL is adversarial, not deferential. A reviewer finding is a hypothesis until the driver verifies it against the artifact, tests, docs, or observed behavior. The driver should patch genuine defects, reject false positives with evidence, and escalate defensible disagreements.

The loop stops when:

- there are no remaining load-bearing findings,
- remaining disagreements are explicitly documented and accepted,
- human judgment is required,
- the reviewer cannot access the artifact,
- a finding cycles after a claimed fix, or
- four sequential rounds have completed.

## Validation

```bash
bash -n bin/install.sh bin/uninstall.sh tests/smoke.sh
./tests/smoke.sh
```

The smoke test installs into a temporary project, verifies the Claude and Codex surfaces, tests overwrite protection, and uninstalls the package.

## File tree

```text
portable/carl/
├── LICENSE
├── README.md
├── SKILL.md
├── adapters/README.md
├── bin/install.sh
├── bin/uninstall.sh
├── commands/carl.md
├── examples/review-packet.md
└── tests/smoke.sh
```

## Security and privacy

The package itself makes no network calls, reads no credentials, emits no telemetry, and stores no review history outside files the user explicitly creates. Reviewer adapters may invoke external services. Do not send proprietary artifacts to a remote reviewer unless that reviewer is approved for the data.

## License

MIT. See [`LICENSE`](LICENSE).
