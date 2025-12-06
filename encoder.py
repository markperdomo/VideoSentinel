"""
Video encoding module for re-encoding videos to modern specifications
"""

import subprocess
import json
import re
import sys
from pathlib import Path
from typing import Optional, Dict
from tqdm import tqdm
from video_analyzer import VideoInfo
from shutdown_manager import shutdown_requested


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

    def __init__(self, verbose: bool = False, recovery_mode: bool = False, downscale_1080p: bool = False):
        self.verbose = verbose
        self.recovery_mode = recovery_mode
        self.downscale_1080p = downscale_1080p

    def _parse_time_to_seconds(self, time_str: str) -> float:
        """
        Parse FFmpeg time string to seconds

        Args:
            time_str: Time string in format "HH:MM:SS.ms"

        Returns:
            Time in seconds as float
        """
        try:
            parts = time_str.split(':')
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
            return hours * 3600 + minutes * 60 + seconds
        except:
            return 0.0

    def _format_eta(self, seconds: float) -> str:
        """
        Format ETA in human-readable format

        Args:
            seconds: Remaining time in seconds

        Returns:
            Formatted string like "2m 30s" or "1h 5m"
        """
        if seconds <= 0:
            return "0s"

        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"

    def _create_progress_bar(self, percentage: float, width: int = 30) -> str:
        """
        Create a visual progress bar

        Args:
            percentage: Progress percentage (0-100)
            width: Width of the progress bar in characters

        Returns:
            Progress bar string like "[████████░░░░░░]"
        """
        filled = int(width * percentage / 100)
        empty = width - filled
        return f"[{'█' * filled}{'░' * empty}]"

    def _parse_ffmpeg_progress(self, line: str) -> Optional[Dict[str, str]]:
        """
        Parse FFmpeg progress output line

        FFmpeg outputs progress in format:
        frame=  123 fps= 45 q=28.0 size=    1024kB time=00:00:05.12 bitrate=1234.5kbits/s speed=1.23x

        Args:
            line: Output line from FFmpeg

        Returns:
            Dictionary with progress info, or None if not a progress line
        """
        # FFmpeg progress lines contain 'frame=' and other metrics
        if 'frame=' not in line:
            return None

        progress = {}

        # Extract frame number
        frame_match = re.search(r'frame=\s*(\d+)', line)
        if frame_match:
            progress['frame'] = frame_match.group(1)

        # Extract fps
        fps_match = re.search(r'fps=\s*([\d.]+)', line)
        if fps_match:
            progress['fps'] = fps_match.group(1)

        # Extract speed
        speed_match = re.search(r'speed=\s*([\d.]+)x', line)
        if speed_match:
            progress['speed'] = speed_match.group(1)

        # Extract time
        time_match = re.search(r'time=(\d+:\d+:[\d.]+)', line)
        if time_match:
            progress['time'] = time_match.group(1)

        # Extract bitrate
        bitrate_match = re.search(r'bitrate=\s*([\d.]+\w+/s)', line)
        if bitrate_match:
            progress['bitrate'] = bitrate_match.group(1)

        return progress if progress else None

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
        video_info: Optional[VideoInfo] = None,
        current_index: Optional[int] = None,
        total_count: Optional[int] = None
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
            current_index: Current video index in batch (1-based, for display)
            total_count: Total number of videos in batch (for display)

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

        # Check for valid existing output (resume support)
        skip_encoding = False
        if output_path.exists():
            existing_size = output_path.stat().st_size
            if self.verbose:
                tqdm.write(f"  Found existing output file ({existing_size / (1024*1024):.1f} MB)")

            # Validate existing file - if it's valid, skip re-encoding
            if self._validate_output(output_path, video_info, lenient=self.recovery_mode):
                if self.verbose:
                    tqdm.write(f"  Existing output is valid, skipping re-encode")
                skip_encoding = True
            else:
                if self.verbose:
                    tqdm.write(f"  Existing output is invalid, removing and re-encoding")
                output_path.unlink()

        # If we're replacing originals, check if replacement was already completed
        if replace_original and not skip_encoding:
            # Calculate what the final path would be
            target_extension = self.EXTENSION_MAP.get(target_codec.lower(), '.mp4')
            final_path = input_path.parent / (input_path.stem + target_extension)

            # If the final path exists and original doesn't, replacement was completed
            if final_path.exists() and final_path != input_path and not input_path.exists():
                if self.verbose:
                    tqdm.write(f"  Replacement already completed, skipping")
                return True

            # If final path exists and is valid, and it's the same as output path,
            # but original still exists, we need to remove the original
            if final_path.exists() and final_path == output_path and input_path.exists() and input_path != final_path:
                if self._validate_output(final_path, video_info, lenient=self.recovery_mode):
                    if self.verbose:
                        tqdm.write(f"  Found valid final output, completing interrupted replacement")
                    input_path.unlink()
                    return True

        # Only encode if we don't have a valid existing output
        if not skip_encoding:
            # Build ffmpeg command
            # Use 'stats' loglevel to get progress info, or 'info' for verbose mode
            loglevel = 'info' if self.verbose else 'error'

            # Base command with global options
            cmd = ['ffmpeg', '-loglevel', loglevel, '-stats']

            # Add INPUT recovery flags if recovery mode is enabled (BEFORE -i)
            if self.recovery_mode:
                # Ignore decoding errors and try to continue
                cmd.extend(['-err_detect', 'ignore_err'])
                # Generate presentation timestamps and discard corrupted packets
                cmd.extend(['-fflags', '+genpts+discardcorrupt+igndts'])
                # Ignore unknown stream types
                cmd.extend(['-ignore_unknown'])

                if self.verbose:
                    tqdm.write("  Recovery mode enabled: using error-tolerant FFmpeg flags")

            # Add input file
            cmd.extend(['-i', str(input_path)])

            # Add OUTPUT recovery flags (AFTER -i)
            if self.recovery_mode:
                # Dynamic memory settings based on file size to balance performance and memory
                # Large files (>10GB): Use conservative settings to avoid OOM on remote servers
                # Small files (<10GB): Use aggressive settings for maximum performance
                file_size_gb = input_path.stat().st_size / (1024**3)
                is_large_file = file_size_gb > 10

                # Set muxing queue size
                max_queue_size = '512' if is_large_file else '1024'
                cmd.extend(['-max_muxing_queue_size', max_queue_size])

                # Set max error rate to 100% (don't fail on errors)
                cmd.extend(['-max_error_rate', '1.0'])

                if self.verbose and is_large_file:
                    tqdm.write(f"  Large file ({file_size_gb:.1f}GB) - using memory-efficient settings (queue:512, threads:4)")

            # Continue with encoding parameters
            cmd.extend([
                '-c:v', ffmpeg_codec,
                '-preset', preset,
                '-crf', str(crf),
                '-c:a', audio_codec,
            ])

            # Dynamic thread limiting for large files in recovery mode
            if self.recovery_mode:
                file_size_gb = input_path.stat().st_size / (1024**3)
                if file_size_gb > 10:
                    cmd.extend(['-threads', '4'])


            # Add audio filter to handle problematic channel layouts
            # This fixes issues like "Unsupported channel layout '6 channels'"
            # Try to map to 5.1, 5.1(side), or fall back to stereo
            if self.recovery_mode:
                cmd.extend(['-af', 'aformat=channel_layouts=5.1|5.1(side)|stereo'])

            # Add final flags
            cmd.extend([
                '-y',  # Overwrite output file if exists
                str(output_path)
            ])

            # Add downscaling filter if requested and video is larger than 1080p
            if self.downscale_1080p and video_info:
                # Check if video is larger than 1080p (either dimension exceeds 1920x1080)
                if video_info.width > 1920 or video_info.height > 1080:
                    # Insert scale filter before output path
                    # Two-stage scaling ensures dimensions are divisible by 2 (required by HEVC/x265):
                    # 1. scale=1920:1080:force_original_aspect_ratio=decrease - fit within box
                    # 2. scale=trunc(iw/2)*2:trunc(ih/2)*2 - round to even dimensions
                    # This prevents "Cannot open libx265 encoder" errors from odd dimensions
                    cmd.insert(-1, '-vf')
                    cmd.insert(-1, 'scale=1920:1080:force_original_aspect_ratio=decrease,scale=trunc(iw/2)*2:trunc(ih/2)*2')

                    if self.verbose:
                        tqdm.write(f"  Downscaling from {video_info.width}x{video_info.height} to fit within 1920x1080 (ensuring even dimensions)")

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
            if not skip_encoding:
                # Display which file we're encoding with position in queue
                if current_index and total_count:
                    tqdm.write(f"[{current_index}/{total_count}] Encoding: {input_path.name}")
                else:
                    tqdm.write(f"Encoding: {input_path.name}")

                if self.verbose:
                    tqdm.write(f"  Output: {output_path.name}")
                    tqdm.write(f"  Command: {' '.join(cmd)}")

                # Run ffmpeg with streaming output to show real-time progress
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    bufsize=1  # Line buffered
                )

                # Track progress
                last_progress = None
                error_output = []

                # Read stderr line by line (FFmpeg writes progress to stderr)
                try:
                    while True:
                        # Check for shutdown signal before reading line
                        if shutdown_requested():
                            tqdm.write("\nShutdown requested, terminating encoding...")
                            process.terminate()
                            # Wait briefly for FFmpeg to exit gracefully
                            try:
                                process.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                process.kill() # Force kill if it doesn't respond
                                process.wait()
                            
                            # Clean up the partial file
                            if output_path.exists():
                                output_path.unlink()
                                tqdm.write(f"  Removed partial file: {output_path.name}")
                            
                            return False # Signal that encoding was stopped

                        line = process.stderr.readline()
                        if not line:
                            break

                        # Store for error reporting
                        error_output.append(line)

                        # Parse progress info
                        progress = self._parse_ffmpeg_progress(line)
                        if progress:
                            last_progress = progress

                            # Only show inline progress in non-verbose mode
                            # In verbose mode, FFmpeg already outputs everything
                            if not self.verbose:
                                # Display progress inline (overwrite same line)
                                speed = progress.get('speed', '?')
                                time_str = progress.get('time', '0:0:0')

                                # Calculate percentage and ETA if we have duration
                                if video_info and video_info.duration > 0:
                                    current_seconds = self._parse_time_to_seconds(time_str)
                                    total_seconds = video_info.duration
                                    percentage = min(100.0, (current_seconds / total_seconds) * 100)

                                    # Calculate ETA if we have speed
                                    eta_str = ""
                                    try:
                                        speed_float = float(speed) if speed != '?' else 0
                                        if speed_float > 0:
                                            remaining_seconds = (total_seconds - current_seconds) / speed_float
                                            eta_str = f" | ETA: {self._format_eta(remaining_seconds)}"
                                    except:
                                        pass

                                    # Create progress bar with percentage
                                    progress_bar = self._create_progress_bar(percentage, width=25)
                                    progress_msg = f"  {progress_bar} {percentage:5.1f}% | {speed}x speed{eta_str}"
                                else:
                                    # Fallback to time-based display if no duration
                                    progress_msg = f"  Encoding: {time_str} | {speed}x speed"

                                # Use ANSI escape sequences for more reliable line overwriting
                                # \r = carriage return, \033[K = clear to end of line
                                # This works more reliably in tmux/screen than just \r
                                print(f"\r\033[K{progress_msg}", end='', flush=True)
                        elif self.verbose and line.strip():
                            # In verbose mode, show ALL ffmpeg output
                            tqdm.write(f"  {line.rstrip()}")

                    # Wait for process to complete
                    process.wait()

                except KeyboardInterrupt:
                    # User pressed Ctrl+C, terminate FFmpeg gracefully
                    tqdm.write("\nUser interrupted, terminating encoding...")
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    
                    # Clean up the partial file
                    if output_path.exists():
                        output_path.unlink()
                        tqdm.write(f"  Removed partial file: {output_path.name}")
                        
                    return False # Treat interruption as a failure for queue management

                # Clear the progress line before printing completion message
                # Only needed if we were showing inline progress (non-verbose mode)
                if last_progress and not self.verbose:
                    # Clear the line by printing spaces, then move to start of line
                    print("\r" + " " * 100 + "\r", end='', flush=True)

                # Check return code
                if process.returncode != 0:
                    if current_index and total_count:
                        tqdm.write(f"✗ [{current_index}/{total_count}] Error encoding {input_path.name}")
                    else:
                        tqdm.write(f"Error encoding {input_path.name}")
                    # Show last few error lines
                    for line in error_output[-10:]:
                        if line.strip():
                            tqdm.write(f"  {line.rstrip()}")
                    return False

                # Validate output before considering it successful
                if not self._validate_output(output_path, video_info, lenient=self.recovery_mode):
                    if current_index and total_count:
                        tqdm.write(f"✗ [{current_index}/{total_count}] Output validation failed for {input_path.name}")
                    else:
                        tqdm.write(f"Error: Output validation failed for {output_path.name}")
                    # Remove invalid output file
                    if output_path.exists():
                        output_path.unlink()
                    return False

                # Show final encoding stats
                if last_progress:
                    fps = last_progress.get('fps', '?')
                    speed = last_progress.get('speed', '?')
                    if current_index and total_count:
                        tqdm.write(f"✓ [{current_index}/{total_count}] Completed: {input_path.name} (avg {fps} fps, {speed}x speed)")
                    else:
                        tqdm.write(f"✓ Completed: {input_path.name} (avg {fps} fps, {speed}x speed)")
                elif self.verbose:
                    tqdm.write(f"Successfully encoded and validated: {output_path}")
            else:
                # Skipped encoding, but show we're resuming
                if current_index and total_count:
                    tqdm.write(f"[{current_index}/{total_count}] Resuming: {input_path.name} (already encoded)")
                else:
                    tqdm.write(f"Resuming: {input_path.name} (already encoded)")

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
        duration_tolerance: float = 2.0,
        lenient: bool = False
    ) -> bool:
        """
        Validate that the encoded output file is valid and playable

        Args:
            output_path: Path to the encoded output file
            source_info: Optional VideoInfo of source for comparison
            duration_tolerance: Allowed duration difference in seconds
            lenient: If True, use lenient validation for recovery mode (allows duration mismatches)

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
                    if lenient:
                        # In recovery mode, allow files with no duration metadata
                        if self.verbose:
                            tqdm.write(f"  Validation passed (lenient): {width}x{height}, no duration metadata (recovered file)")
                    else:
                        if self.verbose:
                            tqdm.write(f"  Validation failed: Output has no duration")
                        return False
                else:
                    duration_diff = abs(output_duration - source_info.duration)
                    if duration_diff > duration_tolerance:
                        if lenient:
                            # In recovery mode, allow significant duration differences
                            # Just warn but don't fail - corrupted source may have wrong duration metadata
                            if self.verbose:
                                tqdm.write(f"  Validation passed (lenient): {width}x{height}, {output_duration:.1f}s (source was {source_info.duration:.1f}s, recovered file may differ)")
                        else:
                            if self.verbose:
                                tqdm.write(f"  Validation failed: Duration mismatch ({output_duration:.1f}s vs {source_info.duration:.1f}s)")
                            return False
                    else:
                        if self.verbose:
                            tqdm.write(f"  Validation passed: {width}x{height}, {output_duration:.1f}s")
            else:
                # No source info to compare against
                if self.verbose:
                    tqdm.write(f"  Validation passed: {width}x{height} (no source comparison)")

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
        total = len(video_paths)

        for idx, video_path in enumerate(video_paths, start=1):
            # Check for graceful shutdown request
            if shutdown_requested():
                print("="*60)
                print("SHUTDOWN REQUESTED - Stopping after current video")
                print("="*60)
                print(f"Processed {idx - 1}/{total} videos before shutdown")
                break

            output_path = self.get_output_path(video_path, output_dir, target_codec=target_codec)

            # Get video info for this video if available
            video_info = video_infos.get(video_path) if video_infos else None

            success = self.re_encode_video(
                video_path,
                output_path,
                target_codec=target_codec,
                video_info=video_info,
                current_index=idx,
                total_count=total,
                **kwargs
            )

            results[video_path] = success

            # Don't duplicate the success message (already shown in re_encode_video)
            if not success:
                tqdm.write(f"✗ [{idx}/{total}] Failed: {video_path.name}")

        # Print summary
        successful = sum(1 for v in results.values() if v)
        print()
        print("="*60)
        print(f"Re-encoding complete: {successful}/{len(video_paths)} successful")
        print("="*60)

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

    def find_existing_output(
        self,
        input_path: Path,
        target_codec: str = 'hevc',
        check_suffixes: list[str] = None
    ) -> Optional[Path]:
        """
        Check if a valid re-encoded output already exists for the input file

        Checks for files with suffixes like _reencoded or _quicklook

        Args:
            input_path: Path to the source video file
            target_codec: Target codec (determines expected extension)
            check_suffixes: List of suffixes to check (default: ['_reencoded', '_quicklook'])

        Returns:
            Path to existing valid output, or None if no valid output exists
        """
        if check_suffixes is None:
            check_suffixes = ['_reencoded', '_quicklook']

        # Get expected output extension
        target_extension = self.EXTENSION_MAP.get(target_codec.lower(), '.mp4')

        # Check for each suffix
        for suffix in check_suffixes:
            # Build potential output path
            potential_output = input_path.parent / (input_path.stem + suffix + target_extension)

            if potential_output.exists():
                # Validate the existing output
                if self._validate_output(potential_output, source_info=None, lenient=self.recovery_mode):
                    if self.verbose:
                        tqdm.write(f"  Found valid existing output: {potential_output.name}")
                    return potential_output
                else:
                    # Invalid output found - remove it
                    if self.verbose:
                        tqdm.write(f"  Found invalid output, removing: {potential_output.name}")
                    potential_output.unlink()

        return None

    def remux_to_mp4(
        self,
        input_path: Path,
        output_path: Path,
        fix_hevc_tag: bool = True
    ) -> bool:
        """
        Remux video to MP4 container without re-encoding (fast!)

        This is useful for:
        - Converting MKV to MP4 for QuickLook compatibility
        - Fixing HEVC tag from hev1 to hvc1 for Apple devices
        - Adding faststart flag for instant preview

        Args:
            input_path: Path to input video file
            output_path: Path for output MP4 file
            fix_hevc_tag: If True, converts HEVC hev1 tag to hvc1 for QuickLook

        Returns:
            True if remux successful, False otherwise
        """
        if not input_path.exists():
            print(f"Error: Input file does not exist: {input_path}")
            return False

        try:
            # Build ffmpeg command for remuxing (no re-encoding)
            cmd = [
                'ffmpeg',
                '-i', str(input_path),
                '-c', 'copy',  # Copy streams without re-encoding
                '-movflags', 'faststart',  # Move moov atom to beginning for fast preview
                '-y',  # Overwrite output file if exists
            ]

            # For HEVC videos, fix the tag for Apple compatibility
            if fix_hevc_tag:
                cmd.extend(['-tag:v', 'hvc1'])

            cmd.append(str(output_path))

            if self.verbose:
                tqdm.write(f"Remuxing: {input_path.name} -> {output_path.name}")

            # Run ffmpeg
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode != 0:
                if self.verbose:
                    tqdm.write(f"Remux failed for {input_path.name}: {result.stderr}")
                return False

            # Validate output
            if not output_path.exists() or output_path.stat().st_size < 1024:
                if self.verbose:
                    tqdm.write(f"Remux output validation failed for {input_path.name}")
                if output_path.exists():
                    output_path.unlink()
                return False

            if self.verbose:
                tqdm.write(f"✓ Remuxed: {input_path.name}")

            return True

        except subprocess.TimeoutExpired:
            print(f"Error: Remux timeout for {input_path.name}")
            return False
        except Exception as e:
            print(f"Error remuxing {input_path.name}: {e}")
            return False
