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
from dataclasses import replace

sys.path.insert(0, os.getcwd())

from promptlock import store  # noqa: E402
from promptlock.runner import Config, check, record, run_suite  # noqa: E402

APP = "examples/demo_app/app.py"
BACKUP = os.path.join(tempfile.gettempdir(), "promptlock_app_backup.py")

STRICT = "Respond with ONLY valid JSON. No prose, no markdown fence."

# CI gate: recall must be perfect and false positives may not exceed this.
MAX_FALSE_POSITIVES = 1

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


# Changes to the model, not the prompt. No file is patched -- only Config --
# because this is the regression that ships as a config edit nobody reads.
MODEL_SWAP = {
    "M1 sonnet->haiku": ({"model": "claude-haiku-4-5"}, True),
    "M2 temperature 0->0.2": ({"temperature": 0.2}, False),
    # 24, not 64: this suite's longest completion is 36 tokens, so a 64-token
    # cap truncates nothing and the variant would test nothing. 24 clips 42 of
    # the 50 cases mid-JSON, which is the regression this variant is for.
    "M3 max_tokens 1000->24": ({"max_tokens": 24}, True),
}


def patch(old: str, new: str) -> None:
    shutil.copy(BACKUP, APP)
    with open(APP, encoding="utf-8") as f:
        source = f.read()
    assert old in source, f"anchor not found: {old!r}"
    with open(APP, "w", encoding="utf-8") as f:
        f.write(source.replace(old, new, 1))


def tier_of(rep: dict, fired: bool) -> str:
    """Which signal caught it -- assertions are free, the judge is not."""
    if any(
        c["verdict"] == "FAIL"
        and c["broken_assertions"]
        and "systemic" not in c["broken_assertions"][0]
        for c in rep["cases"].values()
    ):
        return "assertions"
    return "judge" if fired else "—"


def naive_fires(cfg: Config, baseline: dict) -> bool:
    """Baseline detector: flag if any output text differs at all."""
    cur = run_suite(cfg)
    for cid, new in cur["cases"].items():
        old = baseline["cases"].get(cid)
        if old and [r["text"] for r in old["runs"]] != [r["text"] for r in new["runs"]]:
            return True
    return False


def main() -> int:
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
                rows.append((kind, name, pl, nv, rep["summary"], tier_of(rep, pl), kind == "REGRESSION"))

        # Model swaps vary Config, not the file -- so the file must be pristine
        # first, or the last harmless patch above contaminates every result.
        shutil.copy(BACKUP, APP)
        importlib.invalidate_caches()

        for name, (override, should_fire) in MODEL_SWAP.items():
            variant = replace(cfg, model_params={**cfg.model_params, **override})
            rep = check(variant, baseline)
            pl = rep["summary"]["FAIL"] > 0
            nv = naive_fires(variant, baseline)
            rows.append(("MODEL_SWAP", name, pl, nv, rep["summary"], tier_of(rep, pl), should_fire))
    finally:
        shutil.copy(BACKUP, APP)

    print(f"\n{'':<4}{'variant':<26}{'PromptLock':<12}{'naive diff':<12}{'verdicts':<14}caught by")
    print("-" * 96)
    for _kind, name, pl, nv, s, tier, want in rows:
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

    swaps = [r for r in rows if r[0] == "MODEL_SWAP"]
    if swaps:
        right = sum(1 for r in swaps if r[2] == r[6])
        print(f"{'model / params':<20} {right}/{len(swaps)} classified correctly")
    print("=" * 82)

    # The CI gate. Tuning a threshold until the benchmark passes measures
    # nothing, so this is the number a change has to survive.
    tp, nr, fp, nh, _, _ = stats(2)
    failures = []
    if tp < nr:
        failures.append(f"recall {tp}/{nr} below the required {nr}/{nr}")
    if fp > MAX_FALSE_POSITIVES:
        failures.append(f"false positives {fp}/{nh} above the allowed {MAX_FALSE_POSITIVES}/{nh}")

    # A model swap that stops firing is as much a regression as a missed prompt
    # edit, and M2 going loud is a false positive by another name. Both are
    # gated, and the failure names the variant so CI logs say what broke.
    missed = [r for r in swaps if r[2] != r[6]]
    if missed:
        failures.append(
            "model/param variants misclassified: "
            + ", ".join(f"{r[1]} (expected {'fire' if r[6] else 'quiet'})" for r in missed)
        )

    if failures:
        print("\nGATE FAILED: " + "; ".join(failures))
        return 1
    print(f"\nGate passed: recall {tp}/{nr}, false positives {fp}/{nh} "
          f"(limit {MAX_FALSE_POSITIVES}/{nh}), model/params "
          f"{len(swaps) - len(missed)}/{len(swaps)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
