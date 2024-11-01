from flask import Flask, request, Response, render_template_string, redirect, url_for, jsonify
import os
import mimetypes
import logging
from pathlib import Path
from typing import Union, BinaryIO
from datetime import datetime
import json
import random

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
    MAX_CACHE_AGE = 86400  # 24 hours
    ALLOWED_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.webm'}
    ITEMS_PER_PAGE = 12
    ENABLE_COMMENTS = True
    ENABLE_PLAYLISTS = True

app = Flask(__name__)

# Initialize data storage (in a real app, use a database)
COMMENTS_FILE = 'comments.json'
PLAYLISTS_FILE = 'playlists.json'
WATCH_HISTORY_FILE = 'watch_history.json'

def load_json_file(filename, default=None):
    try:
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {filename}: {e}")
    return default if default is not None else {}

def save_json_file(filename, data):
    try:
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving {filename}: {e}")

def get_video_info(path: Path):
    """Get enhanced video file information"""
    stat = os.stat(path)
    return {
        'name': path.name,
        'size': stat.st_size,
        'modified': stat.st_mtime,
        'mime_type': mimetypes.guess_type(path.name)[0] or 'video/mp4',
        # 'duration': get_video_duration(path),  # You'll need to implement this using a library like ffmpeg-python
        'thumbnail': f"/thumbnails/{path.stem}.jpg"
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

@app.route('/api/comments/<filename>', methods=['GET', 'POST'])
def handle_comments(filename):
    """Handle video comments"""
    comments = load_json_file(COMMENTS_FILE, {})
    if filename not in comments:
        comments[filename] = []
    
    if request.method == 'POST':
        comment_data = request.json
        comment = {
            'text': comment_data['text'],
            'timestamp': datetime.now().isoformat(),
            'username': comment_data.get('username', 'Anonymous')
        }
        comments[filename].append(comment)
        save_json_file(COMMENTS_FILE, comments)
        return jsonify(comment)
    
    return jsonify(comments.get(filename, []))

@app.route('/api/playlists', methods=['GET', 'POST'])
def handle_playlists():
    """Handle playlist operations"""
    playlists = load_json_file(PLAYLISTS_FILE, {})
    
    if request.method == 'POST':
        playlist_data = request.json
        playlist_name = playlist_data['name']
        video_name = playlist_data.get('video')
        
        if video_name:
            if playlist_name not in playlists:
                playlists[playlist_name] = []
            if video_name not in playlists[playlist_name]:
                playlists[playlist_name].append(video_name)
        else:
            playlists[playlist_name] = []
            
        save_json_file(PLAYLISTS_FILE, playlists)
    
    return jsonify(playlists)

@app.route('/video/<path:filename>')
def stream_video(filename):
    """Stream video with support for range requests"""
    try:
        video_path = Path(Config.VIDEO_DIR) / filename
        if not video_path.exists():
            return {'error': 'Video not found'}, 404

        # Update watch history
        history = load_json_file(WATCH_HISTORY_FILE, {})
        history[filename] = datetime.now().isoformat()
        save_json_file(WATCH_HISTORY_FILE, history)

        video_info = get_video_info(video_path)
        total_size = video_info['size']
        mime_type = video_info['mime_type']

        file = open(video_path, 'rb')
        range_header = request.headers.get('Range')
        
        if range_header:
            byte_start, byte_end = range_header.replace('bytes=', '').split('-')
            byte_start = int(byte_start)
            byte_end = min(int(byte_end) if byte_end else total_size - 1, total_size - 1)
            return partial_response(file, byte_start, byte_end, total_size, Config.CHUNK_SIZE, mime_type)

        return full_response(file, total_size, Config.CHUNK_SIZE, mime_type)

    except Exception as e:
        logger.error(f"Error streaming video {filename}: {e}")
        return {'error': str(e)}, 500

@app.route('/api/videos')
def list_videos():
    """List available videos with details and pagination"""
    try:
        page = int(request.args.get('page', 1))
        search = request.args.get('search', '').lower()
        
        videos = []
        video_dir = Path(Config.VIDEO_DIR)
        
        for file in video_dir.glob('*'):
            if file.suffix.lower() in Config.ALLOWED_EXTENSIONS:
                if search and search not in file.name.lower():
                    continue
                    
                video_info = get_video_info(file)
                videos.append({
                    'name': video_info['name'],
                    'url': f'/video/{file.name}',
                    'size': video_info['size'],
                    'size_formatted': format_size(video_info['size']),
                    'modified': video_info['modified'],
                    'thumbnail': video_info['thumbnail'],
                    'duration': video_info.get('duration', 'Unknown')
                })

        # Sort videos by modified date
        # videos.sort(key=lambda x: x['modified'], reverse=True)
        random.shuffle(videos)
        
        # Implement pagination
        start_idx = (page - 1) * Config.ITEMS_PER_PAGE
        end_idx = start_idx + Config.ITEMS_PER_PAGE
        paginated_videos = videos[start_idx:end_idx]
        
        return {
            'videos': paginated_videos,
            'total': len(videos),
            'pages': (len(videos) + Config.ITEMS_PER_PAGE - 1) // Config.ITEMS_PER_PAGE
        }
    except Exception as e:
        logger.error(f"Error listing videos: {e}")
        return {'error': str(e)}, 500

@app.route('/watch/<path:filename>')
def watch_video(filename):
    """Display the enhanced video player"""
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
    """Render the enhanced home page"""
    try:
        return render_template_string(HOME_PAGE_TEMPLATE)
    except Exception as e:
        logger.error(f"Error loading home page: {e}")
        return {'error': str(e)}, 500

# Enhanced templates with minified HTML/CSS
HOME_PAGE_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <title>Video Streaming Portal</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        /* Reset and Base Styles */
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        :root {
            --primary: #2563eb;
            --secondary: #1e40af;
            --text: #1f2937;
            --bg: #f3f4f6;
            --card: #fff;
        }

        body {
            font-family: system-ui, -apple-system, sans-serif;
            background: var(--bg);
            color: var(--text);
        }

        /* Layout */
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 1rem;
        }

        /* Header Styles */
        .header {
            background: var(--primary);
            color: #fff;
            padding: 1rem 0;
            margin-bottom: 2rem;
        }

        .header-content {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        /* Search Bar */
        .search-bar {
            background: #fff;
            border-radius: 24px;
            padding: 0.5rem 1rem;
            display: flex;
            align-items: center;
            max-width: 400px;
            margin: 1rem auto;
        }

        .search-bar input {
            width: 100%;
            border: none;
            outline: none;
            padding: 0.5rem;
        }

        /* Video Grid */
        .video-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 1.5rem;
        }

        /* Video Card */
        .video-card {
            cursor: pointer;
            background: var(--card);
            border-radius: 12px;
            overflow: hidden;
            transition: transform 0.2s;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }

        .video-card:hover {
            transform: translateY(-4px);
        }

        .video-thumbnail {
            width: 100%;
            height: 180px;
            object-fit: cover;
        }

        .video-info {
            padding: 1rem;
        }

        .video-title {
            font-weight: 600;
            margin-bottom: 0.5rem;
        }

        .video-meta {
            color: #666;
            font-size: 0.875rem;
        }

        /* Pagination */
        .pagination {
            display: flex;
            justify-content: center;
            gap: 1rem;
            margin: 2rem 0;
        }

        .page-btn {
            padding: 0.5rem 1rem;
            background: var(--primary);
            color: #fff;
            border: none;
            border-radius: 6px;
            cursor: pointer;
        }

        .page-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        /* Playlists Section */
        .playlists {
            margin: 2rem 0;
        }

        .playlist-btn {
            background: var(--secondary);
            color: #fff;
            border: none;
            padding: 0.5rem 1rem;
            border-radius: 6px;
            cursor: pointer;
        }

        /* Loading and Error States */
        .loading {
            text-align: center;
            padding: 2rem;
        }

        .error {
            background: #fee2e2;
            color: #991b1b;
            padding: 1rem;
            border-radius: 6px;
            margin: 1rem 0;
        }

        /* Modal Styles */
        .modal {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 1000;
        }

        .modal-content {
            background: #fff;
            padding: 2rem;
            border-radius: 12px;
            max-width: 600px;
            max-height: 80vh;
            overflow-y: auto;
        }

        .modal h2 {
            margin-bottom: 1rem;
        }

        .modal button {
            margin-top: 1rem;
            padding: 0.5rem 1rem;
            background: var(--primary);
            color: #fff;
            border: none;
            border-radius: 6px;
            cursor: pointer;
        }

        .modal ul {
            list-style: none;
            margin: 1rem 0;
        }

        .modal li {
            padding: 0.5rem 0;
            border-bottom: 1px solid #eee;
        }

        /* Responsive Design */
        @media (max-width: 768px) {
            .header-content {
                flex-direction: column;
                text-align: center;
            }

            .video-grid {
                grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
            }

            .search-bar {
                margin: 1rem;
            }
        }
    </style>
</head>
<body>
    <!-- Header -->
    <header class="header">
        <div class="container header-content">
            <h1>Video Stream</h1>
        </div>
    </header>

    <!-- Main Content -->
    <div class="container">
        <!-- Search Bar -->
        <div class="search-bar">
            <input type="text" id="searchInput" placeholder="Search videos...">
        </div>

        <!-- Playlist Controls -->
        <div class="playlists">
            <button class="playlist-btn" onclick="showPlaylists()">My Playlists</button>
            <button class="playlist-btn" onclick="showHistory()">Watch History</button>
        </div>

        <!-- Video Grid -->
        <div class="video-grid" id="videoGrid"></div>

        <!-- Pagination -->
        <div class="pagination" id="pagination"></div>

        <!-- Loading and Error States -->
        <div class="loading" id="loading">Loading videos...</div>
        <div class="error" id="errorMessage" style="display:none"></div>
    </div>

    <!-- JavaScript -->
    <script>
        const videoGrid = document.getElementById('videoGrid');
        const loading = document.getElementById('loading');
        const errorMessage = document.getElementById('errorMessage');
        const searchInput = document.getElementById('searchInput');
        let currentPage = 1;
        let totalPages = 1;

        // Load videos with search and pagination
        async function loadVideos(page = 1, search = '') {
            loading.style.display = 'block';
            videoGrid.innerHTML = '';

            try {
                const response = await fetch(`/api/videos?page=${page}&search=${search}`);
                const data = await response.json();
                totalPages = data.pages;

                data.videos.forEach(video => {
                    const div = document.createElement('div');
                    div.className = 'video-card';
                    div.innerHTML = `
                        <img src="/static/images/${video.name.replace('.mp4', '')}.jpg" alt="${video.name}" class="video-thumbnail">
                        <div class="video-info">
                            <div class="video-title">${video.name}</div>
                            <div class="video-meta">${video.size_formatted} • ${video.duration}</div>
                        </div>
                    `;
                    div.onclick = () => window.location.href = `/watch/${video.name}`;
                    videoGrid.appendChild(div);
                });

                updatePagination();
            } catch (error) {
                showError('Error loading videos: ' + error.message);
            } finally {
                loading.style.display = 'none';
            }
        }

        // Update pagination controls
        function updatePagination() {
            const pagination = document.getElementById('pagination');
            pagination.innerHTML = '';

            for (let i = 1; i <= totalPages; i++) {
                const button = document.createElement('button');
                button.className = 'page-btn';
                button.textContent = i;
                button.disabled = i === currentPage;
                button.onclick = () => {
                    currentPage = i;
                    loadVideos(i, searchInput.value);
                };
                pagination.appendChild(button);
            }
        }

        // Show error message
        function showError(message) {
            errorMessage.textContent = message;
            errorMessage.style.display = 'block';
            setTimeout(() => {
                errorMessage.style.display = 'none';
            }, 5000);
        }

        // Show playlists modal
        async function showPlaylists() {
            try {
                const response = await fetch('/api/playlists');
                const playlists = await response.json();
                let content = '';

                Object.entries(playlists).forEach(([name, videos]) => {
                    content += `
                        <div>
                            <h3>${name}</h3>
                            <ul>
                                ${videos.map(video => `<li>${video}</li>`).join('')}
                            </ul>
                        </div>
                    `;
                });

                showModal('My Playlists', content);
            } catch (error) {
                showError('Error loading playlists: ' + error.message);
            }
        }

        // Show watch history modal
        async function showHistory() {
            try {
                const response = await fetch('/api/history');
                const history = await response.json();
                let content = '<ul>';

                Object.entries(history).forEach(([video, timestamp]) => {
                    content += `
                        <li>${video} - Last watched: ${new Date(timestamp).toLocaleString()}</li>
                    `;
                });

                content += '</ul>';
                showModal('Watch History', content);
            } catch (error) {
                showError('Error loading watch history: ' + error.message);
            }
        }

        // Show modal dialog
        function showModal(title, content) {
            const modal = document.createElement('div');
            modal.className = 'modal';
            modal.innerHTML = `
                <div class="modal-content">
                    <h2>${title}</h2>
                    ${content}
                    <button onclick="this.closest('.modal').remove()">Close</button>
                </div>
            `;
            document.body.appendChild(modal);
        }

        // Debounce search input
        function debounce(func, wait) {
            let timeout;
            return function (...args) {
                clearTimeout(timeout);
                timeout = setTimeout(() => func.apply(this, args), wait);
            };
        }

        // Add search event listener with debounce
        searchInput.addEventListener('input', debounce(() => {
            currentPage = 1;
            loadVideos(1, searchInput.value);
        }, 300));

        // Initial load
        loadVideos();
    </script>
</body>
</html>
'''

VIDEO_PLAYER_TEMPLATE = '''
<!DOCTYPE html><html lang="en"><head><title>{{ video_info.name }} - Video Streaming</title><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{margin:0;padding:0;box-sizing:border-box}:root{--primary:#2563eb;--secondary:#1e40af;--text:#1f2937;--bg:#f3f4f6}body{font-family:system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text)}.container{max-width:1400px;margin:0 auto;padding:1rem}.header{background:var(--primary);color:#fff;padding:1rem 0;margin-bottom:2rem}.video-container{position:relative;width:100%;max-width:1200px;margin:0 auto;background:#000;aspect-ratio:16/9}.video-player{width:100%;height:100%;outline:none}.controls{display:flex;justify-content:space-between;align-items:center;padding:1rem;background:#fff;border-radius:8px;margin:1rem 0}.control-btn{padding:.5rem 1rem;background:var(--primary);color:#fff;border:none;border-radius:6px;cursor:pointer;margin:0 .5rem}.video-info{background:#fff;padding:1rem;border-radius:8px;margin:1rem 0}.video-title{font-size:1.5rem;font-weight:600;margin-bottom:1rem}.video-meta{color:#666;margin-bottom:1rem}.comments{background:#fff;padding:1rem;border-radius:8px;margin:1rem 0}.comment-form{margin-bottom:1rem}.comment-form textarea{width:100%;padding:.5rem;border:1px solid #ddd;border-radius:4px;margin-bottom:.5rem;resize:vertical}.comment-list{list-style:none}.comment{padding:1rem;border-bottom:1px solid #eee}.comment-header{display:flex;justify-content:space-between;margin-bottom:.5rem}.comment-user{font-weight:600}.comment-time{color:#666;font-size:.875rem}.playlists{margin:1rem 0}.playlist-select{padding:.5rem;border-radius:4px;margin-right:1rem}@media (max-width:768px){.container{padding:.5rem}.controls{flex-wrap:wrap;gap:.5rem}.control-btn{width:calc(50% - 1rem)}}
</style>
</head><body>
<header class="header">
    <div class="container">
        <a href="/" style="color:#fff;text-decoration:none">← Back to Videos</a>
    </div>
</header>
<div class="container">
    <div class="video-container">
        <video id="videoPlayer" class="video-player" controls autoplay>
            <source src="{{ url_for('stream_video', filename=video_info.name) }}" type="{{ video_info.mime_type }}">
            Your browser does not support the video tag.
        </video>
    </div>
    <div class="controls">
        <div>
            <button class="control-btn" onclick="videoPlayer.playbackRate -= 0.25">Speed -</button>
            <button class="control-btn" onclick="videoPlayer.playbackRate += 0.25">Speed +</button>
        </div>
        <div>
            <button class="control-btn" onclick="toggleTheater()">Theater Mode</button>
            <button class="control-btn" onclick="videoPlayer.requestFullscreen()">Fullscreen</button>
        </div>
    </div>
    <div class="video-info">
        <h1 class="video-title">{{ video_info.name }}</h1>
        <div class="video-meta">
            Size: {{ video_info.size_formatted }} • Duration: {{ video_info.duration }}
        </div>
        <div class="playlists">
            <select id="playlistSelect" class="playlist-select">
                <option value="">Add to playlist...</option>
            </select>
            <button class="control-btn" onclick="addToPlaylist()">Add</button>
        </div>
    </div>
    <div class="comments">
        <h2>Comments</h2>
        <form class="comment-form" onsubmit="submitComment(event)">
            <textarea id="commentText" placeholder="Add a comment..." rows="3"></textarea>
            <button type="submit" class="control-btn">Post</button>
        </form>
        <ul id="commentList" class="comment-list"></ul>
    </div>
</div>
<script>
const videoPlayer=document.getElementById("videoPlayer"),commentList=document.getElementById("commentList"),playlistSelect=document.getElementById("playlistSelect");let isTheaterMode=!1;async function loadComments(){try{const e=await fetch(`/api/comments/{{ video_info.name }}`),t=await e.json();commentList.innerHTML="",t.forEach(e=>{const t=document.createElement("li");t.className="comment",t.innerHTML=`<div class="comment-header"><span class="comment-user">${e.username}</span><span class="comment-time">${new Date(e.timestamp).toLocaleString()}</span></div><div class="comment-text">${e.text}</div>`,commentList.appendChild(t)})}catch(e){console.error("Error loading comments:",e)}}async function submitComment(e){e.preventDefault();const t=document.getElementById("commentText"),n=t.value.trim();if(n){try{const e=await fetch(`/api/comments/{{ video_info.name }}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:n})}),o=await e.json();if(e.ok){const e=document.createElement("li");e.className="comment",e.innerHTML=`<div class="comment-header"><span class="comment-user">${o.username}</span><span class="comment-time">${new Date(o.timestamp).toLocaleString()}</span></div><div class="comment-text">${o.text}</div>`,commentList.insertBefore(e,commentList.firstChild),t.value=""}}catch(e){console.error("Error posting comment:",e)}}}async function loadPlaylists(){try{const e=await fetch("/api/playlists"),t=await e.json();Object.keys(t).forEach(e=>{const t=document.createElement("option");t.value=e,t.textContent=e,playlistSelect.appendChild(t)})}catch(e){console.error("Error loading playlists:",e)}}async function addToPlaylist(){const e=playlistSelect.value;if(e)try{await fetch("/api/playlists",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:e,video:"{{ video_info.name }}"})});alert("Added to playlist!")}catch(e){console.error("Error adding to playlist:",e)}}function toggleTheater(){isTheaterMode=!isTheaterMode;const e=document.querySelector(".video-container");isTheaterMode?(e.style.maxWidth="none",e.style.margin="0",e.style.borderRadius="0"):(e.style.maxWidth="1200px",e.style.margin="0 auto",e.style.borderRadius="8px")}videoPlayer.addEventListener("error",()=>{console.error("Video playback error")}),loadComments(),loadPlaylists();
</script>
</body></html>
'''

def main():
    try:
        # Ensure required directories exist
        os.makedirs(Config.VIDEO_DIR, exist_ok=True)
        
        # Initialize empty JSON files if they don't exist
        for filename in [COMMENTS_FILE, PLAYLISTS_FILE, WATCH_HISTORY_FILE]:
            if not os.path.exists(filename):
                save_json_file(filename, {})
        
        app.run(
            host='0.0.0.0',
            port=8000,
            threaded=True,
            debug=True
        )
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise

if __name__ == '__main__':
    main()