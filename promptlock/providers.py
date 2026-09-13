"""LLM providers.

The mock provider is a *behavioural simulator*, not a canned-response table.
It reads the rendered prompt and changes its output the way a real model would:
strict formatting instructions produce bare JSON, loose ones leak prose, and
every call carries seeded run-to-run noise so flakiness is real and reproducible.
That is what makes the offline demo meaningful.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
from dataclasses import dataclass

# Rough price per 1K tokens, used for the cost assertion.
PRICE_PER_1K = 0.003


@dataclass
class Completion:
    text: str
    latency_ms: float
    cost_usd: float
    tokens: int


def _seed(*parts: str) -> random.Random:
    h = hashlib.sha256("||".join(parts).encode()).hexdigest()
    return random.Random(int(h[:16], 16))


def _tokens(s: str) -> int:
    return max(1, len(s) // 4)


# --------------------------------------------------------------------------
# Mock
# --------------------------------------------------------------------------

LABELS = ["billing", "bug", "feature_request", "account", "other"]

KEYWORDS = {
    "billing": ["invoice", "charge", "charged", "refund", "payment", "card", "price", "subscription", "billed"],
    "bug": ["crash", "error", "broken", "not working", "fails", "bug", "500", "exception", "freeze"],
    "feature_request": ["would be nice", "please add", "feature", "support for", "wish", "can you add", "suggestion"],
    "account": ["login", "password", "sign in", "locked out", "2fa", "email address", "delete my account"],
}

# Signals that a prompt is strict about output format.
STRICT_MARKERS = [
    "only valid json", "json only", "no prose", "no explanation",
    "respond with only", "output only", "do not include any text",
]


class MockProvider:
    """Deterministic-per-(prompt, input, run) simulator with realistic failure modes."""

    name = "mock"

    def complete(self, prompt: str, run: int = 0, **_) -> Completion:
        rng = _seed(prompt, str(run))
        low = prompt.lower()

        ticket = self._extract_ticket(prompt)
        label = self._classify(ticket, rng, low)
        urgency = self._urgency(ticket, low, rng)

        payload = {"category": label, "urgency": urgency, "summary": self._summarise(ticket)}

        # Does the prompt pin the output format down hard enough?
        strict = any(m in low for m in STRICT_MARKERS)
        asks_json = "json" in low
        body = json.dumps(payload)

        if not asks_json:
            # No JSON requested at all -> the model answers in prose.
            text = f"This ticket looks like a {label} issue with {urgency} urgency."
        elif strict:
            # Still leaks a fence occasionally -- real models do.
            text = f"```json\n{body}\n```" if rng.random() < 0.04 else body
        else:
            r = rng.random()
            if r < 0.45:
                text = f"Here's the classification:\n\n```json\n{body}\n```"
            elif r < 0.60:
                text = f"Sure! {body}"
            else:
                text = body

        # A "brief/concise" style nudge without a format anchor makes the model
        # drop optional fields -- a subtle, very real regression.
        if ("brief" in low or "terse" in low) and not strict:
            payload.pop("summary", None)
            text = re.sub(r"\{.*\}", json.dumps(payload), text, flags=re.S)

        tok = _tokens(prompt) + _tokens(text)
        return Completion(
            text=text,
            latency_ms=round(180 + tok * 1.4 + rng.random() * 120, 1),
            cost_usd=round(tok / 1000 * PRICE_PER_1K, 6),
            tokens=tok,
        )

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _extract_ticket(prompt: str) -> str:
        m = re.search(r"<ticket>(.*?)</ticket>", prompt, re.S)
        return (m.group(1) if m else prompt).strip().lower()

    @staticmethod
    def _classify(ticket: str, rng: random.Random, prompt_low: str = "") -> str:
        scores = {k: sum(1 for w in ws if w in ticket) for k, ws in KEYWORDS.items()}
        best = max(scores, key=scores.get)
        # A hedging instruction makes the model retreat to the catch-all bucket.
        floor = 2 if ("when unsure" in prompt_low or "default to other" in prompt_low) else 1
        if scores[best] < floor:
            return "other"
        # Ambiguous tickets (two categories tied) are genuinely flaky.
        tied = [k for k, v in scores.items() if v == scores[best]]
        if len(tied) > 1:
            return rng.choice(sorted(tied))
        return best

    @staticmethod
    def _urgency(ticket: str, prompt_low: str, rng: random.Random) -> str:
        hot = any(w in ticket for w in ["asap", "urgent", "immediately", "down", "can't", "cannot", "blocked"])
        if "err on the side of high urgency" in prompt_low:
            return "high"
        if hot:
            return "high" if rng.random() > 0.1 else "medium"
        return rng.choice(["low", "medium"]) if rng.random() < 0.25 else "low"

    @staticmethod
    def _summarise(ticket: str) -> str:
        words = ticket.replace("\n", " ").split()
        return " ".join(words[:12])


# --------------------------------------------------------------------------
# Real providers (used automatically when a key is present)
# --------------------------------------------------------------------------

class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str = "claude-sonnet-4-6"):
        import anthropic  # noqa: F401  (imported lazily on purpose)
        self.model = model

    def complete(self, prompt: str, run: int = 0, **_) -> Completion:
        import time

        import anthropic

        client = anthropic.Anthropic()
        t0 = time.time()
        r = client.messages.create(
            model=self.model,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in r.content if b.type == "text")
        tok = r.usage.input_tokens + r.usage.output_tokens
        return Completion(
            text=text,
            latency_ms=round((time.time() - t0) * 1000, 1),
            cost_usd=round(tok / 1000 * PRICE_PER_1K, 6),
            tokens=tok,
        )


def get_provider(name: str | None = None):
    name = name or os.environ.get("PROMPTLOCK_PROVIDER", "mock")
    if name == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicProvider()
    return MockProvider()
