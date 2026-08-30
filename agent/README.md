# optiondesk-agent

LangChain bindings for the desk. MIT, like the shell it wraps.

## What this is, and what it deliberately is not

It exposes the desk's capabilities as LangChain tools, turns the artifacts
on disk into retrievable documents, and assembles a prompt that answers a
question strictly from those artifacts.

It is not in the compute path and must never be. Pricing, Greeks,
positioning, simulation and backtests all happen in the engine, which has
no dependency on this package and no knowledge that it exists. If LangChain
were in the compute path, a dependency bump could change a Greek, and the
numbers would stop being reproducible from the engine alone.

The separation is the point:

    engine    numbers, no dependencies, no network
    shell     data, contracts, artifacts, MCP, dashboard
    agent     language: tools, retrieval, and prompt assembly

## Why it exists next to MCP

MCP serves an agent runtime that already exists, such as Claude Code,
Codex or Gemini CLI. This serves an application someone builds themselves,
where the desk is one capability among several and the orchestration is
theirs. Both call the same commands and read the same artifacts.

## Use

```python
from optiondesk_agent import desk_tools, ArtifactStore, build_answer_prompt

tools = desk_tools()                      # LangChain StructuredTools
store = ArtifactStore()                   # documents from the artifact dir
context = store.context_for("SPY")
prompt = build_answer_prompt()            # carries the reporting rules
```

Bring your own model. This package deliberately declares no provider
dependency, so it adds no key requirement and no vendor to the tree.

## The graph

A desk routine as a bounded state machine, in `graph.py`. It needs the
optional extra:

```
pip install -e "agent[graph]"
```

```python
from optiondesk_agent import open_desk

state = open_desk("SPY", budget=8)
state["outcome"]    # complete, exhausted, or failed
state["summary"]
state["log"]        # every step it took, in order
```

Opening a desk is a dependency chain rather than one call: a chain
snapshot, then a Greek ladder from it, then positioning, then structures,
then a comparison. Three nodes handle it. `plan` reads which stages already
have an artifact. `gather` runs exactly one missing stage per visit and
returns to the decision, which keeps the loop visible in the trace and
stops a failure at the stage that failed rather than somewhere downstream.
`report` assembles the summary.

The three exits are kept distinct on purpose. `complete` means every stage
has an artifact, `exhausted` means the step budget ran out, `failed` means
a stage raised. Collapsing them into a boolean is how an agent ends up
reporting success on an empty directory.

There is no model in the graph. Every node runs a deterministic command, so
the same inputs give the same outputs and a failure reproduces. Pass
`model=` only if you want the closing summary written rather than
assembled, and the reporting rules below still apply to it.

Failures end the loop rather than being retried, because every failure this
pipeline produces is structural: a missing snapshot, an unbuildable
structure, a provider that is not answering. Running the same command again
produces the same failure while spending budget a different underlying
could have used.

`langgraph` stays optional at import time. `import optiondesk_agent` works
without it, and only touching `open_desk` or `build_desk_graph` pulls it in.

For loops outside an application, in Claude Code itself, see `LOOPS.md` at
the repository root.

## The reporting rules travel with the prompt

The prompt template carries the same rules the skills state: report the
degraded flag before any number, never substitute a default volatility,
never present modelled premiums as tradable, and never turn an analysis
into a recommendation. A language layer is exactly where those rules get
lost, so they are compiled into it rather than left to the caller.
