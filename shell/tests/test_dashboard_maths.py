"""The arithmetic printed beside each panel, and the pipeline figure.

Every number the maths blocks quote is read from the engine, and these
tests hold the two together: a constant changed in the engine without the
page following it fails here rather than shipping as a stale formula.
"""

import html as html_module
import inspect

from optiondesk import engine_bridge
from optiondesk.artifacts import envelope
from optiondesk.cli import exposure as exposure_cmd
from optiondesk.contracts import SCHEMA_FILES, SIMULATION, validate
from optiondesk.dashboard import flow, maths
from optiondesk.dashboard import page as page_module

from test_dashboard_page import composite_payload, payload


def rendered():
    return page_module.render(composite_payload())


def test_every_section_on_the_composite_desk_prints_its_arithmetic():
    """Catches a section rendering its chart without its formula.

    The composite desk carries a ladder, an exposure, a simulation and a
    backtest, so four blocks are due: pricing, positioning, simulation and
    backtest. The comparison has no plans, so no structures block, and
    the exposure has no smile, so no volatility block.
    """
    page = rendered()

    assert page.count("<details class='maths'") == 4
    assert "GEX = gamma x OI x" in page
    assert "d1 = [ ln(S / K) + (r - q + sigma^2 / 2) T ]" in page
    assert "sigma_t^2 = omega + alpha e_t-1^2 + beta sigma_t-1^2" in page
    assert "moving-block bootstrap" in page
    assert "P(S_T) = sum over legs" not in page
    assert "risk reversal  RR" not in page


def test_the_blocks_appear_only_with_their_data():
    """Catches a formula printed for a panel that is not on the page."""
    page = page_module.render(payload())

    assert "<details class='maths'" not in page
    assert "<svg class='flowchart'" not in page


def test_the_constants_the_blocks_quote_are_the_engines_own():
    """Catches the page restating a number the engine has since changed.

    Each figure below is read from the engine module that owns it and
    formatted the way the block formats it, so this test knows nothing a
    reader of the page does not.
    """
    assert engine_bridge.AVAILABLE
    c = maths.constants()
    exposure = engine_bridge.analytics().exposure
    smile = engine_bridge.analytics().smile
    friction = engine_bridge.strategies().friction
    garch = engine_bridge.simulation().garch
    paths = engine_bridge.simulation().paths
    stats = engine_bridge.backtest().stats
    pricing = engine_bridge.pricing()

    positioning = maths.positioning(c)
    assert "x {:g} x S^2 x 0.01".format(exposure.CONTRACT_MULTIPLIER) in \
        positioning

    volatility = maths.volatility(c, days=46.1)
    assert "nearest {:.2f}, accepted only within {:.2f}".format(
        smile.TARGET_DELTA, smile.DELTA_TOLERANCE) in volatility
    assert "sqrt(46.1 / {:g})".format(pricing.DAYS_PER_YEAR) in volatility
    assert "x {:g} )".format(stats.TRADING_DAYS) in volatility

    structures = maths.structures(c)
    assert "half spread x {:g}".format(friction.HAIRCUT) in structures
    assert "ok below {:.0%} of the net premium, thin up to {:.0%}".format(
        friction.OK_MAX, friction.THIN_MAX) in structures
    assert "wider than {:.0%} of its own mid".format(
        friction.MAX_REL_SPREAD) in structures

    simulation = maths.simulation(c)
    assert "{} chains of {:,} draws after {:,} burn-in".format(
        garch.DEFAULT_CHAINS, garch.DEFAULT_DRAWS, garch.DEFAULT_BURN) in \
        simulation
    assert "split R-hat < {:g} and effective sample size >= {}".format(
        garch.RHAT_LIMIT, garch.MIN_ESS) in simulation
    assert "{:,} paths".format(paths.DEFAULT_PATHS) in simulation

    priced = maths.pricing(c)
    assert "bisection on [{:g}, {:g}]".format(
        pricing.IV_MIN, pricing.IV_MAX) in priced
    assert "vega > {:g}".format(pricing.MIN_VEGA) in priced
    assert "r = {:g}, q = {:g}".format(
        pricing.DEFAULT_R, pricing.DEFAULT_Q) in priced


def test_without_the_engine_the_blocks_name_the_constant_not_a_number(
        monkeypatch):
    """Catches the shell inventing a figure the engine would have supplied.

    A shell installed without the engine still renders the page. Its
    formulas must then show the constant's name, so a reader sees that
    the value is missing rather than a number the shell made up.
    """
    monkeypatch.setattr(engine_bridge, "AVAILABLE", False)

    assert maths.constants() is None
    assert "x MULTIPLIER x S^2" in maths.positioning(None)
    assert "RHAT_LIMIT" in maths.simulation(None)
    assert "OK_MAX" in maths.structures(None)
    assert "IV_MIN" in maths.pricing(None)


def test_the_backtest_block_quotes_the_artifacts_own_schedule():
    """Catches a formula describing a schedule the run did not use.

    The block, the trial count and the interval level are properties of
    the artifact on the page, not of the engine's defaults, and the text
    must follow the artifact.
    """
    backtests = [{
        "strategy": "iron_condor",
        "settings": {"holding_days": 30, "entry_every": 5, "lookback": 60,
                     "first_date": "2021-09-03", "last_date": "2026-09-03"},
        "significance": {"p_value": 0.02, "trials": 2000, "block": 6},
        "interval": {"level": 0.9, "trials": 2000, "block": 6},
    }]
    text = maths.backtest(maths.constants(), backtests)

    assert "enter every 5 trading days, hold 30 trading days" in text
    assert "from 2021-09-03 to 2026-09-03" in text
    assert "b = ceil(30 / 5) = 6" in text
    assert "2,000 times" in text
    assert "90% interval" in text
    assert "over the last 60 closes" in text

    bare = maths.backtest(maths.constants(), None)
    assert "b = ceil(H / E)" in bare
    assert "every E trading days, hold H trading days" in bare


def simulation_artifact(**overrides):
    """A simulation artifact as the command writes it, schema-validated.

    The run deliberately uses none of the engine defaults: 4 chains rather
    than 2, 6,000 draws rather than 3,000, 2,000 burn-in rather than 1,000,
    5,000 paths rather than 20,000. A block that prints a default in place
    of one of these is printing a number the run did not use, and a
    fixture built on the defaults could not tell the two apart.

    The settings sit where cli/simulate.py puts them: chains, draws and
    burn-in in posterior.diagnostics under the engine's own key names, and
    the requested path count beside the kept one in the simulation block.
    An earlier fixture invented posterior.settings and simulation.paths
    alone, so the test passed against keys no artifact carried.
    """
    garch = engine_bridge.simulation().garch
    diagnostics = {
        "chains": 4, "draws_per_chain": 6000, "burn_in": 2000,
        "acceptance_rate": 0.3, "acceptance_rate_including_burn_in": 0.3,
        "rhat": {"mu": 1.01}, "ess": {"mu": 400.0}, "converged": True,
        "rhat_limit": garch.RHAT_LIMIT, "min_ess": garch.MIN_ESS,
        "note": "",
    }
    artifact = {
        "meta": envelope(schema=SIMULATION, tool="optiondesk simulate",
                         provider_used="stub"),
        "underlying": "TEST",
        "spot": 100.0,
        "history": {"observations": 1254, "first": "2021-09-03",
                    "last": "2026-09-03", "period": "5y",
                    "annualised_volatility": 0.2},
        "posterior": {"converged": True, "parameters": {},
                      "diagnostics": diagnostics},
        "simulation": {"horizon_days": 30, "paths": 4998,
                       "requested_paths": 5000, "antithetic": False,
                       "fan": [], "terminal_histogram": []},
        "risk": None,
        "structures": [],
    }
    artifact.update(overrides)
    validate(artifact, SCHEMA_FILES[SIMULATION])
    return artifact


def test_the_simulation_block_quotes_the_artifacts_own_history():
    text = maths.simulation(maths.constants(), simulation_artifact())

    assert "over 1,254 daily returns (2021-09-03 to 2026-09-03)" in text
    assert "daily closes" not in text
    assert "5,000 paths (4,998 kept)" in text
    assert "30 business days out" in text


def test_the_simulation_block_quotes_the_runs_own_sampler_settings():
    """Catches the block printing the engine defaults for every run.

    Measured at ac72957: a 4-chain, 6,000-draw, 2,000-burn-in artifact
    printed "2 chains of 3,000 draws after 1,000 burn-in", and a
    5,000-path run printed "20,000 paths (4,998 kept)", because the block
    read keys the command never writes and fell back to the defaults.
    """
    garch = engine_bridge.simulation().garch
    paths = engine_bridge.simulation().paths
    text = maths.simulation(maths.constants(), simulation_artifact())

    assert "4 chains of 6,000 draws after 2,000 burn-in" in text
    assert "5,000 paths (4,998 kept)" in text
    defaults = "{} chains of {:,} draws after {:,} burn-in".format(
        garch.DEFAULT_CHAINS, garch.DEFAULT_DRAWS, garch.DEFAULT_BURN)
    assert defaults not in text
    assert "{:,} paths".format(paths.DEFAULT_PATHS) not in text


def test_an_artifact_without_a_requested_count_states_only_what_it_kept():
    """Artifacts written before requested_paths existed carry the kept
    count alone. Beside the engine default that read "20,000 paths (200
    kept)" for a 200-path run; alone it is simply true.
    """
    paths = engine_bridge.simulation().paths
    old = simulation_artifact()
    del old["simulation"]["requested_paths"]
    old["simulation"]["paths"] = 200
    text = maths.simulation(maths.constants(), old)

    assert "200 paths;" in text
    assert "{:,}".format(paths.DEFAULT_PATHS) not in text

    complete = simulation_artifact()
    complete["simulation"]["paths"] = 5000
    assert "5,000 paths, all kept" in maths.simulation(maths.constants(),
                                                      complete)


def test_the_history_annualisation_the_block_quotes_is_the_one_used():
    """The realised figure is computed in cli/simulate.py with the shell's
    own trading-day constant; the block prints the engine's. They are the
    same number today, and this holds them together.
    """
    from optiondesk.cli import simulate as simulate_cmd

    stats = engine_bridge.backtest().stats
    assert simulate_cmd.TRADING_DAYS == stats.TRADING_DAYS
    text = maths.volatility(maths.constants())
    assert "sum over t of r_t^2 x {:g} )".format(stats.TRADING_DAYS) in text
    assert "uncentred and divided by n" in text
    assert "sample variance" not in text.split("realised")[1].split(
        "premium gap")[0].replace("centred sample variance", "")


def test_the_pricing_block_states_the_chains_own_carry():
    text = maths.pricing(maths.constants(), 0.0392, 0.0097)

    assert "(this chain: r = 0.0392, q = 0.0097)" in text
    assert "(this chain" not in maths.pricing(maths.constants())


def test_the_time_spread_block_states_the_scan_it_read():
    text = maths.time_spreads(maths.constants(), {"scanned_fraction": 0.4})
    assert "S from 60% to 140% of spot" in text

    bare = maths.time_spreads(maths.constants(), None)
    assert "a stated fraction below" in bare


def test_blocks_escape_their_text():
    """The formulas are full of < and &, which are markup if unescaped."""
    block = maths.block("a < b & c > d")

    assert "a &lt; b &amp; c &gt; d" in block
    assert "<pre class='cmds maths'>" in block
    assert block.startswith("<details class='maths' open>")


def test_the_pipeline_figure_names_every_artifact_and_reads_them_all():
    """Catches the figure drifting from the artifacts the desk writes."""
    figure = flow.diagram()
    page = rendered()

    for _, _, title, artifact, _ in flow.NODES.values():
        assert html_module.escape(title) in figure
        assert html_module.escape(artifact) in figure
    assert figure.count("<path class='arrow") == len(flow.EDGES)
    assert page.count("<svg class='flowchart'") == 1
    assert "How this page was built" in page
    assert "reads all of them and writes nothing" in page
    assert "Nothing here places an order" in page


def test_the_pipeline_edges_join_real_nodes_and_no_two_nodes_share_a_cell():
    cells = [node[:2] for node in flow.NODES.values()]
    assert len(cells) == len(set(cells))
    for source, target, _, shape in flow.EDGES:
        assert source in flow.NODES
        assert target in flow.NODES
        assert shape in ("right", "down", "under")


def test_the_exposure_box_is_fed_by_the_chain_and_not_the_ladder():
    """Catches the figure drawing layout as data flow.

    The exposure command opens chain_*.json and prices gamma for every
    contract itself; it never reads a ladder. The figure drew
    greeks -> exposure because the two boxes sit side by side. The source
    of the command is read here so the edge cannot be put back without
    the command changing first.
    """
    source = inspect.getsource(exposure_cmd.run)
    assert 'latest("chain_*.json"' in source
    assert "greeks_" not in source

    joins = {(edge[0], edge[1]) for edge in flow.EDGES}
    assert ("chain", "exposure") in joins
    assert ("greeks", "exposure") not in joins


def test_the_caption_calls_the_two_inputs_inputs():
    """The source and the closes are fetched or supplied, not commands
    that write artifacts, and the caption used to say every box was
    both. The ledger claim is kept: the page now renders the ledger.
    """
    caption = flow.CAPTION
    assert "inputs, not commands" in caption
    assert "reads all of them and writes nothing" in caption
    assert "Every box is one command" not in caption
    assert "exposure command reads the chain snapshot" in caption
