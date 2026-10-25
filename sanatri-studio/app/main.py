"""Sanatri Studio — script → Legends of Bharat episode → download."""
from __future__ import annotations

import json
import os
import sys
import threading
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.job import run_job  # noqa: E402
from pipeline.script_parser import parse_script, validate_parsed  # noqa: E402

# On Vercel, local disk is ephemeral /tmp; prefer a dedicated worker for generate.
_ON_VERCEL = bool(os.environ.get("VERCEL"))
_WORKER = (os.environ.get("SANATRI_WORKER_URL") or "").rstrip("/")
_DATA_ROOT = Path(os.environ.get("SANATRI_DATA_DIR") or (
    "/tmp/sanatri-studio/jobs" if _ON_VERCEL else str(ROOT / "data" / "jobs")
))
DATA = _DATA_ROOT
DATA.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Sanatri Studio", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


class GenerateRequest(BaseModel):
    script: str = Field(min_length=20)


def _proxy_json(method: str, path: str, body: dict | None = None) -> dict:
    if not _WORKER:
        raise HTTPException(
            503,
            "Video generation needs a persistent worker (FFmpeg + multi-minute jobs). "
            "Set SANATRI_WORKER_URL to your Sanatri Studio host, or run the app on a VM.",
        )
    url = f"{_WORKER}{path}"
    try:
        with httpx.Client(timeout=60.0) as client:
            if method == "POST":
                r = client.post(url, json=body)
            else:
                r = client.get(url)
            if r.status_code >= 400:
                raise HTTPException(r.status_code, r.text)
            return r.json()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Worker unreachable at {_WORKER}: {exc}") from exc


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    html = (Path(__file__).parent / "templates" / "index.html").read_text()
    return HTMLResponse(html)


@app.post("/api/parse")
def api_parse(body: GenerateRequest) -> dict:
    parsed = parse_script(body.script)
    try:
        validate_parsed(parsed)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return parsed.to_dict()


@app.post("/api/generate")
def api_generate(body: GenerateRequest) -> dict:
    # Serverless Vercel cannot run FFmpeg + long jobs locally — proxy when configured.
    if _ON_VERCEL or _WORKER:
        return _proxy_json("POST", "/api/generate", {"script": body.script})

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
    if _ON_VERCEL or _WORKER:
        return _proxy_json("GET", f"/api/status/{job_id}")

    path = DATA / job_id / "status.json"
    if not path.exists():
        raise HTTPException(404, "Job not found")
    return json.loads(path.read_text())


@app.get("/download/{job_id}/{kind}")
def download(job_id: str, kind: str):
    # Redirect to worker so large MP4s bypass Vercel response-size limits.
    if _ON_VERCEL or _WORKER:
        if not _WORKER:
            raise HTTPException(503, "SANATRI_WORKER_URL is not configured")
        return RedirectResponse(
            url=f"{_WORKER}/download/{job_id}/{kind}",
            status_code=307,
        )

    job_dir = DATA / job_id
    mapping = {
        "phone": (job_dir / "out" / "episode-phone.mp4", "jalandhara-or-episode-phone.mp4", "video/mp4"),
        "full": (job_dir / "out" / "episode.mp4", "episode-full.mp4", "video/mp4"),
        "srt": (job_dir / "out" / "episode.srt", "episode.srt", "text/plain"),
        "script": (job_dir / "script.txt", "script.txt", "text/plain"),
    }
    if kind == "phone":
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
    return {
        "ok": True,
        "app": "Sanatri Studio",
        "vercel": _ON_VERCEL,
        "worker": _WORKER or None,
    }
