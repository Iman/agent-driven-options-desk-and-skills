# QuantLib and LEAN evaluation

## UNKNOWN

This is an optional evaluation, outside the published engine, CLI, MCP server
and plugin. It does not establish production readiness or a strategy edge.
Real historical data, assignment, cash dividends, adjusted contracts, margin
stress, and multi-leg execution have not been validated here. QuantLib
Greeks, implied-volatility inversion and discrete dividends remain untested.
The container's complete dependency licence set has not been audited for
redistribution.

LEAN requested 18 data files in the final smoke test. Seven were present;
11 optional quote, trade, open-interest and benchmark-history probes were
absent. The synthetic equity trades and option quotes needed for the two
fills were present. Keep this limitation with the result.

## VERIFIED

The evaluation ran on 2026-09-13 London time, 2026-09-12 UTC. Versions,
source hashes, result hashes and observed test counts are in
[evidence.json](evidence.json).

QuantLib 1.43's analytic European prices agree with Option Desk's existing
Black-Scholes-Merton pricer within `1e-9` for four synthetic cases. The
American finite-difference prices satisfy the tested exercise bounds, and
the 400-by-400 and 800-by-800 grids differ by less than $0.001 per share.
These are four checks, not a broad accuracy certification.

| Synthetic case | European price | American price, 800 grid |
| --- | ---: | ---: |
| Call, spot 100, strike 100, one year, no dividends | 10.450584 | 10.450681 |
| Put, spot 80, strike 100, one year, no dividends | 16.982362 | 20.000000 |
| Call, spot 100, strike 80, one year, 10% continuous yield | 16.154122 | 20.000000 |
| Put, spot 100, strike 100, 30 days, 2% continuous yield | 4.522142 | 4.527373 |

All inputs and unrounded outputs are in
[quantlib-prices.json](results/quantlib-prices.json). The small premium on
the no-dividend call is numerical error. The existing European model is a
deliberate exercise-style choice; this comparison does not establish a bug.

The pinned ARM64 LEAN container completed an offline synthetic SPY call
round trip. It bought one contract at $2.10, sold at $2.20, charged $2 in
fees, and ended with no position. Cash reconciles to
`(2.20 - 2.10) * 100 - 2 = 8`. The importer checked completion, fill status,
data mode and the source plan hash in both order tags.
[lean-smoke.json](results/lean-smoke.json) preserves the observed result.
Its returns and Sharpe ratio describe arbitrary fixture prices and must
not be used to assess a strategy.

Validation observed in this session:

- Existing unit suite: 928 passed before and 928 passed after, with 162
  tests outside the unit selection. No tests were skipped in these runs.
- Explicit evaluation suite: 26 passed, none skipped. QuantLib was installed
  and exercised, not mocked.
- Before implementation, the new suite had a missing-module collection
  error. The importer then had six failing tests before its implementation.
  Three additional contract checks failed before adding refusal of time
  spreads and degraded source plans.
- The first real LEAN run completed, but result import failed because LEAN
  filters encoded hashes from display statistics. Order tags now preserve
  provenance. A rerun and the standalone smoke runner both completed and
  imported successfully. The missing interest-rate error in the first run
  was absent after adding an explicit synthetic zero-rate fixture.

This evaluation does not change production sources or test discovery.
The existing BDD, integration, browser and validation suites were not run.
Local JUnit files are under `artifacts/backend-evaluation/`. The portable
evidence file retains their counts without machine-specific metadata.

## ASSUMPTIONS

The export requires the caller to assert American exercise, a 100-share
multiplier and either synthetic or user-licensed data. The current plan
format does not establish those facts. Before using real data, verify them
against the instrument specification and the data provider's terms.

The QuantLib comparison uses Actual/365 Fixed, flat continuously compounded
rates, constant volatility and continuous dividend yields. A broader
benchmark grid and discrete-dividend fixtures are needed to establish the
limits of a production backend.

## Run the evaluation

From the Option Desk repository root, create a separate environment:

```sh
python3 -m venv /tmp/optiondesk-evaluation-venv
/tmp/optiondesk-evaluation-venv/bin/python -m pip install -e ./engine -r research/backend-evaluation/requirements.txt
/tmp/optiondesk-evaluation-venv/bin/python -m pytest research/backend-evaluation/test_evaluate.py -q --color=no
/tmp/optiondesk-evaluation-venv/bin/python research/backend-evaluation/evaluate.py prices
```

For the LEAN smoke test, start Docker and download the pinned image. The
runner creates a new directory and refuses to reuse an existing one.

```sh
docker pull quantconnect/lean@sha256:591e23a2e55fae410c699c8eef25e8ac66e0d63b8f1146c5c709d2f6041c6510
/tmp/optiondesk-evaluation-venv/bin/python research/backend-evaluation/run_smoke.py /tmp/optiondesk-lean-evaluation
```

The runner mounts only its evaluation directory, disables container
networking, and uses no account credentials. It copies exchange calendars
and contract specifications from the image, generates synthetic data, runs
LEAN, checks the fills and cash, and writes `summary.json`. The image pin is
Linux ARM64; other architectures require a separately validated image pin.

To export an existing strategy plan, substitute its actual path for
`PLAN.json`. Use a new destination and dates within that plan's lifetime:

```sh
/tmp/optiondesk-evaluation-venv/bin/python research/backend-evaluation/evaluate.py export PLAN.json /tmp/optiondesk-plan-export --start 2016-01-04 --end 2016-01-06 --exercise-style american --multiplier 100 --data-mode user-licensed
```

This creates `plan.json` and `main.py`. The export supports single-expiry
option legs with integer contract quantities. It rejects stock legs,
time-spread metadata, degraded sources and unsupported contract semantics.
Model premiums are not passed to LEAN as fills. The template enters at the
first common quote slice and liquidates on the final date. Legs use
separate simulated market orders; there is no atomic spread-fill claim.
Real-data configuration is a further integration step.
The export replays fixed legs. It does not reconstruct historical strategy
selection or prevent look-ahead in a user-provided plan.

Read a completed result with its exported bundle:

```sh
/tmp/optiondesk-evaluation-venv/bin/python research/backend-evaluation/evaluate.py import-result /tmp/optiondesk-lean-evaluation/results/OptionDeskEvaluation.json /tmp/optiondesk-lean-evaluation/plan.json
```

## PLAN

Use QuantLib for an optional pricing backend after validating exercise
metadata, dividend conventions, a larger benchmark grid and worker-process
isolation. Its global settings should not be shared by concurrent requests.
The evaluation restores its date setting and runs as a standalone process.

Keep LEAN as an external historical-backtest engine. Before exposing it in
the desk, validate a licensed historical dataset, short-option assignment,
expiry settlement, multi-leg margin and failed-order handling. Reuse LEAN's
models where validated, with their assumptions reported in the result.

## Credit and licences

QuantLib and QuantConnect LEAN retain their upstream copyrights and
licences. Exact notice text is in [notices/](notices/), and provenance is in
[THIRD-PARTY.md](../../THIRD-PARTY.md#optional-backend-evaluation).
The evaluation's own code follows Option Desk's PolyForm Noncommercial
1.0.0 terms. It does not relicense upstream packages or market data.
