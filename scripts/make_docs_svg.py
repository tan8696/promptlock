"""Render docs/drift-scatter.svg from a real check, for the README.

The report's chart is styled by the page stylesheet, which a standalone .svg
served by GitHub does not get. So the class names are swapped for inline style
attributes here -- inline styles survive GitHub's SVG sanitiser, a <style>
block is not guaranteed to.

    python3 scripts/make_docs_svg.py
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import replace

sys.path.insert(0, os.getcwd())

from promptlock import htmlreport, store  # noqa: E402
from promptlock.runner import Config, check  # noqa: E402

OUT = "docs/drift-scatter.svg"

# Mid-tone values: GitHub serves the same file to light and dark readers, so
# nothing here may rely on the background being one or the other.
STYLES = {
    "grid": "stroke:#9aa4b0;stroke-width:1;stroke-opacity:.35",
    "axis": "stroke:#9aa4b0",
    "tick": "stroke:#8b95a1;stroke-width:1.5",
    "median": "stroke:#b7791f;stroke-width:1;stroke-dasharray:5 4",
    "lbl": "fill:#77818d;font-size:10px;font-family:sans-serif",
    "dot PASS": "fill:#1a7f5a;fill-opacity:.9",
    "dot DRIFT": "fill:#b7791f;fill-opacity:.9",
    "dot FAIL": "fill:#c02b2b;fill-opacity:.9",
}


def main() -> int:
    cfg = Config.load("promptlock.yaml")
    baseline = store.load()
    # The model swap: a spread of pass, drift and fail worth looking at.
    variant = replace(cfg, model_params={**cfg.model_params, "model": "claude-haiku-4-5"})
    report = check(variant, baseline)

    svg = htmlreport._scatter(report["cases"], report.get("suite_drift"))
    svg = re.sub(
        r'class="([^"]+)"',
        lambda m: f'style="{STYLES.get(m.group(1), "")}"',
        svg,
    )
    # Inline in HTML the parser supplies this; a standalone .svg file must
    # declare it or browsers render the XML tree instead of the picture.
    svg = svg.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(svg)

    summary = report["summary"]
    print(f"wrote {OUT} ({os.path.getsize(OUT)} bytes) from a real check: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
