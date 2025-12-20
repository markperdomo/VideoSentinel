# VideoSentinel

A Python CLI utility for managing and validating video libraries. Ensures videos are properly encoded to modern specifications, detects duplicates using perceptual hashing, and identifies encoding issues.

## Features

### Core Capabilities
- **Modern Codec Validation & Re-encoding**: Detect and re-encode videos to HEVC/H.265, AV1, or VP9 with smart quality matching
- **Duplicate Detection**: Perceptual hash-based (10-frame comparison) or filename-based (fast alternative)
- **Quality Ranking**: Automatic best-quality selection using codec efficiency, resolution, and bitrate analysis
- **macOS QuickLook Fixes**: Fast remux (MKV→MP4) or re-encode to fix Finder previews
- **Error Recovery**: Salvage corrupted videos with FFmpeg error-tolerant decoding
- **Downscaling**: Reduce videos >1080p while preserving aspect ratio
- **Library Statistics**: Get a breakdown of video codecs and their storage usage with `--stats`
- **Recursive Scanning**: Process directories recursively with `-r` or `--recursive`
- **Corruption Detection**: Identify encoding issues and corrupted files with `--check-issues` and perform a full integrity check with `--deep-scan`

### Performance & Safety
- **Network Queue Mode**: 3-stage pipeline (download→encode→upload) for 2-3x faster encoding on network storage
- **Smart Resume**: Validates existing outputs, skips completed work, survives interruptions
- **Graceful Shutdown**: Press 'q' to stop cleanly after current video
- **Real-time Progress**: Live encoding stats with visual progress bars, speed multiplier, and ETA
- **Output Validation**: Thoroughly validates re-encoded files before replacing originals
- **Batch Control**: Filter by file type (`--file-types`), limit batch size (`--max-files`)
- **Flexible Output Options**: Specify a target codec (`--target-codec`), a custom output directory (`--output-dir`), or replace original files (`--replace-original`)

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
git clone https://github.com/yourusername/VideoSentinel.git
cd VideoSentinel

# Install Python dependencies
pip install -r requirements.txt
```

## Quick Start

### Basic Operations
```bash
# Check encoding specifications
python video_sentinel.py /path/to/videos --check-specs

# Re-encode non-compliant videos to HEVC
python video_sentinel.py /path/to/videos --check-specs --re-encode

# Fix macOS QuickLook/Finder preview issues (fast remux)
python video_sentinel.py /path/to/videos --check-specs --fix-quicklook
```

### Library Statistics
```bash
# Get a breakdown of video codecs and their storage usage
python video_sentinel.py /path/to/videos --stats --recursive
```

### Duplicate Management
```bash
# Find duplicates (perceptual hash-based)
python video_sentinel.py /path/to/videos --find-duplicates

# Auto-delete duplicates, keeping highest quality
python video_sentinel.py /path/to/videos --find-duplicates --duplicate-action auto-best

# Find duplicates by filename only (fast, for broken files)
python video_sentinel.py /path/to/videos --find-duplicates --filename-duplicates
```

### Advanced Encoding
```bash
# Downscale 4K→1080p and replace originals
python video_sentinel.py /path/to/videos --check-specs --re-encode --downscale-1080p --replace-original

# Network storage: 3-stage pipeline for 2-3x speed boost
python video_sentinel.py /Volumes/Network/videos --check-specs --re-encode --queue-mode

# Recover corrupted/broken videos
python video_sentinel.py /path/to/broken --check-specs --re-encode --recover

# Process specific file types only
python video_sentinel.py /path/to/videos --check-specs --file-types wmv,avi,mov

# Limit batch size for testing
python video_sentinel.py /path/to/videos --check-specs --re-encode --max-files 10

# Detect encoding issues
python video_sentinel.py /path/to/videos --check-issues

# Perform a deep scan for corruption (slower)
python video_sentinel.py /path/to/videos --check-issues --deep-scan

# Force remuxing of all MKV files to MP4
python video_sentinel.py /path/to/videos --force-remux-mkv --replace-original
```

See [docs/USAGE.md](docs/USAGE.md) for comprehensive examples and advanced usage.

## How It Works

### Architecture
Modular design with clear separation of concerns:
- **video_analyzer.py**: FFprobe metadata extraction, QuickLook compatibility checking
- **duplicate_detector.py**: 10-frame perceptual hashing, filename matching
- **encoder.py**: Smart CRF calculation, quality-matched re-encoding
- **network_queue_manager.py**: Download→encode→upload pipeline with state persistence
- **shutdown_manager.py**: Thread-safe graceful shutdown (press 'q')
- **stats.py**: Video codec and size statistics
- **issue_detector.py**: Detects encoding issues and corruption

### Key Algorithms
- **Smart Quality Matching**: CRF calculated from source bits-per-pixel and codec efficiency multipliers (AV1: 2.5×, HEVC: 2.0×, H.264: 1.0×)
- **Quality Ranking**: Newly processed files get +50K priority bonus, followed by QuickLook compatibility, container format, codec modernity, resolution, and normalized bitrate
- **Perceptual Hashing**: 10 evenly-spaced frames per video, 12×12 phash, ≤15 Hamming distance threshold
- **Resume Safety**: Validates existing `_reencoded`/`_quicklook` outputs, skips completed work, handles interrupted operations

## Requirements

- **Python 3.7+**
- **FFmpeg** (system dependency - install via brew/apt/choco)
- **Python packages**: opencv-python, imagehash, Pillow, ffmpeg-python, tqdm (see requirements.txt)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Links

- [Detailed Usage Guide](docs/USAGE.md)
- [Architecture Documentation](CLAUDE.md)
- [Issue Tracker](https://github.com/yourusername/VideoSentinel/issues)
