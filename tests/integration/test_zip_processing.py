import zipfile
import json
import pytest
from pathlib import Path
from core.scanner import FileScanner
from core.state_db import StateDatabase, FileStatus
from tests.conftest import SAMPLE_JPEG_BYTES

def test_zip_scanning_and_jit_staging(temp_dir):
    """
    Verifies that FileScanner can traverse a ZIP archive, identify media files
    and JSON sidecars without full extraction, and stage them as zip:// records in StateDatabase.
    """
    test_zip = temp_dir / "TakeoutArchive.zip"
    
    # Create test ZIP with a media file and matching sidecar
    with zipfile.ZipFile(test_zip, "w") as zf:
        zf.writestr("Takeout/Google Photos/2021/photo.jpg", SAMPLE_JPEG_BYTES)
        sidecar_data = {
            "title": "photo.jpg",
            "photoTakenTime": {"timestamp": "1620043200"}
        }
        zf.writestr("Takeout/Google Photos/2021/photo.jpg.json", json.dumps(sidecar_data))
        
    db = StateDatabase(temp_dir / "zip_test.db")
    config = {
        "supported_image_extensions": [".jpg", ".jpeg", ".png"],
        "supported_video_extensions": [".mp4", ".mov"]
    }
    
    scanner = FileScanner(config, db, temp_dir / "tmp_scanner")
    media_count, json_count = scanner.scan_inputs([test_zip])
    
    assert media_count == 1
    assert json_count == 1
    
    pending = db.get_files_by_status(FileStatus.PENDING)
    assert len(pending) == 1
    assert pending[0].filename == "photo.jpg"
    assert pending[0].path.startswith("zip://")
    
    json_files = db.get_all_json_files()
    assert len(json_files) == 1
    assert json_files[0][0] == "photo.jpg.json"
    assert json_files[0][1].startswith("zip://")
    
    db.close()
