"""Tests for promptlock.stats.

Runs under pytest, or standalone: `python3 tests/test_stats.py`.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from promptlock.stats import wilson, z_for  # noqa: E402


def _close(a: float, b: float, tol: float = 1e-3) -> bool:
    return abs(a - b) < tol


def test_no_trials_is_no_evidence():
    assert wilson(0, 0) == (0.0, 1.0), "zero trials must not imply a confident zero"


def test_known_values_at_95_percent():
    lo, hi = wilson(0, 10)
    assert _close(lo, 0.0) and _close(hi, 0.2775), (lo, hi)

    lo, hi = wilson(10, 10)
    assert _close(lo, 0.7225) and _close(hi, 1.0), (lo, hi)


def test_bounds_stay_inside_unit_interval():
    for trials in range(1, 40):
        for successes in range(trials + 1):
            lo, hi = wilson(successes, trials)
            assert 0.0 <= lo <= hi <= 1.0, (successes, trials, lo, hi)


def test_interval_contains_the_point_estimate():
    for trials in (1, 3, 5, 10, 50):
        for successes in range(trials + 1):
            lo, hi = wilson(successes, trials)
            p = successes / trials
            assert lo <= p <= hi, (successes, trials, p, lo, hi)


def test_more_evidence_narrows_the_interval():
    thin = wilson(1, 3)
    thick = wilson(10, 30)
    assert (thick[1] - thick[0]) < (thin[1] - thin[0]), "same rate, more trials, tighter"


def test_symmetry_of_successes_and_failures():
    for successes, trials in ((0, 10), (3, 10), (7, 20), (1, 3)):
        lo, hi = wilson(successes, trials)
        flo, fhi = wilson(trials - successes, trials)
        assert _close(hi, 1.0 - flo) and _close(lo, 1.0 - fhi)


def test_higher_confidence_widens_the_interval():
    narrow = wilson(5, 10, z_for(0.90))
    wide = wilson(5, 10, z_for(0.99))
    assert (wide[1] - wide[0]) > (narrow[1] - narrow[0])


def test_z_for_known_confidences():
    assert _close(z_for(0.95), 1.95996)
    assert _close(z_for(0.99), 2.57583)
    assert _close(z_for(0.90), 1.64485)


def test_rejects_nonsense_input():
    for bad in (0.0, 1.0, -0.5, 2.0):
        try:
            z_for(bad)
        except ValueError:
            continue
        raise AssertionError(f"z_for({bad}) should have raised")

    try:
        wilson(5, 3)
    except ValueError:
        return
    raise AssertionError("successes > trials should have raised")


def test_two_of_three_is_not_enough_evidence_to_fail():
    """The H10 false positive, stated as a property.

    One pass out of three runs looks catastrophic as a point estimate (33%),
    but the interval still reaches nearly 0.8 -- too weak to fail a build.
    Ten runs at the same rate is a different story.
    """
    _, upper_thin = wilson(1, 3)
    _, upper_thick = wilson(3, 10)
    assert upper_thin > 0.79, upper_thin
    assert upper_thick < upper_thin, "more runs at a similar rate must tighten the case"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"  pass  {name}")
        except AssertionError as e:
            failed.append(name)
            print(f"  FAIL  {name}: {e}")
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
