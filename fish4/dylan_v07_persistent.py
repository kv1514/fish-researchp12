"""Their v0.7, bridged the way their own arbiter runs it: one agent per seat, alive for the deal.

WHY THIS EXISTS AND WHY IT IS A SEPARATE FILE.
`fish4/dylan_v07.py` is stateless: every decision spawns a fresh process and
replays the whole public log into a freshly `reset()` agent. That is the right
shape for the website, which reconstructs each session from its log on every
request, and it is the bridge every published cross-engine number in this
project was measured through.

`scripts4/shim_statefulness_parity.py` established that it is not the same
thing as their arbiter's incremental play, and established WHERE:

    their v0.2   0 of 323 decisions differ     scripted baseline
    their v0.3   0 of 338                      scripted baseline
    their v0.4   81 of 415   (19.5%)           the fitted belief arrives
    their v0.5   137 of 336  (40.8%)
    their v0.6   36 of 292   (12.3%)
    their v0.7   84 of 296   (28.4%)

Zero for both scripted baselines and large for everything from v0.4 on. That is
the version their fitted belief was introduced at, and it is the same boundary
at which `results/ladder_shape_comparison.json` found the two arbiters stop
agreeing.

So this module exists to PRICE that, not to replace anything. `dylan_v07.py` is
left exactly as it is: it produced the published numbers, and a file under
investigation is the last one to edit while investigating it. What ships to the
website does not change on the strength of an instrument.

HOW IT DIFFERS, AND ONLY HOW.
One `external_v07/fish_v07_persist` process per seat per deal. Events are fed
once, in order, as they happen; decisions are answered inline; the process is
closed at the end of the deal. The protocol, the card map, the rules line, the
frozen spec and the legality checking are all `dylan_v07.py`'s, reused rather
than reimplemented, so the ONLY difference between the two agents is whether
their engine gets to keep its state between decisions. That is what makes a
paired contrast between them a measurement of the statelessness and of nothing
else.

WHAT A PAIRED CONTRAST AGAINST IT MEANS. Positive means the stateless bridge
was costing them, i.e. our published margin is inflated by the bridge. It is
not by itself a corrected headline: this measures the two BRIDGES against each
other under our arbiter and our dialect, which is one of the several things
that separate our arbiter's answer from theirs.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from fish.engine import Ask, Claim, Pass
from fish.observation import Observation

from .dylan_v07 import BRIDGE_REV, DylanV07

_ROOT = Path(__file__).resolve().parents[1]

#: Built by `g++ -std=c++20 -O2 -I <their engine/src> -o
#: external_v07/fish_v07_persist external_v07/shim_persist.cpp -pthread`.
_BIN = _ROOT / "external_v07" / "fish_v07_persist"


class DylanV07Persistent(DylanV07):
    """The same policy and the same protocol, with the process kept alive.

    Inherits every translation from ``DylanV07`` -- the card bijection, the
    event encoding, the forced-declaration choice, the legality check and the
    counted fallback -- and overrides only the transport.
    """

    name = "dylan_v07_persistent"

    def __init__(self, timeout: float = 60.0, spec: str = None):
        super().__init__(timeout=timeout, spec=spec)
        if not _BIN.exists():
            raise FileNotFoundError(
                f"{_BIN} not built; compile external_v07/shim_persist.cpp")
        self._proc: subprocess.Popen | None = None
        #: How many events this seat's process has already been shown. The
        #: whole point of the class is that this is not zero at every decision.
        self._shown = 0

    # -- lifecycle -----------------------------------------------------------
    def begin_game(self, player: int, rules, seed: int) -> None:
        super().begin_game(player, rules, seed)
        self._close()
        self._shown = 0

    def _close(self) -> None:
        if self._proc is None:
            return
        try:
            if self._proc.stdin and not self._proc.stdin.closed:
                self._proc.stdin.write("QUIT\n")
                self._proc.stdin.flush()
                self._proc.stdin.close()
            self._proc.wait(timeout=30)
        except Exception:
            try:
                self._proc.kill()
            except Exception:
                pass
        self._proc = None

    def __del__(self):
        try:
            self._close()
        except Exception:
            pass

    # -- transport -----------------------------------------------------------
    def _run(self, lines: list[str]) -> str:
        """Answer one decision, feeding only what this seat has not yet seen.

        ``lines`` is the full script ``DylanV07._feed`` builds: header, the
        whole event history, TURN, DECIDE. Everything before the first event is
        sent once at boot; the events are sent as a tail; the DECIDE is sent
        every time.
        """
        head = [l for l in lines if not l.startswith("EV ")
                and not l.startswith("TURN ") and not l.startswith("DECIDE ")]
        evs = [l for l in lines if l.startswith("EV ")]
        tail = [l for l in lines if l.startswith("TURN ")
                or l.startswith("DECIDE ")]

        if self._proc is None:
            self._proc = subprocess.Popen(
                [str(_BIN)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                text=True, bufsize=1)
            for l in head:
                self._proc.stdin.write(l + "\n")
            self._shown = 0

        if len(evs) < self._shown:
            # The history got SHORTER, which means this process is being asked
            # about a different game than the one it has been watching. There
            # is no honest recovery: a persistent agent fed a history it did
            # not see is not the agent whose behaviour is being measured.
            raise RuntimeError(
                f"history shrank from {self._shown} to {len(evs)} events; "
                "begin_game must be called between deals")
        for l in evs[self._shown:]:
            self._proc.stdin.write(l + "\n")
        self._shown = len(evs)
        for l in tail:
            self._proc.stdin.write(l + "\n")
        self._proc.stdin.flush()

        out = self._proc.stdout.readline()
        if not out:
            rc = self._proc.poll()
            raise RuntimeError(f"persistent v07 shim died (rc={rc})")
        return out.strip()


#: Bumped independently of ``BRIDGE_REV`` because this is a different
#: instrument rather than a revision of that one; games measured through the
#: two are not interchangeable and must never be pooled.
PERSISTENT_REV = 1

__all__ = ["DylanV07Persistent", "PERSISTENT_REV", "BRIDGE_REV"]
