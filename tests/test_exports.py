from app.services.transcript_service import timestamp


def test_timing_rounding():
    assert timestamp(59.9996) == "00:01:00,000"
    assert timestamp(3600.125) == "01:00:00,125"


def test_export_formats_and_versions(client, completed):
    url = f"/api/jobs/{completed['job_id']}"
    original = client.get(url + "/transcript").json()["original"]
    segments = [{**s, "text": "ตรวจทานแล้ว"} for s in original["segments"]]
    client.put(url + "/transcript", json={"revision": 0, "segments": segments})
    assert "ตรวจทานแล้ว" in client.get(url + "/export?format=txt").text
    assert "ตรวจทานแล้ว" not in client.get(url + "/export?format=txt&version=original").text
    assert "00:00:00,125 --> 00:00:00,999" in client.get(url + "/export?format=srt").text
    assert client.get(url + "/export?format=vtt").text.startswith("WEBVTT\n")
    assert client.get(url + "/export?format=json").json()["transcript"]["revision"] == 1
