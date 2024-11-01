from flask import Flask, request, Response, send_from_directory, render_template_string
import os
import mimetypes
import logging
from pathlib import Path
from typing import Union, BinaryIO
import math

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class Config:
    VIDEO_DIR = "."
    CHUNK_SIZE = 1024 * 1024  # 1MB chunks
    BUFFER_SIZE = 10 * 1024 * 1024  # 10MB buffer
    MAX_CACHE_AGE = 86400  # 24 hours in seconds
    ALLOWED_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.webm'}

app = Flask(__name__)

def get_video_info(path: Path) -> dict:
    """Get video file information"""
    stat = os.stat(path)
    return {
        'name': path.name,
        'size': stat.st_size,
        'modified': stat.st_mtime,
        'mime_type': mimetypes.guess_type(path.name)[0] or 'video/mp4'
    }

def partial_response(
    file: BinaryIO,
    start: int,
    end: int,
    total: int,
    chunk_size: int,
    mime_type: str
) -> Response:
    """Generate partial response for range requests"""
    def generate():
        remaining = end - start + 1
        file.seek(start)
        while remaining:
            chunk = min(chunk_size, remaining)
            data = file.read(chunk)
            if not data:
                break
            remaining -= len(data)
            yield data

    headers = {
        'Content-Type': mime_type,
        'Accept-Ranges': 'bytes',
        'Content-Range': f'bytes {start}-{end}/{total}',
        'Content-Length': end - start + 1,
        'Cache-Control': f'public, max-age={Config.MAX_CACHE_AGE}'
    }

    return Response(
        generate(),
        206,
        headers,
        direct_passthrough=True
    )

def full_response(
    file: BinaryIO,
    total: int,
    chunk_size: int,
    mime_type: str
) -> Response:
    """Generate full file response"""
    def generate():
        remaining = total
        while remaining:
            chunk = min(chunk_size, remaining)
            data = file.read(chunk)
            if not data:
                break
            remaining -= len(data)
            yield data

    headers = {
        'Content-Type': mime_type,
        'Accept-Ranges': 'bytes',
        'Content-Length': total,
        'Cache-Control': f'public, max-age={Config.MAX_CACHE_AGE}'
    }

    return Response(
        generate(),
        200,
        headers,
        direct_passthrough=True
    )

@app.route('/video/<path:filename>')
def stream_video(filename):
    """Stream video with support for range requests"""
    try:
        video_path = Path(Config.VIDEO_DIR) / filename
        if not video_path.exists():
            return {'error': 'Video not found'}, 404

        video_info = get_video_info(video_path)
        total_size = video_info['size']
        mime_type = video_info['mime_type']

        # Open file in binary mode
        file = open(video_path, 'rb')

        # Handle range request
        range_header = request.headers.get('Range')
        if range_header:
            byte_start, byte_end = range_header.replace('bytes=', '').split('-')
            byte_start = int(byte_start)
            byte_end = min(
                int(byte_end) if byte_end else total_size - 1,
                total_size - 1
            )
            return partial_response(
                file,
                byte_start,
                byte_end,
                total_size,
                Config.CHUNK_SIZE,
                mime_type
            )

        # Return full file if no range is requested
        return full_response(
            file,
            total_size,
            Config.CHUNK_SIZE,
            mime_type
        )

    except Exception as e:
        logger.error(f"Error streaming video {filename}: {e}")
        return {'error': str(e)}, 500

@app.route('/api/videos')
def list_videos():
    """List available videos with details"""
    try:
        videos = []
        video_dir = Path(Config.VIDEO_DIR)
        for file in video_dir.glob('*'):
            if file.suffix.lower() in Config.ALLOWED_EXTENSIONS:
                video_info = get_video_info(file)
                videos.append({
                    'name': video_info['name'],
                    'url': f'/video/{file.name}',
                    'size': video_info['size'],
                    'size_formatted': format_size(video_info['size'])
                })
        return {'videos': videos}
    except Exception as e:
        logger.error(f"Error listing videos: {e}")
        return {'error': str(e)}, 500

def format_size(size: int) -> str:
    """Format file size in human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"

# Updated HTML template with video thumbnails and sidebar
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Video Streaming</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 0;
            display: flex;
            background-color: #f5f5f5;
        }
        .sidebar {
            width: 200px;
            background-color: #333;
            color: white;
            padding: 20px;
            height: 100vh;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
        }
        .content {
            flex-grow: 1;
            padding: 20px;
        }
        .video-grid {
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            padding-top: 20px;
        }
        .video-item {
            width: 200px;
            cursor: pointer;
            display: flex;
            flex-direction: column;
            align-items: center;
            background-color: white;
            padding: 10px;
            border-radius: 8px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            text-align: center;
        }
        .video-thumbnail {
            width: 100%;
            height: 100px;
            background-color: #ddd;
            border-radius: 4px;
            margin-bottom: 10px;
        }
        .video-title {
            font-size: 1em;
            color: #333;
        }
        .video-player {
            max-width: 100%;
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <div class="sidebar">
        <h2>Categories</h2>
        <a href="#" style="color: #ccc;">All Videos</a>
        <a href="#" style="color: #ccc;">Favorites</a>
        <a href="#" style="color: #ccc;">Recent</a>
    </div>
    <div class="content">
        <h1>Video Streaming</h1>
        <div class="video-player-container">
            <video id="videoPlayer" class="video-player" controls></video>
        </div>
        <div class="video-grid" id="videoGrid"></div>
    </div>

    <script>
        const videoPlayer = document.getElementById('videoPlayer');
        const videoGrid = document.getElementById('videoGrid');

        async function loadVideos() {
            try {
                const response = await fetch('/api/videos');
                const data = await response.json();
                
                data.videos.forEach(video => {
                    const videoDiv = document.createElement('div');
                    videoDiv.className = 'video-item';
                    videoDiv.onclick = () => {
                        videoPlayer.src = video.url;
                        videoPlayer.play();
                    };
                    videoDiv.innerHTML = `
                        <div class="video-thumbnail"></div>
                        <div class="video-title">${video.name}</div>
                    `;
                    videoGrid.appendChild(videoDiv);
                });

            } catch (error) {
                console.error('Error loading videos:', error);
            }
        }

        loadVideos();
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    """Serve the main page"""
    return render_template_string(HTML_TEMPLATE)

def main():
    """Main entry point"""
    try:
        os.makedirs(Config.VIDEO_DIR, exist_ok=True)
        app.run(
            host='0.0.0.0',
            port=8000,
            threaded=True,
            debug=False
        )
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise

if __name__ == '__main__':
    main()

