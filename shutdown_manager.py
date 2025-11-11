#!/usr/bin/env python3
"""
Graceful shutdown manager for VideoSentinel

Provides a mechanism to request graceful shutdown during long-running operations
by pressing 'q' key. Ensures current operation completes before exiting.
"""

import sys
import threading
import select
from typing import Optional


class ShutdownManager:
    """
    Manages graceful shutdown requests during video processing

    Usage:
        manager = ShutdownManager()
        manager.start()

        while processing_videos:
            if manager.shutdown_requested():
                print("Finishing current video then exiting...")
                break
            # ... process video ...

        manager.stop()
    """

    def __init__(self, shutdown_key: str = 'q'):
        """
        Initialize shutdown manager

        Args:
            shutdown_key: Key to press for shutdown (default: 'q')
        """
        self._shutdown_requested = False
        self._shutdown_key = shutdown_key.lower()
        self._listener_thread: Optional[threading.Thread] = None
        self._stop_listener = False
        self._lock = threading.Lock()

    def start(self):
        """Start listening for shutdown key in background thread"""
        if self._listener_thread is not None and self._listener_thread.is_alive():
            return  # Already running

        self._stop_listener = False
        self._shutdown_requested = False

        # Only start listener if stdin is a TTY (not redirected/piped)
        if sys.stdin.isatty():
            self._listener_thread = threading.Thread(
                target=self._listen_for_shutdown,
                daemon=True,
                name="ShutdownListener"
            )
            self._listener_thread.start()

    def stop(self):
        """Stop the listener thread"""
        self._stop_listener = True
        if self._listener_thread is not None:
            # Don't join - it's a daemon thread and might be blocking on input
            self._listener_thread = None

    def shutdown_requested(self) -> bool:
        """
        Check if shutdown has been requested

        Returns:
            True if shutdown was requested, False otherwise
        """
        with self._lock:
            return self._shutdown_requested

    def request_shutdown(self):
        """Manually request shutdown (for testing or external triggers)"""
        with self._lock:
            if not self._shutdown_requested:
                self._shutdown_requested = True

    def _listen_for_shutdown(self):
        """
        Background thread that listens for shutdown key press
        Uses select() on Unix-like systems for non-blocking input
        """
        # Import platform-specific modules
        is_unix = hasattr(select, 'select')

        if not is_unix:
            # On Windows, use a simpler blocking approach
            self._listen_for_shutdown_blocking()
            return

        # Unix/Linux/macOS - use select for better responsiveness
        try:
            import termios
            import tty

            # Save original terminal settings
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)

            try:
                # Set terminal to raw mode for immediate key detection
                tty.setraw(fd)

                while not self._stop_listener:
                    # Check if there's input available (100ms timeout)
                    ready, _, _ = select.select([sys.stdin], [], [], 0.1)

                    if ready:
                        char = sys.stdin.read(1).lower()

                        if char == self._shutdown_key:
                            with self._lock:
                                if not self._shutdown_requested:
                                    self._shutdown_requested = True
                                    # Print message on new line
                                    sys.stdout.write('\n')
                                    sys.stdout.flush()
                            break

            finally:
                # Restore original terminal settings
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

        except Exception as e:
            # Fall back to blocking input if raw mode fails
            # (e.g., in some terminals or when stdin is redirected)
            pass

    def _listen_for_shutdown_blocking(self):
        """
        Fallback blocking listener for Windows or when raw mode unavailable
        Note: This will block until Enter is pressed after the key
        """
        while not self._stop_listener:
            try:
                # This will block until user presses Enter
                line = input()

                if line.lower().strip() == self._shutdown_key:
                    with self._lock:
                        if not self._shutdown_requested:
                            self._shutdown_requested = True
                    break

            except (EOFError, KeyboardInterrupt):
                # stdin closed or Ctrl+C pressed
                break


# Global singleton instance for convenience
_global_manager: Optional[ShutdownManager] = None


def get_shutdown_manager() -> ShutdownManager:
    """
    Get or create the global shutdown manager singleton

    Returns:
        Global ShutdownManager instance
    """
    global _global_manager
    if _global_manager is None:
        _global_manager = ShutdownManager()
    return _global_manager


def start_shutdown_listener():
    """Convenience function to start the global shutdown manager"""
    manager = get_shutdown_manager()
    manager.start()


def stop_shutdown_listener():
    """Convenience function to stop the global shutdown manager"""
    manager = get_shutdown_manager()
    manager.stop()


def shutdown_requested() -> bool:
    """
    Convenience function to check if shutdown was requested

    Returns:
        True if shutdown was requested, False otherwise
    """
    manager = get_shutdown_manager()
    return manager.shutdown_requested()
