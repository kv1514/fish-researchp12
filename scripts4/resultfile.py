"""Where a run's results go, and what it may not overwrite.

WHY THIS EXISTS. `scripts4/signal_no_repeat_run.py` wrote to the fixed path
`results/signal_no_repeat.json` whatever seed base it ran, so the registered
re-run at 10,100,000 silently replaced the 9,900,000 run -- and the paper still
cites that filename for the 9,900,000 numbers. A reader who opens the cited
file gets a different figure for what looks like the same experiment. Nothing
warned anybody: the second run reported success and exited 0.

`scripts4/signal_vs_defer.py` carried the same hazard by default, across four
registrations sharing one output name.

Two rules, both cheap:

  * the default filename carries the seed base, so two runs of one instrument
    at two seeds cannot collide in the first place;
  * writing over an existing payload that was produced at a DIFFERENT seed or
    under a DIFFERENT registration is refused, because that is never what was
    meant. Re-running the same registration at the same seed still overwrites,
    which is the only case where clobbering is the intent.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The payload keys that identify a run. Two payloads that disagree on any of
#: them are different experiments and must not share a filename.
IDENTITY = ("seed_deal", "prereg", "n_deals")


def default_path(stem: str, seed: int) -> Path:
    """`results/<stem>_<seed>.json`. The seed is in the name on purpose."""
    return ROOT / "results" / f"{stem}_{seed}.json"


def _identity(payload: dict) -> dict:
    return {k: payload.get(k) for k in IDENTITY if k in payload}


def write(path: Path, payload: dict, force: bool = False) -> Path:
    """Write `payload`, refusing to replace a different experiment.

    Returns the path written. Raises SystemExit with both identities named
    rather than a bare "refused", because the useful information in this
    failure is WHICH run is about to be lost.
    """
    path = Path(path)
    if path.exists() and not force:
        try:
            old = json.loads(path.read_text())
        except (ValueError, OSError):
            old = None
        if isinstance(old, dict):
            a, b = _identity(old), _identity(payload)
            if a and b and a != b:
                raise SystemExit(
                    f"{path} already holds a DIFFERENT run and would be lost.\n"
                    f"  on disk:  {a}\n"
                    f"  this run: {b}\n"
                    f"Write to a different filename, or pass force=True if the "
                    f"run on disk is genuinely superseded.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1))
    return path
