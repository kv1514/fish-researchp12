"""Is a declared split consistent with ANY complete deal? An exact check.

``results/impossible_claims.json`` finds that 9.2% of m=1 claims declare a
split no complete consistent deal contains, and that every one of them nulls.
The champion is not confused about any individual card -- 0 of 1080 claims put
a card outside its own holder mask -- it is the JOINT that fails, exactly as
``claim4.best_for_half_suit``'s docstring warns: "cards compete for the same
quota slots, so per-card modes can be jointly impossible".

The m=1 measurement enumerated deals to detect this, which works only when one
half-suit is live: hand counts cover every live card, so fixing six of them
determines the rest. At higher m that enumeration is both wrong and expensive.

The general question is a feasibility problem, not an enumeration:

    given each live card's set of possible holders, and each player's number of
    cards in hand, is there an assignment of the remaining live cards that uses
    up exactly the remaining capacity?

That is bipartite matching with capacities, so Hall's condition decides it and
a small max-flow computes it. Cards are units of supply, players are sinks with
capacity equal to their unallocated hand size, and the declaration is feasible
exactly when every card can be placed.

WHY THIS IS NOT THE SAME AS "the belief allows each card"
---------------------------------------------------------
The per-card test is the marginal one and it passes on every claim the champion
has ever made here. Feasibility is the joint, and it is strictly stronger: a
declaration can satisfy every card's mask and still leave some player needing
to hold seven cards of a half-suit that has six, or leave a card with nowhere
legal to go once the declared cards are committed.
"""

from __future__ import annotations

from fish.cards import NUM_PLAYERS, half_suit_cards


def _max_flow(cards, allowed, cap):
    """Cards to players, one unit each. Returns how many can be placed.

    Ford-Fulkerson with a BFS augmenting path. The graph is tiny -- at most 54
    cards and 6 players -- so the simplest correct algorithm is the right one.
    """
    from collections import deque
    n = len(cards)
    # node ids: 0 = source, 1..n = cards, n+1..n+6 = players, n+7 = sink
    S, T = 0, n + NUM_PLAYERS + 1
    adj = {i: {} for i in range(T + 1)}

    def add(u, v, c):
        adj[u][v] = adj[u].get(v, 0) + c
        adj[v].setdefault(u, 0)

    for i in range(n):
        add(S, 1 + i, 1)
        for q in allowed[i]:
            add(1 + i, n + 1 + q, 1)
    for q in range(NUM_PLAYERS):
        if cap[q] > 0:
            add(n + 1 + q, T, cap[q])

    flow = 0
    while True:
        prev = {S: None}
        dq = deque([S])
        while dq and T not in prev:
            u = dq.popleft()
            for v, c in adj[u].items():
                if c > 0 and v not in prev:
                    prev[v] = u
                    dq.append(v)
        if T not in prev:
            return flow
        # bottleneck is always 1 here except on the player-to-sink edge
        v, b = T, float("inf")
        while prev[v] is not None:
            u = prev[v]
            b = min(b, adj[u][v])
            v = u
        v = T
        while prev[v] is not None:
            u = prev[v]
            adj[u][v] -= b
            adj[v][u] += b
            v = u
        flow += b


def declaration_feasible(obs, bel, half_suit: int, assignment) -> bool:
    """True when some complete deal consistent with the record contains it.

    ``assignment[i]`` is the declared holder of the i-th card of ``half_suit``.
    Returns True when the check cannot be run (nothing to place), because this
    is a filter that must only ever reject provable impossibilities.
    """
    me = obs.player
    counts = list(obs.hand_counts)
    declared = list(zip(half_suit_cards(half_suit), assignment))

    # The declaration itself must respect each card's own mask.
    for c, q in declared:
        if not (bel.current_holder_mask(c) >> q) & 1:
            return False

    # Commit the declared cards against their holders' capacity.
    for _, q in declared:
        counts[q] -= 1
        if counts[q] < 0:
            return False

    # Every OTHER live card still has to go somewhere legal.
    rest, allowed = [], []
    for c in range(len(bel.public_loc) if hasattr(bel, "public_loc") else 54):
        hs = c // 6
        if hs >= len(obs.set_winner) or obs.set_winner[hs] is not None:
            continue
        if hs == half_suit:
            continue
        if (obs.hand >> c) & 1:
            counts[me] -= 1
            if counts[me] < 0:
                return False
            continue
        mask = bel.current_holder_mask(c)
        opts = [q for q in range(NUM_PLAYERS) if (mask >> q) & 1 and q != me]
        if not opts:
            return False
        rest.append(c)
        allowed.append(opts)

    if not rest:
        return all(x == 0 for x in counts)
    return _max_flow(rest, allowed, counts) == len(rest)
