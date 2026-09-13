"""Where suite_drift_threshold comes from.

Measures the drift distribution under edits known to be harmless (H) and edits
known to change behaviour (S). The threshold is set in the gap between the two
medians, not guessed.

    python3 scripts/calibrate.py
"""

from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.getcwd())

from promptlock import store  # noqa: E402
from promptlock.runner import Config, check, record  # noqa: E402

APP = "examples/demo_app/app.py"
BACKUP = os.path.join(tempfile.gettempdir(), "promptlock_calibrate_backup.py")

STRICT = "Respond with ONLY valid JSON. No prose, no markdown fence."

VARIANTS = {
    "H whitespace": ("You are a support triage assistant.", "You are a support triage assistant. "),
    "H synonym": ("support triage assistant", "support triage agent"),
    "H verb": ("Classify the ticket below.", "Categorise the ticket below."),
    "H article": ("Classify the ticket below.", "Classify the following ticket."),
    "H politeness": ("Classify the ticket below.", "Please classify the ticket below."),
    "H reorder": (
        STRICT,
        STRICT.replace("No prose, no markdown fence.", "No markdown fence, no prose."),
    ),
    "S urgency-bias": (
        "a one-line summary.",
        "a one-line summary.\nErr on the side of high urgency.",
    ),
    "S hedge": (STRICT, STRICT + "\nWhen unsure, classify as other."),
}


def patch(old: str, new: str, label: str) -> None:
    shutil.copy(BACKUP, APP)
    with open(APP, encoding="utf-8") as f:
        source = f.read()
    assert old in source, f"anchor not found for {label}: {old!r}"
    with open(APP, "w", encoding="utf-8") as f:
        f.write(source.replace(old, new, 1))


def percentile(sorted_desc: list[float], fraction: float) -> float:
    """Index into a descending list by fraction from the top."""
    idx = min(len(sorted_desc) - 1, int(len(sorted_desc) * fraction))
    return sorted_desc[idx]


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    shutil.copy(APP, BACKUP)
    cfg = Config.load("promptlock.yaml")
    store.save(record(cfg))
    baseline = store.load()

    medians = {"H": [], "S": []}
    try:
        for label, (old, new) in VARIANTS.items():
            patch(old, new, label)
            importlib.invalidate_caches()
            report = check(cfg, baseline)
            drifts = sorted((c["drift"] for c in report["cases"].values()), reverse=True)
            median = percentile(drifts, 0.5)
            medians[label[0]].append(median)
            print(
                f"{label:<18} max={drifts[0]:.4f}  p90={percentile(drifts, 0.1):.4f}  "
                f"median={median:.4f}"
            )
    finally:
        shutil.copy(BACKUP, APP)

    if medians["H"] and medians["S"]:
        harmless_top, behavioural_low = max(medians["H"]), min(medians["S"])
        print(f"\nharmless medians  <= {harmless_top:.4f}")
        print(f"behavioural medians >= {behavioural_low:.4f}")
        if behavioural_low > harmless_top:
            print(f"gap: {harmless_top:.4f} .. {behavioural_low:.4f} "
                  f"-> suite_drift_threshold {(harmless_top + behavioural_low) / 2:.4f}")
        else:
            print("no separation on this suite: the two distributions overlap.")


if __name__ == "__main__":
    main()
