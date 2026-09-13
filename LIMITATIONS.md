# Limitations

Written honestly, because a tool that claims to measure regressions should be
able to state where its own measurements stop being trustworthy.

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

The model-tier simulation is the crudest part of it. A model id containing
`haiku` or `mini` gets a higher format-leak rate and a lower evidence bar before
it commits to a label. Those are plausible failure modes, not measured ones —
no claim is being made that any real cheap model behaves this way. Likewise
`PRICE_BY_MODEL` is rough public list pricing hardcoded in `providers.py`, so
the cost delta in the PR comment is indicative, not an invoice.

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

- Breaking an assertion is now a hypothesis test — the 95% Wilson upper bound on
  the new pass-rate must sit `break_margin` below the baseline rate
  (`promptlock/stats.py`). That fixed the `H10 reorder-tail` false positive, but
  it buys evidence with samples: at `k=5` plus confirmation re-runs a real break
  is judged on 10 runs, and the demo suite costs 250 calls to record instead
  of 150.
- **The drift side is still a point threshold.** Only assertions got the
  interval treatment. `drift > max(drift_floor, noise_floor × multiplier)` is
  the same single-number comparison it always was.
- Wilson assumes independent Bernoulli draws. Runs of one case against one
  provider are close enough to that in practice, but correlated failures (a
  provider having a bad minute) violate it and will read as a confident break.
- The noise floor is measured once, at record time. A model that gets noisier
  over time will not be re-profiled until you re-record.

## Not handled

Multi-turn conversations, tool-calling traces, streaming outputs, image inputs,
per-case cost budgets, and baseline merge conflicts when two PRs both re-record.
