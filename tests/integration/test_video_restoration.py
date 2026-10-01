import pytest
from pathlib import Path
from unittest.mock import MagicMock
from core.state_db import StateDatabase, FileStatus, MatchConfidence
from core.writer import MetadataWriter
from tests.conftest import SAMPLE_MOV_BYTES

def test_video_restoration_pipeline_copy_mode(temp_dir, sample_mov_path, sample_sidecar_json):
    """
    Verifies that MetadataWriter parses JSON sidecar, builds video tags (QuickTime/Keys),
    invokes ExifToolEngine, moves video to Completed/ in copy mode, and updates DB status.
    """
    db = StateDatabase(temp_dir / "video_test.db")
    file_id = db.add_media_file(str(temp_dir), sample_mov_path.name, ".mov", len(SAMPLE_MOV_BYTES))
    db.add_json_file(str(temp_dir), sample_sidecar_json.name, str(sample_sidecar_json))
    
    # Set matched status with json_path
    db.update_match_info(file_id, str(sample_sidecar_json), MatchConfidence.CERTAIN, 1)
    
    media_file = db.get_file_by_id(file_id)
    
    mock_engine = MagicMock()
    mock_engine.write_metadata.return_value = True
    
    output_dir = temp_dir / "output"
    config = {
        "settings": {"gps_enabled": True, "timezone_enabled": True}
    }
    
    writer = MetadataWriter(db, mock_engine, config)
    result = writer.process_file(media_file, output_dir, "copy")
    
    assert result["status"] == "completed"
    assert (output_dir / "Completed" / sample_mov_path.name).exists()
    assert mock_engine.write_metadata.called
    
    # Flush async database writes
    db._write_queue.join()
    
    updated_rec = db.get_file_by_id(file_id)
    assert updated_rec.status == FileStatus.COMPLETED
    assert updated_rec.metadata_written is True
    
    db.close()
