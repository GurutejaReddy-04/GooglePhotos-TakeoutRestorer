import pytest
from core.writer import MetadataWriter
from core.parser import ParsedMetadata
from core.state_db import StateDatabase

def test_build_tags_with_gps_enabled(temp_dir):
    """Verifies that GPS tags are included when gps_enabled is True."""
    db = StateDatabase(temp_dir / "test.db")
    config = {"settings": {"gps_enabled": True, "timezone_enabled": False}}
    writer = MetadataWriter(db, None, config)
    
    meta = ParsedMetadata(
        title="Photo.jpg",
        description="A beautiful day",
        taken_timestamp=1620043200.0,
        latitude=41.8902,
        longitude=12.4922,
        altitude=24.5
    )
    
    tags = writer._build_tags(meta)
    assert "GPSLatitude" in tags
    assert "41.8902 N" in tags["GPSLatitude"]
    assert "GPSLongitude" in tags
    assert "12.4922 E" in tags["GPSLongitude"]
    assert "GPSAltitude" in tags
    assert "DateTimeOriginal" in tags
    assert tags["ImageDescription"] == "A beautiful day"
    assert tags["Title"] == "Photo.jpg"
    db.close()

def test_build_tags_with_gps_disabled(temp_dir):
    """Verifies that GPS tags are excluded when gps_enabled is False."""
    db = StateDatabase(temp_dir / "test.db")
    config = {"settings": {"gps_enabled": False, "timezone_enabled": False}}
    writer = MetadataWriter(db, None, config)
    
    meta = ParsedMetadata(
        title="Photo.jpg",
        description=None,
        taken_timestamp=1620043200.0,
        latitude=41.8902,
        longitude=12.4922,
        altitude=24.5
    )
    
    tags = writer._build_tags(meta)
    assert "GPSLatitude" not in tags
    assert "GPSLongitude" not in tags
    assert "GPSAltitude" not in tags
    assert "DateTimeOriginal" in tags
    db.close()

def test_build_tags_null_island_skipped(temp_dir):
    """Verifies that 0.0, 0.0 (Null Island) coordinates are not injected as valid GPS."""
    db = StateDatabase(temp_dir / "test.db")
    config = {"settings": {"gps_enabled": True, "timezone_enabled": False}}
    writer = MetadataWriter(db, None, config)
    
    meta = ParsedMetadata(
        title="Photo.jpg",
        description=None,
        taken_timestamp=1620043200.0,
        latitude=0.0,
        longitude=0.0,
        altitude=0.0
    )
    
    tags = writer._build_tags(meta)
    assert "GPSLatitude" not in tags
    assert "GPSLongitude" not in tags
    db.close()

def test_build_tags_timezone_conversion(temp_dir):
    """Verifies that DateTimeOriginal is adjusted to local time when timezone_enabled is True."""
    db = StateDatabase(temp_dir / "test.db")
    config = {"settings": {"gps_enabled": True, "timezone_enabled": True}}
    writer = MetadataWriter(db, None, config)
    
    # 2021-05-03 12:00:00 UTC in Rome (UTC+2) -> 14:00:00
    meta = ParsedMetadata(
        title="Photo.jpg",
        description=None,
        taken_timestamp=1620043200.0,
        latitude=41.8902,
        longitude=12.4922,
        altitude=24.5
    )
    
    tags = writer._build_tags(meta)
    assert "DateTimeOriginal" in tags
    assert "2021:05:03 14:00:00" in tags["DateTimeOriginal"]
    db.close()
