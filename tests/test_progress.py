from types import SimpleNamespace

from app.asr.faster_whisper_engine import FasterWhisperEngine
from worker.processor import Worker


def test_engine_reports_original_timestamps_without_transcript_text():
    class Model:
        def transcribe(self, *args, **kwargs):
            return iter([SimpleNamespace(start=1, end=3, text="private text"),
                         SimpleNamespace(start=8, end=10, text="private text")]), SimpleNamespace(language="th")
    engine = FasterWhisperEngine.__new__(FasterWhisperEngine)
    engine.settings = SimpleNamespace(asr_vad=True, asr_beam_size=5, asr_batch_size=1)
    engine.model = Model()
    engine.pipeline = engine.model
    events = []
    result = engine.transcribe("unused.wav", "th", events.append)
    assert events[0] == {"processed_seconds": 3, "segments_completed": 1}
    assert events[-1] == {"processed_seconds": 10, "segments_completed": 2}
    assert all(set(event) == {"processed_seconds", "segments_completed"} for event in events)
    assert len(result["segments"]) == 2


def test_progress_visible_before_completion(settings, create_job, client):
    job = create_job()
    job_id = job["job_id"]
    url = f"/api/jobs/{job_id}"

    class ReportingEngine:
        def transcribe(self, path, language, heartbeat):
            heartbeat({"stage": "loading_model"})
            assert client.get(url).json()["stage"] == "loading_model"
            heartbeat({"stage": "transcribing"})
            heartbeat({"processed_seconds": 0.5, "segments_completed": 1})
            active = client.get(url).json()
            assert active["status"] == "processing"
            assert active["progress"] == {"processed_seconds": 0.5, "total_seconds": 1.0, "segments_completed": 1}
            # Overlaps/regressing timestamps do not move the bar backward.
            heartbeat({"processed_seconds": 0.25, "segments_completed": 1})
            assert client.get(url).json()["progress"]["processed_seconds"] == 0.5
            return {"language": "th", "segments": [], "full_text": ""}

    worker = Worker(settings, ReportingEngine())
    assert worker.process_next()
    assert client.get(url).json()["status"] == "succeeded"
    assert "progress" not in client.get(url + "/transcript").json()["original"]


def test_retry_and_recovery_clear_stale_progress(settings, create_job, client):
    job = create_job()
    worker = Worker(settings)
    job.update(status="failed", progress={"processed_seconds": 0.75, "total_seconds": 1, "segments_completed": 1})
    worker.repo.save_manifest(job["job_id"], job)
    assert client.post(f"/api/jobs/{job['job_id']}/retry").json()["progress"] is None
    job.update(status="processing")
    worker.repo.save_manifest(job["job_id"], job)
    with worker.repo.lock("worker", timeout=0):
        worker.recover()
    assert worker.repo.load_manifest(job["job_id"])["progress"] is None
