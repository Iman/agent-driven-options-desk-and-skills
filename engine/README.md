# optiondesk-engine

Pricing and analytics for the option desk. Licensed under the PolyForm
Noncommercial License 1.0.0, the same terms as the rest of the project. See
`LICENSE` for the full text and `../LICENSES.md` for what that permits.

The default engine uses the standard library and has no data providers.
The optional `quantlib` extra adds QuantLib 1.43 for explicit American or
European vanilla pricing. Its public request function uses a fresh worker
process to isolate global settings. Neither pricing path fetches market data.
See [backend integration](../docs/BACKENDS.md) for the model conventions.

The shell fetches data and writes artifacts. The engine turns the data
into analytics. Neither imports the other's internals: the shell reaches the
engine through one adapter module, and degrades with an explicit message when
the engine is not installed.

Current contents:

- `pricing/`: European Black-Scholes-Merton with a continuous dividend
  yield, a Newton-Raphson implied volatility solver with a bisection
  fallback that refuses prices carrying no volatility information, and the
  full analytic Greek ladder from first to third order in documented units.
  The optional QuantLib path reports prices and a convergence check; it does
  not replace the European Greek ladder.
- `strategies/`: the expiry payoff engine, the five-direction outlook
  framework, the structure playbook, and the friction and liquidity gate.
- `analytics/`: dealer gamma exposure with walls and flip levels, max pain,
  volatility smile geometry, and the structure ranking.
- `simulation/`: GARCH(1,1) with Student-t innovations sampled by adaptive
  random-walk Metropolis, posterior predictive paths, value at risk and
  expected shortfall, and position profit distributions.
- `backtest/`: the historical runner with modelled premiums, the
  performance and significance statistics, and forward-test marking.

Read DISCLAIMER.md at the repository root before using any of it. Modelled
premiums are not achievable prices.
