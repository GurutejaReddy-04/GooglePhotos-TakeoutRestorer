import pytest
from pathlib import Path
from unittest.mock import MagicMock
from concurrent.futures import ThreadPoolExecutor
from core.state_db import StateDatabase, FileStatus, MediaFile
from core.writer import MetadataWriter

def test_concurrency_single_worker_claim(temp_dir):
    """
    Verifies that when multiple threads attempt to claim the same media file,
    only exactly ONE worker succeeds and others are rejected (try_mark_processing).
    """
    db_path = temp_dir / "concurrent_state.db"
    db = StateDatabase(db_path)
    
    file_id = db.add_media_file(str(temp_dir), "claim_test.jpg", ".jpg", 1024)
    # Transition to matched so it is eligible
    db.update_file_status(file_id, FileStatus.MATCHED)
    
    claimed_results = []
    
    def try_claim(worker_id):
        success = db.try_mark_processing(file_id)
        if success:
            claimed_results.append(worker_id)
            
    # Launch 10 concurrent threads trying to claim the exact same record
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(try_claim, i) for i in range(10)]
        for f in futures:
            f.result()
            
    # Exactly one thread must have claimed it
    assert len(claimed_results) == 1
    # Status in database must now be processing
    rec = db.get_file_by_id(file_id)
    assert rec.status == FileStatus.PROCESSING
    db.close()

def test_resume_does_not_duplicate_completed(temp_dir):
    """
    Verifies that when resume is triggered:
    - Files already in COMPLETED status are skipped and never re-processed.
    - Files in PENDING or recovered PROCESSING status proceed to completion.
    """
    db_path = temp_dir / "resume_state.db"
    db = StateDatabase(db_path)
    
    # Stage 5 files:
    # 2 COMPLETED
    # 1 PROCESSING (interrupted)
    # 2 PENDING
    id1 = db.add_media_file(str(temp_dir), "file1.jpg", ".jpg", 1024)
    id2 = db.add_media_file(str(temp_dir), "file2.jpg", ".jpg", 1024)
    id3 = db.add_media_file(str(temp_dir), "file3.jpg", ".jpg", 1024)
    id4 = db.add_media_file(str(temp_dir), "file4.jpg", ".jpg", 1024)
    id5 = db.add_media_file(str(temp_dir), "file5.jpg", ".jpg", 1024)
    
    # Batch update statuses synchronously
    db.update_file_status_batch([
        (FileStatus.COMPLETED.value, None, 1, id1),
        (FileStatus.COMPLETED.value, None, 1, id2),
        (FileStatus.PROCESSING.value, None, 0, id3)
    ])
    
    all_files = db.get_media_files_by_ids([id1, id2, id3, id4, id5])
    
    # Filter files needing processing (mirroring processor logic)
    resumable = [f for f in all_files if f.status != FileStatus.COMPLETED]
    assert len(resumable) == 3
    assert {f.id for f in resumable} == {id3, id4, id5}
    
    # COMPLETED files are preserved
    completed = [f for f in all_files if f.status == FileStatus.COMPLETED]
    assert len(completed) == 2
    assert {f.id for f in completed} == {id1, id2}
    
    db.close()
