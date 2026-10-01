"""A runner must not overwrite another run's result, and the rule is one rule.

The defect this pins happened three times on 2026-08-28, by three routes:

  * a smoke test on a scratch journal dropped `cj_confirm.json` into results/;
  * an 8-game instrumentation check replaced an 1,800-game
    `declarer_holding_self.json` with eight games of noise;
  * `error_value.py` on the signalling journal replaced the stuck-gate fit --
    and the paper cites that file twice for +1.7898, which it no longer held.
    Nothing caught it. Every check in the repository passed.

Three local patches would have left the convention that produced them intact,
so `scripts4.journal.result_for` holds the rule and these tests hold the rule
to its word.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts4.journal import result_for

R = Path("/repo/results")


def _for(journal, canonical, name):
    return result_for(Path(journal), canonical_journal=Path(canonical),
                      canonical_name=name, results_dir=R)


def test_the_canonical_journal_keeps_the_historical_name():
    """Nothing already pointing at the old filename may break."""
    can = R / "tempo_journal.jsonl"
    assert _for(can, can, "tempo_confirm.json") == R / "tempo_confirm.json"


def test_a_second_seed_block_gets_its_own_name_inside_results():
    """The 8,000-game replication runs against a different champion than the
    1,000-game run. Sharing a filename would make the older figure vanish while
    the pre-registration still pointed at it."""
    can = R / "tempo_journal.jsonl"
    got = _for(R / "tempo_rep8k_journal.jsonl", can, "tempo_confirm.json")
    assert got == R / "tempo_rep8k_confirm.json"


def test_a_scratch_journal_writes_beside_itself_not_into_the_repository():
    can = R / "concent_journal.jsonl"
    got = _for("/tmp/scratch/cj.jsonl", can, "concent_confirm.json")
    assert got.parent == Path("/tmp/scratch"), got
    assert got.name == "cj_confirm.json", got


def test_a_name_that_does_not_share_the_journals_prefix_appends_the_stem():
    """error_value.json is written for stuck_gate_journal.jsonl, and the two
    share no prefix, so the stem is appended rather than substituted."""
    can = R / "stuck_gate_journal.jsonl"
    assert _for(can, can, "error_value.json") == R / "error_value.json"
    got = _for(R / "signal_gate_journal.jsonl", can, "error_value.json")
    assert got == R / "error_value_signal_gate.json", got


def test_the_journal_suffix_is_stripped_only_once_and_only_at_the_end():
    can = R / "a_journal.jsonl"
    got = _for(R / "journal_of_things_journal.jsonl", can, "a_confirm.json")
    assert got.name == "journal_of_things_confirm.json", got


def test_no_two_distinct_journals_can_collide_on_one_result_path():
    """The property that actually matters, checked rather than argued."""
    can = R / "tempo_journal.jsonl"
    journals = [can, R / "tempo_rep8k_journal.jsonl", R / "tempo2_journal.jsonl",
                Path("/tmp/a/tempo_journal.jsonl"),
                Path("/tmp/b/tempo_journal.jsonl")]
    got = [_for(j, can, "tempo_confirm.json") for j in journals]
    assert len(set(map(str, got))) == len(got), got


def test_an_extensionless_canonical_name_still_works():
    can = R / "x_journal.jsonl"
    assert _for(R / "y_journal.jsonl", can, "x_report").name == "y_report"
