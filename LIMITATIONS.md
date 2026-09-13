# Limitations

Written honestly, because a tool that claims to measure regressions should be
able to state where its own measurements stop being trustworthy.

## Known false positive: `H10 reorder-tail`

Reordering two clauses in the format instruction (`"No prose, no markdown
fence."` → `"No markdown fence, no prose."`) fires on 3 of 50 cases. The edit is
semantically null, but it reshuffles sampling, and three cases happened to land
on the format-leak branch twice in a row — surviving the confirmation re-run.

Fixes, in order of effort: raise `runs_per_case` to 5 (the flake estimate is
currently built from 3 samples, which is thin); or require a *confidence
interval* on the pass-rate rather than a point threshold. Neither was in scope
for this build.

## The embedding is a hashed char n-gram, not a real embedding

`scorers/drift.py` ships a dependency-free bag-of-4-grams vector so `check` runs
offline in CI with no embedding API. Consequences:

- Paraphrase is scored as drift. "The ticket is a billing issue" and "This is
  about billing" look far apart.
- It is character-level, so it is sensitive to formatting and near-blind to
  meaning.

For semantic work, swap `embed()` for a real embedding model. The interface is
one function.

## The mock provider is a simulator, not a model

The offline demo uses a behavioural mock that reads the prompt and changes
format/labels the way a real model plausibly would: strict format instructions
produce bare JSON, loose ones leak prose and markdown fences, hedging
instructions push it toward the catch-all label, and every call carries seeded
run-to-run noise.

This makes the demo reproducible and free, and it exercises every code path.
It is **not** evidence about any real model's behaviour. The benchmark numbers
measure *the detector*, not the model. Run `PROMPTLOCK_PROVIDER=anthropic` for
real behaviour.

## The mock judge is a rubric proxy

Offline, `MockJudge` grades on parseability plus agreement with each case's
`expect.category` and `expect.urgency` labels. Those labels are rule-generated
in `scripts/gen_cases.py`, standing in for the one-off human labelling you would
do when building a real suite — so the offline benchmark is measuring the
detector against known-good labels, not against itself.

It does not grade summary quality. The real judge
(`scorers/judge.py:compare`) has no such gap — it is the position-swapped
rubric prompt, and it activates automatically when a real provider is configured.

## Discovery is static, and the guessed target usually needs correcting

`promptlock init` walks the AST (`promptlock/discover.py`); it never imports or
executes your code, so it is safe to point at an unfamiliar repo. The cost of
that safety:

- **Runtime-assembled prompts are invisible.** A template resolves only if it is
  a module-level string constant or a literal at the call site. Prompts built by
  concatenation, f-strings, config loads, or a database read show as `-`.
- **The scaffolded `target:` is a guess.** init names the function *enclosing*
  the first call site, which is usually the function that calls the model, not
  the `callable(case_input) -> prompt` renderer the config wants. The generated
  file says so in a TODO, but it will not run until a human fixes it.
- **`.complete(` is matched by name alone**, so unrelated methods with that name
  are reported as call sites.

Discovery scaffolds a starting point. It does not produce a runnable suite.

## Python only

The CLI imports your prompt-rendering function directly, so the target has to be
Python. A language-agnostic version would shell out to a subprocess contract
(stdin: case JSON → stdout: prompt) instead. Not built.

## The suite threshold is calibrated on one suite

`suite_drift_threshold: 0.025` sits in the gap between the harmless-edit median
(≤0.019) and the behavioural-edit median (≥0.031) measured on *this* 50-case
suite with *this* mock. It is not a universal constant. Run
`python3 scripts/calibrate.py` against your own suite before trusting the
default; the honest version of this feature auto-calibrates on `record` and that
is not built.

## Statistical caveats

- `k=3` is too few samples to estimate a variance well. It is a default chosen
  for CI cost, not for statistical power.
- `BREAK_RATE = 0.5` (an assertion is broken if it fails in a majority of runs)
  is a threshold, not a hypothesis test. With k=3 it means "2 of 3".
- The noise floor is measured once, at record time. A model that gets noisier
  over time will not be re-profiled until you re-record.

## Not handled

Multi-turn conversations, tool-calling traces, streaming outputs, image inputs,
per-case cost budgets, and baseline merge conflicts when two PRs both re-record.
