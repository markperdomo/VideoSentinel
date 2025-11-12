#!/usr/bin/env python3
"""
Test script for filename-based duplicate detection
"""

from pathlib import Path
from duplicate_detector import DuplicateDetector

def test_filename_duplicates():
    """Test the filename-based duplicate detection logic"""

    # Create a detector instance
    detector = DuplicateDetector(verbose=True)

    # Simulate test files with various naming patterns
    test_files = [
        Path("/test/video.mp4"),
        Path("/test/video_reencoded.mp4"),
        Path("/test/video_quicklook.mp4"),
        Path("/test/video.avi"),
        Path("/test/another.wmv"),
        Path("/test/another_reencoded.mp4"),
        Path("/test/Movie.mkv"),
        Path("/test/MOVIE_reencoded.mp4"),  # Different case
        Path("/test/unique.mp4"),  # No duplicates
    ]

    print("Testing filename-based duplicate detection:")
    print("=" * 80)
    print()

    print("Test files:")
    for f in test_files:
        print(f"  - {f.name}")
    print()

    # Run filename-based duplicate detection
    duplicate_groups = detector.find_duplicates_by_filename(test_files)

    print(f"\nFound {len(duplicate_groups)} duplicate groups:")
    print()

    # Expected groups:
    # 1. video.mp4, video_reencoded.mp4, video_quicklook.mp4, video.avi
    # 2. another.wmv, another_reencoded.mp4
    # 3. Movie.mkv, MOVIE_reencoded.mp4 (case-insensitive)

    for group_name, videos in duplicate_groups.items():
        print(f"{group_name} ({len(videos)} files):")
        for video in videos:
            print(f"  - {video.name}")
        print()

    # Verify expected results
    print("Verification:")
    print("=" * 80)

    assert len(duplicate_groups) == 3, f"Expected 3 groups, got {len(duplicate_groups)}"
    print("✓ Correct number of duplicate groups (3)")

    # Find the group with "video" files
    video_group = None
    another_group = None
    movie_group = None

    for group_name, videos in duplicate_groups.items():
        filenames = [v.name for v in videos]
        if "video.mp4" in filenames:
            video_group = videos
        elif "another.wmv" in filenames:
            another_group = videos
        elif any("movie" in v.name.lower() for v in videos):
            movie_group = videos

    assert video_group is not None and len(video_group) == 4, \
        f"Expected 4 'video' files, got {len(video_group) if video_group else 0}"
    print("✓ Correctly grouped 4 'video' variants (different extensions and suffixes)")

    assert another_group is not None and len(another_group) == 2, \
        f"Expected 2 'another' files, got {len(another_group) if another_group else 0}"
    print("✓ Correctly grouped 2 'another' variants")

    assert movie_group is not None and len(movie_group) == 2, \
        f"Expected 2 'movie' files (case-insensitive), got {len(movie_group) if movie_group else 0}"
    print("✓ Correctly grouped 2 'Movie' variants (case-insensitive)")

    # Verify unique.mp4 is NOT in any group
    for group_name, videos in duplicate_groups.items():
        for video in videos:
            assert video.name != "unique.mp4", "unique.mp4 should not be in any duplicate group"
    print("✓ Correctly excluded 'unique.mp4' (no duplicates)")

    print()
    print("=" * 80)
    print("All tests passed! ✓")
    print("=" * 80)

if __name__ == "__main__":
    test_filename_duplicates()
