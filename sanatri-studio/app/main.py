"""Sanatri Studio — script → Legends of Bharat episode → download."""
from __future__ import annotations

import json
import sys
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.job import run_job  # noqa: E402
from pipeline.script_parser import parse_script  # noqa: E402

DATA = ROOT / "data" / "jobs"
DATA.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Sanatri Studio", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


class GenerateRequest(BaseModel):
    script: str = Field(min_length=20)


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    html = (Path(__file__).parent / "templates" / "index.html").read_text()
    return HTMLResponse(html)


@app.post("/api/parse")
def api_parse(body: GenerateRequest) -> dict:
    parsed = parse_script(body.script)
    return parsed.to_dict()


@app.post("/api/generate")
def api_generate(body: GenerateRequest) -> dict:
    job_id = uuid.uuid4().hex[:12]
    job_dir = DATA / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "status.json").write_text(
        json.dumps({"percent": 1, "message": "Queued…", "state": "running"})
    )

    def worker() -> None:
        try:
            run_job(job_dir, body.script)
        except Exception:
            pass  # status.json already written

    threading.Thread(target=worker, daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
def api_status(job_id: str) -> dict:
    path = DATA / job_id / "status.json"
    if not path.exists():
        raise HTTPException(404, "Job not found")
    return json.loads(path.read_text())


@app.get("/download/{job_id}/{kind}")
def download(job_id: str, kind: str) -> FileResponse:
    job_dir = DATA / job_id
    mapping = {
        "phone": (job_dir / "out" / "episode-phone.mp4", "jalandhara-or-episode-phone.mp4", "video/mp4"),
        "full": (job_dir / "out" / "episode.mp4", "episode-full.mp4", "video/mp4"),
        "srt": (job_dir / "out" / "episode.srt", "episode.srt", "text/plain"),
        "script": (job_dir / "script.txt", "script.txt", "text/plain"),
    }
    if kind == "phone":
        # Prefer a friendly name from result title
        result = job_dir / "result.json"
        name = "sanatri-episode-phone.mp4"
        if result.exists():
            title = json.loads(result.read_text()).get("title", "episode")
            safe = "".join(c if c.isalnum() or c in "-_ " else "" for c in title)[:40].strip().replace(" ", "-")
            name = f"{safe or 'sanatri-episode'}-narration.mp4"
        mapping["phone"] = (job_dir / "out" / "episode-phone.mp4", name, "video/mp4")

    if kind not in mapping:
        raise HTTPException(404, "Unknown download kind")
    path, filename, media = mapping[kind]
    if not path.exists():
        raise HTTPException(404, "File not ready")
    return FileResponse(
        path,
        media_type=media,
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/health")
def health() -> dict:
    return {"ok": True, "app": "Sanatri Studio"}
