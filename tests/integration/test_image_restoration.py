import pytest
from pathlib import Path
from unittest.mock import MagicMock
from core.state_db import StateDatabase, FileStatus, MatchConfidence
from core.writer import MetadataWriter
from core.parser import ParsedMetadata
from tests.conftest import SAMPLE_JPEG_BYTES

def test_image_restoration_pipeline_copy_mode(temp_dir, sample_jpeg_path, sample_sidecar_json):
    """
    Verifies that MetadataWriter parses JSON sidecar, builds appropriate EXIF tags,
    invokes ExifToolEngine, moves media to Completed/ in copy mode, and updates DB status.
    """
    db = StateDatabase(temp_dir / "image_test.db")
    file_id = db.add_media_file(str(temp_dir), sample_jpeg_path.name, ".jpg", len(SAMPLE_JPEG_BYTES))
    db.add_json_file(str(temp_dir), sample_sidecar_json.name, str(sample_sidecar_json))
    
    # Set matched status with json_path
    db.update_match_info(file_id, str(sample_sidecar_json), MatchConfidence.CERTAIN, 1)
    
    media_file = db.get_file_by_id(file_id)
    
    # Mock ExifToolEngine to simulate successful execution
    mock_engine = MagicMock()
    mock_engine.write_metadata.return_value = True
    
    output_dir = temp_dir / "output"
    config = {
        "settings": {"gps_enabled": True, "timezone_enabled": True}
    }
    
    writer = MetadataWriter(db, mock_engine, config)
    result = writer.process_file(media_file, output_dir, "copy")
    
    assert result["status"] == "completed"
    assert (output_dir / "Completed" / sample_jpeg_path.name).exists()
    
    # Verify mock_engine was called with GPS and DateTimeOriginal
    assert mock_engine.write_metadata.called
    call_args = mock_engine.write_metadata.call_args[0]
    tags = call_args[1]
    assert "DateTimeOriginal" in tags
    assert "GPSLatitude" in tags
    
    # Flush async database writes
    db._write_queue.join()
    
    # Verify state database status is COMPLETED
    updated_rec = db.get_file_by_id(file_id)
    assert updated_rec.status == FileStatus.COMPLETED
    assert updated_rec.metadata_written is True
    
    db.close()
