from flask import Flask, request, Response, render_template_string, redirect, url_for, jsonify
import os
import mimetypes
import logging
from pathlib import Path
from typing import Union, BinaryIO
from datetime import datetime, timedelta
import json
import ffmpeg
import threading
import html
from collections import defaultdict
from urllib.parse import unquote

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
    ITEMS_PER_PAGE = 32
    ENABLE_COMMENTS = True
    ENABLE_PLAYLISTS = True
    DURATION_CACHE_FILE = 'duration_cache.json'

app = Flask(__name__)

# Initialize data storage
COMMENTS_FILE = 'comments.json'
PLAYLISTS_FILE = 'playlists.json'
WATCH_HISTORY_FILE = 'watch_history.json'
DURATION_CACHE = {}
duration_cache_lock = threading.Lock()

def convert_duration(duration):
    # Split the duration by ':' to get hours, minutes, and seconds
    parts = duration.split(':')
    hours, minutes, seconds = map(int, parts)

    # Build the readable format based on available time components
    readable_format = []
    if hours > 0:
        readable_format.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        readable_format.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if seconds > 0:
        readable_format.append(f"{seconds} second{'s' if seconds != 1 else ''}")

    # Join the parts into a single string
    return ", ".join(readable_format)

def load_json_file(filename, default=None):
    """Load JSON file with default value"""
    try:
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {filename}: {e}")
    return default if default is not None else {}

def save_json_file(filename, data):
    """Save data to JSON file"""
    try:
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving {filename}: {e}")

def load_duration_cache():
    """Load video duration cache from file"""
    global DURATION_CACHE
    try:
        if os.path.exists(Config.DURATION_CACHE_FILE):
            with open(Config.DURATION_CACHE_FILE, 'r') as f:
                DURATION_CACHE = json.load(f)
    except Exception as e:
        logger.error(f"Error loading duration cache: {e}")
        DURATION_CACHE = {}

def save_duration_cache():
    """Save video duration cache to file"""
    try:
        with open(Config.DURATION_CACHE_FILE, 'w') as f:
            json.dump(DURATION_CACHE, f)
    except Exception as e:
        logger.error(f"Error saving duration cache: {e}")

def get_video_duration(video_path: Path) -> str:
    """Get video duration using ffmpeg"""
    try:
        # Check cache first
        cache_key = str(video_path)
        with duration_cache_lock:
            if cache_key in DURATION_CACHE:
                return DURATION_CACHE[cache_key]

        # Get duration using ffmpeg
        probe = ffmpeg.probe(str(video_path))
        duration_seconds = float(probe['streams'][0]['duration'])
        duration = convert_duration(str(timedelta(seconds=int(duration_seconds))))

        # Cache the result
        with duration_cache_lock:
            DURATION_CACHE[cache_key] = duration
            save_duration_cache()

        return duration
    except Exception as e:
        logger.error(f"Error getting video duration: {e}")
        return "Unknown"

class PlaylistManager:
    def __init__(self):
        self.playlists = defaultdict(list)
        self.load_playlists()

    def load_playlists(self):
        """Load playlists from file"""
        try:
            if os.path.exists(PLAYLISTS_FILE):
                with open(PLAYLISTS_FILE, 'r') as f:
                    self.playlists = defaultdict(list, json.load(f))
        except Exception as e:
            logger.error(f"Error loading playlists: {e}")

    def save_playlists(self):
        """Save playlists to file"""
        try:
            with open(PLAYLISTS_FILE, 'w') as f:
                json.dump(dict(self.playlists), f)
        except Exception as e:
            logger.error(f"Error saving playlists: {e}")

    def create_playlist(self, name: str) -> bool:
        """Create a new playlist"""
        if name not in self.playlists:
            self.playlists[name] = []
            self.save_playlists()
            return True
        return False

    def add_to_playlist(self, name: str, video: str) -> bool:
        """Add video to playlist"""
        if video not in self.playlists[name]:
            self.playlists[name].append(video)
            self.save_playlists()
            return True
        return False

    def remove_from_playlist(self, name: str, video: str) -> bool:
        """Remove video from playlist"""
        if video in self.playlists[name]:
            self.playlists[name].remove(video)
            self.save_playlists()
            return True
        return False

    def get_playlist(self, name: str) -> list:
        """Get playlist contents"""
        return self.playlists[name]

    def get_all_playlists(self) -> dict:
        """Get all playlists"""
        return dict(self.playlists)

    def delete_playlist(self, name: str) -> bool:
        """Delete playlist"""
        if name in self.playlists:
            del self.playlists[name]
            self.save_playlists()
            return True
        return False

playlist_manager = PlaylistManager()

def get_video_info(path: Path):
    """Get enhanced video file information"""
    stat = os.stat(path)
    return {
        'name': path.name,
        'size': stat.st_size,
        'size_formatted': format_size(stat.st_size),
        'modified': stat.st_mtime,
        'modified_formatted': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
        'mime_type': mimetypes.guess_type(path.name)[0] or 'video/mp4',
        'duration': get_video_duration(path),
        'thumbnail': f"/static/images/{html.escape(path.stem)}.jpg"
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

def format_size(size: int) -> str:
    """Format file size in human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"

@app.route('/')
def index():
    """Render the home page"""
    return render_template_string(HOME_PAGE_TEMPLATE)

@app.route('/api/history')
def list_history():
    history = load_json_file(WATCH_HISTORY_FILE, {})
    return history

@app.route('/api/videos')
def list_videos():
    """List available videos with details and pagination"""
    try:
        page = int(request.args.get('page', 1))
        search = request.args.get('search', '').lower()
        playlist = request.args.get('playlist')
        shuffle = request.args.get('shuf')
        
        videos = []
        video_dir = Path(Config.VIDEO_DIR)
        
        # Get videos from playlist if specified
        if playlist:
            playlist_videos = playlist_manager.get_playlist(playlist)
            video_files = [video_dir / html.unescape(unquote(name)) for name in playlist_videos]
            print(video_files)
        else:
            video_files = video_dir.glob('*')
        
        for file in video_files:
            if file.suffix.lower() in Config.ALLOWED_EXTENSIONS:
                if search and search not in file.name.lower():
                    continue
                    
                video_info = get_video_info(file)
                videos.append(video_info)

        # Sort videos by modified date
        if shuffle:
            import random
            random.shuffle(videos)
        else:
            videos.sort(key=lambda x: x['modified'], reverse=True)
        
        # Implement pagination
        start_idx = (page - 1) * Config.ITEMS_PER_PAGE
        end_idx = start_idx + Config.ITEMS_PER_PAGE
        paginated_videos = videos[start_idx:end_idx]
        
        return jsonify({
            'videos': paginated_videos,
            'total': len(videos),
            'pages': (len(videos) + Config.ITEMS_PER_PAGE - 1) // Config.ITEMS_PER_PAGE
        })
    except Exception as e:
        logger.exception(f"Error listing videos: {e}")
        return {'error': str(e)}, 500

@app.route('/api/playlists', methods=['GET', 'POST', 'DELETE'])
def handle_playlists():
    """Handle playlist operations"""
    if request.method == 'GET':
        return jsonify(playlist_manager.get_all_playlists())
    
    elif request.method == 'POST':
        data = request.json
        name = data.get('name')
        video = data.get('video')
        
        if not name:
            return {'error': 'Playlist name required'}, 400
            
        if video:
            success = playlist_manager.add_to_playlist(name, video)
            playlist_manager.load_playlists()
            return {'success': success, 'message': 'Video added to playlist'}
        else:
            success = playlist_manager.create_playlist(name)
            playlist_manager.load_playlists()
            return {'success': success, 'message': 'Playlist created'}
    
    elif request.method == 'DELETE':
        data = request.json
        name = data.get('name')
        video = data.get('video')
        
        if not name:
            return {'error': 'Playlist name required'}, 400
            
        if video:
            success = playlist_manager.remove_from_playlist(name, video)
            return {'success': success, 'message': 'Video removed from playlist'}
        else:
            success = playlist_manager.delete_playlist(name)
            return {'success': success, 'message': 'Playlist deleted'}

@app.route('/api/playlists/<name>')
def get_playlist(name):
    """Get specific playlist contents"""
    playlist = playlist_manager.get_playlist(name)
    if playlist is None:
        return {'error': 'Playlist not found'}, 404
    
    videos = []
    for video_name in playlist:
        video_path = Path(Config.VIDEO_DIR) / video_name
        if video_path.exists():
            videos.append(get_video_info(video_path))
    
    return jsonify(videos)

@app.route('/watch/<path:filename>')
def watch_video(filename):
    """Display the video player"""
    try:
        filename = html.unescape(unquote(filename))
        video_path = Path(Config.VIDEO_DIR) / filename
        if not video_path.exists():
            return {'error': 'Video not found'}, 404

        video_info = get_video_info(video_path)
        playlist_name = request.args.get('playlist')
        
        if playlist_name:
            playlist = playlist_manager.get_playlist(playlist_name)
            try:
                current_index = playlist.index(filename)
                if current_index < len(playlist) - 1:
                    video_info['next_video'] = playlist[current_index + 1]
                    video_info['next_video_url'] = f'/watch/{html.escape(playlist[current_index + 1])}?playlist={playlist_name}'
            except ValueError:
                pass

        return render_template_string(VIDEO_PLAYER_TEMPLATE, video_info=video_info, playlist_name=playlist_name)
    except Exception as e:
        logger.error(f"Error loading video player for {filename}: {e}")
        return {'error': str(e)}, 500

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

# Templates
HOME_PAGE_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <title>Videos That You Like!</title>
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
            --border: #e5e7eb;
            --shadow: rgba(0, 0, 0, 0.1);
        }

        body {
            font-family: system-ui, -apple-system, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
        }

        /* Layout */
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 1rem;
        }

        .header {
            background: white;
            border-bottom: 1px solid var(--border);
            padding: 1rem 0;
            margin-bottom: 2rem;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 1.5rem;
        }

        /* Components */
        .video-card {
            cursor: pointer;
            background: white;
            border-radius: 0.5rem;
            overflow: hidden;
            box-shadow: 0 2px 4px var(--shadow);
            transition: transform 0.2s;
        }

        .video-card:hover {
            transform: translateY(-2px);
        }

        .video-thumbnail {
            width: 100%;
            aspect-ratio: 16/9;
            object-fit: cover;
            background: #ddd;
        }

        .video-info {
            padding: 1rem;
        }

        .video-title {
            font-weight: 400;
            margin-bottom: 0.5rem;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }

        .video-meta {
            font-size: 0.875rem;
            color: #666;
        }

        /* Controls */
        .controls {
            display: flex;
            gap: 1rem;
            margin-bottom: 1.5rem;
            flex-wrap: wrap;
        }

        .controls * {
            font-size: 0.75rem;
        }

        .controls button {
            flex-grow: 1;
        }
        
        .controls input {
            font-size: 1rem;
            padding: 0.5rem 0.5rem;
        }

        input, select, button {
            padding: 0.5rem 1rem;
            border: 1px solid var(--border);
            border-radius: 0.25rem;
            font-size: 1rem;
        }

        button {
            background: var(--primary);
            color: white;
            border: none;
            cursor: pointer;
            transition: background 0.2s;
        }

        button:hover {
            background: var(--secondary);
        }

        /* Pagination */
        .pagination {
            display: flex;
            justify-content: center;
            gap: 0.5rem;
            margin-top: 2rem;
            flex-wrap: wrap;
        }

        .page-button {
            width: 3rem;
            height: 3rem;
            padding: 0.5rem 1rem;
            border: 1px solid var(--border);
            border-radius: 0.25rem;
            background: white;
            cursor: pointer;
        }

        .page-button.active {
            background: var(--primary);
            color: white;
            border-color: var(--primary);
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
    </style>
</head>
<body>
    <main class="container">
        <div class="controls">
            <div>
            <input type="text" id="search" placeholder="Search videos...">
            <select id="playlist-select">
                <option value="">All Videos</option>
            </select>
            </div>
            <button onclick="createPlaylist()">New Playlist</button>
            <button onclick="showHistory()">Watch History</button>
            <button onclick="shuffleVideos()">Shuffle</button>
        </div>

        <div id="videos" class="grid"></div>
        <div id="pagination" class="pagination"></div>
    </main>

    <script>
        let currentPage = 1;
        let totalPages = 1;
        let currentPlaylist = '';

        async function loadVideos(page = 1, search = '', playlist = '', shuffle='') {
            try {
                const response = await fetch(`/api/videos?page=${page}&shuf=${shuffle}&search=${search}&playlist=${playlist}`);
                const data = await response.json();
                
                const videosContainer = document.getElementById('videos');
                videosContainer.innerHTML = '';
                
                data.videos.forEach(video => {
                    const card = document.createElement('div');
                    card.className = 'video-card';
                    card.innerHTML = `
                        <img class="video-thumbnail" src="${video.thumbnail}" alt="${video.name}">
                        <div class="video-info">
                            <div class="video-title">${video.name}</div>
                            <div class="video-meta">
                                ${video.duration} • ${video.size_formatted}
                            </div>
                        </div>
                    `;
                    card.onclick = () => {
                        const url = currentPlaylist ? 
                            `/watch/${encodeURIComponent(video.name)}?playlist=${currentPlaylist}` :
                            `/watch/${encodeURIComponent(video.name)}`;
                        window.location.href = url;
                    };
                    videosContainer.appendChild(card);
                });

                totalPages = data.pages;
                updatePagination();
            } catch (error) {
                console.error('Error loading videos:', error);
            }
        }

        function updatePagination() {
            const pagination = document.getElementById('pagination');
            pagination.innerHTML = '';
            
            for (let i = 1; i <= totalPages; i++) {
                const button = document.createElement('button');
                button.className = `page-button ${i === currentPage ? 'active' : ''}`;
                button.textContent = i;
                button.onclick = () => {
                    currentPage = i;
                    loadVideos(i, document.getElementById('search').value, currentPlaylist);
                };
                pagination.appendChild(button);
            }
        }

        async function loadPlaylists() {
            try {
                const response = await fetch('/api/playlists');
                const playlists = await response.json();
                
                const select = document.getElementById('playlist-select');
                Object.keys(playlists).forEach(name => {
                    const option = document.createElement('option');
                    option.value = name;
                    option.textContent = name;
                    select.appendChild(option);
                });
            } catch (error) {
                console.error('Error loading playlists:', error);
            }
        }

        async function createPlaylist() {
            const name = prompt('Enter playlist name:');
            if (name) {
                try {
                    const response = await fetch('/api/playlists', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({name})
                    });
                    
                    if (response.ok) {
                        location.reload();
                    }
                } catch (error) {
                    console.error('Error creating playlist:', error);
                }
            }
        }

        // Event Listeners
        document.getElementById('search').addEventListener('input', debounce(e => {
            currentPage = 1;
            loadVideos(1, e.target.value, currentPlaylist);
        }, 300));

        document.getElementById('playlist-select').addEventListener('change', e => {
            currentPlaylist = e.target.value;
            currentPage = 1;
            loadVideos(1, document.getElementById('search').value, currentPlaylist);
        });

        function debounce(func, wait) {
            let timeout;
            return function executedFunction(...args) {
                const later = () => {
                    clearTimeout(timeout);
                    func(...args);
                };
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
            };
        }

        // Show error message
        function showError(message) {
            errorMessage.textContent = message;
            errorMessage.style.display = 'block';
            setTimeout(() => {
                errorMessage.style.display = 'none';
            }, 5000);
        }

        function shuffleVideos() {
            loadVideos(1, '', '', shuffle="test");
        }

        // Show watch history modal
        async function showHistory() {
            try {
                const response = await fetch('/api/history');
                const history = await response.json();
                let content = '<ul>';

                Object.entries(history).forEach(([video, timestamp]) => {
                    content += `
                        <li><a href=/watch/${encodeURIComponent(video)}>${video}</a> - Last watched: ${new Date(timestamp).toLocaleString()}</li>
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

        // Initial load
        loadVideos();
        loadPlaylists();
    </script>
</body>
</html>
'''

VIDEO_PLAYER_TEMPLATE = '''
<!DOCTYPE html><html lang="en"><head><title>{{ video_info.name }} - Video Streaming</title><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
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
}

body {
    font-family: system-ui, -apple-system, sans-serif;
    background: var(--bg);
    color: var(--text);
}

.container {
    max-width: 1400px;
    margin: 0 auto;
    padding: 1rem;
}

.header {
    background: var(--primary);
    color: #fff;
}

.video-container {
    position: relative;
    width: 100%;
    max-width: 1200px;
    margin: 0 auto;
    background: #000;
    aspect-ratio: 16 / 9;
}

.video-player {
    width: 100%;
    height: 100%;
    outline: none;
}

.controls {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem;
    background: #fff;
    border-radius: 8px;
    margin: 1rem 0;
}

.in-control {
    display: flex;
    justify-content: space-between;
}

.control-btn {
    padding: 0.5rem 1rem;
    background: var(--primary);
    color: #fff;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    flex-grow: 1;
    margin: 0 0.5rem;
}

.video-info {
    background: #fff;
    padding: 1rem;
    border-radius: 8px;
    margin: 1rem 0;
}

.video-title {
    font-size: 1rem;
    font-weight: 500;
    margin-bottom: 1rem;
}

.video-meta {
    color: #666;
    margin-bottom: 1rem;
}

.comments {
    background: #fff;
    padding: 1rem;
    border-radius: 8px;
    margin: 1rem 0;
}

.comment-form {
    margin-bottom: 1rem;
}

.comment-form textarea {
    width: 100%;
    padding: 0.5rem;
    border: 1px solid #ddd;
    border-radius: 4px;
    margin-bottom: 0.5rem;
    resize: vertical;
}

.comment-list {
    list-style: none;
}

.comment {
    padding: 1rem;
    border-bottom: 1px solid #eee;
}

.comment-header {
    display: flex;
    justify-content: space-between;
    margin-bottom: 0.5rem;
}

.comment-user {
    font-weight: 600;
}

.comment-time {
    color: #666;
    font-size: 0.875rem;
}

.playlists {
    margin: 1rem 0;
}

.playlist-select {
    padding: 0.5rem;
    border-radius: 4px;
    margin: 0.25rem;
}

.playlists button {
    margin: 0.25rem;
}

@media (max-width: 768px) {
    .container {
        padding: 0.5rem;
    }

    .controls {
        flex-wrap: wrap;
        gap: 0.5rem;
    }

    .control-btn {
        margin: 0;
    }
    
    .playlists {
        display: flex;
        flex-wrap: wrap;
    }
    
    .playlist-select {
        flex-grow: 1;
    }
}
</style>
</head><body>
<header class="header">
    <div class="container">
        <a href="/" style="color:#fff;text-decoration:none">← Home</a>
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
        <button class="control-btn" onclick="videoPlayer.playbackRate -= 0.25; document.querySelector('.speed').textContent = videoPlayer.playbackRate + 'x';">Speed -</button>
        <button class="control-btn" onclick="videoPlayer.playbackRate += 0.25; document.querySelector('.speed').textContent = videoPlayer.playbackRate + 'x';">Speed +</button>
        <button class="control-btn" onclick="toggleTheater()">Theater Mode</button>
        <button class="control-btn" onclick="videoPlayer.requestFullscreen()">Fullscreen</button>
    </div>
    <div class="video-info">
        <h1 class="video-title">{{ video_info.name }}</h1>
        <div class="video-meta">
            {{ video_info.size_formatted }} • {{ video_info.duration }} • <span class="speed">1x</span>
        </div>
        <div class="playlists">
            <select id="playlistSelect" class="playlist-select">
                <option value="">Add to playlist...</option>
            </select>
            <button class="control-btn" onclick="addToPlaylist()">Add</button>
            <button class="control-btn" onclick="createPlaylist()">New Playlist</button>
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
async function createPlaylist() {
            const name = prompt('Enter playlist name:');
            if (name) {
                try {
                    const response = await fetch('/api/playlists', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({name})
                    });
                    
                    if (response.ok) {
                        location.reload();
                    }
                } catch (error) {
                    console.error('Error creating playlist:', error);
                }
            }
        }
</script>
</body></html>
'''

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

if __name__ == '__main__':
    try:
        load_duration_cache()

        # Ensure required directories exist
        os.makedirs(Config.VIDEO_DIR, exist_ok=True)

        # Initialize empty JSON files if they don't exist
        for filename in [COMMENTS_FILE, PLAYLISTS_FILE, WATCH_HISTORY_FILE]:
            if not os.path.exists(filename):
                save_json_file(filename, {})

        app.run(
            host='0.0.0.0',
            port=5000,
            threaded=True,
            debug=True
        )
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise
   