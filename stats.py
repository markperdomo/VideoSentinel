"""
Statistics module for video library analysis.
"""

import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from rich.table import Table
from video_analyzer import VideoAnalyzer, VideoInfo
from ui import console


def format_size(size_bytes):
    """Format bytes as human-readable size."""
    if size_bytes == 0:
        return "0B"
    size_names = ("B", "KB", "MB", "GB", "TB")
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024
        i += 1
    return f"{size_bytes:.2f} {size_names[i]}"


class StatsCollector:
    """Collects and displays statistics about a video library."""

    def __init__(self, analyzer: VideoAnalyzer):
        self.analyzer = analyzer

    def collect_stats(self, directory: Path, recursive: bool = True) -> Dict[str, int]:
        """
        Collects statistics about the video files in a directory.

        Args:
            directory: The directory to scan.
            recursive: Whether to scan recursively.

        Returns:
            A dictionary mapping codec to total byte size.
        """
        video_files = self.analyzer.find_videos(directory, recursive=recursive)
        codec_stats = defaultdict(int)

        for video_file in video_files:
            video_info = self.analyzer.get_video_info(video_file)
            if video_info and video_info.is_valid:
                codec_stats[video_info.codec] += video_info.file_size

        return codec_stats

    def display_stats(self, codec_stats: Dict[str, int]):
        """
        Displays the collected statistics as a Rich table.

        Args:
            codec_stats: A dictionary mapping codec to total byte size.
        """
        total_size = sum(codec_stats.values())
        if total_size == 0:
            console.print("No video files found or analyzed.")
            return

        # Sort codecs by size in descending order
        sorted_codecs = sorted(codec_stats.items(), key=lambda item: item[1], reverse=True)

        table = Table(title="Video Library Statistics")
        table.add_column("Codec", style="cyan", no_wrap=True)
        table.add_column("Size", justify="right")
        table.add_column("Percentage", justify="right")

        for codec, size in sorted_codecs:
            percentage = (size / total_size) * 100
            table.add_row(codec, format_size(size), f"{percentage:.2f}%")

        # Footer row
        table.add_section()
        table.add_row("[bold]Total[/bold]", f"[bold]{format_size(total_size)}[/bold]", "[bold]100.00%[/bold]")

        console.print(table)
