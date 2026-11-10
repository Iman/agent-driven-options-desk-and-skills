# Contributing

**Looking for something to work on?** [docs/BACKLOG.md](docs/BACKLOG.md) lists what is known, measured and not done, with the evidence for each item and what finished means. Items marked good first issue are self-contained. Everything there came out of adversarial verification of this project's own numbers, so none of it is speculative.

Issues and pull requests are welcome. This file states what makes them
quick to merge and what causes them to be returned.

## Before you write code

Open an issue first for anything beyond a fix. The project refuses some
changes by design, and a change that crosses one of those lines is better
discussed before review.

Read `docs/CAPABILITIES.md` for what exists. Tests check its counts
against the source tree.

## The rule this project is built on

**Measure before you build, and say what you measured.**

Every change must answer three questions. Which observation made the change
worth doing? Which number was measured before, and which number is measured
now? What would have to be true for the change to be wrong?

A pull request that says "improves performance" gets asked for the two
numbers. One that says "deploy time went from 40 minutes to 4, measured
across five runs, here is the script" gets read immediately.

Most of the defects fixed in this repository were found when a claim was
measured. Examples are a volatility solver that returned its own starting
guess, a test suite whose tolerances made three Greeks untestable, and a
documented figure that was stale within six hours.

## Tests

Follow [Testing and coverage](docs/TESTING.md) for the separate test layers,
success and failure scenarios, and the 80% unit line-coverage gate per package.

Every behavioural change needs a test that was observed to fail before the
change.

```
python3 scripts/refresh.py        rebuilds everything generated, then runs
                                  the three suites and the house rules
python3 scripts/mutate.py         breaks the code on purpose and reports
                                  which breakages the tests notice
```

Write the docstring as what would break, not as a restatement of the
assert. `test_the_inner_vega_guard_refuses_rather_than_dividing_by_zero` is
worth more than `test_implied_vol_returns_none`.

For a defect fix, add a mutation in `scripts/mutate.py`. Without a
mutation, a later reversal of the fix can pass unnoticed.

## House rules, enforced mechanically

`scripts/refresh.py` fails on any of these, so there is no need to argue
about them in review:

- no ANSI escape codes anywhere, in any file
- no emoji
- no em dashes; plain hyphens or a rewrite
- nothing shaped like a provider key

If `cat` is aliased to a syntax highlighter, a file read through the shell
and written back contains colour codes. This fault occurred three times in
this repository. Use `/bin/cat`.

## What will be sent back

Numbers with no provenance. Anything that fills in a missing value with a
plausible default rather than reporting it as missing. Anything that turns
an analysis into a recommendation, which is a regulatory line and not a
stylistic one. Documentation that states what the code should do rather
than what it does.

Generated files edited by hand. `AGENTS.md`, `GEMINI.md`,
`docs/INVENTORY.md`, `plugins/option-desk/` and both marketplace manifests
are all built by scripts. Edit the source and rebuild.

## Licensing and your rights

Contributions are covered by `CLA.md`. In short, you keep your copyright
and stay free to use your own work anywhere, and you grant the copyright
holder a perpetual licence to use it here.

That grant is what allows the project to be relicensed, which it was on
31 August 2026. If that is not acceptable to you, please do not contribute
code; issues and reproductions are just as valuable and carry no such
terms.

The project is under `PolyForm Noncommercial 1.0.0`. It is not open source
in the OSI sense. Check that this is acceptable before contributing.

## Privacy

Read the rule in `CODE_OF_CONDUCT.md` about not asking anyone where they
are or what their network looks like. It applies to reviewers as much as to
anyone else, and "which country are you in?" is a question this project
does not need the answer to.
