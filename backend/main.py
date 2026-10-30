from __future__ import annotations
import os, uuid
from pathlib import Path
from typing import Optional
import chromadb, httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pypdf import PdfReader
DATA=Path(os.getenv("DATA_DIR",str(Path(__file__).resolve().parent/"data"))).expanduser(); UPLOADS=DATA/"uploads"; DB=DATA/"chroma_db"
UPLOADS.mkdir(parents=True,exist_ok=True); DB.mkdir(parents=True,exist_ok=True)
OLLAMA=os.getenv("OLLAMA_BASE_URL","http://localhost:11434").rstrip("/")
DEFAULT=os.getenv("DEFAULT_MODEL","llama3")
MODELS=[x.strip() for x in os.getenv("AVAILABLE_MODELS","llama3,mistral,gemma,qwen,deepseek-r1").split(",") if x.strip()]
SIZE=int(os.getenv("CHUNK_SIZE","900")); OVERLAP=int(os.getenv("CHUNK_OVERLAP","175"))
if SIZE<100 or not 0<=OVERLAP<SIZE: raise RuntimeError("Invalid chunk size/overlap")
chroma=chromadb.PersistentClient(path=str(DB)); collection=chroma.get_or_create_collection("reading_room",metadata={"hnsw:space":"cosine"})
app=FastAPI(title="Reading Room RAG API",version="2.1.0")
app.add_middleware(CORSMiddleware,allow_origins=os.getenv("CORS_ORIGINS","http://localhost:8000").split(","),allow_methods=["*"],allow_headers=["*"])
class ChatRequest(BaseModel):
 question:str=Field(min_length=1,max_length=8000)
 doc_ids:Optional[list[str]]=None
 model:Optional[str]=None
 session_id:Optional[str]=None
def chunks(text):
 text=" ".join(text.split()); out=[]; start=0
 while start<len(text):
  end=min(start+SIZE,len(text)); out.append(text[start:end])
  if end==len(text): break
  start=end-OVERLAP
 return out
@app.get("/health")
def health(): return {"status":"ok","version":app.version,"vector_store":"chroma"}
@app.get("/models")
def models(): return {"models":MODELS,"default":DEFAULT}
@app.post("/upload")
async def upload(files:list[UploadFile]=File(...)):
 results=[]
 for f in files:
  if not f.filename or not f.filename.lower().endswith(".pdf"): raise HTTPException(415,"Only PDF files are supported")
  data=await f.read()
  if not data.startswith(b"%PDF"): raise HTTPException(400,"Invalid PDF")
  if len(data)>30*1024*1024: raise HTTPException(413,"PDF exceeds 30 MB")
  doc_id=str(uuid.uuid4()); filename=Path(f.filename).name; path=UPLOADS/f"{doc_id}.pdf"; path.write_bytes(data)
  try:
   reader=PdfReader(str(path)); records=[]
   for page_no,page in enumerate(reader.pages,1):
    for ix,chunk in enumerate(chunks(page.extract_text() or "")): records.append((chunk,page_no,ix))
   if not records: raise ValueError("No extractable text. OCR is not implemented in this baseline.")
   collection.add(ids=[f"{doc_id}:{p}:{i}" for _,p,i in records],documents=[x[0] for x in records],metadatas=[{"doc_id":doc_id,"filename":filename,"page":p,"chunk_index":i} for _,p,i in records])
   results.append({"doc_id":doc_id,"filename":filename,"num_chunks":len(records),"status":"indexed"})
  except Exception as exc:
   path.unlink(missing_ok=True); raise HTTPException(422,f"Could not index {filename}: {exc}") from exc
 return {"documents":results}
@app.get("/documents")
def documents():
 raw=collection.get(include=["metadatas"]); grouped={}
 for m in raw.get("metadatas") or []:
  x=grouped.setdefault(m["doc_id"],{"doc_id":m["doc_id"],"filename":m["filename"],"num_chunks":0}); x["num_chunks"]+=1
 return {"documents":list(grouped.values())}
@app.delete("/documents/{doc_id}")
def delete_document(doc_id:str):
 found=collection.get(where={"doc_id":doc_id},include=["metadatas"])
 if not found.get("ids"): raise HTTPException(404,"Document not found")
 collection.delete(ids=found["ids"]); (UPLOADS/f"{doc_id}.pdf").unlink(missing_ok=True)
 return {"deleted":doc_id}
@app.post("/chat")
async def chat(req:ChatRequest):
 question=req.question.strip()
 if not question: raise HTTPException(422,"Question cannot be blank")
 model=req.model or DEFAULT
 if model not in MODELS: raise HTTPException(400,"Model is not configured")
 where={"doc_id":{"$in":req.doc_ids}} if req.doc_ids else None
 try: result=collection.query(query_texts=[question],n_results=5,where=where)
 except Exception as exc: raise HTTPException(503,f"Retrieval failed: {exc}") from exc
 docs=(result.get("documents") or [[]])[0]; metas=(result.get("metadatas") or [[]])[0]; ids=(result.get("ids") or [[]])[0]
 if not docs: return {"answer":"No relevant document content found. Upload a PDF first.","sources":[],"analytics":{"chunks_retrieved":0,"model":model}}
 context="\n\n".join(f"[{i+1}] {m['filename']} page {m['page']}: {d}" for i,(d,m) in enumerate(zip(docs,metas)))
 prompt=f"Answer only from the context. If missing, say so. Cite passages as [1], [2].\nCONTEXT:\n{context}\nQUESTION: {question}"
 try:
  async with httpx.AsyncClient(timeout=180) as h:
   response=await h.post(f"{OLLAMA}/api/generate",json={"model":model,"prompt":prompt,"stream":False}); response.raise_for_status(); answer=response.json().get("response","").strip()
 except httpx.HTTPError as exc: raise HTTPException(502,f"Ollama request failed: {exc}") from exc
 sources=[{"filename":m["filename"],"page":m["page"],"chunk_index":m["chunk_index"],"score":None,"snippet":d[:350],"chunk_id":cid} for d,m,cid in zip(docs,metas,ids)]
 return {"answer":answer,"sources":sources,"analytics":{"chunks_retrieved":len(docs),"model":model}}
@app.delete("/sessions/{session_id}")
def clear_session(session_id:str): return {"cleared":session_id}
static=Path("/app/static")
if static.exists(): app.mount("/",StaticFiles(directory=str(static),html=True),name="frontend")
