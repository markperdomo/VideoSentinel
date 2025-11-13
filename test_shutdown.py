#!/usr/bin/env python3
"""
Test script to verify graceful shutdown works during encoding

This script tests both:
1. Pressing 'q' during encoding (graceful shutdown)
2. Pressing Ctrl+C during encoding (interrupt handling)

Usage:
    python test_shutdown.py <path_to_test_video>

Instructions:
    - The script will start encoding the video
    - Try pressing 'q' during encoding - it should stop after current progress update
    - Or try pressing Ctrl+C - it should also stop gracefully
"""

import sys
from pathlib import Path
from encoder import VideoEncoder
from video_analyzer import VideoAnalyzer
from shutdown_manager import start_shutdown_listener, stop_shutdown_listener


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_shutdown.py <path_to_test_video>")
        print()
        print("This script tests graceful shutdown during encoding.")
        print("While encoding, try:")
        print("  - Press 'q' to trigger graceful shutdown")
        print("  - Press Ctrl+C to test interrupt handling")
        sys.exit(1)

    input_path = Path(sys.argv[1])

    if not input_path.exists():
        print(f"Error: File not found: {input_path}")
        sys.exit(1)

    print("="*80)
    print("GRACEFUL SHUTDOWN TEST")
    print("="*80)
    print()
    print(f"Input: {input_path}")
    print()
    print("💡 During encoding, you can:")
    print("   - Press 'q' to trigger graceful shutdown (will stop after current video)")
    print("   - Press Ctrl+C to test interrupt handling")
    print()
    print("="*80)
    print()

    # Create encoder and analyzer
    encoder = VideoEncoder(verbose=True)
    analyzer = VideoAnalyzer(verbose=True)

    # Analyze input video
    print("Analyzing input video...")
    video_info = analyzer.get_video_info(input_path)

    if not video_info or not video_info.is_valid:
        print("Error: Could not analyze video")
        sys.exit(1)

    print(f"Video info: {video_info.width}x{video_info.height}, {video_info.codec}, {video_info.duration:.1f}s")
    print()

    # Create output path
    output_path = input_path.parent / f"{input_path.stem}_test_shutdown.mp4"

    # Start shutdown listener
    start_shutdown_listener()

    try:
        # Encode video
        print("Starting encoding...")
        print("(Try pressing 'q' or Ctrl+C now)")
        print()

        success = encoder.re_encode_video(
            input_path,
            output_path,
            target_codec='hevc',
            video_info=video_info,
            keep_original=True
        )

        if success:
            print()
            print("="*80)
            print("SUCCESS - Encoding completed")
            print("="*80)
            print(f"Output: {output_path}")
            print()
        else:
            print()
            print("="*80)
            print("ENCODING STOPPED")
            print("="*80)
            print("This is expected if you pressed 'q' or Ctrl+C")
            print()

    except KeyboardInterrupt:
        print()
        print("="*80)
        print("INTERRUPTED (Ctrl+C detected)")
        print("="*80)
        print("This is the expected behavior!")
        print()
    finally:
        stop_shutdown_listener()

    # Cleanup test output if it exists
    if output_path.exists():
        print(f"Cleaning up test output: {output_path}")
        output_path.unlink()


if __name__ == "__main__":
    main()
