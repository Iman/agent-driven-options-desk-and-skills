# Changelog

Dates are the day the work landed. Figures quoted here were measured on one
live SPY chain, 2026-10-16 expiry with 2026-12-18 also on disk, unless the
entry says otherwise.

## 0.3.0, 2026-09-02

This release adds private analysis of user-supplied option-chain data.

- The OpenAI Skills-page archive now contains hosted-safe MCP workflows only.
  Local provider, setup, simulation, and backtest instructions remain in a
  separate local-skills archive.

- The CLI imports CSV or JSON with an explicit source and data-rights statement.
- MCP clients can send a JSON object, JSON text, CSV text, or a local path.
- The importer normalizes documented aliases, numeric commas, call or put codes,
  and clear percentage units.
- The importer reports each deterministic repair. It rejects missing, duplicate,
  conflicting, negative, or non-finite market fields.
- Imported snapshots feed the existing Greeks, positioning, strategy, plot, and
  dashboard paths.
- User-data plots include a solid warning footer.
- A new `option_snapshot_schema` tool tells chat clients how to correct an
  attachment without inventing values.
- The hosted service can process uploads privately. The public dashboard remains
  synthetic until a licensed provider is approved.

## 0.2.1, 2026-09-02

This release corrects the data-use boundary. It does not change the analytics.

- Yahoo now needs a separate local personal-use acknowledgement. The
  installer's `--yes` flag does not provide it.
- `PUBLIC_DATA_MODE=demo` blocks all external providers.
- `PUBLIC_DATA_MODE=licensed` permits only providers approved for public web
  display, derived outputs, storage, redistribution, and MCP delivery. No
  included provider has that approval.
- An invalid public data mode fails closed.
- The public OpenAI archive remains skills-only. It accepts user-provided data
  and tells users to share only data they have the right to share.
- The skills use an approved tool when one is present. They do not bypass a
  provider refusal or start a localhost dashboard in place of an in-chat plot.

## 0.2.0, 2026-08-31

The headline: eleven numbers or claims changed, so figures produced by
0.1.0 are not always comparable with figures produced by this release. The
list below says which, because a version number on its own does not.

### Figures that moved

- **Chain quality.** The implied volatility solver tested sensitivity at
  its 0.30 starting guess and refused contracts it could identify from
  there. On the live chain that was 41 contracts; the provider-volatility
  fallback fell from 48 contracts to 2, solved rose from 338 to 380, and
  the chain went from degraded to not degraded. Any 0.1.0 chain marked
  degraded for provider volatility should be re-pulled before its
  degradation is believed.
- **Backtest significance.** The permutation test and the bootstrap
  interval now resample blocks, because the windows overlap: a thirty day
  hold entered every five trading days shares twenty-five of its thirty
  days with its neighbour, and the effective sample is 64 to 88 rather than
  233. Four structures moved from below 0.05 to above it. Iron condor
  0.0005 to 0.0275, bear call spread 0.0005 to 0.0415, jade lizard 0.0380
  to 0.0855, long put 0.1094 to 0.4563, bear put spread 0.0005 to 0.1479.
  Two intervals stopped excluding zero. Every backtest artifact now carries
  `overlap_block`.
- **Time spread legs.** The two-expiry builders selected and priced at the
  module defaults of four percent and no dividend while the snapshot
  carried a measured rate and a fetched yield. Three of the four legs of a
  ratio diagonal land on different strikes at the measured values. Plans
  now carry `risk_free_rate` and `dividend_yield`.
- **The payoff curve.** It was drawn at the module defaults while the
  analysis beside it in the same artifact used the snapshot's rates. One
  calendar carried a maximum gain of 8.136160 in a file whose own curve
  peaked at 9.030645 at the same price.
- **Greeks with a zero rate.** A risk-free rate of exactly zero was falsy
  and was silently replaced by four percent, while the flag reporting a
  missing rate stayed false. Where that happened the live at-the-money call
  moved 14.3 percent in price, 29.5 percent in theta, and vanna changed
  sign.

### Claims that were wrong and are now correct

- `antithetic` read true in every simulation artifact. Of ten thousand
  pairs, none shared a shock sequence: the construction never ran. It is
  removed and the field reads false. No published number was biased by it.
- `delta_ratio` was documented in five places, one of them a JSON schema,
  as what keeps a large move uncapped. It is a bound on the entry split.
  One long against two short satisfies it and is a net short call with
  unbounded loss. The builder now checks the contract count first.
- The exposure artifact reported contracts skipped for missing open
  interest when all of them carried it and the missing thing was
  volatility. Skip reasons are counted separately and reported separately.
- Two-expiry maxima were published as properties of the structure when they
  are properties of the scan window. Plans carry
  `reward_risk_bounded_by_scan`, `max_gain_on_boundary`,
  `max_loss_on_boundary` and `scan_range_sd`, the last in standard
  deviations, because on this chain the window edges sit about ten
  deviations from spot.

### Added

- Four structures, taking the playbook from seventeen to twenty-three:
  `bull_put_spread`, `bear_call_spread`, `ratio_call_diagonal`,
  `ratio_put_diagonal`. The two ratio diagonals are ported from the
  author's earlier work and select legs by delta rather than by distance
  from spot.
- The put sides of the calendar and the diagonal as first-class structures,
  `calendar_put_spread` and `diagonal_put_spread`. They existed only as a
  flag before, so they built correctly and never appeared as a row.
- `compare` builds the two-expiry family, so one page carries all
  twenty-three from one snapshot, and the artifact records `not_compared`
  with the reason for anything absent.
- A composite support panel: one score per structure under a printed
  formula ported from the author's earlier spread engine, with the model,
  the simulation and five years of history side by side and disagreements
  marked rather than averaged.
- A time spreads panel carrying the columns that exist only for two-expiry
  structures.
- `demo.sh`, which runs the whole desk end to end and serves the dashboard.
- `docs/BACKLOG.md`, twelve items with the evidence for each.
- `docs/SCREENSHOTS.md`, every panel and chart from one live run.
- A scan in the refresh pipeline that fails the build on personal material
  in a tracked file.

### Fixed

- The dashboard rendered a confident zero trades for a structure that
  entered 233 and correctly refused a return on risk it cannot define.
- The composite panel ranked a structure the comparison beside it excluded,
  so one page showed sixteen ranked and seventeen ranked.
- Chart tooltips printed raw floats: a drawdown read -26.320660417060417.
- The payoff x axis printed its raw bounds, 574.2599945068359.
- A chart legend with fifteen series wrapped over the plot.
- `calendar_spread` chose its strike from the near chain alone and then
  required the far chain to list it, which made calendars unbuildable on
  most real pairs and reported it as a data problem.
- Relicensing left nineteen surfaces claiming AGPL or MIT, including
  `optiondesk doctor` and a published JSON schema description.

### Verification

Three agents recomputed the arithmetic against implementations written from
the definitions rather than from this source. What held, measured: all
twenty-three payoff analyses from their own legs, probability and tail
statistics to 5.75e-11, sixteen Greeks to 9.95e-13 with every scaling
convention confirmed, put-call parity to 6.55 double epsilon across 40,040
pairs, exposure to 3.5e-16, R-hat to 0.00e+00, the ranking to 0.00e+00.

Five tests in this repository were found to pass against deliberately
broken code, all caught by the mutation harness and none by review.

### Counts

926 tests, 74 mutations, zero survivors, four equivalent mutants each
argued in the harness.

## 0.1.0, 2026-08-30

First public release. Seventeen structures, sixteen Greeks, dealer
positioning, GARCH-t simulation, backtests with modelled premiums, a paper
forward test, a local dashboard, six skills, six commands, two agents and
an MCP server.
