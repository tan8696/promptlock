"""Tests for store (on-disk baseline) and providers (the behavioural mock)."""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from promptlock import providers, store  # noqa: E402

SNAPSHOT = {
    "fingerprint": "abc123",
    "provider": "mock",
    "runs_per_case": 5,
    "model_params": {"model": "claude-sonnet-4-6", "temperature": 0.0},
    "cases": {"t001": {"runs": [{"text": "hello", "cost_usd": 0.001}], "noise_floor": 0.0}},
}


# -- store -------------------------------------------------------------------

def test_baseline_survives_a_round_trip():
    with tempfile.TemporaryDirectory() as root:
        path = os.path.join(root, ".promptlock", "baseline.json")
        store.save(dict(SNAPSHOT), path)
        loaded = store.load(path)

    for key, value in SNAPSHOT.items():
        assert loaded[key] == value, key


def test_save_stamps_a_recorded_at_and_creates_the_directory():
    with tempfile.TemporaryDirectory() as root:
        path = os.path.join(root, "nested", "deeper", "baseline.json")
        store.save(dict(SNAPSHOT), path)
        assert os.path.exists(path)
        assert "recorded_at" in store.load(path)


def test_missing_baseline_exits_with_an_instruction():
    with tempfile.TemporaryDirectory() as root, pytest.raises(SystemExit) as excinfo:
        store.load(os.path.join(root, "absent.json"))
    assert "promptlock record" in str(excinfo.value)


def test_rerecording_identical_behaviour_produces_no_diff():
    """The baseline is committed. A no-op record must not churn the file.

    Otherwise every run restamps recorded_at, and "what changed in this PR?" --
    the question a committed baseline exists to answer -- gets buried.
    """
    with tempfile.TemporaryDirectory() as root:
        path = os.path.join(root, "baseline.json")
        store.save(dict(SNAPSHOT), path)
        with open(path, encoding="utf-8") as f:
            first = f.read()

        store.save(dict(SNAPSHOT), path)
        with open(path, encoding="utf-8") as f:
            second = f.read()

    assert first == second, "re-recording identical content must be byte-identical"


def test_changed_behaviour_restamps_recorded_at():
    with tempfile.TemporaryDirectory() as root:
        path = os.path.join(root, "baseline.json")
        store.save(dict(SNAPSHOT), path)
        before = store.load(path)["recorded_at"]

        changed = dict(SNAPSHOT)
        changed["cases"] = {"t001": {"runs": [{"text": "different", "cost_usd": 0.002}]}}
        store.save(changed, path)
        after = store.load(path)

    assert after["recorded_at"] != before, "real changes must restamp"
    assert after["cases"]["t001"]["runs"][0]["text"] == "different"


def test_save_does_not_mutate_the_callers_dict():
    snapshot = dict(SNAPSHOT)
    with tempfile.TemporaryDirectory() as root:
        store.save(snapshot, os.path.join(root, "baseline.json"))
    assert "recorded_at" not in snapshot


def test_save_works_with_no_directory_component():
    previous = os.getcwd()
    with tempfile.TemporaryDirectory() as root:
        try:
            os.chdir(root)
            store.save(dict(SNAPSHOT), "baseline.json")
            assert os.path.exists("baseline.json")
        finally:
            os.chdir(previous)


def test_fingerprint_is_stable_and_sensitive():
    base = store.fingerprint("PROMPT", "mock", {"k": 5})
    assert base == store.fingerprint("PROMPT", "mock", {"k": 5}), "must be deterministic"
    assert base != store.fingerprint("PROMPT EDITED", "mock", {"k": 5})
    assert base != store.fingerprint("PROMPT", "anthropic", {"k": 5})
    assert base != store.fingerprint("PROMPT", "mock", {"k": 5, "model": "haiku"})


# -- providers ---------------------------------------------------------------

STRICT = "Respond with ONLY valid JSON. No prose, no markdown fence.\n<ticket>my card was charged twice</ticket>"


def test_mock_is_deterministic_per_prompt_run_and_model():
    a = providers.MockProvider().complete(STRICT, run=1)
    b = providers.MockProvider().complete(STRICT, run=1)
    assert a.text == b.text, "same inputs must replay identically"
    assert providers.MockProvider().complete(STRICT, run=2).text != ""


def test_changing_the_model_changes_the_sampling_stream():
    sonnet = providers.MockProvider({"model": "claude-sonnet-4-6"})
    haiku = providers.MockProvider({"model": "claude-haiku-4-5"})
    texts_s = [sonnet.complete(STRICT, run=i).text for i in range(12)]
    texts_h = [haiku.complete(STRICT, run=i).text for i in range(12)]
    assert texts_s != texts_h, "a different model is a different system under test"


def test_cheap_models_leak_format_more_often():
    """The cost-downgrade regression, as a measurable rate rather than a vibe."""
    def leak_rate(model: str) -> float:
        p = providers.MockProvider({"model": model})
        runs = [p.complete(STRICT, run=i).text for i in range(300)]
        return sum(1 for t in runs if t.strip().startswith("```")) / len(runs)

    assert leak_rate("claude-haiku-4-5") > leak_rate("claude-sonnet-4-6") * 2


def test_max_tokens_truncates_the_completion():
    uncapped = providers.MockProvider().complete(STRICT, run=0)
    capped = providers.MockProvider({"max_tokens": 8}).complete(STRICT, run=0)
    assert len(capped.text) < len(uncapped.text)
    assert len(capped.text) <= 8 * 4


def test_max_tokens_above_the_output_length_changes_nothing():
    plain = providers.MockProvider().complete(STRICT, run=0)
    roomy = providers.MockProvider({"max_tokens": 1000}).complete(STRICT, run=0)
    assert plain.text == roomy.text


def test_cheaper_models_cost_less_per_token():
    assert providers.price_per_1k("claude-haiku-4-5") < providers.price_per_1k("claude-sonnet-4-6")
    assert providers.price_per_1k("gpt-4o-mini") < providers.price_per_1k("claude-sonnet-4-6")
    assert providers.price_per_1k("claude-opus-4-1") > providers.price_per_1k("claude-sonnet-4-6")
    assert providers.price_per_1k("something-unknown") == providers.PRICE_PER_1K


def test_a_prompt_that_never_mentions_json_gets_prose_back():
    text = providers.MockProvider().complete("Explain the ticket.\n<ticket>it crashed</ticket>").text
    assert not text.strip().startswith("{")


def test_get_provider_defaults_to_the_mock():
    assert providers.get_provider("mock").name == "mock"
    assert providers.get_provider(None, {"model": "x"}).name == "mock"
