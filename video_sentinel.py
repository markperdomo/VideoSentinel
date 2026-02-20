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

from video_analyzer import VideoAnalyzer, VideoInfo
from duplicate_detector import DuplicateDetector
from issue_detector import IssueDetector
from encoder import VideoEncoder
from network_queue_manager import NetworkQueueManager
from shutdown_manager import start_shutdown_listener, stop_shutdown_listener, shutdown_requested
from stats import StatsCollector
from sample_generator import create_sample_video
from ui import console, section_header, success, error, warning, create_scan_progress, create_batch_progress


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
        console.print(f"  [warning]\u26a0 Warning: Could not analyze videos in this group[/warning]")
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

        console.print(f"  [success]\u2713 Keeping:[/success] {best_video.name}")
        info = video_infos[best_video]

        # Check QuickLook compatibility for the kept file
        compat = analyzer.check_quicklook_compatibility(best_video)
        ql_status = " [QuickLook \u2713]" if compat.get('compatible') else ""

        console.print(f"    ({info.codec.upper()}, {info.width}x{info.height}, {info.bitrate//1000} kbps{ql_status})")

        for video in to_delete:
            info = video_infos[video]
            file_size_mb = video.stat().st_size / (1024 * 1024)

            # Check QuickLook compatibility for files being deleted
            compat = analyzer.check_quicklook_compatibility(video)
            ql_status = " [QuickLook \u2713]" if compat.get('compatible') else ""

            console.print(f"  [error]\u2717 Deleting:[/error] {video.name} ({file_size_mb:.2f} MB)")
            console.print(f"    ({info.codec.upper()}, {info.width}x{info.height}, {info.bitrate//1000} kbps{ql_status})")

    elif action == 'interactive':
        # Show options and let user choose
        console.print()
        console.print(f"[bold]{group_name}[/bold] - {len(videos)} duplicates found:")
        console.print()

        for idx, video in enumerate(ranked_videos, 1):
            info = video_infos[video]
            file_size_mb = video.stat().st_size / (1024 * 1024)
            quality_rank = "\u2605 BEST" if idx == 1 else f"  #{idx}"

            # Check QuickLook compatibility
            compat = analyzer.check_quicklook_compatibility(video)
            ql_badge = " [QuickLook \u2713]" if compat.get('compatible') else ""

            console.print(f"  {quality_rank} [{idx}] {video.name}{ql_badge}")
            console.print(f"      Codec: {info.codec.upper()}, Resolution: {info.width}x{info.height}")
            console.print(f"      Bitrate: {info.bitrate//1000} kbps, Size: {file_size_mb:.2f} MB")
            console.print()

        console.print(f"Options:")
        console.print(f"  1-{len(ranked_videos)}: Keep that video, delete others")
        console.print(f"  0 or Enter: Keep all (no action)")
        console.print()

        choice = input(f"Your choice: ").strip('\r\n\t ').replace('\r', '').replace('\n', '')

        if choice.isdigit() and 1 <= int(choice) <= len(ranked_videos):
            keep_idx = int(choice) - 1
            keep_video = ranked_videos[keep_idx]
            to_keep = keep_video
            to_delete = [v for v in ranked_videos if v != keep_video]

            console.print()
            console.print(f"  [success]\u2713 Keeping:[/success] {keep_video.name}")
            for video in to_delete:
                file_size_mb = video.stat().st_size / (1024 * 1024)
                console.print(f"  [error]\u2717 Will delete:[/error] {video.name} ({file_size_mb:.2f} MB)")
        else:
            console.print(f"  [warning]\u2192 No action, keeping all[/warning]")

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
        'paths',
        type=Path,
        nargs='*',
        help='Video files or directories to analyze (not required for --clear-queue, --file-list)'
    )

    parser.add_argument(
        '--file-list',
        type=Path,
        help='Path to a text file containing video file paths (one path per line)'
    )

    parser.add_argument(
        '-r', '--recursive',
        action='store_true',
        help='Recursively scan subdirectories'
    )

    parser.add_argument(
        '--stats',
        action='store_true',
        help='Display statistics about video codecs and sizes'
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
        '--ignore-duration',
        action='store_true',
        help='Ignore video duration when checking for filename duplicates (useful if re-encoded files have slightly different lengths)'
    )

    parser.add_argument(
        '--fix-quicklook',
        action='store_true',
        help='Fix QuickLook compatibility (remux MKV\u2192MP4, fix HEVC tags, re-encode if needed)'
    )

    parser.add_argument(
        '--force-remux-mkv',
        action='store_true',
        help='Force remuxing of all MKV files to MP4, even if otherwise compliant'
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
        '--create-samples',
        action='store_true',
        help='Analyze videos and create a sample FFmpeg file for unique permutations.'
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
        section_header("CLEARING QUEUE STATE")

        queue_manager = NetworkQueueManager(
            temp_dir=args.temp_dir,
            verbose=args.verbose
        )

        temp_dir = queue_manager.temp_dir
        state_file = queue_manager.state_file

        if state_file.exists():
            console.print(f"Removing state file: {state_file}")
            state_file.unlink()
        else:
            console.print(f"No state file found at: {state_file}")

        # Count and remove temp files
        temp_files = list(temp_dir.glob("*"))
        if temp_files:
            total_size = sum(f.stat().st_size for f in temp_files if f.is_file())
            console.print(f"Removing {len(temp_files)} temp files ({total_size / (1024**2):.2f} MB)")
            queue_manager.cleanup()
            console.print("[success]\u2713 Queue cleared successfully[/success]")
        else:
            console.print("No temp files found")

        sys.exit(0)

    if not args.paths and not args.file_list and not args.clear_queue:
        console.print(f"[error]Error: Path argument or --file-list is required (provide one or more video files/directories or a file list)[/error]", highlight=False)
        parser.print_help()
        sys.exit(1)

    if args.paths and args.file_list:
        console.print(f"[error]Error: Cannot use --file-list with positional path arguments simultaneously. Choose one or the other.[/error]", highlight=False)
        sys.exit(1)

    # Validate input paths (required unless using --clear-queue or --file-list)
    if args.paths:
        for path in args.paths:
            if not path.exists():
                console.print(f"[error]Error: Path '{path}' does not exist[/error]", highlight=False)
                sys.exit(1)
            if not path.is_file() and not path.is_dir():
                console.print(f"[error]Error: '{path}' is not a valid file or directory[/error]", highlight=False)
                sys.exit(1)

    if args.file_list:
        if not args.file_list.exists():
            console.print(f"[error]Error: File list '{args.file_list}' does not exist[/error]", highlight=False)
            sys.exit(1)
        if not args.file_list.is_file():
            console.print(f"[error]Error: '{args.file_list}' is not a valid file[/error]", highlight=False)
            sys.exit(1)


    # If re-encode is specified, automatically enable check-specs (required for re-encoding)
    if args.re_encode and not args.check_specs:
        args.check_specs = True

    # If fix-quicklook is specified, automatically enable check-specs
    if args.fix_quicklook and not args.check_specs:
        args.check_specs = True

    # If no action specified at all, show all checks by default
    if not any([args.check_specs, args.find_duplicates, args.filename_duplicates, args.check_issues, args.re_encode, args.fix_quicklook, args.stats]):
        args.check_specs = True
        args.find_duplicates = True
        args.check_issues = True

    # Handle stats separately
    if args.stats:
        section_header("Video Library Statistics")

        analyzer = VideoAnalyzer(verbose=args.verbose)
        stats_collector = StatsCollector(analyzer)

        for path in args.paths:
            console.print(f"Processing path: {path}")
            codec_stats = stats_collector.collect_stats(path, args.recursive)
            stats_collector.display_stats(codec_stats)
            console.print()

        analyzer.save_cache()
        sys.exit(0)


    # Check ffmpeg availability
    encoder = VideoEncoder(verbose=args.verbose, recovery_mode=args.recover, downscale_1080p=args.downscale_1080p)
    if not encoder.check_ffmpeg_available():
        console.print("[error]Error: ffmpeg is not installed or not in PATH[/error]", highlight=False)
        console.print("[error]Please install ffmpeg to use VideoSentinel[/error]", highlight=False)
        sys.exit(1)

    section_header("VideoSentinel - Video Library Manager")

    if args.paths:
        console.print(f"Processing {len(args.paths)} paths:")
        for path in args.paths:
            console.print(f"  - {path}")
        console.print(f"Recursive scan: {args.recursive}")
    elif args.file_list:
        console.print(f"Processing videos from file list: {args.file_list}")
    else:
        console.print("No specific paths or file list provided for processing (e.g., --clear-queue was used).")

    console.print(f"Target codec: [codec]{args.target_codec.upper()}[/codec]")
    console.print()

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
        console.print(f"File type filter: {', '.join(file_types_filter).upper()}")

    # Find all video files from the provided paths or file list
    video_files = []
    if args.file_list:
        console.print(f"Reading video paths from: {args.file_list}")
        try:
            with open(args.file_list, 'r') as f:
                for line in f:
                    path_str = line.strip()
                    if path_str:
                        video_path = Path(path_str)
                        if video_path.exists() and video_path.is_file() and video_path.suffix.lower() in analyzer.VIDEO_EXTENSIONS:
                            video_files.append(video_path)
                        else:
                            if args.verbose:
                                console.print(f"Skipping invalid or non-video entry in file list: {path_str}", style="dim")
        except Exception as e:
            console.print(f"[error]Error reading file list '{args.file_list}': {e}[/error]", highlight=False)
            sys.exit(1)
    elif args.paths:
        console.print("Finding video files...")
        for path in args.paths:
            if path.is_file():
                if path.suffix.lower() in analyzer.VIDEO_EXTENSIONS:
                    video_files.append(path)
                else:
                    if args.verbose:
                        console.print(f"Skipping non-video file: {path}", style="dim")
            elif path.is_dir():
                video_files.extend(analyzer.find_videos(
                    path,
                    recursive=args.recursive,
                    file_types=file_types_filter
                ))

    # Note: For re-encoding operations, max-files limit is applied AFTER filtering
    # to files that need encoding (smarter behavior). For other operations, apply it here.
    if args.max_files and not args.re_encode and len(video_files) > args.max_files:
        console.print(f"Limiting to first {args.max_files} files (found {len(video_files)} total)")
        video_files = video_files[:args.max_files]

    if not video_files:
        if file_types_filter:
            console.print(f"No video files found matching types: {', '.join(file_types_filter).upper()}")
        else:
            console.print("No video files found.")
        sys.exit(0)

    console.print(f"Found {len(video_files)} video files")
    console.print()

    # Create samples if requested
    if args.create_samples:
        section_header("CREATING SAMPLE VIDEOS")

        with create_scan_progress() as progress:
            task = progress.add_task("Generating samples", total=len(video_files))
            for video_path in video_files:
                video_info = analyzer.get_video_info(video_path)
                if video_info and video_info.is_valid:
                    create_sample_video(video_info)
                progress.advance(task)

        analyzer.save_cache()
        console.print("\nSample creation process complete.")
        sys.exit(0)

    if args.force_remux_mkv:
        subtitle = None
        if args.replace_original:
            subtitle = "\u26a0\ufe0f  REPLACE MODE: Original MKV files will be deleted and replaced with MP4"
        section_header("FORCE REMUX MKV TO MP4", subtitle)

        videos_to_remux = [p for p in video_files if p.suffix.lower() == '.mkv']

        if not videos_to_remux:
            console.print("No MKV files found to remux.")
            sys.exit(0)

        console.print(f"Found {len(videos_to_remux)} MKV files to remux.")
        console.print()

        if args.queue_mode:
            console.print("[bold]QUEUE MODE ENABLED[/bold]")
            queue_manager = NetworkQueueManager(
                temp_dir=args.temp_dir,
                max_buffer_size=args.buffer_size,
                max_temp_size_gb=args.max_temp_size,
                verbose=args.verbose,
                replace_original=args.replace_original
            )
            if queue_manager.load_state():
                console.print("Resumed from previous session\n")

            queue_manager.add_files(videos_to_remux)

            def remux_callback(local_input: Path, local_output: Path, progress=None, file_task=None) -> bool:
                """Callback for remuxing a single video in queue mode"""
                result = encoder.remux_to_mp4(local_input, local_output)
                return result

            try:
                start_shutdown_listener()
                queue_manager.start(remux_callback)
            except KeyboardInterrupt:
                console.print("\n\nInterrupted by user. Queue state saved for resume.")
                sys.exit(0)
            finally:
                stop_shutdown_listener()
        else:
            # Standard mode
            remux_results = {}
            with create_batch_progress() as progress:
                overall = progress.add_task("Remuxing MKV files", total=len(videos_to_remux))
                current = progress.add_task("", total=None)
                for video_path in videos_to_remux:
                    progress.update(current, description=video_path.name)
                    output_path = video_path.with_suffix('.mp4')

                    if output_path == video_path:
                        remux_results[video_path] = 'skipped'
                        progress.advance(overall)
                        continue

                    result = encoder.remux_to_mp4(video_path, output_path)

                    if result:
                        if args.replace_original:
                            try:
                                video_path.unlink()
                                remux_results[video_path] = 'replaced'
                            except Exception as e:
                                remux_results[video_path] = f'delete_failed: {e}'
                        else:
                            remux_results[video_path] = 'created'
                    else:
                        remux_results[video_path] = 'failed'

                    progress.advance(overall)

            # Print summary
            succeeded = sum(1 for v in remux_results.values() if v in ('replaced', 'created'))
            failed = sum(1 for v in remux_results.values() if v == 'failed')
            console.print(f"Remuxed: [success]{succeeded} successful[/success], [error]{failed} failed[/error]")

        console.print("\nForce remux complete.")
        sys.exit(0)

    # Check encoding specifications
    if args.check_specs:
        section_header("ENCODING SPECIFICATION CHECK")

        compliant_videos = []
        non_compliant_videos = []
        failed_analyses = []

        with create_batch_progress() as progress:
            overall = progress.add_task("Analyzing videos", total=len(video_files))
            current = progress.add_task("", total=None)
            for video_path in video_files:
                progress.update(current, description=video_path.name)
                video_info = analyzer.get_video_info(video_path)

                if not video_info or not video_info.is_valid:
                    failed_analyses.append(video_path)
                    progress.advance(overall)
                    continue

                is_compliant = analyzer.meets_modern_specs(video_info)

                if is_compliant:
                    compliant_videos.append(video_path)
                else:
                    non_compliant_videos.append((video_path, video_info))

                    # Early exit: if re-encoding with max-files, stop once we have enough non-compliant videos
                    if args.re_encode and args.max_files and len(non_compliant_videos) >= args.max_files * 2:
                        break

                progress.advance(overall)

        # Print results after progress bar is gone
        console.print()
        console.print(f"Summary: [success]{len(compliant_videos)} compliant[/success], [error]{len(non_compliant_videos)} non-compliant[/error], [warning]{len(failed_analyses)} failed analysis[/warning]")

        if non_compliant_videos:
            console.print()
            console.print("[error]Non-compliant videos:[/error]")
            for video_path, video_info in non_compliant_videos:
                codec_lower = video_info.codec.lower()
                codec_ok = codec_lower in analyzer.MODERN_CODECS
                codec_str = f"[success]{video_info.codec.upper()}[/success]" if codec_ok else f"[error]{video_info.codec.upper()}[/error]"
                console.print(f"  [error]\u2717[/error] {video_path.name}  {codec_str}  {video_info.width}x{video_info.height}  {video_info.container}")

        if failed_analyses:
            console.print()
            console.print("[warning]Videos that couldn't be analyzed:[/warning]")
            for video_path in failed_analyses:
                console.print(f"  {video_path}")

        console.print()

        # Re-encode if requested
        if args.re_encode and non_compliant_videos:
            subtitle_parts = ["Using smart quality matching to preserve visual quality"]
            if args.recover:
                subtitle_parts.append("\U0001f6e0\ufe0f  RECOVERY MODE: Using error-tolerant FFmpeg flags to salvage broken files")
            if args.replace_original:
                subtitle_parts.append("\u26a0\ufe0f  REPLACE MODE: Original files will be deleted and replaced")
            subtitle_parts.append("\U0001f4a1 TIP: Press 'q' at any time to stop after the current video")
            section_header("RE-ENCODING NON-COMPLIANT VIDEOS", "\n".join(subtitle_parts))

            # Start shutdown listener for graceful exit
            start_shutdown_listener()

            # Check for existing valid re-encodes and filter them out
            console.print("Checking for existing re-encoded outputs...")
            videos_needing_encode = []
            videos_already_encoded = []

            with create_batch_progress() as progress:
                overall = progress.add_task("Checking for existing outputs", total=len(non_compliant_videos))
                current = progress.add_task("", total=None)
                for video_path, video_info in non_compliant_videos:
                    progress.update(current, description=video_path.name)
                    existing_output = encoder.find_existing_output(video_path, target_codec=args.target_codec)

                    if existing_output:
                        videos_already_encoded.append((video_path, existing_output))
                    else:
                        videos_needing_encode.append((video_path, video_info))

                        if args.max_files and len(videos_needing_encode) >= args.max_files:
                            break

                    progress.advance(overall)

            console.print()
            if videos_already_encoded:
                console.print(f"Found {len(videos_already_encoded)} video(s) with existing valid re-encodes (skipping)")
            console.print(f"Need to encode: {len(videos_needing_encode)} video(s)")
            console.print()

            # Note: File type filtering now happens at the find_videos stage
            if not videos_needing_encode:
                console.print("No videos need encoding.")
                console.print()
                # Stop shutdown listener since we're not encoding anything
                stop_shutdown_listener()
            else:
                videos_to_encode = [v[0] for v in videos_needing_encode]
                video_infos_dict = {v[0]: v[1] for v in videos_needing_encode}

                # Use queue mode if enabled
                if args.queue_mode:
                    section_header("QUEUE MODE ENABLED",
                        f"Temp directory: {args.temp_dir or 'system temp'}\n"
                        f"Buffer size: {args.buffer_size} files\n"
                        f"Max temp storage: {args.max_temp_size} GB\n\n"
                        "Pipeline stages:\n"
                        "  1. DOWNLOAD: Network \u2192 Local temp storage\n"
                        "  2. ENCODE: Local encoding (fast!)\n"
                        "  3. UPLOAD: Local \u2192 Network")

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
                        console.print("Resumed from previous session")
                        console.print()

                    # Add files to queue
                    queue_manager.add_files(videos_to_encode)

                    # Create encoding callback
                    total = len(videos_to_encode)

                    def encode_callback(local_input: Path, local_output: Path, progress=None, file_task=None) -> bool:
                        """Callback for encoding a single video in queue mode"""
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

                        # Encode the video, passing progress handle for in-place updates
                        result = encoder.re_encode_video(
                            local_input,
                            local_output,
                            target_codec=args.target_codec,
                            video_info=video_info,
                            keep_original=True,  # Queue manager handles cleanup
                            replace_original=False,  # Queue manager handles replacement
                            progress=progress,
                            file_task=file_task,
                        )

                        return result

                    try:
                        # Start the queue (blocks until complete, including final uploads)
                        queue_manager.start(encode_callback)

                        # If shutdown was requested, exit gracefully
                        if shutdown_requested():
                            console.print("Queue processing stopped by user.")
                            # Cleanup is handled in the finally block
                            sys.exit(0)

                        # Show final progress
                        progress = queue_manager.get_progress()
                        section_header("QUEUE MODE COMPLETE")
                        console.print(f"Total: {progress['total']}")
                        console.print(f"Completed: [success]{progress['complete']}[/success]")
                        console.print(f"Failed: [error]{progress['failed']}[/error]")

                        # Cleanup temp directory
                        queue_manager.cleanup()

                    except KeyboardInterrupt:
                        section_header("INTERRUPTED", "Saving state...")
                        queue_manager.stop()
                        stop_shutdown_listener()
                        analyzer.save_cache()
                        console.print()
                        console.print("Progress saved. Run the same command again to resume.")
                        console.print()
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
                        section_header("INTERRUPTED", "Stopping after current video")
                        stop_shutdown_listener()
                        analyzer.save_cache()
                        console.print()
                        console.print("You can safely resume by running the same command again.")
                        console.print()
                        sys.exit(0)
                    finally:
                        # Stop shutdown listener when batch encoding completes
                        stop_shutdown_listener()

        # Fix QuickLook compatibility if requested
        if args.fix_quicklook and compliant_videos:
            section_header("QUICKLOOK COMPATIBILITY CHECK")

            videos_to_remux = []
            videos_to_reencode = []

            with create_batch_progress() as progress:
                overall = progress.add_task("Checking QuickLook compatibility", total=len(compliant_videos))
                current = progress.add_task("", total=None)
                for video_path in compliant_videos:
                    progress.update(current, description=video_path.name)
                    compat = analyzer.check_quicklook_compatibility(video_path)

                    if compat['needs_remux']:
                        videos_to_remux.append(video_path)
                    elif compat['needs_reencode']:
                        videos_to_reencode.append(video_path)

                    progress.advance(overall)

            compatible_count = len(compliant_videos) - len(videos_to_remux) - len(videos_to_reencode)
            console.print()
            console.print(f"Summary: [success]{compatible_count} compatible[/success], "
                  f"[warning]{len(videos_to_remux)} need remux[/warning], "
                  f"[error]{len(videos_to_reencode)} need re-encode[/error]")
            console.print()

            # Check for existing QuickLook outputs to avoid re-processing
            if videos_to_remux or videos_to_reencode:
                console.print("Checking for existing QuickLook outputs...")
                videos_remux_needed = []
                videos_reencode_needed = []
                videos_already_fixed = []

                all_videos_to_check = videos_to_remux + videos_to_reencode

                with create_batch_progress() as progress:
                    overall = progress.add_task("Checking for existing outputs", total=len(all_videos_to_check))
                    current = progress.add_task("", total=None)
                    for video_path in all_videos_to_check:
                        progress.update(current, description=video_path.name)
                        existing_output = encoder.find_existing_output(
                            video_path,
                            target_codec=args.target_codec,
                            check_suffixes=['_quicklook', '_reencoded']
                        )

                        if existing_output:
                            videos_already_fixed.append((video_path, existing_output))
                        else:
                            if video_path in videos_to_remux:
                                videos_remux_needed.append(video_path)
                            else:
                                videos_reencode_needed.append(video_path)

                        progress.advance(overall)

                console.print()
                if videos_already_fixed:
                    console.print(f"Found {len(videos_already_fixed)} video(s) with existing valid QuickLook outputs (skipping)")
                console.print(f"Need to fix: {len(videos_remux_needed) + len(videos_reencode_needed)} video(s)")
                console.print()

                # Update the lists with only videos that need processing
                videos_to_remux = videos_remux_needed
                videos_to_reencode = videos_reencode_needed

            # Combine all videos that need fixing (remux or re-encode)
            all_videos_to_fix = videos_to_remux + videos_to_reencode

            # Process with queue mode if enabled
            if all_videos_to_fix and args.queue_mode:
                section_header("QUEUE MODE ENABLED FOR QUICKLOOK FIX",
                    f"Temp directory: {args.temp_dir or 'system temp'}\n"
                    f"Buffer size: {args.buffer_size} files\n"
                    f"Max temp storage: {args.max_temp_size} GB\n\n"
                    "Pipeline stages:\n"
                    "  1. DOWNLOAD: Network \u2192 Local temp storage\n"
                    "  2. FIX: Remux or re-encode (local, fast!)\n"
                    "  3. UPLOAD: Local \u2192 Network")

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
                    console.print("Resumed from previous session")
                    console.print()

                # Add files to queue
                queue_manager.add_files(all_videos_to_fix)

                # Create processing callback
                def quicklook_fix_callback(local_input: Path, local_output: Path, progress=None, file_task=None) -> bool:
                    """Callback for fixing QuickLook compatibility in queue mode"""
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
                        result = encoder.remux_to_mp4(local_input, local_output)
                        return result
                    elif needs_reencode:
                        result = encoder.re_encode_video(
                            local_input,
                            local_output,
                            target_codec=args.target_codec,
                            video_info=video_info,
                            keep_original=True,
                            replace_original=False,
                            progress=progress,
                            file_task=file_task,
                        )
                        return result
                    else:
                        return False

                try:
                    # Start the queue
                    start_shutdown_listener()
                    queue_manager.start(quicklook_fix_callback)

                    # Show final progress
                    progress = queue_manager.get_progress()
                    section_header("QUEUE MODE COMPLETE")
                    console.print(f"Completed: [success]{progress['complete']}[/success]")
                    if progress['failed'] > 0:
                        console.print(f"Failed: [error]{progress['failed']}[/error]")

                except KeyboardInterrupt:
                    console.print("\n\nInterrupted by user. Queue state saved for resume.")
                    console.print("Run the same command again to resume from where you left off.")
                    analyzer.save_cache()
                    sys.exit(0)
                finally:
                    stop_shutdown_listener()

            # Otherwise process directly (no queue mode)
            elif all_videos_to_fix:
                # Remux videos (fast - just container change)
                if videos_to_remux:
                    section_header("REMUXING FOR QUICKLOOK COMPATIBILITY (FAST)")

                    for video_path in videos_to_remux:
                        output_path = video_path.parent / f"{video_path.stem}_quicklook.mp4"

                        console.print(f"Remuxing: {video_path.name}")
                        result = encoder.remux_to_mp4(video_path, output_path)

                        if result:
                            if args.replace_original:
                                # Delete original and rename output
                                video_path.unlink()
                                output_path.rename(video_path.with_suffix('.mp4'))
                                console.print(f"[success]\u2713 Replaced: {video_path.name} \u2192 {video_path.stem}.mp4[/success]")
                            else:
                                console.print(f"[success]\u2713 Created: {output_path.name}[/success]")
                        else:
                            console.print(f"[error]\u2717 Failed: {video_path.name}[/error]")

                    console.print()

                # Re-encode videos (slower - needs full re-encode)
                if videos_to_reencode:
                    section_header("RE-ENCODING FOR QUICKLOOK COMPATIBILITY")

                    for video_path in videos_to_reencode:
                        video_info = analyzer.get_video_info(video_path)
                        output_path = video_path.parent / f"{video_path.stem}_quicklook.mp4"

                        console.print(f"Re-encoding: {video_path.name}")
                        result = encoder.re_encode_video(
                            video_path,
                            output_path,
                            target_codec=args.target_codec,
                            video_info=video_info,
                            keep_original=not args.replace_original
                        )

                        if result:
                            if args.replace_original:
                                # Delete original and rename output
                                if video_path.exists() and video_path != output_path:
                                    video_path.unlink()
                                if output_path != video_path.with_suffix('.mp4'):
                                    output_path.rename(video_path.with_suffix('.mp4'))
                                console.print(f"[success]\u2713 Replaced: {video_path.name} \u2192 {video_path.stem}.mp4[/success]")
                            else:
                                console.print(f"[success]\u2713 Created: {output_path.name}[/success]")
                        else:
                            console.print(f"[error]\u2717 Failed: {video_path.name}[/error]")

                    console.print()

    # Find duplicates
    if args.find_duplicates or args.filename_duplicates:
        # Stop shutdown listener to restore normal terminal mode for input prompts
        stop_shutdown_listener()

        subtitle_parts = []
        if args.filename_duplicates:
            subtitle_parts.append("Method: Filename matching - fast, no perceptual hashing")
        else:
            subtitle_parts.append("Method: Perceptual hashing")
        if args.duplicate_action != 'report':
            subtitle_parts.append(f"Action: {args.duplicate_action}")
        section_header("DUPLICATE VIDEO DETECTION", "\n".join(subtitle_parts))

        # Use filename-based detection if requested, otherwise use perceptual hashing
        failed_videos = []
        if args.filename_duplicates:
            duplicate_groups = duplicate_detector.find_duplicates_by_filename(
                video_files,
                analyzer=analyzer,
                check_duration=not args.ignore_duration
            )
        else:
            duplicate_groups, failed_videos = duplicate_detector.find_duplicates(video_files)

        if failed_videos:
            console.print()
            console.print(f"[warning]WARNING: The following {len(failed_videos)} files failed the integrity check (could not be read/hashed):[/warning]")
            for video in failed_videos:
                console.print(f"  - [error]{video.name}[/error]")

        if duplicate_groups:
            console.print()
            console.print(f"Found {len(duplicate_groups)} groups of duplicate videos:")
            console.print()

            all_to_delete = []
            all_to_keep = []
            # Map deleted files to their corresponding kept file for space calculation
            delete_to_keep_map = {}

            if args.duplicate_action == 'report':
                # Just report duplicates, no action
                for group_name, videos in duplicate_groups.items():
                    console.print(f"{group_name} ({len(videos)} videos):")
                    for video in videos:
                        file_size_mb = video.stat().st_size / (1024 * 1024)
                        console.print(f"  - {video.name} ({file_size_mb:.2f} MB)")
                    console.print()
            else:
                # Handle each group with auto-best or interactive
                for group_name, videos in duplicate_groups.items():
                    console.print(f"{group_name}:")
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
                    console.print()

                # Perform deletions if any
                if all_to_delete:
                    section_header(f"DELETING {len(all_to_delete)} DUPLICATE FILES")

                    if args.duplicate_action == 'auto-best':
                        # Auto mode - delete immediately
                        confirm = input(f"\nDelete {len(all_to_delete)} files? (yes/no): ").strip('\r\n\t ').replace('\r', '').replace('\n', '').lower()
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

                                    console.print(f"  [success]\u2713[/success] Deleted: {video.name}")
                                except Exception as e:
                                    console.print(f"  [error]\u2717[/error] Failed to delete {video.name}: {e}")

                            console.print()
                            console.print(f"Successfully deleted {deleted_count}/{len(all_to_delete)} files")
                            console.print(f"Total space freed: {total_size_freed / (1024*1024):.2f} MB")
                            console.print(f"Incremental space saved: {incremental_space_saved / (1024*1024):.2f} MB")
                        else:
                            console.print(f"[warning]\u2192 Deletion cancelled[/warning]")
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

                                console.print(f"  [success]\u2713[/success] Deleted: {video.name}")
                            except Exception as e:
                                console.print(f"  [error]\u2717[/error] Failed to delete {video.name}: {e}")

                        console.print()
                        console.print(f"Successfully deleted {deleted_count}/{len(all_to_delete)} files")
                        console.print(f"Total space freed: {total_size_freed / (1024*1024):.2f} MB")
                        console.print(f"Incremental space saved: {incremental_space_saved / (1024*1024):.2f} MB")
                    console.print()

                    # Clean up filenames of kept files (remove _reencoded and _quicklook suffixes)
                    if all_to_keep:
                        section_header("CLEANING UP FILENAMES")

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
                                    console.print(f"  [warning]\u26a0[/warning] Skipping {video.name}: {new_path.name} already exists")
                                else:
                                    try:
                                        video.rename(new_path)
                                        renamed_count += 1
                                        console.print(f"  [success]\u2713[/success] Renamed: {video.name} \u2192 {new_path.name}")
                                    except Exception as e:
                                        console.print(f"  [error]\u2717[/error] Failed to rename {video.name}: {e}")

                        if renamed_count > 0:
                            console.print()
                            console.print(f"Renamed {renamed_count} file(s)")
                        else:
                            console.print(f"No files needed renaming")
                        console.print()
                else:
                    console.print()
                    console.print(f"[warning]No duplicates marked for deletion[/warning]")

            console.print(f"Total duplicates: {sum(len(v) for v in duplicate_groups.values())} videos in {len(duplicate_groups)} groups")
        else:
            console.print()
            console.print("No duplicate videos found.")

        console.print()

    # Check for issues
    if args.check_issues:
        subtitle = "Deep scan mode: decoding entire videos" if args.deep_scan else None
        section_header("ENCODING ISSUE DETECTION", subtitle)

        videos_with_issues = []

        scan_desc = "Deep scanning videos" if args.deep_scan else "Checking for issues"
        with create_batch_progress() as progress:
            overall = progress.add_task(scan_desc, total=len(video_files))
            current = progress.add_task("", total=None)
            for video_path in video_files:
                progress.update(current, description=video_path.name)
                issues = issue_detector.scan_video(video_path, deep_scan=args.deep_scan)

                if issues:
                    videos_with_issues.append((video_path, issues))

                progress.advance(overall)

        # Print all issues after progress bar is gone
        if videos_with_issues:
            console.print()
            for video_path, issues in videos_with_issues:
                console.print(f"{video_path.name}:")
                for issue in issues:
                    severity_symbol = {
                        'critical': '\u2717',
                        'warning': '\u26a0',
                        'info': '\u2139'
                    }.get(issue.severity, '\u2022')

                    severity_style = {
                        'critical': 'error',
                        'warning': 'warning',
                        'info': 'info'
                    }.get(issue.severity, '')

                    console.print(f"  [{severity_style}]{severity_symbol} [{issue.severity.upper()}] {issue.issue_type}: {issue.description}[/{severity_style}]")

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

            console.print()
            console.print(f"Summary: {len(videos_with_issues)} videos with issues")
            console.print(f"  Critical: {critical_count}")
            console.print(f"  Warnings: {warning_count}")
        else:
            console.print("\nNo issues detected.")

        console.print()

    section_header("VideoSentinel scan complete!")

    analyzer.save_cache()


if __name__ == '__main__':
    main()
