"""
File Processor: Multi-threaded orchestration engine.
"""

import os
import time
import queue
import shutil
import threading
import concurrent.futures
from datetime import datetime
from pathlib import Path
from typing import List, Callable, Optional
from concurrent.futures import ThreadPoolExecutor
import logging

from .state_db import StateDatabase, FileStatus
from .exiftool_engine import ExifToolEngine, ExifToolPool
from .writer import MetadataWriter
from .logger import ProcessingLogger
from .progress_model import ProgressModel

logger = logging.getLogger(__name__)

class FileProcessor:
    """
    Multi-threaded orchestration engine for processing media files.
    Manages a pool of ExifTool workers, orchestrates the parsing and writing
    of metadata, and tracks overall progress and error reporting.
    """
    def __init__(self, db: StateDatabase, config: dict, log_dir: Path, run_id: str = None,
                 high_performance: bool = False, progress_model: ProgressModel = None):
        self.db = db
        self.config = config
        self.run_id = run_id
        self.high_performance = high_performance
        self.progress_model = progress_model
        settings = config.get('settings', {})
        self.logger = ProcessingLogger(
            log_dir,
            run_id,
            anonymous=settings.get('anonymous_logging', False)
        )
        
        exiftool_path = config.get('exiftool_path', 'tools/exiftool.exe')

        # Dynamic worker count
        if high_performance:
            cores = os.cpu_count() or 4
            try:
                import psutil
                avail_mb = psutil.virtual_memory().available // (1024 * 1024)
                max_by_mem = max(2, avail_mb // 80)
            except ImportError:
                max_by_mem = cores * 2
            self.max_workers = min(cores, max_by_mem, 12) # Capped at 12 to prevent memory exhaustion
        else:
            self.max_workers = config.get('processing', {}).get('max_workers', 4)

        # Engine selection
        if high_performance:
            self.engine = ExifToolPool(exiftool_path, pool_size=self.max_workers)
        else:
            self.engine = ExifToolEngine(exiftool_path)

        self.writer = MetadataWriter(db, self.engine, config)
        
        self._cancel_event = threading.Event()
        self._progress_queue = queue.Queue()

    def __del__(self):
        try:
            if hasattr(self, 'engine') and self.engine:
                self.engine.stop()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self, 'engine') and self.engine:
            self.engine.stop()

    def _init_output_dirs(self, output_dir: Path):
        """Creates the standard output folder structure."""
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "Completed").mkdir(exist_ok=True)
        (output_dir / "Errors").mkdir(exist_ok=True)
        (output_dir / "Unmatched").mkdir(exist_ok=True)
        logger.info(f"Output directories initialized at {output_dir}")

    def process_files(self, file_ids: List[int], output_dir: Path, output_mode: str,
                      progress_callback: Optional[Callable] = None):
        """
        Processes a list of file IDs using a thread pool.
        """
        logger.info(f"Starting process_files with {len(file_ids)} files")
        self._cancel_event.clear()
        self._init_output_dirs(output_dir)

        process_start = time.monotonic()
        completed_count = 0
        error_count = 0
        skipped_count = 0

        files_to_process = [
            f for f in self.db.get_media_files_by_ids(file_ids)
            if f.status != FileStatus.COMPLETED
        ]
        total = len(files_to_process)
        
        logger.info(f"Files to process: {len(files_to_process)}")

        if self.progress_model:
            self.progress_model.total_processable = total
            self.progress_model.set_phase("processing", "Processing files with ExifTool...")

        try:
            try:
                from concurrent.futures import wait, FIRST_COMPLETED
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    logger.debug("ThreadPoolExecutor started")
                    
                    iterator = iter(files_to_process)
                    future_to_file = {}
                    
                    # Initial fill (buffer 2x the workers to keep queue full)
                    for _ in range(min(self.max_workers * 2, len(files_to_process))):
                        try:
                            f = next(iterator)
                            fut = executor.submit(self.writer.process_file, f, output_dir, output_mode, self._cancel_event)
                            future_to_file[fut] = f
                        except StopIteration:
                            break
                            
                    logger.debug(f"Submitted initial {len(future_to_file)} futures")

                    while future_to_file:
                        if self._cancel_event.is_set():
                            logger.info("Cancel event set, shutting down")
                            executor.shutdown(wait=False, cancel_futures=True)
                            break

                        done, not_done = wait(future_to_file.keys(), return_when=FIRST_COMPLETED)

                        for future in done:
                            media_file = future_to_file.pop(future)
                            
                            # Refill the queue instantly
                            try:
                                f = next(iterator)
                                fut = executor.submit(self.writer.process_file, f, output_dir, output_mode, self._cancel_event)
                                future_to_file[fut] = f
                            except StopIteration:
                                pass

                            result = {"status": "error", "message": "Unknown error"}
                            
                            try:
                                result = future.result(timeout=300)  # 5 minute timeout per file
                                
                                if result["status"] == "completed":
                                    log_level = "SUCCESS"
                                elif result["status"] == "skipped":
                                    log_level = "AUDIT"
                                else:
                                    log_level = "ERROR"

                                self.logger.log(
                                    log_level,
                                    f"{media_file.filename} -> {result['status'].capitalize()} [{result['message']}]",
                                    file_info=result
                                )
                            except (InterruptedError, concurrent.futures.CancelledError):
                                result = {"status": "skipped", "message": "Cancelled"}
                                self.db.update_file_status(media_file.id, FileStatus.PENDING, "Cancelled by user")
                                self.logger.log("AUDIT", f"{media_file.filename} -> CANCELLED", file_info=result)
                            except Exception as e:
                                if self._cancel_event.is_set():
                                    result = {"status": "skipped", "message": "Cancelled during exception"}
                                    self.db.update_file_status(media_file.id, FileStatus.PENDING, "Cancelled by user")
                                    self.logger.log("AUDIT", f"{media_file.filename} -> CANCELLED", file_info=result)
                                else:
                                    result = {
                                        "file_id": media_file.id,
                                        "filename": media_file.filename,
                                        "status": "error",
                                        "message": str(e)
                                    }
                                    self.db.update_file_status(media_file.id, FileStatus.ERROR, str(e))
                                    logger.error(f"Exception processing {media_file.filename}: {e}")
                                    self.logger.log(
                                        "ERROR",
                                        f"{media_file.filename} -> CRASH [{str(e)}]",
                                        file_info=result
                                    )

                            # Update separate counters
                            status = result.get("status", "error")
                            
                            if status == "completed":
                                completed_count += 1
                                if self.progress_model:
                                    self.progress_model.set_current_file(media_file.filename)
                                    self.progress_model.increment_completed()
                                    # Track output size
                                    try:
                                        self.progress_model.add_output_bytes(media_file.size)
                                    except Exception:
                                        pass
                            elif status == "skipped":
                                if result.get("message", "").startswith("Already completed"):
                                    pass
                                else:
                                    skipped_count += 1
                                    if self.progress_model:
                                        self.progress_model.increment_skipped()
                            else:
                                error_count += 1
                                if self.progress_model:
                                    self.progress_model.increment_failed()
                                    
                            lp_status = result.get("live_photo_status")
                            if lp_status:
                                lp_s = lp_status.get("status")
                                if lp_s == "completed":
                                    completed_count += 1
                                    if self.progress_model:
                                        self.progress_model.increment_completed()
                                        try:
                                            if lp_status.get("size"):
                                                self.progress_model.add_output_bytes(lp_status["size"])
                                        except Exception:
                                            pass
                                elif lp_s == "error":
                                    error_count += 1
                                    if self.progress_model:
                                        self.progress_model.increment_failed()

                            # Update phase message periodically
                            if self.progress_model:
                                processed_so_far = completed_count + error_count + skipped_count
                                pct = round((processed_so_far / total) * 100, 1) if total > 0 else 0
                                self.progress_model.set_phase_message(
                                    f"Processing files... {processed_so_far}/{total} ({pct}%)"
                                )

                            # Backward-compatible callback
                            processed_so_far = completed_count + error_count + skipped_count
                            if progress_callback:
                                progress_callback(processed_so_far, total, media_file.filename, status)
                            
                logger.info(f"All files processed. Completed: {completed_count}/{total}")
            except Exception as e:
                logger.error(f"Fatal error in process_files: {e}", exc_info=True)
                raise
            finally:
                logger.debug("Cleanup in finally block")

            if self.progress_model:
                self.progress_model.end_phase("processing")

            # Handle Unmatched Files
            settings = self.config.get('settings', {})
            unmatched_files = self.db.get_files_by_status(FileStatus.UNMATCHED)
            unmatched_count = len(unmatched_files) if unmatched_files else 0

            if self.progress_model:
                self.progress_model.unmatched = unmatched_count

            if settings.get('unmatched_enabled', True):
                if self.progress_model:
                    self.progress_model.set_phase_message("Moving unmatched files...")
                logger.info("Moving unmatched files...")
                self._move_unmatched_files(output_dir, output_mode)

            if self.progress_model:
                self.progress_model.set_phase_message("Copying error files...")
            logger.info("Copying error files...")
            self._copy_error_files(output_dir)

            # Final Reconciliation
            if self.progress_model:
                self.progress_model.set_phase_message("Finalizing export...")

            stats = self.db.get_statistics()
            low_conf_count = stats.get(FileStatus.MATCHED_LOW_CONFIDENCE, 0)
            self.logger.audit_reconciliation(
                scanned=sum(stats.values()),
                completed=stats.get(FileStatus.COMPLETED, 0),
                unmatched=stats.get(FileStatus.UNMATCHED, 0),
                errors=stats.get(FileStatus.ERROR, 0),
                low_confidence=low_conf_count
            )

            # Save run stats to DB
            elapsed = time.monotonic() - process_start
            stats_to_save = {
                'start_time_iso': datetime.now().isoformat(),
                'duration_seconds': round(elapsed, 1),
                'total_processable': total,
                'total_db_rows': sum(stats.values()),
                'completed': completed_count,
                'failed': error_count,
                'skipped': skipped_count,
                'unmatched': unmatched_count,
                'workers_used': self.max_workers,
                'high_performance': self.high_performance,
                'phase_times': dict(self.progress_model.phase_times) if self.progress_model else {},
                'avg_speed': round(total / elapsed, 2) if elapsed > 0 else 0,
                'output_bytes': self.progress_model.output_bytes if self.progress_model else 0,
            }
            self.db.save_run_stats(stats_to_save)
        finally:
            # Stop ExifTool
            try:
                self.engine.stop()
            except Exception as e:
                logger.warning(f"Error stopping ExifTool: {e}")
            
            # Cleanup logger
            try:
                self.logger.cleanup()
            except Exception as e:
                logger.warning(f"Error cleaning up logger: {e}")
            
            logger.info("process_files completed successfully")

    def _move_unmatched_files(self, output_dir: Path, output_mode: str = 'copy'):
        """Copies or moves unmatched files to the Unmatched folder."""
        unmatched_files = self.db.get_files_by_status(FileStatus.UNMATCHED)
        unmatched_dir = output_dir / "Unmatched"
        
        if not unmatched_files:
            return

        use_copy = (output_mode == 'copy')
        action = "Copying" if use_copy else "Moving"
        logger.info(f"{action} {len(unmatched_files)} unmatched files...")
        for media_file in unmatched_files:
            source_str = self.writer._get_full_path(media_file.path, media_file.filename)
            target = unmatched_dir / media_file.filename
            
            counter = 1
            while target.exists():
                target = unmatched_dir / f"{target.stem}_{counter}{target.suffix}"
                counter += 1
            
            try:
                if source_str.startswith("zip://"):
                    self.writer._extract_jit(source_str, output_dir, target_path_override=target)
                else:
                    source = Path(source_str)
                    if source.exists():
                        if use_copy:
                            shutil.copy2(str(source), str(target))
                        else:
                            shutil.move(str(source), str(target))
            except Exception as e:
                logger.error(f"Failed to {action.lower()} unmatched file {media_file.filename}: {e}")

    def _copy_error_files(self, output_dir: Path):
        """Copies files that encountered errors to the Errors folder."""
        error_files = self.db.get_files_by_status(FileStatus.ERROR)
        error_dir = output_dir / "Errors"
        
        if not error_files:
            return

        logger.info(f"Copying {len(error_files)} error files...")
        for media_file in error_files:
            source_str = self.writer._get_full_path(media_file.path, media_file.filename)
            target = error_dir / media_file.filename
            
            counter = 1
            while target.exists():
                target = error_dir / f"{target.stem}_{counter}{target.suffix}"
                counter += 1
            
            try:
                if source_str.startswith("zip://"):
                    self.writer._extract_jit(source_str, output_dir, target_path_override=target)
                else:
                    source = Path(source_str)
                    if source.exists():
                        shutil.copy2(str(source), str(target))
            except Exception as e:
                logger.error(f"Failed to copy error file {media_file.filename}: {e}")

    def cancel(self):
        """Signals the processor to stop."""
        self._cancel_event.set()
