from __future__ import annotations

import argparse
import json
import sys

from . import discover as discover_mod
from . import htmlreport
from . import report as report_mod
from . import store
from .runner import Config, check, record


def main(argv=None) -> int:
    # Windows consoles default to cp1252, which cannot encode the report glyphs.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    p = argparse.ArgumentParser(prog="promptlock", description="CI for prompts.")
    p.add_argument("-c", "--config", default="promptlock.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)

    ini = sub.add_parser("init", help="scan the repo for LLM call sites and scaffold a config")
    ini.add_argument("--root", default=".", help="directory to scan (default: .)")
    ini.add_argument("--dry-run", action="store_true", help="print what was found, write nothing")

    sub.add_parser("record", help="snapshot current outputs as the known-good baseline")

    chk = sub.add_parser("check", help="compare current outputs against the baseline")
    chk.add_argument("--markdown", metavar="PATH", help="write a PR-ready markdown report")
    chk.add_argument("--html", metavar="PATH", help="write a self-contained HTML report")
    chk.add_argument("--json", metavar="PATH", help="write the raw report")
    chk.add_argument("--fail-on", choices=["fail", "drift"], default="fail")

    args = p.parse_args(argv)

    # init runs before any config exists, so it must not load one.
    if args.cmd == "init":
        return discover_mod.init(args.root, dry_run=args.dry_run, config_path=args.config)

    cfg = Config.load(args.config)

    if args.cmd == "record":
        snap = record(cfg)
        store.save(snap)
        n = len(snap["cases"])
        noisy = sum(1 for c in snap["cases"].values() if c["noise_floor"] > 0.05)
        print(f"Recorded {n} cases × {cfg.runs_per_case} runs → {store.BASELINE_PATH}")
        print(f"{noisy} case(s) measured as naturally noisy; thresholds widened for those.")
        return 0

    rep = check(cfg, store.load())
    print(report_mod.console(rep))

    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8") as f:
            f.write(report_mod.markdown(rep))
    if args.html:
        with open(args.html, "w", encoding="utf-8") as f:
            f.write(htmlreport.render(rep))
    if args.json:
        with open(args.json, "w") as f:
            json.dump(rep, f, indent=2)

    bad = rep["summary"]["FAIL"]
    if args.fail_on == "drift":
        bad += rep["summary"]["DRIFT"]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
