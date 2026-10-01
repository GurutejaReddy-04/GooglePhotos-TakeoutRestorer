import pytest
from core.state_db import StateDatabase, FileStatus, MatchConfidence
from core.matcher import MetadataMatcher
from core.writer import MetadataWriter
from unittest.mock import MagicMock

def test_live_photo_pairing(temp_dir):
    """
    Verifies that a Live Photo video (.mov) sharing base name with an image (.jpg)
    is marked as MATCHED at Tier 5 without requiring an independent JSON sidecar,
    and is skipped from double-counting when processed independently.
    """
    db_path = temp_dir / "live_photo.db"
    db = StateDatabase(db_path)
    
    # Insert image, video, and image's JSON sidecar
    img_id = db.add_media_file(str(temp_dir), "IMG_5500.jpg", ".jpg", 2048)
    mov_id = db.add_media_file(str(temp_dir), "IMG_5500.mov", ".mov", 8192)
    db.add_json_file(str(temp_dir), "IMG_5500.jpg.json", str(temp_dir / "IMG_5500.jpg.json"))
    
    config = {
        "matching": {"levenshtein_threshold": 3, "min_truncation_length": 8},
        "settings": {"gps_enabled": True}
    }
    matcher = MetadataMatcher(db, config)
    matcher.run_matching()
    
    img_rec = db.get_file_by_id(img_id)
    mov_rec = db.get_file_by_id(mov_id)
    
    # Image is matched to JSON
    assert img_rec.status == FileStatus.MATCHED
    assert img_rec.json_path == str(temp_dir / "IMG_5500.jpg.json")
    
    # Video is paired as Live Photo
    assert mov_rec.status == FileStatus.MATCHED
    assert mov_rec.json_path is None
    
    # When writer processes the video record independently, it skips it cleanly
    writer = MetadataWriter(db, None, config)
    result = writer.process_file(mov_rec, temp_dir / "output", "copy")
    assert result["status"] == "skipped"
    assert "Live Photo Video" in result["message"]
    
    db.close()
