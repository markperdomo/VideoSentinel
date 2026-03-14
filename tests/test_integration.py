"""Integration tests — full encode/validate/analyze round-trips using real ffmpeg."""

import shutil
from pathlib import Path

import pytest

from video_analyzer import VideoAnalyzer
from encoder import VideoEncoder
from issue_detector import IssueDetector


pytestmark = pytest.mark.timeout(60)


class TestEncodeRoundTrip:
    """End-to-end: analyze → encode → validate → analyze output."""

    def test_hevc_encode(self, real_video, tmp_path):
        """Encode a real video to HEVC and validate the result."""
        analyzer = VideoAnalyzer(use_cache=False)
        encoder = VideoEncoder()

        # Analyze source
        source_info = analyzer.get_video_info(real_video)
        assert source_info is not None
        assert source_info.is_valid

        # Encode
        output = tmp_path / "output_hevc.mp4"
        success = encoder.re_encode_video(
            input_path=real_video,
            output_path=output,
            target_codec="hevc",
            preset="ultrafast",
            crf=28,
            video_info=source_info,
        )
        assert success
        assert output.exists()
        assert output.stat().st_size > 1024

        # Analyze output
        output_info = analyzer.get_video_info(output)
        assert output_info is not None
        assert output_info.is_valid
        assert output_info.codec in ("hevc", "hvc1", "hev1", "h265")
        assert output_info.width > 0
        assert output_info.height > 0
        # Duration should be close to source
        assert abs(output_info.duration - source_info.duration) < 2.0

    def test_h264_encode(self, real_video, tmp_path):
        """Encode to H.264."""
        analyzer = VideoAnalyzer(use_cache=False)
        encoder = VideoEncoder()
        source_info = analyzer.get_video_info(real_video)

        output = tmp_path / "output_h264.mp4"
        success = encoder.re_encode_video(
            input_path=real_video,
            output_path=output,
            target_codec="h264",
            preset="ultrafast",
            crf=28,
            video_info=source_info,
        )
        assert success
        output_info = analyzer.get_video_info(output)
        assert output_info.codec in ("h264", "avc1", "avc")

    def test_smart_crf_produces_valid_output(self, real_video, tmp_path):
        """Encode using auto CRF (no explicit crf) and verify result."""
        analyzer = VideoAnalyzer(use_cache=False)
        encoder = VideoEncoder()
        source_info = analyzer.get_video_info(real_video)

        output = tmp_path / "output_smart.mp4"
        success = encoder.re_encode_video(
            input_path=real_video,
            output_path=output,
            target_codec="hevc",
            preset="ultrafast",
            video_info=source_info,
        )
        assert success
        assert output.exists()

    def test_encode_nonexistent_input_fails(self, tmp_path):
        encoder = VideoEncoder()
        output = tmp_path / "output.mp4"
        success = encoder.re_encode_video(
            input_path=Path("/nonexistent/input.mp4"),
            output_path=output,
        )
        assert success is False

    def test_replace_original(self, real_video, tmp_path):
        """--replace-original: original deleted, output renamed."""
        # Copy to tmp so we can safely delete
        src = tmp_path / "source.avi"
        shutil.copy2(real_video, src)

        analyzer = VideoAnalyzer(use_cache=False)
        encoder = VideoEncoder()
        source_info = analyzer.get_video_info(src)

        output = tmp_path / "source_reencoded.mp4"
        success = encoder.re_encode_video(
            input_path=src,
            output_path=output,
            target_codec="hevc",
            preset="ultrafast",
            crf=28,
            video_info=source_info,
            replace_original=True,
        )
        assert success
        # Original .avi should be gone
        assert not src.exists()
        # Final file should be source.mp4 (renamed from _reencoded)
        final = tmp_path / "source.mp4"
        assert final.exists()

    def test_resume_skips_valid_output(self, real_video, tmp_path):
        """If a valid output already exists, encoding should be skipped."""
        analyzer = VideoAnalyzer(use_cache=False)
        encoder = VideoEncoder()
        source_info = analyzer.get_video_info(real_video)

        output = tmp_path / "output.mp4"
        # First encode
        encoder.re_encode_video(
            input_path=real_video,
            output_path=output,
            target_codec="hevc",
            preset="ultrafast",
            crf=28,
            video_info=source_info,
        )
        first_mtime = output.stat().st_mtime

        # Second encode — should skip
        success = encoder.re_encode_video(
            input_path=real_video,
            output_path=output,
            target_codec="hevc",
            preset="ultrafast",
            crf=28,
            video_info=source_info,
        )
        assert success
        # File should not have been re-written
        assert output.stat().st_mtime == first_mtime


class TestValidateOutput:
    """Test _validate_output with real files."""

    def test_valid_file_passes(self, real_video):
        encoder = VideoEncoder()
        assert encoder._validate_output(real_video) is True

    def test_empty_file_fails(self, tmp_path):
        empty = tmp_path / "empty.mp4"
        empty.write_bytes(b"")
        encoder = VideoEncoder()
        assert encoder._validate_output(empty) is False

    def test_tiny_file_fails(self, tmp_path):
        tiny = tmp_path / "tiny.mp4"
        tiny.write_bytes(b"\x00" * 100)
        encoder = VideoEncoder()
        assert encoder._validate_output(tiny) is False

    def test_nonexistent_file_fails(self):
        encoder = VideoEncoder()
        assert encoder._validate_output(Path("/nonexistent.mp4")) is False

    def test_duration_mismatch_fails(self, real_video):
        """If source says 1000s but output is 2s, validation should fail."""
        from helpers import make_video_info
        source = make_video_info(duration=1000.0)
        encoder = VideoEncoder()
        assert encoder._validate_output(real_video, source_info=source) is False

    def test_duration_mismatch_lenient_passes(self, real_video):
        """Lenient mode allows duration mismatches."""
        from helpers import make_video_info
        source = make_video_info(duration=1000.0)
        encoder = VideoEncoder()
        assert encoder._validate_output(real_video, source_info=source, lenient=True) is True


class TestIssueDetectorIntegration:
    """Full integration: scan a real video with deep scan."""

    def test_deep_scan_clean_video(self, real_video):
        detector = IssueDetector()
        issues = detector.scan_video(real_video, deep_scan=True)
        critical = [i for i in issues if i.severity == "critical"]
        assert len(critical) == 0


class TestAnalyzerCacheIntegration:
    """Test that caching works end-to-end with real probing."""

    def test_cache_hit_on_second_call(self, real_video, tmp_path):
        cache_path = tmp_path / "cache.json"
        # Patch cache location
        analyzer = VideoAnalyzer(use_cache=True)
        analyzer.cache.cache_file = cache_path

        # First call: cache miss
        info1 = analyzer.get_video_info(real_video)
        assert analyzer.cache.misses == 1

        # Second call: cache hit
        info2 = analyzer.get_video_info(real_video)
        assert analyzer.cache.hits == 1
        assert info1.codec == info2.codec
        assert info1.duration == info2.duration
