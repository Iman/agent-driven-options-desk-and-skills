"""Historical and forward testing of option structures.

Copyright (C) 2026 Iman Samizadeh. Licensed under AGPL-3.0-only.

THE HONESTY RULE, CARRIED OVER FROM THE AUTHOR'S PRODUCTION DESK AND
ENFORCED IN CODE RATHER THAN ONLY IN DOCUMENTATION.

Nobody has a history of option chains here. What exists is a history of the
underlying. A backtest of an option structure therefore uses REAL
underlying closes and MODELLED premiums, and every result it produces
carries that fact in a field that cannot be dropped, because the difference
between a modelled premium and a fill is the difference between a backtest
and a fantasy.

What that means concretely, and what it forbids:

  - Entry and exit premiums come from Black-Scholes at an estimated
    volatility, not from a quote anyone could have traded.
  - There is no bid-ask spread in the premium unless a friction estimate is
    supplied, and the real spread is often wider than the modelled edge.
  - No slippage, no assignment, no early exercise, no borrow cost, no
    margin call, no gap through a strike overnight.
  - Survivorship and selection are not addressed at all.

A result from this module is a measurement of a rule against a price
history under a pricing model. It is not achievable profit and loss, and
the artifact says so in words that a reader cannot skip.
"""

from optiondesk_engine.backtest.forward import (
    mark_position,
    settle_position,
)
from optiondesk_engine.backtest.runner import run_backtest
from optiondesk_engine.backtest.stats import (
    bootstrap_mean_interval,
    performance_stats,
    permutation_p_value,
)

__all__ = ["run_backtest", "performance_stats", "permutation_p_value",
           "bootstrap_mean_interval", "mark_position", "settle_position"]
