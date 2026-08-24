"""Binary game log roundtrip and compactness."""

import random
import tempfile
from pathlib import Path

from fish.agents import MemoryAgent
from fish.engine import GameState
from fish.gamelog import GameLogWriter, decode_game, encode_game, read_games
from fish.observation import Observation
from fish.rules import RuleConfig


def _play(seed: int, variant: str = "54"):
    rules = RuleConfig(variant=variant)
    state = GameState.deal(rules, seed=seed)
    initial = list(state.hands)
    agents = [MemoryAgent() for _ in range(6)]
    rng = random.Random(seed)
    for p, ag in enumerate(agents):
        ag.begin_game(p, rules, rng.getrandbits(64))
    while not state.is_terminal:
        p = state.turn
        state.apply(p, agents[p].act(Observation.from_state(state, p)))
    return state, initial


def test_encode_decode_roundtrip():
    for variant in ("54", "48"):
        state, initial = _play(3, variant)
        blob = encode_game(state, initial, seed=3, agent_seed=99)
        rec, off = decode_game(blob)
        assert off == len(blob)
        assert rec["seed"] == 3 and rec["agent_seed"] == 99
        assert rec["variant"] == variant
        assert tuple(rec["history"]) == tuple(state.history)
        assert rec["scores"] == state.scores()
        hands = [0] * 6
        for c, p in enumerate(rec["deal"]):
            if p != 0xFF:
                hands[p] |= 1 << c
        assert hands == initial


def test_multi_game_file_and_compactness():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "games.fish"
        states = []
        with GameLogWriter(path) as w:
            for seed in range(20):
                st, init = _play(seed)
                states.append(st)
                w.write(st, init, seed, agent_seed=seed)
        recs = list(read_games(path))
        assert len(recs) == 20
        for rec, st in zip(recs, states):
            assert tuple(rec["history"]) == tuple(st.history)
        # well under 1 KB per game on average
        assert path.stat().st_size / 20 < 1024


def test_detail_level_zero_writes_nothing():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "off.fish"
        st, init = _play(1)
        with GameLogWriter(path, detail_level=0) as w:
            w.write(st, init, 1)
        assert not path.exists()
