"""Wilson score intervals.

0 out of 3 and 0 out of 30 are both "0%", but only one of them is evidence.
A point threshold cannot tell them apart; an interval can. This turns an
observed pass-rate into the range the true rate plausibly occupies, so failing
a build can require evidence rather than a point estimate crossing a line.

Wilson rather than the textbook normal approximation because it stays inside
[0, 1] and stays sane at p = 0 and p = 1 -- which is exactly where assertion
pass-rates live.
"""

from __future__ import annotations

import math
from statistics import NormalDist


def z_for(confidence: float = 0.95) -> float:
    """Two-sided z for a confidence level. 0.95 -> 1.96."""
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be in (0, 1), got {confidence!r}")
    return NormalDist().inv_cdf(1.0 - (1.0 - confidence) / 2.0)


def wilson(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval (lower, upper) for a binomial pass-rate.

    With no trials the answer is "no evidence", which is the widest possible
    interval -- never a confident zero.
    """
    if trials <= 0:
        return (0.0, 1.0)
    if not 0 <= successes <= trials:
        raise ValueError(f"successes {successes} out of range for {trials} trials")

    p = successes / trials
    z2 = z * z
    denom = 1.0 + z2 / trials
    centre = (p + z2 / (2 * trials)) / denom
    half = z * math.sqrt(p * (1 - p) / trials + z2 / (4 * trials * trials)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))
