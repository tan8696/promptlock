"""Baseline snapshots live in the repo as JSON.

No database, no SaaS. The baseline is reviewable in a PR diff, which means a
human can see exactly what "known good" meant at the time it was recorded.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

BASELINE_PATH = ".promptlock/baseline.json"


def fingerprint(template: str, provider: str, params: dict) -> str:
    blob = json.dumps({"t": template, "p": provider, "k": params}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def _body(data: dict) -> str:
    """The file's content minus the timestamp -- what a diff would actually show."""
    return json.dumps(
        {k: v for k, v in data.items() if k != "recorded_at"}, indent=2, sort_keys=True
    )


def save(data: dict, path: str = BASELINE_PATH) -> None:
    """Write the snapshot, keeping `recorded_at` when nothing else changed.

    Re-recording identical behaviour must produce no diff. Otherwise every run
    churns the file, and "what changed in this PR?" -- the thing a committed
    baseline exists to answer -- gets buried under a timestamp. So the stamp
    means "when known-good last changed", not "when someone last ran record".
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    body = _body(data)

    stamp = datetime.now(timezone.utc).isoformat()
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                previous = json.load(f)
            if _body(previous) == body:
                stamp = previous.get("recorded_at", stamp)
        except (json.JSONDecodeError, OSError):
            pass  # unreadable or corrupt: just write a fresh one

    with open(path, "w", encoding="utf-8") as f:
        json.dump({**json.loads(body), "recorded_at": stamp}, f, indent=2, sort_keys=True)
        f.write("\n")


def load(path: str = BASELINE_PATH) -> dict:
    if not os.path.exists(path):
        raise SystemExit(
            f"No baseline at {path}. Run `promptlock record` on a known-good commit first."
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)
