"""Offline contract tests for the existing GTRG LTX-2.3 V2 cloud transport.

These tests use fake HTTP responses and never upload media or spend credits.
"""
from pathlib import Path

import pytest

from audio_analyze import ltx_client
from audio_analyze.ltx_client import LTXClient, LTXError


class FakeResponse:
    def __init__(self, status_code=200, data=None, content=b""):
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.data = data or {}
        self.content = content
        self.text = str(self.data)
        self.headers = {}

    def json(self):
        return self.data


class FakeSession:
    def __init__(self, statuses=None, job_id="gtrg-job-1"):
        self.posts = []
        self.gets = []
        self.statuses = list(statuses or [
            {"status": "pending"},
            {"status": "processing"},
            {"status": "completed", "result": {"video_url": "https://example.com/gtrg.mp4"}},
        ])
        self.job_id = job_id

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        if url.endswith("/v1/upload"):
            return FakeResponse(data={"upload_url": "https://example.com/upload", "storage_uri": "ltx://media"})
        return FakeResponse(202, {"id": self.job_id} if self.job_id is not None else {})

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        if url == "https://example.com/gtrg.mp4":
            return FakeResponse(content=b"fake-mp4-payload")
        if self.statuses:
            return FakeResponse(data=self.statuses.pop(0))
        raise AssertionError("Unexpected extra status poll")


def client_with_fake_transport(monkeypatch, statuses=None, job_id="gtrg-job-1"):
    monkeypatch.setattr(ltx_client.time, "sleep", lambda seconds: None)
    client = LTXClient(api_key="offline-test-key")
    fake = FakeSession(statuses=statuses, job_id=job_id)
    client.session = fake
    return client, fake


def test_existing_audio_and_seed_image_are_submitted_together(monkeypatch, tmp_path):
    client, fake = client_with_fake_transport(monkeypatch)
    output = tmp_path / "video.mp4"
    exact_gemma_asmo_prompt = "[SUBJECT_LOCK]\nkeep two people\n[MOTION_PROMPT]\nmove on beat"
    result = client.audio_to_video(
        audio_uri="ltx://audio",
        image_uri="ltx://seed",
        prompt=exact_gemma_asmo_prompt,
        output_path=output,
        model="ltx-2-3-pro",
        resolution="1080x1920",
        guidance_scale=12.0,
    )
    assert len(fake.posts) == 1
    url, kwargs = fake.posts[0]
    assert url == "https://api.ltx.io/v2/audio-to-video"
    assert kwargs["json"] == {
        "audio_uri": "ltx://audio",
        "image_uri": "ltx://seed",
        "prompt": exact_gemma_asmo_prompt,
        "model": "ltx-2-3-pro",
        "resolution": "1080x1920",
        "guidance_scale": 12.0,
    }
    assert [url for url, _ in fake.gets[:3]] == [
        "https://api.ltx.io/v2/audio-to-video/gtrg-job-1"
    ] * 3
    assert output.read_bytes() == b"fake-mp4-payload"
    assert result["status"] == "downloaded"
    assert result["job_id"] == "gtrg-job-1"


def test_image_to_video_uses_v2_without_generated_soundtrack(monkeypatch, tmp_path):
    client, fake = client_with_fake_transport(
        monkeypatch,
        statuses=[{"status": "completed", "result": {"video_url": "https://example.com/gtrg.mp4"}}],
    )
    result = client.image_to_video(
        image_uri="ltx://seed",
        prompt="A dancer raises both hands in praise.",
        output_path=tmp_path / "clip.mp4",
        model="ltx-2-3-fast",
        duration=6,
        resolution="720x1280",
    )
    assert fake.posts[0][0] == "https://api.ltx.io/v2/image-to-video"
    assert fake.posts[0][1]["json"]["image_uri"] == "ltx://seed"
    assert fake.posts[0][1]["json"]["generate_audio"] is False
    assert result["status"] == "downloaded"


def test_failed_cloud_job_does_not_submit_again(monkeypatch, tmp_path):
    client, fake = client_with_fake_transport(
        monkeypatch,
        statuses=[{"status": "failed", "error": {"type": "insufficient_funds_error", "message": "Not enough credits"}}],
    )
    with pytest.raises(LTXError, match="gtrg-job-1 failed: Not enough credits"):
        client.audio_to_video("ltx://audio", "motion", tmp_path / "no.mp4", image_uri="ltx://seed")
    assert len(fake.posts) == 1


def test_missing_job_id_refuses_uncontrolled_retry(monkeypatch, tmp_path):
    client, fake = client_with_fake_transport(monkeypatch, job_id=None)
    with pytest.raises(LTXError, match="no job ID"):
        client.audio_to_video("ltx://audio", "motion", tmp_path / "no.mp4", image_uri="ltx://seed")
    assert len(fake.posts) == 1
    assert fake.gets == []


def test_dry_runs_do_not_upload_or_submit(monkeypatch, tmp_path):
    client, fake = client_with_fake_transport(monkeypatch)
    image = client.image_to_video(str(tmp_path / "not-uploaded.png"), "motion", tmp_path / "video.mp4", dry_run=True)
    mixed = client.audio_to_video(str(tmp_path / "not-uploaded.mp3"), "motion", tmp_path / "video.mp4", image_uri=str(tmp_path / "not-uploaded.png"), dry_run=True)
    assert image["endpoint"] == "/v2/image-to-video"
    assert mixed["endpoint"] == "/v2/audio-to-video"
    assert mixed["payload"]["image_uri"].endswith("not-uploaded.png")
    assert fake.posts == []
    assert fake.gets == []


def test_upload_endpoint_remains_v1_without_unneeded_metadata(monkeypatch):
    client, fake = client_with_fake_transport(monkeypatch)
    slot = client._request_upload_slot(Path("anything.png"))
    assert fake.posts[0][0] == "https://api.ltx.io/v1/upload"
    assert "json" not in fake.posts[0][1]
    assert slot["storage_uri"] == "ltx://media"
