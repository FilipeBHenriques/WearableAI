import os
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from database import init_db
from paths import ASSETS_DIR, DIST_DIR
from models import NoteStatus
from schemas import LocationResponse, NoteDetailResponse, NoteResponse, NoteStatusInput, TextInput
from services import capture_service, location_service, model_service, note_service, recurrence_service, recording_service

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


NoteQueryStatus = Literal["active", "done", "all"]


def _serialize_note_tree(note_id: int, status: NoteStatus | None = None):
    note = note_service.get_by_id(note_id)
    if note is None:
        return None

    return _serialize_note(note, status)


def _serialize_note(note, status: NoteStatus | None = None):
    return {
        "id": note.id,
        "text": note.text,
        "category": note.category,
        "created_at": note.created_at,
        "status": note.status,
        "parent_note_id": note.parent_note_id,
        "deadline_at": note.deadline_at,
        "importance_score": note.importance_score,
        "urgency_score": note.urgency_score,
        "rank_score": note.rank_score,
        "urgency_reason": note.urgency_reason,
        "location_id": note.location_id,
        "location_name": note.location_name,
        "location_latitude": note.location_latitude,
        "location_longitude": note.location_longitude,
        "repeat_cycle": note.repeat_cycle,
        "repeat_days": note.repeat_days,
        "repeat_months": note.repeat_months,
        "repeat_time": note.repeat_time,
        "is_repeating": recurrence_service.is_repeating(note),
        "is_due_today": recurrence_service.is_due_on(note),
        "completed_today": recurrence_service.completed_on(note),
        "repeat_display": recurrence_service.repeat_display(note),
        "subnotes": [
            _serialize_note_tree(subnote.id, status)
            for subnote in note_service.get_subnotes(note.id, status)
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
def api_notes(status: NoteQueryStatus | None = None):
    note_status: NoteStatus | None = None if status in (None, "all") else status
    notes = note_service.get_all(note_status)
    return [_serialize_note_tree(note.id, note_status) for note in notes]


@app.get("/api/repeats/today")
def api_today_repeats():
    return [_serialize_note(note) for note in note_service.get_today_repeats()]


@app.get("/api/locations", response_model=list[LocationResponse])
def api_locations():
    return location_service.get_locations()


@app.delete("/api/locations/{location_id}")
def api_delete_location(location_id: int):
    deleted = location_service.delete_saved_location(location_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Location not found")
    return {"deleted": location_id}


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


@app.patch("/api/notes/{note_id}/status")
def api_mark_note_status(note_id: int, body: NoteStatusInput):
    note = note_service.get_by_id(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")

    note_service.mark_note_as(note_id, body.status)
    updated = note_service.get_by_id(note_id)
    return {"id": note_id, "status": updated.status if updated else body.status}


@app.post("/api/notes/{note_id}/toggle-status")
def api_toggle_note_status(note_id: int):
    status = note_service.toggle_note_status(note_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"id": note_id, "status": status}


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
