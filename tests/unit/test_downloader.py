import os
import zipfile
import tarfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import io
import urllib.error

from core.downloader import (
    ExifToolDownloader,
    SecurityError,
    EXIFTOOL_MANIFEST,
    compute_file_sha256,
)

def test_manifest_contains_pinned_versions():
    """Ensures verified manifest contains required versions and checksums."""
    assert "13.59" in EXIFTOOL_MANIFEST
    assert "windows" in EXIFTOOL_MANIFEST["13.59"]
    assert "posix" in EXIFTOOL_MANIFEST["13.59"]
    
    # Official POSIX hash check
    posix_hash = EXIFTOOL_MANIFEST["13.59"]["posix"]["archive_sha256"]
    assert posix_hash == "668ea3acececb7235fbd0f4900e72d5f12c9b07e5c778fd36cb1e9b5828fd65a"
    
    # Official Windows hash check
    win_hash = EXIFTOOL_MANIFEST["13.59"]["windows"]["archive_sha256"]
    assert win_hash == "44b512b25af500724ba579d0a53c8fc5851628b692dd5e5d94ae4a15c2cba9ec"
    assert EXIFTOOL_MANIFEST["13.59"]["windows"]["executable_sha256"] == "68c079c32fdae0d6c7130e9a5fb73f8ac9dabdf9ab8da312da4f6c549d6d3385"

def test_unmanifested_version_rejected(temp_dir):
    """Asserts that requesting an unpinned version fails closed."""
    downloader = ExifToolDownloader(tools_dir=str(temp_dir), version="99.99")
    with pytest.raises(SecurityError, match="not in the verified security manifest"):
        downloader.get_platform_manifest()

def test_is_installed_missing(temp_dir):
    """Asserts is_installed returns False when executable does not exist."""
    downloader = ExifToolDownloader(tools_dir=str(temp_dir))
    assert not downloader.is_installed()

def test_is_installed_zero_bytes(temp_dir):
    """Asserts is_installed returns False when executable is a dummy 0-byte file."""
    downloader = ExifToolDownloader(tools_dir=str(temp_dir))
    downloader.exiftool_exe.touch()
    assert not downloader.is_installed()

def test_is_installed_hash_mismatch(temp_dir):
    """Asserts is_installed fails when executable hash does not match pinned hash."""
    downloader = ExifToolDownloader(tools_dir=str(temp_dir))
    downloader.exiftool_exe.write_bytes(b"tampered binary content")
    # Even if executable is present, hash mismatch must fail
    assert not downloader.is_installed()

def test_safe_zip_slip_rejection(temp_dir):
    """Asserts zip archives with path traversal members are rejected."""
    downloader = ExifToolDownloader(tools_dir=str(temp_dir))
    malicious_zip = temp_dir / "slip.zip"
    
    with zipfile.ZipFile(malicious_zip, "w") as zf:
        zf.writestr("../../evil.exe", b"malicious payload")
        
    staging = temp_dir / ".download_staging"
    staging.mkdir(parents=True, exist_ok=True)
    extract_target = staging / "extracted"
    extract_target.mkdir(parents=True, exist_ok=True)
    
    # Mock download to return our zip with matching hash
    actual_hash = compute_file_sha256(malicious_zip)
    
    with patch.object(downloader, "get_platform_manifest") as mock_manifest:
        mock_manifest.return_value = {
            "archive_sha256": actual_hash,
            "urls": ["http://fake.test/slip.zip"],
            "archive_type": "zip",
            "target_executable": "exiftool.exe"
        }
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.headers = {"content-length": str(malicious_zip.stat().st_size)}
            mock_resp.read.side_effect = [malicious_zip.read_bytes(), b""]
            mock_urlopen.return_value.__enter__.return_value = mock_resp
            
            with pytest.raises(SecurityError, match="path traversal detected"):
                downloader.download_and_install()

def test_checksum_mismatch_fails_closed(temp_dir):
    """Asserts that download fails and raises SecurityError when checksum does not match."""
    downloader = ExifToolDownloader(tools_dir=str(temp_dir))
    fake_archive = temp_dir / "fake.zip"
    fake_archive.write_bytes(b"corrupt archive bytes")
    
    with patch.object(downloader, "get_platform_manifest") as mock_manifest:
        mock_manifest.return_value = {
            "archive_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
            "urls": ["http://fake.test/fake.zip"],
            "archive_type": "zip",
            "target_executable": "exiftool.exe"
        }
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.headers = {"content-length": str(fake_archive.stat().st_size)}
            mock_resp.read.side_effect = [fake_archive.read_bytes(), b""]
            mock_urlopen.return_value.__enter__.return_value = mock_resp
            
            with pytest.raises(SecurityError, match="archive checksum mismatch"):
                downloader.download_and_install()
                
    # Staging should be cleaned up
    assert not (temp_dir / ".download_staging").exists()
