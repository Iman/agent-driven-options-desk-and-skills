"""Chain-level analytics: positioning, exposure and pain.

Copyright (C) 2026 Iman Samizadeh. Licensed under AGPL-3.0-only.

Where the pricing modules answer "what is this contract worth", these
answer "where is the open interest, and what does hedging it imply".
"""

from optiondesk_engine.analytics.exposure import (
    chain_exposure,
    max_pain,
)
from optiondesk_engine.analytics.compare import rank_strategies, score_plan
from optiondesk_engine.analytics.smile import smile_metrics

__all__ = ["chain_exposure", "max_pain", "smile_metrics", "rank_strategies",
           "score_plan"]
