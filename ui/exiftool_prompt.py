import customtkinter as ctk
import tkinter as tk
from tkinter import ttk

class ExifToolDownloadDialog(ctk.CTkToplevel):
    """Modal dialog showing download progress for ExifTool.
    
    Usage:
        def progress_cb(downloaded, total):
            dialog.update_progress(downloaded, total)
        dialog = ExifToolDownloadDialog(parent)
        success = downloader.ensure_installed(progress_cb)
        dialog.destroy()
    """
    def __init__(self, parent, title="Downloading ExifTool..."):
        super().__init__(parent)
        self.title(title)
        self.geometry("400x120")
        self.resizable(False, False)
        # Make it modal
        self.transient(parent)
        self.grab_set()
        # Center on parent
        self.update_idletasks()
        x = parent.winfo_rootx() + parent.winfo_width() // 2 - 200
        y = parent.winfo_rooty() + parent.winfo_height() // 2 - 60
        self.geometry(f"+{x}+{y}")

        self.progress_var = tk.DoubleVar(value=0)
        self.label = ctk.CTkLabel(self, text="Downloading ExifTool")
        self.label.pack(pady=(20, 5))
        self.progress = ttk.Progressbar(self, variable=self.progress_var, maximum=100)
        self.progress.pack(fill="x", padx=20, pady=5)
        self.percent_label = ctk.CTkLabel(self, text="0%")
        self.percent_label.pack(pady=(5, 10))
        # Cancel button (optional)
        self.cancelled = False
        self.cancel_button = ctk.CTkButton(self, text="Cancel", command=self._cancel)
        self.cancel_button.pack(pady=(0, 10))

    def _cancel(self):
        self.cancelled = True
        # The downloader receives progress_callback; we cannot directly abort download,
        # but we can set a flag that the callback can check if needed.
        # For simplicity, just close the dialog.
        self.destroy()

    def update_progress(self, downloaded: int, total: int):
        if total > 0:
            percent = downloaded / total * 100
            self.progress_var.set(percent)
            self.percent_label.configure(text=f"{percent:.1f}%")
            self.update_idletasks()
