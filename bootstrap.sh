#!/usr/bin/env bash
# Verifies a fresh clone/unzip actually works. Safe to re-run.
set -e
cd "$(dirname "$0")"

echo "▸ Python: $(python3 --version)"

python3 -c "import yaml" 2>/dev/null || pip install PyYAML --break-system-packages -q

pip install -e . -q --break-system-packages 2>/dev/null \
  || pip install -e . -q \
  || echo "  (editable install skipped — using 'python3 -m promptlock.cli' instead)"

PL="python3 -m promptlock.cli"

echo "▸ Regenerating demo cases"
python3 scripts/gen_cases.py

echo "▸ Recording baseline"
$PL record

echo "▸ Checking (expect all pass)"
$PL check | tail -3

echo
echo "▸ Done. Next:"
echo "    $PL check --markdown report.md"
echo "    python3 scripts/benchmark.py"
