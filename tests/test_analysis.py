import json
import time

import pytest

from app.config import Settings
from app.services import analysis_service
from app.services.analysis_service import SCHEMA, AnalysisService, sanitize
from app.services.media_service import AppError
from tests.conftest import TestOnlyEngine


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, data_dir=str(tmp_path / "data"), min_free_disk_mb=0, model_cache_dir=str(tmp_path / "models"),
                    analysis_providers="ollama,claude_cli,claude_api")


@pytest.fixture
def completed(settings, create_job):
    from worker.processor import Worker
    job = create_job()
    worker = Worker(settings, TestOnlyEngine())
    with worker.repo.lock("worker", timeout=0):
        assert worker.process_next()
    return job


def fake_result(segment_id=1, corrected="ข้อความที่แก้แล้ว"):
    return {
        "corrections": [{"segment_id": segment_id, "corrected_text": corrected,
                         "changes": [{"from": "ทดสอบ", "to": "แก้แล้ว", "reason": "test", "confidence": "high"}]},
                        {"segment_id": 999, "corrected_text": "ไม่มีช่วงนี้", "changes": []}],
        "summary": {"main_issue": "ทดสอบ", "reason_for_contact": "ทดสอบ", "actions_taken": [],
                    "resolution_status": "unknown", "follow_ups": [],
                    "uncertain_information": [{"item": "x", "segment_ids": [1, 42]}]},
        "sentiment": {"label": "Neutral", "confidence": "low", "trajectory": "", "explanation": "",
                      "evidence": [{"segment_id": 42, "excerpt": "ไม่มีจริง"}]},
        "topics": {"primary": "other", "labels": [{"category": "other", "confidence": "low",
                                                   "segment_ids": [1, 7], "note": ""}]},
        "warnings": [],
    }


def wait(client, job_id):
    for _ in range(100):
        doc = client.get(f"/api/jobs/{job_id}/analysis").json()
        if doc["status"] != "running":
            return doc
        time.sleep(0.05)
    raise AssertionError("analysis did not finish")


def test_schema_is_strict():
    def walk(node):
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])
            for child in node["properties"].values():
                walk(child)
        if node.get("type") == "array":
            walk(node["items"])
    walk(SCHEMA)


def test_sanitize_drops_unknown_ids_and_noop_corrections():
    segments = [{"id": 1, "text": "ทดสอบ"}, {"id": 2, "text": "เหมือนเดิม"}]
    raw = fake_result()
    raw["corrections"].append({"segment_id": 2, "corrected_text": "เหมือนเดิม", "changes": []})
    result = sanitize(raw, segments)
    assert [c["segment_id"] for c in result["corrections"]] == [1]
    assert result["corrections"][0]["original_text"] == "ทดสอบ"
    assert result["sentiment"]["evidence"] == []
    assert result["topics"]["labels"][0]["segment_ids"] == [1]
    assert result["summary"]["uncertain_information"][0]["segment_ids"] == [1]
    with pytest.raises(AppError):
        sanitize({"corrections": []}, segments)


def test_disabled_by_default(tmp_path):
    s = Settings(_env_file=None, data_dir=str(tmp_path / "d"))
    assert s.enabled_analysis_providers == []
    service = AnalysisService(None, None, s)
    assert service.providers() == []
    with pytest.raises(AppError) as e:
        service.start("00000000-0000-4000-8000-000000000000", "claude_cli")
    assert e.value.code == "ANALYSIS_PROVIDER_DISABLED"


def test_analysis_run_and_apply_creates_revision(client, completed, monkeypatch):
    job_id = completed["job_id"]
    seen = {}

    def fake_call(self, system, prompt):
        seen["prompt"] = prompt
        return fake_result()
    monkeypatch.setattr(AnalysisService, "_call_ollama", fake_call)
    assert client.get(f"/api/jobs/{job_id}/analysis").json() == {"status": "none"}
    r = client.post(f"/api/jobs/{job_id}/analysis", json={"provider": "ollama"})
    assert r.status_code == 202 and r.json()["status"] == "running"
    doc = wait(client, job_id)
    assert doc["status"] == "succeeded", doc
    assert doc["transcript_revision"] == 0 and doc["source_version"] == "original"
    assert "ข้อความสำหรับทดสอบระบบเท่านั้น" in seen["prompt"]
    assert [c["segment_id"] for c in doc["result"]["corrections"]] == [1]

    applied = client.post(f"/api/jobs/{job_id}/analysis/apply", json={"revision": 0})
    assert applied.status_code == 200
    assert applied.json()["revision"] == 1
    transcript = client.get(f"/api/jobs/{job_id}/transcript").json()
    assert transcript["edited"]["segments"][0]["text"] == "ข้อความที่แก้แล้ว"
    assert transcript["original"]["segments"][0]["text"] == "ข้อความสำหรับทดสอบระบบเท่านั้น"
    # Analysis was made from revision 0; applying again must not overwrite revision 1.
    again = client.post(f"/api/jobs/{job_id}/analysis/apply", json={"revision": 1})
    assert again.status_code == 409 and again.json()["code"] == "REVISION_CONFLICT"


def test_provider_error_is_recorded_safely(client, completed, monkeypatch):
    job_id = completed["job_id"]

    def boom(self, system, prompt):
        raise AppError("ANALYSIS_PROVIDER_UNAVAILABLE", "เชื่อมต่อ Ollama ไม่ได้", 503)
    monkeypatch.setattr(AnalysisService, "_call_ollama", boom)
    client.post(f"/api/jobs/{job_id}/analysis", json={"provider": "ollama"})
    doc = wait(client, job_id)
    assert doc["status"] == "failed" and doc["error_code"] == "ANALYSIS_PROVIDER_UNAVAILABLE"
    assert client.post(f"/api/jobs/{job_id}/analysis/apply", json={"revision": 0}).status_code == 409


def test_unknown_provider_rejected(client, completed):
    r = client.post(f"/api/jobs/{completed['job_id']}/analysis", json={"provider": "openai"})
    assert r.status_code == 422


def test_deleted_job_is_not_recreated(client, completed, monkeypatch):
    job_id = completed["job_id"]
    repo = client.app.state.repo
    gate = __import__("threading").Event()

    def slow(self, system, prompt):
        gate.wait(5)
        return fake_result()
    monkeypatch.setattr(AnalysisService, "_call_ollama", slow)
    client.post(f"/api/jobs/{job_id}/analysis", json={"provider": "ollama"})
    assert client.post(f"/api/jobs/{job_id}/analysis", json={"provider": "ollama"}).status_code == 409
    assert client.delete(f"/api/jobs/{job_id}").status_code == 202
    gate.set()
    time.sleep(0.3)
    assert not repo.jobs.joinpath(job_id).exists()


def test_claude_cli_invocation(settings, monkeypatch, tmp_path):
    calls = {}

    class Proc:
        stdout = json.dumps({"is_error": False, "structured_output": {"ok": True}}).encode()

    def run(args, **kw):
        calls["args"], calls["kw"] = args, kw
        return Proc()
    monkeypatch.setattr(analysis_service.shutil, "which", lambda name: "C:/bin/claude.exe")
    monkeypatch.setattr(analysis_service.subprocess, "run", run)
    out = AnalysisService(None, None, settings)._call_claude_cli("SYS", "ถอดเสียง")
    assert out == {"ok": True}
    args = calls["args"]
    assert args[:2] == ["C:/bin/claude.exe", "-p"]
    assert args[args.index("--tools") + 1] == ""
    assert json.loads(args[args.index("--json-schema") + 1]) == SCHEMA
    assert calls["kw"]["input"] == "ถอดเสียง".encode()
    assert "--no-session-persistence" in args and "--strict-mcp-config" in args


def test_claude_cli_not_logged_in(settings, monkeypatch):
    class Proc:
        stdout = b"Invalid API key \xc2\xb7 Please run /login"
    monkeypatch.setattr(analysis_service.shutil, "which", lambda name: "claude")
    monkeypatch.setattr(analysis_service.subprocess, "run", lambda *a, **k: Proc())
    with pytest.raises(AppError) as e:
        AnalysisService(None, None, settings)._call_claude_cli("SYS", "x")
    assert e.value.code == "ANALYSIS_PROVIDER_ERROR"
