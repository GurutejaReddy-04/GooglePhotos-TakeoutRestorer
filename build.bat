@echo off
echo Building Google Photos Takeout Restorer with PyInstaller...
pyinstaller GooglePhotosTakeoutRestorer.spec --clean -y
if %ERRORLEVEL% EQU 0 (
    echo.
    echo Build completed successfully. Executable output in dist/GooglePhotosTakeoutRestorer/
) else (
    echo.
    echo Build failed with error code %ERRORLEVEL%.
    exit /b %ERRORLEVEL%
)
