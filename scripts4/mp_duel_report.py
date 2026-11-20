"""Interval and breakdown for the Canadian-Fish-Demo duel.

The unit of resampling is the GAME. Unlike this project's own duels there is no
pairing to cluster on: each game has its own seed and its own deal, and the two
seat-parity sides are run as separate games rather than as a matched pair, so
the games are independent by construction and a plain bootstrap over them is
the right interval.

The headline is the BOOK MARGIN per game, not the win rate. Their game has 8
books, so 4-4 ties are common -- their own hard-vs-hard run ties a quarter of
its games -- and a win rate discards the size of a win. Both are reported, with
the margin first.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

BOOT = 2000
BOOT_SEED = 20_261_001


def boot(vals: list[float], boot: int = BOOT, seed: int = BOOT_SEED) -> list[float]:
    rng = random.Random(seed)
    n = len(vals)
    out = []
    for _ in range(boot):
        out.append(sum(vals[rng.randrange(n)] for _ in range(n)) / n)
    out.sort()
    return [out[int(0.025 * len(out))], out[min(len(out) - 1, int(0.975 * len(out)))]]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("path")
    a = ap.parse_args(argv)
    d = json.loads(Path(a.path).read_text())
    rows = d["rows"]
    if not rows:
        print("no rows", file=sys.stderr)
        return 1

    margin = [r["kScore"] - r["tScore"] for r in rows]
    win = [1.0 if r["kScore"] > r["tScore"] else 0.0 for r in rows]
    loss = [1.0 if r["tScore"] > r["kScore"] else 0.0 for r in rows]
    tie = [1.0 if r["kScore"] == r["tScore"] else 0.0 for r in rows]
    kb = [float(r["kScore"]) for r in rows]
    tb = [float(r["tScore"]) for r in rows]
    vd = [float(r["voids"]) for r in rows]

    n = len(rows)
    m, mci = sum(margin) / n, boot([float(x) for x in margin])
    w, wci = sum(win) / n, boot(win)
    print("=" * 72)
    print(f"  KRAKEN v1.1  vs  Canadian-Fish-Demo '{d['theirs']}'")
    print(f"  {n} games ({d['gamesPerSide']} per seat parity), their engine "
          f"arbitrating, spec {d['spec']}")
    print("=" * 72)
    print(f"  book margin a game      {m:+.4f}  [{mci[0]:+.4f}, {mci[1]:+.4f}]")
    print(f"  books: ours {sum(kb)/n:.3f}   theirs {sum(tb)/n:.3f}   "
          f"(8 a game, so a tie is 4-4)")
    print(f"  win rate of ALL games   {w:.4f}  [{wci[0]:.4f}, {wci[1]:.4f}]")
    print(f"  wins {int(sum(win))}   losses {int(sum(loss))}   "
          f"ties {int(sum(tie))}")
    dec = sum(win) + sum(loss)
    if dec:
        print(f"  win rate of DECIDED     {sum(win)/dec:.4f}   "
              f"(their own hard-vs-medium is 0.585)")
    print(f"  void books a game       {sum(vd)/n:.3f}")
    print("-" * 72)
    print(f"  illegal actions {d.get('illegal', 0)}   "
          f"bridge errors {d.get('errors', 0)}   "
          f"capped games {d.get('capped', 0)}")
    print("  Zero illegal actions is the bridge's self-test: their reducer")
    print("  rejects anything malformed, so a faithful translation shows up as")
    print("  a clean run and a broken one cannot hide.")
    print()
    print("  THEIR BOT IS NOT BRIDGED. It reads seatView() straight from its")
    print("  own engine, so it cannot be handicapped by anything here -- the")
    print("  failure mode that cost this project its last cross-engine")
    print("  headline is structurally absent. Any error in the bridge")
    print("  disadvantages US.")
    out = {"script": "scripts4/mp_duel_report.py", "source": a.path,
           "opponent": d["theirs"], "spec": d["spec"], "n_games": n,
           "margin_per_game": m, "margin_ci": mci,
           "books_ours": sum(kb) / n, "books_theirs": sum(tb) / n,
           "win_rate_all": w, "win_rate_ci": wci,
           "win_rate_decided": (sum(win) / dec) if dec else None,
           "wins": int(sum(win)), "losses": int(sum(loss)),
           "ties": int(sum(tie)), "voids_per_game": sum(vd) / n,
           "illegal": d.get("illegal", 0), "errors": d.get("errors", 0),
           "capped": d.get("capped", 0)}
    dest = Path(a.path).with_name(Path(a.path).stem + "_report.json")
    dest.write_text(json.dumps(out, indent=1) + "\n")
    print(f"\n  wrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
