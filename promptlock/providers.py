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

# Order matters: first substring match wins. Rough public list pricing -- enough
# to make a downgrade's economics visible next to its quality cost, which is the
# trade teams currently make in a spreadsheet with no quality number in it.
PRICE_BY_MODEL = {"haiku": 0.0008, "mini": 0.0006, "opus": 0.015}


def price_per_1k(model: str) -> float:
    low = model.lower()
    return next((p for marker, p in PRICE_BY_MODEL.items() if marker in low), PRICE_PER_1K)


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

# Cost-downgrade regression: the cheap tier holds format less reliably and
# commits to a label on thinner evidence.
CHEAP_MARKERS = ("haiku", "mini")
LEAK_STRICT = 0.04
LEAK_CHEAP = 0.25
DEFAULT_MODEL = "claude-sonnet-4-6"


class MockProvider:
    """Deterministic-per-(prompt, input, run, model) simulator with realistic failure modes."""

    name = "mock"

    def __init__(self, params: dict | None = None):
        self.params = dict(params or {})
        self.model = str(self.params.get("model") or DEFAULT_MODEL)
        self.temperature = float(self.params.get("temperature") or 0.0)
        self.max_tokens = self.params.get("max_tokens")
        self.cheap = any(m in self.model.lower() for m in CHEAP_MARKERS)

    def complete(self, prompt: str, run: int = 0, **_) -> Completion:
        # Model identity is part of the sampling stream: a different model is a
        # different system. Temperature perturbs variance instead of reseeding,
        # which is why a small temperature nudge stays inside the noise floor.
        rng = _seed(prompt, str(run), self.model)
        low = prompt.lower()

        ticket = self._extract_ticket(prompt)
        label = self._classify(ticket, rng, low, self.cheap)
        urgency = self._urgency(ticket, low, rng)

        payload = {"category": label, "urgency": urgency, "summary": self._summarise(ticket)}

        # Does the prompt pin the output format down hard enough?
        strict = any(m in low for m in STRICT_MARKERS)
        asks_json = "json" in low
        body = json.dumps(payload)

        leak = (LEAK_CHEAP if self.cheap else LEAK_STRICT) + 0.05 * self.temperature

        if not asks_json:
            # No JSON requested at all -> the model answers in prose.
            text = f"This ticket looks like a {label} issue with {urgency} urgency."
        elif strict:
            # Still leaks a fence occasionally -- real models do, cheap ones more.
            text = f"```json\n{body}\n```" if rng.random() < leak else body
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

        # max_tokens caps the completion, as it does on a real API. Cut mid-JSON,
        # the output stops parsing -- which is the whole point of the assertion.
        if self.max_tokens and _tokens(text) > int(self.max_tokens):
            text = text[: int(self.max_tokens) * 4]

        tok = _tokens(prompt) + _tokens(text)
        return Completion(
            text=text,
            latency_ms=round(180 + tok * 1.4 + rng.random() * 120, 1),
            cost_usd=round(tok / 1000 * price_per_1k(self.model), 8),
            tokens=tok,
        )

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _extract_ticket(prompt: str) -> str:
        m = re.search(r"<ticket>(.*?)</ticket>", prompt, re.S)
        return (m.group(1) if m else prompt).strip().lower()

    @staticmethod
    def _classify(ticket: str, rng: random.Random, prompt_low: str = "", cheap: bool = False) -> str:
        scores = {k: sum(1 for w in ws if w in ticket) for k, ws in KEYWORDS.items()}
        best = max(scores, key=scores.get)
        # A hedging instruction makes the model retreat to the catch-all bucket.
        floor = 2 if ("when unsure" in prompt_low or "default to other" in prompt_low) else 1
        if cheap:
            # The cheap tier commits to a label on evidence the better one rejects.
            floor -= 1
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

    def __init__(self, params: dict | None = None):
        import anthropic  # noqa: F401  (imported lazily on purpose)
        self.params = dict(params or {})
        self.model = str(self.params.get("model") or DEFAULT_MODEL)

    def complete(self, prompt: str, run: int = 0, **_) -> Completion:
        import time

        import anthropic

        client = anthropic.Anthropic()
        t0 = time.time()
        sampling = {
            k: self.params[k]
            for k in ("temperature", "top_p")
            if self.params.get(k) is not None
        }
        r = client.messages.create(
            model=self.model,
            max_tokens=int(self.params.get("max_tokens") or 1000),
            messages=[{"role": "user", "content": prompt}],
            **sampling,
        )
        text = "".join(b.text for b in r.content if b.type == "text")
        tok = r.usage.input_tokens + r.usage.output_tokens
        return Completion(
            text=text,
            latency_ms=round((time.time() - t0) * 1000, 1),
            cost_usd=round(tok / 1000 * price_per_1k(self.model), 8),
            tokens=tok,
        )


def get_provider(name: str | None = None, params: dict | None = None):
    name = name or os.environ.get("PROMPTLOCK_PROVIDER", "mock")
    if name == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicProvider(params)
    return MockProvider(params)
