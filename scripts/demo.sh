#!/usr/bin/env bash
# 90-second demo. Run from the repo root.
set -e
say() { printf "\n\033[1;35m▸ %s\033[0m\n" "$1"; sleep 1; }

say "1. Snapshot known-good behaviour"
promptlock record

say "2. No changes yet — the suite holds"
promptlock check | tail -3

say "3. A four-word prompt edit that looks harmless"
python3 - <<'PY'
p = "examples/demo_app/app.py"
s = open(p).read()
open(p, "w").write(s.replace(
    "Respond with ONLY valid JSON. No prose, no markdown fence.",
    "Respond in JSON. Keep it brief."))
PY
git --no-pager diff --stat examples/demo_app/app.py 2>/dev/null || true

say "4. CI catches it"
promptlock check || true

say "5. Restore"
git checkout examples/demo_app/app.py 2>/dev/null || true
