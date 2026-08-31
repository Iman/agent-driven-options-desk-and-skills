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

### Proactive: scheduled, and why it does not fit this desk

`/schedule` creates a scheduled cloud agent. That is the important word.
The routine runs on Anthropic's infrastructure, not on your machine, so it
cannot see `optiondesk` in `~/.local/bin`, the virtualenv under
`~/.optiondesk`, or a single artifact in `~/TradingDesk/option-desk`. A
scheduled `/desk-watch` would wake up somewhere with none of the desk and
nothing to compare against.

Earlier versions of this file recommended exactly that, in four places. It
was wrong, and it is the kind of wrong that costs someone an evening before
they work out why nothing runs.

Use the operating system instead, where the work actually lives:

```
# crontab -e, weekdays at 21:30, after the close
30 21 * * 1-5 cd ~/TradingDesk && /Users/you/.local/bin/optiondesk chain SPY
```

Or `launchd` on macOS, which survives reboots and is what
`tradermonty/claude-trading-skills` uses for the same job. Scheduling the
data pull locally and reading it in a session afterwards gets you the
outcome without pretending a cloud routine can reach your disk.

`/schedule` remains the right tool for work that is genuinely remote:
watching a repository, a queue, or anything reachable from the internet
rather than from your home directory.

### The other host schedules differently, and better, for this

OpenAI's scheduled tasks run against a local project rather than in a
detached cloud. They support recurring cadences and RFC 5545 rules, and
they can use skills and plugins, so a daily `desk-watch` there reaches the
same `optiondesk` binary and the same artifacts you would use by hand. The
machine has to be on and the app running, which is the honest catch.

They are created from ChatGPT on the web or the desktop app. The Codex CLI
cannot create or manage them, and neither can the IDE extension, so this is
one of the few places where the desktop app does something the terminal
cannot.

There is no OpenAI equivalent of a goal-based loop that runs until a
condition holds. The nearest was Agent Builder's While node, and Agent
Builder shuts down on 30 November 2026, so it is not worth building on.
Codex answers the same need with subagents, which delegate rather than
iterate. That is why the bounded graph in this project's own `agent[graph]`
package stays: it is the portable version of a goal loop, and there is
nothing on the OpenAI side to swap it for.

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


## The loop this project was missing

Every loop above repeats work. None of them checks the work, and in
September 2026 that gap cost eleven defects.

The desk had 900 passing tests, ten green refresh stages and a mutation
harness with no survivors. Three agents then recomputed the same numbers
from scratch, against independently written implementations, and found
eleven things wrong: a solver refusing contracts it could identify, a rate
of exactly zero silently replaced, a payoff curve drawn at different rates
from the analysis beside it in the same file, an antithetic construction
that had never run while every artifact claimed it had, significance tests
assuming independence that overlapping windows do not have, and five more.
Not one was caught by a test, because a test checks what its author thought
to check, and all eleven lived where nobody had thought to look.

So there is a fourth kind of loop worth running here, and it is not on a
timer. Run it when the numbers start being quoted, when a figure gets
published, or when you have been staring at the same code long enough to
stop seeing it:

```
Recompute, independently, and report only what disagrees.
```

Three properties make it work, and all three are easy to lose:

**It must not call the code it is checking.** An independent
implementation, written from the definition rather than from the source.
Two of the eleven were found only because the checker used a different
normal CDF.

**It must be adversarial about claims, not just arithmetic.** Most of the
arithmetic was right, to between 1e-11 and 1e-16. What was wrong was what
the numbers were said to mean: a flag asserting a property that was not
there, a maximum that was a property of its window, a p-value from a null
the structure cannot produce.

**It must be allowed to report that a test is the problem.** Five tests in
this repository passed against deliberately broken code. A verification
that assumes the suite is the reference cannot find those.

This is not a substitute for the tests. It is the thing that tells you
which tests you never wrote.
