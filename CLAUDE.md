# PromptLock

CI for prompts: fail the PR when a prompt, model, or parameter change silently
degrades LLM output.

## Architecture: three signals, one verdict per case

| Signal | Module | Catches | Can FAIL alone? |
|---|---|---|---|
| Deterministic assertions | `scorers/assertions.py` | schema breaks, missing keys, enum violations, prose leakage, latency/cost blowouts | yes |
| Semantic drift | `scorers/drift.py` | output moved further than the case's own measured noise | no — escalates to the judge |
| Pairwise LLM judge | `scorers/judge.py` | "different" vs genuinely "worse", position-swapped to debias | yes, via drift |

Verdicts: **PASS** (within measured noise) · **DRIFT** (moved, not worse — does
not fail the build) · **FAIL** (assertion the baseline always satisfied now
mostly fails, or the judge said worse in both orderings).

Two ideas carry the design: a **per-case noise floor** measured at record time
(`threshold = max(drift_floor, noise_floor × drift_multiplier)`), and
**confirmation re-runs** that re-sample a suspected regression before failing
the build. A **suite-level drift gate** catches instruction changes that every
individual case absorbs.

---

## HARD RULE — the benchmark is the acceptance gate

`scripts/benchmark.py` is the acceptance test for this project. After **any**
change under `promptlock/`, run it:

```bash
python3 scripts/benchmark.py
```

It replays 19 variants against 50 cases each: 6 prompt edits that genuinely
degrade output, 10 a reviewer would wave through, and 3 model/parameter changes
(`MODEL_SWAP`, scored separately — M2 is expected to stay quiet).

**Recall must stay 6/6. False positives must not exceed 1/10.**

The suite currently scores **6/6 recall, 0/10 false positives, 100% precision**.
The gate is 1/10 so there is headroom, but going 0/10 → 1/10 is a regression
even though it passes: say so rather than letting it pass quietly.

If a change lowers recall or raises false positives, **revert the change and
report what you saw.** Do not tune thresholds, constants, or the case set to
make the numbers come back. The benchmark measures the detector; editing the
detector's constants until the benchmark passes measures nothing.

## HARD RULE — never hand-edit the baseline

`.promptlock/baseline.json` is generated. Never edit it by hand. Regenerate:

```bash
promptlock record
```

## HARD RULE — LIMITATIONS.md stays honest

`LIMITATIONS.md` is the project's credibility. Keep it true:

- Fix something listed there → **delete that entry**.
- Introduce a new limitation → **add it**.

A limitation that has been fixed but is still documented is as much a lie as one
that was never written down.

---

## File map

```
promptlock.yaml             config: target, cases, thresholds, assertions
.promptlock/baseline.json   the snapshot — committed, reviewable in a PR diff
CLAUDE.md                   this file
README.md                   the pitch and the results table
LIMITATIONS.md              where the measurements stop being trustworthy
DEMO.md                     how to record the 90-second demo
SUBMISSION.md               Devpost copy + judging-criteria map
SETUP.md                    first-run instructions for a fresh unzip

promptlock/
  __init__.py       empty — package marker only
  cli.py            argparse entry: `init` | `record` | `check`; exit code is the CI gate
  discover.py       AST walk — finds call sites + prompt constants, scaffolds config.
                    Static only: never imports or executes the scanned repo
  stats.py          Wilson score interval + z_for(confidence). Pure, no imports
                    from the rest of the package
  runner.py         verdict engine — owns run_suite/record/check, noise floors,
                    confirmation re-runs, the Wilson break rule, suite-level
                    systemic drift, and the Config dataclass (every tunable lives here)
  providers.py      MockProvider (behavioural simulator, seeded on prompt+run+model)
                    + AnthropicProvider. Owns model-tier behaviour and PRICE_BY_MODEL
  store.py          baseline save/load + prompt fingerprint
  report.py         markdown (PR comment) + console rendering
  htmlreport.py     self-contained HTML: inline CSS/JS, SVG scatter, char diff.
                    Must stay dependency-free and usable with JS disabled —
                    expansion is native <details>, the diff is computed in Python
  scorers/
    assertions.py   evaluate() per run, rate() per case — the only free FAIL
    drift.py        hashed char 4-gram embedding, cosine, self/cross distance
    judge.py        position-swapped pairwise compare + offline MockJudge rubric

examples/demo_app/  app.py (the target prompt) + cases.yaml (50 tickets)
scripts/
  gen_cases.py      regenerates cases.yaml
  benchmark.py      the acceptance gate — precision/recall vs a naive string diff,
                    exits 1 if recall < 6/6 or false positives > 1/10
  calibrate.py      measures the harmless/behavioural gap behind suite_drift_threshold
  demo.sh           scripted walkthrough; restores the prompt via an EXIT trap
tests/              pytest; also runnable standalone (python3 tests/test_x.py)
  fixtures/         deliberately unrunnable samples for the AST walker to read
.github/workflows/  promptlock.yml (PR check + sticky comment), test.yml (lint,
                    pytest, coverage, benchmark gate)
```

## Ownership notes

- **All tunables live on `Config` in `runner.py`** and are surfaced in
  `promptlock.yaml`. Do not scatter constants into scorers.
- **Scorers are pure and stateless.** They take runs and config, return numbers
  or booleans. Verdict logic belongs in `runner.py`, not in a scorer.
- **`store.py` owns the on-disk format.** Anything that reads or writes
  `.promptlock/` goes through it.
- The demo runs fully offline against `MockProvider` — no API key, no network.
  Benchmark numbers measure *the detector*, not any real model.

## Commands

```bash
promptlock init --dry-run          # scan a repo for LLM call sites
promptlock record                  # snapshot known-good behaviour
promptlock check                   # exits 1 if anything regressed
promptlock check --markdown report.md --html report.html
pytest -q                          # 66 tests
ruff check .                       # must stay clean
python3 scripts/benchmark.py       # the gate
```

If the `promptlock` console script is not on PATH, `python3 -m promptlock.cli`
is equivalent and always works from the repo root.
