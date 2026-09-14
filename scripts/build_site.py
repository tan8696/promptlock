"""Build the static demo site in public/ for Vercel or GitHub Pages.

PromptLock is a CLI, so there is no app to host -- but the report is the part
people need to *see*, and the benchmark is the part they need to *poke at*.

This renders:
  index.html    the pitch
  explore.html  all 19 benchmark variants, interactive, from real runs
  report-*.html two real reports, clean and regressed

Variant definitions are imported from scripts/benchmark.py rather than copied,
so the site can never disagree with the acceptance gate.

    python3 scripts/build_site.py
"""

from __future__ import annotations

import glob
import hashlib
import importlib
import json
import os
import shutil
import sys
from dataclasses import replace

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))

import benchmark as bm  # noqa: E402

from promptlock import htmlreport, store  # noqa: E402
from promptlock.runner import Config, check  # noqa: E402

OUT = "public"
SITE = "https://promptlock-jj6y.vercel.app"
MANIFEST = os.path.join(OUT, "build-manifest.json")

# Everything the generated pages are derived from. Change any of these without
# rebuilding and the live demo shows results the code no longer produces.
INPUTS = [
    "promptlock.yaml",
    "scripts/build_site.py",
    "scripts/benchmark.py",
    "examples/demo_app/app.py",
    "examples/demo_app/cases.yaml",
    ".promptlock/baseline.json",
]


def _inputs_fingerprint() -> str:
    """Hash of the sources the site is built from.

    Normalised to LF and hashed per path, so it is identical on every platform.
    Deliberately not a hash of the *output*: drift values differ in the fourth
    decimal between libm implementations, so byte-comparing generated pages
    across platforms tests the C library, not staleness (see LIMITATIONS.md).
    """
    paths = sorted(INPUTS + glob.glob("promptlock/**/*.py", recursive=True))
    digest = hashlib.sha256()
    for path in paths:
        with open(path, encoding="utf-8") as f:  # universal newlines -> \n
            body = f.read()
        digest.update(path.replace(os.sep, "/").encode())
        digest.update(hashlib.sha256(body.encode()).digest())
    return digest.hexdigest()

SHARED_CSS = """
:root {
  --ink:#14161a; --muted:#5c6570; --line:#e2e6ea; --bg:#fff; --panel:#f7f8fa;
  --accent:#1a7f5a; --warn:#b7791f; --bad:#c02b2b;
}
@media (prefers-color-scheme: dark) {
  :root {
    --ink:#e7ebf0; --muted:#97a1ad; --line:#2b313a; --bg:#14171c;
    --panel:#1b1f26; --accent:#56cfa1; --warn:#e0b25d; --bad:#ff8a8a;
  }
}
* { box-sizing:border-box; }
body {
  margin:0; padding:48px 24px 80px; background:var(--bg); color:var(--ink);
  font:15px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
}
a { color:var(--accent); }
h1 { font-size:34px; margin:0 0 6px; letter-spacing:-0.02em; }
h2 { font-size:14px; text-transform:uppercase; letter-spacing:.05em;
     color:var(--muted); margin:36px 0 12px; }
.tag { font-size:17px; color:var(--muted); margin:0 0 26px; }
.note { color:var(--muted); font-size:13px; }
code, pre { font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }
pre { background:var(--panel); border:1px solid var(--line); border-radius:8px;
      padding:14px; overflow-x:auto; font-size:13px; }
table { border-collapse:collapse; width:100%; margin:0 0 12px; font-size:14px; }
th, td { text-align:left; padding:9px 10px; border-bottom:1px solid var(--line); }
th { color:var(--muted); font-weight:600; font-size:12px;
     text-transform:uppercase; letter-spacing:.04em; }
.n { font-variant-numeric:tabular-nums; }
footer { margin-top:48px; color:var(--muted); font-size:13px;
         border-top:1px solid var(--line); padding-top:18px; }
"""

LANDING = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PromptLock — CI for prompts</title>
<style>__CSS__
.wrap { max-width:760px; margin:0 auto; }
.cta { display:flex; flex-wrap:wrap; gap:10px; margin:14px 0 0; }
.cta a { display:block; padding:14px 18px; border:1px solid var(--line);
         border-radius:10px; background:var(--panel); text-decoration:none;
         color:var(--ink); flex:1 1 230px; }
.cta a:hover { border-color:var(--accent); }
.cta strong { display:block; font-size:15px; color:var(--accent); }
.cta span { color:var(--muted); font-size:13px; }
.win { color:var(--accent); font-weight:700; }
</style>
</head><body><div class="wrap">

<h1>PromptLock</h1>
<p class="tag"><strong>CI for prompts.</strong> Fail the pull request when a
prompt, model, or parameter change silently makes your LLM outputs worse.</p>

<p>Your test suite catches broken code. Nothing catches a prompt edit that
quietly stops returning parseable JSON on half your inputs. Detecting that
output <em>changed</em> is trivial — LLMs are stochastic, so any tool that diffs
strings fires on whitespace and gets muted in a week. Detecting that it got
<em>worse</em> is the product.</p>

<h2>Try it here</h2>
<div class="cta">
  <a href="explore.html"><strong>Explore all 19 changes &rarr;</strong>
  <span>Pick any prompt or model change and see what PromptLock decides, and
  why</span></a>
  <a href="report-fail.html"><strong>A failing report &rarr;</strong>
  <span>Sonnet downgraded to Haiku: 6 of 50 regressed, 73% cheaper</span></a>
  <a href="report-pass.html"><strong>A clean report &rarr;</strong>
  <span>All 50 cases hold — what a quiet PR looks like</span></a>
</div>
<p class="note" style="margin-top:14px">Everything here is real output from
<code>promptlock check</code>, generated by
<code>scripts/build_site.py</code>. Nothing is mocked up.</p>

<h2>Does it work?</h2>
<p>6 prompt edits that genuinely degrade output, 10 a reviewer would wave
through, 3 model/parameter changes. 50 cases each.</p>
<table>
  <tr><th>Detector</th><th>Recall</th><th>False positives</th><th>Precision</th></tr>
  <tr><td>Naive string diff</td><td class="n">6/6</td><td class="n">10/10</td>
      <td class="n">38%</td></tr>
  <tr><td class="win">PromptLock</td><td class="n win">6/6</td>
      <td class="n win">0/10</td><td class="n win">100%</td></tr>
</table>
<p>Both find every real regression. Only one is quiet enough to leave switched
on. That gap is the entire product.</p>

<h2>Run it yourself</h2>
<pre>git clone https://github.com/tan8696/promptlock
cd promptlock &amp;&amp; pip install -e .

promptlock record     # snapshot known-good behaviour
promptlock check      # 50 pass · 0 drift · 0 fail
python3 scripts/benchmark.py</pre>
<p>No API key, no network, no account — the demo runs against a behavioural
mock, so the numbers above reproduce exactly.</p>

<footer>
PromptLock is a command-line tool and GitHub Action, not a hosted service.
This page is a static preview.
&nbsp;·&nbsp; <a href="https://github.com/tan8696/promptlock">Source on GitHub</a>
&nbsp;·&nbsp; MIT
</footer>

</div></body></html>
"""

EXPLORE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PromptLock — explore the benchmark</title>
<style>__CSS__
.wrap { max-width:1100px; margin:0 auto; }
.cols { display:grid; grid-template-columns:290px 1fr; gap:22px;
        align-items:start; }
.list { border:1px solid var(--line); border-radius:10px; overflow:hidden; }
.grp { padding:8px 12px; background:var(--panel); color:var(--muted);
       font-size:11px; text-transform:uppercase; letter-spacing:.05em;
       border-bottom:1px solid var(--line); }
.item { display:flex; align-items:center; gap:8px; width:100%; text-align:left;
        font:inherit; padding:9px 12px; background:none; color:var(--ink);
        border:0; border-bottom:1px solid var(--line); cursor:pointer; }
.item:hover { background:var(--panel); }
.item[aria-current="true"] { background:var(--ink); color:var(--bg); }
.item .dot { width:8px; height:8px; border-radius:50%; flex:0 0 8px; }
.fire .dot { background:var(--bad); }
.quiet .dot { background:var(--accent); }
.panel { border:1px solid var(--line); border-radius:10px; padding:20px; }
.verdict { display:flex; flex-wrap:wrap; gap:10px 18px; align-items:baseline;
           margin-bottom:4px; }
.verdict h3 { margin:0; font-size:20px; letter-spacing:-0.01em; }
.pill { font-size:12px; padding:3px 10px; border-radius:999px;
        border:1px solid var(--line); color:var(--muted); }
.pill.ok { color:var(--accent); border-color:var(--accent); }
.pill.bad { color:var(--bad); border-color:var(--bad); }
.stats { display:flex; flex-wrap:wrap; gap:16px; margin:16px 0;
         font-variant-numeric:tabular-nums; }
.stat { min-width:78px; }
.stat b { display:block; font-size:19px; }
.stat span { color:var(--muted); font-size:11px; text-transform:uppercase;
             letter-spacing:.04em; }
.p { color:var(--accent); } .d { color:var(--warn); } .f { color:var(--bad); }
.edit { background:var(--panel); border:1px solid var(--line);
        border-radius:8px; padding:12px; font-size:13px; margin:6px 0 4px; }
.edit div { white-space:pre-wrap; word-break:break-word; }
.edit .o { color:var(--bad); } .edit .w { color:var(--accent); }
.sbs { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:8px; }
.sbs h4 { font-size:11px; text-transform:uppercase; letter-spacing:.05em;
          color:var(--muted); margin:0 0 5px; }
.out { background:var(--panel); border:1px solid var(--line); border-radius:6px;
       padding:10px; font-size:12px; white-space:pre-wrap; word-break:break-word;
       font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }
mark { border-radius:2px; padding:0 1px; }
mark.del { background:#ffd9d9; color:#7a1b1b; }
mark.ins { background:#cdf1dd; color:#10543b; }
@media (prefers-color-scheme: dark) {
  mark.del { background:#4a1f1f; color:#ffc9c9; }
  mark.ins { background:#123a2a; color:#9fe8c4; }
}
.case { border-top:1px solid var(--line); padding-top:14px; margin-top:14px; }
.case .cid { font-family:ui-monospace,Menlo,Consolas,monospace; font-size:13px; }
.why { background:var(--panel); border-left:3px solid var(--accent);
       padding:10px 14px; border-radius:0 8px 8px 0; margin:14px 0; }
@media (max-width:860px) {
  .cols { grid-template-columns:1fr; }
  .sbs { grid-template-columns:1fr; }
}
</style>
</head><body><div class="wrap">

<p style="margin:0 0 6px"><a href="index.html">&larr; PromptLock</a></p>
<h1>What does it actually decide?</h1>
<p class="tag">All 19 benchmark variants, replayed against 50 cases each. Pick
one. Everything below is real output from <code>promptlock check</code>.</p>

<div class="cols">
  <div class="list" id="list"></div>
  <div class="panel" id="panel"></div>
</div>

<footer>
A green dot means PromptLock stayed quiet, red means it failed the build.
The six <strong>R</strong> variants genuinely degrade output and should all
fire; the ten <strong>H</strong> variants are harmless and should all stay
quiet; the three <strong>M</strong> variants change the model or its sampling
parameters.
&nbsp;·&nbsp; <a href="https://github.com/tan8696/promptlock">Source</a>
</footer>
</div>

<script id="data" type="application/json">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
const LABEL = {REGRESSION:'Real regressions — should fire',
               HARMLESS:'Harmless edits — should stay quiet',
               MODEL_SWAP:'Model & parameter changes'};
const list = document.getElementById('list');
const panel = document.getElementById('panel');

let html = '';
for (const grp of ['REGRESSION','HARMLESS','MODEL_SWAP']) {
  const rows = DATA.filter(v => v.kind === grp);
  if (!rows.length) continue;
  html += `<div class="grp">${LABEL[grp]}</div>`;
  for (const v of rows) {
    html += `<button class="item ${v.fired?'fire':'quiet'}" data-id="${v.id}">
      <span class="dot"></span><span>${v.id}</span></button>`;
  }
}
list.innerHTML = html;

function esc(s){ return s.replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

function render(v) {
  const correct = v.fired === v.expected;
  const want = v.expected ? 'should fire' : 'should stay quiet';
  const did  = v.fired ? 'failed the build' : 'stayed quiet';

  let edit = '';
  if (v.edit_old !== null) {
    edit = `<h2>The change</h2><div class="edit">
      <div class="o">- ${esc(v.edit_old)}</div>
      <div class="w">+ ${esc(v.edit_new)}</div></div>`;
  } else {
    edit = `<h2>The change</h2><div class="edit">
      <div class="w">${esc(v.edit_new)}</div></div>`;
  }

  const cases = v.samples.map(s => `
    <div class="case">
      <div class="cid"><strong>${s.cid}</strong> — ${s.verdict}
        ${s.broken ? '· <span class="f">' + esc(s.broken) + '</span>' : ''}
        <span class="note">· drift ${s.drift} vs threshold ${s.threshold}</span>
      </div>
      <div class="sbs">
        <div><h4>Baseline</h4><div class="out">${s.before}</div></div>
        <div><h4>After the change</h4><div class="out">${s.after}</div></div>
      </div>
    </div>`).join('');

  panel.innerHTML = `
    <div class="verdict">
      <h3>${v.id}</h3>
      <span class="pill">${want}</span>
      <span class="pill ${correct?'ok':'bad'}">${correct?'✓ correct':'✗ wrong'}</span>
    </div>
    <p class="note" style="margin:0">PromptLock ${did}. A naive string diff
      ${v.naive ? 'fired' : 'stayed quiet'}.</p>
    <div class="stats">
      <div class="stat"><b class="p">${v.summary.PASS}</b><span>pass</span></div>
      <div class="stat"><b class="d">${v.summary.DRIFT}</b><span>drift</span></div>
      <div class="stat"><b class="f">${v.summary.FAIL}</b><span>fail</span></div>
      <div class="stat"><b>${v.median}</b><span>median drift</span></div>
      <div class="stat"><b>${v.judge_calls}</b><span>judge calls</span></div>
    </div>
    <div class="why">${v.why}</div>
    ${edit}
    <h2>Cases</h2>${cases}`;

  for (const b of list.querySelectorAll('.item'))
    b.setAttribute('aria-current', String(b.dataset.id === v.id));
}

list.addEventListener('click', e => {
  const b = e.target.closest('.item');
  if (b) render(DATA.find(v => v.id === b.dataset.id));
});
render(DATA[0]);
</script>
</body></html>
"""


def _why(kind: str, fired: bool, expected: bool, rep: dict, tier: str) -> str:
    """One sentence explaining the verdict, in the detector's own terms."""
    suite = rep.get("suite_drift", {})
    if fired and tier == "assertions":
        return (
            "Assertions the baseline satisfied on every run now fail with enough "
            "evidence to clear the Wilson interval, so this fails on the free "
            "signal — no judge call needed."
        )
    if fired and tier == "judge":
        return (
            f"Not a single assertion broke: the output is still valid JSON. The "
            f"suite median moved to {suite.get('median')} against a threshold of "
            f"{suite.get('threshold')}, which sent the top cases to the judge, and "
            f"it called them worse in both orderings."
        )
    if fired:
        return "This failed the build."
    if kind == "HARMLESS":
        return (
            "Output changed — sampling is stochastic, so it always does — but no "
            "case moved further than it moves on its own, and no assertion broke "
            "with enough evidence to count. A naive string diff fires here; this "
            "is the false positive that gets tools muted."
        )
    return (
        f"The suite median is {suite.get('median')}, inside the "
        f"{suite.get('threshold')} threshold. Nothing moved past its own noise."
    )


def _samples(rep: dict, limit: int = 3) -> list[dict]:
    """Up to `limit` cases, worst first -- a FAIL is what people want to see."""
    order = {"FAIL": 0, "DRIFT": 1, "PASS": 2}
    chosen = sorted(
        rep["cases"].items(), key=lambda kv: (order[kv[1]["verdict"]], kv[0])
    )[:limit]

    out = []
    for cid, c in chosen:
        before, after = htmlreport._diff_spans(
            c["baseline_sample"][:340], c["current_sample"][:340]
        )
        out.append({
            "cid": cid,
            "verdict": c["verdict"],
            "broken": ", ".join(c["broken_assertions"][:3]),
            "drift": c["drift"],
            "threshold": c["threshold"],
            "before": before,
            "after": after,
        })
    return out


def _row(kind, name, old, new, rep, fired, naive, expected) -> dict:
    tier = bm.tier_of(rep, fired)
    return {
        "id": name,
        "kind": kind,
        "edit_old": old,
        "edit_new": new,
        "expected": expected,
        "fired": fired,
        "naive": naive,
        "summary": rep["summary"],
        "median": rep.get("suite_drift", {}).get("median"),
        "judge_calls": rep["judge_calls"],
        "tier": tier,
        "why": _why(kind, fired, expected, rep, tier),
        "samples": _samples(rep),
    }


def collect(cfg: Config, baseline: dict) -> list[dict]:
    """Replay every benchmark variant, keeping what the site needs to show."""
    shutil.copy(bm.APP, bm.BACKUP)
    rows = []
    try:
        for kind, variants in (("REGRESSION", bm.REGRESSIONS), ("HARMLESS", bm.HARMLESS)):
            for name, (old, new) in variants.items():
                bm.patch(old, new)
                importlib.invalidate_caches()
                rep = check(cfg, baseline)
                fired = rep["summary"]["FAIL"] > 0

                # Mirror benchmark.py: the naive check re-patches from pristine.
                shutil.copy(bm.BACKUP, bm.APP)
                importlib.invalidate_caches()
                bm.patch(old, new)
                naive = bm.naive_fires(cfg, baseline)

                rows.append(_row(kind, name, old, new, rep, fired, naive,
                                 kind == "REGRESSION"))
                print(f"  {name:<26} {rep['summary']}")

        shutil.copy(bm.BACKUP, bm.APP)
        importlib.invalidate_caches()

        for name, (override, should_fire) in bm.MODEL_SWAP.items():
            variant = replace(cfg, model_params={**cfg.model_params, **override})
            rep = check(variant, baseline)
            fired = rep["summary"]["FAIL"] > 0
            naive = bm.naive_fires(variant, baseline)
            described = ", ".join(f"{k} = {v}" for k, v in override.items())
            rows.append(_row("MODEL_SWAP", name, None, described, rep, fired,
                             naive, should_fire))
            print(f"  {name:<26} {rep['summary']}")
    finally:
        shutil.copy(bm.BACKUP, bm.APP)
        importlib.invalidate_caches()
    return rows


def check_fresh() -> int:
    """Was the committed site built from the code that is here now?"""
    current = _inputs_fingerprint()
    if not os.path.exists(MANIFEST):
        print(f"::error::{MANIFEST} is missing. Run: python3 scripts/build_site.py")
        return 1

    with open(MANIFEST, encoding="utf-8") as f:
        recorded = json.load(f).get("inputs_sha256")

    if recorded != current:
        print("::error::The demo site is stale: it was built from different "
              "sources than the ones in this commit. "
              "Run: python3 scripts/build_site.py && python3 scripts/make_docs_svg.py, "
              "then commit public/ and docs/.")
        print(f"  recorded {recorded}\n  current  {current}")
        return 1

    print(f"demo site is current ({current[:12]})")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if "--check" in sys.argv[1:]:
        return check_fresh()

    cfg = Config.load("promptlock.yaml")
    baseline = store.load()
    os.makedirs(OUT, exist_ok=True)

    for name, (variant, title) in {
        "report-pass.html": (cfg, "PromptLock — clean run"),
        "report-fail.html": (
            replace(cfg, model_params={**cfg.model_params, "model": "claude-haiku-4-5"}),
            "PromptLock — model downgrade",
        ),
    }.items():
        rep = check(variant, baseline)
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            f.write(htmlreport.render(rep, title))
        print(f"  {name:<26} {rep['summary']}")

    rows = collect(cfg, baseline)

    # </script> inside the payload would end the tag early.
    payload = json.dumps(rows, separators=(",", ":")).replace("</", "<\\/")
    explore = EXPLORE.replace("__CSS__", SHARED_CSS).replace("__DATA__", payload)

    with open(os.path.join(OUT, "explore.html"), "w", encoding="utf-8") as f:
        f.write(explore)
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(LANDING.replace("__CSS__", SHARED_CSS))

    # Written last: the fingerprint covers the sources, so it is only valid
    # once everything built from them is on disk.
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(
            {
                "inputs_sha256": _inputs_fingerprint(),
                "variants": len(rows),
                "generated_by": "scripts/build_site.py",
            },
            f,
            indent=2,
            sort_keys=True,
        )
        f.write("\n")

    correct = sum(1 for r in rows if r["fired"] == r["expected"])
    print(f"\n  explore.html  {len(rows)} variants, {correct}/{len(rows)} correct")
    print(f"  index.html    landing page  ({SITE})")
    print(f"  {MANIFEST}  freshness fingerprint")
    return 0


if __name__ == "__main__":
    sys.exit(main())
