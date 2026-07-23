"""Application models and helpers for persisted artifact metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass

from aioffice.domain import Artifact, ArtifactType, Identifier, StorageReference


_CONTROL_CHARACTERS_PATTERN = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    """Artifact plus persistence metadata needed by application services."""

    artifact: Artifact
    display_name: str
    content_type: str | None


@dataclass(frozen=True, slots=True)
class DownloadableArtifact:
    """Artifact metadata used by the download use case."""

    case_id: Identifier
    position: int
    artifact_type: ArtifactType
    storage_reference: StorageReference
    display_name: str
    content_type: str | None


def sanitize_display_name(
    raw_name: str | None,
    *,
    fallback: str,
    max_length: int = 180,
) -> str:
    """Normalize a user-facing artifact name without treating it as a filesystem path."""

    candidate = raw_name or ""
    candidate = _CONTROL_CHARACTERS_PATTERN.sub("", candidate)
    candidate = candidate.replace("/", "_").replace("\\", "_").replace("..", "_")
    candidate = candidate.strip(" .")
    if not candidate or candidate in {".", ".."}:
        candidate = fallback

    if len(candidate) > max_length:
        if "." in candidate:
            stem, extension = candidate.rsplit(".", 1)
            extension = f".{extension}"
        else:
            stem, extension = candidate, ""
        allowed_stem_length = max(1, max_length - len(extension))
        candidate = f"{stem[:allowed_stem_length]}{extension}"
        candidate = candidate.strip(" .") or fallback

    if candidate in {".", ".."}:
        return fallback
    return candidate


def ensure_unique_display_name(display_name: str, *, existing_names: set[str]) -> str:
    """Make a sanitized display name unique within one imported message."""

    if display_name not in existing_names:
        existing_names.add(display_name)
        return display_name

    if "." in display_name:
        stem, extension = display_name.rsplit(".", 1)
        extension = f".{extension}"
    else:
        stem, extension = display_name, ""

    suffix_index = 2
    while True:
        candidate = f"{stem}-{suffix_index}{extension}"
        if candidate not in existing_names:
            existing_names.add(candidate)
            return candidate
        suffix_index += 1
