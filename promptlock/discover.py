"""Auto-discovery: find LLM call sites and prompt templates by reading the AST.

Answers the first question every new user has -- "what do I even put in
cases.yaml?" -- from the source instead of from the user. Static only: nothing
is imported or executed, so scanning an unfamiliar repo is safe.
"""

from __future__ import annotations

import ast
import difflib
import os
import re
from dataclasses import dataclass

SKIP_DIRS = {
    ".git", ".venv", "venv", "env", "node_modules", "tests", "test",
    "__pycache__", ".promptlock", "build", "dist", ".tox", ".mypy_cache",
    "site-packages", ".eggs",
}

# A module-level string is a prompt if it is named like one, or if it looks
# like a format template that is too long to be an incidental literal.
NAME_RE = re.compile(r"PROMPT|TEMPLATE|SYSTEM", re.I)
MIN_TEMPLATE_LEN = 120

CONSTANT = "constant"


@dataclass
class Hit:
    path: str
    line: int
    function: str | None
    kind: str
    name: str
    model: str | None = None
    template: str | None = None

    @property
    def site(self) -> str:
        where = f"{self.path}:{self.line}"
        return f"{where} ({self.function})" if self.function else where


# ---------------------------------------------------------------------------
# AST plumbing
# ---------------------------------------------------------------------------

def _dotted(node: ast.AST) -> str:
    """'client.messages.create' from the attribute chain; '' if not a name/attr."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    elif isinstance(node, ast.Call):
        parts.append("()")  # anthropic.Anthropic().messages.create
    else:
        return ""
    return ".".join(reversed(parts))


def _call_kind(dotted: str) -> str | None:
    parts = dotted.split(".")
    if parts[-3:] == ["chat", "completions", "create"]:
        return "chat.completions.create"
    if parts[-2:] == ["messages", "create"]:
        return "messages.create"
    if parts[-1] == "complete":
        return "complete"
    return None


def _literal_kwarg(node: ast.Call, name: str) -> str | None:
    for kw in node.keywords:
        if kw.arg == name and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return None


def _module_constants(tree: ast.Module) -> dict[str, tuple[str, int]]:
    """Module-level `NAME = "..."` only. Nothing is evaluated."""
    out: dict[str, tuple[str, int]] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets, value = [node.target], node.value
        else:
            continue
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            for t in targets:
                out[t.id] = (value.value, node.lineno)
    return out


class _Visitor(ast.NodeVisitor):
    def __init__(self, path: str, consts: dict[str, tuple[str, int]]):
        self.path = path
        self.consts = consts
        self.stack: list[str] = []
        self.hits: list[Hit] = []

    def visit_FunctionDef(self, node):  # noqa: N802
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node):  # noqa: N802
        dotted = _dotted(node.func)
        kind = _call_kind(dotted) if dotted else None
        if kind:
            self.hits.append(
                Hit(
                    path=self.path,
                    line=node.lineno,
                    function=self.stack[-1] if self.stack else None,
                    kind=kind,
                    name=dotted,
                    model=_literal_kwarg(node, "model"),
                    template=self._template(node),
                )
            )
        self.generic_visit(node)

    # -- template resolution ------------------------------------------------

    def _resolve(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            found = self.consts.get(node.id)
            return found[0] if found else None
        if isinstance(node, ast.Attribute):  # prompts.SYSTEM
            found = self.consts.get(node.attr)
            return found[0] if found else None
        if isinstance(node, ast.Call):  # PROMPT.format(...)
            return self._resolve(node.func.value) if isinstance(node.func, ast.Attribute) else None
        return None

    def _from_messages(self, node: ast.AST) -> str | None:
        if not isinstance(node, ast.List):
            return self._resolve(node)
        for el in node.elts:
            if not isinstance(el, ast.Dict):
                continue
            for k, v in zip(el.keys, el.values):
                if isinstance(k, ast.Constant) and k.value == "content":
                    if found := self._resolve(v):
                        return found
        return None

    def _template(self, node: ast.Call) -> str | None:
        for kw in node.keywords:
            if kw.arg == "messages":
                if found := self._from_messages(kw.value):
                    return found
            elif kw.arg in ("prompt", "system", "input"):
                if found := self._resolve(kw.value):
                    return found
        for arg in node.args:
            if found := self._resolve(arg):
                return found
        return None


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

def iter_py_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in sorted(filenames):
            if fn.endswith(".py"):
                # Forward slashes everywhere: these paths land in generated YAML.
                yield os.path.join(dirpath, fn).replace(os.sep, "/").removeprefix("./")


def scan_file(path: str) -> list[Hit]:
    try:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=path)
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []  # unparseable third-party source is skipped, not fatal

    consts = _module_constants(tree)
    visitor = _Visitor(path, consts)
    visitor.visit(tree)

    hits = list(visitor.hits)
    for name, (value, line) in consts.items():
        if NAME_RE.search(name) or ("{" in value and len(value) > MIN_TEMPLATE_LEN):
            hits.append(Hit(path, line, None, CONSTANT, name, template=value))
    return sorted(hits, key=lambda h: (h.line, h.name))


def discover(root: str = ".") -> list[Hit]:
    hits: list[Hit] = []
    for path in iter_py_files(root):
        hits += scan_file(path)
    return sorted(hits, key=lambda h: (h.path, h.line))


# ---------------------------------------------------------------------------
# Scaffolding
# ---------------------------------------------------------------------------

def _module_of(path: str, root: str) -> str:
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    if rel.endswith(".py"):
        rel = rel[: -len(".py")]
    return rel.replace("/", ".")


def _guess_target(hits: list[Hit], root: str) -> str:
    for h in hits:
        if h.function:
            return f"{_module_of(h.path, root)}:{h.function}"
    return "TODO.your_module:render"


def _case_id(hit: Hit, n: int) -> str:
    stem = os.path.basename(hit.path)[: -len(".py")]
    return f"{stem}_{hit.line}_{n}"


def render_config(hits: list[Hit], root: str, cases_path: str) -> str:
    target = _guess_target(hits, root)
    return f"""# Generated by `promptlock init` from {len(hits)} discovered site(s).
# TODO: `target` must be a callable(case_input) -> prompt. init guesses the
# function enclosing the first call site; that is often the function that calls
# the model, not the one that renders the prompt. Point it at the renderer.
target: {target}
cases: {cases_path}

runs_per_case: 3
provider: mock

drift_floor: 0.12
drift_multiplier: 1.5

# TODO: calibrate against your own suite -- `python3 scripts/calibrate.py`.
suite_drift_threshold: 0.025
systemic_judge_sample: 5

judge_enabled: true
confirm_reruns: true

assertions:
  require_json: true
  # TODO: list the keys your output must carry.
  required_keys: []
"""


def render_cases(hits: list[Hit]) -> str:
    out = [
        "# Generated by `promptlock init`. Every case below is a placeholder --",
        "# replace each TODO with a real input before recording a baseline.",
        "cases:",
    ]
    if not hits:
        out += ["  # No call sites discovered. Add cases by hand.", "  []"]
        return "\n".join(out) + "\n"

    for hit in hits:
        model = f" model={hit.model}" if hit.model else ""
        out.append(f"\n  # {hit.site} -- {hit.kind}{model}")
        for n in (1, 2, 3):
            out += [
                f"  - id: {_case_id(hit, n)}",
                f"    # TODO: a representative input for this call site ({n} of 3)",
                '    input: "TODO"',
                "    expect: {}",
            ]
    return "\n".join(out) + "\n"


def _write(path: str, text: str) -> tuple[str, str | None]:
    """Write `text`, never clobbering an existing file. Returns (path, diff)."""
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path, None

    new_path = path + ".new"
    with open(new_path, "w", encoding="utf-8") as f:
        f.write(text)
    with open(path, encoding="utf-8") as f:
        old = f.read()
    diff = "".join(
        difflib.unified_diff(
            old.splitlines(True), text.splitlines(True), fromfile=path, tofile=new_path
        )
    )
    return new_path, diff


def table(hits: list[Hit]) -> str:
    if not hits:
        return "No LLM call sites or prompt constants found."
    rows = [f"{'site':<44}{'kind':<26}{'model':<22}template"]
    rows.append("-" * 108)
    for h in hits:
        tmpl = (h.template or "").replace("\n", " ")
        tmpl = tmpl[:29] + "..." if len(tmpl) > 32 else tmpl
        label = h.name if h.kind == CONSTANT else h.kind
        rows.append(f"{h.site[:43]:<44}{label[:25]:<26}{(h.model or '-')[:21]:<22}{tmpl or '-'}")
    return "\n".join(rows)


def init(root: str = ".", dry_run: bool = False, config_path: str = "promptlock.yaml") -> int:
    hits = discover(root)
    print(table(hits))
    print(f"\n{len(hits)} site(s) across {len({h.path for h in hits})} file(s).")

    if dry_run:
        print("\n--dry-run: nothing written.")
        return 0

    cases_path = os.path.join(os.path.dirname(config_path) or ".", "cases.yaml")
    cases_rel = os.path.relpath(cases_path, os.path.dirname(config_path) or ".").replace(os.sep, "/")

    written = []
    for path, text in (
        (cases_path, render_cases(hits)),
        (config_path, render_config(hits, root, cases_rel)),
    ):
        out_path, diff = _write(path, text)
        written.append(out_path)
        if diff is None:
            print(f"\nwrote {out_path}")
        else:
            print(f"\n{path} already exists -- wrote {out_path} instead. Diff:\n")
            print(diff or "  (identical)")

    print("\nNext: replace the TODOs, then `promptlock record`.")
    return 0
