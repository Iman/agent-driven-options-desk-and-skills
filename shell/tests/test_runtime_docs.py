"""The generated runtime files must stay derived from the skills."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _generator():
    sys.path.insert(0, str(ROOT / "tools"))
    import gen_runtime_docs

    return gen_runtime_docs


def test_runtime_files_are_in_sync_with_the_skills():
    """Compare generated text against what is on disk.

    The earlier version ran the generator as a subprocess with cwd set to
    the repository, then asserted substrings against the file it had just
    overwritten. Every assertion was a tautology, the test repaired any
    drift it was meant to detect, and running pytest modified the working
    tree. Proven by replacing both files with garbage: the test passed and
    the garbage was silently repaired.
    """
    generator = _generator()
    for name in ("AGENTS.md", "GEMINI.md"):
        on_disk = (ROOT / name).read_text(encoding="utf-8")
        expected = generator.generate(name)
        assert on_disk == expected, (
            "{} is stale. Run python tools/gen_runtime_docs.py".format(name))
        assert "## Skill: options-greeks" in on_disk
        assert "not investment advice" in on_disk


def test_generator_writes_both_files_when_run(tmp_path):
    # The generator itself is exercised in a copy, never in the repository.
    import shutil

    sandbox = tmp_path / "shell"
    shutil.copytree(ROOT, sandbox, ignore=shutil.ignore_patterns(
        ".venv", "__pycache__", ".pytest_cache", "*.egg-info"))
    result = subprocess.run(
        [sys.executable, str(sandbox / "tools" / "gen_runtime_docs.py")],
        capture_output=True, text=True, cwd=str(sandbox))
    assert result.returncode == 0, result.stderr
    for name in ("AGENTS.md", "GEMINI.md"):
        assert (sandbox / name).read_text(encoding="utf-8").startswith("#")


def test_every_skill_has_valid_frontmatter():
    sys.path.insert(0, str(ROOT / "tools"))
    import gen_runtime_docs

    skills = sorted((ROOT / "skills").glob("*/SKILL.md"))
    assert skills, "no skills found"
    for path in skills:
        fields, body = gen_runtime_docs.parse_skill(path)
        assert fields["name"] == path.parent.name
        # The description is what a runtime matches on, so it must say both
        # what the skill does and when to reach for it.
        assert len(fields["description"]) > 80
        assert "Use when" in fields["description"]
        assert body
