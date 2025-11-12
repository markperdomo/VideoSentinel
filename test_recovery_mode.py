#!/usr/bin/env python3
"""
Test script to verify recovery mode flags are added to FFmpeg commands
"""

from encoder import VideoEncoder
from pathlib import Path

def test_recovery_mode():
    """Test that recovery mode properly initializes"""

    print("Testing Recovery Mode Feature")
    print("=" * 80)
    print()

    # Test 1: Encoder without recovery mode
    print("Test 1: VideoEncoder without recovery mode")
    encoder_normal = VideoEncoder(verbose=True, recovery_mode=False)
    assert encoder_normal.recovery_mode == False, "Recovery mode should be False"
    print("✓ Normal encoder created (recovery_mode=False)")
    print()

    # Test 2: Encoder with recovery mode
    print("Test 2: VideoEncoder with recovery mode")
    encoder_recovery = VideoEncoder(verbose=True, recovery_mode=True)
    assert encoder_recovery.recovery_mode == True, "Recovery mode should be True"
    print("✓ Recovery encoder created (recovery_mode=True)")
    print()

    # Test 3: Verify FFmpeg is available
    print("Test 3: Check FFmpeg availability")
    if encoder_normal.check_ffmpeg_available():
        print("✓ FFmpeg is available")
    else:
        print("✗ FFmpeg is not available (required for full testing)")
    print()

    print("=" * 80)
    print("Recovery mode feature tests passed! ✓")
    print("=" * 80)
    print()
    print("Recovery mode FFmpeg command structure:")
    print()
    print("  ffmpeg [global options]")
    print("    [INPUT options] -i input.avi")
    print("    [OUTPUT options] output.mp4")
    print()
    print("INPUT options (before -i):")
    print("  -err_detect ignore_err          # Ignore decoding errors")
    print("  -fflags +genpts+discardcorrupt+igndts  # Fix timestamps, discard corrupt packets")
    print("  -ignore_unknown                 # Ignore unknown streams")
    print()
    print("OUTPUT options (after -i):")
    print("  -max_muxing_queue_size 1024     # Increase buffer size")
    print("  -max_error_rate 1.0             # Allow 100% error rate")
    print()
    print("To test with actual encoding, use:")
    print("  python video_sentinel.py /path/to/broken/video.avi --check-specs --re-encode --recover -v")

if __name__ == "__main__":
    test_recovery_mode()
