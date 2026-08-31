"""Options on futures and on foreign exchange.

Copyright (C) 2026 Iman Samizadeh. Licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate written agreement.

WHAT THESE ARE, AND WHAT THEY ARE NOT FED BY. Black-76 prices an option on
a futures contract, and Garman-Kohlhagen prices an option on a currency
pair. Both are here as pricing capability for somebody bringing their own
data. No free provider this project ships against carries either chain:
probed on 2026-08-30, ES=F, CL=F, GC=F, EURUSD=X and ^TNX all return price
history and zero option expiries. So nothing in the desk pipeline calls
these functions today, and none of the CLI commands can feed them. Use them
directly, with quotes you have obtained yourself.

That is stated plainly because the alternative is a module that looks like
part of a working pipeline and silently is not.

WHY THEY ARE REPARAMETERISATIONS RATHER THAN NEW FORMULAE. Both models are
the same Black-Scholes-Merton equation under a substitution:

    Black-76           an option on a future is BSM with the carry rate set
                       equal to the discount rate, because a futures
                       position costs nothing to hold. Substitute S = F and
                       q = r.

    Garman-Kohlhagen   an option on a currency is BSM where the foreign
                       interest rate plays the part of a dividend yield,
                       because holding the foreign currency earns it.
                       Substitute q = r_foreign.

Writing them as substitutions means they inherit the guards, the validation
and the tested numerics of `bs_price` rather than repeating them, and it
means a fix to the core reaches all three. The tests do not take the
substitution on trust: each is checked against the closed form written out
independently.

WHAT THE GREEKS MEAN HERE. `all_greeks` under these substitutions returns
derivatives with respect to the quantity substituted in, which is not an
equity spot. For Black-76 delta is the change per unit of the futures
price, and hedging it means trading futures, not the underlying commodity.
For Garman-Kohlhagen delta is per unit of the spot exchange rate, quoted in
domestic currency per unit of foreign, and the FX market has several other
delta conventions that this is not. Read the docstring of each function for
what it hands back.
"""

import math

from optiondesk_engine.pricing.black_scholes import (
    DAYS_PER_YEAR,
    DEFAULT_R,
    _cdf,
    bs_price,
    implied_vol,
)
from optiondesk_engine.pricing.greeks_full import all_greeks

__all__ = [
    "black76_price",
    "black76_greeks",
    "black76_implied_vol",
    "garman_kohlhagen_price",
    "garman_kohlhagen_greeks",
    "garman_kohlhagen_implied_vol",
    "forward_from_spot",
    "UNFED",
]

UNFED = (
    "No data provider shipped with this project carries option chains for "
    "futures or foreign exchange. These functions price quotes you supply "
    "yourself."
)


# ------------------------------------------------------------- Black-76

def black76_price(future, strike, t, sigma, kind, r=DEFAULT_R):
    """Price an option on a futures contract.

    future  the futures price, not the spot price of the underlying
    strike  strike price
    t       years to expiry
    sigma   volatility of the futures price
    kind    "call" or "put"
    r       the discount rate

    A futures position requires no cash to hold, so there is no carry to
    pay and the drift of the future under the pricing measure is zero. That
    is the whole of the difference from the equity formula, and it appears
    here as the carry rate equalling the discount rate.
    """
    return bs_price(future, strike, t, sigma, kind, r, r)


def black76_greeks(future, strike, t, sigma, kind, r=DEFAULT_R):
    """The full Greek ladder for an option on a future.

    Every spot derivative is with respect to the FUTURES price. Delta is
    futures delta: hedging it means trading the future, and one unit of
    delta is one futures contract, not one unit of the physical.
    """
    greeks = all_greeks(future, strike, t, sigma, kind, r, r)
    greeks["underlying_is"] = "futures_price"
    return greeks


def black76_implied_vol(price, future, strike, t, kind, r=DEFAULT_R):
    """Solve volatility from a futures option price.

    Returns None when the price identifies no volatility, exactly as the
    equity solver does: a price dominated by intrinsic value reprices
    within tolerance at every volatility in the range, so it identifies
    none of them, and answering anyway would be an invention.
    """
    return implied_vol(price, future, strike, t, kind, r, r)


# ----------------------------------------------------- Garman-Kohlhagen

def garman_kohlhagen_price(spot, strike, t, sigma, kind,
                           r_domestic=DEFAULT_R, r_foreign=0.0):
    """Price a currency option.

    spot        the exchange rate, domestic currency per unit of foreign
    strike      strike in the same quotation
    t           years to expiry
    sigma       volatility of the exchange rate
    kind        "call" or "put", on the foreign currency
    r_domestic  the domestic interest rate, which discounts the payoff
    r_foreign   the foreign interest rate, earned by holding the foreign
                currency and therefore playing the part of a dividend yield

    Quotation matters more here than anywhere else in this module. A call
    on EURUSD at 1.10 is a call on the euro, and the same contract seen
    from the other side is a put on the dollar with a strike of 1/1.10 and
    the two rates exchanged. This function does not know which side you
    mean; it prices what you pass.
    """
    return bs_price(spot, strike, t, sigma, kind, r_domestic, r_foreign)


def garman_kohlhagen_greeks(spot, strike, t, sigma, kind,
                            r_domestic=DEFAULT_R, r_foreign=0.0):
    """The full Greek ladder for a currency option.

    Delta is with respect to the spot exchange rate in the quotation given.
    The FX market quotes several other deltas, forward delta and premium
    adjusted delta among them, and this is none of those. Convert
    deliberately rather than assuming.
    """
    greeks = all_greeks(spot, strike, t, sigma, kind, r_domestic, r_foreign)
    greeks["underlying_is"] = "fx_spot"
    return greeks


def garman_kohlhagen_implied_vol(price, spot, strike, t, kind,
                                 r_domestic=DEFAULT_R, r_foreign=0.0):
    """Solve volatility from a currency option price."""
    return implied_vol(price, spot, strike, t, kind, r_domestic, r_foreign)


# ------------------------------------------------------------- helpers

def forward_from_spot(spot, t, r_domestic=DEFAULT_R, r_foreign=0.0):
    """The forward price implied by a spot and two rates.

    Provided so a caller holding a spot rate can price with Black-76
    deliberately, rather than passing a spot where a forward belongs. That
    substitution is silent, wrong by the whole carry, and worst at long
    expiries, which is where anyone reaches for a forward model.
    """
    if t < 0:
        raise ValueError("t must not be negative")
    return spot * math.exp((r_domestic - r_foreign) * t)
