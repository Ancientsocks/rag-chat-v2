@echo off
echo ========================================================
echo   Starting Reading Room v2 with Docker Compose
echo ========================================================
echo.

cd /d "%~dp0"

echo Starting containers (backend + Ollama)...
docker compose up -d --build

echo.
echo Pulling default model (llama3)...
docker exec -it rag-ollama ollama pull llama3

echo.
echo ========================================================
echo  Server is up at: http://localhost:8000
echo ========================================================
docker compose logs -f backend
