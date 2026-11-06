import os, sqlite3, uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from PIL import Image
import io

BASE = Path(__file__).resolve().parent
UPLOADS = BASE / "uploads"
UPLOADS.mkdir(exist_ok=True)
DB = BASE / "cura.db"
MAX_BYTES = 10 * 1024 * 1024
app = FastAPI(title="Cura API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def connect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS scans (
            id TEXT PRIMARY KEY, filename TEXT NOT NULL, mime_type TEXT NOT NULL,
            stored_path TEXT NOT NULL, extracted_text TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT 'not-configured', status TEXT NOT NULL DEFAULT 'UNVERIFIED',
            created_at TEXT NOT NULL
        )""")
init_db()

def transcribe_with_gemini(raw: bytes, mime: str):
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return ("OCR provider not configured. Set GEMINI_API_KEY and restart the backend to enable transcription.", "not-configured")
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=key)
        prompt = (
            "Transcribe only text visibly present in this image. Do not infer or correct "
            "medication names, doses, units, routes, frequencies, or durations. Preserve "
            "line breaks. If a character or word cannot be read, write [unclear]. "
            "Do not provide medical advice or interpret the prescription. Return only "
            "the literal transcription."
        )
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=[types.Part.from_bytes(data=raw, mime_type=mime), prompt],
        )
        return (response.text or "[No transcription returned]", "Google Gemini API")
    except Exception as exc:
        return (f"OCR service error: {type(exc).__name__}. The source image was saved; transcription requires retry.", "Google Gemini API")

@app.get("/health")
def health():
    return {"status":"ok","service":"cura-api","database":"sqlite","ocr_provider":"Google Gemini API" if os.getenv("GEMINI_API_KEY") else "not-configured","safety":"all OCR output is unverified"}

@app.get("/api/scans")
def list_scans():
    with connect() as con:
        rows = con.execute("SELECT id,filename,extracted_text,model,status,created_at FROM scans ORDER BY created_at DESC LIMIT 100").fetchall()
    return [dict(r) for r in rows]

@app.post("/api/scans")
async def create_scan(file: UploadFile = File(...)):
    allowed = {"image/jpeg":"jpg","image/png":"png","image/webp":"webp"}
    if file.content_type not in allowed:
        raise HTTPException(415, "Upload a JPG, PNG, or WEBP image. PDF support is not included in this demo.")
    raw = await file.read()
    if not raw or len(raw) > MAX_BYTES:
        raise HTTPException(413, "Image is empty or exceeds the 10 MB limit.")
    try:
        Image.open(io.BytesIO(raw)).verify()
    except Exception:
        raise HTTPException(415, "The uploaded file is not a valid image.")
    scan_id = str(uuid.uuid4())
    safe_name = Path(file.filename or "prescription").name[:120]
    path = UPLOADS / f"{scan_id}.{allowed[file.content_type]}"
    path.write_bytes(raw)
    extracted, model = transcribe_with_gemini(raw, file.content_type)
    created = datetime.now(timezone.utc).isoformat()
    with connect() as con:
        con.execute("INSERT INTO scans(id,filename,mime_type,stored_path,extracted_text,model,status,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (scan_id,safe_name,file.content_type,str(path),extracted,model,"UNVERIFIED",created))
    return {"id":scan_id,"filename":safe_name,"extracted_text":extracted,"model":model,"status":"UNVERIFIED","verified":False,"created_at":created,
            "safety_note":"Machine transcription only. Verify against the original document with an authorized healthcare professional."}

@app.get("/")
def home():
    return FileResponse(BASE.parent / "frontend" / "index.html")
