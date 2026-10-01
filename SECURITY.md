# Security Policy

## Overview
Google Photos Takeout Restorer is designed with strict data privacy and supply-chain integrity controls to safely handle personal photo archives.

## Privacy & Local Processing Guarantee
- **Local Execution:** Media processing is performed strictly on your local device.
- **Network Boundaries:** The current implementation contains no code that transmits photo data, metadata, or telemetry. Network access is used only when a verified ExifTool binary must be acquired or repaired; media processing itself is local.
- **Air-Gapped Operation:** For completely offline or air-gapped environments, users can manually place the verified ExifTool executable into the `tools/` directory prior to launch. The application will execute without attempting any network calls.
- **GPS Metadata:** GPS coordinates from Google Takeout `.json` sidecar files are only re-embedded into media files when the GPS restoration setting is explicitly enabled. GPS data is never transmitted off-device.

## ExifTool Supply-Chain Integrity
Google Photos Takeout Restorer relies on Phil Harvey's ExifTool for metadata manipulation. To guarantee supply-chain integrity:
1. **Pinned Manifest:** All downloaded artifacts are pinned in `core/downloader.py` with known SHA-256 cryptographic checksums.
2. **Fail-Closed Acquisition:** If an archive does not match the official pinned SHA-256 hash or is not listed in the verified manifest, the download is immediately rejected, deleted, and execution is aborted.
3. **Archive Traversal Protection:** Extraction routines enforce strict path-traversal safeguards, rejecting any archive entries containing relative (`..`) or absolute path navigation.
4. **Runtime Integrity & Version Validation:** At application startup, the local ExifTool executable is inspected for presence, file integrity, and correct version reporting (`exiftool -ver` == `13.59`). Corrupted or unexpected binaries are rejected and replaced from the verified manifest.

## Verified Checksums (ExifTool 13.59)
- **Windows (x64)** `exiftool-13.59_64.zip`:
  - Archive SHA-256: `44b512b25af500724ba579d0a53c8fc5851628b692dd5e5d94ae4a15c2cba9ec`
  - Executable SHA-256: `68c079c32fdae0d6c7130e9a5fb73f8ac9dabdf9ab8da312da4f6c549d6d3385`
- **POSIX (macOS / Linux)** `Image-ExifTool-13.59.tar.gz`:
  - Archive SHA-256: `668ea3acececb7235fbd0f4900e72d5f12c9b07e5c778fd36cb1e9b5828fd65a`

## Reporting a Vulnerability
If you discover a potential security vulnerability within this project, please report it privately by opening a security advisory on GitHub or emailing the maintainer at `159574479+GurutejaReddy-04@users.noreply.github.com`. Please do not report security vulnerabilities through public GitHub issues.
