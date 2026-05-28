# Build parakeet-ptt Windows executable using PyInstaller.
# Run from the windows/ directory:
#   powershell -ExecutionPolicy Bypass -File packaging\build_exe.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot   # windows/

Write-Host "Building Parakeet PTT Windows executable..." -ForegroundColor Cyan

# Ensure PyInstaller is available
& python -m pip install pyinstaller Pillow --quiet

# Convert SVG icon to ICO (requires Pillow + cairosvg or pre-made .ico)
# For now assumes data\icons\parakeet-ptt.ico exists — see README for conversion steps

pyinstaller `
    --name "Parakeet PTT" `
    --onefile `
    --windowed `
    --icon "$Root\data\icons\parakeet-ptt.ico" `
    --add-data "$Root\data;data" `
    --hidden-import "pynput.keyboard._win32" `
    --hidden-import "pynput.mouse._win32" `
    "$Root\parakeet_ptt\main.py"

Write-Host ""
Write-Host "Done: dist\Parakeet PTT.exe" -ForegroundColor Green
Write-Host "Distribute that single .exe — no Python install required on the target machine."
