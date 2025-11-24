"""
Video issue detection module for identifying corrupted or problematic files
"""

import subprocess
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class VideoIssue:
    """Container for video issue information"""
    file_path: Path
    issue_type: str
    severity: str  # 'critical', 'warning', 'info'
    description: str


class IssueDetector:
    """Detects encoding issues and corrupted video files"""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def check_file_integrity(self, video_path: Path) -> List[VideoIssue]:
        """
        Check video file integrity using ffmpeg

        Args:
            video_path: Path to video file

        Returns:
            List of VideoIssue objects
        """
        issues = []

        try:
            # Use ffmpeg to decode the entire video and check for errors
            cmd = [
                'ffmpeg',
                '-v', 'error',
                '-i', str(video_path),
                '-f', 'null',
                '-'
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            # Check stderr for errors
            if result.stderr:
                error_lines = result.stderr.strip().split('\n')

                # Categorize errors
                for line in error_lines:
                    line_lower = line.lower()

                    if 'corrupt' in line_lower or 'error' in line_lower or 'invalid nal unit size' in line_lower:
                        issues.append(VideoIssue(
                            file_path=video_path,
                            issue_type='corruption',
                            severity='critical',
                            description=line.strip()
                        ))
                    elif 'warning' in line_lower:
                        issues.append(VideoIssue(
                            file_path=video_path,
                            issue_type='warning',
                            severity='warning',
                            description=line.strip()
                        ))

        except subprocess.TimeoutExpired:
            issues.append(VideoIssue(
                file_path=video_path,
                issue_type='timeout',
                severity='warning',
                description='Video integrity check timed out (file may be very large)'
            ))
        except Exception as e:
            issues.append(VideoIssue(
                file_path=video_path,
                issue_type='check_failed',
                severity='critical',
                description=f'Failed to check integrity: {str(e)}'
            ))

        return issues

    def check_incomplete_video(self, video_path: Path, min_duration: float = 1.0) -> Optional[VideoIssue]:
        """
        Check if video appears incomplete (too short or no duration)

        Args:
            video_path: Path to video file
            min_duration: Minimum expected duration in seconds

        Returns:
            VideoIssue if video appears incomplete, None otherwise
        """
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(video_path)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                return VideoIssue(
                    file_path=video_path,
                    issue_type='incomplete',
                    severity='critical',
                    description='Could not determine video duration'
                )

            duration_str = result.stdout.strip()

            if not duration_str or duration_str == 'N/A':
                return VideoIssue(
                    file_path=video_path,
                    issue_type='incomplete',
                    severity='critical',
                    description='Video has no duration (possibly incomplete)'
                )

            try:
                duration = float(duration_str)

                if duration < min_duration:
                    return VideoIssue(
                        file_path=video_path,
                        issue_type='incomplete',
                        severity='warning',
                        description=f'Video duration is very short ({duration:.2f}s)'
                    )
            except ValueError:
                return VideoIssue(
                    file_path=video_path,
                    issue_type='incomplete',
                    severity='warning',
                    description=f'Invalid duration value: {duration_str}'
                )

        except subprocess.TimeoutExpired:
            return VideoIssue(
                file_path=video_path,
                issue_type='timeout',
                severity='warning',
                description='Duration check timed out'
            )
        except Exception as e:
            return VideoIssue(
                file_path=video_path,
                issue_type='check_failed',
                severity='warning',
                description=f'Duration check failed: {str(e)}'
            )

        return None

    def check_missing_audio(self, video_path: Path, expect_audio: bool = True) -> Optional[VideoIssue]:
        """
        Check if video is missing audio when it should have it

        Args:
            video_path: Path to video file
            expect_audio: Whether audio is expected

        Returns:
            VideoIssue if audio is missing, None otherwise
        """
        if not expect_audio:
            return None

        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-select_streams', 'a:0',
                '-show_entries', 'stream=codec_type',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(video_path)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if not result.stdout.strip():
                return VideoIssue(
                    file_path=video_path,
                    issue_type='no_audio',
                    severity='warning',
                    description='Video has no audio stream'
                )

        except Exception as e:
            if self.verbose:
                print(f"Warning: Could not check audio for {video_path}: {e}")

        return None

    def check_unusual_specs(self, video_path: Path) -> List[VideoIssue]:
        """
        Check for unusual video specifications that might indicate issues

        Args:
            video_path: Path to video file

        Returns:
            List of VideoIssue objects
        """
        issues = []

        try:
            # Get video properties
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-show_entries', 'stream=codec_name,width,height,avg_frame_rate',
                '-select_streams', 'v:0',
                '-of', 'default=noprint_wrappers=1',
                str(video_path)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                return issues

            # Parse output
            props = {}
            for line in result.stdout.strip().split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    props[key] = value

            # Check for unusual dimensions
            width = int(props.get('width', 0))
            height = int(props.get('height', 0))

            if width == 0 or height == 0:
                issues.append(VideoIssue(
                    file_path=video_path,
                    issue_type='invalid_dimensions',
                    severity='critical',
                    description=f'Invalid dimensions: {width}x{height}'
                ))
            elif width < 320 or height < 240:
                issues.append(VideoIssue(
                    file_path=video_path,
                    issue_type='low_resolution',
                    severity='info',
                    description=f'Unusually low resolution: {width}x{height}'
                ))

            # Check for unusual aspect ratio
            if width > 0 and height > 0:
                aspect = width / height
                if aspect < 0.5 or aspect > 3.0:
                    issues.append(VideoIssue(
                        file_path=video_path,
                        issue_type='unusual_aspect',
                        severity='info',
                        description=f'Unusual aspect ratio: {aspect:.2f}'
                    ))

            # Check frame rate
            fps_str = props.get('avg_frame_rate', '0/1')
            try:
                num, den = map(int, fps_str.split('/'))
                fps = num / den if den != 0 else 0

                if fps == 0:
                    issues.append(VideoIssue(
                        file_path=video_path,
                        issue_type='invalid_fps',
                        severity='critical',
                        description='Invalid frame rate (0 FPS)'
                    ))
                elif fps > 120:
                    issues.append(VideoIssue(
                        file_path=video_path,
                        issue_type='high_fps',
                        severity='info',
                        description=f'Unusually high frame rate: {fps:.2f} FPS'
                    ))
            except:
                pass

        except Exception as e:
            if self.verbose:
                print(f"Warning: Could not check specs for {video_path}: {e}")

        return issues

    def scan_video(self, video_path: Path, deep_scan: bool = False) -> List[VideoIssue]:
        """
        Perform comprehensive scan of video file

        Args:
            video_path: Path to video file
            deep_scan: Whether to perform deep integrity check (slower)

        Returns:
            List of all detected issues
        """
        all_issues = []

        if self.verbose:
            print(f"Scanning: {video_path.name}")

        # Check for incomplete video
        incomplete_issue = self.check_incomplete_video(video_path)
        if incomplete_issue:
            all_issues.append(incomplete_issue)

        # Check for missing audio
        audio_issue = self.check_missing_audio(video_path)
        if audio_issue:
            all_issues.append(audio_issue)

        # Check for unusual specs
        spec_issues = self.check_unusual_specs(video_path)
        all_issues.extend(spec_issues)

        # Perform deep integrity check if requested
        if deep_scan:
            integrity_issues = self.check_file_integrity(video_path)
            all_issues.extend(integrity_issues)

        return all_issues
