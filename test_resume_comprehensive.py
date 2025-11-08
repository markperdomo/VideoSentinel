#!/usr/bin/env python3
"""
Comprehensive test for all resume scenarios
"""

import tempfile
import shutil
import time
import json
from pathlib import Path
from network_queue_manager import NetworkQueueManager

def test_all_resume_scenarios():
    """Test resume with all possible file states"""

    print("="*80)
    print("Comprehensive Resume Test - All States")
    print("="*80)
    print()

    with tempfile.TemporaryDirectory() as network_dir, \
         tempfile.TemporaryDirectory() as temp_dir:

        network_dir = Path(network_dir)
        temp_dir = Path(temp_dir)

        # Create 7 test files
        test_files = []
        for i in range(7):
            test_file = network_dir / f"test_{i}.txt"
            test_file.write_text(f"Test file {i}" * 50)
            test_files.append(test_file)

        # Create temp files for some states
        temp_local_3 = temp_dir / 'download_test_3.txt'
        temp_local_3.write_text("Downloaded file 3")

        temp_local_4 = temp_dir / 'download_test_4.txt'
        temp_local_4.write_text("Downloaded file 4")

        temp_output_5 = temp_dir / 'encoded_test_5.mp4'
        temp_output_5.write_text("Encoded output 5")

        state_file = temp_dir / "queue_state.json"

        # Create state with all scenarios
        fake_state = {
            'files': [
                # 0: COMPLETE (skip)
                {
                    'source_path': str(test_files[0]),
                    'local_path': None,
                    'output_path': None,
                    'final_path': str(network_dir / 'test_0_reencoded.mp4'),
                    'state': 'complete',
                    'error': None
                },
                # 1: FAILED (skip)
                {
                    'source_path': str(test_files[1]),
                    'local_path': None,
                    'output_path': None,
                    'final_path': None,
                    'state': 'failed',
                    'error': 'Previous encoding failed'
                },
                # 2: PENDING (download normally)
                {
                    'source_path': str(test_files[2]),
                    'local_path': None,
                    'output_path': None,
                    'final_path': None,
                    'state': 'pending',
                    'error': None
                },
                # 3: LOCAL with existing temp file (encode)
                {
                    'source_path': str(test_files[3]),
                    'local_path': str(temp_local_3),
                    'output_path': None,
                    'final_path': None,
                    'state': 'local',
                    'error': None
                },
                # 4: ENCODING with existing temp file (re-encode)
                {
                    'source_path': str(test_files[4]),
                    'local_path': str(temp_local_4),
                    'output_path': None,
                    'final_path': None,
                    'state': 'encoding',
                    'error': None
                },
                # 5: UPLOADING with existing output (upload)
                {
                    'source_path': str(test_files[5]),
                    'local_path': None,
                    'output_path': str(temp_output_5),
                    'final_path': str(network_dir / 'test_5_reencoded.mp4'),
                    'state': 'uploading',
                    'error': None
                },
                # 6: LOCAL but temp missing (re-download)
                {
                    'source_path': str(test_files[6]),
                    'local_path': str(temp_dir / 'download_test_6.txt'),
                    'output_path': None,
                    'final_path': None,
                    'state': 'local',
                    'error': None
                },
            ],
            'timestamp': time.time()
        }

        with open(state_file, 'w') as f:
            json.dump(fake_state, f, indent=2)

        print("Created state with 7 files:")
        print("  0: COMPLETE → should skip")
        print("  1: FAILED → should skip")
        print("  2: PENDING → should download & encode")
        print("  3: LOCAL (temp exists) → should encode")
        print("  4: ENCODING (temp exists) → should re-encode")
        print("  5: UPLOADING (output exists) → should upload")
        print("  6: LOCAL (temp missing) → should re-download & encode")
        print()

        queue_manager = NetworkQueueManager(
            temp_dir=temp_dir,
            max_buffer_size=3,
            verbose=False
        )

        print("Loading state...")
        loaded = queue_manager.load_state()
        print()

        if not loaded:
            print("❌ FAIL: Failed to load state")
            return False

        def mock_encode(input_path: Path, output_path: Path) -> bool:
            if not input_path.exists():
                print(f"  ❌ ERROR: Input missing: {input_path}")
                return False
            print(f"  Encoding: {input_path.name}")
            time.sleep(0.1)
            shutil.copy(input_path, output_path)
            return True

        print("Processing...")
        print()

        import threading
        def run_queue():
            queue_manager.start(mock_encode)

        queue_thread = threading.Thread(target=run_queue)
        queue_thread.start()
        queue_thread.join(timeout=30)

        if queue_thread.is_alive():
            print("❌ FAIL: Hung!")
            queue_manager.stop()
            return False

        print()
        print("="*80)

        progress = queue_manager.get_progress()
        print("Final Progress:")
        print(f"  Complete: {progress['complete']}")
        print(f"  Failed: {progress['failed']}")
        print()

        # Expected:
        # - 0: Already complete (1)
        # - 1: Already failed (remains failed)
        # - 2: Downloaded & encoded (1 complete)
        # - 3: Encoded (1 complete)
        # - 4: Re-encoded (1 complete)
        # - 5: Uploaded (1 complete)
        # - 6: Re-downloaded & encoded (1 complete)
        # Total: 6 complete, 1 failed

        if progress['complete'] == 6 and progress['failed'] == 1:
            print("✓ PASS: All resume scenarios handled correctly!")
            return True
        else:
            print(f"❌ FAIL: Expected 6 complete, 1 failed")
            print(f"  Got {progress['complete']} complete, {progress['failed']} failed")
            return False

if __name__ == "__main__":
    success = test_all_resume_scenarios()
    exit(0 if success else 1)
