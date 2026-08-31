---
description: Simulate an underlying forward and compare realised volatility against implied for every structure on file
argument-hint: SYMBOL [HORIZON_DAYS]
arguments: [symbol, horizon]
---

Project $symbol forward over $horizon business days, or fourteen when no horizon is
given.

1. `optiondesk simulate $symbol --horizon $horizon --draws 4000`
2. Read `converged` first. If it is false, say so, do not quote a single
   quantile, and offer a higher `--draws` instead of proceeding.
3. Report the fan as a range with its horizon attached, the value at risk
   and expected shortfall with their level and horizon, and the tail
   weight from the degrees of freedom.
4. If structures are on file, give the realised against implied table and
   describe the gap as a disagreement between the market's forecast and
   the recent past. Neither side is the truth, and the gap is not an edge.
5. If a structure is on file and the next step would be acting on it, hand
   it to the `options-risk-reviewer` agent. A projection says what the
   underlying might do. It does not say what would have to be true for the
   structure to lose, and that is a different question asked by someone who
   has not seen the reasoning that produced the structure.
