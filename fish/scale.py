"""Resumable sharded simulation for experiments from thousands to 10M+ games."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Iterable, Mapping

from .runner import POLICY_NAMES, play_game


SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class SimulationConfig:
    """Immutable experiment identity and execution settings.

    ``games`` counts actual games, not duplicate pairs. With ``paired=True`` it
    must be even; each adjacent pair uses the same deal, rotates players within
    each team, and swaps the two teams.
    """

    games: int
    lineup: tuple[str, str, str, str, str, str]
    ruleset: str = "54"
    base_seed: int = 0
    workers: int = 0
    shard_size: int = 10_000
    max_plies: int = 3_000
    particle_count: int = 32
    determinizations: int = 8
    paired: bool = False

    def __post_init__(self) -> None:
        if self.games < 1 or self.shard_size < 1 or self.max_plies < 1:
            raise ValueError("games, shard_size, and max_plies must be positive")
        if self.particle_count < 1 or self.determinizations < 1:
            raise ValueError("particle_count and determinizations must be positive")
        if self.workers < 0:
            raise ValueError("workers must be zero (auto) or positive")
        if self.ruleset not in ("48", "54"):
            raise ValueError("ruleset must be '48' or '54'")
        if len(self.lineup) != 6 or any(policy not in POLICY_NAMES for policy in self.lineup):
            raise ValueError(f"lineup must contain six policies from {POLICY_NAMES}")
        if self.paired and self.games % 2:
            raise ValueError("paired simulation requires an even number of games")

    @property
    def effective_workers(self) -> int:
        if self.workers:
            return self.workers
        return max(1, (os.cpu_count() or 2) - 1)

    def identity(self) -> dict[str, Any]:
        """Fields that must remain identical when resuming an experiment."""
        data = asdict(self)
        data.pop("workers")  # Worker count may change safely across resumes.
        return data

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            self.identity(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ShardSpec:
    shard_id: int
    start_game: int
    end_game: int

    @property
    def games(self) -> int:
        return self.end_game - self.start_game


@dataclass(frozen=True, slots=True)
class ShardResult:
    schema_version: int
    fingerprint: str
    shard_id: int
    start_game: int
    end_game: int
    games: int
    team_a_wins: int
    team_b_wins: int
    ties: int
    total_score_a: int
    total_score_b: int
    total_null_sets: int
    total_plies: int
    worker_seconds: float
    seed_first: int
    seed_last: int


@dataclass(frozen=True, slots=True)
class SimulationSummary:
    fingerprint: str
    output_directory: str
    requested_games: int
    completed_games: int
    complete: bool
    completed_shards: int
    total_shards: int
    team_a_wins: int
    team_b_wins: int
    ties: int
    mean_score_a: float
    mean_score_b: float
    mean_null_sets: float
    mean_plies: float
    aggregate_worker_seconds: float
    invocation_wall_seconds: float
    invocation_games_per_second: float


ProgressCallback = Callable[[int, int, int], None]


def shard_specs(config: SimulationConfig) -> tuple[ShardSpec, ...]:
    return tuple(
        ShardSpec(index, start, min(config.games, start + config.shard_size))
        for index, start in enumerate(range(0, config.games, config.shard_size))
    )


def lineup_for_game(config: SimulationConfig, game_index: int) -> tuple[str, ...]:
    """Return a reproducible lineup with optional duplicate swap/seat rotation."""
    if not config.paired:
        return config.lineup
    pair_index = game_index // 2
    rotation = pair_index % 3
    team_a = [config.lineup[index] for index in (0, 2, 4)]
    team_b = [config.lineup[index] for index in (1, 3, 5)]
    team_a = team_a[rotation:] + team_a[:rotation]
    team_b = team_b[rotation:] + team_b[:rotation]
    even, odd = (team_a, team_b) if game_index % 2 == 0 else (team_b, team_a)
    return even[0], odd[0], even[1], odd[1], even[2], odd[2]


def seed_for_game(config: SimulationConfig, game_index: int) -> int:
    return config.base_seed + (game_index // 2 if config.paired else game_index)


def _ruleset_name(value: str):
    from .core import Ruleset

    return Ruleset.joker_54() if value == "54" else Ruleset.standard_48()


def _run_shard(payload: tuple[SimulationConfig, ShardSpec]) -> ShardResult:
    config, shard = payload
    ruleset = _ruleset_name(config.ruleset)
    team_a_wins = team_b_wins = ties = 0
    total_score_a = total_score_b = total_null_sets = total_plies = 0
    started = perf_counter()
    for game_index in range(shard.start_game, shard.end_game):
        result = play_game(
            seed_for_game(config, game_index),
            lineup_for_game(config, game_index),
            ruleset=ruleset,
            debug=False,
            max_plies=config.max_plies,
            particle_count=config.particle_count,
            determinizations=config.determinizations,
        )
        if result.truncated:
            raise RuntimeError(
                f"game index {game_index} exceeded {config.max_plies} plies; "
                "the shard was not checkpointed"
            )
        total_score_a += result.scores[0]
        total_score_b += result.scores[1]
        total_null_sets += ruleset.num_half_suits - sum(result.scores)
        total_plies += result.plies
        if result.winner == 0:
            team_a_wins += 1
        elif result.winner == 1:
            team_b_wins += 1
        else:
            ties += 1
    elapsed = perf_counter() - started
    return ShardResult(
        SCHEMA_VERSION,
        config.fingerprint,
        shard.shard_id,
        shard.start_game,
        shard.end_game,
        shard.games,
        team_a_wins,
        team_b_wins,
        ties,
        total_score_a,
        total_score_b,
        total_null_sets,
        total_plies,
        elapsed,
        seed_for_game(config, shard.start_game),
        seed_for_game(config, shard.end_game - 1),
    )


def _atomic_json(path: Path, data: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _read_shard(path: Path, config: SimulationConfig, expected: ShardSpec) -> ShardResult:
    result = ShardResult(**json.loads(path.read_text(encoding="utf-8")))
    if result.fingerprint != config.fingerprint:
        raise ValueError(f"shard fingerprint mismatch: {path}")
    if (result.shard_id, result.start_game, result.end_game) != (
        expected.shard_id,
        expected.start_game,
        expected.end_game,
    ):
        raise ValueError(f"shard range mismatch: {path}")
    return result


def _write_manifest(path: Path, config: SimulationConfig) -> None:
    _atomic_json(
        path,
        {
            "schema_version": SCHEMA_VERSION,
            "fingerprint": config.fingerprint,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "config": asdict(config),
            "resumable_identity": config.identity(),
        },
    )


def _load_or_create(
    output: Path, config: SimulationConfig, resume: bool
) -> tuple[Path, Path]:
    manifest = output / "manifest.json"
    shards = output / "shards"
    if manifest.exists():
        if not resume:
            raise FileExistsError(
                f"experiment already exists: {output}; pass resume=True to continue"
            )
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data.get("fingerprint") != config.fingerprint:
            raise ValueError("resume configuration does not match the experiment manifest")
    else:
        if output.exists() and any(output.iterdir()):
            raise FileExistsError(f"refusing to use nonempty unrecognized directory: {output}")
        output.mkdir(parents=True, exist_ok=True)
        _write_manifest(manifest, config)
    shards.mkdir(parents=True, exist_ok=True)
    return manifest, shards


def _summarize(
    config: SimulationConfig,
    output: Path,
    results: Iterable[ShardResult],
    *,
    wall_seconds: float,
    newly_completed_games: int,
) -> SimulationSummary:
    rows = tuple(results)
    completed = sum(row.games for row in rows)
    denominator = max(1, completed)
    return SimulationSummary(
        config.fingerprint,
        str(output.resolve()),
        config.games,
        completed,
        completed == config.games,
        len(rows),
        len(shard_specs(config)),
        sum(row.team_a_wins for row in rows),
        sum(row.team_b_wins for row in rows),
        sum(row.ties for row in rows),
        sum(row.total_score_a for row in rows) / denominator,
        sum(row.total_score_b for row in rows) / denominator,
        sum(row.total_null_sets for row in rows) / denominator,
        sum(row.total_plies for row in rows) / denominator,
        sum(row.worker_seconds for row in rows),
        wall_seconds,
        newly_completed_games / wall_seconds if wall_seconds > 0 else 0.0,
    )


def run_simulation(
    config: SimulationConfig,
    output_directory: str | Path,
    *,
    resume: bool = False,
    progress: ProgressCallback | None = None,
) -> SimulationSummary:
    """Run missing shards and return an aggregate, safely resumable summary."""
    output = Path(output_directory)
    _, shard_directory = _load_or_create(output, config, resume)
    specs = shard_specs(config)
    completed: dict[int, ShardResult] = {}
    pending: list[ShardSpec] = []
    for spec in specs:
        path = shard_directory / f"shard-{spec.shard_id:08d}.json"
        if path.exists():
            completed[spec.shard_id] = _read_shard(path, config, spec)
        else:
            pending.append(spec)

    started = perf_counter()
    newly_completed_games = 0

    def checkpoint(result: ShardResult) -> None:
        nonlocal newly_completed_games
        path = shard_directory / f"shard-{result.shard_id:08d}.json"
        if path.exists():
            raise FileExistsError(f"refusing to overwrite shard: {path}")
        _atomic_json(path, asdict(result))
        completed[result.shard_id] = result
        newly_completed_games += result.games
        if progress is not None:
            progress(sum(row.games for row in completed.values()), config.games, result.shard_id)

    if config.effective_workers == 1:
        for spec in pending:
            checkpoint(_run_shard((config, spec)))
    elif pending:
        executor = ProcessPoolExecutor(max_workers=config.effective_workers)
        try:
            futures = {
                executor.submit(_run_shard, (config, spec)): spec for spec in pending
            }
            for future in as_completed(futures):
                checkpoint(future.result())
        except BaseException:
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        else:
            executor.shutdown(wait=True)

    elapsed = perf_counter() - started
    summary = _summarize(
        config,
        output,
        (completed[index] for index in sorted(completed)),
        wall_seconds=elapsed,
        newly_completed_games=newly_completed_games,
    )
    _atomic_json(output / "summary.json", asdict(summary))
    return summary


def estimate_storage(config: SimulationConfig) -> dict[str, int]:
    """Estimate metadata footprint; detailed per-game traces are never emitted."""
    shards = len(shard_specs(config))
    return {
        "games": config.games,
        "shards": shards,
        "estimated_metadata_bytes": 2_048 + shards * 1_024,
        "detailed_game_traces": 0,
    }


__all__ = [
    "SimulationConfig",
    "SimulationSummary",
    "estimate_storage",
    "lineup_for_game",
    "run_simulation",
    "seed_for_game",
    "shard_specs",
]
