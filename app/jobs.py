"""인메모리 잡 저장소 + 백그라운드 실행.

OCR은 blocking이라 ThreadPoolExecutor에서 돌리고, 세마포어로 동시 실행 수를 제한한다.
(MVP 한계: 재시작 시 잡 소멸·수평확장 불가 → 확장 시 Redis/Celery로 JobStore 교체.)
"""

from __future__ import annotations

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from .config import Settings
from .models import JobStatus
from .ocr import OCREngine, build_engine
from .pipeline import analyze_video
from .spellcheck import SpellChecker, build_checker


class JobStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._jobs: dict[str, JobStatus] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=settings.max_concurrent_jobs)
        self._semaphore = threading.Semaphore(settings.max_concurrent_jobs)
        self._engine: OCREngine | None = None
        self._checker: SpellChecker | None = None
        self._engine_lock = threading.Lock()

    # --- 엔진/체커 싱글턴 (모델 로드 1회) ---
    def _get_engine(self) -> OCREngine:
        with self._engine_lock:
            if self._engine is None:
                self._engine = build_engine(self.settings)
            return self._engine

    def _get_checker(self) -> SpellChecker:
        with self._engine_lock:
            if self._checker is None:
                self._checker = build_checker(
                    "hanspell",
                    max_retries=self.settings.spell_max_retries,
                    backoff_s=self.settings.spell_retry_backoff_s,
                )
            return self._checker

    def create(self) -> str:
        job_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._jobs[job_id] = JobStatus(
                job_id=job_id, status="queued", progress=0.0, message="대기 중"
            )
        return job_id

    def get(self, job_id: str) -> JobStatus | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _update(self, job_id: str, **fields) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for k, v in fields.items():
                setattr(job, k, v)

    def submit(
        self, job_id: str, video_path: str, thumb_dir: str, overrides: dict | None = None
    ) -> None:
        self._executor.submit(self._run, job_id, video_path, thumb_dir, overrides or {})

    def _run(
        self, job_id: str, video_path: str, thumb_dir: str, overrides: dict
    ) -> None:
        with self._semaphore:
            self._update(job_id, status="running", message="처리 시작")

            def progress(p: float, msg: str) -> None:
                self._update(job_id, progress=round(p, 3), message=msg)

            try:
                engine = self._get_engine()
                checker = self._get_checker()
                job_settings = (
                    self.settings.model_copy(update=overrides) if overrides else self.settings
                )
                result = analyze_video(
                    video_path,
                    engine,
                    checker,
                    job_settings,
                    thumb_dir,
                    progress_cb=progress,
                )
                self._update(
                    job_id,
                    status="done",
                    progress=1.0,
                    message="완료",
                    result=result,
                )
            except Exception as exc:  # noqa: BLE001 - 사용자에게 오류 노출
                self._update(
                    job_id, status="error", message="오류", error=str(exc)
                )
            finally:
                # 업로드 원본 정리 (썸네일은 결과 조회 위해 유지)
                try:
                    if os.path.exists(video_path):
                        os.remove(video_path)
                except OSError:
                    pass
