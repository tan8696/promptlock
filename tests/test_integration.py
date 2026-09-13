"""End-to-end: record a baseline, degrade the prompt, prove the gate fails.

This is the test that would have caught every bug the unit tests cannot see,
because it exercises the actual CLI exit code -- which is the entire contract
between PromptLock and a CI system.
"""

from __future__ import annotations

import contextlib
import importlib
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from promptlock import cli, htmlreport, store  # noqa: E402
from promptlock import report as report_mod
from promptlock.runner import Config, check, record  # noqa: E402

STRICT_LINE = "Respond with ONLY valid JSON. No prose, no markdown fence."

APP = f'''PROMPT = """You are a support triage assistant.
Classify the ticket below. Return category, urgency and a one-line summary.
{STRICT_LINE}

<ticket>
{{ticket}}
</ticket>
"""


def render(case_input):
    return PROMPT.format(ticket=case_input)
'''

CASES = """cases:
- id: t001
  input: i was charged twice for my subscription this month
  expect: {category: billing, urgency: low}
- id: t002
  input: the app crashes immediately on login, this is urgent
  expect: {category: bug, urgency: high}
- id: t003
  input: please add dark mode, it would be nice
  expect: {category: feature_request, urgency: low}
- id: t004
  input: i am locked out of my account and cannot sign in
  expect: {category: account, urgency: high}
- id: t005
  input: my card was declined but i was billed anyway
  expect: {category: billing, urgency: low}
- id: t006
  input: error 500 when saving, the page is broken
  expect: {category: bug, urgency: low}
"""

CONFIG = """target: miniapp:render
cases: cases.yaml
runs_per_case: 3
provider: mock
model_params:
  model: claude-sonnet-4-6
  temperature: 0.0
  max_tokens: 1000
drift_floor: 0.12
drift_multiplier: 1.5
suite_drift_threshold: 0.025
break_confidence: 0.95
break_margin: 0.2
judge_enabled: true
confirm_reruns: true
assertions:
  require_json: true
  required_keys: [category, urgency, summary]
  enums:
    category: [billing, bug, feature_request, account, other]
  must_not_match:
    - "^(sure|here'?s|certainly)"
"""


@contextlib.contextmanager
def _suite():
    """A throwaway repo with its own target module, cases and config."""
    previous = os.getcwd()
    with tempfile.TemporaryDirectory() as root:
        for name, body in (("miniapp.py", APP), ("cases.yaml", CASES),
                           ("promptlock.yaml", CONFIG)):
            with open(os.path.join(root, name), "w", encoding="utf-8") as f:
                f.write(body)
        os.chdir(root)
        sys.modules.pop("miniapp", None)
        importlib.invalidate_caches()
        try:
            yield root
        finally:
            os.chdir(previous)
            sys.modules.pop("miniapp", None)


def _degrade(root: str) -> None:
    """The R3 brevity nudge: drops the format anchor, so prose leaks in."""
    path = os.path.join(root, "miniapp.py")
    with open(path, encoding="utf-8") as f:
        source = f.read()
    assert STRICT_LINE in source
    with open(path, "w", encoding="utf-8") as f:
        f.write(source.replace(STRICT_LINE, "Respond in JSON. Keep it brief."))
    importlib.invalidate_caches()


def test_record_then_check_passes_on_an_unchanged_prompt():
    with _suite():
        assert cli.main(["record"]) == 0
        assert os.path.exists(store.BASELINE_PATH)
        assert cli.main(["check"]) == 0, "nothing changed, so nothing may fail"


def test_degrading_the_prompt_makes_check_exit_1():
    with _suite() as root:
        assert cli.main(["record"]) == 0
        _degrade(root)
        assert cli.main(["check"]) == 1, "a real regression must fail the build"


def test_the_failure_names_the_broken_assertions():
    with _suite() as root:
        cfg = Config.load("promptlock.yaml")
        store.save(record(cfg))
        _degrade(root)

        rep = check(Config.load("promptlock.yaml"), store.load())

    assert rep["summary"]["FAIL"] > 0
    broken = {name for c in rep["cases"].values() for name in c["broken_assertions"]}
    assert broken, "a FAIL must say which assertion broke"
    assert rep["fingerprint_changed"] is True


def test_fail_on_drift_is_stricter_than_fail_on_fail():
    with _suite():
        assert cli.main(["record"]) == 0
        assert cli.main(["check", "--fail-on", "drift"]) == 0


def test_check_writes_every_report_format():
    with _suite() as root:
        cli.main(["record"])
        _degrade(root)
        code = cli.main(["check", "--markdown", "r.md", "--json", "r.json",
                         "--html", "r.html"])
        assert code == 1
        sizes = {name: os.path.getsize(os.path.join(root, name))
                 for name in ("r.md", "r.json", "r.html")}
        with open(os.path.join(root, "r.html"), encoding="utf-8") as f:
            html_text = f.read()

    assert all(size > 0 for size in sizes.values()), sizes
    assert html_text.startswith("<!doctype html>")
    assert "http://" not in html_text and "https://" not in html_text


def test_reports_render_from_a_report_dict():
    with _suite():
        cfg = Config.load("promptlock.yaml")
        store.save(record(cfg))
        rep = check(cfg, store.load())

    markdown = report_mod.markdown(rep)
    console = report_mod.console(rep)
    page = htmlreport.render(rep)

    assert "## PromptLock" in markdown
    assert "pass" in console
    assert page.count('class="row"') == len(rep["cases"])
    assert "<script>" in page and "src=" not in page


def test_html_escapes_model_output():
    """Model output lands in the page. It must never land as markup."""
    rep = {
        "summary": {"PASS": 0, "DRIFT": 0, "FAIL": 1},
        "judge_calls": 0,
        "fingerprint_changed": False,
        "cases": {
            "t001": {
                "verdict": "FAIL", "broken_assertions": ["json_parses"],
                "drift": 0.5, "threshold": 0.12, "noise_floor": 0.0, "judge": None,
                "baseline_sample": "{}",
                "current_sample": "<script>alert('xss')</script>",
                "cost_usd": 0.0,
            }
        },
    }
    page = htmlreport.render(rep)
    assert "<script>alert" not in page
    assert "&lt;script&gt;alert" in page
