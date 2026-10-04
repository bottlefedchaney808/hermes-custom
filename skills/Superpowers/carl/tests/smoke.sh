#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf -- "$TMP_ROOT"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

bash -n "$PACKAGE_DIR/bin/install.sh" "$PACKAGE_DIR/bin/uninstall.sh" "$PACKAGE_DIR/tests/smoke.sh"
grep -q 'Sequential round loop' "$PACKAGE_DIR/SKILL.md" || fail "sequential loop missing"
grep -q 'Adversarial-back evaluation' "$PACKAGE_DIR/SKILL.md" || fail "adversarial-back missing"
grep -q 'INFRA_BLOCKED' "$PACKAGE_DIR/SKILL.md" || fail "fail-closed verdict missing"
grep -q 'Stop at four rounds' "$PACKAGE_DIR/SKILL.md" || fail "round cap missing"

"$PACKAGE_DIR/bin/install.sh" --target project --runtime both --project-dir "$TMP_ROOT"
[[ -f "$TMP_ROOT/.claude/skills/carl/SKILL.md" ]] || fail "Claude skill missing"
[[ -f "$TMP_ROOT/.claude/commands/carl.md" ]] || fail "Claude command missing"
[[ -f "$TMP_ROOT/.codex/skills/carl/SKILL.md" ]] || fail "Codex skill missing"
cmp -s "$PACKAGE_DIR/SKILL.md" "$TMP_ROOT/.claude/skills/carl/SKILL.md" || fail "Claude skill differs"
cmp -s "$PACKAGE_DIR/SKILL.md" "$TMP_ROOT/.codex/skills/carl/SKILL.md" || fail "Codex skill differs"

printf 'unrelated command
' > "$TMP_ROOT/.claude/commands/carl.md"
if "$PACKAGE_DIR/bin/install.sh" --target project --runtime claude --project-dir "$TMP_ROOT" >/dev/null 2>&1; then
  fail "overwrote existing file without --force"
fi
"$PACKAGE_DIR/bin/install.sh" --target project --runtime claude --project-dir "$TMP_ROOT" --force >/dev/null
compgen -G "$TMP_ROOT/.claude/commands/carl.md.bak.*" >/dev/null || fail "backup missing"

"$PACKAGE_DIR/bin/uninstall.sh" --target project --runtime both --project-dir "$TMP_ROOT"
[[ ! -e "$TMP_ROOT/.claude/skills/carl/SKILL.md" ]] || fail "Claude skill not removed"
[[ ! -e "$TMP_ROOT/.claude/commands/carl.md" ]] || fail "Claude command not removed"
[[ ! -e "$TMP_ROOT/.codex/skills/carl/SKILL.md" ]] || fail "Codex skill not removed"
echo "PASS: portable CARL smoke test"
