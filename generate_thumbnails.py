import os
from pathlib import Path
from PIL import Image
import ffmpeg

VIDEO_DIR = "."
THUMBNAIL_DIR = "thumbnails"

def generate_thumbnail(video_path, thumbnail_path):
    """Generate a thumbnail for the given video file"""
    try:
        # Open the video file using ffmpeg
        stream = ffmpeg.input(str(video_path))
        # Take a screenshot at the 5-second mark
        stream = ffmpeg.output(stream, str(thumbnail_path), vframes=1, r=1, ss=5)
        ffmpeg.run(stream)

        # Resize the thumbnail to a fixed size
        thumbnail = Image.open(thumbnail_path)
        thumbnail.thumbnail((320, 180), resample=Image.BICUBIC)
        thumbnail.save(thumbnail_path)
        print(f"Generated thumbnail for {video_path.name}")
    except Exception as e:
        print(f"Error generating thumbnail for {video_path.name}: {e}")

def main():
    # Create the thumbnail directory if it doesn't exist
    Path(THUMBNAIL_DIR).mkdir(parents=True, exist_ok=True)

    # Generate thumbnails for all MP4 files in the video directory
    for video_path in reversed(sorted(Path(VIDEO_DIR).glob('*.mp4'))):
#    for video_path in []:
#        video_path = Path(video_path)
 #       print(video_path)
        thumbnail_path = Path(THUMBNAIL_DIR) / f"{video_path.stem}.jpg"
        if thumbnail_path.exists():
            continue
        generate_thumbnail(video_path, thumbnail_path)

if __name__ == "__main__":
    main()
