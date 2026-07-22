from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aioffice.domain import Case, Identifier
from aioffice.infrastructure import SQLiteCaseRepository
from aioffice.infrastructure.web.app import create_app


def test_get_root_returns_http_200_and_displays_cases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    repository = SQLiteCaseRepository(database_path=tmp_path / "storage" / "aioffice.db")
    repository.save(Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")))
    repository.close()
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "AI Office" in response.text
    assert "Number of Cases" in response.text
    assert "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in response.text
