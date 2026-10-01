import sys
import os
import json
import pytest
from pathlib import Path
import tempfile
import shutil

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Minimal valid JPEG binary: SOI, APP0 (JFIF), DQT, SOF0, DHT, SOS, EOI
SAMPLE_JPEG_BYTES = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
    b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
    b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342"
    b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
    b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
    b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
)

# Minimal MP4/MOV header bytes (ftyp atom)
SAMPLE_MP4_BYTES = b"\x00\x00\x00\x20ftypmp42\x00\x00\x00\x00isommp42\x00\x00\x00\x08free\x00\x00\x00\x08mdat"
SAMPLE_MOV_BYTES = b"\x00\x00\x00\x14ftypqt  \x20\x05\x03\x00qt  \x00\x00\x00\x08mdat"
SAMPLE_PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"

@pytest.fixture
def temp_dir():
    """Provides an isolated temporary directory cleaned up after test."""
    temp_path = Path(tempfile.mkdtemp(prefix="takeout_test_"))
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)

@pytest.fixture
def sample_jpeg_path(temp_dir):
    """Creates a minimal valid JPEG image."""
    img_path = temp_dir / "IMG_20210503_120000.jpg"
    img_path.write_bytes(SAMPLE_JPEG_BYTES)
    return img_path

@pytest.fixture
def sample_mov_path(temp_dir):
    """Creates a minimal valid MOV video."""
    mov_path = temp_dir / "IMG_20210503_120000.mov"
    mov_path.write_bytes(SAMPLE_MOV_BYTES)
    return mov_path

@pytest.fixture
def sample_sidecar_json(temp_dir):
    """Creates a standard Google Takeout JSON sidecar."""
    json_path = temp_dir / "IMG_20210503_120000.jpg.json"
    data = {
        "title": "IMG_20210503_120000.jpg",
        "description": "Family vacation in Rome",
        "imageViews": "0",
        "creationTime": {
            "timestamp": "1620043200",
            "formatted": "May 3, 2021, 12:00:00 PM UTC"
        },
        "modificationTime": {
            "timestamp": "1620043200",
            "formatted": "May 3, 2021, 12:00:00 PM UTC"
        },
        "photoTakenTime": {
            "timestamp": "1620043200",
            "formatted": "May 3, 2021, 12:00:00 PM UTC"
        },
        "geoData": {
            "latitude": 41.8902,
            "longitude": 12.4922,
            "altitude": 24.5,
            "latitudeSpan": 0.0,
            "longitudeSpan": 0.0
        },
        "geoDataExif": {
            "latitude": 41.8902,
            "longitude": 12.4922,
            "altitude": 24.5,
            "latitudeSpan": 0.0,
            "longitudeSpan": 0.0
        }
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return json_path
