#!/usr/bin/env bash
# Install VideoSentinel zsh completions by sourcing init.zsh from ~/.zshrc.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INIT_FILE="$SCRIPT_DIR/init.zsh"
ZSHRC="${ZDOTDIR:-$HOME}/.zshrc"
MARKER="# >>> VideoSentinel completions >>>"
END_MARKER="# <<< VideoSentinel completions <<<"

if [ ! -f "$INIT_FILE" ]; then
    echo "Error: $INIT_FILE not found" >&2
    exit 1
fi

if [ -f "$ZSHRC" ] && grep -qF "$MARKER" "$ZSHRC"; then
    echo "VideoSentinel completions already registered in $ZSHRC"
    echo "Reload with: source \"$ZSHRC\""
    exit 0
fi

{
    echo ""
    echo "$MARKER"
    echo "source \"$INIT_FILE\""
    echo "$END_MARKER"
} >> "$ZSHRC"

echo "Added VideoSentinel completions to $ZSHRC"
echo "Activate in your current shell with:"
echo "  source \"$ZSHRC\""
