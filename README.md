# VideoSentinel

A Python CLI utility that intelligently brings video libraries up to modern standards. VideoSentinel analyzes your collection, re-encodes legacy formats to space-efficient modern codecs, ensures macOS QuickLook compatibility for instant Finder previews, and detects duplicates — all while preserving visual quality through smart bitrate analysis.

The core idea: you shouldn't need to manually audit thousands of video files to figure out which ones are wasting space in ancient codecs, which ones won't preview in Finder, or which ones are duplicates. VideoSentinel handles all of this automatically, with sensible defaults and safety-first design (originals are never deleted unless you explicitly ask).

## Features

### Modernize Your Library
- **Smart Re-encoding**: Automatically identifies videos in legacy codecs (MPEG2, MPEG4, WMV, XviD, etc.) and re-encodes them to HEVC/H.265, AV1, or VP9
- **Quality-Matched Encoding**: Analyzes source bitrate-per-pixel to calculate optimal CRF — high-quality sources get low CRF to preserve detail, low-quality sources get higher CRF to avoid wasting space
- **10-bit HEVC Output**: Encodes to 10-bit color depth (yuv420p10le) by default for better gradient reproduction and less banding at the same file size
- **Downscaling**: Optionally reduce videos larger than 1080p while preserving aspect ratio

### macOS QuickLook Compatibility
- **Instant Finder Previews**: Fixes videos that won't preview in macOS Finder/QuickLook
- **Fast Remux Path**: Videos that just need a container change (MKV to MP4) or HEVC tag fix (hev1 to hvc1) are remuxed in seconds — no re-encoding
- **10-bit HEVC Support**: Correctly identifies 10-bit HEVC as QuickLook-compatible (supported since macOS High Sierra), avoiding unnecessary re-encodes
- **Faststart Metadata**: Adds `-movflags faststart` so previews load instantly without downloading the entire file

### Duplicate Detection
- **Perceptual Hashing**: Compares 10 evenly-spaced frames per video using perceptual hashes — finds duplicates even across different encodings, resolutions, and quality levels
- **Filename Matching**: Fast alternative that groups files by normalized name (strips suffixes like `_reencoded`, `_quicklook`, `_backup`, copy numbering, etc.)
- **Duration Verification**: Filename duplicates are cross-checked by duration to avoid false matches
- **Smart Quality Ranking**: Automatically keeps the best version based on codec efficiency, resolution, container format, and QuickLook compatibility

### Performance
- **Network Queue Mode**: 3-stage pipeline (download → encode → upload) runs all three stages in parallel for 2-3x faster encoding on network/NAS storage
- **Analysis Caching**: Caches ffprobe results to disk so repeat scans are near-instant — handles NAS quirks like mtime changes from media scanners
- **Single-Pass File Discovery**: Scans directories once regardless of how many video extensions are supported (48+)
- **Smart Resume**: Validates existing outputs, skips completed work, and picks up exactly where it left off after interruptions
- **Graceful Shutdown**: Press 'q' to stop cleanly after the current video finishes

### Safety & Control
- **Originals Preserved by Default**: Re-encoded files get a `_reencoded` suffix — originals are only deleted with explicit `--replace-original`
- **Output Validation**: Every re-encoded file is validated (ffprobe readability, dimensions, duration match) before the original is touched
- **Batch Control**: Filter by file type (`--file-types wmv,avi`), limit batch size (`--max-files 10`), or target specific codecs (`--target-codec av1`)
- **Real-time Progress**: Live encoding stats with visual progress bars, speed multiplier, and ETA
- **Error Recovery Mode**: Salvage corrupted videos with FFmpeg error-tolerant decoding flags
- **Timestamp Normalization**: Handles source files with non-standard timebases that would otherwise crash the encoder

## Installation

### Prerequisites

FFmpeg must be installed on your system:

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get install ffmpeg

# Windows
choco install ffmpeg
```

### Install VideoSentinel

```bash
# Clone the repository
git clone https://github.com/markperdomo/VideoSentinel.git
cd VideoSentinel

# Install Python dependencies
pip install -r requirements.txt
```

## Quick Start

### Scan and fix everything in one shot
```bash
# Check what needs updating, re-encode legacy codecs, and fix QuickLook — all at once
python video_sentinel.py /path/to/videos -r --check-specs --re-encode --fix-quicklook --replace-original

# Same thing but on network storage with the fast pipeline
python video_sentinel.py /Volumes/NAS/videos -r --check-specs --re-encode --fix-quicklook --replace-original --queue-mode
```

### Step by step
```bash
# 1. See what you're working with
python video_sentinel.py /path/to/videos -r --stats

# 2. Check which videos need modernizing
python video_sentinel.py /path/to/videos -r --check-specs

# 3. Re-encode non-compliant videos to HEVC (originals kept by default)
python video_sentinel.py /path/to/videos -r --check-specs --re-encode

# 4. Fix QuickLook previews (fast remux for most files)
python video_sentinel.py /path/to/videos -r --fix-quicklook

# 5. Find and clean up duplicates
python video_sentinel.py /path/to/videos -r --find-duplicates --duplicate-action auto-best
```

### Common workflows
```bash
# Process a list of specific files
python video_sentinel.py --file-list /path/to/my_video_list.txt --check-specs --re-encode

# Only process WMV and AVI files
python video_sentinel.py /path/to/videos -r --check-specs --re-encode --file-types wmv,avi

# Test with a small batch first
python video_sentinel.py /path/to/videos -r --check-specs --re-encode --max-files 5

# Downscale 4K to 1080p during re-encode
python video_sentinel.py /path/to/videos -r --check-specs --re-encode --downscale-1080p --replace-original

# Recover corrupted videos
python video_sentinel.py /path/to/broken -r --check-specs --re-encode --recover

# Find duplicates by filename (fast, works with broken files)
python video_sentinel.py /path/to/videos -r --filename-duplicates --duplicate-action auto-best

# Check for encoding issues and corruption
python video_sentinel.py /path/to/videos -r --check-issues --deep-scan

# Monitor a running queue mode session from another terminal
python monitor_queue.py

# Force remux all MKV files to MP4
python video_sentinel.py /path/to/videos -r --force-remux-mkv --replace-original
```

## How It Works

### Smart Quality Matching
VideoSentinel doesn't just blindly re-encode at a fixed quality level. It analyzes each source video's bits-per-pixel (bpp) to determine how much quality headroom the source has, then picks a codec-specific CRF that preserves perceived quality:

| Source Quality | Bits/Pixel | HEVC CRF | AV1 CRF | H.264 CRF |
|----------------|-----------|-----------|---------|------------|
| Very high (4K Bluray) | >0.25 | 18 | 20 | 16 |
| High (good 1080p) | >0.15 | 20 | 24 | 18 |
| Medium | >0.07 | 23 | 30 | 21 |
| Low | <0.05 | 28 | 32 | 26 |

All HEVC output uses 10-bit color depth (yuv420p10le) for better gradient handling at no file size penalty.

### QuickLook Fix Decision Tree
For each video that already uses a modern codec:
1. **Wrong container** (e.g., MKV) or **wrong HEVC tag** (hev1 instead of hvc1) → **Fast remux** (seconds, no quality loss)
2. **Unsupported pixel format** for the codec → **Full re-encode** (only when truly necessary)
3. **10-bit HEVC in MP4 with hvc1 tag** → **Already compatible**, skip

### Architecture
Modular design with clear separation of concerns:
- **video_sentinel.py** — CLI orchestration, no business logic
- **video_analyzer.py** — FFprobe metadata extraction, QuickLook compatibility checking, analysis caching
- **encoder.py** — Smart CRF calculation, quality-matched re-encoding, output validation
- **duplicate_detector.py** — 10-frame perceptual hashing, filename matching with duration verification
- **network_queue_manager.py** — Download → encode → upload pipeline with state persistence
- **issue_detector.py** — Quick and deep corruption scanning
- **shutdown_manager.py** — Thread-safe graceful shutdown (press 'q')
- **stats.py** — Codec distribution and storage usage statistics
- **monitor_queue.py** — Standalone queue monitoring utility

### Tdarr Integration
Two JavaScript plugins bring VideoSentinel's encoding logic to the Tdarr distributed transcoding framework:
- **Tdarr_Plugin_MC93_Migz1FFMPEG_CPU_modified.js** — Bitrate-based HEVC transcode with Apple compatibility
- **Tdarr_Plugin_vsAIQ.js** — VideoSentinel's smart CRF quality algorithm as a Tdarr plugin

## Requirements

- **Python 3.7+**
- **FFmpeg** (system dependency — install via brew/apt/choco)
- **Python packages**: opencv-python, imagehash, Pillow, ffmpeg-python, tqdm (see requirements.txt)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Links

- [Detailed Usage Guide](docs/USAGE.md)
- [Architecture Documentation](CLAUDE.md)
- [Issue Tracker](https://github.com/markperdomo/VideoSentinel/issues)
