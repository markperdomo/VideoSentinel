# VideoSentinel Usage Guide

Comprehensive guide to using VideoSentinel for video library management.

## Table of Contents

- [Essential Commands](#essential-commands)
- [Interrupting and Resuming](#interrupting-and-resuming-batch-encoding)
- [Graceful Shutdown](#graceful-shutdown-with-key-press)
- [Recovering Broken Videos](#recovering-broken-or-corrupted-videos)
- [Verbose Mode](#verbose-mode-for-debugging)
- [Network Queue Mode](#network-queue-mode-for-network-storage)
- [Managing Duplicates](#managing-duplicate-videos)
- [Fixing QuickLook](#fixing-quicklook-compatibility)
- [Filtering by File Type](#filtering-by-file-type)
- [Limiting Number of Files](#limiting-number-of-files)

## Essential Commands

### Development Environment Setup

```bash
pip install -r requirements.txt
```

### Basic Operations

```bash
# Scan a directory with all checks (default behavior)
python video_sentinel.py /path/to/videos

# Process a single file
python video_sentinel.py /path/to/video.mp4

# Check encoding specifications only
python video_sentinel.py /path/to/videos --check-specs

# Recursive scan
python video_sentinel.py /path/to/videos -r --check-specs

# Verbose output (shows all FFmpeg output, useful for debugging)
python video_sentinel.py /path/to/videos -v
```

### Duplicate Detection

```bash
# Find duplicates using perceptual hashing
python video_sentinel.py /path/to/videos --find-duplicates

# Find duplicates by filename only (fast, no perceptual hashing)
# Matches files with same name ignoring extension and _reencoded/_quicklook suffixes
# Useful when original files are broken and can't generate perceptual hashes
python video_sentinel.py /path/to/videos --filename-duplicates

# Find duplicates and automatically keep best quality
python video_sentinel.py /path/to/videos --find-duplicates --duplicate-action auto-best

# Find duplicates and interactively choose what to keep
python video_sentinel.py /path/to/videos --find-duplicates --duplicate-action interactive

# Find filename duplicates and auto-keep best (fast, works with broken originals)
python video_sentinel.py /path/to/videos --filename-duplicates --duplicate-action auto-best

# Find duplicates only among AVI files
python video_sentinel.py /path/to/videos --find-duplicates --file-types avi
```

### Issue Detection

```bash
# Check for encoding issues
python video_sentinel.py /path/to/videos --check-issues

# Deep scan (decodes entire videos to find corruption - slow)
python video_sentinel.py /path/to/videos --check-issues --deep-scan

# Check issues only for WMV and FLV files
python video_sentinel.py /path/to/videos --check-issues --file-types wmv,flv
```

### Video Re-encoding

```bash
# Re-encode non-compliant videos with smart quality matching
python video_sentinel.py /path/to/videos --check-specs --re-encode

# Re-encode a single file
python video_sentinel.py /path/to/video.avi --check-specs --re-encode

# Replace original files with re-encoded versions (deletes source, renames output)
# Safe to interrupt and resume - automatically detects completed/partial work
python video_sentinel.py /path/to/videos --check-specs --re-encode --replace-original

# Process only specific file types (filters at file discovery - applies to all operations)
python video_sentinel.py /path/to/videos --check-specs --re-encode --file-types wmv,avi,mov
```

### Error Recovery

```bash
# Re-encode with error recovery mode (salvage broken/corrupted files)
python video_sentinel.py /path/to/videos --check-specs --re-encode --recover

# Recover a single broken file
python video_sentinel.py /path/to/broken.avi --re-encode --recover

# Filter to specific broken file types
python video_sentinel.py /path/to/videos --check-specs --re-encode --recover --file-types avi,wmv
```

### Downscaling

```bash
# Downscale videos larger than 1080p to maximum 1920x1080 (preserves aspect ratio)
python video_sentinel.py /path/to/videos --check-specs --re-encode --downscale-1080p

# Downscale a single 4K file
python video_sentinel.py /path/to/4k_movie.mkv --re-encode --downscale-1080p --replace-original

# Downscale 4K videos and replace originals (great for space savings)
python video_sentinel.py /path/to/videos --check-specs --re-encode --downscale-1080p --replace-original
```

### QuickLook Compatibility

```bash
# Fix QuickLook compatibility (fast remux MKV→MP4, fix HEVC tags)
python video_sentinel.py /path/to/videos --check-specs --fix-quicklook

# Fix QuickLook compatibility and replace originals
python video_sentinel.py /path/to/videos --check-specs --fix-quicklook --replace-original
```

### Network Queue Mode

```bash
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

## Interrupting and Resuming Batch Encoding

The encoder supports safe interruption and intelligent resume:

### Safe to Interrupt at Any Time

- Press Ctrl+C to stop encoding
- No corrupted files will be used (validation ensures integrity)
- Partial encodes are automatically detected and removed

### Automatic Resume on Restart

```bash
# Start batch encoding
python video_sentinel.py /videos --re-encode --replace-original

# Interrupt with Ctrl+C after some files complete

# Resume - automatically skips completed files
python video_sentinel.py /videos --re-encode --replace-original
```

### What Happens on Resume

1. ✓ Detects valid `_reencoded` files from previous run
2. ✓ Skips re-encoding those files (shows "Resuming: file.avi (already encoded)")
3. ✓ Completes any interrupted replacements
4. ✓ Continues encoding remaining files
5. ✓ Validates all outputs before using them

### Resume Behavior Examples

- **Completed encode, not replaced:** Skips encoding, completes replacement
- **Fully completed:** Shows "Replacement already completed, skipping"
- **Partial/corrupted encode:** Deletes invalid file, re-encodes from scratch
- **Never encoded:** Encodes normally

This means you can safely interrupt large batch jobs and resume without wasting work!

## Graceful Shutdown with Key Press

For more controlled shutdown during batch encoding, VideoSentinel supports graceful shutdown by pressing the 'q' key:

### How It Works

- Press the `q` key at any time during encoding
- VideoSentinel will finish the current video, then stop
- Progress is saved automatically (same as Ctrl+C)
- Next run will resume from where you left off

### Usage

```bash
# Start batch encoding
python video_sentinel.py /videos --re-encode --replace-original

# During encoding, press 'q' to stop gracefully
# The current video will finish encoding, then the process stops
```

### Key Differences from Ctrl+C

- **Ctrl+C**: Immediate interrupt (may stop mid-encode, but safe due to validation)
- **'q' key**: Graceful shutdown (finishes current video first)
- Both are safe and support resume

### When to Use

- Use `q` when you want to stop cleanly after the current video completes
- Use Ctrl+C when you need to stop immediately

### Important Notes

- The 'q' key listener works in both standard batch mode and queue mode
- In queue mode, pressing 'q' will finish the current encoding, complete any pending uploads, and then exit
- **tmux/screen users**: The 'q' key listener is automatically disabled when running inside tmux or screen to avoid terminal compatibility issues. Use Ctrl+C instead for graceful interruption.

## Recovering Broken or Corrupted Videos

VideoSentinel can attempt to recover broken videos using FFmpeg's error recovery mode. This is useful when:

- Original files are corrupted and won't play properly
- Videos fail to encode with standard settings
- Files have broken timestamps or missing metadata
- Perceptual hashing fails because frames can't be extracted

### How Error Recovery Works

The `--recover` flag enables FFmpeg's error-tolerant flags:

**Input options (before `-i`):**
- `-err_detect ignore_err`: Ignores decoding errors and continues processing
- `-fflags +genpts+discardcorrupt+igndts`: Generates missing timestamps, discards corrupted packets, ignores DTS errors
- `-ignore_unknown`: Ignores unknown stream types

**Output options (after `-i`):**
- `-max_muxing_queue_size 1024`: Increases buffer for problematic files
- `-max_error_rate 1.0`: Allows 100% error rate (doesn't fail on errors)

### Usage

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

### What Recovery Mode Can Fix

- ✓ Videos with corrupted frames (skips bad frames)
- ✓ Files with broken timestamps (regenerates them)
- ✓ Videos missing metadata
- ✓ Files that crash standard ffmpeg encoding
- ✓ Partially downloaded or incomplete files

### Recovery Mode Validation

When `--recover` is enabled, output validation becomes more lenient:

- Allows recovered files to have different durations than source (corrupted sources may have wrong metadata)
- Allows files with missing duration metadata (common in heavily corrupted recoveries)
- Still validates: file exists, has video stream, has valid dimensions, and is readable by ffprobe
- This prevents false-negative validation failures for successfully recovered files

### Limitations

- Cannot recover completely unreadable files (0 bytes, wrong format, etc.)
- May result in shorter duration if large portions are corrupted
- Audio sync issues if significant corruption
- Quality depends on how much of the file is recoverable

### Best Practices

1. Try standard encoding first (`--re-encode` without `--recover`)
2. Use `--recover` only for files that fail standard encoding
3. Always validate recovered files play correctly before deleting originals
4. Combine with `--filename-duplicates` to identify and keep best versions

## Verbose Mode for Debugging

The `-v` or `--verbose` flag enables detailed output for debugging encoding issues:

### Normal Mode (without `-v`)

```
[1/5] Encoding: video.avi
  Encoding: frame=1234 fps=45.2 time=00:01:23.45 speed=1.8x
✓ [1/5] Completed: video.avi (avg 45.2 fps, 1.8x speed)
```

- Shows compact inline progress that overwrites the same line
- Clean, minimal output

### Verbose Mode (with `-v`)

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

### When to Use Verbose Mode

- Debugging encoding failures
- Understanding what recovery mode is doing
- Troubleshooting corrupted files
- Seeing detailed FFmpeg warnings

### When NOT to Use Verbose Mode

- Batch encoding many files (output is too verbose)
- When you just want to see progress
- Production/automated scripts

## Network Queue Mode for Network Storage

When encoding videos on network drives (NAS, SMB shares, etc.), network I/O significantly slows encoding. Queue mode solves this with a three-stage parallel pipeline:

### How It Works

```
Thread 1 (Download): Network → Local temp → [buffer] →
Thread 2 (Encode):                          → [buffer] → Encoded local →
Thread 3 (Upload):                                                      → Network
```

### Usage

```bash
# Basic queue mode
python video_sentinel.py /Volumes/NetworkDrive/videos --check-specs --re-encode --queue-mode

# With custom temp dir and limits
python video_sentinel.py /Volumes/NetworkDrive/videos --check-specs --re-encode --queue-mode \
  --temp-dir /Users/you/temp --buffer-size 3 --max-temp-size 100
```

### Key Features

- **Parallel operations**: Download next while encoding current while uploading previous
- **Smart buffering**: Configurable (default 4 files) to balance speed and disk usage
- **Storage monitoring**: Pauses downloads if temp storage exceeds limit
- **Resume support**: Saves state to disk, handles Ctrl+C gracefully
- **Network compatibility**: Falls back from `copy2` to `copy` for filesystems that don't support metadata

### Performance

- Traditional (network I/O): ~15-20 fps encoding
- Queue mode (local SSD): ~45-60 fps encoding
- **2-3x speed improvement!**

### Architecture Details

- Download/upload use separate threads (I/O-bound, benefits from threading)
- Encoding uses main thread (CPU-bound, no threading benefit)
- Queue states: PENDING → DOWNLOADING → LOCAL → ENCODING → UPLOADING → COMPLETE
- State persisted to JSON for resume capability

### Failure Handling in Queue Mode

When an encode fails in queue mode:

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

3. **Resume behavior:**
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

### Safety Guarantees

- Failed encodes never delete or modify original source files
- Temp files are cleaned up to avoid disk space waste
- State is saved so you can review what failed
- Can safely interrupt and resume without losing failure information

### Monitoring Queue Status

Queue state is persisted to disk for monitoring and resume support:

1. **State file location:**
   ```
   Default: /tmp/videosentinel/queue_state.json
   Custom:  <your-temp-dir>/queue_state.json
   ```

2. **Temp directory location:**
   ```
   Default: /tmp/videosentinel/
   Custom:  <your-temp-dir>/
   ```

3. **State file contents (JSON):**
   - List of all files with their current state
   - Error messages for failed files
   - File paths (source, local temp, output, final destination)
   - Can be inspected manually or with monitoring script

4. **Temp directory contents:**
   - `download_<filename>`: Downloaded files waiting to encode
   - `encoded_<filename>.mp4`: Encoded files waiting to upload
   - `queue_state.json`: State file
   - **Note**: Temp files are automatically deleted when:
     - Encoding fails (downloaded file cleaned up)
     - Upload succeeds (both download and encoded files cleaned up)
     - `--clear-queue` is run

5. **Monitoring with included script:**
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

6. **Manual state file inspection:**
   ```bash
   # View the raw state file
   cat /tmp/videosentinel/queue_state.json | python -m json.tool

   # Check temp directory size
   du -sh /tmp/videosentinel/

   # List temp files
   ls -lh /tmp/videosentinel/
   ```

## Managing Duplicate Videos

VideoSentinel can automatically manage duplicates with `--duplicate-action`:

### Three Modes

1. **report** (default) - Just list duplicates, no action
2. **auto-best** - Automatically keep highest quality, delete others
3. **interactive** - Ask for each duplicate group

### Quality Ranking Algorithm

The quality ranking algorithm prioritizes files based on multiple factors:

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

### Usage Examples

```bash
# Auto-best: automatically keep best, delete others (asks for confirmation)
python video_sentinel.py ~/Videos --find-duplicates --duplicate-action auto-best

# Interactive: shows ranked list, lets you choose per group
python video_sentinel.py ~/Videos --find-duplicates --duplicate-action interactive
```

### Safety Features

- Auto-best mode asks "Delete N files? (yes/no)" before deleting
- Interactive mode confirms choice for each group
- Shows space freed after deletion
- Handles deletion errors gracefully

## Fixing QuickLook Compatibility

VideoSentinel can automatically fix macOS QuickLook/Finder preview issues for videos that are already properly encoded (HEVC/H.264) but won't preview.

### Common QuickLook Issues

1. **Wrong container**: MKV instead of MP4 (QuickLook requires MP4)
2. **Wrong HEVC tag**: hev1 instead of hvc1 (Apple devices need hvc1)
3. **Wrong pixel format**: yuv422p instead of yuv420p (compatibility issue)
4. **Missing faststart**: Metadata at end of file (prevents instant preview)

### Two-Tier Fixing Approach

**1. Fast remux (no re-encoding)** - Takes seconds, not minutes:
- Changes container from MKV to MP4 using `ffmpeg -c copy`
- Fixes HEVC tag with `-tag:v hvc1`
- Adds `-movflags faststart` for instant preview
- No quality loss (just container change)

**2. Full re-encode** - Only when necessary:
- Wrong pixel format requires re-encoding with `-pix_fmt yuv420p`
- Uses same smart quality matching as regular re-encoding

### Usage

```bash
# Check what needs fixing
python video_sentinel.py /Videos --check-specs --fix-quicklook

# Fix and replace originals
python video_sentinel.py /Videos --check-specs --fix-quicklook --replace-original

# Works with queue mode for network storage
python video_sentinel.py /Volumes/NAS/videos --check-specs --fix-quicklook --queue-mode --replace-original
```

### Smart Resume Support

- Automatically checks for existing `_quicklook` or `_reencoded` files before processing
- Validates existing outputs (size, format, duration)
- Skips files with valid outputs to avoid re-processing
- Safe to interrupt (Ctrl+C) and resume - picks up where it left off
- Works with both direct mode and queue mode

### Why This Is Useful

- Many HEVC videos in MKV containers won't preview in Finder
- Re-encoding would take hours, remuxing takes seconds
- Ensures entire library works with QuickLook/spacebar preview
- Resume capability saves time on large batch jobs

## Filtering by File Type

The `--file-types` flag filters files at the discovery stage for maximum efficiency:

### How It Works

- Filters files when scanning the directory (before any analysis)
- Only matching files are loaded, checked, analyzed, and processed
- Applies to all operations: spec checking, duplicate detection, issue detection, re-encoding
- More efficient than loading all files then filtering later

### Usage Examples

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

### Benefits

- **Faster scanning**: Only searches for specified file types
- **Less memory**: Doesn't load unnecessary files into memory
- **Cleaner output**: Only shows results for files you care about
- **Targeted operations**: Perfect for cleaning up legacy format collections

### Implementation Details

- Supports any extension: wmv, avi, mov, mkv, mp4, flv, webm, m4v, mpg, mpeg
- File type parsing: `video_sentinel.py:417-424`
- Filter application: `video_analyzer.py:313-358` (`find_videos()` method)

## Limiting Number of Files

The `--max-files` flag limits the maximum number of files to process in a single run, making it easy to break large jobs into manageable batches.

### How It Works

- Files are discovered normally (respects `--file-types` and `--recursive` flags)
- After discovery, the list is limited to the first N files
- Processing proceeds normally with all other flags
- Perfect for testing, incremental processing, or managing system resources

### Usage Examples

```bash
# Process only the first 100 files found
python video_sentinel.py /videos --check-specs --re-encode --max-files 100

# Test re-encoding settings on first 5 files
python video_sentinel.py /videos --check-specs --re-encode --max-files 5 --verbose

# Find duplicates in batches of 50 files
python video_sentinel.py /videos --find-duplicates --max-files 50

# Combine with file type filtering
python video_sentinel.py /videos --check-specs --re-encode --file-types wmv,avi --max-files 20

# Process first 10 files with queue mode
python video_sentinel.py /Volumes/NAS/videos --check-specs --re-encode --queue-mode --max-files 10
```

### Benefits

- **Manageable batches**: Break large libraries into smaller, manageable chunks
- **Resource control**: Limit disk space, CPU time, or network usage per run
- **Testing**: Quickly test settings on a small subset before processing everything
- **Incremental progress**: Run multiple times to gradually process entire library
- **Predictable runtime**: Know approximately how long a run will take

### Workflow Tips

**Incremental Processing**:
```bash
# Run 1: Process first 100 files
python video_sentinel.py /videos --check-specs --re-encode --max-files 100 --replace-original

# Run 2: Process next batch (already-encoded files are skipped automatically)
python video_sentinel.py /videos --check-specs --re-encode --max-files 100 --replace-original

# Continue until all files are processed
```

**Testing Before Bulk Operations**:
```bash
# Step 1: Test on 5 files first
python video_sentinel.py /videos --check-specs --re-encode --max-files 5

# Step 2: Review output quality and settings

# Step 3: Process all files with confidence
python video_sentinel.py /videos --check-specs --re-encode --replace-original
```

### Implementation Details

- Argument parsing: `video_sentinel.py:370-374`
- Limit application: `video_sentinel.py:531-534`
- Applied after file discovery but before any processing begins
