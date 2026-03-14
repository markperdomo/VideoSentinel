"""Tests for issue_detector.py — scan_video and individual check methods."""

from pathlib import Path

import pytest

from issue_detector import IssueDetector, VideoIssue


class TestIssueDetectorIntegration:
    """Integration tests that require ffmpeg/ffprobe."""

    @pytest.fixture
    def detector(self):
        return IssueDetector()

    def test_healthy_video_no_issues(self, detector, real_video):
        """A valid test video should have no critical issues."""
        issues = detector.scan_video(real_video, deep_scan=False)
        critical = [i for i in issues if i.severity == "critical"]
        assert len(critical) == 0

    def test_deep_scan_healthy_video(self, detector, real_video):
        """Deep scan of a valid video should also be clean."""
        issues = detector.scan_video(real_video, deep_scan=True)
        critical = [i for i in issues if i.severity == "critical"]
        assert len(critical) == 0

    def test_check_incomplete_valid_video(self, detector, real_video):
        """A 2-second video should not be flagged as incomplete."""
        issue = detector.check_incomplete_video(real_video, min_duration=1.0)
        assert issue is None

    def test_check_missing_audio_present(self, detector, real_video):
        """Test video has audio — should not flag missing audio."""
        issue = detector.check_missing_audio(real_video, expect_audio=True)
        assert issue is None

    def test_check_unusual_specs_normal(self, detector, real_video):
        """Normal 320x240 video should not flag unusual specs (low res is info, not critical)."""
        issues = detector.check_unusual_specs(real_video)
        critical = [i for i in issues if i.severity == "critical"]
        assert len(critical) == 0


class TestIssueDetectorUnit:
    """Unit tests using fake/nonexistent files."""

    @pytest.fixture
    def detector(self):
        return IssueDetector()

    def test_check_missing_audio_expect_false(self, detector):
        """When audio is not expected, always returns None."""
        issue = detector.check_missing_audio(Path("/fake.mp4"), expect_audio=False)
        assert issue is None

    def test_check_incomplete_nonexistent_file(self, detector):
        """Non-existent file should return an issue (ffprobe will fail)."""
        issue = detector.check_incomplete_video(Path("/nonexistent/video.mp4"))
        assert issue is not None
        assert issue.severity in ("critical", "warning")

    def test_check_integrity_nonexistent_file(self, detector):
        """Non-existent file should produce an issue."""
        issues = detector.check_file_integrity(Path("/nonexistent/video.mp4"))
        # ffmpeg will error — should get at least one issue
        assert len(issues) > 0

    def test_scan_video_nonexistent_returns_issues(self, detector):
        """Scanning a non-existent file should return issues, not crash."""
        issues = detector.scan_video(Path("/nonexistent/video.mp4"))
        assert len(issues) > 0


class TestVideoIssue:

    def test_dataclass_fields(self):
        issue = VideoIssue(
            file_path=Path("/v/test.mp4"),
            issue_type="corruption",
            severity="critical",
            description="Frame decode error at 00:05:00",
        )
        assert issue.file_path == Path("/v/test.mp4")
        assert issue.issue_type == "corruption"
        assert issue.severity == "critical"
        assert "Frame decode error" in issue.description
