"""Chain-level analytics: positioning, exposure and pain.

Copyright (C) 2026 Iman Samizadeh. Licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate written agreement.

Where the pricing modules answer "what is this contract worth", these
answer "where is the open interest, and what does hedging it imply".
"""

from optiondesk_engine.analytics.exposure import (
    chain_exposure,
    max_pain,
)
from optiondesk_engine.analytics.compare import rank_strategies, score_plan
from optiondesk_engine.analytics.ranking import (
    FORMULA,
    MIN_ABS_PREMIUM,
    RR_CAP,
    SCORE_WEIGHTS,
    THIN_MULTIPLIER,
    VRP_TILT,
    rank_rows,
    row_from_comparison,
    score_row,
)
from optiondesk_engine.analytics.smile import smile_metrics

__all__ = ["chain_exposure", "max_pain", "smile_metrics", "rank_strategies",
           "score_plan", "score_row", "rank_rows", "row_from_comparison",
           "SCORE_WEIGHTS", "RR_CAP", "VRP_TILT", "THIN_MULTIPLIER",
           "MIN_ABS_PREMIUM", "FORMULA"]
