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

VERDICT_ICON = {"PASS": "&#9679;", "DRIFT": "&#9679;", "FAIL": "&#9679;"}

CSS = """
:root {
  --ink: #14161a; --muted: #5c6570; --line: #e2e6ea; --bg: #ffffff;
  --panel: #f7f8fa; --raise: #ffffff; --stripe: #fcfcfd; --hover: #f2f4f7;
  --pass: #1a7f5a; --drift: #9c6511; --fail: #c02b2b;
  --grid: #eceff2; --axis: #c9d0d8; --tick: #98a2ad;
  --warn-bg: #fdf8ec; --warn-line: #f0d9a8; --warn-ink: #8a6d1f;
  --del-bg: #ffd9d9; --del-ink: #7a1b1b;
  --ins-bg: #cdf1dd; --ins-ink: #10543b;
}
/* The report is read wherever the reviewer happens to be. */
@media (prefers-color-scheme: dark) {
  :root {
    --ink: #e7ebf0; --muted: #97a1ad; --line: #2b313a; --bg: #14171c;
    --panel: #1b1f26; --raise: #1b1f26; --stripe: #181c22; --hover: #222833;
    --pass: #56cfa1; --drift: #e0b25d; --fail: #ff8a8a;
    --grid: #232933; --axis: #3a424e; --tick: #6a7481;
    --warn-bg: #241f14; --warn-line: #4a3d20; --warn-ink: #e0b25d;
    --del-bg: #4a1f1f; --del-ink: #ffc9c9;
    --ins-bg: #123a2a; --ins-ink: #9fe8c4;
  }
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
.banner {
  display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 12px;
  border-radius: 8px; padding: 14px 16px; margin-bottom: 20px;
  border: 1px solid var(--line); background: var(--panel);
  border-left: 4px solid var(--muted);
}
.banner strong { font-size: 17px; letter-spacing: -0.01em; }
.banner span { color: var(--muted); }
.banner.pass  { border-left-color: var(--pass); }
.banner.pass strong  { color: var(--pass); }
.banner.drift { border-left-color: var(--drift); }
.banner.drift strong { color: var(--drift); }
.banner.fail  { border-left-color: var(--fail); }
.banner.fail strong  { color: var(--fail); }
.changed {
  border: 1px solid var(--warn-line); background: var(--warn-bg);
  border-radius: 8px; padding: 12px 14px; margin-bottom: 20px;
}
.changed h2 { font-size: 13px; margin: 0 0 6px; text-transform: uppercase;
              letter-spacing: 0.04em; color: var(--warn-ink); }
.changed ul { margin: 0; padding-left: 18px; }
.changed code { background: var(--line); padding: 1px 4px; border-radius: 3px; }
figure { margin: 0 0 24px; border: 1px solid var(--line); border-radius: 8px;
         padding: 12px; overflow-x: auto; }
figcaption { color: var(--muted); font-size: 12px; margin-top: 6px; }
.filters { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; }
.filters button {
  font: inherit; padding: 5px 12px; border: 1px solid var(--line);
  background: var(--raise); border-radius: 999px; cursor: pointer;
  color: var(--ink);
}
.filters button:hover { background: var(--hover); }
.filters button[aria-pressed="true"] { background: var(--ink); color: var(--bg);
                                        border-color: var(--ink); }
.filters .n { opacity: 0.55; font-variant-numeric: tabular-nums; }
:focus-visible { outline: 2px solid var(--pass); outline-offset: 2px;
                 border-radius: 4px; }
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
.row:nth-of-type(odd) > summary { background: var(--stripe); }
.row > summary:hover { background: var(--hover); }
.cid { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.num { text-align: right; font-variant-numeric: tabular-nums;
       color: var(--muted); }
.cause { color: var(--muted); overflow: hidden; text-overflow: ellipsis;
         white-space: nowrap; }
.PASS { color: var(--pass); } .DRIFT { color: var(--drift); }
.FAIL { color: var(--fail); }
.detail { padding: 4px 12px 16px; background: var(--stripe);
          border-top: 1px dashed var(--line); }
.sbs { display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
       margin-top: 10px; }
.sbs h3 { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em;
          color: var(--muted); margin: 0 0 5px; }
pre {
  margin: 0; padding: 10px; background: var(--raise);
  border: 1px solid var(--line);
  border-radius: 6px; white-space: pre-wrap; word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px; line-height: 1.5;
}
mark { border-radius: 2px; padding: 0 1px; }
mark.del { background: var(--del-bg); color: var(--del-ink); }
mark.ins { background: var(--ins-bg); color: var(--ins-ink); }
.meta { display: flex; gap: 16px; flex-wrap: wrap; color: var(--muted);
        font-size: 12px; margin-top: 10px; }
/* SVG presentation attributes cannot take var(), so the chart is styled here.
   Dots inherit their verdict colour through currentColor. */
svg .grid { stroke: var(--grid); stroke-width: 1; }
svg .axis { stroke: var(--axis); }
svg .tick { stroke: var(--tick); stroke-width: 1.5; }
svg .median { stroke: var(--drift); stroke-width: 1; stroke-dasharray: 5 4;
              opacity: 0.8; }
svg .lbl { fill: var(--muted); font-size: 10px; }
svg .dot { fill: currentColor; fill-opacity: 0.9; }
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


def _scatter(cases: dict, suite: dict | None = None) -> str:
    """Drift per case with each case's own threshold drawn as a tick.

    The ticks usually line up, because most cases are stable enough that
    max(drift_floor, noise x multiplier) is just the floor. The ones that sit
    higher are the naturally noisy cases, and seeing which those are is the
    point -- a flat row of ticks with two outliers is the honest picture.
    """
    if not cases:
        return "<p>No cases.</p>"

    suite = suite or {}
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
            f'<line class="grid" x1="{pad_l}" y1="{y:.1f}" x2="{width - 12}" '
            f'y2="{y:.1f}"/>'
            f'<text class="lbl" x="{pad_l - 8}" y="{y + 3:.1f}" '
            f'text-anchor="end">{top * frac:.3f}</text>'
        )

    for i, (_cid, c) in enumerate(items):
        x, ty = x_of(i), y_of(c["threshold"])
        parts.append(
            f'<line class="tick" x1="{x - 4:.1f}" y1="{ty:.1f}" '
            f'x2="{x + 4:.1f}" y2="{ty:.1f}"/>'
        )

    for i, (cid, c) in enumerate(items):
        x, y = x_of(i), y_of(c["drift"])
        parts.append(
            f'<circle class="dot {_esc(c["verdict"])}" cx="{x:.1f}" cy="{y:.1f}" '
            f'r="3.4"><title>{_esc(cid)}: drift {c["drift"]}, '
            f'threshold {c["threshold"]} ({_esc(c["verdict"])})</title></circle>'
        )

    # The suite median: the line the systemic-drift gate actually watches.
    median = suite.get("median")
    if median is not None and median <= top:
        my = y_of(median)
        parts.append(
            f'<line class="median" x1="{pad_l}" y1="{my:.1f}" x2="{width - 12}" '
            f'y2="{my:.1f}"><title>suite median {median}</title></line>'
            f'<text class="lbl" x="{width - 14}" y="{my - 4:.1f}" '
            f'text-anchor="end">suite median {median}</text>'
        )

    parts.append(
        f'<line class="axis" x1="{pad_l}" y1="{pad_t + plot_h}" x2="{width - 12}" '
        f'y2="{pad_t + plot_h}"/>'
        f'<text class="lbl" x="{pad_l}" y="{height - 6}">case 1</text>'
        f'<text class="lbl" x="{width - 12}" y="{height - 6}" '
        f'text-anchor="end">case {len(items)}</text></svg>'
    )
    return "".join(parts)


def _banner(report: dict) -> str:
    """The one line a reviewer reads before deciding whether to care."""
    s = report["summary"]
    total = sum(s.values())
    if s["FAIL"]:
        return (
            f'<div class="banner fail"><strong>{s["FAIL"]} of {total} cases '
            f"regressed</strong><span>This fails the build. Expand a row to see "
            f"which assertion broke and what the output looks like now.</span></div>"
        )
    if s["DRIFT"]:
        return (
            f'<div class="banner drift"><strong>{s["DRIFT"]} of {total} cases '
            f"changed</strong><span>Output moved past its noise floor, but the "
            f"judge did not find it worse. The build passes.</span></div>"
        )
    return (
        f'<div class="banner pass"><strong>All {total} cases hold</strong>'
        f"<span>Nothing moved further than it moves on its own.</span></div>"
    )


def _filters(report: dict) -> str:
    counts = {"ALL": len(report["cases"])}
    for verdict in ("FAIL", "DRIFT", "PASS"):
        counts[verdict] = sum(
            1 for c in report["cases"].values() if c["verdict"] == verdict
        )
    labels = {"ALL": "All", "FAIL": "Fail", "DRIFT": "Drift", "PASS": "Pass"}
    buttons = "".join(
        f'<button data-filter="{key}" aria-pressed="{str(key == "ALL").lower()}">'
        f'{labels[key]} <span class="n">{counts[key]}</span></button>'
        for key in ("ALL", "FAIL", "DRIFT", "PASS")
    )
    return f'<div class="filters" hidden>{buttons}</div>'


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
{_banner(report)}
<div class="cards">{_cards(report)}</div>
{_changed(report)}
<figure>{_scatter(report["cases"], report.get("suite_drift"))}
<figcaption>Each dot is one case's drift; the grey tick beside it is that
case's own threshold, measured from its own noise at record time. A dot below
its tick is within noise. Colour is the verdict.</figcaption></figure>
<div class="legend">
  <span class="PASS">&#9679; pass</span>
  <span class="DRIFT">&#9679; drift</span>
  <span class="FAIL">&#9679; fail</span>
  <span>&#9472; per-case threshold</span>
</div>
{_filters(report)}
{_rows(report)}
</div><script>{JS}</script></body></html>
"""
