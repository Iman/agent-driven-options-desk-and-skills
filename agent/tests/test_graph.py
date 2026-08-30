"""The desk graph: one step per visit, three exits, and a bounded loop.

No network and no model. Every runner here is a closure that records that
it was called and writes the stub artifact its stage stands for, because a
stage now counts as done only when its artifact is on disk. A runner that
writes nothing is therefore a faithful simulation of a broken command
rather than a convenience, and is used deliberately where that is the
behaviour under test.
"""

from types import SimpleNamespace

import pytest

from optiondesk_agent import graph as graph_module
from optiondesk_agent.graph import (
    DEFAULT_BUDGET,
    PIPELINE,
    build_desk_graph,
    open_desk,
)
from optiondesk_agent.prompts import REPORTING_RULES


def recorder(calls, step, artifacts, result=None, write=True):
    """One fake runner: records the call and writes its stage's artifact."""
    def run(state):
        calls.append(step)
        if write:
            artifacts(step, underlying=state["underlying"],
                      expiry=state.get("expiry"))
        return dict(result or {})

    return run


def runner_set(calls, artifacts, result=None, **overrides):
    """A runner for every pipeline stage, with named stages replaced."""
    runners = {step: recorder(calls, step, artifacts, result)
               for step in PIPELINE}
    runners.update(overrides)
    return runners


def ran_steps(state):
    """The steps the log says gather actually ran."""
    return [line.split("gather: ran ")[1].split(" (")[0]
            for line in state["log"] if line.startswith("gather: ran ")]


def _raiser(state):
    """A runner that fails the way a provider refusal fails."""
    raise RuntimeError("provider refused the request")


# --------------------------------------------------------------------------
# The four outcomes of decide.
# --------------------------------------------------------------------------

def test_complete_when_every_stage_has_run(store, write_artifact):
    """Catches the loop exiting early, or never reaching the report node.

    Complete is the only outcome that may claim the set is whole, so if
    another outcome starts producing this header a partial desk gets
    reported as a finished one.
    """
    calls = []
    final = open_desk("SPY", store=store,
                      runners=runner_set(calls, write_artifact))

    assert final["outcome"] == "complete"
    assert calls == list(PIPELINE)
    assert final["missing"] == []
    assert final["summary"].startswith(
        "Desk open on SPY. Every stage has an artifact.")


def test_exhausted_stops_at_the_budget_and_says_so(store, write_artifact):
    """Catches a budget that is counted but not enforced.

    A budget that does not stop the loop is not a budget, and the run it
    was meant to bound is the one that reaches a provider repeatedly.
    """
    calls = []
    final = open_desk("SPY", budget=2, store=store,
                      runners=runner_set(calls, write_artifact))

    assert final["outcome"] == "exhausted"
    assert final["steps_taken"] == 2
    assert len(calls) == 2
    assert final["missing"] == ["exposure", "comparison"]
    assert final["summary"].startswith(
        "Desk partially open on SPY. The step budget ran out")


def test_failed_when_a_runner_raises(store, write_artifact):
    """Catches an exception being swallowed into a successful-looking run.

    A failed step that reports complete is the worst of the three outcomes
    to get wrong: the caller acts on a set it believes is whole.
    """
    def boom(state):
        raise RuntimeError("provider refused the request")

    calls = []
    final = open_desk("SPY", store=store,
                      runners=runner_set(calls, write_artifact, chain=boom))

    assert final["outcome"] == "failed"
    assert final["summary"].startswith("Desk did not open on SPY.")
    assert "Failures:" in final["summary"]


def test_continue_actually_iterates_more_than_once(store, write_artifact):
    """Catches a graph that runs one pass and reports on it.

    If gather never loops back, this suite would still see a plausible
    final state while three of the four stages had never been attempted.
    """
    calls = []
    final = open_desk("SPY", store=store,
                      runners=runner_set(calls, write_artifact))

    assert len(ran_steps(final)) == 4
    assert final["steps_taken"] == 4
    assert len(calls) == 4


# --------------------------------------------------------------------------
# Done means the artifact exists, not that the runner returned.
# --------------------------------------------------------------------------

def test_a_runner_that_writes_nothing_fails_rather_than_completing(store):
    """Catches the run reporting success over an empty directory.

    This is the defect the module docstring says the three exits exist to
    prevent. A command can exit zero and write nothing, and marking the
    stage done on the return value alone drove the whole pipeline to
    complete with the header "Every stage has an artifact" printed directly
    above a context line saying none are on disk.
    """
    def writes_nothing(state):
        return {}

    final = open_desk("SPY", store=store,
                      runners={step: writes_nothing for step in PIPELINE})

    assert final["outcome"] == "failed"
    assert "Every stage has an artifact" not in final["summary"]
    assert final["have"] in ([], None)


def test_the_missing_artifact_failure_names_the_step_and_directory(store):
    """Catches a failure that says a stage broke without saying where.

    The directory is the diagnostic: the usual cause is a runner writing to
    the default artifact directory while the store reads somewhere else,
    and that is invisible unless the message says which path was checked.
    """
    final = open_desk("SPY", store=store,
                      runners={step: (lambda s: {}) for step in PIPELINE})

    assert len(final["failures"]) == 1
    entry = final["failures"][0]
    assert entry.startswith("chain ran but wrote no artifact to ")
    assert str(store.directory) in entry
    assert "gather: chain wrote nothing" in final["log"]


def test_an_artifact_for_the_wrong_underlying_does_not_count_as_done(
        store, write_artifact):
    """Catches the artifact check ignoring which underlying was requested.

    A runner that writes a QQQ chain during an SPY run has not completed
    the SPY chain stage. Accepting any artifact of the right kind would let
    a mis-targeted command satisfy the check.
    """
    def writes_wrong_symbol(state):
        write_artifact("chain", underlying="QQQ")
        return {}

    final = open_desk("SPY", store=store,
                      runners=runner_set([], write_artifact,
                                         chain=writes_wrong_symbol))

    assert final["outcome"] == "failed"
    assert final["failures"][0].startswith("chain ran but wrote no artifact")


def test_a_stage_that_writes_late_in_the_pipeline_still_completes(
        store, write_artifact):
    """Catches the artifact check being applied to the wrong stage.

    Verifying "any pipeline artifact exists" rather than "this stage's
    artifact exists" would pass every step after the first one for free.
    """
    calls = []
    final = open_desk("SPY", store=store,
                      runners=runner_set(calls, write_artifact))

    assert final["outcome"] == "complete"
    assert sorted(final["have"]) == sorted(PIPELINE)


def test_report_will_not_claim_complete_when_the_store_holds_nothing():
    """Catches the header outliving the artifacts it describes.

    gather blocks the common case, but a set believed complete before the
    run starts reaches report without gather ever running. If the artifacts
    are gone by then, the run must not still announce a full desk.
    """
    class VanishingStore:
        """Artifacts that are there for plan and gone by report."""

        def __init__(self):
            self.directory = "/desk/artifacts"
            self.reads = 0

        def records(self, underlying=None, kinds=None):
            self.reads += 1
            if self.reads == 1:
                return [(kind, {"underlying": "SPY", "expiry": None},
                         "{}_SPY.json".format(kind)) for kind in PIPELINE]
            return []

        def context_for(self, underlying=None, kinds=None, limit=12):
            return "No artifacts are on disk for this request."

    final = open_desk("SPY", store=VanishingStore(),
                      runners={step: (lambda s: {}) for step in PIPELINE})

    assert final["outcome"] == "failed"
    assert "Every stage has an artifact" not in final["summary"]
    assert "holds no artifact for SPY" in final["summary"]


def test_the_default_runners_write_where_the_store_reads(monkeypatch, store):
    """Catches the runners and the store pointing at different directories.

    The shipped runners used to hardcode out_dir None, so they wrote to the
    default artifact directory while the store could be reading anywhere.
    With the artifact check in place that split turns every run against a
    non-default store into a failure, and before it, into a false complete.
    """
    from optiondesk.cli import chain as chain_cmd
    from optiondesk.cli import compare as compare_cmd
    from optiondesk.cli import exposure as exposure_cmd
    from optiondesk.cli import greeks as greeks_cmd

    seen = {}

    def capture(step):
        def run(args):
            seen[step] = args.out_dir
            return {}
        return run

    for module, step in ((chain_cmd, "chain"), (greeks_cmd, "greeks"),
                         (exposure_cmd, "exposure"),
                         (compare_cmd, "comparison")):
        monkeypatch.setattr(module, "run", capture(step))

    runners = graph_module._default_runners(store)
    for runner in runners.values():
        runner({"underlying": "SPY", "expiry": None})

    assert set(runners) == set(PIPELINE)
    assert seen == {step: str(store.directory) for step in PIPELINE}


# --------------------------------------------------------------------------
# The loop is bounded.
# --------------------------------------------------------------------------

def test_a_runner_that_marks_nothing_done_terminates_immediately(store):
    """Catches an unbounded loop when a step never satisfies its condition.

    This runner writes no artifact, so nothing it does makes progress the
    store can see. The run must stop rather than spin, and it must stop by
    naming the failure rather than by hitting langgraph's recursion limit,
    which would surface as a crash instead of a diagnosis.
    """
    final = open_desk("SPY", budget=8, store=store,
                      runners={step: (lambda s: {}) for step in PIPELINE})

    assert final["outcome"] == "failed"
    assert final["steps_taken"] == 1


@pytest.mark.parametrize("budget", [1, 2, 3])
def test_steps_taken_never_exceeds_the_budget(store, write_artifact, budget):
    """Catches an off-by-one that lets the loop spend one step too many.

    The budget exists to cap provider calls, so a loop that overruns it by
    one is a loop that makes a call the caller declined to authorise.
    """
    calls = []
    final = open_desk("SPY", budget=budget, store=store,
                      runners=runner_set(calls, write_artifact))

    assert final["steps_taken"] == budget
    assert len(calls) == budget


def test_budget_of_zero_runs_no_step_at_all(store, write_artifact):
    """Catches a budget checked only after the first step has been spent.

    A caller passing zero is declining to run anything, usually to inspect
    the plan; a first free step makes that a network call they refused.
    """
    calls = []
    final = open_desk("SPY", budget=0, store=store,
                      runners=runner_set(calls, write_artifact))

    assert calls == []
    assert final["outcome"] == "exhausted"
    assert final["steps_taken"] == 0


# --------------------------------------------------------------------------
# One step per visit.
# --------------------------------------------------------------------------

def test_gather_runs_exactly_one_step_per_visit(store, write_artifact):
    """Catches gather draining the whole missing list in a single visit.

    Four stages are missing and the budget allows one. If gather ran the
    list, all four runners would fire and the budget would have bounded
    nothing. This is the assertion that distinguishes a loop from a script.
    """
    calls = []
    final = open_desk("SPY", budget=1, store=store,
                      runners=runner_set(calls, write_artifact))

    assert calls == ["chain"]
    assert final["steps_taken"] == 1
    assert final["have"] == ["chain"]
    assert final["missing"] == ["greeks", "exposure", "comparison"]


def test_gather_verifies_one_stage_without_rescanning_the_directory(
        store, write_artifact):
    """Catches the per-step check widening back into a full directory scan.

    The loop comment promises gather does not rescan the whole artifact
    directory on every pass, and the artifact check is the thing most
    likely to break that promise quietly. A scan costs nothing on a fresh
    temp directory and grows with every artifact a real desk accumulates,
    so the regression is invisible in tests and only shows up in use.
    """
    class SpyStore:
        """Passes everything through, remembering what kinds were asked for."""

        def __init__(self, inner):
            self.inner = inner
            self.directory = inner.directory
            self.kind_queries = []

        def records(self, underlying=None, kinds=None):
            self.kind_queries.append(kinds)
            return self.inner.records(underlying, kinds)

        def context_for(self, underlying=None, kinds=None, limit=12):
            return self.inner.context_for(underlying, kinds, limit)

    spy = SpyStore(store)
    open_desk("SPY", store=spy, runners=runner_set([], write_artifact))

    single = [query for query in spy.kind_queries
              if query is not None and len(query) == 1]

    assert [query[0] for query in single] == list(PIPELINE)


def test_steps_run_in_pipeline_order(store, write_artifact):
    """Catches a gather that picks an arbitrary missing step.

    Each stage consumes the previous stage's artifact, so running greeks
    before chain does not produce a Greek ladder, it produces a failure
    whose cause is one step upstream of where it is reported.
    """
    calls = []
    open_desk("SPY", store=store, runners=runner_set(calls, write_artifact))

    assert calls == ["chain", "greeks", "exposure", "comparison"]


def test_a_stage_already_on_disk_is_not_run_again(store, write_artifact):
    """Catches the plan node ignoring what is already in the directory.

    Re-fetching a chain that is already local is a wasted provider call and
    a second, differently timestamped artifact for the same expiry.
    """
    write_artifact("chain", underlying="SPY")
    calls = []
    final = open_desk("SPY", store=store,
                      runners=runner_set(calls, write_artifact))

    assert "chain" not in calls
    assert calls == ["greeks", "exposure", "comparison"]
    assert final["have"][0] == "chain"


def test_an_artifact_for_a_different_expiry_does_not_count_as_progress(
        store, write_artifact):
    """Catches the plan node matching on underlying and ignoring expiry.

    A September chain on disk must not satisfy an October desk. Every later
    stage reads "the latest chain snapshot", so a stale expiry accepted
    here produces a Greek ladder and a positioning report for an expiry
    nobody asked about, with nothing in the output saying which one it is.
    """
    write_artifact("chain", underlying="SPY", expiry="2026-10-16")
    calls = []
    open_desk("SPY", expiry="2026-09-18", store=store,
              runners=runner_set(calls, write_artifact))

    assert calls == ["chain", "greeks", "exposure", "comparison"]


def test_an_artifact_for_the_requested_expiry_does_count_as_progress(
        store, write_artifact):
    """Catches an expiry filter so strict it never matches anything.

    The mirror of the test above. A filter that rejects the expiry it was
    asked for re-fetches a chain that is already local on every run.
    """
    write_artifact("chain", underlying="SPY", expiry="2026-09-18")
    calls = []
    open_desk("SPY", expiry="2026-09-18", store=store,
              runners=runner_set(calls, write_artifact))

    assert "chain" not in calls


def test_artifacts_for_another_underlying_do_not_count_as_progress(
        store, write_artifact):
    """Catches the plan node matching artifacts by kind and ignoring symbol.

    A QQQ chain on disk must not make an SPY desk believe its chain stage
    is done, or the Greek ladder is built from the wrong underlying.
    """
    write_artifact("chain", underlying="QQQ")
    calls = []
    open_desk("SPY", store=store, runners=runner_set(calls, write_artifact))

    assert calls == ["chain", "greeks", "exposure", "comparison"]


# --------------------------------------------------------------------------
# A raising runner is named, and stops the run.
# --------------------------------------------------------------------------

def test_a_raising_runner_names_the_step_and_the_exception(store,
                                                           write_artifact):
    """Catches a failure recorded without saying which step produced it.

    "something failed" in a four stage pipeline costs a human the whole
    chain to bisect; the step name is the entire value of the record.
    """
    def boom(state):
        raise RuntimeError("provider refused the request")

    final = open_desk("SPY", store=store,
                      runners=runner_set([], write_artifact, chain=boom))

    assert len(final["failures"]) == 1
    entry = final["failures"][0]
    assert entry.startswith("chain failed:")
    assert "RuntimeError" in entry
    assert "provider refused the request" in entry


def test_a_raising_runner_does_not_silently_continue(store, write_artifact):
    """Catches the loop carrying on past a failed dependency.

    greeks reads the snapshot chain was supposed to write. Running it after
    chain raised either fails on a missing file or, worse, succeeds against
    a stale snapshot from an earlier session and reports it as today's.
    """
    def boom(state):
        raise RuntimeError("provider refused the request")

    calls = []
    final = open_desk("SPY", store=store,
                      runners=runner_set(calls, write_artifact, chain=boom))

    assert calls == []
    assert final["steps_taken"] == 1
    assert final["outcome"] == "failed"


def test_a_failure_late_in_the_pipeline_keeps_the_earlier_work(
        store, write_artifact):
    """Catches a failure discarding the stages that did succeed.

    The artifacts already written are still valid and still worth reporting;
    throwing them away turns one broken stage into a wasted run.
    """
    def boom(state):
        raise RuntimeError("no structure was buildable")

    calls = []
    final = open_desk("SPY", store=store,
                      runners=runner_set(calls, write_artifact,
                                         comparison=boom))

    assert calls == ["chain", "greeks", "exposure"]
    assert final["outcome"] == "failed"
    assert final["have"] == ["chain", "greeks", "exposure"]
    assert "chain for SPY" in final["summary"]


def test_a_missing_runner_is_a_failure_not_a_skip(store, write_artifact):
    """Catches an unroutable step being treated as nothing to do.

    A pipeline stage with no runner behind it must not look like a stage
    that had nothing to do, or the set is reported complete without it.
    """
    calls = []
    final = open_desk("SPY", store=store,
                      runners={"chain": recorder(calls, "chain",
                                                 write_artifact)})

    assert calls == ["chain"]
    assert final["outcome"] == "failed"
    assert final["failures"] == ["no runner for step greeks"]


# --------------------------------------------------------------------------
# Degradation reaches the reader.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("degraded_step", PIPELINE)
def test_a_degraded_summary_is_logged_for_every_stage(store, write_artifact,
                                                      degraded_step):
    """Catches a stage whose command summary omits the degraded flag.

    All eight desk commands now carry degraded and degraded_reason in the
    summary a caller reads, not only in the artifact envelope, and
    shell/tests/test_summary_degraded_contract.py enforces that statically.
    So every pipeline stage must be able to produce a degraded note here.
    Two of the four could not before that change, and a reader of the log
    could not tell a fallback provider from a clean pull.
    """
    def degraded(state):
        write_artifact(degraded_step, underlying=state["underlying"],
                       expiry=state.get("expiry"))
        return {"degraded": True,
                "degraded_reason": "provider fell back to delayed quotes"}

    runners = runner_set([], write_artifact)
    runners[degraded_step] = degraded
    final = open_desk("SPY", store=store, runners=runners)

    assert final["outcome"] == "complete"
    assert "gather: ran {} (degraded: provider fell back to delayed " \
        "quotes)".format(degraded_step) in final["log"]


def test_a_healthy_step_is_logged_without_a_degraded_note(store,
                                                          write_artifact):
    """Catches every stage being marked degraded, which mutes the signal.

    A flag that fires on clean data is one a reader learns to skip, and
    then misses the run where it mattered.
    """
    final = open_desk("SPY", store=store,
                      runners=runner_set([], write_artifact))

    assert "gather: ran chain" in final["log"]
    assert not [line for line in final["log"] if "degraded" in line]


def test_a_step_that_built_nothing_is_named_in_the_log(store,
                                                       write_artifact):
    """Catches an empty result being logged as an ordinary success.

    "ran comparison" over zero rankable structures reads as a comparison
    that happened; it is a comparison that had nothing to compare.
    """
    def nothing_viable(state):
        write_artifact("comparison", underlying=state["underlying"],
                       expiry=state.get("expiry"))
        return {"built": False}

    final = open_desk("SPY", store=store,
                      runners=runner_set([], write_artifact,
                                         comparison=nothing_viable))

    assert "gather: ran comparison (nothing viable)" in final["log"]


def test_a_summary_without_a_degraded_key_still_reports_the_artifact(
        store, write_artifact):
    """Catches the reader's warning being sourced from the command summary.

    gather reads result.get("degraded") from what the runner returned;
    _summarise reads meta.degraded from what the runner wrote. They are
    two different reads of two different objects, and only the second one
    reaches the reader, because report assembles the body from
    store.context_for and never from the log.

    So a summary dict that carries no degraded key at all costs the log its
    note and costs the reader nothing. That is the safe direction of the
    mismatch, and this pins it: the flag the reader sees does not depend on
    the shape of the dict a command chose to return.
    """
    def silent_about_degradation(state):
        write_artifact("chain", underlying=state["underlying"],
                       expiry=state.get("expiry"), degraded=True,
                       degraded_reason="provider fell back to delayed quotes")
        return {"artifact": "written", "contracts": 812}

    final = open_desk("SPY", budget=1, store=store,
                      runners=runner_set([], write_artifact,
                                         chain=silent_about_degradation))

    assert "gather: ran chain" in final["log"]
    assert not [line for line in final["log"] if "degraded" in line]
    assert "DEGRADED: provider fell back to delayed quotes" in final["summary"]


def test_a_degraded_summary_over_a_clean_artifact_warns_only_in_the_log(
        store, write_artifact):
    """Pins the unsafe direction of the same mismatch, which is not guarded.

    Reversed, the flag is in the command summary and not in the artifact
    envelope. gather logs the note, but report builds its body from
    context_for alone, so the text a person or a model reads carries no
    warning at all. state["log"] is the only place the degradation
    survives, and nothing makes a reader of the summary look there.

    This is a guard, not a live defect. The four commands the graph drives
    set both flags from one expression, so today they cannot disagree:
    chain.py:142 against chain.py:179, greeks.py:154 against greeks.py:186,
    exposure.py:102 against exposure.py:130, compare.py:149 against
    compare.py:177 (read 2026-08-30). If a command is ever changed so that
    only its summary knows it was degraded, this test fails and says which
    half of the pipeline lost the flag.
    """
    def flag_in_summary_only(state):
        write_artifact("chain", underlying=state["underlying"],
                       expiry=state.get("expiry"), degraded=False)
        return {"degraded": True,
                "degraded_reason": "provider fell back to delayed quotes"}

    final = open_desk("SPY", budget=1, store=store,
                      runners=runner_set([], write_artifact,
                                         chain=flag_in_summary_only))

    assert ("gather: ran chain (degraded: provider fell back to delayed "
            "quotes)") in final["log"]
    # The artifact path is in the summary and the temporary directory is
    # named after this test, so match the reason rather than the word.
    assert "DEGRADED" not in final["summary"]
    assert "provider fell back to delayed quotes" not in final["summary"]


def test_degradation_recorded_in_the_artifact_reaches_the_summary(
        store, write_artifact):
    """Catches the report body quoting numbers without the degraded flag.

    The envelope is the durable record. Even if a command summary lost the
    flag again, the report is assembled from the artifacts, so this is the
    path that has to keep working.
    """
    def degraded_writer(state):
        write_artifact("chain", underlying=state["underlying"],
                       expiry=state.get("expiry"), degraded=True,
                       degraded_reason="stale underlying quote")
        return {}

    final = open_desk("SPY", budget=1, store=store,
                      runners=runner_set([], write_artifact,
                                         chain=degraded_writer))

    assert "DEGRADED: stale underlying quote" in final["summary"]


# --------------------------------------------------------------------------
# The report node.
# --------------------------------------------------------------------------

def test_the_report_says_nothing_is_on_disk_rather_than_inventing(
        store, write_artifact):
    """Catches a report that pads an empty directory with plausible prose.

    An empty artifact set has to read as empty. This is the one place a
    language layer is most tempted to be helpful and least entitled to be.
    """
    final = open_desk("SPY", budget=0, store=store,
                      runners=runner_set([], write_artifact))

    assert "No artifacts are on disk for this request." in final["summary"]


def test_a_supplied_model_is_given_the_reporting_rules(store, write_artifact):
    """Catches the model node being handed a bare question.

    A model summarising desk artifacts without the reporting rules is the
    exact failure this package says it exists to prevent: it will round a
    degraded number, or turn an analysis into a recommendation.
    """
    class FakeModel:
        def __init__(self):
            self.messages = None

        def invoke(self, messages):
            self.messages = messages
            return SimpleNamespace(content="model wrote this")

    model = FakeModel()
    final = open_desk("SPY", store=store, model=model,
                      runners=runner_set([], write_artifact))

    assert final["summary"] == "model wrote this"
    system = model.messages[0].content
    assert REPORTING_RULES in system
    assert "Never recommend a trade" in system


# --------------------------------------------------------------------------
# Construction.
# --------------------------------------------------------------------------

def test_build_desk_graph_compiles_without_touching_the_network(
        store, write_artifact):
    """Catches construction reaching a provider or the real artifact dir.

    Building the graph must be free; if it is not, importing a module that
    builds one at load time makes a network call nobody asked for.
    """
    graph = build_desk_graph(store=store,
                             runners=runner_set([], write_artifact))

    assert hasattr(graph, "invoke")


def test_the_default_budget_is_at_least_the_pipeline_length():
    """Catches a default that cannot finish the pipeline it ships with.

    A default budget below the number of stages means the out of the box
    run always reports exhausted, and never once completes.
    """
    assert DEFAULT_BUDGET >= len(PIPELINE)


# --------------------------------------------------------------------------
# The routing invariant that makes gather's empty guard unreachable.
#
# gather opens with `if not missing: return {"log": ["gather: nothing to
# do"]}`, and that line is never executed by a real run. These two tests are
# the proof, and they are what would notice if a future edge broke it. The
# guard itself stays: what protects missing[0] is the routing, not anything
# local to gather, so removing it would turn a routing mistake into an
# IndexError inside a loop.
# --------------------------------------------------------------------------

def test_gather_is_only_ever_entered_on_the_continue_branch(store,
                                                            write_artifact):
    """Catches an edge into gather that does not go through decide.

    This is half the proof that gather's empty guard is unreachable. decide
    returns continue only when missing is non-empty, so as long as every
    edge into gather carries the continue label, gather cannot be entered
    with nothing to do. An edge added straight from plan or report would
    break that, and the next line after the guard is missing[0].
    """
    graph = build_desk_graph(store=store,
                             runners=runner_set([], write_artifact))

    into_gather = [edge for edge in graph.get_graph().edges
                   if edge.target == "gather"]

    assert len(into_gather) == 2
    assert {edge.source for edge in into_gather} == {"plan", "gather"}
    assert all(edge.conditional for edge in into_gather)
    assert {edge.data for edge in into_gather} == {"continue"}


@pytest.mark.parametrize("label, budget, runners_for", [
    ("a clean full run", DEFAULT_BUDGET, lambda w: runner_set([], w)),
    ("a budget that runs out", 2, lambda w: runner_set([], w)),
    ("no budget at all", 0, lambda w: runner_set([], w)),
    ("a raising runner", DEFAULT_BUDGET,
     lambda w: runner_set([], w, chain=_raiser)),
    ("a runner that writes nothing", DEFAULT_BUDGET,
     lambda w: runner_set([], w, greeks=lambda state: {})),
    ("a stage with no runner", DEFAULT_BUDGET,
     lambda w: {step: recorder([], step, w) for step in PIPELINE[:2]}),
])
def test_no_run_of_any_shape_reaches_the_nothing_to_do_guard(
        store, write_artifact, label, budget, runners_for):
    """Catches the empty guard becoming reachable, in either direction.

    This is the other half of the proof, taken from behaviour rather than
    structure: every exit the graph has, driven through gather, and the
    guard fires in none of them. If it ever does fire, either decide has
    stopped gating on missing or gather has stopped clearing it, and both
    are bugs in the loop rather than in this line.
    """
    final = open_desk("SPY", budget=budget, store=store,
                      runners=runners_for(write_artifact))

    assert "gather: nothing to do" not in final["log"]
    assert final["outcome"] in ("complete", "exhausted", "failed")


def test_a_desk_that_is_already_complete_never_enters_gather(store,
                                                             write_artifact):
    """Catches plan reaching gather without passing through decide.

    This is the one starting state where the empty guard could fire: every
    stage already has an artifact, so plan computes an empty missing list
    on the first pass. It is the case an unconditional plan to gather edge
    would break, and the case the other runs here cannot reach because they
    all start from an empty directory.
    """
    for step in PIPELINE:
        write_artifact(step, underlying="SPY")

    calls = []
    final = open_desk("SPY", store=store,
                      runners=runner_set(calls, write_artifact))

    assert final["outcome"] == "complete"
    assert calls == []
    assert not [line for line in final["log"] if line.startswith("gather:")]


def test_every_gather_visit_sees_at_least_one_missing_stage(store,
                                                            write_artifact):
    """Catches gather being handed an already complete missing list.

    The runner is called only after the guard has passed, so recording the
    state each runner sees samples exactly the visits that got through it.
    Every one of them must have had work to do.
    """
    seen = []

    def watcher(step):
        def run(state):
            seen.append(list(state.get("missing") or []))
            write_artifact(step, underlying=state["underlying"],
                           expiry=state.get("expiry"))
            return {}
        return run

    final = open_desk("SPY", store=store,
                      runners={step: watcher(step) for step in PIPELINE})

    assert final["outcome"] == "complete"
    assert len(seen) == len(PIPELINE)
    assert all(missing for missing in seen)
