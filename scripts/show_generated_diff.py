"""Explain how regenerated output differs from what is committed.

The generated pages are single enormous lines, so `git diff` on them says
nothing useful. This reports the first differing character with context, which
is what you actually need to know.

    python3 scripts/show_generated_diff.py public docs
"""

from __future__ import annotations

import subprocess
import sys

CONTEXT_BEFORE = 90
CONTEXT_AFTER = 70


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    # encoding is explicit: text=True decodes with the locale encoding, which is
    # cp1252 on Windows, and turns every em-dash in these pages into mojibake
    # that then reads as a difference.
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, encoding="utf-8", check=False
    )


def changed_paths(scopes: list[str]) -> list[str]:
    out = _git("diff", "--name-only", "--", *scopes)
    return [p for p in out.stdout.split("\n") if p.strip()]


def committed(path: str) -> str | None:
    out = _git("show", f"HEAD:{path}")
    return out.stdout if out.returncode == 0 else None


def report(path: str) -> None:
    old = committed(path)
    if old is None:
        print(f"::error::{path} is not in HEAD (new file)")
        return

    with open(path, encoding="utf-8") as f:
        new = f.read()

    if old == new:
        return

    index = next(
        # strict=False on purpose: unequal lengths are exactly the case the
        # fallback below reports.
        (i for i, (a, b) in enumerate(zip(old, new, strict=False)) if a != b),
        min(len(old), len(new)),
    )
    start = max(0, index - CONTEXT_BEFORE)
    print(f"::error::{path}: first differs at char {index} "
          f"(committed {len(old)} chars, built {len(new)})")
    print(f"::error::  committed: {old[start:index + CONTEXT_AFTER]!r}")
    print(f"::error::  built:     {new[start:index + CONTEXT_AFTER]!r}")


def main(argv: list[str]) -> int:
    scopes = argv[1:] or ["public", "docs"]
    paths = changed_paths(scopes)
    if not paths:
        print("no differences")
        return 0
    for path in paths:
        report(path)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
