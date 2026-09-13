from __future__ import annotations

import argparse
import json
import sys

from . import report as report_mod
from . import store
from .runner import Config, check, record


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="promptlock", description="CI for prompts.")
    p.add_argument("-c", "--config", default="promptlock.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("record", help="snapshot current outputs as the known-good baseline")

    chk = sub.add_parser("check", help="compare current outputs against the baseline")
    chk.add_argument("--markdown", metavar="PATH", help="write a PR-ready markdown report")
    chk.add_argument("--json", metavar="PATH", help="write the raw report")
    chk.add_argument("--fail-on", choices=["fail", "drift"], default="fail")

    args = p.parse_args(argv)
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
        with open(args.markdown, "w") as f:
            f.write(report_mod.markdown(rep))
    if args.json:
        with open(args.json, "w") as f:
            json.dump(rep, f, indent=2)

    bad = rep["summary"]["FAIL"]
    if args.fail_on == "drift":
        bad += rep["summary"]["DRIFT"]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
