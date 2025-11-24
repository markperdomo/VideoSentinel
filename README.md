# VideoSentinel

A powerful Python CLI utility for managing and validating video libraries. VideoSentinel ensures your videos are properly encoded to modern specifications, detects duplicates using perceptual hashing, and identifies encoding issues.

## Features

- **Modern Codec Validation**: Ensures videos use modern codecs (HEVC/H.265, AV1, VP9)
- **Smart Re-encoding**: Automatically re-encodes non-compliant videos with quality matching
- **Duplicate Detection**:
  - Perceptual hash-based detection (finds duplicates even with different encodings)
  - Filename-based detection (fast alternative)
  - Automatic or interactive duplicate management
- **Error Recovery**: Salvage broken or corrupted videos with FFmpeg's error recovery mode
- **Network Queue Mode**: 2-3x faster encoding on network storage with parallel download/encode/upload pipeline
- **macOS QuickLook Fixes**: Automatically fix videos that won't preview in Finder
- **Downscaling**: Reduce 4K videos to 1080p for space savings
- **Resume Support**: Safe interruption and intelligent resume for all operations
- **Graceful Shutdown**: Press 'q' to stop cleanly after current video completes

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

```bash
# Check encoding specifications
python video_sentinel.py /path/to/videos --check-specs

# Find duplicates using perceptual hashing
python video_sentinel.py /path/to/videos --find-duplicates

# Re-encode non-compliant videos
python video_sentinel.py /path/to/videos --check-specs --re-encode

# Fix QuickLook compatibility (fast remux)
python video_sentinel.py /path/to/videos --check-specs --fix-quicklook

# Downscale 4K videos to 1080p and replace originals
python video_sentinel.py /path/to/videos --check-specs --re-encode --downscale-1080p --replace-original

# Network queue mode for fast encoding on network storage
python video_sentinel.py /Volumes/NetworkDrive/videos --check-specs --re-encode --queue-mode

# Find and automatically keep best quality duplicates
python video_sentinel.py /path/to/videos --find-duplicates --duplicate-action auto-best

# Recover broken/corrupted videos
python video_sentinel.py /path/to/broken_videos --check-specs --re-encode --recover

# Process only specific file types
python video_sentinel.py /path/to/videos --check-specs --re-encode --file-types wmv,avi,mov

# Process files matching a wildcard pattern (e.g., all MKV files)
python video_sentinel.py /path/to/videos/*.mkv --check-specs
```

For comprehensive usage examples and detailed documentation, see [docs/USAGE.md](docs/USAGE.md).

## Architecture Overview

VideoSentinel uses a modular architecture with clear separation of concerns:

- **video_sentinel.py**: Main CLI entry point, orchestrates all operations
- **video_analyzer.py**: Metadata extraction using ffprobe, QuickLook compatibility checking
- **duplicate_detector.py**: Perceptual hash-based and filename-based duplicate detection
- **encoder.py**: Smart quality-matching re-encoding with FFmpeg
- **issue_detector.py**: Quick and deep video integrity scanning
- **network_queue_manager.py**: Three-stage pipeline for network storage optimization
- **shutdown_manager.py**: Thread-safe graceful shutdown management

## Key Design Features

- **Smart Quality Matching**: Calculates optimal CRF based on source video quality (bits-per-pixel)
- **Multi-Frame Perceptual Hashing**: Extracts 10 frames per video for robust duplicate detection
- **Output Validation**: Thoroughly validates all re-encoded files before replacing originals
- **Resume Safety**: Automatically detects and skips completed work when interrupted
- **Real-Time Progress**: Live encoding progress with visual progress bars, speed, and ETA
- **Graceful Shutdown**: Press 'q' to stop cleanly after current video

## Requirements

- Python 3.7+
- FFmpeg (for video processing)
- opencv-python (for frame extraction)
- imagehash (for perceptual hashing)
- Pillow (for image processing)
- ffmpeg-python (FFmpeg wrapper)
- tqdm (progress bars)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Links

- [Detailed Usage Guide](docs/USAGE.md)
- [Architecture Documentation](CLAUDE.md)
- [Issue Tracker](https://github.com/yourusername/VideoSentinel/issues)
