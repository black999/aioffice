from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import error as urllib_error

import pytest

from aioffice.application import CaseCategory, ReplyDraftGenerationError, ReplyDraftResponseError
from aioffice.infrastructure.ollama_reply_draft_generator import OllamaReplyDraftGenerator


@dataclass
class _FakeHTTPResponse:
    status: int
    body: str

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self.body.encode("utf-8")


def test_ollama_reply_draft_generator_builds_expected_request(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout: int):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeHTTPResponse(
            status=200,
            body=json.dumps({"message": {"content": '{"subject":"Temat","body":"Tresc"}'}}),
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    generator = OllamaReplyDraftGenerator(
        base_url="http://127.0.0.1:11434",
        model_name="qwen3:4b",
        timeout_seconds=180,
    )

    result = generator.generate(
        case_text="Tekst sprawy",
        category=CaseCategory.INVOICE,
        operator_instruction="Uprzejmie odpowiedz",
    )

    assert result.subject == "Temat"
    assert result.body == "Tresc"
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["timeout"] == 180
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["model"] == "qwen3:4b"
    assert body["stream"] is False
    assert body["format"] == "json"
    assert body["options"]["temperature"] == 0.2
    assert "BEGIN UNTRUSTED CASE CONTENT" in body["messages"][1]["content"]
    assert "BEGIN UNTRUSTED OPERATOR INSTRUCTION" in body["messages"][1]["content"]
    assert "invoice" in body["messages"][1]["content"]


def test_ollama_reply_draft_generator_uses_unknown_category_and_none_instruction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout: int):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeHTTPResponse(
            status=200,
            body=json.dumps({"message": {"content": '{"subject":"Temat","body":"Tresc"}'}}),
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    generator = OllamaReplyDraftGenerator(
        base_url="http://127.0.0.1:11434",
        model_name="qwen3:4b",
        timeout_seconds=180,
    )

    generator.generate(case_text="Tekst", category=None, operator_instruction=None)

    body = captured["body"]
    assert "CATEGORY:\nunknown" in body["messages"][1]["content"]
    assert "OPERATOR INSTRUCTION:\nnone" in body["messages"][1]["content"]


@pytest.mark.parametrize(
    "exception",
    [
        urllib_error.URLError("refused"),
        TimeoutError("timeout"),
    ],
)
def test_ollama_reply_draft_generator_translates_transport_failures(
    monkeypatch: pytest.MonkeyPatch,
    exception: Exception,
) -> None:
    def fake_urlopen(request, timeout: int):
        raise exception

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    generator = OllamaReplyDraftGenerator(
        base_url="http://127.0.0.1:11434",
        model_name="qwen3:4b",
        timeout_seconds=180,
    )

    with pytest.raises(ReplyDraftGenerationError):
        generator.generate(case_text="Tekst", category=None, operator_instruction=None)


def test_ollama_reply_draft_generator_rejects_invalid_transport_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout: _FakeHTTPResponse(status=200, body="not-json"),
    )
    generator = OllamaReplyDraftGenerator(
        base_url="http://127.0.0.1:11434",
        model_name="qwen3:4b",
        timeout_seconds=180,
    )

    with pytest.raises(ReplyDraftGenerationError):
        generator.generate(case_text="Tekst", category=None, operator_instruction=None)


def test_ollama_reply_draft_generator_rejects_invalid_response_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout: _FakeHTTPResponse(
            status=200,
            body=json.dumps({"message": {"content": '{"subject": 1, "body": "Tresc"}'}}),
        ),
    )
    generator = OllamaReplyDraftGenerator(
        base_url="http://127.0.0.1:11434",
        model_name="qwen3:4b",
        timeout_seconds=180,
    )

    with pytest.raises(ReplyDraftResponseError):
        generator.generate(case_text="Tekst", category=None, operator_instruction=None)
