import pytest
from pathlib import Path
from core.matcher import levenshtein_distance, MetadataMatcher
from core.state_db import StateDatabase, FileStatus, MatchConfidence

def test_levenshtein_distance_exact_and_threshold():
    """Verifies Levenshtein distance calculation with threshold early exit."""
    assert levenshtein_distance("photo", "photo", 3) == 0
    assert levenshtein_distance("photo", "photo1", 3) == 1
    assert levenshtein_distance("photo", "ph1to2", 3) == 2
    # Beyond threshold 1: returns threshold + 1
    assert levenshtein_distance("photo", "completely_different", 2) == 3

def test_matcher_exact_matching(temp_dir):
    """Verifies exact sidecar pairing into state database."""
    db_path = temp_dir / "test_state.db"
    db = StateDatabase(db_path)
    
    # Insert media and json files
    db.add_media_file(str(temp_dir), "IMG_1234.jpg", ".jpg", 1024)
    db.add_json_file(str(temp_dir), "IMG_1234.jpg.json", str(temp_dir / "IMG_1234.jpg.json"))
    
    config = {"matching": {"levenshtein_threshold": 3, "min_truncation_length": 8}}
    matcher = MetadataMatcher(db, config)
    matcher.run_matching()
    
    files = db.get_files_by_status(FileStatus.MATCHED)
    assert len(files) == 1
    assert files[0].filename == "IMG_1234.jpg"
    assert files[0].json_path == str(temp_dir / "IMG_1234.jpg.json")
    db.close()

def test_matcher_truncation_51_chars(temp_dir):
    """Verifies Google Takeout 51-char limit truncation matching."""
    db_path = temp_dir / "test_state_trunc.db"
    db = StateDatabase(db_path)
    
    # 55-char media filename
    long_name = "A" * 50 + ".jpg"
    # Google Takeout truncates to e.g. 51 chars
    truncated_json = "A" * 46 + ".j.json"
    
    db.add_media_file(str(temp_dir), long_name, ".jpg", 2048)
    db.add_json_file(str(temp_dir), truncated_json, str(temp_dir / truncated_json))
    
    config = {"matching": {"levenshtein_threshold": 3, "min_truncation_length": 8}}
    matcher = MetadataMatcher(db, config)
    matcher.run_matching()
    
    files = db.get_files_by_status(FileStatus.MATCHED)
    assert len(files) == 1
    assert files[0].filename == long_name
    db.close()

def test_matcher_duplicate_suffix(temp_dir):
    """Verifies (1) duplicate sidecar suffix resolution."""
    db_path = temp_dir / "test_state_dup.db"
    db = StateDatabase(db_path)
    
    # Media has (1) in base name, e.g. IMG_100 (1).jpg
    media_name = "IMG_100 (1).jpg"
    # Google Takeout often creates IMG_100.jpg(1).json
    json_name = "IMG_100.jpg(1).json"
    
    db.add_media_file(str(temp_dir), media_name, ".jpg", 2048)
    db.add_json_file(str(temp_dir), json_name, str(temp_dir / json_name))
    
    config = {"matching": {"levenshtein_threshold": 3, "min_truncation_length": 8}}
    matcher = MetadataMatcher(db, config)
    matcher.run_matching()
    
    files = db.get_files_by_status(FileStatus.MATCHED)
    assert len(files) == 1
    assert files[0].filename == media_name
    db.close()
