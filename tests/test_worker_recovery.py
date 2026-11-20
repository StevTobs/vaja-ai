import pytest
from filelock import Timeout
from worker.processor import Worker
from tests.conftest import TestOnlyEngine


def test_restart_recovery(settings, create_job):
    job = create_job()
    worker = Worker(settings, TestOnlyEngine())
    job.update(status="processing", attempt=1)
    worker.repo.save_manifest(job["job_id"], job)
    with worker.repo.lock("worker", timeout=0):
        worker.recover()
        assert worker.repo.load_manifest(job["job_id"])["status"] == "queued"
        assert worker.process_next()
    current = worker.repo.load_manifest(job["job_id"])
    assert current["status"] == "succeeded" and current["attempt"] == 2
    assert worker.repo.path(job["job_id"], job["original_file"]).exists()
    assert not (worker.repo.job_dir(job["job_id"]) / "working").exists()
    before = worker.repo.load_json(job["job_id"], "transcript.original.json")
    worker.recover()
    assert before == worker.repo.load_json(job["job_id"], "transcript.original.json")


def test_single_worker_lock(settings):
    a, b = Worker(settings, TestOnlyEngine()), Worker(settings, TestOnlyEngine())
    with a.repo.lock("worker", timeout=0):
        with pytest.raises(Timeout):
            with b.repo.lock("worker", timeout=0):
                pass


def test_failure_is_safe(settings, create_job):
    class FailingEngine:
        def transcribe(self, *args):
            raise RuntimeError("SECRET transcript/path/PII")
    job = create_job()
    w = Worker(settings, FailingEngine())
    assert w.process_next()
    failed = w.repo.load_manifest(job["job_id"])
    assert failed["status"] == "failed"
    assert "SECRET" not in failed["error_message"]


def test_delete_during_inference(settings, create_job, client):
    job = create_job()
    class DeletingEngine(TestOnlyEngine):
        def transcribe(self, *args):
            assert client.delete(f"/api/jobs/{job['job_id']}").json()["deferred"]
            return super().transcribe(*args)
    w = Worker(settings, DeletingEngine())
    assert w.process_next()
    assert not w.repo.job_dir(job["job_id"]).exists()
