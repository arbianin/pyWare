@echo off
setlocal
cd /d "%~dp0"
echo ============================================
echo  pyWare - library installer
echo ============================================
echo.

echo [1/2] Checking for Python...
py --version >nul 2>nul
if %errorlevel% neq 0 (
  echo  Python not found. Installing Python 3.12 via winget...
  winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
  if %errorlevel% neq 0 (
    echo  ERROR: could not install Python. Get it manually:
    echo  https://www.python.org/downloads/
    pause
    exit /b 1
  )
  echo  Installed. If 'py' is still unknown, re-open this script.
)
py --version
echo  OK.
echo.

echo [2/2] Installing libraries (PyQt5, psutil, requests)...
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
if %errorlevel% neq 0 (
  echo  ERROR: pip install failed. Check your internet connection.
  pause
  exit /b 1
)
echo  OK.
echo.
echo ============================================
echo  DONE. Launch (as ADMIN):  py main.py
echo  Start Roblox and join a game first.
echo ============================================
pause
