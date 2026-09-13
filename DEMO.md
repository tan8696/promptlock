# Recording the 90-second demo

`scripts/demo.sh` is the script. This file is how to record it.

## Setup

| Setting | Value | Why |
|---|---|---|
| Terminal size | **100 × 30** | The widest output line (the regressions table) is 96 chars. Narrower wraps and looks broken on video. |
| Font size | **16 pt** | Readable in an embedded Devpost player at 720p. 14 is too small once the video is scaled. |
| Font | Any mono — Cascadia Mono, Menlo, JetBrains Mono | — |
| Theme | Dark background, high contrast | The `▸` beat headers are magenta; they need to pop. |
| Shell | `bash` | The script is bash. On Windows use Git Bash. |

Start from a clean checkout so beat 1 shows a real install:

```bash
git clean -n          # check nothing precious is about to go
rm -rf .promptlock report.html report.md
```

Record with:

```bash
BEAT=12 bash scripts/demo.sh
```

`BEAT` is the pause after each beat header. The commands themselves take about
9 seconds total — 12-second pauses are what carry the runtime to ~88 seconds,
and they are the window you speak in.

## The six beats

Spoken lines are written to be read in the pause, at a normal ~2.5 words per
second. Do not rush them; the pause is sized for the line.

---

**Beat 1 — Install** (~10s)

> On screen: `pip install -e .`

"PromptLock is a CLI and a GitHub Action. No account, no API key, no hosted
service. It installs into the repo it's testing."

---

**Beat 2 — Record the baseline** (~12s)

> On screen: `Recorded 50 cases × 5 runs → .promptlock/baseline.json`
> `2 case(s) measured as naturally noisy; thresholds widened for those.`

"It runs every case five times and stores how much each one naturally wobbles.
That second line is the whole idea — two cases are flaky, so they get a wider
threshold than the rest."

---

**Beat 3 — Nothing changed, so nothing fails** (~12s)

> On screen: `50 pass · 0 drift · 0 fail`

"Run it again with no changes and it's silent. That matters more than it
sounds — a tool that cries wolf on an unchanged prompt gets switched off in a
week."

---

**Beat 4 — The edit** (~15s)

> On screen: the minus/plus diff of the four-word change

"Here's the change. 'Respond with only valid JSON, no prose' becomes 'respond
in JSON, keep it brief.' Four words. It'll sail through code review — there is
nothing in that diff a reviewer can object to."

---

**Beat 5 — CI catches it** (~23s)

> On screen: `0 pass · 0 drift · 50 fail`, then the regressions table

"Fifty of fifty cases regressed. The model dropped the summary field entirely
and started leaking prose in front of the JSON. And it tells you which
assertion broke on which case, with the before and after — so you're not
guessing what the four words did. This exits non-zero, so the build fails."

---

**Beat 6 — The report** (~18s)

> On screen: `wrote report.html (66032 bytes)` — then cut to the open file

"And a single self-contained HTML file. No CDN, no dependencies. A drift
scatter with every case's own threshold drawn beside it, filters, and a
character-level diff. It opens straight from disk."

---

## In the editor

- **Cut the pip install output.** Keep the command, drop the wall of text.
- **Hold on beat 5's table for a full 3 seconds** after it lands. It is the
  payoff shot and people need time to read one row.
- **Cut to `report.html` in a browser for beat 6** rather than filming the byte
  count. Scroll the scatter, click one Fail row so the diff opens. That is the
  most persuasive four seconds in the video.
- Total should land at 85–92 seconds. If you are over, tighten beat 1.

## If you want the numbers on screen instead

```bash
python3 scripts/benchmark.py
```

Nineteen variants in about 7 seconds. Worth its own short recording, or a still
of the final table — but it is too dense to read inside the 90-second cut.
