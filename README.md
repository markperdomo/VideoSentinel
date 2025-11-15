# VideoSentinel

A Python command-line utility for managing and validating video libraries. Ensures videos are properly encoded to modern specifications (H.265/HEVC), detects duplicates using perceptual hashing, identifies encoding issues, and safely re-encodes videos with intelligent quality matching. Supports batch processing with smart resume capabilities.

## Features

### Core Capabilities
- **Encoding Validation**: Check if videos meet modern encoding standards (H.265/HEVC, AV1, VP9)
- **Smart Re-encoding**: Automatically re-encode videos with intelligent quality matching based on source bitrate
- **40+ Video Format Support**: Works with virtually all video formats (MP4, MKV, AVI, WMV, FLV, MOV, 3GP, VOB, TS, and many more)
- **Issue Detection**: Identify corrupted files, incomplete videos, and encoding problems (quick or deep scan)
- **Replace Original Mode**: Safely replace original files with re-encoded versions after thorough validation

### Duplicate Management
- **Advanced Duplicate Detection**: Multi-frame perceptual hashing detects similar content even with different encoding, resolution, or quality
- **Filename-Based Duplicates**: Fast duplicate detection by filename only (useful when originals are broken)
- **Intelligent Duplicate Management**: Automatically keep best quality or interactively choose which duplicates to delete
- **Codec-Aware Quality Ranking**: Properly ranks modern codecs (HEVC @ 3000 kbps beats H.264 @ 6000 kbps)

### macOS QuickLook Optimization
- **QuickLook Compatibility Fixer**: Automatically fix preview issues - fast remux MKV→MP4, fix HEVC tags
- **Universal Compatibility**: All outputs optimized for instant preview in macOS Finder and Apple devices

### Network Storage & Performance
- **Network Queue Mode**: 2-3× faster encoding on network drives via download→encode→upload pipeline
- **Smart Buffering**: Parallel download, encoding, and upload operations
- **Queue Monitoring**: Built-in monitoring script to track queue progress and status

### Reliability & Safety
- **Smart Resume Support**: Interrupt and resume batch jobs without losing progress (Ctrl+C safe)
- **Graceful Shutdown**: Press 'q' to finish current video and exit cleanly
- **Error Recovery Mode**: Salvage broken/corrupted videos using FFmpeg's error-tolerant encoding
- **Visual Progress Bar**: Live encoding progress with percentage, speed multiplier, and ETA
- **File Type Filtering**: Target specific legacy formats (wmv, avi, mov) for selective processing
- **Verbose Debug Mode**: Detailed FFmpeg output for troubleshooting encoding issues

## Table of Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
  - [Basic Usage](#basic-usage)
  - [Specific Operations](#specific-operations)
  - [Re-encoding](#re-encoding)
  - [Error Recovery Mode](#error-recovery-mode)
  - [Fixing QuickLook Compatibility](#fixing-quicklook-compatibility)
  - [Network Queue Mode](#network-queue-mode)
  - [Graceful Shutdown](#graceful-shutdown)
  - [Additional Options](#additional-options)
- [Examples](#examples)
- [Modern Encoding Specs](#modern-encoding-specs)
- [Smart Quality Matching](#smart-quality-matching)
- [Re-encoding Safety Measures](#re-encoding-safety-measures)
  - [Replace Original Mode](#replace-original-mode)
  - [macOS QuickLook Compatibility](#macos-quicklook-compatibility)
  - [Interrupting and Resuming Batch Jobs](#interrupting-and-resuming-batch-jobs)
- [Advanced Duplicate Detection](#advanced-duplicate-detection)
  - [Managing Duplicates](#managing-duplicates)
  - [Filename-Based Duplicates](#filename-based-duplicates)
- [How Broken Video Detection Works](#how-broken-video-detection-works)
- [Debugging with Verbose Mode](#debugging-with-verbose-mode)
- [License](#license)

## Requirements

- Python 3.8+
- FFmpeg (must be installed separately on your system)

### Installing FFmpeg

**macOS (Homebrew):**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt-get install ffmpeg
```

**Windows (Chocolatey):**
```bash
choco install ffmpeg
```

## Installation

1. Clone or download this repository
2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

Scan a directory and run all checks:
```bash
python video_sentinel.py /path/to/videos
```

### Specific Operations

Check encoding specifications only:
```bash
python video_sentinel.py /path/to/videos --check-specs
```

Find duplicate videos (perceptual hashing):
```bash
python video_sentinel.py /path/to/videos --find-duplicates
```

Find duplicates by filename only (fast, works with broken files):
```bash
python video_sentinel.py /path/to/videos --filename-duplicates
```

Check for encoding issues:
```bash
python video_sentinel.py /path/to/videos --check-issues
```

Deep scan for corrupted videos:
```bash
python video_sentinel.py /path/to/videos --check-issues --deep-scan
```

### Re-encoding

Re-encode videos that don't meet specs (keeps originals with `_reencoded` suffix):
```bash
python video_sentinel.py /path/to/videos --check-specs --re-encode
```

Re-encode only specific file types (great for cleaning up legacy formats):
```bash
python video_sentinel.py /path/to/videos --check-specs --re-encode --file-types wmv,avi,mov
```

Replace original files with re-encoded versions (safe to interrupt and resume):
```bash
python video_sentinel.py /path/to/videos --check-specs --re-encode --replace-original
```

Specify output directory for re-encoded videos:
```bash
python video_sentinel.py /path/to/videos --re-encode --output-dir /path/to/output
```

Choose target codec:
```bash
python video_sentinel.py /path/to/videos --re-encode --target-codec hevc
```

Downscale 4K/high-resolution videos to 1080p:
```bash
python video_sentinel.py /path/to/videos --check-specs --re-encode --downscale-1080p
```

Combine downscaling with other options:
```bash
# Downscale, use specific codec, and replace originals
python video_sentinel.py /path/to/videos --check-specs --re-encode --downscale-1080p --target-codec hevc --replace-original

# Downscale with queue mode for network storage
python video_sentinel.py /Volumes/NAS/videos --check-specs --re-encode --downscale-1080p --queue-mode
```

### Error Recovery Mode

VideoSentinel can attempt to recover and re-encode broken or corrupted videos using FFmpeg's error-tolerant mode. This is useful when:
- Original files are corrupted and won't play properly
- Videos fail to encode with standard settings
- Files have broken timestamps or missing metadata
- Perceptual hashing fails because frames can't be extracted

**Enable recovery mode:**
```bash
python video_sentinel.py /path/to/videos --check-specs --re-encode --recover
```

**How it works:**

The `--recover` flag enables FFmpeg's error-tolerant flags to salvage broken files:

**Input options** (before `-i`):
- `-err_detect ignore_err` - Ignores decoding errors and continues processing
- `-fflags +genpts+discardcorrupt+igndts` - Generates missing timestamps, discards corrupted packets
- `-ignore_unknown` - Ignores unknown stream types

**Output options** (after `-i`):
- `-max_muxing_queue_size 1024` - Increases buffer for problematic files
- `-max_error_rate 1.0` - Allows 100% error rate (doesn't fail on errors)

**What recovery mode can fix:**
- ✓ Videos with corrupted frames (skips bad frames)
- ✓ Files with broken timestamps (regenerates them)
- ✓ Videos missing metadata
- ✓ Files that crash standard ffmpeg encoding
- ✓ Partially downloaded or incomplete files

**Combine with filename duplicates to clean up broken originals:**
```bash
python video_sentinel.py /path/to/videos --filename-duplicates --duplicate-action auto-best
```

**Recover and replace originals:**
```bash
python video_sentinel.py /path/to/videos --check-specs --re-encode --recover --replace-original
```

**Filter to specific broken file types:**
```bash
python video_sentinel.py /path/to/videos --check-specs --re-encode --recover --file-types avi,wmv
```

**Limitations:**
- Cannot recover completely unreadable files (0 bytes, wrong format)
- May result in shorter duration if large portions are corrupted
- Audio sync issues possible if significant corruption
- Quality depends on how much of the file is recoverable

**Validation:** When `--recover` is enabled, output validation is more lenient to avoid rejecting successfully recovered files that may have different durations or missing metadata.

### Fixing QuickLook Compatibility

If you have videos that are already properly encoded (HEVC/H.264) but don't preview in macOS Finder/QuickLook, use `--fix-quicklook` to automatically fix compatibility issues.

**Common QuickLook issues:**
- Videos in MKV containers (need MP4 for QuickLook)
- HEVC videos with wrong tag (hev1 instead of hvc1)
- Wrong pixel format (needs yuv420p)
- Missing faststart flag (metadata at end of file)

**Two-tier fixing approach:**

**1. Fast remux (no re-encoding)** - Takes seconds:
- Converts MKV → MP4 container
- Fixes HEVC tag to hvc1
- Adds faststart flag

**2. Full re-encode** - Only when necessary:
- Wrong pixel format
- Other codec-level issues

**Check QuickLook compatibility:**
```bash
python video_sentinel.py /path/to/videos --check-specs --fix-quicklook
```

**Fix and replace originals:**
```bash
python video_sentinel.py /path/to/videos --check-specs --fix-quicklook --replace-original
```

**With network queue mode:**
```bash
python video_sentinel.py /Volumes/NAS/videos --check-specs --fix-quicklook --queue-mode --replace-original
```

**Example output:**
```
QUICKLOOK COMPATIBILITY CHECK
================================================================================

✓ video1.mp4: QuickLook compatible
⚠ video2.mkv: Needs remux (fast)
    - Container is matroska, should be MP4
✗ video3.mp4: Needs re-encode
    - HEVC tag is hev1, should be hvc1 for QuickLook
    - Pixel format is yuv422p, should be yuv420p

Summary: 1 compatible, 1 need remux, 1 need re-encode

REMUXING FOR QUICKLOOK COMPATIBILITY (FAST)
================================================================================

Remuxing: video2.mkv
✓ Remuxed: video2.mkv
✓ Replaced: video2.mkv → video2.mp4

RE-ENCODING FOR QUICKLOOK COMPATIBILITY
================================================================================

Re-encoding: video3.mp4
✓ Completed: video3.mp4
✓ Replaced: video3.mp4
```

**Benefits:**
- ✅ **Fast**: Remuxing MKV→MP4 takes seconds (no re-encoding!)
- ✅ **Smart**: Only re-encodes when absolutely necessary
- ✅ **Resume-Safe**: Automatically skips files with existing `_quicklook` or `_reencoded` outputs
- ✅ **Safe**: Works with `--replace-original` flag
- ✅ **Compatible**: Works with queue mode for network storage

**Smart Resume:**
If you interrupt the process (Ctrl+C) and re-run the same command, VideoSentinel will:
1. Check for existing `_quicklook` or `_reencoded` files
2. Validate each existing output (size, format, duration)
3. Skip files with valid outputs
4. Only process files that haven't been fixed yet

**Example:**
```
Checking for existing QuickLook outputs...
✓ video1.mkv: Already has valid output (video1_quicklook.mp4)
✓ video2.mkv: Already has valid output (video2_quicklook.mp4)

Found 2 video(s) with existing valid QuickLook outputs (skipping)
Need to fix: 3 video(s)
```

**Note:** Only processes videos that already meet modern codec specs. Use `--re-encode` for videos with old codecs.

### Network Queue Mode

When encoding videos stored on network drives (NAS, SMB shares, network volumes), encoding can be extremely slow due to network I/O during frame reading. **Queue mode** solves this by implementing a three-stage pipeline:

**How it works:**
1. **Download Thread**: Pre-fetches files from network to local temp storage
2. **Encode Thread**: Processes files locally at full SSD speed
3. **Upload Thread**: Copies completed encodes back to network

All three stages run in parallel, dramatically improving performance!

**Basic queue mode:**
```bash
python video_sentinel.py /Volumes/NetworkDrive/videos --check-specs --re-encode --queue-mode
```

**With custom temp location (recommended - use fast SSD):**
```bash
python video_sentinel.py /Volumes/NetworkDrive/videos \
  --check-specs --re-encode --queue-mode \
  --temp-dir /Users/you/temp \
  --buffer-size 3 \
  --max-temp-size 100
```

**Replace originals with queue mode:**
```bash
python video_sentinel.py /Volumes/NetworkDrive/videos \
  --check-specs --re-encode --queue-mode --replace-original
```

**Queue mode features:**
- **Parallel I/O**: Downloads next file while encoding current and uploading previous
- **Smart buffering**: Keeps 2-4 files buffered locally (configurable)
- **Storage limits**: Pauses downloads if temp storage exceeds limit
- **Resume support**: Saves state to disk, survives Ctrl+C interrupts
- **Automatic cleanup**: Removes temp files after successful upload

**Queue mode options:**
- `--queue-mode`: Enable the queue system
- `--temp-dir`: Where to store temp files (default: system temp, recommend fast local SSD)
- `--buffer-size`: How many files to buffer locally (default: 4, range: 2-5)
- `--max-temp-size`: Max temp storage in GB (default: 50)

**Performance comparison:**
```
Traditional (network I/O during encoding):
  Encoding speed: ~15-20 fps (network bottleneck)

Queue mode (local SSD):
  Encoding speed: ~45-60 fps (CPU-limited)

Speed improvement: 2-3x faster!
```

#### Temporary File Management

**Where temporary files are stored:**

Queue mode uses a local temp directory to buffer files during the download → encode → upload pipeline.

**Default location:** `/tmp/videosentinel/` (system temp directory)

**Custom location (recommended):**
```bash
python video_sentinel.py /Volumes/NAS/videos \
  --queue-mode --re-encode \
  --temp-dir /Users/you/fast-ssd-temp
```

**What's stored in the temp directory:**
- `download_<filename>` - Files downloaded from network (awaiting encoding)
- `encoded_<filename>.mp4` - Encoded outputs (awaiting upload)
- `queue_state.json` - State tracking for resume support

**Automatic cleanup during normal operation:**
- Downloaded originals are deleted immediately after successful encoding
- Encoded outputs are deleted immediately after successful upload
- State file remains for resume capability
- Failed encodes may leave temp files (check state file for status)

**Clearing the queue:**

To remove all temp files and state from a previous session:
```bash
python video_sentinel.py --clear-queue
```

With custom temp directory:
```bash
python video_sentinel.py --clear-queue --temp-dir /Users/you/custom-temp
```

**What `--clear-queue` does:**
1. Deletes `queue_state.json` (removes all tracking)
2. Deletes ALL temp files in the directory
   - ⚠️ **Warning:** This includes files currently downloading, encoding, or awaiting upload
   - You'll lose any work in progress and need to start from scratch
3. Shows how much data was cleared

**Example output:**
```
CLEARING QUEUE STATE
================================================================================
Removing state file: /tmp/videosentinel/queue_state.json
Removing 3 temp files (4523.45 MB)
✓ Queue cleared successfully
================================================================================
```

**When to use `--clear-queue`:**
- After successful completion to free up temp space
- When you want to abandon an in-progress batch and start fresh
- If queue state becomes corrupted
- To reclaim disk space from failed encodes

**When NOT to use it:**
- If you want to resume interrupted work (just re-run the same command instead)
- If uploads are still in progress (they'll be lost)

**Safe resume (recommended):**
```bash
# Interrupted during encoding? Just re-run the same command:
python video_sentinel.py /Volumes/NAS/videos --queue-mode --re-encode

# Queue mode automatically:
# - Loads saved state from queue_state.json
# - Resumes from where it left off
# - Completes any partial operations
```

**Monitoring queue status:**

VideoSentinel includes a monitoring script to track queue progress:

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

### Graceful Shutdown

For controlled shutdown during batch encoding, VideoSentinel supports graceful shutdown by pressing the **'q' key**:

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

### Additional Options

**General Options:**
- `-r, --recursive`: Scan subdirectories recursively
- `-v, --verbose`: Enable verbose output (show all FFmpeg output for debugging)
- `--file-types TYPES`: Filter to specific file types (comma-separated, e.g., "wmv,avi,mov")

**Re-encoding Options:**
- `--target-codec {h264,hevc,av1}`: Target codec for re-encoding (default: hevc)
- `--replace-original`: Replace original files with re-encoded versions (deletes source, renames output)
- `--recover`: Enable error recovery mode for broken/corrupted videos
- `--downscale-1080p`: Downscale videos larger than 1080p to maximum 1920x1080 (preserves aspect ratio)
- `--output-dir PATH`: Output directory for re-encoded videos

**Duplicate Detection Options:**
- `--duplicate-action {report,interactive,auto-best}`: How to handle duplicates (default: report)
- `--filename-duplicates`: Find duplicates by filename only (fast, no perceptual hashing)

**Issue Detection Options:**
- `--deep-scan`: Perform deep integrity check by decoding entire videos (slower but more thorough)

**QuickLook Options:**
- `--fix-quicklook`: Fix QuickLook compatibility (remux MKV→MP4, fix HEVC tags, re-encode if needed)

**Queue Mode Options:**
- `--queue-mode`: Enable network queue mode (see [Network Queue Mode](#network-queue-mode))
- `--temp-dir PATH`: Temporary directory for queue mode (default: system temp)
- `--max-temp-size GB`: Maximum temp storage size in GB for queue mode (default: 50)
- `--buffer-size N`: Number of files to buffer locally in queue mode (default: 4)
- `--clear-queue`: Clear queue state and temp files from previous queue mode session

## Examples

Scan videos recursively and re-encode non-compliant ones (keeps originals):
```bash
python video_sentinel.py ~/Videos -r --check-specs --re-encode
```

Clean up legacy formats by re-encoding specific file types and replacing originals:
```bash
python video_sentinel.py ~/Videos -r --check-specs --re-encode --file-types wmv,avi,mov --replace-original
```

Find duplicates in a large library:
```bash
python video_sentinel.py /media/library -r --find-duplicates
```

Run all checks with verbose output:
```bash
python video_sentinel.py /path/to/videos -r -v
```

Perform deep scan to find corrupted videos:
```bash
python video_sentinel.py ~/Videos -r --check-issues --deep-scan
```

Recover broken videos with error-tolerant encoding:
```bash
python video_sentinel.py ~/Videos --check-specs --re-encode --recover --file-types avi,wmv
```

Downscale 4K videos to 1080p for space savings:
```bash
python video_sentinel.py ~/Videos -r --check-specs --re-encode --downscale-1080p --replace-original
```

Find duplicates by filename and auto-keep best (fast, works with broken originals):
```bash
python video_sentinel.py ~/Videos -r --filename-duplicates --duplicate-action auto-best
```

Fix QuickLook compatibility for network storage with queue mode:
```bash
python video_sentinel.py /Volumes/NAS/videos --check-specs --fix-quicklook --queue-mode --replace-original
```

Clean up duplicate re-encoded versions automatically:
```bash
python video_sentinel.py ~/Videos -r --find-duplicates --duplicate-action auto-best
```

Debug encoding issues with verbose output:
```bash
python video_sentinel.py ~/Videos/problem.avi --re-encode --recover -v
```

## Modern Encoding Specs

VideoSentinel works with **40+ video formats** including MP4, MKV, AVI, WMV, FLV, MOV, 3GP, VOB, TS, and many more.

By default, VideoSentinel considers a video properly encoded if it meets:
- **Modern codecs**: H.265/HEVC, AV1, or VP9 (H.264 is acceptable but not modern)
- **Modern containers**: MP4, MKV/Matroska, or WebM
- **Valid metadata**: Proper dimensions, duration, and stream information
- **No corruption**: No encoding errors or frame corruption

## Smart Quality Matching

VideoSentinel uses **intelligent quality matching** when re-encoding videos to preserve visual quality while potentially reducing file size.

### How It Works

Instead of using a fixed quality setting for all videos, VideoSentinel:

1. **Analyzes source quality** - Calculates bits per pixel (bpp) from bitrate, resolution, and framerate
2. **Determines quality tier** - High-quality sources get lower CRF (better quality), low-quality sources get higher CRF
3. **Adjusts for codec** - Different codecs need different CRF values for equivalent quality
4. **Preserves visual fidelity** - Aims to match or exceed source quality while leveraging modern codec efficiency

### Quality Tiers

**For H.265/HEVC (default):**

| Source Quality | Bits per Pixel | CRF | Example Sources |
|---------------|---------------|-----|-----------------|
| Very High | > 0.25 bpp | 18 | 4K Bluray, high-bitrate 1080p remux |
| High | 0.15-0.25 bpp | 20 | Good 1080p encodes, decent 4K streaming |
| Medium-High | 0.10-0.15 bpp | 22 | Average 1080p |
| Medium | 0.07-0.10 bpp | 23 | Standard 1080p streaming |
| Medium-Low | 0.05-0.07 bpp | 25 | Lower quality 1080p, good 720p |
| Low | < 0.05 bpp | 28 | Low quality sources, SD content |

**For H.264:**
Uses slightly lower CRF values (16-26 range) since H.264 requires lower CRF for equivalent quality to HEVC.

**For AV1:**
Uses higher CRF values (20-32 range) since AV1 has superior compression efficiency.

### Benefits

- **Quality Preservation**: High-quality sources maintain their visual fidelity
- **Space Efficiency**: Low-quality sources don't waste space with unnecessarily low CRF
- **Smart Compression**: Leverages modern codec efficiency (HEVC typically 40-50% smaller than H.264)
- **Automatic**: No manual quality tuning needed

### Real-Time Encoding Progress

During batch encoding, VideoSentinel displays a **visual progress bar** with queue position, percentage, speed, and ETA:

**Progress display format:**
```
[1/5] Encoding: video.wmv
  [████████████████████░░░░░] 80.0% | 5.58x speed | ETA: 2m 15s
```

**What it shows:**
- **Queue position:** `[1/5]` = encoding video 1 of 5
- **Visual progress bar:** 25-character bar showing completion at a glance
- **Percentage:** Exact completion percentage (e.g., 80.0%)
- **Speed multiplier:** How fast encoding is compared to real-time (5.58x = encoding 5.58× faster than playback)
- **ETA:** Estimated time until completion (e.g., "2m 15s", "1h 5m")

**Completion messages:**
```
✓ [1/5] Completed: video.wmv (avg 45.2 fps, 1.8x speed)
✗ [1/5] Error encoding video.wmv: validation failed
```

**Benefits:**
- **Visual at a glance:** Progress bar shows completion instantly
- **Accurate ETA:** Know exactly when encoding will finish
- **Percentage precision:** See exact progress numerically
- **Encoding efficiency:** Speed multiplier shows how fast your hardware is
- **No mental math:** ETA calculated automatically from speed and remaining duration

**Note:** If video duration is unavailable, falls back to time-based display: `Encoding: 00:01:23.45 | 5.58x speed`

### Example

```bash
# Re-encode with smart quality matching (automatic)
python video_sentinel.py ~/Videos --check-specs --re-encode -v
```

**Sample output:**
```
RE-ENCODING NON-COMPLIANT VIDEOS (Using smart quality matching)
================================================================================

Re-encoding videos: 100%|████████| 3/3 [05:32<00:00, 110.75s/video]
  Quality analysis: 0.2134 bpp → CRF 20
  Source: 12450 kbps, 1920x1080, 23.98 fps
✓ high_quality_movie.mp4

  Quality analysis: 0.0823 bpp → CRF 23
  Source: 4800 kbps, 1920x1080, 30.0 fps
✓ standard_video.mp4

  Quality analysis: 0.0421 bpp → CRF 28
  Source: 1200 kbps, 1280x720, 30.0 fps
✓ low_quality_clip.mp4
```

### Manual Override

You can still manually specify CRF if desired (bypasses smart matching):

```python
from encoder import VideoEncoder

encoder = VideoEncoder(verbose=True)
encoder.re_encode_video(
    input_path=Path("video.mp4"),
    output_path=Path("output.mp4"),
    target_codec="hevc",
    crf=18  # Manual CRF overrides smart matching
)
```

## Re-encoding Safety Measures

VideoSentinel implements multiple safety checks to prevent data loss during re-encoding:

### Validation Before Deletion

Before considering an encoding successful, VideoSentinel validates the output file:

1. **File Existence Check** - Confirms output file was created
2. **Size Check** - Ensures file is larger than 1KB (not empty/corrupt)
3. **Format Validation** - Uses ffprobe to verify file can be read
4. **Stream Validation** - Confirms video stream exists and is valid
5. **Dimension Check** - Verifies output has valid resolution (not 0x0)
6. **Duration Comparison** - Compares output duration with source (±2 seconds tolerance)

**If any validation fails:**
- The invalid output file is automatically deleted
- The original file is preserved (never deleted)
- Encoding is marked as failed
- Error message indicates which check failed

### Original File Preservation

By default, **original files are always kept** (`keep_original=True`):

```bash
# Safe - originals are preserved by default
python video_sentinel.py ~/Videos --check-specs --re-encode
```

Output files are saved with `_reencoded` suffix:
```
original_video.mp4          # Original (preserved)
original_video_reencoded.mp4  # New encoded version
```

### When Validation Fails

Example with verbose output showing validation:

```bash
python video_sentinel.py ~/Videos --check-specs --re-encode -v
```

**Successful encoding:**
```
✓ movie.mp4
  Quality analysis: 0.1823 bpp → CRF 20
  Source: 9800 kbps, 1920x1080, 24.0 fps
  Validation passed: 1920x1080, 7234.5s
```

**Failed validation:**
```
✗ corrupt_source.mp4 - Failed
  Validation failed: Duration mismatch (7123.1s vs 7234.5s)
  Output validation failed for corrupt_source_reencoded.mp4
```

In this case:
- Original `corrupt_source.mp4` is preserved
- Invalid output is deleted automatically
- User is warned about the problem

### Recommended Workflow

1. **Test first**: Run on a small subset of videos
2. **Use verbose mode**: See detailed validation info (`-v` flag)
3. **Keep originals**: Default behavior preserves originals
4. **Review results**: Check summary to see success/failure count
5. **Verify manually**: Spot-check a few re-encoded videos before bulk deletion

### Smart Skip for Already Re-Encoded Videos

Before starting batch re-encoding, VideoSentinel checks for existing valid outputs and automatically skips them:

```bash
python video_sentinel.py /videos --re-encode --replace-original

# Output:
# Checking for existing re-encoded outputs...
# ✓ video1.avi: Already has valid output (video1_reencoded.mp4)
# ✓ video2.wmv: Already has valid output (video2_reencoded.mp4)
#
# Found 2 video(s) with existing valid re-encodes (skipping)
# Need to encode: 3 video(s)
```

**How it works:**
- Scans for files with `_reencoded` or `_quicklook` suffixes matching the source filename
- Validates each existing output using the same thorough checks as post-encoding validation
- Deletes invalid/corrupted outputs and re-encodes from scratch
- Skips valid outputs to save time

**Benefits:**
- **Saves hours** when resuming interrupted batch jobs
- **Prevents wasted work** re-encoding files that are already done
- **Validates outputs** to ensure corrupted partial files are detected and removed
- **Works seamlessly** with both `_reencoded` and `_quicklook` suffixed files

**Example scenario:**
```bash
# First run - encode 100 videos, interrupted after 50
python video_sentinel.py /videos --re-encode

# Second run - automatically skips the 50 completed videos
python video_sentinel.py /videos --re-encode
# Checking for existing re-encoded outputs...
# Found 50 video(s) with existing valid re-encodes (skipping)
# Need to encode: 50 video(s)
```

### Replace Original Mode

For production use after thorough testing, VideoSentinel supports replacing original files with re-encoded versions using the `--replace-original` flag:

```bash
python video_sentinel.py /path/to/videos --check-specs --re-encode --replace-original
```

**How it works:**
1. Encodes to temporary file with `_reencoded` suffix (e.g., `video.avi` → `video_reencoded.mp4`)
2. Thoroughly validates the output (same validation as above)
3. Only after successful validation:
   - Deletes the original source file
   - Renames output to match original filename (with proper extension)
4. Example: `video.avi` → encode to `video_reencoded.mp4` → delete `video.avi` → rename to `video.mp4`

**Safety features:**
- Validation must pass before any deletion occurs
- Original is preserved if encoding or validation fails
- All output videos use `.mp4` extension for maximum compatibility
- HEVC videos include macOS QuickLook compatibility tags (`-tag:v hvc1`)

**Safe to interrupt:** You can press Ctrl+C at any time. Partial encodes are automatically detected and cleaned up on resume.

### macOS QuickLook Compatibility

All re-encoded videos are optimized for maximum compatibility, especially with macOS QuickLook (Finder preview):

**Compatibility features:**
- **MP4 container:** All outputs use `.mp4` regardless of source format (never `.avi`, `.wmv`, etc.)
- **HEVC tag:** HEVC videos use `-tag:v hvc1` instead of default `hev1` for Apple device compatibility
- **Pixel format:** Forces `yuv420p` for universal player support
- **Fast start:** Moves metadata to file beginning with `-movflags faststart` for instant previews

**Why this matters:**
- Videos preview instantly in macOS Finder without opening an app
- Compatible with QuickTime Player, iOS devices, and Apple TV
- Works with spacebar preview in Finder
- No "codec not supported" errors on Apple devices

Without these optimizations, HEVC videos may not preview in macOS QuickLook even though they're valid files. VideoSentinel handles this automatically.

### Interrupting and Resuming Batch Jobs

VideoSentinel is designed to handle interruptions gracefully, especially when using `--replace-original`:

**Safe to interrupt at any time:**
- Press Ctrl+C to stop encoding
- No corrupted files will be kept (validation ensures integrity)
- Partial encodes are automatically detected and removed on next run

**Automatic resume on restart:**
```bash
# Start batch encoding with replacement
python video_sentinel.py /videos --re-encode --replace-original

# Interrupt with Ctrl+C after some files complete

# Resume - automatically skips completed files
python video_sentinel.py /videos --re-encode --replace-original
```

**What happens on resume:**

1. ✓ **Fully completed:** Shows "Replacement already completed, skipping"
2. ✓ **Completed encode, not replaced yet:** Skips encoding, completes replacement
3. ✓ **Partial/corrupted encode:** Deletes invalid file, re-encodes from scratch
4. ✓ **Never encoded:** Encodes normally

**Example scenarios:**

**Scenario 1: Batch interrupted mid-encode**
```
First run:
  [1/5] video1.avi → Completed ✓
  [2/5] video2.wmv → Completed ✓
  [3/5] video3.mov → 50% complete... [Ctrl+C pressed]

Second run (same command):
  video1.avi - Replacement already completed, skipping
  video2.wmv - Replacement already completed, skipping
  [1/3] Resuming: video3.mov (partial file detected, re-encoding)
  [2/3] Encoding: video4.avi
  [3/3] Encoding: video5.wmv
```

**Scenario 2: Encode completed but not replaced**
```
First run:
  video.avi → video_reencoded.mp4 (completed, validated)
  [Interrupted before replacement step]

Second run:
  Resuming: video.avi (already encoded)
  [Completes the replacement: deletes video.avi, renames to video.mp4]
```

This means:
- **Safe to re-run** after interruptions without wasting work
- **Never re-encodes** successfully completed files
- **Automatically cleans up** partial/broken files
- **Validates outputs** before considering them complete

**Best practice:** For large batch jobs, you can interrupt and resume as needed. The encoder tracks which files are done and picks up where it left off.

## Advanced Duplicate Detection

VideoSentinel uses a sophisticated multi-frame perceptual hashing approach to find duplicate videos, even when they differ in encoding, quality, or resolution.

### How It Works

Unlike simple file hash comparisons (which only detect byte-for-byte identical files), VideoSentinel's perceptual approach can identify:
- Same video with different encodings (H.264 vs HEVC)
- Different quality levels (4K vs 1080p vs 720p)
- Different bitrates or compression settings
- Re-encoded or transcoded versions
- Videos with slight color corrections or filters

### Technical Approach

1. **Multi-Frame Sampling** - Extracts 10 frames evenly distributed throughout each video (not just beginning/end)
2. **Perceptual Hashing** - Uses `phash` algorithm on each frame (robust to minor differences)
3. **Large Hash Size** - 12x12 (144-bit) hashes provide more granularity than standard 8x8
4. **Average Distance Comparison** - Compares all corresponding frame pairs and averages the distance
5. **Adaptive Threshold** - Default threshold of 15 balances false positives vs false negatives

### Why This Is Better

**Old approach (basic):**
- 3 frames only
- Simple average_hash
- 8x8 (64-bit) hashes
- Poor hash combining (averaged)
- Threshold too strict

**Result:** Missed duplicates or too many false positives

**New approach (improved):**
- 10 frames across entire video
- Perceptual hash (phash)
- 12x12 (144-bit) hashes
- Frame-by-frame comparison
- Relaxed threshold (15)

**Result:** Robust duplicate detection that handles encoding differences

### Usage

```bash
# Find duplicates in a directory
python video_sentinel.py ~/Videos --find-duplicates

# Recursive scan for duplicates
python video_sentinel.py ~/Videos -r --find-duplicates

# With verbose output
python video_sentinel.py ~/Videos --find-duplicates -v
```

### Example Output

```
DUPLICATE VIDEO DETECTION
================================================================================

Computing hashes: 100%|████████████| 150/150 [02:15<00:00,  1.11video/s]
Successfully hashed 150 videos

Found 3 groups of duplicate videos:

group_0 (3 videos):
  - vacation_2023_4k.mp4 (5420.23 MB)
  - vacation_2023_1080p.mp4 (2134.56 MB)
  - vacation_2023_720p.mp4 (890.12 MB)

group_1 (2 videos):
  - movie_bluray.mkv (8900.45 MB)
  - movie_compressed.mp4 (3200.78 MB)

group_2 (2 videos):
  - concert_original.avi (6543.21 MB)
  - concert_reencoded.mp4 (4123.90 MB)

Total duplicates: 7 videos in 3 groups
```

### Understanding Results

Each group contains videos with very similar content. Typically you'll want to:
1. Review each group
2. Keep the highest quality version
3. Delete the duplicates to save space

**Note:** The detector compares frame content, not file names, so it finds true visual duplicates regardless of how the files are named.

### Adjusting Sensitivity

If you're getting too many false positives (videos grouped that aren't duplicates) or false negatives (missing duplicates), you can adjust parameters in the code:

```python
from duplicate_detector import DuplicateDetector

# More strict (fewer false positives, may miss some duplicates)
detector = DuplicateDetector(threshold=10, num_samples=15)

# More lenient (catch more duplicates, may include false positives)
detector = DuplicateDetector(threshold=20, num_samples=10)
```

### Managing Duplicates

VideoSentinel can automatically handle duplicates instead of just reporting them. Use the `--duplicate-action` flag to specify how to handle duplicate groups:

**Three modes available:**

**1. Report mode (default)** - Just list duplicates, no action
```bash
python video_sentinel.py ~/Videos --find-duplicates
# or explicitly:
python video_sentinel.py ~/Videos --find-duplicates --duplicate-action report
```

**2. Auto-best mode** - Automatically keep highest quality, delete others
```bash
python video_sentinel.py ~/Videos --find-duplicates --duplicate-action auto-best
```

**How auto-best ranks quality:**
- **QuickLook compatibility**: +1500 points for macOS QuickLook/Finder preview compatibility
- **Newly processed files**: +1000 points for files with `_quicklook` or `_reencoded` suffixes
- **Container format**: MP4/M4V (+300) > MKV/WebM (+100) > others
- **Codec modernity**: AV1 > VP9 > HEVC > H.264 > older codecs
- **Resolution**: Higher resolution scores higher
- **Bitrate (normalized by codec efficiency)**: Modern codecs need less bitrate for equivalent quality

**Codec Efficiency Normalization:**

VideoSentinel intelligently accounts for codec efficiency when comparing bitrates:
- **HEVC @ 3000 kbps** = equivalent to **H.264 @ 6000 kbps**
- **AV1 @ 2000 kbps** = equivalent to **H.264 @ 5000 kbps**

This ensures re-encoded videos with modern codecs are correctly ranked higher than originals, even at lower bitrates.

**Efficiency multipliers:**
- AV1: 2.5× more efficient than H.264
- VP9, HEVC: 2.0× more efficient than H.264
- H.264: 1.0× (baseline)
- MPEG4: 0.6× (less efficient)
- MPEG2, WMV: 0.4-0.5× (much less efficient)

**Example output:**
```
Group 1:
  ✓ Keeping: movie_quicklook.mp4
    (HVC1, 1920x1080, 3000 kbps [QuickLook ✓])
  ✗ Deleting: movie_original.mkv (450.23 MB)
    (HEVC, 1920x1080, 3500 kbps)
  ✗ Deleting: movie_old.avi (850.45 MB)
    (MPEG4, 1920x1080, 8000 kbps)

Delete 2 files? (yes/no): yes
  ✓ Deleted: movie_h264.mp4
  ✓ Deleted: movie_old.avi

Space freed: 1300.68 MB
```

**3. Interactive mode** - Ask for each duplicate group
```bash
python video_sentinel.py ~/Videos --find-duplicates --duplicate-action interactive
```

**Features:**
- Shows all duplicates ranked by quality with ★ marking the best
- Displays codec, resolution, bitrate, and file size for each
- Lets you choose which to keep (or skip and keep all)
- Provides detailed quality information to help decide

**Example interaction:**
```
Group 1 - 3 duplicates found:

  ★ BEST [1] movie_quicklook.mp4 [QuickLook ✓]
      Codec: HVC1, Resolution: 1920x1080
      Bitrate: 3000 kbps, Size: 350.12 MB

    #2 [2] movie_original.mkv
      Codec: HEVC, Resolution: 1920x1080
      Bitrate: 3500 kbps, Size: 450.23 MB

    #3 [3] movie_old.avi
      Codec: MPEG4, Resolution: 1920x1080
      Bitrate: 8000 kbps, Size: 850.45 MB

Options:
  1-3: Keep that video, delete others
  0 or Enter: Keep all (no action)

Your choice: 1

  ✓ Keeping: movie_hevc.mp4
  ✗ Will delete: movie_h264.mp4 (450.23 MB)
  ✗ Will delete: movie_old.avi (850.45 MB)
```

**Safety features:**
- Auto-best mode asks for confirmation before deleting
- Interactive mode confirms selection before deletion
- Shows total space freed after deletion
- Handles deletion errors gracefully

**Use cases:**
- **Report**: When you just want to see what duplicates exist
- **Auto-best**: When you trust the quality ranking and want to automate cleanup
- **Interactive**: When you want manual control but with quality rankings to help decide

#### Automatic Filename Cleanup

When using `auto-best` or `interactive` modes, VideoSentinel automatically cleans up filenames of kept files by removing `_reencoded` and `_quicklook` suffixes.

**Example:**
```
Before:
  video_reencoded.mp4 (HEVC, kept)
  video.mp4 (H.264, deleted)

After cleanup:
  video.mp4 (HEVC, renamed from video_reencoded.mp4)
```

This keeps your library organized without suffix clutter.

**How it works:**
- After deleting duplicates, checks if kept files have `_reencoded` or `_quicklook` suffixes
- Automatically renames them to remove the suffix
- Only renames if target filename doesn't already exist
- Shows progress: `✓ Renamed: video_reencoded.mp4 → video.mp4`

**Why this is useful:**
- If you've re-encoded files to modern codecs and then run duplicate detection, the better quality re-encoded version gets kept
- Instead of ending up with `video_reencoded.mp4`, you get the clean `video.mp4` filename
- Keeps your library organized and avoids filename pollution

### Filename-Based Duplicates

For situations where perceptual hashing can't work (e.g., original files are too corrupted to extract frames), VideoSentinel offers fast filename-based duplicate detection:

```bash
# Find duplicates by filename only (fast, no video analysis)
python video_sentinel.py /path/to/videos --filename-duplicates

# Find filename duplicates and auto-keep best
python video_sentinel.py /path/to/videos --filename-duplicates --duplicate-action auto-best

# Interactive mode
python video_sentinel.py /path/to/videos --filename-duplicates --duplicate-action interactive
```

**How it works:**
- Normalizes filenames by removing `_reencoded` and `_quicklook` suffixes
- Case-insensitive matching
- Groups files with same base name regardless of extension
- Example: `video.avi`, `video_reencoded.mp4`, `video.mkv` are grouped as duplicates

**When to use:**
- Original files are broken and can't generate perceptual hashes
- You have re-encoded versions and want to clean up originals
- You want fast duplicate detection without video analysis
- Files have consistent naming but different formats/encodings

**Benefits:**
- **Much faster** than perceptual hashing (no video analysis required)
- **Works with broken files** that won't play or can't be decoded
- **Same quality ranking** as perceptual duplicate detection
- **Same actions** available: report, auto-best, interactive

**Example scenario:**
```
Files:
  vacation.avi (corrupted, won't play)
  vacation_reencoded.mp4 (HEVC, working)
  vacation_quicklook.mp4 (H.264, working)

Command:
  python video_sentinel.py /videos --filename-duplicates --duplicate-action auto-best

Result:
  Keeps: vacation_reencoded.mp4 (highest quality)
  Deletes: vacation.avi, vacation_quicklook.mp4
  Renames: vacation_reencoded.mp4 → vacation.mp4
```

## How Broken Video Detection Works

VideoSentinel uses multiple techniques to identify corrupted, incomplete, or problematic video files:

### 1. File Integrity Check (Deep Scan)

When using the `--deep-scan` flag, VideoSentinel performs a thorough integrity check:

```bash
python video_sentinel.py /path/to/videos --check-issues --deep-scan
```

**How it works:**
- Uses `ffmpeg` to decode the entire video without saving output
- Captures all errors, warnings, and corruption issues during decoding
- Detects frame corruption, codec errors, and container problems
- **Note:** This is slower as it must process every frame

**Example command used:**
```bash
ffmpeg -v error -i video.mp4 -f null -
```

Issues detected:
- Corrupted frames or packet data
- Codec decoding errors
- Container format issues
- Audio/video sync problems

### 2. Incomplete Video Detection (Quick Scan)

Identifies videos that weren't fully downloaded or recorded:

**How it works:**
- Uses `ffprobe` to extract video duration metadata
- Flags videos with no duration (N/A or null)
- Warns about videos shorter than 1 second
- Checks for invalid duration values

**Example issues detected:**
- Incomplete downloads (partial files)
- Recording interrupted before finalization
- Corrupted file headers
- Streaming videos without proper end markers

### 3. Missing Audio Detection

Checks if videos are missing expected audio streams:

**How it works:**
- Uses `ffprobe` to query audio stream information
- Flags videos without any audio tracks
- Useful for identifying encoding errors or corrupted audio

**Example command used:**
```bash
ffprobe -select_streams a:0 -show_entries stream=codec_type
```

### 4. Unusual Specification Detection

Identifies videos with abnormal properties that may indicate problems:

**Checks performed:**
- **Invalid dimensions**: Width or height equals 0
- **Extremely low resolution**: Below 320x240
- **Unusual aspect ratios**: Less than 0.5 or greater than 3.0 (e.g., 5:1, 1:10)
- **Invalid frame rates**: 0 FPS (broken) or unreasonably high (>120 FPS)

**Why this matters:**
- Invalid dimensions usually indicate header corruption
- Extreme aspect ratios often result from encoding errors
- Zero FPS means the video won't play properly
- Unusual specs can indicate partial corruption

### Issue Severity Levels

VideoSentinel categorizes issues into three severity levels:

- **✗ CRITICAL**: Prevents video playback or indicates severe corruption
  - Corrupted frames
  - Invalid dimensions (0x0)
  - No duration (incomplete file)
  - Decoding failures

- **⚠ WARNING**: Video may play but has problems
  - Missing audio stream
  - Very short duration
  - Frame corruption in non-critical sections

- **ℹ INFO**: Unusual but not necessarily problematic
  - Low resolution
  - Unusual aspect ratio
  - High frame rate (120+ FPS)

### Example Output

```bash
python video_sentinel.py ~/Videos --check-issues --deep-scan
```

```
ENCODING ISSUE DETECTION (Deep scan mode: decoding entire videos)
================================================================================

vacation_video.mp4:
  ✗ [CRITICAL] corruption: Error decoding frame 1547 - invalid data
  ⚠ [WARNING] no_audio: Video has no audio stream

download_incomplete.mp4:
  ✗ [CRITICAL] incomplete: Video has no duration (possibly incomplete)

old_recording.avi:
  ℹ [INFO] low_resolution: Unusually low resolution: 160x120
  ℹ [INFO] unusual_aspect: Unusual aspect ratio: 0.33

Summary: 3 videos with issues
  Critical: 3
  Warnings: 2
```

### Quick vs Deep Scan

**Quick Scan** (default):
- Fast metadata checks only
- Detects incomplete files, missing audio, invalid specs
- No full video decoding
- Recommended for large libraries

**Deep Scan** (`--deep-scan`):
- Full video decoding and integrity check
- Detects frame-level corruption
- Much slower (depends on video length)
- Recommended when you suspect corruption

## Debugging with Verbose Mode

The `-v` or `--verbose` flag enables detailed output for debugging encoding issues and understanding what VideoSentinel is doing:

**Normal mode (without `-v`):**
```
[1/5] Encoding: video.avi
  [████████████████████░░░░░] 80.0% | 5.58x speed | ETA: 2m 15s
✓ [1/5] Completed: video.avi (avg 45.2 fps, 1.8x speed)
```
- Shows visual progress bar with percentage, speed, and ETA
- Compact inline progress that overwrites the same line
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
- Investigating quality issues
- Understanding codec parameters being used

**When NOT to use verbose mode:**
- Batch encoding many files (output is too verbose)
- When you just want to see progress
- Production/automated scripts

**Example usage:**
```bash
# Debug a single problematic file
python video_sentinel.py /path/to/broken.avi --check-specs --re-encode -v

# See detailed output for recovery mode
python video_sentinel.py /path/to/videos --re-encode --recover -v --file-types avi

# Debug QuickLook issues
python video_sentinel.py /path/to/videos --fix-quicklook -v

# Verbose queue mode for debugging
python video_sentinel.py /Volumes/NAS/videos --queue-mode --re-encode -v
```

**What verbose mode shows:**
- Full FFmpeg command being executed
- All FFmpeg warnings and errors
- Frame-by-frame encoding progress
- Quality (CRF) calculations and decisions
- File validation details
- Recovery mode flag explanations
- Codec tag selections (e.g., hvc1 vs hev1)

This makes verbose mode invaluable for understanding failures and debugging edge cases.

## License

MIT License - Feel free to use and modify as needed.
