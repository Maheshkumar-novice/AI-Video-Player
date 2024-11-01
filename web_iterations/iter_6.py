from flask import Flask, request, Response, render_template_string, redirect, url_for
import os
import mimetypes
import logging
from pathlib import Path
from typing import Union, BinaryIO

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class Config:
    VIDEO_DIR = "."
    CHUNK_SIZE = 1024 * 1024
    BUFFER_SIZE = 10 * 1024 * 1024
    MAX_CACHE_AGE = 86400
    ALLOWED_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.webm'}

app = Flask(__name__)

def get_video_info(path: Path):
    """Get video file information"""
    stat = os.stat(path)
    return {
        'name': path.name,
        'size': stat.st_size,
        'modified': stat.st_mtime,
        'mime_type': mimetypes.guess_type(path.name)[0] or 'video/mp4'
    }

def partial_response(file: BinaryIO, start: int, end: int, total: int, chunk_size: int, mime_type: str):
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

    return Response(
        generate(),
        206,
        {
            'Content-Type': mime_type,
            'Accept-Ranges': 'bytes',
            'Content-Range': f'bytes {start}-{end}/{total}',
            'Content-Length': end - start + 1,
            'Cache-Control': f'public, max-age={Config.MAX_CACHE_AGE}'
        },
        direct_passthrough=True
    )

def full_response(file: BinaryIO, total: int, chunk_size: int, mime_type: str):
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

    return Response(
        generate(),
        200,
        {
            'Content-Type': mime_type,
            'Accept-Ranges': 'bytes',
            'Content-Length': total,
            'Cache-Control': f'public, max-age={Config.MAX_CACHE_AGE}'
        },
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

@app.route('/watch/<path:filename>')
def watch_video(filename):
    """Display the video player for the specified video"""
    try:
        video_path = Path(Config.VIDEO_DIR) / filename
        if not video_path.exists():
            return {'error': 'Video not found'}, 404

        video_info = get_video_info(video_path)
        return render_template_string(VIDEO_PLAYER_TEMPLATE, video_info=video_info)
    except Exception as e:
        logger.error(f"Error loading video player for {filename}: {e}")
        return {'error': str(e)}, 500

def format_size(size: int) -> str:
    """Format file size in human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"

@app.route('/')
def index():
    """Render the home page with the video list"""
    try:
        return render_template_string(HOME_PAGE_TEMPLATE)
    except Exception as e:
        logger.error(f"Error loading home page: {e}")
        return {'error': str(e)}, 500

HOME_PAGE_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Video Streaming</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }

        .video-list {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            grid-gap: 20px;
        }

        .video-item {
            cursor: pointer;
        }

        .video-thumbnail {
            width: 100%;
            height: auto;
            max-height: 180px;
            object-fit: cover;
        }

        .video-info {
            padding: 10px;
        }

        .video-name {
            font-weight: bold;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .video-size {
            color: #666;
        }

        @media (max-width: 768px) {
            .video-list {
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="buttons">
            <button id="favoritesButton">Favorites</button>
        </div>
        <div class="video-list" id="videoList"></div>
        <div class="loading" id="loading">Loading videos...</div>
        <div class="error" id="errorMessage" style="display:none"></div>
    </div>

    <script>
        const videoList = document.getElementById('videoList');
        const loading = document.getElementById('loading');
        const errorMessage = document.getElementById('errorMessage');
        const favoritesButton = document.getElementById('favoritesButton');

        let currentPage = 1;
        let isLoading = false;

        function showError(message) {
            errorMessage.textContent = message;
            errorMessage.style.display = 'block';
            setTimeout(() => {
                errorMessage.style.display = 'none';
            }, 5000);
        }

        function loadVideo(videoUrl, videoName) {
            window.location.href = `/watch/${videoName}`;
        }

        async function loadVideos(page = 1) {
            if (isLoading) {
                return;
            }
            isLoading = true;
            loading.style.display = 'block';

            try {
                const response = await fetch(`/api/videos?page=${page}`);
                const data = await response.json();
                data.videos.forEach(video => {
                    const div = document.createElement('div');
                    div.className = 'video-item';
                    div.innerHTML = `
                        <img src="/static/images/${video.name.replace('.mp4', '')}.jpg" alt="${video.name}" class="video-thumbnail">
                        <div class="video-info">
                            <div class="video-name">${video.name}</div>
                            <div class="video-size">${video.size_formatted}</div>
                        </div>
                    `;
                    div.onclick = () => loadVideo(video.url, video.name);
                    videoList.appendChild(div);
                });

                currentPage++;
            } catch (error) {
                showError('Error loading videos: ' + error.message);
            } finally {
                loading.style.display = 'none';
                isLoading = false;
            }
        }

        favoritesButton.addEventListener('click', () => {
            // TODO: Implement favorites functionality
            showError('Favorites feature not yet implemented.');
        });

        loadVideos();

        window.addEventListener('scroll', () => {
            const scrollHeight = document.documentElement.scrollHeight;
            const scrollTop = document.documentElement.scrollTop;
            const clientHeight = document.documentElement.clientHeight;
            if ((scrollTop + clientHeight) >= scrollHeight && !isLoading) {
                loadVideos(currentPage);
            }
        });
    </script>
</body>
</html>
'''

VIDEO_PLAYER_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>{{ video_info.name }} - Video Streaming</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }

        .video-container {
            position: relative;
            width: 100%;
            padding-top: 56.25%;
            background-color: black;
            margin-bottom: 20px;
        }

        .video-container video {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
        }

        @media (max-width: 768px) {
            .container {
                padding: 10px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="buttons">
            <a href="{{ url_for('index') }}">Home</a>
        </div>
        <div class="video-container">
            <video id="videoPlayer" class="video-player" controls>
                <source src="{{ url_for('stream_video', filename=video_info.name) }}" type="{{ video_info.mime_type }}">
                Your browser does not support the video tag.
            </video>
        </div>
    </div>

    <script>
        const videoPlayer = document.getElementById('videoPlayer');

        videoPlayer.addEventListener('error', () => {
            showError('Error playing video. Please try again.');
        });
    </script>
</body>
</html>
'''

def main():
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
