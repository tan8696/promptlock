"""Measure what actually matters: does the detector fire on real regressions
and stay quiet on harmless edits?

Compares PromptLock against the naive detector every team reaches for first --
"did any output string change?".

    python3 scripts/benchmark.py
"""

from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.getcwd())

from promptlock import store  # noqa: E402
from promptlock.runner import Config, check, record, run_suite  # noqa: E402

APP = "examples/demo_app/app.py"
BACKUP = os.path.join(tempfile.gettempdir(), "promptlock_app_backup.py")

STRICT = "Respond with ONLY valid JSON. No prose, no markdown fence."

# Prompt edits that genuinely degrade the output.
REGRESSIONS = {
    "R1 drop-format-anchor": (STRICT, "Respond in JSON."),
    "R2 remove-json-entirely": (STRICT, "Explain your classification."),
    "R3 brevity-nudge": (STRICT, "Respond in JSON. Keep it brief."),
    "R4 hedging-instruction": (STRICT, STRICT + "\nWhen unsure, classify as other."),
    "R5 terse-rewrite": (STRICT, "Respond in JSON, terse."),
    # Breaks no assertion and clears no per-case threshold. Only the
    # suite-level drift gate plus the judge can see it.
    "R6 urgency-inflation": (
        "a one-line summary.",
        "a one-line summary.\nErr on the side of high urgency.",
    ),
}

# Edits a reviewer would wave through. None should fire.
HARMLESS = {
    "H01 whitespace": ("You are a support triage assistant.", "You are a support triage assistant. "),
    "H02 role-synonym": ("support triage assistant", "support triage agent"),
    "H03 verb-synonym": ("Classify the ticket below.", "Categorise the ticket below."),
    "H04 article": ("Classify the ticket below.", "Classify the following ticket."),
    "H05 blank-line": ("<ticket>", "\n<ticket>"),
    "H06 punctuation": ("Classify the ticket below.", "Classify the ticket below:"),
    "H07 politeness": ("Classify the ticket below.", "Please classify the ticket below."),
    "H08 enum-spacing": ("billing, bug, feature_request, account, other", "billing,bug,feature_request,account,other"),
    "H09 casing": ("Return category", "Return the category"),
    "H10 reorder-tail": (STRICT, STRICT.replace("No prose, no markdown fence.", "No markdown fence, no prose.")),
}


def patch(old: str, new: str) -> None:
    shutil.copy(BACKUP, APP)
    s = open(APP).read()
    assert old in s, f"anchor not found: {old!r}"
    open(APP, "w").write(s.replace(old, new, 1))


def naive_fires(cfg: Config, baseline: dict) -> bool:
    """Baseline detector: flag if any output text differs at all."""
    cur = run_suite(cfg)
    for cid, new in cur["cases"].items():
        old = baseline["cases"].get(cid)
        if old and [r["text"] for r in old["runs"]] != [r["text"] for r in new["runs"]]:
            return True
    return False


def main() -> None:
    # Windows consoles default to cp1252, which cannot encode the table glyphs.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    shutil.copy(APP, BACKUP)
    cfg = Config.load("promptlock.yaml")

    shutil.copy(BACKUP, APP)
    importlib.invalidate_caches()
    store.save(record(cfg))
    baseline = store.load()

    rows = []
    try:
        for kind, variants in (("REGRESSION", REGRESSIONS), ("HARMLESS", HARMLESS)):
            for name, (old, new) in variants.items():
                patch(old, new)
                importlib.invalidate_caches()
                rep = check(cfg, baseline)
                pl = rep["summary"]["FAIL"] > 0
                shutil.copy(BACKUP, APP)
                importlib.invalidate_caches()
                patch(old, new)
                nv = naive_fires(cfg, baseline)
                tier = (
                    "assertions"
                    if any(
                        c["verdict"] == "FAIL" and c["broken_assertions"]
                        and "systemic" not in c["broken_assertions"][0]
                        for c in rep["cases"].values()
                    )
                    else "judge" if pl else "—"
                )
                rows.append((kind, name, pl, nv, rep["summary"], tier))
    finally:
        shutil.copy(BACKUP, APP)

    print(f"\n{'':<4}{'variant':<26}{'PromptLock':<12}{'naive diff':<12}{'verdicts':<14}caught by")
    print("-" * 96)
    for kind, name, pl, nv, s, tier in rows:
        want = kind == "REGRESSION"
        mark = lambda fired: ("FIRE" if fired else "quiet")  # noqa: E731
        ok = "✓" if pl == want else "✗"
        print(
            f"{ok:<4}{name:<26}{mark(pl):<12}{mark(nv):<12}"
            f"{s['PASS']}P/{s['DRIFT']}D/{s['FAIL']}F".ljust(52 + 14)[:66]
            + f"  {tier}"
        )

    regs = [r for r in rows if r[0] == "REGRESSION"]
    harms = [r for r in rows if r[0] == "HARMLESS"]

    def stats(fired_idx: int):
        tp = sum(1 for r in regs if r[fired_idx])
        fp = sum(1 for r in harms if r[fired_idx])
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        return tp, len(regs), fp, len(harms), tp / len(regs), prec

    print("\n" + "=" * 82)
    for label, idx in (("PromptLock", 2), ("naive string diff", 3)):
        tp, nr, fp, nh, rec, prec = stats(idx)
        print(
            f"{label:<20} recall {tp}/{nr} ({rec:.0%})   "
            f"false positives {fp}/{nh} ({fp / nh:.0%})   precision {prec:.0%}"
        )
    print("=" * 82)


if __name__ == "__main__":
    main()
