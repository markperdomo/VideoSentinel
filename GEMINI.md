# Gemini Agent Documentation for VideoSentinel

This document provides a guide for the Gemini agent to understand and interact with the `VideoSentinel` project.

## Project Overview

`VideoSentinel` is a command-line utility written in Python for managing and validating large video libraries. Its primary functions include:

-   **Video Analysis**: Detecting video codecs, resolutions, and other metadata.
-   **Codec Validation**: Ensuring videos are encoded with modern codecs like HEVC or AV1.
-   **Re-encoding**: Automatically re-encoding videos that don't meet specified standards.
-   **Duplicate Detection**: Finding duplicate video files using perceptual hashing or filename matching.
-   **Issue Detection**: Identifying corrupted or improperly encoded video files.
-   **Library Statistics**: Providing reports on codec distribution and storage usage.

The tool is designed to be modular, robust (with resume capabilities), and efficient, even offering a network queue mode for processing files on network storage.

## File Architecture

The project is structured into several key Python modules:

-   `video_sentinel.py`: The main entry point for the CLI application. It handles argument parsing and orchestrates the calls to other modules based on user commands.
-   `video_analyzer.py`: Contains functions for extracting video metadata using `ffprobe`.
-   `encoder.py`: Manages the video re-encoding process, including smart quality (CRF) calculation.
-   `duplicate_detector.py`: Implements logic for finding duplicate videos, primarily using perceptual hashing on video frames.
-   `issue_detector.py`: Contains functions to detect encoding issues and file corruption.
-   `network_queue_manager.py`: Implements the 3-stage pipeline (download, encode, upload) for efficient network operations.
-   `stats.py`: Generates statistics about the video library.
-   `shutdown_manager.py`: Handles graceful shutdown of the application.
-   `requirements.txt`: Lists the required Python packages for the project.
-   `install.sh`: The installation script for setting up the environment.
-   `example_usage.sh`: A shell script containing various examples of how to use the tool.

## Setup and Installation

### Prerequisites

-   **Python 3.7+**
-   **FFmpeg**: This is a critical system dependency. It must be installed and available in the system's PATH.
    -   On macOS: `brew install ffmpeg`
    -   On Debian/Ubuntu: `sudo apt-get install ffmpeg`

### Installation Steps

1.  **Clone the repository (if not already done).**
2.  **Install Python dependencies**: Run the `install.sh` script or execute the pip command directly.

    ```bash
    pip install -r requirements.txt
    ```

## Command-Line Usage

The main script is `video_sentinel.py`. All operations are performed through this script using various command-line arguments.

### Base Command

```bash
python video_sentinel.py [PATH_TO_VIDEOS] [OPTIONS]
```

### Key Options

-   `--file-list [PATH]`: Path to a text file containing video file paths (one path per line). This is an alternative to providing directory or file paths directly.
-   `-r`, `--recursive`: Scan directories recursively.
-   `-v`, `--verbose`: Enable verbose output.
-   `--check-specs`: Check if videos conform to modern encoding standards (e.g., HEVC, AV1).
-   `--re-encode`: Re-encode videos that fail the `--check-specs` validation.
-   `--target-codec [h264|hevc|av1]`: Specify the target codec for re-encoding. Defaults to `hevc`.
-   `--find-duplicates`: Find duplicate videos using perceptual hashing.
-   `--duplicate-action [auto-best|interactive|list]`: Action to take on duplicates.
-   `--check-issues`: Scan for common encoding issues and corruption.
-   `--deep-scan`: Perform a full integrity check by decoding entire files (used with `--check-issues`).
-   `--stats`: Display statistics about the video library's codecs and sizes.
-   `--output-dir [PATH]`: Specify a custom directory for output files.
-   `--replace-original`: Replace original files with the processed versions.
-   `--max-files [N]`: Limit the number of files to process.
-   `--create-samples`: Analyze videos in a directory/subdirectory and create sample FFmpeg files using a synthetic test pattern. The filenames reflect codec, resolution, and extension, ensuring unique permutations are stored.

### Common Use-Cases

-   **Process a list of video files from a text file and check their specifications:**
    ```bash
    python video_sentinel.py --file-list /path/to/my_video_list.txt --check-specs
    ```
-   **Analyze a directory recursively and re-encode non-compliant files to HEVC:**
    ```bash
    python video_sentinel.py /path/to/videos -r --check-specs --re-encode
    ```
-   **Find all duplicate videos in a directory:**
    ```bash
    python video_sentinel.py /path/to/videos --find-duplicates
    ```
-   **Perform a deep corruption check on all videos:**
    ```bash
    python video_sentinel.py /path/to/videos -r --check-issues --deep-scan
    ```
-   **Get a statistical breakdown of codecs used in a library:**
    ```bash
    python video_sentinel.py /path/to/videos -r --stats
    ```
-   **Create sample video files for unique codec/resolution combinations found in a directory:**
    ```bash
    python video_sentinel.py /path/to/videos --create-samples
    ```
-   **Re-encode specific file types to AV1 and save them to a different location:**
    ```bash
    python video_sentinel.py /path/to/videos --file-types wmv,avi --check-specs --re-encode --target-codec av1 --output-dir /path/to/converted
    ```
