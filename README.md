# Google Photos Takeout Restorer

A high-performance, robust desktop application to restore Google Photos metadata from JSON sidecar files directly into your image and video files (EXIF). Perfect for recovering your Google Takeout archive.

![Google Photos Takeout Restorer](assets/screenshot.png)

## Features

- **Metadata Injection:** Merges `.json` sidecar files from Google Takeout directly into the EXIF data of the images (`.jpg`, `.png`, `.heic`, etc.) and videos (`.mp4`, `.mov`).
- **Live Photo Support:** Properly pairs and injects timestamps into both the image and the video parts of Apple Live Photos, avoiding duplicates and double-counting progress.
- **Timezone Correction:** Uses embedded GPS coordinates to intelligently correct UTC timestamps to your local timezone.
- **High Performance:** Utilizes Python's `ThreadPoolExecutor` and pre-warmed `ExifTool` daemon processes to rapidly process tens of thousands of photos using all available CPU cores.
- **Modern UI:** Built with CustomTkinter for a sleek, wizard-style user experience.

## Core Dependency

Google Photos Takeout Restorer relies on **Phil Harvey's ExifTool**. To ensure maximum stability and prevent false-positive Windows Defender hits, the application automatically downloads and locks onto **ExifTool version 13.59 (Windows/macOS/Linux)** during the first-time setup. The executable is safely isolated in the local `tools/` directory.

## Installation

### Option 1: Download the Executable (Windows)

1. Go to the [Releases](https://github.com/GurutejaReddy-04/GooglePhotos-TakeoutFixer/releases) page.
2. Download the latest `GooglePhotosTakeoutFixer.zip`.
3. Extract the folder and run `GooglePhotosTakeoutFixer.exe`. No installation required!

### Option 2: Run from Source

#### Prerequisites
- Python 3.9+
- ExifTool will be automatically downloaded by the application on first run, so manual installation is not required.

#### Setup
```bash
git clone https://github.com/GurutejaReddy-04/GooglePhotos-TakeoutFixer.git
cd "Google Photos Takeout Restorer"

# Create a virtual environment (optional but recommended)
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the app
python main.py
```

## Usage

1. **Import:** Drag and drop your Google Takeout `.zip` files (or extracted folders) into the app.
2. **Destination:** Choose an empty folder where the processed, fixed photos will be saved.
3. **Settings:** Toggle features like GPS, Timezone correction, or High-Performance mode.
4. **Export:** Click Start and watch the progress!

## Building the Executable

To build the standalone application yourself using PyInstaller, simply run the included batch script:

```bash
build.bat
```
The resulting executable package will be available in the `dist/` directory.

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.


## Author

**Guruteja Reddy Nallachi**

GitHub: https://github.com/GurutejaReddy-04
