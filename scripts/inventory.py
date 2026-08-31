#!/usr/bin/env python3
"""Scan every source file and write the inventory nobody maintains by hand.

WHY THIS IS GENERATED RATHER THAN WRITTEN. A hand written index of a
codebase is wrong within a week and nobody notices, because a stale index
looks exactly like a fresh one. This walks the tree, parses each module and
writes what is actually there: every public function and class, with the
first line of its docstring and the line it starts on.

It reports what is missing too. A public function with no docstring is
listed as undocumented rather than quietly skipped, because the point of
the exercise is to find the gaps.

Run it through scripts/refresh.py, or on its own:

    python3 scripts/inventory.py
"""

import ast
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "INVENTORY.md"

PACKAGES = [
    ("engine", "engine/src/optiondesk_engine", "PolyForm-Noncommercial-1.0.0",
     "Every number the desk reports. Standard library only, no network."),
    ("shell", "shell/src/optiondesk", "PolyForm-Noncommercial-1.0.0",
     "Data, contracts, CLI, dashboard, MCP. Runs without the engine, and "
     "says so rather than guessing."),
    ("agent", "agent/src/optiondesk_agent", "PolyForm-Noncommercial-1.0.0",
     "LangChain tool bindings and a LangGraph desk routine. Optional, and "
     "never in the compute path."),
]

TESTS = ["engine/tests", "shell/tests", "agent/tests"]


def first_line(node):
    """First sentence of a docstring, or None."""
    text = ast.get_docstring(node)
    if not text:
        return None
    line = text.strip().split("\n")[0].strip()
    return line.rstrip(".") if line else None


def public(name):
    return not name.startswith("_")


def scan_module(path):
    """Public API of one module, with what it is missing."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        return {"error": "{}: {}".format(type(exc).__name__, exc)}

    functions, classes, undocumented = [], [], []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not public(node.name):
                continue
            doc = first_line(node)
            functions.append({"name": node.name, "line": node.lineno,
                              "doc": doc})
            if doc is None:
                undocumented.append(node.name)
        elif isinstance(node, ast.ClassDef):
            if not public(node.name):
                continue
            doc = first_line(node)
            methods = [child.name for child in node.body
                       if isinstance(child, ast.FunctionDef)
                       and (public(child.name) or child.name == "__init__")]
            classes.append({"name": node.name, "line": node.lineno,
                            "doc": doc, "methods": methods})
            if doc is None:
                undocumented.append(node.name)

    return {
        "doc": first_line(tree),
        "lines": len(path.read_text(encoding="utf-8").splitlines()),
        "functions": functions,
        "classes": classes,
        "undocumented": undocumented,
    }


def count_tests(directory):
    """How many test functions live under a directory, per file."""
    out = {}
    base = ROOT / directory
    if not base.exists():
        return out
    for path in sorted(base.rglob("test_*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        count = sum(
            1 for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_"))
        out[str(path.relative_to(ROOT))] = count
    return out


def skills():
    """Every skill, with its declared metadata and bundled resources."""
    out = []
    base = ROOT / "shell" / "skills"
    for skill_md in sorted(base.glob("*/SKILL.md")):
        text = skill_md.read_text(encoding="utf-8")
        name = description = ""
        if text.startswith("---"):
            end = text.find("---", 3)
            for line in text[3:end].splitlines():
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("description:"):
                    description = line.split(":", 1)[1].strip()
        directory = skill_md.parent
        out.append({
            "name": name or directory.name,
            "description": description,
            "tokens_estimate": len(text) // 4,
            "resources": sorted(
                str(p.relative_to(directory))
                for p in directory.rglob("*")
                if p.is_file() and p.name != "SKILL.md"),
        })
    return out


def markdown_front_matter(path):
    text = path.read_text(encoding="utf-8")
    fields = {}
    if text.startswith("---"):
        end = text.find("---", 3)
        for line in text[3:end].splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                fields[key.strip()] = value.strip()
    return fields


def render():
    stamp = dt.datetime.now().strftime("%Y-%m-%d")
    lines = [
        "# Inventory",
        "",
        "Generated by `scripts/inventory.py` on {}. Do not edit by hand: "
        "run `python3 scripts/refresh.py` and it is rewritten.".format(stamp),
        "",
        "This is the complete public surface of the project, read out of the "
        "source rather than remembered. Anything public and undocumented is "
        "listed as such at the end of its section, which is the only way a "
        "gap gets noticed.",
        "",
    ]

    totals = {"modules": 0, "functions": 0, "classes": 0, "undocumented": 0,
              "lines": 0}

    for label, relative, licence, purpose in PACKAGES:
        base = ROOT / relative
        if not base.exists():
            continue
        lines += ["## Package: {} ({})".format(label, licence), "", purpose,
                  ""]
        for path in sorted(base.rglob("*.py")):
            info = scan_module(path)
            if "error" in info:
                lines += ["### `{}`".format(path.relative_to(ROOT)),
                          "", "Could not parse: {}".format(info["error"]), ""]
                continue
            if not info["functions"] and not info["classes"] \
                    and path.name == "__init__.py" and not info["doc"]:
                continue
            totals["modules"] += 1
            totals["lines"] += info["lines"]
            totals["functions"] += len(info["functions"])
            totals["classes"] += len(info["classes"])
            totals["undocumented"] += len(info["undocumented"])

            lines += ["### `{}`".format(path.relative_to(ROOT)), ""]
            if info["doc"]:
                lines += [info["doc"] + ".", ""]
            lines += ["{} lines.".format(info["lines"]), ""]

            for cls in info["classes"]:
                lines.append("- class **{}** (line {}): {}".format(
                    cls["name"], cls["line"], cls["doc"] or "undocumented"))
                if cls["methods"]:
                    lines.append("  - methods: {}".format(
                        ", ".join("`{}`".format(m) for m in cls["methods"])))
            for func in info["functions"]:
                lines.append("- **{}()** (line {}): {}".format(
                    func["name"], func["line"], func["doc"] or "undocumented"))
            lines.append("")
            if info["undocumented"]:
                lines += ["Undocumented public names in this module: {}."
                          .format(", ".join(info["undocumented"])), ""]

    lines += ["## Skills", ""]
    for skill in skills():
        lines += [
            "### {}".format(skill["name"]), "",
            skill["description"] or "No description in front matter.", "",
            "Roughly {} tokens in SKILL.md. Bundled: {}.".format(
                skill["tokens_estimate"],
                ", ".join("`{}`".format(r) for r in skill["resources"])
                or "nothing"),
            "",
        ]

    for label, directory in (("Commands", ".claude/commands"),
                             ("Agents", ".claude/agents")):
        base = ROOT / directory
        if not base.exists():
            continue
        lines += ["## {}".format(label), ""]
        for path in sorted(base.glob("*.md")):
            fields = markdown_front_matter(path)
            lines.append("- **{}**: {}".format(
                path.stem,
                fields.get("description", "no description in front matter")))
        lines.append("")

    lines += ["## Tests", ""]
    grand = 0
    for directory in TESTS:
        counts = count_tests(directory)
        if not counts:
            continue
        subtotal = sum(counts.values())
        grand += subtotal
        lines += ["### {} ({} test functions)".format(directory, subtotal),
                  ""]
        for path, count in sorted(counts.items()):
            lines.append("- `{}`: {}".format(path, count))
        lines.append("")

    lines += [
        "## Totals", "",
        "{} modules, {} lines of source, {} public functions, {} public "
        "classes, {} test functions.".format(
            totals["modules"], totals["lines"], totals["functions"],
            totals["classes"], grand),
        "",
        "Public names with no docstring: {}.".format(totals["undocumented"])
        if totals["undocumented"] else "Every public name carries a "
        "docstring.",
        "",
    ]
    return "\n".join(lines) + "\n", totals, grand


def main():
    text, totals, tests = render()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print("inventory: {} modules, {} functions, {} classes, {} tests, "
          "{} undocumented".format(totals["modules"], totals["functions"],
                                   totals["classes"], tests,
                                   totals["undocumented"]))
    print("wrote {}".format(OUT.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
