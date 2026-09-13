"""Signal 2: pairwise LLM judge with position-swap debiasing.

Judges are biased toward whichever answer they see first, so every comparison
is run twice with the positions swapped. A verdict only counts if both
orderings agree; disagreement is reported as TIE, never as a regression.

Only invoked on cases that already drifted -- keeps judge spend proportional
to the size of the change, not the size of the suite.
"""

from __future__ import annotations

import json
import re

from .assertions import _extract_json

RUBRIC = """You are grading two candidate outputs from a support-ticket classifier.

Task given to the model:
{task}

Output A:
{a}

Output B:
{b}

Which output better satisfies the task? Judge on: correct category, correct
urgency, and whether the output is machine-parseable in the requested format.
Ignore length and tone unless the task asked for them.

Respond with ONLY valid JSON: {{"winner": "A" | "B" | "tie", "why": "<12 words"}}
"""


def _ask(provider, task: str, a: str, b: str) -> str:
    raw = provider.complete(RUBRIC.format(task=task, a=a, b=b)).text
    parsed = _extract_json(raw)
    if isinstance(parsed, dict) and parsed.get("winner") in {"A", "B", "tie"}:
        return parsed["winner"]
    m = re.search(r"\b(A|B|tie)\b", raw)
    return m.group(1) if m else "tie"


def compare(provider, task: str, baseline: str, candidate: str) -> str:
    """Return 'better' | 'worse' | 'tie' for candidate vs baseline."""
    first = _ask(provider, task, baseline, candidate)   # baseline = A
    second = _ask(provider, task, candidate, baseline)  # candidate = A

    # Translate both into a verdict about the candidate.
    v1 = {"A": "worse", "B": "better", "tie": "tie"}[first]
    v2 = {"A": "better", "B": "worse", "tie": "tie"}[second]
    return v1 if v1 == v2 else "tie"


class MockJudge:
    """Offline stand-in: grades on parseability + agreement with the case hint."""

    def __init__(self, provider=None):
        self.provider = provider

    def compare(self, task: str, baseline: str, candidate: str, hint: dict | None = None) -> str:
        sb, sc = self._score(baseline, hint), self._score(candidate, hint)
        if sc > sb:
            return "better"
        if sc < sb:
            return "worse"
        return "tie"

    @staticmethod
    def _score(text: str, hint: dict | None) -> int:
        parsed = _extract_json(text)
        s = 0
        if parsed is not None:
            s += 2
        if text.strip().startswith("{"):
            s += 1
        if isinstance(parsed, dict):
            s += sum(1 for k in ("category", "urgency", "summary") if k in parsed)
            if hint:
                if parsed.get("category") == hint.get("category"):
                    s += 3
                # Urgency inflation is a real regression: it makes triage useless.
                if "urgency" in hint and parsed.get("urgency") == hint["urgency"]:
                    s += 3
        return s


def get_judge(provider, enabled: bool = True):
    if not enabled:
        return None
    if getattr(provider, "name", "mock") == "mock":
        return MockJudge(provider)

    class RealJudge:
        def compare(self, task, baseline, candidate, hint=None):
            return compare(provider, task, baseline, candidate)

    return RealJudge()
