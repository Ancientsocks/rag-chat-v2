@echo off
echo ========================================================
echo   Starting Reading Room v2 - RAG Chat with Documents
echo ========================================================
echo.

cd /d "%~dp0backend"

if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

echo Installing / verifying dependencies...
"%~dp0backend\venv\Scripts\pip.exe" install -r requirements.txt

echo.
echo Starting FastAPI server at http://localhost:8000 ...
echo (Make sure Ollama is running: ollama serve)
echo.

"%~dp0backend\venv\Scripts\python.exe" -m uvicorn main:app --port 8000

pause
