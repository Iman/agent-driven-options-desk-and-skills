# Master algorithm: research, loops and reporting

[Architecture and diagrams](Architecture.md) | [Testing](../TESTING.md) | [Agent workflows](Agent-Workflows.md)

## Scope and notation

Algorithm 1 uses numbered, IEEE-style pseudocode to describe the complete research workflow.
It joins implemented Python paths and host-agent command instructions into one reference.
It is not one executable function, a new controller, or a claim of IEEE publication.

`A` is the local artifact store. `B` bounds Python graph steps. `K` bounds host-agent attempts.
`M` contains missing required artifacts. `F` contains recorded graph failures. `L` is an optional summary model.
The host-run watch and completion commands are distinct from the Python graph.
The hosted implementation is outside this repository. Its branch shows the documented connection boundary only.

## Algorithm 1

```text
ALGORITHM 1: OPTION DESK RESEARCH, CONTROL AND REPORTING
Input: request Q; operation mode; skill edition; artifact store A;
       graph step budget B; host attempt limit K; optional summary model L
Output: artifacts, quality observations, outcome and grounded report

001  Select the skill edition for the available local or hosted tools.
002  Read the relevant SKILL.md instructions and reporting requirements.
003  IF the tools run on the hosted service THEN
004      Connect through the separately configured remote MCP service.
005      Submit only operations exposed by that service with permitted input.
006      Receive its result; apply REPORT below; RETURN.
007  END IF
008  Check local tool availability and select the artifact directory.
009  IF Q needs an upload schema THEN return option_snapshot_schema.
010  IF an application uses the optional router prompt THEN
011      Assemble the router instruction and Q; obtain a proposed tool call.
012      The caller checks the proposal and invokes a supported local tool.
013      Do not use this model proposal to route the bounded Python graph.
014  END IF
015  Dispatch through CLI handlers, local MCP, or optional agent bindings.
016  Check each tool call for required arguments and supported names.
017  For a user snapshot, check rights, source, time and contract fields.
018  For a provider request, resolve the capability and check access and availability.
019  An explicit provider is strict by default; report failure if unavailable.
020  Route shell calculations through engine_bridge.
021  Preserve IV provenance; count missing IV and skipped calculations.

022  CASE mode OF
023    SINGLE_RESEARCH:
024      Run the requested handler using its declared inputs.
025      Build only structures supported by the available contracts, quotes and model inputs.
026      Retain payoff assumptions, friction, exclusions and degradation.
027       WHEN the requested handler is simulation:
028           Load permitted history and convert closes to daily log returns.
029           Require enough returns for the GARCH fit.
030           Fit GARCH-t with coordinate-wise Metropolis proposals.
031           Adapt step sizes during burn-in; freeze them for retained draws.
032           Compute split R-hat, per-parameter ESS and sampling acceptance.
033           Record convergence status and its diagnostic thresholds.
034           For each predictive path, draw parameters and independent shocks.
035           Propagate log price and conditional variance over the horizon.
036           Discard and count paths rejected by finite-value and upper-log-price guards; fail if none survive.
037           Compute the quantile fan and empirical underlying VaR/ES.
038           Evaluate intrinsic structure payoffs at horizon terminals; expiry alignment and surviving time value are not enforced.
039           Preserve diagnostics even when the posterior did not converge.
040           Withhold unconverged quantiles from the answer, as the reporting rules require.
041       END WHEN

042    BOUNDED_GRAPH:                                      [Python graph]
043      R := [chain, greeks, exposure, comparison].
044      Read A for the selected underlying and optional expiry.
045      M := kinds in R that are absent; s := initial steps_taken or zero.
046      F := recorded failures.
047      REPEAT
048          IF F is nonempty THEN outcome := failed; BREAK.
049          IF M is empty THEN outcome := complete; BREAK.
050          IF s >= B THEN outcome := exhausted; BREAK.
051          k := first missing kind in pipeline order.
052          IF runner k is absent THEN record failure; s := s + 1; CONTINUE.
053          Invoke runner k; count the attempt.
054          IF runner raises THEN record failure; CONTINUE.
055          Re-read A for the expected kind, underlying and expiry.
056          IF expected artifact is absent THEN record failure; CONTINUE.
057          Remove k from M; record progress and any degraded result.
058      UNTIL an outcome is assigned.
059      Re-read report context; if a complete result has no records, fail it.
060      Artifact presence does not establish a successful trading thesis.

061    COMPLETE_DESK:                                  [Host instructions]
062      Select the requested expiry or the nearest listed expiry beyond a week.
063      FOR attempt := 1 TO host limit K DO
064          Read the six criteria directly from artifacts:
065              IV coverage >= 90%; graded rows >= 50;
066              both walls and a smile; rankable structures >= 5;
067              converged simulation with horizon >= ceil(days_to_expiry);
068              no degradation reason except disclosed IV fallback.
069          IF every criterion holds THEN report criteria met; BREAK.
070          IF a structural blocker exists THEN report it and STOP.
071          Run only missing or failing stages.
072          For sparse input, consider a farther expiry or a wider Greek band.
073          For unconverged sampling, try 4000 then 6000 draws.
074          Stop after two failures at 6000 draws.
075      END FOR
076      Report each criterion, its observed value and any unmet condition.
077      Keep these quality criteria separate from BOUNDED_GRAPH's presence checks.

078    WATCH:                                            [Host instructions]
079      Read baseline values BEFORE refreshing the selected expiry.
080      Refresh chain, Greeks and exposure.
081      Compare available old/new values: spot > 1%, ATM IV > 1 point,
082          RR > 0.5 point, regime flip, wall strike change, new degradation.
083      Report a newly unavailable value as unavailable, not a numeric move.
084      Report material changes with previous values, or no material change.
085      Stop this invocation; the host controls any later recurrence.
086      Do not open, mark or close a position in WATCH.

087    BACKTEST:
088      Load permitted underlying history and validate its length.
089      FOR each eligible entry index after the lookback window DO
090          Estimate trailing centred annualized volatility from past returns.
091          Price a synthetic chain for holding_days / 252 years.
092          Build the requested compatible structure.
093          IF volatility or plan is unavailable THEN record skip; CONTINUE.
094          Settle the payoff at the historical exit underlying price.
095          Record entry legs, model premiums, capital at risk and P/L.
096          Record return on risk only where its denominator is defined.
097          Advance entries by entry_every trading-day indices.
098      END FOR
099      Sum returns in risk units; compute statistics and drawdown.
100      Set block length to max(1, ceil(holding_days / entry_every)).
101      Run block sign-flip randomization and moving-block bootstrap; report their assumptions and degenerate samples.
102      Include the buy-and-hold benchmark and model-premium limitations.

103    FORWARD_OPEN:
104      Read an explicit plan or the newest matching saved plan.
105      Record a new open paper position: ID, time, entry legs/prices,
106          entry spot, source plan and optional thesis; save the ledger.

107    FORWARD_MARK:
108      FOR each selected open paper position DO
109          Find the newest on-disk chain matching underlying and expiry.
110          IF absent THEN report unmarkable; keep position open; CONTINUE.
111          Match option legs by symbol, then strike/type; mark stock at spot.
112          Use available mid, bid/ask midpoint, or labelled last trade.
113          IF any leg lacks a mark THEN append unmarkable result.
114          ELSE append mark_value minus entry_value and quality notes.
115     END FOR
116     Save the ledger; report successful marks and unmarkable positions.

117   FORWARD_CLOSE:
118     Require an ID for an open paper position; reject missing/closed IDs.
119     Use explicit settlement price or newest matching on-disk spot.
120     Compute intrinsic-payoff settlement and record closed status/time.
121     Save the ledger. Expiry and quote freshness are not enforced here.
122     This settlement path does not price a surviving two-expiry leg.

123   FORWARD_STATUS:
124     Read open/closed positions and summarize paper outcomes.
125 END CASE

126 For artifact-producing handlers, validate the corresponding JSON schema.
127 Preserve provenance, missing counts, quality flags and model assumptions.
128 Use the artifact writer: archive replaced content by default, then
129     write through a temporary file and atomically replace the target.
130 The preceding writes occur within their handlers, before graph re-checks.

131 REPORT:
132     Assemble saved artifact context for the question or graph outcome.
133     IF a summary model L was supplied to the graph THEN
134         system := REPORTING_RULES.
135         The prompt helper can append caller-supplied deployment rules.
136         human := artifact context followed by the question.
137         Invoke L once for the final summary; do not rerun calculations.
138     ELSE assemble the deterministic graph summary or caller's report.
139     Surface degradation before numbers; give source, time and units.
140     Preserve missing values and the word unlimited.
141     State dealer-sign assumptions and model-premium limitations.
142     Withhold unconverged simulation quantiles under the reporting rules.
143     Present backtest context and uncertainty; give no trade recommendation.
144     Model compliance with these reporting requirements still needs verification.
145 RETURN artifacts, outcome, observations and report.
```

## Implementation and instruction map

| Algorithm block | Evidence |
|---|---|
| Skills and execution surfaces | [Local skills](../../shell/skills/), [hosted skills](../../openai-skills/), [installation guide](Skill-Installation.md) |
| Local tool arguments | [MCP server](../../shell/src/optiondesk/mcp/server.py) |
| Uploads and provider selection | [Chain command](../../shell/src/optiondesk/cli/chain.py), [provider registry](../../shell/src/optiondesk/providers/__init__.py), [provider access](../../shell/src/optiondesk/providers/base.py) |
| Bounded graph and outcomes | [graph.py](../../agent/src/optiondesk_agent/graph.py) |
| Host completion and watch policies | [desk-complete.md](../../.claude/commands/desk-complete.md), [desk-watch.md](../../.claude/commands/desk-watch.md) |
| Historical backtests | [Runner](../../engine/src/optiondesk_engine/backtest/runner.py), [statistics](../../engine/src/optiondesk_engine/backtest/stats.py), [CLI orchestration](../../shell/src/optiondesk/cli/backtest.py) |
| Paper open, mark, close and status | [Ledger command](../../shell/src/optiondesk/cli/forward.py), [mark and settlement math](../../engine/src/optiondesk_engine/backtest/forward.py) |
| Prompt assembly and final summary | [prompts.py](../../agent/src/optiondesk_agent/prompts.py), [graph report node](../../agent/src/optiondesk_agent/graph.py) |
| Validation and replacement | [Contracts](../../shell/src/optiondesk/contracts/), [artifact writer](../../shell/src/optiondesk/artifacts.py) |

## Workflow diagrams

### Graph routing

![Bounded graph and report stage](../diagrams/10_bounded_workflow.png)

### Host loops

![Watch and completion command policies](../diagrams/11_research_loops.png)

### Prompt construction

![Prompt assembly and optional summary model](../diagrams/12_prompt_assembly.png)

### Historical backtest

![Backtest entry loop and uncertainty](../diagrams/13_backtest_workflow.png)

### Forward paper test

![Open, mark, close and status lifecycle](../diagrams/14_forward_paper_lifecycle.png)

## Limits that change interpretation

The Python graph checks artifact presence. The completion command asks the host to check six stronger quality conditions.
Neither condition proves an edge or a profitable strategy.

The watch thresholds are instructions in a command file. Recurrence and attempt limits belong to the host.
Prompt requirements do not prove that a model follows every instruction.
The optional router prompt proposes a tool call. It does not execute the call or route the Python graph.

Backtests use model premiums and omit spreads, slippage, assignment and early exercise.
The runner does not supply the second chain needed by two-expiry builders.
Forward close uses intrinsic settlement and does not enforce expiry or snapshot freshness.
It does not perform general two-expiry valuation.

The reviewed source revision is `79e8d7f`. Public reference archives retain their original contents and historical claims.

## Numerical and inference limits

The IV solver rounds its accepted candidate before returning it. The rounded IV need not reprice within the internal tolerance. Partial option quotes can still produce an ok friction verdict.

Simulation rejects paths at its finite-value and upper-log-price guards. Its structure callback applies intrinsic payoff at the requested horizon without aligning plan expiries or retaining a far leg's time value. Sample means of unbounded payoffs need not estimate a finite expectation under Student-t log returns.

Block sign-flip randomization requires symmetry under the allowed flips. Block methods retain within-block dependence but can lose it at boundaries. A bootstrap with one available block has no resampling variation; its zero-width interval cannot support a conclusion. The current even-sample median field selects the upper middle observation. These are documented runtime limits, not additional guards in the algorithm.
