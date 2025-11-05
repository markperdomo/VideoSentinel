"""
Video encoding module for re-encoding videos to modern specifications
"""

import subprocess
import json
from pathlib import Path
from typing import Optional, Dict
from tqdm import tqdm
from video_analyzer import VideoInfo


class VideoEncoder:
    """Handles video re-encoding operations"""

    # Codec mappings
    CODEC_MAP = {
        'h264': 'libx264',
        'hevc': 'libx265',
        'av1': 'libaom-av1'
    }

    # Extension mappings for output files
    EXTENSION_MAP = {
        'h264': '.mp4',
        'hevc': '.mp4',
        'av1': '.mp4'
    }

    # Preset mappings for encoding speed vs quality
    PRESETS = {
        'fast': 'fast',
        'medium': 'medium',
        'slow': 'slow',
        'veryslow': 'veryslow'
    }

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def calculate_optimal_crf(self, video_info: VideoInfo, target_codec: str = 'hevc') -> int:
        """
        Calculate optimal CRF value based on source video quality

        Analyzes source bitrate and resolution to preserve similar visual quality
        while potentially reducing file size with modern codecs.

        Args:
            video_info: VideoInfo object for the source video
            target_codec: Target codec (affects CRF calculation)

        Returns:
            Optimal CRF value (0-51, lower is better quality)
        """
        if not video_info or not video_info.is_valid:
            # Fallback to safe default
            return 23

        # Calculate bitrate per pixel (quality indicator)
        pixels = video_info.width * video_info.height
        if pixels == 0 or video_info.duration == 0:
            return 23

        # Bitrate in bits per second
        bitrate = video_info.bitrate
        if bitrate == 0:
            # If bitrate unknown, estimate from file size
            if video_info.file_size > 0 and video_info.duration > 0:
                bitrate = int((video_info.file_size * 8) / video_info.duration)
            else:
                return 23

        # Calculate bits per pixel per frame
        fps = video_info.fps if video_info.fps > 0 else 30
        bpp = bitrate / (pixels * fps)

        # Determine quality tier based on bits per pixel
        # High bpp = high quality source, needs lower CRF to preserve
        # Low bpp = low quality source, can use higher CRF

        if target_codec.lower() in ['hevc', 'h265']:
            # HEVC/H.265 CRF mapping
            if bpp > 0.25:  # Very high quality (e.g., 4K Bluray, high-bitrate 1080p)
                crf = 18
            elif bpp > 0.15:  # High quality (e.g., good 1080p, decent 4K)
                crf = 20
            elif bpp > 0.10:  # Medium-high quality
                crf = 22
            elif bpp > 0.07:  # Medium quality
                crf = 23
            elif bpp > 0.05:  # Medium-low quality
                crf = 25
            else:  # Low quality source
                crf = 28
        elif target_codec.lower() == 'av1':
            # AV1 has better compression, can use slightly higher CRF
            if bpp > 0.25:
                crf = 20
            elif bpp > 0.15:
                crf = 24
            elif bpp > 0.10:
                crf = 28
            elif bpp > 0.07:
                crf = 30
            else:
                crf = 32
        else:  # H.264
            # H.264 needs lower CRF for same quality as HEVC
            if bpp > 0.25:
                crf = 16
            elif bpp > 0.15:
                crf = 18
            elif bpp > 0.10:
                crf = 20
            elif bpp > 0.07:
                crf = 21
            elif bpp > 0.05:
                crf = 23
            else:
                crf = 26

        if self.verbose:
            tqdm.write(f"  Quality analysis: {bpp:.4f} bpp → CRF {crf}")
            tqdm.write(f"  Source: {bitrate/1000:.0f} kbps, {video_info.width}x{video_info.height}, {fps:.1f} fps")

        return crf

    def re_encode_video(
        self,
        input_path: Path,
        output_path: Path,
        target_codec: str = 'hevc',
        preset: str = 'medium',
        crf: Optional[int] = None,
        audio_codec: str = 'aac',
        keep_original: bool = True,
        replace_original: bool = False,
        video_info: Optional[VideoInfo] = None
    ) -> bool:
        """
        Re-encode a video file with smart quality matching

        Args:
            input_path: Path to input video file
            output_path: Path for output video file
            target_codec: Target codec (h264, hevc, av1)
            preset: Encoding preset (fast, medium, slow, veryslow)
            crf: Constant Rate Factor for quality (0-51, lower is better quality).
                 If None, automatically calculated based on source quality.
            audio_codec: Audio codec to use
            keep_original: Whether to keep the original file (deprecated, use replace_original)
            replace_original: If True, deletes source and renames output to match source filename
            video_info: VideoInfo object for smart quality matching (optional)

        Returns:
            True if encoding successful, False otherwise
        """
        if not input_path.exists():
            print(f"Error: Input file does not exist: {input_path}")
            return False

        # Get ffmpeg codec name
        ffmpeg_codec = self.CODEC_MAP.get(target_codec.lower())
        if not ffmpeg_codec:
            print(f"Error: Unknown codec: {target_codec}")
            return False

        # Calculate optimal CRF if not specified
        if crf is None:
            if video_info is not None:
                crf = self.calculate_optimal_crf(video_info, target_codec)
                if self.verbose:
                    tqdm.write(f"  Using smart quality matching: CRF {crf}")
            else:
                crf = 23  # Default fallback
                if self.verbose:
                    tqdm.write(f"  Using default CRF: {crf}")

        # Create output directory if it doesn't exist
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Clean up any existing output file (from previous failed/interrupted encodes)
        if output_path.exists():
            existing_size = output_path.stat().st_size
            if self.verbose:
                tqdm.write(f"  Found existing output file ({existing_size / (1024*1024):.1f} MB), will overwrite")

            # Optionally validate existing file - if it's valid, skip re-encoding
            if self._validate_output(output_path, video_info):
                if self.verbose:
                    tqdm.write(f"  Existing output is valid, skipping re-encode")
                return True
            else:
                if self.verbose:
                    tqdm.write(f"  Existing output is invalid, removing and re-encoding")
                output_path.unlink()

        # Build ffmpeg command
        cmd = [
            'ffmpeg',
            '-loglevel', 'error' if not self.verbose else 'info',
            '-i', str(input_path),
            '-c:v', ffmpeg_codec,
            '-preset', preset,
            '-crf', str(crf),
            '-c:a', audio_codec,
            '-y',  # Overwrite output file if exists
            str(output_path)
        ]

        # Add codec-specific parameters
        if target_codec.lower() == 'hevc':
            # Add macOS QuickLook compatibility
            # Use hvc1 tag instead of hev1 for Apple device compatibility
            cmd.insert(-1, '-tag:v')
            cmd.insert(-1, 'hvc1')
            # Ensure yuv420p pixel format for maximum compatibility
            cmd.insert(-1, '-pix_fmt')
            cmd.insert(-1, 'yuv420p')
            # Add movflags for better QuickLook compatibility
            cmd.insert(-1, '-movflags')
            cmd.insert(-1, 'faststart')
            # Add x265-params for better HEVC encoding
            cmd.insert(-1, '-x265-params')
            cmd.insert(-1, 'log-level=error')
        elif target_codec.lower() == 'h264':
            # Add H.264-specific parameters for maximum compatibility
            cmd.insert(-1, '-pix_fmt')
            cmd.insert(-1, 'yuv420p')
            # Add movflags for better QuickLook compatibility
            cmd.insert(-1, '-movflags')
            cmd.insert(-1, 'faststart')
        elif target_codec.lower() == 'av1':
            # Add AV1-specific parameters
            cmd.insert(-1, '-cpu-used')
            cmd.insert(-1, '4')  # Balance between speed and quality
            # Add movflags for better QuickLook compatibility
            cmd.insert(-1, '-movflags')
            cmd.insert(-1, 'faststart')

        try:
            if self.verbose:
                print(f"Encoding: {input_path.name} -> {output_path.name}")
                print(f"Command: {' '.join(cmd)}")

            # Run ffmpeg
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=None  # No timeout for encoding (can take a while)
            )

            if result.returncode != 0:
                if result.stderr:
                    tqdm.write(f"Error encoding {input_path.name}: {result.stderr.strip()}")
                return False

            # Validate output before considering it successful
            if not self._validate_output(output_path, video_info):
                tqdm.write(f"Error: Output validation failed for {output_path.name}")
                # Remove invalid output file
                if output_path.exists():
                    output_path.unlink()
                return False

            if self.verbose:
                tqdm.write(f"Successfully encoded and validated: {output_path}")

            # Handle file replacement logic (only after successful validation)
            if replace_original:
                # Get the proper extension for the target codec
                target_extension = self.EXTENSION_MAP.get(target_codec.lower(), '.mp4')

                # Create final path with original filename but proper extension
                final_path = input_path.parent / (input_path.stem + target_extension)

                # If final path is different from output path, we need to rename
                # (This handles cases where source was .avi and target is .mp4, etc.)
                if final_path != output_path:
                    # If a file already exists at final_path, delete it first
                    # (This handles the case where source was already .mp4)
                    if final_path.exists():
                        if self.verbose:
                            tqdm.write(f"Removing original: {final_path}")
                        final_path.unlink()

                    # Rename output to final path
                    if self.verbose:
                        tqdm.write(f"Renaming {output_path.name} -> {final_path.name}")
                    output_path.rename(final_path)
                else:
                    # Output path already matches desired final path
                    # Just need to delete the original if it's different
                    if input_path.exists() and input_path != final_path:
                        if self.verbose:
                            tqdm.write(f"Removing original: {input_path}")
                        input_path.unlink()
            elif not keep_original:
                # Legacy behavior: just remove original without renaming
                if self.verbose:
                    tqdm.write(f"Removing original: {input_path}")
                input_path.unlink()

            return True

        except subprocess.TimeoutExpired:
            print(f"Error: Encoding timeout for {input_path.name}")
            return False
        except Exception as e:
            print(f"Error encoding {input_path.name}: {e}")
            return False

    def _validate_output(
        self,
        output_path: Path,
        source_info: Optional[VideoInfo] = None,
        duration_tolerance: float = 2.0
    ) -> bool:
        """
        Validate that the encoded output file is valid and playable

        Args:
            output_path: Path to the encoded output file
            source_info: Optional VideoInfo of source for comparison
            duration_tolerance: Allowed duration difference in seconds

        Returns:
            True if output is valid, False otherwise
        """
        try:
            # Check 1: File exists and has size
            if not output_path.exists():
                if self.verbose:
                    tqdm.write(f"  Validation failed: Output file does not exist")
                return False

            file_size = output_path.stat().st_size
            if file_size < 1024:  # Less than 1KB is definitely wrong
                if self.verbose:
                    tqdm.write(f"  Validation failed: Output file too small ({file_size} bytes)")
                return False

            # Check 2: Can be read by ffprobe
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                str(output_path)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                if self.verbose:
                    tqdm.write(f"  Validation failed: ffprobe cannot read output")
                return False

            data = json.loads(result.stdout)

            # Check 3: Has video stream
            video_stream = None
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    video_stream = stream
                    break

            if not video_stream:
                if self.verbose:
                    tqdm.write(f"  Validation failed: No video stream in output")
                return False

            # Check 4: Has valid dimensions
            width = int(video_stream.get('width', 0))
            height = int(video_stream.get('height', 0))

            if width == 0 or height == 0:
                if self.verbose:
                    tqdm.write(f"  Validation failed: Invalid dimensions ({width}x{height})")
                return False

            # Check 5: Compare duration with source (if available)
            if source_info and source_info.duration > 0:
                format_info = data.get('format', {})
                output_duration = float(format_info.get('duration', 0))

                if output_duration == 0:
                    if self.verbose:
                        tqdm.write(f"  Validation failed: Output has no duration")
                    return False

                duration_diff = abs(output_duration - source_info.duration)
                if duration_diff > duration_tolerance:
                    if self.verbose:
                        tqdm.write(f"  Validation failed: Duration mismatch ({output_duration:.1f}s vs {source_info.duration:.1f}s)")
                    return False

                if self.verbose:
                    tqdm.write(f"  Validation passed: {width}x{height}, {output_duration:.1f}s")

            return True

        except subprocess.TimeoutExpired:
            if self.verbose:
                tqdm.write(f"  Validation failed: ffprobe timeout")
            return False
        except Exception as e:
            if self.verbose:
                tqdm.write(f"  Validation failed: {str(e)}")
            return False

    def get_output_path(
        self,
        input_path: Path,
        output_dir: Optional[Path] = None,
        suffix: str = '_reencoded',
        target_codec: str = 'hevc'
    ) -> Path:
        """
        Generate output path for re-encoded video

        Args:
            input_path: Original video path
            output_dir: Output directory (if None, uses same directory as input)
            suffix: Suffix to add to filename
            target_codec: Target codec (determines output extension)

        Returns:
            Output path for re-encoded video (always .mp4 for modern codecs)
        """
        # Always use .mp4 extension for modern codecs
        extension = self.EXTENSION_MAP.get(target_codec.lower(), '.mp4')

        if output_dir:
            # Use specified output directory
            filename = input_path.stem + suffix + extension
            return output_dir / filename
        else:
            # Use same directory as input
            filename = input_path.stem + suffix + extension
            return input_path.parent / filename

    def batch_re_encode(
        self,
        video_paths: list[Path],
        output_dir: Optional[Path] = None,
        target_codec: str = 'hevc',
        video_infos: Optional[Dict[Path, VideoInfo]] = None,
        **kwargs
    ) -> Dict[Path, bool]:
        """
        Re-encode multiple videos with smart quality matching

        Args:
            video_paths: List of video paths to re-encode
            output_dir: Output directory for re-encoded videos
            target_codec: Target codec
            video_infos: Optional dict mapping video paths to VideoInfo objects
                        for smart quality matching
            **kwargs: Additional arguments for re_encode_video

        Returns:
            Dictionary mapping input paths to success status
        """
        results = {}

        for video_path in tqdm(video_paths, desc="Re-encoding videos", unit="video"):
            output_path = self.get_output_path(video_path, output_dir, target_codec=target_codec)

            # Get video info for this video if available
            video_info = video_infos.get(video_path) if video_infos else None

            success = self.re_encode_video(
                video_path,
                output_path,
                target_codec=target_codec,
                video_info=video_info,
                **kwargs
            )

            results[video_path] = success

            if success:
                tqdm.write(f"✓ {video_path.name}")
            else:
                tqdm.write(f"✗ {video_path.name} - Failed")

        # Print summary
        successful = sum(1 for v in results.values() if v)
        print(f"\n{'='*60}")
        print(f"Re-encoding complete: {successful}/{len(video_paths)} successful")
        print(f"{'='*60}")

        return results

    def check_ffmpeg_available(self) -> bool:
        """
        Check if ffmpeg is available on the system

        Returns:
            True if ffmpeg is available, False otherwise
        """
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def get_estimated_size(
        self,
        video_info: VideoInfo,
        target_codec: str = 'hevc',
        crf: int = 23
    ) -> int:
        """
        Estimate output file size after re-encoding

        Args:
            video_info: VideoInfo object for the input video
            target_codec: Target codec
            crf: Constant Rate Factor

        Returns:
            Estimated file size in bytes (rough estimate)
        """
        # This is a rough estimation based on typical compression ratios
        compression_ratios = {
            'h264': 0.7,  # 30% reduction from original
            'hevc': 0.5,  # 50% reduction (better compression)
            'av1': 0.4    # 60% reduction (best compression)
        }

        ratio = compression_ratios.get(target_codec.lower(), 0.7)

        # Adjust for CRF (lower CRF = higher bitrate = larger file)
        crf_factor = 1.0 + (23 - crf) * 0.05

        estimated_size = int(video_info.file_size * ratio * crf_factor)

        return estimated_size
