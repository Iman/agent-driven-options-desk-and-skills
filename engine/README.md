# optiondesk-engine

Pricing and analytics for the option desk. Licensed under the PolyForm
Noncommercial License 1.0.0, the same terms as the rest of the project. See
`LICENSE` for the full text and `../LICENSES.md` for what that permits.

The engine is pure computation. It has no network access, no data providers,
no file system layout opinions and no dependencies outside the standard
library. It takes numbers and returns numbers, which is what makes it testable
against closed-form and finite-difference benchmarks.

The shell fetches data and writes artifacts. The engine turns the data
into analytics. Neither imports the other's internals: the shell reaches the
engine through one adapter module, and degrades with an explicit message when
the engine is not installed.

Current contents:

- `pricing/`: European Black-Scholes-Merton with a continuous dividend
  yield, a Newton-Raphson implied volatility solver with a bisection
  fallback that refuses prices carrying no volatility information, and the
  full analytic Greek ladder from first to third order in documented units.
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
