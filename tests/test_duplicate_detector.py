"""Tests for duplicate_detector.py — hash comparison and filename-based grouping."""

import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import numpy as np
import imagehash
from PIL import Image

from duplicate_detector import DuplicateDetector


# ===== _compare_video_hashes =====

class TestCompareVideoHashes:

    @pytest.fixture
    def detector(self):
        return DuplicateDetector()

    def _make_hash(self, value: int = 0, size: int = 12) -> imagehash.ImageHash:
        """Create an ImageHash from an integer seed for testing."""
        arr = np.zeros((size, size), dtype=bool)
        # Set bits based on value for deterministic but varied hashes
        for i in range(min(value, size * size)):
            arr[i // size][i % size] = True
        return imagehash.ImageHash(arr)

    def test_identical_hashes_distance_zero(self, detector):
        h = self._make_hash(42)
        distance = detector._compare_video_hashes([h, h, h], [h, h, h])
        assert distance == 0.0

    def test_different_hashes_positive_distance(self, detector):
        h1 = self._make_hash(0)
        h2 = self._make_hash(50)
        distance = detector._compare_video_hashes([h1], [h2])
        assert distance > 0

    def test_empty_hashes_returns_negative(self, detector):
        assert detector._compare_video_hashes([], []) == -1
        assert detector._compare_video_hashes([], [self._make_hash()]) == -1
        assert detector._compare_video_hashes([self._make_hash()], []) == -1

    def test_none_hashes_returns_negative(self, detector):
        assert detector._compare_video_hashes(None, None) == -1
        assert detector._compare_video_hashes(None, [self._make_hash()]) == -1

    def test_unequal_lengths_uses_minimum(self, detector):
        """When hash lists differ in length, compare min(len) pairs."""
        h = self._make_hash(42)
        distance = detector._compare_video_hashes([h, h, h], [h])
        assert distance == 0.0

    def test_average_across_frames(self, detector):
        """Distance is averaged across all frame pairs."""
        h_same = self._make_hash(0)
        h_diff = self._make_hash(50)
        # 2 frames: one identical pair (distance=0), one different pair (distance>0)
        d = detector._compare_video_hashes([h_same, h_diff], [h_same, h_same])
        # Average should be between 0 and the full distance
        full_d = detector._compare_video_hashes([h_diff], [h_same])
        assert 0 < d < full_d


# ===== find_duplicates_by_filename =====

class TestFindDuplicatesByFilename:

    @pytest.fixture
    def detector(self):
        return DuplicateDetector()

    def test_same_name_different_extension(self, detector):
        paths = [Path("/v/movie.mp4"), Path("/v/movie.avi"), Path("/v/other.mp4")]
        groups = detector.find_duplicates_by_filename(paths)
        assert len(groups) == 1
        group_files = list(groups.values())[0]
        names = {p.name for p in group_files}
        assert names == {"movie.mp4", "movie.avi"}

    def test_reencoded_suffix_stripped(self, detector):
        paths = [Path("/v/movie.mp4"), Path("/v/movie_reencoded.mp4")]
        groups = detector.find_duplicates_by_filename(paths)
        assert len(groups) == 1

    def test_quicklook_suffix_stripped(self, detector):
        paths = [Path("/v/movie.mp4"), Path("/v/movie_quicklook.mp4")]
        groups = detector.find_duplicates_by_filename(paths)
        assert len(groups) == 1

    def test_codec_suffixes_stripped(self, detector):
        paths = [Path("/v/movie.mp4"), Path("/v/movie_hevc.mp4"), Path("/v/movie_x265.mp4")]
        groups = detector.find_duplicates_by_filename(paths)
        assert len(groups) == 1
        group_files = list(groups.values())[0]
        assert len(group_files) == 3

    def test_copy_suffix_stripped(self, detector):
        paths = [Path("/v/movie.mp4"), Path("/v/movie copy.mp4")]
        groups = detector.find_duplicates_by_filename(paths)
        assert len(groups) == 1

    def test_numbered_copies_stripped(self, detector):
        paths = [Path("/v/movie.mp4"), Path("/v/movie (1).mp4"), Path("/v/movie (2).mp4")]
        groups = detector.find_duplicates_by_filename(paths)
        assert len(groups) == 1
        group_files = list(groups.values())[0]
        assert len(group_files) == 3

    def test_case_insensitive(self, detector):
        paths = [Path("/v/Movie.mp4"), Path("/v/MOVIE.avi")]
        groups = detector.find_duplicates_by_filename(paths)
        assert len(groups) == 1

    def test_no_duplicates_returns_empty(self, detector):
        paths = [Path("/v/movie.mp4"), Path("/v/show.mp4"), Path("/v/trailer.mkv")]
        groups = detector.find_duplicates_by_filename(paths)
        assert len(groups) == 0

    def test_multiple_groups(self, detector):
        paths = [
            Path("/v/movie.mp4"), Path("/v/movie.avi"),
            Path("/v/show.mp4"), Path("/v/show_reencoded.mp4"),
        ]
        groups = detector.find_duplicates_by_filename(paths)
        assert len(groups) == 2

    def test_chained_suffixes(self, detector):
        """Multiple suffixes stacked: movie_reencoded_backup → movie."""
        paths = [Path("/v/movie.mp4"), Path("/v/movie_reencoded_backup.mp4")]
        groups = detector.find_duplicates_by_filename(paths)
        assert len(groups) == 1

    def test_old_backup_suffixes(self, detector):
        paths = [Path("/v/movie.mp4"), Path("/v/movie_old.mp4"), Path("/v/movie_backup.mp4")]
        groups = detector.find_duplicates_by_filename(paths)
        assert len(groups) == 1
        group_files = list(groups.values())[0]
        assert len(group_files) == 3

    def test_trailing_underscores_cleaned(self, detector):
        """After suffix stripping, trailing underscores/spaces should be removed."""
        paths = [Path("/v/movie_.mp4"), Path("/v/movie.mp4")]
        groups = detector.find_duplicates_by_filename(paths)
        assert len(groups) == 1

    def test_single_file_no_group(self, detector):
        paths = [Path("/v/movie.mp4")]
        groups = detector.find_duplicates_by_filename(paths)
        assert len(groups) == 0

    def test_empty_list(self, detector):
        groups = detector.find_duplicates_by_filename([])
        assert len(groups) == 0


# ===== DuplicateDetector initialization =====

class TestDuplicateDetectorInit:

    def test_default_params(self):
        d = DuplicateDetector()
        assert d.hash_size == 12
        assert d.threshold == 15
        assert d.num_samples == 10

    def test_custom_params(self):
        d = DuplicateDetector(hash_size=8, threshold=10, num_samples=5)
        assert d.hash_size == 8
        assert d.threshold == 10
        assert d.num_samples == 5
