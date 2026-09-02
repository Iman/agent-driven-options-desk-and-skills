"""The desk's commands, as LangChain tools.

Every tool is a thin wrapper over a CLI runner that already exists. The
wrapper adds no arithmetic and makes no decision: it validates arguments,
calls the command, and returns the same JSON summary the command prints.

Two properties are deliberate.

Tools never compute. If a tool did arithmetic of its own, the same question
asked through the CLI and through an agent would eventually give different
answers, and there would be no way to tell which was right.

Tools return the summary, not the artifact. The summary is small, carries
the provenance and the degraded flag, and names the artifact path for
anything that needs the full detail. Returning the whole artifact would
fill a context window with a chain of six hundred contracts.
"""

import inspect
from typing import Any

from optiondesk.cli import backtest as backtest_cmd
from optiondesk.cli import chain as chain_cmd
from optiondesk.cli import compare as compare_cmd
from optiondesk.cli import expiries as expiries_cmd
from optiondesk.cli import exposure as exposure_cmd
from optiondesk.cli import forward as forward_cmd
from optiondesk.cli import greeks as greeks_cmd
from optiondesk.cli import plots as plots_cmd
from optiondesk.cli import simulate as simulate_cmd
from optiondesk.cli import strategy as strategy_cmd


class _Args:
    """A namespace the CLI runners accept, built from declared defaults.

    Only declared parameters are honoured. An undeclared key is dropped
    rather than set, so a caller cannot reach a runner argument the tool
    does not advertise, such as the output directory.
    """

    def __init__(self, defaults, supplied):
        self.rejected = []
        for key, value in defaults.items():
            setattr(self, key, value)
        for key, value in (supplied or {}).items():
            if key in defaults:
                setattr(self, key, value)
            else:
                self.rejected.append(key)


SPECS = [
    {
        "name": "option_chain_snapshot",
        "description": (
            "Retrieve an option chain for one underlying and expiry from a "
            "free data provider or uploaded snapshot, solve implied volatility "
            "per contract, and "
            "write a schema validated snapshot. Returns the artifact path "
            "and a summary. Delayed third party data."),
        "runner": chain_cmd.run,
        "defaults": {"symbol": None, "expiry": None, "provider": None,
                     "source_path": None, "from_file": None, "rate": None,
                     "dividend_yield": 0.0, "out_dir": None},
        "public": ("symbol", "expiry", "source_path", "dividend_yield",
                   "rate"),
    },
    {
        "name": "option_expiries",
        "description": (
            "List the expiries a provider carries for an underlying with "
            "days to expiry, marking which are already on disk. Omit the "
            "symbol to list only what is local, with no network access."),
        "runner": expiries_cmd.run,
        "defaults": {"symbol": None, "provider": None, "out_dir": None},
        "public": ("symbol",),
    },
    {
        "name": "option_greeks_ladder",
        "description": (
            "Compute the full first to third order Greek ladder from a "
            "chain snapshot, using each contract's own implied volatility. "
            "Contracts without a usable volatility are skipped and counted, "
            "never defaulted."),
        "runner": greeks_cmd.run,
        "defaults": {"snapshot": None, "band": 0.10, "type": "both",
                     "out_dir": None},
        "public": ("snapshot", "band", "type"),
    },
    {
        "name": "option_plots",
        "description": (
            "Fetch or read a chain and write opaque PNG charts for direct "
            "display: positioning, open interest, volume, implied volatility, "
            "delta, gamma, theta and vega. Use when the user asks to see "
            "plots; return the image paths instead of starting a dashboard."),
        "runner": plots_cmd.run,
        "defaults": {"symbol": None, "expiry": None, "snapshot": None,
                     "source_path": None, "rate": None,
                     "dividend_yield": None, "band": 0.15,
                     "out_dir": None},
        "public": ("symbol", "expiry", "snapshot", "source_path", "rate",
                   "dividend_yield", "band"),
    },
    {
        "name": "option_positioning",
        "description": (
            "Dealer gamma exposure by strike, the call and put walls, the "
            "gamma flip levels, max pain, put to call ratios and volatility "
            "smile geometry. Signs rest on an assumption about who holds "
            "what, which the output states."),
        "runner": exposure_cmd.run,
        "defaults": {"snapshot": None, "multiplier": 100.0, "out_dir": None},
        "public": ("snapshot", "multiplier"),
    },
    {
        "name": "option_strategy_build",
        "description": (
            "Build one structure from a chain: iron condor, butterfly, "
            "vertical spreads, straddle, strangle, covered call, cash "
            "secured put, protective put, calendar or diagonal. Pass "
            "list_only to see the playbook, or recommend with an outlook "
            "from -2 to +2 to rank structures for a view."),
        "runner": strategy_cmd.run,
        "defaults": {"name": None, "snapshot": None, "far_snapshot": None,
                     "kind": "call", "offset": 0.03, "size": 1.0,
                     "underlying_entry": None, "out_dir": None,
                     "list_only": False, "recommend": None,
                     "vol_view": "neutral", "owns_underlying": False,
                     "direction_unknown": False},
        "public": ("name", "snapshot", "far_snapshot", "kind", "size",
                   "list_only", "recommend", "vol_view", "owns_underlying",
                   "direction_unknown"),
    },
    {
        "name": "option_strategy_compare",
        "description": (
            "Build every structure from one chain and rank them by model "
            "expected profit per unit of capital at risk. Returns the "
            "table, the leader, and the caveat that a positive expectation "
            "largely measures the gap between one volatility and the "
            "market's smile. Not a recommendation."),
        "runner": compare_cmd.run,
        "defaults": {"snapshot": None, "size": 1.0,
                     "include_underlying": False, "rebuild": False,
                     "out_dir": None},
        "public": ("snapshot", "size", "include_underlying", "rebuild"),
    },
    {
        "name": "option_simulate",
        "description": (
            "Fit a Bayesian GARCH-t model to the underlying's realised "
            "returns by MCMC and simulate forward. Returns the posterior "
            "with convergence diagnostics, the predictive fan, value at "
            "risk and expected shortfall. Check converged before quoting "
            "any quantile."),
        "runner": simulate_cmd.run,
        "defaults": {"symbol": None, "horizon": 5, "paths": 20000,
                     "draws": 3000, "burn": 1000, "chains": 2,
                     "period": "2y", "provider": None,
                     "no_structures": False, "out_dir": None},
        "public": ("symbol", "horizon", "paths", "draws", "period"),
    },
    {
        "name": "option_backtest",
        "description": (
            "Run a structure across real price history with modelled "
            "premiums. Returns win rate, mean return on capital at risk, "
            "drawdown, a permutation test, a bootstrap interval and a buy "
            "and hold benchmark. Premiums are model values, never fills."),
        "runner": backtest_cmd.run,
        "defaults": {"symbol": None, "strategy": None, "holding_days": 30,
                     "entry_every": 5, "lookback": 60, "period": "5y",
                     "rate": 0.04, "dividend_yield": 0.0, "size": 1.0,
                     "provider": None, "out_dir": None},
        "public": ("symbol", "strategy", "holding_days", "entry_every",
                   "period"),
    },
    {
        "name": "option_forward_test",
        "description": (
            "Paper ledger of positions recorded before their outcome is "
            "known. Actions: open, mark, close, status. Marks are mid "
            "quotes, not fills, and a position with a leg missing from the "
            "later chain is reported unmarkable rather than marked at "
            "zero."),
        "runner": forward_cmd.run,
        "defaults": {"action": "status", "plan": None, "strategy": None,
                     "underlying": None, "position_id": None, "price": None,
                     "thesis": None, "out_dir": None},
        "public": ("action", "strategy", "underlying", "position_id",
                   "price", "thesis"),
    },
]


def tool_specs():
    """The tool definitions, without requiring LangChain to be installed."""
    return [{"name": spec["name"], "description": spec["description"],
             "parameters": list(spec["public"])} for spec in SPECS]


def _annotation_for(default):
    """The type to advertise for a parameter, taken from its own default.

    A default of None says nothing about the type, so the parameter is
    advertised as Any rather than given a guessed one. Guessing here would
    put a type in the tool schema that no one has checked against the
    command behind it.
    """
    return Any if default is None else type(default)


def _callable_for(spec):
    def run(**kwargs):
        args = _Args(spec["defaults"], kwargs)
        result = spec["runner"](args)
        # Not reachable through desk_tools: the schema published below
        # filters unknown keys before run is called. Kept for direct callers
        # of _callable_for and _Args, which have no schema in front of them.
        if args.rejected:
            result = dict(result)
            result["ignored_arguments"] = args.rejected
        return result

    # The wrapper takes **kwargs so it can forward anything, but LangChain
    # builds the tool's schema by introspecting the signature. Left bare,
    # **kwargs produces a schema with one opaque object parameter, no
    # parameter is named to the model, and every supplied argument is
    # dropped by validation before run is called. Publishing the declared
    # public parameters is what makes the advertised arguments arrive.
    run.__name__ = spec["name"]
    run.__signature__ = inspect.Signature([
        inspect.Parameter(key, inspect.Parameter.KEYWORD_ONLY,
                          default=spec["defaults"][key],
                          annotation=_annotation_for(spec["defaults"][key]))
        for key in spec["public"]
    ])
    run.__annotations__ = {
        key: _annotation_for(spec["defaults"][key]) for key in spec["public"]
    }
    return run


def desk_tools(include=None):
    """Build LangChain StructuredTools for the desk.

    include restricts the set by name, which matters when handing an agent
    a narrower surface than the whole desk: an assistant that should only
    read has no business holding the tool that opens a paper position.
    """
    from langchain_core.tools import StructuredTool

    tools = []
    for spec in SPECS:
        if include and spec["name"] not in include:
            continue
        tools.append(StructuredTool.from_function(
            func=_callable_for(spec),
            name=spec["name"],
            description=spec["description"],
        ))
    return tools
