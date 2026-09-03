"""The arithmetic behind each panel, printed beside the panel.

WHY. A chart is a claim about numbers, and a reader who cannot see how the
numbers were made can only accept the chart or ignore it. The composite
panel already prints its formula. This module does the same for every
other section, in the same plain monospace form, and reads every constant
it quotes from the engine so the text cannot drift from the code that
produced the figures.

NOTATION. Nothing here is rendered by a mathematics library: the page works
offline from one vendored chart bundle and the hosted copy forbids
third-party scripts. So the notation is plain text, held to one convention
across every block: sqrt(x), exp(x), ln(x), N(x) for the standard normal
distribution function, x^2 for a power, x_t for a subscript, |x| for an
absolute value, and "sum over ..." for a sum.

Each block is a function of the constants dictionary from constants() and,
where it helps, of the artifact it describes, so a test can render a block
and compare each number in it with the engine module it came from.
"""

import html

from optiondesk import engine_bridge


def constants():
    """Every number the blocks quote, read from the engine.

    Returns None when the engine is not installed. The blocks then print
    each constant's name in place of its value: the shell has no business
    inventing a number the engine would have supplied.
    """
    if not engine_bridge.AVAILABLE:
        return None
    pricing = engine_bridge.pricing()
    analytics = engine_bridge.analytics()
    strategies = engine_bridge.strategies()
    simulation = engine_bridge.simulation()
    backtest = engine_bridge.backtest()
    return {
        "default_r": pricing.DEFAULT_R,
        "default_q": pricing.DEFAULT_Q,
        "days_per_year": pricing.DAYS_PER_YEAR,
        "iv_min": pricing.IV_MIN,
        "iv_max": pricing.IV_MAX,
        "min_vega": pricing.MIN_VEGA,
        "multiplier": analytics.exposure.CONTRACT_MULTIPLIER,
        "target_delta": analytics.smile.TARGET_DELTA,
        "delta_tolerance": analytics.smile.DELTA_TOLERANCE,
        "haircut": strategies.friction.HAIRCUT,
        "ok_max": strategies.friction.OK_MAX,
        "thin_max": strategies.friction.THIN_MAX,
        "max_rel_spread": strategies.friction.MAX_REL_SPREAD,
        "curve_points": strategies.timespread.CURVE_POINTS,
        "draws": simulation.garch.DEFAULT_DRAWS,
        "burn": simulation.garch.DEFAULT_BURN,
        "chains": simulation.garch.DEFAULT_CHAINS,
        "rhat_limit": simulation.garch.RHAT_LIMIT,
        "min_ess": simulation.garch.MIN_ESS,
        "paths": simulation.paths.DEFAULT_PATHS,
        "trading_days": backtest.stats.TRADING_DAYS,
        "lookback": backtest.runner.DEFAULT_LOOKBACK,
    }


def _value(c, key, spec="g"):
    """One constant formatted, or its name when the engine is absent."""
    if not c or c.get(key) is None:
        return key.upper()
    return format(c[key], spec)


def block(text, summary="The maths", open_by_default=True):
    """Wrap one block of plain-text arithmetic as a collapsible note.

    Open by default, for the same reason the composite prints its formula
    without being asked: an ordering whose arithmetic is hidden cannot be
    disagreed with. The reader who has read it once can fold it.
    """
    return ("<details class='maths'{}><summary>{}</summary>"
            "<pre class='cmds maths'>{}</pre></details>").format(
                " open" if open_by_default else "",
                html.escape(summary), html.escape(text))


# ------------------------------------------------------------ the blocks


def pricing(c, rate=None, dividend=None):
    """The model behind every price and Greek on the page."""
    carry = ""
    if rate is not None or dividend is not None:
        carry = " (this chain: r = {}, q = {})".format(
            "unknown" if rate is None else "{:.4f}".format(float(rate)),
            "unknown" if dividend is None
            else "{:.4f}".format(float(dividend)))
    return "\n".join([
        "model      Black-Scholes-Merton, European exercise, continuous "
        "carry q",
        "           T  = calendar days to expiry / {}".format(
            _value(c, "days_per_year")),
        "           d1 = [ ln(S / K) + (r - q + sigma^2 / 2) T ] / "
        "( sigma sqrt(T) )",
        "           d2 = d1 - sigma sqrt(T)",
        "           call = S exp(-qT) N(d1) - K exp(-rT) N(d2)",
        "           put  = K exp(-rT) N(-d2) - S exp(-qT) N(-d1)",
        "carry      r and q are read from the chain snapshot{}; the engine "
        "defaults are r = {}, q = {}".format(
            carry, _value(c, "default_r"), _value(c, "default_q")),
        "implied    sigma solves  model(S, K, T, sigma) = mid,  with "
        "mid = (bid + ask) / 2",
        "           Newton-Raphson from a fixed seed, bisection on [{}, {}] "
        "when Newton leaves the bracket".format(
            _value(c, "iv_min"), _value(c, "iv_max")),
        "           a root is accepted only where the price is sensitive "
        "to volatility, vega > {};".format(_value(c, "min_vega")),
        "           otherwise the contract keeps the provider's figure and "
        "is counted as a fallback,",
        "           or carries no volatility at all and is skipped, never "
        "estimated",
        "greeks     analytic, first to third order, each checked against a "
        "central finite difference",
        "           of the price function in the test suite",
        "           delta = dV/dS                gamma = d2V/dS2"
        "              vega  = dV/dsigma, per 1.00",
        "           theta = dV per calendar day  rho   = dV/dr, per 1.00"
        "      lambda = delta S / V",
        "           vanna = d2V/dS dsigma        vomma = d2V/dsigma2"
        "          charm = d delta per calendar day",
        "           veta  = d vega per day       speed = d3V/dS3"
        "              zomma = d gamma / dsigma",
        "           color = d gamma per day      ultima = d3V/dsigma3"
        "         dual delta = dV/dK,  dual gamma = d2V/dK2",
        "           the four per-day figures are the change as one calendar "
        "day passes, so a negative theta is decay",
    ])


def positioning(c):
    """Dealer gamma exposure, the walls, the flip and max pain."""
    m = _value(c, "multiplier")
    return "\n".join([
        "per contract  GEX = gamma x OI x {} x S^2 x 0.01".format(m),
        "              gamma x S x 0.01 is the delta change over a one "
        "percent move, per share;",
        "              x S turns shares into currency;  x {} x OI scales "
        "it to every open contract".format(m),
        "sign          calls +, puts -   (dealers long calls and short puts "
        "against the public: the conventional",
        "              assumption, stated on the panel because it is "
        "regularly wrong for a single name)",
        "per strike    net_K = sum over the contracts listed at K of "
        "signed GEX",
        "net           sum over strikes; above zero read as dampening, "
        "below zero as amplifying",
        "walls         call wall = the strike with the largest call GEX;  "
        "put wall = the strike with the most negative put GEX",
        "cumulative    C_K = running sum of net_K from the lowest listed "
        "strike upward, so extending the ladder",
        "              shifts the whole profile",
        "flip          the level where C_K crosses zero, interpolated "
        "between the two strikes that straddle it;",
        "              with several crossings the one nearest spot is the "
        "headline and the rest are in the artifact",
        "max pain      argmin over settlement P of  sum over K [ OI_call(K) "
        "max(P - K, 0) + OI_put(K) max(K - P, 0) ] x {}".format(m),
        "              evaluated at each listed strike: a description of "
        "where open interest sits, not a forecast",
        "ratios        put/call OI = sum of put OI / sum of call OI;  "
        "put/call volume the same, on today's volume",
        "skipped       a contract missing gamma, open interest or strike is "
        "counted apart by cause, never treated as zero",
    ])


def volatility(c, days=None):
    """The smile, the expected move, and the premium over realised."""
    target = c.get("target_delta") if c else None
    wing = "{:g}".format(target * 100) if target is not None else "TARGET"
    target_text = ("{:.2f}".format(target) if target is not None
                   else "TARGET_DELTA")
    horizon = "{:g}".format(float(days)) if days else "days"
    return "\n".join([
        "at the money   the listed strike nearest spot, calls winning a "
        "tie; not an interpolated forward",
        "wings          the call and the put whose model delta is nearest "
        "{}, accepted only within {} of it;".format(
            target_text, _value(c, "delta_tolerance", ".2f")),
        "               a chain that does not reach a wing reports the "
        "figure as absent rather than substituted",
        "risk reversal  RR = sigma(put {w}d) - sigma(call {w}d)      "
        "positive: the downside is bid".format(w=wing),
        "butterfly      BF = ( sigma(put {w}d) + sigma(call {w}d) ) / 2 - "
        "sigma(atm)".format(w=wing),
        "skew slope     least-squares slope of sigma against (K / S - 1) x "
        "100, calls only, across the graded band",
        "expected move  EM = S x sigma(atm) x sqrt({} / {})      one "
        "standard deviation over the life of the expiry".format(
            horizon, _value(c, "days_per_year")),
        "               range = [ max(S - EM, 0), S + EM ]: about 68 "
        "percent of outcomes under a lognormal",
        "term           the same figures per expiry on file, so the slope "
        "across tenors is visible",
        "realised       sigma(real) = sqrt( sample variance of daily "
        "ln(S_t / S_t-1) x {} ) over the simulation's history "
        "window".format(_value(c, "trading_days")),
        "premium gap    gap = sigma(atm) - sigma(real) per expiry: a "
        "disagreement between forecast and past, not an edge",
    ])


def structures(c):
    """The payoff engine, the lognormal law behind P(profit), and friction."""
    return "\n".join([
        "payoff         P(S_T) = sum over legs of side x qty x ( value(S_T) "
        "- premium )",
        "               call value max(S_T - K, 0);  put value max(K - S_T, "
        "0);  underlying S_T - entry price",
        "               side is +1 long, -1 short; premiums are snapshot "
        "mids, so this is a shape and not a fill",
        "breakevens     every settlement price where P(S_T) = 0, one per "
        "sign change of the piecewise-linear payoff",
        "extremes       max gain and max loss over all S_T; \"unlimited\" "
        "where the outer slope does not vanish",
        "capital        capital at risk = |max loss| for a defined-risk "
        "structure; undefined where the loss is unbounded,",
        "               and such a structure is listed but not ranked",
        "reward:risk    max gain / |max loss|",
        "P(profit)      the lognormal mass of the profitable regions "
        "between breakevens, under",
        "               ln(S_T) ~ Normal( ln(S) + (mu - sigma^2 / 2) T,  "
        "sigma^2 T ),  mu = 0,  T = days / {}".format(
            _value(c, "days_per_year")),
        "               with sigma = one at-the-money implied volatility "
        "for every strike: a model estimate, not a win rate",
        "expected P/L   E[ P(S_T) ] under the same law, in closed form "
        "region by region, because P is linear in S_T",
        "               between breakevens and the partial expectation of "
        "a lognormal is analytic",
        "shortfall      expected loss = E[ P(S_T) | P(S_T) < 0 ], the same "
        "way",
        "ranking        expected return on risk = E[P] / capital at risk; "
        "the comparison orders on it, ties broken on P(profit)",
        "friction       half spread = (ask - bid) / 2 per option leg;  "
        "entry = qty x half spread x {}".format(_value(c, "haircut")),
        "               round trip = 2 x entry + commission;  verdict ok "
        "below {} of the net premium, thin up to {},".format(
            _value(c, "ok_max", ".0%"), _value(c, "thin_max", ".0%")),
        "               untradeable above that, where a leg quotes wider "
        "than {} of its own mid, or where a leg has no bid".format(
            _value(c, "max_rel_spread", ".0%")),
    ])


def time_spreads(c, analysis=None):
    """Structures marked at the near expiry, with the two ratio columns."""
    fraction = (analysis or {}).get("scanned_fraction")
    if fraction:
        lo = "{:.0%}".format(1.0 - float(fraction))
        hi = "{:.0%}".format(1.0 + float(fraction))
    else:
        lo, hi = "a stated fraction below", "the same above"
    dpy = _value(c, "days_per_year")
    return "\n".join([
        "marking        profit is read on the near expiry's date: the "
        "expired leg is worth its intrinsic value, the surviving",
        "               leg is priced by the model with the implied "
        "volatility it carries today, T = (far days - near days) / "
        "{}".format(dpy),
        "profit         P(S) = sum over legs of side x qty x ( value(S, at "
        "the near expiry) - premium ): a curve, not segments",
        "scan           S from {} to {} of spot in {} steps; breakevens are "
        "where the curve crosses zero".format(
            lo, hi, _value(c, "curve_points")),
        "extremes       max gain and loss are over the scan; one that sits "
        "on the edge is flagged, and the edge is stated in",
        "               standard deviations as  ln(edge / S) / ( sigma_avg "
        "sqrt(near days / {}) )".format(dpy),
        "giveback       max gain - profit at the far end of the scan "
        "(upside for calls, downside for puts): how much of the",
        "               peak a diagonal hands back for being too right",
        "delta ratio    sum over shorts of |delta| x qty  /  sum over longs "
        "of |delta| x qty, at entry, ratio structures only;",
        "               a bound on the split, not the reason a move stays "
        "uncapped: that is holding more far contracts than near",
    ])


def simulation(c, artifact=None):
    """GARCH-t by MCMC, the paths, and the two tail figures."""
    sim = artifact or {}
    history = sim.get("history") or {}
    settings = sim.get("simulation") or {}
    posterior = sim.get("posterior") or {}
    fit = posterior.get("settings") or {}

    def either(key, artifact_value):
        return (format(artifact_value, ",") if artifact_value is not None
                else _value(c, key, ","))

    observations = history.get("observations")
    window = ""
    if history.get("first") and history.get("last"):
        window = " ({} to {})".format(history["first"], history["last"])
    kept = ""
    if settings.get("paths") is not None:
        kept = " ({:,} kept)".format(int(settings["paths"]))
    horizon = ""
    if settings.get("horizon_days") is not None:
        horizon = ", {} business days out".format(settings["horizon_days"])
    return "\n".join([
        "returns        r_t = ln( S_t / S_t-1 ) over {} daily "
        "closes{}".format(
            "{:,}".format(int(observations)) if observations else "the",
            window),
        "model          r_t = mu + e_t,   e_t = sigma_t z_t,   z_t ~ "
        "Student-t(nu) scaled to unit variance",
        "               sigma_t^2 = omega + alpha e_t-1^2 + beta "
        "sigma_t-1^2",
        "               omega > 0, alpha >= 0, beta >= 0, alpha + beta < 1 "
        "(stationary), nu > 2 (finite variance)",
        "posterior      Markov chain Monte Carlo over (mu, omega, alpha, "
        "beta, nu): {} chains of {} draws after {} burn-in;".format(
            either("chains", fit.get("chains")),
            either("draws", fit.get("draws")),
            either("burn", fit.get("burn"))),
        "               converged only when split R-hat < {} and effective "
        "sample size >= {} for every parameter".format(
            _value(c, "rhat_limit"), _value(c, "min_ess")),
        "paths          {} paths{}; each draws its own parameter set from "
        "the posterior, steps sigma_t^2 forward one day".format(
            either("paths", settings.get("requested_paths")), kept),
        "               at a time and exponentiates the summed returns: "
        "independent draws, so parameter uncertainty is in the fan",
        "fan            per-day 5th, 25th, 50th, 75th and 95th percentiles "
        "across paths; no single path is stored",
        "horizon        R = S_horizon / S - 1 across the terminal "
        "prices{}".format(horizon),
        "value at risk  VaR_95 = -( 5th percentile of R ),  VaR_99 = -( 1st "
        "percentile of R ): positive numbers are losses",
        "shortfall      ES_95 = -( mean of R at or below its 5th "
        "percentile ): how bad the bad case is, not where it starts",
        "structures     each saved plan priced at expiry on every terminal "
        "price; P(profit) under this realised law is shown",
        "               beside P(profit) under the implied law, and the "
        "gap between them is reported as the disagreement",
    ])


def backtest(c, backtests=None):
    """Modelled premiums on real closes, and the block-aware tests."""
    first = (backtests or [None])[0] or {}
    settings = first.get("settings") or {}
    significance = first.get("significance") or {}
    interval = first.get("interval") or {}
    hold = settings.get("holding_days")
    entry = settings.get("entry_every")
    hold_text = str(hold) if hold else "H"
    entry_text = str(entry) if entry else "E"
    block_value = significance.get("block") or first.get("overlap_block")
    if not block_value and hold and entry:
        block_value = -(-int(hold) // max(1, int(entry)))
    block_text = str(block_value) if block_value else "ceil(H / E)"
    lookback = settings.get("lookback")
    lookback_text = (str(lookback) if lookback
                     else _value(c, "lookback", "d"))
    trials = significance.get("trials")
    trials_text = "{:,}".format(int(trials)) if trials else "many"
    level = interval.get("level")
    level_text = "{:.0%}".format(float(level)) if level else "the stated"
    window = ""
    if settings.get("first_date") and settings.get("last_date"):
        window = ", from {} to {}".format(settings["first_date"],
                                          settings["last_date"])
    return "\n".join([
        "schedule       enter every {} trading days, hold {} trading days "
        "to expiry{}".format(entry_text, hold_text, window),
        "premiums       Black-Scholes at trailing realised volatility over "
        "the last {} closes,".format(lookback_text),
        "               sigma(real) = sqrt( sample variance of daily "
        "ln(S_t / S_t-1) x {} ), on a model chain of strikes".format(
            _value(c, "trading_days")),
        "               around each entry's spot: no quotes, no spread, no "
        "slippage, no assignment, no early exercise",
        "outcome        profit = payoff at the real close {} days later - "
        "net premium".format(hold_text),
        "               return on risk = profit / |max loss|; undefined "
        "where the loss is unbounded, and then not averaged",
        "equity         cumulative SUM of returns on risk: one unit of "
        "capital risked per trade, never compounded",
        "drawdown       running maximum of equity - equity, in units of "
        "per-trade risk",
        "sharpe         mean / standard deviation of returns on risk, per "
        "trade, not annualised",
        "overlap        a {h}-day hold entered every {e} days shares days "
        "with its neighbours, so trades come in".format(
            h=hold_text, e=entry_text),
        "               blocks of b = ceil({h} / {e}) = {b} that are not "
        "independent".format(h=hold_text, e=entry_text, b=block_text),
        "p-value        signs flipped a block at a time, {} times, "
        "two-sided:".format(trials_text),
        "               p = ( count of |shuffled mean| >= |observed mean| "
        "+ 1 ) / ( trials + 1 )",
        "interval       moving-block bootstrap: blocks of b resampled with "
        "replacement, {} interval on the mean;".format(level_text),
        "               it excludes zero when both ends share a sign",
        "benchmark      buy and hold the underlying over the same windows, "
        "reported beside every row",
    ])
