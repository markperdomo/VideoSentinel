#!/usr/bin/env python3
"""
Test quality ranking to ensure HEVC files rank higher than H.264 even with lower bitrate
"""

from pathlib import Path
from video_analyzer import VideoInfo
from video_sentinel import rank_video_quality

def test_quality_ranking():
    """Test that HEVC with lower bitrate ranks higher than H.264 with higher bitrate"""

    print("="*80)
    print("Testing Quality Ranking - Codec Efficiency")
    print("="*80)
    print()

    # User's exact scenario
    print("Scenario from bug report:")
    print("  Original: AVC1, 1920x1080, 6801 kbps")
    print("  Re-encoded: HVC1, 1920x1080, 3608 kbps")
    print()

    # Create mock VideoInfo for H.264 original
    h264_video = VideoInfo(
        file_path=Path("original.mp4"),
        codec="avc1",
        container="mp4",
        resolution=(1920, 1080),
        width=1920,
        height=1080,
        fps=30.0,
        duration=600.0,
        bitrate=6801000,
        has_audio=True,
        file_size=510075000,
        is_valid=True
    )

    # Create mock VideoInfo for HEVC re-encoded
    hevc_video = VideoInfo(
        file_path=Path("reencoded.mp4"),
        codec="hvc1",
        container="mp4",
        resolution=(1920, 1080),
        width=1920,
        height=1080,
        fps=30.0,
        duration=600.0,
        bitrate=3608000,
        has_audio=True,
        file_size=270600000,
        is_valid=True
    )

    # Calculate scores
    h264_score = rank_video_quality(Path("original.mp4"), h264_video)
    hevc_score = rank_video_quality(Path("reencoded.mp4"), hevc_video)

    print("Quality Scores:")
    print(f"  H.264 (AVC1) @ 6801 kbps: {h264_score}")
    print(f"  HEVC (HVC1) @ 3608 kbps:  {hevc_score}")
    print()

    # Breakdown
    print("Score Breakdown:")
    print()
    print("  H.264 (AVC1):")
    print(f"    Codec score:      400")
    print(f"    Resolution score: {1920 * 1080 // 1000}")
    print(f"    Bitrate (raw):    {6801000 // 10000}")
    print(f"    Efficiency:       1.0x (baseline)")
    print(f"    Normalized:       {6801000 * 1.0 // 10000}")
    print()
    print("  HEVC (HVC1):")
    print(f"    Codec score:      800")
    print(f"    Resolution score: {1920 * 1080 // 1000}")
    print(f"    Bitrate (raw):    {3608000 // 10000}")
    print(f"    Efficiency:       2.0x (HEVC is 2x more efficient)")
    print(f"    Normalized:       {int(3608000 * 2.0 // 10000)}")
    print()

    if hevc_score > h264_score:
        print("✓ PASS: HEVC correctly ranked higher!")
        print(f"  HEVC wins by {hevc_score - h264_score} points")
        print()
        print("Expected behavior: VideoSentinel will keep the HEVC file")
        return True
    else:
        print("❌ FAIL: H.264 ranked higher than HEVC!")
        print(f"  H.264 wins by {h264_score - hevc_score} points")
        print()
        print("This is wrong! HEVC at lower bitrate should be better quality")
        return False

def test_various_scenarios():
    """Test several codec comparison scenarios"""

    print()
    print("="*80)
    print("Additional Test Scenarios")
    print("="*80)
    print()

    scenarios = [
        {
            'name': 'AV1 vs HEVC (same bitrate)',
            'video1': {'codec': 'av1', 'bitrate': 3000000},
            'video2': {'codec': 'hevc', 'bitrate': 3000000},
            'expected_winner': 'video1',
        },
        {
            'name': 'HEVC vs H.264 (HEVC half bitrate)',
            'video1': {'codec': 'hevc', 'bitrate': 2000000},
            'video2': {'codec': 'h264', 'bitrate': 4000000},
            'expected_winner': 'video1',
        },
        {
            'name': 'Old MPEG4 high bitrate vs HEVC low bitrate',
            'video1': {'codec': 'mpeg4', 'bitrate': 10000000},
            'video2': {'codec': 'hevc', 'bitrate': 3000000},
            'expected_winner': 'video2',
        },
    ]

    all_passed = True

    for scenario in scenarios:
        v1 = VideoInfo(
            file_path=Path("v1.mp4"), codec=scenario['video1']['codec'], container="mp4",
            resolution=(1920, 1080), width=1920, height=1080, fps=30.0, duration=600.0,
            bitrate=scenario['video1']['bitrate'], has_audio=True, file_size=0, is_valid=True
        )
        v2 = VideoInfo(
            file_path=Path("v2.mp4"), codec=scenario['video2']['codec'], container="mp4",
            resolution=(1920, 1080), width=1920, height=1080, fps=30.0, duration=600.0,
            bitrate=scenario['video2']['bitrate'], has_audio=True, file_size=0, is_valid=True
        )

        s1 = rank_video_quality(Path("v1.mp4"), v1)
        s2 = rank_video_quality(Path("v2.mp4"), v2)

        winner = 'video1' if s1 > s2 else 'video2'
        passed = winner == scenario['expected_winner']

        status = "✓ PASS" if passed else "❌ FAIL"
        print(f"{status}: {scenario['name']}")
        print(f"  {scenario['video1']['codec'].upper()} @ {scenario['video1']['bitrate']//1000}kbps: {s1}")
        print(f"  {scenario['video2']['codec'].upper()} @ {scenario['video2']['bitrate']//1000}kbps: {s2}")
        print(f"  Winner: {winner} (expected: {scenario['expected_winner']})")
        print()

        if not passed:
            all_passed = False

    return all_passed

if __name__ == "__main__":
    test1 = test_quality_ranking()
    test2 = test_various_scenarios()

    print("="*80)
    if test1 and test2:
        print("All tests passed! ✓")
    else:
        print("Some tests failed! ❌")
    print("="*80)

    exit(0 if (test1 and test2) else 1)
