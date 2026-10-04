#!/usr/bin/env bash
set -euo pipefail

TARGET="user"
RUNTIME="both"
PROJECT_DIR="$PWD"
FORCE=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: uninstall.sh [options]
  --target user|project
  --runtime claude|codex|both
  --project-dir PATH
  --force
  --dry-run
  -h, --help
EOF
}
while (($#)); do
  case "$1" in
    --target) TARGET="${2:?missing value for --target}"; shift 2 ;;
    --runtime) RUNTIME="${2:?missing value for --runtime}"; shift 2 ;;
    --project-dir) PROJECT_DIR="${2:?missing value for --project-dir}"; shift 2 ;;
    --force) FORCE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done
case "$TARGET" in
  user) ROOT="${HOME:?HOME is required}" ;;
  project) ROOT="$(cd -- "$PROJECT_DIR" && pwd)" ;;
  *) echo "--target must be user or project" >&2; exit 2 ;;
esac
case "$RUNTIME" in claude|codex|both) ;; *) echo "invalid --runtime" >&2; exit 2 ;; esac

run() { if ((DRY_RUN)); then printf '+ '; printf '%q ' "$@"; printf '\n'; else "$@"; fi; }
remove_file() {
  local path="$1"
  if [[ ! -e "$path" ]]; then echo "Not installed: $path"; return; fi
  if ((FORCE == 0)) && ! grep -q 'portable-carl' "$path"; then
    echo "Refusing to remove unrecognized file: $path" >&2
    echo "Use --force only after verifying the path." >&2
    exit 3
  fi
  run rm -f -- "$path"
  echo "Removed: $path"
}
if [[ "$RUNTIME" == claude || "$RUNTIME" == both ]]; then
  remove_file "$ROOT/.claude/skills/carl/SKILL.md"
  remove_file "$ROOT/.claude/commands/carl.md"
fi
if [[ "$RUNTIME" == codex || "$RUNTIME" == both ]]; then
  remove_file "$ROOT/.codex/skills/carl/SKILL.md"
fi
echo "Portable CARL uninstall complete. Timestamped backups were left intact."
