# Reading Room — RAG Chat with Documents

A self-hosted PDF question-answering baseline using FastAPI, ChromaDB and Ollama.

## Rebuild branch

This branch restores the missing backend source files while preserving the original repository history and browser frontend. It includes PDF text extraction, persistent ChromaDB retrieval, Ollama generation, Docker configuration and API smoke tests.

**Known gaps:** OCR for scanned PDFs, BM25/RRF hybrid search, cross-encoder reranking, persistent server-side chat memory, authentication/multi-user isolation, durable background ingestion, and production operational controls are not implemented in this baseline. Do not expose publicly without authentication, authorization, quotas, backups, monitoring and secure storage.

## Docker

```bash
docker compose up --build
docker exec -it rag-ollama ollama pull llama3
```
Open http://localhost:8000. The first vector query can download ChromaDB's default embedding model.

## Local backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## Endpoints
- GET /health
- GET /models
- POST /upload (multipart field: files; PDF only)
- GET /documents
- DELETE /documents/{doc_id}
- POST /chat (question, optional doc_ids and model)
- DELETE /sessions/{session_id}

## Tests
```bash
pip install -r backend/requirements.txt pytest
cd backend && pytest -q
```
GitHub Actions runs these API smoke tests on pushes and pull requests. CI passing verifies those paths, not full model inference or every deployment environment.
