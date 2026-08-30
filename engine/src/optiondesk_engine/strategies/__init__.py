"""Multi-leg option strategy construction, payoff analysis and friction.

Copyright (C) 2026 Iman Samizadeh. Licensed under AGPL-3.0-only.

Ported from the author's prior work in the 001-qaunt repository
(smartsheep.witty.strategies) and relicensed here by the copyright holder.
See THIRD-PARTY.md.

Three layers, deliberately separable:

  payoff    the expiry P/L engine. Legs in, risk graph out: net debit or
            credit, breakevens, max gain, max loss, reward to risk, and
            closed-form probability and tail statistics under a lognormal
            settlement model
  outlook   the five-direction framework the playbook is organised around,
            anchored on the one standard deviation expected move
  playbook  the strategy constructors that turn a chain snapshot into a
            concrete set of legs, plus the registry that says which
            outlook each strategy is built for
  friction  what the round trip actually costs at the quoted spreads,
            because a payoff computed at mid is not a payoff anyone gets
"""

from optiondesk_engine.strategies.friction import plan_friction
from optiondesk_engine.strategies.outlook import (
    Outlook,
    chain_iv,
    classify_target,
    expected_move,
    one_sd_band,
)
from optiondesk_engine.strategies.payoff import (
    INF,
    Leg,
    analyze,
    net_option_cash,
    payoff_curve,
    pnl_at_expiry,
    probability_of_profit,
    tail_metrics,
)
from optiondesk_engine.strategies.timespread import (
    TimeLeg,
    build_time_spread,
)
from optiondesk_engine.strategies.playbook import (
    PLAYBOOK,
    build,
    describe,
    recommend,
    split_chain,
)

__all__ = [
    "INF", "Leg", "analyze", "net_option_cash", "payoff_curve",
    "pnl_at_expiry", "probability_of_profit", "tail_metrics",
    "Outlook", "chain_iv", "classify_target", "expected_move", "one_sd_band",
    "PLAYBOOK", "build", "describe", "recommend", "split_chain",
    "TimeLeg", "build_time_spread",
    "plan_friction",
]
