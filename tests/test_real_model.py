import os
import pytest
from app.asr.faster_whisper_engine import FasterWhisperEngine


@pytest.mark.model
@pytest.mark.skipif(os.getenv("RUN_MODEL_TESTS") != "1", reason="Set RUN_MODEL_TESTS=1 after downloading model")
def test_real_local_inference(settings, wav_bytes, tmp_path):
    settings.model_cache_dir = os.getenv("MODEL_CACHE_DIR", "./data/models")
    path = tmp_path / "silence.wav"
    path.write_bytes(wav_bytes)
    engine = FasterWhisperEngine(settings)
    result = engine.transcribe(str(path), "th")
    assert result["language"] == "th"
    assert result["segments"] == []


@pytest.mark.model
@pytest.mark.skipif(not os.getenv("THAI_SAMPLE"), reason="Set THAI_SAMPLE to an authorized local Thai WAV sample")
def test_real_thai_end_to_end_all_required_containers(settings, client, tmp_path, media_tools):
    from pathlib import Path
    from tests.conftest import ffmpeg
    from worker.processor import Worker
    sample = Path(os.environ["THAI_SAMPLE"]).resolve()
    settings.model_cache_dir = os.getenv("MODEL_CACHE_DIR", "./data/models")
    worker = Worker(settings)
    cases = [("wav", "pcm_s16le"), ("mp3", "libmp3lame"), ("m4a", "aac"), ("avi", "pcm_s16le"), ("mp4", "aac")]
    try:
        with worker.repo.lock("worker", timeout=0):
            worker.recover()
            for extension, codec in cases:
                path = tmp_path / f"thai.{extension}"
                if extension in ("avi", "mp4"):
                    ffmpeg("-f", "lavfi", "-i", "color=c=black:s=64x64:r=10", "-i", sample,
                           "-map", "0:v", "-map", "1:a", "-c:v", "mpeg4", "-c:a", codec, "-shortest", path)
                else:
                    ffmpeg("-i", sample, "-c:a", codec, path)
                with path.open("rb") as f:
                    response = client.post("/api/jobs", files={"file": (path.name, f)},
                                           data={"input_kind": "video" if extension in ("avi", "mp4") else "audio"})
                assert response.status_code == 202, response.text
                job_id = response.json()["job_id"]
                assert worker.process_next()
                job = worker.repo.load_manifest(job_id)
                assert job["status"] == "succeeded", job.get("error_code")
                result = client.get(f"/api/jobs/{job_id}/transcript").json()["original"]
                assert result["segments"]
                assert any("\u0e00" <= c <= "\u0e7f" for c in result["full_text"])
                assert all(0 <= s["start"] <= s["end"] <= job["duration_seconds"] + 1 for s in result["segments"])
                assert client.get(f"/api/jobs/{job_id}/export?format=srt").status_code == 200
    finally:
        worker.engine.close()
