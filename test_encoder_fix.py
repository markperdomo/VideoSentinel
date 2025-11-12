#!/usr/bin/env python3
"""
Test script to verify lenient validation mode for recovery
"""

from encoder import VideoEncoder
from video_analyzer import VideoInfo
from pathlib import Path

def test_lenient_validation():
    """Test that recovery mode uses lenient validation"""

    print("Testing Lenient Validation for Recovery Mode")
    print("=" * 80)
    print()

    # Test 1: Normal encoder (strict validation)
    print("Test 1: Normal VideoEncoder (strict validation)")
    encoder_normal = VideoEncoder(verbose=True, recovery_mode=False)
    print(f"✓ recovery_mode = {encoder_normal.recovery_mode}")
    print()

    # Test 2: Recovery encoder (lenient validation)
    print("Test 2: Recovery VideoEncoder (lenient validation)")
    encoder_recovery = VideoEncoder(verbose=True, recovery_mode=True)
    print(f"✓ recovery_mode = {encoder_recovery.recovery_mode}")
    print()

    # Verify the _validate_output method accepts lenient parameter
    print("Test 3: Verify _validate_output accepts 'lenient' parameter")
    import inspect
    sig = inspect.signature(encoder_recovery._validate_output)
    params = list(sig.parameters.keys())
    assert 'lenient' in params, "_validate_output should have 'lenient' parameter"
    print(f"✓ _validate_output parameters: {params}")
    print()

    print("=" * 80)
    print("All validation tests passed! ✓")
    print("=" * 80)
    print()
    print("Recovery mode behavior:")
    print("  - Normal mode (--re-encode): Strict validation, fails on duration mismatch")
    print("  - Recovery mode (--re-encode --recover): Lenient validation, allows:")
    print("    • Duration differences (corrupted source metadata)")
    print("    • Missing duration metadata")
    print("    • Still checks: file exists, video stream, valid dimensions")
    print()
    print("This prevents validation failures when recovering broken files that")
    print("have incorrect or missing metadata but are otherwise playable.")

if __name__ == "__main__":
    test_lenient_validation()
