# Provenance and third-party material

This file records where code, data and assets in this project came from, so
that a licence audit can be done without guesswork. It is updated in the
same change as any material it describes.

Three categories, and the difference between them is legal, not stylistic:

- **Inherited**: the copyright holder's own code, relicensed here.
- **Vendored**: someone else's code, shipped as-is under a permissive
  licence, with attribution.
- **Referenced**: read for ideas, reimplemented from scratch. No lines
  taken. Used where a licence forbids copying, or where the original is in
  another language.

## Inherited from the author's own repositories

All of the following were authored by Iman Samizadeh in the `001-qaunt`
repository (package `smartsheep.witty`, originally marked proprietary) and
are relicensed here under AGPL-3.0 by the copyright holder.

Pricing:

- `engine/src/optiondesk_engine/pricing/black_scholes.py` derives from
  `witty/models/pricing/greeks_full.py` (the `_pdf`, `_cdf`, `bs_price`
  helpers and the module constants) and from the Newton-Raphson implied
  volatility solver in `witty/apps/pullers/us_options_pull.py`. An earlier
  version of this file credited `witty/models/pricing/black_scholes.py`,
  which a line-level comparison against that file put at roughly 3 percent
  similarity with no shared function names. The credit above is the
  corrected one. That comparison was made against a repository that is not
  distributed with this one, so it cannot be re-run from here: anyone
  auditing the attribution has to hold both trees.
- `engine/src/optiondesk_engine/pricing/greeks_full.py` derives from
  `witty/models/pricing/greeks_full.py`, extended here to carry a
  continuous dividend yield.

Strategies, ported in full and adapted to this project's chain contract:

- `engine/src/optiondesk_engine/strategies/payoff.py` from
  `witty/strategies/payoff.py`.
- `engine/src/optiondesk_engine/strategies/outlook.py` from
  `witty/strategies/outlook.py`.
- `engine/src/optiondesk_engine/strategies/playbook.py` from
  `witty/strategies/playbook.py`, with the iron butterfly and long call
  butterfly builders added here.
- `engine/src/optiondesk_engine/strategies/friction.py` from
  `witty/strategies/friction.py`.

Analytics:

- `engine/src/optiondesk_engine/analytics/exposure.py` follows the dealer
  gamma work in `witty/analytics/gex.py` and `witty/analytics/gamma_regime.py`
  in concept, reimplemented against this project's contract.

Shell:

- `shell/src/optiondesk/providers/yahoo.py` derives from the chain retrieval
  in `witty/apps/pullers/us_options_pull.py`, published here under MIT by
  the copyright holder.

Earlier lineage, same author, not directly copied: `smartsheep.io/Options`
(`greek.py`, `ig.py`, `igclient.py`, `igstream.py`). Superseded by witty.

## Vendored third-party assets

- `shell/src/optiondesk/dashboard/static/echarts.min.js`, Apache ECharts
  5.4.3, Apache-2.0, retrieved from cdnjs. Vendored rather than loaded from
  a CDN so the dashboard renders with no network access and no third-party
  request from the viewer's browser. Unmodified upstream build.

  Note on the repository formatting rules: this file contains non-ASCII
  characters and four em dashes in its own upstream strings. Vendored
  upstream assets are exempt from those rules for the same reason
  `engine/LICENSE` is: they must stay byte-identical to be what they claim
  to be. The rules apply to everything this project writes.

## Runtime dependencies

- `yfinance`, Apache-2.0, optional, used by the Yahoo provider. It pulls a
  transitive tree including `requests` (Apache-2.0) and `certifi`
  (MPL-2.0). MPL-2.0 is a weak file-level copyleft that does not affect
  this project's own licensing, but it sits outside the permissive
  allow-list stated in LICENSES.md and is recorded here for that reason.
- `fastapi` and `uvicorn`, MIT, optional, for the dashboard.
- `jsonschema`, MIT, optional. When present it replaces the built-in
  fallback validator.
- `pytest`, MIT, development only.

The engine itself has no runtime dependency outside the Python standard
library, and no network access of any kind.

## Data sources evaluated for a local corpus

These were reviewed as offline data for backtesting across asset classes.
Their licences govern what may be done with them and none of their code is
in this tree.

- `financial-data` (FutureSharks), GPL-3.0, held in a local checkout.
  Twenty-five
  instruments of one-minute bars from 2005-01 to 2020-05, roughly 100
  million rows across six asset classes including bond futures, energy,
  metals and agriculture. The package code is GPL and stays out of the
  tree entirely; the CSV files may be read through a reader written here.
  That separation is what keeps commercial licensing of the engine
  possible.
- `finance-vix` (datasets), ODC-PDDL-1.0, held in a local checkout. VIX
  daily history from
  1990 to 2021-08-19. Public domain dedication, so usable directly. Five
  years stale; the repository ships its own CBOE refresh pipeline.
- `quant-trading`, Apache-2.0, held in a local checkout.
  `data/stoxx50.xlsx`. Permissive, attribution required.

## Referenced for ideas, reimplemented here

No lines from any of these are present. Where a licence is absent, the work
is all rights reserved by default and copying is not permitted regardless of
how it is published.

- `Implied-Volatility-Modelling` (in `algos/volatility`), no licence.
  Volatility surface fitting. Relevant to a measured gap: a flat
  at-the-money volatility understates the downside wing.
- `gammascalping` (JVfisher), no licence, and bound to the Interactive
  Brokers API. Gamma scalping state machine. The Greeks needed to drive one
  are verified correct here; no such strategy exists in this tree yet.
- `volbooster` (msilb), MIT, Scala. Long volatility state machine design.
  MIT would permit copying, but it is another language, so any use is a
  reimplementation.
- `ESG-Rating-and-Financial-performance-of-SP-500`, no licence. The keyless
  Yahoo sustainability acquisition path as an idea only; any ESG puller
  here would be written from scratch.
- `quant-trading` Oil Money project, Apache-2.0. Commodity to currency
  regression, with a train and test split and a null model, which is more
  than most published strategy code carries.
- `graph-theory` (je-suis-tm), Apache-2.0, and `bellman-ford-forex`
  (kcmoffat), no licence. Triangular arbitrage on currency graphs. A
  different problem from options; listed so a later reader knows it was
  considered.
- `voptgen` (maurya373), GPL-3.0. Excluded from the tree for the same
  reason as `financial-data`'s package code.
- `Bellman-Form-BTCe-Arbitrager` (a-r-d) and `FX-Analysis` (Ste11a-star),
  no licence. Not used.
- `claude-trading-skills` (tradermonty), MIT, Copyright 2026 TraderMonty.
  Named at the outset as an example of what a trading skill set for an
  agent looks like, alongside `marketingskills` (coreyhaines31) and
  `LangAlpha` (ginlix-ai). Nothing was copied from any of them, and that
  is a measurement rather than a recollection: an eight-word shingle
  comparison against all 4,844 markdown and Python files in
  `claude-trading-skills` found no shared run in any skill, workflow or
  document here, and the only matches anywhere in the tree were import
  lines, HTML boilerplate, and the standard idiom for computing a mean.
  The largest overlap in any file was 1.7 percent, all of it of that kind.

  Its MIT terms would have permitted reuse with attribution, so the
  absence of reuse is a fact about how this was built and not about what
  the licence allowed. Recorded here so that anyone asking the question
  later finds the answer instead of having to redo the comparison.

  One thing worth knowing for anyone running both: its
  `options-strategy-advisor` claims six of the same trigger phrases as the
  options skills here, including iron condors, covered calls, protective
  puts, spreads, Greeks and simulation. The two are not equivalent, since
  that one is a Black-Scholes teaching simulator with no chain behind it,
  so having both installed makes which one answers a matter of chance.

## Market data is not covered by this licence

No market data is vendored into this repository. Data is fetched at runtime
and governed by each provider's terms, not by this project's licences. See
DISCLAIMER.md section 5.
