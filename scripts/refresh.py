#!/usr/bin/env python3
"""Rebuild everything that is generated, then prove it still holds together.

WHAT THIS IS. One entry point for the whole project, so nothing generated
drifts from its source. It regenerates the runtime documentation, the
inventory, and every installable form of the skills, refreshes the code
index, runs both test suites, and checks the house rules that no test can
see.

WHY IT ENDS WITH CHECKS RATHER THAN STARTING WITH THEM. A refresh that
rewrites files and reports success without running the tests is worse than
no refresh: it hands you a package that was never executed. Every stage
records its own result and the exit code reflects all of them, so a green
line is not printed while something below it is red.

    python3 scripts/refresh.py            everything
    python3 scripts/refresh.py --fast     skip the test suites
    python3 scripts/refresh.py --no-index skip the code index

Stages, in order, because each depends on the one before:

  docs      AGENTS.md and GEMINI.md, from the skills
  inventory docs/INVENTORY.md, from the source
  package   dist/, plugin/, .claude-plugin/, from the skills and commands
  index     .codegraph/, so an agent can navigate the tree by symbol
  tests     engine, shell and agent suites
  rules     no ANSI, no emoji, no em dash, no key material
"""

import argparse
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The three bans, checked mechanically because a reviewer will not catch
# the four hundredth one. ANSI leaks in from tools that colour their
# output; the other two arrive by habit.
ANSI = re.compile(chr(27) + r"\[")
EM_DASH = re.compile("[" + chr(0x2014) + chr(0x2013) + "]")
# Built from code points rather than written out, so this file does not
# itself contain the characters it exists to forbid.
EMOJI = re.compile(
    "[" + "".join((
        "\U0001F300-\U0001FAFF", "\U00002700-\U000027BF",
        "\U0001F000-\U0001F0FF", "\U00002600-\U000026FF",
    )) + "]")
# A key that reaches a tracked file cannot be unpublished. Provider keys
# are typically sixteen or more upper case alphanumerics mixing letters
# and digits; a word in capitals is not one, which is why both classes
# must be present.
# Three letters, not one. A compact ISO timestamp such as 20260830T141217Z
# is sixteen upper case alphanumerics with digits, and archived artifacts
# are named with one, so a single-letter requirement flagged every archive
# filename the moment that feature landed. A provider key mixes letters
# throughout: the Alpha Vantage format carries ten.
KEYLIKE = re.compile(
    r"\b(?=(?:[A-Z0-9]*[A-Z]){3})(?=[A-Z0-9]*[0-9])[A-Z0-9]{16,}\b")

TEXT_SUFFIXES = {".py", ".md", ".json", ".sh", ".txt", ".toml", ".yaml",
                 ".yml", ".cfg", ".html", ".css"}

SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "dist",
             ".codegraph", ".pytest_cache", ".tmp", "plugin",
             ".claude-plugin"}


class Stage:
    """One step of the refresh, with its own verdict."""

    def __init__(self, name):
        self.name = name
        self.ok = True
        self.detail = ""
        self.seconds = 0.0


def run(command, cwd=ROOT, timeout=900):
    """Run a command and return (ok, combined output)."""
    try:
        finished = subprocess.run(
            command, cwd=str(cwd), capture_output=True, text=True,
            timeout=timeout)
    except FileNotFoundError as exc:
        return False, "not found: {}".format(exc)
    except subprocess.TimeoutExpired:
        return False, "timed out after {}s".format(timeout)
    output = (finished.stdout or "") + (finished.stderr or "")
    return finished.returncode == 0, output.strip()


def python_for_tests():
    """The interpreter that has the packages installed, or None.

    Prefers a virtualenv in the tree over whatever is on PATH, because
    running the suite against an interpreter without the packages produces
    a collection error that reads like a broken test.
    """
    for candidate in (ROOT / "shell" / ".venv" / "bin" / "python",
                      ROOT / ".venv" / "bin" / "python",
                      ROOT / "engine" / ".venv" / "bin" / "python"):
        if candidate.exists():
            return candidate
    found = shutil.which("python3")
    return Path(found) if found else None


def sync_readme_counts(interpreter):
    """Rewrite the three test counts the README quotes.

    They are the fastest-rotting numbers in the project: every commit that
    adds a test invalidates them. A test enforces them, which turns a stale
    number into a failure rather than a lie, and this keeps that failure
    from being something a person has to fix by hand.
    """
    readme = ROOT / "README.md"
    if not readme.exists():
        return True, "no README"
    text = readme.read_text(encoding="utf-8")
    updated = text
    changed = []
    for suite in ("engine/tests", "shell/tests", "agent/tests"):
        if not (ROOT / suite).exists():
            continue
        ok, output = run([str(interpreter), "-m", "pytest", suite,
                          "--collect-only", "-q", "--no-header",
                          "-p", "no:cacheprovider"], timeout=300)
        found = re.search(r"(\d+) tests? collected", output)
        if not found:
            return False, "could not collect {}".format(suite)
        count = found.group(1)
        pattern = re.compile(
            r"(pytest {} -q\s+# )(\d+)( tests)".format(re.escape(suite)))
        match = pattern.search(updated)
        if match and match.group(2) != count:
            changed.append("{} {} to {}".format(suite, match.group(2), count))
        updated = pattern.sub(
            lambda m: "{}{}{}".format(m.group(1), count, m.group(3)), updated)
    if updated != text:
        readme.write_text(updated, encoding="utf-8")
    return True, ("README counts updated: " + ", ".join(changed)
                  if changed else "README counts already correct")


def tracked_text_files():
    """Every text file that belongs to the project, generated ones aside."""
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        yield path


def check_rules():
    """The three bans and a key scan, over every tracked text file."""
    problems = []
    for path in tracked_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        relative = path.relative_to(ROOT)
        for label, pattern in (("ANSI escape", ANSI), ("em dash", EM_DASH),
                               ("emoji", EMOJI)):
            for number, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    problems.append("{}:{}: {}".format(relative, number,
                                                       label))
                    break
        if path.name in ("refresh.py",):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if "example" in line.lower() or "XXXX" in line:
                continue
            match = KEYLIKE.search(line)
            if match and not match.group(0).isdigit():
                problems.append("{}:{}: possible key material {}".format(
                    relative, number, match.group(0)[:4] + "..."))
                break
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--fast", action="store_true",
                        help="skip the test suites")
    parser.add_argument("--no-index", action="store_true",
                        help="skip the code index refresh")
    parser.add_argument("--no-package", action="store_true",
                        help="skip rebuilding the installable forms")
    args = parser.parse_args()

    interpreter = python_for_tests()
    stages = []

    def stage(name, work):
        step = Stage(name)
        started = time.time()
        step.ok, step.detail = work()
        step.seconds = time.time() - started
        stages.append(step)
        print("{:9} {:4} {:>6.1f}s  {}".format(
            step.name, "ok" if step.ok else "FAIL", step.seconds,
            step.detail.splitlines()[-1][:96] if step.detail else ""))
        return step

    print("refreshing {}".format(ROOT))
    print("interpreter: {}".format(interpreter or "none found"))
    print()

    stage("docs", lambda: run(
        [str(interpreter or "python3"), "shell/tools/gen_runtime_docs.py"]))
    stage("inventory", lambda: run(
        [str(interpreter or "python3"), "scripts/inventory.py"]))
    if interpreter:
        stage("counts", lambda: sync_readme_counts(interpreter))

    # Check only, never record. A refresh that re-recorded the evidence
    # would make the documented number follow whatever is on disk today,
    # which is the failure the evidence file exists to prevent.
    if interpreter:
        stage("evidence", lambda: run(
            [str(interpreter), "scripts/evidence.py", "check"]))

    if not args.no_package:
        stage("package", lambda: run(
            [str(interpreter or "python3"), "scripts/package.py"]))

    if not args.no_index:
        def index():
            if not shutil.which("codegraph"):
                return True, ("codegraph not installed, index skipped. "
                              "npm i -g @colbymchenry/codegraph to enable")
            command = ["codegraph",
                       "sync" if (ROOT / ".codegraph").exists() else "init",
                       "."]
            ok, output = run(command, timeout=1200)
            # Its progress bars are coloured; never let that reach a file.
            clean = ANSI.sub("", output)
            clean = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", clean)
            tail = [line for line in clean.splitlines() if line.strip()]
            return ok, tail[-1].strip() if tail else "index refreshed"
        stage("index", index)

    if not args.fast and interpreter:
        for suite in ("engine/tests", "shell/tests", "agent/tests"):
            if not (ROOT / suite).exists():
                continue
            stage(suite.split("/")[0], lambda suite=suite: run(
                [str(interpreter), "-m", "pytest", suite, "-q",
                 "--no-header"]))

    stage("rules", lambda: (
        (True, "no ANSI, no emoji, no em dash, no key material")
        if not check_rules()
        else (False, "{} problems: {}".format(
            len(check_rules()), "; ".join(check_rules()[:5])))))

    print()
    failed = [step.name for step in stages if not step.ok]
    if failed:
        print("FAILED: {}".format(", ".join(failed)))
        for step in stages:
            if not step.ok:
                print()
                print("--- {} ---".format(step.name))
                print(step.detail[-2000:])
        return 1
    print("all {} stages passed in {:.1f}s".format(
        len(stages), sum(step.seconds for step in stages)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
