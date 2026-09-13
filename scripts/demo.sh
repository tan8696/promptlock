#!/usr/bin/env bash
# 90-second demo. Safe on a clean clone or an unzipped download.
#
# No git dependency: the prompt is restored from a copy by an EXIT trap, so it
# comes back even if you Ctrl-C halfway through a recording.
#
#   bash scripts/demo.sh          # pauses sized for screen recording
#   BEAT=0 bash scripts/demo.sh   # no pauses, for a quick sanity run

set -euo pipefail
cd "$(dirname "$0")/.."

APP="examples/demo_app/app.py"
BACKUP="$(mktemp)"
cp "$APP" "$BACKUP"
restore() { cp "$BACKUP" "$APP"; rm -f "$BACKUP"; }
trap restore EXIT INT TERM

BEAT="${BEAT:-3}"
say() { printf "\n\033[1;35m▸ %s\033[0m\n\n" "$1"; sleep "$BEAT"; }

# The console script is not on PATH in every environment; the module always is.
PL="promptlock"
command -v promptlock >/dev/null 2>&1 || PL="python3 -m promptlock.cli"

# ---------------------------------------------------------------------------

say "1/6  Install"
pip install -e . -q --break-system-packages 2>/dev/null || pip install -e . -q

say "2/6  Snapshot known-good behaviour"
$PL record

say "3/6  Nothing changed, so nothing fails"
$PL check | tail -2

say "4/6  A four-word prompt edit that looks harmless in review"
python3 - <<'PY'
path = "examples/demo_app/app.py"
old = "Respond with ONLY valid JSON. No prose, no markdown fence."
new = "Respond in JSON. Keep it brief."
with open(path, encoding="utf-8") as f:
    source = f.read()
assert old in source, "demo anchor not found"
with open(path, "w", encoding="utf-8") as f:
    f.write(source.replace(old, new, 1))
print(f"  - {old}\n  + {new}")
PY

say "5/6  CI catches it"
$PL check --markdown report.md | tail -3 || true
printf '\n'
# Print the regressions table itself: the heading is followed by a blank line,
# so a sed range would stop before the rows. awk keeps only the table lines.
awk '/^### Regressions/ {f = 1; next} f && /^\|/ {print; if (++n >= 5) exit}' report.md

say "6/6  A report you can open in a browser"
$PL check --html report.html >/dev/null || true
printf '  wrote report.html (%s bytes) — self-contained, opens from file://\n' \
  "$(wc -c < report.html | tr -d ' ')"

say "Restoring the prompt"
# the EXIT trap does the work; this line is just the narration
