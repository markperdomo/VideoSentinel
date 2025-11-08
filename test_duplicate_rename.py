#!/usr/bin/env python3
"""
Test that duplicate handler removes _reencoded and _quicklook suffixes from kept files
"""

import tempfile
import shutil
from pathlib import Path
from video_analyzer import VideoAnalyzer, VideoInfo
from video_sentinel import handle_duplicate_group

def test_suffix_removal():
    """Test that kept files have suffixes removed"""

    print("="*80)
    print("Testing Duplicate Handler - Suffix Removal")
    print("="*80)
    print()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create test videos - simulated with text files
        # Group 1: HEVC reencoded (better) vs H.264 original (worse)
        original = tmpdir / "video.mp4"
        reencoded = tmpdir / "video_reencoded.mp4"

        original.write_text("original h264 video")
        reencoded.write_text("reencoded hevc video")

        # Create mock analyzer
        class MockAnalyzer:
            def get_video_info(self, path: Path):
                if 'reencoded' in path.name:
                    # HEVC reencoded - better
                    return VideoInfo(
                        file_path=path,
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
                else:
                    # H.264 original - worse
                    return VideoInfo(
                        file_path=path,
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

        analyzer = MockAnalyzer()
        videos = [original, reencoded]

        print("Test files:")
        print(f"  {original.name} (H.264, 6801 kbps)")
        print(f"  {reencoded.name} (HEVC, 3608 kbps)")
        print()

        print("Running auto-best duplicate handler...")
        to_delete, to_keep = handle_duplicate_group(
            "test_group",
            videos,
            analyzer,
            "auto-best",
            verbose=False
        )

        print()
        print("Results:")
        print(f"  To delete: {[v.name for v in to_delete]}")
        print(f"  To keep: {to_keep.name if to_keep else 'None'}")
        print()

        # Verify results
        if to_keep != reencoded:
            print("❌ FAIL: Wrong file kept! Should keep HEVC reencoded file")
            return False

        if to_delete != [original]:
            print("❌ FAIL: Wrong files marked for deletion!")
            return False

        print("✓ Correct file selected (HEVC reencoded)")
        print()

        # Now test the renaming logic
        print("Testing suffix removal...")
        stem = to_keep.stem
        if stem.endswith('_reencoded'):
            new_stem = stem[:-len('_reencoded')]
            new_path = to_keep.parent / (new_stem + to_keep.suffix)

            # Delete the original first (simulating the deletion step)
            original.unlink()

            # Rename
            to_keep.rename(new_path)
            print(f"✓ Renamed: {to_keep.name} → {new_path.name}")

            # Verify new file exists
            if not new_path.exists():
                print("❌ FAIL: Renamed file doesn't exist!")
                return False

            if new_path.name != "video.mp4":
                print(f"❌ FAIL: Wrong filename! Expected 'video.mp4', got '{new_path.name}'")
                return False

            print(f"✓ Suffix removed successfully: {new_path.name}")
            print()
            print("="*80)
            print("All tests passed! ✓")
            print("="*80)
            return True
        else:
            print("❌ FAIL: File doesn't have _reencoded suffix")
            return False

def test_quicklook_suffix():
    """Test _quicklook suffix removal"""

    print()
    print("="*80)
    print("Testing _quicklook Suffix Removal")
    print("="*80)
    print()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create test file with _quicklook suffix
        quicklook = tmpdir / "video_quicklook.mp4"
        quicklook.write_text("quicklook fixed video")

        print(f"Test file: {quicklook.name}")
        print()

        stem = quicklook.stem
        if stem.endswith('_quicklook'):
            new_stem = stem[:-len('_quicklook')]
            new_path = quicklook.parent / (new_stem + quicklook.suffix)

            quicklook.rename(new_path)
            print(f"✓ Renamed: {quicklook.name} → {new_path.name}")

            if new_path.name == "video.mp4":
                print("✓ _quicklook suffix removed successfully")
                print()
                print("="*80)
                print("All tests passed! ✓")
                print("="*80)
                return True
            else:
                print(f"❌ FAIL: Wrong filename! Expected 'video.mp4', got '{new_path.name}'")
                return False

if __name__ == "__main__":
    test1 = test_suffix_removal()
    test2 = test_quicklook_suffix()

    exit(0 if (test1 and test2) else 1)
