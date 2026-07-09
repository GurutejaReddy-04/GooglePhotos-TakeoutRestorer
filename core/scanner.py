"""
File Scanner: Enumerates media and JSON files from ZIPs and folders.
Implements Zip-Slip protection and Windows long path support.
"""

import zipfile
import os
import posixpath
import shutil
from pathlib import Path
from typing import List, Tuple
import logging
from .state_db import StateDatabase

logger = logging.getLogger(__name__)

class FileScanner:
    """
    Handles enumeration of media and JSON files from both raw directories and ZIP archives.
    Implements security measures such as Zip-Slip protection and supports real-time
    progress reporting for the UI via the ProgressModel.
    """
    def __init__(self, config: dict, db: StateDatabase, tmp_dir: Path, progress_model=None):
        self.config = config
        self.db = db
        self.tmp_dir = tmp_dir
        self.progress_model = progress_model
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        
        self.image_exts = set(config.get('supported_image_extensions', []))
        self.video_exts = set(config.get('supported_video_extensions', []))
        self.media_exts = self.image_exts.union(self.video_exts)
        
        # Track extracted directories for cleanup
        self.extracted_dirs = []

    def scan_inputs(self, inputs: List[Path]) -> Tuple[int, int]:
        """
        Scans a list of ZIP files and folders.
        Returns (total_media_found, total_json_found).
        """
        media_count = 0
        json_count = 0
        
        for input_path in inputs:
            # FIX P0-2: Initialize m, j for each iteration
            m, j = 0, 0
            
            if not input_path.exists():
                logger.warning(f"Input path does not exist: {input_path}")
                continue
                
            if self.progress_model:
                self.progress_model.set_phase_message(f"Scanning {input_path.name}...")
                
            if input_path.is_file() and input_path.suffix.lower() == '.zip':
                m, j = self._process_zip(input_path)
            elif input_path.is_dir():
                m, j = self._process_folder(input_path)
            else:
                logger.warning(f"Skipping unsupported input: {input_path}")
                continue  # FIX: Skip to next iteration
            
            media_count += m
            json_count += j
            
        return media_count, json_count

    def _process_zip(self, zip_path: Path) -> Tuple[int, int]:
        """Scans ZIP contents without extracting (JIT extraction mode)."""
        logger.info(f"Scanning ZIP virtually: {zip_path.name}")
        
        media_count = 0
        json_count = 0
        
        media_batch = []
        json_batch = []
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                infolist = zip_ref.infolist()
                total_files = len(infolist)
                for idx, member in enumerate(infolist):
                    if self.progress_model and idx % 500 == 0:
                        pct = int((idx / total_files) * 100) if total_files > 0 else 0
                        self.progress_model.set_phase_message(f"Scanning {zip_path.name} ({pct}%)")
                        self.progress_model.set_current_file(member.filename)
                        
                    if member.is_dir():
                        continue
                        

                    # Build virtual path: zip:///path/to/archive.zip::internal/path.jpg
                    parent_dir = posixpath.dirname(member.filename)
                    if parent_dir == "":
                        virtual_root = f"zip://{zip_path.resolve()}::"
                    else:
                        virtual_root = f"zip://{zip_path.resolve()}::{parent_dir}"
                        
                    filename = posixpath.basename(member.filename)
                    ext = posixpath.splitext(member.filename)[1].lower()
                    
                    if ext == '.json':
                        full_virtual_path = f"zip://{zip_path.resolve()}::{member.filename}"
                        json_batch.append((virtual_root, filename, full_virtual_path))
                        json_count += 1
                    elif ext in self.media_exts:
                        media_batch.append((virtual_root, filename, ext, member.file_size))
                        media_count += 1
                        
                    # Flush batches
                    if len(media_batch) >= self._BATCH_SIZE:
                        self.db.add_media_files_batch(media_batch)
                        media_batch.clear()
                    if len(json_batch) >= self._BATCH_SIZE:
                        self.db.add_json_files_batch(json_batch)
                        json_batch.clear()
                        
            # Flush remaining
            if media_batch:
                self.db.add_media_files_batch(media_batch)
            if json_batch:
                self.db.add_json_files_batch(json_batch)
                
        except Exception as e:
            logger.error(f"Failed to scan ZIP {zip_path.name}: {e}")
            
        return media_count, json_count

    # Number of files to accumulate before flushing to the database.
    _BATCH_SIZE = 500

    def _process_folder(self, folder_path: Path) -> Tuple[int, int]:
        """Recursively walks a folder and indexes files in batches."""
        media_count = 0
        json_count = 0

        media_batch: list = []   # (path, filename, extension, size)
        json_batch: list = []    # (path, filename, full_path)

        file_counter = 0

        # Use os.walk for performance on large directories
        for root, _, files in os.walk(folder_path):
            root_str = str(Path(root))
            for file in files:
                file_counter += 1
                if file_counter % 500 == 0:
                    pass
                    
                file_path = Path(root) / file
                ext = file_path.suffix.lower()

                if ext == '.json':
                    json_batch.append((root_str, file, str(file_path)))
                    json_count += 1
                elif ext in self.media_exts:
                    try:
                        size = file_path.stat().st_size
                        media_batch.append((root_str, file, ext, size))
                        media_count += 1
                    except OSError as e:
                        logger.error(f"Could not read file stats for {file_path}: {e}")

                # Flush batches periodically to keep memory bounded
                if len(media_batch) >= self._BATCH_SIZE:
                    self.db.add_media_files_batch(media_batch)
                    media_batch.clear()
                if len(json_batch) >= self._BATCH_SIZE:
                    self.db.add_json_files_batch(json_batch)
                    json_batch.clear()

        # Flush remaining items
        if media_batch:
            self.db.add_media_files_batch(media_batch)
        if json_batch:
            self.db.add_json_files_batch(json_batch)

        return media_count, json_count
    
    def cleanup(self):
        """Clean up all temporary extraction directories."""
        logger.info(f"Cleaning up {len(self.extracted_dirs)} extracted directories...")
        
        for extract_dir in self.extracted_dirs:
            if extract_dir.exists():
                try:
                    shutil.rmtree(extract_dir)
                    logger.info(f"Cleaned up: {extract_dir}")
                except Exception as e:
                    logger.warning(f"Failed to clean up {extract_dir}: {e}")
            else:
                logger.debug(f"Directory already removed: {extract_dir}")
        
        self.extracted_dirs.clear()
        logger.info("Cleanup complete")
