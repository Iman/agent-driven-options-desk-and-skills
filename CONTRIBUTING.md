# Contributing

Issues and pull requests are welcome. This file says what makes them
land quickly, and what will get them sent back.

## Before you write code

Open an issue first for anything beyond a fix. Not for ceremony: this
project has a strong opinion about what it refuses to do, and a change that
crosses one of those lines is better discussed than discovered at review.

Read `docs/CAPABILITIES.md` for what exists. It is generated in part and
complete by construction, so it will not send you looking for something
that was removed.

## The rule this project is built on

**Measure before you build, and say what you measured.**

Every change should be able to answer three questions. What did you observe
that made this worth doing. What number did you get before, and what number
do you get now. What would have to be true for the change to be wrong.

A pull request that says "improves performance" gets asked for the two
numbers. One that says "deploy time went from 40 minutes to 4, measured
across five runs, here is the script" gets read immediately.

This is not pedantry. Most of the defects fixed in this repository were
found because a confident claim collapsed on first contact with data: a
volatility solver returning its own starting guess, a test suite whose
tolerances made three Greeks untestable, a documented figure that had gone
stale within six hours. All of them read as fine.

## Tests

Every behavioural change needs a test, and the test must be one you have
watched fail.

```
python3 scripts/refresh.py        rebuilds everything generated, then runs
                                  the three suites and the house rules
python3 scripts/mutate.py         breaks the code on purpose and reports
                                  which breakages the tests notice
```

Write the docstring as what would break, not as a restatement of the
assert. `test_the_inner_vega_guard_refuses_rather_than_dividing_by_zero` is
worth more than `test_implied_vol_returns_none`.

If you add a defect fix, add a mutation for it in `scripts/mutate.py`. A
fix without one is a fix nobody notices being undone.

## House rules, enforced mechanically

`scripts/refresh.py` fails on any of these, so there is no need to argue
about them in review:

- no ANSI escape codes anywhere, in any file
- no emoji
- no em dashes; plain hyphens or a rewrite
- nothing shaped like a provider key

A note on the first one. If `cat` on your machine is aliased to a syntax
highlighter, reading a file through the shell and writing it back embeds
colour codes into the source. It has happened three times here. Use
`/bin/cat`.

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

Contributions are covered by `CLA.md`. In short: you keep your copyright
and stay free to use your own work anywhere, and you grant the copyright
holder a perpetual licence to use it here.

That grant is what allows the project to be relicensed, which it was on
2026-08-31. If that is not acceptable to you, please do not contribute
code; issues and reproductions are just as valuable and carry no such
terms.

The project is under `PolyForm Noncommercial 1.0.0`. It is not open source
in the OSI sense, and that will matter to some people. Better to know now
than at review.

## Privacy

Read the rule in `CODE_OF_CONDUCT.md` about not asking anyone where they
are or what their network looks like. It applies to reviewers as much as to
anyone else, and "which country are you in?" is a question this project
does not need the answer to.
