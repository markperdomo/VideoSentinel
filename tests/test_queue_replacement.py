"""
Tests for the deferred replacement workflow in queue mode.

Covers:
- FileState.UPLOADED state transitions
- QueuedFile size tracking and duration fields
- Post-upload validation (size matching)
- get_replacement_report() method
- confirm_replacements() with ffprobe duration validation
- _validate_uploaded_video() method
- load_state() handling of UPLOADED state
- UI replacement table creation
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from network_queue_manager import NetworkQueueManager, QueuedFile, FileState
from ui import create_replacement_table, format_size


# ---------------------------------------------------------------------------
# FileState and QueuedFile basics
# ---------------------------------------------------------------------------

class TestFileStateUploaded:
    """Tests for the new UPLOADED state."""

    def test_uploaded_state_exists(self):
        assert FileState.UPLOADED.value == "uploaded"

    def test_state_ordering_in_pipeline(self):
        """UPLOADED should come between UPLOADING and COMPLETE."""
        states = [s.value for s in FileState]
        assert states.index("uploaded") > states.index("uploading")
        assert states.index("uploaded") < states.index("complete")

    def test_queued_file_size_fields_default_none(self):
        qf = QueuedFile(
            source_path="/src/video.avi",
            local_path=None,
            output_path=None,
            final_path=None,
            state=FileState.PENDING,
        )
        assert qf.source_size is None
        assert qf.output_size is None
        assert qf.source_duration is None

    def test_queued_file_serialization_roundtrip(self):
        """to_dict / from_dict should preserve size and duration fields."""
        qf = QueuedFile(
            source_path="/src/video.avi",
            local_path="/tmp/download_video.avi",
            output_path="/tmp/encoded_video.mp4",
            final_path="/src/video.mp4",
            state=FileState.UPLOADED,
            source_size=5_000_000,
            output_size=2_000_000,
            source_duration=120.5,
        )
        data = qf.to_dict()
        assert data['state'] == 'uploaded'
        assert data['source_size'] == 5_000_000
        assert data['output_size'] == 2_000_000
        assert data['source_duration'] == 120.5

        restored = QueuedFile.from_dict(data)
        assert restored.state == FileState.UPLOADED
        assert restored.source_size == 5_000_000
        assert restored.output_size == 2_000_000
        assert restored.source_duration == 120.5

    def test_from_dict_missing_size_fields(self):
        """Old state files without size/duration fields should still deserialize."""
        data = {
            'source_path': '/src/video.avi',
            'local_path': None,
            'output_path': None,
            'final_path': None,
            'state': 'pending',
            'error': None,
            # No source_size, output_size, or source_duration keys
        }
        qf = QueuedFile.from_dict(data)
        assert qf.source_size is None
        assert qf.output_size is None
        assert qf.source_duration is None


# ---------------------------------------------------------------------------
# get_replacement_report
# ---------------------------------------------------------------------------

class TestGetReplacementReport:

    def test_only_uploaded_files_in_report(self, tmp_path):
        mgr = NetworkQueueManager(temp_dir=tmp_path, verbose=False)
        mgr.files = [
            QueuedFile("/src/a.avi", None, None, "/src/a.mp4", FileState.UPLOADED, source_size=5000, output_size=3000),
            QueuedFile("/src/b.avi", None, None, "/src/b.mp4", FileState.COMPLETE, source_size=4000, output_size=2000),
            QueuedFile("/src/c.avi", None, None, None, FileState.FAILED, error="boom"),
        ]
        report = mgr.get_replacement_report()
        assert len(report) == 1
        assert report[0]['source_path'] == "/src/a.avi"
        assert report[0]['source_size'] == 5000
        assert report[0]['output_size'] == 3000

    def test_empty_report_when_no_uploaded(self, tmp_path):
        mgr = NetworkQueueManager(temp_dir=tmp_path, verbose=False)
        mgr.files = [
            QueuedFile("/src/a.avi", None, None, "/src/a.mp4", FileState.COMPLETE),
        ]
        assert mgr.get_replacement_report() == []


# ---------------------------------------------------------------------------
# _validate_uploaded_video
# ---------------------------------------------------------------------------

class TestValidateUploadedVideo:
    """Tests for the ffprobe-based validation in confirm_replacements."""

    def test_missing_file_returns_error(self, tmp_path):
        mgr = NetworkQueueManager(temp_dir=tmp_path, verbose=False)
        result = mgr._validate_uploaded_video(tmp_path / "nonexistent.mp4", source_duration=10.0)
        assert result is not None
        assert "does not exist" in result

    def test_tiny_file_returns_error(self, tmp_path):
        tiny = tmp_path / "tiny.mp4"
        tiny.write_bytes(b"\x00" * 100)  # < 1KB
        mgr = NetworkQueueManager(temp_dir=tmp_path, verbose=False)
        result = mgr._validate_uploaded_video(tiny, source_duration=10.0)
        assert result is not None
        assert "too small" in result

    def test_ffprobe_failure_returns_error(self, tmp_path):
        """Non-video file should fail ffprobe check."""
        fake = tmp_path / "fake.mp4"
        fake.write_bytes(b"\x00" * 5000)  # > 1KB but not a real video
        mgr = NetworkQueueManager(temp_dir=tmp_path, verbose=False)
        result = mgr._validate_uploaded_video(fake, source_duration=10.0)
        assert result is not None
        assert "ffprobe" in result.lower() or "No video stream" in result

    def test_valid_video_passes(self, real_video, tmp_path):
        """A real video file should pass validation."""
        mgr = NetworkQueueManager(temp_dir=tmp_path, verbose=False)
        result = mgr._validate_uploaded_video(real_video, source_duration=2.0)
        assert result is None  # No error

    def test_duration_mismatch_returns_error(self, real_video, tmp_path):
        """A video with wrong source_duration should fail duration check."""
        mgr = NetworkQueueManager(temp_dir=tmp_path, verbose=False)
        # Real video is 2s, claim source was 100s
        result = mgr._validate_uploaded_video(real_video, source_duration=100.0)
        assert result is not None
        assert "Duration mismatch" in result

    def test_no_source_duration_skips_check(self, real_video, tmp_path):
        """If source_duration is None, duration check is skipped."""
        mgr = NetworkQueueManager(temp_dir=tmp_path, verbose=False)
        result = mgr._validate_uploaded_video(real_video, source_duration=None)
        assert result is None  # Should pass without duration comparison

    def test_ffprobe_timeout_returns_error(self, tmp_path):
        """ffprobe timeout should return an error, not raise."""
        video = tmp_path / "video.mp4"
        video.write_bytes(b"\x00" * 5000)
        mgr = NetworkQueueManager(temp_dir=tmp_path, verbose=False)

        with patch('network_queue_manager.subprocess.run', side_effect=subprocess.TimeoutExpired('ffprobe', 60)):
            result = mgr._validate_uploaded_video(video, source_duration=10.0)
        assert result is not None
        assert "timeout" in result.lower()


# ---------------------------------------------------------------------------
# confirm_replacements
# ---------------------------------------------------------------------------

class TestConfirmReplacements:

    def _mock_validation_pass(self, *args, **kwargs):
        """Mock that always passes validation."""
        return None

    def test_deletes_originals_and_marks_complete(self, tmp_path):
        """confirm_replacements should delete original, mark COMPLETE."""
        network_dir = tmp_path / "network"
        network_dir.mkdir()
        orig = network_dir / "video.avi"
        orig.write_bytes(b"\x00" * 5000)
        encoded = network_dir / "video.mp4"
        encoded.write_bytes(b"\x00" * 3000)

        mgr = NetworkQueueManager(temp_dir=tmp_path / "temp", verbose=False, replace_original=True)
        qf = QueuedFile(
            source_path=str(orig),
            local_path=None,
            output_path=None,
            final_path=str(encoded),
            state=FileState.UPLOADED,
            source_size=5000,
            output_size=3000,
        )
        mgr.files = [qf]

        with patch.object(mgr, '_validate_uploaded_video', self._mock_validation_pass):
            summary = mgr.confirm_replacements()

        assert summary['replaced'] == 1
        assert summary['failed'] == 0
        assert summary['bytes_freed'] == 5000
        assert not orig.exists()
        assert encoded.exists()
        assert qf.state == FileState.COMPLETE

    def test_same_path_no_error(self, tmp_path):
        """When source and final are the same path (e.g., .mp4 -> .mp4), no error."""
        network_dir = tmp_path / "network"
        network_dir.mkdir()
        video = network_dir / "video.mp4"
        video.write_bytes(b"\x00" * 3000)

        mgr = NetworkQueueManager(temp_dir=tmp_path / "temp", verbose=False, replace_original=True)
        qf = QueuedFile(
            source_path=str(video),
            local_path=None,
            output_path=None,
            final_path=str(video),
            state=FileState.UPLOADED,
            source_size=5000,
            output_size=3000,
        )
        mgr.files = [qf]

        with patch.object(mgr, '_validate_uploaded_video', self._mock_validation_pass):
            summary = mgr.confirm_replacements()
        assert summary['replaced'] == 1
        assert summary['failed'] == 0
        assert video.exists()

    def test_fails_if_validation_fails(self, tmp_path):
        """If validation returns an error, original should NOT be deleted."""
        network_dir = tmp_path / "network"
        network_dir.mkdir()
        orig = network_dir / "video.avi"
        orig.write_bytes(b"\x00" * 5000)
        encoded = network_dir / "video.mp4"
        encoded.write_bytes(b"\x00" * 3000)

        mgr = NetworkQueueManager(temp_dir=tmp_path / "temp", verbose=False, replace_original=True)
        qf = QueuedFile(
            source_path=str(orig),
            local_path=None,
            output_path=None,
            final_path=str(encoded),
            state=FileState.UPLOADED,
            source_duration=100.0,
        )
        mgr.files = [qf]

        def mock_fail(*args, **kwargs):
            return "Duration mismatch: 2.0s vs 100.0s"

        with patch.object(mgr, '_validate_uploaded_video', mock_fail):
            summary = mgr.confirm_replacements()

        assert summary['replaced'] == 0
        assert summary['failed'] == 1
        assert orig.exists()  # Original preserved
        assert "Duration mismatch" in summary['errors'][0]

    def test_fails_if_encoded_missing(self, tmp_path):
        """If the encoded file is missing from network, should fail gracefully."""
        network_dir = tmp_path / "network"
        network_dir.mkdir()
        orig = network_dir / "video.avi"
        orig.write_bytes(b"\x00" * 5000)

        mgr = NetworkQueueManager(temp_dir=tmp_path / "temp", verbose=False, replace_original=True)
        qf = QueuedFile(
            source_path=str(orig),
            local_path=None,
            output_path=None,
            final_path=str(network_dir / "video.mp4"),
            state=FileState.UPLOADED,
        )
        mgr.files = [qf]

        # Don't mock — _validate_uploaded_video will detect missing file
        summary = mgr.confirm_replacements()
        assert summary['replaced'] == 0
        assert summary['failed'] == 1
        assert orig.exists()

    def test_state_saved_after_each_deletion(self, tmp_path):
        """Crash safety: state is saved after each file replacement."""
        network_dir = tmp_path / "network"
        network_dir.mkdir()
        orig = network_dir / "video.avi"
        orig.write_bytes(b"\x00" * 5000)
        encoded = network_dir / "video.mp4"
        encoded.write_bytes(b"\x00" * 3000)

        mgr = NetworkQueueManager(temp_dir=tmp_path / "temp", verbose=False, replace_original=True)
        qf = QueuedFile(
            source_path=str(orig),
            local_path=None,
            output_path=None,
            final_path=str(encoded),
            state=FileState.UPLOADED,
        )
        mgr.files = [qf]

        with patch.object(mgr, '_validate_uploaded_video', self._mock_validation_pass), \
             patch.object(mgr, 'save_state') as mock_save:
            mgr.confirm_replacements()
            assert mock_save.call_count >= 1

    def test_confirm_with_real_video(self, real_video, tmp_path):
        """End-to-end: confirm_replacements with a real video passes duration check."""
        import shutil

        network_dir = tmp_path / "network"
        network_dir.mkdir()
        orig = network_dir / "video.avi"
        orig.write_bytes(b"\x00" * 5000)  # Fake original
        encoded = network_dir / "video.mp4"
        shutil.copy2(real_video, encoded)  # Real video as the encoded output

        mgr = NetworkQueueManager(temp_dir=tmp_path / "temp", verbose=False, replace_original=True)
        qf = QueuedFile(
            source_path=str(orig),
            local_path=None,
            output_path=None,
            final_path=str(encoded),
            state=FileState.UPLOADED,
            source_size=5000,
            output_size=encoded.stat().st_size,
            source_duration=2.0,  # Matches the real 2-second video
        )
        mgr.files = [qf]

        summary = mgr.confirm_replacements()
        assert summary['replaced'] == 1
        assert summary['failed'] == 0
        assert not orig.exists()


# ---------------------------------------------------------------------------
# _get_duration helper
# ---------------------------------------------------------------------------

class TestGetDuration:

    def test_real_video_returns_duration(self, real_video, tmp_path):
        duration = NetworkQueueManager._get_duration(real_video)
        assert duration is not None
        assert abs(duration - 2.0) < 1.0  # ~2 second test video

    def test_nonexistent_returns_none(self, tmp_path):
        result = NetworkQueueManager._get_duration(tmp_path / "nope.mp4")
        assert result is None

    def test_non_video_returns_none(self, tmp_path):
        fake = tmp_path / "fake.mp4"
        fake.write_bytes(b"\x00" * 5000)
        result = NetworkQueueManager._get_duration(fake)
        assert result is None or result == 0.0  # ffprobe may return 0 for garbage


# ---------------------------------------------------------------------------
# load_state with UPLOADED
# ---------------------------------------------------------------------------

class TestLoadStateUploaded:

    def test_uploaded_files_not_requeued(self, tmp_path):
        """UPLOADED files should not be re-queued for download/encode/upload."""
        mgr = NetworkQueueManager(temp_dir=tmp_path, verbose=False)
        state = {
            'files': [
                {
                    'source_path': '/src/a.avi',
                    'local_path': None,
                    'output_path': None,
                    'final_path': '/src/a.mp4',
                    'state': 'uploaded',
                    'error': None,
                    'source_size': 5000,
                    'output_size': 3000,
                    'source_duration': 120.5,
                },
            ],
            'timestamp': 1000,
        }
        state_file = tmp_path / "queue_state.json"
        state_file.write_text(json.dumps(state))
        mgr.state_file = state_file

        result = mgr.load_state()
        assert result is True
        assert mgr.download_queue.empty()
        assert mgr.encode_queue.empty()
        assert mgr.upload_queue.empty()
        assert mgr.files[0].state == FileState.UPLOADED
        assert mgr.files[0].source_duration == 120.5


# ---------------------------------------------------------------------------
# get_progress with UPLOADED
# ---------------------------------------------------------------------------

class TestGetProgressUploaded:

    def test_progress_includes_uploaded_count(self, tmp_path):
        mgr = NetworkQueueManager(temp_dir=tmp_path, verbose=False)
        mgr.files = [
            QueuedFile("/src/a.avi", None, None, "/src/a.mp4", FileState.UPLOADED),
            QueuedFile("/src/b.avi", None, None, "/src/b.mp4", FileState.COMPLETE),
        ]
        progress = mgr.get_progress()
        assert progress['uploaded'] == 1
        assert progress['complete'] == 1


# ---------------------------------------------------------------------------
# UI: create_replacement_table and format_size
# ---------------------------------------------------------------------------

class TestUIHelpers:

    def test_format_size_bytes(self):
        assert format_size(0) == "--"
        assert "KB" in format_size(500_000)
        assert "MB" in format_size(5_000_000)
        assert "GB" in format_size(5_000_000_000)

    def test_create_replacement_table_basic(self):
        report = [
            {'source_path': '/src/video.avi', 'final_path': '/src/video.mp4', 'source_size': 10_000_000, 'output_size': 4_000_000},
            {'source_path': '/src/clip.wmv', 'final_path': '/src/clip.mp4', 'source_size': 5_000_000, 'output_size': 2_000_000},
        ]
        table = create_replacement_table(report)
        assert table.title == "Replacement Summary"
        assert len(table.rows) == 3  # 2 data rows + 1 totals row

    def test_create_replacement_table_empty(self):
        table = create_replacement_table([])
        assert len(table.rows) == 0
