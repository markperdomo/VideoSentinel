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
        self._original_terminal_settings = None
        self._terminal_fd = None

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
        """Stop the listener thread and restore terminal settings"""
        self._stop_listener = True

        # Wait for thread to finish (with timeout) so terminal gets restored
        if self._listener_thread is not None and self._listener_thread.is_alive():
            self._listener_thread.join(timeout=0.5)

        # Explicitly restore terminal settings if they were saved
        if self._original_terminal_settings is not None and self._terminal_fd is not None:
            try:
                import termios
                termios.tcsetattr(self._terminal_fd, termios.TCSADRAIN, self._original_terminal_settings)
            except:
                pass
            finally:
                self._original_terminal_settings = None
                self._terminal_fd = None

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

        # Check if running in tmux or screen (causes issues with raw mode)
        import os
        in_tmux = os.environ.get('TMUX') is not None
        in_screen = os.environ.get('STY') is not None
        # Also check TERM variable which often contains "tmux" or "screen"
        term = os.environ.get('TERM', '').lower()
        in_multiplexer = 'tmux' in term or 'screen' in term

        if in_tmux or in_screen or in_multiplexer:
            # In tmux/screen, don't use terminal manipulation at all
            # Just silently disable the listener to avoid breaking the terminal
            return

        # Unix/Linux/macOS - use select for better responsiveness
        try:
            import termios
            import tty

            # Save original terminal settings
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)

            # Store for explicit restoration in stop()
            self._terminal_fd = fd
            self._original_terminal_settings = old_settings

            try:
                # Use cbreak mode instead of raw mode
                # Cbreak allows Ctrl+C to work but gives immediate key detection
                tty.setcbreak(fd)

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
                # Clear saved settings after restoration
                self._original_terminal_settings = None
                self._terminal_fd = None

        except Exception as e:
            # Fall back to blocking input if cbreak mode fails
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
