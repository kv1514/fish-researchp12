"""ValueSearchAgent: paired search with a LEARNED leaf evaluator.

History (both steps were measured, see RESEARCH_LOG.md):

1. Rollout-based search lost badly to its own prior because world-to-world
   variance is ~2.4x the gap between candidate actions.
2. Common random numbers fixed the comparison, making search neutral.
3. A value net trained on BELIEF features then LOST 34-6 when applied
   inside determinized worlds: inside a sampled world every location is
   certain, so belief features (entropy, spread) took values the net never
   saw in training. That was a train/inference distribution mismatch, not a
   failure of value-guided search.

This agent uses a PERFECT-INFORMATION evaluator whose training distribution
matches its use: it scores fully-determined worlds sampled from the agent's
OWN beliefs. Nothing leaks; the world is a hypothesis drawn from legal
information, exactly as a rollout would be.

Leaves are evaluated in ONE batched forward pass per candidate action, which
keeps neural inference from dominating runtime.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import numpy as np

from ..cards import half_suit_mask, team_of
from ..engine import Action, Claim, GameState
from ..features import extract_perfect
from ..observation import Observation
from .probabilistic import ProbabilisticAgent
from .search import evaluate


class ValueSearchAgent(ProbabilisticAgent):
    name = "value_search"

    def __init__(self, model_path: Optional[str] = None, n_worlds: int = 16,
                 n_candidates: int = 6, n_samples: int = 32,
                 claim_threshold: float = 0.97, t_threshold: float = 1.0,
                 blend_static: float = 0.25, suit_bonus: float = 0.06):
        super().__init__(n_samples=n_samples, claim_threshold=claim_threshold,
                         suit_bonus=suit_bonus)
        self.model_path = model_path
        self.n_worlds = n_worlds
        self.n_candidates = n_candidates
        self.t_threshold = t_threshold
        self.blend_static = blend_static
        self._model = None
        self.uses_model = False

    def begin_game(self, player, rules, seed):
        super().begin_game(player, rules, seed)
        if self._model is None and self.model_path:
            p = Path(self.model_path)
            if p.exists():
                from ..learning.value_net import load_value_net
                self._model = load_value_net(p)
                self.uses_model = True

    # -- leaf evaluation ---------------------------------------------------------

    def _leaf_values(self, states: list[GameState]) -> list[float]:
        """Evaluate several post-action positions, batching the network call."""
        static = [evaluate(s, team_of(self.player)) for s in states]
        if self._model is None or not states:
            return static
        try:
            feats = np.stack([
                extract_perfect(s.hands, s.set_winner, s.turn, self.player,
                                self.rules.variant) for s in states])
            learned = self._model.values(feats)
        except Exception:
            return static
        w = self.blend_static
        return [(1 - w) * float(l) + w * s for l, s in zip(learned, static)]

    # -- policy -------------------------------------------------------------------

    def act(self, obs: Observation) -> Action:
        self.bel.update(obs)
        if obs.must_pass():
            return max(obs.legal_passes(),
                       key=lambda p: obs.hand_counts[p.teammate])
        worlds = self._sample_worlds()
        claim_cands = self._claim_candidates(obs, worlds)
        best_claim = max(claim_cands, key=lambda t: t[0]) if claim_cands else None
        if best_claim and best_claim[0] >= self.claim_threshold:
            return best_claim[1]
        asks = obs.legal_asks()
        if not asks or (self.stalled(obs) and obs.claimable_half_suits()):
            return self._forced_claim(obs, worlds)

        n = len(worlds)
        scored = []
        for a in asks:
            hits = sum(1 for w in worlds if w[a.target] & (1 << a.card))
            strength = (obs.hand & half_suit_mask(a.card // 6)).bit_count()
            scored.append((hits / n + self.suit_bonus * strength, a))
        scored.sort(key=lambda t: -t[0])
        candidates: list[Action] = [a for _, a in scored[: self.n_candidates]]
        if best_claim and best_claim[0] >= 0.5:
            candidates.append(best_claim[1])
        if len(candidates) == 1:
            return candidates[0]

        sim_worlds = worlds[: self.n_worlds]
        values: list[list[float]] = []
        for action in candidates:
            states, valid = [], []
            for w in sim_worlds:
                st = GameState.from_components(
                    obs.rules, list(w), obs.turn, list(obs.set_winner))
                try:
                    st.apply(self.player, action)
                except Exception:
                    valid.append(False)
                    continue
                valid.append(True)
                states.append(st)
            vals = self._leaf_values(states)
            it = iter(vals)
            values.append([next(it) if ok else math.nan for ok in valid])

        base = values[0]
        best_idx, best_stat = 0, 0.0
        for i in range(1, len(candidates)):
            diffs = [v - b for v, b in zip(values[i], base)
                     if not (math.isnan(v) or math.isnan(b))]
            if len(diffs) < 3:
                continue
            mean = sum(diffs) / len(diffs)
            var = sum((d - mean) ** 2 for d in diffs) / (len(diffs) - 1)
            se = math.sqrt(var / len(diffs)) if var > 0 else 0.0
            stat = (math.inf if mean > 0 else 0.0) if se == 0 else mean / se
            if stat > self.t_threshold and stat > best_stat:
                best_idx, best_stat = i, stat
        return candidates[best_idx]
