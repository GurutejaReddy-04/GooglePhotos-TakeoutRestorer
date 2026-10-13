@echo off
cd /d "%~dp0"

if exist "%USERPROFILE%\.conda\envs\takeout_py311\pythonw.exe" (
    start "" "%USERPROFILE%\.conda\envs\takeout_py311\pythonw.exe" main.py
    exit /b 0
) else (
    start "" pythonw main.py
    exit /b 0
)
