import json

import pytest

from app.config import LiveSettings, Settings, snapshot
from worker.processor import ModelProcess


def fields(payload):
    return {f["key"]: f for g in payload["groups"] for f in g["fields"]}


def test_every_setting_is_listed_and_bootstrap_is_read_only(client):
    data = fields(client.get("/api/settings").json())
    assert set(data) == set(Settings.model_fields)
    for key in ("app_env", "host", "port", "data_dir", "api_token", "claude_cli_path", "model_cache_dir"):
        assert data[key]["editable"] is False
    assert data["asr_model"]["editable"] and data["analysis_providers"]["type"] == "multi"
    assert data["max_upload_mb"]["min"] == 1 and data["asr_beam_size"]["max"] == 10
    assert data["api_token"]["value"] is None and data["anthropic_api_key"]["value"] is None


def test_ui_override_applies_live_and_persists(client, settings):
    r = client.put("/api/settings", json={"values": {"max_upload_mb": 5, "analysis_providers": "ollama",
                                                     "asr_vad": False}})
    assert r.status_code == 200, r.text
    data = fields(r.json())
    assert data["max_upload_mb"]["value"] == 5 and data["max_upload_mb"]["source"] == "ui"
    live = client.app.state.settings
    live._checked = 0
    assert live.max_upload_mb == 5 and live.enabled_analysis_providers == ["ollama"] and live.asr_vad is False
    # New process (worker / restart) reads the same overrides.
    assert LiveSettings(settings).max_upload_mb == 5
    assert client.get("/api/system").json()["max_upload_mb"] == 5
    assert client.get("/api/analysis/providers").json()[0]["id"] == "ollama"
    # Reset falls back to .env / defaults.
    data = fields(client.put("/api/settings", json={"reset": ["max_upload_mb"]}).json())
    assert data["max_upload_mb"]["value"] == 100 and data["max_upload_mb"]["source"] != "ui"


def test_invalid_values_are_rejected_without_writing(client, settings):
    path = LiveSettings(settings).path
    for values in ({"max_upload_mb": 0}, {"asr_beam_size": 99}, {"claude_effort": "turbo"},
                   {"ollama_url": "file:///etc/passwd"}, {"asr_audio_filter": "amovie=/etc/passwd"},
                   {"asr_audio_filter": "ametadata=mode=print:file=/tmp/x"}):
        r = client.put("/api/settings", json={"values": values})
        assert r.status_code == 422, values
        assert r.json()["code"] == "INVALID_SETTINGS"
    assert not path.exists()


def test_bootstrap_and_unknown_keys_cannot_be_set(client):
    for values in ({"api_token": "x" * 40}, {"claude_cli_path": "C:/evil.exe"}, {"data_dir": "/"}, {"nope": 1}):
        r = client.put("/api/settings", json={"values": values})
        assert r.status_code == 400 and r.json()["code"] == "SETTING_READ_ONLY"
    assert client.put("/api/settings", json={"reset": ["port"]}).status_code == 400


def test_secret_is_write_only(client):
    r = client.put("/api/settings", json={"values": {"anthropic_api_key": "sk-test-123"}})
    data = fields(r.json())
    assert data["anthropic_api_key"]["is_set"] is True and "sk-test" not in r.text
    # None keeps the stored secret; "" clears it.
    fields(client.put("/api/settings", json={"values": {"anthropic_api_key": None, "asr_beam_size": 4}}).json())
    client.app.state.settings._checked = 0
    assert client.app.state.settings.anthropic_api_key == "sk-test-123"
    data = fields(client.put("/api/settings", json={"values": {"anthropic_api_key": ""}}).json())
    assert data["anthropic_api_key"]["is_set"] is False


def test_corrupt_overrides_fall_back_to_env(settings):
    live = LiveSettings(settings)
    live.path.parent.mkdir(parents=True, exist_ok=True)
    live.path.write_text(json.dumps({"max_upload_mb": -5}), encoding="utf-8")
    assert live.max_upload_mb == 100 and live.error
    live.path.write_text("{not json", encoding="utf-8")
    live._checked = 0
    assert live.max_upload_mb == 100


def test_overrides_file_cannot_change_bootstrap(settings):
    live = LiveSettings(settings)
    live.path.parent.mkdir(parents=True, exist_ok=True)
    live.path.write_text(json.dumps({"data_dir": "/elsewhere", "app_env": "server", "asr_beam_size": 2}), encoding="utf-8")
    assert live.data_dir == settings.data_dir and live.app_env == "local" and live.asr_beam_size == 2


def test_model_process_restarts_when_asr_settings_change(settings):
    live = LiveSettings(settings)
    process = ModelProcess(live)
    before = ModelProcess.model_key(snapshot(live))
    live.save({"asr_beam_size": 2})
    live._checked = 0
    assert ModelProcess.model_key(snapshot(live)) != before
    live.save({"asr_beam_size": 2, "max_upload_mb": 7})
    live._checked = 0
    # Non-ASR settings do not reload the model.
    assert ModelProcess.model_key(snapshot(live)) == ModelProcess.model_key(live.build({"asr_beam_size": 2}))
    assert process.loaded is None


def test_download_only_configured_models(client):
    r = client.post("/api/settings/models/download", json={"name": "some/other-model"})
    assert r.status_code == 400 and r.json()["code"] == "MODEL_NOT_CONFIGURED"


@pytest.mark.parametrize("chain", ["", "highpass=f=100,dynaudnorm=f=150:g=15", "loudnorm,afftdn=nf=-25"])
def test_safe_audio_filters_allowed(chain):
    assert Settings(_env_file=None, asr_audio_filter=chain).asr_audio_filter == chain


def test_shutdown_only_under_launcher(client, monkeypatch):
    assert client.post("/api/shutdown", json={}).status_code == 409
    assert client.get("/api/system").json()["launcher"] is False
    monkeypatch.setenv("VAJA_LAUNCHER", "1")
    assert client.post("/api/shutdown", json={}).status_code == 202
    assert (client.app.state.repo.data_dir / "stop.flag").exists()
