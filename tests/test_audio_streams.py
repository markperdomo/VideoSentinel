"""Tests for stream preservation, audio codec policy, and encoding profiles.

Covers the guarantees that make --replace-original safe for multi-track files:
every audio track survives, and an encode that loses one fails validation.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from encoder import VideoEncoder
from helpers import make_video_info


def streams_of(path: Path):
    """Return [(codec_type, codec_name), ...] for a media file."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    data = json.loads(result.stdout)
    return [(s["codec_type"], s["codec_name"]) for s in data["streams"]]


@pytest.fixture
def multitrack_video(tmp_path):
    """A WEB-DL-shaped MKV: h264 video, 3 audio tracks, SRT subtitles."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pytest.skip("ffmpeg not available")

    subs = tmp_path / "subs.srt"
    subs.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello\n\n")
    out = tmp_path / "show.mkv"

    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", "testsrc=size=320x240:rate=24:duration=3",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-f", "lavfi", "-i", "sine=frequency=660:duration=3",
        "-f", "lavfi", "-i", "sine=frequency=880:duration=3",
        "-i", str(subs),
        "-map", "0:v", "-map", "1:a", "-map", "2:a", "-map", "3:a", "-map", "4:s",
        "-c:v", "libx264", "-preset", "ultrafast", "-b:v", "300k",
        "-c:a", "aac", "-c:s", "srt",
        "-metadata:s:a:0", "language=eng",
        "-metadata:s:a:1", "language=eng",
        "-metadata:s:a:2", "language=spa",
        str(out),
    ], capture_output=True, timeout=60, check=True)
    return out


# ===== _build_stream_args =====

class TestBuildStreamArgs:
    """Stream mapping decisions, driven by a stubbed probe for determinism."""

    @pytest.fixture
    def encoder(self):
        return VideoEncoder()

    @staticmethod
    def _fake_streams():
        return [
            {"index": 0, "codec_type": "video", "codec_name": "h264"},
            {"index": 1, "codec_type": "video", "codec_name": "mjpeg",
             "disposition": {"attached_pic": 1}},
            {"index": 2, "codec_type": "audio", "codec_name": "eac3"},
            {"index": 3, "codec_type": "audio", "codec_name": "truehd"},
            {"index": 4, "codec_type": "subtitle", "codec_name": "hdmv_pgs_subtitle"},
            {"index": 5, "codec_type": "subtitle", "codec_name": "subrip"},
        ]

    def test_maps_every_audio_stream(self, encoder):
        with patch.object(encoder, "_probe_streams", return_value=self._fake_streams()):
            args = encoder._build_stream_args(Path("x.mkv"), "copy", ".mp4")
        assert "-map" in args
        assert "0:2" in args and "0:3" in args

    def test_skips_attached_cover_art(self, encoder):
        with patch.object(encoder, "_probe_streams", return_value=self._fake_streams()):
            args = encoder._build_stream_args(Path("x.mkv"), "copy", ".mp4")
        assert "0:1" not in args

    def test_drops_bitmap_subs_for_mp4(self, encoder):
        with patch.object(encoder, "_probe_streams", return_value=self._fake_streams()):
            args = encoder._build_stream_args(Path("x.mkv"), "copy", ".mp4")
        assert "0:4" not in args      # PGS dropped
        assert "0:5" in args          # subrip kept
        assert "mov_text" in args

    def test_keeps_bitmap_subs_for_mkv(self, encoder):
        with patch.object(encoder, "_probe_streams", return_value=self._fake_streams()):
            args = encoder._build_stream_args(Path("x.mkv"), "copy", ".mkv")
        assert "0:4" in args
        assert args[args.index("-c:s") + 1] == "copy"

    def test_incompatible_audio_falls_back_for_mp4(self, encoder):
        """TrueHD can't go in MP4 — that stream alone gets transcoded."""
        with patch.object(encoder, "_probe_streams", return_value=self._fake_streams()):
            args = encoder._build_stream_args(Path("x.mkv"), "copy", ".mp4")
        # eac3 is output audio 0 (copied), truehd is output audio 1 (converted)
        assert "-c:a:1" in args
        assert args[args.index("-c:a:1") + 1] == VideoEncoder.COPY_FALLBACK_AUDIO
        assert "-c:a:0" not in args

    def test_no_fallback_needed_for_mkv(self, encoder):
        """MKV holds TrueHD fine, so nothing is transcoded."""
        with patch.object(encoder, "_probe_streams", return_value=self._fake_streams()):
            args = encoder._build_stream_args(Path("x.mkv"), "copy", ".mkv")
        assert "-c:a:1" not in args

    def test_global_audio_codec_precedes_overrides(self, encoder):
        """ffmpeg resolves per-stream opts by last match — order is load-bearing."""
        with patch.object(encoder, "_probe_streams", return_value=self._fake_streams()):
            args = encoder._build_stream_args(Path("x.mkv"), "copy", ".mp4")
        assert args.index("-c:a") < args.index("-c:a:1")

    def test_preserves_chapters_and_metadata(self, encoder):
        with patch.object(encoder, "_probe_streams", return_value=self._fake_streams()):
            args = encoder._build_stream_args(Path("x.mkv"), "copy", ".mp4")
        assert "-map_chapters" in args
        assert "-map_metadata" in args

    def test_probe_failure_falls_back_safely(self, encoder):
        """Unprobeable file still gets a valid audio codec, not a broken map."""
        with patch.object(encoder, "_probe_streams", return_value=None):
            args = encoder._build_stream_args(Path("x.mkv"), "copy", ".mp4")
        assert args == ["-c:a", "copy"]

    def test_explicit_codec_disables_fallback_logic(self, encoder):
        """When transcoding all audio anyway, no per-stream override is needed."""
        with patch.object(encoder, "_probe_streams", return_value=self._fake_streams()):
            args = encoder._build_stream_args(Path("x.mkv"), "aac", ".mp4")
        assert args[args.index("-c:a") + 1] == "aac"
        assert "-c:a:1" not in args


# ===== Real encodes =====

class TestMultiTrackEncoding:

    def test_re_encode_preserves_all_tracks(self, multitrack_video, tmp_path):
        encoder = VideoEncoder()
        out = tmp_path / "out.mp4"
        assert encoder.re_encode_video(multitrack_video, out, target_codec="hevc")

        found = streams_of(out)
        assert sum(1 for t, _ in found if t == "audio") == 3
        assert sum(1 for t, _ in found if t == "subtitle") == 1

    def test_re_encode_copies_audio_untouched(self, multitrack_video, tmp_path):
        encoder = VideoEncoder()
        out = tmp_path / "out.mp4"
        encoder.re_encode_video(multitrack_video, out, target_codec="hevc")

        # Video re-encoded, audio bit-exact
        assert [c for t, c in streams_of(out) if t == "video"] == ["hevc"]
        assert all(c == "aac" for t, c in streams_of(out) if t == "audio")

    def test_remux_preserves_all_tracks(self, multitrack_video, tmp_path):
        encoder = VideoEncoder()
        out = tmp_path / "remux.mp4"
        assert encoder.remux_to_mp4(multitrack_video, out)
        assert sum(1 for t, _ in streams_of(out) if t == "audio") == 3


# ===== Validation gate =====

class TestAudioValidation:

    def _strip_audio(self, src: Path, dest: Path):
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(src),
             "-map", "0:v", "-an", "-c:v", "copy", str(dest)],
            capture_output=True, timeout=60, check=True,
        )

    def test_rejects_output_with_no_audio(self, multitrack_video, tmp_path):
        encoder = VideoEncoder()
        bad = tmp_path / "silent.mp4"
        self._strip_audio(multitrack_video, bad)

        info = make_video_info(audio_stream_count=3, duration=3.0)
        assert encoder._validate_output(bad, source_info=info) is False

    def test_rejects_partial_audio_loss(self, multitrack_video, tmp_path):
        encoder = VideoEncoder()
        partial = tmp_path / "one_track.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(multitrack_video),
             "-map", "0:v", "-map", "0:a:0", "-c", "copy", str(partial)],
            capture_output=True, timeout=60, check=True,
        )
        info = make_video_info(audio_stream_count=3, duration=3.0)
        assert encoder._validate_output(partial, source_info=info) is False

    def test_accepts_output_with_all_audio(self, multitrack_video, tmp_path):
        encoder = VideoEncoder()
        out = tmp_path / "good.mp4"
        encoder.re_encode_video(multitrack_video, out, target_codec="hevc")

        info = make_video_info(audio_stream_count=3, duration=3.0)
        assert encoder._validate_output(out, source_info=info) is True

    def test_recovery_mode_tolerates_audio_loss(self, multitrack_video, tmp_path):
        """Salvaging a corrupt file may legitimately lose audio — warn, don't fail."""
        encoder = VideoEncoder()
        bad = tmp_path / "silent.mp4"
        self._strip_audio(multitrack_video, bad)

        info = make_video_info(audio_stream_count=3, duration=3.0)
        assert encoder._validate_output(bad, source_info=info, lenient=True) is True

    def test_silent_source_is_not_penalized(self, multitrack_video, tmp_path):
        """A source with no audio should validate against an output with none."""
        encoder = VideoEncoder()
        bad = tmp_path / "silent.mp4"
        self._strip_audio(multitrack_video, bad)

        info = make_video_info(has_audio=False, audio_stream_count=0, duration=3.0)
        assert encoder._validate_output(bad, source_info=info) is True

    def test_falls_back_to_has_audio_for_stale_cache(self, multitrack_video, tmp_path):
        """Cache entries predating audio_stream_count still catch total audio loss."""
        encoder = VideoEncoder()
        bad = tmp_path / "silent.mp4"
        self._strip_audio(multitrack_video, bad)

        info = make_video_info(has_audio=True, audio_stream_count=0, duration=3.0)
        assert encoder._validate_output(bad, source_info=info) is False


# ===== Profiles =====

class TestWebripProfile:

    def test_lowers_crf_for_compressed_source(self):
        """A typical 3.5 Mbps 1080p WEB-DL: bpp says CRF 23, profile pulls it to 19."""
        info = make_video_info(bitrate=3_500_000, width=1920, height=1080, fps=24.0)

        assert VideoEncoder().calculate_optimal_crf(info, "hevc") == 23
        assert VideoEncoder(profile="webrip").calculate_optimal_crf(info, "hevc") == 19

    def test_lowers_crf_for_weak_source(self):
        """A 2.5 Mbps 1080p source: bpp says CRF 25, profile pulls it to 21."""
        info = make_video_info(bitrate=2_500_000, width=1920, height=1080, fps=24.0)

        assert VideoEncoder().calculate_optimal_crf(info, "hevc") == 25
        assert VideoEncoder(profile="webrip").calculate_optimal_crf(info, "hevc") == 21

    def test_clamps_low_bitrate_sources(self):
        """A weak 720p source would drop to CRF 24; the clamp holds it at 22."""
        info = make_video_info(bitrate=900_000, width=1280, height=720, fps=24.0)
        assert VideoEncoder(profile="webrip").calculate_optimal_crf(info, "hevc") == 22

    def test_clamps_high_bitrate_sources(self):
        """A high-bitrate source can't go below the profile floor."""
        info = make_video_info(bitrate=50_000_000, width=1920, height=1080, fps=24.0)
        assert VideoEncoder(profile="webrip").calculate_optimal_crf(info, "hevc") == 19

    def test_crf_stays_in_valid_range(self):
        """Never emits a CRF ffmpeg would reject, whatever the source."""
        for bitrate in (100, 1_000_000, 500_000_000):
            info = make_video_info(bitrate=bitrate, width=1920, height=1080, fps=24.0)
            crf = VideoEncoder(profile="webrip").calculate_optimal_crf(info, "hevc")
            assert 0 <= crf <= 51

    def test_profile_sets_preset_and_audio(self):
        settings = VideoEncoder.PROFILES["webrip"]
        assert settings["preset"] == "slow"
        assert settings["audio_codec"] == "copy"

    def test_no_profile_leaves_crf_unchanged(self):
        info = make_video_info(bitrate=3_500_000, width=1920, height=1080, fps=24.0)
        assert VideoEncoder(profile=None).calculate_optimal_crf(info, "hevc") == 23

    def test_rejects_x265_param_containing_colon(self):
        """':' is ffmpeg's separator — a value containing one corrupts the chain."""
        broken = {"bad": {"description": "x", "x265_params": ["deblock=-1:-1"]}}
        with patch.dict(VideoEncoder.PROFILES, broken):
            with pytest.raises(ValueError, match="separator"):
                VideoEncoder(profile="bad")

    def test_shipped_profiles_have_no_colons(self):
        for name, settings in VideoEncoder.PROFILES.items():
            for param in settings.get("x265_params", []):
                assert ":" not in param, f"{name} profile: {param}"
