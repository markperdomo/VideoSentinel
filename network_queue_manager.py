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


class FileState(Enum):
    """Represents the current state of a file in the pipeline"""
    PENDING = "pending"           # Waiting to be downloaded
    DOWNLOADING = "downloading"   # Currently downloading from network
    LOCAL = "local"               # Downloaded, waiting to encode
    ENCODING = "encoding"         # Currently encoding
    UPLOADING = "uploading"       # Encoded, uploading to network
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
        replace_original: bool = False
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

        # Worker threads
        self.download_thread: Optional[threading.Thread] = None
        self.upload_thread: Optional[threading.Thread] = None

        # State persistence
        self.state_file = self.temp_dir / "queue_state.json"

        # Setup logging
        self.logger = logging.getLogger(__name__)
        if verbose:
            logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

    def add_files(self, source_paths: List[Path]) -> None:
        """Add files to the processing queue"""
        with self.files_lock:
            for path in source_paths:
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
        """
        self.encode_callback = encode_callback

        # Start worker threads
        self.download_thread = threading.Thread(target=self._download_worker, daemon=True)
        self.upload_thread = threading.Thread(target=self._upload_worker, daemon=True)

        self.download_thread.start()
        self.upload_thread.start()

        # Main thread handles encoding (CPU-bound, no benefit to threading)
        self._encode_worker()

        # Wait for all uploads to complete before exiting
        if self.verbose:
            self.logger.info("Encoding complete, waiting for uploads to finish...")

        # Wait for upload queue to drain
        self.upload_queue.join()

        # Give upload thread time to finish processing the last file
        if self.upload_thread.is_alive():
            self.upload_thread.join(timeout=30)

        if self.verbose:
            self.logger.info("All uploads complete")

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
                    continue

                # Update state
                self._update_file_state(queued_file, FileState.DOWNLOADING)

                try:
                    # Copy from network to local temp
                    source = Path(queued_file.source_path)
                    local_path = self.temp_dir / f"download_{source.name}"

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

    def _encode_worker(self) -> None:
        """Main thread worker: Encodes files locally"""
        while not self.stop_event.is_set():
            try:
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
                    # Setup paths
                    local_input = Path(queued_file.local_path)
                    local_output = self.temp_dir / f"encoded_{local_input.stem}.mp4"

                    if self.verbose:
                        self.logger.info(f"Encoding: {local_input.name}")

                    # Call the encoding callback
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
                        error_msg = "Encoding failed or output missing"
                        self.logger.error(f"{local_input.name}: {error_msg}")
                        queued_file.error = error_msg
                        self._update_file_state(queued_file, FileState.FAILED)

                        # Clean up
                        if local_input.exists():
                            local_input.unlink()

                except Exception as e:
                    error_msg = f"Encoding error: {str(e)}"
                    self.logger.error(f"{local_input.name}: {error_msg}")
                    queued_file.error = error_msg
                    self._update_file_state(queued_file, FileState.FAILED)

                    # Clean up
                    if Path(queued_file.local_path).exists():
                        Path(queued_file.local_path).unlink()

                finally:
                    self.encode_queue.task_done()
                    self.save_state()

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
                    # Check if we're completely done
                    if (self.download_queue.empty() and
                        self.encode_queue.empty() and
                        self._all_downloaded_or_failed()):
                        break
                    continue

                # Update state
                self._update_file_state(queued_file, FileState.UPLOADING)

                try:
                    output = Path(queued_file.output_path)
                    final = Path(queued_file.final_path)

                    # Show upload progress (not just in verbose mode)
                    print(f"Uploading: {output.name} -> {final.name}")

                    # Copy encoded file to network destination
                    final.parent.mkdir(parents=True, exist_ok=True)

                    # Try to preserve metadata, but fall back to regular copy if it fails
                    # (Network filesystems often don't support metadata preservation)
                    try:
                        shutil.copy2(output, final)
                    except (OSError, PermissionError) as e:
                        if self.verbose:
                            self.logger.debug(f"Metadata preservation failed, using regular copy: {e}")
                        shutil.copy(output, final)

                    # If replace_original mode, delete the source
                    if self.replace_original:
                        source = Path(queued_file.source_path)
                        if source.exists() and source != final:
                            source.unlink()
                            if self.verbose:
                                self.logger.info(f"Deleted original: {source.name}")

                    # Clean up local output
                    output.unlink()

                    # Mark complete
                    self._update_file_state(queued_file, FileState.COMPLETE)

                    # Show completion (not just in verbose mode)
                    print(f"✓ Uploaded: {final.name}")

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

    def save_state(self) -> None:
        """Persist queue state to disk for resume support"""
        try:
            with self.files_lock:
                state = {
                    'files': [f.to_dict() for f in self.files],
                    'timestamp': time.time()
                }

            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)

        except Exception as e:
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
            for queued_file in self.files:
                if queued_file.state == FileState.PENDING:
                    self.download_queue.put(queued_file)
                elif queued_file.state == FileState.LOCAL:
                    self.encode_queue.put(queued_file)
                elif queued_file.state == FileState.ENCODING:
                    # Resume encoding
                    self.encode_queue.put(queued_file)
                elif queued_file.state in [FileState.UPLOADING]:
                    # Resume upload (if output exists)
                    if queued_file.output_path and Path(queued_file.output_path).exists():
                        self.upload_queue.put(queued_file)
                    else:
                        # Output missing, need to re-encode
                        queued_file.state = FileState.LOCAL
                        self.encode_queue.put(queued_file)

            if self.verbose:
                self.logger.info(f"Resumed from saved state: {len(self.files)} files")

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
                'complete': sum(1 for f in self.files if f.state == FileState.COMPLETE),
                'failed': sum(1 for f in self.files if f.state == FileState.FAILED),
            }

    def cleanup(self) -> None:
        """Clean up temp directory and state file"""
        try:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
            self.logger.info("Cleaned up temp directory")
        except Exception as e:
            self.logger.error(f"Cleanup failed: {e}")
