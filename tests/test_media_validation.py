import wave
import pytest
from app.services.media_service import AppError, MediaService
from tests.conftest import ffmpeg


@pytest.mark.parametrize("extension,codec", [("wav", "pcm_s16le"), ("mp3", "libmp3lame"), ("m4a", "aac"), ("flac", "flac"), ("ogg", "libopus"), ("webm", "libopus")])
def test_real_audio_formats(tmp_path, settings, media_tools, extension, codec):
    path = tmp_path / f"test.{extension}"
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:a", codec, path)
    service = MediaService(settings)
    probe = service.probe(path)
    target = tmp_path / "out.wav"
    service.extract(path, target, probe["audio_streams"][0]["index"])
    with wave.open(str(target)) as f:
        assert f.getframerate() == 16000


@pytest.mark.parametrize("extension,vcodec,acodec", [("avi", "mpeg4", "pcm_s16le"), ("mp4", "mpeg4", "aac")])
def test_real_video_absolute_stream_index(tmp_path, settings, media_tools, extension, vcodec, acodec):
    path = tmp_path / f"test.{extension}"
    ffmpeg("-f", "lavfi", "-i", "color=c=black:s=64x64:d=1", "-f", "lavfi", "-i", "sine=duration=1",
           "-c:v", vcodec, "-c:a", acodec, "-shortest", path)
    service = MediaService(settings)
    probe = service.probe(path)
    assert probe["has_video"]
    assert probe["audio_streams"][0]["index"] == 1
    service.extract(path, tmp_path / "out.wav", 1)


def test_no_audio(tmp_path, settings, media_tools):
    path = tmp_path / "silent.mp4"
    ffmpeg("-f", "lavfi", "-i", "color=s=64x64:d=1", "-c:v", "mpeg4", path)
    with pytest.raises(AppError) as e:
        MediaService(settings).probe(path)
    assert e.value.code == "NO_AUDIO_STREAM"


def test_duration_limit(tmp_path, settings, media_tools):
    path = tmp_path / "long.wav"
    ffmpeg("-f", "lavfi", "-i", "sine=duration=2", path)
    settings.max_duration_seconds = 1
    with pytest.raises(AppError) as e:
        MediaService(settings).probe(path)
    assert e.value.code == "DURATION_TOO_LONG"


def test_multiple_tracks_held_until_selection(tmp_path, settings, client, media_tools):
    path = tmp_path / "multi.mkv"
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=300:duration=1", "-f", "lavfi", "-i", "sine=frequency=600:duration=1",
           "-map", "0:a", "-map", "1:a", "-c:a", "pcm_s16le", path)
    with path.open("rb") as f:
        r = client.post("/api/jobs", files={"file": (path.name, f)})
    job = r.json()
    assert job["stage"] == "awaiting_track"
    from worker.processor import Worker
    from tests.conftest import TestOnlyEngine
    w = Worker(settings, TestOnlyEngine())
    assert not w.process_next()
    r = client.put(f"/api/jobs/{job['job_id']}/track?index=1", json={})
    assert r.status_code == 200
    assert w.process_next()
    assert w.repo.load_manifest(job["job_id"])["audio_stream_index"] == 1


def test_stereo_preserved(tmp_path, settings, media_tools):
    path = tmp_path / "stereo.wav"
    ffmpeg("-f", "lavfi", "-i", "sine=duration=1", "-ac", "2", path)
    target = tmp_path / "out.wav"
    MediaService(settings).extract(path, target, 0)
    with wave.open(str(target)) as f:
        assert f.getnchannels() == 2
