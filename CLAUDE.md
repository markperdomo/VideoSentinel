# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VideoSentinel is a Python CLI utility for managing and validating video libraries. It ensures videos are properly encoded to modern specifications (H.265/HEVC), detects duplicates using perceptual hashing, and identifies encoding issues.

Key features:
- Video encoding validation and re-encoding to modern codecs (HEVC, AV1, VP9)
- Perceptual hash-based duplicate detection
- Filename-based duplicate detection (fast alternative)
- Error recovery mode for corrupted videos
- Network queue mode for optimal encoding on network storage
- macOS QuickLook compatibility fixes
- Graceful shutdown and resume support

## Architecture

### Module Structure

VideoSentinel follows a modular architecture with clear separation of concerns:

**video_sentinel.py** (Main CLI Entry Point)
- Orchestrates all operations via argparse CLI
- Initializes and coordinates all core modules
- Handles user interaction and progress reporting with tqdm
- No business logic - pure coordination layer

**video_analyzer.py** (Metadata Extraction)
- Uses `ffprobe` to extract video metadata (codec, resolution, bitrate, fps, duration)
- Returns `VideoInfo` dataclass with all video properties
- Determines if videos meet modern specs (HEVC/H.265, AV1, VP9)
- Finds video files by extension in directories
- QuickLook compatibility checking

**duplicate_detector.py** (Perceptual Hash Comparison & Filename Matching)
- Implements multi-frame perceptual hashing using OpenCV and ImageHash
- Extracts 10 frames evenly distributed throughout each video
- Uses `phash` (perceptual hash) with 12x12 hash size for robustness
- Compares frame-by-frame with threshold of 15 Hamming distance
- Groups duplicates even if they differ in encoding, quality, or resolution
- Also provides filename-based duplicate detection (fast alternative)
  - Normalizes filenames by removing `_reencoded` and `_quicklook` suffixes
  - Case-insensitive matching
  - Groups files with same base name regardless of extension
  - Useful when broken files can't generate perceptual hashes

**encoder.py** (Video Re-encoding)
- Re-encodes videos to modern codecs (H.264, HEVC, AV1) using `ffmpeg`
- Implements **smart quality matching**: calculates optimal CRF based on source bits-per-pixel (bpp)
- Quality tiers: high bpp sources get lower CRF (better quality), low bpp sources get higher CRF
- Validates output before considering encoding successful (checks file size, dimensions, duration)
- Automatically cleans up invalid outputs; preserves originals by default
- Resume-safe: validates existing outputs and skips re-encoding if valid
- Fast remux capability for QuickLook fixes

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
- Resume State Validation:
  - Validates temp files still exist when resuming
  - Re-downloads if temp files missing
  - Shows detailed resume summary with file state breakdown

**shutdown_manager.py** (Graceful Shutdown Control)
- Provides thread-safe graceful shutdown mechanism during batch operations
- Background daemon thread monitors for 'q' key press
- Uses platform-specific input methods: `select()` on Unix, blocking input on Windows
- Sets terminal to raw mode on Unix for immediate key detection (no Enter needed)
- Thread-safe shutdown flag protected by locks for concurrent access
- Singleton pattern with global instance for easy access across modules
- Automatically stops listener threads when operations complete
- No external dependencies beyond Python standard library

**monitor_queue.py** (Queue Monitoring Utility)
- Standalone CLI utility for monitoring network queue mode operations
- Reads queue state file to display current status (pending, downloading, encoding, uploading, complete, failed)
- Shows failed files with detailed error messages
- Displays temp directory size and contents
- Provides file-by-file status breakdown
- Can filter to show only failed files with `--failed-only` flag
- Useful for monitoring long-running queue mode sessions in a separate terminal

### Key Design Patterns

**Dataclasses for Type Safety**
- `VideoInfo`: Immutable container for video metadata
- `VideoIssue`: Immutable container for detected problems

**Smart Quality Matching Algorithm**
The encoder calculates optimal CRF (Constant Rate Factor) based on source quality:
1. Calculates bits per pixel (bpp) = bitrate / (width × height × fps)
2. Maps bpp to quality tier with codec-specific CRF values
3. High bpp (>0.25) → low CRF (18 for HEVC) = preserve high quality
4. Low bpp (<0.05) → high CRF (28 for HEVC) = avoid wasting space

**Multi-Frame Perceptual Hashing**
1. Extracts 10 frames evenly distributed throughout video
2. Computes perceptual hash (phash) for each frame with 12x12 size
3. Compares corresponding frames between videos
4. Averages Hamming distances across all frame pairs
5. Groups videos if average distance ≤ threshold (default 15)

**Output Validation Safety**
Before deleting or replacing files, the encoder validates outputs:
1. File exists and size > 1KB
2. `ffprobe` can read the file
3. Has valid video stream with non-zero dimensions
4. Duration matches source within ±2 seconds
5. If validation fails, deletes invalid output and preserves original

**Replace Original Mode with Smart Resume**
When `--replace-original` flag is used, the encoder:
1. Encodes to temporary output path with `_reencoded` suffix
2. Validates the output thoroughly
3. Only after successful validation:
   - Deletes the original source file
   - Renames output to match original filename (but with proper extension)
4. Example: `video.avi` → encode to `video_reencoded.mp4` → delete `video.avi` → rename to `video.mp4`
5. Extension is determined by target codec (all codecs currently use `.mp4`)

**Smart Resume Support**:
If the process is interrupted, the encoder intelligently resumes:
1. Checks if a valid `_reencoded` output already exists from previous run
2. If found and valid, skips re-encoding and completes the replacement
3. Detects if replacement was already completed (original deleted, final file exists)
4. Shows "Resuming: video.mp4 (already encoded)" instead of wasting time re-encoding
5. Never re-encodes files that are already successfully encoded
6. Validates outputs before considering them complete to avoid using corrupted partial files

**Real-Time Encoding Progress**
During video encoding, the encoder displays live visual progress with queue position:
1. Shows position in batch: `[1/5] Encoding: video.wmv`
2. Parses FFmpeg's stderr output in real-time using regex patterns
3. Extracts key metrics: frame count, fps (encoding speed), time position, speed multiplier
4. Calculates percentage based on current time vs total video duration
5. Displays visual progress bar with percentage, speed, and ETA
6. Format: `[████████████████████░░░░░] 80.0% | 5.58x speed | ETA: 2m 15s`
7. Updates inline with carriage returns (overwrites same line)
8. Shows final stats: `✓ [1/5] Completed: video.wmv (avg 45.2 fps, 1.8x speed)`
9. Error messages also include position: `✗ [1/5] Error encoding video.wmv`

**Progress Bar Features:**
- Visual bar (25 chars wide) using █ (filled) and ░ (empty) characters
- Percentage shows exact completion (e.g., 80.0%)
- Speed multiplier shows encoding efficiency (e.g., 5.58x = encoding 5.58× faster than real-time)
- ETA calculated from remaining duration and current speed (e.g., "2m 15s", "1h 5m")
- Automatically falls back to time-based display if video duration unavailable

**Graceful Shutdown Manager** (shutdown_manager.py)
Provides thread-safe graceful shutdown during batch encoding operations:
1. Background thread monitors for 'q' key press using platform-specific input methods
2. Uses `select()` on Unix-like systems (macOS/Linux) for non-blocking input detection
3. Falls back to simpler blocking approach on Windows or when raw mode unavailable
4. Sets thread-safe shutdown flag when key is detected
5. Encoding loops check flag between videos and exit gracefully after current video
6. Automatically cleans up listener threads when encoding completes
7. Works in both batch encoding mode and queue mode
8. Implementation: Singleton pattern with `get_shutdown_manager()` for global access

### Important Implementation Details

**Modern Codec Standards**
- Modern: HEVC/H.265, AV1, VP9
- Acceptable: H.264, HEVC, AV1, VP9
- Videos must be in MP4, MKV, Matroska, or WebM containers

**Encoding Presets**
- FFmpeg presets: fast, medium, slow, veryslow
- Trade-off between encoding speed and compression efficiency
- Default: medium (balanced)

**macOS QuickLook Compatibility**
- **All output videos use MP4 container** (never preserves source extension like .avi, .wmv)
- **HEVC**: Uses `-tag:v hvc1` (not default `hev1`) for Apple compatibility
- **All codecs**: Forces `-pix_fmt yuv420p` for maximum player compatibility
- **All codecs**: Uses `-movflags faststart` to move metadata to file start for instant QuickLook previews
- Without these parameters, videos may not preview properly in macOS Finder/QuickLook

**Codec Mappings**
- h264 → libx264 (FFmpeg encoder)
- hevc → libx265 (FFmpeg encoder)
- av1 → libaom-av1 (FFmpeg encoder)

**Video File Extensions**
Supported: 40+ video formats including:
- Modern: .mp4, .mkv, .webm, .m4v, .mov
- Legacy: .avi, .wmv, .asf, .divx
- MPEG: .mpg, .mpeg, .mpe, .mpv, .m2v, .mp2
- Flash: .flv, .f4v, .f4p, .f4a, .f4b
- Mobile: .3gp, .3g2
- Broadcast: .mts, .m2ts, .ts, .mxf, .vob, .dv
- Open: .ogv, .ogg, .ogm
- RealMedia: .rm, .rmvb
- QuickTime: .qt, .mqv
- Other: .gif, .gifv, .yuv, .drc, .mng, .nsv, .roq, .svi, .dat, .vid, .movie, .amv, .xvid

**Safety Defaults**
- `keep_original=True`: Never deletes originals automatically (unless `--replace-original` is used)
- `replace_original=False`: By default, keeps originals with `_reencoded` suffix
- Output suffix: `_reencoded` to avoid overwriting sources
- Duration tolerance: ±2 seconds when validating re-encoded videos
- Timeout: 300 seconds (5 minutes) for integrity checks
- Files are only deleted after successful encoding and validation

**Smart Output Detection**
Before re-encoding, checks for existing valid outputs:
- Looks for files with `_reencoded` or `_quicklook` suffixes matching the source filename
- Validates outputs using same checks as post-encoding validation:
  - File exists and size > 1KB
  - ffprobe can read the file
  - Has valid video stream with non-zero dimensions
  - Duration matches expected values (if source info available)
- Deletes invalid/corrupted existing outputs
- Skips encoding if valid output already exists
- Implementation: `find_existing_output()` method with configurable suffix list
- Used in main CLI to pre-check before batch encoding

**Duplicate Filename Cleanup**
After deleting duplicates (auto-best or interactive mode):
- Removes `_reencoded` suffix from kept files
- Removes `_quicklook` suffix from kept files
- Only renames if target filename doesn't already exist
- Preserves file organization without suffix clutter
- Example: `video_reencoded.mp4` (kept) → `video.mp4` after deleting `video.mp4` (duplicate)
- Shows progress: `✓ Renamed: video_reencoded.mp4 → video.mp4`
- Handles errors gracefully (skips if target exists, shows error if rename fails)

**Quality Ranking with Codec Efficiency**
Duplicate quality ranking uses comprehensive scoring to prioritize the best file:

**Ranking factors (in priority order):**
1. **Newly processed files (HIGHEST PRIORITY)**: +50,000 points for files with `_quicklook` or `_reencoded` suffixes
   - Massive bonus ensures newly processed files ALWAYS beat originals
   - Even 1080p re-encode beats 4K original (intentional design)
   - Prevents accidentally deleting your explicitly created files
2. **QuickLook compatibility**: +5,000 points for macOS QuickLook/Finder preview compatibility
3. **Container format**: MP4/M4V (+300), MKV/WebM (+100), others (0)
4. **Codec modernity**: AV1 (1000), VP9 (900), HEVC/HVC1 (800), H.264 (400), MPEG4 (200), MPEG2/WMV (50-100)
5. **Resolution**: Width × height / 1000
6. **Normalized bitrate**: Bitrate adjusted by codec efficiency / 10000

**Codec efficiency multipliers:**
- AV1: 2.5× (e.g., 2000 kbps → 5000 kbps H.264 equivalent)
- HEVC/VP9/HVC1: 2.0× (e.g., 3000 kbps → 6000 kbps H.264 equivalent)
- H.264/AVC1: 1.0× baseline
- MPEG4/XviD: 0.6× (less efficient than H.264)
- MPEG2/WMV: 0.4-0.5× (much less efficient)

**Why this works:**
- **Newly processed files get absolute priority** - the +50,000 bonus is intentionally massive to ensure your explicitly created files (downscaled, re-encoded, remuxed) are never accidentally deleted in favor of originals
- QuickLook-compatible files strongly preferred (critical for macOS users)
- MP4 container preferred over MKV for universal compatibility
- Modern codec re-encodes rank higher than originals even at lower bitrate
- Examples:
  - `movie_reencoded.mp4` (1080p, 3000 kbps) beats `movie.mkv` (4K, 10000 kbps) ← intentional!
  - `movie_quicklook.mp4` (HVC1, 3000 kbps, MP4) beats `movie.mkv` (HEVC, 3500 kbps, MKV)

**CLI Flags Reference**

**Core Operations**
- `--check-specs`: Check if videos meet modern encoding specifications (HEVC/H.265, AV1, VP9)
- `--find-duplicates`: Find duplicate videos using perceptual hashing (10-frame comparison)
- `--re-encode`: Automatically re-encode videos that don't meet modern specs
- `--fix-quicklook`: Fix QuickLook compatibility (remux MKV→MP4, fix HEVC tags, re-encode if needed)
- `--check-issues`: Detect encoding issues and corrupted files (quick scan)

**Encoding Options**
- `--target-codec {h264,hevc,av1}`: Target codec for re-encoding (default: hevc)
- `--downscale-1080p`: Downscale videos larger than 1080p to 1920x1080 while preserving aspect ratio
  - Uses two-stage FFmpeg scale filter for proper dimension handling
  - Only scales down, never upscales (videos ≤1080p are unchanged)
- `--recover`: Enable error recovery mode during re-encoding
  - Uses FFmpeg error-tolerant flags to salvage broken/corrupted videos
  - Input flags: `-err_detect ignore_err`, `-fflags +genpts+discardcorrupt+igndts`, `-ignore_unknown`
  - Output flags: `-max_muxing_queue_size 1024`, `-max_error_rate 1.0`
- `--replace-original`: Replace original files with re-encoded versions (deletes source, renames output)
- `--output-dir PATH`: Custom directory for re-encoded videos (default: same as source with `_reencoded` suffix)

**Duplicate Management**
- `--filename-duplicates`: Find duplicates by filename only (fast, no perceptual hashing)
  - Matches files with same name ignoring extension and `_reencoded`/`_quicklook` suffixes
  - Useful when original files are broken and can't generate perceptual hashes
- `--duplicate-action {report,interactive,auto-best}`: How to handle duplicates (default: report)
  - `report`: Only report duplicates, no action
  - `interactive`: Ask user for each duplicate group
  - `auto-best`: Automatically keep best quality, delete others

**Issue Detection**
- `--check-issues`: Detect encoding issues and corrupted files (quick scan)
- `--deep-scan`: Perform deep integrity check (slower, decodes entire video to find frame-level corruption)

**Network Queue Mode**
- `--queue-mode`: Enable network queue mode (3-stage download → encode → upload pipeline for 2-3x speed)
- `--temp-dir PATH`: Custom temporary directory for queue mode (default: system temp)
- `--max-temp-size GB`: Maximum temp storage size in GB for queue mode (default: 50)
- `--buffer-size N`: Number of files to buffer locally in queue mode (default: 4)
- `--clear-queue`: Clear queue state and temp files from previous queue mode session

**Filtering & Batch Control**
- `--file-types TYPES`: Comma-separated file extensions to process (e.g., `wmv,avi,mov`)
  - Filters files at discovery stage (applies to all operations)
  - More efficient than scanning all files then filtering later
- `--max-files N`: Limit processing to first N files found (e.g., `--max-files 100`)
  - **Smart re-encoding**: With `--re-encode`, stops analyzing early once enough non-compliant files are found (2x buffer), then filters to N files needing encoding
  - **Standard mode**: For other operations, limits to first N files discovered
  - Perfect for manageable batches, testing, or incremental processing on large libraries
- `-r`, `--recursive`: Recursively scan subdirectories

**General Options**
- `-v`, `--verbose`: Enable verbose output for debugging

## Common Development Patterns

### Adding New Video Checks

When adding new checks to `issue_detector.py`:
1. Create a new method returning `VideoIssue` or `List[VideoIssue]`
2. Set appropriate severity: 'critical', 'warning', or 'info'
3. Add check to `scan_video()` method
4. Use descriptive `issue_type` strings (e.g., 'corruption', 'no_audio')

### Adding New Codecs

To support new codecs in `encoder.py`:
1. Add to `CODEC_MAP` dict with FFmpeg encoder name
2. Add CRF calculation logic in `calculate_optimal_crf()` method
3. Add codec-specific parameters in `re_encode_video()` method if needed

### Modifying Duplicate Detection Sensitivity

Adjust in `DuplicateDetector.__init__()`:
- `threshold`: Lower = stricter matching (fewer false positives, may miss duplicates)
- `num_samples`: More frames = more accurate but slower
- `hash_size`: Larger = more granular but slower

## Dependencies

### External System Dependencies

**FFmpeg must be installed:**
- macOS: `brew install ffmpeg`
- Ubuntu/Debian: `sudo apt-get install ffmpeg`
- Windows: `choco install ffmpeg`

The application checks for FFmpeg availability at startup and exits if not found.

### Python Dependencies

All video operations depend on **FFmpeg** being installed:
- `ffprobe`: Metadata extraction and validation
- `ffmpeg`: Re-encoding and integrity checks

Python dependencies (requirements.txt):
- **opencv-python**: Frame extraction from videos
- **imagehash**: Perceptual hashing (phash algorithm)
- **Pillow**: Image processing for hashing
- **ffmpeg-python**: FFmpeg wrapper utilities
- **tqdm**: Progress bars for CLI

## Testing Individual Modules

```bash
# Test video analysis
python -c "from video_analyzer import VideoAnalyzer; from pathlib import Path; a = VideoAnalyzer(verbose=True); print(a.get_video_info(Path('test.mp4')))"

# Test duplicate detection
python -c "from duplicate_detector import DuplicateDetector; from pathlib import Path; d = DuplicateDetector(verbose=True); print(d.get_similarity_score(Path('video1.mp4'), Path('video2.mp4')))"

# Test encoding
python -c "from encoder import VideoEncoder; from pathlib import Path; e = VideoEncoder(verbose=True); e.re_encode_video(Path('input.mp4'), Path('output.mp4'))"
```
