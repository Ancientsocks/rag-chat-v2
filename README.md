# Reading Room v2 — RAG Chat with Documents

Upload multiple PDFs (including scanned ones), ask questions in a real conversation, and get
answers grounded in your documents with page/chunk-level citations, retrieval scores, and
full analytics. Fully free and open-source — no API keys anywhere.

## What's new in v2

| # | Feature | Notes |
|---|---------|-------|
| 1 | **Multi-PDF support** | Upload many PDFs at once; search across all of them or scope to specific ones |
| 2 | **Chat memory** | Follow-up questions ("which one pays highest?") resolve using conversation history, via question condensing |
| 3 | **Hybrid search** | Vector (MMR) + BM25 keyword search, fused with Reciprocal Rank Fusion |
| 4 | **Richer citations** | Every source shows document, page, chunk index, and retrieval/rerank score |
| 5 | **OCR support** | Scanned/image-based PDF pages are auto-detected and OCR'd (Tesseract) before chunking |
| 6 | **Reranking** | Top 20 hybrid candidates re-scored by a cross-encoder, best 5 sent to the LLM |
| 7 | **Model selection** | Switch between Llama 3, Mistral, Gemma, Qwen, DeepSeek at runtime (all via Ollama) |
| 8 | **UI upgrades** | Dark mode, chat history sidebar, typing animation, upload progress, clear chat |
| 9 | **Analytics panel** | Per-answer: chunks retrieved, timings per stage, model used, docs searched |
| 10 | **Docker** | `docker compose up` runs backend + Ollama together |

## Stack

Python · FastAPI · LangChain · ChromaDB (vector) · `rank-bm25` (keyword) · sentence-transformers
(embeddings + cross-encoder reranker) · PyMuPDF + pytesseract (OCR) · Ollama (LLMs) · plain
HTML/JS frontend · Docker.

## How the pipeline works

**Ingestion:** PDF → per-page text extraction → pages with near-zero text are flagged as
scanned and OCR'd with Tesseract → chunked (~900 chars, 175 overlap) with `doc_id`, filename,
page, and chunk index attached as metadata → embedded locally and stored in Chroma → the same
chunks are indexed in an in-memory BM25 index for keyword search.

**Query:**
1. If there's prior conversation in this session, the LLM condenses the follow-up question
   into a standalone one (e.g. "which one pays highest?" → "which IT job mentioned pays the
   highest salary?").
2. The standalone question is run through **both** vector search (MMR, to reduce redundant
   hits) and BM25 keyword search, each returning up to `RETRIEVAL_K` (default 10) chunks.
3. Both ranked lists are merged via **Reciprocal Rank Fusion** into a candidate pool of up to
   `RERANK_CANDIDATES` (default 20).
4. A cross-encoder reranker re-scores each (question, chunk) pair and keeps the best
   `RERANK_TOP_N` (default 5).
5. Those chunks, formatted with their citations, plus the recent conversation history, are
   sent to the selected Ollama model with a context-only-answering instruction.
6. The answer, sources (with scores), and analytics (timings per stage, chunks retrieved,
   model used) are returned together; the turn is saved to session memory.

## Setup — local (no Docker)

### 1. Install Ollama and pull models

```bash
# macOS: brew install ollama, or download from https://ollama.com
ollama serve
ollama pull llama3        # pull whichever models you want available in the dropdown
ollama pull mistral
```

### 2. System dependency for OCR

```bash
# macOS
brew install tesseract
# Ubuntu/Debian
sudo apt-get install tesseract-ocr
```

### 3. Python deps

```bash
cd backend
python3 -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Run

```bash
uvicorn main:app --reload --port 8000
```

Open **http://localhost:8000**. API docs at **http://localhost:8000/docs**.

## Setup — Docker (one command)

```bash
cp .env.example .env      # adjust if you want non-default models/settings
docker compose up --build
```

This starts Ollama and the backend together. The first time, pull a model into the Ollama
container:

```bash
docker exec -it rag-ollama ollama pull llama3
```

Then open **http://localhost:8000**.

## Configuration

All tunables are environment variables — see `.env.example` for the full list, including
retrieval `k`, MMR/hybrid/rerank toggles, chunk size/overlap, OCR thresholds, and chat memory
length.

## API reference

- `POST /upload` — multipart, field `files` (one or more PDFs)
- `GET /documents` — list indexed documents
- `DELETE /documents/{doc_id}` — remove a document, its vectors, and rebuild the BM25 index
- `GET /models` — available models for the selector + default
- `POST /chat` — `{"question", "doc_ids": [...] | null, "model": "llama3" | null, "session_id"}`
  → `{"answer", "sources": [...], "analytics": {...}}`
- `DELETE /sessions/{session_id}` — clear a conversation's memory

## Design notes / production considerations

- **Chat memory** is an in-memory dict keyed by `session_id` — fine for a single-process
  demo. For production, swap it for Redis or a DB table (`memory.py` isolates this so the
  swap doesn't touch the rest of the engine).
- **BM25 index** is rebuilt in-memory on every upload/delete from Chroma's stored documents,
  so it can never drift out of sync — fine at demo scale; at large scale you'd persist and
  incrementally update it instead of rebuilding.
- **OCR** uses Tesseract via PyMuPDF+pytesseract rather than EasyOCR/PaddleOCR — much lighter
  (no large model downloads, no GPU dependency) while still fully open-source; swap in
  `ocr_utils.py` if you need EasyOCR's higher accuracy on messier scans.
- **Large PDF uploads** currently block the request while chunking/embedding/OCR run. For
  production, move this to a background worker (Celery/RQ) and let the client poll for
  status.
- **Model switching** creates a new Ollama client per model name on first use and caches it;
  make sure any model offered in `AVAILABLE_MODELS` has actually been `ollama pull`'d, or
  chat requests using it will fail with a clear error telling the user to pull it.

## Project structure

```
rag-chat-v2/
├── backend/
│   ├── main.py           # FastAPI routes
│   ├── rag_engine.py      # ingestion, hybrid retrieval, reranking, generation
│   ├── bm25_index.py       # in-memory BM25 keyword index
│   ├── reranker.py         # cross-encoder reranking
│   ├── memory.py            # session chat history + question condensing
│   ├── ocr_utils.py          # scanned-page detection + Tesseract OCR
│   ├── config.py               # all env-var-driven settings
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   └── index.html          # dark mode, sessions sidebar, model picker, analytics panel
├── docker-compose.yml
├── .env.example
└── data/                     # uploaded PDFs + persistent Chroma store (gitignored contents)
```
