"""
Video analysis module for checking encoding specs and detecting issues
"""

import json
import subprocess
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass


@dataclass
class VideoInfo:
    """Container for video file information"""
    file_path: Path
    codec: str
    container: str
    resolution: tuple
    width: int
    height: int
    bitrate: int
    duration: float
    fps: float
    has_audio: bool
    audio_codec: Optional[str] = None
    file_size: int = 0
    is_valid: bool = True
    error_message: Optional[str] = None


class VideoAnalyzer:
    """Analyzes video files to extract encoding information"""

    # Common video file extensions
    VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg'}

    # Modern codec standards
    MODERN_CODECS = {'hevc', 'h265', 'av1', 'vp9'}
    ACCEPTABLE_CODECS = {'h264', 'hevc', 'h265', 'av1', 'vp9'}

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def is_video_file(self, file_path: Path) -> bool:
        """Check if file is a video based on extension"""
        return file_path.suffix.lower() in self.VIDEO_EXTENSIONS

    def get_video_info(self, file_path: Path) -> Optional[VideoInfo]:
        """
        Extract video information using ffprobe

        Args:
            file_path: Path to video file

        Returns:
            VideoInfo object or None if file cannot be analyzed
        """
        if not file_path.exists():
            return None

        try:
            # Use ffprobe to get video metadata
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                str(file_path)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                return VideoInfo(
                    file_path=file_path,
                    codec='unknown',
                    container='unknown',
                    resolution=(0, 0),
                    width=0,
                    height=0,
                    bitrate=0,
                    duration=0.0,
                    fps=0.0,
                    has_audio=False,
                    is_valid=False,
                    error_message=f"ffprobe failed: {result.stderr}"
                )

            data = json.loads(result.stdout)

            # Find video and audio streams
            video_stream = None
            audio_stream = None

            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video' and video_stream is None:
                    video_stream = stream
                elif stream.get('codec_type') == 'audio' and audio_stream is None:
                    audio_stream = stream

            if not video_stream:
                return VideoInfo(
                    file_path=file_path,
                    codec='unknown',
                    container='unknown',
                    resolution=(0, 0),
                    width=0,
                    height=0,
                    bitrate=0,
                    duration=0.0,
                    fps=0.0,
                    has_audio=False,
                    is_valid=False,
                    error_message="No video stream found"
                )

            # Extract video information
            codec = video_stream.get('codec_name', 'unknown')
            width = int(video_stream.get('width', 0))
            height = int(video_stream.get('height', 0))

            # Calculate FPS
            fps_str = video_stream.get('r_frame_rate', '0/1')
            try:
                num, den = map(int, fps_str.split('/'))
                fps = num / den if den != 0 else 0.0
            except:
                fps = 0.0

            # Get format information
            format_info = data.get('format', {})
            container = format_info.get('format_name', 'unknown').split(',')[0]
            duration = float(format_info.get('duration', 0.0))
            bitrate = int(format_info.get('bit_rate', 0))
            file_size = int(format_info.get('size', 0))

            # Audio information
            has_audio = audio_stream is not None
            audio_codec = audio_stream.get('codec_name') if audio_stream else None

            return VideoInfo(
                file_path=file_path,
                codec=codec,
                container=container,
                resolution=(width, height),
                width=width,
                height=height,
                bitrate=bitrate,
                duration=duration,
                fps=fps,
                has_audio=has_audio,
                audio_codec=audio_codec,
                file_size=file_size,
                is_valid=True
            )

        except subprocess.TimeoutExpired:
            return VideoInfo(
                file_path=file_path,
                codec='unknown',
                container='unknown',
                resolution=(0, 0),
                width=0,
                height=0,
                bitrate=0,
                duration=0.0,
                fps=0.0,
                has_audio=False,
                is_valid=False,
                error_message="ffprobe timeout"
            )
        except Exception as e:
            return VideoInfo(
                file_path=file_path,
                codec='unknown',
                container='unknown',
                resolution=(0, 0),
                width=0,
                height=0,
                bitrate=0,
                duration=0.0,
                fps=0.0,
                has_audio=False,
                is_valid=False,
                error_message=str(e)
            )

    def meets_modern_specs(self, video_info: VideoInfo) -> bool:
        """
        Check if video meets modern encoding specifications

        Args:
            video_info: VideoInfo object

        Returns:
            True if video meets modern specs, False otherwise
        """
        if not video_info.is_valid:
            return False

        # Check codec
        codec_lower = video_info.codec.lower()
        if codec_lower not in self.MODERN_CODECS:
            return False

        # Check container
        if video_info.container not in {'mp4', 'mkv', 'matroska', 'webm'}:
            return False

        # Video should have valid dimensions
        if video_info.width == 0 or video_info.height == 0:
            return False

        return True

    def find_videos(self, directory: Path, recursive: bool = False) -> List[Path]:
        """
        Find all video files in a directory

        Args:
            directory: Directory to scan
            recursive: Whether to scan recursively

        Returns:
            List of video file paths
        """
        video_files = []

        if recursive:
            for ext in self.VIDEO_EXTENSIONS:
                video_files.extend(directory.rglob(f'*{ext}'))
        else:
            for ext in self.VIDEO_EXTENSIONS:
                video_files.extend(directory.glob(f'*{ext}'))

        return sorted(video_files)
