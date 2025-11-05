# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VideoSentinel is a Python CLI utility for managing and validating video libraries. It ensures videos are properly encoded to modern specifications (H.265/HEVC), detects duplicates using perceptual hashing, and identifies encoding issues.

## Essential Commands

### Development Environment Setup
```bash
pip install -r requirements.txt
```

### Running the Application
```bash
# Scan a directory with all checks (default behavior)
python video_sentinel.py /path/to/videos

# Check encoding specifications only
python video_sentinel.py /path/to/videos --check-specs

# Find duplicates using perceptual hashing
python video_sentinel.py /path/to/videos --find-duplicates

# Check for encoding issues
python video_sentinel.py /path/to/videos --check-issues

# Deep scan (decodes entire videos to find corruption - slow)
python video_sentinel.py /path/to/videos --check-issues --deep-scan

# Re-encode non-compliant videos with smart quality matching
python video_sentinel.py /path/to/videos --check-specs --re-encode

# Re-encode only specific file types (great for cleaning up legacy formats)
python video_sentinel.py /path/to/videos --check-specs --re-encode --file-types wmv,avi,mov

# Replace original files with re-encoded versions (deletes source, renames output)
python video_sentinel.py /path/to/videos --check-specs --re-encode --replace-original

# Recursive scan
python video_sentinel.py /path/to/videos -r --check-specs

# Verbose output
python video_sentinel.py /path/to/videos -v
```

### Testing Individual Modules
```bash
# Test video analysis
python -c "from video_analyzer import VideoAnalyzer; from pathlib import Path; a = VideoAnalyzer(verbose=True); print(a.get_video_info(Path('test.mp4')))"

# Test duplicate detection
python -c "from duplicate_detector import DuplicateDetector; from pathlib import Path; d = DuplicateDetector(verbose=True); print(d.get_similarity_score(Path('video1.mp4'), Path('video2.mp4')))"

# Test encoding
python -c "from encoder import VideoEncoder; from pathlib import Path; e = VideoEncoder(verbose=True); e.re_encode_video(Path('input.mp4'), Path('output.mp4'))"
```

## Architecture

### Module Structure

VideoSentinel follows a modular architecture with clear separation of concerns:

**video_sentinel.py** (Main CLI Entry Point)
- Orchestrates all operations via argparse CLI
- Initializes and coordinates all four core modules
- Handles user interaction and progress reporting with tqdm
- No business logic - pure coordination layer

**video_analyzer.py** (Metadata Extraction)
- Uses `ffprobe` to extract video metadata (codec, resolution, bitrate, fps, duration)
- Returns `VideoInfo` dataclass with all video properties
- Determines if videos meet modern specs (HEVC/H.265, AV1, VP9)
- Finds video files by extension in directories

**duplicate_detector.py** (Perceptual Hash Comparison)
- Implements multi-frame perceptual hashing using OpenCV and ImageHash
- Extracts 10 frames evenly distributed throughout each video
- Uses `phash` (perceptual hash) with 12x12 hash size for robustness
- Compares frame-by-frame with threshold of 15 Hamming distance
- Groups duplicates even if they differ in encoding, quality, or resolution

**encoder.py** (Video Re-encoding)
- Re-encodes videos to modern codecs (H.264, HEVC, AV1) using `ffmpeg`
- Implements **smart quality matching**: calculates optimal CRF based on source bits-per-pixel (bpp)
- Quality tiers: high bpp sources get lower CRF (better quality), low bpp sources get higher CRF
- Validates output before considering encoding successful (checks file size, dimensions, duration)
- Automatically cleans up invalid outputs; preserves originals by default
- Resume-safe: validates existing outputs and skips re-encoding if valid

**issue_detector.py** (Problem Detection)
- Quick scan: checks duration, audio presence, unusual specs (dimensions, fps, aspect ratio)
- Deep scan: decodes entire video with `ffmpeg` to find frame-level corruption
- Categorizes issues by severity: critical, warning, info
- Returns `VideoIssue` dataclass with type, severity, and description

### Key Design Patterns

**Dataclasses for Type Safety**
- `VideoInfo` (video_analyzer.py:13-28): Immutable container for video metadata
- `VideoIssue` (issue_detector.py:12-17): Immutable container for detected problems

**Smart Quality Matching Algorithm** (encoder.py:34-119)
The encoder calculates optimal CRF (Constant Rate Factor) based on source quality:
1. Calculates bits per pixel (bpp) = bitrate / (width × height × fps)
2. Maps bpp to quality tier with codec-specific CRF values
3. High bpp (>0.25) → low CRF (18 for HEVC) = preserve high quality
4. Low bpp (<0.05) → high CRF (28 for HEVC) = avoid wasting space

**Multi-Frame Perceptual Hashing** (duplicate_detector.py:135-169)
1. Extracts 10 frames evenly distributed throughout video
2. Computes perceptual hash (phash) for each frame with 12x12 size
3. Compares corresponding frames between videos
4. Averages Hamming distances across all frame pairs
5. Groups videos if average distance ≤ threshold (default 15)

**Output Validation Safety** (encoder.py:256-354)
Before deleting or replacing files, the encoder validates outputs:
1. File exists and size > 1KB
2. `ffprobe` can read the file
3. Has valid video stream with non-zero dimensions
4. Duration matches source within ±2 seconds
5. If validation fails, deletes invalid output and preserves original

**Replace Original Mode** (encoder.py:258-285)
When `--replace-original` flag is used, the encoder:
1. Encodes to temporary output path with `_reencoded` suffix
2. Validates the output thoroughly
3. Only after successful validation:
   - Deletes the original source file
   - Renames output to match original filename (but with proper extension)
4. Example: `video.avi` → encode to `video_reencoded.mp4` → delete `video.avi` → rename to `video.mp4`
5. Extension is determined by target codec (all codecs currently use `.mp4`)

### Dependencies

All video operations depend on **FFmpeg** being installed:
- `ffprobe`: Metadata extraction and validation
- `ffmpeg`: Re-encoding and integrity checks

Python dependencies (requirements.txt):
- **opencv-python**: Frame extraction from videos
- **imagehash**: Perceptual hashing (phash algorithm)
- **Pillow**: Image processing for hashing
- **ffmpeg-python**: FFmpeg wrapper utilities
- **tqdm**: Progress bars for CLI

### Important Implementation Details

**Modern Codec Standards** (video_analyzer.py:38-39)
- Modern: HEVC/H.265, AV1, VP9
- Acceptable: H.264, HEVC, AV1, VP9
- Videos must be in MP4, MKV, Matroska, or WebM containers

**Encoding Presets** (encoder.py:24-29)
- FFmpeg presets: fast, medium, slow, veryslow
- Trade-off between encoding speed and compression efficiency
- Default: medium (balanced)

**macOS QuickLook Compatibility** (encoder.py:203-213)
- HEVC videos use `-tag:v hvc1` (not default `hev1`) for Apple device compatibility
- Forces `-pix_fmt yuv420p` for maximum player compatibility
- Without these parameters, HEVC videos won't preview in macOS Finder/QuickLook

**Codec Mappings** (encoder.py:17-21)
- h264 → libx264 (FFmpeg encoder)
- hevc → libx265 (FFmpeg encoder)
- av1 → libaom-av1 (FFmpeg encoder)

**Video File Extensions** (video_analyzer.py:35)
Supported: .mp4, .mkv, .avi, .mov, .wmv, .flv, .webm, .m4v, .mpg, .mpeg

**Safety Defaults**
- `keep_original=True`: Never deletes originals automatically (unless `--replace-original` is used)
- `replace_original=False`: By default, keeps originals with `_reencoded` suffix
- Output suffix: `_reencoded` to avoid overwriting sources
- Duration tolerance: ±2 seconds when validating re-encoded videos
- Timeout: 300 seconds (5 minutes) for integrity checks
- Files are only deleted after successful encoding and validation

## Common Development Patterns

### Adding New Video Checks

When adding new checks to `issue_detector.py`:
1. Create a new method returning `VideoIssue` or `List[VideoIssue]`
2. Set appropriate severity: 'critical', 'warning', or 'info'
3. Add check to `scan_video()` method (issue_detector.py:304)
4. Use descriptive `issue_type` strings (e.g., 'corruption', 'no_audio')

### Adding New Codecs

To support new codecs in `encoder.py`:
1. Add to `CODEC_MAP` dict (encoder.py:17) with FFmpeg encoder name
2. Add CRF calculation logic in `calculate_optimal_crf()` (encoder.py:34)
3. Add codec-specific parameters in `re_encode_video()` if needed (encoder.py:203-210)

### Modifying Duplicate Detection Sensitivity

Adjust in `DuplicateDetector.__init__()` (duplicate_detector.py:17):
- `threshold`: Lower = stricter matching (fewer false positives, may miss duplicates)
- `num_samples`: More frames = more accurate but slower
- `hash_size`: Larger = more granular but slower

## External System Dependencies

**FFmpeg must be installed:**
- macOS: `brew install ffmpeg`
- Ubuntu/Debian: `sudo apt-get install ffmpeg`
- Windows: `choco install ffmpeg`

The application checks for FFmpeg availability at startup (video_sentinel.py:110-114) and exits if not found.
