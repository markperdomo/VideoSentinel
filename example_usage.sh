#!/bin/bash
# Example usage of VideoSentinel

# Basic scan of a directory (runs all checks)
python video_sentinel.py /path/to/videos

# Recursive scan with verbose output
python video_sentinel.py /path/to/videos -r -v

# Check only encoding specifications
python video_sentinel.py /path/to/videos --check-specs

# Find duplicate videos only
python video_sentinel.py /path/to/videos --find-duplicates

# Check for encoding issues only (quick scan)
python video_sentinel.py /path/to/videos --check-issues

# Deep scan for corruption (slower, decodes entire videos)
python video_sentinel.py /path/to/videos --check-issues --deep-scan

# Deep scan recursively with verbose output
python video_sentinel.py /path/to/videos -r --check-issues --deep-scan -v

# Check specs and automatically re-encode non-compliant videos
python video_sentinel.py /path/to/videos --check-specs --re-encode

# Re-encode with custom output directory
python video_sentinel.py /path/to/videos --check-specs --re-encode --output-dir /path/to/output

# Re-encode to H.264 instead of HEVC
python video_sentinel.py /path/to/videos --check-specs --re-encode --target-codec h264

# Full scan: check everything recursively
python video_sentinel.py /path/to/videos -r --check-specs --check-issues --find-duplicates -v

# Process only files matching a wildcard pattern (e.g. all .mkv files in a directory)
python video_sentinel.py /path/to/videos/*.mkv --check-specs
