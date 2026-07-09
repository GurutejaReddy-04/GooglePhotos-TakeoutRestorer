"""
Page 2: Destination - Choose the output folder.
"""

import customtkinter as ctk
from tkinter import filedialog
from pathlib import Path
import shutil


class PageDestination(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.title_label = ctk.CTkLabel(
            self, text="Choose a destination folder",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        self.title_label.grid(row=0, column=0, pady=(40, 5), sticky="n")

        self.subtitle_label = ctk.CTkLabel(
            self,
            text="The destination folder is where your photos will be saved.",
            text_color=("gray40", "gray60"), font=ctk.CTkFont(size=14)
        )
        self.subtitle_label.grid(row=1, column=0, pady=(0, 25), sticky="n")

        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.grid(row=2, column=0, sticky="n")

        self.btn_choose = ctk.CTkButton(
            self.btn_frame, text="Choose Folder", width=180, height=42,
            fg_color="#3B8ED0", hover_color="#2A6CA8",
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=8,
            command=self.select_folder
        )
        self.btn_choose.pack(pady=10)

        self.path_label = ctk.CTkLabel(
            self, text="", text_color="#2CC985", font=ctk.CTkFont(size=12)
        )
        self.path_label.grid(row=3, column=0, pady=(10, 0), sticky="n")

        # Disk space indicator
        self.disk_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray60")
        )
        self.disk_label.grid(row=4, column=0, pady=(5, 0), sticky="n")

        # Validation feedback label
        self.validation_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=12), wraplength=600
        )
        self.validation_label.grid(row=5, column=0, pady=(5, 0), sticky="n")

        # Restore state if navigating back
        if self.app.app_state["destination"]:
            path = self.app.app_state["destination"]
            self.path_label.configure(text=str(path))
            self._show_disk_space(path)
            self.app.enable_next(True)

    def _show_disk_space(self, path: Path):
        """Show available disk space for the selected destination."""
        try:
            usage = shutil.disk_usage(str(path))
            free_gb = usage.free / (1024 ** 3)
            total_gb = usage.total / (1024 ** 3)
            pct_free = (usage.free / usage.total) * 100

            if free_gb >= 10:
                color = ("gray50", "gray60")
            elif free_gb >= 2:
                color = ("#E67E22", "#F39C12")
            else:
                color = ("#E74C3C", "#FF6B6B")

            self.disk_label.configure(
                text=f" {free_gb:.1f} GB free of {total_gb:.0f} GB ({pct_free:.0f}% available)",
                text_color=color
            )
        except Exception:
            self.disk_label.configure(text="")

    def _validate_destination(self, path: Path) -> tuple:
        """Validate the destination path.

        Returns (is_valid, message, is_warning).
        is_valid=False blocks progression; is_warning=True shows a caution but allows it.
        """

        # Check write permissions by attempting to create a temp file
        try:
            path.mkdir(parents=True, exist_ok=True)
            test_file = path / ".takeout_fixer_write_test"
            test_file.touch()
            test_file.unlink()
        except PermissionError:
            return False, " Cannot write to this folder. Please choose a different destination.", False
        except OSError as e:
            return False, f" Cannot access this folder: {e}", False

        # Check if destination overlaps with any source input
        inputs = self.app.app_state.get("inputs", [])
        dest_resolved = path.resolve()
        for inp in inputs:
            inp_resolved = inp.resolve()
            try:
                # Check if dest is inside a source or a source is inside dest
                if dest_resolved == inp_resolved:
                    return True, "Destination is the same as a source folder. In-place mode will modify originals.", True
                
                try:
                    if dest_resolved.is_relative_to(inp_resolved):
                        return True, "Destination is inside a source folder. This may cause issues in copy mode.", True
                    if inp_resolved.is_relative_to(dest_resolved):
                        return True, "A source folder is inside the destination. Output may mix with source files.", True
                except AttributeError:
                    # Fallback for Python < 3.9
                    if dest_resolved.parts[:len(inp_resolved.parts)] == inp_resolved.parts:
                        return True, "Destination is inside a source folder. This may cause issues in copy mode.", True
                    if inp_resolved.parts[:len(dest_resolved.parts)] == dest_resolved.parts:
                        return True, "A source folder is inside the destination. Output may mix with source files.", True
            except (ValueError, OSError):
                pass

        return True, "", False

    def select_folder(self):
        folder = filedialog.askdirectory(title="Choose Destination Folder")
        if folder:
            path = Path(folder)

            is_valid, message, is_warning = self._validate_destination(path)

            if not is_valid:
                self.path_label.configure(text=str(path), text_color="red")
                self.validation_label.configure(text=message, text_color="red")
                self.disk_label.configure(text="")
                self.app.enable_next(False)
                return

            self.app.app_state["destination"] = path
            self.path_label.configure(text=str(path), text_color="#2CC985")
            self._show_disk_space(path)

            if is_warning:
                self.validation_label.configure(text=message, text_color="orange")
            else:
                self.validation_label.configure(text="Destination is ready", text_color="#2CC985")

            self.app.enable_next(True)