"""Always-valid sequential tests for paired-deal differentials.

WHY NOT JUST PEEK AT THE t-TEST
-------------------------------
Every experiment in v0.3 ran a fixed number of pairs, and the temptation to
watch the interval and stop when it looked convincing was handled by
willpower. Willpower is not a type-I error guarantee. MEASURED (4000
synthetic null experiments, each monitored after every one of 4000 paired
deals, ``scripts4/run_typeI_simulation.py``): peeking at the fixed-n 95%
t-interval rejects a TRUE null 68.8% of the time against the real measured
differential distribution, and 92.1% against a skewed one. Since the whole
point of this infrastructure is to stop runs early when the answer is clear,
the stopping rule itself has to be valid under continuous monitoring.

WHAT IS IMPLEMENTED
-------------------
Two nonparametric, *anytime-valid* procedures for the mean of a bounded
observation, both from Waudby-Smith & Ramdas, "Estimating means of bounded
random variables by betting" (JRSS-B 2024):

1. ``EmpiricalBernsteinCS`` - the predictable-plug-in empirical-Bernstein
   confidence sequence. It emits an interval at every t with the guarantee
   ``P(exists t : mu not in CI_t) <= alpha``. It is the right object when
   you want an effect-size estimate you can quote at any moment, and it
   yields a test by rejecting the first time the interval excludes the null.

2. ``BettingTest`` - a pair of one-sided test supermartingales (capital
   processes) with aGRAPA bets, one for ``mu > m0`` and one for ``mu < m0``,
   each run at level alpha/2. Validity is Ville's inequality:
   ``P(exists t : K_t >= 1/alpha) <= alpha`` for a nonnegative supermartingale
   with ``K_0 = 1``. This is the more powerful of the two for a pure
   accept/reject question, because it spends all its evidence on the
   hypothesis rather than on covering the whole parameter.

Both need observations in a KNOWN bounded range. Paired set-differentials
are bounded by construction: a pair sums two games, each of which can differ
by at most the number of half-suits, so the range is [-18, +18] on the
54-card deck. ``HarnessConfig.diff_bound`` supplies it. Passing an
observation outside the declared range raises rather than silently voiding
the guarantee, because the bound is load-bearing.

WHY BOTH, AND WHICH TO USE
--------------------------
Default is ``method="betting"``. MEASURED at the effect size this project
cares about (0.3 sets/pair against the real per-pair sd of 3.869): both reach
100% power, but the betting test's median stopping time is 1330 pairs against
the confidence sequence's 1963, i.e. it stops 32% sooner for the same alpha.
Its false-positive rate is higher than the CS's (2.1% vs 0.5%) but still
comfortably under the nominal 5%; the CS pays for its interval by being more
conservative. Use the CS when the deliverable is an interval.

CALIBRATION IS MEASURED, NOT ASSUMED. ``simulate_type_i`` runs synthetic null
experiments under CONTINUOUS monitoring and reports the empirical
false-positive rate with an exact binomial upper bound; ``simulate_power``
does the same against an alternative. The numbers this file was accepted on
are in ``fish4/evalx/README.md`` and
``results/v04_sequential_calibration.json``; a reduced-size version of the
same simulation runs in ``tests4/test_evalx.py`` on every test run.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional, Sequence

import numpy as np

Sampler = Callable[[np.random.Generator, int, int], np.ndarray]


class OutOfBounds(ValueError):
    """An observation fell outside the declared range.

    Not recoverable by clipping: the validity of both procedures rests on the
    range, so a violated range means the reported error control is void.
    """


# ---------------------------------------------------------------------------
# Shared predictable plug-ins
# ---------------------------------------------------------------------------
#
# Both procedures need running estimates of the mean and variance that are
# PREDICTABLE (a function of X_1..X_{t-1} only) at the moment they are used to
# choose the bet lambda_t. Using X_t to choose lambda_t would break the
# supermartingale property, which is the single easiest way to build a
# sequential test that looks calibrated in a smoke test and is not.
#
# The 1/2 and 1/4 offsets are the WSR priors: they make the estimates
# well-defined at t=0 and keep lambda finite on the first step.

def _psi_e(lam: np.ndarray) -> np.ndarray:
    """psi_E(lambda) = (-log(1-lambda) - lambda) / 4, the empirical-Bernstein
    cumulant bound. Requires lambda < 1, which the truncation ``c`` enforces."""
    return (-np.log1p(-lam) - lam) / 4.0


@dataclass
class _PlugIn:
    """Running mean/variance plug-ins, vectorized over independent streams."""

    n_streams: int = 1
    t: int = 0
    sum_x: np.ndarray = field(default=None)
    sum_sq_dev: np.ndarray = field(default=None)

    def __post_init__(self):
        self.sum_x = np.zeros(self.n_streams)
        self.sum_sq_dev = np.zeros(self.n_streams)

    @property
    def mu(self) -> np.ndarray:
        """mu_hat_t = (1/2 + sum X_i) / (t + 1)."""
        return (0.5 + self.sum_x) / (self.t + 1)

    @property
    def sigma2(self) -> np.ndarray:
        """sigma2_hat_t = (1/4 + sum (X_i - mu_hat_i)^2) / (t + 1)."""
        return (0.25 + self.sum_sq_dev) / (self.t + 1)

    def push(self, x: np.ndarray) -> None:
        self.t += 1
        self.sum_x = self.sum_x + x
        mu_t = (0.5 + self.sum_x) / (self.t + 1)
        self.sum_sq_dev = self.sum_sq_dev + (x - mu_t) ** 2


# ---------------------------------------------------------------------------
# Empirical-Bernstein confidence sequence
# ---------------------------------------------------------------------------

class EmpiricalBernsteinCS:
    """Predictable-plug-in empirical-Bernstein confidence sequence.

    Vectorized over ``n_streams`` independent experiments so the calibration
    simulation runs the SAME code path as a single live experiment; the two
    are asserted equal in ``tests4/test_evalx.py``.

    ``lower``/``upper`` are the a-priori bounds of the observation. Internally
    everything works on ``z = (x - lower) / (upper - lower)`` in [0,1]; the
    reported interval is mapped back to the caller's units.
    """

    def __init__(self, alpha: float = 0.05, lower: float = -18.0,
                 upper: float = 18.0, c: float = 0.5, n_streams: int = 1,
                 running_intersection: bool = True):
        if not (0 < alpha < 1):
            raise ValueError("alpha must be in (0,1)")
        if upper <= lower:
            raise ValueError("upper must exceed lower")
        if not (0 < c < 1):
            raise ValueError("truncation c must be in (0,1)")
        self.alpha = alpha
        self.lower = float(lower)
        self.upper = float(upper)
        self.width_scale = self.upper - self.lower
        self.c = c
        self.n_streams = n_streams
        self.running_intersection = running_intersection

        self._plug = _PlugIn(n_streams)
        self._sum_lam = np.zeros(n_streams)
        self._sum_lam_x = np.zeros(n_streams)
        self._sum_v_psi = np.zeros(n_streams)
        self._lo = np.zeros(n_streams)          # in [0,1] scaled units
        self._hi = np.ones(n_streams)
        self.t = 0

    # -- scaling ------------------------------------------------------------

    def _scale(self, x) -> np.ndarray:
        arr = np.asarray(x, dtype=float).reshape(-1)
        if arr.size != self.n_streams:
            raise ValueError(f"expected {self.n_streams} observations, "
                             f"got {arr.size}")
        if np.any(arr < self.lower - 1e-9) or np.any(arr > self.upper + 1e-9):
            bad = arr[(arr < self.lower - 1e-9) | (arr > self.upper + 1e-9)]
            raise OutOfBounds(
                f"observation(s) {bad[:5]} outside declared range "
                f"[{self.lower}, {self.upper}]; the anytime-validity of this "
                f"confidence sequence depends on that range, so the run is "
                f"void rather than merely optimistic")
        return (arr - self.lower) / self.width_scale

    def _unscale(self, z: np.ndarray) -> np.ndarray:
        return self.lower + self.width_scale * z

    # -- the update ---------------------------------------------------------

    def update(self, x) -> tuple:
        """Feed one observation per stream; return the current (lo, hi)."""
        z = self._scale(x)
        t = self.t + 1

        # lambda_t uses ONLY sigma2_{t-1} and mu_{t-1}: predictable by design.
        sigma2_prev = self._plug.sigma2
        mu_prev = self._plug.mu
        denom = sigma2_prev * t * math.log(1.0 + t)
        lam = np.sqrt(2.0 * math.log(2.0 / self.alpha) / np.maximum(denom, 1e-300))
        lam = np.minimum(lam, self.c)

        v = 4.0 * (z - mu_prev) ** 2
        self._sum_lam += lam
        self._sum_lam_x += lam * z
        self._sum_v_psi += v * _psi_e(lam)

        self._plug.push(z)
        self.t = t

        centre = self._sum_lam_x / self._sum_lam
        half = (math.log(2.0 / self.alpha) + self._sum_v_psi) / self._sum_lam
        lo = np.maximum(0.0, centre - half)
        hi = np.minimum(1.0, centre + half)
        if self.running_intersection:
            # Intersecting a confidence sequence with its own past is valid
            # (the union bound over times is already paid) and never widens.
            lo = np.maximum(lo, self._lo)
            hi = np.minimum(hi, self._hi)
        self._lo, self._hi = lo, hi
        return self.interval()

    def interval(self) -> tuple:
        return (self._unscale(self._lo), self._unscale(self._hi))

    def excludes(self, null: float = 0.0) -> np.ndarray:
        lo, hi = self.interval()
        return (lo > null) | (hi < null)

    def point_estimate(self) -> np.ndarray:
        """The lambda-weighted centre, in the caller's units."""
        return self._unscale(self._sum_lam_x / np.maximum(self._sum_lam, 1e-300))


# ---------------------------------------------------------------------------
# Betting test (pair of one-sided test supermartingales)
# ---------------------------------------------------------------------------

class BettingTest:
    """Two-sided anytime-valid test of ``H0: mu == null`` by betting.

    Capital for the "mu > null" direction is
    ``K_t = prod_i (1 + lam_i (Z_i - m0))`` with ``lam_i >= 0`` predictable and
    ``Z_i, m0`` in [0,1]. Under H0 (indeed under ``mu <= m0``) each factor has
    conditional expectation ``1 + lam_i (mu - m0) <= 1``, so ``K`` is a
    nonnegative supermartingale started at 1 and Ville's inequality gives
    ``P(exists t : K_t >= 2/alpha) <= alpha/2``. The mirrored process
    (``Z -> 1 - Z``) covers ``mu < null``; a union bound over the two
    directions gives an overall level ``alpha``.

    Bets are aGRAPA (approximate-GRO with a-priori plug-ins):
    ``lam_t = clip((mu_{t-1} - m0) / (sigma2_{t-1} + (mu_{t-1} - m0)^2),
    0, c/m0)``. The truncation ``c < 1`` keeps every factor strictly positive,
    so the log-capital never goes to -inf on a bad step.
    """

    def __init__(self, alpha: float = 0.05, lower: float = -18.0,
                 upper: float = 18.0, null: float = 0.0, c: float = 0.5,
                 n_streams: int = 1):
        if not (0 < alpha < 1):
            raise ValueError("alpha must be in (0,1)")
        if not (lower < null < upper):
            raise ValueError("null must lie strictly inside [lower, upper]")
        self.alpha = alpha
        self.lower = float(lower)
        self.upper = float(upper)
        self.width_scale = self.upper - self.lower
        self.null = float(null)
        self.m0 = (null - lower) / self.width_scale
        self.c = c
        self.n_streams = n_streams

        self._plug = _PlugIn(n_streams)
        self.log_wealth_up = np.zeros(n_streams)
        self.log_wealth_down = np.zeros(n_streams)
        self.log_threshold = math.log(2.0 / alpha)   # alpha/2 per direction
        self.t = 0

    def _scale(self, x) -> np.ndarray:
        arr = np.asarray(x, dtype=float).reshape(-1)
        if arr.size != self.n_streams:
            raise ValueError(f"expected {self.n_streams} observations, "
                             f"got {arr.size}")
        if np.any(arr < self.lower - 1e-9) or np.any(arr > self.upper + 1e-9):
            raise OutOfBounds(
                f"observation outside declared range [{self.lower}, "
                f"{self.upper}]; Ville's inequality no longer applies")
        return (arr - self.lower) / self.width_scale

    def update(self, x) -> None:
        z = self._scale(x)
        mu_prev = self._plug.mu
        sig2_prev = self._plug.sigma2

        gap_up = mu_prev - self.m0
        lam_up = np.clip(gap_up / (sig2_prev + gap_up ** 2), 0.0,
                         self.c / self.m0)
        gap_dn = self.m0 - mu_prev
        lam_dn = np.clip(gap_dn / (sig2_prev + gap_dn ** 2), 0.0,
                         self.c / (1.0 - self.m0))

        self.log_wealth_up += np.log1p(lam_up * (z - self.m0))
        self.log_wealth_down += np.log1p(lam_dn * (self.m0 - z))

        self._plug.push(z)
        self.t += 1

    # -- readouts -----------------------------------------------------------

    @property
    def log_e_value(self) -> np.ndarray:
        """log of the two-sided e-value (max of the two directions, times
        alpha/2 accounting handled by ``log_threshold``)."""
        return np.maximum(self.log_wealth_up, self.log_wealth_down)

    def rejected(self) -> np.ndarray:
        return self.log_e_value >= self.log_threshold

    def direction(self) -> np.ndarray:
        """+1 where the 'mu > null' capital crossed, -1 where 'mu < null' did,
        0 where neither has."""
        up = self.log_wealth_up >= self.log_threshold
        dn = self.log_wealth_down >= self.log_threshold
        return np.where(up, 1, np.where(dn, -1, 0))

    def running_mean(self) -> np.ndarray:
        return self.lower + self.width_scale * (
            self._plug.sum_x / max(1, self._plug.t))


# ---------------------------------------------------------------------------
# The user-facing single-experiment wrapper
# ---------------------------------------------------------------------------

@dataclass
class SequentialDecision:
    """State of a live sequential experiment after ``n`` observations."""

    n: int
    decision: str                # "x_better" | "y_better" | "continue" | "inconclusive"
    estimate: float
    ci_lo: float
    ci_hi: float
    log_e_value: float
    stopped: bool

    def summary(self) -> str:
        return (f"n={self.n:5d}  {self.decision:12s}  "
                f"est {self.estimate:+.3f} sets/pair  "
                f"anytime CI [{self.ci_lo:+.3f},{self.ci_hi:+.3f}]  "
                f"log10(e) {self.log_e_value / math.log(10):.2f}")


class SequentialTest:
    """Run a paired-deal experiment until the answer is clear (or n_max).

    Maintains BOTH procedures: the betting pair supplies the decision (it is
    the more powerful), the empirical-Bernstein CS supplies an anytime-valid
    interval so a stopped experiment can still quote an effect size that is
    honest about the optional stopping. The two share their alpha budget by
    being reported separately, not combined: the decision is at level
    ``alpha`` and the interval covers at level ``1 - alpha``, and we never
    claim the pair is jointly at ``alpha``.
    """

    def __init__(self, alpha: float = 0.05, lower: float = -18.0,
                 upper: float = 18.0, null: float = 0.0,
                 method: str = "betting", n_max: Optional[int] = None,
                 c: float = 0.5):
        if method not in ("betting", "eb_cs"):
            raise ValueError("method must be 'betting' or 'eb_cs'")
        self.method = method
        self.alpha = alpha
        self.null = null
        self.n_max = n_max
        self.cs = EmpiricalBernsteinCS(alpha=alpha, lower=lower, upper=upper,
                                       c=c, n_streams=1)
        self.bet = BettingTest(alpha=alpha, lower=lower, upper=upper,
                               null=null, c=c, n_streams=1)
        self.n = 0
        self._values: list = []

    def update(self, x: float) -> SequentialDecision:
        self.cs.update([x])
        self.bet.update([x])
        self.n += 1
        self._values.append(float(x))
        lo, hi = self.cs.interval()
        lo, hi = float(lo[0]), float(hi[0])

        if self.method == "betting":
            d = int(self.bet.direction()[0])
        else:
            d = 1 if lo > self.null else (-1 if hi < self.null else 0)

        if d > 0:
            decision, stopped = "x_better", True
        elif d < 0:
            decision, stopped = "y_better", True
        elif self.n_max is not None and self.n >= self.n_max:
            decision, stopped = "inconclusive", True
        else:
            decision, stopped = "continue", False

        return SequentialDecision(
            n=self.n, decision=decision,
            estimate=statistics.fmean(self._values),
            ci_lo=lo, ci_hi=hi,
            log_e_value=float(self.bet.log_e_value[0]), stopped=stopped)

    def run(self, stream: Iterable) -> SequentialDecision:
        """Consume ``stream`` until a decision is reached or it is exhausted."""
        last = SequentialDecision(0, "continue", 0.0, float("-inf"),
                                  float("inf"), 0.0, False)
        for x in stream:
            last = self.update(x)
            if last.stopped:
                break
        if not last.stopped and (self.n_max is None or self.n < self.n_max):
            last.decision = "inconclusive"
            last.stopped = True
        return last


# ---------------------------------------------------------------------------
# Samplers for the calibration simulations
# ---------------------------------------------------------------------------

def gaussian_sampler(sd: float, mean: float = 0.0,
                     half_range: Optional[float] = None) -> Sampler:
    """Normal noise, optionally truncated to ``+/- half_range`` before the
    mean shift.

    Truncation is not cosmetic: both procedures are only valid for bounded
    observations, and an untruncated normal will eventually produce a value
    outside any declared range (which correctly raises ``OutOfBounds``).
    Clipping SYMMETRIC noise leaves its mean at exactly zero, so the null
    stays exact; the shift is applied afterwards.
    """
    def sample(rng, n_streams, n_steps):
        z = rng.normal(0.0, sd, size=(n_steps, n_streams))
        if half_range is not None:
            z = np.clip(z, -half_range, half_range)
        return z + mean
    return sample


def empirical_sampler(values: Sequence[float], mean: float = 0.0) -> Sampler:
    """Bootstrap from REAL measured per-pair differentials, recentred to an
    exact mean.

    Preferred over a Gaussian null: the real differential distribution is
    discrete, skewed and heavier-tailed than normal, and those are exactly the
    features that break procedures which assume normality. Recentring by the
    sample mean makes the resampling distribution's mean exactly ``mean``, so
    the null is exact rather than approximate.
    """
    arr = np.asarray(values, dtype=float)
    arr = arr - arr.mean() + mean

    def sample(rng, n_streams, n_steps):
        return rng.choice(arr, size=(n_steps, n_streams), replace=True)
    return sample


def symmetric_bound(values: Sequence[float], mean: float = 0.0,
                    floor: float = 0.0) -> float:
    """Smallest symmetric range that contains ``empirical_sampler``'s output.

    Declaring a range wider than necessary costs a little power (the
    empirical-Bernstein and betting bounds both scale their second-order term
    with the range) but never costs validity, so when in doubt widen.
    """
    arr = np.asarray(values, dtype=float)
    arr = arr - arr.mean() + mean
    return max(floor, float(np.ceil(np.abs(arr).max())))


def two_point_sampler(sd: float, skew: float = 0.9, mean: float = 0.0) -> Sampler:
    """A deliberately nasty null: a rare large value against a common small
    one, matched to ``sd``. Heavy skew is where naive Bernstein-style bounds
    and normal approximations part company."""
    p = 1.0 - skew
    a = sd * math.sqrt((1 - p) / p)
    b = -sd * math.sqrt(p / (1 - p))

    def sample(rng, n_streams, n_steps):
        u = rng.random(size=(n_steps, n_streams))
        return np.where(u < p, a, b) + mean
    return sample


# ---------------------------------------------------------------------------
# Calibration simulations
# ---------------------------------------------------------------------------

@dataclass
class SimulationResult:
    label: str
    method: str
    n_reps: int
    n_max: int
    alpha: float
    n_rejected: int
    n_correct_sign: int
    stop_times: list = field(default_factory=list)
    rejection_curve: list = field(default_factory=list)   # (t, cumulative rate)

    @property
    def rate(self) -> float:
        return self.n_rejected / self.n_reps

    @property
    def correct_rate(self) -> float:
        return self.n_correct_sign / self.n_reps

    def binomial_ci(self, conf: float = 0.95) -> tuple:
        """Exact Clopper-Pearson interval for the rejection rate.

        Computed from the Beta quantile via a bisection on the regularized
        incomplete beta function so this module keeps its scipy-free
        dependency footprint (numpy only, as the repo does elsewhere).
        """
        return _clopper_pearson(self.n_rejected, self.n_reps, conf)

    @property
    def median_stop(self) -> float:
        return float(np.median(self.stop_times)) if self.stop_times else float("nan")

    def summary(self) -> str:
        lo, hi = self.binomial_ci()
        s = (f"{self.label:34s} {self.method:8s} "
             f"rate {self.rate:6.3%} [{lo:.3%},{hi:.3%}] "
             f"of {self.n_reps} reps, n_max {self.n_max}")
        if self.stop_times:
            s += (f", median stop {self.median_stop:.0f}"
                  f", correct sign {self.correct_rate:.3%}")
        return s

    def to_dict(self) -> dict:
        lo, hi = self.binomial_ci()
        return {"label": self.label, "method": self.method,
                "n_reps": self.n_reps, "n_max": self.n_max,
                "alpha": self.alpha, "n_rejected": self.n_rejected,
                "rate": self.rate, "rate_ci95": [lo, hi],
                "correct_sign_rate": self.correct_rate,
                "median_stop": self.median_stop,
                "mean_stop": float(np.mean(self.stop_times))
                if self.stop_times else None,
                "rejection_curve": self.rejection_curve}


def _betainc_regularized(a: float, b: float, x: float, n: int = 4096) -> float:
    """I_x(a,b) by Simpson quadrature on the Beta density.

    Adequate here: it is used only to place a Clopper-Pearson endpoint to
    about 1e-6, and the alternative is a scipy dependency the repo does not
    otherwise carry. Checked against known values in tests4.
    """
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    n = n if n % 2 == 0 else n + 1
    ts = np.linspace(0.0, x, n + 1)
    ts = np.clip(ts, 1e-15, 1 - 1e-15)
    log_f = (a - 1) * np.log(ts) + (b - 1) * np.log1p(-ts)
    f = np.exp(log_f - (math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)))
    h = x / n
    total = f[0] + f[-1] + 4 * f[1:-1:2].sum() + 2 * f[2:-1:2].sum()
    return float(min(1.0, max(0.0, total * h / 3.0)))


def _clopper_pearson(k: int, n: int, conf: float = 0.95) -> tuple:
    if n == 0:
        return (0.0, 1.0)
    a = 1.0 - conf

    def quantile(target: float, beta_a: float, beta_b: float) -> float:
        """p such that I_p(beta_a, beta_b) == target, by bisection.
        I is increasing in p, so plain bisection converges."""
        lo, hi = 0.0, 1.0
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if _betainc_regularized(beta_a, beta_b, mid, n=1024) > target:
                hi = mid
            else:
                lo = mid
        return 0.5 * (lo + hi)

    # Clopper-Pearson: lower = Beta(a/2; k, n-k+1), upper = Beta(1-a/2; k+1, n-k)
    low = 0.0 if k == 0 else quantile(a / 2, k, n - k + 1)
    high = 1.0 if k == n else quantile(1 - a / 2, k + 1, n - k)
    return (low, high)


def _simulate(sampler: Sampler, n_reps: int, n_max: int, alpha: float,
              lower: float, upper: float, method: str, seed: int,
              label: str, curve_points: int = 24,
              null: float = 0.0) -> SimulationResult:
    """Core simulation loop, vectorized across reps and monitored EVERY step.

    Continuous monitoring is the whole point: the rejection flag is latched
    the first time a stream crosses, so a procedure that is only valid at a
    fixed n will show up here as an inflated rate rather than passing quietly.
    """
    rng = np.random.default_rng(seed)
    data = sampler(rng, n_reps, n_max)
    if data.shape != (n_max, n_reps):
        raise ValueError(f"sampler returned {data.shape}, expected "
                         f"{(n_max, n_reps)}")

    if method == "betting":
        proc = BettingTest(alpha=alpha, lower=lower, upper=upper, null=null,
                           n_streams=n_reps)
    elif method == "eb_cs":
        proc = EmpiricalBernsteinCS(alpha=alpha, lower=lower, upper=upper,
                                    n_streams=n_reps)
    elif method == "naive_t":
        proc = None            # the deliberately-invalid comparator
    else:
        raise ValueError(f"unknown method {method!r}")

    rejected = np.zeros(n_reps, dtype=bool)
    direction = np.zeros(n_reps, dtype=int)
    stop_time = np.full(n_reps, -1, dtype=int)

    # naive fixed-n t-test state, kept only to quantify how bad peeking is
    s1 = np.zeros(n_reps)
    s2 = np.zeros(n_reps)

    curve_at = sorted(set(int(round(x)) for x in
                          np.geomspace(2, n_max, curve_points)))
    curve = []

    for t in range(n_max):
        x = data[t]
        if method == "betting":
            proc.update(x)
            fresh = (~rejected) & proc.rejected()
            if fresh.any():
                direction[fresh] = proc.direction()[fresh]
        elif method == "eb_cs":
            proc.update(x)
            lo, hi = proc.interval()
            crossed = (lo > null) | (hi < null)
            fresh = (~rejected) & crossed
            if fresh.any():
                direction[fresh] = np.where(lo[fresh] > null, 1, -1)
        else:
            s1 += x
            s2 += x * x
            n = t + 1
            if n >= 3:
                mean = s1 / n
                var = np.maximum(1e-12, (s2 - n * mean * mean) / (n - 1))
                tstat = (mean - null) / np.sqrt(var / n)
                crossed = np.abs(tstat) >= 1.96
                fresh = (~rejected) & crossed
                if fresh.any():
                    direction[fresh] = np.sign(mean[fresh]).astype(int)
            else:
                fresh = np.zeros(n_reps, dtype=bool)

        if fresh.any():
            stop_time[fresh] = t + 1
            rejected |= fresh
        if (t + 1) in curve_at:
            curve.append((t + 1, float(rejected.mean())))

    stops = [int(s) for s in stop_time if s > 0]
    n_correct = int(((direction > 0) & rejected).sum())
    return SimulationResult(label=label, method=method, n_reps=n_reps,
                            n_max=n_max, alpha=alpha,
                            n_rejected=int(rejected.sum()),
                            n_correct_sign=n_correct, stop_times=stops,
                            rejection_curve=curve)


def simulate_type_i(sampler: Sampler, n_reps: int = 2000, n_max: int = 2000,
                    alpha: float = 0.05, lower: float = -18.0,
                    upper: float = 18.0, method: str = "betting",
                    seed: int = 12345, label: str = "null") -> SimulationResult:
    """Empirical false-positive rate under CONTINUOUS monitoring.

    ``sampler`` must generate observations whose mean is exactly the null
    (``empirical_sampler`` and ``gaussian_sampler`` do by construction). A
    valid procedure has ``rate <= alpha`` up to binomial noise, and the
    Clopper-Pearson interval on the result is what the README quotes.
    """
    return _simulate(sampler, n_reps, n_max, alpha, lower, upper, method,
                     seed, label)


def simulate_power(sampler: Sampler, n_reps: int = 2000, n_max: int = 4000,
                   alpha: float = 0.05, lower: float = -18.0,
                   upper: float = 18.0, method: str = "betting",
                   seed: int = 999, label: str = "alt") -> SimulationResult:
    """Power and stopping-time distribution against a shifted sampler.

    ``correct_rate`` counts only rejections in the RIGHT direction, so a
    procedure cannot buy power with sign errors.
    """
    return _simulate(sampler, n_reps, n_max, alpha, lower, upper, method,
                     seed, label)


__all__ = ["OutOfBounds", "EmpiricalBernsteinCS", "BettingTest",
           "SequentialTest", "SequentialDecision", "SimulationResult",
           "gaussian_sampler", "empirical_sampler", "two_point_sampler",
           "simulate_type_i", "simulate_power"]
