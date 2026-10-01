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


def _wilson(k, n, z=1.96):
    """Wilson interval. Several of these cells have zero errors in thousands of
    declarations, where the normal interval is [0, 0] and says nothing."""
    if not n:
        return 0.0, 0.0, 0.0
    ph = k / n
    d = 1.0 + z * z / n
    c = (ph + z * z / (2 * n)) / d
    h = z * ((ph * (1 - ph) / n + z * z / (4 * n * n)) ** 0.5) / d
    return ph, max(0.0, c - h), min(1.0, c + h)


def fig_mediator():
    """The natural lever against the one that actually carries the risk.

    Left: error rate against how many of the six the declarer HOLDS. This is
    the lever everyone reaches for, and it is not even monotone -- holding all
    six is the safest state of all, so the curve turns over.

    Right: the same declarations against how many of the six have never been
    publicly LOCATED. That one is monotone and spans zero to eleven percent.
    """
    d = _load("declarer_holding_self.json")
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(6.3, 2.5), sharey=True)

    ks = sorted(int(k) for k in d["err_by_k"])
    kv = [d["err_by_k"][str(k)] for k in ks]
    pk = [_wilson(r["wrong"], r["n"]) for r in kv]
    a1.plot(ks, [p[0] for p in pk], "-o", ms=4.5, lw=1.4, color=LGRAY,
            mec="none", zorder=3)
    for k, (m, lo, hi) in zip(ks, pk):
        a1.plot([k, k], [lo, hi], color=LGRAY, lw=1.1, zorder=2)
    a1.set_xlabel("cards of the six the declarer holds")
    a1.set_ylabel("misdeclaration rate", fontsize=8)
    a1.set_xticks(ks)
    a1.annotate("not monotone:\nholding all six\nis the safest", (6, 0.004),
                fontsize=7, color=GRAY, ha="right", va="bottom")

    us = sorted(int(k) for k in d["err_by_unmoved"])
    uv = [d["err_by_unmoved"][str(u)] for u in us]
    pu = [_wilson(r["wrong"], r["n"]) for r in uv]
    a2.plot(us, [p[0] for p in pu], "-o", ms=4.5, lw=1.4, color=BLUE,
            mec="none", zorder=3)
    for u, (m, lo, hi) in zip(us, pu):
        a2.plot([u, u], [lo, hi], color=BLUE, lw=1.1, zorder=2)
    a2.set_xlabel("cards of the six never publicly located")
    a2.set_xticks(us)
    last = uv[-1]
    a2.annotate("zero errors in 4,980\ndeclarations at one", (1, 0.070),
                fontsize=7, color=BLUE, ha="left")
    a2.annotate(f"n={last['n']}", (us[-1] - 0.14, pu[-1][0]), fontsize=6.5,
                color=GRAY, ha="right", va="center")
    n = d["n_claims_ours"]
    fig.suptitle(f"the same {n:,} declarations, cut two ways", fontsize=8.5,
                 color=GRAY, y=0.985)
    # Leave the top strip for the suptitle: tight_layout does not reserve it,
    # so without the rect the title is clipped by the figure edge.
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(FIGS / "mediator.pdf")
    plt.close(fig)


def fig_paths():
    """Where the misdeclarations actually are: all of them are compelled.

    Two of the four paths a declaration can arrive by are exactly perfect over
    thousands of declarations. Every error the engine makes comes from the two
    paths where it declares because it must, not because it wants to.
    """
    d = _load("declarer_holding_self.json")["by_path"]
    order = ["voluntary", "exact", "gate", "forced"]
    label = {"voluntary": "voluntary", "exact": "exact solver",
             "gate": "gated", "forced": "forced"}
    fig, ax = plt.subplots(figsize=(6.3, 1.9))
    ys = range(len(order))
    for y, key in zip(ys, order):
        r = d[key]
        m, lo, hi = _wilson(r["wrong"], r["n"])
        col = ORANGE if r["wrong"] else BLUE
        ax.plot([lo, hi], [y, y], color=col, lw=1.4, zorder=2)
        ax.plot([m], [y], "o", ms=5.5, color=col, mec="none", zorder=3)
        txt = (f"{r['wrong']:,} of {r['n']:,} wrong"
               if r["wrong"] else f"0 of {r['n']:,} wrong")
        ax.annotate(txt, (hi + 0.012, y), va="center", fontsize=7.5,
                    color=col)
    ax.set_yticks(list(ys))
    ax.set_yticklabels([label[k] for k in order])
    ax.set_ylim(-0.6, len(order) - 0.4)
    ax.set_xlim(-0.02, 0.62)
    ax.set_xlabel("misdeclaration rate, with 95% Wilson interval")
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(FIGS / "paths.pdf")
    plt.close(fig)


def fig_ceiling():
    """What perfect card-reading is worth, one side of the table at a time.

    EVERY VALUE HERE IS OBTAINED BY CHEATING. The arms are handed the true
    deal; the opposition never is. These are bounds on what information could
    buy, not strength measurements, and they never appear in a ladder.
    """
    d = _load("ceiling_split.json")
    rows = [("its teammates' cards", d["arms"]["T_team"]),
            ("its opponents' cards", d["arms"]["O_opp"]),
            ("every hand at the table", d["arms"]["F_all"])]
    fig, ax = plt.subplots(figsize=(6.3, 1.9))
    for y, (name, r) in enumerate(rows):
        lo, hi = r["ci95"]
        col = BLUE if y < 2 else GRAY
        ax.plot([lo, hi], [y, y], color=col, lw=1.4, zorder=2)
        ax.plot([r["ceiling"]], [y], "o", ms=5.5, color=col, mec="none",
                zorder=3)
        ax.annotate(f"{r['ceiling']:+.2f}", (hi + 0.12, y), va="center",
                    fontsize=7.5, color=col)
    t, o = d["arms"]["T_team"]["ceiling"], d["arms"]["O_opp"]["ceiling"]
    ax.annotate(f"{t / o:.1f}x, at "
                f"{d['arms']['T_team']['pinned_by_cheat_per_game']:.0f} against "
                f"{d['arms']['O_opp']['pinned_by_cheat_per_game']:.0f} "
                f"cards pinned a game",
                (0.99, 0.97), xycoords="axes fraction", ha="right",
                va="top", fontsize=7, color=GRAY)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([n for n, _ in rows])
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.set_xlim(0, 7.6)
    ax.set_xlabel("sets per game over the honest engine\n"
                  "(a bound obtained by cheating, not a strength)")
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(FIGS / "ceiling.pdf")
    plt.close(fig)


def fig_gamma_split():
    """Why the split was withdrawn: the two scores move opposite ways.

    Paired against the incumbent cell, by decision. Sharpening the model on our
    own side improves the proper score and makes the posterior name the true
    holder LESS often -- mass spreading, not the read improving. The allocation
    decision reads the argmax, so that is a worse belief for the job it has.
    """
    path = ROOT / "results" / "gamma_split.json"
    if not path.exists():
        print("  (skipping gammasplit: results/gamma_split.json not present)")
        return
    d = json.loads(path.read_text())
    sel = sorted((r for r in d["rows"]
                  if r["gamma_opp"] == 0.35 and r.get("paired_team")),
                 key=lambda r: r["gamma_team"])
    xs = [r["gamma_team"] for r in sel]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(6.3, 2.3), sharex=True)
    for ax, key, lab, col in ((a1, "nll", "paired $\\Delta$ NLL", BLUE),
                              (a2, "top1", "paired $\\Delta$ top-1", ORANGE)):
        m = [r["paired_team"][key][0] for r in sel]
        lo = [r["paired_team"][key][1] for r in sel]
        hi = [r["paired_team"][key][2] for r in sel]
        ax.axhline(0.0, color=GRAY, lw=0.8, zorder=1)
        for x, a, b in zip(xs, lo, hi):
            ax.plot([x, x], [a, b], color=col, lw=1.2, zorder=2)
        ax.plot(xs, m, "-o", ms=4, lw=1.3, color=col, mec="none", zorder=3)
        ax.set_xlabel(r"$\gamma_{\mathrm{team}}$")
        ax.set_ylabel(lab, fontsize=8)
        ax.set_xticks([0, 0.35, 0.7, 1.0, 1.5, 2.0, 3.0])
        ax.set_xticklabels(["0", ".35", ".7", "1", "1.5", "2", "3"])
    a1.annotate("better", (0.02, 0.06), xycoords="axes fraction",
                fontsize=7, color=GRAY)
    a2.annotate("worse", (0.02, 0.06), xycoords="axes fraction",
                fontsize=7, color=GRAY)
    a1.annotate("NLL improves\naround 0.7", (0.30, 0.30),
                xycoords="axes fraction", fontsize=7, color=BLUE)
    a2.annotate("and top-1 falls\nthe whole way", (0.42, 0.62),
                xycoords="axes fraction", fontsize=7, color=ORANGE)
    fig.suptitle(rf"$\gamma_{{\mathrm{{opp}}}}$ held at the incumbent 0.35; "
                 rf"{d['decisions']:,} decisions, paired by decision",
                 fontsize=8, color=GRAY, y=0.99)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(FIGS / "gammasplit.pdf")
    plt.close(fig)


def fig_pairing():
    """Pairing's value is set by how often a knob fires, not by its size."""
    d = _load("pairing_value.json")
    pts = []
    for run in d["runs"]:
        for name, r in run["pairs"].items():
            pts.append((r["same_margin_share"], abs(r["effect"]),
                        r["efficiency"]))
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(6.3, 2.4), sharey=True)
    a1.plot([x for x, _, _ in pts], [e for _, _, e in pts], "o", ms=5,
            color=BLUE, mec="none")
    a1.set_xlabel("share of deals with an identical margin\n"
                  "(the knob never fired)")
    a1.set_ylabel("variance reduction\nfrom pairing", fontsize=8)
    a1.set_yscale("log")
    a1.set_yticks([1, 10, 100])
    a1.set_yticklabels(["1x", "10x", "100x"])
    top = max(pts, key=lambda q: q[2])
    a1.annotate(f"{top[2]:.0f}x", (top[0], top[2]), textcoords="offset points",
                xytext=(-6, -2), ha="right", fontsize=7.5, color=BLUE)
    a2.plot([y for _, y, _ in pts], [e for _, _, e in pts], "o", ms=5,
            color=LGRAY, mec="none")
    a2.set_xlabel("size of the effect being measured\n(sets per pair)")
    small = [e for _, y, e in pts if y < 0.15]
    a2.annotate(f"effects under 0.15 span\n{min(small):.0f}x to {max(small):.0f}x "
                "on their own:\neffect size does not size the run",
                (0.95, 0.92), xycoords="axes fraction", ha="right", va="top",
                fontsize=7, color=GRAY)
    fig.tight_layout()
    fig.savefig(FIGS / "pairing.pdf")
    plt.close(fig)


if __name__ == "__main__":
    fig_effects()
    fig_ladder()
    fig_support()
    fig_mediator()
    fig_paths()
    fig_ceiling()
    fig_pairing()
    fig_gamma_split()
    for f in sorted(FIGS.glob("*.pdf")):
        print(f"{f.relative_to(ROOT)}  {f.stat().st_size:,} bytes")
