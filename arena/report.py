"""Render a tournament as the win-rate matrix people actually read."""

from __future__ import annotations

from arena.roster import ROSTER


def render_matrix(t: dict) -> str:
    field = t["field"]
    cells = t["cells"]
    short = {n: n.replace("kraken-", "k-") for n in field}
    out = []
    out.append(f"Every ordered matchup over {t['n_deals_per_cell']} duplicate "
               f"deals (each played twice, sides swapped; the PAIR is the "
               f"unit).")
    out.append("Rows played side A, columns side B. Cell = row's win rate.\n")
    head = "| Policy (side A) | " + " | ".join(short[c] for c in field) \
           + " | Row average |"
    out.append(head)
    out.append("|" + "---|" * (len(field) + 2))
    for a in field:
        row, vals = [], []
        for b in field:
            c = cells.get(f"{a}|{b}")
            if c is None:
                row.append("--"); continue
            v = c["win_rate"]
            vals.append(v)
            row.append(f"{v:.1%}" + ("*" if a == b else ""))
        avg = sum(vals) / len(vals) if vals else float("nan")
        out.append(f"| {a} | " + " | ".join(row) + f" | {avg:.1%} |")
    out.append("")
    diag = [(a, cells[f"{a}|{a}"]) for a in field if f"{a}|{a}" in cells]
    if diag:
        rates = [c["win_rate"] for _, c in diag]
        out.append(f"\\* Diagonal (a policy against a copy of itself) spans "
                   f"{min(rates):.1%}-{max(rates):.1%}. Agent randomness is "
                   f"seeded INDEPENDENTLY per side, so this is a real "
                   f"measurement of the harness's own noise and should "
                   f"straddle 50%. Under the harness default it would read "
                   f"exactly 50.0% whether or not anything worked.")
        # W/T/L for each self-match, because a diagonal cell landing on
        # exactly 50.0% is ambiguous from the rate alone: it is either a
        # small-sample coincidence (wins and losses that happen to balance)
        # or the structural tie the harness default produces. Only the split
        # tells them apart, and the difference is whether the check means
        # anything.
        out.append("")
        out.append("  self-match splits (W/T/L of pairs): " + ",  ".join(
            f"{a} {c['wins']}/{c['ties']}/{c['losses']}" for a, c in diag))
    return "\n".join(out)


def render_margins(t: dict) -> str:
    field, cells = t["field"], t["cells"]
    out = ["\nSet margin per game (row minus column), same runs:\n"]
    out.append("| Policy (side A) | " + " | ".join(
        c.replace("kraken-", "k-") for c in field) + " |")
    out.append("|" + "---|" * (len(field) + 1))
    for a in field:
        row = []
        for b in field:
            c = cells.get(f"{a}|{b}")
            row.append("--" if c is None else f"{c['margin']:+.2f}")
        out.append(f"| {a} | " + " | ".join(row) + " |")
    return "\n".join(out)


def render_field(field: list[str]) -> str:
    out = ["\nThe field:\n"]
    for n in field:
        out.append(f"- **{n}** — {ROSTER[n]['blurb']}")
    return "\n".join(out)
