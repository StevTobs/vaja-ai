@echo off
rem Double-click to install VAJA AI. Opens the installer window; no commands to type.
start "" powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0installer\install.ps1"
