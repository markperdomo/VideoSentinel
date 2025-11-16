#!/usr/bin/env python3
"""
Test progress bar rendering with different methods
"""

import sys
import time

def test_old_method():
    """Test the old method (\\r with padding)"""
    print("Test 1: Old method (\\r with padding)")
    for i in range(11):
        progress_msg = f"  Progress: {i*10}%"
        print(f"\r{progress_msg:<100}", end='', flush=True)
        time.sleep(0.3)
    print()  # Final newline
    print()

def test_new_method():
    """Test the new method (\\r\\033[K)"""
    print("Test 2: New method (\\r\\033[K)")
    for i in range(11):
        progress_msg = f"  Progress: {i*10}%"
        print(f"\r\033[K{progress_msg}", end='', flush=True)
        time.sleep(0.3)
    print()  # Final newline
    print()

def test_with_varying_length():
    """Test with messages of varying length (to show clearing works)"""
    print("Test 3: Varying length messages (new method)")
    messages = [
        "Short",
        "A much longer progress message here",
        "Medium length msg",
        "X",
        "Back to a longer message again",
        "Done!"
    ]
    for msg in messages:
        print(f"\r\033[K  {msg}", end='', flush=True)
        time.sleep(0.5)
    print()  # Final newline
    print()

if __name__ == "__main__":
    print("=" * 80)
    print("Progress Bar Test (should work in tmux, screen, and regular terminals)")
    print("=" * 80)
    print()

    test_old_method()
    test_new_method()
    test_with_varying_length()

    print("=" * 80)
    print("If you saw smooth overwriting (not newlines), the fix works!")
    print("=" * 80)
