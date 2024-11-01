import tkinter as tk
from tkinter import ttk, filedialog
import os
from pathlib import Path
import subprocess
import json
from datetime import datetime
import humanize
import threading
from queue import Queue
import time

class ModernMediaPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("Modern Media Player")
        self.root.geometry("800x600")
        self.root.configure(bg='#f0f0f0')

        # Style configuration
        self.style = ttk.Style()
        self.style.configure('Custom.TFrame', background='#f0f0f0')
        self.style.configure('Custom.TButton', padding=5)
        self.style.configure('Title.TLabel', font=('Helvetica', 12, 'bold'))
        self.style.configure('Info.TLabel', font=('Helvetica', 9))
        self.style.configure('VideoFrame.TFrame', background='#ffffff', relief='solid')

        # Playlist variables
        self.playlist = []
        self.current_index = -1
        self.current_process = None
        self.history_file = Path.home() / '.media_player_history.json'
        self.load_history()
        
        # Video entry references
        self.video_entries = {}
        
        self.setup_ui()

    def setup_ui(self):
        # Main container
        self.main_frame = ttk.Frame(self.root, style='Custom.TFrame', padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Top control panel
        self.control_frame = ttk.Frame(self.main_frame, style='Custom.TFrame')
        self.control_frame.pack(fill=tk.X, pady=(0, 10))

        # Buttons with modern styling
        btn_style = {'width': 10, 'style': 'Custom.TButton'}
        self.open_button = ttk.Button(self.control_frame, text="Open Folder", command=self.open_folder, **btn_style)
        self.open_button.pack(side=tk.LEFT, padx=5)

        self.play_button = ttk.Button(self.control_frame, text="Play", command=self.play_selected, **btn_style)
        self.play_button.pack(side=tk.LEFT, padx=5)

        self.prev_button = ttk.Button(self.control_frame, text="Previous", command=self.play_previous, **btn_style)
        self.prev_button.pack(side=tk.LEFT, padx=5)

        self.next_button = ttk.Button(self.control_frame, text="Next", command=self.play_next, **btn_style)
        self.next_button.pack(side=tk.LEFT, padx=5)

        # Search frame
        self.search_frame = ttk.Frame(self.main_frame, style='Custom.TFrame')
        self.search_frame.pack(fill=tk.X, pady=(0, 10))

        self.search_var = tk.StringVar()
        self.search_var.trace('w', self.filter_playlist)
        self.search_entry = ttk.Entry(self.search_frame, textvariable=self.search_var)
        self.search_entry.pack(fill=tk.X, padx=5)
        ttk.Label(self.search_frame, text="Search", style='Info.TLabel').pack(side=tk.LEFT)

        # Create scrollable frame for playlist
        self.canvas = tk.Canvas(self.main_frame, bg='#ffffff')
        self.scrollbar = ttk.Scrollbar(self.main_frame, orient="vertical", command=self.canvas.yview)
        self.playlist_frame = ttk.Frame(self.canvas, style='Custom.TFrame')

        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas_frame = self.canvas.create_window((0, 0), window=self.playlist_frame, anchor="nw")

        # Bind events
        self.playlist_frame.bind("<Configure>", self.on_frame_configure)
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        self.root.bind("<MouseWheel>", self.on_mousewheel)

        # Now Playing label
        self.now_playing_var = tk.StringVar(value="Ready to play")
        self.now_playing_label = ttk.Label(
            self.main_frame, 
            textvariable=self.now_playing_var,
            style='Title.TLabel',
            wraplength=780
        )
        self.now_playing_label.pack(fill=tk.X, pady=10)

    def on_frame_configure(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_frame, width=event.width)

    def on_mousewheel(self, event):
        self.canvas.yview_scroll(-1 * (event.delta // 120), "units")

    def load_history(self):
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r') as f:
                    self.history = json.load(f)
            else:
                self.history = {}
        except:
            self.history = {}

    def save_history(self):
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.history, f)
        except:
            pass

    def get_quick_video_info(self, video_path):
        # Get basic file stats quickly
        stats = Path(video_path).stat()
        size = humanize.naturalsize(stats.st_size)
        modified = datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M')
        last_played = self.history.get(str(video_path), "Never")
        
        if last_played != "Never":
            last_played = datetime.fromtimestamp(last_played).strftime('%Y-%m-%d %H:%M')

        return {
            'size': size,
            'modified': modified,
            'last_played': last_played
        }

    def create_video_entry(self, video_path, parent):
        # Create frame for video entry
        frame = ttk.Frame(parent, style='VideoFrame.TFrame')
        frame.pack(fill=tk.X, pady=2, padx=5)

        # Info frame
        info_frame = ttk.Frame(frame, style='Custom.TFrame')
        info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Title
        title_label = ttk.Label(
            info_frame,
            text=Path(video_path).name,
            style='Title.TLabel'
        )
        title_label.pack(anchor='w')

        # Get quick video info
        info = self.get_quick_video_info(video_path)

        # Info label
        info_text = f"Size: {info['size']} | Modified: {info['modified']} | Last played: {info['last_played']}"
        info_label = ttk.Label(
            info_frame,
            text=info_text,
            style='Info.TLabel'
        )
        info_label.pack(anchor='w')

        # Store reference to frame
        self.video_entries[video_path] = frame

        # Make the whole frame clickable
        for widget in [frame, title_label, info_label]:
            widget.bind('<Button-1>', lambda e, path=video_path: self.play_file(path))
            widget.bind('<Enter>', lambda e: frame.configure(style='VideoFrame.TFrame'))
            widget.bind('<Leave>', lambda e: frame.configure(style='VideoFrame.TFrame'))

    def filter_playlist(self, *args):
        search_term = self.search_var.get().lower()
        
        for video_path in self.playlist:
            entry = self.video_entries.get(video_path)
            if entry:
                if search_term in Path(video_path).name.lower():
                    entry.pack(fill=tk.X, pady=2, padx=5)
                else:
                    entry.pack_forget()

    def open_folder(self):
        folder_path = filedialog.askdirectory()
        if folder_path:
            # Clear current playlist
            self.playlist.clear()
            for widget in self.playlist_frame.winfo_children():
                widget.destroy()
            self.video_entries.clear()
            
            # Add all MP4 files to playlist
            for file in sorted(Path(folder_path).glob("*.mp4")):
                self.playlist.append(str(file))
                self.create_video_entry(str(file), self.playlist_frame)

            self.current_index = -1
            self.now_playing_var.set(f"Loaded {len(self.playlist)} videos. Click any video to play.")

    def play_file(self, file_path):
        # Stop any currently playing video
        if self.current_process:
            self.current_process.terminate()
            self.current_process = None

        try:
            # Update history
            self.history[file_path] = datetime.now().timestamp()
            self.save_history()

            # Try different video players
            if os.name == 'posix':
                players = ['vlc', 'mpv', 'mplayer', 'xdg-open']
                for player in players:
                    try:
                        if subprocess.run(['which', player], 
                                       stdout=subprocess.PIPE, 
                                       stderr=subprocess.PIPE).returncode == 0:
                            self.current_process = subprocess.Popen([player, file_path])
                            break
                    except:
                        continue
            else:
                os.startfile(file_path)

            self.now_playing_var.set(f"Now playing: {Path(file_path).name}")
            self.current_index = self.playlist.index(file_path)
            
        except Exception as e:
            self.now_playing_var.set(f"Error playing file: {str(e)}")

    def play_selected(self):
        if self.current_index >= 0 and self.current_index < len(self.playlist):
            self.play_file(self.playlist[self.current_index])

    def play_next(self):
        if not self.playlist:
            return
        self.current_index = (self.current_index + 1) % len(self.playlist)
        self.play_file(self.playlist[self.current_index])

    def play_previous(self):
        if not self.playlist:
            return
        self.current_index = (self.current_index - 1) % len(self.playlist)
        self.play_file(self.playlist[self.current_index])

    def __del__(self):
        if self.current_process:
            self.current_process.terminate()

if __name__ == "__main__":
    root = tk.Tk()
    app = ModernMediaPlayer(root)
    root.mainloop()
