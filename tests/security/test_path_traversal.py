import zipfile
import tarfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.downloader import ExifToolDownloader, SecurityError, compute_file_sha256

def test_zip_slip_rejection(temp_dir):
    """Verifies that zip members attempting path traversal trigger SecurityError."""
    downloader = ExifToolDownloader(tools_dir=str(temp_dir))
    slip_zip = temp_dir / "slip.zip"
    
    with zipfile.ZipFile(slip_zip, "w") as zf:
        zf.writestr("../../escape.exe", b"malicious binary")

    actual_hash = compute_file_sha256(slip_zip)

    with patch.object(downloader, "get_platform_manifest") as mock_manifest:
        mock_manifest.return_value = {
            "archive_sha256": actual_hash,
            "urls": ["https://fake.mirror/slip.zip"],
            "archive_type": "zip",
            "target_executable": "exiftool.exe"
        }
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.headers = {"content-length": str(slip_zip.stat().st_size)}
            mock_resp.read.side_effect = [slip_zip.read_bytes(), b""]
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            with pytest.raises(SecurityError, match="path traversal detected"):
                downloader.download_and_install()

    # Escape file must not exist anywhere outside
    assert not (temp_dir.parent / "escape.exe").exists()

def test_tar_slip_rejection(temp_dir):
    """Verifies that tar members attempting path traversal trigger SecurityError."""
    downloader = ExifToolDownloader(tools_dir=str(temp_dir))
    slip_tar = temp_dir / "slip.tar.gz"

    with tarfile.open(slip_tar, "w:gz") as tf:
        tarinfo = tarfile.TarInfo(name="../escape.pl")
        payload = b"malicious script"
        tarinfo.size = len(payload)
        import io
        tf.addfile(tarinfo, io.BytesIO(payload))

    actual_hash = compute_file_sha256(slip_tar)

    with patch.object(downloader, "get_platform_manifest") as mock_manifest:
        mock_manifest.return_value = {
            "archive_sha256": actual_hash,
            "urls": ["https://fake.mirror/slip.tar.gz"],
            "archive_type": "tar.gz",
            "target_executable": "exiftool"
        }
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.headers = {"content-length": str(slip_tar.stat().st_size)}
            mock_resp.read.side_effect = [slip_tar.read_bytes(), b""]
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            with pytest.raises(SecurityError, match="path traversal detected"):
                downloader.download_and_install()

    assert not (temp_dir.parent / "escape.pl").exists()
