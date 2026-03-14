"""
Shared fixtures for VideoSentinel tests.

Provides:
- tmp directories with fake video files (no ffmpeg needed)
- A real tiny test video generated via ffmpeg (for integration tests)
- Common VideoInfo fixtures
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Allow imports from project root and tests dir
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import make_video_info


@pytest.fixture
def video_info():
    """A typical valid 1080p HEVC VideoInfo."""
    return make_video_info()


# ---------------------------------------------------------------------------
# Temporary directory with fake video files (no ffmpeg needed)
# ---------------------------------------------------------------------------

@pytest.fixture
def video_dir(tmp_path):
    """Create a temp directory containing empty files with video extensions."""
    files = [
        "movie.mp4", "clip.avi", "show.mkv", "trailer.wmv",
        "notes.txt", "image.jpg",
    ]
    for name in files:
        (tmp_path / name).write_bytes(b"\x00" * 1024)
    return tmp_path


@pytest.fixture
def nested_video_dir(tmp_path):
    """Temp directory tree with videos at multiple levels."""
    root = tmp_path / "library"
    root.mkdir()
    (root / "a.mp4").write_bytes(b"\x00" * 1024)
    sub = root / "subdir"
    sub.mkdir()
    (sub / "b.mkv").write_bytes(b"\x00" * 1024)
    (sub / "c.txt").write_bytes(b"\x00" * 1024)
    deep = sub / "deep"
    deep.mkdir()
    (deep / "d.avi").write_bytes(b"\x00" * 1024)
    return root


# ---------------------------------------------------------------------------
# Real test video (requires ffmpeg) — session-scoped for speed
# ---------------------------------------------------------------------------

def _ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@pytest.fixture(scope="session")
def real_video(tmp_path_factory):
    """Generate a tiny 2-second test video using ffmpeg.

    Returns the Path, or skips the test if ffmpeg is not installed.
    """
    if not _ffmpeg_available():
        pytest.skip("ffmpeg not available")

    out = tmp_path_factory.mktemp("videos") / "test_input.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=24",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
        "-c:a", "aac", "-b:a", "64k",
        "-pix_fmt", "yuv420p",
        str(out),
    ]
    subprocess.run(cmd, capture_output=True, timeout=30, check=True)
    return out


# ---------------------------------------------------------------------------
# Cache fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def cache_file(tmp_path):
    """Return a Path for a temporary cache JSON file."""
    return tmp_path / "test_cache.json"
