Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkspaceRoot = Split-Path -Parent $ProjectRoot
$Python = Join-Path $WorkspaceRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $Python)) {
    Write-Host 'Virtual environment not found. Please create .venv first.' -ForegroundColor Red
    exit 1
}

Set-Location $ProjectRoot
& $Python -m uvicorn app.main:app --reload
