"""Simulation: volatility models, posteriors, and forward path distributions.

Copyright (C) 2026 Iman Samizadeh. Licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate written agreement.

The pricing modules answer what a contract is worth under an assumed
volatility. These answer a different question: given what this underlying
has actually done, what is the distribution of where it lands, and what does
that imply for a position.

Standard library only, like the rest of the engine. The sampler is a plain
adaptive random-walk Metropolis rather than anything exotic, because a
sampler whose diagnostics can be read and checked is worth more than a
faster one whose failures are invisible.
"""

from optiondesk_engine.simulation.garch import (
    GarchPosterior,
    fit_garch_t,
    garch_log_likelihood,
)
from optiondesk_engine.simulation.paths import (
    position_distribution,
    simulate_paths,
    terminal_risk,
)

__all__ = ["fit_garch_t", "garch_log_likelihood", "GarchPosterior",
           "simulate_paths", "terminal_risk", "position_distribution"]
