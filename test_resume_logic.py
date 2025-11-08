#!/usr/bin/env python3
"""
Test script for the resume logic that checks for existing re-encoded outputs
"""

import tempfile
import shutil
from pathlib import Path
from encoder import VideoEncoder

def test_find_existing_output():
    """Test the find_existing_output method"""

    # Create a temporary directory for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Copy our test video to simulate a source file
        source_video = Path("properly encoded hevc video.mp4")
        if not source_video.exists():
            print("❌ Test video not found")
            return False

        test_source = tmpdir / "test_video.avi"
        shutil.copy(source_video, test_source)

        # Initialize encoder
        encoder = VideoEncoder(verbose=True)

        print("\n" + "="*80)
        print("TEST 1: No existing output - should return None")
        print("="*80)
        result = encoder.find_existing_output(test_source, target_codec='hevc')
        if result is None:
            print("✓ PASS: Correctly returned None when no output exists")
        else:
            print(f"❌ FAIL: Expected None, got {result}")
            return False

        print("\n" + "="*80)
        print("TEST 2: Valid _reencoded output exists - should return the path")
        print("="*80)
        # Create a valid _reencoded output
        reencoded_path = tmpdir / "test_video_reencoded.mp4"
        shutil.copy(source_video, reencoded_path)

        result = encoder.find_existing_output(test_source, target_codec='hevc')
        if result == reencoded_path:
            print(f"✓ PASS: Correctly found existing output: {result.name}")
        else:
            print(f"❌ FAIL: Expected {reencoded_path}, got {result}")
            return False

        print("\n" + "="*80)
        print("TEST 3: Valid _quicklook output exists - should return the path")
        print("="*80)
        # Remove _reencoded and create _quicklook instead
        reencoded_path.unlink()
        quicklook_path = tmpdir / "test_video_quicklook.mp4"
        shutil.copy(source_video, quicklook_path)

        result = encoder.find_existing_output(test_source, target_codec='hevc')
        if result == quicklook_path:
            print(f"✓ PASS: Correctly found existing output: {result.name}")
        else:
            print(f"❌ FAIL: Expected {quicklook_path}, got {result}")
            return False

        print("\n" + "="*80)
        print("TEST 4: Invalid (tiny) output exists - should remove it and return None")
        print("="*80)
        # Remove valid output and create an invalid one
        quicklook_path.unlink()
        invalid_path = tmpdir / "test_video_reencoded.mp4"
        invalid_path.write_text("invalid")  # Create a tiny invalid file

        result = encoder.find_existing_output(test_source, target_codec='hevc')
        if result is None and not invalid_path.exists():
            print("✓ PASS: Correctly removed invalid output and returned None")
        else:
            print(f"❌ FAIL: Expected None and file removed, got {result}, exists: {invalid_path.exists()}")
            return False

        print("\n" + "="*80)
        print("ALL TESTS PASSED! ✓")
        print("="*80)
        return True

if __name__ == "__main__":
    success = test_find_existing_output()
    exit(0 if success else 1)
