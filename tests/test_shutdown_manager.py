"""Tests for shutdown_manager.py and ui.py helpers."""

import threading

import pytest

from shutdown_manager import ShutdownManager, get_shutdown_manager, shutdown_requested
from ui import fit_filename


# ===== ShutdownManager =====

class TestShutdownManager:

    def test_initial_state_not_requested(self):
        mgr = ShutdownManager()
        assert mgr.shutdown_requested() is False

    def test_request_shutdown(self):
        mgr = ShutdownManager()
        mgr.request_shutdown()
        assert mgr.shutdown_requested() is True

    def test_request_shutdown_idempotent(self):
        mgr = ShutdownManager()
        mgr.request_shutdown()
        mgr.request_shutdown()
        assert mgr.shutdown_requested() is True

    def test_start_and_stop_no_crash(self):
        """start/stop should not raise even without a TTY."""
        mgr = ShutdownManager()
        mgr.start()
        mgr.stop()
        assert mgr.shutdown_requested() is False

    def test_stop_without_start(self):
        """stop without start should not raise."""
        mgr = ShutdownManager()
        mgr.stop()

    def test_thread_safety(self):
        """Multiple threads requesting shutdown should not race."""
        mgr = ShutdownManager()
        errors = []

        def request():
            try:
                for _ in range(100):
                    mgr.request_shutdown()
                    _ = mgr.shutdown_requested()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=request) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0
        assert mgr.shutdown_requested() is True

    def test_custom_shutdown_key(self):
        mgr = ShutdownManager(shutdown_key="x")
        assert mgr._shutdown_key == "x"


class TestGlobalShutdownManager:

    def test_singleton_returns_same_instance(self):
        mgr1 = get_shutdown_manager()
        mgr2 = get_shutdown_manager()
        assert mgr1 is mgr2


# ===== fit_filename =====

class TestFitFilename:

    def test_short_name_unchanged(self):
        assert fit_filename("short.mp4", width=50) == "short.mp4"

    def test_long_name_truncated(self):
        name = "a" * 100 + ".mp4"
        result = fit_filename(name, width=30)
        assert len(result) <= 30
        # Should end with part of the original (extension visible)
        assert ".mp4" in result or result.endswith("mp4")

    def test_contains_ellipsis(self):
        name = "very_long_filename_that_exceeds_width.mp4"
        result = fit_filename(name, width=25)
        assert "\u2026" in result  # ellipsis character

    def test_exact_width_unchanged(self):
        name = "exactly20chars.mp4.."  # 20 chars
        result = fit_filename(name, width=20)
        assert result == name

    def test_width_zero_uses_terminal(self):
        """Width=0 should calculate from terminal size, not crash."""
        result = fit_filename("test.mp4", width=0)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_minimum_width(self):
        """Even with extreme truncation, result should be usable."""
        name = "very_long_name.mp4"
        result = fit_filename(name, width=20)
        assert len(result) <= 20
