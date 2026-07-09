"""
Page 4: Confirm & Export - Summary, Start Processing, and Rich Progress Display.
"""

import customtkinter as ctk
import threading
from pathlib import Path
import sys
import os
import shutil
import time
import logging

logger = logging.getLogger(__name__)

from core.scanner import FileScanner
from core.matcher import MetadataMatcher
from core.processor import FileProcessor
from core.state_db import FileStatus
from core.progress_model import ProgressModel


class PageConfirm(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self._polling = False

        self.grid_rowconfigure(4, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Title
        self.title_label = ctk.CTkLabel(
            self, text="Export files to",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        self.title_label.grid(row=0, column=0, pady=(30, 5), sticky="n")

        # Destination path display
        dest_path = self.app.app_state.get("destination", "No destination selected")
        self.path_label = ctk.CTkLabel(
            self, text=str(dest_path),
            font=ctk.CTkFont(size=12), wraplength=700,
            text_color=("gray40", "gray60")
        )
        self.path_label.grid(row=1, column=0, pady=(0, 15), sticky="n")

        # Summary info
        inputs = self.app.app_state.get("inputs", [])
        input_count = len(inputs)
        mode = self.app.app_state["settings"].get("output_mode", "copy")
        hp_mode = self.app.app_state["settings"].get("high_performance", False)
        
        summary_parts = [f"Sources: {input_count} input(s)", f"Mode: {mode.capitalize()}"]
        if hp_mode:
            cores = os.cpu_count() or 4
            summary_parts.append(f"High Performance ({cores} cores)")
        
        self.summary_label = ctk.CTkLabel(
            self, text="    ".join(summary_parts),
            font=ctk.CTkFont(size=13), text_color="gray", justify="center"
        )
        self.summary_label.grid(row=2, column=0, pady=(0, 15), sticky="n")

        # Action buttons frame
        self.action_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.action_frame.grid(row=3, column=0, pady=(5, 10), sticky="n")

        # Start Export button
        self.btn_start = ctk.CTkButton(
            self.action_frame, text="Start Export", width=200, height=48,
            fg_color="#3B8ED0", hover_color="#2A6CA8",
            font=ctk.CTkFont(size=15, weight="bold"),
            corner_radius=10,
            command=self.start_export
        )
        self.btn_start.pack(side="left", padx=10)

        # Stop Export button
        self.btn_stop = ctk.CTkButton(
            self.action_frame, text="Stop Export", width=200, height=48,
            fg_color="#E74C3C", hover_color="#C0392B",
            font=ctk.CTkFont(size=15, weight="bold"),
            corner_radius=10,
            command=self.cancel_export
        )
        self.btn_stop.pack(side="left", padx=10)
        self.btn_stop.pack_forget()  # Hidden initially

        # Progress Section (hidden until export starts)
        self.progress_frame = ctk.CTkFrame(self, corner_radius=12, fg_color="transparent")
        self.progress_frame.grid(row=4, column=0, sticky="nsew", padx=20, pady=(5, 15))
        self.progress_frame.grid_columnconfigure(0, weight=1)
        self.progress_frame.grid_remove()  # Hidden initially

        # Phase label
        self.phase_label = ctk.CTkLabel(
            self.progress_frame, text="Initializing...",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=("#2563EB", "#60A5FA"), fg_color="transparent"
        )
        self.phase_label.grid(row=0, column=0, padx=20, pady=(20, 8), sticky="w")

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(
            self.progress_frame, height=14, corner_radius=7,
            fg_color=("gray85", "gray25"), progress_color="#3B8ED0"
        )
        self.progress_bar.grid(row=1, column=0, padx=20, pady=(0, 5), sticky="ew")
        self.progress_bar.set(0)

        # Percentage + stats row
        self.stats_row = ctk.CTkFrame(self.progress_frame, fg_color="transparent")
        self.stats_row.grid(row=2, column=0, padx=20, pady=(0, 5), sticky="ew")
        self.stats_row.grid_columnconfigure(1, weight=1)

        self.pct_label = ctk.CTkLabel(
            self.stats_row, text="0%",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=("#1E40AF", "#93C5FD"), fg_color="transparent"
        )
        self.pct_label.grid(row=0, column=0, padx=(0, 15), sticky="w")

        self.count_label = ctk.CTkLabel(
            self.stats_row, text="0 / 0 files",
            font=ctk.CTkFont(size=13), text_color="gray", fg_color="transparent"
        )
        self.count_label.grid(row=0, column=1, sticky="w")

        # Detail stats row
        self.detail_row = ctk.CTkFrame(self.progress_frame, fg_color="transparent")
        self.detail_row.grid(row=3, column=0, padx=20, pady=(0, 5), sticky="ew")
        self.detail_row.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.speed_label = ctk.CTkLabel(
            self.detail_row, text="Speed: —",
            font=ctk.CTkFont(size=12), text_color=("gray40", "gray60"), fg_color="transparent"
        )
        self.speed_label.grid(row=0, column=0, sticky="w")

        self.elapsed_label = ctk.CTkLabel(
            self.detail_row, text="Elapsed: 0s",
            font=ctk.CTkFont(size=12), text_color=("gray40", "gray60"), fg_color="transparent"
        )
        self.elapsed_label.grid(row=0, column=1, sticky="w")

        self.eta_label = ctk.CTkLabel(
            self.detail_row, text="ETA: —",
            font=ctk.CTkFont(size=12), text_color=("gray40", "gray60"), fg_color="transparent"
        )
        self.eta_label.grid(row=0, column=2, sticky="w")

        self.workers_label = ctk.CTkLabel(
            self.detail_row, text="",
            font=ctk.CTkFont(size=12), text_color=("gray40", "gray60"), fg_color="transparent"
        )
        self.workers_label.grid(row=0, column=3, sticky="e")

        # Current file label
        self.current_file_label = ctk.CTkLabel(
            self.progress_frame, text="",
            font=ctk.CTkFont(size=11), text_color=("gray50", "gray60"), fg_color="transparent",
            anchor="w"
        )
        self.current_file_label.grid(row=4, column=0, padx=20, pady=(0, 5), sticky="w")

        # Results breakdown row
        self.breakdown_row = ctk.CTkFrame(self.progress_frame, fg_color="transparent")
        self.breakdown_row.grid(row=5, column=0, padx=20, pady=(5, 15), sticky="ew")
        self.breakdown_row.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.ok_label = ctk.CTkLabel(
            self.breakdown_row, text="OK: 0",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=("#27AE60", "#2ECC71"), fg_color="transparent"
        )
        self.ok_label.grid(row=0, column=0, sticky="w")

        self.skip_label = ctk.CTkLabel(
            self.breakdown_row, text="Skipped: 0",
            font=ctk.CTkFont(size=12), text_color=("gray40", "gray60"), fg_color="transparent"
        )
        self.skip_label.grid(row=0, column=1, sticky="w")

        self.err_label = ctk.CTkLabel(
            self.breakdown_row, text="Errors: 0",
            font=ctk.CTkFont(size=12), text_color=("#E74C3C", "#FF6B6B")
        )
        self.err_label.grid(row=0, column=2, sticky="w")

        self.unmatched_label = ctk.CTkLabel(
            self.breakdown_row, text="Unmatched: 0",
            font=ctk.CTkFont(size=12), text_color=("#F39C12", "#F1C40F")
        )
        self.unmatched_label.grid(row=0, column=3, sticky="e")

        # Simple status fallback
        self.status_label = ctk.CTkLabel(self, text="", text_color="gray",
                                          font=ctk.CTkFont(size=12))
        self.status_label.grid(row=5, column=0, pady=(0, 10), sticky="n")


    def start_export(self):
        """Initiates the export process, updates UI, and runs pipeline in a background thread."""
        self._cancelled = False
        self._navigate_back_after_cancel = False
        
        # Reveal progress UI
        self.progress_frame.grid()
        
        # Toggle buttons
        self.btn_start.pack_forget()
        self.btn_stop.pack(side="left", padx=10)
        self.app.btn_back.configure(state="disabled")
        
        # Launch processing in a daemon thread
        thread = threading.Thread(target=self.run_processing_pipeline, daemon=True)
        self.app.app_state["processor_thread"] = thread
        thread.start()

    def cancel_export(self, is_back_action=False):
        """Called when the Stop button is clicked or Back is pressed."""
        if getattr(self, '_cancelled', False):
            return True
            
        import tkinter.messagebox
        msg = "Are you sure you want to stop the export? Progress will be saved, but you'll have to resume later."
        if is_back_action:
            msg = "Going back will stop the current export process. " + msg
            
        if tkinter.messagebox.askyesno("Stop Export", msg, parent=self):
            self._cancelled = True
            self.btn_stop.configure(state="disabled", text="Stopping...")
            self.update_status("Stopping process... please wait.")
            processor = self.app.app_state.get("processor")
            if processor:
                processor.cancel()
            return True
        return False

    def on_back_pressed(self):
        """Intercept back navigation."""
        if getattr(self, '_polling', False):
            # Process is running!
            if self.cancel_export(is_back_action=True):
                self._navigate_back_after_cancel = True
            return False # Block immediate back navigation
        return True

    def _restore_ui_after_cancel(self):
        self.btn_stop.pack_forget()
        self.btn_stop.configure(state="normal", text="Stop Export")
        self.btn_start.pack(side="left", padx=10)
        self.btn_start.configure(state="normal", text="Resume Export")
        self.app.btn_back.configure(state="normal")
        if getattr(self, '_navigate_back_after_cancel', False):
            self._navigate_back_after_cancel = False
            self.app.go_back()

    def run_processing_pipeline(self):
        """The actual core processing logic."""
        scanner = None
        tmp_dir = None
        try:
            db = self.app.app_state["db"]
            config = self.app.app_state["config"]
            inputs = self.app.app_state["inputs"]
            destination = self.app.app_state.get("destination")
            if not destination:
                raise ValueError("Destination is not set in application state.")
            
            settings = self.app.app_state["settings"]
            run_id = self.app.app_state.get("run_id", "default")
            hp_mode = settings.get("high_performance", False)

            config['settings'] = settings

            tmp_dir = destination / "Output" / ".tmp_working"
            log_dir = destination / "Output" / "Logs"

            # Create progress model
            progress_model = ProgressModel()
            self.app.app_state["progress_model"] = progress_model

            # Start UI polling
            self._polling = True
            self.app.after(200, self._poll_progress)

            # 1. Scan
            progress_model.set_phase("scanning", "Scanning input files...")
            self.update_status("Scanning input files...")
            scanner = FileScanner(config, db, tmp_dir, progress_model=progress_model)
            media_count, json_count = scanner.scan_inputs(inputs)
            progress_model.end_phase("scanning")
            progress_model.total_scanned = media_count
            
            if media_count == 0:
                scanner.cleanup()
                self._cleanup_tmp_working(tmp_dir)
                self._polling = False
                self.update_status("No media files found in inputs!")
                self.app.after(2000, self.go_to_results)
                return

            # 2. Match
            if getattr(self, '_cancelled', False):
                scanner.cleanup()
                self._cleanup_tmp_working(tmp_dir)
                self._polling = False
                self.app.after(0, self._restore_ui_after_cancel)
                return

            progress_model.set_phase("matching", f"Matching metadata for {media_count} files...")
            self.update_status(f"Found {media_count} media files, {json_count} JSON files. Matching metadata...")
            matcher = MetadataMatcher(db, config)
            matcher.run_matching()
            progress_model.end_phase("matching")
            
            if getattr(self, '_cancelled', False):
                scanner.cleanup()
                self._cleanup_tmp_working(tmp_dir)
                self._polling = False
                self.app.after(0, self._restore_ui_after_cancel)
                return

            # 3. Get matched file IDs (both CERTAIN and LOW_CONFIDENCE)
            certain_files = db.get_files_by_status(FileStatus.MATCHED)
            low_conf_files = db.get_files_by_status(FileStatus.MATCHED_LOW_CONFIDENCE)
            file_ids = [f.id for f in certain_files + low_conf_files]

            # Count unmatched
            unmatched_files = db.get_files_by_status(FileStatus.UNMATCHED)
            progress_model.unmatched = len(unmatched_files)

            if not file_ids:
                scanner.cleanup()
                self._cleanup_tmp_working(tmp_dir)
                self._polling = False
                self.update_status("No matches found. Check logs.")
                self.app.after(2000, self.go_to_results)
                return

            # 4. Process
            self.update_status(f"Processing {len(file_ids)} matched files...")
            output_dir = destination / "Output"
            output_mode = settings.get("output_mode", "copy")

            processor = FileProcessor(
                db, config, log_dir, run_id,
                high_performance=hp_mode,
                progress_model=progress_model
            )
            self.app.app_state["processor"] = processor

            # Show worker count
            self.app.after(0, lambda w=processor.max_workers: self.workers_label.configure(
                text=f"{w} workers"
            ))

            # Throttle UI updates to prevent Tkinter event queue overflow
            self._last_progress_update = 0.0

            def on_progress(completed, total, filename, status):

                now = time.time()
                if completed == total or now - getattr(self, "_last_progress_update", 0.0) > 0.1:
                    self._last_progress_update = now
                    pct = round((completed / total) * 100, 1) if total > 0 else 0
                    msg = f"Processing: {completed}/{total} ({pct}%)"
                    self.update_status(msg)

            processor.process_files(
                file_ids, output_dir, output_mode,
                progress_callback=on_progress
            )
            
            if getattr(self, '_cancelled', False):
                logger.info("Export cancelled by user")
                self.update_status("Export cancelled by user.")
                if scanner:
                    scanner.cleanup()
                self._cleanup_tmp_working(tmp_dir)
                self._polling = False
                self.app.after(0, self._restore_ui_after_cancel)
                return

            # Clean up extracted files after processing no longer needs them.
            if scanner:
                scanner.cleanup()
            self._cleanup_tmp_working(tmp_dir)

            self._polling = False
            self.app.after(0, lambda: self._update_progress_complete())
            self.update_status("Export complete!")
            self.app.after(1000, self.go_to_results)

        except Exception as e:
            logger.exception("Error in processing pipeline")
            self.update_status(f"Error: {str(e)}")
            self._polling = False
            if scanner:
                scanner.cleanup()
            if tmp_dir:
                self._cleanup_tmp_working(tmp_dir)
            self.app.after(0, self._on_processing_error)

    def _update_progress_complete(self):
        """Set progress bar to 100% on completion."""
        self.progress_bar.set(1.0)
        self.pct_label.configure(text="100%")
        self.phase_label.configure(
            text="Processing Complete!",
            text_color=("#27AE60", "#2ECC71")
        )
        self.progress_bar.configure(progress_color="#27AE60")

    def _poll_progress(self):
        """Periodically read from ProgressModel and update UI."""
        if not self._polling:
            return
        
        pm = self.app.app_state.get("progress_model")
        if pm is None:
            self.app.after(500, self._poll_progress)
            return

        snap = pm.get_snapshot()
        frac = snap["progress_fraction"]
        total = snap["total_processable"]
        processed = snap["processed"]
        elapsed = snap["elapsed"]

        # Progress bar
        self.progress_bar.set(frac)

        # Percentage
        pct = round(frac * 100, 1)
        self.pct_label.configure(text=f"{pct}%")

        # Count
        self.count_label.configure(text=f"{processed} / {total} files")

        # Phase
        phase_msg = snap.get("phase_message", "")
        if phase_msg:
            self.phase_label.configure(text=phase_msg)

        # Speed
        speed = pm.get_speed()
        if speed > 0:
            self.speed_label.configure(text=f"{speed:.1f} files/s")
        else:
            self.speed_label.configure(text="Speed: —")

        # Elapsed
        self.elapsed_label.configure(text=f"{self._format_duration(elapsed)}")

        # ETA
        phase = snap.get("current_phase", "")
        eta = pm.get_eta_seconds()
        
        if phase in ("scanning", "matching"):
            self.eta_label.configure(text="ETA: —")
        elif eta is not None and eta > 0:
            self.eta_label.configure(text=f"~{self._format_duration(eta)} remaining")
        elif total > 0 and processed >= total:
            self.eta_label.configure(text="Done!")
        else:
            self.eta_label.configure(text="ETA: calculating...")

        # Current file
        cf = snap.get("current_file", "")
        if cf:
            # Truncate long filenames
            display_name = cf if len(cf) <= 70 else f"...{cf[-67:]}"
            self.current_file_label.configure(text=f"File: {display_name}")

        # Breakdown
        self.ok_label.configure(text=f"{snap['completed']}")
        self.skip_label.configure(text=f"{snap['skipped']} skipped")
        self.err_label.configure(text=f"{snap['failed']} errors")
        self.unmatched_label.configure(text=f"{snap['unmatched']} unmatched")

        # Continue polling
        self.app.after(300, self._poll_progress)

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format seconds into a human-readable duration string."""
        seconds = int(seconds)
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            m, s = divmod(seconds, 60)
            return f"{m}m {s}s"
        else:
            h, rem = divmod(seconds, 3600)
            m, s = divmod(rem, 60)
            return f"{h}h {m}m {s}s"

    def _cleanup_tmp_working(self, tmp_dir: Path):
        """Clean up the .tmp_working directory immediately after processing."""
        try:
            if tmp_dir and tmp_dir.exists():
                shutil.rmtree(tmp_dir)
                logger.info(f"Cleaned up temp directory: {tmp_dir}")
        except Exception as e:
            logger.warning(f"Could not clean up {tmp_dir}: {e}")

    def _on_processing_error(self):
        """Restores UI after a processing error."""
        self.btn_start.configure(state="normal", text="Retry Export")
        self.app.show_footer()

    def update_status(self, message):
        """Thread-safe UI update."""
        self.app.after(0, lambda: self.status_label.configure(text=message))

    def go_to_results(self):
        """Navigates to the final Results page."""
        self.app.current_page_index = 5
        self.app.show_page(self.app.page_classes[5])
