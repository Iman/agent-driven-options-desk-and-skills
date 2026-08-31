"""A desk routine as a state graph, with a bounded loop.

Copyright (C) 2026 Iman Samizadeh. PolyForm Noncommercial 1.0.0, like the rest of this project.

WHAT THIS IS FOR. Opening a desk on an underlying is not one call, it is a
short dependency chain: a chain snapshot, then a Greek ladder from it, then
positioning, then structures, then a comparison. Each step needs the
previous one's artifact. Written as a script that is a sequence; written as
a graph it becomes something you can inspect, resume, and stop early when
the data says stop.

THE LOOP, AND WHY IT IS BOUNDED. The gather node runs one missing step per
visit and comes back. It loops until the artifact set is complete, the
budget is spent, or a step fails in a way repeating cannot fix. Three
distinct exits, because "it finished", "it ran out of turns" and "it broke"
are three different outcomes and collapsing them is how an agent ends up
reporting success on an empty directory.

There is no model in this graph. Every node calls a deterministic command
and reads an artifact, so the same inputs give the same outputs and a
failure is reproducible. A language model belongs at the edges, deciding
what to ask for and how to say what came back, and there is a node for that
which stays inert unless you pass one in.

WHAT COMPLETE DOES NOT MEAN. This graph reports that every stage produced
an artifact. It does not report that the artifacts are right, and those are
different claims. Three independent verifications in September 2026 found
eleven defects in numbers that every stage of this graph would have called
complete: a solver refusing contracts it could identify, significance tests
assuming an independence that overlapping windows do not have, a maximum
that was a property of its own scan window. The gather node checks that a
file appeared. Nothing here checks what is in it.

The report node carries degradation through for that reason. When a stage
writes an artifact marked degraded, the summary says so rather than
presenting a complete run, because "every stage finished" and "the figures
can be relied on" are the two claims most easily confused by anything
reading this output, human or otherwise.

Requires langgraph, which is an optional extra of this package.
"""

import operator
from typing import Annotated, Any, TypedDict

from optiondesk_agent.artifacts import ArtifactStore

# The order matters: each step consumes what the previous one wrote.
PIPELINE = ("chain", "greeks", "exposure", "comparison")

DEFAULT_BUDGET = 8


class DeskState(TypedDict, total=False):
    """What flows through the graph.

    Kept flat and JSON-shaped so a checkpointer can serialise it and a
    human can read a paused run.
    """

    underlying: str
    expiry: str
    band: float
    budget: int
    steps_taken: int
    have: list
    missing: list
    log: Annotated[list, operator.add]
    failures: Annotated[list, operator.add]
    summary: str
    outcome: str


def _present(store, underlying, expiry=None, steps=PIPELINE):
    """Which of the named stages already have an artifact for this target.

    steps narrows the scan. gather passes the single stage it just ran, so
    verifying one runner's work costs one filtered read rather than a walk
    of the whole directory.
    """
    have = []
    for kind, payload, _ in store.records(underlying=underlying, kinds=steps):
        if expiry and payload.get("expiry") not in (None, expiry):
            continue
        if kind not in have:
            have.append(kind)
    return have


def build_desk_graph(store=None, runners=None, model=None):
    """Compile the routine.

    store lets a test point at a temporary directory. runners lets a test
    substitute the commands, which is the only way to exercise the loop
    without the network. model is optional and only used by the report
    node; without it the report is assembled from the artifacts alone.
    """
    from langgraph.graph import END, START, StateGraph

    store = store or ArtifactStore()
    runners = runners or _default_runners(store)

    def plan(state: DeskState) -> DeskState:
        underlying = state["underlying"]
        have = _present(store, underlying, state.get("expiry"))
        missing = [step for step in PIPELINE if step not in have]
        return {
            "have": have,
            "missing": missing,
            "budget": state.get("budget", DEFAULT_BUDGET),
            "steps_taken": state.get("steps_taken", 0),
            "log": ["plan: have {}, missing {}".format(
                ", ".join(have) or "nothing", ", ".join(missing) or "nothing")],
        }

    def gather(state: DeskState) -> DeskState:
        """Run exactly one missing step, then return to the decision.

        One per visit rather than all of them, so the loop is visible in
        the trace and a failure stops the run at the step that failed
        instead of somewhere downstream.
        """
        missing = list(state.get("missing") or [])
        # Unreachable through the compiled graph, and deliberately kept.
        #
        # Both edges into this node are the "continue" branch of decide (see
        # the two add_conditional_edges calls below), and decide returns
        # "continue" only after `if not state.get("missing")` has already
        # returned "complete". So missing is non-empty on every real entry,
        # and this line stays uncovered by design rather than by omission.
        # test_graph.py proves both halves: that the only edges into gather
        # carry the "continue" label, and that no run of any shape ever logs
        # this line.
        #
        # It is not deleted because what protects missing[0] below is that
        # routing invariant, not anything local to this function. A future
        # edge from plan or report straight into gather would turn the line
        # after this one into an IndexError, and an unexplained IndexError
        # inside a loop is a much worse thing to debug than a log line.
        if not missing:
            return {"log": ["gather: nothing to do"]}
        step = missing[0]
        runner = runners.get(step)
        if runner is None:
            return {"failures": ["no runner for step {}".format(step)],
                    "steps_taken": state.get("steps_taken", 0) + 1}
        try:
            result = runner(state)
        except Exception as exc:
            return {
                "failures": ["{} failed: {}: {}".format(
                    step, type(exc).__name__, exc)],
                "steps_taken": state.get("steps_taken", 0) + 1,
                "log": ["gather: {} raised".format(step)],
            }

        # A stage counts as done when its artifact is on disk, not when
        # its runner returned. A command that exits cleanly without writing,
        # or writes into a directory the store does not read, would
        # otherwise drive the run to "complete" over an empty directory.
        if step not in _present(store, state["underlying"],
                                state.get("expiry"), steps=(step,)):
            return {
                "failures": ["{} ran but wrote no artifact to {}".format(
                    step, store.directory)],
                "steps_taken": state.get("steps_taken", 0) + 1,
                "log": ["gather: {} wrote nothing".format(step)],
            }

        have = list(state.get("have") or [])
        if step not in have:
            have.append(step)
        note = ""
        if isinstance(result, dict):
            if result.get("degraded"):
                note = " (degraded: {})".format(result.get("degraded_reason"))
            elif result.get("built") is False:
                note = " (nothing viable)"
        return {
            "have": have,
            "missing": [s for s in missing if s != step],
            "steps_taken": state.get("steps_taken", 0) + 1,
            "log": ["gather: ran {}{}".format(step, note)],
        }

    def decide(state: DeskState) -> str:
        """Continue, stop because it is done, or stop because it cannot be.

        Failures end the loop rather than being retried. Every failure this
        pipeline produces is structural, a missing snapshot or an
        unbuildable structure, and running the same command again produces
        the same failure while spending budget that a different underlying
        or expiry could have used.
        """
        if state.get("failures"):
            return "failed"
        if not state.get("missing"):
            return "complete"
        if state.get("steps_taken", 0) >= state.get("budget",
                                                    DEFAULT_BUDGET):
            return "exhausted"
        return "continue"

    def report(state: DeskState) -> DeskState:
        context = store.context_for(state["underlying"], limit=8)
        outcome = state.get("_outcome") or (
            "failed" if state.get("failures")
            else "complete" if not state.get("missing") else "exhausted")
        # Completeness is a claim about the directory, so it is checked
        # against the directory. gather already refuses to mark a stage done
        # without its artifact; this is the second lock, covering a set
        # believed complete before the run whose artifacts went away
        # underneath it.
        extra_failures = []
        if outcome == "complete" and not store.records(
                underlying=state["underlying"]):
            outcome = "failed"
            extra_failures.append(
                "every stage reported done but {} holds no artifact for "
                "{}".format(store.directory, state["underlying"]))
        failures = list(state.get("failures") or []) + extra_failures
        header = {
            "complete": "Desk open on {}. Every stage has an artifact.",
            "exhausted": ("Desk partially open on {}. The step budget ran "
                          "out before the set was complete."),
            "failed": "Desk did not open on {}. A step failed.",
        }[outcome].format(state["underlying"])

        # Degradation is carried into the summary rather than left in the
        # artifacts for someone to find. "Every stage has an artifact" and
        # "the figures can be relied on" are two claims, and a reader who
        # sees only the first will hear the second. An audit of this
        # project found eleven defects in numbers every stage of this graph
        # would have called complete.
        degraded = []
        for kind, payload, _ in store.records(underlying=state["underlying"]):
            meta = (payload or {}).get("meta") or {}
            if meta.get("degraded"):
                degraded.append("  {}: {}".format(
                    kind, meta.get("degraded_reason") or "degraded"))

        body = [header, "", context]
        if degraded:
            body += ["", "Degraded stages, which the figures above inherit:"]
            body += sorted(set(degraded))
        if failures:
            body += ["", "Failures:"] + ["  " + f for f in failures]
        summary = "\n".join(body)

        if model is not None:
            from optiondesk_agent.prompts import build_answer_prompt

            prompt = build_answer_prompt()
            summary = model.invoke(prompt.format_messages(
                question="Summarise the state of this desk for a "
                         "professional reader.",
                context=context)).content

        return {"summary": summary, "outcome": outcome,
                "failures": extra_failures}

    graph = StateGraph(DeskState)
    graph.add_node("plan", plan)
    graph.add_node("gather", gather)
    graph.add_node("report", report)
    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", decide, {
        "continue": "gather",
        "complete": "report",
        "exhausted": "report",
        "failed": "report",
    })
    # The loop: gather returns to the same decision rather than to plan, so
    # the whole artifact directory is not rescanned on every pass. gather
    # does read the store for the one stage it just ran, because "done" has
    # to mean the artifact exists rather than the runner returned, and one
    # filtered read per step is the cheapest way to hold that line.
    graph.add_conditional_edges("gather", decide, {
        "continue": "gather",
        "complete": "report",
        "exhausted": "report",
        "failed": "report",
    })
    graph.add_edge("report", END)
    return graph.compile()


def _default_runners(store):
    """The real commands, one per pipeline stage.

    Every runner is told to write into the store's own directory. The store
    is what gather then checks for the artifact, so a runner left writing
    to the default location would report a stage done that the store cannot
    see, which is the split that let a run complete over nothing.
    """
    from optiondesk.cli import chain as chain_cmd
    from optiondesk.cli import compare as compare_cmd
    from optiondesk.cli import exposure as exposure_cmd
    from optiondesk.cli import greeks as greeks_cmd

    class _Args:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    out_dir = str(store.directory)

    def run_chain(state):
        return chain_cmd.run(_Args(
            symbol=state["underlying"], expiry=state.get("expiry"),
            provider=None, rate=None, dividend_yield=0.0, out_dir=out_dir))

    def run_greeks(state):
        return greeks_cmd.run(_Args(
            snapshot=None, band=state.get("band", 0.06), type="both",
            out_dir=out_dir))

    def run_exposure(state):
        return exposure_cmd.run(_Args(snapshot=None, multiplier=100.0,
                                      out_dir=out_dir))

    def run_comparison(state):
        return compare_cmd.run(_Args(snapshot=None, size=1.0,
                                     include_underlying=False, rebuild=False,
                                     out_dir=out_dir))

    return {"chain": run_chain, "greeks": run_greeks,
            "exposure": run_exposure, "comparison": run_comparison}


def open_desk(underlying, expiry=None, budget=DEFAULT_BUDGET, store=None,
              runners=None, model=None):
    """Run the routine to completion and return the final state."""
    graph = build_desk_graph(store=store, runners=runners, model=model)
    return graph.invoke({
        "underlying": underlying,
        "expiry": expiry,
        "budget": budget,
        "log": [],
        "failures": [],
    })
