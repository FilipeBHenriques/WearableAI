import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from database import init_db
from schemas import TextInput
from services import capture_service, note_service, recording_service

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, "..", "frontend", "dist")

app = FastAPI()
init_db()

if os.path.isdir(DIST_DIR):
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(DIST_DIR, "assets")),
        name="assets",
    )


# ── Pages ──────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index():
    dist_index = os.path.join(DIST_DIR, "index.html")
    if os.path.exists(dist_index):
        with open(dist_index, encoding="utf-8") as f:
            return f.read()
    return HTMLResponse(
        "<h2>Run <code>cd frontend && npm run build</code> to serve the UI.</h2>"
    )


# ── Notes ──────────────────────────────────────────────────────────────────────

@app.get("/api/notes")
def api_notes():
    notes = note_service.get_all()
    return [
        {"id": n.id, "text": n.text, "category": n.category, "created_at": n.created_at}
        for n in notes
    ]


@app.get("/api/notes/{note_id}")
def api_get_note(note_id: int):
    note = note_service.get_by_id(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"id": note.id, "text": note.text, "category": note.category, "created_at": note.created_at}


@app.delete("/api/notes/{note_id}")
def api_delete_note(note_id: int):
    note_service.delete(note_id)
    return {"deleted": note_id}


# ── Recording ──────────────────────────────────────────────────────────────────

@app.post("/api/record/start")
def api_record_start():
    recording_service.start_recording()
    return {"status": "recording"}


@app.post("/api/record/stop")
def api_record_stop():
    return capture_service.stop_and_save()


# ── Text input ─────────────────────────────────────────────────────────────────

@app.post("/api/text")
def api_text(body: TextInput):
    return capture_service.process_text(body.text)


# ── SPA fallback (serves index.html for any non-API route in production) ───────

@app.get("/{full_path:path}", response_class=HTMLResponse)
def spa_fallback(full_path: str):
    dist_index = os.path.join(DIST_DIR, "index.html")
    if os.path.exists(dist_index):
        with open(dist_index, encoding="utf-8") as f:
            return f.read()
    return HTMLResponse("<h2>Run <code>cd frontend && npm run build</code> first.</h2>")
