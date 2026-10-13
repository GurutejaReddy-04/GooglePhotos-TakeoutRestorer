@echo off
echo Building Takeout Restorer with PyInstaller...
pyinstaller TakeoutRestorer.spec --clean -y
if %ERRORLEVEL% EQU 0 (
    echo.
    echo Build completed successfully. Executable output in dist/TakeoutRestorer/
) else (
    echo.
    echo Build failed with error code %ERRORLEVEL%.
    exit /b %ERRORLEVEL%
)
