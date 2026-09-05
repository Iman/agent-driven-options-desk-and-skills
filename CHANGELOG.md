# Changelog

Dates are the day the work landed. Figures quoted here were measured on one
live SPY chain, 2026-10-16 expiry with 2026-12-18 also on disk, unless the
entry says otherwise.

## Unreleased

- The maths printed beside each dashboard panel now matches the code that
  made the numbers. A line-by-line review found thirteen sentences that did
  not: the simulation block printed the engine's default chains, draws and
  burn-in for every run because it read a key the artifact never carried,
  and printed a default path count the same way; the realised-volatility
  formula described the backtest's centred estimator, not the simulation's
  uncentred one; the pipeline figure joined greeks to exposure when
  exposure reads the chain; the caption said the page reads every artifact
  while the forward ledger was never read; and the mid, band, unlimited,
  region, open-interest ratio and observation-count sentences each
  overstated the code. The artifact now records the paths requested, the
  page shows each backtest's own buy-and-hold figure beside its row, and a
  ledger panel renders forward_ledger.json when it exists.
- The local MCP server lists a title and the four annotation hints for
  every tool, and an output schema for the two whose shape is fixed. A
  refusal names its true cause: demo mode, a missing dependency, a missing
  key, or unaccepted provider terms, in place of one string for all four.
  Error results carry the disclaimer that success results carry.
- The desk-watch, desk-risk and desk-test commands no longer print a bare
  flag when the optional second argument is omitted; the default is in the
  command line and the flag is added only when a value was given.
- The greeks, positioning and strategy skills say that the local desk does
  not gate the data_source name of user-supplied data, and that the
  provider's terms are the user's responsibility. The hosted service blocks
  Yahoo, yfinance and Alpha Vantage names; the local desk does not.
- The dashboard folds per-row import repairs into one line per repair, with
  the row ranges, so a chain with hundreds of bid-and-ask rows no longer
  prints hundreds of identical notes above the first chart. Artifacts and
  MCP repair lists are unchanged.
- The dashboard header names the artifact file, not the directory that
  holds it, so one machine's layout no longer appears on the page.
- The implied volatility solver refuses the top edge of a flat band. Deep
  in or out of the money, a quote within 1e-6 of intrinsic reprices at
  every volatility from IV_MIN up to the point where vega has just cleared
  MIN_VEGA, and the solver returned that point: on a grid of 1440
  contracts, 43 came back 0.001 to 0.07 above the truth, the worst a put at
  S=50 K=90 T=1 returning 0.1175 for a true 0.05 with vega 2.6e-27 there.
  A root is now accepted only when a step of SIGMA_RESOLUTION either way
  takes the model price out of the tolerance band, so a returned volatility
  is within 0.005 of every volatility that reprices the quote. Checking
  one side was measured and is not enough: at the worst case the step up
  moved the price by 2.8e-6 and the step down by 3e-7. After the change
  the same grid returns nothing more than 0.0016 from the truth.
- The backtest prices its model chain over the trading days it holds.
  holding_days indexes trading-day closes and the statistics annualise by
  252 / holding_days, but the chain was priced at holding_days / 365.
  Measured: an at the money straddle at 18 percent volatility was 4.1186
  against 4.9573 at 30 / 252, so entry premiums were about 17 percent low
  on every trade of every backtest. The chain is now priced at
  holding_days / 252 and states its life in calendar days so the
  expected-move band lands on the same t. Backtest artifacts written
  before this carry the old premiums, and the FAQ's 47 percent per trade
  figure was measured on one of them.
- Two-expiry plans carry net Greeks, friction and a probability of profit,
  as the schema, docs/CAPABILITIES.md and the strategy skill said all
  along; every calendar, diagonal and ratio diagonal plan wrote all three
  as null. Each leg is now priced at its own expiry and its own volatility
  (on the fixture pair: net vega 4.402 that way, exactly zero at the near
  expiry), friction is the same arithmetic on the same quotes, and the
  probability is the lognormal mass of the profitable part of the marking
  curve at the near expiry under the near chain's at-the-money volatility,
  integrated numerically because that curve has no closed form. The method
  is stated in the plan's notes and its model field, and the comparison
  can now rank these structures.
- The simulation's function docstring and loop comment still said paths
  came in antithetic pairs while the module docstring and the code said
  independent draws; the words now match the code, and an odd path count
  is no longer rounded down. The guard test correlated the even and odd
  entries of the SORTED terminal list, which reads +0.9966 on honest paths
  and +0.9983 on mirrored ones, so it could not see the thing it guarded.
  The engine keeps generation order in terminal_by_path and the test
  asserts consecutive paths correlate near zero, which mirrored pairs fail
  at -0.99.
- One mutation for each of the four, so the harness has eighty-five.

## Unreleased, 2026-09-03

The dashboard now shows its own arithmetic, and the screenshots come from a
script rather than a hand.

- A pipeline figure at the top of the dashboard: every command, the
  artifact it writes, and which artifact feeds which, drawn as inline SVG in
  the page's palette so it renders offline and follows the theme.
- A printed maths block under each section: the Black-Scholes-Merton model
  and the solver's acceptance rule, dealer gamma exposure with its sign
  convention and max pain, the smile figures and the expected move, the
  payoff engine and the lognormal law behind P(profit), time-spread marking
  and the two ratio columns, GARCH-t by MCMC with the diagnostics and the
  two tail figures, and the backtest's block-aware tests. Every constant is
  read from the engine and a test holds the two together.
- `scripts/screenshots.py` captures every section, panel and chart from a
  live dashboard, clipped to the element's own box, and rewrites
  `docs/SCREENSHOTS.md`. The README's images and figures were refreshed
  from a 2026-09-03 run: SPY at 2026-10-16, 394 contracts, 10 fallbacks.
- A second plugin, `option-desk-hosted`, in both marketplaces: the four
  hosted-safe skills and the remote Streamable HTTP MCP at
  optiondesk.avidquant.com, for claude.ai, ChatGPT and Codex users with no
  local install. Kept apart from the local plugin because the two servers
  expose tools with the same names.
- PRIVACY.md now describes the hosted service and points at its own
  policy; it had said the project has no servers. DISCLAIMER.md no longer
  states its regulated-status and indemnity sections twice.

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
