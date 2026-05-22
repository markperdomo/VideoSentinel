#!/usr/bin/env bash
# Shortcut: re-encode Archive videos in queue mode with replacement
set -euo pipefail

cd "$(dirname "$0")"

source venv/bin/activate

# video_sentinel.py holds its own host-wide process lock and exits 75 if
# another run is already active. Treat that as a clean "skipped" so this
# scheduled routine doesn't log it as a failure.
./video_sentinel.py \
  /Volumes/Archive/Favs \
  /Volumes/Archive/Sites \
  -r \
  --re-encode \
  --queue-mode \
  -j 2 \
  --replace-original \
  || {
    status=$?
    if [ "$status" -eq 75 ]; then
      echo "Another VideoSentinel session is already running — skipping."
      exit 0
    fi
    exit "$status"
  }
