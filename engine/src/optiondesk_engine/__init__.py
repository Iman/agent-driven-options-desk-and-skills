"""Option pricing and analytics engine.

Copyright (C) 2026 Iman Samizadeh

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU Affero General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option) any
later version.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for more
details.

You should have received a copy of the GNU Affero General Public License along
with this program. If not, see <https://www.gnu.org/licenses/>.

A separate commercial licence is available from the copyright holder.
"""

__version__ = "0.1.0"
LICENSE = "AGPL-3.0-only"

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
