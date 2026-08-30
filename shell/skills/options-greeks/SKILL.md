---
name: options-greeks
description: Retrieve an option chain from free market data and compute the full first to third order Greek ladder (delta, gamma, vega, theta, rho, lambda, vanna, vomma, charm, veta, speed, zomma, color, ultima, dual delta, dual gamma) for any US listed underlying. Use when the user asks about option Greeks, an option chain, implied volatility by strike, delta or gamma exposure, theta decay, vega risk, or how a strike or expiry compares. Not for order placement and not for recommendations.
---

# Option Greeks

Two commands. The first fetches a chain and writes a snapshot, the second
turns that snapshot into a Greek ladder. Both write a schema-validated JSON
artifact and print a JSON summary. Read the summary, cite the artifact path,
and do not re-derive numbers yourself.

## When to use

Use for questions about option pricing sensitivities: what is the delta of a
strike, where gamma peaks, how much theta a position bleeds per day, what
vega exposure looks like across the chain, how implied volatility varies by
strike, or what a specific contract is worth under Black-Scholes-Merton.

Do not use for order placement, position sizing against a live account, or
anything that amounts to a recommendation to trade.

## Run it

```
optiondesk chain SPY
optiondesk greeks
```

`chain` takes `--expiry YYYY-MM-DD` (default: nearest listed),
`--dividend-yield` as a decimal, and `--rate` to override the fetched
13-week T-bill rate. `greeks` takes `--snapshot PATH` (default: the most
recent snapshot), `--band` to widen or narrow the strike window around spot
(0.10 by default, 0 keeps every strike) and `--type call|put|both`.

`optiondesk doctor` reports which providers and which analytics engine are
available, and where artifacts are written.

## What comes back

The `greeks` summary carries the artifact path, the number of rows graded,
the skip counts, and an at-the-money sample. The artifact carries one row per
contract with all sixteen Greeks plus price, implied volatility, moneyness
and days to expiry, and a `units` block that states the unit of every field.

## Units, because they are the usual source of a wrong answer

Volatility is per 1.00, so 0.20 means 20 percent. Vega is per 1.00 of
volatility, so divide by 100 for the conventional per-point figure. Theta,
charm, veta and color are all per calendar day of time passing, so theta is
normally negative for a long option. Delta and gamma are per 1.0 of
underlying move.

## Rules you must follow when reporting

Check `degraded` in the artifact meta. When it is true, say so and give the
reason before giving any number.

Contracts with no usable implied volatility are skipped and counted in
`skipped.no_iv`. Never fill in a volatility to make the ladder look
complete, and never present a skipped strike as if it were graded.

Prices here are Black-Scholes-Merton model values computed from delayed
third-party quotes. They are not tradable prices and not fills. Say so when
presenting them.

This is research output, not investment advice, not a recommendation and not
a solicitation. Do not phrase results as what the user should buy or sell.
See DISCLAIMER.md at the repository root.

## Failure modes worth recognising

If the summary reports the analytics engine is missing, the ladder cannot be
computed. Tell the user to install `optiondesk-engine`, and mention that it
is licensed AGPL-3.0 separately from the MIT shell.

If no provider is available, the message names each candidate and why it was
skipped, which is usually a missing `yfinance` install.

If a snapshot has a `spot_asof` older than the current session, the spot came
from the last settled close, not from today. Quote the date rather than
implying the number is live.
