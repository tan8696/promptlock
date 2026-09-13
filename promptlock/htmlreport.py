"""Self-contained HTML report: one file, no CDN, no fonts, no libraries.

Progressive enhancement is the design constraint, not a nicety. Expansion uses
native <details>, and the character diff is computed here in Python -- so with
JavaScript disabled the page is still the whole report. JS only adds filtering.

Named htmlreport rather than html so it cannot be confused with the stdlib
module it imports.
"""

from __future__ import annotations

import html
from difflib import SequenceMatcher

VERDICT_COLOUR = {"PASS": "#1a7f5a", "DRIFT": "#b7791f", "FAIL": "#c02b2b"}
VERDICT_ICON = {"PASS": "&#9679;", "DRIFT": "&#9679;", "FAIL": "&#9679;"}

CSS = """
:root {
  --ink: #14161a; --muted: #5c6570; --line: #e2e6ea; --bg: #ffffff;
  --panel: #f7f8fa; --pass: #1a7f5a; --drift: #b7791f; --fail: #c02b2b;
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 32px 24px 64px; background: var(--bg); color: var(--ink);
  font: 14px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto,
        Helvetica, Arial, sans-serif;
}
.wrap { max-width: 980px; margin: 0 auto; }
h1 { font-size: 20px; margin: 0 0 4px; letter-spacing: -0.01em; }
.sub { color: var(--muted); margin: 0 0 24px; }
.cards { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; }
.card {
  flex: 1 1 150px; background: var(--panel); border: 1px solid var(--line);
  border-radius: 8px; padding: 12px 14px;
}
.card .k { color: var(--muted); font-size: 12px; text-transform: uppercase;
           letter-spacing: 0.04em; }
.card .v { font-size: 20px; font-weight: 600; margin-top: 2px;
           font-variant-numeric: tabular-nums; }
.changed {
  border: 1px solid #f0d9a8; background: #fdf8ec; border-radius: 8px;
  padding: 12px 14px; margin-bottom: 20px;
}
.changed h2 { font-size: 13px; margin: 0 0 6px; text-transform: uppercase;
              letter-spacing: 0.04em; color: #8a6d1f; }
.changed ul { margin: 0; padding-left: 18px; }
.changed code { background: #f4ead3; padding: 1px 4px; border-radius: 3px; }
figure { margin: 0 0 24px; border: 1px solid var(--line); border-radius: 8px;
         padding: 12px; overflow-x: auto; }
figcaption { color: var(--muted); font-size: 12px; margin-top: 6px; }
.filters { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; }
.filters button {
  font: inherit; padding: 5px 11px; border: 1px solid var(--line);
  background: #fff; border-radius: 999px; cursor: pointer; color: var(--ink);
}
.filters button[aria-pressed="true"] { background: var(--ink); color: #fff;
                                        border-color: var(--ink); }
.row { border: 1px solid var(--line); border-top: none; }
.row:first-of-type { border-top: 1px solid var(--line);
                     border-radius: 8px 8px 0 0; }
.row:last-of-type { border-radius: 0 0 8px 8px; }
.row > summary {
  display: grid; grid-template-columns: 18px 88px 1fr 104px 104px;
  gap: 10px; align-items: center; padding: 9px 12px; cursor: pointer;
  list-style: none;
}
.row > summary::-webkit-details-marker { display: none; }
.row:nth-of-type(odd) > summary { background: #fcfcfd; }
.row > summary:hover { background: #f2f4f7; }
.cid { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.num { text-align: right; font-variant-numeric: tabular-nums;
       color: var(--muted); }
.cause { color: var(--muted); overflow: hidden; text-overflow: ellipsis;
         white-space: nowrap; }
.PASS { color: var(--pass); } .DRIFT { color: var(--drift); }
.FAIL { color: var(--fail); }
.detail { padding: 4px 12px 16px; background: #fcfcfd;
          border-top: 1px dashed var(--line); }
.sbs { display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
       margin-top: 10px; }
.sbs h3 { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em;
          color: var(--muted); margin: 0 0 5px; }
pre {
  margin: 0; padding: 10px; background: #fff; border: 1px solid var(--line);
  border-radius: 6px; white-space: pre-wrap; word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px; line-height: 1.5;
}
mark { border-radius: 2px; padding: 0 1px; }
mark.del { background: #ffd9d9; color: #7a1b1b; }
mark.ins { background: #cdf1dd; color: #10543b; }
.meta { display: flex; gap: 16px; flex-wrap: wrap; color: var(--muted);
        font-size: 12px; margin-top: 10px; }
.legend { display: flex; gap: 14px; color: var(--muted); font-size: 12px; }
@media (max-width: 720px) {
  .row > summary { grid-template-columns: 16px 1fr 76px; }
  .cause, .row > summary .num.thr { display: none; }
  .sbs { grid-template-columns: 1fr; }
}
"""

# Filtering is the only thing JS owns. Everything else works without it.
JS = """
(function () {
  var buttons = document.querySelectorAll('.filters button');
  var rows = document.querySelectorAll('.row');
  function apply(want) {
    rows.forEach(function (r) {
      var show = want === 'ALL' || r.dataset.verdict === want;
      r.hidden = !show;
      if (!show) { r.open = false; }
    });
    buttons.forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.filter === want));
    });
  }
  buttons.forEach(function (b) {
    b.addEventListener('click', function () { apply(b.dataset.filter); });
  });
  document.querySelector('.filters').hidden = false;
})();
"""


def _esc(s) -> str:
    return html.escape(str(s), quote=True)


def _diff_spans(before: str, after: str) -> tuple[str, str]:
    """Character-level diff as escaped HTML, changes wrapped in <mark>.

    Computed here rather than in the browser so the diff survives JS being off.
    """
    matcher = SequenceMatcher(None, before, after, autojunk=False)
    left, right = [], []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        old, new = _esc(before[i1:i2]), _esc(after[j1:j2])
        if tag == "equal":
            left.append(old)
            right.append(new)
            continue
        if old:
            left.append(f'<mark class="del">{old}</mark>')
        if new:
            right.append(f'<mark class="ins">{new}</mark>')
    return "".join(left), "".join(right)


def _scatter(cases: dict) -> str:
    """Drift per case with each case's own threshold drawn as a tick.

    The ticks usually line up, because most cases are stable enough that
    max(drift_floor, noise x multiplier) is just the floor. The ones that sit
    higher are the naturally noisy cases, and seeing which those are is the
    point -- a flat row of ticks with two outliers is the honest picture.
    """
    if not cases:
        return "<p>No cases.</p>"

    width, height, pad_l, pad_b, pad_t = 900, 260, 46, 26, 12
    items = list(cases.items())
    top = max(
        [c["drift"] for _, c in items] + [c["threshold"] for _, c in items] + [0.01]
    ) * 1.15
    plot_w = width - pad_l - 12
    plot_h = height - pad_b - pad_t

    def x_of(i: int) -> float:
        return pad_l + (plot_w * (i + 0.5) / len(items))

    def y_of(v: float) -> float:
        return pad_t + plot_h - (plot_h * (v / top))

    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
        f'role="img" aria-label="Per-case drift against each case\'s own threshold">'
    ]

    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        y = y_of(top * frac)
        parts.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width - 12}" y2="{y:.1f}" '
            f'stroke="#eceff2" stroke-width="1"/>'
            f'<text x="{pad_l - 8}" y="{y + 3:.1f}" text-anchor="end" '
            f'font-size="10" fill="#8a929b">{top * frac:.3f}</text>'
        )

    for i, (cid, c) in enumerate(items):
        x, ty = x_of(i), y_of(c["threshold"])
        parts.append(
            f'<line x1="{x - 4:.1f}" y1="{ty:.1f}" x2="{x + 4:.1f}" y2="{ty:.1f}" '
            f'stroke="#98a2ad" stroke-width="1.5"/>'
        )

    for i, (cid, c) in enumerate(items):
        x, y = x_of(i), y_of(c["drift"])
        colour = VERDICT_COLOUR.get(c["verdict"], "#666")
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="{colour}" '
            f'fill-opacity="0.85"><title>{_esc(cid)}: drift {c["drift"]}, '
            f'threshold {c["threshold"]} ({_esc(c["verdict"])})</title></circle>'
        )

    parts.append(
        f'<line x1="{pad_l}" y1="{pad_t + plot_h}" x2="{width - 12}" '
        f'y2="{pad_t + plot_h}" stroke="#c9d0d8"/>'
        f'<text x="{pad_l}" y="{height - 6}" font-size="10" fill="#8a929b">'
        f'case 1</text>'
        f'<text x="{width - 12}" y="{height - 6}" font-size="10" fill="#8a929b" '
        f'text-anchor="end">case {len(items)}</text></svg>'
    )
    return "".join(parts)


def _cards(report: dict) -> str:
    s = report["summary"]
    sd = report.get("suite_drift", {})
    cost = report.get("cost", {})
    median, threshold = sd.get("median", 0), sd.get("threshold", 0)
    systemic = " (systemic)" if sd.get("systemic") else ""
    cells = [
        ("pass", s["PASS"], "PASS"),
        ("drift", s["DRIFT"], "DRIFT"),
        ("fail", s["FAIL"], "FAIL"),
        ("median drift", f"{median} / {threshold}{systemic}", ""),
        ("judge calls", report.get("judge_calls", 0), ""),
        ("total cost", f"${cost.get('current_total', 0):.5f}", ""),
    ]
    return "".join(
        f'<div class="card"><div class="k">{_esc(k)}</div>'
        f'<div class="v {cls}">{_esc(v)}</div></div>'
        for k, v, cls in cells
    )


def _changed(report: dict) -> str:
    if not report.get("fingerprint_changed"):
        return ""
    params = report.get("params", {})
    old, new = params.get("baseline") or {}, params.get("current") or {}
    rows = [
        f"<li><code>{_esc(k)}</code>: <code>{_esc(old.get(k, '—'))}</code> &rarr; "
        f"<code>{_esc(new.get(k, '—'))}</code></li>"
        for k in sorted(set(old) | set(new))
        if old.get(k) != new.get(k)
    ]
    cost = report.get("cost", {})
    before, after = cost.get("baseline_per_run"), cost.get("current_per_run")
    if before and after is not None:
        pct = (after - before) / before * 100
        rows.append(
            f"<li>cost: <code>${before:.6f}</code> &rarr; <code>${after:.6f}</code> "
            f"per run ({pct:+.0f}%)</li>"
        )
    if not rows:
        rows.append("<li>the prompt template was edited</li>")
    return f'<div class="changed"><h2>What changed</h2><ul>{"".join(rows)}</ul></div>'


def _rows(report: dict) -> str:
    out = []
    for cid, c in report["cases"].items():
        cause = ", ".join(c["broken_assertions"]) or (
            f"judge: {c['judge']}" if c.get("judge") else ""
        )
        before, after = _diff_spans(c["baseline_sample"], c["current_sample"])
        verdict = c["verdict"]
        out.append(
            f'<details class="row" data-verdict="{_esc(verdict)}">'
            f'<summary>'
            f'<span class="{_esc(verdict)}">{VERDICT_ICON.get(verdict, "&#9679;")}</span>'
            f'<span class="cid">{_esc(cid)}</span>'
            f'<span class="cause">{_esc(cause)}</span>'
            f'<span class="num">{c["drift"]}</span>'
            f'<span class="num thr">{c["threshold"]}</span>'
            f'</summary>'
            f'<div class="detail">'
            f'<div class="meta"><span>verdict: <strong class="{_esc(verdict)}">'
            f'{_esc(verdict)}</strong></span>'
            f'<span>drift {c["drift"]} vs threshold {c["threshold"]}</span>'
            f'<span>noise floor {c.get("noise_floor", 0)}</span>'
            f'<span>judge: {_esc(c.get("judge") or "not called")}</span>'
            f'<span>cost ${c.get("cost_usd", 0):.6f}</span></div>'
            f'<div class="sbs">'
            f"<div><h3>Baseline</h3><pre>{before}</pre></div>"
            f"<div><h3>Current</h3><pre>{after}</pre></div>"
            f"</div></div></details>"
        )
    return "".join(out)


def render(report: dict, title: str = "PromptLock report") -> str:
    s = report["summary"]
    total = sum(s.values())
    if s["FAIL"]:
        headline = f"{s['FAIL']} of {total} cases regressed"
    elif s["DRIFT"]:
        headline = f"{s['DRIFT']} of {total} cases changed without getting worse"
    else:
        headline = f"all {total} cases hold"

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<style>{CSS}</style>
</head><body><div class="wrap">
<h1>{_esc(title)}</h1>
<p class="sub">{_esc(headline)}.</p>
<div class="cards">{_cards(report)}</div>
{_changed(report)}
<figure>{_scatter(report["cases"])}
<figcaption>Each dot is one case's drift; the grey tick beside it is that
case's own threshold, measured from its own noise at record time. A dot below
its tick is within noise. Colour is the verdict.</figcaption></figure>
<div class="legend">
  <span class="PASS">&#9679; pass</span>
  <span class="DRIFT">&#9679; drift</span>
  <span class="FAIL">&#9679; fail</span>
  <span>&#9472; per-case threshold</span>
</div>
<div class="filters" hidden>
  <button data-filter="ALL" aria-pressed="true">All</button>
  <button data-filter="FAIL" aria-pressed="false">Fail</button>
  <button data-filter="DRIFT" aria-pressed="false">Drift</button>
  <button data-filter="PASS" aria-pressed="false">Pass</button>
</div>
{_rows(report)}
</div><script>{JS}</script></body></html>
"""
