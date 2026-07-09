"""
Page 0: Welcome / Resume - Resume past exports or start a new one.
"""

import customtkinter as ctk
import datetime
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class PageWelcome(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.title_label = ctk.CTkLabel(
            self, text="Welcome to Google Photos Takeout Restorer",
            font=ctk.CTkFont(size=22, weight="bold")
        )
        self.title_label.grid(row=0, column=0, pady=(40, 5), sticky="n")

        self.subtitle_label = ctk.CTkLabel(
            self,
            text="Resume a previous export or start a new one.",
            text_color=("gray40", "gray60"), font=ctk.CTkFont(size=14)
        )
        self.subtitle_label.grid(row=1, column=0, pady=(0, 25), sticky="n")

        # Runs Container
        self.runs_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.runs_frame.grid(row=2, column=0, sticky="nsew", padx=40)
        self.runs_frame.grid_columnconfigure(0, weight=1)

        self._load_runs()

        self.new_btn = ctk.CTkButton(
            self, text="Start New Export", width=200, height=45,
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self._start_new
        )
        self.new_btn.grid(row=3, column=0, pady=30, sticky="n")

        # Hide footer on this page
        self.app.hide_footer()

    def _load_runs(self):
        db_dir = self.app._get_db_dir()
        if not db_dir.exists():
            return
            
        import sqlite3
        
        row_idx = 0
        for db_file in sorted(db_dir.glob("state_*.db"), key=lambda p: p.stat().st_mtime, reverse=True):
            if db_file.name == f"state_{self.app.run_id}.db":
                continue # Skip the empty one we just created
                
            try:
                # Get stats
                conn = sqlite3.connect(db_file)
                cursor = conn.cursor()
                cursor.execute("SELECT status, count(*) FROM media_files GROUP BY status")
                stats = dict(cursor.fetchall())
                
                cursor.execute("SELECT key, value FROM run_config")
                config = dict(cursor.fetchall())
                conn.close()
                
                total = sum(stats.values())
                if total == 0:
                    continue # Skip empty databases
                    
                completed = stats.get("completed", 0) + stats.get("error", 0) + stats.get("skipped", 0)
                
                pct = int((completed / total) * 100)
                
                destination_name = config.get("destination", "")
                if destination_name:
                    from pathlib import Path
                    dest_path = Path(destination_name).name
                    title_text = f"Restore to '{dest_path}'"
                else:
                    title_text = "Unfinished Restore Session"
                
                mtime = datetime.datetime.fromtimestamp(db_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                
                card = ctk.CTkFrame(self.runs_frame, corner_radius=10, border_width=1)
                card.grid(row=row_idx, column=0, pady=5, sticky="ew")
                card.grid_columnconfigure(1, weight=1)
                
                ctk.CTkLabel(card, text=title_text, font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=15, pady=(10,0), sticky="w")
                ctk.CTkLabel(card, text=f"Last active: {mtime}").grid(row=1, column=0, padx=15, pady=(0,10), sticky="w")
                
                ctk.CTkLabel(card, text=f"{pct}% Complete", font=ctk.CTkFont(weight="bold"), text_color="#2CC985").grid(row=0, column=1, padx=15, pady=(10,0), sticky="e")
                ctk.CTkLabel(card, text=f"{completed} / {total} files").grid(row=1, column=1, padx=15, pady=(0,10), sticky="e")
                
                btn_frame = ctk.CTkFrame(card, fg_color="transparent")
                btn_frame.grid(row=0, column=2, rowspan=2, padx=15, pady=10)
                
                resume_btn = ctk.CTkButton(btn_frame, text="Resume", width=80, command=lambda f=db_file: self._resume_run(f))
                resume_btn.pack(side="left", padx=(0, 5))
                
                delete_btn = ctk.CTkButton(
                    btn_frame, text="Delete", width=60, 
                    fg_color="#E74C3C", hover_color="#C0392B",
                    command=lambda f=db_file: self._delete_run(f)
                )
                delete_btn.pack(side="left")
                
                row_idx += 1
            except Exception:
                continue

    def _delete_run(self, db_file: Path):
        import tkinter.messagebox as messagebox
        import sqlite3
        import shutil
        
        run_id = db_file.stem.split("_")[1] if "_" in db_file.stem else db_file.stem
        if not messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete Run {run_id}?\n\nThis will permanently delete the saved state and cannot be undone."):
            return
            
        try:
            # First, read the DB to find destination for temp file cleanup
            try:
                conn = sqlite3.connect(db_file)
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM run_config WHERE key = 'destination'")
                row = cursor.fetchone()
                conn.close()
                if row:
                    dest_path = Path(row[0])
                    tmp_dir = dest_path / "Output" / ".tmp_working"
                    if tmp_dir.exists():
                        shutil.rmtree(tmp_dir)
            except Exception as e:
                logger.error(f"Error cleaning up tmp directory: {e}")

            # Also clean up WAL/SHM files
            for ext in ['', '-wal', '-shm']:
                f = Path(str(db_file) + ext)
                if f.exists():
                    f.unlink()
        except Exception as e:
            logger.error(f"Error deleting run: {e}")
            
        # Refresh the UI
        for widget in self.runs_frame.winfo_children():
            widget.destroy()
        self._load_runs()

    def _start_new(self):
        self.app.show_footer()
        self.app.go_next()

    def _resume_run(self, db_file: Path):
        self.app.resume_run(db_file)
