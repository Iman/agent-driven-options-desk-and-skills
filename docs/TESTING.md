# Testing and coverage

[Development guide](wiki/Development.md) | [Contributing](../CONTRIBUTING.md)

## Install test dependencies

From the repository root, activate your virtual environment and run:

```sh
python -m pip install -e ./engine -e './shell[dev]' -e './agent[dev]'
python -m playwright install chromium
```

On Linux CI, install Chromium and its system dependencies with `python -m playwright install --with-deps chromium`.

## Test layers

Each test belongs to one layer. The root `conftest.py` assigns the markers before test selection.

| Layer | Scope | Happy path | Failure path |
|---|---|---|---|
| Unit | In-process functions and command handlers. External process and network boundaries are replaced. Temporary files are permitted. | Calculations, provider response parsing, paper entries and settlements. | Missing quotes, rejected input, transport errors, invalid position IDs, and repeat settlement. |
| BDD | Gherkin scenarios using production command handlers and synthetic inputs. | Import a chain and produce research artifacts. | Missing rights, spot, or source; malformed replacement; unavailable volatility. |
| Integration | Real CLI and MCP processes, loopback HTTP, Chromium, and existing installer/container checks. | Import both expiries, compare structures, generate plots, settle a paper position, and render the dashboard. | Invalid input preserves prior artifacts; bad MCP requests leave the session usable; missing static files return 404. |
| Validation | Documentation, generated files, packaging metadata, repository rules, and coverage-gate behavior. | Inventories and reports agree with their sources. | Missing evidence, stale claims, or one package below its threshold fails the check. |

Unit tests cannot launch subprocesses, bind sockets, or connect sockets through the guarded Python interfaces.
Tests that need these operations belong in the integration layer.
This is a test-isolation guard, not an operating-system network sandbox.

The BDD source is [sample_desk.feature](../shell/tests/bdd/sample_desk.feature).
The process and browser workflow is [test_sample_journey.py](../shell/tests/integration/test_sample_journey.py).
All new workflow inputs are synthetic. Child application processes run in demo mode, which refuses external providers.
These tests do not verify live-provider availability, broker execution, or every supported installation environment.

## Run the 80% unit coverage gate

Run these commands from the repository root:

```sh
mkdir -p artifacts/coverage
python -m coverage run -m pytest -m unit -q --color=no --junitxml=artifacts/coverage/unit-tests.xml
python -m coverage json
python -m coverage xml
python -m coverage html
python scripts/check_unit_coverage.py artifacts/coverage/unit.json
```

The minimum is **80% line coverage for each Python package**: engine, shell, and agent.
A stronger package cannot offset a weaker package.
The gate compares unrounded line counts and rejects reports that omit production Python files.
The denominator includes production Python under all three `src` directories.
It excludes tests, Bash scripts, and vendored JavaScript.

Branch coverage is collected and reported, but it has no separate minimum.
BDD and integration runs do not contribute to unit coverage.
Do not combine their coverage data with the unit report.

Open `artifacts/coverage/html/index.html` to inspect uncovered lines and branches.
Reports are local build artifacts. CI uploads them for each Python version.

## Run acceptance, integration, and validation tests

```sh
python -m pytest -m bdd -q --color=no
python -m pytest -m integration -q --color=no
python -m pytest -m validation -q --color=no
```

Integration tests need loopback sockets, process execution, and installed Chromium.
The workflow starts and stops its own dashboard process.
The tests use temporary artifact directories.

To run every layer together, use `python -m pytest -q --color=no`.
That command verifies behavior but does not produce the isolated unit-coverage measurement.

## Use TDD for behavior changes

TDD is the order of development, not an additional test suite.

1. Describe the expected success and failure behavior.
2. Write a focused test before changing the implementation.
3. Run it and record the failure. Check that the failure concerns the intended behavior.
4. Make the smallest implementation change that satisfies the test.
5. Repeat the same test and inspect its passing result.
6. Refactor if needed, then run the affected layers and unit-coverage gate.

For a defect, reproduce the defect before editing production code.
A test written against behavior that already passes is regression coverage; it does not establish a TDD cycle.
Record commands and observed results in the change description.
Do not describe test-authoring mistakes as product defects.

The coverage gate was developed test-first: eight cases initially reported setup errors because the new module did not exist.
After implementation, the same eight cases passed.
Those cases cover the threshold, a weak individual package, rounding, missing evidence, invalid counts, and branch/line separation.
Three additional command-level cases check exit status and omitted source files.
This establishes the new gate's behavior; it is not evidence of an analytics defect correction.

## CI and generated documentation

The [refresh workflow](../.github/workflows/refresh.yml) runs the layers separately on Python 3.11 and 3.13.
It uploads test and coverage reports, refreshes generated files, and runs the mutation harness.

When tests or public interfaces change, update generated inventories and README collection counts:

```sh
python scripts/refresh.py --fast --no-index
```

This command skips test execution. Its success does not establish passing tests.
Read the actual non-zero test totals from the layer runs.
