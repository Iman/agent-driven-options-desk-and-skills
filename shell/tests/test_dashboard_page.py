"""The dashboard page: what appears, what is escaped, what is not claimed."""

import json
import re

import pytest

from optiondesk.artifacts import DISCLAIMER, envelope, write_json
from optiondesk.dashboard import app as app_module
from optiondesk.dashboard import page as page_module


def payload(**overrides):
    base = {"artifact_dir": "/tmp/artifacts", "ladder": None,
            "ladder_path": None, "exposure": None, "exposure_path": None,
            "comparison": None, "plans": [], "groups": [], "selected": None,
            "series": {"calls": [], "puts": []}, "disclaimer": DISCLAIMER}
    base.update(overrides)
    return base


def ladder(degraded=False, degraded_reason=None, notes=None,
           provider_used="stub"):
    return {
        "meta": envelope(schema="optiondesk/greeks_ladder/v1",
                         tool="test", provider_used=provider_used,
                         degraded=degraded, degraded_reason=degraded_reason,
                         notes=notes),
        "underlying": "TEST", "spot": 100.0, "expiry": "2026-09-18",
        "units": {"delta": "a", "vega": "b", "theta": "c"},
        "rows": [{"type": "call", "strike": 100.0, "expiry": "2026-09-18",
                  "iv": 0.3, "price": 3.59, "delta": 0.55, "gamma": 0.03,
                  "vega": 0.11, "theta": -0.05}],
    }


def test_an_empty_desk_still_renders_a_complete_document():
    """Catches a fresh install raising instead of rendering.

    render indexes ladder, plans and series without .get, so an empty
    collection is the first thing that would break on a new machine.

    This asserts only what the branch currently produces. The getting
    started panel it builds is assigned to a local and never concatenated
    into the return value, so none of that text reaches the page; that is
    reported as a defect rather than pinned here as intended behaviour.
    """
    html = page_module.render(payload())

    assert html.startswith("<!doctype html>")
    assert html.rstrip().endswith("</html>")
    assert "not investment advice" in html


def test_degradation_is_shown_as_a_banner_with_its_reason():
    """Catches a degraded artifact rendering as a clean one.

    The flag exists so a reader hesitates before quoting the numbers. A
    page that does not show it has thrown that away.
    """
    html = page_module.render(payload(
        ladder=ladder(degraded=True,
                      degraded_reason="risk-free rate: ^IRX unavailable")))

    assert "Degraded." in html
    assert "^IRX unavailable" in html
    assert ">degraded" in html


def test_notes_are_shown_without_claiming_the_page_is_degraded():
    """Catches notes and degradation being conflated on the page.

    Wing contracts with no quotes are an observation. Rendering that as a
    degradation banner would mark almost every page degraded and the banner
    would stop meaning anything.
    """
    html = page_module.render(payload(
        ladder=ladder(notes=["23 contracts carry no implied volatility"])))

    assert "23 contracts carry no implied volatility" in html
    assert "Degraded." not in html
    assert ">clean" in html


def test_values_taken_from_artifacts_are_escaped():
    """Catches markup in an artifact being written into the page verbatim.

    Artifacts are files on disk; the page must not treat their contents as
    trusted markup.
    """
    html = page_module.render(payload(
        ladder=ladder(provider_used="<b>evil</b>")))

    assert "&lt;b&gt;evil&lt;/b&gt;" in html


def test_the_ladder_table_states_that_skipped_contracts_are_absent():
    """Catches the ladder being read as the whole chain.

    Contracts with no usable volatility are not in the table. Without the
    sentence saying so, a reader counts rows and concludes the chain is
    smaller than it is.
    """
    html = page_module.render(payload(ladder=ladder()))

    assert "1 graded contracts" in html
    assert "skipped, not estimated" in html


def test_the_disclaimer_is_on_every_page():
    """Catches the disclaimer surviving only on the populated page.

    It is a licence and liability requirement, not decoration.
    """
    empty = page_module.render(payload())
    populated = page_module.render(payload(ladder=ladder()))

    for html in (empty, populated):
        assert "not investment advice" in html


def test_the_page_is_a_pure_function_of_its_payload():
    """Catches a clock, a random value, or set ordering reaching the markup.

    The page is meant to be a pure function of the collected data; anything
    else makes it untestable and makes two tabs disagree.
    """
    given = payload(ladder=ladder())
    assert page_module.render(given) == page_module.render(given)


def test_the_embedded_payload_is_valid_json():
    """Catches a chart payload the browser cannot parse.

    Every chart on the page reads this one blob, so a malformed value here
    silently empties all of them at once.
    """
    html = page_module.render(payload(ladder=ladder()))
    start = html.index("window.__OPTIONDESK__ = ") + len(
        "window.__OPTIONDESK__ = ")
    end = html.index("};</script>", start) + 1
    embedded = json.loads(html[start:end])

    assert embedded["spot"] == 100.0
    assert embedded["series"] == {"calls": [], "puts": []}


def test_the_selector_marks_the_current_group_and_links_the_others(tmp_path):
    """Catches the picker losing the current selection or an addressable link.

    Plain query-parameter links are what make every view bookmarkable.
    """
    for expiry in ("2026-09-18", "2026-10-16"):
        write_json({"underlying": "TEST", "expiry": expiry, "spot": 100.0,
                    "meta": {}},
                   "chain_TEST_{}.json".format(expiry), tmp_path)
    write_json({"underlying": "TEST", "expiry": "2026-09-18", "spot": 100.0,
                "meta": {}, "exposure": {"rows": [], "net_gex": 0.0,
                                         "assumption": "stated"}},
               "exposure_TEST_2026-09-18.json", tmp_path)

    html = app_module.render_index(str(tmp_path), "TEST", "2026-09-18")
    assert "?u=TEST&amp;e=2026-09-18" in html
    assert "?u=TEST&amp;e=2026-10-16" in html
    assert "class='pill on'" in html


def test_numbers_are_formatted_and_missing_ones_say_so():
    """Catches a missing value being rendered as zero.

    A gamma flip that could not be computed and one that sits at zero are
    different facts, and n/a is how the page keeps them apart.
    """
    assert page_module._num(None) == "n/a"
    assert page_module._num(1234.5) == "1,234.50"
    assert page_module._percent(None) == "n/a"
    assert page_module._percent(0.2512, 2) == "25.12%"
    assert page_module._compact(None) == "n/a"
    assert page_module._compact(2.5e9) == "2.50bn"
    assert page_module._compact(-1500.0) == "-1.5k"


def comparison(max_gain="unlimited", rows=None):
    return {
        "criterion": "model expected profit divided by capital at risk",
        "caveat": "This is an ordering under stated assumptions, not a "
                  "recommendation to trade any of them.",
        "leader": {"strategy": "long_call", "expected_return_on_risk": 0.061,
                   "probability_of_profit": 0.43, "capital_at_risk": 1.89,
                   "friction_verdict": "ok"},
        "margin_over_runner_up": 0.0097,
        "rankable_count": 1,
        "excluded_count": 1,
        "rows": rows if rows is not None else [
            {"rank": 1, "strategy": "long_call", "trade_type": "debit",
             "net_cash": -3.59, "max_gain": max_gain, "max_loss": -3.59,
             "capital_at_risk": 3.59, "reward_risk": None,
             "probability_of_profit": 0.43, "expected_pnl": 0.22,
             "expected_return_on_risk": 0.061, "net_delta": 0.55,
             "net_theta": -0.05, "net_vega": 0.11, "rankable": True,
             "friction_verdict": "ok"},
            {"rank": None, "strategy": "iron_condor", "trade_type": "credit",
             "net_cash": 0.76, "max_gain": 0.76, "max_loss": -4.24,
             "capital_at_risk": 4.24, "reward_risk": 0.18,
             "probability_of_profit": None, "expected_pnl": None,
             "expected_return_on_risk": None, "net_delta": 0.0,
             "net_theta": 0.0, "net_vega": 0.0, "rankable": False,
             "excluded_because": ["no probability could be computed"],
             "friction_verdict": "untradeable"},
        ],
        "ranked": ["long_call"],
    }


def test_an_unbounded_gain_reaches_the_table_as_the_word_unlimited():
    """Catches the sentinel being formatted as a number or dropped.

    The comparison formats every other cell with a float format. Passing a
    string through that would raise; silently blanking it would erase the
    only structure on the page with uncapped upside.
    """
    html = page_module.render(payload(ladder=ladder(),
                                      comparison=comparison()))
    assert ">unlimited<" in html


def test_the_comparison_shows_its_criterion_and_its_caveat():
    """Catches an ordering published as a ranking with no stated basis.

    Without the criterion and the caveat the table reads as advice.
    """
    html = page_module.render(payload(ladder=ladder(),
                                      comparison=comparison()))

    assert "model expected profit divided by capital at risk" in html
    assert "not a recommendation to trade" in html
    assert "Read this before using the order." in html


def test_an_unrankable_structure_is_shown_with_why_it_was_excluded():
    """Catches an excluded structure vanishing from the table.

    A missing row reads as a structure that lost the comparison, which is a
    different claim from one that could not be scored.
    """
    html = page_module.render(payload(ladder=ladder(),
                                      comparison=comparison()))

    assert "iron condor" in html
    assert "no probability could be computed" in html
    assert "class='out'" in html or "out'" in html


def test_positioning_and_volatility_tiles_render_from_an_exposure():
    """Catches the tiles losing the assumption or a wall.

    Every wall on the page rests on the dealer sign convention, and a
    reader who cannot see it cannot judge the level.
    """
    exposure = {
        "meta": envelope(schema="optiondesk/exposure/v1", tool="test",
                         provider_used="stub"),
        "underlying": "TEST", "spot": 100.0, "expiry": "2026-09-18",
        "days_to_expiry": 30.0,
        "exposure": {"rows": [], "net_gex": 2.5e9, "regime": "dampening",
                     "gamma_flip": 98.5,
                     "call_wall": {"strike": 105.0, "gex": 1.2e9},
                     "put_wall": {"strike": 95.0, "gex": -1.1e9},
                     "put_call_oi_ratio": 1.2,
                     "put_call_volume_ratio": 0.9,
                     "assumption": "dealers are long calls and short puts"},
        "max_pain": {"strike": 100.0},
        "smile": {"atm_iv": 0.30, "atm_strike": 100.0,
                  "risk_reversal": 0.008, "butterfly": 0.001,
                  "skew_slope_per_percent": -0.0021,
                  "expected_move": 8.6, "expected_range": [91.4, 108.6]},
    }
    html = page_module.render(payload(exposure=exposure))

    assert "Net gamma exposure" in html and "2.50bn" in html
    assert "dampening" in html
    assert "Call wall" in html and "105.00" in html
    assert "Max pain" in html
    assert "At-the-money IV" in html and "30.00%" in html
    assert "Expected range" in html and "91.40 to 108.60" in html
    assert "dealers are long calls and short puts" in html


# --------------------------------------------------------------------------
# The four cross-expiry panels. Each canvas must appear only when the
# artifact behind it is on disk, and each must carry its own assumption
# where the reader can see it, the way the exposure panels carry the
# dealer sign convention.
# --------------------------------------------------------------------------


def canvases(html):
    """Every chart container on the page, in the order they appear."""
    return re.findall(r"<div id='([^']+)' class='chart", html)


SURFACE = {"points": [[95.0, 20.0, 0.30, "2026-09-18"],
                      [105.0, 20.0, 0.22, "2026-09-18"],
                      [95.0, 47.0, 0.28, "2026-10-16"],
                      [105.0, 47.0, 0.24, "2026-10-16"]],
           "expiries": [{"expiry": "2026-09-18", "days": 20.0, "spot": 100.0,
                         "strikes": 2},
                        {"expiry": "2026-10-16", "days": 47.0, "spot": 100.0,
                         "strikes": 2}]}

PREMIUM = {"rows": [{"expiry": "2026-09-18", "days": 20.0, "implied": 0.20,
                     "realised": 0.30, "gap": -0.10},
                    {"expiry": "2026-10-16", "days": 47.0, "implied": 0.25,
                     "realised": 0.30, "gap": -0.05}],
           "realised": 0.30,
           "history": {"observations": 500, "first": "2024-08-29",
                       "last": "2026-08-28", "period": "2y"}}

CONDORS = [{"strategy": "iron_condor", "expiry": "2026-09-18", "days": 20.0,
            "short_low": 90.0, "short_high": 110.0, "width": 20.0,
            "wing": 5.0, "expected_return_on_risk": 0.12,
            "probability_of_profit": 0.7, "capital_at_risk": 8.0,
            "net_cash": 2.0, "max_loss": -8.0, "friction_verdict": "ok",
            "rank": 1}]

SIMULATION = {
    "spot": 100.0,
    "history": {"annualised_volatility": 0.30, "observations": 500,
                "first": "2024-08-29", "last": "2026-08-28", "period": "2y"},
    "posterior": {"converged": True,
                  "parameters": {name: {"p5": 0.1, "p50": 0.2, "p95": 0.3,
                                        "rhat": 1.0, "ess": 400.0}
                                 for name in ("mu", "omega", "alpha", "beta",
                                              "nu")},
                  "diagnostics": {"rhat": {"mu": 1.0}, "ess": {"mu": 400.0},
                                  "note": ""}},
    "simulation": {"horizon_days": 14, "paths": 2000,
                   "fan": [{"day": 1, "p5": 97.0, "p25": 99.0, "p50": 100.0,
                            "p75": 101.0, "p95": 103.0}],
                   "terminal_histogram": []},
    "risk": {"var_95": 0.03, "es_95": 0.05, "var_99": 0.06},
    "structures": [],
}


def test_the_surface_canvas_appears_only_with_more_than_one_chain():
    """Catches a surface panel drawn over a single expiry, or none at all.

    The collector returns None below two expiries. If the page drew the
    canvas anyway the script would mount an empty chart, and if it refused
    a real surface the whole panel would silently vanish.
    """
    without = page_module.render(payload(ladder=ladder()))
    assert "id='surface'" not in without
    assert "Volatility surface" not in without

    with_it = page_module.render(payload(ladder=ladder(), surface=SURFACE))
    assert "id='surface'" in with_it
    assert "surface" in canvases(with_it)


def test_the_surface_states_which_side_of_the_strike_it_drew():
    """Catches the out-of-the-money rule going unstated.

    A call and a put at one strike quote different volatilities. A reader
    who does not know which was taken cannot read the panel at all.
    """
    html = page_module.render(payload(ladder=ladder(), surface=SURFACE))

    assert "Out-of-the-money side only" in html
    assert "puts below spot, calls at or above it" in html
    assert "Nothing is interpolated" in html
    # The expiries it actually drew, so a missing chain is visible as one.
    assert "2026-09-18 at 20.0 days (2 strikes)" in html


def test_the_premium_canvas_appears_only_with_a_realised_figure():
    """Catches a premium panel drawn with nothing to measure the gap from."""
    without = page_module.render(payload(ladder=ladder()))
    assert "id='vrp'" not in without

    with_it = page_module.render(payload(ladder=ladder(),
                                         variance_premium=PREMIUM))
    assert "id='vrp'" in with_it
    assert "Variance risk premium" in with_it


def test_the_premium_is_labelled_a_disagreement_and_not_an_edge():
    """Catches the gap being presented as something to trade.

    The simulation skill's rule: the gap between implied and realised is a
    disagreement between the market's forecast and the recent past. A
    panel that implies otherwise is the failure this assertion exists for.
    """
    html = page_module.render(payload(ladder=ladder(),
                                      variance_premium=PREMIUM))

    # Apostrophe-free fragments: the panel text is escaped on the way out,
    # so asserting on "market's" would be asserting on the escaping.
    assert "not an edge and not a signal" in html
    assert "disagreement between the market" in html
    assert "and the recent past" in html
    # And the window the realised figure came from, not just the figure.
    assert "500 closes from 2024-08-29 to 2026-08-28" in html
    # And that the axis is tenor, not calendar time.
    assert "days to expiry, not calendar time" in html


def test_the_condor_panel_says_it_is_not_a_search_across_the_chain():
    """Catches the scatter being read as every condor the chain admits.

    Nothing on disk enumerates them and the playbook builds one per
    expiry, so a panel titled as a search would overstate what it shows by
    orders of magnitude.
    """
    without = page_module.render(payload(ladder=ladder()))
    assert "id='condors'" not in without

    html = page_module.render(payload(ladder=ladder(), condors=CONDORS))
    assert "id='condors'" in html
    assert "This is not a search across the chain" in html
    assert "builds exactly one condor per expiry" in html


def test_the_gamma_panel_needs_a_simulation_and_something_to_overlay():
    """Catches the panel appearing with nothing to draw on the corridor.

    Without a ladder or a plan there are no strikes and no gamma profile,
    which leaves a chart that repeats the fan panel above it.
    """
    # An exposure, so the page gets past the empty-desk branch and the
    # guard is actually reached. Written with ladder=None and plans=[] and
    # no exposure, this assertion passed because the whole page was the
    # "nothing to show yet" one, and the mutation harness proved it could
    # not fail.
    bare = {"underlying": "TEST", "expiry": "2026-09-18", "spot": 100.0,
            "meta": {}, "exposure": {"rows": [], "net_gex": 0.0,
                                     "assumption": "stated"}}
    alone = page_module.render(payload(ladder=None, exposure=bare,
                                       plans=[], simulation=SIMULATION))
    assert "id='gex'" in alone, "the page must have rendered for real"
    assert "id='gammascalp'" not in alone

    with_ladder = page_module.render(payload(ladder=ladder(),
                                             simulation=SIMULATION))
    assert "id='gammascalp'" in with_ladder


def test_the_gamma_panel_refuses_to_call_the_fan_a_set_of_paths():
    """Catches quantiles being presented as individual simulated paths.

    The artifact stores p5 to p95 per day and nothing else. Five
    trajectories labelled as paths would be five claims about paths that
    were never recorded.
    """
    html = page_module.render(payload(ladder=ladder(), simulation=SIMULATION))

    assert "not five individual paths" in html
    assert "individual paths cannot be drawn from it" in html
    # And that the gamma shown is the chain's, not the position's.
    assert "gamma across price, which no artifact carries" in html


def test_none_of_the_four_panels_appear_on_an_empty_desk():
    """Catches a new install showing four empty canvases.

    Every canvas on this page renders only when its artifact exists, and
    the empty-desk branch embeds its own payload, so a key the script
    reads unguardedly would throw on the very first page.
    """
    html = page_module.render(payload())

    assert canvases(html) == []
    for missing in ("id='surface'", "id='vrp'", "id='condors'",
                    "id='gammascalp'"):
        assert missing not in html
    start = html.index("window.__OPTIONDESK__ = ") + len(
        "window.__OPTIONDESK__ = ")
    embedded = json.loads(html[start:html.index("};</script>", start) + 1])
    assert embedded["surface"] is None
    assert embedded["variance_premium"] is None
    assert embedded["condors"] == []


def test_the_four_new_payload_keys_reach_the_script():
    """Catches a panel being drawn over a blob that does not carry its data.

    The markup and the data are wired separately. A canvas with no entry
    in the embedded payload is a permanently blank chart, and it looks
    exactly like a chart whose artifact is missing.
    """
    html = page_module.render(payload(
        ladder=ladder(), surface=SURFACE, variance_premium=PREMIUM,
        condors=CONDORS, simulation=SIMULATION))
    start = html.index("window.__OPTIONDESK__ = ") + len(
        "window.__OPTIONDESK__ = ")
    embedded = json.loads(html[start:html.index("};</script>", start) + 1])

    assert len(embedded["surface"]["points"]) == 4
    assert embedded["variance_premium"]["realised"] == 0.30
    assert embedded["condors"][0]["width"] == 20.0
    assert embedded["simulation"]["simulation"]["fan"][0]["p50"] == 100.0
