#!/usr/bin/env python3
"""
Test script to verify the network queue manager resume logic
"""

import tempfile
import shutil
import time
import json
from pathlib import Path
from network_queue_manager import NetworkQueueManager, QueuedFile, FileState

def test_resume_with_missing_files():
    """Test that resume handles missing temp files correctly"""

    print("="*80)
    print("Testing Network Queue Manager - Resume with Missing Temp Files")
    print("="*80)
    print()

    # Create temporary directories
    with tempfile.TemporaryDirectory() as network_dir, \
         tempfile.TemporaryDirectory() as temp_dir:

        network_dir = Path(network_dir)
        temp_dir = Path(temp_dir)

        # Create test files on "network"
        test_files = []
        for i in range(3):
            test_file = network_dir / f"test_{i}.txt"
            test_file.write_text(f"Test file {i}" * 100)
            test_files.append(test_file)

        print(f"Created {len(test_files)} test files in {network_dir}")
        print(f"Using temp dir: {temp_dir}")
        print()

        # Create a fake saved state with files in various states
        state_file = temp_dir / "queue_state.json"

        # Simulate state: one complete, one in LOCAL (but temp file missing), one pending
        fake_state = {
            'files': [
                # File 0: Already complete (should be skipped)
                {
                    'source_path': str(test_files[0]),
                    'local_path': str(temp_dir / 'download_test_0.txt'),
                    'output_path': str(temp_dir / 'encoded_test_0.mp4'),
                    'final_path': str(network_dir / 'test_0_reencoded.mp4'),
                    'state': 'complete',
                    'error': None
                },
                # File 1: In LOCAL state but temp file is missing (should re-download)
                {
                    'source_path': str(test_files[1]),
                    'local_path': str(temp_dir / 'download_test_1.txt'),
                    'output_path': None,
                    'final_path': None,
                    'state': 'local',
                    'error': None
                },
                # File 2: Still pending (should download normally)
                {
                    'source_path': str(test_files[2]),
                    'local_path': None,
                    'output_path': None,
                    'final_path': None,
                    'state': 'pending',
                    'error': None
                }
            ],
            'timestamp': time.time()
        }

        # Write the fake state
        with open(state_file, 'w') as f:
            json.dump(fake_state, f, indent=2)

        print("Created fake saved state:")
        print(f"  File 0: COMPLETE (should skip)")
        print(f"  File 1: LOCAL but temp missing (should re-download)")
        print(f"  File 2: PENDING (should download)")
        print()

        # Initialize queue manager
        queue_manager = NetworkQueueManager(
            temp_dir=temp_dir,
            max_buffer_size=2,
            verbose=False
        )

        # Load state (this is where the bug would occur)
        print("Loading saved state...")
        loaded = queue_manager.load_state()

        if not loaded:
            print("❌ FAIL: Failed to load state")
            return False

        print()
        print("State loaded successfully!")
        print()

        # Define a simple "encoding" callback
        def mock_encode(input_path: Path, output_path: Path) -> bool:
            """Mock encoding - just copies the file"""
            if not input_path.exists():
                print(f"  ❌ ERROR: Input file does not exist: {input_path}")
                return False

            print(f"  Encoding: {input_path.name} -> {output_path.name}")
            time.sleep(0.2)
            shutil.copy(input_path, output_path)
            return True

        # Start processing
        print("Starting queue processing...")
        print()

        start_time = time.time()

        try:
            import threading

            def run_queue():
                queue_manager.start(mock_encode)

            queue_thread = threading.Thread(target=run_queue)
            queue_thread.start()
            queue_thread.join(timeout=30)

            if queue_thread.is_alive():
                print()
                print("❌ FAIL: Queue manager hung!")
                queue_manager.stop()
                return False

        except Exception as e:
            print(f"❌ FAIL: Exception occurred: {e}")
            import traceback
            traceback.print_exc()
            return False

        elapsed = time.time() - start_time

        print()
        print("="*80)
        print(f"✓ Queue completed in {elapsed:.2f} seconds")
        print("="*80)
        print()

        # Check progress
        progress = queue_manager.get_progress()
        print("Final progress:")
        print(f"  Total: {progress['total']}")
        print(f"  Completed: {progress['complete']}")
        print(f"  Failed: {progress['failed']}")
        print()

        # We expect:
        # - File 0: Already complete (1)
        # - File 1: Re-downloaded and encoded (1)
        # - File 2: Downloaded and encoded (1)
        # Total: 3 complete

        if progress['complete'] == 3 and progress['failed'] == 0:
            print("✓ PASS: All files processed correctly!")
            print("  - File 0 was skipped (already complete)")
            print("  - File 1 was re-downloaded (temp missing)")
            print("  - File 2 was downloaded normally")
            return True
        else:
            print(f"❌ FAIL: Expected 3 complete, 0 failed")
            print(f"  Got {progress['complete']} complete, {progress['failed']} failed")
            return False

if __name__ == "__main__":
    success = test_resume_with_missing_files()
    exit(0 if success else 1)
