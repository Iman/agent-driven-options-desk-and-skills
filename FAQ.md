# Questions people actually ask

## Using it

**Do I need an API key?**

No. Chains, Greeks, positioning, structures, simulation and backtests all
run on free sources with no signup. A key adds an alternative provider, and
a provider whose key is missing is skipped rather than failing.

**How do I tell it which option to look at?**

`optiondesk expiries SPY` lists what the provider carries and marks what
you already have. Then `optiondesk chain SPY --expiry 2026-09-18`. The
dashboard groups everything by underlying and expiry and gives you a picker
for both, so several symbols and dates coexist without mixing.

**Why does the spot price look stale?**

It is the last settled close, and the artifact says which session it came
from in `spot_asof`. On a weekend or before the open, that is correct
behaviour and not a bug. The provider serves partial bars with no close,
and taking the newest row rather than the newest real close is how a NaN
gets into a pipeline that then reports it as a number.

**Why did it skip contracts?**

Because their price carries no information about volatility. Anything
dominated by intrinsic value reprices within tolerance at every volatility
in the range, so the price identifies none of them. Those contracts get
`iv: null` and are counted in `counts.without_iv` on the chain snapshot,
and in `skipped.no_iv` on any Greek ladder built from it. Filling in a default would
produce a complete and entirely fictional Greek ladder that looks exactly
as authoritative as a real one.

**What does `degraded` mean, and how is it different from `notes`?**

`degraded` means the output is lower quality than the pipeline can
normally produce: a provider fell back, a rate could not be fetched, the
engine was absent, the expiry has passed. `notes` records ordinary
observations, such as wing contracts having no quotes. If both went in one
field, almost every artifact would be flagged and the flag would stop
meaning anything.

**Why is maximum loss sometimes the word "unlimited"?**

Because it is. JSON has no infinity. Writing null would erase the
difference between an unbounded risk and an unknown one, and writing a
large number would invent a floor that does not exist.

**Does this work on anything other than stocks?**

Yes, on seven classes through one provider: index options via `^SPX`,
equity and ETF directly, rates via `TLT`, metals via `GLD`, energy via
`USO`, crypto via `BITO`, FX via `FXE`. All measured pulling real chains.
Futures and FX spot carry no option chains from the free provider, so the
exchange-traded proxies are the route rather than a shortcut.

**Why did my TLT Greeks change?**

Because the dividend yield is now fetched instead of assumed to be zero,
and TLT pays about 4.7 percent. On a 173-day chain that moved at-the-money
implied volatility from 0.0737 to 0.1133 and delta from 0.635 to 0.491.
The old numbers were the wrong ones. Pass `--dividend-yield` to override.

**Why does BITO refuse to give a dividend yield?**

Because its two sources disagree by 23 percentage points: 38.8 percent
computed from distributions actually paid against 61.7 percent published.
Funds distributing option income do that. Picking a side would be a guess
presented as a measurement, so the artifact is degraded and says why.

## Trusting the numbers

**Are these real prices?**

No. Premiums are Black-Scholes values, or mid quotes from delayed
third-party data. They are not fills and a real entry crosses the spread on
every leg. The friction estimate is the only part of the system that
touches the cost of trading, and it is an estimate.

**Can I trade from this?**

It is research software and it is not investment advice. The author holds
no regulated status. Nothing here is a recommendation, a solicitation or a
personal suggestion, and the structure ranking is an ordering under stated
assumptions rather than a view about what you should do. Read
DISCLAIMER.md.

**The backtest says a structure made 47 percent per trade. Is that real?**

The numbers in this answer come from one run, a bull call spread on SPY
over five years to 2026-08-28, and the artifact behind them is regenerated
by the next backtest. Read them as an illustration of how to read a
backtest, not as a result to quote.

Read the benchmark first. Over the same five years, simply holding SPY over
the same windows returned about 1.6 percent per window, and a leveraged
directional structure amplifies exactly that drift. Then read the honesty
statement: real closes, modelled premiums, no spread, no slippage, no
assignment, and entry and exit priced by the same model, which means the
test cannot detect any edge arising from the market disagreeing with that
model. Then read the p-value, the block beside it, and the caveat. The block
matters: these windows overlap, since a thirty day hold entered every five
trading days shares twenty-five of its thirty days with its neighbour, so
the effective sample is 64 to 88 rather than 233 and the test flips signs a
block at a time. Treating them as independent understated the standard
error by about a factor of two, and correcting it moved four structures on
this desk from below 0.05 to above it. The caveat still stands on top of
all that: a rule chosen because its backtest looked good has already spent
its degrees of freedom.

**Why does the simulation artifact say `antithetic: false`?**

Because it is, and older artifacts that said true were wrong. The mirroring
was measured in September 2026 and found to be inert: of ten thousand
pairs, none shared a shock sequence, because the shocks were drawn inside
the sign loop. The estimates were never biased by it, so no published
number changed, but the field was a false statement about how they were
produced. The construction is gone and each path now draws its own
parameters, which matters more for the tail than mirroring would have.

**The simulation has been sitting there for a minute. Has it hung?**

Almost certainly not. The sampler is a Metropolis-Hastings walk in pure
Python, single threaded, with no progress output between start and finish.
It runs `(draws + burn) x chains` iterations and each one walks every
observation in the history. On an eighteen core arm64 machine with 1253
daily observations the defaults take about eight seconds and the heaviest
sensible settings about twenty-seven; a slower machine takes proportionally
longer, and a long history at a high draw count runs for minutes.

The command prints a line to stderr before it starts, naming the iteration
count and a rough duration. Wait for it. Killing the run writes nothing at
all, and lowering `--draws` to make it finish faster is the surest way to
get `converged: false`, which means the numbers cannot be quoted.

**The simulation says `converged: false`. Can I use the numbers?**

No. It means the chains did not agree, by split R-hat above 1.05 or an
effective sample size below 100 on some parameter. Raise `--draws` to 4000
and run it again. The quantiles are still written to the artifact, because
deleting them would hide what happened, but they should not be quoted.

**Why do the two probabilities disagree?**

One comes from the volatility the options are priced at, the other from the
volatility the underlying has actually shown. They are answers to different
questions and the gap between them is the interesting part. Neither side is
the truth, and the gap is not an edge.

**The gamma walls look precise. How much should I trust them?**

The arithmetic is exact; the sign convention is an assumption. It assumes
dealers are long calls and short puts against the public, which is the
market convention and is frequently wrong for a single name, especially
around events and in heavily retail-traded tickers. Every wall moves with
that assumption, and the artifact carries it in a field.

## Structure and licensing

**Why are there three packages under one licence?**

The split is about dependencies and testability, not licensing. The engine
has no dependencies outside the standard library and no network access,
which is what lets it be checked against closed-form and finite-difference
benchmarks. The shell holds everything that touches the outside world. The
agent layer is optional and never in the compute path. One adapter module
joins the shell to the engine, so the seam can be checked with one grep,
and the shell runs without the engine by reporting Greeks as unavailable
rather than guessing them.

**Can I use this commercially?**

Not without a written agreement. The licence is
[PolyForm Noncommercial 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0):
free for any noncommercial purpose, including personal study, research,
hobby projects, and use by charities, schools, public research bodies and
government however they are funded.

Commercial use means anything for commercial advantage or private monetary
compensation. Using it inside a fund, selling it or access to it, paid
consulting or signals produced with it, and raising money on the back of it
all need an agreement first. Ask the copyright holder; terms are negotiable
and a revenue share is one of the shapes they can take.

**It used to be MIT and AGPL. What happened?**

Those terms permitted the thing they were meant to prevent. AGPL allows
commercial use and selling; it only requires that a modified version run as
a network service publishes its source. Someone taking the engine, wrapping
it and raising money on it was complying. Relicensed on 2026-08-31, one day
after publication.

Copies taken under the old terms keep them for those versions. A licence
already granted cannot be withdrawn, and pretending otherwise would be
worse than the original mistake.

**What is the difference between the skills, the commands, the agents and
the MCP tools?**

Skills are domain knowledge, loaded when relevant, describing conventions
and the rules for reporting. Commands are one-shot procedures you invoke
deliberately, like `/desk-open SPY`. Agents are delegated workers with a
narrower brief, such as the adversarial risk reviewer. MCP tools are the
typed capability surface any runtime can call. They are four ways to reach
the same commands, and each suits a different moment.

**Does this work in ChatGPT or Codex, or only Claude?**

Both. Codex scans `.agents/skills` in a repository and `~/.agents/skills`
for your user, and this repository symlinks the first to `shell/skills`, so
a clone is enough and `npx skills add` covers the second. There is a plugin
for Codex too, registered with `codex plugin marketplace add`, carrying the
same six skills as the Claude bundle.

What differs is the tools, not the skills. Codex on your machine can run
the local MCP server; ChatGPT in a browser cannot execute a binary on your
computer, so there the skills are knowledge and instructions. Each skill
states that itself rather than leaving you to find out: prefer the MCP
tool, fall back to the command line, and if neither exists say that no
fresh figures can be produced instead of inventing them.

The six commands and two agents are Claude-only. A Codex install is five
skills plus the MCP declaration, and the documentation says so rather than
implying parity.

**Why LangChain as well as MCP?**

MCP serves a runtime that already exists, such as Claude Code, Codex or
Gemini CLI. The LangChain bindings serve an application you build yourself,
where this is one capability among several and the orchestration is yours.
Both call the same commands and read the same artifacts. Neither is in the
compute path: every number comes from the engine, which depends on neither.

## Repeating it

**What is the difference between a loop and the graph?**

A loop is a Claude Code primitive: the same command run again until a stop
condition holds, whether that condition is a checkable goal, a clock, or a
schedule. The graph is a LangGraph state machine inside the optional agent
package, for an application you are building yourself. Both are bounded and
neither places an order. `LOOPS.md` covers both.

**Can I run it on a schedule?**

Inside a session, `/loop 6h run /desk-watch SPY`.

Without a session, use `cron` or `launchd`. Claude Code's `/schedule`
creates a scheduled cloud agent, which runs on Anthropic's infrastructure
and cannot see `optiondesk` on your machine or a single artifact in your
home directory. This documentation recommended `/schedule` in four places
and was wrong in all four.

Either way use `/desk-watch` rather than `/desk-open` for anything
recurring: it reports only material change and says "no material change"
otherwise, which is what keeps a recurring command worth reading.

**What makes a good loop, and what does not?**

Good, because the finish is mechanical: bringing an artifact set to
completeness, refreshing until a simulation converges, marking positions
when a newer chain exists, watching for a named threshold. Bad, because
there is no defined finish: find me a good trade, keep improving the
strategy, monitor the market. Express those as thresholds instead.

## Maintaining it

**How do I regenerate the documentation?**

`python3 scripts/refresh.py`. It rebuilds the runtime docs, the inventory
and every installable form, refreshes the code index, runs the three test
suites and scans for house-rule violations. `docs/INVENTORY.md`,
`AGENTS.md` and `GEMINI.md` are generated, so editing them by hand is
wasted work.

**Do I need CodeGraph?**

No. It is an optional code index,
`npm i -g @colbymchenry/codegraph`, that lets an agent ask where a symbol
is defined, what calls it, and which tests a change affects, without
grepping. The refresh skips the stage with a note when the binary is
absent, and the index is machine-local and git-ignored.

**What does the rules stage check?**

Every tracked text file, for ANSI escape codes, emoji, em dashes and
anything shaped like a provider key. It fails the refresh on a hit. The key
check was verified by planting a key-shaped string and confirming the
refresh went red, because a guard that has never fired is not known to
work.

## Running it

**If I pull the same chain twice, do I lose the first one?**

No. The outgoing artifact moves to `archive/<date>/` under a name carrying
the time it was generated, and the live filename stays exactly as it was so
nothing that reads artifacts has to change. Identical bytes are not
archived. `OPTIONDESK_ARCHIVE=0` turns it off. Nothing prunes the archive
for you.

**How do I know a number in the documentation is real?**

`docs/evidence.json` names the artifact each documented figure came from,
when it was generated and which provider answered, and a test fails if the
prose stops matching it. It holds derived figures only, never provider
data. Record with `scripts/evidence.py record`, check with
`scripts/evidence.py check`, and note that the refresh only ever checks:
re-recording on every refresh would make the documented number quietly
follow whatever was pulled last.

**Where do artifacts go?**

`~/TradingDesk/option-desk` by default. Override with
`OPTIONDESK_ARTIFACTS` or `--out-dir`. Everything is a schema-validated
JSON file, and the dashboard only ever reads them.

**The dashboard is empty.**

It renders artifacts, and writes none. Run `optiondesk chain SPY`, then
`greeks`, then `exposure`, then `compare`, and refresh. The empty page
tells you the same thing with the commands on it.

**Can I run it on a different port?**

`optiondesk dashboard --port 8799`. It binds to 127.0.0.1 only.

**Does anything phone home?**

The shell fetches market data from whichever provider answers, and that is
all. The engine has no network access of any kind. The dashboard serves
locally with a vendored copy of its charting library, so a viewer's browser
makes no third-party request. Nothing is sent anywhere about you or your
usage.

**How much of this is tested?**

Over five hundred tests across the three packages, and the exact counts
are checked by a test instead of being remembered here. The Greeks are checked against
central finite differences of the price function they claim to
differentiate, with mutation testing, which is in the tree as
`scripts/mutate.py` and which you can run, confirming that a sign flip or a
dropped term in any of the sixteen fails the suite. The MCMC is validated
by recovering parameters it was given, with coverage measured across
several datasets rather than one. Statistical properties are tested as
frequencies, because a 90 percent interval is supposed to miss one time in
ten.

**Something is wrong. How do I tell what?**

`optiondesk doctor` for the environment. Every artifact carries its own
provenance: which tool wrote it, when, which provider answered, whether it
was degraded and why. For a Greek ladder,
`python3 ~/.claude/skills/options-greeks/scripts/check_artifact.py <path>`
prints a one-line verdict.
