"""
Page 1: Import - Select Google Takeout ZIP files or folders.
"""

import customtkinter as ctk
from tkinter import filedialog
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

try:
    import windnd
except ImportError:
    windnd = None


class PageImport(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app


        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Title
        self.title_label = ctk.CTkLabel(
            self,
            text="Import Your Google Takeout Files",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        self.title_label.grid(row=0, column=0, pady=(0, 5), sticky="n")

        # Subtitle
        self.subtitle_label = ctk.CTkLabel(
            self,
            text="Add ZIP files or extracted folders from your Google Photos Takeout",
            font=ctk.CTkFont(size=14),
            text_color=("gray40", "gray60")
        )
        self.subtitle_label.grid(row=1, column=0, pady=(0, 20), sticky="n")

        # Drop Zone
        self.drop_zone = ctk.CTkFrame(
            self, 
            border_width=2, 
            border_color="#3B8ED0", 
            fg_color=("gray96", "#1E293B"),
            corner_radius=12
        )
        self.drop_zone.grid(row=2, column=0, sticky="nsew", pady=10)
        self.drop_zone.grid_rowconfigure(1, weight=1)
        self.drop_zone.grid_columnconfigure(0, weight=1)

        self.drop_zone.bind("<Button-1>", self.select_files)

        self.upload_icon = ctk.CTkLabel(
            self.drop_zone, text="[ + ]", font=ctk.CTkFont(size=45)
        )
        self.upload_icon.grid(row=0, column=0, pady=(25, 8))
        self.upload_icon.bind("<Button-1>", self.select_files)

        drop_instruction = "Click to select files or drag & drop here" if windnd else "Click to select files"
        self.drop_text = ctk.CTkLabel(
            self.drop_zone,
            text=drop_instruction,
            font=ctk.CTkFont(size=15, weight="bold")
        )
        self.drop_text.grid(row=1, column=0, pady=8)
        self.drop_text.bind("<Button-1>", self.select_files)

        self.or_label = ctk.CTkLabel(
            self.drop_zone, text="— or select manually —",
            text_color=("gray50", "gray60"),
            font=ctk.CTkFont(size=12)
        )
        self.or_label.grid(row=2, column=0, pady=12)

        # Buttons
        self.btn_frame = ctk.CTkFrame(self.drop_zone, fg_color="transparent")
        self.btn_frame.grid(row=3, column=0, pady=(0, 25))

        self.btn_zip = ctk.CTkButton(
            self.btn_frame, text="Select ZIP Files", width=170, height=40,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#3B8ED0", hover_color="#2A6CA8",
            corner_radius=8, command=self.select_files
        )
        self.btn_zip.pack(side="left", padx=10)

        self.btn_folder = ctk.CTkButton(
            self.btn_frame, text="Select Folders", width=170, height=40,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#27AE60", hover_color="#219A52",
            corner_radius=8, command=self.select_folders
        )
        self.btn_folder.pack(side="left", padx=10)

        # Selected Files Header with count badge
        self.list_header = ctk.CTkFrame(self, fg_color="transparent")
        self.list_header.grid(row=3, column=0, pady=(12, 5), sticky="nw")

        self.list_label = ctk.CTkLabel(
            self.list_header, text="Selected Items",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.list_label.pack(side="left")

        self.count_label = ctk.CTkLabel(
            self.list_header, text="",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray60")
        )
        self.count_label.pack(side="left", padx=(10, 0))

        # Selected Files List
        self.list_frame = ctk.CTkScrollableFrame(self, height=150, corner_radius=10)
        self.list_frame.grid(row=4, column=0, sticky="nsew", pady=5)
        self.list_frame.grid_columnconfigure(0, weight=1)

        self.update_list()

        # Hook windnd drag and drop to the toplevel window
        if windnd is not None:
            try:
                windnd.hook_dropfiles(self.winfo_toplevel(), func=self._on_drop_files)
            except Exception as e:
                logger.error(f"Failed to hook drag and drop: {e}")

    def _on_drop_files(self, files):
        if not self.winfo_viewable():
            return
            
        added = False
        for f in files:
            try:
                if isinstance(f, bytes):
                    try:
                        path_str = f.decode('utf-8')
                    except UnicodeDecodeError:
                        path_str = f.decode('mbcs')
                else:
                    path_str = str(f)
                    
                path = Path(path_str)
                if path.exists() and path not in self.app.app_state["inputs"]:
                    # We accept directories or zip files natively
                    if path.is_dir() or path.suffix.lower() == '.zip':
                        self.app.app_state["inputs"].append(path)
                        added = True
            except Exception as e:
                logger.error(f"Error reading dropped file: {e}")
                
        if added:
            self.after(10, self.update_list)

    def select_files(self, event=None):
        files = filedialog.askopenfilenames(
            title="Select Google Takeout ZIP files",
            filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")]
        )
        if files:
            for f in files:
                path = Path(f)
                if path not in self.app.app_state["inputs"]:
                    self.app.app_state["inputs"].append(path)
            self.update_list()

    def select_folders(self, event=None):
        folder = filedialog.askdirectory(title="Select Takeout Folder")
        if folder:
            path = Path(folder)
            if path not in self.app.app_state["inputs"]:
                self.app.app_state["inputs"].append(path)
            self.update_list()

    def _bind_mousewheel(self, widget):
        """Bind wheel scrolling on nested widgets inside the scrollable list."""
        widget.bind("<MouseWheel>", self._on_mousewheel)
        widget.bind("<Button-4>", self._on_mousewheel)
        widget.bind("<Button-5>", self._on_mousewheel)

        for child in widget.winfo_children():
            self._bind_mousewheel(child)

    def _on_mousewheel(self, event):
        canvas = getattr(self.list_frame, "_parent_canvas", None)
        if canvas is None:
            return None

        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        else:
            delta = -1 * int(event.delta / 120) if event.delta else 0

        if delta:
            canvas.yview_scroll(delta, "units")
        return "break"

    def update_list(self):
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        self._bind_mousewheel(self.list_frame)

        count = len(self.app.app_state["inputs"])

        if not count:
            self.app.enable_next(False)
            self.count_label.configure(text="")
            return

        self.app.enable_next(True)
        self.count_label.configure(text=f"({count})")

        for idx, path in enumerate(self.app.app_state["inputs"]):
            row_frame = ctk.CTkFrame(self.list_frame, fg_color="transparent")
            row_frame.pack(fill="x", padx=5, pady=2)
            row_frame.grid_columnconfigure(1, weight=1)

            icon = "[DIR]" if path.is_dir() else "[ZIP]"
            ctk.CTkLabel(row_frame, text=icon, font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=0, padx=(5, 10))
            ctk.CTkLabel(row_frame, text=str(path), anchor="w",
                        font=ctk.CTkFont(size=12)).grid(row=0, column=1, sticky="ew")
            
            btn_remove = ctk.CTkButton(
                row_frame, text="", width=30, height=28,
                fg_color="transparent", text_color=("#E74C3C", "#FF6B6B"),
                hover_color=("#FFE0E0", "#5C2828"),
                corner_radius=6,
                command=lambda p=path: self.remove_input(p)
            )
            btn_remove.grid(row=0, column=2, padx=(10, 5))
            self._bind_mousewheel(row_frame)

    def remove_input(self, path):
        if path in self.app.app_state["inputs"]:
            self.app.app_state["inputs"].remove(path)
            self.update_list()
