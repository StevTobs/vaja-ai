import io
import shutil
import subprocess
import wave

import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, data_dir=str(tmp_path / "data"), min_free_disk_mb=0, model_cache_dir=str(tmp_path / "models"))


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def wav_bytes():
    out = io.BytesIO()
    with wave.open(out, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(b"\0\0" * 16000)
    return out.getvalue()


@pytest.fixture
def media_tools():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg and FFprobe required for real codec integration")


@pytest.fixture
def create_job(client, wav_bytes, media_tools):
    def create(**data):
        r = client.post("/api/jobs", files={"file": ("call.wav", wav_bytes, "audio/wav")}, data=data)
        assert r.status_code == 202, r.text
        return r.json()
    return create


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", *map(str, args)], check=True,
                   capture_output=True, timeout=30)


class TestOnlyEngine:
    """Explicit test double for lifecycle/revision tests; never used by the app."""
    def transcribe(self, path, language, heartbeat):
        heartbeat()
        return {"language": "th", "segments": [{"id": 1, "start": 0.125, "end": 0.999,
                "text": "ข้อความสำหรับทดสอบระบบเท่านั้น"}], "full_text": "ข้อความสำหรับทดสอบระบบเท่านั้น"}


@pytest.fixture
def completed(settings, create_job):
    from worker.processor import Worker
    job = create_job()
    worker = Worker(settings, TestOnlyEngine())
    with worker.repo.lock("worker", timeout=0):
        assert worker.process_next()
    return job
