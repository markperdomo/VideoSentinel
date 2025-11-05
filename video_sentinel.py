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
from typing import List
from tqdm import tqdm

from video_analyzer import VideoAnalyzer, VideoInfo
from duplicate_detector import DuplicateDetector
from issue_detector import IssueDetector
from encoder import VideoEncoder


def main():
    """Main entry point for VideoSentinel CLI"""
    parser = argparse.ArgumentParser(
        description='VideoSentinel - Manage and validate your video library',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        'directory',
        type=Path,
        help='Directory containing video files to analyze'
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
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )

    args = parser.parse_args()

    # Validate input directory
    if not args.directory.exists():
        print(f"Error: Directory '{args.directory}' does not exist", file=sys.stderr)
        sys.exit(1)

    if not args.directory.is_dir():
        print(f"Error: '{args.directory}' is not a directory", file=sys.stderr)
        sys.exit(1)

    # If no action specified, show all checks by default
    if not any([args.check_specs, args.find_duplicates, args.check_issues]):
        args.check_specs = True
        args.find_duplicates = True
        args.check_issues = True

    # Check ffmpeg availability
    encoder = VideoEncoder(verbose=args.verbose)
    if not encoder.check_ffmpeg_available():
        print("Error: ffmpeg is not installed or not in PATH", file=sys.stderr)
        print("Please install ffmpeg to use VideoSentinel", file=sys.stderr)
        sys.exit(1)

    print("="*80)
    print(f"VideoSentinel - Video Library Manager")
    print("="*80)
    print(f"Scanning directory: {args.directory}")
    print(f"Recursive scan: {args.recursive}")
    print(f"Target codec: {args.target_codec.upper()}")
    print("="*80)
    print()

    # Initialize components
    analyzer = VideoAnalyzer(verbose=args.verbose)
    duplicate_detector = DuplicateDetector(verbose=args.verbose)
    issue_detector = IssueDetector(verbose=args.verbose)

    # Find all video files
    print("Finding video files...")
    video_files = analyzer.find_videos(args.directory, recursive=args.recursive)

    if not video_files:
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
                tqdm.write(f"✗ {video_path.name}: Unable to analyze")
                continue

            is_compliant = analyzer.meets_modern_specs(video_info)

            if is_compliant:
                compliant_videos.append(video_path)
                if args.verbose:
                    tqdm.write(f"✓ {video_path.name}: Meets specs ({video_info.codec}, {video_info.width}x{video_info.height})")
            else:
                non_compliant_videos.append((video_path, video_info))
                tqdm.write(f"✗ {video_path.name}")
                tqdm.write(f"    Codec: {video_info.codec} (should be H.265/HEVC or better)")
                tqdm.write(f"    Resolution: {video_info.width}x{video_info.height}")
                tqdm.write(f"    Container: {video_info.container}")

        print()
        print(f"Summary: {len(compliant_videos)} compliant, {len(non_compliant_videos)} non-compliant")
        print()

        # Re-encode if requested
        if args.re_encode and non_compliant_videos:
            print("="*80)
            print("RE-ENCODING NON-COMPLIANT VIDEOS")
            print("(Using smart quality matching to preserve visual quality)")
            print("="*80)

            # Filter by file types if specified
            videos_to_encode_tuples = non_compliant_videos
            if args.file_types:
                # Parse file types (remove dots and convert to lowercase)
                target_extensions = [
                    ext.strip().lower().lstrip('.')
                    for ext in args.file_types.split(',')
                ]

                # Filter videos by extension
                filtered_videos = [
                    (path, info) for path, info in non_compliant_videos
                    if path.suffix.lower().lstrip('.') in target_extensions
                ]

                skipped_count = len(non_compliant_videos) - len(filtered_videos)

                print()
                print(f"File type filter: {', '.join(target_extensions).upper()}")
                print(f"Videos matching filter: {len(filtered_videos)}")
                if skipped_count > 0:
                    print(f"Videos skipped (other formats): {skipped_count}")
                print()

                videos_to_encode_tuples = filtered_videos

            if not videos_to_encode_tuples:
                print("No videos match the file type filter.")
                print()
            else:
                videos_to_encode = [v[0] for v in videos_to_encode_tuples]
                video_infos_dict = {v[0]: v[1] for v in videos_to_encode_tuples}

                encoder.batch_re_encode(
                    videos_to_encode,
                    output_dir=args.output_dir,
                    target_codec=args.target_codec,
                    video_infos=video_infos_dict
                )

    # Find duplicates
    if args.find_duplicates:
        print("="*80)
        print("DUPLICATE VIDEO DETECTION")
        print("="*80)

        duplicate_groups = duplicate_detector.find_duplicates(video_files)

        if duplicate_groups:
            print(f"\nFound {len(duplicate_groups)} groups of duplicate videos:\n")

            for group_name, videos in duplicate_groups.items():
                print(f"{group_name} ({len(videos)} videos):")
                for video in videos:
                    file_size_mb = video.stat().st_size / (1024 * 1024)
                    print(f"  - {video.name} ({file_size_mb:.2f} MB)")
                print()

            print(f"Total duplicates: {sum(len(v) for v in duplicate_groups.values())} videos in {len(duplicate_groups)} groups")
        else:
            print("\nNo duplicate videos found.")

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
                tqdm.write(f"\n{video_path.name}:")
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
