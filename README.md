# PromptLock — CI for prompts

Your test suite catches broken code. Nothing catches a prompt edit that quietly
stops returning parseable JSON on 23 of your 50 inputs.

PromptLock snapshots your LLM outputs on a known-good commit, then fails the
pull request when a prompt, model, or parameter change makes them worse.

```
❌ 50 of 50 cases regressed.

| Case   | Cause                             | Baseline                          | Now                              |
|--------|-----------------------------------|-----------------------------------|----------------------------------|
| t001   | `key:summary`                     | {"category":"billing","urgency":… | Here's the classification: ```j… |
| t002   | `key:summary`, `nomatch:^(sure…)` | {"category":"billing","urgency":… | Sure! {"category":"billing", …   |
```

That PR changed four words in a prompt — it dropped `summary` from the output
and started leaking prose. No reviewer catches this by reading a diff.

Every number in this README comes from a command in this repo. That one is
`bash scripts/demo.sh`.

## Does it work?

6 prompt edits that genuinely degrade output, 10 a reviewer would wave through,
3 model/parameter changes. 50 cases each. One command, no API key:

```bash
python3 scripts/benchmark.py
```

| Detector | Recall | False positives | Precision |
|---|---|---|---|
| Naive string diff | 6/6 (100%) | 10/10 (100%) | 38% |
| **PromptLock** | **6/6 (100%)** | **0/10 (0%)** | **100%** |

Both find every real regression. Only one is quiet enough to leave switched on.
That gap is the product.

## 30-second try it

```bash
pip install -e .
promptlock record                      # snapshot known-good behaviour
promptlock check                       # 50 pass · 0 drift · 0 fail

# now break the prompt: in examples/demo_app/app.py, change
#   "Respond with ONLY valid JSON. No prose, no markdown fence."
# to
#   "Respond in JSON. Keep it brief."

promptlock check                       # 0 pass · 0 drift · 50 fail, exits 1
promptlock check --html report.html    # open it — scatter, filters, diffs
```

No API key, no network, no account. The demo runs against a behavioural mock.
Prefer it scripted? `bash scripts/demo.sh` does the same and restores the file.

---

## The actual problem

You have no ground-truth labels for LLM output. So you cannot write
`assert output == expected`. Every team discovers this and falls back to
eyeballing a few examples, which does not scale past the first week.

The naive fix — diff the output strings — fires on **every** prompt edit,
including whitespace, because sampling is stochastic. Teams mute it within days.

**Detecting change is trivial. Detecting *degradation* is the product.**

## How it works

Three independent signals, one verdict per case.

| Signal | What it catches | Cost |
|---|---|---|
| **1. Deterministic assertions** | Schema breaks, missing keys, enum violations, prose leakage, latency/cost blowouts | Free |
| **2. Semantic drift** | Output moved, in a way assertions can't express | Free (local embeddings) |
| **3. Pairwise LLM judge** | "Different" vs "worse", on the cases that drifted | 2 calls/drifted case |

### The two ideas that make it usable

**Per-case noise floor.** Every case is run `k` times at record time and its own
mean pairwise self-distance is stored. A case that naturally wobbles gets a wider
threshold than one that is rock solid. Nothing is compared against a global
constant you had to guess.

```
drift threshold = max(drift_floor, case_noise_floor × 1.5)
```

**Confirmation re-runs.** When an assertion looks broken, the case is re-sampled
`k` more times before the build is failed — flaky-test quarantine, applied to
prompts. This alone takes the false-positive rate from 100% to 10%.

**Breaking a build is a hypothesis test.** A pass-rate of 0/3 and 0/30 are both
"0%", but only one is evidence. An assertion counts as broken only when the 95%
Wilson upper bound on its new pass-rate sits a clear margin below the rate the
baseline held (`promptlock/stats.py`), so an unlucky 2-of-3 cannot fail your
build. This is what took the last false positive to zero.

**Position-swapped judging.** LLM judges favour whichever answer they see first,
so every comparison runs twice with the positions swapped. A verdict only counts
when both orderings agree; disagreement is reported as a tie, never a regression.

**Suite-level drift.** A harmless edit nudges two or three cases past their
thresholds by luck. An instruction change shifts the *whole distribution* —
`"Err on the side of high urgency"` moves the median case 3× its usual distance
while breaking no assertion and clearing no per-case threshold. Per-case gating
buys precision; the suite gate buys back sensitivity. The threshold sits in the
measured gap between harmless and behavioural edits (`scripts/calibrate.py`),
not in a guess.

**A model swap is a prompt change.** The fingerprint covers the model id and
sampling parameters, not just the template, so a cost-driven downgrade is caught
by the same gate — and the PR comment states the trade in one line:

```
> ⚠️ What changed
> - `model`: `claude-sonnet-4-6` → `claude-haiku-4-5`
> - cost: $0.000332 → $0.000089 per run (-73%)
```

73% cheaper, 6 of 50 cases regressed. That decision currently gets made in a
spreadsheet with no quality number in it.

**Judge spend scales with the change, not the suite.** The judge is only invoked
on cases that already drifted, plus the top 5 when systemic drift fires. A no-op
PR costs zero judge calls.

## Results in detail

The headline table is [above](#does-it-work). `scripts/benchmark.py` also exits
non-zero if recall drops below 6/6, false positives rise above 1/10, or any
model/parameter variant lands on the wrong side — so the detector cannot regress
silently. That is the gate CI runs.

The model/parameter group is scored separately, since two of its three variants
*should* fire and one should not:

| Variant | Expected | Result |
|---|---|---|
| `M1` sonnet → haiku | fire | ✅ fires — format leak, 6 of 50 regressed |
| `M2` temperature 0.0 → 0.2 | quiet | ✅ quiet — inside the measured noise |
| `M3` max_tokens 1000 → 24 | fire | ✅ fires — truncation breaks JSON on 42 of 50 |

Two of the six break **zero assertions** — `R4 hedging-instruction` and
`R6 urgency-inflation` produce perfectly valid JSON with the wrong values.
Nothing but the suite-level drift gate plus the judge sees them. The tiers are
not decoration.

`H10 reorder-tail` — a semantically null clause swap that used to fire on 3 of
50 cases — went quiet when the point threshold became a Wilson interval. It was
fixed, not tuned away: every constant in `promptlock.yaml` is unchanged from the
run that scored 86%. What remains uncertain is in
[LIMITATIONS.md](LIMITATIONS.md).

## Quickstart

```bash
pip install -e .

promptlock init          # scan the repo for LLM call sites, scaffold a config
promptlock record        # snapshot known-good behaviour on main
# ...edit examples/demo_app/app.py PROMPT...
promptlock check         # exits 1 if anything regressed
promptlock check --html report.html   # one self-contained file, opens from file://
```

The HTML report is a single file with no CDN, no fonts, and no libraries: a
drift scatter with every case's own threshold drawn beside it, a filterable
case list, and a character-level diff of baseline vs current. Expansion is
native `<details>` and the diff is computed in Python, so it still works with
JavaScript disabled — JS only adds the filter buttons.

Try it:

```bash
# Change "Respond with ONLY valid JSON. No prose, no markdown fence."
#     to "Respond in JSON. Keep it brief."
promptlock check
```

The demo runs entirely offline against a behavioural mock — no API key, no
flaky CI. Point it at a real model with:

```bash
export PROMPTLOCK_PROVIDER=anthropic ANTHROPIC_API_KEY=sk-...
promptlock record && promptlock check
```

## Architecture

```
promptlock.yaml            config: target, cases, thresholds, assertions
.promptlock/baseline.json  the snapshot — committed to git, reviewable in a PR diff

promptlock/
  cli.py          init | record | check
  discover.py     AST walk: finds LLM call sites + prompt constants, scaffolds config
  runner.py       verdict engine: noise floors, confirmation re-runs
  providers.py    mock behavioural simulator + Anthropic
  store.py        baseline snapshot + prompt fingerprint
  stats.py        Wilson score interval — evidence, not a point threshold
  report.py       markdown (PR comment) + console
  htmlreport.py   self-contained HTML report: SVG scatter, filters, char diff
  scorers/
    assertions.py deterministic — schema, keys, enums, regex, latency, cost
    drift.py      hashed char n-gram embeddings, dependency-free
    judge.py      pairwise, position-swapped

examples/demo_app/   support-ticket classifier, 50 cases
scripts/benchmark.py precision/recall vs the naive detector
.github/workflows/   PR check + sticky comment
```

No database. No hosted service. The baseline is a JSON file in your repo, which
means "what did known-good mean here?" is answerable by `git log`.

## Config

```yaml
target: examples.demo_app.app:render   # callable(case_input) -> prompt
cases: examples/demo_app/cases.yaml

runs_per_case: 5          # k — higher k, tighter noise estimate, more spend
drift_floor: 0.12          # absolute lower bound on the per-case threshold
drift_multiplier: 1.5      # how far past its own noise a case may move
suite_drift_threshold: 0.025   # median drift that counts as a distribution shift
systemic_judge_sample: 5       # cases sent to the judge when systemic drift fires
break_confidence: 0.95     # confidence level for the pass-rate interval
break_margin: 0.2          # how far below baseline the upper bound must sit

model_params:              # part of the fingerprint — a swap is a change
  model: claude-sonnet-4-6
  temperature: 0.0
  top_p: 1.0
  max_tokens: 1000
judge_enabled: true
confirm_reruns: true      # re-sample before failing the build

assertions:
  require_json: true
  required_keys: [category, urgency, summary]
  enums:
    category: [billing, bug, feature_request, account, other]
  must_not_match: ["^(sure|here'?s|certainly)"]
  max_latency_ms: 3000
  max_cost_usd: 0.01
```

## Verdicts

- **PASS** — within this case's measured noise.
- **DRIFT** — output moved past its noise floor, but the judge did not find it
  worse. Reported, collapsed, does not fail the build.
- **FAIL** — an assertion the baseline always satisfied now mostly fails, or the
  judge called it worse in both orderings.

## License

MIT
