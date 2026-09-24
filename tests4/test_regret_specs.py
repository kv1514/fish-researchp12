"""The regret instruments' three policy roles must resolve independently.

WHY THIS TEST EXISTS
--------------------
`scripts4/ask_regret.py` drives three distinct roles from what used to be one
`SPEC`: the agents that HARVEST positions, the agents that ROLL OUT each
candidate, and the agent whose choice is the INCUMBENT. Collapsing them was not
harmless -- it is exactly what made two published regret figures incomparable,
because the champion arm changed the population and the continuation at the same
time as the policy under test.

The 2x2 that separates them only means anything if the knobs are real. A knob
that silently does nothing is this project's most expensive recurring failure:
in one session `path_ledger` wrote two arms to one filename, its `--arm` flag
with a space instead of `=` parsed as an EMPTY arm and ran the default, and
`exploitability`'s resume journal keyed on the deal index alone. All three
produced a plausible number rather than an error.

The specs are read from the environment at IMPORT time, so each case runs in its
own interpreter. Reloading in-process would test a reload, not the thing.
"""

from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_PROBE = (
    "import sys; sys.path.insert(0, %r)\n"
    "from scripts4.ask_regret import SPEC, HARVEST_SPEC, ROLLOUT_SPEC\n"
    "name = lambda d: 'champion' if d.get('w_lookahead') else 'objective'\n"
    "print(name(HARVEST_SPEC), name(ROLLOUT_SPEC), name(SPEC))\n" % ROOT)


def _roles(**env):
    e = dict(os.environ)
    for k in ("ASK_REGRET_SPEC", "ASK_REGRET_HARVEST_SPEC",
              "ASK_REGRET_ROLLOUT_SPEC", "ASK_REGRET_INCUMBENT_SPEC"):
        e.pop(k, None)
    e.update(env)
    out = subprocess.run([sys.executable, "-c", _PROBE], capture_output=True,
                         text=True, env=e, cwd=ROOT, timeout=180)
    assert out.returncode == 0, out.stderr[-2000:]
    return tuple(out.stdout.split())


def test_the_default_is_the_objective_in_isolation_everywhere():
    assert _roles() == ("objective", "objective", "objective")


def test_the_global_switch_moves_all_three():
    assert _roles(ASK_REGRET_SPEC="champion") == (
        "champion", "champion", "champion")


def test_each_role_can_be_set_alone():
    assert _roles(ASK_REGRET_HARVEST_SPEC="champion") == (
        "champion", "objective", "objective")
    assert _roles(ASK_REGRET_ROLLOUT_SPEC="champion") == (
        "objective", "champion", "objective")
    assert _roles(ASK_REGRET_INCUMBENT_SPEC="champion") == (
        "objective", "objective", "champion")


def test_a_role_override_beats_the_global_switch():
    """The 2x2's off-diagonal cells are exactly this case.

    `harvest=champion, rollout=objective` is the cell that separates the
    position distribution from the continuation policy, and it can only be
    reached if the specific override wins.
    """
    assert _roles(ASK_REGRET_SPEC="champion",
                  ASK_REGRET_ROLLOUT_SPEC="objective") == (
        "champion", "objective", "champion")


def test_an_unrecognised_value_falls_back_to_the_objective():
    """Never silently champion. A typo must not change the measured policy."""
    assert _roles(ASK_REGRET_SPEC="v06") == (
        "objective", "objective", "objective")


def test_the_banner_names_every_role():
    """Every run prints it, so a results file can never be misread later."""
    probe = ("import sys; sys.path.insert(0, %r)\n"
             "from scripts4.ask_regret import spec_banner\n"
             "print(spec_banner())\n" % ROOT)
    e = dict(os.environ)
    e["ASK_REGRET_HARVEST_SPEC"] = "champion"
    e.pop("ASK_REGRET_SPEC", None)
    e.pop("ASK_REGRET_ROLLOUT_SPEC", None)
    e.pop("ASK_REGRET_INCUMBENT_SPEC", None)
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                         text=True, env=e, cwd=ROOT, timeout=180)
    assert out.returncode == 0, out.stderr[-2000:]
    line = out.stdout.strip()
    assert "harvest=champion" in line, line
    assert "rollout=objective-only" in line, line
    assert "incumbent=objective-only" in line, line
