"""FastAPI 앱 — 업로드·백그라운드 잡·폴링·정적 프론트 서빙."""

from __future__ import annotations

import os
import shutil

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .jobs import JobStore
from .models import JobStatus

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
UPLOAD_DIR = os.path.join(BASE_DIR, settings.upload_dir)
THUMB_ROOT = os.path.join(UPLOAD_DIR, "thumbs")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(THUMB_ROOT, exist_ok=True)

app = FastAPI(title="자막 오타 검수 보조 도구", version="0.1.0")
store = JobStore(settings)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "ocr_engine": settings.ocr_engine}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.post("/analyze")
async def analyze(file: UploadFile) -> JSONResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="파일이 없습니다.")

    job_id = store.create()
    dest = os.path.join(UPLOAD_DIR, f"{job_id}_{os.path.basename(file.filename)}")

    size = 0
    limit = settings.max_upload_mb * 1024 * 1024
    with open(dest, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                out.close()
                os.remove(dest)
                raise HTTPException(
                    status_code=413,
                    detail=f"파일이 너무 큽니다(최대 {settings.max_upload_mb}MB).",
                )
            out.write(chunk)

    thumb_dir = os.path.join(THUMB_ROOT, job_id)
    store.submit(job_id, dest, thumb_dir)
    return JSONResponse(status_code=202, content={"job_id": job_id})


@app.get("/jobs/{job_id}", response_model=JobStatus)
def job_status(job_id: str) -> JobStatus:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="잡을 찾을 수 없습니다.")
    return job


@app.get("/jobs/{job_id}/thumbs/{name}")
def thumb(job_id: str, name: str) -> FileResponse:
    # 경로 탈출 방지
    safe = os.path.basename(name)
    path = os.path.join(THUMB_ROOT, job_id, safe)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="썸네일 없음")
    return FileResponse(path)


# 정적 프론트 자산
if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
