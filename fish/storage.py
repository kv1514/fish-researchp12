"""Compact experiment storage using the Python standard library only."""

from __future__ import annotations

from contextlib import AbstractContextManager
import json
from pathlib import Path
import sqlite3
from typing import Any
import zlib


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS experiments (
    experiment_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    config_json TEXT NOT NULL,
    source_revision TEXT
);
CREATE TABLE IF NOT EXISTS games (
    experiment_id TEXT NOT NULL,
    game_index INTEGER NOT NULL,
    seed INTEGER NOT NULL,
    ruleset TEXT NOT NULL,
    team_a_policy TEXT NOT NULL,
    team_b_policy TEXT NOT NULL,
    score_a INTEGER NOT NULL,
    score_b INTEGER NOT NULL,
    null_sets INTEGER NOT NULL,
    winner INTEGER,
    decisions INTEGER NOT NULL,
    elapsed_seconds REAL,
    trace_zlib BLOB,
    PRIMARY KEY (experiment_id, game_index),
    FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id)
);
CREATE INDEX IF NOT EXISTS idx_games_policies
ON games(team_a_policy, team_b_policy);
CREATE TABLE IF NOT EXISTS metrics (
    experiment_id TEXT NOT NULL,
    name TEXT NOT NULL,
    step INTEGER NOT NULL,
    value REAL NOT NULL,
    metadata_json TEXT,
    PRIMARY KEY (experiment_id, name, step),
    FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id)
);
"""


class ExperimentStore(AbstractContextManager["ExperimentStore"]):
    """SQLite summaries with opt-in compressed detailed traces.

    Detailed logging is disabled by the caller simply by omitting ``trace``.
    This avoids per-action JSON files while preserving reproducibility metadata.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.executescript(SCHEMA)

    def __exit__(self, *exc_info: object) -> None:
        if exc_info[0] is None:
            self.connection.commit()
        else:
            self.connection.rollback()
        self.connection.close()

    def create_experiment(
        self, experiment_id: str, config: dict[str, Any], source_revision: str | None = None
    ) -> None:
        self.connection.execute(
            "INSERT INTO experiments(experiment_id, config_json, source_revision) VALUES(?,?,?)",
            (experiment_id, json.dumps(config, sort_keys=True, separators=(",", ":")), source_revision),
        )

    def add_game(
        self,
        experiment_id: str,
        game_index: int,
        *,
        seed: int,
        ruleset: str,
        team_a_policy: str,
        team_b_policy: str,
        score_a: int,
        score_b: int,
        null_sets: int,
        winner: int | None,
        decisions: int,
        elapsed_seconds: float | None = None,
        trace: dict[str, Any] | list[Any] | None = None,
    ) -> None:
        payload = None
        if trace is not None:
            raw = json.dumps(trace, separators=(",", ":")).encode("utf-8")
            payload = zlib.compress(raw, level=6)
        self.connection.execute(
            """INSERT INTO games VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                experiment_id,
                game_index,
                seed,
                ruleset,
                team_a_policy,
                team_b_policy,
                score_a,
                score_b,
                null_sets,
                winner,
                decisions,
                elapsed_seconds,
                payload,
            ),
        )

    def add_metric(
        self,
        experiment_id: str,
        name: str,
        step: int,
        value: float,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.connection.execute(
            "INSERT INTO metrics VALUES(?,?,?,?,?)",
            (
                experiment_id,
                name,
                step,
                float(value),
                None if metadata is None else json.dumps(metadata, sort_keys=True),
            ),
        )

    def read_trace(self, experiment_id: str, game_index: int) -> Any | None:
        row = self.connection.execute(
            "SELECT trace_zlib FROM games WHERE experiment_id=? AND game_index=?",
            (experiment_id, game_index),
        ).fetchone()
        if row is None:
            raise KeyError((experiment_id, game_index))
        if row[0] is None:
            return None
        return json.loads(zlib.decompress(row[0]))
