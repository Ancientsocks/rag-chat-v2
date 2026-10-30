from fastapi.testclient import TestClient
import main
client=TestClient(main.app)
def test_health():
 r=client.get("/health"); assert r.status_code==200 and r.json()["status"]=="ok"
def test_models():
 r=client.get("/models"); assert r.status_code==200 and r.json()["default"] in r.json()["models"]
def test_reject_non_pdf():
 r=client.post("/upload",files=[("files",("a.txt",b"hello","text/plain"))]); assert r.status_code==415
def test_reject_invalid_pdf():
 r=client.post("/upload",files=[("files",("bad.pdf",b"not pdf","application/pdf"))]); assert r.status_code==400
def test_blank_question():
 r=client.post("/chat",json={"question":"   "}); assert r.status_code==422
