# Literature / Fish: prior-art and methods survey

Prepared for the Fish engine research project (FishBot). Scope: what the
published literature actually establishes that bears on building a strong agent
for **Literature** (Fish, Canadian Fish, Russian Fish), and what it does *not*
establish.

Game under study, per `SPEC.md`: 6 players, two teams of 3 in alternating seats,
54-card deck partitioned into nine 6-card half-suits, ASK(target, card) against a
named opponent, CLAIM(half_suit, assignment) requiring an *exact* declaration of
the distribution of a half-suit within the claimant's own team. No legal private
communication. Every card movement is public. Consequently the hidden state
reduces to constraints on the initial deal, and the current hidden state is a
deterministic, publicly-computable function of (initial deal, public history).

## How to read this document

Every citation below was retrieved and checked during this survey. Where a claim
rests on the abstract or search metadata rather than the full text, that is
flagged inline. Where no source exists, the document says so explicitly instead
of guessing. Numbers quoted from papers are quoted from the papers.

Confidence tags used:
- **[verified]** primary text read during this survey
- **[abstract]** abstract or publisher record read, full text not read
- **[gap]** searched for and not found; treat as absent from the literature

---

## 1. Literature / Fish specifically

### (a) What is known

**There is no peer-reviewed AI research on Literature.** This survey searched for
"Literature card game", "Canadian Fish", "Russian Fish", "Fish card game" in
combination with MCTS, belief state, imperfect information, reinforcement
learning, determinization and thesis/report terms, across the web and arXiv. No
academic paper, thesis, or technical report on the game was found. **[gap]**

What does exist:

1. **Rules references.** The canonical English rule statements are John McLeod's
   Pagat entry and the Wikipedia article. Both are cited by essentially every
   implementation.
   - John McLeod, "Literature", *pagat.com*.
     https://www.pagat.com/quartet/literature.html
   - "Literature (card game)", *Wikipedia*.
     https://en.wikipedia.org/wiki/Literature_(card_game)

2. **Open-source implementations with bots, none research-grade.**
   - `neelsomani/literature` (Neel Somani, MIT licence): a Python Literature
     implementation with Q-learning bots. Its own documentation states that the
     bots only consider asking for a card known to be absent from a target when
     no other move exists, that the state encoding contains only first-order
     knowledge with no nested "what others know that others know", that training
     hits infinite loops and games are truncated at 200 moves with noise added
     to move scores, and that training is limited to the 4-player variant.
     https://github.com/neelsomani/literature **[verified]**
   - `Dynosol/playfish.io`, a React web implementation of Fish with the Pagat
     rules. https://github.com/Dynosol/playfish.io **[abstract]**
   - `Raghav-Sao/literature`, an online implementation advertising bot play.
     https://github.com/Raghav-Sao/literature **[abstract]**
   - `iuruoy-shao/fish`, an RL agent for Fish.
     https://github.com/iuruoy-shao/fish **[abstract]**

   None of these publish an evaluation protocol, a strength measurement against
   a credible baseline, or an exact belief representation. They are prior art in
   the "someone has built this" sense only.

3. **Go Fish is now in a standard benchmark, with a directly relevant negative
   result.** Valet includes Go Fish (classified as "Quartet", USA, 1850, 4
   players, French deck) among 21 traditional imperfect-information card games,
   encoded in the RECYCLE card-game description language.
   - Mark Goadrich, Achille Morenville, Éric Piette, "Valet: A Standardized
     Testbed of Traditional Imperfect-Information Card Games", arXiv:2603.03252,
     March 2026. https://arxiv.org/abs/2603.03252 **[verified]**

   Two findings from that paper matter to us. First, Go Fish and President have
   the *highest branching factors* in the testbed, which the authors attribute to
   core mechanics rather than to a modelling artefact. Second, and more
   important: in their MCTS-vs-random baseline, "games such as Go Fish and Crazy
   Eights show little separation between MCTS and random play, likely because
   CardStock's determinizations account only for visibility and not for
   information inferred from action history." That is a published, citable
   demonstration that naive determinization is close to worthless in the
   ask-and-give family precisely because the entire strategic content lives in
   inference from the *choice* of ask, not in card visibility.

4. **Deduction-game framing.** The closest published methodological framing is
   entropy-directed search for deduction games.
   - Fandi Meng, Simon Lucas, "Deduction Game Framework and Information Set
     Entropy Search", IEEE Conference on Games (CoG), 2024. arXiv:2407.21178.
     https://arxiv.org/abs/2407.21178 **[abstract]**
     Proposes Information Set Entropy Search (ISES), a forward search driven by
     Shannon-entropy reduction of the information set, evaluated on eight
     deduction games, reported to beat SO-ISMCTS under short decision times.
     Caveat: the abstract describes ISES as solving *single-player* deduction
     games, so the transfer to a 3v3 adversarial-team setting is not immediate.

5. **Go Fish game theory.** No published game-theoretic analysis of Go Fish was
   found. Searches returned strategy blog posts and one course resource only.
   **[gap]** Treat "Go Fish is unsolved / unstudied" as accurate but low-value:
   the game is trivial compared to Literature (no teams, no declaration, no
   half-suit constraint on legal asks).

### (b) What transfers to Literature

The genuine absence is the opportunity. Concretely, what is missing from the
literature and is defensible as a contribution:

- No published belief representation for a game where every card motion is
  public and hidden state is exactly the initial deal.
- No published treatment of an *exact-declaration* scoring mechanic. The CLAIM
  action is unusual: it is a one-shot, all-or-nothing bet on a 6-dimensional
  joint assignment, which is exactly the kind of action that breaks
  determinized search (see §2).
- No published analysis of a game where the coordination channel between
  teammates is a *public, adversarially observed, costly* action (the ask), as
  opposed to Hanabi's free hint or Bridge's ritualised bidding.

### (c) Recommendations

1. State the prior-art claim precisely in the paper: "we are not aware of
   peer-reviewed AI work on Literature; the closest benchmarked relative is Go
   Fish in Valet (Goadrich et al. 2026), where determinized MCTS is reported to
   be near-indistinguishable from random play." Do not claim the *family* is
   unstudied.
2. Cite Valet's Go Fish result as motivation for belief-weighted rather than
   visibility-only determinization. It is the single most on-point published
   empirical fact we have.
3. Consider contributing a Literature ruleset to Valet/RECYCLE or OpenSpiel.
   Cheap, and it converts "no benchmark exists" from a complaint into an asset.

---

## 2. Perfect-Information Monte Carlo and determinization pathologies

### (a) What is known

**Frank & Basin's two errors.** The formal critique of sampling perfect-
information worlds and solving them.

- Ian Frank, David Basin, "Search in games with incomplete information: A case
  study using Bridge card play", *Artificial Intelligence* 100(1–2):87–123, 1998.
  https://www.sciencedirect.com/science/article/pii/S0004370297000829
  (An ICGA Journal note on the same work appears as *ICGA Journal* 21(3):194,
  1998, https://journals.sagepub.com/doi/10.3233/ICG-1998-21308. Cite the AIJ
  version.) **[verified via the AAAI-10 and Cowling et al. accounts]**
- Ian Frank, David Basin, "A theoretical and empirical investigation of search in
  imperfect information games", *Theoretical Computer Science* 252(1–2):217–256,
  2001.
  https://www.sciencedirect.com/science/article/pii/S0304397500000839

The two errors, as restated verbatim in the primary sources read for this survey:

- **Strategy fusion.** "PIMC search (incorrectly) believes it can use a different
  strategy in each world, whereas in reality there are situations (or information
  sets) which consist of multiple perfect information scenarios. In the full
  imperfect information game, a player cannot distinguish between these
  situations, and must choose the same strategy in each one" (Long et al. 2010,
  p. 135). Long et al. add a sharp structural condition: strategy fusion only
  actually *causes a move-selection error* when (i) there are anti-correlated
  moves on one part of the tree and (ii) there is a move guaranteed better on the
  other part. Otherwise PIMC merely overestimates the value.
- **Non-locality.** "In an imperfect information game, a node's value may depend
  on other regions of the game tree not contained within its subtree, primarily
  due to the opponent's ability to direct the play towards regions of the tree
  that he knows (or at least guesses) are favorable for him, using private
  information that he possesses but we do not" (Long et al. 2010, p. 135).

**Long et al.'s three properties.** The paper that explains why PIMC nonetheless
works in some domains.

- Jeffrey Long, Nathan R. Sturtevant, Michael Buro, Timothy Furtak,
  "Understanding the Success of Perfect Information Monte Carlo Sampling in Game
  Tree Search", *Proceedings of AAAI-10*, pp. 134–140, 2010.
  https://ojs.aaai.org/index.php/AAAI/article/view/7562 **[verified, full text]**

Definitions, quoted from p. 136:

- **Leaf correlation, `lc`**: "gives the probability all sibling, terminal nodes
  have the same payoff value. Low leaf node correlation indicates a game where it
  is nearly always possible for a player to affect their payoff even very late in
  a game."
- **Bias, `b`**: "determines the probability that the game will favor a
  particular player over the other. With very high or very low bias, we expect
  there to be large, homogeneous sections of the game, and as long as a
  game-playing algorithm can find these large regions, it should perform well."
- **Disambiguation factor, `df`**: "determines how quickly the number of nodes in
  a player's information set shrinks with regard to the depth of the tree. [...]
  If `df` is 0, then p never gains any direct knowledge of his opponent's private
  information. If `df` is 1, the game collapses to a perfect information game."

Synthetic-tree generative semantics (needed if we want to reproduce their
figures): sibling terminal pairs are made identical with probability `lc` and
anti-correlated otherwise; correlated pairs take value +1 with probability `b`;
each time a player is to move, each of their information sets is recursively
split in half with probability `df`. Trees are depth 8 with 8 worlds per player
(chance-node degree 64), 10,000 trees per parameter triple, 2 games per tree with
sides swapped.

Measurement protocol for real games (p. 136, and applied on pp. 139): sample
terminal nodes by random playouts; collapse chains of a single legal move; find
"pre-terminal" nodes where *all* moves lead directly to terminal positions;
declare them correlated if all move values are equal; estimate bias as the
fraction of correlated pre-terminal nodes that are wins for the reference player;
estimate `df` by comparing the number of consistent worlds now against the number
when that player last moved, then converting the average reduction ratio.

Measured results:

| Game | `lc` | `df` | Notes |
|---|---|---|---|
| Skat (suit, grand, null) | 0.8 to ~1.0 | ≈0.6 | bias varies by hand |
| Hearts | 0.8 to ~1.0 | ≈0.6 | 3,000 games, 500 sample points each |
| Kuhn poker | 0.5 | 0 | bias 0.5, by inspection |

Consequences reported: for Skat, PIMC "loses only 0.1 points per game against
equilibrium and gains 0.4 points over random play" on a [-1,1] payoff scale. In
Skat endgames with three tricks left, ~15% of games are still undecided, and on
those PIMC costs 0.42 tournament points per deal against a CFR solution; averaged
over all deals that is 0.063 TP per deal, i.e. ~11.3 TP over a 180-deal
tournament against an empirical TP standard deviation of 778. Their conclusion:
"the advantage over PIMC in the endgame hardly matters for winning tournaments."

The critical counterweight, from the same paper's Table 1 (Kuhn poker, average
payoff):

| Player | vs Nash | vs Best-Response |
|---|---|---|
| Random (p1) | -0.161 | -0.417 |
| Random (p2) | -0.130 | -0.500 |
| PIMC (p1) | -0.056 | -0.083 |
| PIMC (p2) | +0.056 | -0.166 |

PIMC achieves the equilibrium payoff against a Nash opponent because it never
takes dominated actions, yet loses 0.166 as p2 against a best-responder where
+0.056 was available. The authors call out exploitability as the major unaddressed
issue: "the performance of PIMC search could be substantially worse against a
player that attempts to exploit its mistakes."

**GIB.** The canonical PIMC success story, and the origin of most of the practical
fixes.

- Matthew L. Ginsberg, "GIB: Imperfect Information in a Computationally
  Challenging Game", *Journal of Artificial Intelligence Research* 14:303–358,
  2001. https://www.jair.org/index.php/jair/article/view/10279 (also
  arXiv:1106.0669). **[abstract]**
  Five contributions: partition search; practical Monte Carlo on realistic
  problems; a focus on *achievable sets* to fix Monte Carlo's problems; alpha-beta
  extended from total orders to distributive lattices; squeaky-wheel optimization
  for cardplay. Long et al. note that the lattice enhancement bought only 0.1
  IMPs per deal, and only for declarer play where GIB was already strongest.

**The achievable-set idea, modernised.** alpha-mu attacks strategy fusion and
non-locality directly by carrying vectors of per-world outcomes rather than
scalars.

- Tristan Cazenave, Véronique Ventos, "The alpha-mu Search Algorithm for the Game
  of Bridge", arXiv:1911.07960, 2019; also in *Monte Carlo Search* (Springer
  CCIS), 2021. https://arxiv.org/abs/1911.07960 **[abstract]**
- Tristan Cazenave, Swann Legras, Véronique Ventos, "Optimizing alpha-mu",
  arXiv:2101.12639, 2021. https://arxiv.org/abs/2101.12639 **[abstract]**
  Reported to outperform PIMC in Bridge and to solve Bridge endings exactly while
  remaining anytime.

**Russell & Norvig's objection, and Ginsberg's concurrence.** Quoted through
Cowling et al. 2012 §III (read in full for this survey): determinization "will
never choose to make an information gathering play (i.e., a play that causes an
opponent to reveal some hidden information) nor will it make an information
hiding play (i.e., a play that avoids revealing some of the agent's hidden
information to an opponent)."

- Stuart Russell, Peter Norvig, *Artificial Intelligence: A Modern Approach*, 2nd
  ed., Prentice Hall, 2002 (the "averaging over clairvoyancy" passage).

### (b) What transfers to Literature

**Disambiguation factor is very high, probably the highest of any studied card
game.** Every ASK is a hard public constraint on the deal. A single ask
simultaneously establishes: the asker holds at least one card of the named
half-suit; the asker does not hold the named card; and (on failure) the target
does not hold the named card, or (on success) the exact card moves publicly.
Skat and Hearts sit at `df ≈ 0.6`. Literature should be well above that. On Long
et al.'s axes this is *favourable* to PIMC in absolute terms and strongly
favourable relative to random play.

**Leaf correlation is the open question, and there is reason to think it is
low.** The CLAIM mechanic is an anti-correlated sibling pair by construction: at
a node where a claim is available, one declared assignment scores and every other
declared assignment loses the half-suit. That is exactly the "low `lc`" structure
Long et al. identify as PIMC's worst case: "PIMC search always believes that the
critical decisions are going to come 'later' and that what it does higher up the
tree does not actually matter." We should not assume Skat's numbers.

**Strategy fusion on CLAIM is catastrophic and should be treated as a hard
design constraint, not a tuning issue.** In any determinization, the searcher
*knows* the true half-suit layout, so the claim action evaluates as a guaranteed
win, and the assignment it would declare differs across determinizations. A PIMC
agent therefore (i) massively overestimates the value of claiming, and (ii) has no
coherent single assignment to declare. This is the textbook Frank-Basin failure
mode instantiated in a mechanic that decides the entire score of the game. Any
result showing determinized search choosing claims is measuring an artefact.

**Non-locality is strongly present.** A failed ask hands the turn to the target,
so opponents actively steer the game using private information. Additionally, the
*absence* of an obvious ask is informative (the asker may lack a card in that
half-suit, or may be hiding). Determinized search cannot represent either.

**Information hiding matters more here than in Skat.** Asking reveals your own
half-suit holdings to three opponents. In Skat, the equivalent leak is bounded by
suit-following rules; in Literature the leak is chosen voluntarily by the actor.
The Russell-Norvig objection therefore bites harder.

**Exploitability matters more than in Skat.** The Kuhn table above is the
relevant precedent, not the Skat tournament-point argument. Our opponents observe
our ask policy directly and can adapt.

### (c) Recommendations

1. **Measure `lc`, `b`, `df` for Literature using Long et al.'s exact protocol
   and publish the numbers.** This is cheap, is a citable contribution in its own
   right (they explicitly ask for "a game that is in between the extremes"), and
   it tells us before we build anything whether PIMC-family methods are the right
   family. Report the distribution, not a point: they show Skat is "a cloud of
   parameters depending on the strength of each hand."
2. **Forbid determinized search from selecting CLAIM.** Route CLAIM through an
   explicit belief computation (§5). The claim decision is
   `EV = P(exact) * V_win + (1 - P(exact)) * V_lose`, and the assignment to
   declare is the MAP assignment under the belief, both of which the exact DP in
   §5 computes without search.
3. **Instrument the ask policy for information value.** Determinized search
   cannot value probing asks. If we want them, they must come from an explicit
   entropy or belief-sharpening term (cf. Meng & Lucas 2024) or from a search
   that carries per-world vectors rather than scalars (alpha-mu).
4. **Consider alpha-mu for the claim/no-claim and endgame decisions.** It is the
   published method that directly attacks strategy fusion, it is anytime, and our
   endgames are small.

---

## 3. Information Set MCTS, determinization allocation, variance reduction

### (a) What is known

- Peter I. Cowling, Edward J. Powley, Daniel Whitehouse, "Information Set Monte
  Carlo Tree Search", *IEEE Transactions on Computational Intelligence and AI in
  Games* 4(2):120–143, 2012.
  https://eprints.whiterose.ac.uk/id/eprint/75048/ **[verified, full text]**
- Edward J. Powley, Peter I. Cowling, Daniel Whitehouse, "Information capture and
  reuse strategies in Monte Carlo Tree Search, with applications to games of
  hidden information", *Artificial Intelligence* 217:92–116, 2014.
  https://www.sciencedirect.com/science/article/pii/S0004370214001052
  **[abstract]** (the ICARUS framework)
- Daniel Whitehouse, Edward J. Powley, Peter I. Cowling, "Determinization and
  information set Monte Carlo Tree Search for the card game Dou Di Zhu",
  *IEEE CIG*, 2011. https://ieeexplore.ieee.org/document/6031993/ **[abstract]**

The three algorithms, as defined in the 2012 paper:

- **SO-ISMCTS** (single-observer): one tree of information sets from the root
  player's viewpoint; each iteration samples a determinization and restricts
  selection/expansion to actions legal in it. Fixes the first flavour of strategy
  fusion (a deterministic solver making different decisions in different states
  of one information set).
- **SO-ISMCTS + POM** (partially observable moves): groups opponent moves that
  the root player cannot distinguish. Plain SO-ISMCTS "suffers from strategy
  fusion, as it treats all opponent moves as fully observable."
- **MO-ISMCTS** (multiple-observer): a separate tree per player, each built over
  that player's information sets; addresses strategy fusion arising from
  partially observable moves.

**The subset-armed bandit problem**, in the authors' words (§IV-B): "we have a
multiarmed bandit where only a subset, and generally a different subset, of the
arms is available on each trial." Their fix is to replace the parent visit count
in UCB1 with "the number of trials in which the parent was visited *and* node was
available"; without it, "rare actions [...] are over-explored [...] resulting in
a disproportionately large UCB value." They flag the residual defect explicitly:
"it does not allow an action to have a different value depending on which subset
of actions it belongs to (instead the value is the average across all visited
subsets)", and note that an in-depth analysis "is a subject for future work."
That analysis does not appear to have been published. **[gap]**

**Why ISMCTS misallocates determinizations, from the primary source.** The 2012
paper surveys belief distributions (poker, Scrabble, Skat) and then states
plainly: "We do not consider belief distributions in this paper." ISMCTS as
published samples determinizations *uniformly* from the information set. Every
subsequent claim that ISMCTS "misallocates determinizations" reduces to this:
computational effort is spread in proportion to the uniform measure on consistent
worlds rather than the posterior measure, so implausible worlds receive the same
budget as plausible ones. The published fix in trick-taking games is to replace
the uniform sampler with a learned posterior (§6).

**Hidden-information leakage into opponent models.** A second, distinct defect:
if the playout/opponent policy is run on a determinization consistent with *our*
hand, the simulated opponents implicitly know our hand.

- Timothy Furtak, Michael Buro, "Recursive Monte Carlo search for imperfect
  information games", *IEEE CIG*, 2013.
  https://skatgame.net/mburo/ps/recmc13.pdf **[abstract]**
  Introduces recursive imperfect-information Monte Carlo (IIMC / IIMCTS) with
  bounded recursion depth in playouts, motivated by exactly this leak: "the player
  leaks private information to their playout adversaries by only sampling states
  consistent with the player's private information." Reported as producing the
  state-of-the-art Skat player of its time.
- James Goodman, "Re-determinizing Information Set Monte Carlo Tree Search in
  Hanabi", arXiv:1902.06075, 2019. https://arxiv.org/abs/1902.06075 **[abstract]**
  Winner of the CIG 2018 Hanabi competition. Re-determinizes inside the search to
  prevent "a leakage of hidden information into opponent models that can occur in
  IS-MCTS, and is particularly severe in Hanabi." Uses a learned leaf evaluator to
  fit a 40 ms per-move budget, and a simple Bayesian opponent model for the mixed
  track.

**Smooth UCT.**

- Johannes Heinrich, David Silver, "Smooth UCT Search in Computer Poker",
  *IJCAI 2015*, pp. 554–560.
  https://www.semanticscholar.org/paper/8db6005fda5ed2d5d0e011a1ac14d26386e630b9
  **[abstract]** Mixes the agent's own average policy into self-play action
  selection, inheriting the fictitious-play intuition. Outperformed UCT in Limit
  Texas Hold'em and won three silver medals at the 2014 ACPC.
- Johannes Heinrich, David Silver, "Deep Reinforcement Learning from Self-Play in
  Imperfect-Information Games", arXiv:1603.01121, 2016.
  https://arxiv.org/abs/1603.01121 **[abstract]** (NFSP; the deep successor.)

**Multi-player caveat.**

- Nathan R. Sturtevant, "An Analysis of UCT in Multi-Player Games", *ICGA
  Journal* 31(4):195–208, 2008.
  https://webdocs.cs.ualberta.ca/~nathanst/papers/mpuct_icga.pdf **[abstract]**
  UCT in a multi-player game computes a *mixed*-strategy equilibrium, whereas
  max^n computes a pure-strategy one. Relevant because Literature is 6-sided even
  though it is 2-team.

**Common random numbers and paired comparison.** I could not find a peer-reviewed
game-search paper whose contribution is CRN or paired-comparison variance
reduction in MCTS. **[gap]** What exists is (i) CRN as a standard simulation
technique and (ii) its game-AI instantiation as duplicate/mirrored deals, used
without fanfare in the game-AI papers themselves:

- Art B. Owen, *Monte Carlo theory, methods and examples*, 2013, Ch. 8 "Variance
  reduction". https://artowen.su.domains/mc/Ch-var-basic.pdf **[abstract]**
- Long et al. 2010 (above) state their protocol as: "we generated 10000 synthetic
  trees and played 2 games per tree, with the competing players swapping sides in
  the second game." **[verified]** That *is* CRN over the chance node.
- Solinas et al. 2019 (§6) similarly report tournaments with seatings "reversed".
  **[verified]**

### (b) What transfers to Literature

- **The subset-armed bandit is unavoidable in Literature.** By SPEC §4.1, a
  player's legal asks depend on their own hand (must hold a card of the half-suit,
  must not hold the named card). So when the observer is not the player to act,
  states in one information set have different action sets. Any ISMCTS variant we
  build needs the availability-count correction, and inherits its known defect
  (action value averaged across subsets).
- **MO-ISMCTS is the structurally correct variant**, because Literature has
  partially observable opponent moves in a subtle sense: opponents observe the ask
  and the transfer, but they do not observe *why* it was chosen; and the legality
  of the ask itself carries information. SO-ISMCTS would treat opponent moves as
  fully observable and thereby import strategy fusion.
- **The information leak is the leading candidate explanation for the ROADMAP's
  open problem #1** ("no search variant has yet been significantly BETTER than the
  belief policy"). If our playouts sample determinizations consistent with our own
  hand and then run an opponent policy on them, our simulated opponents behave as
  if they can see our hand, which systematically distorts the value of exactly the
  lines where our hand is the deciding factor. Furtak & Buro and Goodman both
  report meaningful gains from fixing precisely this.
- **Uniform determinization is wrong here in a specific, measurable way.** Our
  belief is highly non-uniform after a handful of asks, and (§5) we can compute it
  exactly. Spending search budget uniformly over consistent deals is throwing away
  the engine's single strongest component.

### (c) Recommendations

1. **Re-determinize inside playouts** (Goodman 2019) or adopt bounded-depth
   recursive IIMC (Furtak & Buro 2013). Run this as a controlled A/B against the
   current search on the existing 327-position benchmark plus a paired self-play
   suite. This is the highest-value single change suggested by §2–§3.
2. **Replace uniform determinization with exact belief-weighted sampling** using
   the DP in §5. Cowling et al. explicitly leave belief distributions out; we can
   put them in exactly rather than approximately.
3. **Use MO-ISMCTS, not SO-ISMCTS**, and implement the availability-count UCB
   correction. Log the per-subset visit distribution so we can detect the known
   averaging defect rather than assume it away.
4. **Keep CRN discipline**: fixed deal seeds, every deal replayed under a fixed
   set of seat rotations, and paired statistics. The ROADMAP already reports that
   "common random numbers only removed the deficit", which is consistent with CRN
   working as intended (variance reduction, not strength).
5. If we ever want equilibrium-flavoured behaviour rather than best-response-to-a-
   fixed-model behaviour, Smooth UCT is the cheapest published option, but see §4
   for why 2-player convergence guarantees do not carry to a 3v3 team game.

---

## 4. Team games with hidden information and no communication

### (a) What is known

**The right solution concept is not Nash.** Literature is a two-team zero-sum
game where teammates may agree on conventions before play but cannot communicate
during it. That is a named, studied setting.

- Bernhard von Stengel, Daphne Koller, "Team-Maxmin Equilibria", *Games and
  Economic Behavior* 21(1–2):309–321, 1997.
  http://www.maths.lse.ac.uk/personal/stengel/TEXTE/teammax.html **[abstract]**
  A team of players with a common payoff against an adversary; the team is not a
  single player because members cannot coordinate their actions. The team-maxmin
  equilibrium (TME) is the natural selection. Known to be computationally
  intractable even for 3-player team games.
- Andrea Celli, Nicola Gatti, "Computational Results for Extensive-Form
  Adversarial Team Games", *AAAI-18*, 2018. arXiv:1711.06930.
  https://ojs.aaai.org/index.php/AAAI/article/view/11462 **[abstract]**
  Defines three communication regimes: (1) communicate and correlate before and
  during play, (2) communicate only *before* play, (3) no communication. Gives the
  appropriate solution concept and an exact algorithm for each, and shows the
  inefficiency from restricted communication "can be arbitrarily large in the size
  of the game tree." Regime (2) is TMECor, the team-maxmin equilibrium with a
  correlation device. **Literature is regime (2)**: teams agree on conventions
  beforehand, then play with no channel.
- Brian Hu Zhang, Gabriele Farina, Andrea Celli, Tuomas Sandholm, "Team Belief
  DAG: Generalizing the Sequence Form to Team Games for Fast Computation of
  Correlated Team Max-Min Equilibria via Regret Minimization", arXiv:2202.00789;
  ICML 2023. https://proceedings.mlr.press/v202/zhang23j/zhang23j.pdf
  **[abstract]** A coordinator observes what is public to all team members and
  issues a prescription for every private state consistent with that observation.
  The DAG's size is exponential only in a parameter measuring *uncommon
  information within the team*, and it plugs into off-the-shelf CFR variants.
- Luca Carminati, Federico Cacciamani, Marco Ciccone, Nicola Gatti, "A Marriage
  between Adversarial Team Games and 2-player Games: Enabling Abstractions,
  No-Regret Learning, and Subgame Solving", ICML 2022.
  https://proceedings.mlr.press/v162/carminati22a/carminati22a.pdf **[abstract]**
- Brian Hu Zhang, Gabriele Farina, Tuomas Sandholm, "Subgame Solving in
  Adversarial Team Games", NeurIPS 2022.
  https://openreview.net/pdf?id=Roiw2Trm-qP **[abstract]**

**Public information and the coordinator reformulation.** The structural reason
Literature is tractable to reason about at all.

- Ashutosh Nayyar, Aditya Mahajan, Demosthenis Teneketzis, "Decentralized
  Stochastic Control with Partial History Sharing: A Common Information
  Approach", *IEEE Transactions on Automatic Control* 58(7):1644–1658, 2013.
  arXiv:1209.1695. https://arxiv.org/abs/1209.1695 **[abstract]**
  Reformulates a decentralised problem, from the standpoint of a coordinator who
  sees only the commonly-known information, as an equivalent centralised POMDP.
- Noam Brown, Anton Bakhtin, Adam Lerer, Qucheng Gong, "Combining Deep
  Reinforcement Learning and Search for Imperfect-Information Games" (ReBeL),
  *NeurIPS 2020*. https://arxiv.org/abs/2007.13544 **[abstract]**
  Public belief states: "state" expanded to include the probabilistic belief
  distribution of all agents given common-knowledge observations and policies.
  Provable convergence to Nash **in two-player zero-sum games**.

**Hanabi: coordination through public action choice.**

- Nolan Bard, Jakob N. Foerster, Sarath Chandar, Neil Burch, Marc Lanctot,
  H. Francis Song, Emilio Parisotto, Vincent Dumoulin, Subhodeep Moitra, Edward
  Hughes, Iain Dunning, Shibl Mourad, Hugo Larochelle, Marc G. Bellemare, Michael
  Bowling, "The Hanabi Challenge: A New Frontier for AI Research", *Artificial
  Intelligence* 280:103216, 2020. https://arxiv.org/abs/1902.00506 **[abstract]**
  Introduces the Hanabi Learning Environment and, crucially, separates the
  *self-play* and *ad-hoc team play* benchmarks.
- Christopher Cox, Jessica De Silva, Philip Deorsey, Franklin H. J. Kenter, Troy
  Retter, Josh Tobin, "How to Make the Perfect Fireworks Display: Two Strategies
  for Hanabi", *Mathematics Magazine* 88(5):323–336, 2015.
  https://www.tandfonline.com/doi/abs/10.4169/math.mag.88.5.323 **[abstract]**
  The hat-guessing construction: modular arithmetic over a publicly agreed
  encoding lets one public hint convey information to every other player at once.
  This is the purest example of a legal, information-theoretically optimal
  convention built entirely on public action choice.
  The strongest self-play Hanabi bots for 3+ players use this family (WTFWThat).
  A readable exposition: Arthur O'Dwyer, "Hat-game strategies in Hanabi", 2018,
  https://quuxplusone.github.io/blog/2018/03/29/hat-guessing-in-hanabi/
  **[abstract]**
- Jakob N. Foerster, H. Francis Song, Edward Hughes, Neil Burch, Iain Dunning,
  Shimon Whiteson, Matthew Botvinick, Michael Bowling, "Bayesian Action Decoder
  for Deep Multi-Agent Reinforcement Learning", *ICML 2019*, pp. 1942–1951.
  https://arxiv.org/abs/1811.01458 **[abstract]** Public-belief-conditioned
  policies; the RL analogue of the coordinator reformulation.
- Hengyuan Hu, Adam Lerer, Alex Peysakhovich, Jakob N. Foerster, "'Other-Play' for
  Zero-Shot Coordination", *ICML 2020*, PMLR 119.
  https://arxiv.org/abs/2003.02979 **[verified via abstract fetch]**
  The core diagnosis: "applying self-play naively to the zero-shot coordination
  problem can produce agents that establish highly specialized conventions that do
  not carry over to novel partners." Other-play maximises expected return when
  the partner may apply an arbitrary relabelling from a known symmetry group of
  the game, which destroys conventions that depend only on arbitrary labels. They
  report higher scores when paired with independently trained agents *and* with
  humans.
- Hengyuan Hu, Adam Lerer, Brandon Cui, Luis Pineda, David Wu, Noam Brown, Jakob
  N. Foerster, "Off-Belief Learning", *ICML 2021*, PMLR 139:4369–4379.
  https://proceedings.mlr.press/v139/hu21c.html **[abstract]**
  Unlike methods that converge to *any* equilibrium, OBL converges to a *unique*
  policy by grounding beliefs in an assumption that past partner behaviour was
  from a fixed baseline, which removes conventions that only carry meaning by
  self-referential agreement.
- Andrei Lupu, Brandon Cui, Hengyuan Hu, Jakob N. Foerster, "Trajectory Diversity
  for Zero-Shot Coordination", *ICML 2021*, PMLR 139:7204–7213.
  https://proceedings.mlr.press/v139/lupu21a.html **[abstract]**
- Hengyuan Hu, Jakob N. Foerster, "Simplified Action Decoder for Deep Multi-Agent
  Reinforcement Learning", *ICLR 2020*.
  https://openreview.net/pdf?id=B1xm3RVtwB **[abstract]**

**Bridge, Skat, and the other partnership games.**

- Ginsberg 2001 (above) for declarer play.
- Jiang Rong, Tao Qin, Bo An, "Competitive Bridge Bidding with Deep Neural
  Networks", *AAMAS 2019*. arXiv:1903.00900. https://arxiv.org/abs/1903.00900
  **[abstract]** Two networks: one infers the partner's cards, the second selects
  a bid from the first's output. Bidding treated explicitly as inference-plus-
  signalling under adversarial observation.
- Qucheng Gong, Yu Jiang, Yuandong Tian, "Simple is Better: Training an End-to-End
  Contract Bridge Bidding Agent without Human Knowledge", 2020.
  https://openreview.net/forum?id=SklViCEFPH **[abstract]** Beats WBridge5 from
  self-play, and reports that "explicitly modeling belief is not necessary in
  boosting the performance." A useful counterweight to belief-centric dogma, but
  note the domain: bidding has a small, discrete, ritualised action space.
- Michael Buro, Jeffrey R. Long, Timothy Furtak, Nathan R. Sturtevant, "Improving
  State Evaluation, Inference, and Search in Trick-Based Card Games", *IJCAI
  2009*, pp. 1407–1413. https://www.ijcai.org/Proceedings/09/Papers/236.pdf
  **[abstract]** Kermit; the first expert-level computer Skat player. Skat's two
  defenders are a team with no communication facing a soloist, which is the
  closest published analogue to our setting.
- Stefan Edelkamp, "Knowledge-Based Paranoia Search in Trick-Taking", arXiv:
  2104.05423, 2021; IEEE CoG 2021. https://arxiv.org/abs/2104.05423 **[abstract]**
  Combines partial-information game-tree search with knowledge representation to
  find *forced wins* over the belief space, with a variant for "a forced win
  against most worlds."
- Pier Luca Lanzi, Stefano Di Palma, "Traditional Wisdom and Monte Carlo Tree
  Search Face-to-Face in the Card Game Scopone", arXiv:1807.06813, 2018; *IEEE
  Transactions on Games*. https://arxiv.org/abs/1807.06813 **[abstract]**
  Rule-based players encoding traditional partnership conventions versus MCTS and
  ISMCTS; ISMCTS beat every rule-based player.
- Doppelkopf and Tichu have working implementations and student theses but no
  strong published research result. Examples: Peter Müller, "Tichu Bot", ETH
  Zurich semester thesis, 2020,
  https://pub.tik.ee.ethz.ch/students/2020-FS/SA-2020-19.pdf; Nicolas Wyss,
  "Reinforcement Learning for Tichu", University of Bern BA thesis,
  https://prg.inf.unibe.ch/wp-content/uploads/2024/08/BA_NicolasWyss.pdf.
  **[abstract]** Cite these as evidence of the shape of the field, not as
  results.

**How convention overfitting is measured.** Two standard instruments:

- **Cross-play (XP)**: pair agents from *independently seeded training runs* and
  compare against the self-play (SP) score. The SP-minus-XP gap is the convention
  overfitting. Introduced as the evaluation for zero-shot coordination in Hu et
  al. 2020.
- **Ad-hoc team play / zero-shot coordination**: pair against a held-out pool of
  agents (or humans) never seen in training. Formalised as a benchmark track in
  Bard et al. 2020.

### (b) What transfers to Literature

- **Literature is TMECor, not Nash.** Teammates agree on conventions before play
  (that is what a "system" is in partnership card games) and cannot communicate
  during it. Celli & Gatti's regime (2) is an exact description. This changes what
  "optimal" means and what "exploitability" means, and it invalidates the
  convergence guarantees of the 2p0s toolbox (CFR, ReBeL, Smooth UCT).
- **The common-information reformulation is exact and unusually clean here.**
  Because every card movement is public, the public history is common knowledge
  in the strong sense, and the joint hidden state is exactly the initial deal.
  This is a better fit for the coordinator/public-belief-state machinery than
  most card games, where discards and draws create asymmetric partial
  observations.
- **But the uncommon information within a team is large.** A team of 3 holds 27
  cards in three private hands. The TB-DAG parameter (greatest number of joint
  private states in any belief) is astronomically large at the root. TB-DAG is
  therefore *not* a full-game method for us. It may be viable for late-game
  subgames where several half-suits are resolved, which is worth a scoping
  calculation.
- **The Hanabi convention literature transfers in diagnosis, not in remedy.**
  The diagnosis (self-play manufactures conventions that do not survive contact
  with a novel partner; measure it with cross-play) transfers directly and
  cheaply. The remedies do not transfer cleanly:
  - *Other-play* relies on a known symmetry group. Literature's obvious
    candidates are the four suits and the half-suit-internal card labels, but
    neither is a true symmetry: the ranks within a half-suit are not
    interchangeable for humans, and the two jokers are individually askable
    (SPEC §2). Any OP-style symmetrisation must be justified against the actual
    automorphism group of the game, not assumed.
  - *Off-belief learning* is defined for a fully cooperative Dec-POMDP. Literature
    is zero-sum between teams. Grounding beliefs in a fixed baseline policy has no
    obvious adversarial analogue, and the uniqueness result should not be assumed
    to carry.
  - *Hat-guessing* is a genuinely instructive limiting case: it shows that when
    the signalling channel is free and unobserved by an adversary, information-
    theoretically optimal encodings dominate human conventions. In Literature the
    channel is neither free (a failed ask surrenders the turn) nor unobserved
    (three opponents are listening). This asymmetry is, in my view, the most
    interesting thing about the game and the strongest novelty claim available.
- **Skat's defender pair is our closest published analogue** and should be the
  comparator we discuss, not Hanabi.

### (c) Recommendations

1. **Adopt cross-play as a first-class metric now.** Train N independently seeded
   FishBots, report SP and XP score matrices, and report SP-minus-XP explicitly.
   It is cheap, it is standard (Hu et al. 2020, Bard et al. 2020), and without it
   any self-play strength number is uninterpretable.
2. **Frame the solution concept as TMECor in the paper** and cite Celli & Gatti
   2018 and von Stengel & Koller 1997. Do not write "Nash equilibrium".
3. **Scope TB-DAG for endgames only.** Compute the "uncommon information" parameter
   at various points in the game and report where it becomes tractable. If it
   never does, say so: that is a legitimate negative result about a 3v3 game with
   9-card hands.
4. **Do not implement other-play or OBL until the symmetry/cooperation
   preconditions are checked.** Write down the actual automorphism group of
   Literature first. If the four suits are genuinely interchangeable in our
   ruleset, an OP-style suit-relabelling equivariance is defensible and cheap;
   the joker asymmetry in the Specials half-suit means half-suit 8 is not
   symmetric with the others.
5. **Study the adversarially-observed signalling channel as the paper's thesis.**
   Measure how much a convention gains the team versus how much it leaks to the
   opposing team. That trade-off has no published treatment I could find.

---

## 5. Exact belief tracking and combinatorial inference

### (a) What is known

**The general problem is hard.**

- Leslie G. Valiant, "The complexity of computing the permanent", *Theoretical
  Computer Science* 8(2):189–201, 1979.
  https://www.sciencedirect.com/science/article/pii/0304397579900446
  **[abstract]** Computing the permanent is #P-complete even for 0/1 matrices;
  equivalently, counting perfect matchings in a bipartite graph is #P-complete.
- Mark Jerrum, Alistair Sinclair, Eric Vigoda, "A polynomial-time approximation
  algorithm for the permanent of a matrix with nonnegative entries", *Journal of
  the ACM* 51(4):671–697, 2004. https://faculty.cc.gatech.edu/~vigoda/Permanent.pdf
  **[abstract]** An FPRAS via MCMC. Polynomial, but the exponents make it a
  theoretical rather than a practical tool.
- Alexander Barvinok, "An approximation algorithm for counting contingency
  tables", arXiv:0803.3948, 2008.
  https://dept.math.lsa.umich.edu/~barvinok/atlas.pdf **[abstract]**
  Quasi-polynomial `N^{O(log N)}` for smooth margins, via an integral
  representation of the count as the expectation of a permanent of a random
  matrix with exponential entries.
- Persi Diaconis, Anil Gangolli, "Rectangular arrays with fixed margins", in
  *Discrete Probability and Algorithms*, IMA Vol. 72, Springer, 1995, pp. 15–41.
  https://link.springer.com/chapter/10.1007/978-1-4612-0801-3_3 **[abstract]**
  The survey of exact and approximate counting for arrays with fixed margins, and
  the origin of the Diaconis-Gangolli Markov chain.

**Sequential importance sampling, and the reason to distrust it.**

- Yuguo Chen, Persi Diaconis, Susan P. Holmes, Jun S. Liu, "Sequential Monte
  Carlo Methods for Statistical Analysis of Tables", *Journal of the American
  Statistical Association* 100(469):109–120, 2005.
  https://www.tandfonline.com/doi/abs/10.1198/016214504000001303 **[abstract]**
  SIS for two-way 0/1 and contingency tables with fixed margins, sampling column
  by column from carefully chosen conditionals; reported as sometimes orders of
  magnitude more efficient than competing Monte Carlo methods.
- Ivona Bezáková, Alistair Sinclair, Daniel Štefankovič, Eric Vigoda, "Negative
  Examples for Sequential Importance Sampling of Binary Contingency Tables",
  *Algorithmica* 64(4):606–620, 2012; ESA 2006, pp. 136–147. arXiv:math/0606650.
  https://arxiv.org/abs/math/0606650 **[abstract]**
  A family of instances where SIS "if run for any subexponential number of
  trials, will underestimate the number of tables by an exponential factor", for
  *any* of the usual row/column orderings. This is the reason SIS must never be
  reported without an effective-sample-size diagnostic.

**Constraint propagation gives arc consistency and feasibility for free.**

- Jean-Charles Régin, "Generalized Arc Consistency for Global Cardinality
  Constraint", *AAAI-96*, pp. 209–215.
  https://cdn.aaai.org/AAAI/1996/AAAI96-031.pdf **[verified, full text]**
  A GCC constrains, for each value `v_i`, the number of variables in `X` assigned
  `v_i` to lie in `[l_i, u_i]`. The paper gives generalized arc consistency via a
  new flow-integrality theorem, with **space complexity `O(|X| x |V|)` and time
  complexity `O(|X|^2 x |V|)`** (stated in the abstract and re-derived on p. 6 as
  `O(|X(C)| |D(C)|)` space and `O(|X(C)|^2 |D(C)|)` time).
- Jean-Charles Régin, "A Filtering Algorithm for Constraints of Difference in
  CSPs", *AAAI-94*, pp. 362–367.
  https://cdn.aaai.org/AAAI/1994/AAAI94-055.pdf **[abstract]** The alldifferent
  special case, via matching theory, `O(pd)` space and `O(p^2 d^2)` time.
- Philip Hall, "On Representatives of Subsets", *Journal of the London
  Mathematical Society* s1-10(1):26–30, 1935. Hall's condition: a family of sets
  has a system of distinct representatives iff every subfamily of size k has a
  union of size at least k. **[abstract]**
- David Gale, "A theorem on flows in networks", *Pacific Journal of Mathematics*
  7(2):1073–1082, 1957; Herbert J. Ryser, "Combinatorial properties of matrices
  of zeros and ones", *Canadian Journal of Mathematics* 9:371–377, 1957. The
  Gale-Ryser theorem: necessary and sufficient conditions for a 0/1 matrix with
  prescribed row and column sums. **[abstract]**

**The game-AI paper that formalises exactly our question.** This is the most
directly relevant technical citation in the entire survey.

- Christopher Solinas, Douglas Rebstock, Nathan R. Sturtevant, Michael Buro,
  "History Filtering in Imperfect Information Games: Algorithms and Complexity",
  arXiv:2311.14651, 2023. https://arxiv.org/abs/2311.14651 **[verified, full text]**

  Results:
  - **Theorem 1**: there is a joint policy for which the *construction* problem
    (produce a single history consistent with a public state) is **FNP-complete**.
    So in general, even one consistent world is intractable to build.
  - **Definition 3 / Theorem 2**: a public tree is *sparse* iff every public state
    `S` satisfies `|H_S| <= p(t)` for a polynomial `p`. The enumeration problem is
    solvable in polynomial time **iff** the public tree is sparse. Two-player
    Texas Hold'em is sparse. Trick-taking card games are generally dense.
  - **Lemma 2**: for trick-taking card games, construction *is* polynomial via
    integer max-flow. Their network: source to one vertex per suit with capacity
    equal to the unknown cards remaining in that suit; suit vertices to player
    vertices where that player may still hold that suit (voids omitted); player
    vertices to sink with capacity equal to the unknown cards remaining in that
    hand. An integral flow is a *suit length assignment*.
  - **TTCG Gibbs sampler**: Metropolis-Hastings over histories, with neighbours
    generated by `RingSwap` on the suit-length assignment matrix (add one to
    `A[i][j]`, remove one from `A[i][k]`, then repair the column sums by BFS over
    short swap sequences), acceptance ratio using unnormalized reach
    probabilities and the neighbourhood sizes. Theorems 3 and 4: the chain is
    aperiodic and irreducible, and its stationary distribution is the target
    `P_pi`. Demonstrated on Oh Hell.

**Learned, factorized beliefs used to weight PIMC samples.**

- Christopher Solinas, Douglas Rebstock, Michael Buro, "Improving Search with
  Supervised Learning in Trick-Based Card Games", *AAAI-19*, 33(1):1158–1165.
  arXiv:1903.09604. https://arxiv.org/abs/1903.09604 **[verified, full text]**
  Their Equation 1, the factorization we should copy:

  `p(s | h) proportional to product over cards c of L(h)[c, loc(c, s)]`

  where `L(h)` is a `|C| x l` matrix of per-card location probabilities from a
  network trained on move history, `l` is the number of possible locations, and
  `loc(c, s)` is card `c`'s location in state `s`. They apply softmax over rows so
  each card's distribution sums to 1, and note explicitly: "Our work does not
  impose any additional constraints, but constraints on the number of total cards
  in each hand or each suit's length could be added as well."

  Implementation reality check, from their §4: they *enumerate the entire
  information set* to normalize. "The rough maximum of 42 million states in Skat
  is manageable in around 2 seconds on modern hardware." This works because Skat's
  information sets are ~10^7.5. **It does not scale to Literature.**

### (b) What transfers to Literature, and one result that is better than the
### literature

**Our belief problem, stated precisely.** Hidden state is the initial deal. All
card motion is public, so all constraints can be pushed back to the initial deal
and the current assignment is a public function of it. Constraints observed
during play:

1. **Unary negative**: after a failed ASK(t, c), player `t` does not hold `c`.
   Also, by SPEC §4.1 rule 4, the asker did not hold `c` at the time of asking.
2. **Unary positive**: a successfully transferred card, or a card revealed by a
   claim, has a known holder.
3. **Cardinality**: hand sizes are public at all times.
4. **Group lower bound (disjunctive)**: by SPEC §4.1 rule 3, an asker holds *at
   least one* card of the named half-suit at the moment of the ask.

Constraints 1–3 give exactly a bipartite degree-constrained subgraph problem:
assign each unknown card to a player, respecting per-card candidate sets and
per-player quotas. Counting such assignments is the permanent problem, #P-complete
in general (Valiant 1979).

**But our instance is polynomial, exactly, and cheaply, because there are only 6
players.** Run a dynamic program over *remaining quota vectors*. Process unknown
cards in any fixed order; the DP state is the vector of remaining quotas
`(n_0, ..., n_5)` with `n_i` in `0..9`; each card transitions to one of at most 6
successors, weighted by its candidate set.

I computed the exact size of this state space for the 54-card variant:

| Quantity | Value |
|---|---|
| Total DP states across all layers | **1,000,000** (exactly `10^6`) |
| Largest single layer | 55,252 |
| Transitions per counting pass | ~6,000,000 |
| Number of unconstrained deals | ~1.011 x 10^38 |

So we can count `10^38` objects exactly in six million big-integer operations.
What this buys:

- **Exact normalization**, where Solinas et al. 2019 needed brute-force
  enumeration of the information set.
- **Exact per-card marginals** `P(card c is held by player p)` by a
  forward-backward pass, no sampling.
- **Exact sampling** of consistent deals by backward sampling from the DP tables.
  No MCMC, no rejection, no importance weights, no burn-in, no mixing question.
  This sidesteps the Solinas et al. 2023 Gibbs sampler entirely for the
  factorized case.
- **Weighted versions stay exact** provided the weight factorizes per card,
  `w(s) = product over c of f(c, loc(c, s))`. That is exactly the Solinas et al.
  2019 Equation 1 form. So we can have a learned belief *and* exact hand-size
  constraints *and* exact normalization simultaneously, which no published card-
  game system does as far as this survey found.
- **Exact CLAIM evaluation.** Pin the 6 cards of a half-suit to the declared
  holders and rerun the DP: that ratio is `P(exact)` directly. Replace sum-product
  with max-product to get the **MAP assignment**, which is the assignment we
  should declare. Both in the same `~6M` operations.

**What breaks the DP, and how to handle it.** Constraint type 4 (group lower
bound: "player p holds at least one card of half-suit H") is not a per-card
constraint and does not fit the DP or the flow network. Handle by
inclusion-exclusion: each such constraint forbids the event "player p holds zero
cards of H", and each forbidden event is itself expressible as a candidate-set
restriction (remove p from the candidate set of all 6 cards of H), so a sum over
`2^k` sign-alternating DP runs is exact for `k` active group constraints. `k` is
small in practice (constraints expire when a half-suit resolves), and the
inclusion-exclusion terms can be truncated with a rigorous Bonferroni bound if
`k` ever grows.

**What also breaks the DP**: a belief weight that depends on a player's *whole
hand* rather than on individual cards (for example, a policy-based inference term
of the form "would this player have asked that, given this whole hand?"). Then
fall back to importance sampling with the exact DP as the proposal, which is a
very strong proposal because it is exact for the factorized part, and report
effective sample size. Bezáková et al. is the citation for why an unreported ESS
is not acceptable.

**Régin's GCC is still worth implementing**, not for counting but as a fast
filter and as a correctness oracle: GAC on the GCC gives exactly the set of
(card, player) pairs that occur in at least one consistent assignment, in
`O(|X|^2 |V|)`. Any card-player pair the DP assigns positive probability must be
arc-consistent, and vice versa. That is a cheap, independent cross-check on the
belief module, which is the single most load-bearing component of the engine.

**Where our public tree sits on the Solinas et al. 2023 axis.** Literature's
public tree is **dense**: `|H_S|` is ~`10^38` at the root and remains far above
any polynomial in the history length for most of the game. By their Theorem 2,
polynomial enumeration is impossible. This is a precise, citable statement of why
the Skat approach (enumerate 42 million states and normalize) cannot be ported,
and why the DP result above matters.

### (c) Recommendations

1. **Build the quota DP as the canonical belief engine.** Sum-product for
   normalization and marginals, max-product for MAP claims, backward sampling for
   exact determinizations. Use exact integers or log-space with care;
   `10^38`-scale counts overflow float64 mantissas but not the exponent range, so
   log-space is fine for probabilities and big integers are fine for counts.
2. **Adopt Solinas et al. 2019 Equation 1 as the belief parameterization** and
   note in the paper that we enforce the hand-size constraint they explicitly left
   unenforced. That is a clean, defensible delta on a strong baseline.
3. **Handle group lower bounds by inclusion-exclusion**, and unit-test that the
   inclusion-exclusion count matches brute force on small variants (a 4-player,
   4-half-suit toy).
4. **Implement Régin GCC propagation as an independent oracle** for the belief
   module's support, plus Hall / Gale-Ryser feasibility assertions.
5. **Do not implement SIS, MCMC, JSV, or Barvinok.** Document in the paper that
   they are unnecessary at this scale and cite them as the fallback for
   non-factorizable weights only. If a non-factorizable term is ever added, use
   the DP as an SIS proposal and report ESS.
6. **Cite Solinas et al. 2023 for the sparsity dichotomy** and state where
   Literature falls. This is the cleanest available framing for "why exact belief
   in this game is interesting."

---

## 6. Bayesian opponent modelling from action choice

### (a) What is known

- **Table-based inference.** Buro, Long, Furtak & Sturtevant, IJCAI 2009 (above):
  state evaluations learned from human game data, then used to perform inference
  on the unobserved hands of opponents. Produced Kermit, the first expert-level
  Skat player. **[abstract]**
- **Neural per-card inference.** Solinas, Rebstock & Buro, AAAI 2019 (above),
  §5(a). Trained on 20 million human games from a Skat server, predicting the
  full 32-card configuration (not only the unknown cards; they report that
  predicting full targets makes learning easier). Features include void suits,
  lead cards, sloughed cards, bidding type and bucketed bid magnitude. Results:
  BDCI (their inference) beat KI (Kermit's inference, the prior state of the art)
  by more than 4 tournament points per game in suit and null games, with one
  standard deviation of 1.0–1.4 TP; no significance in grand games, attributed to
  the soloist's overwhelming advantage in the test set. Cost: 3.1x slowdown.
  **[verified, full text]**
- **Inference from the choice of action, not just legality.**
  - Douglas Rebstock, Christopher Solinas, Michael Buro, Nathan R. Sturtevant,
    "Policy Based Inference in Trick-Taking Card Games", *IEEE CoG 2019*.
    arXiv:1905.10911. https://arxiv.org/abs/1905.10911 **[abstract]**
    Uses a player model to infer the probability of being in a given state within
    an information set, i.e. Bayesian updating on the *policy*, not merely on
    rule-forced revelations.
  - Douglas Rebstock, Christopher Solinas, Michael Buro, "Learning Policies from
    Human Data for Skat", arXiv:1905.10907, 2019.
    https://arxiv.org/abs/1905.10907 **[abstract]**
- **Inference and bluffing emerging from search.**
  - Peter I. Cowling, Daniel Whitehouse, Edward J. Powley, "Emergent bluffing and
    inference with Monte Carlo Tree Search", *IEEE CIG 2015*, pp. 114–121.
    http://orangehelicopter.com/academic/papers/cig15.pdf **[abstract]**
    Shows how MCTS can be enhanced to perform inference and bluffing, which vanilla
    MCTS cannot do, and that these behaviours emerge rather than being scripted.
- **The exploitability counterweight.**
  - Long et al. 2010 Table 1 (§2 above): PIMC matches equilibrium value against a
    Nash opponent but loses substantially to a best-responder.
  - Viliam Lisý, Michael Bowling, "Equilibrium Approximation Quality of Current
    No-Limit Poker Bots", AAAI-17 Workshops. arXiv:1612.07547.
    https://arxiv.org/abs/1612.07547 **[abstract]**
    The Local Best Response (LBR) method: a cheap lower bound on best-response
    value, used to show that abstraction-based poker bots were "remarkably poor
    Nash equilibrium approximations." The instrument to copy.
  - Hu et al. 2020 (§4 above): self-play conventions do not transfer.

### (b) What transfers to Literature

- **The rule-forced part of inference in Literature is enormously stronger than
  in Skat** (see §5), so the marginal value of *policy-based* inference is
  correspondingly different: much of what a Skat network has to learn, we can
  derive exactly. The place policy-based inference actually pays here is the
  narrow residual: which of several rule-consistent worlds is likely given that
  the opponent chose *this* ask rather than another equally legal one, and given
  that they did *not* claim.
- **The "did not claim" signal is distinctive and, as far as this survey found,
  unstudied.** A player who could claim and did not is telling you something about
  their team's belief state. That is a second-order, convention-laden inference of
  exactly the kind that is powerful in self-play and fragile against novel
  opponents.
- **The exploitability risk is the mirror image of the inference opportunity.**
  Any inference model that keys on "opponents ask X only when Y" is a model an
  adaptive opponent can invert. Long et al.'s Kuhn table is the warning.

### (c) Recommendations

1. **Adopt TSSR as the belief-quality metric**, defined by Solinas et al. 2019
   Equation 2: `TSSR = p(s* | h) / (1/n) = p(s* | h) * n`, "how many times more
   likely the true state is going to be selected, compared to uniform random
   sampling." For us, `p(s* | h)` and `n` are both computable *exactly* by the DP,
   where they needed Monte Carlo estimates for the baseline. Report TSSR by
   half-suits-resolved and by ply, as they report it by trick number.
2. **Separate rule-forced inference from policy-based inference in the
   ablation.** Report three agents: uniform-over-consistent, exact-rule-forced,
   and exact-plus-policy. This isolates how much of our strength is deduction (not
   exploitable) versus opponent modelling (exploitable).
3. **Build an LBR-style attacker.** Train or search a best-responding *team*
   against a frozen FishBot and report the value it extracts. This is the only
   honest way to make an absolute claim about the policy-based inference layer.
4. **Do not let the ask policy be trained purely against its own inference
   model.** That is the self-play convention trap in its most direct form.

---

## 7. Evaluation methodology

### (a) What is known

**Duplicate and paired designs.** The standard variance-reduction device in card
game evaluation is to replay the same deal with the roles permuted.

- Duplicate bridge is the canonical instantiation: the same deals are played at
  every table, with directions reversed for teams, and scores are compared as IMPs
  or matchpoints. Board-a-match reduces variance further by scoring each board as
  win/loss/tie.
- Long et al. 2010 use it in synthetic experiments: "we generated 10000 synthetic
  trees and played 2 games per tree, with the competing players swapping sides in
  the second game." **[verified]**
- Solinas et al. 2019 use it in Skat tournaments, reporting seatings "reversed",
  with one standard deviation over all matchups of 1.0–1.4 tournament points.
  **[verified]**
- Art B. Owen, *Monte Carlo theory, methods and examples*, Ch. 8, for common
  random numbers as the general technique, including the warning that it can
  backfire if the coupling induces negative correlation.
  https://artowen.su.domains/mc/Ch-var-basic.pdf **[abstract]**

**Rating systems.**

- Rémi Coulom, "Whole-History Rating: A Bayesian Rating System for Players of
  Time-Varying Strength", *Computers and Games 2008*, LNCS 5131, pp. 113–124.
  https://www.remi-coulom.fr/WHR/ **[abstract]** A dynamic Bradley-Terry model
  computing the exact MAP over the whole rating history; reported to predict
  better than Elo, Glicko, TrueSkill and decayed-history methods, and fast enough
  for live servers.
- A caution I found but did not read in full: "Is Elo Rating Reliable? A Study
  Under Model Misspecification", arXiv:2502.10985, 2025.
  https://arxiv.org/html/2502.10985v1 **[abstract]** Flagged so we do not over-
  claim from Elo separations.

**Exploitability and best response at scale.**

- Michael Johanson, Kevin Waugh, Michael Bowling, Martin Zinkevich, "Accelerating
  Best Response Calculation in Large Extensive Games", *IJCAI 2011*, pp. 258–265.
  https://www.ijcai.org/Proceedings/11/Papers/054.pdf **[abstract]**
  Makes exact best-response computation feasible for heads-up limit hold'em by
  avoiding full tree traversal; parallelisable.
- Lisý & Bowling 2017 (above): LBR gives a cheap *lower bound* on exploitability
  when the exact computation is infeasible. A lower bound is enough to falsify an
  "our agent is near-optimal" claim, which is the usual thing worth doing.

**Cross-play and ad-hoc coordination.** Hu et al. 2020 and Bard et al. 2020, as
in §4. The SP-minus-XP gap is the standard convention-overfitting measurement.

**Establishing absolute strength when equilibrium is infeasible.** The published
practice, in descending order of rigour:

1. Exact best-response value (Johanson et al. 2011) where the game is small
   enough. Not available to us.
2. Best-response *lower bound* (Lisý & Bowling 2017). Available to us.
3. Solve restricted subgames exactly and measure the agent's loss there.
   Long et al. 2010 do exactly this for Skat endgames (CFR on 3-tricks-left
   positions, 15% of games unresolved, 0.42 TP loss on those). The Fish engine's
   327 solvable endgame positions in `ROADMAP.md` are the same instrument.
4. Play against strong humans. Buro et al. 2009 and Ginsberg 2001 both rest their
   "expert level" claims on this.
5. Head-to-head against prior published agents. Not available to us; there are
   none.

### (b) What transfers to Literature

- **Duplicate design is richer here than in bridge** because there are 6 seats and
  the team partition is fixed (players 0,2,4 versus 1,3,5). Rotating the *deal*
  by one seat swaps the teams' holdings entirely; rotating by two keeps teams
  intact but permutes within them. A clean protocol: for each generated deal, play
  it under all 6 cyclic seat rotations, so each team holds each set of three hands
  exactly once, and score the pair as a single observation.
- **The Skat variance figure is the right sanity anchor.** Long et al. report a TP
  standard deviation of 778 over 180 deals, which is why a 0.063 TP/deal edge is
  practically irrelevant there. We should compute the analogous quantity for
  Literature before declaring any effect "significant".
- **The 327-position endgame benchmark is a "solve restricted subgames" measure**,
  and inherits that method's known bias: it measures only positions small enough
  to solve. Long et al. are explicit that Skat's *unresolved* endgames are where
  PIMC's loss lives. The `ROADMAP.md` observation that belief agents already hit
  100% on information-resolved positions is exactly the selection effect to guard
  against.
- **There is no external opponent, so absolute strength must come from
  best-response lower bounds and from human play.** Cross-play gives relative
  robustness, not absolute strength.

### (c) Recommendations

1. **Every evaluation result should be a paired result.** Fixed deal seeds, all 6
   cyclic rotations, paired test statistics. Report the paired standard deviation
   alongside the mean, as Solinas et al. do.
2. **Report the raw per-deal standard deviation** and the number of deals needed
   to resolve the effect size we care about, before running the experiment. This
   is the discipline the Skat 778-TP figure teaches.
3. **Use WHR or a paired Bradley-Terry model, not raw win rate**, once there are
   more than two agents in the pool, and do not over-interpret small rating gaps
   (arXiv:2502.10985).
4. **Build the LBR-style attacker (see §6) and report its value as the headline
   robustness number.** For a team game, the attacker must be a coordinated
   *team* best response, which is the TMECor-flavoured version of the metric; say
   so explicitly rather than reusing the 2p0s definition.
5. **Report the endgame benchmark with its selection effect stated.** Two numbers:
   agreement on information-resolved positions (a bug detector, currently at 100%
   for the belief agents, which means it has no headroom left) and value loss on
   genuinely uncertain positions (where the 0.104-to-0.465 spread in `ROADMAP.md`
   actually lives).
6. **Add cross-play to the standard report**, per §4.

---

## Ranked recommendations for FishBot v0.4

Ordered by expected value: (information gained about where strength is lost) x
(probability the change actually helps) / (cost).

1. **Take CLAIM out of determinized search entirely; decide it from the exact
   belief DP (`P(exact)` by sum-product, declared assignment by max-product).**
   Strategy fusion makes every determinization value a claim as a guaranteed win
   and pick a different assignment, so any search-selected claim is an artefact.
   *Frank & Basin, AIJ 100:87–123, 1998; Long et al., AAAI-10, 2010.*

2. **Re-determinize inside playouts so simulated opponents stop seeing our
   hand.** This is the most specific, testable hypothesis available for the
   ROADMAP's open problem #1 (search has never beaten its own prior): a leaking
   playout systematically misvalues exactly the lines our hand decides.
   *Furtak & Buro, IEEE CIG 2013; Goodman, arXiv:1902.06075, 2019.*

3. **Replace uniform determinization with exact belief-weighted sampling from the
   quota DP.** ISMCTS as published samples uniformly and its authors say so
   outright; we can sample from the true posterior exactly, which no published
   card-game system does.
   *Cowling, Powley & Whitehouse, IEEE TCIAIG 4(2):120–143, 2012 ("We do not
   consider belief distributions in this paper"); Solinas, Rebstock & Buro,
   AAAI-19, 2019.*

4. **Measure `lc`, `b`, `df` for Literature with Long et al.'s exact protocol and
   publish the numbers.** Cheap, decides a priori whether the PIMC family is even
   right for this game, and the authors explicitly asked for a game between the
   extremes. My prior: `df` well above Skat's 0.6, `lc` well below Skat's 0.9
   because of the all-or-nothing claim.
   *Long, Sturtevant, Buro & Furtak, AAAI-10, pp. 134–140, 2010.*

5. **Adopt TSSR as the belief metric, computed exactly rather than by Monte
   Carlo.** It converts "is our belief good?" from a vibe into a number, and our
   version is strictly better-founded than the original because both numerator
   and denominator are exact.
   *Solinas, Rebstock & Buro, AAAI-19, 2019, Eq. 2.*

6. **Add cross-play between independently seeded FishBots, and report SP minus
   XP.** Without it, every self-play strength claim in the paper is
   uninterpretable, and the fix costs only training runs we would do anyway.
   *Hu, Lerer, Peysakhovich & Foerster, ICML 2020; Bard et al., AIJ 280, 2020.*

7. **Build a coordinated best-responding opposing team and report the value it
   extracts (LBR-style lower bound).** This is the only route to an absolute
   claim, and it directly tests the PIMC exploitability warning that Long et al.
   flag as the open issue in their own work.
   *Lisý & Bowling, arXiv:1612.07547, 2017; Johanson, Waugh, Bowling &
   Zinkevich, IJCAI 2011.*

8. **Enforce the exact factorized belief `p(s|h) ∝ ∏_c L(h)[c, loc(c,s)]` with
   hand-size quotas via the DP, and handle the "asker holds ≥1 of the half-suit"
   constraints by inclusion-exclusion.** Solinas et al. explicitly note the
   hand-size constraint could be added and do not add it; adding it exactly is a
   clean contribution.
   *Solinas, Rebstock & Buro, AAAI-19, 2019, Eq. 1; Régin, AAAI-96, pp. 209–215.*

9. **State the solution concept as TMECor and stop writing "Nash".** Literature is
   a two-team zero-sum game with pre-play agreement and no in-play communication,
   which is Celli & Gatti's regime (2) exactly; the 2p0s convergence results we
   might be tempted to lean on do not apply.
   *Celli & Gatti, AAAI-18, 2018; von Stengel & Koller, GEB 21:309–321, 1997.*

10. **Add Régin GCC propagation plus Hall / Gale-Ryser assertions as an
    independent correctness oracle on the belief module.** The belief module is
    the load-bearing component; a second, structurally different implementation of
    its support set is the cheapest insurance available.
    *Régin, AAAI-96 (GAC for GCC, `O(|X| |V|)` space, `O(|X|^2 |V|)` time);
    Hall 1935; Gale 1957; Ryser 1957.*

Runner-up, worth scoping but not in the top 10: **alpha-mu for endgames and for
the claim/no-claim decision** (Cazenave & Ventos, arXiv:1911.07960), because it
attacks strategy fusion directly by propagating per-world outcome vectors rather
than scalars, and our endgames are small. It is ranked below the above because
recommendation 1 already removes the worst strategy-fusion damage at a fraction
of the cost.

---

## Claims we should NOT make

1. **"Literature has never been studied."** Say instead: no peer-reviewed AI work
   on Literature was found; open-source implementations with bots exist
   (`neelsomani/literature`, `Dynosol/playfish.io`, `iuruoy-shao/fish`); and the
   close relative Go Fish is in the Valet benchmark (Goadrich, Morenville &
   Piette, arXiv:2603.03252, 2026). Overclaiming novelty is the fastest way to
   lose a reviewer.

2. **"PIMC works in trick-taking card games, so it works here."** Long et al.'s
   favourable Skat numbers hold at Skat's measured point (`lc` 0.8–1.0,
   `df ≈ 0.6`). Literature's all-or-nothing CLAIM is an anti-correlated
   sibling structure, which is their identified worst case for PIMC. Until we
   measure, this is an open question, not a premise.

3. **"Our agent is near-optimal because it agrees with exact play on the endgame
   benchmark."** That benchmark contains only positions small enough to solve.
   Long et al. show for Skat that PIMC's loss lives specifically in the ~15% of
   endgames that are *not* resolved. `ROADMAP.md` already reports 100% agreement
   on information-resolved positions, which means that instrument is saturated
   and carries no further signal.

4. **"We compute / approach a Nash equilibrium."** Literature is a 3v3 team
   zero-sum game. The relevant concepts are TME and TMECor (von Stengel & Koller
   1997; Celli & Gatti 2018), TME is intractable even for 3-player team games, and
   CFR/ReBeL/Smooth UCT guarantees are stated for two-player zero-sum. Do not
   import them.

5. **"Hanabi's zero-shot-coordination methods apply."** Hanabi is fully
   cooperative and its hint channel is not observed by an adversary. In Literature
   the coordination channel is the ask, which is costly and heard by three
   opponents. Other-play additionally requires a genuine symmetry group, and our
   Specials half-suit (two individually-askable coloured jokers, SPEC §2) breaks
   naive suit symmetry. Borrow the *diagnosis* (self-play conventions overfit;
   measure with cross-play), not the remedies.

6. **"Sampling consistent deals requires approximation."** It does not, for
   uniform or per-card-factorized beliefs: the quota DP is exact at `10^6` states
   and ~`6 x 10^6` transitions. Do not present SIS, MCMC, JSV or Barvinok as
   necessary; present them as the fallback for non-factorizable weights, and cite
   Bezáková, Sinclair, Štefankovič & Vigoda (Algorithmica 64(4), 2012) for why SIS
   without an effective-sample-size diagnostic is not trustworthy.

7. **"Self-play win rate demonstrates strength."** It demonstrates strength
   against the training distribution. Report cross-play and a best-response lower
   bound alongside it, or make no strength claim.

8. **"Search beats the belief prior."** Not until it does so on a paired,
   rotation-controlled design with the per-deal variance reported. The current
   73.6% vs 75.6% under genuine uncertainty in `ROADMAP.md` is a deficit, not a
   gain, and the Skat precedent (778 TP standard deviation over 180 deals) is a
   reminder of how easily an effect this size is noise.

9. **"The belief state is the information set."** The information set is a set;
   the belief is a measure on it. ISMCTS's uniform determinization is a particular,
   generally incorrect, choice of that measure, as its own authors note.

10. **"Go Fish results tell us about Literature."** The Valet finding that MCTS
    barely separates from random in Go Fish is a statement about visibility-only
    determinization, not about the game's intrinsic difficulty. Cite it as
    motivation for belief-weighted determinization, not as a difficulty claim.

11. **"Asks are the only information channel, so there is no signalling."** Asks
    *are* a signalling channel, and a legal one. Do not describe Literature as a
    game without conventions; describe it as a game whose conventions are public
    and adversarially observed.

---

## Bibliography

Sorted by section of first substantive use.

**PIMC and determinization**
- Frank, I., & Basin, D. (1998). Search in games with incomplete information: A case study using Bridge card play. *Artificial Intelligence*, 100(1–2), 87–123. https://www.sciencedirect.com/science/article/pii/S0004370297000829
- Frank, I., & Basin, D. (2001). A theoretical and empirical investigation of search in imperfect information games. *Theoretical Computer Science*, 252(1–2), 217–256. https://www.sciencedirect.com/science/article/pii/S0304397500000839
- Ginsberg, M. L. (2001). GIB: Imperfect Information in a Computationally Challenging Game. *JAIR*, 14, 303–358. https://www.jair.org/index.php/jair/article/view/10279
- Long, J., Sturtevant, N. R., Buro, M., & Furtak, T. (2010). Understanding the Success of Perfect Information Monte Carlo Sampling in Game Tree Search. *AAAI-10*, 134–140. https://ojs.aaai.org/index.php/AAAI/article/view/7562
- Russell, S., & Norvig, P. (2002). *Artificial Intelligence: A Modern Approach* (2nd ed.). Prentice Hall.
- Cazenave, T., & Ventos, V. (2019). The alpha-mu Search Algorithm for the Game of Bridge. arXiv:1911.07960. https://arxiv.org/abs/1911.07960
- Cazenave, T., Legras, S., & Ventos, V. (2021). Optimizing alpha-mu. arXiv:2101.12639. https://arxiv.org/abs/2101.12639

**ISMCTS and search**
- Cowling, P. I., Powley, E. J., & Whitehouse, D. (2012). Information Set Monte Carlo Tree Search. *IEEE Transactions on Computational Intelligence and AI in Games*, 4(2), 120–143. https://eprints.whiterose.ac.uk/id/eprint/75048/
- Powley, E. J., Cowling, P. I., & Whitehouse, D. (2014). Information capture and reuse strategies in Monte Carlo Tree Search, with applications to games of hidden information. *Artificial Intelligence*, 217, 92–116. https://www.sciencedirect.com/science/article/pii/S0004370214001052
- Whitehouse, D., Powley, E. J., & Cowling, P. I. (2011). Determinization and information set Monte Carlo Tree Search for the card game Dou Di Zhu. *IEEE CIG 2011*. https://ieeexplore.ieee.org/document/6031993/
- Furtak, T., & Buro, M. (2013). Recursive Monte Carlo search for imperfect information games. *IEEE CIG 2013*. https://skatgame.net/mburo/ps/recmc13.pdf
- Goodman, J. (2019). Re-determinizing Information Set Monte Carlo Tree Search in Hanabi. arXiv:1902.06075. https://arxiv.org/abs/1902.06075
- Heinrich, J., & Silver, D. (2015). Smooth UCT Search in Computer Poker. *IJCAI 2015*, 554–560.
- Heinrich, J., & Silver, D. (2016). Deep Reinforcement Learning from Self-Play in Imperfect-Information Games. arXiv:1603.01121. https://arxiv.org/abs/1603.01121
- Sturtevant, N. R. (2008). An Analysis of UCT in Multi-Player Games. *ICGA Journal*, 31(4), 195–208. https://webdocs.cs.ualberta.ca/~nathanst/papers/mpuct_icga.pdf
- Cowling, P. I., Whitehouse, D., & Powley, E. J. (2015). Emergent bluffing and inference with Monte Carlo Tree Search. *IEEE CIG 2015*, 114–121. http://orangehelicopter.com/academic/papers/cig15.pdf

**Team games and coordination**
- von Stengel, B., & Koller, D. (1997). Team-Maxmin Equilibria. *Games and Economic Behavior*, 21(1–2), 309–321. http://www.maths.lse.ac.uk/personal/stengel/TEXTE/teammax.html
- Celli, A., & Gatti, N. (2018). Computational Results for Extensive-Form Adversarial Team Games. *AAAI-18*. https://ojs.aaai.org/index.php/AAAI/article/view/11462
- Zhang, B. H., Farina, G., Celli, A., & Sandholm, T. (2023). Team Belief DAG: Generalizing the Sequence Form to Team Games for Fast Computation of Correlated Team Max-Min Equilibria via Regret Minimization. *ICML 2023*. https://proceedings.mlr.press/v202/zhang23j/zhang23j.pdf
- Carminati, L., Cacciamani, F., Ciccone, M., & Gatti, N. (2022). A Marriage between Adversarial Team Games and 2-player Games. *ICML 2022*. https://proceedings.mlr.press/v162/carminati22a/carminati22a.pdf
- Zhang, B. H., Farina, G., & Sandholm, T. (2022). Subgame Solving in Adversarial Team Games. *NeurIPS 2022*. https://openreview.net/pdf?id=Roiw2Trm-qP
- Nayyar, A., Mahajan, A., & Teneketzis, D. (2013). Decentralized Stochastic Control with Partial History Sharing: A Common Information Approach. *IEEE TAC*, 58(7), 1644–1658. https://arxiv.org/abs/1209.1695
- Brown, N., Bakhtin, A., Lerer, A., & Gong, Q. (2020). Combining Deep Reinforcement Learning and Search for Imperfect-Information Games. *NeurIPS 2020*. https://arxiv.org/abs/2007.13544
- Bard, N., Foerster, J. N., Chandar, S., Burch, N., Lanctot, M., Song, H. F., Parisotto, E., Dumoulin, V., Moitra, S., Hughes, E., Dunning, I., Mourad, S., Larochelle, H., Bellemare, M. G., & Bowling, M. (2020). The Hanabi Challenge: A New Frontier for AI Research. *Artificial Intelligence*, 280, 103216. https://arxiv.org/abs/1902.00506
- Cox, C., De Silva, J., Deorsey, P., Kenter, F. H. J., Retter, T., & Tobin, J. (2015). How to Make the Perfect Fireworks Display: Two Strategies for Hanabi. *Mathematics Magazine*, 88(5), 323–336. https://www.tandfonline.com/doi/abs/10.4169/math.mag.88.5.323
- O'Dwyer, A. (2018). Hat-game strategies in Hanabi. https://quuxplusone.github.io/blog/2018/03/29/hat-guessing-in-hanabi/
- Foerster, J. N., Song, H. F., Hughes, E., Burch, N., Dunning, I., Whiteson, S., Botvinick, M., & Bowling, M. (2019). Bayesian Action Decoder for Deep Multi-Agent Reinforcement Learning. *ICML 2019*, 1942–1951. https://arxiv.org/abs/1811.01458
- Hu, H., & Foerster, J. N. (2020). Simplified Action Decoder for Deep Multi-Agent Reinforcement Learning. *ICLR 2020*. https://openreview.net/pdf?id=B1xm3RVtwB
- Hu, H., Lerer, A., Peysakhovich, A., & Foerster, J. N. (2020). "Other-Play" for Zero-Shot Coordination. *ICML 2020*, PMLR 119. https://arxiv.org/abs/2003.02979
- Hu, H., Lerer, A., Cui, B., Pineda, L., Wu, D., Brown, N., & Foerster, J. N. (2021). Off-Belief Learning. *ICML 2021*, PMLR 139, 4369–4379. https://proceedings.mlr.press/v139/hu21c.html
- Lupu, A., Cui, B., Hu, H., & Foerster, J. N. (2021). Trajectory Diversity for Zero-Shot Coordination. *ICML 2021*, PMLR 139, 7204–7213. https://proceedings.mlr.press/v139/lupu21a.html
- Rong, J., Qin, T., & An, B. (2019). Competitive Bridge Bidding with Deep Neural Networks. *AAMAS 2019*. https://arxiv.org/abs/1903.00900
- Gong, Q., Jiang, Y., & Tian, Y. (2020). Simple is Better: Training an End-to-End Contract Bridge Bidding Agent without Human Knowledge. https://openreview.net/forum?id=SklViCEFPH
- Buro, M., Long, J. R., Furtak, T., & Sturtevant, N. R. (2009). Improving State Evaluation, Inference, and Search in Trick-Based Card Games. *IJCAI 2009*, 1407–1413. https://www.ijcai.org/Proceedings/09/Papers/236.pdf
- Edelkamp, S. (2021). Knowledge-Based Paranoia Search in Trick-Taking. arXiv:2104.05423. https://arxiv.org/abs/2104.05423
- Di Palma, S., & Lanzi, P. L. (2018). Traditional Wisdom and Monte Carlo Tree Search Face-to-Face in the Card Game Scopone. arXiv:1807.06813. https://arxiv.org/abs/1807.06813
- Müller, P. (2020). Tichu Bot. Semester thesis, ETH Zurich. https://pub.tik.ee.ethz.ch/students/2020-FS/SA-2020-19.pdf
- Wyss, N. Reinforcement Learning for Tichu. BA thesis, University of Bern. https://prg.inf.unibe.ch/wp-content/uploads/2024/08/BA_NicolasWyss.pdf

**Combinatorial inference and belief**
- Valiant, L. G. (1979). The complexity of computing the permanent. *Theoretical Computer Science*, 8(2), 189–201. https://www.sciencedirect.com/science/article/pii/0304397579900446
- Jerrum, M., Sinclair, A., & Vigoda, E. (2004). A polynomial-time approximation algorithm for the permanent of a matrix with nonnegative entries. *Journal of the ACM*, 51(4), 671–697. https://faculty.cc.gatech.edu/~vigoda/Permanent.pdf
- Barvinok, A. (2008). An approximation algorithm for counting contingency tables. arXiv:0803.3948. https://arxiv.org/abs/0803.3948
- Diaconis, P., & Gangolli, A. (1995). Rectangular arrays with fixed margins. In *Discrete Probability and Algorithms*, IMA Vol. 72, 15–41. https://link.springer.com/chapter/10.1007/978-1-4612-0801-3_3
- Chen, Y., Diaconis, P., Holmes, S. P., & Liu, J. S. (2005). Sequential Monte Carlo Methods for Statistical Analysis of Tables. *JASA*, 100(469), 109–120. https://www.tandfonline.com/doi/abs/10.1198/016214504000001303
- Bezáková, I., Sinclair, A., Štefankovič, D., & Vigoda, E. (2012). Negative Examples for Sequential Importance Sampling of Binary Contingency Tables. *Algorithmica*, 64(4), 606–620 (ESA 2006, 136–147). https://arxiv.org/abs/math/0606650
- Régin, J.-C. (1994). A Filtering Algorithm for Constraints of Difference in CSPs. *AAAI-94*, 362–367. https://cdn.aaai.org/AAAI/1994/AAAI94-055.pdf
- Régin, J.-C. (1996). Generalized Arc Consistency for Global Cardinality Constraint. *AAAI-96*, 209–215. https://cdn.aaai.org/AAAI/1996/AAAI96-031.pdf
- Hall, P. (1935). On Representatives of Subsets. *Journal of the London Mathematical Society*, s1-10(1), 26–30.
- Gale, D. (1957). A theorem on flows in networks. *Pacific Journal of Mathematics*, 7(2), 1073–1082.
- Ryser, H. J. (1957). Combinatorial properties of matrices of zeros and ones. *Canadian Journal of Mathematics*, 9, 371–377.
- Solinas, C., Rebstock, D., Sturtevant, N. R., & Buro, M. (2023). History Filtering in Imperfect Information Games: Algorithms and Complexity. arXiv:2311.14651. https://arxiv.org/abs/2311.14651

**Opponent modelling and inference**
- Solinas, C., Rebstock, D., & Buro, M. (2019). Improving Search with Supervised Learning in Trick-Based Card Games. *AAAI-19*, 33(1), 1158–1165. https://arxiv.org/abs/1903.09604
- Rebstock, D., Solinas, C., Buro, M., & Sturtevant, N. R. (2019). Policy Based Inference in Trick-Taking Card Games. *IEEE CoG 2019*. https://arxiv.org/abs/1905.10911
- Rebstock, D., Solinas, C., & Buro, M. (2019). Learning Policies from Human Data for Skat. arXiv:1905.10907. https://arxiv.org/abs/1905.10907
- Lisý, V., & Bowling, M. (2017). Equilibrium Approximation Quality of Current No-Limit Poker Bots. *AAAI-17 Workshops*. arXiv:1612.07547. https://arxiv.org/abs/1612.07547

**Evaluation**
- Johanson, M., Waugh, K., Bowling, M., & Zinkevich, M. (2011). Accelerating Best Response Calculation in Large Extensive Games. *IJCAI 2011*, 258–265. https://www.ijcai.org/Proceedings/11/Papers/054.pdf
- Coulom, R. (2008). Whole-History Rating: A Bayesian Rating System for Players of Time-Varying Strength. *Computers and Games 2008*, LNCS 5131, 113–124. https://www.remi-coulom.fr/WHR/
- Owen, A. B. (2013). *Monte Carlo theory, methods and examples*, Ch. 8: Variance reduction. https://artowen.su.domains/mc/Ch-var-basic.pdf
- (2025). Is Elo Rating Reliable? A Study Under Model Misspecification. arXiv:2502.10985. https://arxiv.org/html/2502.10985v1

**Literature / Fish / Go Fish**
- McLeod, J. Literature. *pagat.com*. https://www.pagat.com/quartet/literature.html
- Literature (card game). *Wikipedia*. https://en.wikipedia.org/wiki/Literature_(card_game)
- Goadrich, M., Morenville, A., & Piette, É. (2026). Valet: A Standardized Testbed of Traditional Imperfect-Information Card Games. arXiv:2603.03252. https://arxiv.org/abs/2603.03252
- Meng, F., & Lucas, S. (2024). Deduction Game Framework and Information Set Entropy Search. *IEEE CoG 2024*. arXiv:2407.21178. https://arxiv.org/abs/2407.21178
- Somani, N. `neelsomani/literature`. https://github.com/neelsomani/literature
- `Dynosol/playfish.io`. https://github.com/Dynosol/playfish.io
- `Raghav-Sao/literature`. https://github.com/Raghav-Sao/literature
- `iuruoy-shao/fish`. https://github.com/iuruoy-shao/fish

---

## Explicit gaps (searched for, not found)

- Peer-reviewed AI research on Literature / Canadian Fish / Russian Fish. Nothing.
- Peer-reviewed game-theoretic analysis of Go Fish. Nothing.
- A published follow-up analysis of the subset-armed bandit problem, which Cowling
  et al. 2012 flagged as future work. Nothing found.
- A peer-reviewed game-search paper whose contribution is common random numbers or
  paired comparison as a variance-reduction method in MCTS. Nothing found; the
  practice appears as protocol detail inside other papers (Long et al. 2010,
  Solinas et al. 2019) and as inherited duplicate-bridge convention.
- Any treatment of a coordination channel that is simultaneously (i) the only
  legal signalling mechanism between teammates and (ii) fully observed by the
  opposing team. This is, on the evidence of this survey, genuinely open, and is
  the strongest novelty claim available to us.
