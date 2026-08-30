"""JSON contracts for every artifact this project writes.

The schema is the interface. Skills, the MCP server, the dashboard and any
third-party consumer read artifacts, never internal Python objects, so the
schema is what has to stay stable, not the code that produces it.
"""

from optiondesk.contracts.validate import (
    ValidationError,
    load_schema,
    validate,
)

CHAIN_SNAPSHOT = "optiondesk/chain_snapshot/v1"
GREEKS_LADDER = "optiondesk/greeks_ladder/v1"
STRATEGY_PLAN = "optiondesk/strategy_plan/v1"
EXPOSURE = "optiondesk/exposure/v1"
STRATEGY_COMPARISON = "optiondesk/strategy_comparison/v1"
SIMULATION = "optiondesk/simulation/v1"
BACKTEST = "optiondesk/backtest/v1"
FORWARD_LEDGER = "optiondesk/forward_ledger/v1"

SCHEMA_FILES = {
    CHAIN_SNAPSHOT: "chain_snapshot.schema.json",
    GREEKS_LADDER: "greeks_ladder.schema.json",
    STRATEGY_PLAN: "strategy_plan.schema.json",
    EXPOSURE: "exposure.schema.json",
    STRATEGY_COMPARISON: "strategy_comparison.schema.json",
    SIMULATION: "simulation.schema.json",
    BACKTEST: "backtest.schema.json",
    FORWARD_LEDGER: "forward_ledger.schema.json",
}

__all__ = ["validate", "load_schema", "ValidationError",
           "CHAIN_SNAPSHOT", "GREEKS_LADDER", "STRATEGY_PLAN", "EXPOSURE", "STRATEGY_COMPARISON", "SIMULATION", "BACKTEST", "FORWARD_LEDGER", "SCHEMA_FILES"]
