"""
Page 5: Results - Display processing summary, statistics, and logs.
"""

import customtkinter as ctk
import os
from core.state_db import FileStatus


class PageResults(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        self.grid_rowconfigure(5, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ---- Retrieve run stats from DB (source of truth for progress) ----
        run_stats = self.app.app_state["db"].get_run_stats()
        db_stats = self.app.app_state["db"].get_statistics()

        # Use run_stats for correct progress (total_processable, not total_scanned)
        total_processable = run_stats.get("total_processable", 0)
        completed_count = run_stats.get("completed", 0)
        error_count = run_stats.get("failed", 0)
        skipped_count = run_stats.get("skipped", 0)
        unmatched_count = run_stats.get("unmatched", db_stats.get(FileStatus.UNMATCHED, 0))
        total_db_rows = run_stats.get("total_db_rows", sum(db_stats.values()) if db_stats else 0)
        duration = run_stats.get("duration_seconds", 0)
        avg_speed = run_stats.get("avg_speed", 0)
        workers_used = run_stats.get("workers_used", 0)
        hp_mode = run_stats.get("high_performance", False)
        output_bytes = run_stats.get("output_bytes", 0)

        # FIX: Progress is calculated against total_processable (matched files),
        # NOT total_scanned (all media files including unmatched ones).
        # This fixes the 64.2% bug where unmatched files inflated the denominator.
        processed_total = completed_count + error_count + skipped_count
        if total_processable > 0:
            progress_val = min(1.0, processed_total / total_processable)
        elif processed_total > 0:
            progress_val = 1.0  # All that could be processed were processed
        else:
            progress_val = 0.0

        # ---- Success Header ----
        self.success_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.success_frame.grid(row=0, column=0, pady=(15, 5), sticky="n")

        ctk.CTkLabel(
            self.success_frame, text="", font=ctk.CTkFont(size=40)
        ).pack(pady=(0, 5))

        ctk.CTkLabel(
            self.success_frame, text="Processing Complete!",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=("#27AE60", "#2ECC71")
        ).pack(pady=(0, 5))

        # Duration and speed subtitle
        subtitle_parts = []
        if duration > 0:
            subtitle_parts.append(f"Duration: {self._format_duration(duration)}")
        if avg_speed > 0:
            subtitle_parts.append(f"Avg Speed: {avg_speed:.1f} files/sec")
        if workers_used > 0:
            mode_str = "HP" if hp_mode else "Standard"
            subtitle_parts.append(f"{mode_str} ({workers_used} workers)")

        if subtitle_parts:
            ctk.CTkLabel(
                self.success_frame,
                text="    ".join(subtitle_parts),
                font=ctk.CTkFont(size=12),
                text_color=("gray40", "gray60")
            ).pack(pady=(0, 10))

        # ---- Action Buttons ----
        btn_frame = ctk.CTkFrame(self.success_frame, fg_color="transparent")
        btn_frame.pack(pady=(5, 0))

        self.btn_export_again = ctk.CTkButton(
            btn_frame, text=" Export Again", width=140, height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="transparent", border_width=2, border_color="#3B8ED0",
            text_color="#3B8ED0", hover_color=("gray90", "#1E3A5F"),
            corner_radius=8, command=self.export_again
        )
        self.btn_export_again.pack(side="left", padx=8)

        self.btn_view_files = ctk.CTkButton(
            btn_frame, text=" Open Output Folder", width=180, height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#3B8ED0", hover_color="#2A6CA8",
            corner_radius=8, command=self.view_exported_files
        )
        self.btn_view_files.pack(side="left", padx=8)

        self.btn_copy_logs = ctk.CTkButton(
            btn_frame, text=" Copy Log Path", width=150, height=38,
            font=ctk.CTkFont(size=13),
            fg_color="transparent", border_width=1,
            border_color=("gray60", "gray40"),
            text_color=("gray40", "gray60"),
            hover_color=("gray90", "gray20"),
            corner_radius=8, command=self.copy_logs
        )
        self.btn_copy_logs.pack(side="left", padx=8)

        # ---- Processing Results Card ----
        self.res_header = ctk.CTkFrame(self, corner_radius=12)
        self.res_header.grid(row=1, column=0, sticky="ew", padx=20, pady=10)
        self.res_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.res_header, text=" Processing Results",
            font=ctk.CTkFont(size=16, weight="bold")
        ).grid(row=0, column=0, padx=20, pady=(15, 5), sticky="w")

        # Subtitle: X of Y matched files processed (Z total scanned)
        result_text = f"{processed_total} of {total_processable} matched files processed"
        if total_db_rows > total_processable:
            result_text += f"  ({total_db_rows} total scanned)"

        ctk.CTkLabel(
            self.res_header, text=result_text,
            font=ctk.CTkFont(size=13), text_color="gray"
        ).grid(row=1, column=0, padx=20, pady=(0, 10), sticky="w")

        # Progress Bar
        self.progress_bar = ctk.CTkProgressBar(
            self.res_header, height=10, corner_radius=5,
            fg_color=("gray90", "gray20"),
            progress_color="#27AE60" if progress_val >= 1.0 else "#3B8ED0"
        )
        self.progress_bar.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="ew")
        self.progress_bar.set(progress_val)

        # Breakdown row
        breakdown_frame = ctk.CTkFrame(self.res_header, fg_color="transparent")
        breakdown_frame.grid(row=3, column=0, padx=20, pady=(0, 15), sticky="ew")
        breakdown_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        ctk.CTkLabel(
            breakdown_frame,
            text=f"{completed_count} completed ({round(progress_val * 100, 1)}%)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=("#27AE60", "#2ECC71")
        ).grid(row=0, column=0, sticky="w")

        if skipped_count > 0:
            ctk.CTkLabel(
                breakdown_frame,
                text=f"{skipped_count} skipped",
                font=ctk.CTkFont(size=13),
                text_color=("gray40", "gray60")
            ).grid(row=0, column=1, sticky="w")

        if error_count > 0:
            ctk.CTkLabel(
                breakdown_frame,
                text=f"{error_count} errors",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=("#E74C3C", "#FF6B6B")
            ).grid(row=0, column=2, sticky="w")

        if unmatched_count > 0:
            ctk.CTkLabel(
                breakdown_frame,
                text=f"{unmatched_count} unmatched",
                font=ctk.CTkFont(size=13),
                text_color=("#F39C12", "#F1C40F")
            ).grid(row=0, column=3, sticky="e")

        # ---- Statistics Cards ----
        self.stats_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.stats_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=8)
        self.stats_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)



        img_exts = self.app.app_state["config"].get("supported_image_extensions", [])
        vid_exts = self.app.app_state["config"].get("supported_video_extensions", [])
        total_size, img_count, vid_count = self.app.app_state["db"].get_media_stats(img_exts, vid_exts)

        # Format output size nicely
        if output_bytes > 0:
            size_display = self._format_size(output_bytes)
        else:
            size_display = self._format_size(total_size * 1024)  # total_size is in KB

        self.create_stat_card(
            self.stats_frame, 0, " OUTPUT SIZE", size_display, f"{completed_count} files",
            fg_color=("gray93", "#2D3748"), text_color=("#111827", "#F3F4F6"), accent="#3B8ED0"
        )
        self.create_stat_card(
            self.stats_frame, 1, " IMAGES", str(img_count), "",
            fg_color=("#F4F0FF", "#2E2640"), text_color=("#5B21B6", "#C4B5FD"), accent="#8B5CF6"
        )
        self.create_stat_card(
            self.stats_frame, 2, " VIDEOS", str(vid_count), "",
            fg_color=("#F0F8FF", "#263240"), text_color=("#1E40AF", "#93C5FD"), accent="#3B82F6"
        )
        self.create_stat_card(
            self.stats_frame, 3, "UNMATCHED", str(unmatched_count), "",
            fg_color=("#FFF8F0", "#3D3020"), text_color=("#92400E", "#FCD34D"), accent="#F59E0B"
        )

        # ---- Search & Filter ----
        self.filter_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.filter_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=8)

        self.search_entry = ctk.CTkEntry(
            self.filter_frame, placeholder_text="Search by filename...", 
            width=280, height=36, font=ctk.CTkFont(size=13), corner_radius=8
        )
        self.search_entry.pack(side="left", padx=(0, 15))
        self.search_entry.bind("<KeyRelease>", self.filter_list)

        self.filter_dropdown = ctk.CTkOptionMenu(
            self.filter_frame,
            values=["All Files", "Completed", "Low Confidence", "Errors", "Unmatched"],
            width=160, height=36, font=ctk.CTkFont(size=13),
            corner_radius=8, command=self.on_filter_change
        )
        self.filter_dropdown.pack(side="left")

        # Show count placeholder (updated by _execute_filter)
        self.file_count_label = ctk.CTkLabel(
            self.filter_frame, text="Loading...",
            font=ctk.CTkFont(size=12), text_color=("gray40", "gray60")
        )
        self.file_count_label.pack(side="right", padx=10)

        # ---- Results List ----
        self.list_frame = ctk.CTkScrollableFrame(self, height=200, corner_radius=12)
        self.list_frame.grid(row=5, column=0, sticky="nsew", padx=20, pady=(5, 15))

        self.display_limit = 1000
        self._all_filtered_files = []
        self.current_visible_count = 100
        
        # Load initial data
        self._execute_filter()

    def create_stat_card(self, parent, col, title, value, subtext, fg_color, text_color, accent):
        card = ctk.CTkFrame(
            parent, fg_color=fg_color, corner_radius=12, height=100,
            border_width=1, border_color=accent
        )
        card.grid(row=0, column=col, padx=8, pady=8, sticky="nsew")
        card.grid_propagate(False)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text=title, font=ctk.CTkFont(size=10, weight="bold"),
            text_color=accent
        ).grid(row=0, column=0, pady=(12, 3), padx=12, sticky="w")
        
        ctk.CTkLabel(
            card, text=value, font=ctk.CTkFont(size=22, weight="bold"),
            text_color=text_color
        ).grid(row=1, column=0, pady=(0, 3), padx=12, sticky="w")
        
        if subtext:
            ctk.CTkLabel(
                card, text=subtext, font=ctk.CTkFont(size=11), text_color="gray"
            ).grid(row=2, column=0, pady=(0, 8), padx=12, sticky="w")


    def render_list(self):
        """Render list using pack() with pagination to prevent Tkinter GUI lag."""
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        files = self._all_filtered_files
        if not files:
            ctk.CTkLabel(
                self.list_frame, text="No files to display", text_color="gray"
            ).pack(pady=20)
            return

        visible_files = files[:self.current_visible_count]

        if len(files) == self.display_limit:
            ctk.CTkLabel(
                self.list_frame, 
                text=f"Showing first {self.display_limit} files. Use search/filter to narrow results.",
                font=ctk.CTkFont(size=12),
                text_color="gray"
            ).pack(pady=(0, 10))

        for f in visible_files:
            if f.status == FileStatus.COMPLETED:
                bg = ("#F0FDF4", "#1C2E24")
            elif f.status == FileStatus.ERROR:
                bg = ("#FEF2F2", "#2E1C1C")
            else:
                bg = "transparent"

            row = ctk.CTkFrame(self.list_frame, corner_radius=8, fg_color=bg)
            row.pack(fill="x", pady=2, padx=5)

            if f.status == FileStatus.COMPLETED:
                icon, status_text = "", "Successfully processed with metadata"
            elif f.status == FileStatus.ERROR:
                icon, status_text = "", f.error_message or "Error"
            elif f.status == FileStatus.MATCHED_LOW_CONFIDENCE:
                icon, status_text = "", "Low confidence match - review recommended"
            elif f.status == FileStatus.UNMATCHED:
                icon, status_text = "", "No matching metadata found"
            else:
                icon, status_text = "", f.status.value.capitalize()

            ctk.CTkLabel(row, text=icon, font=ctk.CTkFont(size=16)).pack(side="left", padx=10, pady=8)
            ctk.CTkLabel(row, text=f"{f.filename}  —  {status_text}", anchor="w",
                        font=ctk.CTkFont(size=12)).pack(side="left", fill="x", expand=True, padx=5)

        if len(files) > self.current_visible_count:
            load_more_btn = ctk.CTkButton(
                self.list_frame, 
                text=f"Load More ({len(files) - self.current_visible_count} remaining)", 
                height=32,
                command=self.load_more_files
            )
            load_more_btn.pack(pady=15)

    def load_more_files(self):
        self.current_visible_count += 100
        self.render_list()

    def filter_list(self, event=None):
        if hasattr(self, '_search_timer'):
            self.after_cancel(self._search_timer)
        self._search_timer = self.after(300, self._execute_filter)
        
    def _execute_filter(self):
        query = self.search_entry.get().lower()
        if not query:
            query = None
            
        choice = self.filter_dropdown.get()
        status_map = {
            "All Files": None, "Completed": FileStatus.COMPLETED,
            "Low Confidence": FileStatus.MATCHED_LOW_CONFIDENCE,
            "Errors": FileStatus.ERROR, "Unmatched": FileStatus.UNMATCHED,
        }
        target = status_map.get(choice)
        
        filtered = self.app.app_state["db"].search_media_files(query=query, status=target, limit=self.display_limit)
        
        # NOTE: We no longer have an exact count of ALL filtered files if it exceeds the limit
        count_text = f"{len(filtered)} files" if len(filtered) < self.display_limit else f"{self.display_limit}+ files"
        self.file_count_label.configure(text=count_text)
        
        self._all_filtered_files = filtered
        self.current_visible_count = 100
        self.render_list()

    def on_filter_change(self, choice):
        self._execute_filter()

    def export_again(self):
        self.app.reset_for_new_run()
        self.app.current_page_index = 0
        self.app.show_page(self.app.page_classes[0])
        self.app.show_footer()

    def view_exported_files(self):
        dest = self.app.app_state.get("destination")
        if dest and dest.exists():
            output_dir = dest / "Output" / "Completed"
            os.startfile(str(output_dir if output_dir.exists() else dest))

    def copy_logs(self):
        dest = self.app.app_state.get("destination")
        if dest:
            log_dir = dest / "Output" / "Logs"
            if log_dir.exists():
                logs = list(log_dir.glob("*.log"))
                if logs:
                    latest_log = max(logs, key=lambda p: p.stat().st_mtime)
                    self.clipboard_clear()
                    self.clipboard_append(str(latest_log))
                    self.btn_copy_logs.configure(text="Path Copied!")
                    self.after(2000, lambda: self.btn_copy_logs.configure(text=" Copy Log Path"))

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format seconds into human-readable duration."""
        seconds = int(seconds)
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            m, s = divmod(seconds, 60)
            return f"{m}m {s}s"
        else:
            h, rem = divmod(seconds, 3600)
            m, s = divmod(rem, 60)
            return f"{h}h {m}m"

    @staticmethod
    def _format_size(nbytes: float) -> str:
        """Format bytes into human-readable size."""
        if nbytes < 1024:
            return f"{nbytes:.0f} B"
        elif nbytes < 1024 ** 2:
            return f"{nbytes / 1024:.1f} KB"
        elif nbytes < 1024 ** 3:
            return f"{nbytes / (1024 ** 2):.1f} MB"
        else:
            return f"{nbytes / (1024 ** 3):.2f} GB"
