import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from uuid import UUID
from filelock import FileLock


def utcnow():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as f:
            tmp = f.name
            json.dump(payload, f, ensure_ascii=False, allow_nan=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        # Windows refuses to replace a file another process has open (e.g. the API reading
        # worker.json); such readers are brief, so retry instead of failing the writer.
        for attempt in range(50):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == 49:
                    raise
                time.sleep(0.02)
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


class FileJobRepository:
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir).resolve()
        self.jobs = self.data_dir / "jobs"
        self.jobs.mkdir(parents=True, exist_ok=True)
        self.locks = self.data_dir / "locks"
        self.locks.mkdir(exist_ok=True)

    def lock(self, name="repository", timeout=30):
        return FileLock(str(self.locks / f"{name}.lock"), timeout=timeout, thread_local=False)

    def job_dir(self, job_id: str) -> Path:
        if str(UUID(job_id)) != job_id:
            raise ValueError("Invalid job ID")
        path = self.jobs / job_id
        if path.is_symlink() or path.resolve().parent != self.jobs.resolve():
            raise ValueError("Unsafe path")
        return path

    def path(self, job_id: str, filename: str) -> Path:
        if Path(filename).name != filename or filename in (".", ".."):
            raise ValueError("Unsafe filename")
        path = self.job_dir(job_id) / filename
        if path.is_symlink() or path.resolve().parent != self.job_dir(job_id).resolve():
            raise ValueError("Unsafe path")
        return path

    def create_job_dir(self, job_id):
        path = self.job_dir(job_id)
        path.mkdir(exist_ok=False)
        return path

    def save_manifest(self, job_id, manifest):
        self.save_json(job_id, "manifest.json", manifest)

    def load_manifest(self, job_id):
        return self.load_json(job_id, "manifest.json")

    def list_manifests(self):
        result = []
        for child in self.jobs.iterdir():
            if child.is_symlink() or not child.is_dir():
                continue
            try:
                result.append(self.load_manifest(child.name))
            except (ValueError, FileNotFoundError):
                continue
        return sorted(result, key=lambda j: j["created_at"], reverse=True)

    def save_json(self, job_id, filename, payload):
        atomic_json(self.path(job_id, filename), payload)

    def load_json(self, job_id, filename):
        return json.loads(self.path(job_id, filename).read_text(encoding="utf-8"))

    def delete_job(self, job_id):
        path = self.job_dir(job_id)
        if path.exists():
            shutil.rmtree(path)
