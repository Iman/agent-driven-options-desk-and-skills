# Everything this project can do

The complete catalogue: every surface, every command, every tool, every
structure, and the things it deliberately refuses to do. If something is
not listed here it does not exist, and if something here does not work that
is a bug worth reporting.

Two companion documents are generated rather than written, so they cannot
go stale: `docs/INVENTORY.md` is the public API read straight out of the
source, and `AGENTS.md` and `GEMINI.md` are the runtime instructions built
from the skills. All three are rebuilt by `python3 scripts/refresh.py`.

---

## 1. The shape of it

Three packages, two licences, one adapter between them.

| package | licence | what it is | depends on |
|---|---|---|---|
| `engine` | AGPL-3.0-only | every number the desk reports | the standard library, nothing else |
| `shell` | MIT | data, contracts, CLI, dashboard, MCP server | the engine, optionally |
| `agent` | MIT | LangChain tools, LangGraph routine | the shell, and langchain-core |

The engine has no network access of any kind and no third-party
dependency. The shell reaches the internet, validates what comes back
against a schema, and writes an artifact. The agent layer is optional and
never sits in the compute path: it calls the same commands and reads the
same artifacts as a human would.

They are joined by exactly one module, `shell/src/optiondesk/engine_bridge.py`.
That is the whole licence boundary and it can be checked with one grep. If
the engine is not installed, the shell still runs and reports Greeks as
unavailable rather than inventing them.

Everything anything produces is a JSON artifact on disk, validated against
a schema, carrying its own provenance: which tool wrote it, when, which
provider answered, whether the result was degraded and why. The dashboard
only reads those files. So does the agent layer. So does a person.

---

## 2. Six ways to reach it

The same capability is exposed six times because six different moments
call for different things. None of them is a wrapper around another: they
all call the same commands.

| surface | for | invoked by |
|---|---|---|
| CLI | a person at a terminal, and every other surface underneath | `optiondesk <command>` |
| Skills | an agent that needs to know the conventions before it acts | loaded automatically when relevant |
| Commands | a deliberate one-shot procedure | `/desk-open SPY` |
| Agents | delegated work with a narrower brief and its own context | the agent runtime, or by name |
| MCP tools | any runtime that speaks the protocol | `optiondesk-mcp` over stdio |
| LangChain tools | an application you are building yourself | `desk_tools()` |

---

## 3. The command line

Twelve commands. Each does one thing, writes one schema-validated artifact,
and prints a JSON summary to standard output.

| command | what it does |
|---|---|
| `optiondesk expiries SPY` | what the provider lists, what is already on disk, days to each |
| `optiondesk chain SPY` | pull one chain, solve implied volatility per contract, write a snapshot |
| `optiondesk greeks` | the sixteen Greek ladder from a snapshot, graded |
| `optiondesk strategy` | build one named structure, or recommend one from a stated view |
| `optiondesk compare` | build every buildable structure from one chain and rank them |
| `optiondesk exposure` | dealer gamma, walls, flip levels, max pain, put-call ratios, smile |
| `optiondesk simulate` | GARCH(1,1)-t posterior by MCMC, forward paths, tail risk |
| `optiondesk backtest` | one structure entered repeatedly across real history |
| `optiondesk forward` | paper ledger: open, mark, close, status |
| `optiondesk keys` | see, set or locate provider credentials, never printing one in full |
| `optiondesk doctor` | engine presence, provider availability, credential status, paths |
| `optiondesk dashboard` | serve the local dashboard, bound to 127.0.0.1 |

Common flags: `--out-dir` puts artifacts somewhere other than
`~/TradingDesk/option-desk`, `--provider` forces one data source and fails
rather than silently falling back, `--snapshot` picks a specific artifact
instead of the newest.

---

## 4. The engine: what it computes

### 4.1 Pricing and implied volatility

Black-Scholes-Merton with a continuous dividend yield, plus Black-76 for
options on futures and Garman-Kohlhagen for currency options. The latter
two are substitutions into the same core, so they inherit its guards and
numerics, and they are tested against the published formulae written out
independently rather than against the module itself. Nothing feeds them:
no provider here carries futures or FX option chains, and the module says
so in its first paragraph. Implied volatility
is solved by Newton-Raphson with a bisection fallback.

The part that matters is what it refuses. A contract whose price is
dominated by intrinsic value reprices within tolerance at every volatility
in the range, so its price identifies none of them. Those contracts get
`iv: null` and are counted in `counts.without_iv` on the chain snapshot, and in
`skipped.no_iv` on the Greek ladder built from it, rather than being
filled with a default. A complete Greek ladder built on default volatilities looks
exactly as authoritative as a real one, which is why the refusal is the
feature.

### 4.2 The sixteen Greeks

| order | Greeks |
|---|---|
| first | delta, vega, theta, rho, lambda |
| second | gamma, vanna, vomma, charm, veta |
| third | speed, zomma, color, ultima |
| strike | dual delta, dual gamma |

Every one is tested against a central finite difference of the price
function it claims to differentiate, and mutation testing confirms that a
sign flip or a dropped term in any of the sixteen fails the suite. Two sign
errors, in veta and color, were found exactly this way.

Net position Greeks are reported with a `complete` flag and a `missing`
list, because a position Greek summed over legs where one leg had no
volatility is not a smaller number, it is a wrong one.

### 4.3 Seventeen structures

| structure | when it is the right shape |
|---|---|
| long call | very bullish, stock replacement, risk capped at premium |
| long put | bearish, risk capped at premium |
| bull call spread | mildly bullish, full profit on a normal move |
| bear put spread | mildly bearish, higher probability than a long put |
| cash secured put | neutral to mildly bullish, or paid to wait to own |
| covered call | own it, expect sideways to mildly up |
| protective put | keep the upside, cap the downside, pay for it |
| straddle | a big move, direction unknown |
| strangle | cheaper than a straddle, needs a bigger move |
| iron condor | range bound with volatility expected to fall |
| iron butterfly | pinned rather than merely range bound |
| long call butterfly | a cheap bet on pinning near a strike |
| calendar spread | sell near, buy far, same strike, collect the decay difference |
| diagonal spread | a calendar with a directional lean |
| ratio spread | financed by selling more than you buy, and uncapped on the short side |
| broken wing butterfly | a butterfly with unequal wings, no risk on one side, often a credit |
| jade lizard | short put plus short call spread, no upside risk when the credit exceeds the call width |

Each plan carries legs, breakevens, maximum gain and loss, reward to risk,
model probability of profit, net Greeks, and a friction estimate of what
the round trip costs at quoted spreads.

Two of these are different in kind. A calendar and a diagonal have legs on
different expiries, so when the near leg dies the far leg is still alive
and still worth something. The payoff is a curve rather than line segments
and can only be drawn by pricing the surviving leg, which is done at the
volatility it carries today. That assumption is the largest source of error
in a time spread and it travels with every plan in an `assumption` field.

Maximum loss is sometimes the string "unlimited" rather than a number,
because JSON has no infinity, null would erase the difference between
unbounded and unknown, and a large number would invent a floor that does
not exist.

### 4.4 Positioning and volatility geometry

Dealer gamma exposure by strike, the call and put walls, every gamma flip
crossing rather than only the first, max pain, put-call ratios by volume
and by open interest, and the smile: at-the-money implied volatility, the
25-delta risk reversal, the butterfly, the skew slope and the implied
expected move.

The arithmetic is exact. The sign convention is an assumption, namely that
dealers are long calls and short puts against the public. That is the
market convention and it is frequently wrong for a single name, especially
around events and in heavily retail-traded tickers. Every wall moves with
that assumption and the artifact carries it in a field.

Max pain refuses to compute on a chain with zero open interest rather than
returning the lowest strike.

### 4.5 Comparison and ranking

Every buildable structure from one chain, scored on model expected profit
per unit of capital at risk, with a statistically picked leader and the
caveat that goes with it. Structures whose expectation is not finite are
unrankable rather than sorted to an end, because a NaN in a sort key makes
the winner depend on the order the list happened to be in.

The ranking is an ordering under stated assumptions. It is not a
recommendation, and the caveat saying so is part of the artifact rather
than a footnote in the interface.

### 4.6 Simulation

A Bayesian GARCH(1,1) with Student-t innovations, fitted by adaptive
random-walk Metropolis, then simulated forward.

What it reports about itself matters as much as what it reports about the
market. Split R-hat and effective sample size are computed per parameter,
and a chain that never moved reports R-hat as infinite and an effective
sample size of one rather than the perfect 1.0 and large number that a
naive calculation gives a stuck chain. Post-burn acceptance rate must be
above zero. `converged: false` means the quantiles are still written, so
nothing is hidden, but they should not be quoted.

From the posterior: the predictive fan, the terminal distribution, value at
risk at 95 and 99 percent, expected shortfall, and the profit
distribution of any structures already built. Parameters are drawn per
path rather than fixed at the posterior mean, so parameter uncertainty
reaches the tails instead of being averaged away.

### 4.7 Backtest and forward test

A backtest asks what a rule would have done. A forward test asks what a
position actually did from the moment it was written down. They are
different questions and the second one cannot be gamed by hindsight.

The backtest uses real underlying closes and modelled premiums, with no
spread, no slippage and no assignment, and prices entry and exit with the
same model, which means it cannot detect any edge that comes from the
market disagreeing with that model. That honesty statement is a field in
the artifact, not a caveat in a readme. It reports win rate, mean return on
capital at risk, drawdown in risk units, a permutation test, a bootstrap
interval, and a buy-and-hold benchmark over the same windows, because a
directional structure amplifies drift and a number without its benchmark is
a number that flatters itself.

Returns are summed in risk units rather than compounded, because
compounding a fixed-risk sequence produces minus one hundred percent the
first time a trade loses its full risk.

The forward ledger has four verbs: open, mark, close, status. A position
that cannot be marked, because no chain covers it, is refused rather than
marked at its entry price.

---

## 5. Data

| provider | needs a key | covers |
|---|---|---|
| Yahoo | no | option chains, underlying history, quotes, a risk-free proxy, dividend yield |
| Alpha Vantage | yes | underlying history and quotes, as a fallback |

Seven asset classes reach the desk through this one provider: index
options through `^SPX`, equity and ETF, rates through `TLT`, metals
through `GLD`, energy through `USO`, crypto through `BITO` and FX through
`FXE`. All were measured pulling real chains on 2026-08-30. Futures and FX
spot are the exception and carry no chains at all here, which is why the
exchange-traded proxies are the route rather than a preference.

The dividend yield is computed from payments actually made over the
trailing year rather than read from the provider's published field, whose
units have changed between library versions and would be a hundredfold
error waiting for an upgrade. The published figure is kept as a
cross-check, and when the two disagree by more than a quarter neither is
used. Assuming zero was measurably wrong: on a 173-day TLT chain it
understated at-the-money implied volatility by 54 percent and overstated
delta by 23 percent.

Providers are registered per capability with a priority order. A provider
whose key is absent is skipped rather than failing. A provider named
explicitly with `--provider` is honoured strictly: if it cannot answer, the
command fails rather than quietly using a different one, because a silent
substitution is how the wrong data ends up in a report that names the right
source.

Keys live in `~/.optiondesk/config.env`, outside any repository, readable
only by you. Resolution order is the command line, then the environment,
then `.env` in the working directory, then that file. They are never
printed in full, never logged, and never written into an artifact.
`optiondesk keys list` shows what is needed and what is set, masked.

Everything works with no key at all.

---

## 6. Contracts

Eight JSON schemas, one per artifact type: chain snapshot, Greek ladder,
strategy plan, strategy comparison, exposure, simulation, backtest, forward
ledger.

Every artifact carries the same envelope: schema name, tool, timestamp,
provider used, `degraded` and its reason, and free-text notes. `degraded`
means the output is worse than the pipeline can normally produce, such as a
provider falling back or an expiry having passed. `notes` records ordinary
observations. If both went in one field almost every artifact would be
flagged and the flag would stop meaning anything.

Schemas are self-contained: cross-file references are rejected at load
time, so an artifact can be validated by anyone holding one file.

An artifact that is replaced moves into `archive/<date>/` first, named for
the time it was generated. The live filename never changes, so nothing that
resolves the newest artifact by name has to know the archive exists.
Identical bytes are not archived, `OPTIONDESK_ARCHIVE=0` turns it off, and
nothing prunes: deleting your own measurements is not a decision this
project makes for you.

`docs/evidence.json` pins every figure quoted in the documentation to the
artifact it was read from, with the generation time, the provider and the
degraded flag. Derived numbers only, a few kilobytes, no provider data, and
recorded by hand rather than by the refresh. The refresh checks it. This
exists because a documented measurement went stale within six hours of
being written and nothing noticed: the chain behind "595 solved, 12
refused" reported 590 and 17 on the next pull.

The `degraded` flag and its reason appear in the printed summary as well as
in the artifact, on every path of every command that has an upstream that
can fail, including the two paths that report a structure could not be
built at all. Commands with no upstream carry the key set to false rather
than omitting it, so a consumer can read it unconditionally. That
is a recent correction: five commands wrote degradation into the envelope
and printed a summary with no trace of it, so an MCP client holding the tool
result, or anyone reading standard output, could not tell that the numbers
came from a fallback provider or a stale chain. The reporting rule every
skill states, say it is degraded before quoting any number from it, was
unenforceable for those commands because the flag never reached the reader.
A static test now fails the suite if a command that can degrade omits the
flag, and it was verified by removing one and watching it go red.

---

## 7. The dashboard

`optiondesk dashboard --port 8799`, bound to 127.0.0.1, serving Apache
ECharts from a vendored copy so a viewer's browser makes no third-party
request.

Thirty-nine panels and, at most, thirty-two chart canvases: twenty with
fixed identities, six Greek profiles and up to six per-structure outcome
distributions. Each renders only when the artifact behind it exists, rather
than being drawn empty:

- payoff at expiry, with breakevens and the expected-move band
- dealer gamma by strike, cumulative exposure and the flip
- open interest, volume by strike, the max pain profile
- the smile, the term structure of volatility and expected move, skew across expiries
- six Greek profiles: delta, gamma, vega, theta, vanna, charm
- every structure on one axis, probability against expected return, where each structure lands
- posterior predictive fan, terminal distribution, up to six per-structure outcome distributions
- realised volatility against implied
- backtest equity, drawdown from peak, per-trade outcome distribution
- the volatility surface, strike against expiry, assembled from every chain on disk for that underlying
- the variance risk premium, implied against realised, on an axis of days to expiry rather than calendar time, because the history block carries one realised figure and not a series
- the condors that exist as artifacts, short width against expected return, which is not the same as every condor the chain admits
- gamma scalping levels from the simulation fan, with the reference levels driven by whichever structure is selected

Conventions hold across every panel so a reader learns them once: spot is a
dotted grey line, breakevens are dashed amber, the expected move is a
shaded band, profit is green and loss is red measured from zero, and
reference labels alternate top and bottom so they never collide. Light and
dark follow the viewer's system setting.

Pickers for underlying and expiry, so several symbols and dates coexist
without mixing. An empty dashboard says which commands would fill it.

---

## 8. Skills

Five skills, following the progressive disclosure pattern: a name and
description that decide whether the skill loads at all, a SKILL.md that is
a router rather than a manual, and bundled resources loaded only when the
work needs them.

| skill | fires on | bundles |
|---|---|---|
| `options-greeks` | Greeks, chains, implied volatility by strike, theta decay, vega risk | `reference.md`, `workflows/pull-and-grade.md`, `scripts/check_artifact.py` |
| `options-strategy` | what structure fits a view, what an iron condor pays, which spread is better | `reference.md`, `workflows/choose-a-structure.md` |
| `options-positioning` | where the walls are, gamma flip, max pain, put-call ratio, skew | `reference.md`, `workflows/read-the-book.md` |
| `options-simulation` | what the underlying might do, value at risk, Monte Carlo, MCMC | `reference.md`, `workflows/run-a-projection.md` |
| `options-backtest` | has this worked historically, is the edge real, paper trade this | `reference.md`, `workflows/evaluate-a-rule.md` |

Every skill carries the same reporting rules: cite the artifact path, never
re-derive a number in prose, say when something is degraded before quoting
anything from it, and never recommend a trade.

They work with no Python installed at all, as domain knowledge rather than
automation. `./install.sh --skills-only` does exactly that.

For Codex and Gemini CLI, which load no skills, the same five are compiled
into `AGENTS.md` and `GEMINI.md` along with a command reference generated
from the argparse parsers. Both files are written to the repository root
and to `shell/`, because those runtimes look upward from where they were
opened and a copy in only one place is a file nobody reads.

---

## 9. Commands

Six, in `.claude/commands/`. A command is a procedure you invoke
deliberately, which is what separates it from a skill that loads itself.

| command | does |
|---|---|
| `/desk-open SYMBOL` | the full open: chain, ladder, positioning, every structure ranked |
| `/desk-risk` | project the underlying forward, compare realised against implied, then hand any structure on file to the adversarial reviewer |
| `/desk-test` | backtest and forward-test a structure, with the benchmark |
| `/desk-mark` | mark the paper ledger against the newest chain |
| `/desk-watch SYMBOL` | refresh and report only material change, built for time-based loops |
| `/desk-complete SYMBOL` | drive the artifact set to completeness, built for goal-based loops |

`/desk-complete` is a command rather than an agent, though it retries and
could be either. The deciding question is whether the work needs its own
context: it does not, because its six criteria are read from artifacts on
disk rather than from a conversation, and the main thread benefits from
seeing which criterion failed. The two agents below are agents for the
opposite reason.

---

## 10. Agents

Two, in `.claude/agents/`. An agent gets its own context window and a
narrower brief, which is what you want when the work would otherwise
pollute the main thread or when its job is to disagree.

`options-risk-reviewer` re-derives the risk of a proposed structure
independently from the artifacts, attacks the assumptions, and states what
would have to be true for the structure to lose. It is adversarial by
design: an agent that agrees with the plan it was given is not a review.
`/desk-risk` hands off to it as its last step; otherwise it is reached by
naming it or by description match.

`desk-data-auditor` checks freshness, completeness and internal consistency
of the artifacts before anyone reports from them. Stale data that looks
current is the failure this exists to catch.

---

## 11. MCP tools

Ten, over stdio, from `optiondesk-mcp`. Typed schemas, no prose, for any
runtime that speaks the protocol: Claude Code, Codex, Gemini CLI and
anything else.

`option_chain_snapshot`, `option_greeks_ladder`, `option_expiries`,
`option_strategy_build`, `option_strategy_compare`, `option_positioning`,
`option_simulate`, `option_backtest`, `option_forward_test`,
`option_desk_status`.

Arguments are whitelisted against the advertised schema, so a tool cannot
be talked into writing outside its output directory, and anything supplied
but not advertised comes back in `ignored_arguments` rather than
disappearing. Required arguments are enforced against the schema that
publishes them, so an omission is a `-32602` naming the tool and the
parameter rather than an `AttributeError` from somewhere inside a handler.
A malformed request is the caller's error and is reported as one; only a
genuine server fault is `-32603`.

Notifications, meaning requests with no id, are answered with nothing and,
more importantly, not executed. Until recently a `tools/call` sent as a
notification both ran the tool and emitted an unsolicited response with a
null id. A request carrying id `0`, which is legal and easy to lose to a
truthiness test, is still answered.

Every tool description carries the reporting rule, appended in a loop
rather than typed into ten strings so a tool added later cannot ship
without it, and every result that produces numbers carries the disclaimer.
That matters more here than anywhere else: this server is the surface Codex
and Gemini reach, and neither of them loads the skills where those rules
otherwise live.

---

## 12. The LangChain layer

For an application you are building yourself, where this is one capability
among several and the orchestration is yours.

`desk_tools()` returns nine `StructuredTool` objects wrapping the same
commands. `ArtifactStore` reads the artifact directory and exposes it three
ways: `records()` for the raw payloads, `documents()` as LangChain
`Document` objects for retrieval, and `context_for(underlying)` as a
summarised block short enough to put in a prompt. `prompts.py` holds the
reporting rules as text, so an application that uses these tools inherits
the same discipline about degraded data and about not recommending trades.

Nothing here computes anything. Every number still comes from the engine.

---

## 13. The graph

`agent/src/optiondesk_agent/graph.py`, requiring the optional `langgraph`
extra.

Opening a desk is not one call, it is a dependency chain: a snapshot, then
a ladder from it, then positioning, then structures, then a comparison.
Written as a script that is a sequence. Written as a graph it becomes
something you can inspect, resume from a checkpoint, and stop early when
the data says stop.

```python
from optiondesk_agent import open_desk

state = open_desk("SPY", budget=8)
state["outcome"]   # complete, exhausted, or failed
state["summary"]
state["log"]       # what it did, in order
```

Three nodes. `plan` reads which stages already have an artifact. `gather`
runs exactly one missing stage per visit and returns to the decision, which
is what makes the loop visible in the trace and stops a failure at the
stage that failed rather than somewhere downstream. `report` assembles the
summary.

The loop is bounded and its exits are distinct: `complete` when every stage
has an artifact, `exhausted` when the step budget is spent, `failed` when a
stage raised. Collapsing those three into a boolean is how an agent ends up
reporting success on an empty directory.

There is no model in the graph. Every node runs a deterministic command, so
the same inputs give the same outputs and a failure reproduces. Pass a
model only if you want the closing summary written rather than assembled.

---

## 14. Loops

Separate from the graph, and worth keeping separate. See `LOOPS.md` for the
full treatment.

| kind | how | which command |
|---|---|---|
| turn based | you ask, it finishes | `/desk-open SPY` |
| goal based | stop when a checkable condition holds | `/goal run /desk-complete SPY until every criterion is met, stop after
5 tries.` |
| time based | run again every so often | `/schedule every weekday at 21:30: run /desk-watch SPY` |
| proactive | scheduled, with a goal inside | `/schedule every weekday at 22:00: run /desk-complete SPY` |
| graph | inside an application you build | `open_desk("SPY", budget=8)` |

The two loop commands exist because a loop needs a stop condition that can
be checked without judgement. `/desk-complete` has six mechanical criteria.
`/desk-watch` has six named thresholds and stays silent below all of them.
"Find me a good trade" is not a loop, it is a request with no defined
finish, and an agent given one either stops arbitrarily or runs until
something breaks.

No loop in this project places an order, and none ever will.

---

## 15. Keeping it honest

`python3 scripts/refresh.py` rebuilds everything generated and then proves
it still holds together. Ten stages in a full run, since the test stage
is one per suite, and the exit code reflects all of them.

| stage | what it does |
|---|---|
| docs | regenerates `AGENTS.md` and `GEMINI.md` from the skills |
| inventory | regenerates `docs/INVENTORY.md` from the source |
| counts | rewrites the test counts the README quotes, which rot on every commit that adds a test |
| evidence | checks, never records, that documented figures still match `docs/evidence.json` |
| package | rebuilds `dist/`, `plugin/` and the marketplace manifest |
| index | refreshes the CodeGraph index so an agent can navigate by symbol |
| engine | runs the engine suite |
| shell | runs the shell suite |
| agent | runs the agent suite |
| rules | checks the house rules no test can see |

The rules stage scans every tracked text file for ANSI escape codes, emoji,
em dashes and anything shaped like a provider key, and fails the refresh if
it finds one. It is checked mechanically because a reviewer will not catch
the four hundredth instance, and a key that reaches a published file cannot
be unpublished.

The ANSI half of that scan is not hypothetical. On this machine `cat` is
aliased to `highlight -O ansi --force`, so anything that reads a file
through the shell and writes the result back embeds colour codes into the
source. A test file acquired a literal escape at column one of line 286
during this session and the scan caught it within the minute. Use
`/bin/cat` when a file's bytes matter.

The scan is itself tested, in `shell/tests/test_house_rules.py`, which
plants each banned thing in a temporary tree and asserts the scan reports
it, then plants ordinary prose and asserts it does not. That second half
matters as much: an early version flagged the word PARAMETERISATION as a
key, and a scan with false positives is switched off within a day, which
leaves you with no scan on the day it would have mattered.

`--fast` skips the suites, `--no-index` skips the index, `--no-package`
skips the installable forms.

Mutation testing is deliberately not one of the stages. It takes about a
minute and it is an activity rather than a check: `python3 scripts/mutate.py`.

### CodeGraph

The index is built by [CodeGraph](https://github.com/colbymchenry/codegraph),
`npm i -g @colbymchenry/codegraph`. It parses the tree into symbols and
call edges so an agent can ask where something is defined and what calls it
without grepping, and so a change can be traced to the tests it affects:

```
codegraph explore "implied volatility guard"
codegraph node all_greeks
codegraph impact bs_price
codegraph affected shell/src/optiondesk/cli/chain.py
```

It is optional. The refresh skips the stage with a note if the binary is
not installed, and `.codegraph/` is machine-local and git-ignored. Its
size is not quoted here: the index is rebuilt on every refresh and any
number written down is stale by the next run. `codegraph status` prints the
current figures.

`codegraph install` registers it as an MCP server, so an agent can query the
index directly rather than through the shell. `codegraph sync -q` in a
`post-commit` hook keeps it current between refreshes. Neither is done for
you, because indexing somebody's repository without being asked is not a
decision this project gets to make.

### The tests

The suites are the reason any of the above can be claimed. The Greeks are
checked against finite differences of their own price function. The MCMC is
validated by recovering parameters it was given, with coverage measured
across several datasets rather than one, and statistical properties tested
as frequencies because a 90 percent interval is supposed to miss one time
in ten. Mutation testing has been run against the Greek suite to confirm
the tests can actually fail: an earlier version used an absolute tolerance
that let fourteen of thirty-one mutations survive, which is a test suite
that passes rather than a test suite that works.

The harness is `scripts/mutate.py`, in the tree and runnable, because
"mutation tested" was written in this documentation before anything in the
repository could check it, which is exactly the unverifiable claim this
project is supposed to refuse. It applies forty-two breakages to a copy of
each file, runs the tests that ought to catch each one, and reports three
outcomes: killed by the test file named for it, killed elsewhere in the
suite, or survived. The current result is twenty-two, three and zero, plus
one mutant proven equivalent and recorded as such with the argument for why
it cannot be killed.

Fourteen of the twenty-six exist because of defects found and fixed on one day:
an MCP server that answered notifications, one that never enforced its own
required arguments, one that returned an internal error for a malformed
call, a house-rules scan whose key pattern could be weakened without
complaint, and a not-built result that dropped the degraded flag. A fix
without a mutation is a fix nobody notices being undone.

Running it for the first time found two genuine holes. The implied
volatility solver has two identifiability guards and only the outer one was
tested: with the inner one removed, thirty-nine of four hundred and fifty
sampled inputs raised ZeroDivisionError and ninety-four returned a
volatility for a price that identifies none, a one cent deep out of the
money put coming back at 254 percent. And nothing asserted that a
non-finite expectation stays out of the ranking. Both are now covered.

---

## 16. Installing

Six paths, each verified rather than written from memory. See `INSTALL.md`.

One command for everything (`./install.sh`), as a Claude Code plugin with
the commands and agents, from a checkout by hand, skills only with no
Python, zip upload for claude.ai in the browser, or the MCP server alone
for a runtime that has its own conventions.

`./install.sh --uninstall` removes exactly what it created and nothing
else: the virtualenv and source it made, the two symlinks if they still
point into it, the skills it marked as its own, and its own MCP
registration. Artifacts, other skills and binaries it did not create are
left alone.

---

## 17. What it will not do

It does not place orders. There is no broker integration, no execution
path, and no order object anywhere in the tree. `/desk-mark` touches a
paper ledger.

It does not give advice. Rankings are orderings under stated assumptions.
The reporting rules in every skill forbid recommending a trade, an entry,
an exit or a size, and the disclaimer is embedded in artifacts and in the
dashboard rather than living only in a file nobody opens.

It does not fill in missing data. A contract whose price identifies no
volatility gets a null. A position that cannot be marked is refused. A
simulation that did not converge says so. A provider named explicitly and
unable to answer fails rather than substituting.

It does not phone home. The shell fetches market data from whichever
provider answers, the engine has no network access at all, and nothing
about you or your usage is sent anywhere.

Read `DISCLAIMER.md`. This is research software, the author holds no
regulated status, and nothing here is a recommendation or a solicitation.

---

## 18. Where to go next

The obvious extensions, in the order they would pay off:

Asset classes beyond equity options, which is where the architecture is
already pointed: crypto options through a provider that carries them,
futures options under Black-76, a Treasury curve and bond pricing, FX
options with the two-currency convention. The engine's pricing module takes
a continuous yield already, which is most of what a futures or FX option
needs.

More structures still: the payoff engine expresses more than the playbook
names. Ratio spreads, broken wing butterflies and jade lizards are in as of
this pass; put ratios, condors with unequal wings and the rest of the
flexible-wing family are not.

More charts still. The surface, the variance risk premium, a condor panel
and gamma scalping levels shipped in this pass, taking the dashboard from
28 canvases to 32. Two of them are narrower than they sound, and the panels
say so themselves rather than leaving it to be discovered: the condor panel
plots the condors that exist as artifacts, because nothing in the engine
enumerates every condor a chain admits, and the gamma panel plots levels
rather than paths, because the simulation artifact stores the fan as
quantiles per day and not as individual paths. Both would need engine work
to become what their names suggest.

Each of those is additive. Nothing in this project has ever been removed to
make room for something else, and nothing should be.
