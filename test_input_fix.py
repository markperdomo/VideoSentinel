#!/usr/bin/env python3
"""
Test script to verify shutdown listener doesn't interfere with input()
"""

from shutdown_manager import ShutdownManager

def test_input_with_listener():
    """Test that input() works correctly when shutdown listener is stopped"""
    print("Testing shutdown listener behavior with input()...")
    print()

    # Start the listener
    print("1. Starting shutdown listener (terminal in raw mode)...")
    manager = ShutdownManager()
    manager.start()

    import time
    time.sleep(0.5)  # Give listener time to start

    print("   Listener started. Terminal is now in raw mode.")
    print()

    # Stop the listener
    print("2. Stopping shutdown listener (restoring normal mode)...")
    manager.stop()
    time.sleep(0.5)  # Give listener time to stop and restore terminal

    print("   Listener stopped. Terminal restored to normal mode.")
    print()

    # Try to get input
    print("3. Testing input()...")
    try:
        response = input("   Type 'yes' and press Enter: ").strip().lower()
        print()

        if response == 'yes':
            print("✓ SUCCESS: Input worked correctly!")
            print("   The fix is working - shutdown listener properly releases terminal.")
        else:
            print(f"✓ Input received: '{response}'")
            print("   Terminal is working, but you didn't type 'yes'")
    except Exception as e:
        print(f"✗ FAILED: {e}")
        print("   This suggests the terminal is still in raw mode")

    print()

if __name__ == '__main__':
    test_input_with_listener()
