Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Starting Reading Room v2 - RAG Chat with Documents" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

$backendDir = Join-Path $PSScriptRoot "backend"
Set-Location -Path $backendDir

if (-not (Test-Path "$backendDir\venv")) {
    Write-Host "Creating Python virtual environment..." -ForegroundColor Yellow
    python -m venv "$backendDir\venv"
}

Write-Host "Installing / verifying dependencies..." -ForegroundColor Yellow
& "$backendDir\venv\Scripts\pip.exe" install -r "$backendDir\requirements.txt"

Write-Host "`nStarting server at http://localhost:8000 ..." -ForegroundColor Green
Write-Host "(Ensure Ollama is running with: ollama serve)`n" -ForegroundColor Yellow

& "$backendDir\venv\Scripts\python.exe" -m uvicorn main:app --port 8000
