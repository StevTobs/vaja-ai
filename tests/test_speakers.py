import csv
import io
import time

import pytest

from app.services import diarization_service
from app.services.analysis_service import role_names, sanitize
from app.services.diarization_service import DiarizationService, assign_speakers
from tests.conftest import TestOnlyEngine


@pytest.fixture
def completed(settings, create_job):
    from worker.processor import Worker
    job = create_job()
    worker = Worker(settings, TestOnlyEngine())
    with worker.repo.lock("worker", timeout=0):
        assert worker.process_next()
    return job


def test_assign_majority_overlap_and_nearest():
    segments = [{"id": 1, "start": 0, "end": 10, "text": "a"}, {"id": 2, "start": 10, "end": 20, "text": "b"},
                {"id": 3, "start": 40, "end": 41, "text": "c"}]
    turns = [{"start": 0, "end": 3, "speaker": "S1"}, {"start": 3, "end": 9, "speaker": "S2"},
             {"start": 12, "end": 20, "speaker": "S1"}, {"start": 30, "end": 35, "speaker": "S2"}]
    assert [s["speaker"] for s in assign_speakers(segments, turns)] == ["S2", "S1", "S2"]
    assert assign_speakers(segments, [])[0]["speaker"] is None


def test_worker_without_model_warns_but_succeeds(client, completed):
    job = client.get(f"/api/jobs/{completed['job_id']}").json()
    assert job["status"] == "succeeded"
    assert any("แยกผู้พูด" in w for w in job["warnings"])


def test_worker_labels_speakers(settings, create_job, monkeypatch, client):
    from worker.processor import Worker
    monkeypatch.setattr(DiarizationService, "ready", lambda self: True)
    monkeypatch.setattr(DiarizationService, "run", lambda self, path, progress=None: [
        {"start": 0, "end": 1, "speaker": "S1"}])
    job = create_job()
    worker = Worker(settings, TestOnlyEngine())
    with worker.repo.lock("worker", timeout=0):
        assert worker.process_next()
    doc = client.get(f"/api/jobs/{job['job_id']}/transcript").json()["original"]
    assert doc["segments"][0]["speaker"] == "S1"
    assert doc["speaker_names"] == {"S1": "ผู้พูด 1"}


def test_edit_speakers_and_names_then_reset(client, completed):
    url = f"/api/jobs/{completed['job_id']}/transcript"
    segs = client.get(url).json()["original"]["segments"]
    segs = [{**s, "speaker": "S2"} for s in segs]
    r = client.put(url, json={"revision": 0, "segments": segs, "speaker_names": {"S2": " ลูกค้า "}})
    assert r.status_code == 200, r.text
    assert r.json()["speaker_names"] == {"S2": "ลูกค้า"}
    # Names kept when not sent; labels without a name get a default.
    segs[0]["speaker"] = "S3"
    doc = client.put(url, json={"revision": 1, "segments": segs}).json()
    assert doc["speaker_names"] == {"S2": "ลูกค้า", "S3": "ผู้พูด 3"}
    assert client.put(url, json={"revision": 2, "segments": segs, "speaker_names": {"bad": "x"}}).status_code == 422
    bad = [{**s, "speaker": "agent"} for s in segs]
    assert client.put(url, json={"revision": 2, "segments": bad}).status_code == 422
    reset = client.put(url, json={"revision": 2, "segments": [], "reset": True}).json()
    assert all(s.get("speaker") is None for s in reset["segments"])


def test_exports_include_speakers_and_csv(client, completed):
    job_id = completed["job_id"]
    url = f"/api/jobs/{job_id}/transcript"
    segs = [{**s, "speaker": "S1"} for s in client.get(url).json()["original"]["segments"]]
    segs[0]["text"] = "=HYPERLINK(\"x\")"
    client.put(url, json={"revision": 0, "segments": segs, "speaker_names": {"S1": "เจ้าหน้าที่"}})
    r = client.get(f"/api/jobs/{job_id}/export?format=csv&version=edited")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "charset=utf-8" in r.headers["content-type"]
    raw = r.content.decode("utf-8")
    assert raw.startswith("﻿")
    rows = list(csv.reader(io.StringIO(raw.lstrip("﻿"))))
    assert rows[0] == ["ลำดับ", "เวลาเริ่ม", "เวลาจบ", "เริ่ม (วินาที)", "จบ (วินาที)", "ผู้พูด", "ข้อความ"]
    assert rows[1][0] == "1" and rows[1][1] == "00:00:00.125" and rows[1][5] == "เจ้าหน้าที่"
    assert rows[1][6].startswith("'=")  # no formula execution in Excel
    assert client.get(f"/api/jobs/{job_id}/export?format=txt").text.startswith("เจ้าหน้าที่: ")
    assert "<v เจ้าหน้าที่>" in client.get(f"/api/jobs/{job_id}/export?format=vtt").text
    assert "เจ้าหน้าที่: " in client.get(f"/api/jobs/{job_id}/export?format=srt").text
    # Original has no speakers: plain export unchanged, CSV speaker column empty.
    original = list(csv.reader(io.StringIO(client.get(f"/api/jobs/{job_id}/export?format=csv&version=original")
                                           .content.decode("utf-8").lstrip("﻿"))))
    assert original[1][5] == ""


def test_speaker_job_for_existing_transcript(client, completed, monkeypatch):
    job_id = completed["job_id"]
    assert client.post(f"/api/jobs/{job_id}/speakers", json={}).json()["code"] == "DIARIZATION_MODEL_MISSING"
    monkeypatch.setattr(DiarizationService, "ready", lambda self: True)
    monkeypatch.setattr(DiarizationService, "run", lambda self, path, progress=None: [
        {"start": 0, "end": 0.5, "speaker": "S1"}, {"start": 0.5, "end": 1, "speaker": "S2"}])
    assert client.post(f"/api/jobs/{job_id}/speakers", json={}).status_code == 202
    for _ in range(100):
        state = client.get(f"/api/jobs/{job_id}/speakers").json()
        if state["status"] != "running":
            break
        time.sleep(0.05)
    assert state["status"] == "succeeded" and state["revision"] == 1, state
    t = client.get(f"/api/jobs/{job_id}/transcript").json()
    assert t["edited"]["segments"][0]["speaker"] == "S2"  # 0.125-0.999 overlaps S2 most
    assert "speaker" not in t["original"]["segments"][0] or t["original"]["segments"][0]["speaker"] is None


def test_ai_roles_sanitized_and_named():
    segments = [{"id": 1, "text": "สวัสดีค่ะ การไฟฟ้า", "speaker": "S1"}, {"id": 2, "text": "ค่าไฟแพง", "speaker": "S2"}]
    base = {"corrections": [], "summary": {}, "sentiment": {}, "topics": {}, "warnings": []}
    raw = {**base, "speaker_roles": [{"speaker": "S2", "role": "customer", "confidence": "high", "reason": ""},
                                     {"speaker": "S1", "role": "agent", "confidence": "high", "reason": ""},
                                     {"speaker": "S9", "role": "agent", "confidence": "high", "reason": ""}]}
    roles = sanitize(raw, segments)["speaker_roles"]
    assert [r["speaker"] for r in roles] == ["S1", "S2"]
    assert role_names(roles, {"S1": "ผู้พูด 1", "S2": "ผู้พูด 2"}) == {"S1": "เจ้าหน้าที่", "S2": "ลูกค้า"}
    two = [{"speaker": "S1", "role": "customer"}, {"speaker": "S2", "role": "customer"},
           {"speaker": "S3", "role": "unknown"}]
    assert role_names(two, {"S3": "ผู้พูด 3"}) == {"S1": "ลูกค้า 1", "S2": "ลูกค้า 2", "S3": "ผู้พูด 3"}


def test_speaker_model_in_settings(client):
    models = client.get("/api/settings").json()["models"]
    assert models["speaker-diarization"]["cached"] is False
    groups = {g["id"] for g in client.get("/api/settings").json()["groups"]}
    assert "speakers" in groups


def test_diarization_service_numbers_speakers_by_first_appearance(settings, tmp_path, monkeypatch):
    import types
    import wave
    path = tmp_path / "a.wav"
    with wave.open(str(path), "wb") as f:
        f.setnchannels(2), f.setsampwidth(2), f.setframerate(16000), f.writeframes(b"\0\0" * 32000)
    seg = lambda s, e, k: types.SimpleNamespace(start=s, end=e, speaker=k)  # noqa: E731

    class FakeResult(list):
        def sort_by_start_time(self):
            return self

    class FakeEngine:
        def __init__(self, config):
            pass

        def process(self, samples, callback=None):
            assert samples.ndim == 1 and len(samples) == 16000  # stereo mixed to mono
            return FakeResult([seg(0, 1, 7), seg(1, 2, 3), seg(2, 3, 7)])
    fake = types.SimpleNamespace(**{n: (lambda *a, **k: None) for n in (
        "OfflineSpeakerDiarizationConfig", "OfflineSpeakerSegmentationModelConfig",
        "OfflineSpeakerSegmentationPyannoteModelConfig", "SpeakerEmbeddingExtractorConfig", "FastClusteringConfig")},
        OfflineSpeakerDiarization=FakeEngine)
    monkeypatch.setitem(__import__("sys").modules, "sherpa_onnx", fake)
    monkeypatch.setattr(DiarizationService, "ready", lambda self: True)
    turns = DiarizationService(settings).run(path)
    assert [t["speaker"] for t in turns] == ["S1", "S2", "S1"]
    assert diarization_service.default_name("S2") == "ผู้พูด 2"
