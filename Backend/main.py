"""
VoiceForge backend
-------------------
A small FastAPI service that wraps Coqui's XTTS v2 model to provide
voice cloning + text-to-speech over a simple REST API.

Endpoints
---------
GET    /api/voices                 -> list cloned voices
POST   /api/voices                 -> register a new voice (multipart: name, file)
DELETE /api/voices/{voice_id}      -> remove a cloned voice
POST   /api/synthesize             -> generate speech in a cloned voice
GET    /api/outputs/{filename}     -> download/stream a generated clip
GET    /api/health                 -> readiness probe (reports if the model is loaded)

Run with:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import uuid
import json
import shutil
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from voice_engine import VoiceEngine

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
VOICES_DIR = STORAGE_DIR / "voices"
OUTPUTS_DIR = STORAGE_DIR / "outputs"
REGISTRY_PATH = STORAGE_DIR / "voices.json"

VOICES_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm"}
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB reference sample cap

app = FastAPI(title="VoiceForge", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this to your frontend's origin in production
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = VoiceEngine()


# ---------------------------------------------------------------------------
# Persistence helpers — a tiny JSON registry is plenty for a self-hosted app.
# Swap this for a real database if you need multi-user accounts.
# ---------------------------------------------------------------------------

def _load_registry() -> dict:
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text())
    return {}


def _save_registry(registry: dict) -> None:
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2))


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class VoiceOut(BaseModel):
    id: str
    name: str
    created_at: Optional[str] = None


class SynthesizeRequest(BaseModel):
    voice_id: str
    text: str
    language: str = "en"
    speed: float = 1.0


class SynthesizeResponse(BaseModel):
    filename: str
    url: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok", "model_loaded": engine.is_loaded()}


@app.get("/api/voices", response_model=List[VoiceOut])
def list_voices():
    registry = _load_registry()
    return [VoiceOut(id=vid, **meta) for vid, meta in registry.items()]


@app.post("/api/voices", response_model=VoiceOut)
async def create_voice(name: str = Form(...), file: UploadFile = File(...)):
    """
    Register a new cloned voice from a short reference recording.

    IMPORTANT — consent: only upload a recording of your own voice, or one
    you have explicit, verifiable permission to clone. This endpoint does
    not verify consent on its own; that responsibility sits with whoever
    deploys and uses this app. See README.md for suggested safeguards.
    """
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(ALLOWED_AUDIO_EXTENSIONS)}",
        )

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Reference audio is too large (25 MB max).")
    if len(contents) < 10_000:
        raise HTTPException(
            status_code=400,
            detail="Reference audio is too short — use at least a few seconds of clear speech.",
        )

    voice_id = uuid.uuid4().hex[:12]
    dest = VOICES_DIR / f"{voice_id}{ext}"
    dest.write_bytes(contents)

    import datetime

    registry = _load_registry()
    registry[voice_id] = {
        "name": name.strip() or "Untitled voice",
        "created_at": datetime.datetime.utcnow().isoformat() + "Z",
        "sample_path": str(dest),
    }
    _save_registry(registry)

    return VoiceOut(id=voice_id, name=registry[voice_id]["name"], created_at=registry[voice_id]["created_at"])


@app.delete("/api/voices/{voice_id}")
def delete_voice(voice_id: str):
    registry = _load_registry()
    meta = registry.pop(voice_id, None)
    if meta is None:
        raise HTTPException(status_code=404, detail="Voice not found")
    sample_path = Path(meta["sample_path"])
    if sample_path.exists():
        sample_path.unlink()
    _save_registry(registry)
    return {"ok": True}


@app.post("/api/synthesize", response_model=SynthesizeResponse)
def synthesize(req: SynthesizeRequest):
    registry = _load_registry()
    meta = registry.get(req.voice_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Voice not found")

    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is empty")
    if len(text) > 2000:
        raise HTTPException(status_code=400, detail="Text is too long (2000 character max per request)")

    out_name = f"{uuid.uuid4().hex[:12]}.wav"
    out_path = OUTPUTS_DIR / out_name

    try:
        engine.synthesize(
            text=text,
            speaker_wav=meta["sample_path"],
            language=req.language,
            speed=req.speed,
            out_path=str(out_path),
        )
    except Exception as exc:  # surface model errors as a clean 500 instead of a stack trace
        raise HTTPException(status_code=500, detail=f"Synthesis failed: {exc}") from exc

    return SynthesizeResponse(filename=out_name, url=f"/api/outputs/{out_name}")


@app.get("/api/outputs/{filename}")
def get_output(filename: str):
    path = OUTPUTS_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, media_type="audio/wav")
