# Contributing to Takeout Restorer for Google Photos

Thank you for your interest in contributing! 

## Development Setup

1. Fork the repository and clone it locally.
2. Create a virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```
3. Install runtime and development dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```
4. ExifTool Setup: ExifTool will be automatically downloaded and verified against its official checksum when running `python main.py`. Alternatively, you can manually place the approved `exiftool.exe` (Windows) or `exiftool` script (macOS/Linux) into the `tools/` directory.

## Running Tests

Run the deterministic test suite before submitting changes:
```bash
pytest tests/ -v
```

## Pull Request Process

1. Create a descriptive branch name (e.g., `feature/live-photo-support` or `bugfix/progress-bar-math`).
2. Write clear commit messages.
3. Ensure all automated tests pass (`pytest tests/ -v`). If you add a new feature, please include corresponding unit and integration tests under `tests/`.
4. Submit your PR against the `main` branch.

## Code Style

- We use standard Python conventions (PEP 8).
- Please keep CustomTkinter UI logic in `ui/` and data/processing logic strictly within `core/`.
- Ensure ExifTool background processes are safely cleaned up using `try...finally` blocks as implemented in `FileProcessor`.
