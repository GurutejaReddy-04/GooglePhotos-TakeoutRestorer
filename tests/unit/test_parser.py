import json
import pytest
from pathlib import Path
from core.parser import JSONParser, ParsedMetadata

def test_parse_valid_sidecar(sample_sidecar_json):
    """Verifies that a valid Google Takeout sidecar extracts all metadata fields."""
    parsed = JSONParser.parse(sample_sidecar_json)
    assert parsed is not None
    assert parsed.title == "IMG_20210503_120000.jpg"
    assert parsed.description == "Family vacation in Rome"
    assert parsed.taken_timestamp == 1620043200.0
    assert parsed.latitude == 41.8902
    assert parsed.longitude == 12.4922
    assert parsed.altitude == 24.5

def test_parse_missing_file(temp_dir):
    """Verifies parser handles nonexistent file cleanly."""
    nonexistent = temp_dir / "does_not_exist.json"
    parsed = JSONParser.parse(nonexistent)
    assert parsed is None

def test_parse_corrupt_json(temp_dir):
    """Verifies parser handles invalid JSON syntax without unhandled crash."""
    corrupt = temp_dir / "corrupt.json"
    corrupt.write_text("{ this is not valid json : [", encoding="utf-8")
    parsed = JSONParser.parse(corrupt)
    assert parsed is None

def test_parse_empty_file(temp_dir):
    """Verifies parser handles empty 0-byte file cleanly."""
    empty = temp_dir / "empty.json"
    empty.touch()
    parsed = JSONParser.parse(empty)
    assert parsed is None

def test_parse_missing_gps(temp_dir):
    """Verifies parser succeeds when geoData is omitted."""
    no_gps = temp_dir / "no_gps.json"
    data = {
        "title": "photo.jpg",
        "photoTakenTime": {"timestamp": "1600000000"}
    }
    no_gps.write_text(json.dumps(data), encoding="utf-8")
    parsed = JSONParser.parse(no_gps)
    assert parsed is not None
    assert parsed.taken_timestamp == 1600000000.0
    assert parsed.latitude is None
    assert parsed.longitude is None
    assert parsed.altitude is None

def test_parse_fallback_geodata(temp_dir):
    """Verifies fallback to geoData when geoDataExif is missing."""
    fallback_gps = temp_dir / "fallback_gps.json"
    data = {
        "title": "photo.jpg",
        "photoTakenTime": {"timestamp": "1600000000"},
        "geoData": {
            "latitude": 37.7749,
            "longitude": -122.4194,
            "altitude": 10.0
        }
    }
    fallback_gps.write_text(json.dumps(data), encoding="utf-8")
    parsed = JSONParser.parse(fallback_gps)
    assert parsed is not None
    assert parsed.latitude == 37.7749
    assert parsed.longitude == -122.4194
