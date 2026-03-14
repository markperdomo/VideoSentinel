"""Tests for encoder.py — CRF calculation, parsing helpers, output paths, formatting."""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from encoder import VideoEncoder
from helpers import make_video_info


# ===== calculate_optimal_crf =====

class TestCalculateOptimalCrf:

    @pytest.fixture
    def encoder(self):
        return VideoEncoder()

    # --- HEVC tiers ---

    def test_hevc_very_high_bpp(self, encoder):
        """bpp > 0.25 → CRF 18 for HEVC."""
        # 4K bluray-style: high bitrate, moderate resolution
        info = make_video_info(bitrate=50_000_000, width=1920, height=1080, fps=24.0)
        crf = encoder.calculate_optimal_crf(info, "hevc")
        assert crf == 18

    def test_hevc_high_bpp(self, encoder):
        """0.15 < bpp <= 0.25 → CRF 20."""
        # bpp = 8_000_000 / (1920*1080*24) ≈ 0.16
        info = make_video_info(bitrate=8_000_000, width=1920, height=1080, fps=24.0)
        crf = encoder.calculate_optimal_crf(info, "hevc")
        assert crf == 20

    def test_hevc_medium_high_bpp(self, encoder):
        """0.10 < bpp <= 0.15 → CRF 22."""
        # bpp = 5_500_000 / (1920*1080*24) ≈ 0.11
        info = make_video_info(bitrate=5_500_000, width=1920, height=1080, fps=24.0)
        crf = encoder.calculate_optimal_crf(info, "hevc")
        assert crf == 22

    def test_hevc_medium_bpp(self, encoder):
        """0.07 < bpp <= 0.10 → CRF 23."""
        # bpp = 4_000_000 / (1920*1080*24) ≈ 0.08
        info = make_video_info(bitrate=4_000_000, width=1920, height=1080, fps=24.0)
        crf = encoder.calculate_optimal_crf(info, "hevc")
        assert crf == 23

    def test_hevc_medium_low_bpp(self, encoder):
        """0.05 < bpp <= 0.07 → CRF 25."""
        # bpp = 3_000_000 / (1920*1080*24) ≈ 0.06
        info = make_video_info(bitrate=3_000_000, width=1920, height=1080, fps=24.0)
        crf = encoder.calculate_optimal_crf(info, "hevc")
        assert crf == 25

    def test_hevc_low_bpp(self, encoder):
        """bpp <= 0.05 → CRF 28."""
        # bpp = 1_000_000 / (1920*1080*24) ≈ 0.02
        info = make_video_info(bitrate=1_000_000, width=1920, height=1080, fps=24.0)
        crf = encoder.calculate_optimal_crf(info, "hevc")
        assert crf == 28

    # --- AV1 tiers ---

    def test_av1_very_high_bpp(self, encoder):
        info = make_video_info(bitrate=50_000_000, width=1920, height=1080, fps=24.0)
        assert encoder.calculate_optimal_crf(info, "av1") == 20

    def test_av1_low_bpp(self, encoder):
        info = make_video_info(bitrate=1_000_000, width=1920, height=1080, fps=24.0)
        assert encoder.calculate_optimal_crf(info, "av1") == 32

    # --- H.264 tiers ---

    def test_h264_very_high_bpp(self, encoder):
        info = make_video_info(bitrate=50_000_000, width=1920, height=1080, fps=24.0)
        assert encoder.calculate_optimal_crf(info, "h264") == 16

    def test_h264_low_bpp(self, encoder):
        info = make_video_info(bitrate=1_000_000, width=1920, height=1080, fps=24.0)
        assert encoder.calculate_optimal_crf(info, "h264") == 26

    # --- Edge cases ---

    def test_invalid_video_returns_default(self, encoder):
        info = make_video_info(is_valid=False)
        assert encoder.calculate_optimal_crf(info, "hevc") == 23

    def test_none_video_returns_default(self, encoder):
        assert encoder.calculate_optimal_crf(None, "hevc") == 23

    def test_zero_pixels_returns_default(self, encoder):
        info = make_video_info(width=0, height=0, resolution=(0, 0))
        assert encoder.calculate_optimal_crf(info, "hevc") == 23

    def test_zero_bitrate_estimates_from_file_size(self, encoder):
        """When bitrate=0, should estimate from file_size/duration."""
        # file_size=75MB, duration=120s → bitrate ≈ 5Mbps
        # bpp = 5_000_000 / (1920*1080*24) ≈ 0.10 → CRF 22
        info = make_video_info(bitrate=0, file_size=75_000_000, duration=120.0)
        crf = encoder.calculate_optimal_crf(info, "hevc")
        assert crf == 22

    def test_zero_bitrate_zero_file_size_returns_default(self, encoder):
        info = make_video_info(bitrate=0, file_size=0)
        assert encoder.calculate_optimal_crf(info, "hevc") == 23

    def test_zero_fps_uses_30_fallback(self, encoder):
        """fps=0 should fall back to 30, not divide by zero."""
        info = make_video_info(bitrate=50_000_000, fps=0.0)
        crf = encoder.calculate_optimal_crf(info, "hevc")
        assert isinstance(crf, int)
        assert 18 <= crf <= 28


# ===== _parse_time_to_seconds =====

class TestParseTimeToSeconds:

    @pytest.fixture
    def encoder(self):
        return VideoEncoder()

    def test_normal_time(self, encoder):
        assert encoder._parse_time_to_seconds("01:30:45.50") == pytest.approx(5445.5)

    def test_zero_time(self, encoder):
        assert encoder._parse_time_to_seconds("00:00:00.00") == 0.0

    def test_hours_only(self, encoder):
        assert encoder._parse_time_to_seconds("02:00:00.00") == 7200.0

    def test_fractional_seconds(self, encoder):
        assert encoder._parse_time_to_seconds("00:00:05.12") == pytest.approx(5.12)

    def test_invalid_format_returns_zero(self, encoder):
        assert encoder._parse_time_to_seconds("invalid") == 0.0

    def test_empty_string_returns_zero(self, encoder):
        assert encoder._parse_time_to_seconds("") == 0.0


# ===== _parse_ffmpeg_progress =====

class TestParseFFmpegProgress:

    @pytest.fixture
    def encoder(self):
        return VideoEncoder()

    def test_typical_progress_line(self, encoder):
        line = "frame=  123 fps= 45.2 q=28.0 size=    1024kB time=00:00:05.12 bitrate=1234.5kbits/s speed=1.23x"
        result = encoder._parse_ffmpeg_progress(line)
        assert result is not None
        assert result["frame"] == "123"
        assert result["fps"] == "45.2"
        assert result["speed"] == "1.23"
        assert result["time"] == "00:00:05.12"
        assert result["bitrate"] == "1234.5kbits/s"

    def test_non_progress_line_returns_none(self, encoder):
        assert encoder._parse_ffmpeg_progress("Some error message") is None

    def test_frame_only(self, encoder):
        result = encoder._parse_ffmpeg_progress("frame=500")
        assert result is not None
        assert result["frame"] == "500"

    def test_high_speed(self, encoder):
        line = "frame= 5000 fps=200.0 q=25.0 size=  50000kB time=01:30:00.00 bitrate=5000.0kbits/s speed=10.5x"
        result = encoder._parse_ffmpeg_progress(line)
        assert result["speed"] == "10.5"


# ===== get_output_path =====

class TestGetOutputPath:

    @pytest.fixture
    def encoder(self):
        return VideoEncoder()

    def test_default_same_directory(self, encoder):
        inp = Path("/videos/movie.avi")
        out = encoder.get_output_path(inp)
        assert out == Path("/videos/movie_reencoded.mp4")

    def test_custom_output_dir(self, encoder, tmp_path):
        inp = Path("/videos/movie.avi")
        out = encoder.get_output_path(inp, output_dir=tmp_path)
        assert out == tmp_path / "movie_reencoded.mp4"

    def test_custom_suffix(self, encoder):
        inp = Path("/videos/movie.avi")
        out = encoder.get_output_path(inp, suffix="_quicklook")
        assert out == Path("/videos/movie_quicklook.mp4")

    def test_h264_codec_still_mp4(self, encoder):
        inp = Path("/videos/movie.mkv")
        out = encoder.get_output_path(inp, target_codec="h264")
        assert out.suffix == ".mp4"

    def test_av1_codec_still_mp4(self, encoder):
        inp = Path("/videos/movie.webm")
        out = encoder.get_output_path(inp, target_codec="av1")
        assert out.suffix == ".mp4"

    def test_preserves_stem(self, encoder):
        inp = Path("/videos/My Movie (2024).wmv")
        out = encoder.get_output_path(inp)
        assert out.stem == "My Movie (2024)_reencoded"


# ===== _format_size =====

class TestFormatSize:

    def test_zero(self):
        assert VideoEncoder._format_size(0) == "--"

    def test_negative(self):
        assert VideoEncoder._format_size(-100) == "--"

    def test_kilobytes(self):
        assert VideoEncoder._format_size(500 * 1024) == "500 KB"

    def test_megabytes(self):
        result = VideoEncoder._format_size(150 * 1024 * 1024)
        assert "150" in result
        assert "MB" in result

    def test_gigabytes(self):
        result = VideoEncoder._format_size(2 * 1024**3)
        assert "2" in result
        assert "GB" in result


# ===== _format_duration =====

class TestFormatDuration:

    def test_seconds_only(self):
        assert VideoEncoder._format_duration(45) == "45s"

    def test_minutes_and_seconds(self):
        assert VideoEncoder._format_duration(125) == "2m 5s"

    def test_hours_and_minutes(self):
        assert VideoEncoder._format_duration(3700) == "1h 1m"

    def test_zero(self):
        assert VideoEncoder._format_duration(0) == "0s"


# ===== CODEC_MAP and EXTENSION_MAP consistency =====

class TestCodecMaps:

    def test_all_codecs_have_extensions(self):
        encoder = VideoEncoder()
        for codec in encoder.CODEC_MAP:
            assert codec in encoder.EXTENSION_MAP, f"Missing extension for codec {codec}"

    def test_all_extensions_are_mp4(self):
        """Current design: all codecs output to .mp4."""
        encoder = VideoEncoder()
        for codec, ext in encoder.EXTENSION_MAP.items():
            assert ext == ".mp4", f"Codec {codec} has unexpected extension {ext}"
