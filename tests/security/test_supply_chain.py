import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.downloader import ExifToolDownloader, SecurityError, compute_file_sha256

def test_tampered_payload_aborts_installation(temp_dir):
    """
    Verifies that a tampered download archive fails SHA-256 verification,
    raises SecurityError, and immediately deletes all temporary staging artifacts.
    """
    downloader = ExifToolDownloader(tools_dir=str(temp_dir))
    tampered_archive = temp_dir / "tampered.zip"
    tampered_archive.write_bytes(b"arbitrary untrusted bytes")

    with patch.object(downloader, "get_platform_manifest") as mock_manifest:
        mock_manifest.return_value = {
            "archive_sha256": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            "urls": ["https://fake.mirror/tampered.zip"],
            "archive_type": "zip",
            "target_executable": "exiftool.exe"
        }
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.headers = {"content-length": str(tampered_archive.stat().st_size)}
            mock_resp.read.side_effect = [tampered_archive.read_bytes(), b""]
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            with pytest.raises(SecurityError, match="archive checksum mismatch"):
                downloader.download_and_install()

    # Assert no staging files or fake executables remain
    assert not (temp_dir / ".download_staging").exists()
    assert not downloader.exiftool_exe.exists()

def test_unmanifested_platform_aborts(temp_dir):
    """Verifies that an unknown platform or version fails closed."""
    downloader = ExifToolDownloader(tools_dir=str(temp_dir), version="1.0.0")
    with pytest.raises(SecurityError, match="not in the verified security manifest"):
        downloader.download_and_install()
