"""
Metadata Writer: Orchestrates writing metadata to media files.
"""

import os
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import logging
import zipfile
import uuid

from .parser import JSONParser, ParsedMetadata
from .exiftool_engine import ExifToolEngine
from .timezone_resolver import TimezoneResolver
from .state_db import StateDatabase, MediaFile, FileStatus

logger = logging.getLogger(__name__)

class MetadataWriter:
    def __init__(self, db: StateDatabase, engine: ExifToolEngine, config: dict):
        self.db = db
        self.engine = engine
        self.config = config
        self.settings = config.get('settings', {})
        
        self.live_photo_config = config.get('live_photo_pairs', {
            'image_ext': '.jpg',
            'video_ext': '.mov'
        })

    def process_file(self, media_file: MediaFile, output_dir: Optional[Path], output_mode: str, cancel_event=None) -> Dict[str, Any]:
        """
        Processes a single media file: parses JSON, writes metadata, moves/copies.
        Returns a status dictionary.
        """
        result = {
            "file_id": media_file.id,
            "filename": media_file.filename,
            "status": "error",
            "message": ""
        }

        # FIX: Initialize temp_copy_path BEFORE try block to prevent UnboundLocalError
        temp_copy_path = None
        temp_files_to_cleanup = []

        try:
            if media_file.id and not self.db.try_mark_processing(media_file.id):
                current_file = self.db.get_file_by_id(media_file.id)
                result["status"] = "skipped"
                result["message"] = (
                    f"Already {current_file.status.value}"
                    if current_file else
                    "Already claimed by another worker"
                )
                return result

            # 1. Parse JSON
            if not media_file.json_path:
                if media_file.status == FileStatus.MATCHED:
                    # Live Photo Video correctly paired with an image. Skip independent processing.
                    result["status"] = "skipped"
                    result["message"] = "Live Photo Video (processed alongside image)"
                    return result
                
                if self.settings.get('unmatched_enabled', False) and media_file.status == FileStatus.UNMATCHED:
                    return self._process_unmatched(media_file, output_dir, output_mode, cancel_event)
                
                raise ValueError("No JSON path associated with media file.")
            
            json_str_path = media_file.json_path
            if json_str_path.startswith("zip://"):
                jit_json_path = self._extract_jit(json_str_path, output_dir)
                temp_files_to_cleanup.append(jit_json_path)
                json_path = jit_json_path
            else:
                json_path = Path(json_str_path)
                
            metadata = JSONParser.parse(json_path)
            if not metadata or metadata.taken_timestamp is None:
                raise ValueError("Failed to parse valid timestamp from JSON.")

            # 2. Build ExifTool tags
            tags = self._build_tags(metadata)

            # 3. Write Metadata via ExifTool
            source_str_path = self._get_full_path(media_file.path, media_file.filename)
            
            if output_mode == 'copy' and output_dir:
                target_dir = output_dir / "Completed"
                target_dir.mkdir(parents=True, exist_ok=True)
                target_path = target_dir / media_file.filename
                
                # Prevent filename collisions
                counter = 1
                while target_path.exists():
                    target_path = target_dir / f"{target_path.stem}_{counter}{target_path.suffix}"
                    counter += 1
                    
                temp_copy_path = target_path
                
                if source_str_path.startswith("zip://"):
                    # Direct extraction, avoids double I/O
                    self._extract_jit(source_str_path, output_dir, target_path_override=target_path)
                else:
                    shutil.copy2(Path(source_str_path), target_path)
                    
            elif output_mode == 'in-place':
                if source_str_path.startswith("zip://"):
                    raise ValueError("In-Place mode is not supported for ZIP archives. Please use Copy mode.")
                target_path = Path(source_str_path)
            else:
                target_path = Path(source_str_path)

            keep_backup = (
                output_mode == 'in-place' and
                self.settings.get('in_place_backup_enabled', True)
            )
            success = self.engine.write_metadata(str(target_path), tags, keep_backup=keep_backup, cancel_event=cancel_event)
            if not success:
                # FIX: Auto-heal Google Takeout HEIC/JPEG extension mismatch
                is_jpeg_signature = False
                try:
                    with open(target_path, 'rb') as f:
                        is_jpeg_signature = f.read(3) == b'\xff\xd8\xff'
                except Exception:
                    pass

                if target_path.suffix.lower() == '.heic' and is_jpeg_signature:
                    logger.info(f"Auto-healing mismatched extension: {target_path.name} is actually a JPEG.")
                    new_target_path = target_path.with_suffix('.jpg')
                    
                    # Ensure we don't overwrite an existing file by accident
                    if new_target_path.exists() and new_target_path != target_path:
                        counter = 1
                        healed_path = target_path.with_name(f"{target_path.stem}_healed.jpg")
                        while healed_path.exists():
                            healed_path = target_path.with_name(f"{target_path.stem}_healed_{counter}.jpg")
                            counter += 1
                        new_target_path = healed_path
                        
                    target_path.rename(new_target_path)
                    target_path = new_target_path
                    
                    if output_mode == 'copy':
                        temp_copy_path = target_path
                        
                    # Retry ExifTool injection
                    success = self.engine.write_metadata(str(target_path), tags, keep_backup=keep_backup)
                    if not success:
                        raise RuntimeError("ExifTool failed even after auto-healing HEIC to JPG.")
                else:
                    raise RuntimeError("ExifTool reported failure or no changes made.")

            # 4. Apply File System Timestamps (MUST be after ExifTool)
            if metadata.taken_timestamp is not None:
                ts = metadata.taken_timestamp
                os.utime(str(target_path), (ts, ts))

            # 5. Handle Live Photos (if applicable)
            live_photo_result = self._handle_live_photo(media_file, metadata, target_path, output_dir, output_mode, cancel_event=cancel_event, temp_files_to_cleanup=temp_files_to_cleanup)
            if live_photo_result:
                result["live_photo_status"] = live_photo_result

            result["status"] = "completed"
            result["message"] = "Successfully processed with metadata"
            self.db.update_file_status(media_file.id, FileStatus.COMPLETED)

        except Exception as e:
            result["status"] = "error"
            result["message"] = str(e)
            self.db.update_file_status(media_file.id, FileStatus.ERROR, str(e))
            
            # FIX P2-3: Clean up partial copy on failure
            # Now temp_copy_path is always defined (either None or a Path)
            if output_mode == 'copy' and temp_copy_path and temp_copy_path.exists():
                try:
                    temp_copy_path.unlink()
                    logger.info(f"Removed partial copy on failure: {temp_copy_path}")
                except Exception as cleanup_error:
                    logger.error(f"Failed to clean up {temp_copy_path}: {cleanup_error}")
            
            logger.error(f"Error processing {media_file.filename}: {e}")
            
        finally:
            for tmp_file in temp_files_to_cleanup:
                try:
                    if tmp_file.exists():
                        tmp_file.unlink()
                except Exception as cleanup_error:
                    logger.debug(f"Failed to clean up JIT file {tmp_file}: {cleanup_error}")

        return result

    def _process_unmatched(self, media_file: MediaFile, output_dir: Optional[Path], output_mode: str, cancel_event=None) -> Dict[str, Any]:
        """Handles unmatched files by safely copying/extracting them to the Unmatched folder."""
        if not output_dir or output_mode != 'copy':
            return {"status": "error", "message": "Unmatched files can only be processed in Copy mode with an output directory."}
            
        try:
            source_str_path = self._get_full_path(media_file.path, media_file.filename)
            target_dir = output_dir / "Unmatched"
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / media_file.filename
            
            counter = 1
            while target_path.exists():
                target_path = target_dir / f"{target_path.stem}_{counter}{target_path.suffix}"
                counter += 1
                
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("Cancelled by user")
                
            if source_str_path.startswith("zip://"):
                self._extract_jit(source_str_path, output_dir, target_path_override=target_path)
            else:
                shutil.copy2(Path(source_str_path), target_path)
                
            self.db.update_file_status(media_file.id, FileStatus.COMPLETED)
            return {"status": "completed", "file_id": media_file.id, "message": "Copied to Unmatched"}
        except Exception as e:
            self.db.update_file_status(media_file.id, FileStatus.ERROR, str(e))
            return {"status": "error", "file_id": media_file.id, "message": str(e)}

    def _build_tags(self, metadata: ParsedMetadata) -> Dict[str, Any]:
        """Builds the dictionary of ExifTool tags."""
        tags = {}
        
        # Timestamps
        if metadata.taken_timestamp is not None:
            dt = datetime.fromtimestamp(metadata.taken_timestamp, tz=timezone.utc)
            formatted_dt = self._format_exif_datetime(dt)
            tags["DateTimeOriginal"] = formatted_dt
            tags["DateTimeDigitized"] = formatted_dt

        # GPS
        if self.settings.get('gps_enabled', True):
            if metadata.latitude is not None and metadata.longitude is not None:
                # Skip if coordinates are 0.0 (null island - means no GPS)
                if metadata.latitude != 0.0 or metadata.longitude != 0.0:
                    tags["GPSLatitude"] = f"{abs(metadata.latitude)} {'N' if metadata.latitude >= 0 else 'S'}"
                    tags["GPSLongitude"] = f"{abs(metadata.longitude)} {'E' if metadata.longitude >= 0 else 'W'}"
                    if metadata.altitude is not None and metadata.altitude != 0.0:
                        tags["GPSAltitude"] = f"{abs(metadata.altitude)} {'Above Sea Level' if metadata.altitude >= 0 else 'Below Sea Level'}"

        # Timezone Correction
        if metadata.taken_timestamp is not None and self._has_real_gps(metadata):
            if self.settings.get('timezone_enabled', True):
                local_dt = TimezoneResolver.get_local_timestamp(
                    metadata.taken_timestamp, metadata.latitude, metadata.longitude
                )
                local_formatted = self._format_exif_datetime(local_dt)
                tags["DateTimeOriginal"] = local_formatted
                tags["DateTimeDigitized"] = local_formatted

        # Text Metadata
        if metadata.description:
            tags["ImageDescription"] = metadata.description
        if metadata.title:
            tags["XPTitle"] = metadata.title
            tags["Title"] = metadata.title

        return tags

    def _has_real_gps(self, metadata: ParsedMetadata) -> bool:
        """Return True when metadata contains coordinates other than Null Island."""
        return (
            metadata.latitude is not None and
            metadata.longitude is not None and
            (metadata.latitude != 0.0 or metadata.longitude != 0.0)
        )

    def _format_exif_datetime(self, dt: datetime) -> str:
        """Format a datetime for EXIF date/time tags.

        When the datetime is timezone-aware, the UTC offset is appended
        (e.g. '2024:01:15 14:30:00+05:30') which ExifTool understands.
        """
        base = dt.strftime("%Y:%m:%d %H:%M:%S")
        if dt.tzinfo is not None and dt.utcoffset() is not None:
            offset = dt.strftime("%z")          # e.g. '+0530'
            offset = offset[:3] + ":" + offset[3:]  # -> '+05:30'
            base += offset
        return base

    def _date_time_original_for_metadata(self, metadata: ParsedMetadata) -> str:
        """Build DateTimeOriginal, honoring timezone correction when possible."""
        if self.settings.get('timezone_enabled', True) and self._has_real_gps(metadata):
            local_dt = TimezoneResolver.get_local_timestamp(
                metadata.taken_timestamp, metadata.latitude, metadata.longitude
            )
            return self._format_exif_datetime(local_dt)

        utc_dt = datetime.fromtimestamp(metadata.taken_timestamp, tz=timezone.utc)
        return self._format_exif_datetime(utc_dt)

    def _calculate_path_match_score(self, path1: str, path2: str) -> int:
        """Calculate matching suffix component score between two paths (case-insensitive)."""
        def get_components(p_str: str) -> list[str]:
            if p_str.startswith("zip://"):
                parts = p_str.split("::", 1)
                internal = parts[1] if len(parts) > 1 else ""
                p = Path(internal)
            else:
                p = Path(p_str)
            return [part.lower() for part in p.parts if part]

        comp1 = get_components(path1)
        comp2 = get_components(path2)

        score = 0
        for c1, c2 in zip(reversed(comp1), reversed(comp2)):
            if c1 == c2:
                score += 1
            else:
                break
        return score

    def _handle_live_photo(self, media_file: MediaFile, metadata: ParsedMetadata, 
                           target_path: Path, output_dir: Optional[Path], output_mode: str, cancel_event=None, temp_files_to_cleanup=None):
        """
        Checks for and processes the paired video file for Live Photos.
        """
        ext = media_file.extension.lower()
        
        # Only check for live photo videos if the current file is an image format known to have Live Photo equivalents
        image_exts = {".jpg", ".jpeg", ".heic"}
        video_exts = [".mov", ".mp4"]
        
        if ext in image_exts:
            stem = Path(media_file.filename).stem
            video_file = None
            video_source = None
            video_ext_found = None
            
            # 1. Try cross-directory DB query first to find videos spanning multiple ZIPs
            best_candidate = None
            best_score = -1
            for v_ext in video_exts:
                v_name = stem + v_ext
                candidates = self.db.get_all_files_by_exact_name(v_name)
                for cand in candidates:
                    score = self._calculate_path_match_score(media_file.path, cand.path)
                    if score >= 1 and score > best_score:
                        best_score = score
                        best_candidate = cand

            if best_candidate:
                video_file = best_candidate
                v_str_path = self._get_full_path(video_file.path, video_file.filename)
                if v_str_path.startswith("zip://"):
                    if output_mode == 'in-place':
                        logger.warning("Skipping ZIP Live Photo video in In-Place mode")
                    else:
                        jit_vid_path = self._extract_jit(v_str_path, output_dir)
                        if temp_files_to_cleanup is not None:
                            temp_files_to_cleanup.append(jit_vid_path)
                        video_source = jit_vid_path
                else:
                    video_source = Path(v_str_path)
                video_ext_found = video_file.extension
            
            # 2. Fall back to local directory search if not in DB cross-search
            if not video_source:
                for v_ext in video_exts:
                    if media_file.path.startswith("zip://"):
                        # Local directory fallback doesn't make sense for unextracted ZIPs
                        # Cross-directory query should have found it anyway.
                        continue
                    v_source = Path(media_file.path) / (stem + v_ext)
                    if not v_source.exists():
                        v_source = self._find_live_photo_video(Path(media_file.path), stem, v_ext)
                    if v_source and v_source.exists():
                        video_source = v_source
                        video_file = self.db.get_file_by_path_filename(str(v_source.parent), v_source.name)
                        video_ext_found = v_ext
                        break
            
            if video_source and video_source.exists():
                video_filename = video_source.name
                video_target = target_path.with_suffix(video_ext_found)
                video_claimed = False
                
                try:
                    if video_file and video_file.id:
                        video_claimed = self.db.try_mark_processing(video_file.id)
                        if not video_claimed:
                            logger.info(f"Skipping live photo video already claimed: {video_filename}")
                            return None
                            
                    if cancel_event and cancel_event.is_set():
                        raise InterruptedError("Cancelled by user")

                    if output_mode == 'copy' and output_dir:
                        shutil.copy2(video_source, video_target)
                        video_target_path = video_target
                    else:
                        video_target_path = video_source
                        
                    # Write timestamp to the video part as well
                    if metadata.taken_timestamp is not None:
                        tags = {
                            "DateTimeOriginal": self._date_time_original_for_metadata(metadata)
                        }
                        keep_backup = (
                            output_mode == 'in-place' and
                            self.settings.get('in_place_backup_enabled', True)
                        )
                        if not self.engine.write_metadata(str(video_target_path), tags, keep_backup=keep_backup, cancel_event=cancel_event):
                            raise RuntimeError("ExifTool reported failure for paired Live Photo video.")
                        ts = metadata.taken_timestamp
                        os.utime(str(video_target_path), (ts, ts))

                    if video_file and video_file.id:
                        self.db.update_file_status(video_file.id, FileStatus.COMPLETED)
                    
                    return {"status": "completed", "file_id": video_file.id if video_file else None, "size": video_source.stat().st_size}
                    
                except Exception as e:
                    if video_claimed and video_file and video_file.id:
                        self.db.update_file_status(video_file.id, FileStatus.ERROR, str(e))
                    logger.warning(f"Failed to process live photo video {video_filename}: {e}")
                    return {"status": "error", "file_id": video_file.id if video_file else None}
        return None

    def _find_live_photo_video(self, folder: Path, stem: str, video_ext: str) -> Optional[Path]:
        """Find the paired video using case-insensitive extension matching.
        
        Returns the path to the video file if found, or None if not found.
        """
        try:
            for candidate in folder.iterdir():
                if (
                    candidate.is_file() and
                    candidate.stem.lower() == stem.lower() and
                    candidate.suffix.lower() == video_ext
                ):
                    return candidate
        except OSError:
            pass
        return None

    def _get_full_path(self, path: str, filename: str) -> str:
        """Constructs a full path, handling zip:// prefixes safely."""
        if path.startswith("zip://"):
            if path.endswith("::"):
                return f"{path}{filename}"
            else:
                return f"{path}/{filename}"
        else:
            return str(Path(path) / filename)

    def _extract_jit(self, virtual_path: str, output_dir: Path, target_path_override: Optional[Path] = None) -> Path:
        """Extracts a virtual path from a zip to a temporary file, or directly to a target path."""
        parts = virtual_path[6:].split("::")
        zip_path = Path(parts[0])
        internal_path = parts[1]
        
        if target_path_override:
            target_path = target_path_override
            target_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            jit_dir = output_dir / ".tmp_working" / "JIT"
            jit_dir.mkdir(parents=True, exist_ok=True)
            
            target_path = jit_dir / Path(internal_path).name
            unique_id = uuid.uuid4().hex[:8]
            target_path = jit_dir / f"{target_path.stem}_{unique_id}{target_path.suffix}"
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            with zip_ref.open(internal_path) as source, open(target_path, "wb") as target:
                shutil.copyfileobj(source, target)
                
        return target_path
