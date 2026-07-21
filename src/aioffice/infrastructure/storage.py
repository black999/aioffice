"""Filesystem-backed storage implementation."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile

from aioffice.domain import StorageReference


_CHUNK_SIZE = 1024 * 1024


@dataclass(slots=True)
class FilesystemStorage:
    """Store artifacts on the local filesystem using SHA-256-based paths."""

    root_directory: Path

    def __post_init__(self) -> None:
        self.root_directory = self.root_directory.expanduser().resolve()

    def store_file(self, source_path: Path) -> StorageReference:
        """Store a file under the content-addressed storage tree."""

        if not source_path.is_file():
            msg = f"source path does not exist or is not a file: {source_path}"
            raise FileNotFoundError(msg)

        staging_directory = self.root_directory / "storage" / ".staging"
        staging_directory.mkdir(parents=True, exist_ok=True)

        with NamedTemporaryFile(dir=staging_directory, delete=False) as temporary_file:
            temporary_path = Path(temporary_file.name)
            file_hash = self._copy_and_hash(source_path=source_path, target_path=temporary_path)

        try:
            locator = self._build_locator(file_hash=file_hash, suffix=source_path.suffix.lower())
            existing_reference = self._find_existing_reference(file_hash=file_hash)
            if existing_reference is not None:
                return existing_reference

            target_path = self.root_directory / "storage" / locator
            target_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path.replace(target_path)
            return StorageReference(storage_name="filesystem", locator=locator.as_posix())
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    def calculate_sha256(self, source_path: Path) -> str:
        """Calculate the SHA-256 hash of a file without loading it into memory."""

        digest = sha256()
        with source_path.open("rb") as source_file:
            for chunk in iter(lambda: source_file.read(_CHUNK_SIZE), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _copy_and_hash(self, source_path: Path, target_path: Path) -> str:
        digest = sha256()
        with source_path.open("rb") as source_file, target_path.open("wb") as target_file:
            while chunk := source_file.read(_CHUNK_SIZE):
                digest.update(chunk)
                target_file.write(chunk)
        return digest.hexdigest()

    def _build_locator(self, file_hash: str, suffix: str) -> Path:
        filename = f"{file_hash}{suffix}"
        return Path("artifacts") / file_hash[:2] / file_hash[2:4] / filename

    def _find_existing_reference(self, file_hash: str) -> StorageReference | None:
        bucket_directory = self.root_directory / "storage" / "artifacts" / file_hash[:2] / file_hash[2:4]
        if not bucket_directory.exists():
            return None

        for candidate in bucket_directory.iterdir():
            if candidate.is_file() and candidate.stem == file_hash:
                locator = candidate.relative_to(self.root_directory / "storage")
                return StorageReference(storage_name="filesystem", locator=locator.as_posix())
        return None
