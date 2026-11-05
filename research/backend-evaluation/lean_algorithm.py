"""Local backtest template using the QuantConnect LEAN Python API.

API reference: QuantConnect/Lean Algorithm.Python/BasicTemplateOptionsAlgorithm.py.
LEAN is Copyright QuantConnect Corporation, Apache-2.0. See notices/.
"""
from AlgorithmImports import *
from datetime import datetime
import json
from pathlib import Path


class OptionDeskEvaluation(QCAlgorithm):
    def initialize(self):
        if self.live_mode:
            raise ValueError("Option Desk evaluation permits backtesting only")
        plan = json.loads(Path(__file__).with_name("plan.json").read_text())
        self.plan_tag = "OptionDesk plan sha256: " + plan["plan_sha256"]
        self.set_runtime_statistic("OptionDesk Data Mode", plan["data_mode"])
        self.set_start_date(datetime.fromisoformat(plan["start"]))
        self.set_end_date(datetime.fromisoformat(plan["end"]))
        self.set_cash(100000)
        equity = self.add_equity(plan["underlying"], Resolution.MINUTE)
        equity.set_data_normalization_mode(DataNormalizationMode.RAW)
        self.set_benchmark(equity.symbol)
        self.targets = []
        for leg in plan["legs"]:
            symbol = Symbol.create_option(equity.symbol, Market.USA, OptionStyle.AMERICAN,
                                          OptionRight.CALL if leg["kind"] == "call" else OptionRight.PUT,
                                          leg["strike"], datetime.fromisoformat(plan["expiry"]))
            security = self.add_option_contract(symbol, Resolution.MINUTE)
            if security.symbol_properties.contract_multiplier != plan["multiplier"]:
                raise ValueError("contract multiplier differs from exported plan")
            self.targets.append((symbol, leg["quantity"]))
        self.entered = False
        self.exited = False
        self.exit_date = datetime.fromisoformat(plan["end"]).date()

    def on_data(self, data):
        if not all(data.quote_bars.contains_key(symbol) for symbol, _ in self.targets):
            return
        if not self.entered and self.time.date() < self.exit_date:
            self.entered = True
            for symbol, quantity in self.targets:
                self.market_order(symbol, quantity, tag=self.plan_tag)
        elif self.entered and not self.exited and self.time.date() == self.exit_date:
            self.exited = True
            self.liquidate(tag=self.plan_tag)

    def on_end_of_algorithm(self):
        if not self.entered or not self.exited or self.portfolio.invested:
            raise ValueError("incomplete evaluation: missing entry, exit or remaining holdings")
