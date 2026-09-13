"""Markdown report. FAILs are expanded, DRIFTs collapsed, PASSes counted only."""

from __future__ import annotations

ICON = {"PASS": "✅", "DRIFT": "🟡", "FAIL": "❌"}


def _trim(s: str, n: int = 160) -> str:
    s = s.replace("\n", " ").replace("|", "\\|").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _param_changes(report: dict) -> list[tuple[str, str, str]]:
    """(name, before, after) for every model parameter that moved."""
    params = report.get("params", {})
    old, new = params.get("baseline") or {}, params.get("current") or {}
    return [
        (key, str(old.get(key, "—")), str(new.get(key, "—")))
        for key in sorted(set(old) | set(new))
        if old.get(key) != new.get(key)
    ]


def _cost_delta(report: dict) -> str | None:
    cost = report.get("cost") or {}
    before, after = cost.get("baseline_per_run"), cost.get("current_per_run")
    if not before or after is None:
        return None
    pct = (after - before) / before * 100
    if abs(pct) < 0.5:
        return None
    return f"${before:.6f} → ${after:.6f} per run ({pct:+.0f}%)"


def _what_changed(report: dict) -> list[str]:
    """Name the change, not just the fact of one. A fingerprint hash helps nobody."""
    if not report.get("fingerprint_changed"):
        return []

    rows = _param_changes(report)
    cost = _cost_delta(report)
    if not rows and not cost:
        return ["> ⚠️ **The prompt fingerprint changed** — the template itself was edited.", ""]

    out = ["> ⚠️ **What changed**", ">"]
    for name, before, after in rows:
        out.append(f"> - `{name}`: `{before}` → `{after}`")
    if cost:
        out.append(f"> - cost: {cost}")
    if not rows:
        out.append("> - the prompt template was edited")
    return out + [""]


def markdown(report: dict) -> str:
    s = report["summary"]
    total = sum(s.values())
    out = ["## PromptLock", ""]

    if s["FAIL"]:
        out.append(f"**❌ {s['FAIL']} of {total} cases regressed.**")
    elif s["DRIFT"]:
        out.append(f"**🟡 Output changed on {s['DRIFT']} of {total} cases, but no case got worse.**")
    else:
        out.append(f"**✅ All {total} cases hold.**")

    out += [
        "",
        f"`{s['PASS']} pass · {s['DRIFT']} drift · {s['FAIL']} fail` — "
        f"{report['judge_calls']} judge calls"
        + ("  ·  ⚠️ prompt fingerprint changed" if report["fingerprint_changed"] else ""),
        "",
    ]

    out += _what_changed(report)

    sd = report.get("suite_drift", {})
    if sd.get("systemic"):
        out += [
            f"> ⚠️ **Systemic drift.** Median case moved `{sd['median']}` "
            f"(suite threshold `{sd['threshold']}`). The whole output distribution "
            "shifted, not a handful of cases — that is what an instruction change "
            "looks like. Top drifted cases were sent to the judge.",
            "",
        ]

    fails = {k: v for k, v in report["cases"].items() if v["verdict"] == "FAIL"}
    if fails:
        out += ["### Regressions", "", "| Case | Cause | Baseline | Now |", "|---|---|---|---|"]
        for cid, c in fails.items():
            cause = ", ".join(f"`{b}`" for b in c["broken_assertions"]) or "judge: worse"
            out.append(f"| `{cid}` | {cause} | {_trim(c['baseline_sample'], 70)} | {_trim(c['current_sample'], 70)} |")
        out.append("")

    drifts = {k: v for k, v in report["cases"].items() if v["verdict"] == "DRIFT"}
    if drifts:
        out += [
            "<details><summary>"
            f"🟡 {len(drifts)} cases changed without getting worse</summary>",
            "",
            "| Case | Drift | Threshold | Noise floor | Judge |",
            "|---|---|---|---|---|",
        ]
        for cid, c in drifts.items():
            out.append(
                f"| `{cid}` | {c['drift']} | {c['threshold']} | {c['noise_floor']} | {c['judge'] or '—'} |"
            )
        out += ["", "</details>", ""]

    return "\n".join(out)


def console(report: dict) -> str:
    lines = []
    for cid, c in sorted(report["cases"].items(), key=lambda x: x[1]["verdict"], reverse=True):
        detail = ", ".join(c["broken_assertions"]) or (f"judge={c['judge']}" if c["judge"] else "")
        lines.append(f"  {ICON[c['verdict']]} {cid:<14} drift={c['drift']:<7} {detail}")
    s = report["summary"]
    sd = report.get("suite_drift", {})
    if sd.get("systemic"):
        lines.append(f"\n  ⚠️ systemic drift: median {sd['median']} > {sd['threshold']}")
    lines.append(f"\n  {s['PASS']} pass · {s['DRIFT']} drift · {s['FAIL']} fail")
    return "\n".join(lines)
