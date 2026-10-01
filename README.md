# Google Photos Takeout Restorer

A high-performance, robust desktop application to restore Google Photos metadata from JSON sidecar files directly into your image and video files (EXIF). Perfect for recovering your Google Takeout archive.

![Google Photos Takeout Restorer](assets/screenshot.png)

## Features

- **Metadata Injection:** Merges `.json` sidecar files from Google Takeout directly into the EXIF data of the images (`.jpg`, `.png`, `.heic`, etc.) and videos (`.mp4`, `.mov`).
- **Live Photo Support:** Properly pairs and injects timestamps into both the image and the video parts of Apple Live Photos, avoiding duplicates and double-counting progress.
- **Timezone Correction:** Uses embedded GPS coordinates to intelligently correct UTC timestamps to your local timezone.
- **High Performance:** Utilizes Python's `ThreadPoolExecutor` and pre-warmed `ExifTool` daemon processes to rapidly process photo libraries using a multi-threaded worker pool (default 4 workers, up to 12 in High-Performance mode).
- **Modern UI:** Built with CustomTkinter for a sleek, wizard-style user experience.

---

## 🚀 Project Evolution: Python Prototype → Rust Rewrite

This repository represents the **original Python reference implementation** of Google Photos Takeout Restorer. 

To overcome platform packaging trade-offs and maximize throughput, a full native rewrite was subsequently built in Rust:
👉 **[GooglePhotos-TakeoutRestorer-Rust](https://github.com/GurutejaReddy-04/GooglePhotos-TakeoutRestorer-Rust)**

### Why the Rust Rewrite?
- **IPC Protocol:** Persistent ExifTool STDIN command batching reduces per-file process communication overhead.
- **Concurrency:** Multi-threaded work distribution configured across CPU cores without Python Global Interpreter Lock (GIL) constraints.
- **Packaging & Startup:** Fully self-contained native binary with zero Python runtime dependencies or PyInstaller unpack latency.
- **UI Architecture:** Native GPU-accelerated Slint interface replacing Tkinter.

Both repositories remain public to document this architectural evolution.

---

## Core Dependency & Supply-Chain Security

Google Photos Takeout Restorer relies on **Phil Harvey's ExifTool**. To ensure maximum stability and supply-chain integrity:
- The application automatically downloads and verifies **ExifTool version 13.59** against pinned cryptographic SHA-256 checksums from official distribution mirrors.
- If checksum verification fails or an unmanifested version is encountered, the installer fails closed and aborts execution.
- The executable is isolated in the local `tools/` directory.
- For air-gapped / offline environments, simply place the verified executable into `tools/` prior to running; no network requests will be attempted.
- See [SECURITY.md](SECURITY.md) for full supply-chain policies and checksum manifests.

---

## Privacy & Local Processing Guarantee

- **Local Execution:** Media processing is performed strictly locally on your device.
- **No Telemetry:** The current implementation contains no code that transmits photo data, metadata, or telemetry. Network access is used only when a verified ExifTool binary must be acquired or repaired; media processing itself is local.
- **GPS Privacy:** GPS coordinates from Google Takeout `.json` sidecars are only re-embedded if the GPS toggle is enabled. Location data is never transmitted off-device.

---

## Installation

### Option 1: Download the Executable (Windows)

1. Go to the [Releases](https://github.com/GurutejaReddy-04/GooglePhotos-TakeoutRestorer/releases) page.
2. Download the latest `GooglePhotosTakeoutRestorer.zip`.
3. Extract the folder and run `GooglePhotosTakeoutRestorer.exe`. No installation required!

### Option 2: Run from Source

#### Prerequisites
- Python 3.9+ (tested on Python 3.9, 3.10, 3.11, 3.12)
- ExifTool is verified and downloaded automatically on first run, or can be pre-staged in `tools/`.

#### Setup
```bash
git clone https://github.com/GurutejaReddy-04/GooglePhotos-TakeoutRestorer.git
cd GooglePhotos-TakeoutRestorer

# Create a virtual environment (recommended)
python -m venv venv

# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install runtime dependencies
pip install -r requirements.txt

# (Optional) Install development and test dependencies
pip install -r requirements-dev.txt

# Run the app
python main.py
```

---

## Usage

1. **Import:** Drag and drop your Google Takeout `.zip` files (or extracted folders) into the app.
2. **Destination:** Choose an empty folder where the processed, fixed photos will be saved.
3. **Settings:** Toggle features like GPS, Timezone correction, or High-Performance mode.
4. **Export:** Click Start and monitor progress in real time!

---

## Performance & Concurrency Model

The application processes media asynchronously:
- **Normal Mode:** 4 concurrent worker threads with persistent ExifTool daemons.
- **High-Performance Mode:** Dynamically scales worker count up to 12 workers based on available CPU cores and RAM (`min(cores, available_ram_mb // 80, 12)`), preventing memory exhaustion while maximizing throughput.
- To run reproducible synthetic benchmarks on your hardware:
  ```bash
  python scripts/benchmark_pipeline.py
  ```

---

## Building the Executable

To package the standalone application yourself using PyInstaller:

**On Windows:**
```bash
build.bat
```

**Cross-Platform (Manual):**
```bash
pyinstaller GooglePhotosTakeoutRestorer.spec --clean -y
```
The resulting executable package will be available in the `dist/GooglePhotosTakeoutRestorer/` directory.

---

## Testing

Run the automated test suite:
```bash
pytest tests/ -v
```

---

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Author

**Guruteja Reddy Nallachi**
GitHub: https://github.com/GurutejaReddy-04

