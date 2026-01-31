#!/bin/sh
# Встановити git hooks (перевірка секретів перед push)
HOOKS_DIR="$(cd "$(dirname "$0")/.." && pwd)/.git/hooks"
SRC="$(cd "$(dirname "$0")" && pwd)/git-hooks/pre-push"
if [ -d "$(dirname "$HOOKS_DIR")" ]; then
  cp "$SRC" "$HOOKS_DIR/pre-push"
  chmod +x "$HOOKS_DIR/pre-push"
  echo "Hooks installed: .git/hooks/pre-push"
else
  echo "Not a git repo"
  exit 1
fi
