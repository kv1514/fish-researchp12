"""Generate the paper's figures from the results files, and only from them.

Every number drawn here is read from the same ``results/*.json`` the manifest
(`scripts4/check_paper_numbers.py`) watches, so a figure cannot silently
disagree with the text: if a results file changes, both the prose check and
the regenerated figure move together, and a figure regenerated from stale
files fails the same review the prose would.

Design rules (print first): one axis per plot, position encodes the value,
color is one validated pair -- blue #2a78d6 for this project's shipped/live
series, orange #eb6834 for the contrast series -- plus grays for context.
Direct labels, no legend boxes where two labels do the job, no chartjunk.

    py scripts4/make_figures.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
FIGS = ROOT / "paper" / "figs"
FIGS.mkdir(exist_ok=True)

BLUE = "#2a78d6"
ORANGE = "#eb6834"
GRAY = "#52514e"
LGRAY = "#b8b7b2"

plt.rcParams.update({
    "font.family": "serif",
    "font.size": 9,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.linewidth": 0.7,
    "xtick.direction": "out",
    "ytick.direction": "out",
    "figure.dpi": 150,
})


def _load(name):
    return json.loads((ROOT / "results" / name).read_text())


def _duel(label):
    for line in (ROOT / "results" / "v04_duels.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("label") == label:
            last = r
    return last


# ---------------------------------------------------------------- fig 1
def fig_effects():
    """Forest plot: every pre-registered in-play effect, with its interval."""
    rows = []

    def fe_ci(v):
        fe, se = v["pooled"]["fe"], v["pooled"]["fe_se"]
        return fe, [fe - 1.96 * se, fe + 1.96 * se]

    d = _duel("FINAL: v04 champion vs v03 champion")
    rows.append(("Opponent model (v0.4 vs v0.3)", d["diff_mean"],
                 d["diff_ci"], "shipped", d["n_pairs"]))
    aw = _load("award_headline.json")
    rows.append(("Deployed vs v0.3, standard scoring", aw["estimate"],
                 aw["ci"], "shipped", aw["n_pairs"]))
    p = _load("precision_verdict.json")
    fe, ci = fe_ci(p)
    rows.append(("Posterior budget 160→480 draws", fe, ci, "shipped",
                 p["n_pairs"]))
    s = _load("settle_verdict.json")
    fe, ci = fe_ci(s)
    rows.append(("Belief-space lookahead", fe, ci, "shipped", s["n_pairs"]))
    c = _load("combined_verdict.json")
    rows.append(("Deployed config, direct", c["estimate"], c["ci"],
                 "shipped", c["n_pairs"]))
    a = _load("at_ask_verdict.json")
    fe, ci = fe_ci(a)
    rows.append(("At-ask-time depth", fe, ci, "not shipped", a["n_pairs"]))
    e = _load("endgame_ask_stack.json")
    rows.append(("Endgame ask correction (void era)", e["diff"], e["ci95"],
                 "not shipped", e["n_pairs"]))
    r4 = _load("r4_award_check.json")
    rows.append(("Endgame correction, award rule", r4["estimate"], r4["ci"],
                 "not shipped", r4["n_pairs"]))
    # The rule-matched (award-baseline) run; the void-era first run is in
    # the text. Same design, disjoint deals, same conclusion.
    f = _load("foreign_award_check.json")
    rows.append(("Endgame correction vs foreign v0.7", f["effect"],
                 f["ci95"], "context", f["n_pairs"]))
    w = _load("learned_weights_verdict.json")
    rows.append(("Learned whole-game ask weights", w["estimate"], w["ci"],
                 "not shipped", w["n_pairs"]))
    rows.sort(key=lambda r: -r[1])

    fig, ax = plt.subplots(figsize=(6.3, 3.45))
    ys = range(len(rows))[::-1]
    for y, (name, est, ci, kind, n) in zip(ys, rows):
        col = BLUE if kind == "shipped" else (
            ORANGE if kind == "context" else GRAY)
        ax.plot(ci, [y, y], color=col, lw=1.4, solid_capstyle="butt")
        ax.plot([est], [y], "o", ms=4.5, color=col)
        ax.annotate(f"{est:+.2f}", (max(ci[1], est) + 0.06, y),
                    va="center", fontsize=8, color=col)
        # n= column pinned to the plot edge so xlim stays data-tight.
        ax.annotate(f"n={n:,}", (0.01, y),
                    xycoords=("axes fraction", "data"),
                    va="center", ha="left", fontsize=7, color=GRAY)
    ax.axvline(0, color=LGRAY, lw=0.8, zorder=0)
    ax.set_yticks(list(ys))
    ax.set_yticklabels([r[0] for r in rows], fontsize=8.5)
    ax.set_xlabel("sets per duplicate deal-pair (95% CI)")
    ax.set_xlim(-1.75, 3.05)
    ax.spines["left"].set_visible(False)
    ax.tick_params(left=False)
    fig.tight_layout()
    fig.savefig(FIGS / "effects.pdf")
    plt.close(fig)


# ---------------------------------------------------------------- fig 2
def fig_ladder():
    """The deception picture: sibling rungs grow while true strength collapses."""
    sib_m, sib, sib_ci = [3, 4, 5, 9], [], []
    for m in sib_m:
        v = _load(f"endgame_m{m}_verdict.json")
        sib.append(v["diff"])
        sib_ci.append(v["ci95"])
    x = _load("xplay_sweep.json")["by_m"]
    xp_m = sorted(int(k) for k in x)
    xp = [x[str(m)]["margin"] for m in xp_m]
    xp_ci = [x[str(m)]["ci"] for m in xp_m]

    # One shared position map for BOTH panels: the panels share x, so every
    # series must be plotted through it or bars land under the wrong tick.
    pos = {m: i for i, m in enumerate([0, 2, 3, 4, 5, 9])}

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(6.3, 3.6), sharex=True,
                                 layout="constrained")
    xb = [pos[m] for m in sib_m]
    a1.bar(xb, sib, width=0.5, color=BLUE)
    for x0, v, ci in zip(xb, sib, sib_ci):
        a1.plot([x0, x0], ci, color="#0b3f78", lw=1.1)
        a1.annotate(f"+{v:.2f}", (x0, ci[1] + 0.12), ha="center", fontsize=8,
                    color=BLUE)
    a1.set_ylabel("rung gain vs sibling\n(sets/pair)", fontsize=8)
    a1.set_ylim(0, 5.2)

    xs = [pos[m] for m in xp_m]
    a2.axhline(0, color=LGRAY, lw=0.8, zorder=0)
    a2.plot(xs, xp, "-o", color=ORANGE, ms=4.5, lw=1.4)
    for xi, v, ci in zip(xs, xp, xp_ci):
        a2.plot([xi, xi], ci, color="#a33f14", lw=1.1)
    a2.annotate("loses to v0.3", (pos[9], xp[-1] - 0.55), ha="center",
                fontsize=8, color=ORANGE)
    a2.set_ylabel("margin vs v0.3\n(sets/game)", fontsize=8)
    a2.set_xticks(list(pos.values()))
    a2.set_xticklabels([str(m) for m in pos])
    a2.set_xlabel("endgame_m — how much of the game the correction covers")
    fig.savefig(FIGS / "ladder.pdf")
    plt.close(fig)


# ---------------------------------------------------------------- fig 3
def fig_support():
    """Exact deviation gain against belief support, m = 1 solved positions."""
    d = _load("ii_endgame.json")
    pts = [(r["support"], r["gain"]) for r in d["solved"]]
    fig, ax = plt.subplots(figsize=(6.3, 2.4))
    import random
    rng = random.Random(7)
    xs = [s + rng.uniform(-0.18, 0.18) for s, _ in pts]
    ys = [g + rng.uniform(-0.02, 0.02) for _, g in pts]
    ax.plot(xs, ys, "o", ms=2.4, color=LGRAY, alpha=0.7, mec="none",
            zorder=1)
    bands = [(1, 2), (3, 4), (5, 8), (9, 16), (17, 24)]
    bx, bm, blo, bhi = [], [], [], []
    for lo, hi in bands:
        sel = [g for s, g in pts if lo <= s <= hi]
        if len(sel) < 3:
            continue
        m = sum(sel) / len(sel)
        var = sum((v - m) ** 2 for v in sel) / (len(sel) - 1)
        se = (var / len(sel)) ** 0.5
        bx.append((lo + hi) / 2)
        bm.append(m)
        blo.append(m - 1.96 * se)
        bhi.append(m + 1.96 * se)
    for x0, lo, hi in zip(bx, blo, bhi):
        ax.plot([x0, x0], [lo, hi], color=BLUE, lw=1.3, zorder=3)
    ax.plot(bx, bm, "-o", ms=4.5, color=BLUE, lw=1.4, zorder=4)
    ax.set_xscale("log")
    ax.set_xticks([1, 2, 4, 8, 16, 24])
    ax.set_xticklabels(["1", "2", "4", "8", "16", "24"])
    ax.set_xlabel("belief support (consistent deals, log scale)")
    ax.set_ylabel("exact gain from\ndeviating (sets)", fontsize=8)
    ax.annotate(f"{len(pts)} solved m=1 positions; band means with 95% CI",
                (0.98, 0.04), xycoords="axes fraction", ha="right",
                fontsize=7.5, color=GRAY)
    fig.tight_layout()
    fig.savefig(FIGS / "support.pdf")
    plt.close(fig)


if __name__ == "__main__":
    fig_effects()
    fig_ladder()
    fig_support()
    for f in sorted(FIGS.glob("*.pdf")):
        print(f"{f.relative_to(ROOT)}  {f.stat().st_size:,} bytes")
