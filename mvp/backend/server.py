import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from database import init_db
from paths import ASSETS_DIR, DIST_DIR
from schemas import NoteDetailResponse, NoteResponse, TextInput
from services import capture_service, model_service, note_service, recording_service

app = FastAPI()
init_db()


@app.on_event("startup")
def startup() -> None:
    print(f"[backend] cwd={os.getcwd()}")
    print(f"[backend] dist={DIST_DIR} (exists={DIST_DIR.is_dir()})")
    if ASSETS_DIR.is_dir():
        print(f"[backend] serving /assets from {ASSETS_DIR}")
    model_service.warm_up_all()


if ASSETS_DIR.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=str(ASSETS_DIR)),
        name="assets",
    )


@app.get("/api/health")
def api_health():
    return model_service.get_status()


def _serialize_note_tree(note_id: int):
    note = note_service.get_by_id(note_id)
    if note is None:
        return None

    return {
        "id": note.id,
        "text": note.text,
        "category": note.category,
        "created_at": note.created_at,
        "parent_note_id": note.parent_note_id,
        "subnotes": [
            _serialize_note_tree(subnote.id)
            for subnote in note_service.get_subnotes(note_id)
        ],
    }


@app.get("/", response_class=HTMLResponse)
def index():
    dist_index = DIST_DIR / "index.html"
    if dist_index.is_file():
        return dist_index.read_text(encoding="utf-8")
    return HTMLResponse(
        "<h2>Run <code>cd frontend && npm run build</code> to serve the UI.</h2>"
    )


@app.get("/api/notes")
def api_notes():
    notes = note_service.get_all()
    return [_serialize_note_tree(note.id) for note in notes]


@app.get("/api/notes/{note_id}")
def api_get_note(note_id: int):
    note_tree = _serialize_note_tree(note_id)
    if note_tree is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note_tree


@app.delete("/api/notes/{note_id}")
def api_delete_note(note_id: int):
    note_service.delete(note_id)
    return {"deleted": note_id}


@app.post("/api/record/start")
def api_record_start():
    recording_service.start_recording()
    return {"status": "recording"}


@app.post("/api/record/stop")
def api_record_stop():
    return capture_service.stop_and_save()


@app.post("/api/text")
def api_text(body: TextInput):
    return capture_service.process_text(body.text)


@app.get("/{full_path:path}", response_class=HTMLResponse)
def spa_fallback(full_path: str):
    if full_path.startswith("api/") or full_path == "api":
        raise HTTPException(status_code=404, detail="Not found")

    dist_index = DIST_DIR / "index.html"
    if dist_index.is_file():
        return dist_index.read_text(encoding="utf-8")
    return HTMLResponse("<h2>Run <code>cd frontend && npm run build</code> first.</h2>")
