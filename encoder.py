"""
Video encoding module for re-encoding videos to modern specifications
"""

import subprocess
import json
import re
import sys
from pathlib import Path
from typing import Optional, Dict
from video_analyzer import VideoInfo
from shutdown_manager import shutdown_requested
from ui import console, section_header, create_encoding_progress


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
            console.print(f"  Quality analysis: {bpp:.4f} bpp \u2192 CRF {crf}", style="dim")
            console.print(f"  Source: {bitrate/1000:.0f} kbps, {video_info.width}x{video_info.height}, {fps:.1f} fps", style="dim")

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
        total_count: Optional[int] = None,
        progress=None,
        file_task=None
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
            progress: Optional Rich Progress instance from caller (avoids creating per-file progress)
            file_task: Optional task ID within progress to update for this file's encoding

        Returns:
            True if encoding successful, False otherwise
        """
        if not input_path.exists():
            console.print(f"[error]Error: Input file does not exist: {input_path}[/error]")
            return False

        # Get ffmpeg codec name
        ffmpeg_codec = self.CODEC_MAP.get(target_codec.lower())
        if not ffmpeg_codec:
            console.print(f"[error]Error: Unknown codec: {target_codec}[/error]")
            return False

        # Calculate optimal CRF if not specified
        if crf is None:
            if video_info is not None:
                crf = self.calculate_optimal_crf(video_info, target_codec)
                if self.verbose:
                    console.print(f"  Using smart quality matching: CRF {crf}", style="dim")
            else:
                crf = 23  # Default fallback
                if self.verbose:
                    console.print(f"  Using default CRF: {crf}", style="dim")

        # Create output directory if it doesn't exist
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Check for valid existing output (resume support)
        skip_encoding = False
        if output_path.exists():
            existing_size = output_path.stat().st_size
            if self.verbose:
                console.print(f"  Found existing output file ({existing_size / (1024*1024):.1f} MB)", style="dim")

            # Validate existing file - if it's valid, skip re-encoding
            if self._validate_output(output_path, video_info, lenient=self.recovery_mode):
                if self.verbose:
                    console.print(f"  Existing output is valid, skipping re-encode", style="dim")
                skip_encoding = True
            else:
                if self.verbose:
                    console.print(f"  Existing output is invalid, removing and re-encoding", style="dim")
                output_path.unlink()

        # If we're replacing originals, check if replacement was already completed
        if replace_original and not skip_encoding:
            # Calculate what the final path would be
            target_extension = self.EXTENSION_MAP.get(target_codec.lower(), '.mp4')
            final_path = input_path.parent / (input_path.stem + target_extension)

            # If the final path exists and original doesn't, replacement was completed
            if final_path.exists() and final_path != input_path and not input_path.exists():
                if self.verbose:
                    console.print(f"  Replacement already completed, skipping", style="dim")
                return True

            # If final path exists and is valid, and it's the same as output path,
            # but original still exists, we need to remove the original
            if final_path.exists() and final_path == output_path and input_path.exists() and input_path != final_path:
                if self._validate_output(final_path, video_info, lenient=self.recovery_mode):
                    if self.verbose:
                        console.print(f"  Found valid final output, completing interrupted replacement", style="dim")
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
                    console.print("  Recovery mode enabled: using error-tolerant FFmpeg flags", style="dim")

            # Add input file
            cmd.extend(['-i', str(input_path)])

            # Compute file size once for memory-safe decisions
            file_size_gb = input_path.stat().st_size / (1024**3)
            is_large_file = file_size_gb > 4  # >4GB triggers memory-safe settings

            # Add OUTPUT recovery flags (AFTER -i)
            if self.recovery_mode:
                # Set muxing queue size (conservative for large files)
                max_queue_size = '512' if is_large_file else '1024'
                cmd.extend(['-max_muxing_queue_size', max_queue_size])

                # Set max error rate to 100% (don't fail on errors)
                cmd.extend(['-max_error_rate', '1.0'])

                if self.verbose and is_large_file:
                    console.print(f"  Large file ({file_size_gb:.1f}GB) - using memory-efficient settings (queue:512, threads:4)", style="dim")

            # Memory-safe muxing queue for large files in normal mode
            if not self.recovery_mode and is_large_file:
                cmd.extend(['-max_muxing_queue_size', '512'])
                if self.verbose:
                    console.print(f"  Large file ({file_size_gb:.1f}GB) - using memory-safe muxing queue", style="dim")

            # Continue with encoding parameters
            cmd.extend([
                '-c:v', ffmpeg_codec,
                '-preset', preset,
                '-crf', str(crf),
                '-c:a', audio_codec,
            ])

            # Dynamic thread limiting for large files in recovery mode
            if self.recovery_mode and is_large_file:
                cmd.extend(['-threads', '4'])


            # Add audio filter to handle problematic channel layouts
            # This fixes issues like "Unsupported channel layout '6 channels'"
            # Try to map to 5.1, 5.1(side), or fall back to stereo
            if self.recovery_mode:
                cmd.extend(['-af', 'aformat=channel_layouts=5.1|5.1(side)|stereo'])

            # Build the video filter chain
            vf_filters = []
            if self.downscale_1080p and video_info:
                if video_info.width > 1920 or video_info.height > 1080:
                    vf_filters.append('scale=1920:1080:force_original_aspect_ratio=decrease')
                    if self.verbose:
                        console.print(f"  Downscaling from {video_info.width}x{video_info.height} to fit within 1920x1080", style="dim")

            # For HEVC, ensure dimensions are divisible by 2 to avoid encoder errors
            if target_codec.lower() == 'hevc':
                vf_filters.append('scale=trunc(iw/2)*2:trunc(ih/2)*2')
                if self.verbose:
                    console.print("  Ensuring even dimensions for HEVC encoding", style="dim")

            # If any filters are defined, add them to the command
            if vf_filters:
                cmd.extend(['-vf', ",".join(vf_filters)])

            # Add codec-specific parameters
            if target_codec.lower() == 'hevc':
                # Add macOS QuickLook compatibility
                # Use hvc1 tag instead of hev1 for Apple device compatibility
                cmd.extend(['-tag:v', 'hvc1'])
                # Ensure yuv420p pixel format for maximum compatibility
                cmd.extend(['-pix_fmt', 'yuv420p'])
                # Add movflags for better QuickLook compatibility
                cmd.extend(['-movflags', 'faststart'])
                # Build x265 params
                x265_params = ['log-level=error']
                if is_large_file:
                    # Memory-safe settings: limit thread pools and lookahead buffers
                    # to prevent OOM on large high-res files
                    x265_params.extend([
                        'pools=4',
                        'frame-threads=2',
                        'lookahead-depth=10',
                    ])
                cmd.extend(['-x265-params', ':'.join(x265_params)])
            elif target_codec.lower() == 'h264':
                # Add H.264-specific parameters for maximum compatibility
                cmd.extend(['-pix_fmt', 'yuv420p'])
                # Add movflags for better QuickLook compatibility
                cmd.extend(['-movflags', 'faststart'])
            elif target_codec.lower() == 'av1':
                # Add AV1-specific parameters
                cmd.extend(['-cpu-used', '4'])  # Balance between speed and quality
                # Add movflags for better QuickLook compatibility
                cmd.extend(['-movflags', 'faststart'])

            # Add final flags
            cmd.extend([
                '-y',  # Overwrite output file if exists
                str(output_path)
            ])

        # Determine whether to use caller's progress or create our own
        use_external_progress = progress is not None and file_task is not None

        try:
            if not skip_encoding:
                if self.verbose:
                    if current_index and total_count:
                        console.print(f"[bold]\\[{current_index}/{total_count}][/bold] Encoding: [filename]{input_path.name}[/filename]")
                    console.print(f"  Output: {output_path.name}", style="dim")
                    console.print(f"  Command: {' '.join(cmd)}", style="dim")

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

                # Determine total duration for progress calculation
                total_seconds = video_info.duration if video_info and video_info.duration > 0 else 0

                # Read stderr line by line with Rich progress display
                try:
                    if use_external_progress:
                        # Use the caller's Progress instance (batch mode)
                        rich_progress = progress
                        task = file_task
                        # Reset the file task for this file
                        if total_seconds > 0:
                            rich_progress.update(task, description=f"  {input_path.name}", completed=0, total=1000, speed="", eta="")
                        else:
                            rich_progress.update(task, description=f"  {input_path.name}", completed=0, total=None, speed="", eta="")
                    else:
                        # Standalone mode - create our own Progress context
                        rich_progress = create_encoding_progress()
                        rich_progress.start()
                        if total_seconds > 0:
                            task = rich_progress.add_task(f"  {input_path.name}", total=1000, speed="", eta="")
                        else:
                            task = rich_progress.add_task(f"  {input_path.name}", total=None, speed="", eta="")

                    while True:
                        # Check for shutdown signal before reading line
                        if shutdown_requested():
                            if not use_external_progress:
                                rich_progress.stop()
                                console.print("[warning]Shutdown requested, terminating encoding...[/warning]")
                            process.terminate()
                            try:
                                process.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait()

                            if output_path.exists():
                                output_path.unlink()

                            return False

                        line = process.stderr.readline()
                        if not line:
                            break

                        error_output.append(line)

                        ffmpeg_progress = self._parse_ffmpeg_progress(line)
                        if ffmpeg_progress:
                            last_progress = ffmpeg_progress

                            if not self.verbose:
                                speed = ffmpeg_progress.get('speed', '?')
                                time_str = ffmpeg_progress.get('time', '0:0:0')
                                speed_display = f"{speed}x" if speed != '?' else ""

                                if total_seconds > 0:
                                    current_seconds = self._parse_time_to_seconds(time_str)
                                    percentage = min(100.0, (current_seconds / total_seconds) * 100)

                                    eta_display = ""
                                    try:
                                        speed_float = float(speed) if speed != '?' else 0
                                        if speed_float > 0:
                                            remaining = (total_seconds - current_seconds) / speed_float
                                            mins, secs = divmod(int(remaining), 60)
                                            hours, mins = divmod(mins, 60)
                                            if hours > 0:
                                                eta_display = f"ETA: {hours}h {mins}m"
                                            elif mins > 0:
                                                eta_display = f"ETA: {mins}m {secs}s"
                                            else:
                                                eta_display = f"ETA: {secs}s"
                                    except (ValueError, ZeroDivisionError):
                                        pass

                                    rich_progress.update(task, completed=int(percentage * 10), speed=speed_display, eta=eta_display)
                                else:
                                    rich_progress.update(task, speed=speed_display, eta=time_str)
                        elif self.verbose and line.strip():
                            console.print(f"  {line.rstrip()}", style="dim")

                    process.wait()

                    if not use_external_progress:
                        rich_progress.stop()

                except KeyboardInterrupt:
                    if not use_external_progress:
                        rich_progress.stop()
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()

                    if output_path.exists():
                        output_path.unlink()

                    # Re-raise so callers (batch_re_encode, main) can handle it
                    raise

                # Check return code
                if process.returncode != 0:
                    if not use_external_progress:
                        console.print(f"[error]\u2717 Error encoding {input_path.name}[/error]")
                        for line in error_output[-10:]:
                            if line.strip():
                                console.print(f"  {line.rstrip()}", style="dim")
                    return False

                # Validate output before considering it successful
                if not self._validate_output(output_path, video_info, lenient=self.recovery_mode):
                    if not use_external_progress:
                        console.print(f"[error]\u2717 Output validation failed for {input_path.name}[/error]")
                    if output_path.exists():
                        output_path.unlink()
                    return False

                # Show final encoding stats (only in standalone mode)
                if not use_external_progress and last_progress:
                    fps = last_progress.get('fps', '?')
                    speed = last_progress.get('speed', '?')
                    console.print(f"[success]\u2713 Completed: {input_path.name}[/success] [dim](avg {fps} fps, {speed}x speed)[/dim]")
            else:
                # Skipped encoding (valid output already exists)
                if not use_external_progress:
                    console.print(f"Resuming: [filename]{input_path.name}[/filename] [dim](already encoded)[/dim]")

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
                            console.print(f"Removing existing file at target: {final_path}", style="dim")
                        final_path.unlink()

                    # Rename output to final path
                    if self.verbose:
                        console.print(f"Renaming {output_path.name} -> {final_path.name}", style="dim")
                    output_path.rename(final_path)

                # Delete original input file if it's different from the final path
                # (This handles e.g. .avi -> .mp4, where we need to delete the .avi)
                # Note: If input_path == final_path (e.g. .mp4 -> .mp4), it was already
                # deleted in the block above when we cleared the destination.
                if input_path.exists() and input_path != final_path:
                    if self.verbose:
                        console.print(f"Removing original source: {input_path}", style="dim")
                    input_path.unlink()
            elif not keep_original:
                # Legacy behavior: just remove original without renaming
                if self.verbose:
                    console.print(f"Removing original: {input_path}", style="dim")
                input_path.unlink()

            return True

        except subprocess.TimeoutExpired:
            console.print(f"[error]Error: Encoding timeout for {input_path.name}[/error]")
            return False
        except Exception as e:
            console.print(f"[error]Error encoding {input_path.name}: {e}[/error]")
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
                    console.print(f"  Validation failed: Output file does not exist", style="dim")
                return False

            file_size = output_path.stat().st_size
            if file_size < 1024:  # Less than 1KB is definitely wrong
                if self.verbose:
                    console.print(f"  Validation failed: Output file too small ({file_size} bytes)", style="dim")
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
                    console.print(f"  Validation failed: ffprobe cannot read output", style="dim")
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
                    console.print(f"  Validation failed: No video stream in output", style="dim")
                return False

            # Check 4: Has valid dimensions
            width = int(video_stream.get('width', 0))
            height = int(video_stream.get('height', 0))

            if width == 0 or height == 0:
                if self.verbose:
                    console.print(f"  Validation failed: Invalid dimensions ({width}x{height})", style="dim")
                return False

            # Check 5: Compare duration with source (if available)
            if source_info and source_info.duration > 0:
                format_info = data.get('format', {})
                output_duration = float(format_info.get('duration', 0))

                if output_duration == 0:
                    if lenient:
                        # In recovery mode, allow files with no duration metadata
                        if self.verbose:
                            console.print(f"  Validation passed (lenient): {width}x{height}, no duration metadata (recovered file)", style="dim")
                    else:
                        if self.verbose:
                            console.print(f"  Validation failed: Output has no duration", style="dim")
                        return False
                else:
                    duration_diff = abs(output_duration - source_info.duration)
                    if duration_diff > duration_tolerance:
                        if lenient:
                            # In recovery mode, allow significant duration differences
                            # Just warn but don't fail - corrupted source may have wrong duration metadata
                            if self.verbose:
                                console.print(f"  Validation passed (lenient): {width}x{height}, {output_duration:.1f}s (source was {source_info.duration:.1f}s, recovered file may differ)", style="dim")
                        else:
                            if self.verbose:
                                console.print(f"  Validation failed: Duration mismatch ({output_duration:.1f}s vs {source_info.duration:.1f}s)", style="dim")
                            return False
                    else:
                        if self.verbose:
                            console.print(f"  Validation passed: {width}x{height}, {output_duration:.1f}s", style="dim")
            else:
                # No source info to compare against
                if self.verbose:
                    console.print(f"  Validation passed: {width}x{height} (no source comparison)", style="dim")

            return True

        except subprocess.TimeoutExpired:
            if self.verbose:
                console.print(f"  Validation failed: ffprobe timeout", style="dim")
            return False
        except Exception as e:
            if self.verbose:
                console.print(f"  Validation failed: {str(e)}", style="dim")
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
        failed_files = []
        total = len(video_paths)

        try:
            with create_encoding_progress() as batch_progress:
                overall_task = batch_progress.add_task("Encoding batch", total=total, speed="", eta="")
                file_task = batch_progress.add_task("", total=None, speed="", eta="")

                for idx, video_path in enumerate(video_paths, start=1):
                    # Check for graceful shutdown request
                    if shutdown_requested():
                        break

                    output_path = self.get_output_path(video_path, output_dir, target_codec=target_codec)
                    video_info = video_infos.get(video_path) if video_infos else None

                    result = self.re_encode_video(
                        video_path,
                        output_path,
                        target_codec=target_codec,
                        video_info=video_info,
                        current_index=idx,
                        total_count=total,
                        progress=batch_progress,
                        file_task=file_task,
                        **kwargs
                    )

                    results[video_path] = result
                    if not result:
                        failed_files.append(video_path)

                    batch_progress.update(overall_task, completed=idx, speed="", eta="")
        except KeyboardInterrupt:
            console.print("\n[warning]Interrupted by user.[/warning]")

        # Print summary after progress bar is gone
        successful = sum(1 for v in results.values() if v)
        section_header(f"Re-encoding complete: {successful}/{total} successful")
        if failed_files:
            console.print("[error]Failed files:[/error]")
            for f in failed_files:
                console.print(f"  [error]\u2717[/error] {f.name}")

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
                        console.print(f"  Found valid existing output: {potential_output.name}", style="dim")
                    return potential_output
                else:
                    # Invalid output found - remove it
                    if self.verbose:
                        console.print(f"  Found invalid output, removing: {potential_output.name}", style="dim")
                    potential_output.unlink()

        return None

    def _get_video_codec(self, file_path: Path) -> Optional[str]:
        """Get video codec of a file using ffprobe"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=codec_name',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(file_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return result.stdout.strip().lower()
        except Exception:
            pass
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
            console.print(f"[error]Error: Input file does not exist: {input_path}[/error]")
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
                # Check if it's actually HEVC before applying tag
                codec = self._get_video_codec(input_path)
                if codec in ['hevc', 'h265', 'hev1', 'hvc1']:
                    cmd.extend(['-tag:v', 'hvc1'])

            cmd.append(str(output_path))

            if self.verbose:
                console.print(f"Remuxing: {input_path.name} -> {output_path.name}", style="dim")

            # Run ffmpeg
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode != 0:
                if self.verbose:
                    console.print(f"[error]Remux failed for {input_path.name}: {result.stderr}[/error]")
                return False

            # Validate output
            if not output_path.exists() or output_path.stat().st_size < 1024:
                if self.verbose:
                    console.print(f"[error]Remux output validation failed for {input_path.name}[/error]")
                if output_path.exists():
                    output_path.unlink()
                return False

            if self.verbose:
                console.print(f"[success]\u2713 Remuxed: {input_path.name}[/success]")

            return True

        except subprocess.TimeoutExpired:
            console.print(f"[error]Error: Remux timeout for {input_path.name}[/error]")
            return False
        except Exception as e:
            console.print(f"[error]Error remuxing {input_path.name}: {e}[/error]")
            return False
