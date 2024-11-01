import tkinter as tk
from tkinter import ttk, filedialog
import os
from pathlib import Path
import subprocess

class SimpleMediaPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("Simple Media Player")
        self.root.geometry("600x500")
        
        # Configure styles
        self.style = ttk.Style()
        self.style.configure('Header.TLabel', font=('Helvetica', 11, 'bold'))
        self.style.configure('PlaylistItem.TLabel', font=('Helvetica', 10))
        
        # Variables
        self.playlist = []
        self.current_index = -1
        self.current_process = None
        
        self.setup_ui()

    def setup_ui(self):
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Header
        header_label = ttk.Label(
            main_frame, 
            text="Video Player", 
            style='Header.TLabel'
        )
        header_label.pack(pady=(0, 10))

        # Buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(0, 10))

        # Buttons
        ttk.Button(
            button_frame, 
            text="Open Folder",
            command=self.open_folder,
            width=15
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            button_frame,
            text="Previous",
            command=self.play_previous,
            width=15
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            button_frame,
            text="Next",
            command=self.play_next,
            width=15
        ).pack(side=tk.LEFT, padx=5)

        # Playlist frame with scrollbar
        playlist_frame = ttk.Frame(main_frame)
        playlist_frame.pack(fill=tk.BOTH, expand=True)

        # Scrollbar
        scrollbar = ttk.Scrollbar(playlist_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Playlist
        self.playlist_box = tk.Listbox(
            playlist_frame,
            yscrollcommand=scrollbar.set,
            font=('Helvetica', 10),
            activestyle='none',
            selectmode=tk.SINGLE
        )
        self.playlist_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.playlist_box.yview)

        # Bind double-click event
        self.playlist_box.bind('<Double-Button-1>', self.play_selected_from_list)

        # Status label
        self.status_var = tk.StringVar(value="Ready to play")
        self.status_label = ttk.Label(
            main_frame,
            textvariable=self.status_var,
            style='Header.TLabel'
        )
        self.status_label.pack(pady=(10, 0))

    def open_folder(self):
        folder_path = filedialog.askdirectory()
        if folder_path:
            # Clear current playlist
            self.playlist_box.delete(0, tk.END)
            self.playlist.clear()
            
            # Add all MP4 files to playlist
            for file in sorted(Path(folder_path).glob("*.mp4")):
                self.playlist.append(str(file))
                self.playlist_box.insert(tk.END, file.name)

            self.current_index = -1
            self.status_var.set(f"Found {len(self.playlist)} videos")

    def play_file(self, file_path):
        # Stop any currently playing video
        if self.current_process:
            self.current_process.terminate()
            self.current_process = None

        try:
            # Try different video players
            if os.name == 'posix':  # Linux/Unix
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

            self.status_var.set(f"Playing: {Path(file_path).name}")
            
        except Exception as e:
            self.status_var.set(f"Error playing file")

    def play_selected_from_list(self, event):
        selection = self.playlist_box.curselection()
        if selection:
            self.current_index = selection[0]
            self.play_file(self.playlist[self.current_index])

    def play_next(self):
        if not self.playlist:
            return
            
        self.current_index = (self.current_index + 1) % len(self.playlist)
        self.playlist_box.selection_clear(0, tk.END)
        self.playlist_box.selection_set(self.current_index)
        self.playlist_box.see(self.current_index)
        self.play_file(self.playlist[self.current_index])

    def play_previous(self):
        if not self.playlist:
            return
            
        self.current_index = (self.current_index - 1) % len(self.playlist)
        self.playlist_box.selection_clear(0, tk.END)
        self.playlist_box.selection_set(self.current_index)
        self.playlist_box.see(self.current_index)
        self.play_file(self.playlist[self.current_index])

    def __del__(self):
        if self.current_process:
            self.current_process.terminate()

if __name__ == "__main__":
    root = tk.Tk()
    app = SimpleMediaPlayer(root)
    root.mainloop()
