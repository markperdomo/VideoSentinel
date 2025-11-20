#!/usr/bin/env python3
"""
VideoSentinel - A CLI utility for video file management and validation

Features:
- Analyze video encoding specs (codec, resolution, bitrate)
- Detect duplicate videos using perceptual hashing
- Identify encoding issues and corrupted files
- Re-encode videos to modern H.265/HEVC standards
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional
from tqdm import tqdm

from video_analyzer import VideoAnalyzer, VideoInfo
from duplicate_detector import DuplicateDetector
from issue_detector import IssueDetector
from encoder import VideoEncoder
from network_queue_manager import NetworkQueueManager
from shutdown_manager import start_shutdown_listener, stop_shutdown_listener


# ANSI color codes for terminal output
class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

    @staticmethod
    def green(text):
        return f"{Colors.GREEN}{text}{Colors.RESET}"

    @staticmethod
    def red(text):
        return f"{Colors.RED}{text}{Colors.RESET}"

    @staticmethod
    def yellow(text):
        return f"{Colors.YELLOW}{text}{Colors.RESET}"

    @staticmethod
    def bold(text):
        return f"{Colors.BOLD}{text}{Colors.RESET}"


def rank_video_quality(video_path: Path, video_info: VideoInfo, analyzer: VideoAnalyzer = None) -> int:
    """
    Rank video quality for duplicate selection
    Higher score = better quality

    Considers:
    - Codec modernity
    - Resolution
    - Bitrate (normalized by codec efficiency)
    - QuickLook compatibility (macOS)
    - Recent processing (newly encoded files)
    """
    score = 0

    # Codec scoring (modern codecs are better)
    codec_scores = {
        'av1': 1000,
        'vp9': 900,
        'hevc': 800,
        'hvc1': 800,  # HEVC variant (macOS QuickLook compatible)
        'h265': 800,
        'h264': 400,
        'avc1': 400,  # H.264 variant
        'avc': 400,   # H.264 variant
        'mpeg4': 200,
        'mpeg2': 100,
        'wmv': 50,
        'xvid': 50,
    }
    score += codec_scores.get(video_info.codec.lower(), 0)

    # Resolution scoring (pixels)
    score += video_info.width * video_info.height // 1000

    # Bitrate scoring - normalized by codec efficiency
    # Modern codecs need less bitrate for same quality, so we normalize to H.264 equivalent
    codec_efficiency = {
        'av1': 2.5,    # AV1 is ~2.5x more efficient than H.264
        'vp9': 2.0,    # VP9 is ~2x more efficient than H.264
        'hevc': 2.0,   # HEVC is ~2x more efficient than H.264
        'hvc1': 2.0,   # HEVC variant
        'h265': 2.0,   # HEVC alternate name
        'h264': 1.0,   # Baseline
        'avc1': 1.0,   # H.264 variant
        'avc': 1.0,    # H.264 variant
        'mpeg4': 0.6,  # MPEG4 is less efficient than H.264
        'mpeg2': 0.4,  # MPEG2 is much less efficient
        'wmv': 0.5,    # Old codecs are less efficient
        'xvid': 0.6,
    }

    efficiency = codec_efficiency.get(video_info.codec.lower(), 1.0)
    # Normalize bitrate to H.264 equivalent (multiply by efficiency factor)
    normalized_bitrate = video_info.bitrate * efficiency
    score += int(normalized_bitrate // 10000)

    # Newly processed file bonus (HIGHEST PRIORITY - always prefer over originals)
    # Files with _quicklook or _reencoded suffixes are newly processed
    # This bonus is intentionally VERY high to ensure newly processed files
    # always beat originals, even if original is 4K and new file is 1080p
    stem_lower = video_path.stem.lower()
    if '_quicklook' in stem_lower or '_reencoded' in stem_lower:
        score += 50000  # Massive bonus to heavily favor newly processed files

    # QuickLook compatibility bonus (significant advantage for macOS users)
    if analyzer:
        compat = analyzer.check_quicklook_compatibility(video_path)
        if compat.get('compatible'):
            score += 5000  # Big bonus for QuickLook compatible files

    # Container preference (MP4 > MKV > others for compatibility)
    container_bonus = {
        '.mp4': 300,
        '.m4v': 300,
        '.mkv': 100,
        '.webm': 100,
    }
    score += container_bonus.get(video_path.suffix.lower(), 0)

    return score


def handle_duplicate_group(
    group_name: str,
    videos: List[Path],
    analyzer: VideoAnalyzer,
    action: str,
    verbose: bool = False
) -> tuple[List[Path], Optional[Path]]:
    """
    Handle a duplicate group based on action

    Args:
        group_name: Name of the duplicate group
        videos: List of duplicate video paths
        analyzer: VideoAnalyzer instance
        action: 'report', 'interactive', or 'auto-best'
        verbose: Enable verbose output

    Returns:
        Tuple of (videos to delete, video to keep)
    """
    to_delete = []
    to_keep = None

    if action == 'report':
        # Just report, no action
        return to_delete, to_keep

    # Get video info for all duplicates
    video_infos = {}
    for video in videos:
        info = analyzer.get_video_info(video)
        if info:
            video_infos[video] = info

    if not video_infos:
        print(f"  {Colors.yellow('Warning: Could not analyze videos in this group')}")
        return to_delete, to_keep

    # Rank videos by quality (including QuickLook compatibility and container preferences)
    ranked_videos = sorted(
        video_infos.keys(),
        key=lambda v: rank_video_quality(v, video_infos[v], analyzer),
        reverse=True
    )

    if action == 'auto-best':
        # Keep the best, mark others for deletion
        best_video = ranked_videos[0]
        to_keep = best_video
        to_delete = [v for v in ranked_videos if v != best_video]

        print(f"  {Colors.green('✓ Keeping:')} {best_video.name}")
        info = video_infos[best_video]

        # Check QuickLook compatibility for the kept file
        compat = analyzer.check_quicklook_compatibility(best_video)
        ql_status = " [QuickLook ✓]" if compat.get('compatible') else ""

        print(f"    ({info.codec.upper()}, {info.width}x{info.height}, {info.bitrate//1000} kbps{ql_status})")

        for video in to_delete:
            info = video_infos[video]
            file_size_mb = video.stat().st_size / (1024 * 1024)

            # Check QuickLook compatibility for files being deleted
            compat = analyzer.check_quicklook_compatibility(video)
            ql_status = " [QuickLook ✓]" if compat.get('compatible') else ""

            print(f"  {Colors.red('✗ Deleting:')} {video.name} ({file_size_mb:.2f} MB)")
            print(f"    ({info.codec.upper()}, {info.width}x{info.height}, {info.bitrate//1000} kbps{ql_status})")

    elif action == 'interactive':
        # Show options and let user choose
        print()
        print(f"{Colors.bold(group_name)} - {len(videos)} duplicates found:")
        print()

        for idx, video in enumerate(ranked_videos, 1):
            info = video_infos[video]
            file_size_mb = video.stat().st_size / (1024 * 1024)
            quality_rank = "★ BEST" if idx == 1 else f"  #{idx}"

            # Check QuickLook compatibility
            compat = analyzer.check_quicklook_compatibility(video)
            ql_badge = " [QuickLook ✓]" if compat.get('compatible') else ""

            print(f"  {quality_rank} [{idx}] {video.name}{ql_badge}")
            print(f"      Codec: {info.codec.upper()}, Resolution: {info.width}x{info.height}")
            print(f"      Bitrate: {info.bitrate//1000} kbps, Size: {file_size_mb:.2f} MB")
            print()

        print(f"Options:")
        print(f"  1-{len(ranked_videos)}: Keep that video, delete others")
        print(f"  0 or Enter: Keep all (no action)")
        print()

        choice = input(f"Your choice: ").strip().replace('\r', '')

        if choice.isdigit() and 1 <= int(choice) <= len(ranked_videos):
            keep_idx = int(choice) - 1
            keep_video = ranked_videos[keep_idx]
            to_keep = keep_video
            to_delete = [v for v in ranked_videos if v != keep_video]

            print()
            print(f"  {Colors.green('✓ Keeping:')} {keep_video.name}")
            for video in to_delete:
                file_size_mb = video.stat().st_size / (1024 * 1024)
                print(f"  {Colors.red('✗ Will delete:')} {video.name} ({file_size_mb:.2f} MB)")
        else:
            print(f"  {Colors.yellow('→ No action, keeping all')}")

    return to_delete, to_keep


def main():
    """Main entry point for VideoSentinel CLI"""
    # Reset terminal to normal mode at startup (in case previous run left it in cbreak mode)
    if sys.stdin.isatty():
        try:
            import termios
            fd = sys.stdin.fileno()
            # Get current settings
            try:
                attrs = termios.tcgetattr(fd)
                # Enable canonical mode (ICANON) and echo (ECHO) for normal line-buffered input
                # This reverses cbreak/raw mode settings
                attrs[3] |= termios.ICANON | termios.ECHO  # lflag
                termios.tcsetattr(fd, termios.TCSANOW, attrs)
            except:
                pass
        except ImportError:
            # On Windows or systems without termios, skip
            pass

    parser = argparse.ArgumentParser(
        description='VideoSentinel - Manage and validate your video library',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        'path',
        type=Path,
        nargs='?',
        help='Video file or directory to analyze (not required for --clear-queue)'
    )

    parser.add_argument(
        '-r', '--recursive',
        action='store_true',
        help='Recursively scan subdirectories'
    )

    parser.add_argument(
        '--check-specs',
        action='store_true',
        help='Check if videos meet modern encoding specifications'
    )

    parser.add_argument(
        '--find-duplicates',
        action='store_true',
        help='Find duplicate videos using perceptual hashing'
    )

    parser.add_argument(
        '--filename-duplicates',
        action='store_true',
        help='Find duplicates by filename only (fast, no perceptual hashing). Matches files with same name ignoring extension and _reencoded/_quicklook suffixes.'
    )

    parser.add_argument(
        '--fix-quicklook',
        action='store_true',
        help='Fix QuickLook compatibility (remux MKV→MP4, fix HEVC tags, re-encode if needed)'
    )

    parser.add_argument(
        '--duplicate-action',
        choices=['report', 'interactive', 'auto-best'],
        default='report',
        help='Action for duplicate groups: report (default, no action), interactive (ask for each group), auto-best (keep best quality, delete others)'
    )

    parser.add_argument(
        '--check-issues',
        action='store_true',
        help='Detect encoding issues and corrupted files'
    )

    parser.add_argument(
        '--deep-scan',
        action='store_true',
        help='Perform deep integrity check (slower, decodes entire video to find corruption)'
    )

    parser.add_argument(
        '--re-encode',
        action='store_true',
        help='Automatically re-encode videos that don\'t meet specs'
    )

    parser.add_argument(
        '--recover',
        action='store_true',
        help='Enable error recovery mode when re-encoding. Uses FFmpeg flags to ignore errors, generate missing timestamps, and salvage corrupted/broken videos. Useful for recovering broken files.'
    )

    parser.add_argument(
        '--downscale-1080p',
        action='store_true',
        help='Downscale videos larger than 1080p to a maximum of 1920x1080 while preserving aspect ratio. Useful for reducing file size and ensuring compatibility.'
    )

    parser.add_argument(
        '--target-codec',
        default='hevc',
        choices=['h264', 'hevc', 'av1'],
        help='Target codec for re-encoding (default: hevc)'
    )

    parser.add_argument(
        '--output-dir',
        type=Path,
        help='Directory for re-encoded videos (default: same as source with _reencoded suffix)'
    )

    parser.add_argument(
        '--file-types',
        type=str,
        help='Filter re-encoding to specific file types (comma-separated, e.g., "wmv,avi,mov")'
    )

    parser.add_argument(
        '--max-files',
        type=int,
        help='Maximum number of files to process in this run (stops searching after N files found)'
    )

    parser.add_argument(
        '--replace-original',
        action='store_true',
        help='Replace original files with re-encoded versions (deletes source, renames output)'
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )

    parser.add_argument(
        '--queue-mode',
        action='store_true',
        help='Enable queue mode for network storage (downloads files locally, encodes, then uploads)'
    )

    parser.add_argument(
        '--temp-dir',
        type=Path,
        help='Temporary directory for queue mode (default: system temp)'
    )

    parser.add_argument(
        '--max-temp-size',
        type=float,
        default=50.0,
        help='Maximum temp storage size in GB for queue mode (default: 50)'
    )

    parser.add_argument(
        '--buffer-size',
        type=int,
        default=4,
        help='Number of files to buffer locally in queue mode (default: 4)'
    )

    parser.add_argument(
        '--clear-queue',
        action='store_true',
        help='Clear queue state and temp files from previous queue mode session'
    )

    args = parser.parse_args()

    # Handle --clear-queue flag (can be used standalone)
    if args.clear_queue:
        print("="*80)
        print("CLEARING QUEUE STATE")
        print("="*80)

        queue_manager = NetworkQueueManager(
            temp_dir=args.temp_dir,
            verbose=args.verbose
        )

        temp_dir = queue_manager.temp_dir
        state_file = queue_manager.state_file

        if state_file.exists():
            print(f"Removing state file: {state_file}")
            state_file.unlink()
        else:
            print(f"No state file found at: {state_file}")

        # Count and remove temp files
        temp_files = list(temp_dir.glob("*"))
        if temp_files:
            total_size = sum(f.stat().st_size for f in temp_files if f.is_file())
            print(f"Removing {len(temp_files)} temp files ({total_size / (1024**2):.2f} MB)")
            queue_manager.cleanup()
            print(f"{Colors.green('✓')} Queue cleared successfully")
        else:
            print("No temp files found")

        print("="*80)
        sys.exit(0)

    # Validate input path (required unless using --clear-queue)
    if not args.path:
        print(f"Error: Path argument is required (provide a video file or directory)", file=sys.stderr)
        sys.exit(1)

    if not args.path.exists():
        print(f"Error: Path '{args.path}' does not exist", file=sys.stderr)
        sys.exit(1)

    # Check if path is a file or directory
    is_single_file = args.path.is_file()
    is_directory = args.path.is_dir()

    if not is_single_file and not is_directory:
        print(f"Error: '{args.path}' is not a file or directory", file=sys.stderr)
        sys.exit(1)

    # If re-encode is specified, automatically enable check-specs (required for re-encoding)
    if args.re_encode and not args.check_specs:
        args.check_specs = True

    # If fix-quicklook is specified, automatically enable check-specs
    if args.fix_quicklook and not args.check_specs:
        args.check_specs = True

    # If no action specified at all, show all checks by default
    if not any([args.check_specs, args.find_duplicates, args.filename_duplicates, args.check_issues, args.re_encode, args.fix_quicklook]):
        args.check_specs = True
        args.find_duplicates = True
        args.check_issues = True

    # Check ffmpeg availability
    encoder = VideoEncoder(verbose=args.verbose, recovery_mode=args.recover, downscale_1080p=args.downscale_1080p)
    if not encoder.check_ffmpeg_available():
        print("Error: ffmpeg is not installed or not in PATH", file=sys.stderr)
        print("Please install ffmpeg to use VideoSentinel", file=sys.stderr)
        sys.exit(1)

    print("="*80)
    print(f"VideoSentinel - Video Library Manager")
    print("="*80)
    if is_single_file:
        print(f"Processing file: {args.path}")
    else:
        print(f"Scanning directory: {args.path}")
        print(f"Recursive scan: {args.recursive}")
    print(f"Target codec: {args.target_codec.upper()}")
    print("="*80)
    print()

    # Initialize components
    # If downscale_1080p enabled, mark videos >1080p as non-compliant
    max_resolution = (1920, 1080) if args.downscale_1080p else None
    analyzer = VideoAnalyzer(verbose=args.verbose, max_resolution=max_resolution)
    duplicate_detector = DuplicateDetector(verbose=args.verbose)
    issue_detector = IssueDetector(verbose=args.verbose)

    # Parse file types filter if specified
    file_types_filter = None
    if args.file_types:
        file_types_filter = [
            ext.strip().lower().lstrip('.')
            for ext in args.file_types.split(',')
        ]
        print(f"File type filter: {', '.join(file_types_filter).upper()}")

    # Find all video files (or use single file)
    if is_single_file:
        print(f"Processing single file: {args.path.name}")
        video_files = [args.path]
    else:
        print("Finding video files...")
        video_files = analyzer.find_videos(
            args.path,
            recursive=args.recursive,
            file_types=file_types_filter
        )

    # Note: For re-encoding operations, max-files limit is applied AFTER filtering
    # to files that need encoding (smarter behavior). For other operations, apply it here.
    if args.max_files and not args.re_encode and len(video_files) > args.max_files:
        print(f"Limiting to first {args.max_files} files (found {len(video_files)} total)")
        video_files = video_files[:args.max_files]

    if not video_files:
        if file_types_filter:
            print(f"No video files found matching types: {', '.join(file_types_filter).upper()}")
        else:
            print("No video files found.")
        sys.exit(0)

    print(f"Found {len(video_files)} video files")
    print()

    # Check encoding specifications
    if args.check_specs:
        print("="*80)
        print("ENCODING SPECIFICATION CHECK")
        print("="*80)
        print()

        compliant_videos = []
        non_compliant_videos = []

        for video_path in tqdm(video_files, desc="Analyzing videos", unit="video"):
            video_info = analyzer.get_video_info(video_path)

            if not video_info or not video_info.is_valid:
                tqdm.write(Colors.yellow(f"✗ {video_path.name}: Unable to analyze"))
                continue

            is_compliant = analyzer.meets_modern_specs(video_info)

            if is_compliant:
                compliant_videos.append(video_path)
                tqdm.write(Colors.green(f"✓ {video_path.name}: Meets specs ({video_info.codec.upper()}, {video_info.width}x{video_info.height})"))
            else:
                non_compliant_videos.append((video_path, video_info))
                tqdm.write(Colors.red(f"✗ {video_path.name}"))

                # Show specific reasons for non-compliance
                codec_lower = video_info.codec.lower()
                codec_compliant = codec_lower in analyzer.MODERN_CODECS
                resolution_compliant = True

                if analyzer.max_resolution is not None:
                    max_width, max_height = analyzer.max_resolution
                    resolution_compliant = video_info.width <= max_width and video_info.height <= max_height

                if not codec_compliant:
                    tqdm.write(f"    Codec: {Colors.red(video_info.codec.upper())} (should be {Colors.green('H.265/HEVC')}, {Colors.green('AV1')}, or {Colors.green('VP9')})")
                else:
                    tqdm.write(f"    Codec: {Colors.green(video_info.codec.upper())}")

                if not resolution_compliant:
                    tqdm.write(f"    Resolution: {Colors.red(f'{video_info.width}x{video_info.height}')} (exceeds max {max_width}x{max_height})")
                else:
                    tqdm.write(f"    Resolution: {video_info.width}x{video_info.height}")

                tqdm.write(f"    Container: {video_info.container}")

                # Early exit: if re-encoding with max-files, stop once we have enough non-compliant videos
                # We use a 2x buffer since some might have existing outputs
                if args.re_encode and args.max_files and len(non_compliant_videos) >= args.max_files * 2:
                    print()
                    print(f"Found {len(non_compliant_videos)} non-compliant videos (enough for --max-files {args.max_files}), stopping analysis")
                    break

        print()
        print(f"Summary: {Colors.green(f'{len(compliant_videos)} compliant')}, {Colors.red(f'{len(non_compliant_videos)} non-compliant')}")
        print()

        # Re-encode if requested
        if args.re_encode and non_compliant_videos:
            print("="*80)
            print("RE-ENCODING NON-COMPLIANT VIDEOS")
            print("(Using smart quality matching to preserve visual quality)")
            if args.recover:
                print("🛠️  RECOVERY MODE: Using error-tolerant FFmpeg flags to salvage broken files")
            if args.replace_original:
                print("⚠️  REPLACE MODE: Original files will be deleted and replaced")
            print()
            print("💡 TIP: Press 'q' at any time to stop after the current video")
            print("="*80)
            print()

            # Start shutdown listener for graceful exit
            start_shutdown_listener()

            # Check for existing valid re-encodes and filter them out
            print("Checking for existing re-encoded outputs...")
            videos_needing_encode = []
            videos_already_encoded = []

            for video_path, video_info in tqdm(non_compliant_videos, desc="Checking for existing outputs", unit="video"):
                existing_output = encoder.find_existing_output(video_path, target_codec=args.target_codec)

                if existing_output:
                    videos_already_encoded.append((video_path, existing_output))
                    tqdm.write(Colors.green(f"✓ {video_path.name}: Already has valid output ({existing_output.name})"))
                else:
                    videos_needing_encode.append((video_path, video_info))

                    # Apply max-files limit smartly: stop once we have enough files that need encoding
                    if args.max_files and len(videos_needing_encode) >= args.max_files:
                        print()
                        print(f"Reached limit of {args.max_files} files needing encoding (checked {len(videos_already_encoded) + len(videos_needing_encode)} total)")
                        break

            print()
            if videos_already_encoded:
                print(f"Found {len(videos_already_encoded)} video(s) with existing valid re-encodes (skipping)")
                print(f"Need to encode: {len(videos_needing_encode)} video(s)")
                print()

            # Note: File type filtering now happens at the find_videos stage
            if not videos_needing_encode:
                print("No videos need encoding.")
                print()
                # Stop shutdown listener since we're not encoding anything
                stop_shutdown_listener()
            else:
                videos_to_encode = [v[0] for v in videos_needing_encode]
                video_infos_dict = {v[0]: v[1] for v in videos_needing_encode}

                # Use queue mode if enabled
                if args.queue_mode:
                    print()
                    print("="*80)
                    print("QUEUE MODE ENABLED")
                    print("="*80)
                    print(f"Temp directory: {args.temp_dir or 'system temp'}")
                    print(f"Buffer size: {args.buffer_size} files")
                    print(f"Max temp storage: {args.max_temp_size} GB")
                    print()
                    print("Pipeline stages:")
                    print("  1. DOWNLOAD: Network → Local temp storage")
                    print("  2. ENCODE: Local encoding (fast!)")
                    print("  3. UPLOAD: Local → Network")
                    print("="*80)
                    print()

                    # Initialize queue manager
                    queue_manager = NetworkQueueManager(
                        temp_dir=args.temp_dir,
                        max_buffer_size=args.buffer_size,
                        max_temp_size_gb=args.max_temp_size,
                        verbose=args.verbose,
                        replace_original=args.replace_original
                    )

                    # Try to resume from previous state
                    if queue_manager.load_state():
                        print("Resumed from previous session")
                        print()

                    # Add files to queue
                    queue_manager.add_files(videos_to_encode)

                    # Create encoding callback
                    current_idx = [0]  # Use list to allow modification in nested function
                    total = len(videos_to_encode)

                    def encode_callback(local_input: Path, local_output: Path) -> bool:
                        """Callback for encoding a single video in queue mode"""
                        current_idx[0] += 1

                        # Find the original network path for this file
                        # (local_input is a temp file, need to find which video it corresponds to)
                        video_info = None

                        # Try to find matching video_info by filename
                        for orig_path, info in video_infos_dict.items():
                            if orig_path.name == local_input.name or local_input.name.startswith('download_'):
                                # Check if the downloaded file matches
                                check_name = local_input.name.replace('download_', '')
                                if orig_path.name == check_name:
                                    video_info = info
                                    break

                        # Encode the video
                        success = encoder.re_encode_video(
                            local_input,
                            local_output,
                            target_codec=args.target_codec,
                            video_info=video_info,
                            current_index=current_idx[0],
                            total_count=total,
                            keep_original=True,  # Queue manager handles cleanup
                            replace_original=False  # Queue manager handles replacement
                        )

                        return success

                    try:
                        # Start the queue (blocks until complete, including final uploads)
                        print("Starting queue pipeline...")
                        print()
                        queue_manager.start(encode_callback)

                        # Show final progress
                        progress = queue_manager.get_progress()
                        print()
                        print("="*80)
                        print("QUEUE MODE COMPLETE")
                        print("="*80)
                        print(f"Total: {progress['total']}")
                        print(f"Completed: {Colors.green(str(progress['complete']))}")
                        print(f"Failed: {Colors.red(str(progress['failed']))}")
                        print("="*80)
                        print()

                        # Cleanup temp directory
                        queue_manager.cleanup()

                    except KeyboardInterrupt:
                        print()
                        print("="*80)
                        print("INTERRUPTED - Saving state...")
                        print("="*80)
                        queue_manager.stop()
                        stop_shutdown_listener()
                        print()
                        print("Progress saved. Run the same command again to resume.")
                        print()
                        sys.exit(0)
                    finally:
                        # Stop shutdown listener when queue mode completes
                        stop_shutdown_listener()

                else:
                    # Standard batch encoding (no queue)
                    try:
                        encoder.batch_re_encode(
                            videos_to_encode,
                            output_dir=args.output_dir,
                            target_codec=args.target_codec,
                            video_infos=video_infos_dict,
                            replace_original=args.replace_original
                        )
                    except KeyboardInterrupt:
                        print()
                        print("="*80)
                        print("INTERRUPTED - Stopping after current video")
                        print("="*80)
                        stop_shutdown_listener()
                        print()
                        print("You can safely resume by running the same command again.")
                        print()
                        sys.exit(0)
                    finally:
                        # Stop shutdown listener when batch encoding completes
                        stop_shutdown_listener()

        # Fix QuickLook compatibility if requested
        if args.fix_quicklook and compliant_videos:
            print("="*80)
            print("QUICKLOOK COMPATIBILITY CHECK")
            print("="*80)
            print()

            videos_to_remux = []
            videos_to_reencode = []

            for video_path in tqdm(compliant_videos, desc="Checking QuickLook compatibility", unit="video"):
                compat = analyzer.check_quicklook_compatibility(video_path)

                if compat['compatible']:
                    tqdm.write(Colors.green(f"✓ {video_path.name}: QuickLook compatible"))
                elif compat['needs_remux']:
                    tqdm.write(Colors.yellow(f"⚠ {video_path.name}: Needs remux (fast)"))
                    for issue in compat['issues']:
                        tqdm.write(f"    - {issue}")
                    videos_to_remux.append(video_path)
                elif compat['needs_reencode']:
                    tqdm.write(Colors.red(f"✗ {video_path.name}: Needs re-encode"))
                    for issue in compat['issues']:
                        tqdm.write(f"    - {issue}")
                    videos_to_reencode.append(video_path)

            print()
            print(f"Summary: {Colors.green(f'{len(compliant_videos) - len(videos_to_remux) - len(videos_to_reencode)} compatible')}, "
                  f"{Colors.yellow(f'{len(videos_to_remux)} need remux')}, "
                  f"{Colors.red(f'{len(videos_to_reencode)} need re-encode')}")
            print()

            # Check for existing QuickLook outputs to avoid re-processing
            if videos_to_remux or videos_to_reencode:
                print("Checking for existing QuickLook outputs...")
                videos_remux_needed = []
                videos_reencode_needed = []
                videos_already_fixed = []

                all_videos_to_check = videos_to_remux + videos_to_reencode

                for video_path in tqdm(all_videos_to_check, desc="Checking for existing outputs", unit="video"):
                    # Look for existing _quicklook or _reencoded files
                    existing_output = encoder.find_existing_output(
                        video_path,
                        target_codec=args.target_codec,
                        check_suffixes=['_quicklook', '_reencoded']
                    )

                    if existing_output:
                        videos_already_fixed.append((video_path, existing_output))
                        tqdm.write(Colors.green(f"✓ {video_path.name}: Already has valid output ({existing_output.name})"))
                    else:
                        # Add to appropriate list based on original categorization
                        if video_path in videos_to_remux:
                            videos_remux_needed.append(video_path)
                        else:
                            videos_reencode_needed.append(video_path)

                print()
                if videos_already_fixed:
                    print(f"Found {len(videos_already_fixed)} video(s) with existing valid QuickLook outputs (skipping)")
                    print(f"Need to fix: {len(videos_remux_needed) + len(videos_reencode_needed)} video(s)")
                    print()

                # Update the lists with only videos that need processing
                videos_to_remux = videos_remux_needed
                videos_to_reencode = videos_reencode_needed

            # Combine all videos that need fixing (remux or re-encode)
            all_videos_to_fix = videos_to_remux + videos_to_reencode

            # Process with queue mode if enabled
            if all_videos_to_fix and args.queue_mode:
                print()
                print("="*80)
                print("QUEUE MODE ENABLED FOR QUICKLOOK FIX")
                print("="*80)
                print(f"Temp directory: {args.temp_dir or 'system temp'}")
                print(f"Buffer size: {args.buffer_size} files")
                print(f"Max temp storage: {args.max_temp_size} GB")
                print()
                print("Pipeline stages:")
                print("  1. DOWNLOAD: Network → Local temp storage")
                print("  2. FIX: Remux or re-encode (local, fast!)")
                print("  3. UPLOAD: Local → Network")
                print("="*80)
                print()

                # Initialize queue manager
                queue_manager = NetworkQueueManager(
                    temp_dir=args.temp_dir,
                    max_buffer_size=args.buffer_size,
                    max_temp_size_gb=args.max_temp_size,
                    verbose=args.verbose,
                    replace_original=args.replace_original
                )

                # Try to resume from previous state
                if queue_manager.load_state():
                    print("Resumed from previous session")
                    print()

                # Add files to queue
                queue_manager.add_files(all_videos_to_fix)

                # Create processing callback
                current_idx = [0]
                total = len(all_videos_to_fix)

                def quicklook_fix_callback(local_input: Path, local_output: Path) -> bool:
                    """Callback for fixing QuickLook compatibility in queue mode"""
                    current_idx[0] += 1

                    # Find the original network path to determine if remux or re-encode
                    needs_remux = False
                    needs_reencode = False
                    video_info = None

                    # Check if this file needs remux or re-encode
                    for orig_path in videos_to_remux:
                        check_name = local_input.name.replace('download_', '')
                        if orig_path.name == check_name:
                            needs_remux = True
                            break

                    for orig_path in videos_to_reencode:
                        check_name = local_input.name.replace('download_', '')
                        if orig_path.name == check_name:
                            needs_reencode = True
                            video_info = analyzer.get_video_info(local_input)
                            break

                    # Process based on what's needed
                    if needs_remux:
                        print(f"[{current_idx[0]}/{total}] Remuxing: {local_input.name}")
                        success = encoder.remux_to_mp4(local_input, local_output)
                        if success:
                            print(f"✓ [{current_idx[0]}/{total}] Completed: {local_input.name}")
                        return success
                    elif needs_reencode:
                        success = encoder.re_encode_video(
                            local_input,
                            local_output,
                            target_codec=args.target_codec,
                            video_info=video_info,
                            current_index=current_idx[0],
                            total_count=total,
                            keep_original=True,
                            replace_original=False
                        )
                        return success
                    else:
                        return False

                try:
                    # Start the queue
                    print("Starting queue pipeline...")
                    print()
                    start_shutdown_listener()
                    queue_manager.start(quicklook_fix_callback)

                    # Show final progress
                    progress = queue_manager.get_progress()
                    print()
                    print("="*80)
                    print("QUEUE MODE COMPLETE")
                    print("="*80)
                    print(f"Completed: {Colors.green(str(progress['complete']))}")
                    if progress['failed'] > 0:
                        print(f"Failed: {Colors.red(str(progress['failed']))}")
                    print("="*80)
                    print()

                except KeyboardInterrupt:
                    print("\n\nInterrupted by user. Queue state saved for resume.")
                    print("Run the same command again to resume from where you left off.")
                    sys.exit(0)
                finally:
                    stop_shutdown_listener()

            # Otherwise process directly (no queue mode)
            elif all_videos_to_fix:
                # Remux videos (fast - just container change)
                if videos_to_remux:
                    print("="*80)
                    print("REMUXING FOR QUICKLOOK COMPATIBILITY (FAST)")
                    print("="*80)
                    print()

                    for video_path in videos_to_remux:
                        output_path = video_path.parent / f"{video_path.stem}_quicklook.mp4"

                        print(f"Remuxing: {video_path.name}")
                        success = encoder.remux_to_mp4(video_path, output_path)

                        if success:
                            if args.replace_original:
                                # Delete original and rename output
                                video_path.unlink()
                                output_path.rename(video_path.with_suffix('.mp4'))
                                print(f"✓ Replaced: {video_path.name} → {video_path.stem}.mp4")
                            else:
                                print(f"✓ Created: {output_path.name}")
                        else:
                            print(f"✗ Failed: {video_path.name}")

                    print()

                # Re-encode videos (slower - needs full re-encode)
                if videos_to_reencode:
                    print("="*80)
                    print("RE-ENCODING FOR QUICKLOOK COMPATIBILITY")
                    print("="*80)
                    print()

                    for video_path in videos_to_reencode:
                        video_info = analyzer.get_video_info(video_path)
                        output_path = video_path.parent / f"{video_path.stem}_quicklook.mp4"

                        print(f"Re-encoding: {video_path.name}")
                        success = encoder.re_encode_video(
                            video_path,
                            output_path,
                            target_codec=args.target_codec,
                            video_info=video_info,
                            keep_original=not args.replace_original
                        )

                        if success:
                            if args.replace_original:
                                # Delete original and rename output
                                if video_path.exists() and video_path != output_path:
                                    video_path.unlink()
                                if output_path != video_path.with_suffix('.mp4'):
                                    output_path.rename(video_path.with_suffix('.mp4'))
                                print(f"✓ Replaced: {video_path.name} → {video_path.stem}.mp4")
                            else:
                                print(f"✓ Created: {output_path.name}")
                        else:
                            print(f"✗ Failed: {video_path.name}")

                    print()

    # Find duplicates
    if args.find_duplicates or args.filename_duplicates:
        # Stop shutdown listener to restore normal terminal mode for input prompts
        stop_shutdown_listener()

        print("="*80)
        print("DUPLICATE VIDEO DETECTION")
        if args.filename_duplicates:
            print("(Method: Filename matching - fast, no perceptual hashing)")
        else:
            print("(Method: Perceptual hashing)")
        if args.duplicate_action != 'report':
            print(f"(Action: {args.duplicate_action})")
        print("="*80)

        # Use filename-based detection if requested, otherwise use perceptual hashing
        if args.filename_duplicates:
            duplicate_groups = duplicate_detector.find_duplicates_by_filename(video_files, analyzer=analyzer)
        else:
            duplicate_groups = duplicate_detector.find_duplicates(video_files)

        if duplicate_groups:
            print()
            print(f"Found {len(duplicate_groups)} groups of duplicate videos:")
            print()

            all_to_delete = []
            all_to_keep = []
            # Map deleted files to their corresponding kept file for space calculation
            delete_to_keep_map = {}

            if args.duplicate_action == 'report':
                # Just report duplicates, no action
                for group_name, videos in duplicate_groups.items():
                    print(f"{group_name} ({len(videos)} videos):")
                    for video in videos:
                        file_size_mb = video.stat().st_size / (1024 * 1024)
                        print(f"  - {video.name} ({file_size_mb:.2f} MB)")
                    print()
            else:
                # Handle each group with auto-best or interactive
                for group_name, videos in duplicate_groups.items():
                    print(f"{group_name}:")
                    to_delete, to_keep = handle_duplicate_group(
                        group_name,
                        videos,
                        analyzer,
                        args.duplicate_action,
                        args.verbose
                    )
                    all_to_delete.extend(to_delete)
                    if to_keep:
                        all_to_keep.append(to_keep)
                        # Map each deleted file to its kept file
                        for deleted_file in to_delete:
                            delete_to_keep_map[deleted_file] = to_keep
                    print()

                # Perform deletions if any
                if all_to_delete:
                    print()
                    print("="*80)
                    print(f"DELETING {len(all_to_delete)} DUPLICATE FILES")
                    print("="*80)

                    if args.duplicate_action == 'auto-best':
                        # Auto mode - delete immediately
                        confirm = input(f"\nDelete {len(all_to_delete)} files? (yes/no): ").strip().replace('\r', '').lower()
                        if confirm == 'yes':
                            deleted_count = 0
                            total_size_freed = 0
                            incremental_space_saved = 0

                            for video in all_to_delete:
                                try:
                                    deleted_size = video.stat().st_size
                                    video.unlink()
                                    deleted_count += 1
                                    total_size_freed += deleted_size

                                    # Calculate incremental space saved (deleted - kept)
                                    if video in delete_to_keep_map:
                                        kept_file = delete_to_keep_map[video]
                                        if kept_file.exists():
                                            kept_size = kept_file.stat().st_size
                                            incremental_space_saved += max(0, deleted_size - kept_size)
                                        else:
                                            incremental_space_saved += deleted_size
                                    else:
                                        incremental_space_saved += deleted_size

                                    print(f"  {Colors.green('✓')} Deleted: {video.name}")
                                except Exception as e:
                                    print(f"  {Colors.red('✗')} Failed to delete {video.name}: {e}")

                            print()
                            print(f"Successfully deleted {deleted_count}/{len(all_to_delete)} files")
                            print(f"Total space freed: {total_size_freed / (1024*1024):.2f} MB")
                            print(f"Incremental space saved: {incremental_space_saved / (1024*1024):.2f} MB")
                        else:
                            print(f"{Colors.yellow('→ Deletion cancelled')}")
                    else:
                        # Interactive mode - already got confirmation per group, delete now
                        deleted_count = 0
                        total_size_freed = 0
                        incremental_space_saved = 0

                        for video in all_to_delete:
                            try:
                                deleted_size = video.stat().st_size
                                video.unlink()
                                deleted_count += 1
                                total_size_freed += deleted_size

                                # Calculate incremental space saved (deleted - kept)
                                if video in delete_to_keep_map:
                                    kept_file = delete_to_keep_map[video]
                                    if kept_file.exists():
                                        kept_size = kept_file.stat().st_size
                                        incremental_space_saved += max(0, deleted_size - kept_size)
                                    else:
                                        incremental_space_saved += deleted_size
                                else:
                                    incremental_space_saved += deleted_size

                                print(f"  {Colors.green('✓')} Deleted: {video.name}")
                            except Exception as e:
                                print(f"  {Colors.red('✗')} Failed to delete {video.name}: {e}")

                        print()
                        print(f"Successfully deleted {deleted_count}/{len(all_to_delete)} files")
                        print(f"Total space freed: {total_size_freed / (1024*1024):.2f} MB")
                        print(f"Incremental space saved: {incremental_space_saved / (1024*1024):.2f} MB")
                    print()

                    # Clean up filenames of kept files (remove _reencoded and _quicklook suffixes)
                    if all_to_keep:
                        print("="*80)
                        print("CLEANING UP FILENAMES")
                        print("="*80)
                        print()

                        renamed_count = 0
                        for video in all_to_keep:
                            # Check if filename has _reencoded or _quicklook suffix
                            stem = video.stem
                            if stem.endswith('_reencoded') or stem.endswith('_quicklook'):
                                # Remove the suffix
                                if stem.endswith('_reencoded'):
                                    new_stem = stem[:-len('_reencoded')]
                                else:
                                    new_stem = stem[:-len('_quicklook')]

                                new_path = video.parent / (new_stem + video.suffix)

                                # Check if target path already exists
                                if new_path.exists():
                                    print(f"  {Colors.yellow('⚠')} Skipping {video.name}: {new_path.name} already exists")
                                else:
                                    try:
                                        video.rename(new_path)
                                        renamed_count += 1
                                        print(f"  {Colors.green('✓')} Renamed: {video.name} → {new_path.name}")
                                    except Exception as e:
                                        print(f"  {Colors.red('✗')} Failed to rename {video.name}: {e}")

                        if renamed_count > 0:
                            print()
                            print(f"Renamed {renamed_count} file(s)")
                        else:
                            print(f"No files needed renaming")
                        print()
                else:
                    print()
                    print(f"{Colors.yellow('No duplicates marked for deletion')}")

            print(f"Total duplicates: {sum(len(v) for v in duplicate_groups.values())} videos in {len(duplicate_groups)} groups")
        else:
            print()
            print("No duplicate videos found.")

        print()

    # Check for issues
    if args.check_issues:
        print("="*80)
        print("ENCODING ISSUE DETECTION")
        if args.deep_scan:
            print("(Deep scan mode: decoding entire videos)")
        print("="*80)
        print()

        videos_with_issues = []

        scan_desc = "Deep scanning videos" if args.deep_scan else "Checking for issues"
        for video_path in tqdm(video_files, desc=scan_desc, unit="video"):
            issues = issue_detector.scan_video(video_path, deep_scan=args.deep_scan)

            if issues:
                videos_with_issues.append((video_path, issues))
                tqdm.write(f"{video_path.name}:")
                for issue in issues:
                    severity_symbol = {
                        'critical': '✗',
                        'warning': '⚠',
                        'info': 'ℹ'
                    }.get(issue.severity, '•')

                    tqdm.write(f"  {severity_symbol} [{issue.severity.upper()}] {issue.issue_type}: {issue.description}")

        if videos_with_issues:
            critical_count = sum(
                1 for _, issues in videos_with_issues
                for issue in issues
                if issue.severity == 'critical'
            )
            warning_count = sum(
                1 for _, issues in videos_with_issues
                for issue in issues
                if issue.severity == 'warning'
            )

            print()
            print(f"Summary: {len(videos_with_issues)} videos with issues")
            print(f"  Critical: {critical_count}")
            print(f"  Warnings: {warning_count}")
        else:
            print("\nNo issues detected.")

        print()

    print("="*80)
    print("VideoSentinel scan complete!")
    print("="*80)


if __name__ == '__main__':
    main()
