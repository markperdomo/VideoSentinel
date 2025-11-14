#!/usr/bin/env python3
"""
Test shutdown manager tmux compatibility
"""
import os
import sys
from shutdown_manager import ShutdownManager

def test_tmux_detection():
    """Test that shutdown manager detects tmux properly"""

    # Check if we're in tmux
    in_tmux = os.environ.get('TMUX') is not None
    in_screen = os.environ.get('STY') is not None

    print(f"Running in tmux: {in_tmux}")
    print(f"Running in screen: {in_screen}")
    print(f"stdin is tty: {sys.stdin.isatty()}")
    print()

    # Create and start manager
    manager = ShutdownManager()
    print("Starting shutdown manager...")
    manager.start()

    if in_tmux or in_screen:
        print("✓ Shutdown listener should be disabled (tmux/screen detected)")
        print("✓ Terminal should behave normally")
        print("✓ You should be able to type and use Ctrl+C")
    else:
        print("✓ Shutdown listener is active")
        print("✓ Press 'q' to test graceful shutdown")
        print("✓ Press Ctrl+C to exit")

    print()
    print("Testing for 5 seconds...")

    import time
    for i in range(50):
        if manager.shutdown_requested():
            print("\n✓ Shutdown was requested!")
            break
        time.sleep(0.1)
        if i % 10 == 0:
            print(f"  {i//10 + 1} seconds elapsed...")

    manager.stop()
    print("\n✓ Test complete!")

if __name__ == '__main__':
    test_tmux_detection()
