"""
Main entry point for Google Photos Takeout Fixer.
"""

import sys
import os

# Ensure the root directory is in the Python path
# This allows imports like 'from core.state_db import ...' to work anywhere
root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)


def print_runtime_diagnostics():
    """Print import paths so terminal runs reveal shadowed modules."""
    if os.environ.get("TAKEOUT_FIXER_DEBUG_PATHS", "0") != "1":
        return

    try:
        import core.writer as writer_module
        import ui.pages.page_results as results_module

        print(f"[Runtime] python: {sys.executable}")
        print(f"[Runtime] cwd: {os.getcwd()}")
        print(f"[Runtime] main.py: {os.path.abspath(__file__)}")
        print(f"[Runtime] core.writer: {os.path.abspath(writer_module.__file__)}")
        print(f"[Runtime] page_results: {os.path.abspath(results_module.__file__)}")
    except Exception as exc:
        print(f"[Runtime] Could not print import diagnostics: {exc}")

import threading
import customtkinter as ctk

def show_download_splash(downloader):
    """Show a blocking download splash screen."""
    splash = ctk.CTk()
    splash.title("Downloading Dependencies")
    splash.geometry("400x150")
    splash.resizable(False, False)
    
    # Center window
    splash.update_idletasks()
    width = splash.winfo_width()
    height = splash.winfo_height()
    x = (splash.winfo_screenwidth() // 2) - (width // 2)
    y = (splash.winfo_screenheight() // 2) - (height // 2)
    splash.geometry(f'{width}x{height}+{x}+{y}')
    
    label = ctk.CTkLabel(splash, text="First-time setup: Downloading ExifTool...", font=("Inter", 14))
    label.pack(pady=(20, 10))
    
    progress = ctk.CTkProgressBar(splash, width=300)
    progress.pack(pady=10)
    progress.set(0)
    
    status_label = ctk.CTkLabel(splash, text="Connecting...", font=("Inter", 12), text_color="gray")
    status_label.pack()

    def update_progress(downloaded, total):
        if total > 0:
            percent = downloaded / total
            # Use after() to safely update UI from background thread
            splash.after(0, lambda: progress.set(percent))
            splash.after(0, lambda: status_label.configure(text=f"{downloaded // 1024} KB / {total // 1024} KB"))
        else:
            splash.after(0, lambda: progress.configure(mode="indeterminate"))
            splash.after(0, progress.start)

    def download_thread():
        try:
            downloader.download_and_install(progress_callback=update_progress)
            splash.after(0, splash.destroy)
        except Exception as e:
            err_msg = str(e)
            splash.after(0, lambda msg=err_msg: status_label.configure(text=f"Error: {msg}", text_color="red"))
            # Keep window open so user can see error

    threading.Thread(target=download_thread, daemon=True).start()
    splash.mainloop()

def main():
    print_runtime_diagnostics()
    
    # Ensure ExifTool is installed, downloading with a splash screen if needed
    from core.downloader import ExifToolDownloader
    downloader = ExifToolDownloader()
    if not downloader.is_installed():
        show_download_splash(downloader)

    if not downloader.is_installed():
        print("ExifTool installation failed. Exiting.")
        sys.exit(1)

    # Initialize the CustomTkinter app
    from ui.app import App
    app = App()
    
    # Handle window closing
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    # Start the GUI event loop
    app.mainloop()

if __name__ == "__main__":
    main()
