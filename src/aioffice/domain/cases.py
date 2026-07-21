"""Case aggregate for grouping artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field

from .artifacts import Artifact
from .events import DomainEvent
from .identifiers import Identifier


@dataclass(slots=True)
class Case:
    """Aggregate root that groups artifacts and records domain events."""

    id: Identifier = field(default_factory=Identifier.new)
    _artifacts: list[Artifact] = field(default_factory=list, init=False, repr=False)
    _pending_events: list[DomainEvent] = field(default_factory=list, init=False, repr=False)

    @property
    def artifacts(self) -> tuple[Artifact, ...]:
        return tuple(self._artifacts)

    @property
    def pending_events(self) -> tuple[DomainEvent, ...]:
        return tuple(self._pending_events)

    def add_artifact(self, artifact: Artifact) -> None:
        if any(existing.id == artifact.id for existing in self._artifacts):
            msg = f"artifact {artifact.id} is already assigned to case {self.id}"
            raise ValueError(msg)
        self._artifacts.append(artifact)
        self._pending_events.append(
            DomainEvent(
                name="case.artifact_added",
                payload={
                    "case_id": str(self.id),
                    "artifact_id": str(artifact.id),
                    "artifact_type": artifact.artifact_type.value,
                },
            )
        )

    def pull_events(self) -> tuple[DomainEvent, ...]:
        events = tuple(self._pending_events)
        self._pending_events.clear()
        return events
