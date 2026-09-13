"""Run cases and turn three signals into one verdict per case.

Two ideas carry the whole design:

1. **Per-case noise floor.** Each case is run k times so its natural variance
   is measured, not assumed. A change is a regression only if it moves the
   output further than that case moves on its own.

2. **Confirmation re-runs.** A suspected regression is re-sampled before the
   build is failed, the way flaky tests are quarantined. Detecting change is
   trivial; the hard part is not crying wolf.
"""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field

import yaml

from . import stats
from .providers import get_provider
from .scorers import assertions, drift
from .scorers import judge as judge_mod
from .store import fingerprint

PASS, DRIFT, FAIL = "PASS", "DRIFT", "FAIL"


@dataclass
class Config:
    target: str
    cases: str
    runs_per_case: int = 3
    provider: str = "mock"
    drift_floor: float = 0.12
    drift_multiplier: float = 1.5
    # Suite-level gate. A harmless edit nudges a couple of cases by luck; an
    # instruction change shifts the whole distribution. Calibrated from the
    # measured separation between the two (see scripts/calibrate.py).
    suite_drift_threshold: float = 0.025
    systemic_judge_sample: int = 5
    # Failing a build is a hypothesis test, not a point threshold. An assertion
    # is broken only when the upper bound of its new pass-rate, at this
    # confidence, sits `break_margin` below the rate the baseline held.
    break_confidence: float = 0.95
    break_margin: float = 0.2
    judge_enabled: bool = True
    confirm_reruns: bool = True
    # Model id and sampling parameters are part of the system under test, so
    # they are part of the fingerprint. Swapping a model is a change like any
    # prompt edit, and this is what makes it visible.
    model_params: dict = field(default_factory=dict)
    assertions: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: str = "promptlock.yaml") -> "Config":
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
        return cls(**{k: v for k, v in raw.items() if k in cls.__dataclass_fields__})


def _import_target(spec: str):
    """'pkg.mod:function' -> (callable(case_input) -> prompt, module)."""
    mod_name, _, fn_name = spec.partition(":")
    sys.path.insert(0, "")
    mod = importlib.import_module(mod_name)
    importlib.reload(mod)
    return getattr(mod, fn_name), mod


def load_cases(path: str) -> list[dict]:
    with open(path) as f:
        return yaml.safe_load(f)["cases"]


def _run_case(provider, prompt: str, k: int, offset: int = 0) -> list[dict]:
    out = []
    for i in range(offset, offset + k):
        c = provider.complete(prompt, run=i)
        out.append(
            {"text": c.text, "latency_ms": c.latency_ms, "cost_usd": c.cost_usd, "tokens": c.tokens}
        )
    return out


def run_suite(cfg: Config) -> dict:
    render, mod = _import_target(cfg.target)
    provider = get_provider(cfg.provider, cfg.model_params)

    results = {}
    for case in load_cases(cfg.cases):
        prompt = render(case["input"])
        results[case["id"]] = {
            "prompt": prompt,
            "hint": case.get("expect", {}),
            "runs": _run_case(provider, prompt, cfg.runs_per_case),
        }

    return {
        "fingerprint": fingerprint(
            getattr(mod, "PROMPT", ""),
            provider.name,
            {"k": cfg.runs_per_case, **cfg.model_params},
        ),
        "provider": provider.name,
        "runs_per_case": cfg.runs_per_case,
        "model_params": dict(cfg.model_params),
        "cases": results,
    }


def record(cfg: Config) -> dict:
    """Snapshot known-good behaviour, enriched with each case's noise profile."""
    snap = run_suite(cfg)
    for data in snap["cases"].values():
        data["noise_floor"] = round(drift.self_distance([r["text"] for r in data["runs"]]), 4)
        data["assert_rates"] = assertions.rate(data["runs"], cfg.assertions)
    snap["assertions"] = cfg.assertions
    return snap


def _broken(old_rates: dict, new_counts: dict[str, tuple[int, int]], cfg: Config) -> list[str]:
    """Assertions the baseline always satisfied and the candidate now reliably fails.

    "Reliably" is the whole difference between a regression and a bad draw. The
    upper bound of the new pass-rate has to sit a clear margin below what the
    baseline held -- so 2-of-3 unlucky runs is not enough evidence to fail a
    build, while a genuine break at the same nominal rate over more runs is.
    """
    z = stats.z_for(cfg.break_confidence)
    broken = []
    for name, (passes, trials) in new_counts.items():
        baseline_rate = old_rates.get(name, 0.0)
        if baseline_rate < 0.99:
            continue  # the baseline never held it; that is not a regression
        _, upper = stats.wilson(passes, trials, z)
        if upper < baseline_rate - cfg.break_margin:
            broken.append(name)
    return broken


def check(cfg: Config, baseline: dict) -> dict:
    current = run_suite(cfg)
    provider = get_provider(cfg.provider, cfg.model_params)
    judge = judge_mod.get_judge(provider, cfg.judge_enabled)
    k = cfg.runs_per_case

    report = {
        "fingerprint_changed": current["fingerprint"] != baseline.get("fingerprint"),
        "params": {
            "baseline": baseline.get("model_params", {}),
            "current": current.get("model_params", {}),
        },
        "cases": {},
        "summary": {PASS: 0, DRIFT: 0, FAIL: 0},
        "judge_calls": 0,
        "confirm_reruns": 0,
    }

    spend = {"baseline": 0.0, "baseline_runs": 0, "current": 0.0, "current_runs": 0}

    for cid, new in current["cases"].items():
        old = baseline["cases"].get(cid)
        if old is None:
            continue

        old_rates = old.get("assert_rates", {})
        runs = list(new["runs"])
        broken = _broken(old_rates, assertions.counts(runs, cfg.assertions), cfg)

        # Re-sample before failing the build. Flake quarantine, not gut feel.
        # The re-runs join the sample, so the interval tightens on real breaks.
        if broken and cfg.confirm_reruns:
            runs += _run_case(provider, new["prompt"], k, offset=k)
            report["confirm_reruns"] += k
            broken = _broken(old_rates, assertions.counts(runs, cfg.assertions), cfg)

        floor = old.get("noise_floor", 0.0)
        threshold = max(cfg.drift_floor, floor * cfg.drift_multiplier)
        observed = drift.cross_distance([r["text"] for r in old["runs"]], [r["text"] for r in runs])

        verdict, judge_verdict = PASS, None
        if broken:
            verdict = FAIL
        elif observed > threshold:
            # Judge spend scales with the size of the change, not the suite.
            if judge:
                judge_verdict = judge.compare(
                    new["prompt"], old["runs"][0]["text"], runs[0]["text"], new.get("hint")
                )
                report["judge_calls"] += 2
            verdict = FAIL if judge_verdict == "worse" else DRIFT

        spend["baseline"] += sum(r["cost_usd"] for r in old["runs"])
        spend["baseline_runs"] += len(old["runs"])
        spend["current"] += sum(r["cost_usd"] for r in runs)
        spend["current_runs"] += len(runs)

        report["summary"][verdict] += 1
        report["cases"][cid] = {
            "verdict": verdict,
            "broken_assertions": broken,
            "drift": round(observed, 4),
            "threshold": round(threshold, 4),
            "noise_floor": round(floor, 4),
            "judge": judge_verdict,
            "baseline_sample": old["runs"][0]["text"],
            "current_sample": runs[0]["text"],
            "cost_usd": round(sum(r["cost_usd"] for r in runs), 6),
            "prompt": new["prompt"],
            "hint": new.get("hint"),
        }

    # Per-run, not per-suite: a model swap changes unit cost, and the confirmation
    # re-runs mean the two sides do not have the same number of calls.
    report["cost"] = {
        "baseline_per_run": spend["baseline"] / max(1, spend["baseline_runs"]),
        "current_per_run": spend["current"] / max(1, spend["current_runs"]),
        "current_total": round(spend["current"], 6),
    }

    _detect_systemic_drift(report, cfg, judge)
    for c in report["cases"].values():
        c.pop("prompt", None)
        c.pop("hint", None)
    return report


def _median(xs: list[float]) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    mid = len(xs) // 2
    return xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2


def _detect_systemic_drift(report: dict, cfg: Config, judge) -> None:
    """Catch semantic changes that every individual case absorbs.

    "Err on the side of high urgency" breaks no assertion and clears no
    per-case threshold, but it moves the median case three times its usual
    distance. Per-case gating buys precision; this buys back the sensitivity.
    """
    cases = report["cases"]
    median = _median([c["drift"] for c in cases.values()])
    systemic = median > cfg.suite_drift_threshold
    report["suite_drift"] = {
        "median": round(median, 4),
        "threshold": cfg.suite_drift_threshold,
        "systemic": systemic,
    }
    if not systemic or not judge:
        return

    candidates = sorted(
        (c for c in cases.values() if c["verdict"] != FAIL),
        key=lambda c: -c["drift"],
    )[: cfg.systemic_judge_sample]

    for c in candidates:
        c["judge"] = judge.compare(
            c["prompt"], c["baseline_sample"], c["current_sample"], c.get("hint")
        )
        report["judge_calls"] += 2
        if c["judge"] == "worse":
            report["summary"][c["verdict"]] -= 1
            report["summary"][FAIL] += 1
            c["verdict"] = FAIL
            c["broken_assertions"] = c["broken_assertions"] or ["systemic drift + judge: worse"]
