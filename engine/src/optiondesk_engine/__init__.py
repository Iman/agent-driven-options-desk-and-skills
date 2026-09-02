"""The analytics engine.

Copyright (C) 2026 Iman Samizadeh.

Licensed under the PolyForm Noncommercial License 1.0.0. Any noncommercial
purpose is permitted, including personal study, research, and use by
charitable, educational, public research, health, environmental and
government organisations. Commercial use, which includes any use for
commercial advantage or private monetary compensation, requires a separate
written agreement with the copyright holder.

The full terms are in LICENSE at the root of this package and at
https://polyformproject.org/licenses/noncommercial/1.0.0

This is research software. It is not investment advice, not a
recommendation and not a solicitation. See DISCLAIMER.md.
"""

__version__ = "0.3.0"
LICENSE = "PolyForm-Noncommercial-1.0.0"

from optiondesk_engine.pricing.black_scholes import (
    bs_price,
    implied_vol,
)
from optiondesk_engine.pricing.greeks_full import (
    GREEK_KEYS,
    all_greeks,
)
from optiondesk_engine.backtest import (
    bootstrap_mean_interval,
    performance_stats,
    permutation_p_value,
    run_backtest,
)
from optiondesk_engine.strategies import (
    PLAYBOOK,
    Leg,
    Outlook,
    analyze,
    build,
    describe,
    payoff_curve,
    plan_friction,
    probability_of_profit,
    recommend,
    split_chain,
    tail_metrics,
)

__all__ = ["bs_price", "implied_vol", "all_greeks", "GREEK_KEYS",
           "PLAYBOOK", "Leg", "Outlook", "analyze", "build", "describe",
           "payoff_curve", "plan_friction", "probability_of_profit",
           "recommend", "split_chain", "tail_metrics",
           "run_backtest", "performance_stats", "permutation_p_value",
           "bootstrap_mean_interval",
           "__version__", "LICENSE"]
