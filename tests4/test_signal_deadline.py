"""The deadline instrument must measure the clock, not its own repeats.

WHY THIS FILE EXISTS. The first version of `scripts4/signal_deadline.py`
reported the stall clock at 12.3 actions where the split landed in time against
38.5 where it did not -- a separation of 26 actions, in the hoped-for direction,
on the first run. It was almost entirely an artifact. The signalling gate is a
per-turn predicate, so in a dead position it stays true and the seat re-signals
at the same half-suit every turn: 295 fires across 14 episodes, one of them 69
turns long. Counting every fire (a) repeats a single eventual declaration once
per repeat and (b) walks the clock upward across the repeats by construction.
On first fires only the same separation is 4.5 actions.

So the tests here are about the two things that make the number mean anything:
the unit is one FIRST fire per (deal, parity, half-suit), and the interval is
clustered on the deal. A test that the instrument runs would have passed on the
broken version.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts4"))

from fish4.agent4 import FishBot4                              # noqa: E402
from scripts4 import signal_deadline as sd                     # noqa: E402
from scripts4.path_ledger import PATHS                         # noqa: E402


def fire(deal, hs, path, repeat=0, kv_even=0, **kw):
    row = {"deal": deal, "kv_even": kv_even, "hs": hs, "path": path,
           "repeat": repeat, "seat": 0, "by_us": 1, "wrong": 0}
    for k in sd.KEYS:                  # read, not restated: a fixture that
        row[k] = kw.get(k, 0)          # lists its own keys drifts silently
    assert not set(kw) - set(sd.KEYS), f"not an observable: {set(kw) - set(sd.KEYS)}"
    return row


def rows_of(fires):
    by = {}
    for f in fires:
        by.setdefault((f["deal"], f["kv_even"]), []).append(f)
    return [{"deal": d, "kv_even": k, "margin": 0, "terminal": 1, "fires": fs}
            for (d, k), fs in by.items()]


# --------------------------------------------------------------------------
# the unit
# --------------------------------------------------------------------------

def test_repeats_are_excluded_from_the_group_means():
    """The bug this file is named for, in its smallest form.

    One episode that lands in time and spins for ten turns, against one that is
    too late and fires once. Counting every fire, `in_time` would be dominated
    by the repeats and its mean `since_claim` would be 9.5. On first fires it
    is 0, which is the state the gate was actually looking at.
    """
    fires = [fire(1, 0, "voluntary", repeat=i, since_claim=i)
             for i in range(11)]
    fires.append(fire(2, 0, "forced", repeat=0, since_claim=40))
    s = sd.summarise(rows_of(fires))
    assert s["n_fires"] == 12
    assert s["n_first_fires"] == 2
    assert s["group_means"]["in_time"]["since_claim"] == 0
    assert s["group_means"]["too_late"]["since_claim"] == 40


def test_one_declaration_is_counted_once_however_long_it_spun():
    """A 69-turn episode and a 1-turn episode weigh the same."""
    fires = [fire(1, 0, "forced", repeat=i) for i in range(69)]
    fires.append(fire(2, 0, "forced", repeat=0))
    s = sd.summarise(rows_of(fires))
    assert s["by_path_first_fire"] == {"forced": 2}
    assert s["group_n"]["too_late"] == 2


def test_the_same_half_suit_in_two_deals_is_two_episodes():
    fires = [fire(1, 3, "forced"), fire(2, 3, "forced")]
    assert sd.summarise(rows_of(fires))["n_first_fires"] == 2


def test_the_same_half_suit_in_two_parities_is_two_episodes():
    """Both parities of a deal are separate games, and separate episodes.

    They are NOT separate clusters -- see the clustering test below -- because
    they share a shuffle. Two episodes, one cluster.
    """
    fires = [fire(1, 3, "forced", kv_even=0), fire(1, 3, "forced", kv_even=1)]
    s = sd.summarise(rows_of(fires))
    assert s["n_first_fires"] == 2
    assert s["spin"]["n_episodes"] == 2


def test_spin_reports_the_length_of_an_episode_not_the_count_of_fires():
    fires = ([fire(1, 0, "forced", repeat=i) for i in range(5)]
             + [fire(2, 0, "forced", repeat=i) for i in range(1)])
    sp = sd.summarise(rows_of(fires))["spin"]
    assert sp["n_episodes"] == 2
    assert sp["max"] == 5
    assert sp["mean_fires_per_episode"] == 3.0


# --------------------------------------------------------------------------
# the interval
# --------------------------------------------------------------------------

def _episode_bootstrap(fires, key, n=4000, seed=sd.BOOT_SEED):
    """What `diff_ci` would do if it treated every episode as independent.

    Written out here rather than imported, because the point of the test below
    is to compare the shipped estimator against the mistake it avoids. A test
    that only asserted the shipped interval covers zero would pass on both.
    """
    import random
    rng = random.Random(seed)
    draws = []
    for _ in range(n):
        pick = [fires[rng.randrange(len(fires))] for _ in range(len(fires))]
        a = [f[key] for f in pick if f["path"] in sd.TOO_LATE]
        b = [f[key] for f in pick if f["path"] in sd.IN_TIME]
        if a and b:
            draws.append(sum(a) / len(a) - sum(b) / len(b))
    draws.sort()
    return draws[int(0.025 * len(draws))], draws[int(0.975 * len(draws)) - 1]


def test_the_interval_clusters_on_the_deal():
    """Episodes inside one deal are not each independent evidence.

    Ten deals, forty episodes each, and every episode inside a deal carries the
    same value -- so a deal contributes ONE observation however many episodes
    it happens to spawn. Six deals separate by +10 and four by -10, for a point
    estimate of +2 on thin evidence.

    The design is chosen so the two estimators DISAGREE about the conclusion,
    not merely about the width: clustered on ten deals the interval covers
    zero, while resampling the four hundred episodes as if independent excludes
    it. An earlier version of this test used a symmetric design where both
    covered zero, so it would have passed with the clustering removed -- which
    is no test at all.
    """
    fires = []
    for d in range(10):
        v = 10 if d < 6 else -10
        for e in range(20):
            fires.append(fire(d, e, "forced", since_claim=v))
            fires.append(fire(d, e + 20, "voluntary", since_claim=0))
    point, lo, hi, n_deals = sd.diff_ci(fires, "since_claim")
    assert n_deals == 10, "clusters are deals, not the 400 episodes"
    assert point == pytest.approx(2.0)
    assert lo < 0 < hi, f"clustered on 10 deals it must cover zero: [{lo}, {hi}]"

    e_lo, e_hi = _episode_bootstrap(fires, "since_claim")
    assert e_lo > 0, (
        "the design is only a test if the un-clustered estimator reaches the "
        f"wrong conclusion; it gave [{e_lo:.3f}, {e_hi:.3f}]")
    assert (hi - lo) > (e_hi - e_lo)


def test_the_interval_is_reproducible():
    fires = [fire(d, 0, "forced" if d % 2 else "voluntary", since_claim=d)
             for d in range(20)]
    a = sd.diff_ci(fires, "since_claim")
    b = sd.diff_ci(fires, "since_claim")
    assert a == b


def test_diff_ci_is_none_when_a_group_is_empty():
    """No interval at all, rather than an interval built on one group."""
    fires = [fire(d, 0, "voluntary", since_claim=d) for d in range(5)]
    assert sd.diff_ci(fires, "since_claim") is None


def test_the_sign_is_too_late_minus_in_time():
    fires = ([fire(d, 0, "forced", since_claim=40) for d in range(6)]
             + [fire(d, 1, "voluntary", since_claim=10) for d in range(6)])
    point, lo, hi, _ = sd.diff_ci(fires, "since_claim")
    assert point == pytest.approx(30.0)


# --------------------------------------------------------------------------
# what the instrument reads from the engine, rather than restates
# --------------------------------------------------------------------------

def test_the_stall_window_is_read_from_the_agent_not_retyped():
    """The deadline is the engine's number, and must follow it if it moves.

    An earlier draft reached for `FishBot4.__init__.__kwdefaults__`, which is
    None -- `stall_window` is positional-or-keyword -- so the expression fell
    through to a literal 80. It was right by coincidence and would have gone on
    printing 80 after the engine changed.
    """
    assert sd.STALL_WINDOW == inspect.signature(
        FishBot4.__init__).parameters["stall_window"].default


def test_since_claim_counts_actions_after_the_last_resolution():
    from fish.engine import ClaimEvent

    class Obs:
        def __init__(self, h):
            self.history = tuple(h)

    ev = ClaimEvent(claimer=0, half_suit=0, declared=(), revealed=(), winner=0)
    assert sd._since_claim(Obs([])) == 0
    assert sd._since_claim(Obs(["a", "b", "c"])) == 3
    assert sd._since_claim(Obs([ev])) == 0
    assert sd._since_claim(Obs([ev, "a", "b"])) == 2
    assert sd._since_claim(Obs(["a", ev, "b"])) == 1


def test_the_paths_it_splits_on_are_real_paths():
    assert set(sd.IN_TIME) | set(sd.TOO_LATE) <= set(PATHS)
    assert not set(sd.IN_TIME) & set(sd.TOO_LATE)


def test_the_arm_is_the_one_whose_ceiling_is_under_study():
    """Arm C from prereg/deadline_signalling.md, read from that instrument."""
    from scripts4.signal_gate_confirm import ARMS
    assert sd.ARM == ARMS["C_measured"]


def test_the_seed_base_is_not_the_one_that_motivated_the_question():
    """A description must not be taken on the deals that produced the lead.

    The 52-vs-72 split came off `signal_gate_confirm`'s deals. Describing that
    population on the same shuffles, and then registering against it, is how a
    lead gets confirmed by its own evidence.
    """
    from scripts4.signal_gate_confirm import SEED0 as MOTIVATING
    assert sd.SEED0 != MOTIVATING


def test_it_records_the_engine_that_produced_it():
    src = (ROOT / "scripts4" / "signal_deadline.py").read_text()
    assert "engine_fingerprint()" in src


def test_it_says_in_the_payload_that_it_registers_nothing():
    """The file itself has to carry the warning, not only the docstring."""
    src = (ROOT / "scripts4" / "signal_deadline.py").read_text()
    assert '"descriptive": True' in src
    assert "registers_nothing" in src


def test_every_observable_the_instrument_records_is_compared():
    """A field recorded and never compared is a field nobody will notice is
    missing. The play loop's row and `KEYS` must agree."""
    src = (ROOT / "scripts4" / "signal_deadline.py").read_text()
    block = src[src.index('fires.append({'):src.index('"step": len(obs.history)')]
    recorded = set(__import__("re").findall(r'"(\w+)":', block)) | {"step"}
    bookkeeping = {"seat", "hs", "repeat"}
    assert recorded - bookkeeping == set(sd.KEYS), (
        f"recorded but not compared: {recorded - bookkeeping - set(sd.KEYS)}; "
        f"compared but not recorded: {set(sd.KEYS) - recorded}")


def test_p_best_is_carried_as_a_negative_control():
    """The gate's own threshold was widened 3.3x for three declarations in a
    thousand games. If this instrument finds `p_best` predictive, one of the
    two is wrong -- so it has to be recorded to be checkable."""
    assert "p_best" in sd.KEYS
    agent = (ROOT / "fish4" / "agent4.py").read_text()
    sig = agent[agent.index('"signal"'):agent.index('"signal"') + 700]
    assert "p_best" in sig, "the signal trace must carry the gate's own input"
