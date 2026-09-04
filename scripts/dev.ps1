# Levanta backend y frontend en Windows, en dos ventanas separadas.
#   .\scripts\dev.ps1
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot

Write-Host "== Backend ==" -ForegroundColor Cyan
Push-Location "$raiz\backend"
if (-not (Test-Path ".venv")) {
    python -m venv .venv
    & ".\.venv\Scripts\pip.exe" install -q -r requirements.txt
}
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$raiz\backend'; .\.venv\Scripts\uvicorn.exe app.main:app --reload --port 8000"
)
Pop-Location

Write-Host "== Frontend ==" -ForegroundColor Cyan
Push-Location "$raiz\frontend"
if (-not (Test-Path "node_modules")) { npm install }
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command", "cd '$raiz\frontend'; npm run dev"
)
Pop-Location

Write-Host ""
Write-Host "  Panel:    http://localhost:3000" -ForegroundColor Green
Write-Host "  API docs: http://localhost:8000/docs" -ForegroundColor Green
