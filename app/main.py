import base64
import json
import os
import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import LiveSettings, Settings, get_settings
from app.models.schemas import ApplyAnalysis, DownloadModel, EditTranscript, InputKind, StartAnalysis, UpdateSettings
from app.repositories.file_repository import FileJobRepository
from app.services.analysis_service import AnalysisService
from app.services.diarization_service import SpeakerJobs
from app.services.job_service import JobService
from app.services.media_service import AppError, MediaService
from app.services.settings_service import SettingsService
from app.services.transcript_service import TranscriptService


class LockedFileResponse(FileResponse):
    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.media_lock.release()


def create_app(settings: Settings | LiveSettings | None = None):
    settings = settings or get_settings()
    if isinstance(settings, Settings):
        settings = LiveSettings(settings)
    repo = FileJobRepository(settings.data_dir)
    media = MediaService(settings)
    jobs = JobService(repo, media, settings)
    transcripts = TranscriptService(repo)
    analysis = AnalysisService(repo, transcripts, settings)
    config = SettingsService(settings)
    speakers = SpeakerJobs(repo, transcripts, settings)
    app = FastAPI(title="VAJA AI (วาจา เอไอ) · Thai ASR", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.repo, app.state.settings = repo, settings
    if settings.app_env == "local":
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])

    @app.middleware("http")
    async def guard(request: Request, call_next):
        request.state.request_id = str(uuid4())
        if settings.api_token:
            try:
                scheme, value = request.headers.get("authorization", "").split(" ", 1)
                username, password = base64.b64decode(value, validate=True).decode().split(":", 1)
                valid = scheme.lower() == "basic" and username == "vaja" and secrets.compare_digest(password.encode(), settings.api_token.encode())
            except (ValueError, UnicodeError):
                valid = False
            if not valid:
                return JSONResponse({"code": "UNAUTHORIZED", "message": "Authentication required"}, status_code=401,
                                    headers={"WWW-Authenticate": 'Basic realm="VAJA AI", charset="UTF-8"'})
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            # Same-origin mutations; credentials cannot authorize cross-site forms.
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                return JSONResponse({"code": "ORIGIN_REJECTED", "message": "Cross-origin request rejected"}, status_code=403)
            if request.method in ("POST", "PUT"):
                try:
                    length = int(request.headers["content-length"])
                except (KeyError, ValueError):
                    return JSONResponse({"code": "LENGTH_REQUIRED", "message": "Content-Length required"}, status_code=411)
                limit = (settings.max_upload_mb + 1) * 1024**2 if request.url.path == "/api/jobs" else 8 * 1024**2
                if length < 0 or length > limit:
                    return JSONResponse({"code": "FILE_TOO_LARGE", "message": "Request exceeds size limit"}, status_code=413)
                receive = request._receive
                received = 0
                async def bounded_receive():
                    nonlocal received
                    message = await receive()
                    received += len(message.get("body", b""))
                    if received > limit:
                        raise AppError("FILE_TOO_LARGE", "Request exceeds size limit", 413)
                    return message
                request._receive = bounded_receive
        try:
            response = await call_next(request)
        except Exception:
            response = JSONResponse({"code": "INTERNAL_ERROR", "message": "เกิดข้อผิดพลาดภายในระบบ",
                                     "request_id": request.state.request_id}, status_code=500)
        response.headers.update({"X-Request-ID": request.state.request_id, "X-Content-Type-Options": "nosniff",
                                 "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                                 "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self' blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'"})
        return response

    @app.exception_handler(AppError)
    async def app_error(request, exc):
        return JSONResponse({"code": exc.code, "message": exc.message, "request_id": request.state.request_id}, status_code=exc.status)

    @app.exception_handler(FileNotFoundError)
    async def missing(request, exc):
        return JSONResponse({"code": "NOT_FOUND", "message": "ไม่พบงานหรือไฟล์", "request_id": request.state.request_id}, status_code=404)

    @app.exception_handler(ValueError)
    async def bad_id(request, exc):
        return JSONResponse({"code": "INVALID_REQUEST", "message": "ข้อมูลคำขอไม่ถูกต้อง", "request_id": request.state.request_id}, status_code=400)

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        return JSONResponse({"code": "INVALID_REQUEST", "message": "ตรวจสอบชนิดและขนาดข้อมูลที่ส่ง", "request_id": request.state.request_id}, status_code=422)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/system")
    def system():
        heartbeat, alive = None, False
        path = repo.data_dir / "worker.json"
        if path.exists():
            try:
                heartbeat = json.loads(path.read_text(encoding="utf-8"))
                alive = (datetime.now(timezone.utc) - datetime.fromisoformat(heartbeat["updated_at"])).total_seconds() < 15
            except (ValueError, KeyError, FileNotFoundError):
                pass
        return {"api": "ok", "worker_alive": alive, "worker": heartbeat, "model_id": settings.asr_model,
                "device": settings.asr_device, "compute_type": settings.asr_compute_type,
                "beam_size": settings.asr_beam_size, "batch_size": settings.asr_batch_size,
                "model_local_files_only": settings.model_local_files_only,
                "ffmpeg": bool(shutil.which("ffmpeg")), "ffprobe": bool(shutil.which("ffprobe")),
                "max_upload_mb": settings.max_upload_mb, "max_duration_seconds": settings.max_duration_seconds,
                "poll_seconds": settings.job_poll_seconds, "launcher": os.environ.get("VAJA_LAUNCHER") == "1"}

    @app.post("/api/shutdown", status_code=202)
    def shutdown():
        # Only when started by the desktop launcher, which watches this flag and stops API + worker.
        if os.environ.get("VAJA_LAUNCHER") != "1":
            raise AppError("NOT_LAUNCHER", "ปิดจากหน้าเว็บได้เฉพาะเมื่อเปิดผ่านไอคอน VAJA AI", 409)
        (repo.data_dir / "stop.flag").write_text("stop", encoding="utf-8")
        return {"status": "stopping"}

    @app.post("/api/jobs", status_code=202)
    def upload(file: Annotated[UploadFile, File()], title: Annotated[str, Form(max_length=200)] = "",
               input_kind: Annotated[InputKind, Form()] = "audio",
               call_id: Annotated[str, Form(max_length=200)] = "",
               source_system: Annotated[str, Form(max_length=200)] = "",
               recorded_at: Annotated[str, Form(max_length=100)] = ""):
        try:
            return jobs.create(file, title, input_kind,
                               dict(call_id=call_id or None, source_system=source_system or None, recorded_at=recorded_at or None))
        finally:
            file.file.close()

    @app.get("/api/jobs")
    def list_jobs():
        return repo.list_manifests()

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        return repo.load_manifest(job_id)

    @app.put("/api/jobs/{job_id}/track")
    def select_track(job_id: str, index: int = Query(ge=0)):
        return jobs.select_track(job_id, index)

    @app.post("/api/jobs/{job_id}/retry", status_code=202)
    def retry(job_id: str, index: int | None = Query(default=None, ge=0)):
        return jobs.retry(job_id, index)

    @app.delete("/api/jobs/{job_id}", status_code=202)
    def delete(job_id: str):
        return jobs.delete(job_id)

    @app.get("/api/jobs/{job_id}/transcript")
    def get_transcript(job_id: str):
        with repo.lock():
            return transcripts.get(job_id)

    @app.put("/api/jobs/{job_id}/transcript")
    def save_transcript(job_id: str, edit: EditTranscript):
        return transcripts.save(job_id, edit)

    @app.get("/api/settings")
    def get_config():
        return config.describe()

    @app.put("/api/settings")
    def update_config(body: UpdateSettings):
        return config.update(body.values, body.reset)

    @app.post("/api/settings/models/download", status_code=202)
    def download_model(body: DownloadModel):
        return config.download(body.name)

    @app.get("/api/jobs/{job_id}/speakers")
    def get_speakers(job_id: str):
        with repo.lock():
            return speakers.get(job_id)

    @app.post("/api/jobs/{job_id}/speakers", status_code=202)
    def start_speakers(job_id: str):
        return speakers.start(job_id)

    @app.get("/api/analysis/providers")
    def analysis_providers():
        return analysis.providers()

    @app.get("/api/jobs/{job_id}/analysis")
    def get_analysis(job_id: str):
        with repo.lock():
            return analysis.get(job_id)

    @app.post("/api/jobs/{job_id}/analysis", status_code=202)
    def start_analysis(job_id: str, body: StartAnalysis):
        return analysis.start(job_id, body.provider)

    @app.post("/api/jobs/{job_id}/analysis/apply")
    def apply_analysis(job_id: str, body: ApplyAnalysis):
        return analysis.apply(job_id, body.revision)

    @app.get("/api/jobs/{job_id}/export")
    def export(job_id: str, format: Literal["txt", "json", "srt", "vtt", "csv"] = "txt",
               version: Literal["original", "edited"] = "edited"):
        content, mime = transcripts.export(job_id, format, version)
        return Response(content.encode("utf-8"), media_type=f"{mime}; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{job_id}.{format}"'})

    @app.get("/api/jobs/{job_id}/media")
    async def playback(job_id: str, request: Request, audio: bool = False):
        # Hold a per-media lock through streaming so deletion cannot unlink an open file.
        lock = repo.lock(f"media-{job_id}" if len(job_id) == 36 and job_id.replace("-", "").isalnum() else "invalid-media")
        await run_in_threadpool(lock.acquire)
        try:
            job = await run_in_threadpool(repo.load_manifest, job_id)
            path = repo.path(job_id, "playback.wav" if audio else job["original_file"])
            if not path.exists():
                raise FileNotFoundError()
            # Starlette FileResponse supports HTTP Range, including browser seek.
            response = LockedFileResponse(path, filename=None, media_type="audio/wav" if audio else None)
            response.media_lock = lock
            return response
        except BaseException:
            lock.release()
            raise

    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/")
    def index():
        return FileResponse(static / "index.html")

    return app


app = create_app()
