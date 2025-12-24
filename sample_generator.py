import os
import subprocess
import logging
from video_analyzer import VideoInfo

# Set to store unique permutations of video settings that have been processed
generated_permutations = set()

CODEC_TO_ENCODER = {
    # AV1
    'av1': 'libaom-av1',
    'av01': 'libaom-av1',
    # HEVC
    'hevc': 'libx265',
    'h265': 'libx265',
    'hvc1': 'libx265',
    'hev1': 'libx265',
    # H.264
    'h264': 'libx264',
    'avc1': 'libx264',
    # VP9/VP8
    'vp9': 'libvpx-vp9',
    'vp8': 'libvpx',
    # Flash
    'flv1': 'flv',
    # H.263
    'h263': 'h263',
    # Older Codecs
    'mpeg4': 'mpeg4',
    'mpeg2video': 'mpeg2video',
    'mpeg1video': 'mpeg1video',
    'theora': 'libtheora',
}

ENCODER_TO_EXTENSION = {
    'libaom-av1': 'mp4',
    'libx265': 'mp4',
    'libx264': 'mp4',
    'libvpx-vp9': 'webm',
    'libvpx': 'webm',
    'mpeg4': 'mp4',
    'mpeg2video': 'mpg',
    'mpeg1video': 'mpg',
    'libtheora': 'ogv',
    'flv': 'flv',
    'h263': '3gp',
}


def create_sample_video(video_info: VideoInfo, sample_dir='sample_video_files'):
    """
    Creates a sample video file based on the properties of a given video.

    Args:
        video_info (VideoInfo): A dataclass object containing video metadata.
        sample_dir (str): The directory to save the sample files.
    """
    try:
        codec = video_info.codec
        width = video_info.width
        height = video_info.height
        
        # Get the correct ffmpeg encoder for the given codec
        encoder = CODEC_TO_ENCODER.get(codec)
        if not encoder:
            logging.warning(f"No known encoder for codec '{codec}'. Skipping sample creation.")
            return

        # Get a compatible extension for the chosen encoder
        ext = ENCODER_TO_EXTENSION.get(encoder)
        if not ext:
            logging.warning(f"No known container for encoder '{encoder}'. Skipping sample creation.")
            return

        # Create a unique identifier for the permutation
        permutation = (width, height, codec, ext)
        if not width or not height or permutation in generated_permutations:
            return

        # Generate a descriptive filename
        output_filename = f"sample_{width}x{height}_{codec}.{ext}"
        output_path = os.path.join(sample_dir, output_filename)

        if os.path.exists(output_path):
            logging.debug(f"Sample file already exists: {output_path}")
            generated_permutations.add(permutation)
            return

        # Use a standard sample file as input
        base_sample = os.path.join(sample_dir, '11_h264_main.mp4')
        if not os.path.exists(base_sample):
            logging.error(f"Base sample file not found: {base_sample}")
            return
            
        logging.info(f"Creating sample for permutation: {permutation}")

        # Construct the ffmpeg command
        command = [
            'ffmpeg',
            '-i', base_sample,
            '-vf', f'scale={width}:{height}',
            '-c:v', encoder,
            '-y', # Overwrite output file if it exists
            '-t', '5', # Create a 5-second sample
            output_path
        ]

        # Execute the command
        result = subprocess.run(command, capture_output=True, text=True)

        if result.returncode == 0:
            logging.info(f"Successfully created sample: {output_path}")
            generated_permutations.add(permutation)
        else:
            logging.error(f"Failed to create sample for {permutation}: {result.stderr}")

    except Exception as e:
        logging.error(f"An error occurred in create_sample_video: {e}")

