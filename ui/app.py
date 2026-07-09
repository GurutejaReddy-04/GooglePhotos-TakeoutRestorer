"""
Main Application Window and Wizard Controller.
"""

import customtkinter as ctk
from pathlib import Path
import json
import os
import sys
import uuid
import shutil
import time
import logging

logger = logging.getLogger(__name__)

from core.state_db import StateDatabase

from ui.pages.page_welcome import PageWelcome
from ui.pages.page_import import PageImport
from ui.pages.page_destination import PageDestination
from ui.pages.page_settings import PageSettings
from ui.pages.page_confirm import PageConfirm
from ui.pages.page_results import PageResults


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window configuration
        self.title("Google Photos Takeout Restorer")
        self.geometry("1000x750")
        self.minsize(900, 650)

        # Theme Management
        self.current_theme = "System"
        ctk.set_appearance_mode(self.current_theme.lower())
        ctk.set_default_color_theme("blue")

        # Generate unique run ID
        self.run_id = str(uuid.uuid4())[:8]
        
        # Application State
        self.app_state = {
            "inputs": [],
            "destination": None,
            "settings": {
                "gps_enabled": True,
                "timezone_enabled": True,
                "unmatched_enabled": True,
                "anonymous_logging": False,
                "in_place_backup_enabled": True,
                "output_mode": "copy",
                "high_performance": False,
            },
            "config": self._load_config(),
            "db": None,
            "run_id": self.run_id,
            "progress_model": None,
        }

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Header
        self.header_frame = ctk.CTkFrame(self, height=65, corner_radius=0)
        self.header_frame.grid(row=0, column=0, sticky="ew")
        self.header_frame.grid_columnconfigure(0, weight=1)
        
        self.header_label = ctk.CTkLabel(
            self.header_frame,
            text="Google Photos Takeout Restorer",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        self.header_label.grid(row=0, column=0, padx=25, pady=18, sticky="w")

        # Step Indicator with progress dots
        self.step_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.step_frame.grid(row=0, column=1, padx=(0, 10), pady=18, sticky="e")

        self.step_label = ctk.CTkLabel(
            self.step_frame,
            text="Step 1 of 5",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray60")
        )
        self.step_label.pack(side="left")
        
        # Theme Toggle
        self.theme_label = ctk.CTkLabel(
            self.header_frame, text="Theme:",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray60")
        )
        self.theme_label.grid(row=0, column=2, padx=(0, 5), pady=18, sticky="e")
        
        self.theme_menu = ctk.CTkOptionMenu(
            self.header_frame,
            values=["System", "Light", "Dark"],
            command=self.change_theme,
            width=100,
            height=30,
            font=ctk.CTkFont(size=12),
            corner_radius=6
        )
        self.theme_menu.grid(row=0, column=3, padx=(0, 25), pady=18, sticky="e")
        self.theme_menu.set(self.current_theme)

        # Content Area
        self.content_frame = ctk.CTkFrame(self, corner_radius=0)
        self.content_frame.grid(row=1, column=0, sticky="nsew", padx=25, pady=20)
        self.content_frame.grid_rowconfigure(0, weight=1)
        self.content_frame.grid_columnconfigure(0, weight=1)

        # Footer
        self.footer_frame = ctk.CTkFrame(self, height=70, corner_radius=0)
        self.footer_frame.grid(row=2, column=0, sticky="ew")

        self.btn_back = ctk.CTkButton(
            self.footer_frame, text=" Back", width=120, height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="transparent", border_width=2,
            border_color=("gray60", "gray40"),
            text_color=("gray30", "gray70"),
            hover_color=("gray90", "gray20"),
            corner_radius=8,
            command=self.go_back, state="disabled"
        )
        self.btn_back.pack(side="left", padx=25, pady=16)

        self.btn_next = ctk.CTkButton(
            self.footer_frame, text="Next Step ", width=140, height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=8,
            command=self.go_next, state="disabled"
        )
        self.btn_next.pack(side="right", padx=25, pady=16)

        # Page Management
        self.pages = {}
        self.current_page_index = 0
        self.page_classes = [
            PageWelcome, PageImport, PageDestination, PageSettings,
            PageConfirm, PageResults
        ]

        # Initialize database and run state
        self.reset_for_new_run()

        self.show_page(PageWelcome)

    def hide_footer(self):
        self.footer_frame.grid_remove()

    def show_footer(self):
        self.footer_frame.grid()

    def change_theme(self, new_theme: str):
        self.current_theme = new_theme
        ctk.set_appearance_mode(new_theme.lower())
        if hasattr(self, 'theme_menu'):
            self.theme_menu.set(new_theme)

    DEFAULT_CONFIG = {
        "app_name": "Google Photos Takeout Restorer",
        "version": "2.0.0",
        "exiftool_path": "tools/exiftool.exe",
        "supported_image_extensions": [
            ".jpg", ".jpeg", ".png", ".heic", ".heif",
            ".webp", ".gif", ".tiff", ".tif", ".raw",
            ".dng", ".cr2", ".nef", ".arw", ".bmp"
        ],
        "supported_video_extensions": [
            ".mp4", ".mov", ".m4v", ".3gp", ".avi", ".mkv", ".wmv"
        ],
        "live_photo_pairs": {
            "image_ext": ".jpg",
            "video_ext": ".mov"
        },
        "processing": {
            "max_workers": 4,
            "chunk_size": 100
        },
        "matching": {
            "levenshtein_threshold": 3,
            "min_truncation_length": 8
        }
    }

    def _deep_update(self, base_dict: dict, update_dict: dict) -> dict:
        """Recursively update a dictionary."""
        import copy
        result = copy.deepcopy(base_dict)
        for k, v in update_dict.items():
            if isinstance(v, dict) and k in result and isinstance(result[k], dict):
                result[k] = self._deep_update(result[k], v)
            else:
                result[k] = copy.deepcopy(v)
        return result

    def _load_config(self):
        config_path = Path(__file__).parent.parent / "config.json"
        config = {}
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse config.json: {e}")
        return self._deep_update(self.DEFAULT_CONFIG, config)

    def show_page(self, page_class):
        for widget in self.content_frame.winfo_children():
            widget.destroy()
        page = page_class(self.content_frame, self)
        page.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.pages[page_class] = page

        # Update step indicator
        if self.current_page_index == 0:
            self.step_label.configure(text="")
            self.step_frame.grid_remove()
        else:
            self.step_frame.grid()
            step_num = self.current_page_index
            step_names = ["Import", "Destination", "Settings", "Export", "Results"]
            step_name = step_names[step_num - 1] if step_num - 1 < len(step_names) else ""
            self.step_label.configure(text=f"Step {step_num} of 5 — {step_name}")

        self.update_navigation_buttons()

    def go_next(self):
        if self.current_page_index < len(self.page_classes) - 1:
            # Save configuration when leaving settings
            if self.page_classes[self.current_page_index] == PageSettings:
                config_to_save = {
                    "inputs": self.app_state.get("inputs", []),
                    "destination": self.app_state.get("destination"),
                    "settings": self.app_state.get("settings", {})
                }
                if self.app_state.get("db"):
                    self.app_state["db"].save_config(config_to_save)
                    
            self.current_page_index += 1
            self.show_page(self.page_classes[self.current_page_index])

    def resume_run(self, db_file: Path):
        """Load state from a previous run and jump straight to the results/processing page."""
        logger.info(f"Resuming run from {db_file}")
        
        # Close current dummy db
        if self.app_state.get("db"):
            self.app_state["db"].close()
        
        # Load the selected DB
        self.app_state["db"] = StateDatabase(db_file)
        self.run_id = db_file.stem.split("_")[1]
        self.app_state["run_id"] = self.run_id
        
        # Restore app config
        config = self.app_state["db"].load_config()
        self.app_state["inputs"] = config.get("inputs", [])
        self.app_state["destination"] = config.get("destination", None)
        self.app_state["settings"].update(config.get("settings", {}))
        
        # Jump directly to PageConfirm
        self.current_page_index = self.page_classes.index(PageConfirm)
        self.show_page(PageConfirm)
        self.show_footer()

    def go_back(self):
        if self.current_page_index > 0:
            current_page = self.pages.get(self.page_classes[self.current_page_index])
            if current_page and hasattr(current_page, 'on_back_pressed'):
                if not current_page.on_back_pressed():
                    return
            self.current_page_index -= 1
            self.show_page(self.page_classes[self.current_page_index])

    def update_navigation_buttons(self):
        self.btn_back.configure(state="normal" if self.current_page_index > 0 else "disabled")
        if self.current_page_index == 3:
            self.btn_next.configure(state="disabled")
        elif self.current_page_index == len(self.page_classes) - 1:
            self.btn_next.configure(text="Finish", state="disabled")
        else:
            self.btn_next.configure(text="Next Step ")

    def enable_next(self, enabled: bool):
        self.btn_next.configure(state="normal" if enabled else "disabled")
    
    def disable_next(self):
        self.btn_next.configure(state="disabled")

    def on_closing(self):
        """Cleanup on app close with proper resource management."""
        logger.info("=== Closing Application ===")
        
        # Unhook windnd drag-drop proc to avoid ctypes CallWindowProcW access violations on exit
        try:
            import windnd
            import platform
            import ctypes
            hwnd = self.winfo_id()
            if platform.architecture()[0] == "32bit":
                SetWindowLong = ctypes.windll.user32.SetWindowLongW
            else:
                SetWindowLong = ctypes.windll.user32.SetWindowLongPtrA
            GWL_WNDPROC = -4
            for i in range(200):
                name = f"old_wndproc_{i}"
                if hasattr(windnd, name):
                    old_proc = getattr(windnd, name)
                    if old_proc is not None:
                        SetWindowLong(hwnd, GWL_WNDPROC, old_proc)
                        setattr(windnd, name, None)
                new_name = f"new_wndproc_{i}"
                if hasattr(windnd, new_name):
                    setattr(windnd, new_name, None)
        except Exception as e:
            logger.debug(f"Failed to unhook windnd: {e}")
        
        if self.app_state["db"]:
            try:
                self.app_state["db"]._get_connection().execute("PRAGMA wal_checkpoint(TRUNCATE)")
                self.app_state["db"].close()
            except Exception as e:
                logger.error(f"Error closing database: {e}")
                
        # Gracefully shut down background processing tasks and exiftool workers
        processor = self.app_state.get("processor")
        if processor:
            logger.info("Stopping background processing threads...")
            try:
                processor.cancel()
                if hasattr(processor, "engine") and processor.engine:
                    processor.engine.stop()
            except Exception as e:
                logger.error(f"Error stopping processor engine: {e}")
                
        worker_thread = self.app_state.get("processor_thread")
        if worker_thread and worker_thread.is_alive():
            logger.info("Waiting for processing thread to finish...")
            worker_thread.join(timeout=3.0)
            if worker_thread.is_alive():
                logger.warning("Processing thread did not exit cleanly within timeout.")
        
        time.sleep(0.5) # Allow handles to release
        
        self._cleanup_temp_directories()
        
        logger.info("=== Application Closed ===")
        self.destroy()

    def _cleanup_database_files(self, db_path: Path):
        if not db_path.exists():
            return
        for attempt in range(3):
            try:
                for ext in ['-wal', '-shm']:
                    p = Path(str(db_path) + ext)
                    if p.exists():
                        p.unlink()
                if db_path.exists():
                    db_path.unlink()
                break
            except PermissionError:
                if attempt < 2:
                    time.sleep(1)
            except Exception as e:
                logger.warning(f"Cleanup error: {e}")
                break

    @staticmethod
    def _get_db_dir() -> Path:
        """Return (and create) a dedicated persistent directory for state databases."""
        db_dir = Path.home() / ".takeout_fixer" / "runs"
        db_dir.mkdir(parents=True, exist_ok=True)
        return db_dir

    def _cleanup_old_databases(self):
        # We no longer aggressively clean old databases because we want to allow resuming.
        pass

    def _cleanup_temp_directories(self):
        destination = self.app_state.get("destination")
        if not destination:
            return
        try:
            tmp_dir = destination / "Output" / ".tmp_working"
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir)
                logger.info(f"Cleaned up temp directory: {tmp_dir}")
        except Exception as e:
            logger.warning(f"Could not clean up temp directory: {e}")

    def reset_for_new_run(self):
        # Close the old database
        old_db = self.app_state.get("db")
        if old_db:
            try:
                old_db._get_connection().execute("PRAGMA wal_checkpoint(TRUNCATE)")
                old_db.close()
            except Exception as e:
                logger.warning(f"Error closing old database: {e}")

        self.app_state["inputs"] = []
        self.app_state["destination"] = None
        self.app_state["progress_model"] = None
        self.run_id = str(uuid.uuid4())[:8]
        self.app_state["run_id"] = self.run_id
        db_path = self._get_db_dir() / f"state_{self.run_id}.db"
        self.app_state["db"] = StateDatabase(db_path)


if __name__ == "__main__":
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
