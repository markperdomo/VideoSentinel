"""Tests for video_analyzer.py — VideoInfo, VideoCache, and VideoAnalyzer."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from video_analyzer import VideoInfo, VideoCache, VideoAnalyzer
from helpers import make_video_info


# ===== VideoInfo serialization =====

class TestVideoInfo:

    def test_to_dict_and_back(self, video_info):
        """Round-trip: VideoInfo -> dict -> VideoInfo preserves all fields."""
        d = video_info.to_dict()
        restored = VideoInfo.from_dict(d)
        assert restored.codec == video_info.codec
        assert restored.width == video_info.width
        assert restored.height == video_info.height
        assert restored.resolution == video_info.resolution
        assert restored.duration == video_info.duration
        assert restored.fps == video_info.fps
        assert restored.has_audio == video_info.has_audio
        assert restored.file_size == video_info.file_size

    def test_from_dict_resolution_converts_list_to_tuple(self):
        """JSON deserializes lists; from_dict must convert to tuple."""
        d = make_video_info().to_dict()
        d["resolution"] = [1920, 1080]  # simulate JSON load
        info = VideoInfo.from_dict(d)
        assert isinstance(info.resolution, tuple)
        assert info.resolution == (1920, 1080)

    def test_from_dict_does_not_mutate_input(self):
        """from_dict should not modify the original dict."""
        d = make_video_info().to_dict()
        original_path = d["file_path"]
        VideoInfo.from_dict(d)
        assert d["file_path"] == original_path  # still a string, not Path

    def test_invalid_video_info(self):
        info = make_video_info(is_valid=False, error_message="ffprobe failed")
        assert not info.is_valid
        assert info.error_message == "ffprobe failed"


# ===== VideoCache =====

class TestVideoCache:

    def test_empty_cache_returns_none(self, cache_file):
        cache = VideoCache(cache_file)
        assert cache.get(Path("/nonexistent/file.mp4")) is None
        assert cache.misses == 1

    def test_set_and_get(self, cache_file, tmp_path):
        """Store a VideoInfo and retrieve it; file size must match."""
        video_file = tmp_path / "video.mp4"
        video_file.write_bytes(b"\x00" * 5000)

        info = make_video_info(file_path=video_file)
        cache = VideoCache(cache_file)
        cache.set(video_file, info)

        result = cache.get(video_file)
        assert result is not None
        assert result.codec == "hevc"
        assert cache.hits == 1

    def test_cache_invalidated_by_size_change(self, cache_file, tmp_path):
        """If file size changes, cache entry is stale."""
        video_file = tmp_path / "video.mp4"
        video_file.write_bytes(b"\x00" * 5000)

        info = make_video_info(file_path=video_file)
        cache = VideoCache(cache_file)
        cache.set(video_file, info)

        # Change file size
        video_file.write_bytes(b"\x00" * 9999)
        assert cache.get(video_file) is None
        assert cache.misses == 1

    def test_save_and_reload(self, cache_file, tmp_path):
        """Cache persists to disk and can be reloaded."""
        video_file = tmp_path / "video.mp4"
        video_file.write_bytes(b"\x00" * 5000)

        info = make_video_info(file_path=video_file)
        cache = VideoCache(cache_file)
        cache.set(video_file, info)
        cache.save()

        # New cache instance loads from disk
        cache2 = VideoCache(cache_file)
        result = cache2.get(video_file)
        assert result is not None
        assert result.width == 1920

    def test_auto_save_at_100_updates(self, cache_file, tmp_path):
        """Cache auto-saves every 100 entries."""
        cache = VideoCache(cache_file)
        for i in range(101):
            f = tmp_path / f"v{i}.mp4"
            f.write_bytes(b"\x00" * (1000 + i))
            cache.set(f, make_video_info(file_path=f))

        # Should have auto-saved; updates_count reset
        assert cache.updates_count < 100

    def test_corrupt_cache_file_handled(self, cache_file):
        """Corrupt JSON on disk doesn't crash — cache starts empty."""
        cache_file.write_text("NOT VALID JSON {{{")
        cache = VideoCache(cache_file)
        assert cache.cache == {}


# ===== VideoAnalyzer.is_video_file =====

class TestIsVideoFile:

    @pytest.fixture
    def analyzer(self):
        return VideoAnalyzer(use_cache=False)

    @pytest.mark.parametrize("ext", [".mp4", ".mkv", ".avi", ".wmv", ".webm", ".mov", ".flv", ".3gp"])
    def test_valid_extensions(self, analyzer, ext):
        assert analyzer.is_video_file(Path(f"test{ext}"))

    @pytest.mark.parametrize("ext", [".txt", ".jpg", ".png", ".py", ".json", ".md"])
    def test_invalid_extensions(self, analyzer, ext):
        assert not analyzer.is_video_file(Path(f"test{ext}"))

    def test_case_insensitive(self, analyzer):
        assert analyzer.is_video_file(Path("test.MP4"))
        assert analyzer.is_video_file(Path("test.Mkv"))


# ===== VideoAnalyzer.meets_modern_specs =====

class TestMeetsModernSpecs:

    @pytest.fixture
    def analyzer(self):
        return VideoAnalyzer(use_cache=False)

    def test_hevc_mp4_is_modern(self, analyzer):
        info = make_video_info(codec="hevc", container="mp4")
        assert analyzer.meets_modern_specs(info) is True

    def test_av1_mkv_is_modern(self, analyzer):
        info = make_video_info(codec="av1", container="mkv")
        assert analyzer.meets_modern_specs(info) is True

    def test_vp9_webm_is_modern(self, analyzer):
        info = make_video_info(codec="vp9", container="webm")
        assert analyzer.meets_modern_specs(info) is True

    def test_hvc1_tag_is_modern(self, analyzer):
        info = make_video_info(codec="hvc1", container="mp4")
        assert analyzer.meets_modern_specs(info) is True

    def test_h264_is_not_modern(self, analyzer):
        info = make_video_info(codec="h264", container="mp4")
        assert analyzer.meets_modern_specs(info) is False

    def test_mpeg4_avi_is_not_modern(self, analyzer):
        info = make_video_info(codec="mpeg4", container="avi")
        assert analyzer.meets_modern_specs(info) is False

    def test_invalid_video_not_modern(self, analyzer):
        info = make_video_info(is_valid=False)
        assert analyzer.meets_modern_specs(info) is False

    def test_zero_dimensions_not_modern(self, analyzer):
        info = make_video_info(codec="hevc", width=0, height=0, resolution=(0, 0))
        assert analyzer.meets_modern_specs(info) is False

    def test_bad_container_not_modern(self, analyzer):
        info = make_video_info(codec="hevc", container="avi")
        assert analyzer.meets_modern_specs(info) is False

    def test_max_resolution_pass(self):
        analyzer = VideoAnalyzer(use_cache=False, max_resolution=(1920, 1080))
        info = make_video_info(codec="hevc", width=1920, height=1080)
        assert analyzer.meets_modern_specs(info) is True

    def test_max_resolution_exceed(self):
        analyzer = VideoAnalyzer(use_cache=False, max_resolution=(1920, 1080))
        info = make_video_info(codec="hevc", width=3840, height=2160, resolution=(3840, 2160))
        assert analyzer.meets_modern_specs(info) is False

    def test_mov_container_accepted(self, analyzer):
        """mov is essentially mp4 — should be accepted."""
        info = make_video_info(codec="hevc", container="mov")
        assert analyzer.meets_modern_specs(info) is True


# ===== VideoAnalyzer.find_videos =====

class TestFindVideos:

    @pytest.fixture
    def analyzer(self):
        return VideoAnalyzer(use_cache=False)

    def test_finds_video_files(self, analyzer, video_dir):
        videos = analyzer.find_videos(video_dir)
        names = {v.name for v in videos}
        assert "movie.mp4" in names
        assert "clip.avi" in names
        assert "show.mkv" in names
        assert "trailer.wmv" in names
        # Non-video files excluded
        assert "notes.txt" not in names
        assert "image.jpg" not in names

    def test_non_recursive_only_top_level(self, analyzer, nested_video_dir):
        videos = analyzer.find_videos(nested_video_dir, recursive=False)
        assert len(videos) == 1
        assert videos[0].name == "a.mp4"

    def test_recursive_finds_all(self, analyzer, nested_video_dir):
        videos = analyzer.find_videos(nested_video_dir, recursive=True)
        names = {v.name for v in videos}
        assert names == {"a.mp4", "b.mkv", "d.avi"}

    def test_file_types_filter(self, analyzer, video_dir):
        videos = analyzer.find_videos(video_dir, file_types=["mp4", "mkv"])
        names = {v.name for v in videos}
        assert "movie.mp4" in names
        assert "show.mkv" in names
        assert "clip.avi" not in names
        assert "trailer.wmv" not in names

    def test_file_types_invalid_returns_empty(self, analyzer, video_dir):
        videos = analyzer.find_videos(video_dir, file_types=["xyz", "abc"])
        assert videos == []

    def test_sorted_output(self, analyzer, video_dir):
        videos = analyzer.find_videos(video_dir)
        assert videos == sorted(videos)

    def test_skips_macos_resource_forks(self, analyzer, tmp_path):
        """Files starting with ._ should be skipped."""
        (tmp_path / "good.mp4").write_bytes(b"\x00" * 100)
        (tmp_path / "._good.mp4").write_bytes(b"\x00" * 100)
        videos = analyzer.find_videos(tmp_path)
        assert len(videos) == 1
        assert videos[0].name == "good.mp4"

    def test_empty_directory(self, analyzer, tmp_path):
        assert analyzer.find_videos(tmp_path) == []


# ===== VideoAnalyzer.get_video_info with real ffmpeg =====

class TestGetVideoInfoIntegration:

    def test_real_video_info(self, real_video):
        """Integration: probe a real video file."""
        analyzer = VideoAnalyzer(use_cache=False)
        info = analyzer.get_video_info(real_video)
        assert info is not None
        assert info.is_valid
        assert info.codec in ("h264", "avc1", "avc")
        assert info.width == 320
        assert info.height == 240
        assert info.has_audio
        assert 1.5 <= info.duration <= 2.5
        assert info.fps > 0

    def test_nonexistent_file_returns_none(self):
        analyzer = VideoAnalyzer(use_cache=False)
        assert analyzer.get_video_info(Path("/nonexistent/file.mp4")) is None


# ===== QuickLook compatibility =====

def _mock_ffprobe_result(codec_name, codec_tag, pix_fmt, format_name):
    """Build a mock subprocess.CompletedProcess mimicking ffprobe JSON output."""
    data = {
        "format": {"format_name": format_name, "tags": {}},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": codec_name,
                "codec_tag_string": codec_tag,
                "pix_fmt": pix_fmt,
            }
        ],
    }
    return MagicMock(returncode=0, stdout=json.dumps(data))


class TestCheckQuickLookCompatibility:
    """Tests for VideoAnalyzer.check_quicklook_compatibility."""

    def _check(self, codec_name, codec_tag="", pix_fmt="yuv420p", format_name="mp4"):
        analyzer = VideoAnalyzer(use_cache=False)
        mock_result = _mock_ffprobe_result(codec_name, codec_tag, pix_fmt, format_name)
        with patch("video_analyzer.subprocess.run", return_value=mock_result):
            return analyzer.check_quicklook_compatibility(Path("/fake/video.mp4"))

    # --- AV1 support ---

    def test_av1_in_mp4_is_compatible(self):
        compat = self._check("av1", format_name="mp4")
        assert compat["compatible"] is True
        assert not compat["needs_remux"]
        assert not compat["needs_reencode"]

    def test_av1_in_mkv_needs_remux_only(self):
        compat = self._check("av1", format_name="matroska,webm")
        assert compat["compatible"] is False
        assert compat["needs_remux"] is True
        assert compat["needs_reencode"] is False
        assert any("Container" in issue for issue in compat["issues"])

    def test_av1_10bit_in_mp4_is_compatible(self):
        compat = self._check("av1", pix_fmt="yuv420p10le", format_name="mp4")
        assert compat["compatible"] is True
        assert not compat["needs_reencode"]

    def test_av1_10bit_in_mkv_needs_remux_only(self):
        compat = self._check("av1", pix_fmt="yuv420p10le", format_name="matroska,webm")
        assert compat["compatible"] is False
        assert compat["needs_remux"] is True
        assert compat["needs_reencode"] is False

    def test_av1_unsupported_pix_fmt_needs_reencode(self):
        compat = self._check("av1", pix_fmt="yuv444p", format_name="mp4")
        assert compat["needs_reencode"] is True

    # --- HEVC support ---

    def test_hevc_hvc1_in_mp4_is_compatible(self):
        compat = self._check("hevc", codec_tag="hvc1", format_name="mp4")
        assert compat["compatible"] is True

    def test_hevc_hev1_in_mp4_needs_remux(self):
        compat = self._check("hevc", codec_tag="hev1", format_name="mp4")
        assert compat["compatible"] is False
        assert compat["needs_remux"] is True
        assert not compat["needs_reencode"]

    def test_hevc_in_mkv_needs_remux(self):
        compat = self._check("hevc", codec_tag="hvc1", format_name="matroska,webm")
        assert compat["compatible"] is False
        assert compat["needs_remux"] is True

    def test_hevc_10bit_is_compatible(self):
        compat = self._check("hevc", codec_tag="hvc1", pix_fmt="yuv420p10le", format_name="mp4")
        assert compat["compatible"] is True

    # --- H.264 support ---

    def test_h264_in_mp4_is_compatible(self):
        compat = self._check("h264", format_name="mp4")
        assert compat["compatible"] is True

    def test_h264_in_mkv_needs_remux(self):
        compat = self._check("h264", format_name="matroska,webm")
        assert compat["needs_remux"] is True

    # --- Unsupported codecs ---

    def test_vp9_needs_reencode(self):
        compat = self._check("vp9", format_name="mp4")
        assert compat["needs_reencode"] is True

    def test_mpeg2video_needs_reencode(self):
        compat = self._check("mpeg2video", format_name="mp4")
        assert compat["needs_reencode"] is True

    # --- Edge cases ---

    def test_mov_container_is_compatible(self):
        compat = self._check("h264", format_name="mov,mp4,m4a,3gp,3g2,mj2")
        assert compat["compatible"] is True
        assert not compat["needs_remux"]

    def test_ffprobe_failure_returns_not_compatible(self):
        analyzer = VideoAnalyzer(use_cache=False)
        mock_result = MagicMock(returncode=1, stdout="", stderr="error")
        with patch("video_analyzer.subprocess.run", return_value=mock_result):
            compat = analyzer.check_quicklook_compatibility(Path("/fake/video.mp4"))
        assert compat["compatible"] is False
        assert not compat["needs_remux"]
        assert not compat["needs_reencode"]
