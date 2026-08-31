"""The dashboard page: markup, tiles and tables.

Charts live in charts.py, styling in style.py. This module decides what is
on the page and in what order, which is the part worth arguing about.

Order follows how a desk actually reads a chain: what is the market doing
(positioning), what is volatility priced at (the smile), what would a
structure pay (strategies), then the raw ladder for anyone who wants to
check the numbers themselves.
"""

import html
import json

from optiondesk.dashboard.charts import SCRIPT
from optiondesk.dashboard.style import STYLE


def _tile(key, value, tone="", sub=""):
    return (
        "<div class='tile'><div class='k'>{}</div>"
        "<div class='v {}'>{}</div>{}</div>"
    ).format(html.escape(str(key)), tone, html.escape(str(value)),
             "<div class='s'>{}</div>".format(html.escape(str(sub)))
             if sub else "")


def _tiles(items):
    return "<div class='tiles'>" + "".join(
        _tile(*item) for item in items) + "</div>"


def _num(value, digits=2, suffix=""):
    if value is None:
        return "n/a"
    try:
        return "{:,.{d}f}{}".format(float(value), suffix, d=digits)
    except (TypeError, ValueError):
        return str(value)


def _compact(value):
    if value is None:
        return "n/a"
    value = float(value)
    magnitude = abs(value)
    if magnitude >= 1e9:
        return "{:.2f}bn".format(value / 1e9)
    if magnitude >= 1e6:
        return "{:.1f}m".format(value / 1e6)
    if magnitude >= 1e3:
        return "{:.1f}k".format(value / 1e3)
    return "{:.2f}".format(value)


def _percent(value, digits=1):
    return "n/a" if value is None else "{:.{d}f}%".format(
        float(value) * 100, d=digits)


def _positioning_tiles(exposure):
    if not exposure:
        return ""
    ex = exposure["exposure"]
    smile = exposure.get("smile") or {}
    pain = exposure.get("max_pain") or {}
    net = ex.get("net_gex")
    return _tiles([
        ("Net gamma exposure", _compact(net),
         "pos" if (net or 0) > 0 else "neg", "per 1% move"),
        ("Hedging regime", ex.get("regime", "n/a"),
         "pos" if ex.get("regime") == "dampening" else "neg",
         "dampening or amplifying"),
        ("Gamma flip", _num(ex.get("gamma_flip")), "",
         "cumulative crosses zero"),
        ("Call wall", _num((ex.get("call_wall") or {}).get("strike")), "",
         _compact((ex.get("call_wall") or {}).get("gex"))),
        ("Put wall", _num((ex.get("put_wall") or {}).get("strike")), "",
         _compact((ex.get("put_wall") or {}).get("gex"))),
        ("Max pain", _num(pain.get("strike")), "", "least payout"),
        ("Put / call OI", _num(ex.get("put_call_oi_ratio"), 2), "",
         "open interest"),
        ("Put / call volume", _num(ex.get("put_call_volume_ratio"), 2), "",
         "today"),
    ])


def _volatility_tiles(exposure):
    if not exposure or not exposure.get("smile"):
        return ""
    smile = exposure["smile"]
    band = smile.get("expected_range") or [None, None]
    return _tiles([
        ("At-the-money IV", _percent(smile.get("atm_iv"), 2), "",
         "strike {}".format(_num(smile.get("atm_strike")))),
        ("25-delta risk reversal", _percent(smile.get("risk_reversal"), 2),
         "neg" if (smile.get("risk_reversal") or 0) > 0 else "pos",
         "put minus call"),
        ("25-delta butterfly", _percent(smile.get("butterfly"), 2), "",
         "wings minus body"),
        ("Skew slope", _num(smile.get("skew_slope_per_percent"), 4), "",
         "iv per 1% of strike"),
        ("Expected move", _num(smile.get("expected_move")), "",
         "one standard deviation"),
        ("Expected range", "{} to {}".format(_num(band[0]), _num(band[1])),
         "", "68% of outcomes"),
    ])


def _table(rows, columns, body_id=None):
    head = "".join("<th>{}</th>".format(html.escape(c)) for c in columns)
    body = []
    for row in rows:
        cells = []
        for column in columns:
            value = row.get(column)
            if isinstance(value, float):
                cells.append("<td>{:.6g}</td>".format(value))
            else:
                cells.append("<td>{}</td>".format(
                    html.escape(str("" if value is None else value))))
        body.append("<tr>{}</tr>".format("".join(cells)))
    return ("<div class='scroll'><table><thead><tr>{}</tr></thead>"
            "<tbody{}>{}</tbody></table></div>").format(
                head, " id='{}'".format(body_id) if body_id else "",
                "".join(body))


def _selector(groups, selected):
    """Underlying and expiry picker, built from what is on disk.

    Plain links with query parameters rather than a script-driven control:
    the server already knows how to render any group, so a link is enough,
    and every view is addressable and bookmarkable.
    """
    if not groups:
        return ""
    underlyings = []
    seen = set()
    for group in groups:
        symbol = group["underlying"]
        if symbol in seen:
            continue
        seen.add(symbol)
        underlyings.append(symbol)

    current = (selected or {}).get("underlying")
    current_expiry = (selected or {}).get("expiry")

    sym_buttons = "".join(
        "<a class='pill{}' href='?u={}'>{}</a>".format(
            " on" if symbol == current else "",
            html.escape(str(symbol)), html.escape(str(symbol)))
        for symbol in underlyings)

    expiry_buttons = "".join(
        "<a class='pill{}' href='?u={}&amp;e={}' title='{}'>{}</a>".format(
            " on" if group["expiry"] == current_expiry else "",
            html.escape(str(group["underlying"])),
            html.escape(str(group["expiry"] or "")),
            html.escape(", ".join(group["have"]) or "nothing yet"),
            html.escape(str(group["expiry"] or "no expiry")))
        for group in groups if group["underlying"] == current)

    have = ", ".join((selected or {}).get("have") or []) or "nothing"
    return (
        "<div class='selector'>"
        "<div class='row'><span class='lbl'>underlying</span>{sym}</div>"
        "<div class='row'><span class='lbl'>expiry</span>{exp}</div>"
        "<div class='row'><span class='lbl'>on disk</span>"
        "<span class='empty'>{have}{plans}</span></div>"
        "</div>"
    ).format(sym=sym_buttons, exp=expiry_buttons, have=html.escape(have),
             plans=(", {} strategy plans".format(
                 (selected or {}).get("plan_count", 0))
                 if (selected or {}).get("plan_count") else ""))


def _add_more(selected):
    """The commands that put another underlying or expiry on this page."""
    symbol = (selected or {}).get("underlying") or "SPY"
    return _panel(
        "Analysing something else",
        "This page renders artifacts on disk. To add an underlying or an "
        "expiry, run the commands below and refresh. Any agent connected to "
        "the MCP server can run them for you.",
        "<pre class='cmds'>"
        "optiondesk expiries QQQ            # what is listed\n"
        "optiondesk chain QQQ --expiry 2026-09-18\n"
        "optiondesk greeks --band 0.06\n"
        "optiondesk exposure\n"
        "optiondesk compare                 # every structure, ranked\n"
        "optiondesk simulate QQQ --horizon 14\n"
        "optiondesk backtest QQQ iron_condor --period 5y\n"
        "\n"
        "optiondesk expiries                # what you already have\n"
        "</pre>"
        "<p class='hint'>Currently showing {}. Each command writes one "
        "schema-validated artifact into the artifact directory.</p>".format(
            html.escape(str(symbol))))


def _comparison_panel(comparison):
    """Every structure side by side, with the ordering criterion visible."""
    if not comparison:
        return ""
    rows = comparison.get("rows") or []
    if not rows:
        return ""
    leader = comparison.get("leader") or {}

    header = ["rank", "structure", "type", "net", "max gain", "max loss",
              "capital at risk", "reward:risk", "P(profit)", "expected P/L",
              "return on risk", "delta", "theta", "vega", "friction"]

    def cell(value, digits=2, percent=False):
        if value is None:
            return "n/a"
        if isinstance(value, str):
            return html.escape(value)
        if percent:
            return "{:.1f}%".format(float(value) * 100)
        return "{:,.{d}f}".format(float(value), d=digits)

    body = []
    ordered = sorted(rows, key=lambda r: (r.get("rank") or 999,
                                          r.get("strategy") or ""))
    for row in ordered:
        classes = []
        if row.get("rank") == 1:
            classes.append("lead")
        if not row.get("rankable"):
            classes.append("out")
        excluded = "; ".join(row.get("excluded_because") or [])
        body.append(
            "<tr class='{cls}' title='{why}'>"
            "<td>{rank}</td><td>{name}</td><td>{type}</td><td>{net}</td>"
            "<td>{gain}</td><td>{loss}</td><td>{risk}</td><td>{rr}</td>"
            "<td>{pop}</td><td>{ev}</td><td>{ror}</td><td>{delta}</td>"
            "<td>{theta}</td><td>{vega}</td>"
            "<td><span class='badge {fv}'>{fv}</span></td></tr>".format(
                cls=" ".join(classes), why=html.escape(excluded),
                rank=row.get("rank") or "",
                name=html.escape(str(row.get("strategy", "")).replace(
                    "_", " ")),
                type=html.escape(str(row.get("trade_type") or "")),
                net=cell(row.get("net_cash")),
                gain=cell(row.get("max_gain")),
                loss=cell(row.get("max_loss")),
                risk=cell(row.get("capital_at_risk")),
                rr=cell(row.get("reward_risk")),
                pop=cell(row.get("probability_of_profit"), percent=True),
                ev=cell(row.get("expected_pnl")),
                ror=cell(row.get("expected_return_on_risk"), percent=True),
                delta=cell(row.get("net_delta"), 3),
                theta=cell(row.get("net_theta"), 3),
                vega=cell(row.get("net_vega")),
                fv=html.escape(str(row.get("friction_verdict") or "n/a"))))

    lead_line = ""
    if leader:
        margin = comparison.get("margin_over_runner_up")
        lead_line = (
            "<p class='lead-line'><strong>Top of the ordering: {name}</strong>"
            " at {ror} expected return on capital at risk, "
            "P(profit) {pop}{margin}.</p>".format(
                name=html.escape(str(leader.get("strategy", "")).replace(
                    "_", " ")),
                ror=cell(leader.get("expected_return_on_risk"), percent=True),
                pop=cell(leader.get("probability_of_profit"), percent=True),
                margin=(", ahead of the next by {}".format(
                    cell(margin, percent=True)) if margin else "")))

    return _panel(
        "Every structure, side by side",
        comparison.get("criterion", ""),
        lead_line
        + "<div class='scroll'><table><thead><tr>"
        + "".join("<th>{}</th>".format(html.escape(h)) for h in header)
        + "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>"
        + "<p class='caveat'><strong>Read this before using the order.</strong>"
        " {}</p>".format(html.escape(comparison.get("caveat", ""))))


def _outcome_word(value):
    """Which way one view expects a structure to come out, or None.

    Deliberately three words and not a number. The three views are measured
    in different units over different horizons, so their magnitudes are not
    comparable and only the direction is.
    """
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not (number == number):  # NaN, which is neither profit nor loss
        return None
    return "profit" if number > 0 else ("loss" if number < 0 else "flat")


def _views_disagree(model, sim, backtest):
    """(short, long) description of where the three views part company.

    Nothing is averaged and nothing is reconciled. Two independent things
    are reported: whether the views agree on the direction of the outcome,
    and how far apart their probabilities of profit are. A view that is not
    on disk is absent from both, never counted as agreement.
    """
    directions = [
        ("model", _outcome_word((model or {}).get("expected_pnl"))),
        ("simulation", _outcome_word((sim or {}).get("mean"))),
        ("history", _outcome_word(
            ((backtest or {}).get("statistics") or {}).get("mean_return"))),
    ]
    directions = [(name, word) for name, word in directions if word]

    probabilities = [
        ("model", (model or {}).get("probability_of_profit")),
        ("simulation",
         (sim or {}).get("realised_vol_probability_of_profit")),
        ("history",
         ((backtest or {}).get("statistics") or {}).get("win_rate")),
    ]
    probabilities = [(name, value) for name, value in probabilities
                     if value is not None]

    if len(directions) + len(probabilities) == 0:
        return "no view", "nothing on disk says how this structure comes out"
    if len(directions) < 2 and len(probabilities) < 2:
        return ("one view only",
                "only one of the three views covers this structure, so "
                "there is nothing for it to disagree with")

    detail = ["{} expects {}".format(name, word) for name, word in directions]
    split = len({word for _, word in directions}) > 1

    spread = None
    if len(probabilities) > 1:
        low = min(probabilities, key=lambda pair: pair[1])
        high = max(probabilities, key=lambda pair: pair[1])
        spread = (high[1] - low[1]) * 100.0
        detail.append(
            "probability of profit runs from {} at {} to {} at {}, a gap of "
            "{:.1f} points".format(low[0], _percent(low[1]), high[0],
                                   _percent(high[1]), spread))

    short = "split on direction" if split else (
        "agree on direction" if len(directions) > 1 else "direction: one view")
    if spread is not None:
        short += ", {:.0f} pt gap".format(spread)
    return short, "; ".join(detail)


def _composite_rows(comparison, simulation, backtests):
    """Every compared structure, scored, with its other two views attached.

    The score comes from the engine, reached through the bridge like every
    other piece of analytics. The two extra views are matched by strategy
    name against the simulation's per-structure block and the backtests on
    disk, and a structure that appears in only one of them carries None for
    the others rather than a substitute.
    """
    from optiondesk import engine_bridge

    if not engine_bridge.AVAILABLE:
        return None
    ranking = engine_bridge.analytics().ranking

    rows = (comparison or {}).get("rows") or []
    if not rows:
        return None

    by_name = {row.get("strategy"): row for row in rows}
    scored, rejected = ranking.rank_rows(
        [ranking.row_from_comparison(row) for row in rows],
        vol_view="neutral", top=len(rows))

    simulated = {structure.get("strategy"): structure
                 for structure in ((simulation or {}).get("structures") or [])}
    historical = {test.get("strategy"): test for test in (backtests or [])}

    out = []
    for row in scored:
        name = row["structure"]
        model = by_name.get(name) or {}
        sim = simulated.get(name)
        history = historical.get(name)
        short, long = _views_disagree(model, sim, history)
        out.append({"scored": row, "model": model, "sim": sim,
                    "backtest": history, "disagree": short,
                    "disagree_detail": long})
    return {"ranked": out, "rejected": rejected,
            "weights": ranking.SCORE_WEIGHTS, "formula": ranking.FORMULA,
            "rr_cap": ranking.RR_CAP, "vrp_tilt": ranking.VRP_TILT,
            "thin_multiplier": ranking.THIN_MULTIPLIER,
            "min_premium": ranking.MIN_ABS_PREMIUM}


def _composite_horizons(comparison, simulation, backtests, days):
    """The three horizons the score is built from, stated in one sentence.

    Written out because the composite is the one place in this dashboard
    where figures from three different horizons land in a single number. A
    score that mixed forty-six days of model settlement with a thirty-day
    simulation and a thirty-day holding period, and did not say so, would
    be presenting an incomparability as a measurement.
    """
    expiry = (comparison or {}).get("expiry")
    parts = ["the model figures settle at the {} expiry{}".format(
        expiry or "selected", ", {} days away".format(_num(days, 1))
        if days else "")]

    horizon = ((simulation or {}).get("simulation") or {}).get("horizon_days")
    if horizon is not None:
        parts.append("the simulation runs {} days".format(horizon))
    else:
        parts.append("no simulation is on disk, so that column is empty")

    holdings = sorted({(test.get("settings") or {}).get("holding_days")
                       for test in (backtests or [])
                       if (test.get("settings") or {}).get("holding_days")})
    if holdings:
        windows = sorted({((test.get("settings") or {}).get("first_date"),
                           (test.get("settings") or {}).get("last_date"))
                          for test in backtests})
        first, last = windows[0] if windows else (None, None)
        parts.append(
            "the backtest holds {} days per trade{}".format(
                " or ".join(str(h) for h in holdings),
                ", entered across {} to {}".format(first, last)
                if first and last else ""))
    else:
        parts.append("no backtest is on disk, so those columns are empty")

    return ("Three horizons, not one, and they are not reconciled: "
            + "; ".join(parts) + ".")


def _composite_section(comparison, simulation, backtests, days):
    """One composite score per structure, with its inputs and its dissent.

    The shape follows _comparison_panel: a wide table under a printed
    criterion. What is different is that the criterion here is arithmetic
    rather than a sentence, so the arithmetic is printed too, along with
    every component that went into it. A reader who dislikes the ordering
    can point at the weight or the component they dislike.

    Nothing here selects a structure. The columns to the right of the score
    are three independent readings of the same structure and they routinely
    disagree; the last column says so rather than averaging the
    disagreement away, because the disagreement is the most informative
    thing on the row.
    """
    assembled = _composite_rows(comparison, simulation, backtests)
    if not assembled:
        return ""

    weights = assembled["weights"]
    header = ["rank", "structure", "score", "pop", "edge", "rr", "es",
              "adjust", "friction", "model P(profit)", "model P/L",
              "sim P(profit)", "sim mean", "history trades",
              "history win rate", "history mean on risk", "views"]

    body = []
    for entry in assembled["ranked"]:
        row = entry["scored"]
        parts = row["components"]
        model = entry["model"]
        sim = entry["sim"] or {}
        stats = (entry["backtest"] or {}).get("statistics") or {}
        substituted = parts["substituted"]
        title = entry["disagree_detail"]
        if substituted:
            title += ". Substituted: " + "; ".join(substituted)
        body.append(
            "<tr class='{cls}' title='{why}'>"
            "<td>{rank}</td><td>{name}{mark}</td><td><strong>{score}</strong>"
            "</td><td>{pop}</td><td>{edge}</td><td>{rr}</td><td>{es}</td>"
            "<td>{adjust}</td>"
            "<td><span class='badge {fv}'>{fv}</span></td>"
            "<td>{mpop}</td><td>{mpnl}</td><td>{spop}</td><td>{smean}</td>"
            "<td>{trades}</td><td>{win}</td><td>{hmean}</td>"
            "<td>{views}</td></tr>".format(
                cls="lead" if row.get("rank") == 1 else "",
                why=html.escape(title),
                rank=row.get("rank") or "",
                name=html.escape(str(row["structure"]).replace("_", " ")),
                mark=" *" if substituted else "",
                score=_num(row["score"], 1),
                pop=_num(parts["pop_norm"], 3),
                edge=_num(parts["edge_norm"], 3),
                rr=_num(parts["rr_norm"], 3),
                es=_num(parts["es_norm"], 3),
                adjust="{:+.1f}, x{:.2f}".format(parts["vrp_tilt"],
                                                 parts["thin_multiplier"]),
                fv=html.escape(str(model.get("friction_verdict") or "n/a")),
                mpop=_percent(model.get("probability_of_profit")),
                mpnl=_num(model.get("expected_pnl")),
                spop=_percent(sim.get("realised_vol_probability_of_profit")),
                smean=_num(sim.get("mean")),
                # Not stats.get("trades", 0): a backtest of a structure
                # with an unbounded loss writes statistics as an empty
                # object, so that default renders a confident "0 trades"
                # where the truth is that nothing could be measured.
                trades=_num(stats.get("trades"), 0),
                win=_percent(stats.get("win_rate")),
                hmean=_percent(stats.get("mean_return"), 2),
                views=html.escape(entry["disagree"])))

    substitutions = [
        "<li><strong>{}</strong>: {}</li>".format(
            html.escape(str(entry["scored"]["structure"]).replace("_", " ")),
            html.escape("; ".join(entry["scored"]["components"]["substituted"])))
        for entry in assembled["ranked"]
        if entry["scored"]["components"]["substituted"]]
    substitution_html = ""
    if substitutions:
        substitution_html = (
            "<p class='assume'>Marked with an asterisk above: an input was "
            "absent and something stood in for it. The score was still "
            "computed, and what stood in is named here so it can be "
            "discounted.</p><ul class='notes'>"
            + "".join(substitutions) + "</ul>")

    excluded_html = ""
    if assembled["rejected"]:
        items = []
        for row in assembled["rejected"]:
            exclusion = row["exclusion"]
            items.append(
                "<li><strong>{}</strong>: {}. Absent: {}.</li>".format(
                    html.escape(str(row.get("structure") or "").replace(
                        "_", " ")),
                    html.escape(str(exclusion.get("reason") or
                                    exclusion.get("excluded"))),
                    html.escape(", ".join(exclusion.get("missing") or [])
                                or "nothing")))
        excluded_html = (
            "<p class='assume'>{} of the structures compared here carry no "
            "score. They are listed rather than dropped: a structure left "
            "out of an ordering is part of what the ordering says.</p>"
            "<ul class='notes'>{}</ul>".format(len(assembled["rejected"]),
                                               "".join(items)))

    formula = (
        "score = 100 * ({pop:.2f} pop + {edge:.2f} edge + {rr:.2f} rr "
        "+ {es:.2f} (1 - es))\n"
        "  pop    model probability of profit, on [0, 1]\n"
        "  edge   (expected P/L - round trip friction) / premium,\n"
        "         clamped to [-1, 1] and mapped onto [0, 1]\n"
        "  rr     min(reward:risk, {cap:g}) / {cap:g}; unbounded gain scores "
        "1.000\n"
        "  es     |expected shortfall| / worst case, capped at 1.000\n"
        "then   + {tilt:g} or - {tilt:g} for a volatility view, credit "
        "families\n"
        "         favoured on crush and debit families on expand\n"
        "       x {thin:g} when the friction verdict is thin\n"
        "       clamped to [0, 100]\n"
        "premium is floored at {floor:.2f} so quote noise cannot inflate "
        "edge".format(
            pop=weights["pop"], edge=weights["edge"], rr=weights["rr"],
            es=weights["es"], cap=assembled["rr_cap"],
            tilt=assembled["vrp_tilt"], thin=assembled["thin_multiplier"],
            floor=assembled["min_premium"]))

    return (
        "<h2 class='section'>Composite support</h2>"
        + _panel(
            "Which structure has the most support under one printed formula",
            "Four measured quantities on one axis, with the weights shown. "
            "This is an ordering under stated weights, not an estimate of "
            "edge and not a view on what to do.",
            "<pre class='cmds'>" + html.escape(formula) + "</pre>"
            + "<p class='assume'>{}</p>".format(
                html.escape(_composite_horizons(comparison, simulation,
                                                backtests, days)))
            + "<p class='hint'>The volatility view is neutral, because "
              "nothing on disk states one, so the tilt is {:+.1f} on every "
              "row. Under a crush view every credit structure gains {:g} "
              "points and every debit structure loses {:g}; under expand the "
              "two swap.</p>".format(0.0, assembled["vrp_tilt"],
                                     assembled["vrp_tilt"])
            + "<div class='scroll'><table><thead><tr>"
            + "".join("<th>{}</th>".format(html.escape(h)) for h in header)
            + "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>"
            + substitution_html
            + excluded_html
            + "<p class='caveat'><strong>What this number is not.</strong> "
              "It is not an edge estimate. Three of the four components come "
              "from the same lognormal model at a single at-the-money "
              "volatility, so they move together and the composite is far "
              "less independent than four terms suggest. The weights were "
              "chosen and written down, not fitted to anything, and a "
              "different set would reorder the table. The model, simulation "
              "and history columns measure different things over different "
              "horizons and are shown side by side for exactly that reason. "
              "Where they disagree the last column says so, and that "
              "disagreement is not resolved here.</p>"))


def _diagnostic_line(diagnostics):
    """Worst R-hat and smallest ESS, or a statement that there are none.

    Every R-hat is None when the chains were too short to split, and the
    unguarded max() over an empty generator did not merely omit a tile: it
    raised inside the renderer and took the whole dashboard process down,
    on an artifact the pipeline had written quite happily.
    """
    rhats = [v for v in (diagnostics.get("rhat") or {}).values()
             if v is not None]
    esses = [v for v in (diagnostics.get("ess") or {}).values()
             if v is not None]
    if not rhats or not esses:
        return "diagnostics unavailable"
    worst = max(rhats)
    return "R-hat {}, ESS {:.0f}".format(
        "infinite" if worst == float("inf") else "{:.3f}".format(worst),
        min(esses))


def _simulation_section(simulation):
    """The posterior, the fan, and the risk that follows from it."""
    if not simulation:
        return ""
    posterior = simulation["posterior"]
    diagnostics = posterior["diagnostics"]
    risk = simulation.get("risk") or {}
    history = simulation.get("history") or {}
    params = posterior["parameters"]
    converged = posterior["converged"]

    warn = ""
    if not converged:
        warn = ("<div class='warn'><strong>The sampler has not "
                "converged.</strong> {}</div>".format(
                    html.escape(diagnostics.get("note", ""))))

    tiles = _tiles([
        ("Horizon", "{} days".format(
            simulation["simulation"]["horizon_days"]), "",
         "{:,} paths".format(simulation["simulation"]["paths"])),
        ("Realised volatility", _percent(
            history.get("annualised_volatility"), 1), "", "annualised"),
        ("Persistence", _num(params["alpha"]["p50"] + params["beta"]["p50"],
                             3), "", "alpha plus beta"),
        ("Tail weight", _num(params["nu"]["p50"], 1), "",
         "degrees of freedom"),
        ("VaR 95", _percent(risk.get("var_95"), 2), "neg", "over horizon"),
        ("Expected shortfall 95", _percent(risk.get("es_95"), 2), "neg",
         "mean of the tail"),
        ("VaR 99", _percent(risk.get("var_99"), 2), "neg", "over horizon"),
        ("Converged", "yes" if converged else "no",
         "pos" if converged else "neg", _diagnostic_line(diagnostics)),
    ])

    parameter_rows = []
    for name in ("mu", "omega", "alpha", "beta", "nu"):
        stats = params[name]
        rhat = stats.get("rhat")
        parameter_rows.append(
            "<tr><td>{}</td><td>{:.6g}</td><td>{:.6g}</td><td>{:.6g}</td>"
            "<td>{}</td><td>{:.0f}</td></tr>".format(
                name, stats["p5"], stats["p50"], stats["p95"],
                "n/a" if rhat is None else (
                    "infinite" if rhat == float("inf")
                    else "{:.3f}".format(rhat)),
                stats.get("ess") or 0))

    structures = simulation.get("structures") or []
    structure_rows = []
    for row in sorted(structures, key=lambda r: -(r.get("disagreement") or 0)):
        disagreement = row.get("disagreement")
        tone = ""
        if disagreement is not None:
            tone = "pos" if disagreement > 0 else "neg"
        structure_rows.append(
            "<tr><td>{}</td><td>{}</td><td>{}</td><td class='{}'>{}</td>"
            "<td>{}</td><td>{}</td><td>{}</td></tr>".format(
                html.escape(str(row["strategy"]).replace("_", " ")),
                _percent(row.get("realised_vol_probability_of_profit"), 1),
                _percent(row.get("implied_vol_probability_of_profit"), 1),
                tone,
                ("{:+.1f} pts".format(disagreement * 100)
                 if disagreement is not None else "n/a"),
                _num(row.get("median")), _num(row.get("p5")),
                _num(row.get("expected_shortfall_5"))))

    body = (warn + tiles
            + _panel("Posterior predictive fan",
                     "Every path draws its own parameter set from the "
                     "posterior, so the width carries parameter uncertainty "
                     "as well as volatility. Bands are the 5 to 95 and 25 to "
                     "75 ranges.",
                     "<div id='fan' class='chart'></div>")
            + "<div class='grid2'>"
            + _panel("Terminal distribution",
                     "Where the paths finish. The tail is Student-t, not "
                     "normal, because the returns are.",
                     "<div id='terminal' class='chart short'></div>")
            + _panel("Posterior parameters",
                     "Median with the 5 and 95 percent bounds, plus the "
                     "convergence diagnostics for each parameter.",
                     "<div class='scroll'><table><thead><tr><th>parameter"
                     "</th><th>p5</th><th>median</th><th>p95</th>"
                     "<th>R-hat</th><th>ESS</th></tr></thead><tbody>"
                     + "".join(parameter_rows) + "</tbody></table></div>")
            + "</div>")

    if structure_rows:
        body += _panel(
            "Realised volatility against implied",
            "Probability of profit for each structure under the volatility "
            "the underlying has actually shown, next to the probability "
            "under the volatility its options are priced at. The gap is the "
            "disagreement between the market's forecast and the past, and "
            "neither side of it is the truth.",
            "<div class='scroll'><table><thead><tr><th>structure</th>"
            "<th>P(profit) realised</th><th>P(profit) implied</th>"
            "<th>gap</th><th>median P/L</th><th>p5</th>"
            "<th>expected shortfall</th></tr></thead><tbody>"
            + "".join(structure_rows) + "</tbody></table></div>")

    return "<h2 class='section'>Simulation</h2>" + body


def _backtest_section(backtests):
    """Historical behaviour of each structure, with its honesty statement."""
    if not backtests:
        return ""
    rows = []
    honesty = ""
    for test in backtests:
        stats = test.get("statistics") or {}
        significance = test.get("significance") or {}
        interval = test.get("interval") or {}
        honesty = test.get("honesty", honesty)
        p_value = significance.get("p_value")
        rows.append(
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td>"
            "<td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                html.escape(str(test.get("strategy", "")).replace("_", " ")),
                stats.get("trades", 0),
                _percent(stats.get("win_rate"), 1),
                _percent(stats.get("mean_return"), 2),
                _num(stats.get("total_return_on_risk")),
                _num(stats.get("max_drawdown_in_risk_units")),
                _num(stats.get("sharpe_per_trade"), 3),
                ("{:.4f}".format(p_value) if p_value is not None else "n/a"),
                "yes" if interval.get("excludes_zero") else "no"))

    benchmark = (backtests[0].get("benchmark") or {}).get("statistics") or {}
    benchmark_line = ""
    if benchmark:
        benchmark_line = (
            "<p class='hint'>Buy and hold the underlying over the same "
            "windows: {} per window across {} windows. A structure that "
            "merely tracks the market should be read against this, not "
            "against zero.</p>".format(
                _percent(benchmark.get("mean_return"), 2),
                benchmark.get("trades", 0)))

    return ("<h2 class='section'>Backtest</h2>"
            + _panel(
                "Structures across real history, with modelled premiums",
                "Entered on a fixed schedule and held to expiry. One unit of "
                "capital at risk per trade, returns summed rather than "
                "compounded.",
                benchmark_line
                + "<div class='scroll'><table><thead><tr><th>structure</th>"
                "<th>trades</th><th>win rate</th><th>mean on risk</th>"
                "<th>total</th><th>max drawdown</th><th>sharpe per trade</th>"
                "<th>p-value</th><th>interval excludes zero</th></tr></thead>"
                "<tbody>" + "".join(rows) + "</tbody></table></div>"
                + "<div id='equity' class='chart short'></div>"
                + "<p class='caveat'><strong>What this is not.</strong> {}"
                "</p>".format(html.escape(honesty))))


def _term_section(term_structure):
    """Volatility across expiries, which one chain cannot show."""
    if len(term_structure or []) < 2:
        return ""
    rows = []
    for row in term_structure:
        rows.append(
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td>"
            "<td>{}</td></tr>".format(
                html.escape(str(row.get("expiry"))),
                _num(row.get("days"), 1),
                _percent(row.get("atm_iv"), 2),
                _percent(row.get("risk_reversal"), 2),
                _percent(row.get("butterfly"), 2),
                _num(row.get("expected_move"))))
    return (
        "<h2 class='section'>Term structure</h2>"
        + "<div class='grid2'>"
        + _panel("Volatility and expected move by expiry",
                 "At-the-money volatility on the left axis, the one "
                 "standard deviation move on the right. An upward slope is "
                 "the market charging more for time.",
                 "<div id='term' class='chart short'></div>")
        + _panel("Skew across expiries",
                 "The 25-delta risk reversal and butterfly by tenor. A "
                 "steepening risk reversal means the downside is getting "
                 "relatively dearer as you go out.",
                 "<div id='skewterm' class='chart short'></div>")
        + "</div>"
        + _panel("Every expiry on file",
                 "Pulled chains only. Add more with optiondesk chain SYM "
                 "--expiry DATE.",
                 "<div class='scroll'><table><thead><tr><th>expiry</th>"
                 "<th>days</th><th>atm iv</th><th>25d risk reversal</th>"
                 "<th>25d butterfly</th><th>expected move</th></tr></thead>"
                 "<tbody>" + "".join(rows) + "</tbody></table></div>"))


def _surface_section(surface):
    """Implied volatility by strike and expiry, from every chain on disk."""
    if not surface or len(surface.get("expiries") or []) < 2:
        return ""
    expiries = surface["expiries"]
    listed = ", ".join(
        "{} at {} days ({} strikes)".format(
            row.get("expiry"), _num(row.get("days"), 1), row.get("strikes"))
        for row in expiries)
    return (
        "<h2 class='section'>Volatility surface</h2>"
        + _panel(
            "Implied volatility by strike and expiry",
            "One square per listed contract, at its own strike and its own "
            "expiry's days. Colour is the contract's implied volatility. "
            "Spot is the dotted line; drag to zoom the strike axis.",
            "<div id='surface' class='chart tall'></div>"
            "<p class='assume'>{}</p>".format(html.escape(
                "Out-of-the-money side only: puts below spot, calls at or "
                "above it. Both sides quote a volatility at the same strike "
                "and they disagree, so one had to be chosen and this is the "
                "side that trades. Nothing is interpolated, between strikes "
                "or between expiries: a gap is a strike that is not listed, "
                "and a far expiry looks sparser than a near one because it "
                "quotes fewer strikes. The colour scale runs from the 2nd "
                "to the 75th percentile of the volatilities within the "
                "strike window the view opens on, so that the wings and "
                "the nearest expiry do not take the whole range on their "
                "own; anything above the top of the scale is drawn at the "
                "top colour rather than greyed out, which is why a "
                "short-dated row can saturate. On file: {}.".format(
                    listed)))))


def _premium_section(premium):
    """Implied volatility against the volatility the underlying has shown."""
    if not premium or len(premium.get("rows") or []) < 2:
        return ""
    history = premium.get("history") or {}
    rows = []
    for row in premium["rows"]:
        gap = row.get("gap")
        rows.append(
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td>"
            "<td>{}</td></tr>".format(
                html.escape(str(row.get("expiry"))),
                _num(row.get("days"), 1),
                _percent(row.get("implied"), 2),
                _percent(row.get("realised"), 2),
                ("{:+.2f} pts".format(gap * 100)
                 if gap is not None else "n/a")))
    window = "{} closes from {} to {}".format(
        history.get("observations"), history.get("first"),
        history.get("last"))
    return (
        "<h2 class='section'>Variance risk premium</h2>"
        + _panel(
            "What the options are priced at, against what the underlying "
            "has done",
            "At-the-money implied volatility per expiry on the left axis, "
            "the gap to realised volatility as bars on the right. The "
            "amber line is the realised figure the gap is measured from.",
            "<div id='vrp' class='chart short'></div>"
            "<div class='scroll'><table><thead><tr><th>expiry</th>"
            "<th>days</th><th>implied at the money</th><th>realised</th>"
            "<th>gap</th></tr></thead><tbody>" + "".join(rows)
            + "</tbody></table></div>"
            + "<p class='assume'>{}</p>".format(html.escape(
                "The gap is a disagreement between the market's forecast "
                "and the recent past, not an edge and not a signal. It is "
                "not coloured as profit and loss for that reason. Implied "
                "is the at-the-money volatility of each expiry's own smile; "
                "realised is one annualised figure over {}, from the "
                "simulation's history block, so it is the same number "
                "against every expiry rather than a matched-horizon "
                "estimate.".format(window)))
            + "<p class='caveat'>{}</p>".format(html.escape(
                "The axis is days to expiry, not calendar time. No artifact "
                "on disk carries realised volatility through time: the "
                "simulation records one figure over one window, so the "
                "premium cannot be plotted through calendar time from what "
                "is here, and it is not."))))


def _condor_section(condors):
    """Structures with two short strikes, scored, across every expiry."""
    if not condors:
        return ""
    families = sorted({row["strategy"] for row in condors})
    expiries = sorted({row["expiry"] for row in condors if row.get("expiry")})
    return (
        "<h2 class='section'>Condor search</h2>"
        + _panel(
            "Every condor on file, by the distance between its shorts",
            "Each structure with two short strikes, placed by how far apart "
            "those shorts are and by its expected return on capital at "
            "risk. Size is the capital at risk, colour is the model "
            "probability of profit. The dashed line is zero expectation. A "
            "butterfly sits at zero width: it is a condor whose shorts have "
            "been pulled together.",
            "<div id='condors' class='chart'></div>"
            "<p class='assume'>{}</p>".format(html.escape(
                "This is not a search across the chain. Nothing on disk "
                "enumerates the condors a chain admits, and the engine's "
                "playbook builds exactly one condor per expiry, at the "
                "edges of the expected-move band, so the alternatives it "
                "did not build were never priced and are not here. What is "
                "plotted is the {} structures that exist as artifacts, "
                "across {}: {}. Widths and wing distances are measured off "
                "each plan's own legs; the scores are that expiry's own "
                "comparison artifact, so no structure is ranked against "
                "another expiry's ordering. Adding an expiry adds "
                "points.".format(len(condors), ", ".join(expiries) or "no "
                                 "expiry", ", ".join(families))))))


def _time_spread_section(plans):
    """The structures whose legs live on different expiries.

    They are separated from the rest because their numbers mean something
    different. Every other structure settles on one date, so its maximum
    gain and loss are exact. These are marked at the near expiry with the
    surviving leg priced at the volatility it carries today, so the
    figures are a shape under an unchanged surface, not a forecast.

    The two columns that only exist here are the ones that separate a
    ratio diagonal from a plain one: delta ratio, the short delta mass
    over the long at entry, and giveback, how much of the peak profit the
    structure hands back at the far end of the scan. A 1x1 diagonal can be
    too right. The ratio versions avoid it by holding more back-month
    contracts than front-month ones, which is the property that does the
    work; the delta ratio is a bound on the split, not the reason.
    """
    spreads = []
    for plan in plans or []:
        days = {leg.get("days_to_expiry") for leg in plan.get("legs") or []
                if leg.get("days_to_expiry") is not None}
        if len(days) < 2:
            continue
        analysis = plan.get("analysis") or {}
        legs = plan.get("legs") or []
        near = min(days)
        far = max(days)
        long_leg = next((leg for leg in legs if leg.get("side") == "long"),
                        None)
        short_leg = next((leg for leg in legs if leg.get("side") == "short"),
                         None)
        spreads.append({
            "structure": (plan.get("strategy") or "").replace("_", " "),
            "side": (long_leg or {}).get("kind") or "",
            "near days": _num(near, 1),
            "far days": _num(far, 1),
            "long strike": _num((long_leg or {}).get("strike")),
            "short strike": _num((short_leg or {}).get("strike")),
            "long qty": _num((long_leg or {}).get("qty"), 1),
            "short qty": _num((short_leg or {}).get("qty"), 1),
            "delta ratio": _num(plan.get("delta_ratio"), 3),
            "giveback": _num(plan.get("giveback")),
            "net": _num(analysis.get("net_cash")),
            "max gain": _num(analysis.get("max_gain")),
            "max loss": _num(analysis.get("max_loss")),
        })
    if not spreads:
        return ""
    spreads.sort(key=lambda row: row["structure"])
    columns = ["structure", "side", "near days", "far days", "long strike",
               "short strike", "long qty", "short qty", "delta ratio",
               "giveback", "net", "max gain", "max loss"]
    return (
        "<h2 class='section'>Time spreads</h2>"
        + _panel(
            "Structures with legs on two expiries",
            "Marked at the near expiry with the surviving leg priced at "
            "the volatility it carries today. Delta ratio is the short "
            "delta mass over the long: below one is what keeps a large "
            "move from being capped. Giveback is how much of the peak "
            "profit is handed back at the far end of the scanned range.",
            _table(spreads, columns)
            + "<p class='assume'>Maximum gain and loss here are over the "
              "scanned range rather than over all prices, because the "
              "surviving leg makes the profit a curve with no closed "
              "form. A blank delta ratio means the structure is a 1x1 and "
              "does not hold one.</p>"))


def _gamma_scalp_section(simulation, ladder, plans, expiry):
    """The simulated corridor with the gamma that sits across it."""
    if not simulation:
        return ""
    fan = (simulation.get("simulation") or {}).get("fan") or []
    if not fan:
        return ""
    has_gamma = any(row.get("gamma") is not None
                    for row in ((ladder or {}).get("rows") or []))
    if not has_gamma and not plans:
        return ""
    horizon = (simulation.get("simulation") or {}).get("horizon_days")
    return _panel(
        "Where a delta hedge would be working",
        "The simulated corridor with the structure's own strikes drawn "
        "across it, short strikes dashed amber and long strikes dotted. "
        "Delta moves fastest where gamma is largest, so a delta-hedged "
        "position rebalances most often where the corridor crosses those "
        "levels. Use the structure picker above to change the position.",
        "<div id='gammascalp' class='chart tall'></div>"
        "<p class='assume'>{}</p>".format(html.escape(
            "The five lines are the 5th, 25th, 50th, 75th and 95th "
            "percentiles of the simulated distribution over {} business "
            "days, not five individual paths. The artifact stores the "
            "quantiles per day and no individual path, so individual paths "
            "cannot be drawn from it. The gamma profile on the top axis is "
            "per-contract gamma by strike from the {} ladder, evaluated at "
            "today's spot: it shows where gamma sits in the chain, and it "
            "is not the position's gamma across price, which no artifact "
            "carries. The position's net gamma at spot is the figure in "
            "the structure tiles above.".format(
                horizon if horizon is not None else "the simulated",
                expiry or "graded"))))


def _depth_section(chain_series):
    if not chain_series or not (chain_series.get("calls")
                                or chain_series.get("puts")):
        return ""
    return _panel(
        "Volume by strike",
        "Contracts traded today, calls up and puts down, across the whole "
        "chain rather than the graded band. Open interest is where "
        "positions sit; volume is where they moved.",
        "<div id='volume' class='chart short'></div>")


def _overlay_section(plans, comparison):
    if not plans:
        return ""
    body = _panel(
        "Every structure on one axis",
        "The same payoff curves drawn together, so the shapes can be "
        "compared directly rather than one at a time. Drag to zoom.",
        "<div id='overlay' class='chart tall'></div>")
    if comparison and comparison.get("rows"):
        body += _panel(
            "Probability against expected return",
            "Each structure placed by model probability of profit and "
            "expected return on capital at risk, sized by that capital. "
            "Red is a structure friction calls untradeable. The dashed line "
            "is zero expectation: below it the model expects a loss.",
            "<div id='riskreward' class='chart'></div>")
    return body


def _distribution_section(simulation):
    """One profit distribution per structure, from the simulated paths."""
    if not simulation:
        return ""
    structures = [s for s in (simulation.get("structures") or [])
                  if s.get("histogram")]
    if not structures:
        return ""
    cells = "".join(
        "<div class='panel'><div id='dist{}' class='chart short'></div>"
        "</div>".format(index)
        for index in range(min(6, len(structures))))
    return _panel(
        "Where each structure lands",
        "Profit distribution across the simulated paths, priced at expiry "
        "from the structure's own legs, using the volatility the underlying "
        "has actually shown rather than the volatility its options are "
        "priced at. Green is profit, red is loss, the dashed line is the "
        "median outcome.",
        "<div class='grid3'>" + cells + "</div>")


def _backtest_detail_section(backtests):
    if not backtests:
        return ""
    return ("<div class='grid2'>"
            + _panel("Drawdown from peak",
                     "How far each structure fell below its own running "
                     "high, in units of per-trade risk.",
                     "<div id='drawdown' class='chart short'></div>")
            + _panel("Outcome distribution per trade",
                     "Every trade's return on risk, so a high win rate "
                     "sitting on a few large losses is visible as such.",
                     "<div id='tradehist' class='chart short'></div>")
            + "</div>")


def _panel(title, hint, body):
    return ("<div class='panel'><h3>{}</h3><p class='hint'>{}</p>{}</div>"
            ).format(html.escape(title), html.escape(hint), body)


def render(payload):
    """Render the complete dashboard document from one payload.

    Returns a full HTML page rather than fragments, because the dashboard is
    served without a build step and a fragment that renders alone but not in
    place is a failure that only appears in the browser.
    """
    ladder = payload["ladder"]
    exposure = payload.get("exposure")
    plans = payload["plans"]
    series = payload["series"]

    head = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Option desk</title><style>{}</style>"
        "<script src='/static/echarts.min.js'></script></head><body>"
        "<div class='wrap'>".format(STYLE)
    )

    if not ladder and not plans and not exposure:
        body = (
            "<header class='top'><div class='title'><h1>Option desk</h1>"
            "</div><div class='meta'>{}</div></header>"
            "<div class='panel'><h3>Nothing to show yet</h3>"
            "<p class='hint'>Produce some data first.</p>"
            "<p><code>optiondesk chain SPY</code><br>"
            "<code>optiondesk greeks</code><br>"
            "<code>optiondesk exposure</code><br>"
            "<code>optiondesk compare</code><br>"
            "<code>optiondesk simulate SPY --horizon 14</code></p></div>"
        ).format(html.escape(payload["artifact_dir"]))
        # The body used to be built and then dropped: the return
        # concatenated only the head and the footer, so the first page a
        # new user ever sees was blank between them.
        return head + body + (
            "<footer>{}</footer></div>"
            "<script>window.__OPTIONDESK__ = {};</script>"
            "<script>{}</script></body></html>").format(
            html.escape(payload["disclaimer"]),
            json.dumps({"series": {"calls": [], "puts": []}, "plans": [],
                        "spot": None, "exposure": None, "simulation": None,
                        "backtests": [], "surface": None,
                        "variance_premium": None, "condors": []}), SCRIPT)

    meta = (ladder or exposure or {}).get("meta", {})
    spot = ((ladder or {}).get("spot") or (exposure or {}).get("spot")
            or (plans[0]["spot"] if plans else None))
    underlying = ((ladder or {}).get("underlying")
                  or (exposure or {}).get("underlying")
                  or (plans[0]["underlying"] if plans else ""))
    expiry = ((exposure or {}).get("expiry")
              or (ladder["rows"][0]["expiry"] if ladder and ladder.get("rows")
                  else "")
              or (plans[0].get("expiry") if plans else ""))
    days = (exposure or {}).get("days_to_expiry")
    degraded = bool(meta.get("degraded"))

    header = (
        "<header class='top'><div class='title'>"
        "<h1>Option desk</h1><span class='sym'>{sym}</span>"
        "<span class='meta'>spot {spot} &middot; {expiry}{dte} &middot; "
        "{provider}</span></div>"
        "<div class='meta'><span class='dot{stale}'></span>{status} &middot; "
        "generated {generated} &middot; {path}</div></header>"
    ).format(
        sym=html.escape(str(underlying)),
        spot=_num(spot),
        expiry=html.escape(str(expiry or "no expiry")),
        dte=" ({} days)".format(_num(days, 1)) if days else "",
        provider=html.escape(str(meta.get("provider_used") or "no provider")),
        stale=" stale" if degraded else "",
        status="degraded" if degraded else "clean",
        generated=html.escape(str(meta.get("generated_utc") or "n/a")),
        path=html.escape(str(payload.get("ladder_path")
                             or payload["artifact_dir"])))

    warn = ""
    if degraded:
        warn = ("<div class='warn'><strong>Degraded.</strong> {}</div>"
                .format(html.escape(str(meta.get("degraded_reason") or ""))))

    notes = (meta.get("notes") or [])
    notes_html = ("<ul class='notes'>" + "".join(
        "<li>{}</li>".format(html.escape(str(n))) for n in notes) + "</ul>"
        if notes else "")

    sections = []
    sections.append(_selector(payload.get("groups") or [],
                              payload.get("selected")))

    comparison = payload.get("comparison")
    if comparison:
        sections.append("<h2 class='section'>Structure comparison</h2>"
                        + _comparison_panel(comparison))

    # Directly under the comparison, because it is the same structures read
    # a second way and the reader should meet the two orderings together
    # rather than a screen apart.
    sections.append(_composite_section(comparison,
                                       payload.get("simulation"),
                                       payload.get("backtests"), days))

    sections.append(_time_spread_section(plans))

    if exposure:
        assumption = ("<p class='assume'>{}</p>".format(
            html.escape(exposure["exposure"].get("assumption", ""))))
        sections.append(
            "<h2 class='section'>Positioning</h2>"
            + _positioning_tiles(exposure)
            + _panel(
                "Dealer gamma exposure by strike",
                "Exposure a hedger would have to trade per one percent move, "
                "calls above the line and puts below. Walls are where that "
                "hedging concentrates.",
                "<div id='gex' class='chart'></div>" + assumption)
            + "<div class='grid2'>"
            + _panel("Cumulative exposure and the flip",
                     "Running total across strikes. Where it crosses zero is "
                     "the level below which hedging amplifies moves rather "
                     "than damping them.",
                     "<div id='gexcum' class='chart short'></div>")
            + _panel("Open interest",
                     "Calls up, puts down. Where the contracts actually sit, "
                     "before any assumption about who is on which side.",
                     "<div id='oi' class='chart short'></div>")
            + "</div>"
            + _panel("Max pain profile",
                     "Total payout to option holders at each settlement "
                     "price. The minimum is the conventional max pain level. "
                     "It describes where open interest sits, not where price "
                     "is going.",
                     "<div id='pain' class='chart short'></div>"))

    if exposure and exposure.get("smile"):
        sections.append("<h2 class='section'>Volatility</h2>"
                        + _volatility_tiles(exposure))

    sections.append(_term_section(payload.get("term_structure")))
    sections.append(_surface_section(payload.get("surface")))
    sections.append(_premium_section(payload.get("variance_premium")))

    if series["calls"] or series["puts"]:
        sections.append(_panel(
            "The smile",
            "Implied volatility by strike with the 25-delta wings marked. "
            "The gap between them is the risk reversal, and its sign says "
            "which side of the market is bid.",
            "<div id='smile' class='chart'></div>"))
        sections.append(
            "<div class='grid3'>"
            + _panel("Delta", "dV/dS per 1.0 of underlying",
                     "<div id='delta' class='chart short'></div>")
            + _panel("Gamma", "delta change per 1.0 of underlying",
                     "<div id='gamma' class='chart short'></div>")
            + _panel("Vega", "per 1.00 of volatility",
                     "<div id='vega' class='chart short'></div>")
            + _panel("Theta", "value change per calendar day",
                     "<div id='theta' class='chart short'></div>")
            + _panel("Vanna", "d2V/dS dsigma",
                     "<div id='vanna' class='chart short'></div>")
            + _panel("Charm", "delta change per calendar day",
                     "<div id='charm' class='chart short'></div>")
            + "</div>")

    sections.append(_depth_section(payload.get("chain_series")))

    if plans:
        picker = "".join(
            "<button type='button' aria-pressed='false'>{}</button>".format(
                html.escape(p["strategy"].replace("_", " "))) for p in plans)
        legs_table = _table([], ["leg", "strike", "qty", "price", "bid",
                                 "ask", "iv", "open int"], body_id="plan-legs")
        sections.append(
            "<h2 class='section'>Structures</h2>"
            + _panel(
                "Payoff at expiry",
                "Profit above the zero line, loss below. Spot dotted, "
                "breakevens dashed, expected move shaded. Premiums are mid "
                "quotes, so this is the structure's shape and not a fill.",
                "<div class='picker'>{}</div>"
                "<div id='plan-tiles' class='tiles'></div>"
                "<p class='hint' id='plan-when'></p>"
                "<p class='hint' id='plan-friction'></p>"
                "<div id='payoff' class='chart tall'></div>"
                "{}".format(picker, legs_table)))

    if ladder and ladder.get("rows"):
        columns = ["strike", "type", "iv", "price", "delta", "gamma", "vega",
                   "theta", "rho", "vanna", "vomma", "charm", "speed",
                   "zomma", "color"]
        sections.append(
            "<h2 class='section'>The ladder</h2>"
            + _panel(
                "{} graded contracts".format(len(ladder["rows"])),
                "Theta, charm, veta and color are per calendar day. Vega is "
                "per 1.00 of volatility, so divide by 100 for the per-point "
                "figure. Contracts with no usable implied volatility are not "
                "here: they were skipped, not estimated.",
                _table(ladder["rows"], columns)))

    sections.append(_overlay_section(plans, comparison))
    sections.append(_condor_section(payload.get("condors")))
    sections.append(_simulation_section(payload.get("simulation")))
    sections.append(_distribution_section(payload.get("simulation")))
    sections.append(_gamma_scalp_section(payload.get("simulation"), ladder,
                                         plans, expiry))
    sections.append(_backtest_section(payload.get("backtests")))
    sections.append(_backtest_detail_section(payload.get("backtests")))
    sections.append("<h2 class='section'>Adding data</h2>"
                    + _add_more(payload.get("selected")))

    embedded = json.dumps({
        "series": series,
        "chain_series": payload.get("chain_series")
        or {"calls": [], "puts": []},
        "term_structure": payload.get("term_structure") or [],
        "surface": payload.get("surface"),
        "variance_premium": payload.get("variance_premium"),
        "condors": payload.get("condors") or [],
        "comparison": comparison,
        "spot": spot,
        "plans": plans,
        "exposure": exposure,
        "simulation": payload.get("simulation"),
        "backtests": payload.get("backtests") or [],
    }, default=str)

    return (head + header + warn + notes_html + "".join(sections)
            + ("<footer>{}</footer></div>"
               "<script>window.__OPTIONDESK__ = {};</script>"
               "<script>{}</script></body></html>").format(
                   html.escape(payload["disclaimer"]), embedded, SCRIPT))
