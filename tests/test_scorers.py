"""Tests for the three scorers: assertions, drift, judge."""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from promptlock.providers import Completion  # noqa: E402
from promptlock.scorers import assertions, drift, judge  # noqa: E402

CFG = {
    "require_json": True,
    "required_keys": ["category", "urgency", "summary"],
    "enums": {"category": ["billing", "bug"], "urgency": ["low", "high"]},
    "must_not_match": ["^(sure|here'?s)"],
    "max_latency_ms": 3000,
    "max_cost_usd": 0.01,
}

GOOD = json.dumps({"category": "billing", "urgency": "low", "summary": "charged twice"})


def _run(text: str, latency: float = 100.0, cost: float = 0.001) -> dict:
    return {"text": text, "latency_ms": latency, "cost_usd": cost, "tokens": 10}


# -- assertions --------------------------------------------------------------

def test_clean_json_satisfies_everything():
    res = assertions.evaluate(_run(GOOD), CFG)
    assert all(res.values()), [k for k, v in res.items() if not v]


def test_malformed_json_fails_parse_and_keys():
    res = assertions.evaluate(_run("this is not JSON at all"), CFG)
    assert res["json_parses"] is False
    assert res["json_bare"] is False
    assert res["key:category"] is False and res["key:summary"] is False
    assert res["enum:category"] is False


def test_truncated_json_fails_to_parse():
    res = assertions.evaluate(_run(GOOD[: len(GOOD) // 2]), CFG)
    assert res["json_parses"] is False, "a half-written object must not parse"


def test_fenced_json_parses_but_is_not_bare():
    res = assertions.evaluate(_run(f"```json\n{GOOD}\n```"), CFG)
    assert res["json_parses"] is True, "a fence is tolerated by the parser"
    assert res["json_bare"] is False, "but it is still not a bare object"


def test_prose_preamble_trips_the_nomatch_rule():
    res = assertions.evaluate(_run(f"Sure! {GOOD}"), CFG)
    assert res["nomatch:^(sure|here'?s)"] is False


def test_enum_violation_is_caught_even_when_the_key_exists():
    text = json.dumps({"category": "wildcard", "urgency": "low", "summary": "x"})
    res = assertions.evaluate(_run(text), CFG)
    assert res["key:category"] is True
    assert res["enum:category"] is False


def test_latency_and_cost_budgets():
    assert assertions.evaluate(_run(GOOD, latency=9999), CFG)["latency"] is False
    assert assertions.evaluate(_run(GOOD, cost=1.0), CFG)["cost"] is False


def test_counts_and_rate_agree():
    runs = [_run(GOOD), _run("garbage"), _run(GOOD)]
    counts = assertions.counts(runs, CFG)
    rates = assertions.rate(runs, CFG)
    assert counts["json_parses"] == (2, 3)
    assert abs(rates["json_parses"] - 2 / 3) < 1e-9


def test_counts_on_no_runs_is_empty():
    assert assertions.counts([], CFG) == {}
    assert assertions.rate([], CFG) == {}


# -- drift -------------------------------------------------------------------

def test_self_distance_of_identical_texts_is_zero():
    assert drift.self_distance(["same text", "same text", "same text"]) == 0.0


def test_self_distance_of_one_or_none_is_zero():
    assert drift.self_distance(["only one"]) == 0.0
    assert drift.self_distance([]) == 0.0


def test_self_distance_of_disjoint_texts_is_large():
    d = drift.self_distance(["aaaa aaaa aaaa", "zzzz zzzz zzzz"])
    assert d > 0.9, f"share no n-grams, so near-orthogonal, got {d}"


def test_distance_is_symmetric_and_zero_on_self():
    assert drift.distance("hello world", "hello world") < 1e-9
    assert abs(drift.distance("abc def", "ghi jkl") - drift.distance("ghi jkl", "abc def")) < 1e-9


def test_cross_distance_handles_empty_sides():
    assert drift.cross_distance([], ["x"]) == 0.0
    assert drift.cross_distance(["x"], []) == 0.0


def test_embedding_is_unit_length():
    vec = drift.embed("some representative output")
    assert abs(sum(v * v for v in vec) - 1.0) < 1e-9


# -- judge -------------------------------------------------------------------

class _AlwaysPicksFirst:
    """A maximally position-biased judge: whatever is shown first wins."""

    name = "fake"

    def complete(self, prompt: str, run: int = 0, **_):
        return Completion(
            text=json.dumps({"winner": "A", "why": "it was first"}),
            latency_ms=1.0, cost_usd=0.0, tokens=1,
        )


class _PrefersTheGoodOne:
    """Judges on content, so the two orderings agree."""

    name = "fake"

    def complete(self, prompt: str, run: int = 0, **_):
        slot_a = prompt.split("Output A:")[1].split("Output B:")[0]
        winner = "A" if "GOOD" in slot_a else "B"
        return Completion(
            text=json.dumps({"winner": winner, "why": "content"}),
            latency_ms=1.0, cost_usd=0.0, tokens=1,
        )


def test_position_bias_is_reported_as_tie_not_regression():
    verdict = judge.compare(_AlwaysPicksFirst(), "task", "baseline out", "candidate out")
    assert verdict == "tie", "orderings disagree, so the judge must not call a winner"


def test_agreeing_orderings_produce_a_verdict():
    assert judge.compare(_PrefersTheGoodOne(), "task", "BAD", "GOOD") == "better"
    assert judge.compare(_PrefersTheGoodOne(), "task", "GOOD", "BAD") == "worse"


def test_unparseable_judge_reply_falls_back_to_tie():
    class _Babbling:
        name = "fake"

        def complete(self, prompt, run=0, **_):
            return Completion(text="I cannot decide", latency_ms=1.0, cost_usd=0.0, tokens=1)

    assert judge.compare(_Babbling(), "task", "a", "b") == "tie"


def test_mock_judge_prefers_the_output_matching_the_hint():
    mock = judge.MockJudge()
    hint = {"category": "billing", "urgency": "high"}
    right = json.dumps({"category": "billing", "urgency": "high", "summary": "s"})
    wrong = json.dumps({"category": "bug", "urgency": "low", "summary": "s"})
    assert mock.compare("task", wrong, right, hint) == "better"
    assert mock.compare("task", right, wrong, hint) == "worse"
    assert mock.compare("task", right, right, hint) == "tie"


def test_judge_is_disabled_when_asked():
    assert judge.get_judge(_AlwaysPicksFirst(), enabled=False) is None
