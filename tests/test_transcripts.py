def test_original_immutable_and_revision_conflict(client, completed):
    url = f"/api/jobs/{completed['job_id']}/transcript"
    initial = client.get(url).json()
    segments = [{**s, "text": "แก้ไขแล้ว"} for s in initial["original"]["segments"]]
    assert client.put(url, json={"revision": 0, "segments": segments}).status_code == 200
    assert client.put(url, json={"revision": 0, "segments": segments}).status_code == 409
    saved = client.get(url).json()
    assert saved["original"] == initial["original"]
    assert saved["edited"]["full_text"] == "แก้ไขแล้ว"
    assert client.put(url, json={"revision": 1, "segments": [], "reset": True}).json()["revision"] == 2
    assert client.app.state.repo.path(completed["job_id"], "transcript.revision.1.json").exists()


def test_cannot_forge_timestamps(client, completed):
    url = f"/api/jobs/{completed['job_id']}/transcript"
    data = client.get(url).json()
    segments = [{**s, "end": 99} for s in data["original"]["segments"]]
    assert client.put(url, json={"revision": 0, "segments": segments}).status_code == 400
    segments[0]["start"] = -1
    assert client.put(url, json={"revision": 0, "segments": segments}).status_code == 422


def test_revision_pointer_crash_recovers(client, completed):
    job_id = completed["job_id"]
    url = f"/api/jobs/{job_id}/transcript"
    doc = client.get(url).json()["original"]
    revision = {**doc, "revision": 1, "edited_at": doc["created_at"]}
    client.app.state.repo.save_json(job_id, "transcript.revision.1.json", revision)
    assert client.get(url).json()["revision"] == 1
    assert client.put(url, json={"revision": 1, "segments": doc["segments"]}).json()["revision"] == 2
    assert client.app.state.repo.load_json(job_id, "transcript.revision.1.json") == revision
