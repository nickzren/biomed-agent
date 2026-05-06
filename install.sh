#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:---both}"
SKILL_NAME="biomed-research"
SOURCE_DIR="$ROOT/skills/$SKILL_NAME"

usage() {
  cat <<'USAGE'
Install the biomed-research skill for Codex and/or Claude Code.

Usage:
  ./install.sh [--codex|--claude|--both]

Default: --both
USAGE
}

case "$MODE" in
  --both|--codex|--claude) ;;
  -h|--help) usage; exit 0 ;;
  *) echo "Unknown option: $MODE" >&2; usage >&2; exit 2 ;;
esac

install_one() {
  local home_dir="$1" label="$2"
  local target="$home_dir/skills/$SKILL_NAME"
  local stamp

  mkdir -p "$home_dir/skills"
  if [ -L "$target" ] && [ "$(readlink "$target")" = "$SOURCE_DIR" ]; then
    echo "OK $label: $target"
    return
  fi
  if [ -e "$target" ] || [ -L "$target" ]; then
    stamp="$(date +%Y%m%d%H%M%S)"
    mv "$target" "$target.backup.$stamp"
    echo "BACKUP $label: $target.backup.$stamp"
  fi
  ln -s "$SOURCE_DIR" "$target"
  echo "LINK $label: $target -> $SOURCE_DIR"
}

[ -f "$SOURCE_DIR/SKILL.md" ] || { echo "Missing $SOURCE_DIR/SKILL.md" >&2; exit 1; }

if [ "$MODE" = "--both" ] || [ "$MODE" = "--codex" ]; then
  install_one "${CODEX_HOME:-$HOME/.codex}" "Codex"
fi
if [ "$MODE" = "--both" ] || [ "$MODE" = "--claude" ]; then
  install_one "${CLAUDE_HOME:-$HOME/.claude}" "Claude"
fi

echo "Installed $SKILL_NAME. Start a new Codex or Claude Code session."
