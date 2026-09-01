"""The house-rules scan must actually fire.

WHAT WOULD BREAK. scripts/refresh.py ends with a stage that scans every
tracked text file for ANSI escape codes, emoji, em dashes and anything
shaped like a provider key, and the documentation says that scan was
"verified by planting a key-shaped string and confirming the refresh went
red". That verification was done by hand and then thrown away, which makes
it exactly the kind of claim this project is supposed to refuse: a guard
nobody can check is a guard nobody should trust.

So the planting is done here instead, every run. A scan that has never
fired is not known to work, and one that fires on everything is worse than
none.
"""

import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
REFRESH = ROOT / "scripts" / "refresh.py"


def _refresh():
    """Load refresh.py as a module without running it."""
    spec = importlib.util.spec_from_file_location("desk_refresh", REFRESH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def refresh():
    if not REFRESH.exists():
        pytest.skip("refresh.py not present")
    return _refresh()


# The planted strings. None of them is a real credential: the key-shaped one
# is sixteen characters of the right shape and belongs to nothing.
PLANTED = [
    ("ANSI escape", "\x1b[31mred\x1b[0m"),
    ("em dash", "one" + chr(0x2014) + "two"),
    ("em dash", "one" + chr(0x2013) + "two"),
    ("emoji", "shipped " + chr(0x1F680)),
    # Split so the literal never appears in this file: the scan reads
    # every tracked text file including this one, and a test that
    # trips the guard it is testing fails for the wrong reason.
    ("possible key material", "token " + "AB12CD34" + "EF56GH78"),
]


@pytest.mark.parametrize("label,planted", PLANTED,
                         ids=[p[1][:12] for p in PLANTED])
def test_the_scan_catches_what_it_claims_to_catch(refresh, tmp_path,
                                                  monkeypatch, label,
                                                  planted):
    """Each ban is planted in a scanned file and must be reported."""
    monkeypatch.setattr(refresh, "ROOT", tmp_path)
    (tmp_path / "planted.md").write_text(planted + "\n", encoding="utf-8")
    problems = refresh.check_rules()
    assert problems, "nothing was reported for {}".format(label)
    assert any(label in problem for problem in problems), (
        "{} was not the reason given: {}".format(label, problems))


def test_a_clean_tree_reports_nothing(refresh, tmp_path, monkeypatch):
    """A scan that fires on ordinary prose would be turned off within a day."""
    monkeypatch.setattr(refresh, "ROOT", tmp_path)
    (tmp_path / "clean.md").write_text(
        "Ordinary prose with a hyphen-joined word, a number 12345, an "
        "ALLCAPS word like PARAMETERISATION, and a code fence.\n",
        encoding="utf-8")
    (tmp_path / "clean.py").write_text(
        'VALUE = "SOME_CONSTANT_NAME"\n', encoding="utf-8")
    assert refresh.check_rules() == []


def test_a_capitalised_word_is_not_mistaken_for_a_key(refresh, tmp_path,
                                                      monkeypatch):
    """The first version of this scan flagged the word PARAMETERISATION.

    Sixteen upper case letters look like a key until you require a digit as
    well. A scan with false positives gets ignored, and an ignored scan is
    the same as no scan on the day it matters.
    """
    monkeypatch.setattr(refresh, "ROOT", tmp_path)
    (tmp_path / "prose.py").write_text(
        "# THE PARAMETERISATION MATTERS MORE THAN THE SAMPLER.\n"
        "# See also REPARAMETERISATION and IDENTIFIABILITY.\n",
        encoding="utf-8")
    assert refresh.check_rules() == []


def test_the_real_tree_is_clean(refresh):
    """The repository itself, scanned by the same code the refresh runs."""
    problems = refresh.check_rules()
    assert problems == [], "house rules violated: {}".format(problems[:5])


def test_a_compact_timestamp_is_not_mistaken_for_a_key(refresh, tmp_path,
                                                       monkeypatch):
    """Archived artifacts are named with one, and every name tripped it.

    20260830T141217Z is sixteen upper case alphanumerics containing digits,
    which is exactly the shape the scan looks for. Requiring three letters
    rather than one separates a timestamp, which has two, from a provider
    key, which has ten.
    """
    monkeypatch.setattr(refresh, "ROOT", tmp_path)
    (tmp_path / "names.py").write_text(
        'ARCHIVED = "chain_SPY_2026-09-18_20260830T141217Z.json"\n'
        'ALSO = "20260830T194100Z"\n',
        encoding="utf-8")
    assert refresh.check_rules() == []


def test_a_real_key_shape_still_trips_it(refresh, tmp_path, monkeypatch):
    """Narrowing the pattern must not blunt it."""
    monkeypatch.setattr(refresh, "ROOT", tmp_path)
    # Same shape as a provider key, and deliberately not one: this string
    # belongs to nothing. Never put a real credential in a test, split or
    # otherwise, because the test file is published with everything else.
    (tmp_path / "leak.md").write_text(
        "key " + "9K4MZ7Q1" + "RD2VHN6X" + "\n", encoding="utf-8")
    problems = refresh.check_rules()
    assert any("key material" in p for p in problems), problems


def test_personal_material_is_caught(refresh, tmp_path, monkeypatch):
    """An agent working in this tree once wrote a file of notes about the
    maintainer's CV and an article draft into docs/. It was untracked and
    was caught by reading the working tree, which is luck rather than a
    control.

    The scan must fire on that shape of content. It must not quote what it
    found: a report that echoes the line puts the material into the log,
    which is the thing being prevented.
    """
    # Assembled from pieces rather than written out, because a test file
    # containing the literal phrase would itself trip the scan it is
    # testing, and the scan reads every tracked file including this one.
    planted = tmp_path / "notes.md"
    planted.write_text(
        "{} {}: {} version 13.3 rebuilt tonight.\n".format(
            "Campaign", "notes", "CV"), encoding="utf-8")
    monkeypatch.setattr(refresh, "tracked_text_files", lambda: [planted])
    monkeypatch.setattr(refresh, "ROOT", tmp_path)
    problems = refresh.check_rules()
    assert problems, "the scan did not fire on personal material"
    assert any("personal material" in p for p in problems)
    assert not any("13.3" in p or "ampaign" in p for p in problems), (
        "the report quoted the material it was meant to keep out of logs")


def test_ordinary_option_prose_does_not_trip_the_personal_scan(
        refresh, tmp_path, monkeypatch):
    """This repository says profile, position and exposure constantly. A
    scan that fired on those would be switched off within a day.
    """
    planted = tmp_path / "ordinary.md"
    planted.write_text(
        "The max pain profile shows where open interest sits. A position "
        "profile is a different thing from a volatility profile, and the "
        "delta profile of this structure is flat.\n", encoding="utf-8")
    monkeypatch.setattr(refresh, "tracked_text_files", lambda: [planted])
    monkeypatch.setattr(refresh, "ROOT", tmp_path)
    assert refresh.check_rules() == []


def test_no_mutant_is_left_in_the_source():
    """An interrupted mutation run leaves the tree mutated, and the next
    `git add -A` commits it.

    That is not hypothetical. On 2026-08-31 a run of scripts/mutate.py was
    interrupted between applying a mutation and its finally block, and the
    ratio diagonal's entry-time delta bound went to origin as `if False:`
    inside the commit that added the sampler notice. The suite stayed green,
    because the mutation was recorded as an equivalent mutant and no test
    could kill it, and the harness reported it as SKIPPED rather than as
    damage: pattern not present, which reads like a stale entry rather than
    a deleted guard.

    This is the check that turns that into a failure. For every mutation,
    if the original text is gone and the replacement is present, the source
    is carrying a mutant.
    """
    import importlib.util
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "mutate_module", root / "scripts" / "mutate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    stuck = []
    for name, path, find, replace, _tests in module.MUTATIONS:
        text = (root / path).read_text(encoding="utf-8")
        if find not in text and replace in text:
            stuck.append("{} in {}".format(name, path))

    assert not stuck, (
        "the working tree is carrying mutated source: {}".format(stuck))


def test_every_mutation_still_matches_its_target():
    """A mutation whose pattern is gone proves nothing and says so quietly.

    The harness prints SKIPPED and carries on, so the count in the
    documentation stays right while the guard behind it has evaporated. One
    entry was found dead this way in an audit, naming a sentence in
    CAPABILITIES.md that had been reworded, and a second was a genuinely
    deleted guard. Neither failed anything.
    """
    import importlib.util
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "mutate_module", root / "scripts" / "mutate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    missing = []
    for name, path, find, _replace, _tests in module.MUTATIONS:
        target = root / path
        if not target.exists():
            missing.append("{}: {} does not exist".format(name, path))
            continue
        if find not in target.read_text(encoding="utf-8"):
            missing.append("{}: pattern gone from {}".format(name, path))

    assert not missing, (
        "mutations that can no longer be applied, so they guard nothing: "
        "{}".format(missing))
