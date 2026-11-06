# Cura — Presentation Package

A small hackathon prototype for prescription capture and medication continuity.

## Contents
- `frontend/index.html` — responsive browser UI
- `backend/main.py` — FastAPI backend
- `backend/cura.db` — created automatically on first run (SQLite)
- `backend/uploads/` — uploaded image files
- `backend/requirements.txt` — Python dependencies

## Run on macOS

Open Terminal and run:

```bash
cd ~/Downloads/Cura-Presentation-Package/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional: enable image transcription with Google Gemini:
1. Create an API key at https://aistudio.google.com/apikey
2. Set it in the same Terminal session:

```bash
export GEMINI_API_KEY='YOUR_API_KEY'
```

Start the server:

```bash
uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

Open `http://127.0.0.1:8001/` for the UI and `http://127.0.0.1:8001/health` for status.

If no API key is configured, the app still accepts and stores the image and clearly reports that OCR is not configured. It does not fabricate a transcription.

## Database
SQLite is initialized automatically at `backend/cura.db`. Each scan stores a UUID, original filename, MIME type, local image path, raw transcription, OCR provider, status, and timestamp.

## Important demo limitations
- Image uploads only: JPG, PNG, WEBP; 10 MB maximum.
- PDF upload and multi-word page segmentation are not implemented.
- OCR text is always `UNVERIFIED`; this app does not create medication orders or recommend treatment.
- The Gemini prompt requests literal transcription only and asks the model to mark uncertain text `[unclear]`. OCR can still be wrong.
- Use synthetic/demo data only. Do not upload real patient records without appropriate privacy, consent, and security controls.
- This is a hackathon prototype, not a production medical system.
