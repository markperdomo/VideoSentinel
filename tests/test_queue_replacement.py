"""
Tests for the deferred replacement workflow in queue mode.

Covers:
- FileState.UPLOADED state transitions
- QueuedFile size tracking fields
- Post-upload validation (size matching)
- get_replacement_report() method
- confirm_replacements() method
- load_state() handling of UPLOADED state
- UI replacement table creation
"""

import json
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

    def test_queued_file_serialization_roundtrip(self):
        """to_dict / from_dict should preserve size fields."""
        qf = QueuedFile(
            source_path="/src/video.avi",
            local_path="/tmp/download_video.avi",
            output_path="/tmp/encoded_video.mp4",
            final_path="/src/video.mp4",
            state=FileState.UPLOADED,
            source_size=5_000_000,
            output_size=2_000_000,
        )
        data = qf.to_dict()
        assert data['state'] == 'uploaded'
        assert data['source_size'] == 5_000_000
        assert data['output_size'] == 2_000_000

        restored = QueuedFile.from_dict(data)
        assert restored.state == FileState.UPLOADED
        assert restored.source_size == 5_000_000
        assert restored.output_size == 2_000_000

    def test_from_dict_missing_size_fields(self):
        """Old state files without size fields should still deserialize."""
        data = {
            'source_path': '/src/video.avi',
            'local_path': None,
            'output_path': None,
            'final_path': None,
            'state': 'pending',
            'error': None,
            # No source_size or output_size keys
        }
        qf = QueuedFile.from_dict(data)
        assert qf.source_size is None
        assert qf.output_size is None


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
# confirm_replacements
# ---------------------------------------------------------------------------

class TestConfirmReplacements:

    def test_deletes_originals_and_marks_complete(self, tmp_path):
        """confirm_replacements should delete original, mark COMPLETE."""
        # Create fake files on "network"
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

        summary = mgr.confirm_replacements()

        assert summary['replaced'] == 1
        assert summary['failed'] == 0
        assert summary['bytes_freed'] == 5000
        assert not orig.exists()  # Original deleted
        assert encoded.exists()   # Encoded still there
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
            final_path=str(video),  # Same path
            state=FileState.UPLOADED,
            source_size=5000,
            output_size=3000,
        )
        mgr.files = [qf]

        summary = mgr.confirm_replacements()
        assert summary['replaced'] == 1
        assert summary['failed'] == 0
        assert video.exists()  # File should still exist (it was overwritten, not deleted)

    def test_fails_if_encoded_missing(self, tmp_path):
        """If the encoded file is missing from network, should fail gracefully."""
        network_dir = tmp_path / "network"
        network_dir.mkdir()
        orig = network_dir / "video.avi"
        orig.write_bytes(b"\x00" * 5000)
        # No encoded file

        mgr = NetworkQueueManager(temp_dir=tmp_path / "temp", verbose=False, replace_original=True)
        qf = QueuedFile(
            source_path=str(orig),
            local_path=None,
            output_path=None,
            final_path=str(network_dir / "video.mp4"),  # Doesn't exist
            state=FileState.UPLOADED,
        )
        mgr.files = [qf]

        summary = mgr.confirm_replacements()
        assert summary['replaced'] == 0
        assert summary['failed'] == 1
        assert orig.exists()  # Original should NOT be deleted

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

        with patch.object(mgr, 'save_state') as mock_save:
            mgr.confirm_replacements()
            assert mock_save.call_count >= 1


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
                },
            ],
            'timestamp': 1000,
        }
        state_file = tmp_path / "queue_state.json"
        state_file.write_text(json.dumps(state))
        mgr.state_file = state_file

        result = mgr.load_state()
        assert result is True
        # Should not be in any processing queue
        assert mgr.download_queue.empty()
        assert mgr.encode_queue.empty()
        assert mgr.upload_queue.empty()
        # File should remain in UPLOADED state
        assert mgr.files[0].state == FileState.UPLOADED


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
        # 2 data rows + 1 totals row
        assert len(table.rows) == 3

    def test_create_replacement_table_empty(self):
        table = create_replacement_table([])
        assert len(table.rows) == 0
