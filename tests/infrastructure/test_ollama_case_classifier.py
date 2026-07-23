from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import error as urllib_error

import pytest

from aioffice.application import (
    CaseCategory,
    CaseClassificationError,
    CaseClassificationResponseError,
)
from aioffice.infrastructure.ollama_case_classifier import OllamaCaseClassifier


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


def test_ollama_classifier_builds_expected_request(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout: int):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeHTTPResponse(
            status=200,
            body=json.dumps(
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "category": "invoice",
                                "confidence": 0.92,
                                "rationale": "Invoice-related content",
                            }
                        )
                    }
                }
            ),
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    classifier = OllamaCaseClassifier(
        base_url="http://127.0.0.1:11434",
        model_name="qwen2.5:7b",
        timeout_seconds=120,
    )

    result = classifier.classify("Example case text")

    assert result.category is CaseCategory.INVOICE
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["timeout"] == 120
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["stream"] is False
    assert body["format"] == "json"
    assert body["options"]["temperature"] == 0
    assert body["model"] == "qwen2.5:7b"
    assert "BEGIN UNTRUSTED CASE CONTENT" in body["messages"][1]["content"]
    assert "END UNTRUSTED CASE CONTENT" in body["messages"][1]["content"]
    assert "zignor" in body["messages"][0]["content"].lower()


@pytest.mark.parametrize(
    ("exception", "expected_exception"),
    (
        (urllib_error.URLError("refused"), CaseClassificationError),
        (TimeoutError("timeout"), CaseClassificationError),
    ),
)
def test_ollama_classifier_translates_transport_failures(
    monkeypatch: pytest.MonkeyPatch,
    exception: Exception,
    expected_exception: type[Exception],
) -> None:
    def fake_urlopen(request, timeout: int):
        raise exception

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    classifier = OllamaCaseClassifier(
        base_url="http://127.0.0.1:11434",
        model_name="qwen2.5:7b",
        timeout_seconds=120,
    )

    with pytest.raises(expected_exception):
        classifier.classify("Example case text")


def test_ollama_classifier_rejects_invalid_transport_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout: _FakeHTTPResponse(status=200, body="not-json"),
    )
    classifier = OllamaCaseClassifier(
        base_url="http://127.0.0.1:11434",
        model_name="qwen2.5:7b",
        timeout_seconds=120,
    )

    with pytest.raises(CaseClassificationError):
        classifier.classify("Example case text")


def test_ollama_classifier_rejects_invalid_classification_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout: _FakeHTTPResponse(
            status=200,
            body=json.dumps({"message": {"content": '{"category":"unknown","confidence":0.9,"rationale":"x"}'}}),
        ),
    )
    classifier = OllamaCaseClassifier(
        base_url="http://127.0.0.1:11434",
        model_name="qwen2.5:7b",
        timeout_seconds=120,
    )

    with pytest.raises(CaseClassificationResponseError):
        classifier.classify("Example case text")
