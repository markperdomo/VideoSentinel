#!/usr/bin/env python3
"""
Test script for graceful shutdown functionality

This test verifies that:
1. The shutdown listener starts successfully
2. The shutdown flag can be set
3. The shutdown flag can be checked
4. The listener stops cleanly
"""

import time
import sys
from shutdown_manager import (
    ShutdownManager,
    start_shutdown_listener,
    stop_shutdown_listener,
    shutdown_requested
)


def test_basic_functionality():
    """Test basic shutdown manager functionality"""
    print("="*60)
    print("Testing Graceful Shutdown Manager")
    print("="*60)
    print()

    # Test 1: Create instance
    print("Test 1: Creating ShutdownManager instance...")
    manager = ShutdownManager()
    print("✓ Instance created")
    print()

    # Test 2: Start listener
    print("Test 2: Starting listener thread...")
    manager.start()
    print("✓ Listener started")
    print()

    # Test 3: Check shutdown status (should be False)
    print("Test 3: Checking initial shutdown status...")
    if not manager.shutdown_requested():
        print("✓ Shutdown not requested (expected)")
    else:
        print("✗ ERROR: Shutdown already requested!")
        return False
    print()

    # Test 4: Manually request shutdown
    print("Test 4: Manually requesting shutdown...")
    manager.request_shutdown()
    print("✓ Shutdown requested")
    print()

    # Test 5: Check shutdown status (should be True now)
    print("Test 5: Verifying shutdown status...")
    if manager.shutdown_requested():
        print("✓ Shutdown status correctly set")
    else:
        print("✗ ERROR: Shutdown status not set!")
        return False
    print()

    # Test 6: Stop listener
    print("Test 6: Stopping listener thread...")
    manager.stop()
    print("✓ Listener stopped")
    print()

    return True


def test_global_functions():
    """Test global convenience functions"""
    print("="*60)
    print("Testing Global Convenience Functions")
    print("="*60)
    print()

    # Test 1: Start global listener
    print("Test 1: Starting global shutdown listener...")
    start_shutdown_listener()
    print("✓ Global listener started")
    print()

    # Test 2: Check status (should be False initially)
    print("Test 2: Checking initial status...")
    if not shutdown_requested():
        print("✓ Shutdown not requested (expected)")
    else:
        print("✗ ERROR: Shutdown already requested!")
        return False
    print()

    # Test 3: Stop listener
    print("Test 3: Stopping global listener...")
    stop_shutdown_listener()
    print("✓ Global listener stopped")
    print()

    return True


def test_simulated_encoding_loop():
    """Simulate an encoding loop with shutdown check"""
    print("="*60)
    print("Testing Simulated Encoding Loop")
    print("="*60)
    print()
    print("This test simulates encoding 5 videos.")
    print("Press 'q' to test graceful shutdown, or wait for all videos to complete.")
    print()

    start_shutdown_listener()

    videos = ["video1.mp4", "video2.mp4", "video3.mp4", "video4.mp4", "video5.mp4"]

    for idx, video in enumerate(videos, start=1):
        # Check for shutdown request
        if shutdown_requested():
            print()
            print("="*60)
            print("SHUTDOWN REQUESTED - Stopping after current video")
            print("="*60)
            print(f"Processed {idx - 1}/{len(videos)} videos before shutdown")
            print()
            break

        print(f"[{idx}/{len(videos)}] Processing: {video}")

        # Simulate encoding time (1 second per video)
        for i in range(10):
            time.sleep(0.1)
            print(".", end="", flush=True)

        print(f" ✓ Completed")
        print()

    stop_shutdown_listener()

    print("Encoding loop finished")
    print()
    return True


def main():
    """Run all tests"""
    print()
    print("╔═══════════════════════════════════════════════════════╗")
    print("║        Graceful Shutdown Manager Test Suite          ║")
    print("╚═══════════════════════════════════════════════════════╝")
    print()

    all_passed = True

    # Run basic functionality tests
    if not test_basic_functionality():
        all_passed = False
        print("✗ Basic functionality tests FAILED")
    else:
        print("✓ Basic functionality tests PASSED")

    print()

    # Run global functions tests
    if not test_global_functions():
        all_passed = False
        print("✗ Global functions tests FAILED")
    else:
        print("✓ Global functions tests PASSED")

    print()

    # Run simulated encoding loop test
    if not test_simulated_encoding_loop():
        all_passed = False
        print("✗ Simulated encoding loop test FAILED")
    else:
        print("✓ Simulated encoding loop test PASSED")

    print()
    print("="*60)
    if all_passed:
        print("ALL TESTS PASSED ✓")
    else:
        print("SOME TESTS FAILED ✗")
    print("="*60)
    print()

    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
