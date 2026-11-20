from uuid import uuid4
from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


def test_upload_persists_before_asr(client, create_job):
    job = create_job(title="ทดสอบ", call_id="C1", input_kind="microphone")
    assert job["status"] == "queued"
    assert job["sha256"] and job["attempt"] == 0
    assert client.get(f"/api/jobs/{job['job_id']}/transcript").status_code == 409
    assert client.get("/api/jobs").json()[0]["title"] == "ทดสอบ"


def test_retry_and_delete(client, create_job):
    job = create_job()
    url = f"/api/jobs/{job['job_id']}"
    assert client.post(url + "/retry").status_code == 409
    repo = client.app.state.repo
    job["status"] = "failed"
    repo.save_manifest(job["job_id"], job)
    assert client.post(url + "/retry").json()["status"] == "queued"
    assert client.delete(url).json() == {"deferred": False}
    assert client.get(url).status_code == 404


def test_processing_delete_deferred(client, create_job):
    job = create_job()
    job["status"] = "processing"
    client.app.state.repo.save_manifest(job["job_id"], job)
    assert client.delete(f"/api/jobs/{job['job_id']}").json()["deferred"]
    assert client.app.state.repo.job_dir(job["job_id"]).exists()


def test_range_and_media_busy(client, create_job):
    job = create_job()
    url = f"/api/jobs/{job['job_id']}"
    r = client.get(url + "/media", headers={"Range": "bytes=0-15"})
    assert r.status_code == 206 and len(r.content) == 16
    assert r.headers["content-range"].startswith("bytes 0-15/")
    lock = client.app.state.repo.lock(f"media-{job['job_id']}")
    with lock:
        assert client.delete(url).status_code == 409
    assert client.delete(url).status_code == 202


def test_unsafe_ids_and_paths(client):
    assert client.get("/api/jobs/not-a-uuid").status_code == 400
    repo = client.app.state.repo
    import pytest
    with pytest.raises(ValueError):
        repo.path(str(uuid4()), "../secret")


def test_upload_cap_and_invalid_media(client, settings, wav_bytes, media_tools):
    settings.max_upload_mb = 1
    r = client.post("/api/jobs", files={"file": ("a.wav", b"x" * (1024**2 + 1))})
    assert r.status_code == 413
    r = client.post("/api/jobs", files={"file": ("a.wav", b"not real media")})
    assert r.status_code == 400 and r.json()["code"] == "INVALID_MEDIA"
    assert not list(client.app.state.repo.jobs.iterdir())


def test_auth_all_routes_and_origin(tmp_path):
    cfg = Settings(_env_file=None, data_dir=str(tmp_path), app_env="server", api_token="z" * 32)
    c = TestClient(create_app(cfg))
    for path in ("/", "/static/app.js", "/api/health", "/api/jobs", f"/api/jobs/{uuid4()}/media"):
        assert c.get(path).status_code == 401
    assert c.get("/api/jobs", auth=("vaja", cfg.api_token)).status_code == 200
    assert c.post("/api/jobs", auth=("vaja", cfg.api_token), headers={"Origin": "https://evil.example"}).status_code == 403


def test_server_requires_secret(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        Settings(_env_file=None, app_env="server", api_token="")


def test_filename_cannot_escape(client, wav_bytes, media_tools):
    r = client.post("/api/jobs", files={"file": ("../../call.wav", wav_bytes)})
    assert r.status_code == 202
    job = r.json()
    assert job["original_file"] == "original.wav"
    assert job["original_filename"] == "call.wav"
