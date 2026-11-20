import hashlib
import shutil
from pathlib import Path
from uuid import uuid4
from filelock import Timeout

from app.repositories.file_repository import utcnow
from app.services.media_service import AppError

EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".webm", ".mp4", ".avi", ".mov", ".mkv"}


class JobService:
    def __init__(self, repo, media, settings):
        self.repo, self.media, self.settings = repo, media, settings

    def check_disk(self, additional=0):
        used = sum(p.stat().st_size for p in self.repo.jobs.rglob("*") if p.is_file() and not p.is_symlink())
        if used + additional > self.settings.disk_quota_mb * 1024**2:
            raise AppError("DISK_QUOTA", "พื้นที่จัดเก็บงานเต็ม กรุณาลบงานเก่า", 507)
        if shutil.disk_usage(self.repo.data_dir).free < additional + self.settings.min_free_disk_mb * 1024**2:
            raise AppError("DISK_FULL", "พื้นที่ว่างในดิสก์ไม่เพียงพอ", 507)

    def create(self, upload, title, input_kind, metadata):
        name = (upload.filename or "recording.webm").replace("\\", "/").split("/")[-1][:255]
        ext = Path(name).suffix.lower()
        if ext not in EXTENSIONS:
            raise AppError("UNSUPPORTED_EXTENSION", "นามสกุลไฟล์ไม่รองรับ")
        job_id = str(uuid4())
        # Serialize admission so concurrent uploads cannot bypass the disk quota.
        with self.repo.lock("upload", timeout=600):
            self.check_disk()
            directory = self.repo.create_job_dir(job_id)
            try:
                source = directory / ("original" + ext)
                count, digest = 0, hashlib.sha256()
                with source.open("xb") as out:
                    while chunk := upload.file.read(1024 * 1024):
                        count += len(chunk)
                        if count > self.settings.max_upload_mb * 1024**2:
                            raise AppError("FILE_TOO_LARGE", "ไฟล์ใหญ่เกินขีดจำกัด", 413)
                        self.check_disk(len(chunk))
                        out.write(chunk)
                        digest.update(chunk)
                probe = self.media.probe(source)
                formats = set(probe["format_name"].split(","))
                if "mov" in formats:
                    validated_ext = ".mp4" if probe["has_video"] else ".m4a"
                elif "matroska" in formats:
                    validated_ext = ".webm" if ext == ".webm" else ".mkv"
                else:
                    validated_ext = next(("." + f for f in ("wav", "mp3", "flac", "ogg", "avi") if f in formats), ext)
                validated_source = directory / ("original" + validated_ext)
                if source != validated_source:
                    source.rename(validated_source)
                    source = validated_source
                if any(s.get("channels", 1) > 8 for s in probe["audio_streams"]):
                    raise AppError("CHANNEL_LIMIT", "MVP รองรับไม่เกิน 8 channels ต่อ track")
                track = probe["audio_streams"][0]
                now = utcnow()
                manifest = dict(schema_version=1, job_id=job_id, title=title.strip() or name,
                                input_kind=input_kind, original_filename=name, original_file=source.name,
                                media_type="video" if probe["has_video"] else "audio", size_bytes=count,
                                sha256=digest.hexdigest(), **probe, **metadata,
                                audio_stream_index=track["index"], channels=track.get("channels"),
                                status="queued", stage="awaiting_track" if len(probe["audio_streams"]) > 1 else "queued", attempt=0, model_id=self.settings.asr_model,
                                language=self.settings.asr_language, created_at=now, updated_at=now,
                                error_code=None, error_message=None, delete_requested=False)
                with self.repo.lock():
                    self.repo.save_manifest(job_id, manifest)
                return manifest
            except BaseException:
                self.repo.delete_job(job_id)
                raise

    def retry(self, job_id, index=None):
        with self.repo.lock():
            job = self.repo.load_manifest(job_id)
            if job["status"] != "failed":
                raise AppError("INVALID_STATE", "Retry ใช้ได้เฉพาะงานที่ล้มเหลว", 409)
            self._select(job, index)
            job.update(status="queued", stage="queued", progress=None, error_code=None, error_message=None, updated_at=utcnow())
            self.repo.save_manifest(job_id, job)
            return job

    def select_track(self, job_id, index):
        with self.repo.lock():
            job = self.repo.load_manifest(job_id)
            if job["status"] != "queued":
                raise AppError("INVALID_STATE", "เลือก track ได้เฉพาะงานที่ยังอยู่ในคิว", 409)
            self._select(job, index)
            job.update(stage="queued", updated_at=utcnow())
            self.repo.save_manifest(job_id, job)
            return job

    @staticmethod
    def _select(job, index):
        if index is None:
            return
        track = next((s for s in job["audio_streams"] if s["index"] == index), None)
        if track is None:
            raise AppError("INVALID_TRACK", "ไม่พบ audio track ที่เลือก")
        job.update(audio_stream_index=index, channels=track.get("channels"), track_explicit=True)

    def delete(self, job_id):
        with self.repo.lock():
            job = self.repo.load_manifest(job_id)
            if job["status"] == "processing":
                job.update(delete_requested=True, updated_at=utcnow())
                self.repo.save_manifest(job_id, job)
                return {"deferred": True}
            try:
                with self.repo.lock(f"media-{job_id}", timeout=0):
                    self.repo.delete_job(job_id)
            except Timeout:
                raise AppError("MEDIA_BUSY", "กำลังเล่นหรือดาวน์โหลดไฟล์ กรุณาหยุดเล่นแล้วลองลบอีกครั้ง", 409)
            return {"deferred": False}
