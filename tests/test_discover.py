"""Tests for promptlock.discover.

Runs under pytest, or standalone: `python3 tests/test_discover.py`.
"""

from __future__ import annotations

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from promptlock import discover  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures")


def _fixture(name: str) -> str:
    return os.path.join(FIXTURES, name + ".py")


def _one(hits, kind):
    matches = [h for h in hits if h.kind == kind]
    assert len(matches) == 1, f"expected exactly one {kind}, got {len(matches)}"
    return matches[0]


def test_openai_style_call():
    hits = discover.scan_file(_fixture("openai_style"))
    call = _one(hits, "chat.completions.create")
    assert call.function == "summarise"
    assert call.model == "gpt-4o-mini"
    assert "<ticket>" in call.template, "template should resolve through PROMPT.format(...)"
    assert call.line > 0


def test_anthropic_style_call():
    hits = discover.scan_file(_fixture("anthropic_style"))
    call = _one(hits, "messages.create")
    assert call.function == "classify"
    assert call.model == "claude-sonnet-4-6"
    assert "triage assistant" in call.template


def test_constant_without_call_site():
    hits = discover.scan_file(_fixture("constant_only"))
    assert all(h.kind == discover.CONSTANT for h in hits), "no call sites in this fixture"

    names = {h.name for h in hits}
    assert "RERANK_TEMPLATE" in names, "name matches /TEMPLATE/"
    assert "GUIDANCE" in names, "long string with {placeholders}"
    assert "LABEL" not in names and "MAX_DOCS" not in names, "must not match short/non-str"


def test_file_with_zero_hits():
    assert discover.scan_file(_fixture("nothing")) == []


def test_enclosing_function_is_none_for_module_constants():
    hits = discover.scan_file(_fixture("constant_only"))
    assert all(h.function is None for h in hits)


def test_discover_walks_a_directory():
    hits = discover.discover(FIXTURES)
    paths = {os.path.basename(h.path) for h in hits}
    assert {"openai_style.py", "anthropic_style.py", "constant_only.py"} <= paths
    assert "nothing.py" not in paths
    assert hits == sorted(hits, key=lambda h: (h.path, h.line))


def test_skip_dirs_are_not_walked():
    with tempfile.TemporaryDirectory() as root:
        for d in ("node_modules", ".venv", "tests", "src"):
            os.makedirs(os.path.join(root, d))
            with open(os.path.join(root, d, "m.py"), "w", encoding="utf-8") as f:
                f.write("X = 1\n")
        found = {os.path.basename(os.path.dirname(p)) for p in discover.iter_py_files(root)}
    assert found == {"src"}


def test_never_overwrites_an_existing_config():
    with tempfile.TemporaryDirectory() as root:
        path = os.path.join(root, "promptlock.yaml")
        with open(path, "w", encoding="utf-8") as f:
            f.write("target: mine:render\n")

        out, diff = discover._write(path, "target: generated:render\n")

        assert out == path + ".new", "must not clobber the existing file"
        assert os.path.exists(out)
        with open(path, encoding="utf-8") as f:
            assert f.read() == "target: mine:render\n", "original left untouched"
        assert "mine:render" in diff and "generated:render" in diff


def test_writes_directly_when_no_config_exists():
    with tempfile.TemporaryDirectory() as root:
        path = os.path.join(root, "promptlock.yaml")
        out, diff = discover._write(path, "target: generated:render\n")
    assert out == path and diff is None


def test_cases_stub_has_three_todo_cases_per_site():
    hits = discover.discover(FIXTURES)
    text = discover.render_cases(hits)
    assert text.count("- id: ") == 3 * len(hits)
    assert text.count("# TODO:") == 3 * len(hits)
    assert "cases:" in text


def test_config_scaffold_targets_a_discovered_function():
    hits = discover.discover(FIXTURES)
    text = discover.render_config(hits, FIXTURES, "cases.yaml")
    assert "cases: cases.yaml" in text
    assert "target: " in text and "TODO" in text


def test_empty_repo_still_scaffolds():
    text = discover.render_cases([])
    assert "cases:" in text and "No call sites discovered" in text


def test_init_dry_run_writes_nothing(capsys):
    with tempfile.TemporaryDirectory() as root:
        config = os.path.join(root, "promptlock.yaml")
        assert discover.init(FIXTURES, dry_run=True, config_path=config) == 0
        assert os.listdir(root) == [], "--dry-run must not write"
    out = capsys.readouterr().out
    assert "site(s)" in out and "nothing written" in out


def test_init_scaffolds_config_and_cases(capsys):
    with tempfile.TemporaryDirectory() as root:
        config = os.path.join(root, "promptlock.yaml")
        assert discover.init(FIXTURES, dry_run=False, config_path=config) == 0
        written = sorted(os.listdir(root))
        with open(config, encoding="utf-8") as f:
            body = f.read()
    assert written == ["cases.yaml", "promptlock.yaml"]
    assert "cases: cases.yaml" in body
    assert "site(s)" in capsys.readouterr().out


def test_init_refuses_to_clobber_and_prints_a_diff(capsys):
    with tempfile.TemporaryDirectory() as root:
        config = os.path.join(root, "promptlock.yaml")
        with open(config, encoding="utf-8", mode="w") as f:
            f.write("target: mine:render\n")

        discover.init(FIXTURES, dry_run=False, config_path=config)

        with open(config, encoding="utf-8") as f:
            assert f.read() == "target: mine:render\n", "original must survive"
        assert os.path.exists(config + ".new")
    assert "already exists" in capsys.readouterr().out


def test_table_on_no_hits():
    assert "No LLM call sites" in discover.table([])


def test_unparseable_source_is_skipped_not_fatal():
    with tempfile.TemporaryDirectory() as root:
        broken = os.path.join(root, "broken.py")
        with open(broken, "w", encoding="utf-8") as f:
            f.write("def (((( oops\n")
        assert discover.scan_file(broken) == []


if __name__ == "__main__":
    import inspect

    # Tests taking a pytest fixture (capsys) need pytest; skip them standalone.
    tests = [
        (n, f) for n, f in sorted(globals().items())
        if n.startswith("test_") and callable(f) and not inspect.signature(f).parameters
    ]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"  pass  {name}")
        except AssertionError as e:
            failed.append(name)
            print(f"  FAIL  {name}: {e}")
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
