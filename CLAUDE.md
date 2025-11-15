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

# Find duplicates by filename only (fast, no perceptual hashing)
# Matches files with same name ignoring extension and _reencoded/_quicklook suffixes
# Useful when original files are broken and can't generate perceptual hashes
python video_sentinel.py /path/to/videos --filename-duplicates

# Check for encoding issues
python video_sentinel.py /path/to/videos --check-issues

# Deep scan (decodes entire videos to find corruption - slow)
python video_sentinel.py /path/to/videos --check-issues --deep-scan

# Re-encode non-compliant videos with smart quality matching
python video_sentinel.py /path/to/videos --check-specs --re-encode

# Re-encode with error recovery mode (salvage broken/corrupted files)
python video_sentinel.py /path/to/videos --check-specs --re-encode --recover

# Process only specific file types (filters at file discovery - applies to all operations)
python video_sentinel.py /path/to/videos --check-specs --re-encode --file-types wmv,avi,mov

# Find duplicates only among AVI files
python video_sentinel.py /path/to/videos --find-duplicates --file-types avi

# Check issues only for WMV and FLV files
python video_sentinel.py /path/to/videos --check-issues --file-types wmv,flv

# Replace original files with re-encoded versions (deletes source, renames output)
# Safe to interrupt and resume - automatically detects completed/partial work
python video_sentinel.py /path/to/videos --check-specs --re-encode --replace-original

# Recursive scan
python video_sentinel.py /path/to/videos -r --check-specs

# Verbose output (shows all FFmpeg output, useful for debugging)
python video_sentinel.py /path/to/videos -v

# Find duplicates and automatically keep best quality
python video_sentinel.py /path/to/videos --find-duplicates --duplicate-action auto-best

# Find duplicates and interactively choose what to keep
python video_sentinel.py /path/to/videos --find-duplicates --duplicate-action interactive

# Find filename duplicates and auto-keep best (fast, works with broken originals)
python video_sentinel.py /path/to/videos --filename-duplicates --duplicate-action auto-best

# Fix QuickLook compatibility (fast remux MKV→MP4, fix HEVC tags)
python video_sentinel.py /path/to/videos --check-specs --fix-quicklook

# Fix QuickLook compatibility and replace originals
python video_sentinel.py /path/to/videos --check-specs --fix-quicklook --replace-original

# Network queue mode (for network storage - downloads local, encodes fast, uploads back)
python video_sentinel.py /Volumes/NetworkDrive/videos --check-specs --re-encode --queue-mode

# Network queue mode with custom temp dir and settings
python video_sentinel.py /Volumes/NetworkDrive/videos --check-specs --re-encode --queue-mode \
  --temp-dir /Users/you/temp --buffer-size 3 --max-temp-size 100

# Clear queue state and temp files
python video_sentinel.py --clear-queue

# Monitor queue mode status (during or after encoding)
python monitor_queue.py

# Monitor with custom temp dir
python monitor_queue.py --temp-dir /Users/you/temp
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
- **Resume State Validation** (network_queue_manager.py:458-540):
  - When resuming from saved state, validates temp files still exist
  - Checks if local downloads still exist in temp dir
  - Checks if encoded outputs still exist
  - Automatically re-downloads if temp files missing
  - Shows detailed resume summary with file state breakdown:
    - Already complete (skip)
    - Previously failed (skip)
    - Resuming upload (output exists)
    - Resuming encoding (local file exists)
    - Re-encoding (interrupted, local file exists)
    - Pending download (not started)
    - Re-downloading (temp files missing)

**shutdown_manager.py** (Graceful Shutdown Control)
- Provides thread-safe graceful shutdown mechanism during batch operations
- Background daemon thread monitors for 'q' key press
- Uses platform-specific input methods: `select()` on Unix, blocking input on Windows
- Sets terminal to raw mode on Unix for immediate key detection (no Enter needed)
- Thread-safe shutdown flag protected by locks for concurrent access
- Singleton pattern with global instance for easy access across modules
- Automatically stops listener threads when operations complete
- No external dependencies beyond Python standard library

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

**Real-Time Encoding Progress** (encoder.py:45-147, 455-490)
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

**Smart Output Detection** (encoder.py:703-745)
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
- Used in video_sentinel.py:447-461 to pre-check before batch encoding

**Duplicate Filename Cleanup** (video_sentinel.py:816-849)
After deleting duplicates (auto-best or interactive mode):
- Removes `_reencoded` suffix from kept files
- Removes `_quicklook` suffix from kept files
- Only renames if target filename doesn't already exist
- Preserves file organization without suffix clutter
- Example: `video_reencoded.mp4` (kept) → `video.mp4` after deleting `video.mp4` (duplicate)
- Shows progress: `✓ Renamed: video_reencoded.mp4 → video.mp4`
- Handles errors gracefully (skips if target exists, shows error if rename fails)

**Quality Ranking with Codec Efficiency** (video_sentinel.py:55-132)
Duplicate quality ranking uses comprehensive scoring to prioritize the best file:

**Ranking factors (in priority order):**
1. **QuickLook compatibility**: +1500 points for macOS QuickLook/Finder preview compatibility
2. **Newly processed files**: +1000 points for files with `_quicklook` or `_reencoded` suffixes
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
- Ensures QuickLook-compatible files are always preferred (critical for macOS users)
- Newly processed files rank higher than originals (avoids deleting fresh encodes)
- MP4 container preferred over MKV for universal compatibility
- Modern codec re-encodes rank higher than originals even at lower bitrate
- Example: `movie_quicklook.mp4` (HVC1, 3000 kbps, MP4) beats `movie.mkv` (HEVC, 3500 kbps, MKV)

**CLI Flags for New Features**
- `--file-types TYPES`: Comma-separated file extensions to process (e.g., `wmv,avi,mov`)
  - Filters files at discovery stage (applies to all operations: check-specs, duplicates, issues, re-encode)
  - More efficient than scanning all files then filtering later
  - Only files matching specified extensions are loaded, analyzed, and processed
- `--filename-duplicates`: Find duplicates by filename only (fast, no perceptual hashing)
  - Matches files with same name ignoring extension and `_reencoded`/`_quicklook` suffixes
  - Much faster than `--find-duplicates` (no video analysis required)
  - Useful when original files are broken and can't generate perceptual hashes
  - Example: groups `video.avi`, `video_reencoded.mp4`, `video.mkv` as duplicates
- `--recover`: Enable error recovery mode during re-encoding
  - Uses FFmpeg error-tolerant flags to salvage broken/corrupted videos
  - Input flags (before `-i`): `-err_detect ignore_err`, `-fflags +genpts+discardcorrupt+igndts`, `-ignore_unknown`
  - Output flags (after `-i`): `-max_muxing_queue_size 1024`, `-max_error_rate 1.0`
  - Ignores decoding errors, generates missing timestamps, discards corrupted packets
  - Useful for recovering videos that won't play or fail to encode normally
  - Combined with `--re-encode` flag
- `--fix-quicklook`: Fix QuickLook compatibility (remux MKV→MP4, fix HEVC tags, re-encode if needed)
- `--queue-mode`: Enable network queue mode (download → encode → upload pipeline)
- `--temp-dir PATH`: Temp directory for queue mode (default: system temp)
- `--buffer-size N`: Number of files to buffer in queue mode (default: 4)
- `--max-temp-size GB`: Max temp storage size in GB (default: 50)
- `--clear-queue`: Clear queue state and temp files from previous queue mode session
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

### Graceful Shutdown with Key Press

For more controlled shutdown during batch encoding, VideoSentinel supports graceful shutdown by pressing the 'q' key:

**How it works:**
- Press the `q` key at any time during encoding
- VideoSentinel will finish the current video, then stop
- Progress is saved automatically (same as Ctrl+C)
- Next run will resume from where you left off

**Usage:**
```bash
# Start batch encoding
python video_sentinel.py /videos --re-encode --replace-original

# During encoding, press 'q' to stop gracefully
# The current video will finish encoding, then the process stops
```

**Key differences from Ctrl+C:**
- **Ctrl+C**: Immediate interrupt (may stop mid-encode, but safe due to validation)
- **'q' key**: Graceful shutdown (finishes current video first)
- Both are safe and support resume

**When to use:**
- Use `q` when you want to stop cleanly after the current video completes
- Use Ctrl+C when you need to stop immediately

**Important notes:**
- The 'q' key listener works in both standard batch mode and queue mode
- In queue mode, pressing 'q' will finish the current encoding, complete any pending uploads, and then exit
- **tmux/screen users**: The 'q' key listener is automatically disabled when running inside tmux or screen to avoid terminal compatibility issues. Use Ctrl+C instead for graceful interruption.

### Recovering Broken or Corrupted Videos

VideoSentinel can attempt to recover broken videos using FFmpeg's error recovery mode. This is useful when:
- Original files are corrupted and won't play properly
- Videos fail to encode with standard settings
- Files have broken timestamps or missing metadata
- Perceptual hashing fails because frames can't be extracted

**How error recovery works:**

The `--recover` flag enables FFmpeg's error-tolerant flags:

Input options (before `-i`):
- `-err_detect ignore_err`: Ignores decoding errors and continues processing
- `-fflags +genpts+discardcorrupt+igndts`: Generates missing timestamps, discards corrupted packets, ignores DTS errors
- `-ignore_unknown`: Ignores unknown stream types

Output options (after `-i`):
- `-max_muxing_queue_size 1024`: Increases buffer for problematic files
- `-max_error_rate 1.0`: Allows 100% error rate (doesn't fail on errors)

**Usage:**
```bash
# Re-encode broken files with recovery mode
python video_sentinel.py /path/to/broken_videos --check-specs --re-encode --recover

# Combine with filename-based duplicates to clean up broken originals
python video_sentinel.py /path/to/videos --filename-duplicates --duplicate-action auto-best --recover

# Recover and replace originals
python video_sentinel.py /path/to/videos --check-specs --re-encode --recover --replace-original

# Filter to specific broken file types
python video_sentinel.py /path/to/videos --check-specs --re-encode --recover --file-types avi,wmv
```

**What recovery mode can fix:**
- ✓ Videos with corrupted frames (skips bad frames)
- ✓ Files with broken timestamps (regenerates them)
- ✓ Videos missing metadata
- ✓ Files that crash standard ffmpeg encoding
- ✓ Partially downloaded or incomplete files

**Recovery mode validation:**

When `--recover` is enabled, output validation becomes more lenient:
- Allows recovered files to have different durations than source (corrupted sources may have wrong metadata)
- Allows files with missing duration metadata (common in heavily corrupted recoveries)
- Still validates: file exists, has video stream, has valid dimensions, and is readable by ffprobe
- This prevents false-negative validation failures for successfully recovered files

**Limitations:**
- Cannot recover completely unreadable files (0 bytes, wrong format, etc.)
- May result in shorter duration if large portions are corrupted
- Audio sync issues if significant corruption
- Quality depends on how much of the file is recoverable

**Best practices:**
1. Try standard encoding first (`--re-encode` without `--recover`)
2. Use `--recover` only for files that fail standard encoding
3. Always validate recovered files play correctly before deleting originals
4. Combine with `--filename-duplicates` to identify and keep best versions

### Verbose Mode for Debugging

The `-v` or `--verbose` flag enables detailed output for debugging encoding issues:

**Normal mode (without `-v`):**
```
[1/5] Encoding: video.avi
  Encoding: frame=1234 fps=45.2 time=00:01:23.45 speed=1.8x
✓ [1/5] Completed: video.avi (avg 45.2 fps, 1.8x speed)
```
- Shows compact inline progress that overwrites the same line
- Clean, minimal output

**Verbose mode (with `-v`):**
```
[1/5] Encoding: video.avi
  Output: video_reencoded.mp4
  Command: ffmpeg -loglevel info -stats ...
  Recovery mode enabled: using error-tolerant FFmpeg flags
  [all FFmpeg output lines...]
  frame=1234 fps=45 q=28.0 size=1024kB time=00:01:23.45 bitrate=1234.5kbits/s speed=1.8x
  [more FFmpeg output...]
✓ [1/5] Completed: video.avi
```
- Shows ALL FFmpeg output line-by-line
- Each line creates a new line (no overwriting)
- More detailed but scrolls more
- Shows recovery mode warnings and errors
- Useful for diagnosing why encoding fails

**When to use verbose mode:**
- Debugging encoding failures
- Understanding what recovery mode is doing
- Troubleshooting corrupted files
- Seeing detailed FFmpeg warnings

**When NOT to use verbose mode:**
- Batch encoding many files (output is too verbose)
- When you just want to see progress
- Production/automated scripts

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

**Failure handling in queue mode:**

When an encode fails in queue mode (network_queue_manager.py:311-329):

1. **Immediate actions:**
   - File is marked with `FileState.FAILED`
   - Error message is stored in the `error` field
   - Temp files are cleaned up immediately (downloaded file deleted)
   - State is saved to disk
   - Original source file is never touched/deleted

2. **Progress reporting:**
   - Failed files are counted and displayed in the final summary
   - Shows "Failed: X" in red at completion
   - Does not count toward "Completed" count

3. **Resume behavior (network_queue_manager.py:478-481):**
   - Failed files are **NOT automatically retried** on resume
   - Shown in resume summary as "Previously failed (skipped): X"
   - Files remain in FAILED state across resume sessions
   - Must be manually re-run if desired (remove from state or start fresh)

4. **Common failure causes:**
   - Encoding errors (corrupted source, unsupported codec)
   - Disk space issues (temp storage full)
   - FFmpeg crashes or timeouts
   - Download failures (network issues)

5. **Handling failed files:**
   ```bash
   # Option 1: Clear state and retry all files (including previously failed)
   python video_sentinel.py --clear-queue
   python video_sentinel.py /Volumes/NAS/videos --check-specs --re-encode --queue-mode

   # Option 2: Process failed files individually without queue mode
   # (Review error messages in logs to identify which files failed)
   ```

6. **Why failed files aren't automatically retried:**
   - Prevents infinite retry loops on permanently corrupted files
   - Allows user to inspect and fix issues before retrying
   - Saves time by not repeatedly attempting impossible encodes
   - State file provides a record of what failed for manual review

**Safety guarantees:**
- Failed encodes never delete or modify original source files
- Temp files are cleaned up to avoid disk space waste
- State is saved so you can review what failed
- Can safely interrupt and resume without losing failure information

**Monitoring queue status:**

Queue state is persisted to disk for monitoring and resume support:

1. **State file location** (network_queue_manager.py:92,119):
   ```
   Default: /tmp/videosentinel/queue_state.json
   Custom:  <your-temp-dir>/queue_state.json
   ```

2. **Temp directory location**:
   ```
   Default: /tmp/videosentinel/
   Custom:  <your-temp-dir>/
   ```

3. **State file contents (JSON)**:
   - List of all files with their current state
   - Error messages for failed files
   - File paths (source, local temp, output, final destination)
   - Can be inspected manually or with monitoring script

4. **Temp directory contents**:
   - `download_<filename>`: Downloaded files waiting to encode
   - `encoded_<filename>.mp4`: Encoded files waiting to upload
   - `queue_state.json`: State file
   - **Note**: Temp files are automatically deleted when:
     - Encoding fails (downloaded file cleaned up)
     - Upload succeeds (both download and encoded files cleaned up)
     - `--clear-queue` is run

5. **Monitoring with included script**:
   ```bash
   # View queue status and progress
   python monitor_queue.py

   # Monitor queue with custom temp dir
   python monitor_queue.py --temp-dir /Users/you/temp

   # Show all files including completed
   python monitor_queue.py --all

   # Show only failed files
   python monitor_queue.py --failed-only
   ```

   The monitor shows:
   - Queue summary (pending, downloading, encoding, uploading, complete, failed counts)
   - Progress percentage
   - Failed files with error messages
   - Temp directory size and contents
   - Detailed file-by-file status

6. **Manual state file inspection**:
   ```bash
   # View the raw state file
   cat /tmp/videosentinel/queue_state.json | python -m json.tool

   # Check temp directory size
   du -sh /tmp/videosentinel/

   # List temp files
   ls -lh /tmp/videosentinel/
   ```

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

### Fixing QuickLook Compatibility

VideoSentinel can automatically fix macOS QuickLook/Finder preview issues for videos that are already properly encoded (HEVC/H.264) but won't preview.

**Common QuickLook issues:**
1. **Wrong container**: MKV instead of MP4 (QuickLook requires MP4)
2. **Wrong HEVC tag**: hev1 instead of hvc1 (Apple devices need hvc1)
3. **Wrong pixel format**: yuv422p instead of yuv420p (compatibility issue)
4. **Missing faststart**: Metadata at end of file (prevents instant preview)

**Two-tier fixing approach:**

**1. Fast remux (no re-encoding)** - Takes seconds, not minutes:
- Changes container from MKV to MP4 using `ffmpeg -c copy`
- Fixes HEVC tag with `-tag:v hvc1`
- Adds `-movflags faststart` for instant preview
- No quality loss (just container change)

**2. Full re-encode** - Only when necessary:
- Wrong pixel format requires re-encoding with `-pix_fmt yuv420p`
- Uses same smart quality matching as regular re-encoding

**Usage:**
```bash
# Check what needs fixing
python video_sentinel.py /Videos --check-specs --fix-quicklook

# Fix and replace originals
python video_sentinel.py /Videos --check-specs --fix-quicklook --replace-original

# Works with queue mode for network storage
python video_sentinel.py /Volumes/NAS/videos --check-specs --fix-quicklook --queue-mode --replace-original
```

**Implementation details:**
- Compatibility check: `video_analyzer.py:200-283` (`check_quicklook_compatibility()`)
- Fast remux: `encoder.py:703-779` (`remux_to_mp4()`)
- Integration: `video_sentinel.py:699-909` (includes queue mode support)

**Smart Resume Support:**
- Automatically checks for existing `_quicklook` or `_reencoded` files before processing
- Validates existing outputs (size, format, duration)
- Skips files with valid outputs to avoid re-processing
- Safe to interrupt (Ctrl+C) and resume - picks up where it left off
- Works with both direct mode and queue mode

**Why this is useful:**
- Many HEVC videos in MKV containers won't preview in Finder
- Re-encoding would take hours, remuxing takes seconds
- Ensures entire library works with QuickLook/spacebar preview
- Resume capability saves time on large batch jobs

### Filtering by File Type

The `--file-types` flag filters files at the discovery stage for maximum efficiency:

**How it works:**
- Filters files when scanning the directory (before any analysis)
- Only matching files are loaded, checked, analyzed, and processed
- Applies to all operations: spec checking, duplicate detection, issue detection, re-encoding
- More efficient than loading all files then filtering later

**Usage examples:**
```bash
# Only process WMV and AVI files for re-encoding
python video_sentinel.py /videos --check-specs --re-encode --file-types wmv,avi

# Find duplicates only among MOV files
python video_sentinel.py /videos --find-duplicates --file-types mov

# Check issues only for legacy FLV files
python video_sentinel.py /videos --check-issues --file-types flv

# Combine with other flags
python video_sentinel.py /videos --check-specs --re-encode --file-types wmv,avi,mov \
  --replace-original --queue-mode
```

**Benefits:**
- **Faster scanning**: Only searches for specified file types
- **Less memory**: Doesn't load unnecessary files into memory
- **Cleaner output**: Only shows results for files you care about
- **Targeted operations**: Perfect for cleaning up legacy format collections

**Implementation details:**
- File type parsing: `video_sentinel.py:417-424`
- Filter application: `video_analyzer.py:313-358` (`find_videos()` method)
- Supports any extension: wmv, avi, mov, mkv, mp4, flv, webm, m4v, mpg, mpeg

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
