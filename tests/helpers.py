"""Shared test helpers — importable from any test module."""

from pathlib import Path
from video_analyzer import VideoInfo


def make_video_info(**overrides) -> VideoInfo:
    """Create a VideoInfo with sensible defaults; override any field."""
    defaults = dict(
        file_path=Path("/fake/video.mp4"),
        codec="hevc",
        container="mp4",
        resolution=(1920, 1080),
        width=1920,
        height=1080,
        bitrate=5_000_000,
        duration=120.0,
        fps=24.0,
        has_audio=True,
        audio_codec="aac",
        file_size=75_000_000,
        is_valid=True,
        error_message=None,
    )
    defaults.update(overrides)
    return VideoInfo(**defaults)
