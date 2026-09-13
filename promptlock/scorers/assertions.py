"""Signal 1: deterministic assertions.

Cheap, unfakeable, and the only scorer that can produce a FAIL on its own.
A violation only counts as a regression if the *baseline* satisfied it --
we detect degradation, not pre-existing badness.
"""

from __future__ import annotations

import json
import re
from typing import Any


def _extract_json(text: str) -> Any:
    """Parse JSON, tolerating a markdown fence or a short prose preamble."""
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    candidate = fence.group(1) if fence else text
    try:
        return json.loads(candidate.strip())
    except Exception:
        brace = re.search(r"\{.*\}", candidate, re.S)
        if brace:
            try:
                return json.loads(brace.group(0))
            except Exception:
                return None
    return None


def evaluate(output: dict, cfg: dict) -> dict[str, bool]:
    """Return {assertion_name: passed}."""
    text = output["text"]
    res: dict[str, bool] = {}

    if cfg.get("require_json"):
        parsed = _extract_json(text)
        res["json_parses"] = parsed is not None

        # Stricter than json_parses: no fence, no preamble, just the object.
        res["json_bare"] = text.strip().startswith("{") and text.strip().endswith("}")

        for key in cfg.get("required_keys", []):
            res[f"key:{key}"] = isinstance(parsed, dict) and key in parsed

        enums: dict[str, list] = cfg.get("enums", {})
        for key, allowed in enums.items():
            res[f"enum:{key}"] = isinstance(parsed, dict) and parsed.get(key) in allowed

    for pat in cfg.get("must_match", []):
        res[f"match:{pat}"] = bool(re.search(pat, text, re.I))
    for pat in cfg.get("must_not_match", []):
        res[f"nomatch:{pat}"] = not re.search(pat, text, re.I)

    if "max_latency_ms" in cfg:
        res["latency"] = output["latency_ms"] <= cfg["max_latency_ms"]
    if "max_cost_usd" in cfg:
        res["cost"] = output["cost_usd"] <= cfg["max_cost_usd"]

    return res


def rate(runs: list[dict], cfg: dict) -> dict[str, float]:
    """Pass-rate per assertion across k runs of one case."""
    if not runs:
        return {}
    tallies: dict[str, list[bool]] = {}
    for r in runs:
        for name, ok in evaluate(r, cfg).items():
            tallies.setdefault(name, []).append(ok)
    return {name: sum(v) / len(v) for name, v in tallies.items()}
