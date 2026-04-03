"""
Network Queue Manager for VideoSentinel

Implements a three-stage pipeline for encoding network-stored videos:
1. Download: Pre-fetch files from network to local temp storage
2. Encode: Process files locally (fast)
3. Upload: Copy completed encodes back to network

This dramatically improves performance when working with network storage by:
- Eliminating network I/O during encoding
- Enabling parallel download/encode/upload operations
- Buffering files locally for consistent encoding speed
"""

import shutil
import subprocess
import tempfile
import threading
import queue
import json
import time
from pathlib import Path
from typing import List, Optional, Dict, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import logging
from shutdown_manager import shutdown_requested
from ui import console, section_header, create_queue_progress, fit_filename


class FileState(Enum):
    """Represents the current state of a file in the pipeline"""
    PENDING = "pending"           # Waiting to be downloaded
    DOWNLOADING = "downloading"   # Currently downloading from network
    LOCAL = "local"               # Downloaded, waiting to encode
    ENCODING = "encoding"         # Currently encoding
    UPLOADING = "uploading"       # Encoded, uploading to network
    UPLOADED = "uploaded"         # Uploaded and validated, original not yet deleted
    COMPLETE = "complete"         # Fully processed and uploaded
    FAILED = "failed"            # Error occurred


@dataclass
class QueuedFile:
    """Tracks a file through the encoding pipeline"""
    source_path: str              # Original network path
    local_path: Optional[str]     # Temp local path (None until downloaded)
    output_path: Optional[str]    # Local encoded output (None until encoded)
    final_path: Optional[str]     # Final network destination (None until uploaded)
    state: FileState
    error: Optional[str] = None
    source_size: Optional[int] = None      # Original file size in bytes
    output_size: Optional[int] = None      # Encoded file size in bytes
    source_duration: Optional[float] = None  # Original video duration in seconds

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization"""
        data = asdict(self)
        data['state'] = self.state.value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'QueuedFile':
        """Create from dict (JSON deserialization)"""
        data['state'] = FileState(data['state'])
        return cls(**data)


class NetworkQueueManager:
    """
    Manages a three-stage pipeline for efficient network video encoding.

    Architecture:
    - Download thread: Pre-fetches files to local temp storage
    - Encoder thread: Processes local files (uses existing VideoEncoder)
    - Upload thread: Copies completed files back to network
    - Main thread: Coordinates queues and tracks progress
    """

    def __init__(
        self,
        temp_dir: Optional[Path] = None,
        max_buffer_size: int = 4,
        max_temp_size_gb: Optional[float] = None,
        verbose: bool = False,
        replace_original: bool = False,
        parallel: int = 1
    ):
        """
        Initialize the queue manager.

        Args:
            temp_dir: Local directory for temp files (None = system temp)
            max_buffer_size: Max number of files to buffer locally
            max_temp_size_gb: Max temp storage in GB (None = no limit)
            verbose: Enable detailed logging
            replace_original: Whether to replace originals on network
        """
        self.temp_dir = Path(temp_dir) if temp_dir else Path(tempfile.gettempdir()) / "videosentinel"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        self.max_buffer_size = max_buffer_size
        self.max_temp_size_bytes = int(max_temp_size_gb * 1024**3) if max_temp_size_gb else None
        self.verbose = verbose
        self.replace_original = replace_original
        self.parallel = max(1, parallel)

        # Shared encode progress counter (thread-safe for parallel encoding)
        self._encode_completed_count = 0
        self._encode_completed_lock = threading.Lock()

        # Queues for thread coordination
        self.download_queue: queue.Queue[QueuedFile] = queue.Queue()
        self.encode_queue: queue.Queue[QueuedFile] = queue.Queue()
        self.upload_queue: queue.Queue[QueuedFile] = queue.Queue()

        # Thread-safe file tracking
        self.files: List[QueuedFile] = []
        self.files_lock = threading.Lock()

        # Control flags
        self.stop_event = threading.Event()
        self.paused_event = threading.Event()
        self.encoding_complete = threading.Event()

        # Worker threads
        self.download_thread: Optional[threading.Thread] = None
        self.upload_thread: Optional[threading.Thread] = None

        # State persistence
        self.state_file = self.temp_dir / "queue_state.json"

        # Progress display (set during start())
        self._progress = None
        self._overall_task = None
        self._dl_task = None
        self._enc_task = None
        self._ul_task = None

        # Setup logging
        self.logger = logging.getLogger(__name__)
        if verbose:
            logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

    def add_files(self, source_paths: List[Path]) -> None:
        """Add files to the processing queue, skipping any already present (e.g. from resume)"""
        with self.files_lock:
            existing_sources = {f.source_path for f in self.files}
            for path in source_paths:
                if str(path) in existing_sources:
                    continue
                queued_file = QueuedFile(
                    source_path=str(path),
                    local_path=None,
                    output_path=None,
                    final_path=None,
                    state=FileState.PENDING
                )
                self.files.append(queued_file)
                self.download_queue.put(queued_file)

        self.save_state()

    def start(self, encode_callback: Callable[[Path, Path], bool]) -> None:
        """
        Start the pipeline workers.

        Args:
            encode_callback: Function to encode a file (local_input, local_output) -> success
                             Signature: (local_input, local_output) -> bool
                             OR: (local_input, local_output, progress, file_task) -> bool
                             The 4-arg form allows the encoder to update the progress display.
        """
        self.encode_callback = encode_callback

        # Clear the encoding complete flag (important for resumed sessions)
        self.encoding_complete.clear()

        # Reset shared counter for this session
        self._encode_completed_count = 0

        total = len(self.files)
        # Count already-completed files from resumed sessions
        with self.files_lock:
            self._encode_completed_count = sum(1 for f in self.files if f.state in (FileState.COMPLETE, FileState.UPLOADED))

        with create_queue_progress() as progress:
            self._progress = progress
            self._overall_task = progress.add_task(
                f"Pipeline  0/{total}", total=total, speed="", eta=""
            )
            self._dl_task = progress.add_task(
                "[dim]Download:[/dim] idle", total=None, speed="", eta=""
            )

            # Create encode task row(s) — one per parallel worker
            self._enc_tasks = []
            for i in range(self.parallel):
                task = progress.add_task(
                    "[dim]Encode:[/dim]   idle", total=None, speed="", eta=""
                )
                self._enc_tasks.append(task)
            # Keep self._enc_task pointing to the first for backward compat
            self._enc_task = self._enc_tasks[0]

            self._ul_task = progress.add_task(
                "[dim]Upload:[/dim]   idle", total=None, speed="", eta=""
            )

            # Start worker threads
            self.download_thread = threading.Thread(target=self._download_worker, daemon=True)
            self.upload_thread = threading.Thread(target=self._upload_worker, daemon=True)

            self.download_thread.start()
            self.upload_thread.start()

            if self.parallel <= 1:
                # Main thread handles encoding (existing behavior)
                self._encode_worker(self._enc_tasks[0])
            else:
                # Launch N parallel encode worker threads
                encode_threads = []
                for enc_task in self._enc_tasks:
                    t = threading.Thread(
                        target=self._encode_worker, args=(enc_task,), daemon=True
                    )
                    t.start()
                    encode_threads.append(t)
                for t in encode_threads:
                    t.join()

            # Signal that encoding is complete (no more uploads coming)
            self.encoding_complete.set()

            # Update encoding rows to show done
            for enc_task in self._enc_tasks:
                progress.update(enc_task, description="[dim]Encode:[/dim]   [success]done[/success]", speed="", eta="")

            # Wait for all uploads to complete before exiting
            if self.verbose:
                self.logger.info("Encoding complete, waiting for uploads to finish...")

            progress.update(self._ul_task, description="[dim]Upload:[/dim]   finishing...")

            # Wait for upload queue to drain
            self.upload_queue.join()

            # Give upload thread time to finish processing the last file
            if self.upload_thread.is_alive():
                self.upload_thread.join(timeout=30)

            progress.update(self._ul_task, description="[dim]Upload:[/dim]   [success]done[/success]", speed="", eta="")

            if self.verbose:
                self.logger.info("All uploads complete")

        # Clear progress references
        self._progress = None

    def stop(self) -> None:
        """Stop all workers gracefully"""
        self.stop_event.set()

        if self.download_thread:
            self.download_thread.join(timeout=5)
        if self.upload_thread:
            self.upload_thread.join(timeout=5)

        self.save_state()

    def _download_worker(self) -> None:
        """Worker thread: Downloads files from network to local temp storage"""
        while not self.stop_event.is_set():
            try:
                # Check if we need to pause (buffer full or storage limit)
                while self._should_pause_downloads():
                    if self.stop_event.is_set():
                        return
                    time.sleep(1)

                # Get next file to download (with timeout so we can check stop_event)
                try:
                    queued_file = self.download_queue.get(timeout=1)
                except queue.Empty:
                    # Check if all files have been downloaded (no more PENDING files)
                    if self._all_downloaded_or_failed():
                        break
                    continue

                # Update state
                self._update_file_state(queued_file, FileState.DOWNLOADING)

                try:
                    # Ensure temp directory exists before downloading
                    if not self._ensure_temp_dir_exists():
                        raise Exception("Temp directory unavailable")

                    # Copy from network to local temp
                    source = Path(queued_file.source_path)
                    local_path = self.temp_dir / f"download_{source.name}"

                    if self._progress and self._dl_task is not None:
                        self._progress.update(
                            self._dl_task,
                            description=f"[dim]Download:[/dim] {fit_filename(source.name)}",
                        )

                    if self.verbose:
                        self.logger.info(f"Downloading: {source.name}")

                    # Try to preserve metadata, but fall back to regular copy if it fails
                    # (Network filesystems often don't support metadata preservation)
                    try:
                        shutil.copy2(source, local_path)
                    except (OSError, PermissionError) as e:
                        if self.verbose:
                            self.logger.debug(f"Metadata preservation failed, using regular copy: {e}")
                        shutil.copy(source, local_path)

                    # Update queued file
                    queued_file.local_path = str(local_path)
                    self._update_file_state(queued_file, FileState.LOCAL)

                    # Add to encode queue
                    self.encode_queue.put(queued_file)

                    if self.verbose:
                        self.logger.info(f"Downloaded: {source.name}")

                except Exception as e:
                    error_msg = f"Download failed: {str(e)}"
                    self.logger.error(f"{source.name}: {error_msg}")
                    queued_file.error = error_msg
                    self._update_file_state(queued_file, FileState.FAILED)

                finally:
                    self.download_queue.task_done()
                    self.save_state()

            except Exception as e:
                self.logger.error(f"Download worker error: {e}")

        # Mark download row as done
        if self._progress and self._dl_task is not None:
            self._progress.update(
                self._dl_task,
                description="[dim]Download:[/dim] [success]done[/success]",
            )

    def _encode_worker(self, enc_task=None) -> None:
        """
        Encode worker: processes files from the encode queue.

        When parallel > 1, multiple instances run on separate threads,
        each with its own enc_task for independent progress display.
        """
        total = len(self.files)

        while not self.stop_event.is_set():
            try:
                # Check for graceful shutdown request
                if shutdown_requested():
                    self.stop_event.set()  # Signal other threads to stop
                    break  # Exit loop - current video already completed

                # Get next file to encode (with timeout)
                try:
                    queued_file = self.encode_queue.get(timeout=1)
                except queue.Empty:
                    # Check if we're done (no more downloads coming and encode queue empty)
                    if self.download_queue.empty() and self._all_downloaded_or_failed():
                        break
                    continue

                # Update state
                self._update_file_state(queued_file, FileState.ENCODING)

                try:
                    # Ensure temp directory exists before encoding
                    if not self._ensure_temp_dir_exists():
                        raise Exception("Temp directory unavailable")

                    # Setup paths
                    local_input = Path(queued_file.local_path)
                    local_output = self.temp_dir / f"encoded_{local_input.stem}.mp4"

                    # Verify local input still exists (might have been deleted)
                    if not local_input.exists():
                        raise Exception(f"Local input file missing: {local_input}")

                    if self.verbose:
                        self.logger.info(f"Encoding: {local_input.name}")

                    # Update encoding row for this worker's task
                    if self._progress and enc_task is not None:
                        self._progress.update(
                            enc_task,
                            description=f"[dim]Encode:[/dim]   {fit_filename(local_input.name.removeprefix('download_'))}",
                            speed="", eta="",
                        )

                    # Call the encoding callback, passing progress handle if available
                    try:
                        success = self.encode_callback(
                            local_input, local_output,
                            self._progress, enc_task,
                        )
                    except TypeError:
                        # Fallback for callbacks that don't accept progress args
                        success = self.encode_callback(local_input, local_output)

                    if success and local_output.exists():
                        # Update queued file
                        queued_file.output_path = str(local_output)

                        # Determine final network destination
                        source = Path(queued_file.source_path)
                        if self.replace_original:
                            # Replace original with .mp4 extension
                            queued_file.final_path = str(source.with_suffix('.mp4'))
                        else:
                            # Add _reencoded suffix
                            queued_file.final_path = str(source.parent / f"{source.stem}_reencoded.mp4")

                        # Add to upload queue
                        self.upload_queue.put(queued_file)

                        if self.verbose:
                            self.logger.info(f"Encoded: {local_input.name}")

                        # Clean up local input (no longer needed)
                        local_input.unlink()
                    else:
                        # Build a descriptive error message
                        if not success and local_output.exists():
                            error_msg = "Encoding succeeded but output failed validation (duration/dimension mismatch or corruption)"
                        elif not success:
                            error_msg = "FFmpeg encoding failed (check source file integrity)"
                        else:
                            error_msg = "Encoding produced no output file"
                        self.logger.error(f"{local_input.name}: {error_msg}")
                        queued_file.error = error_msg
                        self._update_file_state(queued_file, FileState.FAILED)

                        # Clean up
                        if local_input.exists():
                            local_input.unlink()

                    # Update overall progress (thread-safe)
                    with self._encode_completed_lock:
                        self._encode_completed_count += 1
                        completed_count = self._encode_completed_count
                    if self._progress and self._overall_task is not None:
                        self._progress.update(
                            self._overall_task,
                            completed=completed_count,
                            description=f"Pipeline  {completed_count}/{total}",
                            speed="", eta="",
                        )

                except Exception as e:
                    error_msg = f"Encoding error: {str(e)}"
                    self.logger.error(f"{local_input.name}: {error_msg}")
                    queued_file.error = error_msg
                    self._update_file_state(queued_file, FileState.FAILED)

                    # Clean up
                    if Path(queued_file.local_path).exists():
                        Path(queued_file.local_path).unlink()

                    with self._encode_completed_lock:
                        self._encode_completed_count += 1
                        completed_count = self._encode_completed_count
                    if self._progress and self._overall_task is not None:
                        self._progress.update(
                            self._overall_task,
                            completed=completed_count,
                            description=f"Pipeline  {completed_count}/{total}",
                            speed="", eta="",
                        )

                finally:
                    self.encode_queue.task_done()
                    self.save_state()

                # Reset task display when idle
                if self._progress and enc_task is not None:
                    self._progress.update(
                        enc_task,
                        description="[dim]Encode:[/dim]   idle",
                        completed=0, total=None, speed="", eta=""
                    )

            except Exception as e:
                self.logger.error(f"Encode worker error: {e}")

    def _upload_worker(self) -> None:
        """Worker thread: Uploads completed encodes back to network"""
        while not self.stop_event.is_set():
            try:
                # Get next file to upload (with timeout)
                try:
                    queued_file = self.upload_queue.get(timeout=1)
                except queue.Empty:
                    # Check if we're completely done (encoding finished and no more uploads)
                    if self.encoding_complete.is_set():
                        # Encoding is done, no more items will be added to upload queue
                        break
                    continue

                # Update state
                self._update_file_state(queued_file, FileState.UPLOADING)

                try:
                    output = Path(queued_file.output_path)
                    final = Path(queued_file.final_path)

                    # Verify output file still exists (might have been deleted)
                    if not output.exists():
                        raise Exception(f"Encoded output file missing: {output}")

                    # Update upload status in progress display
                    if self._progress and self._ul_task is not None:
                        self._progress.update(
                            self._ul_task,
                            description=f"[dim]Upload:[/dim]   {fit_filename(final.name)}",
                        )

                    # Copy encoded file to network destination
                    final.parent.mkdir(parents=True, exist_ok=True)

                    # Record file sizes and source duration for reporting & confirmation
                    source = Path(queued_file.source_path)
                    try:
                        queued_file.source_size = source.stat().st_size
                    except OSError:
                        pass  # Source may be on slow network, size is best-effort

                    # Get source duration for confirmation-phase validation
                    if queued_file.source_duration is None:
                        queued_file.source_duration = self._get_duration(source)
                    local_output_size = output.stat().st_size
                    queued_file.output_size = local_output_size

                    # Try to preserve metadata, but fall back to regular copy if it fails
                    # (Network filesystems often don't support metadata preservation)
                    try:
                        shutil.copy2(output, final)
                    except (OSError, PermissionError) as e:
                        if self.verbose:
                            self.logger.debug(f"Metadata preservation failed, using regular copy: {e}")
                        shutil.copy(output, final)

                    # Post-upload validation: verify the uploaded file matches expected size
                    if not final.exists():
                        raise Exception(f"Upload verification failed: {final} does not exist after copy")
                    uploaded_size = final.stat().st_size
                    if uploaded_size != local_output_size:
                        # Size mismatch - network copy may be corrupted/truncated
                        raise Exception(
                            f"Upload verification failed: size mismatch "
                            f"(local={local_output_size}, uploaded={uploaded_size})"
                        )

                    # Clean up local output
                    output.unlink()

                    if self.replace_original:
                        # Deferred replacement: mark as UPLOADED (originals deleted later
                        # in confirm_replacements() after user can review)
                        self._update_file_state(queued_file, FileState.UPLOADED)
                    else:
                        # No replacement needed, we're done
                        self._update_file_state(queued_file, FileState.COMPLETE)

                    # Update upload status to show completion
                    if self._progress and self._ul_task is not None:
                        self._progress.update(
                            self._ul_task,
                            description=f"[dim]Upload:[/dim]   [success]\u2713 {fit_filename(final.name)}[/success]",
                        )

                except Exception as e:
                    error_msg = f"Upload failed: {str(e)}"
                    self.logger.error(f"{output.name}: {error_msg}")
                    queued_file.error = error_msg
                    self._update_file_state(queued_file, FileState.FAILED)

                finally:
                    self.upload_queue.task_done()
                    self.save_state()

            except Exception as e:
                self.logger.error(f"Upload worker error: {e}")

    def _should_pause_downloads(self) -> bool:
        """Check if downloads should be paused due to buffer or storage limits"""
        with self.files_lock:
            # Check buffer size (count files in LOCAL state)
            local_count = sum(1 for f in self.files if f.state == FileState.LOCAL)
            if local_count >= self.max_buffer_size:
                return True

            # Check storage limit
            if self.max_temp_size_bytes:
                temp_size = self._get_temp_storage_usage()
                if temp_size >= self.max_temp_size_bytes:
                    if self.verbose:
                        self.logger.warning(f"Temp storage limit reached: {temp_size / 1024**3:.1f}GB")
                    return True

            return False

    def _get_temp_storage_usage(self) -> int:
        """Get current temp directory usage in bytes"""
        total = 0
        for item in self.temp_dir.iterdir():
            if item.is_file():
                total += item.stat().st_size
        return total

    def _all_downloaded_or_failed(self) -> bool:
        """Check if all files have been downloaded or failed"""
        with self.files_lock:
            return all(
                f.state not in [FileState.PENDING, FileState.DOWNLOADING]
                for f in self.files
            )

    def _update_file_state(self, queued_file: QueuedFile, new_state: FileState) -> None:
        """Thread-safe state update"""
        with self.files_lock:
            queued_file.state = new_state

    def _ensure_temp_dir_exists(self) -> bool:
        """
        Ensure temp directory exists, recreating it if deleted.

        Returns:
            True if directory exists or was created, False on error
        """
        try:
            if not self.temp_dir.exists():
                if self.verbose:
                    self.logger.warning(f"Temp directory missing, recreating: {self.temp_dir}")
                self.temp_dir.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            self.logger.error(f"Failed to create temp directory: {e}")
            return False

    def save_state(self) -> None:
        """Persist queue state to disk for resume support"""
        try:
            # Ensure parent directory exists (in case it was deleted)
            if not self._ensure_temp_dir_exists():
                return  # Can't save state if temp dir can't be created

            with self.files_lock:
                state = {
                    'files': [f.to_dict() for f in self.files],
                    'timestamp': time.time()
                }

            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)

        except Exception as e:
            # Log but don't crash - state persistence is best-effort
            self.logger.error(f"Failed to save state: {e}")

    def load_state(self) -> bool:
        """Load queue state from disk for resume support"""
        try:
            if not self.state_file.exists():
                return False

            with open(self.state_file, 'r') as f:
                state = json.load(f)

            with self.files_lock:
                self.files = [QueuedFile.from_dict(f) for f in state['files']]

            # Re-populate queues based on state
            resumed_count = {'pending': 0, 'local': 0, 'encoding': 0, 'uploading': 0, 'complete': 0, 'failed': 0, 're-download': 0}

            for queued_file in self.files:
                if queued_file.state == FileState.COMPLETE:
                    # Already complete, skip
                    resumed_count['complete'] += 1
                    continue
                elif queued_file.state == FileState.FAILED:
                    # Previously failed, could retry but skip for now
                    resumed_count['failed'] += 1
                    continue
                elif queued_file.state == FileState.PENDING:
                    resumed_count['pending'] += 1
                    self.download_queue.put(queued_file)
                elif queued_file.state == FileState.LOCAL:
                    # Validate that local file still exists
                    if queued_file.local_path and Path(queued_file.local_path).exists():
                        resumed_count['local'] += 1
                        self.encode_queue.put(queued_file)
                    else:
                        # Local file missing, need to re-download
                        resumed_count['re-download'] += 1
                        if self.verbose:
                            self.logger.info(f"Local file missing for {queued_file.source_path}, re-downloading")
                        queued_file.state = FileState.PENDING
                        queued_file.local_path = None
                        self.download_queue.put(queued_file)
                elif queued_file.state == FileState.ENCODING:
                    # Validate local file exists before resuming encoding
                    if queued_file.local_path and Path(queued_file.local_path).exists():
                        # Resume encoding from LOCAL state (will re-encode)
                        resumed_count['encoding'] += 1
                        queued_file.state = FileState.LOCAL
                        self.encode_queue.put(queued_file)
                    else:
                        # Local file missing, need to re-download
                        resumed_count['re-download'] += 1
                        if self.verbose:
                            self.logger.info(f"Local file missing for {queued_file.source_path}, re-downloading")
                        queued_file.state = FileState.PENDING
                        queued_file.local_path = None
                        self.download_queue.put(queued_file)
                elif queued_file.state == FileState.UPLOADED:
                    # Already uploaded and validated, waiting for confirmation
                    # (originals not yet deleted — will be handled by confirm_replacements)
                    resumed_count['complete'] += 1  # Count as done for pipeline purposes
                elif queued_file.state in [FileState.UPLOADING]:
                    # Resume upload (if output exists)
                    if queued_file.output_path and Path(queued_file.output_path).exists():
                        resumed_count['uploading'] += 1
                        self.upload_queue.put(queued_file)
                    else:
                        # Output missing, check if local input exists
                        if queued_file.local_path and Path(queued_file.local_path).exists():
                            # Can re-encode from existing local file
                            resumed_count['local'] += 1
                            queued_file.state = FileState.LOCAL
                            self.encode_queue.put(queued_file)
                        else:
                            # Need to re-download
                            resumed_count['re-download'] += 1
                            if self.verbose:
                                self.logger.info(f"Files missing for {queued_file.source_path}, re-downloading")
                            queued_file.state = FileState.PENDING
                            queued_file.local_path = None
                            queued_file.output_path = None
                            self.download_queue.put(queued_file)

            # Show resume summary
            section_header("RESUMING QUEUE", f"{len(self.files)} total files")
            if resumed_count['complete'] > 0:
                console.print(f"  Already complete:  [success]{resumed_count['complete']}[/success]")
            if resumed_count['failed'] > 0:
                console.print(f"  Previously failed: [error]{resumed_count['failed']}[/error]")
            if resumed_count['uploading'] > 0:
                console.print(f"  Resuming upload:   [warning]{resumed_count['uploading']}[/warning]")
            if resumed_count['local'] > 0:
                console.print(f"  Resuming encoding: [warning]{resumed_count['local']}[/warning]")
            if resumed_count['encoding'] > 0:
                console.print(f"  Re-encoding:       [warning]{resumed_count['encoding']}[/warning]")
            if resumed_count['pending'] > 0:
                console.print(f"  Pending download:  [info]{resumed_count['pending']}[/info]")
            if resumed_count['re-download'] > 0:
                console.print(f"  Re-downloading:    [info]{resumed_count['re-download']}[/info]")
            console.print()

            return True

        except Exception as e:
            self.logger.error(f"Failed to load state: {e}")
            return False

    def get_progress(self) -> Dict[str, int]:
        """Get current progress statistics"""
        with self.files_lock:
            return {
                'total': len(self.files),
                'pending': sum(1 for f in self.files if f.state == FileState.PENDING),
                'downloading': sum(1 for f in self.files if f.state == FileState.DOWNLOADING),
                'local': sum(1 for f in self.files if f.state == FileState.LOCAL),
                'encoding': sum(1 for f in self.files if f.state == FileState.ENCODING),
                'uploading': sum(1 for f in self.files if f.state == FileState.UPLOADING),
                'uploaded': sum(1 for f in self.files if f.state == FileState.UPLOADED),
                'complete': sum(1 for f in self.files if f.state == FileState.COMPLETE),
                'failed': sum(1 for f in self.files if f.state == FileState.FAILED),
            }

    def get_replacement_report(self) -> List[Dict]:
        """
        Get a report of all files ready for replacement (UPLOADED state).

        Returns:
            List of dicts with: source_path, final_path, source_size, output_size
        """
        report = []
        with self.files_lock:
            for f in self.files:
                if f.state == FileState.UPLOADED:
                    report.append({
                        'source_path': f.source_path,
                        'final_path': f.final_path,
                        'source_size': f.source_size or 0,
                        'output_size': f.output_size or 0,
                    })
        return report

    @staticmethod
    def _get_duration(video_path: Path, timeout: int = 60) -> Optional[float]:
        """Get video duration in seconds via ffprobe. Returns None on failure."""
        try:
            cmd = [
                'ffprobe', '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                str(video_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode != 0:
                return None
            data = json.loads(result.stdout)
            return float(data.get('format', {}).get('duration', 0)) or None
        except Exception:
            return None

    def _validate_uploaded_video(
        self, final_path: Path, source_duration: Optional[float],
        duration_tolerance: float = 2.0
    ) -> Optional[str]:
        """
        Validate an uploaded video on the network before deleting the original.

        Checks:
        1. File exists and size > 1KB
        2. ffprobe can read it and finds a video stream
        3. Duration matches source within tolerance

        Returns:
            None if valid, or an error message string if validation failed.
        """
        if not final_path.exists():
            return f"File does not exist: {final_path}"

        if final_path.stat().st_size < 1024:
            return f"File too small ({final_path.stat().st_size} bytes): {final_path.name}"

        # ffprobe the uploaded file (longer timeout for network paths)
        try:
            cmd = [
                'ffprobe', '-v', 'quiet',
                '-print_format', 'json',
                '-show_format', '-show_streams',
                str(final_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                return f"ffprobe cannot read file: {final_path.name}"

            data = json.loads(result.stdout)

            # Check for video stream
            has_video = any(
                s.get('codec_type') == 'video' for s in data.get('streams', [])
            )
            if not has_video:
                return f"No video stream found: {final_path.name}"

            # Duration check
            if source_duration and source_duration > 0:
                output_duration = float(data.get('format', {}).get('duration', 0))
                if output_duration > 0:
                    diff = abs(output_duration - source_duration)
                    if diff > duration_tolerance:
                        return (
                            f"Duration mismatch: {final_path.name} "
                            f"({output_duration:.1f}s vs source {source_duration:.1f}s, "
                            f"diff={diff:.1f}s)"
                        )

        except subprocess.TimeoutExpired:
            return f"ffprobe timeout (network may be slow): {final_path.name}"
        except Exception as e:
            return f"Validation error: {e}"

        return None  # All checks passed

    def confirm_replacements(self) -> Dict:
        """
        Delete originals for all UPLOADED files, completing the replacement.

        For each UPLOADED file:
        1. Validate the uploaded encoded file (ffprobe, duration check)
        2. Delete the original source file
        3. Mark as COMPLETE
        4. Save state after each deletion (crash-safe)

        Returns:
            Summary dict: {'replaced': int, 'failed': int, 'bytes_freed': int, 'errors': list}
        """
        summary = {'replaced': 0, 'failed': 0, 'bytes_freed': 0, 'errors': []}

        with self.files_lock:
            uploaded_files = [f for f in self.files if f.state == FileState.UPLOADED]

        for queued_file in uploaded_files:
            try:
                source = Path(queued_file.source_path)
                final = Path(queued_file.final_path)

                # Validate uploaded file: existence, ffprobe, duration match
                validation_error = self._validate_uploaded_video(
                    final, queued_file.source_duration
                )
                if validation_error:
                    error_msg = f"Skipping replacement — {validation_error}"
                    self.logger.error(error_msg)
                    queued_file.error = error_msg
                    summary['errors'].append(error_msg)
                    summary['failed'] += 1
                    continue

                # Delete original if it's a different file than the final
                if source.exists() and source != final:
                    source_size = source.stat().st_size
                    source.unlink()
                    summary['bytes_freed'] += source_size
                    if self.verbose:
                        self.logger.info(f"Deleted original: {source.name}")
                elif source.exists() and source == final:
                    # Same path (e.g., .mp4 → .mp4), original is already overwritten
                    pass

                self._update_file_state(queued_file, FileState.COMPLETE)
                summary['replaced'] += 1

                # Save state after each deletion for crash safety
                self.save_state()

            except Exception as e:
                error_msg = f"Failed to replace {queued_file.source_path}: {e}"
                self.logger.error(error_msg)
                queued_file.error = error_msg
                summary['errors'].append(error_msg)
                summary['failed'] += 1
                self.save_state()

        return summary

    def cleanup(self) -> None:
        """Clean up temp directory and state file"""
        try:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
            self.logger.info("Cleaned up temp directory")
        except Exception as e:
            self.logger.error(f"Cleanup failed: {e}")
