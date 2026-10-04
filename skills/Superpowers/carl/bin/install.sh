#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TARGET="user"
RUNTIME="both"
PROJECT_DIR="$PWD"
FORCE=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: install.sh [options]
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

run() {
  if ((DRY_RUN)); then printf '+ '; printf '%q ' "$@"; printf '\n'; else "$@"; fi
}

install_file() {
  local src="$1" dst="$2" parent backup
  parent="$(dirname -- "$dst")"
  if [[ -f "$dst" ]] && cmp -s -- "$src" "$dst"; then echo "Already current: $dst"; return; fi
  if [[ -e "$dst" ]]; then
    if ((FORCE == 0)); then
      echo "Refusing to overwrite existing file: $dst" >&2
      echo "Re-run with --force to back up and replace it." >&2
      exit 3
    fi
    backup="${dst}.bak.$(date -u +%Y%m%dT%H%M%SZ)"
    echo "Backing up: $dst -> $backup"
    run cp -p -- "$dst" "$backup"
  fi
  run mkdir -p -- "$parent"
  run cp -- "$src" "$dst"
  echo "Installed: $dst"
}

if [[ "$RUNTIME" == claude || "$RUNTIME" == both ]]; then
  install_file "$PACKAGE_DIR/SKILL.md" "$ROOT/.claude/skills/carl/SKILL.md"
  install_file "$PACKAGE_DIR/commands/carl.md" "$ROOT/.claude/commands/carl.md"
fi
if [[ "$RUNTIME" == codex || "$RUNTIME" == both ]]; then
  install_file "$PACKAGE_DIR/SKILL.md" "$ROOT/.codex/skills/carl/SKILL.md"
fi

printf '
Portable CARL installed. Target: %s (%s). Runtime: %s.
' "$TARGET" "$ROOT" "$RUNTIME"
