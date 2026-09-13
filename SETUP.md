# Setup (read this first)

## 1. Unzip and enter the folder

```bash
unzip promptlock.zip
cd promptlock          # <- you must be INSIDE this folder for anything to work
ls                     # you should see: README.md  promptlock.yaml  pyproject.toml
```

If `ls` shows another `promptlock` folder instead of `README.md`, go one level
deeper: `cd promptlock`.

## 2. Verify it runs

```bash
bash bootstrap.sh
```

Expected final lines:

```
50 pass · 0 drift · 0 fail
```

`bootstrap.sh` installs the package, regenerates the 50 demo cases, records a
baseline, and runs a check. It is safe to run more than once.

## 3. Start Claude Code

```bash
cd promptlock     # the folder containing README.md and promptlock.yaml
claude
```

Claude Code reads the directory you launch it from. If it says it cannot find
the project, you launched it from the wrong directory — run `pwd` and confirm
the path ends in `/promptlock` and `ls` shows `README.md`.

## Troubleshooting

**`promptlock: command not found`**
The console-script did not land on PATH. Use the module form instead — it always
works, and works from a plain `git clone` with no install:

```bash
python3 -m promptlock.cli record
python3 -m promptlock.cli check
```

**`No baseline at .promptlock/baseline.json`**
Some unzip tools silently drop dot-directories. Just regenerate it:

```bash
python3 -m promptlock.cli record
```

**`ModuleNotFoundError: No module named 'promptlock'`**
You are not in the project root. `cd` to the folder containing `pyproject.toml`.

**`ModuleNotFoundError: No module named 'yaml'`**
```bash
pip install PyYAML --break-system-packages
```

**`error: externally-managed-environment`**
Add `--break-system-packages` to the pip command, or use a venv:
```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -e .
```
