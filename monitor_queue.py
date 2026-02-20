#!/usr/bin/env python3
"""
Queue Monitor for VideoSentinel Network Queue Mode

Monitors the queue state file and temp directory to show:
- Current queue status (pending, downloading, encoding, uploading, complete, failed)
- Failed files with error messages
- Temp directory size and contents
- Detailed file-by-file status
"""

import json
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

from rich.table import Table
from rich.panel import Panel
from ui import console, section_header


def get_queue_state_path(temp_dir: Path = None) -> Path:
    """Get the path to the queue state file"""
    if temp_dir:
        base_dir = Path(temp_dir)
    else:
        base_dir = Path(tempfile.gettempdir()) / "videosentinel"

    return base_dir / "queue_state.json"


def get_temp_dir_path(temp_dir: Path = None) -> Path:
    """Get the path to the temp directory"""
    if temp_dir:
        return Path(temp_dir)
    else:
        return Path(tempfile.gettempdir()) / "videosentinel"


def format_size(bytes_val: int) -> str:
    """Format bytes as human-readable size"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} TB"


def get_temp_dir_info(temp_dir: Path) -> Dict:
    """Get information about temp directory contents"""
    if not temp_dir.exists():
        return {'exists': False, 'size': 0, 'files': []}

    files = []
    total_size = 0

    for file_path in temp_dir.iterdir():
        if file_path.is_file():
            size = file_path.stat().st_size
            total_size += size
            files.append({
                'name': file_path.name,
                'size': size,
                'size_str': format_size(size)
            })

    return {
        'exists': True,
        'size': total_size,
        'size_str': format_size(total_size),
        'file_count': len(files),
        'files': sorted(files, key=lambda x: x['size'], reverse=True)
    }


def load_queue_state(state_file: Path) -> Dict:
    """Load and parse the queue state file"""
    if not state_file.exists():
        return None

    with open(state_file, 'r') as f:
        return json.load(f)


def print_queue_summary(state: Dict):
    """Print high-level queue statistics"""
    files = state.get('files', [])

    # Count by state
    state_counts = {
        'pending': 0,
        'downloading': 0,
        'local': 0,
        'encoding': 0,
        'uploading': 0,
        'complete': 0,
        'failed': 0
    }

    for file_info in files:
        file_state = file_info.get('state', 'unknown')
        if file_state in state_counts:
            state_counts[file_state] += 1

    total = len(files)

    section_header("QUEUE SUMMARY")
    console.print(f"Total files: {total}")
    console.print()

    if state_counts['pending'] > 0:
        console.print(f"  Pending download:  [info]{state_counts['pending']}[/info]")
    if state_counts['downloading'] > 0:
        console.print(f"  Downloading:       [info]{state_counts['downloading']}[/info]")
    if state_counts['local'] > 0:
        console.print(f"  Ready to encode:   [warning]{state_counts['local']}[/warning]")
    if state_counts['encoding'] > 0:
        console.print(f"  Encoding:          [warning]{state_counts['encoding']}[/warning]")
    if state_counts['uploading'] > 0:
        console.print(f"  Uploading:         [warning]{state_counts['uploading']}[/warning]")
    if state_counts['complete'] > 0:
        console.print(f"  Complete:          [success]{state_counts['complete']}[/success]")
    if state_counts['failed'] > 0:
        console.print(f"  Failed:            [error]{state_counts['failed']}[/error]")

    console.print()

    # Progress bar
    if total > 0:
        complete_pct = (state_counts['complete'] / total) * 100
        failed_pct = (state_counts['failed'] / total) * 100
        in_progress_pct = 100 - complete_pct - failed_pct

        console.print(f"Progress: {complete_pct:.1f}% complete, {failed_pct:.1f}% failed, {in_progress_pct:.1f}% in progress")

    console.print()


def print_failed_files(state: Dict):
    """Print details of failed files"""
    files = state.get('files', [])
    failed_files = [f for f in files if f.get('state') == 'failed']

    if not failed_files:
        return

    section_header("FAILED FILES")

    for idx, file_info in enumerate(failed_files, 1):
        source = Path(file_info['source_path']).name
        error = file_info.get('error', 'Unknown error')

        console.print(f"{idx}. [error]\u2717[/error] {source}")
        console.print(f"   Error: {error}")
        console.print()


def print_temp_dir_info(temp_dir: Path):
    """Print information about temp directory"""
    info = get_temp_dir_info(temp_dir)

    section_header("TEMP DIRECTORY")
    console.print(f"Location: {temp_dir}")
    console.print()

    if not info['exists']:
        console.print("[warning]Directory does not exist (queue not started or already cleaned)[/warning]")
        console.print()
        return

    console.print(f"Total size: {info['size_str']}")
    console.print(f"File count: {info['file_count']}")
    console.print()

    if info['file_count'] > 0:
        console.print("Files:")
        for file_info in info['files'][:10]:  # Show top 10 largest
            console.print(f"  - {file_info['name']} ({file_info['size_str']})")

        if info['file_count'] > 10:
            console.print(f"  ... and {info['file_count'] - 10} more files")
        console.print()


def print_detailed_status(state: Dict, show_all: bool = False):
    """Print detailed file-by-file status"""
    files = state.get('files', [])

    if not show_all:
        # Only show non-complete files by default
        files = [f for f in files if f.get('state') != 'complete']

    if not files:
        section_header("No files to show (all complete)")
        return

    title = "ALL FILES" if show_all else "IN PROGRESS + FAILED"

    table = Table(title=f"Detailed Status ({title})")
    table.add_column("#", style="dim", width=4)
    table.add_column("Status", width=14)
    table.add_column("File")
    table.add_column("Details", style="dim")

    state_styles = {
        'complete': 'green',
        'failed': 'red',
        'encoding': 'yellow',
        'uploading': 'yellow',
        'pending': 'cyan',
        'downloading': 'cyan',
        'local': 'cyan',
    }

    state_symbols = {
        'pending': '\u23f3',
        'downloading': '\u2b07',
        'local': '\U0001f4be',
        'encoding': '\u2699',
        'uploading': '\u2b06',
        'complete': '\u2705',
        'failed': '\u274c'
    }

    for idx, file_info in enumerate(files, 1):
        source = Path(file_info['source_path']).name
        file_state = file_info.get('state', 'unknown')
        style = state_styles.get(file_state, '')
        symbol = state_symbols.get(file_state, '?')
        details = file_info.get('error', '') if file_state == 'failed' else ''

        table.add_row(
            str(idx),
            f"[{style}]{symbol} {file_state.upper()}[/{style}]",
            source,
            details
        )

    console.print(table)


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Monitor VideoSentinel queue mode status',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--temp-dir',
        type=Path,
        help='Custom temp directory (if specified during encoding)'
    )

    parser.add_argument(
        '--all',
        action='store_true',
        help='Show all files including completed ones in detailed view'
    )

    parser.add_argument(
        '--failed-only',
        action='store_true',
        help='Only show failed files'
    )

    args = parser.parse_args()

    # Get paths
    state_file = get_queue_state_path(args.temp_dir)
    temp_dir = get_temp_dir_path(args.temp_dir)

    console.print()
    console.print(Panel("VideoSentinel Queue Monitor", style="bold cyan"))
    console.print()
    console.print(f"State file: {state_file}")
    console.print()

    # Load state
    state = load_queue_state(state_file)

    if not state:
        console.print("[warning]No queue state file found.[/warning]")
        console.print()
        console.print("This could mean:")
        console.print("  - Queue mode has not been started yet")
        console.print("  - Queue was already cleared with --clear-queue")
        console.print("  - Using a different temp directory than expected")
        console.print()
        sys.exit(0)

    # Print information
    if args.failed_only:
        print_failed_files(state)
    else:
        print_queue_summary(state)
        print_failed_files(state)
        print_temp_dir_info(temp_dir)
        print_detailed_status(state, show_all=args.all)

    console.print()


if __name__ == '__main__':
    main()
