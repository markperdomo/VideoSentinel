#!/usr/bin/env python3
"""
Test carriage return behavior in different terminal modes
"""

import sys
import time
import os

def test_basic_carriage_return():
    """Test basic carriage return without any terminal manipulation"""
    print("Test 1: Basic carriage return (no terminal manipulation)")
    for i in range(10):
        print(f"\rProgress: {i*10}%", end='', flush=True)
        time.sleep(0.2)
    print()  # Final newline
    print()

def test_with_terminal_reset():
    """Test after resetting terminal to canonical mode (like video_sentinel.py does)"""
    print("Test 2: After terminal reset to canonical mode")

    # Apply the same terminal reset that video_sentinel.py does
    if sys.stdin.isatty():
        try:
            import termios
            fd = sys.stdin.fileno()
            try:
                attrs = termios.tcgetattr(fd)
                # Enable canonical mode (ICANON) and echo (ECHO)
                attrs[3] |= termios.ICANON | termios.ECHO  # lflag
                termios.tcsetattr(fd, termios.TCSANOW, attrs)
                print("  Terminal set to canonical mode")
            except:
                print("  Could not set terminal mode")
        except ImportError:
            print("  termios not available")

    print()
    for i in range(10):
        print(f"\rProgress: {i*10}%", end='', flush=True)
        time.sleep(0.2)
    print()  # Final newline
    print()

def test_environment():
    """Print environment info"""
    print("Environment Information:")
    print(f"  TERM: {os.environ.get('TERM', 'not set')}")
    print(f"  TMUX: {os.environ.get('TMUX', 'not set')}")
    print(f"  STY (screen): {os.environ.get('STY', 'not set')}")
    print(f"  stdin.isatty(): {sys.stdin.isatty()}")
    print(f"  stdout.isatty(): {sys.stdout.isatty()}")
    print()

if __name__ == "__main__":
    test_environment()
    test_basic_carriage_return()
    test_with_terminal_reset()
    print("Tests complete!")
