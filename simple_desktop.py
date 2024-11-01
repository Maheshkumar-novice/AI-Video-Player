import tkinter as tk
from tkinter import ttk, filedialog
import os
from pathlib import Path
import subprocess
import random


class SimpleMediaPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("Simple Media Player")
        self.root.geometry("400x500")

        # Playlist variables
        self.playlist = []
        self.current_index = -1
        self.current_process = None
        self.folder_path = None

        self.setup_ui()

    def setup_ui(self):
        # Create main container
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Create playlist listbox
        self.playlist_label = ttk.Label(self.main_frame, text="Playlist:")
        self.playlist_label.pack(fill=tk.X)

        self.playlist_box = tk.Listbox(self.main_frame, selectmode=tk.SINGLE)
        self.playlist_box.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.playlist_box.bind('<Double-Button-1>', lambda e: self.play_selected())

        # Control buttons frame
        self.control_frame = ttk.Frame(self.main_frame)
        self.control_frame.pack(fill=tk.X, pady=5)

        # Create buttons
        self.open_button = ttk.Button(self.control_frame, text="Open Folder", command=self.open_folder)
        self.open_button.pack(side=tk.LEFT, padx=5)

        self.play_button = ttk.Button(self.control_frame, text="Play", command=self.play_selected)
        self.play_button.pack(side=tk.LEFT, padx=5)

        self.prev_button = ttk.Button(self.control_frame, text="Previous", command=self.play_previous)
        self.prev_button.pack(side=tk.LEFT, padx=5)

        self.next_button = ttk.Button(self.control_frame, text="Next", command=self.play_next)
        self.next_button.pack(side=tk.LEFT, padx=5)

        self.shuffle_button = ttk.Button(self.control_frame, text="Shuffle", command=self.shuffle)
        self.shuffle_button.pack(side=tk.LEFT, padx=5)

        # Now Playing label
        self.now_playing_var = tk.StringVar(value="Ready to play")
        self.now_playing_label = ttk.Label(self.main_frame, textvariable=self.now_playing_var, wraplength=380)
        self.now_playing_label.pack(fill=tk.X, pady=10)

    def shuffle(self):
        if not self.folder_path:
            folder_path = filedialog.askdirectory()
            self.folder_path = folder_path

        folder_path = self.folder_path

        self.playlist_box.delete(0, tk.END)
        self.playlist.clear()
        
        videos =list(Path(folder_path).glob("*.mp4"))
        random.shuffle(videos)

        # Add all MP4 files to playlist
        for file in videos:
            self.playlist.append(str(file))
            self.playlist_box.insert(tk.END, file.name)

        self.current_index = -1
        self.now_playing_var.set("Folder loaded. Double-click a file to play.")

    def open_folder(self):
        folder_path = filedialog.askdirectory()
        if folder_path:
            self.folder_path = folder_path

            # Clear current playlist
            self.playlist_box.delete(0, tk.END)
            self.playlist.clear()
            
            # Add all MP4 files to playlist
            for file in sorted(Path(folder_path).glob("*.mp4")):
                self.playlist.append(str(file))
                self.playlist_box.insert(tk.END, file.name)

            self.current_index = -1
            self.now_playing_var.set("Folder loaded. Double-click a file to play.")

    def play_file(self, file_path):
        # Stop any currently playing video
        if self.current_process:
            self.current_process.terminate()
            self.current_process = None

        try:
            # Use different commands based on the operating system
            if os.name == 'posix':  # Linux/Unix
                # Try different video players in order of preference
                players = ['vlc', 'mpv', 'mplayer', 'xdg-open']
                
                for player in players:
                    try:
                        # Check if the player is installed
                        if subprocess.run(['which', player], 
                                       stdout=subprocess.PIPE, 
                                       stderr=subprocess.PIPE).returncode == 0:
                            self.current_process = subprocess.Popen([player, file_path])
                            break
                    except:
                        continue
            else:  # Windows
                os.startfile(file_path)

            self.now_playing_var.set(f"Now playing: {Path(file_path).name}")
            
        except Exception as e:
            self.now_playing_var.set(f"Error playing file: {str(e)}")

    def play_selected(self):
        selection = self.playlist_box.curselection()
        if selection:
            self.current_index = selection[0]
            self.play_file(self.playlist[self.current_index])
            self.playlist_box.selection_clear(0, tk.END)
            self.playlist_box.selection_set(self.current_index)

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
