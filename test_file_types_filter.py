#!/usr/bin/env python3
"""
Test script for --file-types filtering functionality

This test verifies that:
1. The find_videos method correctly filters by file types
2. File type filtering happens at the discovery stage
3. Multiple file types can be specified
4. Invalid file types are handled gracefully
"""

import tempfile
import sys
from pathlib import Path
from video_analyzer import VideoAnalyzer


def create_test_files(test_dir: Path):
    """Create dummy video files with various extensions for testing"""
    test_files = [
        'video1.mp4',
        'video2.mkv',
        'video3.avi',
        'video4.wmv',
        'video5.mov',
        'video6.flv',
        'video7.mp4',
        'video8.avi',
        'document.txt',  # Non-video file
        'image.jpg',     # Non-video file
    ]

    created = []
    for filename in test_files:
        file_path = test_dir / filename
        file_path.touch()  # Create empty file
        created.append(file_path)

    return created


def test_no_filter():
    """Test finding all video files without filter"""
    print("="*60)
    print("Test 1: Find all video files (no filter)")
    print("="*60)

    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir)
        create_test_files(test_dir)

        analyzer = VideoAnalyzer(verbose=False)
        videos = analyzer.find_videos(test_dir)

        print(f"Found {len(videos)} video files:")
        for video in videos:
            print(f"  - {video.name}")

        # Should find all video files (8 total), not txt or jpg
        expected = 8
        if len(videos) == expected:
            print(f"✓ PASS: Found {expected} videos as expected")
            return True
        else:
            print(f"✗ FAIL: Expected {expected} videos, found {len(videos)}")
            return False


def test_single_type_filter():
    """Test filtering for a single file type"""
    print()
    print("="*60)
    print("Test 2: Filter for AVI files only")
    print("="*60)

    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir)
        create_test_files(test_dir)

        analyzer = VideoAnalyzer(verbose=False)
        videos = analyzer.find_videos(test_dir, file_types=['avi'])

        print(f"Found {len(videos)} AVI files:")
        for video in videos:
            print(f"  - {video.name}")

        # Should find only AVI files (2 total)
        expected = 2
        all_avi = all(v.suffix.lower() == '.avi' for v in videos)

        if len(videos) == expected and all_avi:
            print(f"✓ PASS: Found {expected} AVI files as expected")
            return True
        else:
            print(f"✗ FAIL: Expected {expected} AVI files, found {len(videos)}")
            return False


def test_multiple_types_filter():
    """Test filtering for multiple file types"""
    print()
    print("="*60)
    print("Test 3: Filter for WMV and MOV files")
    print("="*60)

    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir)
        create_test_files(test_dir)

        analyzer = VideoAnalyzer(verbose=False)
        videos = analyzer.find_videos(test_dir, file_types=['wmv', 'mov'])

        print(f"Found {len(videos)} WMV/MOV files:")
        for video in videos:
            print(f"  - {video.name}")

        # Should find WMV and MOV files (2 total: video4.wmv, video5.mov)
        expected = 2
        all_wmv_or_mov = all(v.suffix.lower() in ['.wmv', '.mov'] for v in videos)

        if len(videos) == expected and all_wmv_or_mov:
            print(f"✓ PASS: Found {expected} WMV/MOV files as expected")
            return True
        else:
            print(f"✗ FAIL: Expected {expected} WMV/MOV files, found {len(videos)}")
            return False


def test_extension_normalization():
    """Test that extensions are normalized (with/without dots, case)"""
    print()
    print("="*60)
    print("Test 4: Extension normalization (.MP4, mp4, MP4)")
    print("="*60)

    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir)
        create_test_files(test_dir)

        analyzer = VideoAnalyzer(verbose=False)

        # Test various forms of specifying mp4
        for file_types in [['.MP4'], ['mp4'], ['MP4']]:
            videos = analyzer.find_videos(test_dir, file_types=file_types)
            if len(videos) != 2:  # Should find 2 MP4 files
                print(f"✗ FAIL: file_types={file_types} found {len(videos)} files (expected 2)")
                return False

        print("✓ PASS: All extension forms (.MP4, mp4, MP4) work correctly")
        return True


def test_invalid_type():
    """Test handling of invalid file types"""
    print()
    print("="*60)
    print("Test 5: Invalid file type (non-video extension)")
    print("="*60)

    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir)
        create_test_files(test_dir)

        analyzer = VideoAnalyzer(verbose=False)
        videos = analyzer.find_videos(test_dir, file_types=['txt', 'jpg'])

        print(f"Found {len(videos)} files with invalid types:")
        for video in videos:
            print(f"  - {video.name}")

        # Should find 0 files (txt and jpg are not video extensions)
        if len(videos) == 0:
            print("✓ PASS: Invalid types correctly return no results")
            return True
        else:
            print(f"✗ FAIL: Expected 0 files for invalid types, found {len(videos)}")
            return False


def test_mixed_valid_invalid():
    """Test filtering with mix of valid and invalid types"""
    print()
    print("="*60)
    print("Test 6: Mix of valid (mp4) and invalid (txt) types")
    print("="*60)

    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir)
        create_test_files(test_dir)

        analyzer = VideoAnalyzer(verbose=False)
        videos = analyzer.find_videos(test_dir, file_types=['mp4', 'txt'])

        print(f"Found {len(videos)} files:")
        for video in videos:
            print(f"  - {video.name}")

        # Should find only MP4 files (2 total), txt should be filtered out
        expected = 2
        all_mp4 = all(v.suffix.lower() == '.mp4' for v in videos)

        if len(videos) == expected and all_mp4:
            print(f"✓ PASS: Found {expected} MP4 files, invalid type filtered out")
            return True
        else:
            print(f"✗ FAIL: Expected {expected} MP4 files, found {len(videos)}")
            return False


def main():
    """Run all tests"""
    print()
    print("╔═══════════════════════════════════════════════════════╗")
    print("║        File Types Filter Test Suite                  ║")
    print("╚═══════════════════════════════════════════════════════╝")
    print()

    tests = [
        test_no_filter,
        test_single_type_filter,
        test_multiple_types_filter,
        test_extension_normalization,
        test_invalid_type,
        test_mixed_valid_invalid,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"✗ FAIL: Test raised exception: {e}")
            failed += 1

    print()
    print("="*60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("="*60)
    print()

    if failed == 0:
        print("✓ ALL TESTS PASSED")
        return 0
    else:
        print("✗ SOME TESTS FAILED")
        return 1


if __name__ == '__main__':
    sys.exit(main())
