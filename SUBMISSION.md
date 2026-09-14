# PromptLock — submission

## Devpost description (200 words)

Your test suite catches broken code. Nothing catches a prompt edit that quietly
stops returning parseable JSON on half your inputs.

PromptLock is CI for prompts. It records how your LLM behaves on a known-good
commit, then fails the pull request when a prompt, model, or parameter change
makes that behaviour worse.

The hard part isn't detecting change — LLMs are stochastic, so string-diffing
tools fire on whitespace and get muted within a week. The hard part is
detecting *degradation*. PromptLock measures how
much each case naturally wobbles, stores that noise floor, and only raises an
alarm when a change moves a case further than it moves on its own. Failing a
build is a hypothesis test, not a threshold: an assertion counts as broken only
when a Wilson confidence interval on its new pass-rate clears the baseline by a
margin, so an unlucky run can't fail your build.

On a 19-variant benchmark it catches 6 of 6 real regressions with 0 false
positives out of 10 harmless edits — 100% precision, against 38% for a naive
string diff.

It needs zero labelled data to start. Point it at a function, run `record`, and
you have a regression gate the same afternoon.

---

## What it does

Three independent signals produce one verdict per test case:

- **Deterministic assertions** — schema breaks, missing keys, enum violations,
  prose leaking into JSON, latency and cost blowouts. Free, and the only signal
  that can fail a build on its own.
- **Semantic drift** — output moved in a way assertions can't express. Free:
  dependency-free hashed character n-grams, no embedding API.
- **Pairwise LLM judge** — the difference between "changed" and "worse", run
  twice with positions swapped so judge position-bias reports as a tie rather
  than a regression.

Verdicts are PASS (within measured noise), DRIFT (moved, not worse — reported,
doesn't block) and FAIL (an assertion the baseline always held now reliably
fails, or the judge called it worse in both orderings).

Four mechanisms make it quiet enough to leave switched on: a **per-case noise
floor** measured at record time, **confirmation re-runs** that re-sample before
failing, a **Wilson interval** on the pass-rate instead of a point threshold,
and a **suite-level drift gate** that catches instruction changes every
individual case absorbs.

The fingerprint covers the model id and sampling parameters, not just the
template — so a cost-driven downgrade is caught by the same gate, and the PR
comment states the trade in one line: `model: sonnet → haiku`, `cost -73%`,
6 of 50 cases regressed.

## How we built it

Python, standard library only. The single runtime dependency is PyYAML.

- `promptlock/runner.py` is the verdict engine and owns every tunable.
- `promptlock/stats.py` is a Wilson score interval using `statistics.NormalDist`.
- `promptlock/discover.py` walks the repo with `ast` to find LLM call sites and
  prompt constants — static only, it never imports or executes what it scans.
- `promptlock/htmlreport.py` emits a self-contained report: inline SVG scatter,
  no CDN, no fonts, no libraries.
- `promptlock/providers.py` ships a behavioural *simulator*, not a canned
  response table. It reads the prompt and degrades the way a real model would —
  strict format instructions produce bare JSON, loose ones leak fences, cheaper
  model tiers leak more often. That is what makes an offline benchmark mean
  anything.

## Challenges

**Proving the detector works without a labelled dataset.** Solved by building
the benchmark first: 6 edits that genuinely degrade output, 10 a reviewer would
wave through, 3 model changes, scored on precision and recall against a naive
string diff. The benchmark became the acceptance gate — it exits non-zero if
recall drops below 6/6, if false positives exceed 1/10, or if any model change
lands on the wrong side. No change can be validated by tuning a threshold until
the numbers come back.

**One false positive we couldn't tune away.** A semantically null clause swap
fired on 3 of 50 cases. It was documented in LIMITATIONS.md rather than hidden,
then fixed properly by replacing the point threshold with a Wilson interval and
raising k to 5. False positives went 1/10 → 0/10 with no constant touched.

**A benchmark variant that tested nothing.** The `max_tokens` truncation case
was specified at 64 tokens, but the suite's longest completion is 36 — so it
truncated nothing and passed by accident. Measured it, found the real cliff at
32, and corrected the fixture rather than the detector.

## What we learned

Non-determinism is a property of the system under test, not a defect to
suppress. Every tool that treats it as a defect — temperature zero, global
thresholds, averaging across runs — is applying one guess uniformly to cases
with wildly different variance. Measuring variance per case, at record time, is
what moved precision from 38% to 100% on the same suite.

The second lesson: a metric you can tune is not a metric. Writing the benchmark
gate before the features, and making it fail CI, is the only reason the numbers
in this README can be trusted.

## What's next

- **Auto-calibration on `record`** — derive `suite_drift_threshold` from the
  repo's own drift distribution instead of a constant calibrated on one suite.
  Nothing in the category does this.
- **Flake budget as a CI output** — report which prompts are inherently
  unreliable, inverting the question from "did this PR break things" to "which
  of our AI surface is load-bearing and fragile".
- **Sequential testing** — sample more only on cases whose verdict is still
  uncertain. Same confidence, a fraction of the spend.
- **Validation gate before any of it:** run the Action on three real repos and
  measure how many firings the maintainer agrees with. Below four in five, the
  precision work isn't finished and no feature matters.

---

## Judging criteria → artifact

**Innovation**
- `promptlock/stats.py` + `runner._broken` — failing a build as a hypothesis
  test on the pass-rate, not a threshold crossing. This is the novel bit.
- `runner._detect_systemic_drift` — catches instruction changes that break zero
  assertions and clear every per-case threshold (`R6 urgency-inflation`).
- Baseline-relative testing: **zero labelled data to first value**, where every
  comparable tool requires you to write expectations first.

**Technical implementation**
- `scripts/benchmark.py` — 19 variants, precision/recall against a naive
  detector, and the CI gate that exits 1 if the detector regresses.
- 66 tests, 92% coverage, every module covered: `tests/`. Ruff clean.
- `promptlock/discover.py` — an `ast` walk that never executes what it scans,
  with four fixtures covering OpenAI-style, Anthropic-style, constant-only and
  empty files.
- Zero dependencies beyond PyYAML. The demo runs fully offline.

**Problem-solving and impact**
- `LIMITATIONS.md` — written honestly, including the caveats that remain. One
  entry was deleted only after the limitation was actually fixed.
- `promptlock init` — the adoption unlock: point it at an unfamiliar repo and it
  finds the call sites for you.
- The model-swap PR comment: quality delta and cost delta in the same line, for
  a decision teams currently make in a spreadsheet with no quality number in it.

**Presentation**
- **Live demo: https://promptlock-jj6y.vercel.app** — the landing page, two real
  reports, and an interactive explorer over all 19 benchmark variants. Judges can
  click `H10 reorder-tail` (the false positive we fixed) and see it correctly
  stay quiet, or `R6 urgency-inflation` and see a regression that breaks zero
  assertions and is caught only by the suite drift gate plus the judge.
  Built by `scripts/build_site.py` from real runs — the variant definitions are
  imported from `scripts/benchmark.py`, so the site cannot disagree with the gate.
- `scripts/demo.sh` — safe on a clean clone, restores the prompt via an EXIT
  trap, six beats sized for recording.
- `DEMO.md` — exact terminal size, font size, and a spoken line per beat timed
  to 90 seconds.
- `promptlock check --html report.html` — self-contained report that opens from
  `file://` and still works with JavaScript disabled.
- `README.md` — every number in it is reproducible by a command in the repo.
