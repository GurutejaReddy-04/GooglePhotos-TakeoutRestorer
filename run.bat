@echo off
cd /d "%~dp0"

if exist "C:\Users\GURUTEJAREDDY\.conda\envs\takeout_py311\pythonw.exe" (
    start "" "C:\Users\GURUTEJAREDDY\.conda\envs\takeout_py311\pythonw.exe" main.py
    exit /b 0
) else (
    start "" pythonw main.py
    exit /b 0
)
