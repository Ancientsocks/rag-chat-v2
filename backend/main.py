
from __future__ import annotations

import os
import uuid
import logging
from pathlib import Path
from typing import Optional

import chromadb
import httpx

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pypdf import PdfReader


# ============================================================
# 1. CONFIGURATION
# ============================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reading-room")

DATA = Path(
    os.getenv(
        "DATA_DIR",
        str(Path(__file__).resolve().parent / "data")
    )
).expanduser()

UPLOADS = DATA / "uploads"
DB = DATA / "chroma_db"

UPLOADS.mkdir(parents=True, exist_ok=True)
DB.mkdir(parents=True, exist_ok=True)

OLLAMA = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434"
).rstrip("/")

DEFAULT = os.getenv("DEFAULT_MODEL", "llama3")

MODELS = [
    x.strip()
    for x in os.getenv(
        "AVAILABLE_MODELS",
        "llama3,mistral,gemma,qwen,deepseek-r1"
    ).split(",")
    if x.strip()
]

SIZE = int(os.getenv("CHUNK_SIZE", "900"))
OVERLAP = int(os.getenv("CHUNK_OVERLAP", "175"))

MAX_FILE_SIZE = 30 * 1024 * 1024
MAX_FILES_PER_UPLOAD = 10
RETRIEVAL_COUNT = 5

if SIZE < 100 or not 0 <= OVERLAP < SIZE:
    raise RuntimeError("Invalid chunk size or overlap configuration")


# ============================================================
# 2. CHROMADB INITIALIZATION
# ============================================================

chroma = chromadb.PersistentClient(path=str(DB))

collection = chroma.get_or_create_collection(
    name="reading_room",
    metadata={"hnsw:space": "cosine"}
)


# ============================================================
# 3. FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="Reading Room RAG API",
    description="Chat with your PDF documents using RAG and Ollama.",
    version="2.2.0"
)

cors_origins = [
    x.strip()
    for x in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:8002"
    ).split(",")
    if x.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"]
)


# ============================================================
# 4. REQUEST SCHEMAS
# ============================================================

class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=8000)
    doc_ids: Optional[list[str]] = None
    model: Optional[str] = None
    session_id: Optional[str] = None


# ============================================================
# 5. TEXT CHUNKING
# ============================================================

def chunks(text: str) -> list[str]:
    """
    Split extracted PDF text into overlapping chunks.
    """

    text = " ".join(text.split())

    output = []
    start = 0

    while start < len(text):
        end = min(start + SIZE, len(text))

        chunk = text[start:end].strip()

        if chunk:
            output.append(chunk)

        if end == len(text):
            break

        start = end - OVERLAP

    return output


# ============================================================
# 6. HEALTH CHECK
# ============================================================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": app.version,
        "vector_store": "chroma"
    }


# ============================================================
# 7. AVAILABLE MODELS
# ============================================================

@app.get("/models")
def models():
    return {
        "models": MODELS,
        "default": DEFAULT
    }


# ============================================================
# 8. PDF UPLOAD AND INDEXING
# ============================================================

@app.post("/upload")
async def upload(files: list[UploadFile] = File(...)):

    if not files:
        raise HTTPException(
            status_code=400,
            detail="Please upload at least one PDF."
        )

    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_FILES_PER_UPLOAD} files per upload."
        )

    results = []

    for file in files:

        filename = Path(file.filename or "").name

        if not filename or not filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=415,
                detail="Only PDF files are supported."
            )

        data = await file.read()

        if len(data) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"{filename} exceeds the 30 MB limit."
            )

        if not data.startswith(b"%PDF"):
            raise HTTPException(
                status_code=400,
                detail=f"{filename} is not a valid PDF."
            )

        doc_id = str(uuid.uuid4())
        path = UPLOADS / f"{doc_id}.pdf"

        path.write_bytes(data)

        try:

            reader = PdfReader(str(path))

            records = []

            for page_no, page in enumerate(reader.pages, start=1):

                page_text = page.extract_text() or ""

                page_chunks = chunks(page_text)

                for index, chunk in enumerate(page_chunks):

                    records.append(
                        (chunk, page_no, index)
                    )

            if not records:
                raise ValueError(
                    "No extractable text found. "
                    "Scanned PDFs require OCR, which is not implemented yet."
                )

            collection.add(
                ids=[
                    f"{doc_id}:{page}:{index}"
                    for _, page, index in records
                ],
                documents=[
                    record[0]
                    for record in records
                ],
                metadatas=[
                    {
                        "doc_id": doc_id,
                        "filename": filename,
                        "page": page,
                        "chunk_index": index
                    }
                    for _, page, index in records
                ]
            )

            results.append(
                {
                    "doc_id": doc_id,
                    "filename": filename,
                    "num_chunks": len(records),
                    "status": "indexed"
                }
            )

            logger.info(
                "Indexed PDF: %s (%s chunks)",
                filename,
                len(records)
            )

        except Exception as exc:

            path.unlink(missing_ok=True)

            raise HTTPException(
                status_code=422,
                detail=f"Could not index {filename}: {exc}"
            ) from exc

    return {
        "documents": results
    }


# ============================================================
# 9. LIST UPLOADED DOCUMENTS
# ============================================================

@app.get("/documents")
def documents():

    raw = collection.get(
        include=["metadatas"]
    )

    grouped = {}

    for metadata in raw.get("metadatas") or []:

        doc_id = metadata["doc_id"]

        document = grouped.setdefault(
            doc_id,
            {
                "doc_id": doc_id,
                "filename": metadata["filename"],
                "num_chunks": 0
            }
        )

        document["num_chunks"] += 1

    return {
        "documents": list(grouped.values())
    }


# ============================================================
# 10. DELETE A DOCUMENT
# ============================================================

@app.delete("/documents/{doc_id}")
def delete_document(doc_id: str):

    found = collection.get(
        where={"doc_id": doc_id},
        include=["metadatas"]
    )

    if not found.get("ids"):
        raise HTTPException(
            status_code=404,
            detail="Document not found."
        )

    collection.delete(
        ids=found["ids"]
    )

    file_path = UPLOADS / f"{doc_id}.pdf"

    file_path.unlink(missing_ok=True)

    logger.info("Deleted document: %s", doc_id)

    return {
        "deleted": doc_id,
        "status": "success"
    }


# ============================================================
# 11. RAG CHAT
# ============================================================

@app.post("/chat")
async def chat(req: ChatRequest):

    question = req.question.strip()

    if not question:
        raise HTTPException(
            status_code=422,
            detail="Question cannot be blank."
        )

    model = req.model or DEFAULT

    if model not in MODELS:
        raise HTTPException(
            status_code=400,
            detail="Model is not configured."
        )

    # --------------------------------------------------------
    # STEP 1: RETRIEVE RELEVANT CHUNKS FROM CHROMADB
    # --------------------------------------------------------

    where = (
        {"doc_id": {"$in": req.doc_ids}}
        if req.doc_ids
        else None
    )

    try:

        result = collection.query(
            query_texts=[question],
            n_results=RETRIEVAL_COUNT,
            where=where
        )

    except Exception as exc:

        logger.exception("ChromaDB retrieval failed")

        raise HTTPException(
            status_code=503,
            detail=f"Retrieval failed: {exc}"
        ) from exc

    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    ids = (result.get("ids") or [[]])[0]

    if not docs:

        return {
            "answer": "No relevant document content found. Upload a PDF first.",
            "sources": [],
            "analytics": {
                "chunks_retrieved": 0,
                "model": model
            }
        }

    # --------------------------------------------------------
    # STEP 2: BUILD DOCUMENT CONTEXT
    # --------------------------------------------------------

    context = "\n\n".join(
        (
            f"[{index + 1}] "
            f"{metadata['filename']} "
            f"(page {metadata['page']}): "
            f"{document}"
        )
        for index, (document, metadata)
        in enumerate(zip(docs, metas))
    )

    # --------------------------------------------------------
    # STEP 3: BUILD PROMPT
    # --------------------------------------------------------

    prompt = (
        "You are an intelligent document question-answering assistant.\n"
        "Answer the user's question using only the supplied document context.\n"
        "Do not invent information or assume facts that are not present.\n"
        "If the answer is missing, clearly state that the document "
        "does not contain the requested information.\n"
        "Use clear and simple language.\n"
        "Cite supporting passages using references such as [1] and [2].\n\n"
        f"DOCUMENT CONTEXT:\n{context}\n\n"
        f"USER QUESTION:\n{question}\n\n"
        "ANSWER:"
    )

    # --------------------------------------------------------
    # STEP 4: CALL OLLAMA
    # --------------------------------------------------------

    timeout = httpx.Timeout(
        timeout=600.0,
        connect=10.0
    )

    try:

        async with httpx.AsyncClient(
            timeout=timeout
        ) as client:

            response = await client.post(
                f"{OLLAMA}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False
                }
            )

            response.raise_for_status()

            answer = (
                response.json()
                .get("response", "")
                .strip()
            )

            if not answer:

                raise HTTPException(
                    status_code=502,
                    detail="Ollama returned an empty response."
                )

    except httpx.TimeoutException as exc:

        logger.exception("Ollama request timed out")

        raise HTTPException(
            status_code=504,
            detail="AI response timed out. Please try again."
        ) from exc

    except httpx.HTTPError as exc:

        logger.exception("Ollama request failed")

        raise HTTPException(
            status_code=502,
            detail=f"Ollama request failed: {exc}"
        ) from exc

    # --------------------------------------------------------
    # STEP 5: BUILD SOURCE REFERENCES
    # --------------------------------------------------------

    sources = [
        {
            "filename": metadata["filename"],
            "page": metadata["page"],
            "chunk_index": metadata["chunk_index"],
            "score": None,
            "snippet": document[:350],
            "chunk_id": chunk_id
        }
        for document, metadata, chunk_id
        in zip(docs, metas, ids)
    ]

    # --------------------------------------------------------
    # STEP 6: RETURN RESPONSE
    # --------------------------------------------------------

    logger.info(
        "Chat completed using model %s; retrieved %s chunks",
        model,
        len(docs)
    )

    return {
        "answer": answer,
        "sources": sources,
        "analytics": {
            "chunks_retrieved": len(docs),
            "model": model
        }
    }


# ============================================================
# 12. CLEAR CHAT SESSION
# ============================================================

@app.delete("/sessions/{session_id}")
def clear_session(session_id: str):

    # Session history is not implemented in this version.
    # This endpoint currently provides a compatibility response.

    return {
        "cleared": session_id,
        "status": "success",
        "note": "Persistent conversation history is not implemented."
    }


# ============================================================
# 13. SERVE FRONTEND
# ============================================================

static = Path("/app/static")

if static.exists():

    app.mount(
        "/",
        StaticFiles(
            directory=str(static),
            html=True
        ),
        name="frontend"
    )
