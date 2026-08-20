"""Command line interface for matches, analysis, tournaments, and benchmarks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter
from typing import Any, Sequence

from .analysis import analysis_as_dict, analyze_observation, observation_from_dict
from .core import Ruleset
from .evaluation import DuplicateEvaluator, round_robin
from .runner import POLICY_NAMES, evaluation_adapter, play_game
from .selfplay import EvolutionConfig, train_population
from .scale import SimulationConfig, estimate_storage, run_simulation


def _ruleset(value: str) -> Ruleset:
    return Ruleset.joker_54() if value == "54" else Ruleset.standard_48()


def _team_seats(team_a: str, team_b: str) -> tuple[str, ...]:
    return team_a, team_b, team_a, team_b, team_a, team_b


def _command_play(args: argparse.Namespace) -> int:
    result = play_game(
        args.seed,
        _team_seats(args.team_a, args.team_b),
        ruleset=_ruleset(args.rules),
        debug=args.debug,
        max_plies=args.max_plies,
        particle_count=args.particles,
        determinizations=args.determinizations,
    )
    print(json.dumps({
        "seed": result.seed,
        "team_a_score": result.scores[0],
        "team_b_score": result.scores[1],
        "winner": None if result.winner is None else ("A" if result.winner == 0 else "B"),
        "plies": result.plies,
        "elapsed_seconds": result.elapsed_seconds,
        "decisions_per_second": result.decisions_per_second,
        "terminated": result.terminated,
    }, indent=2))
    return 0 if result.terminated else 2


def _command_benchmark(args: argparse.Namespace) -> int:
    started = perf_counter()
    results = [
        play_game(
            args.seed + index,
            (args.agent,) * 6,
            ruleset=_ruleset(args.rules),
            debug=args.debug,
            max_plies=args.max_plies,
            particle_count=args.particles,
            determinizations=args.determinizations,
        )
        for index in range(args.games)
    ]
    elapsed = perf_counter() - started
    plies = sum(result.plies for result in results)
    print(json.dumps({
        "agent": args.agent,
        "ruleset": args.rules,
        "seed_start": args.seed,
        "games": args.games,
        "elapsed_seconds": elapsed,
        "games_per_second": args.games / elapsed,
        "decisions_per_second": plies / elapsed,
        "mean_plies": plies / args.games,
        "truncated_games": sum(result.truncated for result in results),
    }, indent=2))
    return 0 if all(result.terminated for result in results) else 2


def _command_evaluate(args: argparse.Namespace) -> int:
    evaluator = DuplicateEvaluator(
        evaluation_adapter(
            ruleset=_ruleset(args.rules),
            debug=args.debug,
            max_plies=args.max_plies,
            particle_count=args.particles,
            determinizations=args.determinizations,
        )
    )
    report = evaluator.evaluate(
        args.policy_a,
        args.policy_b,
        deals=args.deals,
        seed=args.seed,
        policy_a_name=args.policy_a,
        policy_b_name=args.policy_b,
    )
    print(json.dumps({
        "policy_a": args.policy_a,
        "policy_b": args.policy_b,
        "duplicate_deals": args.deals,
        "games": 2 * args.deals,
        "point_rate": report.point_rate.estimate,
        "point_rate_95_ci": [report.point_rate.low, report.point_rate.high],
        "paired_half_suit_margin": report.paired_margin.estimate,
        "paired_margin_95_ci": [report.paired_margin.low, report.paired_margin.high],
    }, indent=2))
    return 0


def _command_tournament(args: argparse.Namespace) -> int:
    evaluator = DuplicateEvaluator(
        evaluation_adapter(
            ruleset=_ruleset(args.rules),
            debug=args.debug,
            max_plies=args.max_plies,
            particle_count=args.particles,
            determinizations=args.determinizations,
        )
    )
    result = round_robin(
        {name: name for name in args.agents},
        evaluator,
        deals_per_pair=args.deals,
        seed=args.seed,
    )
    print(json.dumps({
        "duplicate_deals_per_pair": args.deals,
        "ratings": [
            {
                "policy": name,
                "rating": rating.value,
                "uncertainty": rating.uncertainty,
                "games": rating.games,
            }
            for name, rating in result.ratings
        ],
    }, indent=2))
    return 0


def _command_analyze(args: argparse.Namespace) -> int:
    document = json.loads(Path(args.state).read_text(encoding="utf-8"))
    observation = observation_from_dict(document)
    result = analyze_observation(
        observation,
        agent_name=args.agent,
        seed=args.seed,
        particle_count=args.particles,
        determinizations=args.determinizations,
        alternatives=args.alternatives,
    )
    print(json.dumps(analysis_as_dict(result, observation.ruleset), indent=2))
    return 0


def _command_selfplay(args: argparse.Namespace) -> int:
    config = EvolutionConfig(
        population_size=args.population,
        generations=args.generations,
        duplicate_deals=args.deals,
        mutation_sigma=args.sigma,
        historical_opponents=args.history,
        seed=args.seed,
        max_plies=args.max_plies,
    )
    results = train_population(
        config,
        ruleset=_ruleset(args.rules),
        output_directory=args.output,
    )
    print(json.dumps({
        "algorithm": "population evolutionary self-play baseline",
        "generations": [
            {
                "generation": result.generation,
                "champion": {
                    "suit_concentration": result.champion.suit_concentration,
                    "inverse_target_cards": result.champion.inverse_target_cards,
                    "low_target_cards": result.champion.low_target_cards,
                },
                "fitness": result.champion_fitness,
                "checkpoint": result.checkpoint,
            }
            for result in results
        ],
    }, indent=2))
    return 0


def _command_simulate(args: argparse.Namespace) -> int:
    if args.lineup is not None:
        lineup = tuple(args.lineup)
    else:
        lineup = (args.policy,) * 6
    config = SimulationConfig(
        games=args.games,
        lineup=lineup,  # type: ignore[arg-type]
        ruleset=args.rules,
        base_seed=args.seed,
        workers=args.workers,
        shard_size=args.shard_size,
        max_plies=args.max_plies,
        particle_count=args.particles,
        determinizations=args.determinizations,
        paired=args.paired,
    )
    if args.dry_run:
        print(json.dumps({
            "config": {
                "games": config.games,
                "lineup": config.lineup,
                "ruleset": config.ruleset,
                "base_seed": config.base_seed,
                "workers": config.effective_workers,
                "shard_size": config.shard_size,
                "paired": config.paired,
            },
            "storage": estimate_storage(config),
        }, indent=2))
        return 0

    last_reported = 0

    def progress(completed: int, total: int, shard_id: int) -> None:
        nonlocal last_reported
        if completed == total or completed - last_reported >= args.progress_every:
            print(
                json.dumps({
                    "event": "simulation_progress",
                    "completed_games": completed,
                    "total_games": total,
                    "percent": 100.0 * completed / total,
                    "last_shard": shard_id,
                }),
                file=sys.stderr,
                flush=True,
            )
            last_reported = completed

    summary = run_simulation(
        config,
        args.output,
        resume=args.resume,
        progress=progress,
    )
    print(json.dumps({
        "fingerprint": summary.fingerprint,
        "output_directory": summary.output_directory,
        "complete": summary.complete,
        "completed_games": summary.completed_games,
        "requested_games": summary.requested_games,
        "team_a_wins": summary.team_a_wins,
        "team_b_wins": summary.team_b_wins,
        "ties": summary.ties,
        "mean_score_a": summary.mean_score_a,
        "mean_score_b": summary.mean_score_b,
        "mean_null_sets": summary.mean_null_sets,
        "mean_plies": summary.mean_plies,
        "invocation_wall_seconds": summary.invocation_wall_seconds,
        "invocation_games_per_second": summary.invocation_games_per_second,
    }, indent=2))
    return 0 if summary.complete else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fish", description="Literature/Fish research engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--rules", choices=("48", "54"), default="54")
    common.add_argument("--seed", type=int, default=20260820)
    common.add_argument("--max-plies", type=int, default=10_000)
    common.add_argument("--particles", type=int, default=96)
    common.add_argument("--determinizations", type=int, default=48)
    common.add_argument("--debug", action="store_true")

    play = subparsers.add_parser("play", parents=[common], help="run one engine-vs-engine game")
    play.add_argument("--team-a", choices=POLICY_NAMES, default="heuristic")
    play.add_argument("--team-b", choices=POLICY_NAMES, default="random")
    play.set_defaults(handler=_command_play)

    benchmark = subparsers.add_parser("benchmark", parents=[common], help="measure simulator throughput")
    benchmark.add_argument("--agent", choices=POLICY_NAMES, default="random")
    benchmark.add_argument("--games", type=int, default=1000)
    benchmark.set_defaults(handler=_command_benchmark)

    evaluate = subparsers.add_parser("evaluate", parents=[common], help="duplicate-deal policy comparison")
    evaluate.add_argument("policy_a", choices=POLICY_NAMES)
    evaluate.add_argument("policy_b", choices=POLICY_NAMES)
    evaluate.add_argument("--deals", type=int, default=100)
    evaluate.set_defaults(handler=_command_evaluate)

    tournament = subparsers.add_parser("tournament", parents=[common], help="duplicate-deal round robin")
    tournament.add_argument("agents", nargs="+", choices=POLICY_NAMES)
    tournament.add_argument("--deals", type=int, default=50)
    tournament.set_defaults(handler=_command_tournament)

    analyze = subparsers.add_parser("analyze", help="analyze a legal observation JSON file")
    analyze.add_argument("state")
    analyze.add_argument("--agent", choices=POLICY_NAMES, default="search")
    analyze.add_argument("--seed", type=int, default=0)
    analyze.add_argument("--particles", type=int, default=256)
    analyze.add_argument("--determinizations", type=int, default=256)
    analyze.add_argument("--alternatives", type=int, default=5)
    analyze.set_defaults(handler=_command_analyze)

    selfplay = subparsers.add_parser(
        "selfplay", parents=[common], help="run population evolutionary self-play"
    )
    selfplay.add_argument("--population", type=int, default=6)
    selfplay.add_argument("--generations", type=int, default=3)
    selfplay.add_argument("--deals", type=int, default=20)
    selfplay.add_argument("--sigma", type=float, default=0.25)
    selfplay.add_argument("--history", type=int, default=3)
    selfplay.add_argument("--output", default="runs/selfplay")
    selfplay.set_defaults(handler=_command_selfplay)

    simulate = subparsers.add_parser(
        "simulate",
        parents=[common],
        help="run a resumable sharded experiment designed for 10M+ games",
    )
    simulate.add_argument("--games", type=int, required=True)
    lineup_group = simulate.add_mutually_exclusive_group()
    lineup_group.add_argument("--policy", choices=POLICY_NAMES, default="random")
    lineup_group.add_argument(
        "--lineup",
        nargs=6,
        choices=POLICY_NAMES,
        metavar=("P0", "P1", "P2", "P3", "P4", "P5"),
    )
    simulate.add_argument("--workers", type=int, default=0, help="0 uses CPU count minus one")
    simulate.add_argument("--shard-size", type=int, default=10_000)
    simulate.add_argument("--paired", action="store_true", help="duplicate deals with team swaps and seat rotations")
    simulate.add_argument("--output", required=True)
    simulate.add_argument("--resume", action="store_true")
    simulate.add_argument("--dry-run", action="store_true")
    simulate.add_argument("--progress-every", type=int, default=10_000)
    simulate.set_defaults(handler=_command_simulate)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    for name in (
        "games", "deals", "particles", "determinizations", "alternatives",
        "population", "generations", "history",
        "shard_size", "progress_every",
    ):
        if hasattr(args, name) and getattr(args, name) < 1:
            parser.error(f"--{name.replace('_', '-')} must be positive")
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
