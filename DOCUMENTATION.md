# Google Photos Takeout Restorer - Technical Documentation

## 1. Project Overview
Google Photos Takeout Restorer is a robust, high-performance cross-platform desktop application designed to process Google Takeout data. It merges `.json` sidecar files containing essential metadata back into image and video files (via EXIF/XMP). It runs on Windows, macOS, and Linux, and leverages CustomTkinter for a sleek wizard UI, alongside a parallelized Python background worker architecture that manages `ExifTool` daemon processes.

## 2. Architecture & Execution Flow
The system is divided into two primary tiers:
1. **Frontend UI Tier (`ui/`)**: A CustomTkinter-based wizard that collects inputs, validates them, and renders the progress dynamically using a polled callback architecture.
2. **Core Processing Tier (`core/`)**: A multi-threaded, robust backend that scans the inputs, pairs files with their JSON counterparts, extracts them JIT (Just-in-Time) if they are in ZIP archives, and writes the metadata via persistent ExifTool processes.

### Pipeline Execution Flow:
1. **Import Stage**: User selects or drags ZIPs/folders.
2. **Destination Stage**: Validation of output paths and OS permissions.
3. **Settings Stage**: Configuration of pipeline features (GPS, Timezones, concurrency).
4. **Processing (Confirm) Stage**:
   - `FileScanner`: Deeply scans the input (including traversing nested ZIP files natively via Python's `zipfile`) and stages them in SQLite.
   - `MetadataMatcher`: Pairs each media file with its respective Google JSON file using confidence heuristics.
   - `FileProcessor`: A threaded pipeline that reads the matching JSON, extracts the media file to a `.tmp_working` directory, and dispatches it to a worker thread.
   - `ExifToolEngine`: Maintains persistent `exiftool -stay_open True` background processes to drastically reduce the startup overhead of executing ExifTool per file.
   - Files are moved to their final `Completed` or `Unmatched` folders.
5. **Results Stage**: Final cleanup, metrics calculation, and user report generation.

## 3. Folder Structure
```text
GooglePhotosTakeoutRestorer/
├── core/                   # Backend processing engine
│   ├── downloader.py       # ExifTool binary downloader
│   ├── exiftool_engine.py  # Persistent ExifTool process manager
│   ├── matcher.py          # Fuzzy matching logic for JSON/Media
│   ├── parser.py           # Google Takeout JSON metadata parser
│   ├── processor.py        # Concurrent pipeline dispatcher
│   ├── progress_model.py   # Dataclass wrappers for progress reporting
│   ├── scanner.py          # Multi-format ZIP/Folder indexer
│   ├── state_db.py         # Thread-safe SQLite backend for state
│   └── writer.py           # Exif injection & Auto-healing core logic
├── ui/                     # Frontend interface
│   ├── app.py              # Main CustomTkinter Application root
│   └── pages/              # Wizard views (page_welcome.py, etc.)
├── tools/                  # (Ignored) Auto-downloaded ExifTool binaries
├── main.py                 # Application Entry Point
├── README.md               # User-facing project description
└── DOCUMENTATION.md        # Technical architectural documentation
```

## 4. Module Descriptions

### `core/exiftool_engine.py`
The most critical performance component. Instead of launching a new ExifTool binary for every image (which incurs a ~300ms overhead), this engine spawns a pool of background perl daemons. Commands are piped to the daemon's STDIN and results are parsed from STDOUT asynchronously.

### `core/state_db.py`
To handle the scale of tens of thousands of files without blowing up RAM, all file states are stored in a local SQLite database (`state_<run_id>.db`). This enables atomic transactions, crash recovery, and rich filtering for the UI's progress bars.

### `core/writer.py`
The writer orchestrates the actual metadata injection. It includes a robust "auto-healing" pipeline: if Google Takeout incorrectly labels a JPEG as a `.heic` file, `writer.py` will read the magic bytes, rename it to `.jpg`, and retry the ExifTool injection automatically.

## 5. Build & Deployment
The application is packaged into a single-file executable using **PyInstaller**. 
The `GooglePhotosTakeoutRestorer.spec` file defines the build constraints, ensuring CustomTkinter assets are bundled correctly.
```bash
pyinstaller GooglePhotosTakeoutRestorer.spec --clean -y
```

## 6. Error Handling
The processing pipeline implements graceful degradation:
- **Corrupt ZIPs**: Skipped with a logged warning, but does not crash the pipeline.
- **Corrupt Metadata**: Defaults to basic file timestamping.
- **ExifTool Daemon Crashes**: The `ExifToolEngine` detects broken pipes and falls back to a one-shot `subprocess.run` execution for that specific file, then restarts the daemon in the background.

## 7. Security Considerations
- The `ExifTool` binary is downloaded strictly from Phil Harvey's official GitHub releases or source distribution to ensure supply chain security. The `downloader.py` verifies file integrity if hashes are provided.
- The UI runs in User space and only requires Write permissions for the Destination Directory. No elevation (Admin rights) is requested.

## 8. Troubleshooting
- **Unicode UI Artifacts**: Ensure the host OS supports the font rendering for symbols. If the progress bar text glitches, it's typically related to CustomTkinter `fg_color` transparency mismatches.
- **Slow Processing**: The `High Performance Mode` utilizes extensive threads. If I/O bound (e.g. HDD instead of SSD), this mode might actually bottleneck due to disk thrashing. Recommend disabling it for mechanical drives.
- **Residual .tmp_working folders**: If the app crashes completely, a `.tmp_working` folder might be left in the Output directory. It can be safely deleted.

## 9. Future Improvements
- **Cross-Platform Drag and Drop**: Port the `windnd` drag-and-drop feature to native macOS/Linux hooks to allow dragging ZIP archives on non-Windows platforms.
- **Other Cloud Providers**: Add support for parsing metadata formatting from other platforms (e.g. Apple iCloud Takeouts).
