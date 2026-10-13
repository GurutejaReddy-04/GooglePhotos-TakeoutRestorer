@echo off
cd /d "%~dp0"
echo Starting Google Photos Takeout Restorer...

if exist "C:\Users\GURUTEJAREDDY\.conda\envs\takeout_py311\python.exe" (
    "C:\Users\GURUTEJAREDDY\.conda\envs\takeout_py311\python.exe" main.py
) else (
    python main.py
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Application exited with an error.
    pause
)
