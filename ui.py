"""
Shared UI module for VideoSentinel
Provides a centralized Rich console and common UI helpers.
"""

import os
from rich.console import Console
from rich.panel import Panel
from rich.table import Column, Table
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
    TaskProgressColumn,
    MofNCompleteColumn,
)
from rich.theme import Theme

# Custom theme with semantic color names
VS_THEME = Theme({
    "success": "green",
    "error": "red",
    "warning": "yellow",
    "info": "cyan",
    "highlight": "magenta",
    "filename": "bold white",
    "codec": "bold cyan",
    "dim": "dim",
})

# Global console instance -- all modules import this
console = Console(theme=VS_THEME, highlight=False)


def section_header(title: str, subtitle: str = None):
    """Display a section header as a Rich Panel."""
    content = title
    if subtitle:
        content += f"\n[dim]{subtitle}[/dim]"
    console.print()
    console.print(Panel(content, style="bold cyan", expand=True))
    console.print()


def success(message: str):
    """Print a success message with green checkmark."""
    console.print(f"[success]\u2713[/success] {message}")


def error(message: str):
    """Print an error message with red X."""
    console.print(f"[error]\u2717[/error] {message}")


def warning(message: str):
    """Print a warning message."""
    console.print(f"[warning]\u26a0[/warning] {message}")


def info(message: str):
    """Print an info message."""
    console.print(f"[info]\u2139[/info] {message}")


def fit_filename(name: str, width: int = 0) -> str:
    """Truncate a filename to at most *width* characters.

    Long names keep the first and last portions with an ellipsis in the
    middle so the extension stays visible (e.g. ``very_long_na…encoded.mp4``).

    If *width* is 0 (default), a sensible value is calculated from the
    current terminal width, leaving room for progress-bar columns.
    """
    if width <= 0:
        # Fixed columns in queue/encoding progress:
        #   spinner(2) + bar(20) + task%(4) + speed(8) + eta(14) + separators(6) = 54
        # Leave the rest for the description column.  The description
        # includes a prefix ("Download: " ≈ 12 chars) so subtract that too.
        try:
            term_width = os.get_terminal_size().columns
        except OSError:
            term_width = 80
        width = max(20, term_width - 54 - 12)
    if len(name) <= width:
        return name
    # Keep extension visible: split into stem + tail
    keep_end = min(12, width // 3)
    keep_start = width - keep_end - 1  # 1 char for ellipsis
    return name[:keep_start] + "\u2026" + name[-keep_end:]


def create_scan_progress() -> Progress:
    """
    Create a Rich Progress bar for scanning/analyzing loops.
    transient=True so the bar disappears after completion.
    """
    return Progress(
        SpinnerColumn(),
        TextColumn(
            "[progress.description]{task.description}",
            table_column=Column(ratio=1, no_wrap=True, overflow="ellipsis"),
        ),
        BarColumn(),
        MofNCompleteColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    )


def create_batch_progress() -> Progress:
    """
    Create a two-row Rich Progress for batch operations.

    Usage:
        with create_batch_progress() as progress:
            overall = progress.add_task("Processing", total=len(files))
            current = progress.add_task("", total=None)
            for f in files:
                progress.update(current, description=f"Current: {f.name}")
                ...
                progress.advance(overall)

    Both rows update in-place (no scrolling). transient=True so the
    entire display vanishes when the context exits, leaving room for
    a printed summary.
    """
    return Progress(
        SpinnerColumn(),
        TextColumn(
            "[progress.description]{task.description}",
            table_column=Column(ratio=1, no_wrap=True, overflow="ellipsis"),
        ),
        BarColumn(),
        TaskProgressColumn(),
        MofNCompleteColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    )


def create_encoding_progress() -> Progress:
    """
    Create a Rich Progress bar for encoding display.
    Shows: spinner, description, bar, percentage, speed, ETA.
    transient=True so the bar disappears after completion.

    The description column uses ratio=1 to fill remaining space, keeping
    the bar and stats anchored to the right regardless of filename length.

    Supports multiple tasks so batch_re_encode can add an overall
    task alongside the per-file encoding task.
    """
    return Progress(
        SpinnerColumn(),
        TextColumn(
            "[progress.description]{task.description}",
            table_column=Column(ratio=1, no_wrap=True, overflow="ellipsis"),
        ),
        BarColumn(bar_width=20),
        TaskProgressColumn(),
        TextColumn("{task.fields[speed]}", table_column=Column(width=8)),
        TextColumn("{task.fields[eta]}", table_column=Column(width=14)),
        console=console,
        transient=True,
    )


def format_size(size_bytes: int) -> str:
    """Format bytes to human-readable size."""
    if size_bytes <= 0:
        return "--"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.0f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 ** 3):.2f} GB"


def create_replacement_table(report_data: list) -> Table:
    """
    Create a Rich Table summarizing files ready for replacement.

    Args:
        report_data: List of dicts with keys: source_path, final_path, source_size, output_size

    Returns:
        Rich Table with per-file rows and a totals row.
    """
    from pathlib import Path

    table = Table(title="Replacement Summary", show_header=True, header_style="bold cyan")
    table.add_column("File", style="filename", no_wrap=True, max_width=50)
    table.add_column("Original", justify="right")
    table.add_column("Encoded", justify="right")
    table.add_column("Saved", justify="right")

    total_source = 0
    total_output = 0

    for entry in report_data:
        source_name = Path(entry['source_path']).name
        source_size = entry['source_size']
        output_size = entry['output_size']
        total_source += source_size
        total_output += output_size

        if source_size > 0 and output_size > 0:
            pct = (1 - output_size / source_size) * 100
            saved_str = f"[success]{pct:.0f}%[/success]" if pct > 0 else f"[warning]{pct:+.0f}%[/warning]"
        else:
            saved_str = "--"

        table.add_row(source_name, format_size(source_size), format_size(output_size), saved_str)

    # Totals row
    if report_data:
        table.add_section()
        if total_source > 0:
            total_pct = (1 - total_output / total_source) * 100
            total_saved_str = f"[success]{total_pct:.0f}%[/success]" if total_pct > 0 else f"[warning]{total_pct:+.0f}%[/warning]"
        else:
            total_saved_str = "--"
        space_freed = total_source - total_output if total_source > total_output else 0
        table.add_row(
            f"[bold]{len(report_data)} files[/bold]",
            format_size(total_source),
            format_size(total_output),
            total_saved_str,
        )
        table.caption = f"Space to be freed: [success]{format_size(space_freed)}[/success]"

    return table


def create_queue_progress() -> Progress:
    """
    Create a Rich Progress for queue mode (download/encode/upload pipeline).

    Shows 4 rows, all updating in-place:
      1. Overall pipeline progress (completed files / total)
      2. Download status line
      3. Encoding progress (with speed + ETA from FFmpeg)
      4. Upload status line

    The description column uses ratio=1 to fill remaining space, keeping
    the bar and stats anchored to the right regardless of filename length.

    Usage:
        with create_queue_progress() as progress:
            overall = progress.add_task("Pipeline", total=N, speed="", eta="")
            dl_task = progress.add_task("[dim]Download:[/dim] idle", total=None, speed="", eta="")
            enc_task = progress.add_task("[dim]Encode:[/dim] idle", total=None, speed="", eta="")
            ul_task = progress.add_task("[dim]Upload:[/dim] idle", total=None, speed="", eta="")
    """
    return Progress(
        SpinnerColumn(),
        TextColumn(
            "[progress.description]{task.description}",
            table_column=Column(ratio=1, no_wrap=True, overflow="ellipsis"),
        ),
        BarColumn(bar_width=20),
        TaskProgressColumn(),
        TextColumn("{task.fields[speed]}", table_column=Column(width=8)),
        TextColumn("{task.fields[eta]}", table_column=Column(width=14)),
        console=console,
        transient=True,
    )
