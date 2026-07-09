import sys
import os
import urllib.request
import logging
import zipfile
import tarfile
from pathlib import Path
import shutil
import hashlib

logger = logging.getLogger(__name__)

def get_latest_exiftool_info() -> dict:
    """
    Attempts to retrieve the specific 13.59 version first.
    Falls back to the latest ExifTool version using the GitHub releases API.
    Returns a dict with 'url', 'version', and 'expected_hash' (if available).
    """
    is_windows = os.name == 'nt'
    specific_version = '13.59'
    
    # Check specific version via HEAD request
    if is_windows:
        asset_name = f'exiftool-{specific_version}_64.zip'
        sf_link = f"https://master.dl.sourceforge.net/project/exiftool/{asset_name}?viasf=1"
        expected_hash = "44b512b25af500724ba579d0a53c8fc5851628b692dd5e5d94ae4a15c2cba9ec"
    else:
        asset_name = f'Image-ExifTool-{specific_version}.tar.gz'
        sf_link = f"https://master.dl.sourceforge.net/project/exiftool/{asset_name}?viasf=1"
        expected_hash = "4d05a0f95d7156eeda51124801cb26daf01a6e31b335f79cbef15f4f26e7f9bd"

    try:
        req = urllib.request.Request(sf_link, method='HEAD', headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                logger.info(f"Specific version {specific_version} is available.")
                return {'url': sf_link, 'version': specific_version, 'expected_hash': expected_hash}
    except Exception as e:
        logger.warning(f"Specific version {specific_version} not found on SourceForge: {e}. Falling back to latest GitHub release.")

    # Fallback to latest GitHub release
    github_api = 'https://api.github.com/repos/exiftool/exiftool/releases/latest'
    try:
        req = urllib.request.Request(github_api, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/vnd.github.v3+json'})
        with urllib.request.urlopen(req, timeout=10) as response:
            import json as _json
            data = _json.load(response)
            latest_version = data.get('tag_name', '').lstrip('v')
            
            for asset in data.get('assets', []):
                name = asset.get('name', '')
                if is_windows and name.startswith('exiftool-') and name.endswith('_64.zip'):
                    return {'url': asset.get('browser_download_url'), 'version': latest_version, 'expected_hash': None}
                elif not is_windows and name.startswith('Image-ExifTool-') and name.endswith('.tar.gz'):
                    return {'url': asset.get('browser_download_url'), 'version': latest_version, 'expected_hash': None}
    except Exception as e:
        logger.error(f"GitHub release lookup failed: {e}")
        
    # Absolute last resort
    return {'url': sf_link, 'version': specific_version, 'expected_hash': expected_hash}

from core.utils import get_app_base_path

class ExifToolDownloader:
    def __init__(self, tools_dir: str = "tools"):
        self.tools_dir = Path(tools_dir)
        self.exiftool_exe = self.tools_dir / "exiftool.exe"
        self.exiftool_script = self.tools_dir / "exiftool"

    def is_installed(self) -> bool:
        """Check if ExifTool is present. On Windows only the exe is required."""
        if os.name == 'nt':
            return self.exiftool_exe.exists()
        else:
            return self.exiftool_script.exists()

    def ensure_installed(self, progress_callback=None) -> bool:
        """Public helper that ensures ExifTool is installed, invoking download if needed.
        Returns True if ExifTool is present after the call, False otherwise.
        """
        if self.is_installed():
            logger.info("ExifTool is already installed.")
            return True
        try:
            self.download_and_install(progress_callback)
            return self.is_installed()
        except Exception as e:
            logger.error(f"Failed to ensure ExifTool installation: {e}")
            return False

    def download_and_install(self, progress_callback=None):
        """
        Downloads and installs ExifTool if it's not present.
        """
        if self.is_installed():
            logger.info("ExifTool is already installed.")
            return

        self.tools_dir.mkdir(parents=True, exist_ok=True)

        # Clean up existing corrupted tools (skip .gitkeep and any user-added files)
        for item in self.tools_dir.iterdir():
            if item.name == ".gitkeep":
                continue
            # Only remove known ExifTool related files/directories
            if item.is_file() and not item.name.lower().endswith('.exe'):
                continue
            try:
                if item.is_file():
                    item.unlink()
                else:
                    shutil.rmtree(item)
            except Exception:
                pass

        is_windows = os.name == 'nt'
        ext = ".zip" if is_windows else ".tar.gz"
        temp_file_path = self.tools_dir / f"exiftool_download_temp{ext}"

        try:
            info = get_latest_exiftool_info()
            url = info['url']
            expected = info['expected_hash']
            logger.info(f"Downloading ExifTool from: {url}")

            # 1. Download
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                total_size = int(response.headers.get('content-length', 0))
                block_size = 1024 * 8
                downloaded = 0
                with open(temp_file_path, 'wb') as f:
                    while True:
                        buffer = response.read(block_size)
                        if not buffer:
                            break
                        f.write(buffer)
                        downloaded += len(buffer)
                        if progress_callback:
                            progress_callback(downloaded, total_size)

            # 1.5 Verify Checksum (if available)
            if expected:
                logger.info("Verifying checksum...")
                sha256_hash = hashlib.sha256()
                with open(temp_file_path, 'rb') as f:
                    for byte_block in iter(lambda: f.read(4096), b""):
                        sha256_hash.update(byte_block)
                calculated_hash = sha256_hash.hexdigest()
                
                if calculated_hash != expected:
                    raise ValueError(f"Checksum mismatch! Expected {expected}, got {calculated_hash}. The download may be corrupted or compromised.")
            else:
                logger.info("Skipping checksum verification for dynamically fetched version.")

            # 2. Extract
            logger.info("Extracting ExifTool...")
            if is_windows:
                with zipfile.ZipFile(temp_file_path, 'r') as zip_ref:
                    for member in zip_ref.namelist():
                        if '..' in member or member.startswith('/') or member.startswith('\\'):
                            raise ValueError(f"Malicious zip file path traversal detected: {member}")
                    zip_ref.extractall(self.tools_dir)
            else:
                with tarfile.open(temp_file_path, 'r:gz') as tar_ref:
                    tools_dir_abs = self.tools_dir.resolve()
                    for member in tar_ref.getmembers():
                        target_path = (self.tools_dir / member.name).resolve()
                        if os.path.commonpath([str(tools_dir_abs), str(target_path)]) != str(tools_dir_abs):
                            raise ValueError(f"Malicious tar file path traversal detected: {member.name}")
                    tar_ref.extractall(self.tools_dir)

            # 3. Cleanup and Rename
            extracted_dirs = [d for d in self.tools_dir.iterdir() if d.is_dir() and d.name.lower().startswith(("exiftool", "image-exiftool"))]
            if extracted_dirs:
                source_dir = extracted_dirs[0]
                for item in source_dir.iterdir():
                    target = self.tools_dir / item.name
                    if target.exists():
                        if target.is_dir():
                            shutil.rmtree(target)
                        else:
                            target.unlink()
                    shutil.move(str(item), str(target))
                shutil.rmtree(source_dir, ignore_errors=True)
                if is_windows:
                    k_exe = self.tools_dir / "exiftool(-k).exe"
                    if k_exe.exists():
                        k_exe.rename(self.exiftool_exe)
                    logger.info(f"Successfully installed ExifTool to {self.exiftool_exe}")
                else:
                    self.exiftool_script.chmod(0o755)
                    logger.info(f"Successfully installed ExifTool to {self.exiftool_script}")
            else:
                logger.error("Could not find extracted exiftool directory")

        except Exception as e:
            logger.error(f"Failed to extract ExifTool: {e}")
            raise
        finally:
            if temp_file_path.exists():
                try:
                    temp_file_path.unlink()
                except Exception:
                    pass
