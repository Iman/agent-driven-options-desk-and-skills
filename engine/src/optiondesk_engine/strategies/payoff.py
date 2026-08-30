"""Expiry payoff engine for multi-leg option strategies.

Copyright (C) 2026 Iman Samizadeh. Licensed under AGPL-3.0-only.
Ported from smartsheep.witty.strategies.payoff.

Every strategy in the playbook is a list of legs at a single expiry. This
module computes what a risk graph shows: net debit or credit, breakevens,
maximum gain, maximum loss, and the closed-form probability and tail
statistics that follow from a lognormal settlement model.

Prices are in the underlying's quote units throughout. Nothing here knows
about contract multipliers or currency: multiply outside if you need to.
That keeps the arithmetic auditable and stops a 100x from being applied
twice, which is the single most common way a position size goes wrong.
"""

import math

INF = float("inf")

_KINDS = ("call", "put", "underlying")
DAYS_PER_YEAR = 365.0


class Leg:
    """One leg of a strategy.

    kind    "call", "put" or "underlying"
    side    +1 long (bought), -1 short (sold or written)
    price   premium per unit for options, entry price for the underlying
    strike  strike price, required for option legs
    qty     contracts, or deal size multiplier
    ref     the source contract dict from the chain snapshot, kept so the
            friction model can read the real bid and ask later
    """

    def __init__(self, kind, side, price, strike=None, qty=1.0, ref=None):
        if kind not in _KINDS:
            raise ValueError("kind must be one of {}".format(_KINDS))
        if side not in (1, -1):
            raise ValueError("side must be +1 (long) or -1 (short)")
        if kind != "underlying" and strike is None:
            raise ValueError("option legs need a strike")
        self.kind = kind
        self.side = side
        self.price = float(price)
        self.strike = None if strike is None else float(strike)
        self.qty = float(qty)
        self.ref = ref

    def pnl_at_expiry(self, price):
        if self.kind == "call":
            value = max(price - self.strike, 0.0)
        elif self.kind == "put":
            value = max(self.strike - price, 0.0)
        else:
            value = price
        return self.side * self.qty * (value - self.price)

    def as_dict(self):
        ref = self.ref or {}
        return {
            "kind": self.kind,
            "side": "long" if self.side > 0 else "short",
            "strike": self.strike,
            "price": self.price,
            "qty": self.qty,
            "symbol": ref.get("symbol"),
            "bid": ref.get("bid"),
            "ask": ref.get("ask"),
            "iv": ref.get("iv"),
            "open_interest": ref.get("open_interest"),
            "volume": ref.get("volume"),
        }

    def __repr__(self):
        side = "long" if self.side > 0 else "short"
        if self.kind == "underlying":
            return "Leg({} underlying @ {:g} x{:g})".format(
                side, self.price, self.qty)
        return "Leg({} {} {:g} @ {:g} x{:g})".format(
            side, self.kind, self.strike, self.price, self.qty)


def pnl_at_expiry(legs, price):
    """Total strategy profit or loss if the underlying settles at price."""
    return sum(leg.pnl_at_expiry(price) for leg in legs)


def net_option_cash(legs):
    """Cash from the option legs at the moment the trade is opened.

    Positive is a credit received, negative is a debit paid. The underlying
    leg is excluded on purpose: the debit or credit label describes the
    option transaction, so a covered call is a credit trade even though
    stock was bought at some earlier point.
    """
    return sum(-leg.side * leg.qty * leg.price
               for leg in legs if leg.kind != "underlying")


def _slopes(legs):
    """Profit slope per point below the lowest and above the highest strike."""
    left = right = 0.0
    for leg in legs:
        if leg.kind == "call":
            right += leg.side * leg.qty
        elif leg.kind == "put":
            left -= leg.side * leg.qty
        else:
            left += leg.side * leg.qty
            right += leg.side * leg.qty
    return left, right


def analyze(legs, spot=None):
    """Risk graph metrics for a single expiry strategy.

    Returns net_cash, trade_type, breakevens, max_gain, max_loss and
    reward_risk. max_gain is INF and max_loss is -INF where the position is
    genuinely unbounded, which is a fact about the trade and must not be
    rounded down to a comfortable number.
    """
    if not legs:
        raise ValueError("no legs")

    strikes = sorted({leg.strike for leg in legs if leg.strike is not None})
    left_slope, right_slope = _slopes(legs)

    # Expiry P/L is piecewise linear with kinks only at strikes, so
    # evaluating at zero, at every strike, and one point beyond the last
    # strike pins the entire graph down.
    right_anchor = (strikes[-1] if strikes else (spot or 100.0)) + 1.0
    xs = [0.0] + strikes + [right_anchor]
    ys = [pnl_at_expiry(legs, x) for x in xs]

    finite_candidates = ys[:-1] if strikes else ys
    max_gain = max(finite_candidates)
    max_loss = min(finite_candidates)
    if right_slope > 1e-12:
        max_gain = INF
    if right_slope < -1e-12:
        max_loss = -INF
    # A position that keeps losing as the underlying falls is unbounded on
    # the left in practical terms, bounded only by the underlying reaching
    # zero. That bound is real, so the left side stays finite, and ys[0]
    # already carries the value at zero.

    breakevens = []
    for (x0, y0), (x1, y1) in zip(zip(xs, ys), zip(xs[1:], ys[1:])):
        if y0 == 0.0:
            breakevens.append(x0)
        if (y0 < 0 < y1) or (y1 < 0 < y0):
            breakevens.append(x0 - y0 * (x1 - x0) / (y1 - y0))
    x_last, y_last = xs[-1], ys[-1]
    if abs(right_slope) > 1e-12:
        crossing = x_last - y_last / right_slope
        if crossing >= x_last:
            breakevens.append(crossing)
    if y_last == 0.0 and abs(right_slope) <= 1e-12:
        breakevens.append(x_last)
    breakevens = sorted({round(b, 6) for b in breakevens if b >= 0})

    net_cash = net_option_cash(legs)
    result = {
        "net_cash": net_cash,
        "trade_type": "credit" if net_cash > 0 else "debit",
        "breakevens": breakevens,
        "max_gain": max_gain,
        "max_loss": max_loss,
        "reward_risk": None,
    }
    # Reward to risk only means something when there is a loss to risk. A
    # structure whose worst outcome is a profit has none, and dividing the
    # best profit by the smallest profit and calling it reward over risk
    # produced a 6.0 on a position that cannot lose.
    if (max_gain != INF and max_loss not in (0.0, -INF)
            and max_loss < 0.0):
        result["reward_risk"] = max_gain / abs(max_loss)
    result["risk_free"] = bool(max_loss is not None
                               and max_loss != -INF and max_loss >= 0.0)
    return result


def _lognormal_cdf_factory(spot, iv, days, drift):
    """Settlement distribution under the current implied volatility."""
    t = days / DAYS_PER_YEAR
    sd = iv * math.sqrt(t)
    m = math.log(spot) + (drift - 0.5 * iv * iv) * t

    def cdf(price):
        if price <= 0:
            return 0.0
        return 0.5 * (1.0 + math.erf(
            (math.log(price) - m) / (sd * math.sqrt(2.0))))

    def survival(price):
        """P(S > price), computed without the cancellation in 1 - cdf.

        At a large volatility times horizon, cdf(lo) rounds to exactly 1.0
        and 1 - cdf collapses to zero, deleting the region that carries the
        entire expectation. Measured: a long call worth 99.5 in expectation
        was reported as a 0.5 expected loss with probability of loss 1.0.
        erfc has no such cancellation.
        """
        if price <= 0:
            return 1.0
        return 0.5 * math.erfc((math.log(price) - m) / (sd * math.sqrt(2.0)))

    return cdf, m, sd, survival


def _usable(spot, iv, days):
    """Every input must be a finite positive number.

    NaN defeats the obvious guard: "not nan" is False and "nan <= 0" is
    False, so a NaN volatility passed straight through and produced a NaN
    probability alongside a fabricated expected loss of exactly zero.
    """
    for value in (spot, iv, days):
        if value is None:
            return False
        try:
            number = float(value)
        except (TypeError, ValueError):
            return False
        if not math.isfinite(number) or number <= 0:
            return False
    return True


def probability_of_profit(legs, spot, iv, days, drift=0.0):
    """Probability the strategy expires profitable, or None.

    The payoff is piecewise linear and breakevens split the price axis into
    profitable and unprofitable regions, so this is the lognormal mass of
    the profitable ones. It is a model estimate under today's implied
    volatility with no directional drift, not a forecast, and certainly not
    a win rate anyone has observed.
    """
    if not _usable(spot, iv, days):
        return None
    cdf, _, _, survival = _lognormal_cdf_factory(spot, iv, days, drift)

    metrics = analyze(legs, spot=spot)
    bounds = [b for b in metrics["breakevens"] if b > 0]
    edges = [0.0] + sorted(bounds) + [INF]
    prob = 0.0
    for lo, hi in zip(edges, edges[1:]):
        if hi == INF:
            sample = max(lo * 1.01, spot * 4.0) if lo > 0 else spot * 4.0
        elif lo == 0.0:
            sample = hi / 2.0
        else:
            sample = (lo + hi) / 2.0
        if pnl_at_expiry(legs, sample) > 0:
            if hi == INF:
                prob += survival(lo)
            else:
                prob += cdf(hi) - cdf(lo)
    return min(max(prob, 0.0), 1.0)


def tail_metrics(legs, spot, iv, days, drift=0.0):
    """Closed-form loss statistics under the same lognormal model.

    Between consecutive boundary points the expiry P/L is linear in S, and
    under a lognormal both the probability of a region and the partial
    expectation of S over it are closed form. That gives exact expected
    P/L, probability of loss and expected shortfall with no simulation and
    no sampling error.

    Returns p_loss, expected_loss (negative, the mean P/L across losing
    outcomes) and expected_pnl, or None when volatility or horizon is
    unusable.
    """
    if not _usable(spot, iv, days):
        return None
    try:
        cdf, m, sd, survival = _lognormal_cdf_factory(spot, iv, days,
                                                      drift)
    except (OverflowError, ValueError):
        return None

    def partial_expectation(price):
        """E[S 1{S < price}], the building block for a region's mean."""
        if price <= 0:
            return 0.0
        z = (math.log(price) - m - sd * sd) / sd
        return math.exp(m + 0.5 * sd * sd) * 0.5 * (
            1.0 + math.erf(z / math.sqrt(2.0)))

    metrics = analyze(legs, spot=spot)
    strikes = sorted({leg.strike for leg in legs if leg.strike is not None})
    bounds = sorted(set([b for b in metrics["breakevens"] if b > 0]
                        + [k for k in strikes if k > 0]))
    edges = [0.0] + bounds + [INF]

    p_loss = 0.0
    expected_loss = 0.0
    expected_pnl = 0.0
    for lo, hi in zip(edges, edges[1:]):
        a = max(lo, 1e-9)
        b = a * 2.0 if hi == INF else hi
        pa, pb = pnl_at_expiry(legs, a), pnl_at_expiry(legs, b)
        slope = (pb - pa) / (b - a) if b != a else 0.0
        intercept = pa - slope * a
        if hi == INF:
            prob = survival(lo)
            expectation = math.exp(m + 0.5 * sd * sd) - partial_expectation(lo)
        else:
            prob = cdf(hi) - cdf(lo)
            expectation = partial_expectation(hi) - partial_expectation(lo)
        if prob <= 0:
            continue
        region_ev = slope * expectation + intercept * prob
        expected_pnl += region_ev
        sample = lo * 1.5 + 1.0 if hi == INF else (lo + hi) / 2.0
        if pnl_at_expiry(legs, sample) < 0:
            p_loss += prob
            expected_loss += region_ev

    if not (math.isfinite(p_loss) and math.isfinite(expected_pnl)):
        return None
    return {
        "p_loss": min(max(p_loss, 0.0), 1.0),
        "expected_loss": (expected_loss / p_loss) if p_loss > 1e-9 else 0.0,
        "expected_pnl": expected_pnl,
    }


def payoff_curve(legs, lo, hi, points=200):
    """(prices, pnls) across [lo, hi], with exact strikes included.

    The strikes are inserted so the kinks render sharply instead of being
    rounded off by whatever grid resolution the caller picked.
    """
    if points < 2:
        raise ValueError("points must be >= 2")
    if hi <= lo:
        raise ValueError("hi must be above lo")
    step = (hi - lo) / (points - 1)
    xs = [lo + i * step for i in range(points)]
    for strike in {leg.strike for leg in legs if leg.strike is not None}:
        if lo < strike < hi:
            xs.append(strike)
    xs = sorted(xs)
    return xs, [pnl_at_expiry(legs, x) for x in xs]
