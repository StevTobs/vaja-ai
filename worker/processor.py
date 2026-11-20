import multiprocessing as mp
import os
import shutil
import threading
import time
from pathlib import Path

from app.config import snapshot
from app.repositories.file_repository import FileJobRepository, atomic_json, utcnow
from app.services.diarization_service import DiarizationService
from app.services.job_service import JobService
from app.services.media_service import AppError, MediaService


def inference_process(connection, settings):
    # Reap an orphaned native inference process after a hard parent crash.
    parent = mp.parent_process()
    def monitor_parent():
        while parent is not None and parent.is_alive():
            time.sleep(0.5)
        os._exit(1)
    threading.Thread(target=monitor_parent, daemon=True).start()
    repo = FileJobRepository(settings.data_dir)
    with repo.lock("inference", timeout=30):
        if parent is not None and not parent.is_alive():
            return
        inference_loop(connection, settings)


def inference_loop(connection, settings):
    engine = None
    while True:
        try:
            path, language = connection.recv()
        except EOFError:
            break
        try:
            if engine is None:
                connection.send(("progress", {"stage": "loading_model"}))
                from app.asr.faster_whisper_engine import FasterWhisperEngine
                engine = FasterWhisperEngine(settings)
            connection.send(("progress", {"stage": "transcribing"}))
            result = engine.transcribe(path, language, on_progress=lambda data: connection.send(("progress", data)))
            connection.send(("result", result))
        except Exception as exc:
            code = "RESOURCE_EXHAUSTED" if isinstance(exc, MemoryError) else "TRANSCRIPTION_FAILED"
            connection.send(("error", code))


class ModelProcess:
    """Persistent inference child: terminate on deadline without losing worker heartbeat."""
    def __init__(self, settings):
        self.settings, self.process, self.connection, self.loaded = settings, None, None, None

    @staticmethod
    def model_key(cfg):
        # Everything the child reads; a change from the settings UI restarts it on the next job.
        return tuple(sorted((k, v) for k, v in cfg.model_dump().items() if k.startswith(("asr_", "model_"))))

    def close(self):
        if self.process:
            self.process.terminate()
            self.process.join(10)
            if self.process.is_alive():
                self.process.kill()
                self.process.join()
        if self.connection:
            self.connection.close()
        self.process, self.connection = None, None

    def transcribe(self, path, language, heartbeat):
        cfg = snapshot(self.settings)
        if self.process and self.process.is_alive() and self.loaded != self.model_key(cfg):
            self.close()
        if not self.process or not self.process.is_alive():
            self.close()
            context = mp.get_context("spawn")
            self.connection, child = context.Pipe()
            self.process = context.Process(target=inference_process, args=(child, cfg), daemon=True)
            self.process.start()
            self.loaded = self.model_key(cfg)
            child.close()
        self.connection.send((str(path), language))
        deadline = time.monotonic() + cfg.asr_timeout_seconds
        while True:
            heartbeat()
            if time.monotonic() > deadline:
                self.close()
                raise AppError("ASR_TIMEOUT", "ถอดเสียงเกินเวลาที่กำหนด", 500)
            if self.connection.poll(1):
                try:
                    kind, result = self.connection.recv()
                except EOFError:
                    raise AppError("ASR_PROCESS_EXITED", "โปรเซสโมเดลหยุดทำงาน", 500)
                if kind == "progress":
                    heartbeat(result)
                    continue
                if kind == "error":
                    raise AppError(result, "โหลดโมเดลหรือถอดเสียงไม่สำเร็จ ตรวจสอบ model cache และการตั้งค่า", 500)
                return result
            if not self.process.is_alive():
                self.close()
                raise AppError("ASR_PROCESS_EXITED", "โปรเซสโมเดลหยุดทำงาน อาจมีหน่วยความจำไม่เพียงพอ", 500)


class Worker:
    def __init__(self, settings, engine=None):
        self.settings = settings
        self.repo = FileJobRepository(settings.data_dir)
        self.media = MediaService(settings)
        self.jobs = JobService(self.repo, self.media, settings)
        self.engine = engine or ModelProcess(settings)
        self.diarization = DiarizationService(settings)
        self.current_job = None

    def heartbeat(self, progress=None):
        if progress is not None and self.current_job:
            with self.repo.lock():
                job = self.repo.load_manifest(self.current_job)
                if progress.get("stage") in ("loading_model", "transcribing"):
                    job["stage"] = progress["stage"]
                if "processed_seconds" in progress:
                    measured = job.get("progress") or {}
                    total = measured.get("total_seconds", job["duration_seconds"])
                    measured.update(processed_seconds=min(total, max(measured.get("processed_seconds", 0), progress["processed_seconds"])),
                                    segments_completed=max(measured.get("segments_completed", 0), progress["segments_completed"]))
                    job["progress"] = measured
                job["updated_at"] = utcnow()
                self.repo.save_manifest(self.current_job, job)
        atomic_json(self.repo.data_dir / "worker.json", {"updated_at": utcnow(), "job_id": self.current_job,
                    "model_id": self.settings.asr_model, "device": self.settings.asr_device})

    def recover(self):
        # Call only while holding the singleton OS-backed worker lock.
        # Wait for any orphan inference to release its resources before cleanup.
        with self.repo.lock("inference", timeout=30):
            self._recover_jobs()

    def _recover_jobs(self):
        with self.repo.lock():
            for job in self.repo.list_manifests():
                if job["status"] == "processing":
                    if job.get("delete_requested"):
                        with self.repo.lock(f"media-{job['job_id']}", timeout=600):
                            self.repo.delete_job(job["job_id"])
                        continue
                    job.update(status="queued", stage="recovered", progress=None, updated_at=utcnow())
                    self.repo.save_manifest(job["job_id"], job)
                work = self.repo.job_dir(job["job_id"]) / "working"
                if work.exists() and not work.is_symlink():
                    shutil.rmtree(work)
        # Unpublished uploads are removed only when no uploader is running.
        with self.repo.lock("upload", timeout=600):
            for directory in self.repo.jobs.iterdir():
                if directory.is_dir() and not directory.is_symlink() and not (directory / "manifest.json").exists():
                    try:
                        self.repo.delete_job(directory.name)
                    except ValueError:
                        pass

    def stage(self, job_id, stage, **updates):
        with self.repo.lock():
            job = self.repo.load_manifest(job_id)
            job.update(stage=stage, updated_at=utcnow(), **updates)
            self.repo.save_manifest(job_id, job)
        self.heartbeat()

    def diarize(self, job_id, audio, result):
        """Add speaker labels to result in place; a failure only adds a warning, never fails the job."""
        if not self.diarization.ready():
            return ["ไม่ได้แยกผู้พูด: ยังไม่ได้ดาวน์โหลดโมเดลแยกผู้พูด (หน้า ตั้งค่า)"]
        self.stage(job_id, "diarizing")
        try:
            segments, names = self.diarization.label(audio, result["segments"], lambda done, total: self.heartbeat())
        except Exception:
            return ["แยกผู้พูดไม่สำเร็จ ผลถอดเสียงยังใช้ได้ตามปกติ"]
        result.update(segments=segments, speaker_names=names)
        return []

    def process_next(self):
        with self.repo.lock():
            queued = [j for j in self.repo.list_manifests() if j["status"] == "queued" and j.get("stage") != "awaiting_track"]
            if not queued:
                return False
            job = queued[-1]
            job_id = job["job_id"]
            job.update(status="processing", stage="probing", attempt=job["attempt"] + 1,
                       progress=None, started_at=utcnow(), updated_at=utcnow(), model_id=self.settings.asr_model,
                       inference_config={"device": self.settings.asr_device, "compute_type": self.settings.asr_compute_type,
                                         "beam_size": self.settings.asr_beam_size, "batch_size": self.settings.asr_batch_size})
            self.repo.save_manifest(job_id, job)
        self.current_job = job_id
        started = time.monotonic()
        work = self.repo.job_dir(job_id) / "working"
        try:
            work.mkdir(exist_ok=True)
            source = self.repo.path(job_id, job["original_file"])
            probe = self.media.probe(source)
            self.stage(job_id, "decoding")
            tracks = [s for s in probe["audio_streams"] if s["index"] == job["audio_stream_index"]]
            if not job.get("track_explicit"):
                tracks += [s for s in probe["audio_streams"] if s not in tracks]
            audio = work / "audio.wav"
            last_error = None
            for track in tracks:
                try:
                    self.jobs.check_disk(int(probe["duration_seconds"] * 16000 * 2 * track.get("channels", 1)))
                    decoded_duration = self.media.extract(source, audio, track["index"])
                    job.update(audio_stream_index=track["index"], channels=track.get("channels"))
                    last_error = None
                    break
                except AppError as exc:
                    last_error = exc
            if last_error:
                raise last_error
            self.jobs.check_disk(audio.stat().st_size)
            asr_audio = self.media.prepare_asr(audio, work / "asr.wav")
            self.stage(job_id, "transcribing", progress={"processed_seconds": 0, "total_seconds": decoded_duration,
                                                       "segments_completed": 0})
            result = self.engine.transcribe(str(asr_audio), job["language"], self.heartbeat)
            warnings = []
            if self.settings.diarization_enabled and result["segments"]:
                warnings += self.diarize(job_id, audio, result)
            self.stage(job_id, "saving")
            doc = {"schema_version": 1, "job_id": job_id, "model_id": self.settings.asr_model,
                   "created_at": utcnow(), **result}
            with self.repo.lock():
                current = self.repo.load_manifest(job_id)
                if current.get("delete_requested"):
                    with self.repo.lock(f"media-{job_id}", timeout=600):
                        self.repo.delete_job(job_id)
                else:
                    self.repo.save_json(job_id, "transcript.original.json", doc)
                    audio.replace(self.repo.path(job_id, "playback.wav"))
                    current.update(status="succeeded", stage="succeeded", finished_at=utcnow(), updated_at=utcnow(),
                                   processing_seconds=round(time.monotonic() - started, 3),
                                   audio_stream_index=job["audio_stream_index"], channels=job["channels"],
                                   warnings=(["ASR ผสม channels เพื่อถอดเสียง; metadata และเสียงแยก channels ยังคงอยู่"] if (job["channels"] or 1) > 1 else []) + warnings)
                    self.repo.save_manifest(job_id, current)
        except Exception as exc:
            with self.repo.lock():
                current = self.repo.load_manifest(job_id)
                if current.get("delete_requested"):
                    with self.repo.lock(f"media-{job_id}", timeout=600):
                        self.repo.delete_job(job_id)
                else:
                    current.update(status="failed", stage="failed", finished_at=utcnow(), updated_at=utcnow(),
                                   error_code=exc.code if isinstance(exc, AppError) else "PROCESSING_FAILED",
                                   error_message=exc.message if isinstance(exc, AppError) else "ประมวลผลไม่สำเร็จ กรุณาตรวจสอบทรัพยากรและการตั้งค่า")
                    self.repo.save_manifest(job_id, current)
        finally:
            if work.exists():
                shutil.rmtree(work)
            self.current_job = None
            self.heartbeat()
        return True
