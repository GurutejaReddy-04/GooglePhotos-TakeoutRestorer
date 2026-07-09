"""
Shared utility functions for the core module.
"""

import sys
from pathlib import Path


def get_app_base_path() -> Path:
    """
    Get the base path of the application, handling both development and PyInstaller modes.
    """
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        if hasattr(sys, '_MEIPASS'):
            # PyInstaller --onedir mode
            return Path(sys._MEIPASS)
        else:
            # PyInstaller --onefile mode or other
            return Path(sys.executable).parent
    else:
        # Running in development mode
        return Path(__file__).parent.parent
