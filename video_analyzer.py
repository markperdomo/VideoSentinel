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

    # Common video file extensions - comprehensive list covering most video formats
    VIDEO_EXTENSIONS = {
        # Common modern formats
        '.mp4', '.mkv', '.webm', '.m4v', '.mov',
        # Legacy/Windows formats
        '.avi', '.wmv', '.asf', '.divx',
        # MPEG variants
        '.mpg', '.mpeg', '.mpe', '.mpv', '.m2v', '.mp2',
        # Flash/streaming
        '.flv', '.f4v', '.f4p', '.f4a', '.f4b',
        # Mobile/3GPP
        '.3gp', '.3g2',
        # Broadcast/professional
        '.mts', '.m2ts', '.ts', '.mxf', '.vob', '.dv',
        # Open formats
        '.ogv', '.ogg', '.ogm',
        # RealMedia
        '.rm', '.rmvb',
        # QuickTime variants
        '.qt', '.mqv',
        # Other formats
        '.gif', '.gifv', '.yuv', '.drc', '.mng', '.nsv', '.roq', '.svi',
        # Additional common extensions
        '.dat', '.vid', '.movie', '.amv', '.xvid'
    }

    # Modern codec standards - includes all variations and tags
    MODERN_CODECS = {'hevc', 'h265', 'hvc1', 'hev1', 'av1', 'av01', 'vp9', 'vp09'}
    ACCEPTABLE_CODECS = {'h264', 'avc', 'avc1', 'hevc', 'h265', 'hvc1', 'hev1', 'av1', 'av01', 'vp9', 'vp09'}

    def __init__(self, verbose: bool = False, max_resolution: Optional[tuple] = None):
        """
        Initialize VideoAnalyzer

        Args:
            verbose: Enable verbose output
            max_resolution: Optional (width, height) tuple for maximum acceptable resolution.
                          Videos exceeding this will be marked as non-compliant.
                          E.g., (1920, 1080) for 1080p maximum.
        """
        self.verbose = verbose
        self.max_resolution = max_resolution

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

            # Also check codec_tag_string for variations (e.g., hvc1, hev1 for HEVC)
            codec_tag = video_stream.get('codec_tag_string', '').lower().strip('[]')
            if self.verbose and codec_tag:
                print(f"  Detected codec: {codec}, tag: {codec_tag}")

            # Use codec tag if it provides more specific info (e.g., hvc1 instead of hevc)
            # But only if it's a recognized codec variant
            if codec_tag and codec_tag in self.MODERN_CODECS | self.ACCEPTABLE_CODECS:
                codec = codec_tag

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

    def check_quicklook_compatibility(self, file_path: Path) -> Dict[str, any]:
        """
        Check if video is compatible with macOS QuickLook

        Args:
            file_path: Path to video file

        Returns:
            Dict with compatibility info: {
                'compatible': bool,
                'issues': List[str],
                'needs_remux': bool,  # Just needs container change
                'needs_reencode': bool  # Needs full re-encode
            }
        """
        issues = []
        needs_remux = False
        needs_reencode = False

        try:
            # Get detailed stream info
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
                return {'compatible': False, 'issues': ['Cannot analyze file'], 'needs_remux': False, 'needs_reencode': False}

            data = json.loads(result.stdout)
            format_info = data.get('format', {})

            # Find video stream
            video_stream = None
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    video_stream = stream
                    break

            if not video_stream:
                return {'compatible': False, 'issues': ['No video stream'], 'needs_remux': False, 'needs_reencode': False}

            # Check 1: Container should be MP4
            container = format_info.get('format_name', '').lower()
            if 'mp4' not in container and 'mov' not in container:
                issues.append(f"Container is {container}, should be MP4")
                needs_remux = True

            # Check 2: For HEVC, check codec tag (should be hvc1, not hev1)
            codec_name = video_stream.get('codec_name', '').lower()
            codec_tag = video_stream.get('codec_tag_string', '').lower()

            if codec_name in ['hevc', 'h265']:
                if codec_tag != 'hvc1':
                    issues.append(f"HEVC tag is {codec_tag}, should be hvc1 for QuickLook")
                    needs_reencode = True

            # Check 3: Pixel format should be yuv420p
            pix_fmt = video_stream.get('pix_fmt', '').lower()
            if pix_fmt and pix_fmt != 'yuv420p':
                issues.append(f"Pixel format is {pix_fmt}, should be yuv420p")
                needs_reencode = True

            # Check 4: Faststart flag (check if moov atom is at the beginning)
            # This is harder to check programmatically, but we can infer from format tags
            format_tags = format_info.get('tags', {})
            # Note: ffprobe doesn't directly show faststart, but we can recommend it

            compatible = len(issues) == 0

            return {
                'compatible': compatible,
                'issues': issues,
                'needs_remux': needs_remux and not needs_reencode,  # Only remux if no re-encode needed
                'needs_reencode': needs_reencode
            }

        except Exception as e:
            return {'compatible': False, 'issues': [f"Error: {str(e)}"], 'needs_remux': False, 'needs_reencode': False}

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

        # Check container (mov and mp4 are essentially the same - both MPEG-4 Part 14)
        if video_info.container not in {'mp4', 'mov', 'mkv', 'matroska', 'webm'}:
            return False

        # Video should have valid dimensions
        if video_info.width == 0 or video_info.height == 0:
            return False

        # Check maximum resolution if configured
        if self.max_resolution is not None:
            max_width, max_height = self.max_resolution
            # Video exceeds max resolution if either dimension is larger
            if video_info.width > max_width or video_info.height > max_height:
                return False

        return True

    def find_videos(
        self,
        directory: Path,
        recursive: bool = False,
        file_types: Optional[List[str]] = None
    ) -> List[Path]:
        """
        Find all video files in a directory

        Args:
            directory: Directory to scan
            recursive: Whether to scan recursively
            file_types: Optional list of file extensions to filter (e.g., ['wmv', 'avi', 'mov'])
                       If None, uses all VIDEO_EXTENSIONS

        Returns:
            List of video file paths
        """
        video_files = []

        # Determine which extensions to search for
        if file_types:
            # Normalize extensions (remove dots, convert to lowercase, add dot prefix)
            extensions = {
                f'.{ext.strip().lower().lstrip(".")}'
                for ext in file_types
            }
            # Filter to only valid video extensions
            search_extensions = extensions & self.VIDEO_EXTENSIONS
            if not search_extensions:
                # No valid video extensions provided
                if self.verbose:
                    print(f"Warning: No valid video extensions in file_types: {file_types}")
                return []
        else:
            search_extensions = self.VIDEO_EXTENSIONS

        # Search for files
        if recursive:
            for ext in search_extensions:
                video_files.extend(directory.rglob(f'*{ext}'))
        else:
            for ext in search_extensions:
                video_files.extend(directory.glob(f'*{ext}'))

        return sorted(video_files)
