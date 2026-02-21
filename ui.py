"""
Shared UI module for VideoSentinel
Provides a centralized Rich console and common UI helpers.
"""

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
console = Console(theme=VS_THEME)


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
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        TextColumn("{task.fields[speed]}", table_column=Column(width=8)),
        TextColumn("{task.fields[eta]}", table_column=Column(width=14)),
        console=console,
        transient=True,
    )


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
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        TextColumn("{task.fields[speed]}", table_column=Column(width=8)),
        TextColumn("{task.fields[eta]}", table_column=Column(width=14)),
        console=console,
        transient=True,
    )
