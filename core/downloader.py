import sys
import os
import urllib.request
import logging
import zipfile
import tarfile
from pathlib import Path
import shutil
import hashlib
import subprocess
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class SecurityError(ValueError):
    """Raised when cryptographic verification or archive integrity fails."""
    pass

# Manifest of verified installable ExifTool distributions
EXIFTOOL_MANIFEST = {
    "13.59": {
        "windows": {
            "filename": "exiftool-13.59_64.zip",
            "archive_sha256": "44b512b25af500724ba579d0a53c8fc5851628b692dd5e5d94ae4a15c2cba9ec",
            "executable_sha256": "68c079c32fdae0d6c7130e9a5fb73f8ac9dabdf9ab8da312da4f6c549d6d3385",
            "urls": [
                "https://master.dl.sourceforge.net/project/exiftool/exiftool-13.59_64.zip?viasf=1",
                "https://sourceforge.net/projects/exiftool/files/exiftool-13.59_64.zip/download",
                "https://exiftool.org/exiftool-13.59_64.zip",
                "https://exiftool.org/archive/exiftool-13.59_64.zip"
            ],
            "archive_type": "zip",
            "target_executable": "exiftool.exe",
            "intermediate_executable": "exiftool(-k).exe"
        },
        "posix": {
            "filename": "Image-ExifTool-13.59.tar.gz",
            "archive_sha256": "668ea3acececb7235fbd0f4900e72d5f12c9b07e5c778fd36cb1e9b5828fd65a",
            "executable_sha256": None,
            "urls": [
                "https://master.dl.sourceforge.net/project/exiftool/Image-ExifTool-13.59.tar.gz?viasf=1",
                "https://sourceforge.net/projects/exiftool/files/Image-ExifTool-13.59.tar.gz/download",
                "https://exiftool.org/Image-ExifTool-13.59.tar.gz",
                "https://exiftool.org/archive/Image-ExifTool-13.59.tar.gz"
            ],
            "archive_type": "tar.gz",
            "target_executable": "exiftool"
        }
    }
}

DEFAULT_VERSION = "13.59"

def compute_file_sha256(file_path: Path) -> str:
    """Computes the SHA-256 hash of a local file in chunks."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest().lower()

class ExifToolDownloader:
    def __init__(self, tools_dir: str = "tools", version: str = DEFAULT_VERSION):
        self.tools_dir = Path(tools_dir)
        self.version = version
        self.is_windows = os.name == 'nt'
        self.platform_key = "windows" if self.is_windows else "posix"
        self.exiftool_exe = self.tools_dir / ("exiftool.exe" if self.is_windows else "exiftool")

    def get_platform_manifest(self) -> Dict[str, Any]:
        """Retrieves the pinned manifest for the requested version and platform."""
        if self.version not in EXIFTOOL_MANIFEST:
            raise SecurityError(f"Requested ExifTool version '{self.version}' is not in the verified security manifest.")
        platform_info = EXIFTOOL_MANIFEST[self.version].get(self.platform_key)
        if not platform_info:
            raise SecurityError(f"No verified manifest entry for platform '{self.platform_key}' in ExifTool {self.version}.")
        return platform_info

    def is_installed(self) -> bool:
        """
        Comprehensive runtime integrity check:
        1. Executable exists and is non-empty.
        2. Cryptographic SHA-256 matches manifest (if pinned).
        3. Invoking `exiftool -ver` succeeds and reports expected version.
        """
        if not self.exiftool_exe.exists():
            return False

        try:
            # Check non-empty
            if self.exiftool_exe.stat().st_size == 0:
                logger.warning(f"ExifTool binary at {self.exiftool_exe} is 0 bytes.")
                return False

            manifest = self.get_platform_manifest()

            # Verify executable hash if pinned
            expected_exe_hash = manifest.get("executable_sha256")
            if expected_exe_hash:
                actual_exe_hash = compute_file_sha256(self.exiftool_exe)
                if actual_exe_hash != expected_exe_hash.lower():
                    logger.warning(
                        f"Runtime integrity mismatch on {self.exiftool_exe}: "
                        f"expected {expected_exe_hash}, got {actual_exe_hash}."
                    )
                    return False

            # Verify runtime version execution
            proc = subprocess.run(
                [str(self.exiftool_exe), "-ver"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if proc.returncode != 0:
                logger.warning(f"ExifTool execution check failed with return code {proc.returncode}.")
                return False

            reported_version = proc.stdout.strip()
            if reported_version != self.version:
                logger.warning(
                    f"ExifTool version mismatch: expected {self.version}, reported {reported_version}."
                )
                return False

            return True

        except (SecurityError, subprocess.SubprocessError, OSError, ValueError) as e:
            logger.warning(f"Runtime validation check on ExifTool failed: {e}")
            return False

    def ensure_installed(self, progress_callback=None) -> bool:
        """
        Ensures a verified ExifTool binary is installed.
        If missing, corrupted, or version-mismatched, triggers atomic acquisition/repair.
        """
        if self.is_installed():
            logger.info("ExifTool is installed and verified.")
            return True

        logger.info("ExifTool not present or integrity check failed; acquiring verified artifact.")
        try:
            self.download_and_install(progress_callback)
            return self.is_installed()
        except Exception as e:
            logger.error(f"Failed to ensure verified ExifTool installation: {e}")
            return False

    def _purge_existing_tools(self):
        """Cleans up existing ExifTool binaries/directories in tools_dir before reinstall."""
        if not self.tools_dir.exists():
            return
        for item in self.tools_dir.iterdir():
            if item.name == ".gitkeep":
                continue
            try:
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            except Exception as e:
                logger.warning(f"Could not purge {item}: {e}")

    def download_and_install(self, progress_callback=None):
        """
        Downloads, verifies against SHA-256, safely extracts, and atomically installs ExifTool.
        Fails closed on hash mismatch, unverified archive, or path traversal.
        """
        manifest = self.get_platform_manifest()
        expected_archive_hash = manifest["archive_sha256"]
        urls = manifest["urls"]
        archive_type = manifest["archive_type"]

        self.tools_dir.mkdir(parents=True, exist_ok=True)
        staging_dir = self.tools_dir / ".download_staging"
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        staging_dir.mkdir(parents=True, exist_ok=True)

        download_file = staging_dir / f"downloaded_archive.{archive_type}"
        extract_dir = staging_dir / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)

        # 1. Download from verified manifest mirrors
        downloaded = False
        last_error = None

        for url in urls:
            logger.info(f"Attempting ExifTool download from: {url}")
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=30) as response:
                    total_size = int(response.headers.get("content-length", 0))
                    block_size = 1024 * 64
                    current_bytes = 0

                    with open(download_file, "wb") as f:
                        while True:
                            buffer = response.read(block_size)
                            if not buffer:
                                break
                            f.write(buffer)
                            current_bytes += len(buffer)
                            if progress_callback:
                                progress_callback(current_bytes, total_size)

                downloaded = True
                logger.info(f"Download completed successfully from {url}.")
                break
            except Exception as e:
                logger.warning(f"Mirror failed ({url}): {e}")
                last_error = e
                if download_file.exists():
                    download_file.unlink(missing_ok=True)

        if not downloaded:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise ConnectionError(
                f"Failed to download ExifTool from all verified mirrors. Last error: {last_error}"
            )

        try:
            # 2. Strict SHA-256 Checksum Verification
            logger.info("Verifying archive SHA-256 checksum...")
            calculated_hash = compute_file_sha256(download_file)

            if calculated_hash != expected_archive_hash.lower():
                raise SecurityError(
                    f"ExifTool archive checksum mismatch! "
                    f"Expected {expected_archive_hash}, got {calculated_hash}. "
                    f"The archive may be corrupted or tampered with."
                )
            logger.info("Archive checksum successfully verified.")

            # 3. Safe Extraction with Path Traversal Protection
            logger.info("Safely extracting ExifTool archive...")
            if archive_type == "zip":
                with zipfile.ZipFile(download_file, "r") as zip_ref:
                    extract_dir_abs = extract_dir.resolve()
                    for member in zip_ref.namelist():
                        if ".." in member or member.startswith("/") or member.startswith("\\"):
                            raise SecurityError(f"Malicious zip file path traversal detected: {member}")
                        target_path = (extract_dir / member).resolve()
                        if os.path.commonpath([str(extract_dir_abs), str(target_path)]) != str(extract_dir_abs):
                            raise SecurityError(f"Zip slip path traversal detected: {member}")
                    zip_ref.extractall(extract_dir)
            else:
                with tarfile.open(download_file, "r:gz") as tar_ref:
                    extract_dir_abs = extract_dir.resolve()
                    for member in tar_ref.getmembers():
                        if ".." in member.name or member.name.startswith("/") or member.name.startswith("\\"):
                            raise SecurityError(f"Malicious tar file path traversal detected: {member.name}")
                        target_path = (extract_dir / member.name).resolve()
                        if os.path.commonpath([str(extract_dir_abs), str(target_path)]) != str(extract_dir_abs):
                            raise SecurityError(f"Tar slip path traversal detected: {member.name}")
                    tar_ref.extractall(extract_dir)

            # 4. Locate and verify extracted payload
            target_name = manifest["target_executable"]
            intermediate_name = manifest.get("intermediate_executable")

            # Check if extracted inside a subfolder (e.g. Image-ExifTool-13.59/)
            subdirs = [d for d in extract_dir.iterdir() if d.is_dir()]
            search_roots = [extract_dir] + subdirs

            found_exe = None
            for root in search_roots:
                if intermediate_name and (root / intermediate_name).exists():
                    found_exe = root / intermediate_name
                    # Rename intermediate e.g. exiftool(-k).exe -> exiftool.exe
                    final_renamed = root / target_name
                    if final_renamed.exists():
                        final_renamed.unlink()
                    found_exe.rename(final_renamed)
                    found_exe = final_renamed
                    break
                elif (root / target_name).exists():
                    found_exe = root / target_name
                    break

            if not found_exe or not found_exe.exists():
                raise FileNotFoundError(f"Could not locate expected executable '{target_name}' in extracted payload.")

            # Verify executable SHA-256 if pinned
            expected_exe_hash = manifest.get("executable_sha256")
            if expected_exe_hash:
                actual_exe_hash = compute_file_sha256(found_exe)
                if actual_exe_hash != expected_exe_hash.lower():
                    raise SecurityError(
                        f"Extracted executable checksum mismatch! "
                        f"Expected {expected_exe_hash}, got {actual_exe_hash}."
                    )

            # 5. Atomic Promotion into tools_dir
            self._purge_existing_tools()

            # Move contents of the payload directory to tools_dir
            payload_dir = found_exe.parent
            for item in payload_dir.iterdir():
                target_dest = self.tools_dir / item.name
                if target_dest.exists():
                    if target_dest.is_dir():
                        shutil.rmtree(target_dest)
                    else:
                        target_dest.unlink()
                shutil.move(str(item), str(target_dest))

            # On POSIX, ensure permissions
            installed_exe = self.tools_dir / target_name
            if not self.is_windows and installed_exe.exists():
                installed_exe.chmod(0o755)

            logger.info(f"Successfully installed and verified ExifTool at {installed_exe}.")

        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)
