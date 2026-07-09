"""
SQLite database for managing file index, match results, and processing state.
Ensures flat memory footprint for 100,000+ file libraries.
"""

import sqlite3
import json
import threading
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class FileStatus(Enum):
    PENDING = "pending"
    MATCHED = "matched"
    MATCHED_LOW_CONFIDENCE = "matched_low_confidence"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"
    UNMATCHED = "unmatched"


class MatchConfidence(Enum):
    CERTAIN = "certain"
    LOW = "low"
    NONE = "none"


@dataclass
class MediaFile:
    id: Optional[int]
    path: str
    filename: str
    extension: str
    size: int
    status: FileStatus
    json_path: Optional[str]
    match_confidence: Optional[MatchConfidence]
    match_tier: Optional[int]
    error_message: Optional[str]
    metadata_written: bool
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'path': self.path,
            'filename': self.filename,
            'extension': self.extension,
            'size': self.size,
            'status': self.status.value,
            'json_path': self.json_path,
            'match_confidence': self.match_confidence.value if self.match_confidence else None,
            'match_tier': self.match_tier,
            'error_message': self.error_message,
            'metadata_written': self.metadata_written
        }
    
    @classmethod
    def from_row(cls, row: Tuple) -> 'MediaFile':
        return cls(
            id=row[0],
            path=row[1],
            filename=row[2],
            extension=row[3],
            size=row[4],
            status=FileStatus(row[5]),
            json_path=row[6],
            match_confidence=MatchConfidence(row[7]) if row[7] else None,
            match_tier=row[8],
            error_message=row[9],
            metadata_written=bool(row[10])
        )

import queue

class StateDatabase:
    """Thread-safe SQLite database manager with async write queue."""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._local = threading.local()
        self._write_lock = threading.Lock()
        self._connections = []
        self._connections_lock = threading.Lock()
        self._init_database()
        
        # Async write queue with a sensible maxsize to prevent memory bloat
        self._write_queue = queue.Queue(maxsize=10000)
        self._stop_event = threading.Event()
        self._writer_thread = threading.Thread(target=self._db_writer_worker, daemon=True)
        self._writer_thread.start()
    
    def close(self):
        """Shut down the background writer thread and close connections."""
        self.flush()
        self._stop_event.set()
        # Push a dummy event to unblock queue.get()
        self._write_queue.put(None)
        if self._writer_thread.is_alive():
            self._writer_thread.join(timeout=5.0)
        
        # Close all tracked connections
        with self._connections_lock:
            for conn in self._connections:
                try:
                    conn.close()
                except Exception:
                    pass
            self._connections.clear()
        
        if hasattr(self._local, 'connection'):
            self._local.connection = None
    
    def flush(self):
        """Block until all pending async writes have been committed."""
        self._write_queue.join()
    
    def _db_writer_worker(self):
        """Background daemon thread that processes DB updates sequentially."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            while not self._stop_event.is_set() or not self._write_queue.empty():
                try:
                    # Group updates in small batches to maximize throughput
                    batch = []
                    while len(batch) < 100:
                        try:
                            update = self._write_queue.get(timeout=0.1)
                            if update is None:
                                break
                            batch.append(update)
                        except queue.Empty:
                            break
                    
                    if not batch:
                        continue
                    
                    for attempt in range(3):
                        try:
                            with self._write_lock:
                                cursor.executemany("""
                                    UPDATE media_files 
                                    SET status = ?, error_message = ?, metadata_written = ?
                                    WHERE id = ?
                                """, batch)
                                conn.commit()
                            break
                        except sqlite3.OperationalError as e:
                            if 'database is locked' in str(e) and attempt < 2:
                                time.sleep(0.2)
                            
                    for _ in batch:
                        self._write_queue.task_done()
                        
                except Exception as e:
                    logger.error(f"Database writer thread error: {e}")
        finally:
            if hasattr(self._local, 'connection') and self._local.connection:
                try:
                    self._local.connection.close()
                except Exception:
                    pass
                self._local.connection = None
            # Also clean up the queue task count just in case
            while not self._write_queue.empty():
                try:
                    self._write_queue.get_nowait()
                    self._write_queue.task_done()
                except (queue.Empty, ValueError):
                    break

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=30.0,
                check_same_thread=False
            )
            conn.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrency
            conn.execute("PRAGMA journal_mode=WAL")
            # NORMAL is safe for WAL mode (protects against process crashes)
            conn.execute("PRAGMA synchronous=NORMAL")
            # Increase cache size and busy timeout
            conn.execute("PRAGMA cache_size=-64000")
            conn.execute("PRAGMA busy_timeout=30000")
            self._local.connection = conn
            
            with self._connections_lock:
                self._connections.append(conn)
        return self._local.connection
    
    def _init_database(self):
        """Initialize database schema."""
        conn = self._get_connection()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS media_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                filename TEXT NOT NULL,
                extension TEXT NOT NULL,
                size INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                json_path TEXT,
                match_confidence TEXT,
                match_tier INTEGER,
                error_message TEXT,
                metadata_written INTEGER DEFAULT 0,
                UNIQUE(path, filename)
            );
            
            CREATE TABLE IF NOT EXISTS json_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                filename TEXT NOT NULL,
                full_path TEXT NOT NULL UNIQUE,
                processed INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS processing_state (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS run_config (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            
            CREATE INDEX IF NOT EXISTS idx_media_status ON media_files(status);
            CREATE INDEX IF NOT EXISTS idx_media_filename ON media_files(filename);
            CREATE INDEX IF NOT EXISTS idx_json_filename ON json_files(filename);
        """)
        
        with self._write_lock:
            conn.commit()
        logger.info(f"Database initialized: {self.db_path}")
    
    def reset(self):
        """Clear all data for a fresh run. Used for 'Export Again' functionality."""
        conn = self._get_connection()
        cursor = conn.cursor()
        with self._write_lock:
            cursor.execute("DELETE FROM media_files")
            cursor.execute("DELETE FROM json_files")
            cursor.execute("DELETE FROM processing_state")
            conn.commit()
        logger.info("Database reset for new session")

    def add_media_files_batch(self, rows: list) -> int:
        """Bulk-insert media files.  *rows* is a list of (path, filename, extension, size) tuples.

        Returns the number of rows actually inserted.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            with self._write_lock:
                cursor.executemany("""
                    INSERT OR IGNORE INTO media_files
                    (path, filename, extension, size, status)
                    VALUES (?, ?, ?, ?, 'pending')
                """, rows)
                conn.commit()
            return cursor.rowcount
        except sqlite3.Error as e:
            logger.error(f"Error in batch media insert: {e}")
            return 0

    def add_json_files_batch(self, rows: list) -> int:
        """Bulk-insert JSON files.  *rows* is a list of (path, filename, full_path) tuples.

        Returns the number of rows actually inserted.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            with self._write_lock:
                cursor.executemany("""
                    INSERT OR IGNORE INTO json_files
                    (path, filename, full_path)
                    VALUES (?, ?, ?)
                """, rows)
                conn.commit()
            return cursor.rowcount
        except sqlite3.Error as e:
            logger.error(f"Error in batch json insert: {e}")
            return 0

    def get_media_stats(self, img_exts: list, vid_exts: list):
        """Calculates total size, image count, and video count directly via SQL."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT SUM(size) FROM media_files WHERE status = 'completed'")
        total_size = cursor.fetchone()[0] or 0
        
        img_count = 0
        if img_exts:
            img_placeholders = ','.join('?' for _ in img_exts)
            cursor.execute(f"SELECT COUNT(*) FROM media_files WHERE status = 'completed' AND extension IN ({img_placeholders})", list(img_exts))
            img_count = cursor.fetchone()[0]
            
        vid_count = 0
        if vid_exts:
            vid_placeholders = ','.join('?' for _ in vid_exts)
            cursor.execute(f"SELECT COUNT(*) FROM media_files WHERE status = 'completed' AND extension IN ({vid_placeholders})", list(vid_exts))
            vid_count = cursor.fetchone()[0]
            
        return round(total_size / 1024, 1), img_count, vid_count

    def search_media_files(self, query=None, status=None, limit=1000) -> list[MediaFile]:
        """Fetch media files with server-side filtering."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        sql = "SELECT id, path, filename, extension, size, status, json_path, match_confidence, match_tier, error_message, metadata_written FROM media_files"
        conditions = []
        params = []
        
        if query:
            conditions.append("filename LIKE ?")
            params.append(f"%{query}%")
        
        if status:
            conditions.append("status = ?")
            params.append(status.value if hasattr(status, 'value') else status)
            
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
            
        sql += " LIMIT ?"
        params.append(limit)
        
        cursor.execute(sql, params)
        
        files = []
        for row in cursor.fetchall():
            # Convert status string back to FileStatus enum
            status_val = FileStatus(row[5]) if row[5] else FileStatus.PENDING
            conf_val = MatchConfidence(row[7]) if row[7] else MatchConfidence.NONE
            files.append(MediaFile(
                id=row[0], path=row[1], filename=row[2], extension=row[3], size=row[4],
                status=status_val, json_path=row[6], match_confidence=conf_val,
                match_tier=row[8], error_message=row[9], metadata_written=bool(row[10])
            ))
        return files
    
    def add_media_file(self, path: str, filename: str, extension: str, size: int) -> int:
        """Add a media file to the database. Returns file ID."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO media_files 
                (path, filename, extension, size, status)
                VALUES (?, ?, ?, ?, 'pending')
            """, (path, filename, extension, size))
            conn.commit()
            
            cursor.execute("""
                SELECT id FROM media_files WHERE path = ? AND filename = ?
            """, (path, filename))
            row = cursor.fetchone()
            return row[0] if row else None
        except sqlite3.Error as e:
            logger.error(f"Error adding media file {filename}: {e}")
            return None
    
    def add_json_file(self, path: str, filename: str, full_path: str) -> Optional[int]:
        """Add a JSON sidecar file to the database."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            with self._write_lock:
                cursor.execute("""
                    INSERT OR IGNORE INTO json_files 
                    (path, filename, full_path)
                    VALUES (?, ?, ?)
                """, (path, filename, full_path))
                conn.commit()
            
            cursor.execute("SELECT id FROM json_files WHERE full_path = ?", (full_path,))
            row = cursor.fetchone()
            return row[0] if row else None
        except sqlite3.Error as e:
            logger.error(f"Error adding JSON file {filename}: {e}")
            return None
    
    def update_file_status(self, file_id: int, status: FileStatus, 
                          error_message: Optional[str] = None):
        """Update the status of a media file via the async write queue."""
        metadata_written = 1 if status == FileStatus.COMPLETED else 0
        self._write_queue.put((status.value, error_message, metadata_written, file_id))
    
    def update_match_info(self, file_id: int, json_path: str,
                         confidence: MatchConfidence, tier: int):
        """Update match information for a media file."""
        self.update_match_info_batch([(json_path, confidence.value, tier, 
            FileStatus.MATCHED.value if confidence == MatchConfidence.CERTAIN 
            else FileStatus.MATCHED_LOW_CONFIDENCE.value, file_id)])
            
    def update_match_info_batch(self, rows: list):
        """Bulk update match information. rows is a list of (json_path, match_confidence, match_tier, status, id)."""
        if not rows:
            return
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            with self._write_lock:
                cursor.executemany("""
                    UPDATE media_files 
                    SET json_path = ?, match_confidence = ?, match_tier = ?, status = ?
                    WHERE id = ?
                """, rows)
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Error in batch update match info: {e}")
            
    def update_file_status_batch(self, rows: list):
        """Bulk update file status. rows is a list of (status, error_message, metadata_written, id)."""
        if not rows:
            return
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            with self._write_lock:
                cursor.executemany("""
                    UPDATE media_files 
                    SET status = ?, error_message = ?, metadata_written = ?
                    WHERE id = ?
                """, rows)
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Error in batch file status update: {e}")
    
    def get_files_by_status(self, status: FileStatus) -> List[MediaFile]:
        """Get all media files with a specific status."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT * FROM media_files WHERE status = ?", (status.value,))
            return [MediaFile.from_row(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error fetching files with status {status}: {e}")
            return []

    def get_file_by_path_filename(self, path: str, filename: str) -> Optional[MediaFile]:
        """Get a media file by its unique path and filename pair."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "SELECT * FROM media_files WHERE path = ? AND filename = ?",
                (path, filename)
            )
            row = cursor.fetchone()
            if not row:
                cursor.execute(
                    "SELECT * FROM media_files WHERE path = ? AND filename = ? COLLATE NOCASE",
                    (path, filename)
                )
                row = cursor.fetchone()
            return MediaFile.from_row(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Error fetching media file {path}/{filename}: {e}")
            return None

    def get_file_by_exact_name(self, filename: str) -> Optional[MediaFile]:
        """Get a media file by its exact filename, regardless of path."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "SELECT * FROM media_files WHERE filename = ?",
                (filename,)
            )
            row = cursor.fetchone()
            if not row:
                cursor.execute(
                    "SELECT * FROM media_files WHERE filename = ? COLLATE NOCASE",
                    (filename,)
                )
                row = cursor.fetchone()
            return MediaFile.from_row(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Error fetching media file by exact name {filename}: {e}")
            return None

    def get_all_files_by_exact_name(self, filename: str) -> List[MediaFile]:
        """Get all media files by exact filename, regardless of path."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "SELECT * FROM media_files WHERE filename = ?",
                (filename,)
            )
            rows = cursor.fetchall()
            if not rows:
                cursor.execute(
                    "SELECT * FROM media_files WHERE filename = ? COLLATE NOCASE",
                    (filename,)
                )
                rows = cursor.fetchall()
            return [MediaFile.from_row(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Error fetching media files by exact name {filename}: {e}")
            return []

    def get_file_by_id(self, file_id: int) -> Optional[MediaFile]:
        """Get a media file by database ID."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM media_files WHERE id = ?", (file_id,))
            row = cursor.fetchone()
            return MediaFile.from_row(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Error fetching media file {file_id}: {e}")
            return None

    def try_mark_processing(self, file_id: int) -> bool:
        """
        Atomically claim a matched file for processing.

        Returns False when another worker already claimed or finished the file.
        """
        # Ensure any pending async status writes are flushed before we read
        self.flush()
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            with self._write_lock:
                cursor.execute("""
                    UPDATE media_files
                    SET status = ?, error_message = NULL, metadata_written = 0
                    WHERE id = ?
                      AND status IN (?, ?, ?)
                """, (
                    FileStatus.PROCESSING.value,
                    file_id,
                    FileStatus.MATCHED.value,
                    FileStatus.MATCHED_LOW_CONFIDENCE.value,
                    FileStatus.UNMATCHED.value
                ))
                conn.commit()
                return cursor.rowcount == 1
        except sqlite3.Error as e:
            logger.error(f"Error claiming file {file_id} for processing: {e}")
            return False

    def get_media_files_by_ids(self, file_ids: List[int]) -> List[MediaFile]:
        """Get media files for the requested IDs without loading the full table."""
        if not file_ids:
            return []

        conn = self._get_connection()
        cursor = conn.cursor()
        files: List[MediaFile] = []

        try:
            for start in range(0, len(file_ids), 900):
                chunk = file_ids[start:start + 900]
                placeholders = ",".join("?" for _ in chunk)
                cursor.execute(
                    f"SELECT * FROM media_files WHERE id IN ({placeholders})",
                    chunk
                )
                files.extend(MediaFile.from_row(row) for row in cursor.fetchall())
            return files
        except sqlite3.Error as e:
            logger.error(f"Error fetching media files by ID: {e}")
            return []
    
    def get_all_media_files(self) -> List[MediaFile]:
        """Get all media files."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT * FROM media_files")
            return [MediaFile.from_row(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error resetting uncompleted files: {e}")
            return []

    def save_config(self, config: dict):
        """Save run configuration to database."""
        try:
            with self._write_lock:
                conn = self._get_connection()
                cursor = conn.cursor()
                # We stringify paths if any, and dump the rest
                for key, value in config.items():
                    if isinstance(value, list) and all(isinstance(p, Path) for p in value):
                        val_str = json.dumps([str(p) for p in value])
                    elif isinstance(value, Path):
                        val_str = str(value)
                    else:
                        val_str = json.dumps(value)
                    cursor.execute("INSERT OR REPLACE INTO run_config (key, value) VALUES (?, ?)", (key, val_str))
                conn.commit()
        except Exception as e:
            logger.error(f"Error saving config to DB: {e}")

    def load_config(self) -> dict:
        """Load run configuration from database."""
        config = {}
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM run_config")
            for key, value in cursor.fetchall():
                try:
                    if key == "inputs":
                        config[key] = [Path(p) for p in json.loads(value)]
                    elif key == "destination":
                        config[key] = Path(value) if value != "null" else None
                    else:
                        config[key] = json.loads(value)
                except Exception:
                    config[key] = value
            return config
        except Exception as e:
            logger.error(f"Error loading config from DB: {e}")
            return {}
    
    def get_all_json_files(self) -> List[Tuple[str, str]]:
        """Get all JSON files as a list of (filename, full_path) tuples.

        Returns a list instead of a dict so that duplicate filenames
        across different directories are preserved.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT filename, full_path FROM json_files")
            return [(row[0], row[1]) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error fetching JSON files: {e}")
            return []
    
    def get_statistics(self) -> Dict[str, int]:
        """Get processing statistics."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT status, COUNT(*) FROM media_files GROUP BY status")
            stats = {status: 0 for status in FileStatus}
            for row in cursor.fetchall():
                stats[FileStatus(row[0])] = row[1]
            return stats
        except sqlite3.Error as e:
            logger.error(f"Error fetching statistics: {e}")
            return {}
    
    def save_processing_state(self, key: str, value: Any):
        """Save a processing state value."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            with self._write_lock:
                cursor.execute("""
                    INSERT OR REPLACE INTO processing_state (key, value)
                    VALUES (?, ?)
                """, (key, json.dumps(value)))
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Error saving state {key}: {e}")
    
    def get_processing_state(self, key: str, default: Any = None) -> Any:
        """Get a processing state value."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT value FROM processing_state WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
            return default
        except sqlite3.Error as e:
            logger.error(f"Error fetching state {key}: {e}")
            return default
    
    def save_run_stats(self, stats: dict):
        """Persist run statistics for post-run reporting."""
        self.save_processing_state('run_stats', stats)

    def get_run_stats(self) -> dict:
        """Retrieve the most recently saved run statistics."""
        return self.get_processing_state('run_stats', {})


    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
