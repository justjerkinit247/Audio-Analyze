import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from audio_analyze.local_ai_client import LocalAIClient, LocalAIConfig, LocalAIError, extract_json_object


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.posts = []
        self.gets = []

    def post(self, url, json, timeout):
        self.posts.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse(self.payload)

    def get(self, url, timeout):
        self.gets.append({"url": url, "timeout": timeout})
        return FakeResponse({"models": [{"name": "gemma3:4b"}]})


def test_extract_json_object_accepts_strict_json():
    assert extract_json_object('{"answer": "ok"}') == {"answer": "ok"}


def test_extract_json_object_extracts_wrapped_json():
    assert extract_json_object('Here is the JSON: {"answer": "ok"}') == {"answer": "ok"}


def test_extract_json_object_rejects_empty_content():
    try:
        extract_json_object("")
    except LocalAIError as exc:
        assert "empty" in str(exc).lower()
    else:
        raise AssertionError("expected LocalAIError")


def test_chat_json_uses_ollama_json_mode_and_parses_message_content():
    session = FakeSession({"message": {"content": '{"ltx_motion_prompt": "camera drifts"}'}})
    client = LocalAIClient(
        LocalAIConfig(base_url="http://127.0.0.1:11434", model="gemma3:4b", timeout_seconds=12),
        session=session,
    )

    data = client.chat_json("system", "user")

    assert data["ltx_motion_prompt"] == "camera drifts"
    assert session.posts[0]["url"] == "http://127.0.0.1:11434/api/chat"
    assert session.posts[0]["json"]["format"] == "json"
    assert session.posts[0]["json"]["model"] == "gemma3:4b"
    assert session.posts[0]["timeout"] == 12


def test_chat_text_returns_message_content():
    session = FakeSession({"message": {"content": "plain answer"}})
    client = LocalAIClient(LocalAIConfig(), session=session)

    assert client.chat_text("system", "user") == "plain answer"


def test_health_check_reports_models():
    session = FakeSession({"message": {"content": "unused"}})
    client = LocalAIClient(LocalAIConfig(model="gemma3:4b"), session=session)

    report = client.health_check()

    assert report["ok"] is True
    assert report["provider"] == "ollama"
    assert report["model"] == "gemma3:4b"
    assert report["models"] == [{"name": "gemma3:4b"}]
