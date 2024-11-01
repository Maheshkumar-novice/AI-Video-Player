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
from tkinter import font as tkfont
import platform

class ModernUI:
    # Color scheme
    COLORS = {
        'bg_dark': '#1E1E1E',
        'bg_light': '#2D2D2D',
        'accent': '#007ACC',
        'text': '#FFFFFF',
        'text_secondary': '#BBBBBB',
        'success': '#4CC38A',
        'warning': '#F1FA8C',
        'error': '#FF5555'
    }
    
    # Font configurations
    FONTS = {
        'heading': ('Segoe UI', 12, 'bold'),
        'subheading': ('Segoe UI', 11),
        'body': ('Segoe UI', 10),
        'small': ('Segoe UI', 9)
    }

class ModernMediaPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("Modern Media Player")
        self.root.geometry("1200x800")
        
        # Set system-specific UI scale
        if platform.system() == 'Windows':
            self.root.tk.call('tk', 'scaling', 1.3)
        
        # Configure the root window
        self.root.configure(bg=ModernUI.COLORS['bg_dark'])
        
        # Initialize style
        self.setup_styles()
        
        # Initialize variables
        self.playlist = []
        self.current_index = -1
        self.current_process = None
        self.history_file = Path.home() / '.media_player_history.json'
        self.favorites_file = Path.home() / '.media_player_favorites.json'
        self.load_history()
        self.load_favorites()
        
        # Video entry references
        self.video_entries = {}
        
        # Setup UI
        self.setup_ui()
        
        # Bind global shortcuts
        self.setup_shortcuts()

    def setup_styles(self):
        self.style = ttk.Style()
        
        # Configure common styles
        self.style.configure('Modern.TFrame',
                           background=ModernUI.COLORS['bg_dark'])
        
        self.style.configure('Card.TFrame',
                           background=ModernUI.COLORS['bg_light'],
                           relief='flat')
        
        self.style.configure('Modern.TButton',
                           background=ModernUI.COLORS['accent'],
                           foreground=ModernUI.COLORS['text'],
                           padding=(10, 5),
                           font=ModernUI.FONTS['body'])
        
        self.style.map('Modern.TButton',
                      background=[('active', ModernUI.COLORS['accent'])])
        
        # Custom button styles
        self.style.configure('Icon.TButton',
                           padding=2,
                           font=('Segoe UI', 12))
        
        self.style.configure('Play.TButton',
                           background=ModernUI.COLORS['success'],
                           padding=2,
                           font=('Segoe UI', 12))

    def setup_ui(self):
        # Main container with padding
        self.main_container = ttk.Frame(self.root, style='Modern.TFrame', padding=10)
        self.main_container.pack(fill=tk.BOTH, expand=True)
        
        # Create left sidebar
        self.setup_sidebar()
        
        # Create main content area
        self.setup_main_content()
        
        # Create status bar
        self.setup_status_bar()

    def setup_sidebar(self):
        # Sidebar container
        self.sidebar = ttk.Frame(self.main_container, style='Modern.TFrame', width=300)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        self.sidebar.pack_propagate(False)
        
        # Recent section
        self.setup_recent_section()
        
        # Favorites section
        self.setup_favorites_section()

    def setup_recent_section(self):
        # Recent section header
        recent_header = ttk.Frame(self.sidebar, style='Modern.TFrame')
        recent_header.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(recent_header,
                 text="Recently Played",
                 font=ModernUI.FONTS['heading'],
                 foreground=ModernUI.COLORS['text'],
                 background=ModernUI.COLORS['bg_dark']).pack(side=tk.LEFT)
        
        # Recent items container
        self.recent_frame = ttk.Frame(self.sidebar, style='Modern.TFrame')
        self.recent_frame.pack(fill=tk.X)

    def setup_favorites_section(self):
        # Favorites section header
        fav_header = ttk.Frame(self.sidebar, style='Modern.TFrame')
        fav_header.pack(fill=tk.X, pady=(20, 5))
        
        ttk.Label(fav_header,
                 text="Favorites",
                 font=ModernUI.FONTS['heading'],
                 foreground=ModernUI.COLORS['text'],
                 background=ModernUI.COLORS['bg_dark']).pack(side=tk.LEFT)
        
        # Favorites container
        self.favorites_frame = ttk.Frame(self.sidebar, style='Modern.TFrame')
        self.favorites_frame.pack(fill=tk.X)

    def setup_main_content(self):
        # Main content container
        self.content = ttk.Frame(self.main_container, style='Modern.TFrame')
        self.content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Control bar
        self.setup_control_bar()
        
        # Search bar
        self.setup_search_bar()
        
        # Playlist area
        self.setup_playlist_area()

    def setup_control_bar(self):
        self.control_bar = ttk.Frame(self.content, style='Modern.TFrame')
        self.control_bar.pack(fill=tk.X, pady=(0, 10))
        
        # Control buttons
        buttons = [
            ("Open Folder", self.open_folder, 'Modern.TButton'),
            ("Play", self.play_selected, 'Play.TButton'),
            ("Previous", self.play_previous, 'Modern.TButton'),
            ("Next", self.play_next, 'Modern.TButton')
        ]
        
        for text, command, style in buttons:
            btn = ttk.Button(self.control_bar,
                           text=text,
                           command=command,
                           style=style)
            btn.pack(side=tk.LEFT, padx=5)

    def setup_search_bar(self):
        self.search_frame = ttk.Frame(self.content, style='Card.TFrame', padding=5)
        self.search_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.search_var = tk.StringVar()
        self.search_var.trace('w', self.filter_playlist)
        
        search_entry = ttk.Entry(self.search_frame,
                               textvariable=self.search_var,
                               font=ModernUI.FONTS['body'])
        search_entry.pack(fill=tk.X, padx=5)
        
        ttk.Label(self.search_frame,
                 text="Search",
                 font=ModernUI.FONTS['small'],
                 foreground=ModernUI.COLORS['text_secondary'],
                 background=ModernUI.COLORS['bg_light']).pack(side=tk.LEFT, padx=5)

    def setup_playlist_area(self):
        # Canvas for scrollable playlist
        self.canvas = tk.Canvas(self.content,
                              bg=ModernUI.COLORS['bg_dark'],
                              highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.content,
                                     orient="vertical",
                                     command=self.canvas.yview)
        
        self.playlist_frame = ttk.Frame(self.canvas, style='Modern.TFrame')
        
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.canvas_frame = self.canvas.create_window(
            (0, 0),
            window=self.playlist_frame,
            anchor="nw",
            width=self.canvas.winfo_reqwidth()
        )
        
        # Bind events
        self.playlist_frame.bind("<Configure>", self.on_frame_configure)
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        self.root.bind("<MouseWheel>", self.on_mousewheel)

    def setup_status_bar(self):
        self.status_frame = ttk.Frame(self.root, style='Card.TFrame', padding=5)
        self.status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        self.now_playing_var = tk.StringVar(value="Ready to play")
        self.now_playing_label = ttk.Label(
            self.status_frame,
            textvariable=self.now_playing_var,
            font=ModernUI.FONTS['body'],
            foreground=ModernUI.COLORS['text'],
            background=ModernUI.COLORS['bg_light']
        )
        self.now_playing_label.pack(fill=tk.X, padx=5)

    def setup_shortcuts(self):
        # self.root.bind('<space>', lambda e: self.play_selected())
        self.root.bind('<Left>', lambda e: self.play_previous())
        self.root.bind('<Right>', lambda e: self.play_next())
        self.root.bind('<Control-f>', lambda e: self.search_var.focus())

    def create_recent_entry(self, video_path):
        frame = ttk.Frame(self.recent_frame, style='Card.TFrame')
        frame.pack(fill=tk.X, pady=1, padx=2)
        
        # Add hover effect
        frame.bind('<Enter>', lambda e: frame.configure(style='Card.TFrame'))
        frame.bind('<Leave>', lambda e: frame.configure(style='Card.TFrame'))
        
        name_label = ttk.Label(
            frame,
            text=Path(video_path).name[:30] + "..." if len(Path(video_path).name) > 30 else Path(video_path).name,
            font=ModernUI.FONTS['body'],
            foreground=ModernUI.COLORS['text'],
            background=ModernUI.COLORS['bg_light']
        )
        name_label.pack(side=tk.LEFT, padx=5, pady=5)
        
        play_btn = ttk.Button(
            frame,
            text="▶",
            style='Play.TButton',
            width=3,
            command=lambda: self.play_file(video_path)
        )
        play_btn.pack(side=tk.RIGHT, padx=2, pady=2)

    def create_favorite_entry(self, video_path):
        frame = ttk.Frame(self.favorites_frame, style='Card.TFrame')
        frame.pack(fill=tk.X, pady=1, padx=2)
        
        name_label = ttk.Label(
            frame,
            text=Path(video_path).name[:20] + "..." if len(Path(video_path).name) > 20 else Path(video_path).name,
            font=ModernUI.FONTS['body'],
            foreground=ModernUI.COLORS['text'],
            background=ModernUI.COLORS['bg_light']
        )
        name_label.pack(side=tk.LEFT, padx=5, pady=5)
        
        btn_frame = ttk.Frame(frame, style='Card.TFrame')
        btn_frame.pack(side=tk.RIGHT)
        
        unfav_btn = ttk.Button(
            btn_frame,
            text="♥",
            style='Icon.TButton',
            width=3,
            command=lambda: self.toggle_favorite(video_path)
        )
        unfav_btn.pack(side=tk.RIGHT, padx=2, pady=2)
        
        play_btn = ttk.Button(
            btn_frame,
            text="▶",
            style='Play.TButton',
            width=3,
            command=lambda: self.play_file(video_path)
        )
        play_btn.pack(side=tk.RIGHT, padx=2, pady=2)

    def create_video_entry(self, video_path, parent):
        frame = ttk.Frame(parent, style='Card.TFrame')
        frame.pack(fill=tk.X, pady=2, padx=5)
        
        # Add hover effect
        frame.bind('<Enter>', lambda e: frame.configure(style='Card.TFrame'))
        frame.bind('<Leave>', lambda e: frame.configure(style='Card.TFrame'))
        
        # Info frame
        info_frame = ttk.Frame(frame, style='Card.TFrame', padding=5)
        info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(
            info_frame,
            text=Path(video_path).name,
            font=ModernUI.FONTS['heading'],
            foreground=ModernUI.COLORS['text'],
            background=ModernUI.COLORS['bg_light']
        )
        title_label.pack(anchor='w')
        
        # File info
        info = self.get_quick_video_info(video_path)
        info_text = f"Size: {info['size']} | Modified: {info['modified']} | Last played: {info['last_played']}"
        info_label = ttk.Label(
            info_frame,
            text=info_text,
            font=ModernUI.FONTS['small'],
            foreground=ModernUI.COLORS['text_secondary'],
            background=ModernUI.COLORS['bg_light']
        )
        info_label.pack(anchor='w')
        
        # Button frame
        btn_frame = ttk.Frame(frame, style='Card.TFrame')
        btn_frame.pack(side=tk.RIGHT, padx=5, pady=5)
        
        # Favorite button
        fav_text = "♥" if video_path in self.favorites else "♡"
        fav_btn = ttk.Button(
            btn_frame,
            text=fav_text,
            style='Icon.TButton',
            width=3,
            command=lambda: self.toggle_favorite(video_path)
        )
        fav_btn.pack(side=tk.RIGHT, padx=2)
        
        # Play button
        play_btn = ttk.Button(
            btn_frame,
            text="▶",
            style='Play.TButton',
            width=3,
            command=lambda: self.play_file(video_path)
        )
        play_btn.pack(side=tk.RIGHT, padx=2)
        
        # Continuing from where we left off...
        self.video_entries[video_path] = frame

        # Make the entire frame clickable
        for widget in [frame, info_frame, title_label, info_label]:
            widget.bind('<Button-1>', lambda e, path=video_path: self.play_file(path))

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
        except Exception as e:
            print(f"Error saving history: {e}")

    def load_favorites(self):
        try:
            if self.favorites_file.exists():
                with open(self.favorites_file, 'r') as f:
                    self.favorites = json.load(f)
            else:
                self.favorites = []
        except:
            self.favorites = []

    def save_favorites(self):
        try:
            with open(self.favorites_file, 'w') as f:
                json.dump(self.favorites, f)
        except Exception as e:
            print(f"Error saving favorites: {e}")

    def toggle_favorite(self, video_path):
        if video_path in self.favorites:
            self.favorites.remove(video_path)
        else:
            self.favorites.append(video_path)
        self.save_favorites()
        
        # Update UI
        self.update_recent_and_favorites()
        self.update_video_entry(video_path)

    def update_video_entry(self, video_path):
        if video_path in self.video_entries:
            old_frame = self.video_entries[video_path]
            old_frame.destroy()
            self.create_video_entry(video_path, self.playlist_frame)

    def update_recent_and_favorites(self):
        # Clear current entries
        for widget in self.recent_frame.winfo_children():
            widget.destroy()
        for widget in self.favorites_frame.winfo_children():
            widget.destroy()

        # Update recent
        recent_files = sorted(
            self.history.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        if recent_files:
            for file_path, _ in recent_files:
                if Path(file_path).exists():
                    self.create_recent_entry(file_path)
        else:
            ttk.Label(
                self.recent_frame,
                text="No recent files",
                font=ModernUI.FONTS['body'],
                foreground=ModernUI.COLORS['text_secondary'],
                background=ModernUI.COLORS['bg_dark']
            ).pack(pady=5)

        # Update favorites
        if self.favorites:
            for file_path in self.favorites:
                if Path(file_path).exists():
                    self.create_favorite_entry(file_path)
        else:
            ttk.Label(
                self.favorites_frame,
                text="No favorites yet",
                font=ModernUI.FONTS['body'],
                foreground=ModernUI.COLORS['text_secondary'],
                background=ModernUI.COLORS['bg_dark']
            ).pack(pady=5)

    def get_quick_video_info(self, video_path):
        try:
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
        except Exception as e:
            return {
                'size': 'Unknown',
                'modified': 'Unknown',
                'last_played': 'Never'
            }

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
            
            # Add all video files to playlist
            video_extensions = ('.mp4', '.avi', '.mkv', '.mov', '.wmv')
            import random
            vids = list(Path(folder_path).glob("*.*"))
            random.shuffle(vids)
            for file in vids:
                if file.suffix.lower() in video_extensions:
                    self.playlist.append(str(file))
                    self.create_video_entry(str(file), self.playlist_frame)

            self.current_index = -1
            self.update_status(f"Loaded {len(self.playlist)} videos")
            self.load_favorites()
            self.update_recent_and_favorites()

    def update_status(self, message, message_type='info'):
        colors = {
            'info': ModernUI.COLORS['text'],
            'success': ModernUI.COLORS['success'],
            'error': ModernUI.COLORS['error'],
            'warning': ModernUI.COLORS['warning']
        }
        self.now_playing_var.set(message)
        self.now_playing_label.configure(foreground=colors.get(message_type, ModernUI.COLORS['text']))

    def play_file(self, file_path):
        if self.current_process:
            self.current_process.terminate()
            self.current_process = None

        try:
            # Update history
            self.history[file_path] = datetime.now().timestamp()
            self.save_history()
            self.update_recent_and_favorites()

            # Play the file
            if os.name == 'posix':  # Linux/Mac
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
            else:  # Windows
                os.startfile(file_path)

            self.update_status(f"Now playing: {Path(file_path).name}", 'success')
            self.current_index = self.playlist.index(file_path) if file_path in self.playlist else -1

        except Exception as e:
            self.update_status(f"Error playing file: {str(e)}", 'error')

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

    def on_frame_configure(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def on_canvas_configure(self, event):
        # Update the width of the canvas frame to fit the canvas
        self.canvas.itemconfig(self.canvas_frame, width=event.width)

    def on_mousewheel(self, event):
        self.canvas.yview_scroll(-1 * (event.delta // 120), "units")

    def __del__(self):
        if self.current_process:
            self.current_process.terminate()

if __name__ == "__main__":
    root = tk.Tk()
    
    # Set DPI awareness for Windows
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
    
    app = ModernMediaPlayer(root)
    root.mainloop()
