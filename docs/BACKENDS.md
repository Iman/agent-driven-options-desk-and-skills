# Optional QuantLib and LEAN backends

Install QuantLib into the same environment as the engine:

```sh
python -m pip install -e './engine[quantlib]'
optiondesk price --spot 80 --strike 100 --valuation-date 2026-09-12 --expiry 2027-09-12 --volatility .2 --rate .05 --dividend-yield 0 --kind put --exercise-style american
```

The `option_price` MCP tool accepts the same named inputs. Each request
uses a fresh process. The result reports premium per underlying unit,
exercise style, a European reference and the difference between two
finite-difference grids. A difference over 0.001 marks the result degraded.
Grid agreement is not a guaranteed numerical error bound.

The model uses Actual/365 Fixed, constant volatility, flat continuous rates
and a continuous dividend yield. Discrete dividends are not implemented.
Existing chain Greeks and strategy premiums still use their existing models.
Do not present them as American-option sensitivities.

## LEAN handoff

```sh
optiondesk lean export --plan PLAN.json --destination NEW_DIRECTORY --start 2016-01-04 --end 2016-01-06 --exercise-style american --multiplier 100 --data-mode user-licensed
optiondesk lean import --result RESULT.json --bundle NEW_DIRECTORY/plan.json
```

Substitute the actual plan paths and dates. `option_lean` exposes both
actions through MCP. MCP exports use a new directory under the desk's
artifact root. The tool exports or imports files; it does not execute LEAN.

The export contains `main.py` and `plan.json`. It accepts single-expiry
American US equity options with integer quantities and a 100-share
multiplier. Degraded inputs, stock legs, time spreads and unsupported terms
are refused. Price inputs from the plan do not become historical fills.

Supply a local LEAN runtime, configuration and permitted historical data.
The algorithm class is `OptionDeskBacktest`. It enters on the first common
quote slice and liquidates on the final date using separate simulated
market orders. The template rejects live mode.

The importer requires completed status, filled orders, matching plan tags
and data mode. It reports that data coverage and model suitability remain
unvalidated. This workflow does not reconstruct point-in-time strategy
selection, prove atomic spread fills, or validate assignment-generated
orders. LEAN's statistical units are retained.

The original isolated evaluation, image pin, synthetic-data runner and
results are in [backend evaluation](../research/backend-evaluation/README.md).
The production adapter is separately covered by CLI/MCP and process tests.
QuantLib and LEAN notices are included in the Python packages and local
plugin. See [credits](../THIRD-PARTY.md#optional-production-backends).

## Validation evidence

VERIFIED on 2026-09-13: 937 unit tests and 46 integration tests passed in
the separate Option Desk environment. All 111 validation tests passed in
a source snapshot that excludes ignored private files. In the working
directory, the house-rule test still reports eight findings in private
article drafts. The original committed checker reports the same findings.

The production LEAN handoff ran against the pinned runtime with synthetic
quotes: two filled orders, no remaining holdings and an eight-dollar net
gain. This checks the handoff, not historical strategy performance.
The installed engine and shell wheels also priced the documented American
put through QuantLib successfully.

UNKNOWN: performance on licensed historical option data and suitability
for production portfolios. Synthetic fixtures do not establish either.
