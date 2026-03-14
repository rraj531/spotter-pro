@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Local virtual environment not found at .venv\Scripts\python.exe
  echo Create it with: python -m venv .venv
  pause
  exit /b 1
)

".venv\Scripts\python.exe" "main.pyw"
exit /b %errorlevel%
