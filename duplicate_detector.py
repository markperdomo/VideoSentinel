"""
Duplicate video detection using perceptual hashing
"""

import cv2
import imagehash
from PIL import Image
from pathlib import Path
from typing import Dict, List, Tuple, Set
from collections import defaultdict
from tqdm import tqdm


class DuplicateDetector:
    """Detects duplicate videos using perceptual hashing of video frames"""

    def __init__(self, hash_size: int = 12, threshold: int = 15, num_samples: int = 10, verbose: bool = False):
        """
        Initialize duplicate detector

        Args:
            hash_size: Size of the perceptual hash (default 12 = 144-bit hash per frame)
            threshold: Average Hamming distance threshold for considering videos similar (default: 15)
            num_samples: Number of frames to sample from each video (default: 10)
            verbose: Enable verbose output
        """
        self.hash_size = hash_size
        self.threshold = threshold
        self.num_samples = num_samples
        self.verbose = verbose

    def extract_frame(self, video_path: Path, frame_number: int = 0) -> Image.Image:
        """
        Extract a specific frame from a video

        Args:
            video_path: Path to video file
            frame_number: Frame number to extract (default: 0 for first frame)

        Returns:
            PIL Image object or None if extraction fails
        """
        try:
            cap = cv2.VideoCapture(str(video_path))

            if not cap.isOpened():
                if self.verbose:
                    print(f"Warning: Could not open video: {video_path}")
                return None

            # Get total frame count
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            if total_frames == 0:
                if self.verbose:
                    print(f"Warning: Video has no frames: {video_path}")
                cap.release()
                return None

            # If frame_number is beyond video length, use last frame
            if frame_number >= total_frames:
                frame_number = total_frames - 1

            # Set frame position
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

            # Read frame
            ret, frame = cap.read()
            cap.release()

            if not ret or frame is None:
                if self.verbose:
                    print(f"Warning: Could not read frame {frame_number} from: {video_path}")
                return None

            # Convert BGR (OpenCV) to RGB (PIL)
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Convert to PIL Image
            return Image.fromarray(frame_rgb)

        except Exception as e:
            if self.verbose:
                print(f"Error extracting frame from {video_path}: {e}")
            return None

    def extract_multiple_frames(self, video_path: Path, num_frames: int = 3) -> List[Image.Image]:
        """
        Extract multiple frames evenly distributed throughout the video

        Args:
            video_path: Path to video file
            num_frames: Number of frames to extract

        Returns:
            List of PIL Image objects
        """
        frames = []

        try:
            cap = cv2.VideoCapture(str(video_path))

            if not cap.isOpened():
                return frames

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            if total_frames == 0:
                cap.release()
                return frames

            # Calculate frame positions (evenly distributed)
            if total_frames < num_frames:
                frame_positions = list(range(total_frames))
            else:
                step = total_frames // (num_frames + 1)
                frame_positions = [step * (i + 1) for i in range(num_frames)]

            for pos in frame_positions:
                cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
                ret, frame = cap.read()

                if ret and frame is not None:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frames.append(Image.fromarray(frame_rgb))

            cap.release()

        except Exception as e:
            if self.verbose:
                print(f"Error extracting frames from {video_path}: {e}")

        return frames

    def compute_video_hash(self, video_path: Path) -> List[imagehash.ImageHash]:
        """
        Compute perceptual hashes for multiple frames of a video

        Uses multiple frames throughout the video for robust duplicate detection

        Args:
            video_path: Path to video file

        Returns:
            List of perceptual hashes (one per sampled frame) or None if computation fails
        """
        try:
            # Extract frames evenly distributed throughout the video
            frames = self.extract_multiple_frames(video_path, num_frames=self.num_samples)

            if not frames:
                if self.verbose:
                    tqdm.write(f"Warning: No frames extracted from: {video_path}")
                return None

            # Compute perceptual hash (phash) for each frame
            # phash is more robust than average_hash for finding similar images
            hashes = []
            for frame in frames:
                hash_value = imagehash.phash(frame, hash_size=self.hash_size)
                hashes.append(hash_value)

            return hashes

        except Exception as e:
            if self.verbose:
                tqdm.write(f"Error computing hash for {video_path}: {e}")
            return None

    def find_duplicates(self, video_paths: List[Path]) -> Dict[str, List[Path]]:
        """
        Find duplicate videos in a list using multi-frame perceptual hashing

        Args:
            video_paths: List of video file paths

        Returns:
            Dictionary mapping group IDs to lists of duplicate video paths
        """
        # Compute hashes for all videos
        video_hashes: Dict[Path, List[imagehash.ImageHash]] = {}

        for video_path in tqdm(video_paths, desc="Computing hashes", unit="video"):
            hash_list = self.compute_video_hash(video_path)
            if hash_list is not None:
                video_hashes[video_path] = hash_list

        tqdm.write(f"Successfully hashed {len(video_hashes)} videos")

        # Find similar videos based on average hash distance across frames
        duplicate_groups: Dict[str, List[Path]] = {}
        processed: Set[Path] = set()
        group_id = 0

        video_list = list(video_hashes.keys())

        for i, video1 in enumerate(video_list):
            if video1 in processed:
                continue

            # Start a new group
            current_group = [video1]
            processed.add(video1)

            # Compare with all remaining videos
            for video2 in video_list[i + 1:]:
                if video2 in processed:
                    continue

                # Calculate average Hamming distance across all frame pairs
                distance = self._compare_video_hashes(video_hashes[video1], video_hashes[video2])

                if distance >= 0 and distance <= self.threshold:
                    current_group.append(video2)
                    processed.add(video2)

            # Only save groups with duplicates (2+ videos)
            if len(current_group) > 1:
                duplicate_groups[f"group_{group_id}"] = current_group
                group_id += 1

        return duplicate_groups

    def _compare_video_hashes(
        self,
        hashes1: List[imagehash.ImageHash],
        hashes2: List[imagehash.ImageHash]
    ) -> float:
        """
        Compare two lists of video frame hashes

        Uses minimum average distance across corresponding frames

        Args:
            hashes1: List of hashes from first video
            hashes2: List of hashes from second video

        Returns:
            Average Hamming distance (lower = more similar), or -1 if incomparable
        """
        if not hashes1 or not hashes2:
            return -1

        # Take the minimum number of frames available
        num_frames = min(len(hashes1), len(hashes2))

        if num_frames == 0:
            return -1

        # Calculate distance for each corresponding frame pair
        distances = []
        for i in range(num_frames):
            distance = hashes1[i] - hashes2[i]
            distances.append(distance)

        # Return average distance across all frames
        avg_distance = sum(distances) / len(distances)
        return avg_distance

    def get_similarity_score(self, video1: Path, video2: Path) -> float:
        """
        Get similarity score between two videos (lower is more similar)

        Args:
            video1: Path to first video
            video2: Path to second video

        Returns:
            Average Hamming distance across frames (0 = identical, higher = more different)
            Returns -1 if comparison fails
        """
        hashes1 = self.compute_video_hash(video1)
        hashes2 = self.compute_video_hash(video2)

        if hashes1 is None or hashes2 is None:
            return -1

        return self._compare_video_hashes(hashes1, hashes2)

    def find_duplicates_by_filename(
        self,
        video_paths: List[Path],
        analyzer=None,
        check_duration: bool = True,
        duration_tolerance: float = 2.0
    ) -> Dict[str, List[Path]]:
        """
        Find duplicate videos based on filename matching (ignoring extension and common suffixes)

        This is useful when:
        - Original files are broken and can't generate perceptual hashes
        - You want very fast duplicate detection without video analysis
        - Files have same name but different extensions (_reencoded, _quicklook, etc.)

        Args:
            video_paths: List of video file paths
            analyzer: Optional VideoAnalyzer instance for duration checking
            check_duration: If True and analyzer provided, verify durations match (default: True)
            duration_tolerance: Maximum duration difference in seconds (default: 2.0)

        Returns:
            Dictionary mapping group IDs to lists of duplicate video paths
        """
        # Group videos by normalized filename
        filename_groups: Dict[str, List[Path]] = defaultdict(list)

        for video_path in video_paths:
            # Get the base filename without extension
            stem = video_path.stem

            # Remove common suffixes: _reencoded, _quicklook
            normalized_name = stem
            for suffix in ['_reencoded', '_quicklook']:
                if normalized_name.endswith(suffix):
                    normalized_name = normalized_name[:-len(suffix)]
                    break

            # Convert to lowercase for case-insensitive matching
            normalized_name = normalized_name.lower()

            # Group by normalized name
            filename_groups[normalized_name].append(video_path)

        # Convert to duplicate groups format (only groups with 2+ files)
        duplicate_groups: Dict[str, List[Path]] = {}
        group_id = 0
        filtered_count = 0

        for normalized_name, videos in filename_groups.items():
            if len(videos) > 1:
                # If duration checking enabled and analyzer available, filter by duration
                if check_duration and analyzer is not None:
                    # Get video info for all files in group
                    video_info_map = {}
                    for video in videos:
                        info = analyzer.get_video_info(video)
                        if info and info.duration > 0:
                            video_info_map[video] = info

                    # Group videos by similar duration
                    duration_groups = []
                    processed = set()

                    for video1, info1 in video_info_map.items():
                        if video1 in processed:
                            continue

                        # Start a new duration-based subgroup
                        duration_group = [video1]
                        processed.add(video1)

                        # Find other videos with similar duration
                        for video2, info2 in video_info_map.items():
                            if video2 in processed:
                                continue

                            duration_diff = abs(info1.duration - info2.duration)
                            if duration_diff <= duration_tolerance:
                                duration_group.append(video2)
                                processed.add(video2)

                        # Only keep groups with 2+ videos
                        if len(duration_group) > 1:
                            duration_groups.append(duration_group)

                    # Add each duration-based subgroup as a separate duplicate group
                    for duration_group in duration_groups:
                        duplicate_groups[f"group_{group_id}"] = duration_group
                        group_id += 1

                    # Track how many filename matches were filtered out by duration check
                    if len(duration_groups) == 0 and len(videos) > 1:
                        filtered_count += 1
                        if self.verbose:
                            tqdm.write(f"Filtered out '{normalized_name}': files have different durations")
                else:
                    # No duration checking, add all files with matching filenames
                    duplicate_groups[f"group_{group_id}"] = videos
                    group_id += 1

        if self.verbose:
            tqdm.write(f"Found {len(duplicate_groups)} filename-based duplicate groups")
            if check_duration and analyzer is not None and filtered_count > 0:
                tqdm.write(f"Filtered out {filtered_count} groups due to duration mismatch")

        return duplicate_groups
