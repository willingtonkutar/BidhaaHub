@echo off
setlocal
for %%I in ("%~dp0..") do set "PROJECT_ROOT=%%~fI"
for %%I in ("%PROJECT_ROOT%..") do set "WORKSPACE_ROOT=%%~fI"
set "PYTHON=%WORKSPACE_ROOT%\.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
  echo Virtual environment not found. Please create .venv first.
  exit /b 1
)

cd /d "%PROJECT_ROOT%"
"%PYTHON%" -m uvicorn app.main:app --reload
