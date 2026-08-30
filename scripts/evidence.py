#!/usr/bin/env python3
"""Pin the numbers the documentation quotes to the artifacts they came from.

WHY THIS EXISTS. Several figures in the documentation were measured from
real artifacts: a chain with 607 contracts of which 595 solved, a backtest
whose mean return was 47 percent against a 1.6 percent benchmark, a
completeness run that hit 547 of 575. Artifacts are keyed by underlying and
expiry, so the next pull replaces them, and within six hours of that README
sentence being written the same chain had moved to 590 solved and 17
refused. The prose was still true of the measurement and no longer provable
from the desk.

So the figures are recorded here with their provenance: which artifact,
when it was generated, which provider answered. That is a few kilobytes of
derived numbers rather than a copy of the provider's data, which matters
because this project tells its own users that redistribution is governed by
the provider's terms.

    python3 scripts/evidence.py record    read the artifacts, write the file
    python3 scripts/evidence.py check     verify the docs still match it

Recording is deliberate and manual. If the refresh regenerated this file it
would silently track whatever is on disk today, the documented number would
follow it, and the whole exercise would prove nothing.
"""

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "docs" / "evidence.json"


def _artifacts_dir():
    from optiondesk.config import artifact_dir

    return artifact_dir()


# Each claim names where the number lives in the artifact, and the exact
# string the documentation uses. The document text is checked rather than
# the number alone, because "607" appearing somewhere in a README is not
# evidence that the sentence about contracts is right.
CLAIMS = [
    {
        "id": "readme_chain_contracts",
        "artifact": "chain_SPY_2026-09-18.json",
        "generated_utc": "2026-08-30T14:12:17+00:00",
        "path": ["contracts", "__len__"],
        "documents": {"README.md": "607 contracts, spot, listed expiries"},
        "about": "contracts in the chain the data-flow diagram walks through",
    },
    {
        "id": "readme_chain_solved",
        "artifact": "chain_SPY_2026-09-18.json",
        "generated_utc": "2026-08-30T14:12:17+00:00",
        "path": ["counts", "with_iv"],
        "documents": {"README.md": "595 solved, 12 refused as unidentified"},
        "about": "contracts whose price identified a volatility",
    },
    {
        "id": "readme_chain_refused",
        "artifact": "chain_SPY_2026-09-18.json",
        "generated_utc": "2026-08-30T14:12:17+00:00",
        "path": ["counts", "without_iv"],
        "documents": {"README.md": "595 solved, 12 refused as unidentified"},
        "about": "contracts refused because the price identifies no "
                 "volatility",
    },
    {
        "id": "faq_backtest_mean_return",
        "artifact": "backtest_SPY_bull_call_spread_30d.json",
        "path": ["statistics", "mean_return"],
        "documents": {"FAQ.md": "made 47 percent per trade"},
        "about": "mean return on capital at risk per trade",
    },
    {
        "id": "faq_benchmark_mean_return",
        "artifact": "backtest_SPY_bull_call_spread_30d.json",
        "path": ["benchmark", "statistics", "mean_return"],
        "documents": {"FAQ.md": "about 1.6 percent per window"},
        "about": "buy and hold over the same windows",
    },
]


def _dig(payload, path):
    """Walk a path into a payload. __len__ takes the length of a list."""
    value = payload
    for step in path:
        if step == "__len__":
            return len(value)
        value = value[step]
    return value


def _generated(path):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    return (payload.get("meta") or {}).get("generated_utc")


def _find_artifact(name, generated_utc=None):
    """The artifact a claim is about, live or archived.

    A claim may pin `generated_utc`, and pinning is the normal case rather
    than the exception. A documented sentence describes one measurement,
    and the artifact carrying that name today is a different measurement
    with the same key: the chain behind "595 solved, 12 refused" reported
    590 and 17 six hours later. Without the pin this file would record
    whatever is newest and agree with nothing.

    Unpinned, the live copy wins and the newest archived copy is the
    fallback, which is right for a figure that is about the current state.
    """
    directory = _artifacts_dir()
    stem = Path(name).stem
    candidates = [directory / name]
    candidates += sorted((directory / "archive").rglob(stem + "_*.json"))
    candidates = [c for c in candidates if c.exists()]
    if generated_utc:
        for candidate in candidates:
            if _generated(candidate) == generated_utc:
                return candidate
        return None
    return candidates[0] if candidates else None


def record():
    entries = {}
    missing = []
    for claim in CLAIMS:
        path = _find_artifact(claim["artifact"], claim.get("generated_utc"))
        if path is None:
            missing.append("{}{}".format(
                claim["artifact"],
                " generated {}".format(claim["generated_utc"])
                if claim.get("generated_utc") else ""))
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        meta = payload.get("meta", {})
        entries[claim["id"]] = {
            "value": _dig(payload, claim["path"]),
            "about": claim["about"],
            "artifact": path.name,
            "generated_utc": meta.get("generated_utc"),
            "provider_used": meta.get("provider_used"),
            "degraded": bool(meta.get("degraded")),
            "documents": claim["documents"],
        }
    if missing:
        print("could not find: {}".format(", ".join(sorted(set(missing)))))
        print("run the commands that write them, then record again")
        return 1
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps({
        "note": ("Figures quoted in the documentation, with the artifact "
                 "each came from. Derived numbers only: no provider data "
                 "is reproduced here. Written by scripts/evidence.py."),
        "figures": entries,
    }, indent=1) + "\n", encoding="utf-8")
    print("recorded {} figures to {}".format(len(entries),
                                             EVIDENCE.relative_to(ROOT)))
    for key, entry in entries.items():
        print("  {:28} {:<22} {}".format(key, entry["value"],
                                         entry["artifact"]))
    return 0


def check():
    """Every recorded figure must still appear in the document that cites it."""
    if not EVIDENCE.exists():
        print("no evidence file: run scripts/evidence.py record")
        return 1
    figures = json.loads(EVIDENCE.read_text(encoding="utf-8"))["figures"]
    problems = []
    for key, entry in figures.items():
        for document, sentence in entry["documents"].items():
            text = (ROOT / document).read_text(encoding="utf-8")
            if sentence not in text:
                problems.append(
                    "{}: {} no longer contains {!r}".format(key, document,
                                                            sentence))
                continue
            if not _sentence_agrees(sentence, entry["value"]):
                problems.append(
                    "{}: {} says {!r} but the recorded value is {}".format(
                        key, document, sentence, entry["value"]))
    for problem in problems:
        print(problem)
    print("{} figures checked, {} problems".format(len(figures),
                                                   len(problems)))
    return 1 if problems else 0


def _sentence_agrees(sentence, value):
    """Does the documented sentence carry the recorded number?

    Percentages are matched at the precision the prose uses, because the
    prose rounds on purpose: 0.4742 is written as 47 percent and demanding
    the full figure would force the documentation to read like a printout.
    """
    numbers = [float(n) for n in re.findall(r"\d+\.?\d*", sentence)]
    if not numbers:
        return False
    if isinstance(value, int):
        return float(value) in numbers
    for written in numbers:
        if abs(written - value) < 1e-9:
            return True
        if abs(written - value * 100.0) <= 0.5:
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("action", choices=("record", "check"))
    args = parser.parse_args()
    return record() if args.action == "record" else check()


if __name__ == "__main__":
    raise SystemExit(main())
