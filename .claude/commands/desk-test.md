---
description: Backtest a structure with modelled premiums and judge honestly whether the result means anything
argument-hint: SYMBOL STRUCTURE [PERIOD]
arguments: [symbol, structure, period]
---

Test $structure on $symbol over $period, defaulting to five years.

1. `optiondesk backtest $symbol $structure --period 5y`. When a period was
   given, use `--period $period` in place of 5y. An omitted argument
   expands to nothing, and a bare `--period` is rejected before any
   history is fetched.
2. Read the output in this order, which is the order that stops a backtest
   selling itself: trade count, then the buy and hold benchmark, then the
   p-value, then the bootstrap interval, and only then the headline return.
3. Under thirty trades, decline to draw a conclusion and say why.
4. Quote the honesty statement from the artifact whenever you quote a
   number from it: real closes, modelled premiums, no spread, no slippage,
   no assignment, and entry and exit priced by the same model.
5. If the user wants to take it further, register it forward rather than
   tuning it: `optiondesk forward open --strategy $structure --thesis "..."`.
