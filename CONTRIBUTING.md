# Contributing to Google Photos Takeout Restorer

Thank you for your interest in contributing! 

## Development Setup

1. Fork the repository and clone it locally.
2. Create a virtual environment: `python -m venv venv`
3. Activate the environment and install requirements: `pip install -r requirements.txt`
4. Download ExifTool and place it in the `tools/` directory.

## Pull Request Process

1. Create a descriptive branch name (e.g., `feature/live-photo-support` or `bugfix/progress-bar-math`).
2. Write clear commit messages.
3. If you add a new feature, please try to test it end-to-end to ensure it doesn't break existing metadata injection.
4. Submit your PR against the `main` branch.

## Code Style

- We use standard Python conventions (PEP 8).
- Please keep CustomTkinter UI logic in `ui/` and data/processing logic strictly within `core/`.
- Ensure ExifTool background processes are safely cleaned up using `try...finally` blocks as implemented in `FileProcessor`.
