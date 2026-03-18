#!/usr/bin/env bash
# Sets the GitHub repository description and topics.
# Requires: gh CLI (https://cli.github.com/) authenticated with repo admin access.
#
# Usage: .github/setup-repo-metadata.sh

set -euo pipefail

REPO="markperdomo/VideoSentinel"

DESCRIPTION="Python CLI for managing video libraries — smart re-encoding to modern codecs (HEVC/AV1/VP9), perceptual hash duplicate detection, macOS QuickLook fixes, and network queue mode"

HOMEPAGE="https://github.com/markperdomo/VideoSentinel"

echo "Setting repository description..."
gh repo edit "$REPO" \
  --description "$DESCRIPTION" \
  --homepage "$HOMEPAGE"

echo "Setting repository topics..."
gh repo edit "$REPO" \
  --add-topic video \
  --add-topic ffmpeg \
  --add-topic hevc \
  --add-topic video-encoding \
  --add-topic duplicate-detection \
  --add-topic cli \
  --add-topic python \
  --add-topic macos-quicklook \
  --add-topic video-management \
  --add-topic perceptual-hashing

echo "Done! Repository metadata updated."
