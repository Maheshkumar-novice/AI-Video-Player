from flask import Flask, request, Response, render_template_string
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

def format_size(size: int) -> str:
    """Format file size in human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Video Streaming</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f1f1f1;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        .video-container {
            display: none;
            position: relative;
            width: 100%;
            padding-top: 56.25%;
            background-color: black;
            margin-bottom: 20px;
        }
        .video-player {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
        }
        .video-list {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 20px;
        }
        .video-item {
            background-color: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            cursor: pointer;
            overflow: hidden;
        }
        .video-item:hover {
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
        }
        .video-thumbnail {
            width: 100%;
            height: 150px;
            object-fit: cover;
        }
        .video-info {
            padding: 12px;
        }
        .video-name {
            font-weight: bold;
            font-size: 16px;
            margin-bottom: 8px;
        }
        .video-size {
            color: #666;
            font-size: 14px;
        }
        .buttons {
            display: flex;
            justify-content: space-between;
            margin-bottom: 20px;
        }
        .buttons button {
            background-color: #4CAF50;
            color: white;
            border: none;
            padding: 10px 20px;
            text-align: center;
            text-decoration: none;
            display: inline-block;
            font-size: 16px;
            border-radius: 4px;
            cursor: pointer;
        }
        .loading, .error {
            text-align: center;
            padding: 20px;
            color: #666;
        }
        .error {
            color: red;
            background-color: #fee;
            border-radius: 4px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="buttons">
            <button id="homeButton">Home</button>
            <button id="favoritesButton">Favorites</button>
        </div>
        <div class="video-container" id="videoContainer">
            <video id="videoPlayer" class="video-player" controls>
                Your browser does not support the video tag.
            </video>
        </div>
        <div class="video-list" id="videoList"></div>
        <div class="loading" id="loading">Loading videos...</div>
        <div class="error" id="errorMessage" style="display:none"></div>
    </div>

    <script>
        const videoContainer = document.getElementById('videoContainer');
        const videoPlayer = document.getElementById('videoPlayer');
        const videoList = document.getElementById('videoList');
        const loading = document.getElementById('loading');
        const errorMessage = document.getElementById('errorMessage');
        const homeButton = document.getElementById('homeButton');
        const favoritesButton = document.getElementById('favoritesButton');

        let currentPage = 1;
        let isLoading = false;
        let currentVideo = null;

        function showError(message) {
            errorMessage.textContent = message;
            errorMessage.style.display = 'block';
            setTimeout(() => {
                errorMessage.style.display = 'none';
            }, 5000);
        }

        function loadVideo(videoUrl, videoName) {
            videoContainer.style.display = 'block';
            const currentTime = videoPlayer.currentTime;
            const wasPlaying = !videoPlayer.paused;
            videoPlayer.src = videoUrl;
            videoPlayer.load();
            if (wasPlaying) {
                videoPlayer.play().catch(error => {
                    showError('Error playing video: ' + error.message);
                });
            }
            document.title = `Playing: ${videoName}`;
            currentVideo = { url: videoUrl, name: videoName };
        }

        function hideVideo() {
            videoContainer.style.display = 'none';
            videoPlayer.src = '';
            currentVideo = null;
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
                        <img src="/api/placeholder/320/180" alt="${video.name}" class="video-thumbnail">
                        <div class="video-info">
                            <div class="video-name">${video.name}</div>
                            <div class="video-size">${video.size_formatted}</div>
                        </div>
                    `;
                    div.onclick = () => loadVideo(video.url, video.name);
                    videoList.appendChild(div);
                });

                if (data.videos.length > 0 && !currentVideo) {
                    loadVideo(data.videos[0].url, data.videos[0].name);
                }

                currentPage++;
            } catch (error) {
                showError('Error loading videos: ' + error.message);
            } finally {
                loading.style.display = 'none';
                isLoading = false;
            }
        }

        videoPlayer.addEventListener('error', () => {
            showError('Error playing video. Please try again.');
        });

        homeButton.addEventListener('click', () => {
            videoList.innerHTML = '';
            hideVideo();
            loadVideos();
        });

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

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

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
