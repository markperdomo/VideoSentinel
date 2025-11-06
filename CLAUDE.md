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
# Safe to interrupt and resume - automatically detects completed/partial work
python video_sentinel.py /path/to/videos --check-specs --re-encode --replace-original

# Recursive scan
python video_sentinel.py /path/to/videos -r --check-specs

# Verbose output
python video_sentinel.py /path/to/videos -v

# Find duplicates and automatically keep best quality
python video_sentinel.py /path/to/videos --find-duplicates --duplicate-action auto-best

# Find duplicates and interactively choose what to keep
python video_sentinel.py /path/to/videos --find-duplicates --duplicate-action interactive

# Network queue mode (for network storage - downloads local, encodes fast, uploads back)
python video_sentinel.py /Volumes/NetworkDrive/videos --check-specs --re-encode --queue-mode

# Network queue mode with custom temp dir and settings
python video_sentinel.py /Volumes/NetworkDrive/videos --check-specs --re-encode --queue-mode \
  --temp-dir /Users/you/temp --buffer-size 3 --max-temp-size 100
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

**network_queue_manager.py** (Network Storage Optimization)
- Three-stage pipeline for encoding files on network storage: Download → Encode → Upload
- Download thread pre-fetches files from network to local temp storage
- Encode thread processes files locally at full SSD speed (main thread)
- Upload thread copies completed files back to network in background
- All three stages run in parallel for 2-3x performance improvement
- Smart buffering with configurable buffer size (default: 4 files)
- Storage monitoring pauses downloads if temp size exceeds limit
- State persistence for resume support (survives Ctrl+C interrupts)
- Automatic cleanup of temp files after successful upload
- Handles network filesystem limitations (falls back from copy2 to copy for metadata)

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

**Replace Original Mode with Smart Resume** (encoder.py:234-270, 392-445)
When `--replace-original` flag is used, the encoder:
1. Encodes to temporary output path with `_reencoded` suffix
2. Validates the output thoroughly
3. Only after successful validation:
   - Deletes the original source file
   - Renames output to match original filename (but with proper extension)
4. Example: `video.avi` → encode to `video_reencoded.mp4` → delete `video.avi` → rename to `video.mp4`
5. Extension is determined by target codec (all codecs currently use `.mp4`)

**Smart Resume Support** (encoder.py:234-270):
If the process is interrupted, the encoder intelligently resumes:
1. Checks if a valid `_reencoded` output already exists from previous run
2. If found and valid, skips re-encoding and completes the replacement
3. Detects if replacement was already completed (original deleted, final file exists)
4. Shows "Resuming: video.mp4 (already encoded)" instead of wasting time re-encoding
5. Never re-encodes files that are already successfully encoded
6. Validates outputs before considering them complete to avoid using corrupted partial files

**Real-Time Encoding Progress** (encoder.py:43-87, 296-390)
During video encoding, the encoder displays live progress information with queue position:
1. Shows position in batch: `[1/5] Encoding: video.wmv`
2. Parses FFmpeg's stderr output in real-time using regex patterns
3. Extracts key metrics: frame count, fps (encoding speed), time position, speed multiplier
4. Displays progress inline with carriage returns (overwrites same line)
5. Shows final stats: `✓ [1/5] Completed: video.wmv (avg 45.2 fps, 1.8x speed)`
6. Format: `Encoding: frame=1234 fps=45.2 time=00:01:23.45 speed=1.8x`
7. Error messages also include position: `✗ [1/5] Error encoding video.wmv`

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

**macOS QuickLook Compatibility** (encoder.py:263-290)
- **All output videos use MP4 container** (never preserves source extension like .avi, .wmv)
- **HEVC**: Uses `-tag:v hvc1` (not default `hev1`) for Apple compatibility
- **All codecs**: Forces `-pix_fmt yuv420p` for maximum player compatibility
- **All codecs**: Uses `-movflags faststart` to move metadata to file start for instant QuickLook previews
- Without these parameters, videos may not preview properly in macOS Finder/QuickLook

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

**CLI Flags for New Features**
- `--queue-mode`: Enable network queue mode (download → encode → upload pipeline)
- `--temp-dir PATH`: Temp directory for queue mode (default: system temp)
- `--buffer-size N`: Number of files to buffer in queue mode (default: 4)
- `--max-temp-size GB`: Max temp storage size in GB (default: 50)
- `--duplicate-action {report,interactive,auto-best}`: How to handle duplicates (default: report)

## Usage Tips

### Interrupting and Resuming Batch Encoding

The encoder supports safe interruption and intelligent resume:

**Safe to interrupt at any time:**
- Press Ctrl+C to stop encoding
- No corrupted files will be used (validation ensures integrity)
- Partial encodes are automatically detected and removed

**Automatic resume on restart:**
```bash
# Start batch encoding
python video_sentinel.py /videos --re-encode --replace-original

# Interrupt with Ctrl+C after some files complete

# Resume - automatically skips completed files
python video_sentinel.py /videos --re-encode --replace-original
```

**What happens on resume:**
1. ✓ Detects valid `_reencoded` files from previous run
2. ✓ Skips re-encoding those files (shows "Resuming: file.avi (already encoded)")
3. ✓ Completes any interrupted replacements
4. ✓ Continues encoding remaining files
5. ✓ Validates all outputs before using them

**Resume behavior examples:**
- **Completed encode, not replaced:** Skips encoding, completes replacement
- **Fully completed:** Shows "Replacement already completed, skipping"
- **Partial/corrupted encode:** Deletes invalid file, re-encodes from scratch
- **Never encoded:** Encodes normally

This means you can safely interrupt large batch jobs and resume without wasting work!

### Network Queue Mode for Network Storage

When encoding videos on network drives (NAS, SMB shares, etc.), network I/O significantly slows encoding. Queue mode solves this with a three-stage parallel pipeline:

**How it works:**
```
Thread 1 (Download): Network → Local temp → [buffer] →
Thread 2 (Encode):                          → [buffer] → Encoded local →
Thread 3 (Upload):                                                      → Network
```

**Usage:**
```bash
# Basic queue mode
python video_sentinel.py /Volumes/NetworkDrive/videos --check-specs --re-encode --queue-mode

# With custom temp dir and limits
python video_sentinel.py /Volumes/NetworkDrive/videos --check-specs --re-encode --queue-mode \
  --temp-dir /Users/you/temp --buffer-size 3 --max-temp-size 100
```

**Key features:**
- **Parallel operations**: Download next while encoding current while uploading previous
- **Smart buffering**: Configurable (default 4 files) to balance speed and disk usage
- **Storage monitoring**: Pauses downloads if temp storage exceeds limit
- **Resume support**: Saves state to disk, handles Ctrl+C gracefully
- **Network compatibility**: Falls back from `copy2` to `copy` for filesystems that don't support metadata

**Performance:**
- Traditional (network I/O): ~15-20 fps encoding
- Queue mode (local SSD): ~45-60 fps encoding
- **2-3x speed improvement!**

**Architecture details:**
- Download/upload use separate threads (I/O-bound, benefits from threading)
- Encoding uses main thread (CPU-bound, no threading benefit)
- Queue states: PENDING → DOWNLOADING → LOCAL → ENCODING → UPLOADING → COMPLETE
- State persisted to JSON for resume capability

### Managing Duplicate Videos

VideoSentinel can automatically manage duplicates with `--duplicate-action`:

**Three modes:**

1. **report** (default) - Just list duplicates, no action
2. **auto-best** - Automatically keep highest quality, delete others
3. **interactive** - Ask for each duplicate group

**Quality ranking algorithm** (video_sentinel.py:54-83):
```python
def rank_video_quality(video_path: Path, video_info: VideoInfo) -> int:
    score = 0

    # Codec scoring (modern codecs better)
    codec_scores = {
        'av1': 1000, 'vp9': 900, 'hevc': 800, 'h264': 400,
        'mpeg4': 200, 'mpeg2': 100, 'wmv': 50
    }
    score += codec_scores.get(codec_info.codec.lower(), 0)

    # Resolution scoring
    score += video_info.width * video_info.height // 1000

    # Bitrate scoring
    score += video_info.bitrate // 10000

    return score
```

**Usage examples:**
```bash
# Auto-best: automatically keep best, delete others (asks for confirmation)
python video_sentinel.py ~/Videos --find-duplicates --duplicate-action auto-best

# Interactive: shows ranked list, lets you choose per group
python video_sentinel.py ~/Videos --find-duplicates --duplicate-action interactive
```

**Safety features:**
- Auto-best mode asks "Delete N files? (yes/no)" before deleting
- Interactive mode confirms choice for each group
- Shows space freed after deletion
- Handles deletion errors gracefully

**Implementation location:**
- Ranking logic: `video_sentinel.py:54-83`
- Handler function: `video_sentinel.py:86-179`
- Integration: `video_sentinel.py:530-622`

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
