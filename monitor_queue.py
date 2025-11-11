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


class Colors:
    """ANSI color codes"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'

    @staticmethod
    def green(text):
        return f"{Colors.GREEN}{text}{Colors.RESET}"

    @staticmethod
    def red(text):
        return f"{Colors.RED}{text}{Colors.RESET}"

    @staticmethod
    def yellow(text):
        return f"{Colors.YELLOW}{text}{Colors.RESET}"

    @staticmethod
    def cyan(text):
        return f"{Colors.CYAN}{text}{Colors.RESET}"


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

    print("="*70)
    print("QUEUE SUMMARY")
    print("="*70)
    print(f"Total files: {total}")
    print()

    if state_counts['pending'] > 0:
        print(f"  Pending download:  {Colors.cyan(str(state_counts['pending']))}")
    if state_counts['downloading'] > 0:
        print(f"  Downloading:       {Colors.cyan(str(state_counts['downloading']))}")
    if state_counts['local'] > 0:
        print(f"  Ready to encode:   {Colors.yellow(str(state_counts['local']))}")
    if state_counts['encoding'] > 0:
        print(f"  Encoding:          {Colors.yellow(str(state_counts['encoding']))}")
    if state_counts['uploading'] > 0:
        print(f"  Uploading:         {Colors.yellow(str(state_counts['uploading']))}")
    if state_counts['complete'] > 0:
        print(f"  Complete:          {Colors.green(str(state_counts['complete']))}")
    if state_counts['failed'] > 0:
        print(f"  Failed:            {Colors.red(str(state_counts['failed']))}")

    print()

    # Progress bar
    if total > 0:
        complete_pct = (state_counts['complete'] / total) * 100
        failed_pct = (state_counts['failed'] / total) * 100
        in_progress_pct = 100 - complete_pct - failed_pct

        print(f"Progress: {complete_pct:.1f}% complete, {failed_pct:.1f}% failed, {in_progress_pct:.1f}% in progress")

    print()


def print_failed_files(state: Dict):
    """Print details of failed files"""
    files = state.get('files', [])
    failed_files = [f for f in files if f.get('state') == 'failed']

    if not failed_files:
        return

    print("="*70)
    print("FAILED FILES")
    print("="*70)
    print()

    for idx, file_info in enumerate(failed_files, 1):
        source = Path(file_info['source_path']).name
        error = file_info.get('error', 'Unknown error')

        print(f"{idx}. {Colors.red('✗')} {source}")
        print(f"   Error: {error}")
        print()


def print_temp_dir_info(temp_dir: Path):
    """Print information about temp directory"""
    info = get_temp_dir_info(temp_dir)

    print("="*70)
    print("TEMP DIRECTORY")
    print("="*70)
    print(f"Location: {temp_dir}")
    print()

    if not info['exists']:
        print(Colors.yellow("Directory does not exist (queue not started or already cleaned)"))
        print()
        return

    print(f"Total size: {info['size_str']}")
    print(f"File count: {info['file_count']}")
    print()

    if info['file_count'] > 0:
        print("Files:")
        for file_info in info['files'][:10]:  # Show top 10 largest
            print(f"  - {file_info['name']} ({file_info['size_str']})")

        if info['file_count'] > 10:
            print(f"  ... and {info['file_count'] - 10} more files")
        print()


def print_detailed_status(state: Dict, show_all: bool = False):
    """Print detailed file-by-file status"""
    files = state.get('files', [])

    if not show_all:
        # Only show non-complete files by default
        files = [f for f in files if f.get('state') != 'complete']

    if not files:
        print("="*70)
        print("No files to show (all complete)")
        print("="*70)
        return

    print("="*70)
    print(f"DETAILED STATUS {'(ALL FILES)' if show_all else '(IN PROGRESS + FAILED)'}")
    print("="*70)
    print()

    state_symbols = {
        'pending': '⏳',
        'downloading': '⬇️',
        'local': '💾',
        'encoding': '⚙️',
        'uploading': '⬆️',
        'complete': '✅',
        'failed': '❌'
    }

    for idx, file_info in enumerate(files, 1):
        source = Path(file_info['source_path']).name
        file_state = file_info.get('state', 'unknown')
        symbol = state_symbols.get(file_state, '?')

        # Color based on state
        if file_state == 'complete':
            status_str = Colors.green(file_state.upper())
        elif file_state == 'failed':
            status_str = Colors.red(file_state.upper())
        elif file_state in ['encoding', 'uploading']:
            status_str = Colors.yellow(file_state.upper())
        else:
            status_str = Colors.cyan(file_state.upper())

        print(f"{idx}. {symbol} {source}")
        print(f"   Status: {status_str}")

        if file_state == 'failed' and file_info.get('error'):
            print(f"   Error: {Colors.red(file_info['error'])}")

        print()


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

    print()
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║          VideoSentinel Queue Monitor                             ║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    print()
    print(f"State file: {state_file}")
    print()

    # Load state
    state = load_queue_state(state_file)

    if not state:
        print(Colors.yellow("No queue state file found."))
        print()
        print("This could mean:")
        print("  - Queue mode has not been started yet")
        print("  - Queue was already cleared with --clear-queue")
        print("  - Using a different temp directory than expected")
        print()
        sys.exit(0)

    # Print information
    if args.failed_only:
        print_failed_files(state)
    else:
        print_queue_summary(state)
        print_failed_files(state)
        print_temp_dir_info(temp_dir)
        print_detailed_status(state, show_all=args.all)

    print("="*70)
    print()


if __name__ == '__main__':
    main()
