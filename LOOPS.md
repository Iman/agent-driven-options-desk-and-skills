# Running this on a loop

Two different things are called loops here, and both are supported.

## Claude Code loops

Agents repeating cycles of work until a stop condition is met. Four kinds,
and this project has commands shaped for three of them.

### Turn based: you ask, it finishes

`/desk-open SPY` pulls a chain, grades it, reads positioning and ranks
every structure. It ends when the artifacts exist. Nothing recurring, no
stop condition beyond the work being done.

### Goal based: stop when a checkable condition holds

```
/goal run /desk-complete SPY until every criterion is met, stop after
5 tries.
```

`/desk-complete` exists for this. Its exit criteria are all mechanical: a
chain with at least ninety percent of contracts carrying an implied
volatility, a ladder with fifty or more graded rows, exposure with both
walls and a smile, a comparison with five or more rankable structures, a
converged simulation whose horizon reaches the expiry, and no artifact
degraded for a reason other than volatility fallback. An evaluator can
check every one of those without judgement, which is what makes it a good
goal.

That last criterion is worded the way it is because of a measurement.
An earlier version required nothing in the set to be degraded at all, and
four live SPY pulls showed that criterion failing every time: between 15
and 61 percent of contracts on a real chain price at the provider's
published volatility, because an intrinsic-dominated price identifies none.
That is routine rather than a fault, the flag is set at a 5 percent
threshold, and a goal that can never be reached is worse than no goal. The
lesson generalises: write the criterion, then run it against real data
before advertising it as achievable.

It also says when to stop trying. A sparse expiry does not improve on the
third attempt, and a provider that is down is not fixed by asking again.

The rewritten criteria were then run against a live pull rather than
assumed to work: SPY, expiry 31.1 days out, 547 of 575 contracts with a
solved volatility (95.1 percent), a 175 row ladder, both walls and a smile,
9 rankable structures, a converged simulation, and no degradation beyond
the volatility fallback. All six met. One criterion failed on the first
attempt, by an afternoon: a 31 day horizon against 31.1 days to expiry, so
the criterion now says to round up. That is the sort of thing only a real
run finds.

### Time based: run it again every so often

```
/schedule every weekday at 21:30: run /desk-watch SPY
/loop 6h run /desk-watch SPY
```

`/desk-watch` is written to stay quiet. It reports only a spot move over
one percent, a volatility move over a point, a gamma regime flip, a wall
moving strike, a risk reversal move over half a point, or a degradation
that was not there before. Otherwise it says "no material change" and
stops. A recurring command that restates everything each time trains you to
ignore it.

Match the interval to the data, not to your impatience. The free provider
serves the last settled close and stamps the session it belongs to, so
nothing this command watches can move more than once per trading day. A
thirty minute loop would re-pull the same close and report nothing, over
and over, which is how a loop becomes noise that happens to be silent.
Once a day after the close is the honest cadence, and the command says so
itself.

`/desk-mark` suits the same treatment on a slower cadence, since marking a
paper position only means something once new quotes exist.

### Proactive: scheduled, with a goal inside it

```
/schedule every weekday at 22:00: run /desk-complete SPY until every
criterion is met, stop after 3 tries.
```

The routine runs on its own, each run has a checkable finish, and the whole
thing stops when you stop it.

## What makes a good loop here, and what does not

Good, because the finish is mechanical: bringing an artifact set to
completeness, refreshing until a simulation converges, marking open
positions when a newer chain exists, watching for a named threshold to be
crossed.

Bad, because there is no defined finish: "find me a good trade", "keep
improving the strategy", "monitor the market". Those never terminate, and
an agent given one will either stop arbitrarily or keep going until
something breaks. If you want something like that, express it as a
threshold: "watch until the 25 delta risk reversal exceeds six points, then
stop and tell me".

## A loop must never place an order

Nothing in this project executes a trade, and no command it ships will
open, size or close a real position. `/desk-mark` touches only the paper
ledger. If you build a loop on top of this that reaches a broker, that is
yours, and the disclaimer applies with more force rather than less.

## Graph loops, for applications you build

Separately from the Claude Code primitives, the agent layer ships a
LangGraph state graph with a bounded loop:

```python
from optiondesk_agent import open_desk

state = open_desk("SPY", budget=8)
print(state["outcome"])   # complete, exhausted, or failed
print(state["summary"])
```

The gather node runs one missing step per visit and returns to the
decision, looping until the set is complete, the step budget is spent, or a
step fails. Three distinct outcomes, because "it finished", "it ran out of
turns" and "it broke" are three different things and collapsing them is how
an agent reports success on an empty directory.

There is no model in the graph. Every node runs a deterministic command, so
the same inputs give the same outputs and a failure is reproducible. Pass a
model only if you want the final summary written rather than assembled.

Install it with the optional extra:

```
pip install -e "agent[graph]"
```
