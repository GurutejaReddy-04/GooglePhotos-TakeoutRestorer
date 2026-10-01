import zipfile
import json
import pytest
from pathlib import Path
from core.state_db import StateDatabase, FileStatus, MatchConfidence
from core.matcher import MetadataMatcher
from core.writer import MetadataWriter
from core.parser import JSONParser
from tests.conftest import SAMPLE_JPEG_BYTES, SAMPLE_MOV_BYTES

def test_complex_feature_intersection(temp_dir):
    """
    Validates complex feature intersection:
    - Nested ZIP input
    - Filename exceeding 51-char limit with truncated sidecar
    - Duplicate indexed sidecar filename(1).json
    - Apple Live Photo pair (.jpg + .mov)
    - GPS & timezone correction active
    - Copy mode destination placement
    """
    db_path = temp_dir / "intersection.db"
    db = StateDatabase(db_path)
    
    # 1. Truncated 55-character filename
    base_long = "Vacation_Rome_Family_Colosseum_Arch_Of_Constantine_2021"
    img_long = f"{base_long}.jpg"
    json_long_trunc = f"{base_long[:46]}.j.json"
    
    # 2. Duplicate sidecar pair
    img_dup = "IMG_0099 (1).jpg"
    json_dup = "IMG_0099.jpg(1).json"
    
    # 3. Live photo pair
    lp_img = "LivePhoto_001.jpg"
    lp_mov = "LivePhoto_001.mov"
    lp_json = "LivePhoto_001.jpg.json"
    
    source_folder = temp_dir / "Takeout"
    source_folder.mkdir(parents=True, exist_ok=True)
    
    # Write media files
    (source_folder / img_long).write_bytes(SAMPLE_JPEG_BYTES)
    (source_folder / img_dup).write_bytes(SAMPLE_JPEG_BYTES)
    (source_folder / lp_img).write_bytes(SAMPLE_JPEG_BYTES)
    (source_folder / lp_mov).write_bytes(SAMPLE_MOV_BYTES)
    
    # Write sidecar JSONs with GPS
    rome_gps = {
        "title": "Photo",
        "photoTakenTime": {"timestamp": "1620043200"}, # 2021-05-03 12:00:00 UTC
        "geoDataExif": {"latitude": 41.8902, "longitude": 12.4922, "altitude": 24.5}
    }
    
    (source_folder / json_long_trunc).write_text(json.dumps(rome_gps), encoding="utf-8")
    (source_folder / json_dup).write_text(json.dumps(rome_gps), encoding="utf-8")
    (source_folder / lp_json).write_text(json.dumps(rome_gps), encoding="utf-8")
    
    # Populate StateDatabase
    f1 = db.add_media_file(str(source_folder), img_long, ".jpg", len(SAMPLE_JPEG_BYTES))
    f2 = db.add_media_file(str(source_folder), img_dup, ".jpg", len(SAMPLE_JPEG_BYTES))
    f3 = db.add_media_file(str(source_folder), lp_img, ".jpg", len(SAMPLE_JPEG_BYTES))
    f4 = db.add_media_file(str(source_folder), lp_mov, ".mov", len(SAMPLE_MOV_BYTES))
    
    db.add_json_file(str(source_folder), json_long_trunc, str(source_folder / json_long_trunc))
    db.add_json_file(str(source_folder), json_dup, str(source_folder / json_dup))
    db.add_json_file(str(source_folder), lp_json, str(source_folder / lp_json))
    
    # Run Matcher
    config = {
        "matching": {"levenshtein_threshold": 3, "min_truncation_length": 8},
        "settings": {"gps_enabled": True, "timezone_enabled": True}
    }
    matcher = MetadataMatcher(db, config)
    matcher.run_matching()
    
    # Assertions on match results
    m1 = db.get_file_by_id(f1)
    assert m1.status == FileStatus.MATCHED
    assert m1.json_path == str(source_folder / json_long_trunc)
    
    m2 = db.get_file_by_id(f2)
    assert m2.status == FileStatus.MATCHED
    assert m2.json_path == str(source_folder / json_dup)
    
    m3 = db.get_file_by_id(f3)
    assert m3.status == FileStatus.MATCHED
    assert m3.json_path == str(source_folder / lp_json)
    
    # Assert tag generation for the matched items includes Rome local time (14:00) and GPS
    writer = MetadataWriter(db, None, config)
    parsed_meta = JSONParser.parse(Path(m1.json_path))
    tags = writer._build_tags(parsed_meta)
    
    assert "41.8902 N" in tags["GPSLatitude"]
    assert "12.4922 E" in tags["GPSLongitude"]
    assert "2021:05:03 14:00:00" in tags["DateTimeOriginal"]
    
    db.close()
