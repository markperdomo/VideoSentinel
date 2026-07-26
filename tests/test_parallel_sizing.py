"""
Tests for sizing the parallel worker pool to the actual workload.

Each ffmpeg instance sizes its x265 thread pool as cpu_count // parallel, so
requesting more workers than there are files starves every encode and leaves
most of the CPU idle. Covers:
- VideoEncoder.set_parallel()
- batch_re_encode() clamping to len(video_paths)
- NetworkQueueManager.resolve_parallel() clamping to remaining work
- The x265 pools/frame-threads values that result
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from encoder import VideoEncoder
from network_queue_manager import NetworkQueueManager, QueuedFile, FileState


def _queued(state: FileState, idx: int = 0) -> QueuedFile:
    return QueuedFile(
        source_path=f"/net/show/ep{idx}.mkv",
        local_path=None,
        output_path=None,
        final_path=None,
        state=state,
    )


# ---------------------------------------------------------------------------
# set_parallel
# ---------------------------------------------------------------------------

class TestSetParallel:

    def test_sets_value(self):
        encoder = VideoEncoder(parallel=1)
        encoder.set_parallel(6)
        assert encoder.parallel == 6

    def test_clamps_to_at_least_one(self):
        encoder = VideoEncoder(parallel=4)
        encoder.set_parallel(0)
        assert encoder.parallel == 1

    def test_clamps_negative(self):
        encoder = VideoEncoder(parallel=4)
        encoder.set_parallel(-3)
        assert encoder.parallel == 1


# ---------------------------------------------------------------------------
# batch_re_encode clamping
# ---------------------------------------------------------------------------

class TestBatchParallelClamping:

    @pytest.fixture
    def stub_batch(self):
        """Stub out the actual parallel encode so only the sizing runs."""
        with patch.object(VideoEncoder, '_batch_re_encode_parallel',
                          return_value=({}, [], 0.0)) as batch, \
             patch.object(VideoEncoder, '_print_session_summary'):
            yield batch

    def test_more_files_than_workers_keeps_requested(self, stub_batch):
        encoder = VideoEncoder(parallel=4)
        encoder.batch_re_encode([Path(f"v{i}.mp4") for i in range(8)], parallel=4)
        assert encoder.parallel == 4

    def test_fewer_files_than_workers_clamps(self, stub_batch):
        """-j 4 over a 2-file batch must drop to 2, not starve both encodes."""
        encoder = VideoEncoder(parallel=4)
        encoder.batch_re_encode([Path("a.mp4"), Path("b.mp4")], parallel=4)
        assert encoder.parallel == 2

    def test_exact_match_unchanged(self, stub_batch):
        encoder = VideoEncoder(parallel=3)
        encoder.batch_re_encode([Path(f"v{i}.mp4") for i in range(3)], parallel=3)
        assert encoder.parallel == 3

    def test_single_file_falls_back_to_sequential(self, stub_batch):
        """One file with -j 4 should take the sequential path entirely."""
        encoder = VideoEncoder(parallel=4)
        encoder.batch_re_encode([Path("only.mp4")], parallel=4)
        assert encoder.parallel == 1
        stub_batch.assert_not_called()

    def test_empty_batch_clamps_to_one(self, stub_batch):
        encoder = VideoEncoder(parallel=4)
        encoder.batch_re_encode([], parallel=4)
        assert encoder.parallel == 1


# ---------------------------------------------------------------------------
# NetworkQueueManager.resolve_parallel
# ---------------------------------------------------------------------------

class TestResolveParallel:

    @pytest.fixture
    def manager(self):
        return NetworkQueueManager(temp_dir=Path(tempfile.mkdtemp()), parallel=4)

    def test_more_work_than_workers_keeps_requested(self, manager):
        manager.files = [_queued(FileState.PENDING, i) for i in range(9)]
        assert manager.resolve_parallel() == 4
        assert manager.parallel == 4

    def test_clamps_to_remaining_work(self, manager):
        manager.files = [_queued(FileState.PENDING, i) for i in range(2)]
        assert manager.resolve_parallel() == 2

    def test_finished_files_do_not_count(self, manager):
        """Resuming a queue where most files are done should not over-provision."""
        manager.files = [
            _queued(FileState.COMPLETE, 0),
            _queued(FileState.UPLOADED, 1),
            _queued(FileState.FAILED, 2),
            _queued(FileState.PENDING, 3),
            _queued(FileState.LOCAL, 4),
        ]
        assert manager.resolve_parallel() == 2

    def test_in_flight_states_count_as_work(self, manager):
        manager.files = [
            _queued(FileState.DOWNLOADING, 0),
            _queued(FileState.ENCODING, 1),
            _queued(FileState.UPLOADING, 2),
        ]
        assert manager.resolve_parallel() == 3

    def test_empty_queue_clamps_to_one(self, manager):
        manager.files = []
        assert manager.resolve_parallel() == 1

    def test_all_complete_clamps_to_one(self, manager):
        manager.files = [_queued(FileState.COMPLETE, i) for i in range(5)]
        assert manager.resolve_parallel() == 1

    def test_never_raises_above_requested(self, manager):
        manager.parallel = 2
        manager.files = [_queued(FileState.PENDING, i) for i in range(10)]
        assert manager.resolve_parallel() == 2


# ---------------------------------------------------------------------------
# The x265 thread budget that results
# ---------------------------------------------------------------------------

class TestX265ThreadBudget:
    """The whole point of clamping: pools/frame-threads must reflect reality."""

    def _x265_params(self, encoder, tmp_path):
        """Build a command and pull out the -x265-params value."""
        src = tmp_path / "in.mkv"
        src.write_bytes(b"x" * 2048)
        captured = {}

        def fake_popen(cmd, **kwargs):
            captured['cmd'] = cmd
            raise RuntimeError("stop after command build")

        with patch.object(VideoEncoder, 'find_existing_output', return_value=None), \
             patch.object(VideoEncoder, '_probe_streams', return_value=[
                 {'index': 0, 'codec_type': 'video', 'codec_name': 'h264', 'disposition': {}},
                 {'index': 1, 'codec_type': 'audio', 'codec_name': 'aac', 'disposition': {}},
             ]), \
             patch('encoder.subprocess.Popen', side_effect=fake_popen):
            encoder.re_encode_video(src, tmp_path / "out.mp4", target_codec='hevc', crf=20)

        cmd = captured['cmd']
        return cmd[cmd.index('-x265-params') + 1]

    def test_starved_pools_without_clamp(self, tmp_path):
        """Regression guard: -j 4 on a 14-core box gives each encode 3 pools."""
        encoder = VideoEncoder(parallel=4)
        with patch('encoder.os.cpu_count', return_value=14):
            params = self._x265_params(encoder, tmp_path)
        assert 'pools=3' in params
        assert 'frame-threads=1' in params

    def test_clamped_pools_use_the_whole_cpu(self, tmp_path):
        """After clamping to the 2 files that exist, each encode gets half the box."""
        encoder = VideoEncoder(parallel=4)
        encoder.set_parallel(2)
        with patch('encoder.os.cpu_count', return_value=14):
            params = self._x265_params(encoder, tmp_path)
        assert 'pools=7' in params
        assert 'frame-threads=3' in params

    def test_sequential_adds_no_thread_limits(self, tmp_path):
        """parallel=1 must not constrain x265 at all."""
        encoder = VideoEncoder(parallel=1)
        with patch('encoder.os.cpu_count', return_value=14):
            params = self._x265_params(encoder, tmp_path)
        assert 'pools=' not in params
        assert 'frame-threads=' not in params
