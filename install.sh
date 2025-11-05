#!/bin/bash
# Installation script for VideoSentinel

echo "======================================"
echo "VideoSentinel Installation"
echo "======================================"
echo ""

# Check Python version
echo "Checking Python version..."
python3 --version

if [ $? -ne 0 ]; then
    echo "Error: Python 3 is not installed"
    exit 1
fi

# Check for ffmpeg
echo ""
echo "Checking for ffmpeg..."
if command -v ffmpeg &> /dev/null; then
    echo "ffmpeg is installed:"
    ffmpeg -version | head -n 1
else
    echo "Warning: ffmpeg is not installed"
    echo ""
    echo "Please install ffmpeg:"
    echo "  macOS:   brew install ffmpeg"
    echo "  Ubuntu:  sudo apt-get install ffmpeg"
    echo "  Windows: choco install ffmpeg"
    echo ""
    read -p "Do you want to continue without ffmpeg? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Install Python dependencies
echo ""
echo "Installing Python dependencies..."
pip3 install -r requirements.txt

if [ $? -eq 0 ]; then
    echo ""
    echo "======================================"
    echo "Installation complete!"
    echo "======================================"
    echo ""
    echo "Usage:"
    echo "  python3 video_sentinel.py /path/to/videos"
    echo ""
    echo "For more examples, see example_usage.sh"
else
    echo ""
    echo "Error: Failed to install dependencies"
    exit 1
fi
