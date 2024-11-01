# video_server.py
from http.server import HTTPServer, SimpleHTTPRequestHandler
import socketserver
from flask import Flask, send_from_directory, Response, render_template
import os
import argparse
import logging
from pathlib import Path
import mimetypes
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
class Config:
    VIDEO_DIR = "."
    ALLOWED_EXTENSIONS = {'.mp4', '.webm', '.mkv', '.avi', '.mov'}
    CHUNK_SIZE = 1024 * 1024  # 1MB chunks for streaming
    DEFAULT_PORT = 8000

# Simple HTTP Server Implementation
class VideoHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=Config.VIDEO_DIR, **kwargs)
    
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        super().end_headers()

    def do_GET(self):
        try:
            super().do_GET()
        except Exception as e:
            logger.error(f"Error serving request: {e}")
            self.send_error(500, f"Internal server error: {str(e)}")

def run_simple_server(port=Config.DEFAULT_PORT):
    try:
        with socketserver.TCPServer(("", port), VideoHandler) as httpd:
            logger.info(f"Simple server running at http://localhost:{port}")
            httpd.serve_forever()
    except Exception as e:
        logger.error(f"Failed to start simple server: {e}")
        raise

# Flask Server Implementation
app = Flask(__name__)

def get_video_info(filepath):
    """Get video file information"""
    stat = os.stat(filepath)
    return {
        'name': os.path.basename(filepath),
        'size': stat.st_size,
        'modified': stat.st_mtime,
        'url': f'/videos/{os.path.basename(filepath)}'
    }

@app.route('/')
def index():
    """Serve the main page"""
    return render_template('index.html')

@app.route('/videos/<path:filename>')
def serve_video(filename):
    """Stream video file"""
    try:
        video_path = os.path.join(Config.VIDEO_DIR, filename)
        if not os.path.exists(video_path):
            return {'error': 'Video not found'}, 404

        def generate():
            with open(video_path, 'rb') as video:
                while True:
                    chunk = video.read(Config.CHUNK_SIZE)
                    if not chunk:
                        break
                    yield chunk

        mime_type, _ = mimetypes.guess_type(filename)
        return Response(
            generate(),
            mimetype=mime_type or 'video/mp4',
            headers={
                'Content-Disposition': f'inline; filename={filename}',
                'Accept-Ranges': 'bytes'
            }
        )
    except Exception as e:
        logger.error(f"Error serving video {filename}: {e}")
        return {'error': str(e)}, 500

@app.route('/api/playlist')
def video_playlist():
    """Get list of available videos"""
    try:
        videos = []
        for file in os.listdir(Config.VIDEO_DIR):
            if any(file.lower().endswith(ext) for ext in Config.ALLOWED_EXTENSIONS):
                video_path = os.path.join(Config.VIDEO_DIR, file)
                videos.append(get_video_info(video_path))
        return {'videos': videos}
    except Exception as e:
        logger.error(f"Error getting playlist: {e}")
        return {'error': str(e)}, 500

def run_flask_server(port=Config.DEFAULT_PORT):
    """Run the Flask server"""
    try:
        # Ensure video directory exists
        os.makedirs(Config.VIDEO_DIR, exist_ok=True)
        
        # Create templates directory if it doesn't exist
        templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
        os.makedirs(templates_dir, exist_ok=True)
        
        # Create index.html template
        index_template = """
<!DOCTYPE html>
<html>
<head>
    <title>Video Streaming Server</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .video-player {
            width: 100%;
            margin-bottom: 20px;
        }
        video {
            width: 100%;
            max-height: 70vh;
            background-color: #000;
        }
        .video-list {
            margin-top: 20px;
        }
        .video-item {
            padding: 10px;
            margin: 5px 0;
            background-color: #f8f9fa;
            border-radius: 4px;
            cursor: pointer;
            transition: background-color 0.2s;
        }
        .video-item:hover {
            background-color: #e9ecef;
        }
        .error {
            color: red;
            padding: 10px;
            background-color: #fee;
            border-radius: 4px;
            display: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Video Streaming Server</h1>
        <div class="error" id="errorMessage"></div>
        <div class="video-player">
            <video id="videoPlayer" controls>
                <source src="" type="video/mp4">
                Your browser does not support the video tag.
            </video>
        </div>
        <h2>Available Videos</h2>
        <div class="video-list" id="playlist"></div>
    </div>
    
    <script>
        const videoPlayer = document.getElementById('videoPlayer');
        const playlist = document.getElementById('playlist');
        const errorMessage = document.getElementById('errorMessage');

        function showError(message) {
            errorMessage.textContent = message;
            errorMessage.style.display = 'block';
            setTimeout(() => {
                errorMessage.style.display = 'none';
            }, 5000);
        }

        function loadVideo(videoUrl) {
            videoPlayer.src = videoUrl;
            videoPlayer.play().catch(error => {
                showError('Error playing video: ' + error.message);
            });
        }

        function formatFileSize(bytes) {
            const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
            if (bytes === 0) return '0 Byte';
            const i = parseInt(Math.floor(Math.log(bytes) / Math.log(1024)));
            return Math.round(bytes / Math.pow(1024, i), 2) + ' ' + sizes[i];
        }

        function loadPlaylist() {
            fetch('/api/playlist')
                .then(response => response.json())
                .then(data => {
                    playlist.innerHTML = '';
                    data.videos.forEach(video => {
                        const div = document.createElement('div');
                        div.className = 'video-item';
                        div.innerHTML = `
                            ${video.name} (${formatFileSize(video.size)})
                        `;
                        div.onclick = () => loadVideo(video.url);
                        playlist.appendChild(div);
                    });
                    
                    // Load first video automatically
                    if (data.videos.length > 0) {
                        loadVideo(data.videos[0].url);
                    }
                })
                .catch(error => {
                    showError('Error loading playlist: ' + error.message);
                });
        }

        // Initial load
        loadPlaylist();

        // Reload playlist every 30 seconds
        setInterval(loadPlaylist, 30000);
    </script>
</body>
</html>
"""
        
        # Write template file
        template_path = os.path.join(templates_dir, 'index.html')
        with open(template_path, 'w') as f:
            f.write(index_template)
        
        logger.info(f"Flask server running at http://localhost:{port}")
        app.run(host='0.0.0.0', port=port, debug=False)
    except Exception as e:
        logger.error(f"Failed to start Flask server: {e}")
        raise

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Video Streaming Server')
    parser.add_argument('--port', type=int, default=Config.DEFAULT_PORT,
                      help='Port to run the server on')
    parser.add_argument('--simple', action='store_true',
                      help='Use simple HTTP server instead of Flask')
    args = parser.parse_args()

    try:
        # Ensure video directory exists
        os.makedirs(Config.VIDEO_DIR, exist_ok=True)
        
        if args.simple:
            run_simple_server(args.port)
        else:
            run_flask_server(args.port)
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise

if __name__ == '__main__':
    main()
