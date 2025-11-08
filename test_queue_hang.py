#!/usr/bin/env python3
"""
Test script to verify the network queue manager doesn't hang at the end
"""

import tempfile
import shutil
import time
from pathlib import Path
from network_queue_manager import NetworkQueueManager

def test_queue_completes():
    """Test that the queue manager completes without hanging"""

    print("="*80)
    print("Testing Network Queue Manager - No Hang Test")
    print("="*80)
    print()

    # Create temporary directories
    with tempfile.TemporaryDirectory() as network_dir, \
         tempfile.TemporaryDirectory() as temp_dir:

        network_dir = Path(network_dir)
        temp_dir = Path(temp_dir)

        # Create a few small test files
        test_files = []
        for i in range(3):
            test_file = network_dir / f"test_{i}.txt"
            test_file.write_text(f"Test file {i}" * 100)
            test_files.append(test_file)

        print(f"Created {len(test_files)} test files in {network_dir}")
        print(f"Using temp dir: {temp_dir}")
        print()

        # Initialize queue manager
        queue_manager = NetworkQueueManager(
            temp_dir=temp_dir,
            max_buffer_size=2,
            verbose=True
        )

        # Add files to queue
        queue_manager.add_files(test_files)
        print(f"Added {len(test_files)} files to queue")
        print()

        # Define a simple "encoding" callback that just copies the file
        def mock_encode(input_path: Path, output_path: Path) -> bool:
            """Mock encoding - just copies the file with a delay"""
            print(f"  Mock encoding: {input_path.name} -> {output_path.name}")
            time.sleep(0.5)  # Simulate encoding time
            shutil.copy(input_path, output_path)
            return True

        # Start processing with a timeout to detect hangs
        print("Starting queue processing...")
        print()

        start_time = time.time()
        timeout = 30  # 30 seconds should be plenty for 3 small files

        try:
            # Start the queue in a separate check to detect timeout
            import threading

            def run_queue():
                queue_manager.start(mock_encode)

            queue_thread = threading.Thread(target=run_queue)
            queue_thread.start()
            queue_thread.join(timeout=timeout)

            if queue_thread.is_alive():
                print()
                print("❌ FAIL: Queue manager hung! Timeout after 30 seconds")
                queue_manager.stop()
                return False

        except Exception as e:
            print(f"❌ FAIL: Exception occurred: {e}")
            return False

        elapsed = time.time() - start_time

        print()
        print("="*80)
        print(f"✓ PASS: Queue completed successfully in {elapsed:.2f} seconds")
        print("="*80)
        print()

        # Check progress
        progress = queue_manager.get_progress()
        print("Final progress:")
        print(f"  Total: {progress['total']}")
        print(f"  Completed: {progress['complete']}")
        print(f"  Failed: {progress['failed']}")
        print()

        if progress['complete'] == len(test_files):
            print("✓ All files processed successfully")
            return True
        else:
            print(f"❌ Expected {len(test_files)} completed, got {progress['complete']}")
            return False

if __name__ == "__main__":
    success = test_queue_completes()
    exit(0 if success else 1)
