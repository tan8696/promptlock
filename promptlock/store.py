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


def save(data: dict, path: str = BASELINE_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data["recorded_at"] = datetime.now(timezone.utc).isoformat()
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def load(path: str = BASELINE_PATH) -> dict:
    if not os.path.exists(path):
        raise SystemExit(
            f"No baseline at {path}. Run `promptlock record` on a known-good commit first."
        )
    with open(path) as f:
        return json.load(f)
