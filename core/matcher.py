"""
Metadata Matcher: Maps JSON sidecars to media files using a tiered confidence algorithm.
"""

import re
from pathlib import Path
from typing import Dict
import logging
import time
from .state_db import StateDatabase, FileStatus, MatchConfidence

logger = logging.getLogger(__name__)

def levenshtein_distance(s1: str, s2: str, threshold: int) -> int:
    """Pure Python Levenshtein distance calculation with early exit."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1, threshold)
    if len(s2) == 0:
        return len(s1)
    if abs(len(s1) - len(s2)) > threshold:
        return threshold + 1
        
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        min_in_row = i + 1
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            val = min(insertions, deletions, substitutions)
            current_row.append(val)
            if val < min_in_row:
                min_in_row = val
        previous_row = current_row
        
        # Early exit if the minimum possible distance in this row already exceeds threshold
        if min_in_row > threshold:
            return threshold + 1
            
    return previous_row[-1]

class MetadataMatcher:
    def __init__(self, db: StateDatabase, config: dict):
        self.db = db
        self.fuzzy_threshold = config.get('matching', {}).get('levenshtein_threshold', 3)
        # FIX P2-2: Add minimum length floor for truncation matching
        self.min_truncation_length = config.get('matching', {}).get('min_truncation_length', 8)

    def run_matching(self):
        """Executes the tiered matching algorithm."""
        logger.info("Starting metadata matching process...")
        
        json_file_list = self.db.get_all_json_files()  # List[(filename, full_path)]
        pending_files = self.db.get_files_by_status(FileStatus.PENDING)
        
        # Group JSONs by folder for same-folder optimization.
        json_by_folder: Dict[str, Dict[str, str]] = {}
        # List of all paths for a given JSON filename to handle cross-folder duplicates safely
        json_files_all: Dict[str, list[str]] = {}
        for fname, fpath in json_file_list:
            try:
                # Use absolute() instead of resolve() to avoid blocking disk I/O on thousands of files
                folder = str(Path(fpath).parent.absolute())
            except Exception:
                folder = str(Path(fpath).parent)
                
            if folder not in json_by_folder:
                json_by_folder[folder] = {}
            json_by_folder[folder][fname] = fpath
            
            if fname not in json_files_all:
                json_files_all[fname] = []
            json_files_all[fname].append(fpath)

        # Accumulate matches for batch update
        match_updates = []
        status_updates = []
        
        def find_json_path(j_name: str, folder_j: dict, all_j: dict) -> str:
            # 1. Prefer same folder
            if j_name in folder_j:
                return folder_j[j_name]
            # 2. Fallback to any folder if unique, or pick the first if duplicated
            if j_name in all_j and all_j[j_name]:
                return all_j[j_name][0]
            return None

        def generate_candidates(base: str, ext: str, suffix: str = "") -> list[str]:
            """Generate all possible JSON filenames Google Takeout might use."""
            s = f"({suffix})" if suffix else ""
            cands = []
            
            # Google Takeout enforces a strict 51-character limit on filenames in some ZIPs.
            # It will chop ".supplemental-metadata", or even the file extension itself!
            
            # 1. Truncate extension (e.g. .jpg -> .jp, .j, "")
            for i in range(len(ext), -1, -1):
                trunc_ext = ext[:i]
                e = f".{trunc_ext}" if trunc_ext else ""
                cands.append(f"{base}{e}{s}.json")
                
            # 2. Truncate supplemental-metadata (e.g. .supplemental-me, .suppl, .s)
            supp = ".supplemental-metadata"
            for i in range(len(supp), 0, -1):
                trunc_supp = supp[:i]
                cands.append(f"{base}.{ext}{trunc_supp}{s}.json")
                cands.append(f"{base}{trunc_supp}{s}.json")
                
            return cands

        # Pre-compute set of image base names for fast Live Photo video pairing
        image_bases = set()
        for f in pending_files:
            if '.' in f.filename:
                base, ext = f.filename.rsplit('.', 1)
                if ext.lower() in {'jpg', 'jpeg', 'heic', 'png'}:
                    image_bases.add(base)

        for idx, media_file in enumerate(pending_files):
            # Yield the GIL periodically so Tkinter mainloop can update the UI timer
            if idx % 100 == 0:
                time.sleep(0.001)
                
            try:
                media_folder = str(Path(media_file.path).absolute())
            except Exception:
                media_folder = media_file.path
                
            media_name = media_file.filename
            if '.' not in media_name:
                continue
            media_base, media_ext = media_name.rsplit('.', 1)
            
            # Helper to try a list of candidates
            def try_candidates(candidates: list[str], tier: int) -> bool:
                for cand in candidates:
                    j_path = find_json_path(cand, folder_jsons, json_files_all)
                    if j_path:
                        match_updates.append((j_path, MatchConfidence.CERTAIN.value, tier, FileStatus.MATCHED.value, media_file.id))
                        return True
                return False

            matched = False
            folder_jsons = json_by_folder.get(media_folder, {})
            
            # Tier 1: Exact matches and basic supplemental metadata
            if try_candidates(generate_candidates(media_base, media_ext), 1):
                continue
                
            # Tier 2: Strip '-edited'
            if media_base.endswith('-edited'):
                clean_base = media_base[:-7]
                if try_candidates(generate_candidates(clean_base, media_ext), 2):
                    continue
                    
            # Tier 3: Move (N) from base name to after extension
            match_n = re.match(r'^(.+?)\s*\((\d+)\)$', media_base)
            if match_n:
                clean_base = match_n.group(1)
                suffix_n = match_n.group(2)
                # Try with suffix moved to end
                if try_candidates(generate_candidates(clean_base, media_ext, suffix_n), 3):
                    continue
                # Also try the original name as base in case suffix wasn't moved in JSON
                if try_candidates(generate_candidates(media_base, media_ext), 3):
                    continue
                    
            # Tier 4: Progressive truncation match
            for i in range(1, len(media_base) - self.min_truncation_length + 1):
                truncated = media_base[:-i]
                if len(truncated) < self.min_truncation_length:
                    break
                if try_candidates(generate_candidates(truncated, media_ext), 4):
                    matched = True
                    break
                    
            if matched:
                continue
                
            # Tier 4.5: Live Photo Video Match
            # If it's a video and shares a base name with an image, it's a Live Photo.
            if media_ext.lower() in {'mp4', 'mov'} and media_base in image_bases:
                # Mark as MATCHED without a JSON file, so it doesn't show up as unmatched.
                # writer.py handles the actual processing of Live Photos.
                match_updates.append((None, MatchConfidence.CERTAIN.value, 5, FileStatus.MATCHED.value, media_file.id))
                matched = True
                continue
                
            # Tier 5: Levenshtein fuzzy match
            best_match = None
            best_dist = self.fuzzy_threshold + 1
            
            # Only do fuzzy match within same folder to avoid O(n*m) across entire library.
            # Also limit to folders with <= 1000 JSONs to prevent exponential CPU hangs.
            if folder_jsons and len(folder_jsons) <= 1000:
                media_base_lower = media_base.lower()
                media_base_len = len(media_base_lower)
                for j_name, j_path in folder_jsons.items():
                    # Compare base names without extensions
                    j_base = j_name.replace('.json', '').replace('.supplemental-metadata', '')
                    j_base_lower = j_base.lower()
                    
                    # Dynamic threshold: allow 1 error per 10 characters, minimum 1
                    dynamic_threshold = min(self.fuzzy_threshold, max(1, media_base_len // 10))
                    
                    # Short-circuit: if length difference is greater than threshold, distance MUST be greater
                    if abs(media_base_len - len(j_base_lower)) > dynamic_threshold:
                        continue
                        
                    dist = levenshtein_distance(media_base_lower, j_base_lower, dynamic_threshold)
                    if dist <= dynamic_threshold and dist < best_dist:
                        best_dist = dist
                        best_match = j_path
            elif folder_jsons and len(folder_jsons) > 1000:
                logger.debug(
                    "Fuzzy matching skipped for '%s' because folder '%s' has too many JSONs (%d), "
                    "preventing O(N^2) CPU hang.",
                    media_name, media_folder, len(folder_jsons)
                )
            else:
                logger.debug(
                    "No JSON files in folder '%s' for '%s'; fuzzy matching skipped "
                    "because it is folder-scoped for performance.",
                    media_folder,
                    media_name
                )
                    
            if best_match:
                match_updates.append((best_match, MatchConfidence.LOW.value, 5, FileStatus.MATCHED_LOW_CONFIDENCE.value, media_file.id))
            else:
                # Tier 6: No match
                status_updates.append((FileStatus.UNMATCHED.value, None, 0, media_file.id))
                
        # Perform batch updates
        if match_updates:
            self.db.update_match_info_batch(match_updates)
        if status_updates:
            self.db.update_file_status_batch(status_updates)
            
        logger.info("Matching process complete.")

    def _apply_match(self, file_id: int, json_path: str, confidence: MatchConfidence, tier: int):
        """Legacy helper. Do not use for loops."""
        self.db.update_match_info(file_id, json_path, confidence, tier)
