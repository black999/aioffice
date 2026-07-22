from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aioffice.domain import Artifact, ArtifactType, Case, Identifier, StorageReference
from aioffice.infrastructure import AppSettings, SQLiteCaseRepository
from aioffice.infrastructure.web.app import create_app


def test_get_root_returns_http_200_and_displays_cases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = AppSettings(
        data_directory=tmp_path / "configured-data",
        database_path=tmp_path / "configured-data" / "aioffice.db",
        artifacts_directory=tmp_path / "configured-data" / "artifacts",
        incoming_directory=tmp_path / "configured-data" / "incoming",
        processed_directory=tmp_path / "configured-data" / "processed",
        host="127.0.0.1",
        port=8000,
    )
    repository = SQLiteCaseRepository(database_path=settings.database_path)
    repository.save(Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")), reference_number=1)
    repository.close()
    with TestClient(create_app(settings)) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "AI Office" in response.text
    assert "Number of Cases" in response.text
    assert '<a href="/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"><code>CASE-000001</code></a>' in response.text


def test_get_case_workspace_returns_http_200_and_displays_case_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = AppSettings(
        data_directory=tmp_path / "configured-data",
        database_path=tmp_path / "configured-data" / "aioffice.db",
        artifacts_directory=tmp_path / "configured-data" / "artifacts",
        incoming_directory=tmp_path / "configured-data" / "incoming",
        processed_directory=tmp_path / "configured-data" / "processed",
        host="127.0.0.1",
        port=8000,
    )
    repository = SQLiteCaseRepository(database_path=settings.database_path)
    case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    repository.save(case, reference_number=1)
    repository.close()
    with TestClient(create_app(settings)) as client:
        response = client.get("/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert response.status_code == 200
    assert "CASE-000001" in response.text
    assert "<h1>CASE-000001</h1>" in response.text
    assert "open" in response.text
    assert "Created" in response.text
    assert "Imported" in response.text
    assert "No artifacts" in response.text
    assert "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" not in response.text


def test_get_case_workspace_displays_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = AppSettings(
        data_directory=tmp_path / "configured-data",
        database_path=tmp_path / "configured-data" / "aioffice.db",
        artifacts_directory=tmp_path / "configured-data" / "artifacts",
        incoming_directory=tmp_path / "configured-data" / "incoming",
        processed_directory=tmp_path / "configured-data" / "processed",
        host="127.0.0.1",
        port=8000,
    )
    repository = SQLiteCaseRepository(database_path=settings.database_path)
    case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.PDF,
            storage_reference=StorageReference(
                storage_name="filesystem",
                locator="artifacts/aa/bb/document.pdf",
            ),
        )
    )
    repository.save(case, reference_number=1)
    repository.close()
    with TestClient(create_app(settings)) as client:
        response = client.get("/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert response.status_code == 200
    assert "PDF — artifacts/aa/bb/document.pdf" in response.text


def test_get_case_workspace_returns_404_for_missing_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = AppSettings(
        data_directory=tmp_path / "configured-data",
        database_path=tmp_path / "configured-data" / "aioffice.db",
        artifacts_directory=tmp_path / "configured-data" / "artifacts",
        incoming_directory=tmp_path / "configured-data" / "incoming",
        processed_directory=tmp_path / "configured-data" / "processed",
        host="127.0.0.1",
        port=8000,
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert response.status_code == 404


def test_get_case_workspace_returns_404_for_invalid_identifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = AppSettings(
        data_directory=tmp_path / "configured-data",
        database_path=tmp_path / "configured-data" / "aioffice.db",
        artifacts_directory=tmp_path / "configured-data" / "artifacts",
        incoming_directory=tmp_path / "configured-data" / "incoming",
        processed_directory=tmp_path / "configured-data" / "processed",
        host="127.0.0.1",
        port=8000,
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/cases/not-a-uuid")

    assert response.status_code == 404


def test_create_app_uses_passed_database_path(tmp_path: Path) -> None:
    settings = AppSettings(
        data_directory=tmp_path / "first-data",
        database_path=tmp_path / "first-data" / "aioffice.db",
        artifacts_directory=tmp_path / "first-data" / "artifacts",
        incoming_directory=tmp_path / "first-data" / "incoming",
        processed_directory=tmp_path / "first-data" / "processed",
        host="127.0.0.1",
        port=8000,
    )
    repository = SQLiteCaseRepository(database_path=settings.database_path)
    repository.save(Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")), reference_number=1)
    repository.close()
    with TestClient(create_app(settings)) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "CASE-000001" in response.text


def test_web_app_works_independently_of_current_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = AppSettings(
        data_directory=tmp_path / "configured-data",
        database_path=tmp_path / "configured-data" / "aioffice.db",
        artifacts_directory=tmp_path / "configured-data" / "artifacts",
        incoming_directory=tmp_path / "configured-data" / "incoming",
        processed_directory=tmp_path / "configured-data" / "processed",
        host="127.0.0.1",
        port=8000,
    )
    repository = SQLiteCaseRepository(database_path=settings.database_path)
    repository.save(Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")), reference_number=1)
    repository.close()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    with TestClient(create_app(settings)) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "CASE-000001" in response.text


def test_dashboard_and_case_workspace_use_same_configured_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = AppSettings(
        data_directory=tmp_path / "configured-data",
        database_path=tmp_path / "configured-data" / "aioffice.db",
        artifacts_directory=tmp_path / "configured-data" / "artifacts",
        incoming_directory=tmp_path / "configured-data" / "incoming",
        processed_directory=tmp_path / "configured-data" / "processed",
        host="127.0.0.1",
        port=8000,
    )
    repository = SQLiteCaseRepository(database_path=settings.database_path)
    repository.save(Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")), reference_number=1)
    repository.close()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    with TestClient(create_app(settings)) as client:
        dashboard_response = client.get("/")
        workspace_response = client.get("/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert dashboard_response.status_code == 200
    assert workspace_response.status_code == 200
    assert "CASE-000001" in dashboard_response.text
    assert "CASE-000001" in workspace_response.text
