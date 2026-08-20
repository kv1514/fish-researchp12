"""Persistent, append-only policy league and conservative champion promotion."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class PolicyRecord:
    policy_id: str
    kind: str
    created_at: str
    rating: float
    rating_uncertainty: float
    artifact: str | None
    artifact_sha256: str | None
    config: dict[str, Any]
    training_seed: int | None = None
    source_revision: str | None = None
    evaluation: dict[str, Any] | None = None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class LeagueRegistry:
    """A small JSON registry that never overwrites a policy record.

    Artifacts are referenced, not deleted or moved. Registering the same ID twice
    is an error, which prevents an experiment from silently replacing a champion.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if self.path.exists():
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self._data = {"schema_version": 1, "champion": None, "policies": []}

    @property
    def champion_id(self) -> str | None:
        value = self._data["champion"]
        return None if value is None else str(value)

    def records(self) -> tuple[PolicyRecord, ...]:
        return tuple(PolicyRecord(**item) for item in self._data["policies"])

    def get(self, policy_id: str) -> PolicyRecord:
        for record in self.records():
            if record.policy_id == policy_id:
                return record
        raise KeyError(policy_id)

    def register(
        self,
        policy_id: str,
        kind: str,
        *,
        rating: float,
        rating_uncertainty: float,
        config: dict[str, Any],
        artifact: str | Path | None = None,
        training_seed: int | None = None,
        source_revision: str | None = None,
        evaluation: dict[str, Any] | None = None,
    ) -> PolicyRecord:
        if any(item["policy_id"] == policy_id for item in self._data["policies"]):
            raise ValueError(f"policy ID already exists: {policy_id}")
        artifact_path = None if artifact is None else Path(artifact)
        if artifact_path is not None and not artifact_path.is_file():
            raise FileNotFoundError(artifact_path)
        record = PolicyRecord(
            policy_id=policy_id,
            kind=kind,
            created_at=datetime.now(timezone.utc).isoformat(),
            rating=float(rating),
            rating_uncertainty=max(0.0, float(rating_uncertainty)),
            artifact=None if artifact_path is None else str(artifact_path.resolve()),
            artifact_sha256=None if artifact_path is None else _file_sha256(artifact_path),
            config=dict(config),
            training_seed=training_seed,
            source_revision=source_revision,
            evaluation=None if evaluation is None else dict(evaluation),
        )
        self._data["policies"].append(asdict(record))
        if self._data["champion"] is None:
            self._data["champion"] = policy_id
        self.save()
        return record

    def promotion_margin(self, challenger_id: str, z: float = 1.96) -> float:
        """Return a conservative rating margin over the current champion."""
        challenger = self.get(challenger_id)
        if self.champion_id is None:
            return float("inf")
        champion = self.get(self.champion_id)
        combined = (challenger.rating_uncertainty**2 + champion.rating_uncertainty**2) ** 0.5
        return challenger.rating - champion.rating - z * combined

    def promote(self, challenger_id: str, *, z: float = 1.96) -> None:
        self.get(challenger_id)
        if challenger_id == self.champion_id:
            return
        if self.promotion_margin(challenger_id, z) <= 0.0:
            raise ValueError("challenger has not beaten the champion convincingly")
        self._data["champion"] = challenger_id
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self._data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary.replace(self.path)
