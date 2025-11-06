# VideoSentinel

A Python command-line utility for managing and validating video libraries. Ensures videos are properly encoded to modern specifications (H.265/HEVC), detects duplicates using perceptual hashing, identifies encoding issues, and safely re-encodes videos with intelligent quality matching. Supports batch processing with smart resume capabilities.

## Features

- **Encoding Validation**: Check if videos meet modern encoding standards (H.265/HEVC by default)
- **Advanced Duplicate Detection**: Find duplicate videos using multi-frame perceptual hashing (detects similar content even with different encoding, resolution, or quality)
- **Intelligent Duplicate Management**: Automatically keep best quality or interactively choose which duplicates to delete
- **Network Queue Mode**: Optimized pipeline for encoding files stored on network drives - downloads to local temp storage, encodes fast, then uploads back
- **Issue Detection**: Identify corrupted files, incomplete videos, and encoding problems
- **Smart Re-encoding**: Automatically re-encode videos to modern specifications with intelligent quality matching based on source bitrate
- **Replace Original Mode**: Safely replace original files with re-encoded versions after thorough validation
- **Smart Resume Support**: Interrupt and resume batch encoding jobs without losing progress
- **Real-Time Progress**: Live encoding statistics with queue position, fps, speed multiplier, and time position
- **File Type Filtering**: Target specific legacy formats (wmv, avi, mov) for selective re-encoding
- **macOS QuickLook Compatible**: All outputs optimized for instant preview in macOS Finder
- **Flexible CLI**: Multiple operation modes with configurable options

## Table of Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
  - [Basic Usage](#basic-usage)
  - [Specific Operations](#specific-operations)
  - [Re-encoding](#re-encoding)
  - [Network Queue Mode](#network-queue-mode)
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
- [How Broken Video Detection Works](#how-broken-video-detection-works)
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

Find duplicate videos:
```bash
python video_sentinel.py /path/to/videos --find-duplicates
```

Check for encoding issues:
```bash
python video_sentinel.py /path/to/videos --check-issues
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

### Additional Options

- `-r, --recursive`: Scan subdirectories recursively
- `-v, --verbose`: Enable verbose output
- `--target-codec {h264,hevc,av1}`: Target codec for re-encoding (default: hevc)
- `--file-types`: Filter re-encoding to specific file types (comma-separated, e.g., "wmv,avi,mov")
- `--replace-original`: Replace original files with re-encoded versions (deletes source, renames output)
- `--deep-scan`: Perform deep integrity check by decoding entire videos (slower but more thorough)
- `--queue-mode`: Enable network queue mode (see [Network Queue Mode](#network-queue-mode))
- `--temp-dir PATH`: Temporary directory for queue mode (default: system temp)
- `--max-temp-size GB`: Maximum temp storage size in GB for queue mode (default: 50)
- `--buffer-size N`: Number of files to buffer locally in queue mode (default: 4)

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

## Modern Encoding Specs

By default, VideoSentinel considers a video properly encoded if it meets:
- Codec: H.265/HEVC (or H.264 minimum)
- Container: MP4 or MKV
- No corruption or encoding errors

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

During batch encoding, VideoSentinel displays live progress information with queue position and encoding statistics:

**Progress display format:**
```
[1/5] Encoding: video.wmv - frame=1234 fps=45.2 time=00:01:23.45 speed=1.8x
```

**What it shows:**
- **Queue position:** `[1/5]` = encoding video 1 of 5
- **Current frame:** Number of frames encoded so far
- **Encoding speed:** Frames per second (fps) being processed
- **Time position:** Current position in the video being encoded
- **Speed multiplier:** How fast encoding is compared to real-time (1.8x = encoding 1.8× faster than playback)

**Completion messages:**
```
✓ [1/5] Completed: video.wmv (avg 45.2 fps, 1.8x speed)
✗ [1/5] Error encoding video.wmv: validation failed
```

This helps you:
- Track progress in large batch operations
- Estimate remaining time
- Identify slow-encoding videos
- Monitor encoding efficiency

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
- **Codec modernity**: AV1 > VP9 > HEVC > H.264 > older codecs
- **Resolution**: Higher resolution scores higher
- **Bitrate**: Higher bitrate typically means better quality

**Example output:**
```
Group 1:
  ✓ Keeping: movie_hevc.mp4
    (HEVC, 1920x1080, 5000 kbps)
  ✗ Deleting: movie_h264.mp4 (450.23 MB)
    (H264, 1920x1080, 3500 kbps)
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

  ★ BEST [1] movie_hevc.mp4
      Codec: HEVC, Resolution: 1920x1080
      Bitrate: 5000 kbps, Size: 350.12 MB

    #2 [2] movie_h264.mp4
      Codec: H264, Resolution: 1920x1080
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

## License

MIT License - Feel free to use and modify as needed.
