import os, io, uuid, sqlite3
from pathlib import Path
from datetime import datetime, timezone
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image

BASE = Path(__file__).resolve().parent
UPLOADS = BASE / "uploads"
UPLOADS.mkdir(exist_ok=True)
DB = BASE / "cura.sqlite3"
MAX_BYTES = 10 * 1024 * 1024
ALLOWED = {"image/jpeg", "image/png", "application/pdf"}
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_API_KEY = "AQ.Ab8RN6JEfy-eaR_qOPsqnMvzMdQ2-OKi-aDrL8dmKK3_DOrHzA"
MODEL = "gemini-3.5-flash-lite"
app = FastAPI(title="Cura Gemini OCR API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS scans (
            id TEXT PRIMARY KEY, filename TEXT NOT NULL, mime_type TEXT NOT NULL,
            stored_path TEXT NOT NULL, text TEXT NOT NULL, model TEXT NOT NULL,
            verified INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)""")
init_db()

@app.get("/health")
def health():
    return {"status":"ok", "service":"cura-gemini-ocr", "provider":"Google Gemini API",
            "model":MODEL, "api_key_configured":bool(os.getenv("GEMINI_API_KEY")),
            "database":"sqlite", "output_status":"UNVERIFIED"}

@app.post("/v1/ocr/handwriting")
async def ocr_handwriting(file: UploadFile = File(...)):
    mime = (file.content_type or "").lower()
    if mime not in ALLOWED:
        raise HTTPException(415, "Upload a PNG, JPEG, or PDF file.")
    raw = await file.read()
    if not raw or len(raw) > MAX_BYTES:
        raise HTTPException(413, "File is empty or exceeds the 10 MB limit.")
    if mime != "application/pdf":
        try:
            Image.open(io.BytesIO(raw)).verify()
        except Exception:
            raise HTTPException(415, "The uploaded image is invalid or unreadable.")
    api_key = GEMINI_API_KEY
    if not api_key:
        raise HTTPException(503, "GEMINI_API_KEY is not configured on the backend.")
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        prompt = ("Transcribe only the text visibly present in this prescription document. "
                  "Do not infer, autocorrect, normalize, or complete medicine names, numbers, "
                  "dosages, units, routes, frequencies, dates, or durations. Preserve the "
                  "document's reading order and line breaks. If any word, character, or number "
                  "is uncertain, write [unclear] at that location. Do not provide medical advice, "
                  "identify a medicine from context, or make clinical interpretations. Return "
                  "only a literal transcription. Include headings and handwritten annotations "
                  "when legible.")
        part = types.Part.from_bytes(data=raw, mime_type=mime)
        response = client.models.generate_content(model=MODEL, contents=[part, prompt])
        text = (response.text or "").strip()
        if not text:
            raise HTTPException(502, "Gemini returned an empty transcription.")
    except HTTPException:
        raise
    except Exception as exc:
        # Do not expose provider details, request payloads, or credentials to the browser.
        raise HTTPException(502, f"Gemini OCR request failed ({type(exc).__name__}).")

    scan_id = str(uuid.uuid4())
    ext = "pdf" if mime == "application/pdf" else ("png" if mime == "image/png" else "jpg")
    stored = UPLOADS / f"{scan_id}.{ext}"
    stored.write_bytes(raw)
    created = datetime.now(timezone.utc).isoformat()
    filename = Path(file.filename or f"prescription.{ext}").name[:160]
    with db() as con:
        con.execute("INSERT INTO scans VALUES(?,?,?,?,?,?,?,?)",
                    (scan_id, filename, mime, str(stored), text, MODEL, 0, created))
    lines = [{"text": line, "confidence": None} for line in text.splitlines() if line.strip()]
    return {"id":scan_id, "text":text, "lines":lines, "model":MODEL,
            "verified":False, "status":"UNVERIFIED", "created_at":created,
            "safety_note":"Machine transcription only. Verify every field against the original document with an authorized healthcare professional."}

@app.get("/api/scans")
def list_scans():
    with db() as con:
        rows = con.execute("SELECT id,filename,mime_type,text,model,verified,created_at FROM scans ORDER BY created_at DESC LIMIT 100").fetchall()
    return [dict(r) for r in rows]

@app.get("/")
def frontend():
    return FileResponse(BASE.parent / "frontend" / "index.html")
