"""Case-related application services."""

from __future__ import annotations

from dataclasses import dataclass, field

from aioffice.domain import Artifact, Case, Identifier


@dataclass(slots=True)
class CaseFactory:
    """Create cases from domain artifacts."""

    def create_from_artifact(self, artifact: Artifact) -> Case:
        """Create a new case and attach the provided artifact."""

        case = Case()
        case.add_artifact(artifact)
        return case


@dataclass(slots=True)
class InMemoryCaseRegistry:
    """In-memory registry for created cases."""

    _cases: dict[Identifier, Case] = field(default_factory=dict, init=False, repr=False)

    def add(self, case: Case) -> None:
        """Register a case in memory."""

        self._cases[case.id] = case

    def get(self, case_id: Identifier) -> Case | None:
        """Return a registered case by identifier."""

        return self._cases.get(case_id)

    def list(self) -> tuple[Case, ...]:
        """Return all registered cases."""

        return tuple(self._cases.values())

    def count(self) -> int:
        """Return the number of registered cases."""

        return len(self._cases)
