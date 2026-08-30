"""The artifact directory as retrievable documents.

Every test points the store at a temporary directory, so nothing here reads
the real artifact directory or depends on what a previous session left in
it.
"""

import json
import os
from pathlib import Path

import pytest

from optiondesk_agent.artifacts import KINDS, ArtifactStore, _summarise


def touch(path, when):
    """Give a file a known modification time, since ordering is by mtime."""
    os.utime(path, (when, when))


# --------------------------------------------------------------------------
# An empty store.
# --------------------------------------------------------------------------

def test_context_for_an_empty_store_says_there_is_nothing(store):
    """Catches an empty directory rendering as an empty context string.

    An empty string reads to a model as "no constraints" and invites an
    answer from memory. The absence has to be stated, not implied.
    """
    context = store.context_for("SPY")

    assert "No artifacts are on disk" in context
    assert "Nothing can be answered from data that has not been pulled." \
        in context


def test_an_absent_directory_is_empty_rather_than_an_error(tmp_path):
    """Catches a first run raising before anything has ever been written.

    The artifact directory does not exist until the first command writes to
    it, so a store built before then must read as empty, not blow up.
    """
    store = ArtifactStore(tmp_path / "never-created")

    assert store.records() == []
    assert store.documents() == []
    assert "No artifacts are on disk" in store.context_for("SPY")


def test_context_for_an_unknown_underlying_says_there_is_nothing(
        store, write_artifact):
    """Catches the underlying filter being dropped on the context path.

    Returning another symbol's artifacts for an unmatched request is worse
    than returning none: the answer is grounded in the wrong instrument.
    """
    write_artifact("chain", underlying="SPY")

    assert "No artifacts are on disk" in store.context_for("QQQ")


# --------------------------------------------------------------------------
# Filtering.
# --------------------------------------------------------------------------

def test_records_filters_by_underlying(store, write_artifact):
    """Catches the symbol filter being ignored.

    An SPY question answered partly from QQQ artifacts produces numbers
    that are individually correct and collectively meaningless.
    """
    write_artifact("chain", underlying="SPY")
    write_artifact("chain", underlying="QQQ")
    write_artifact("greeks", underlying="QQQ")

    records = store.records(underlying="SPY")

    assert len(records) == 1
    assert records[0][1]["underlying"] == "SPY"


def test_the_underlying_filter_is_case_insensitive(store, write_artifact):
    """Catches a lowercase symbol matching nothing.

    Symbols arrive from a model as often as from a person, and a model
    writes spy as readily as SPY. A case sensitive match reports an empty
    desk for a directory that is full.
    """
    write_artifact("chain", underlying="SPY")

    assert len(store.records(underlying="spy")) == 1


def test_records_filters_by_kind(store, write_artifact):
    """Catches the kinds filter being ignored, which floods the context.

    Asking for positioning and receiving the backtest as well spends the
    context window on the artifact that was not asked for.
    """
    write_artifact("chain", underlying="SPY")
    write_artifact("exposure", underlying="SPY")
    write_artifact("backtest", underlying="SPY")

    kinds = [kind for kind, _, _ in store.records(kinds=("exposure",))]

    assert kinds == ["exposure"]


def test_a_file_that_is_not_an_artifact_kind_is_ignored(store, tmp_path):
    """Catches an unrelated JSON file being summarised as an artifact.

    The kind comes from the filename prefix, so any stray JSON dropped in
    the directory would otherwise be read as desk output.
    """
    (tmp_path / "notes_SPY.json").write_text('{"underlying": "SPY"}',
                                             encoding="utf-8")

    assert store.records() == []


def test_malformed_json_is_skipped_not_raised(store, tmp_path,
                                              write_artifact):
    """Catches one truncated file taking down every read of the directory.

    A command killed mid-write leaves exactly this. The remaining artifacts
    are still good and must still be readable.
    """
    write_artifact("chain", underlying="SPY")
    (tmp_path / "greeks_SPY_na.json").write_text("{ not json",
                                                 encoding="utf-8")

    records = store.records()

    assert [kind for kind, _, _ in records] == ["chain"]


def test_a_json_document_that_is_not_an_object_is_skipped(store, tmp_path):
    """Catches a bare list or string being handed to the summariser.

    _summarise calls .get on the payload immediately, so a non-object
    payload is an AttributeError on an otherwise ordinary read.
    """
    (tmp_path / "chain_SPY.json").write_text("[1, 2, 3]", encoding="utf-8")

    assert store.records() == []


def test_records_are_newest_first(store, write_artifact):
    """Catches ordering by name, which is not ordering by time.

    context_for takes the first twelve. If the order is wrong, the twelve
    it keeps are not the twelve that describe the desk as it is now.
    """
    old = write_artifact("chain", underlying="SPY", expiry="2026-09-18")
    new = write_artifact("greeks", underlying="SPY", expiry="2026-09-18")
    touch(old, 1_000_000)
    touch(new, 2_000_000)

    assert [kind for kind, _, _ in store.records()] == ["greeks", "chain"]


def test_context_for_respects_its_limit(store, write_artifact):
    """Catches the limit being ignored and the whole directory inlined.

    The limit is what keeps a long lived artifact directory from filling a
    context window with months of superseded snapshots.
    """
    for index, kind in enumerate(KINDS):
        path = write_artifact(kind, underlying="SPY")
        touch(path, 1_000_000 + index)

    context = store.context_for("SPY", limit=2)

    assert len(context.split("\n\n")) == 2


# --------------------------------------------------------------------------
# What a summary carries.
# --------------------------------------------------------------------------

def test_a_degraded_artifact_is_flagged_before_any_number(store,
                                                          write_artifact):
    """Catches the degraded flag being placed after the figures, or lost.

    Reporting rule 1 requires the flag before any number from the artifact.
    A flag that appears three lines below the spot price has already been
    read past by the time it matters.
    """
    write_artifact("chain", underlying="SPY", degraded=True,
                   degraded_reason="provider fell back to delayed quotes",
                   spot=512.4, counts={"with_iv": 40, "without_iv": 3})

    lines = store.context_for("SPY").splitlines()
    flagged = [i for i, line in enumerate(lines) if line.startswith("DEGRADED")]
    numbers = [i for i, line in enumerate(lines) if "spot 512.4" in line]

    assert flagged and numbers
    assert flagged[0] < numbers[0]
    assert "provider fell back to delayed quotes" in lines[flagged[0]]


def test_a_healthy_artifact_carries_no_degraded_line(store, write_artifact):
    """Catches every artifact being flagged, which makes the flag useless.

    A warning that fires on clean data is one a reader learns to skip, and
    then misses the one that mattered.
    """
    write_artifact("chain", underlying="SPY")

    assert "DEGRADED" not in store.context_for("SPY")


def test_a_summary_names_the_path_to_the_full_artifact(store,
                                                       write_artifact):
    """Catches the summary becoming a dead end.

    The summary is deliberately lossy. Without the path, the detail it
    dropped is unreachable and the reader has to guess instead.
    """
    path = write_artifact("chain", underlying="SPY")

    assert "full artifact: {}".format(path) in store.context_for("SPY")


def test_skipped_contracts_are_counted_in_the_summary(store, write_artifact):
    """Catches contracts with no volatility vanishing from the summary.

    Reporting rule 2 turns on that count. If the summary does not carry it,
    a partially graded chain reads exactly like a fully graded one.
    """
    write_artifact("chain", underlying="SPY", spot=512.4,
                   contracts=[{}, {}, {}],
                   counts={"with_iv": 2, "without_iv": 1})

    context = store.context_for("SPY")

    assert "3 contracts, 2 with a usable implied volatility, 1 without" \
        in context


def test_the_positioning_assumption_travels_with_its_numbers(store,
                                                             write_artifact):
    """Catches walls and flip levels being summarised without the caveat.

    Reporting rule 5 requires the assumption whenever a wall is quoted, so
    dropping it from the summary makes the rule impossible to follow.
    """
    write_artifact("exposure", underlying="SPY",
                   exposure={"net_gex": 1234.0, "regime": "long gamma",
                             "assumption": "dealers are short puts",
                             "call_wall": {"strike": 520.0},
                             "put_wall": {"strike": 500.0}})

    context = store.context_for("SPY")

    assert "call wall 520.0" in context
    assert "assumption: dealers are short puts" in context


def test_documents_carry_the_degraded_flag_in_metadata(store,
                                                       write_artifact):
    """Catches a retriever that can rank artifacts but not filter bad ones.

    Metadata is the only handle a vector store has. Without the flag there,
    a degraded artifact is indistinguishable from a clean one at retrieval.
    """
    write_artifact("chain", underlying="SPY", degraded=True,
                   degraded_reason="stale quote")

    document = store.documents("SPY")[0]

    assert document.metadata["degraded"] is True
    assert document.metadata["kind"] == "chain"
    assert document.metadata["underlying"] == "SPY"
    assert document.page_content.startswith("chain for SPY")


def test_summarise_survives_a_payload_with_almost_nothing_in_it():
    """Catches the summariser assuming keys a partial artifact may lack.

    A degraded or interrupted command can write an envelope with very
    little under it, and the summariser is the first thing to read it.
    """
    text = _summarise("chain", {"meta": {}}, "/tmp/chain_x.json")

    assert "chain for unknown" in text
    assert "full artifact: /tmp/chain_x.json" in text


def write_raw(directory, name, payload):
    """Write an artifact the fixture cannot express, such as a null meta."""
    path = directory / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# Notes.
# --------------------------------------------------------------------------

def test_meta_notes_are_carried_into_the_summary(store, tmp_path):
    """Catches the notes block being dropped from the document.

    Notes are where a command records what it did that was not a defect,
    such as how many contracts fell outside the requested band. Dropping
    them lets a filtered ladder read as the whole chain.
    """
    write_raw(tmp_path, "chain_SPY_na.json", {
        "underlying": "SPY",
        "meta": {"generated_utc": "2026-08-30T12:00:00+00:00",
                 "degraded": False,
                 "notes": ["12 contracts outside the 0.06 band around spot"]}})

    context = store.context_for("SPY")

    assert "note: 12 contracts outside the 0.06 band around spot" in context


def test_only_the_first_three_notes_are_quoted(store, tmp_path):
    """Catches an unbounded note list crowding out the other artifacts.

    context_for inlines up to twelve artifacts. A command that recorded
    forty notes would otherwise spend the whole context on one of them.
    """
    write_raw(tmp_path, "chain_SPY_na.json", {
        "underlying": "SPY",
        "meta": {"generated_utc": "2026-08-30T12:00:00+00:00",
                 "degraded": False,
                 "notes": ["note number {}".format(i) for i in range(10)]}})

    context = store.context_for("SPY")

    assert len([ln for ln in context.splitlines()
                if ln.startswith("note: ")]) == 3
    assert "note number 2" in context
    assert "note number 3" not in context


# --------------------------------------------------------------------------
# The per kind detail blocks.
# --------------------------------------------------------------------------

def test_the_greeks_summary_quotes_the_contract_nearest_the_spot(
        store, write_artifact):
    """Catches the at the money row being picked by position, not by strike.

    The ladder is not in strike order once puts and calls are interleaved,
    so taking the first row, or the middle one, quotes an arbitrary
    contract while calling it at the money.
    """
    write_artifact("greeks", underlying="SPY", spot=505.0,
                   skipped={"no_iv": 4},
                   rows=[{"strike": 480.0, "type": "call", "iv": 0.9,
                          "delta": 0.9, "gamma": 0.9, "vega": 0.9,
                          "theta": -0.9},
                         {"strike": 500.0, "type": "call", "iv": 0.2,
                          "delta": 0.55, "gamma": 0.01, "vega": 0.3,
                          "theta": -0.05},
                         {"strike": 520.0, "type": "put", "iv": 0.8,
                          "delta": 0.8, "gamma": 0.8, "vega": 0.8,
                          "theta": -0.8}])

    context = store.context_for("SPY")

    assert "3 contracts graded, 4 skipped for having no implied volatility." \
        in context
    assert ("at the money call strike 500.0: iv 20.00%, delta 0.5500, "
            "gamma 0.01000, vega 0.30, theta -0.050 per day.") in context


def test_a_greeks_ladder_with_no_rows_quotes_no_contract(store,
                                                         write_artifact):
    """Catches an empty ladder being described by a fabricated row.

    Every contract can be skipped for having no usable volatility. The
    count line still has to render, and nothing may be named at the money
    when nothing was graded.
    """
    write_artifact("greeks", underlying="SPY", spot=505.0,
                   skipped={"no_iv": 12}, rows=[])

    context = store.context_for("SPY")

    assert "0 contracts graded, 12 skipped" in context
    assert "at the money" not in context


def test_the_strategy_summary_carries_the_structure_and_its_bounds(
        store, write_artifact):
    """Catches max loss being dropped from a structure's summary.

    A defined risk structure summarised without its maximum loss reads as
    an open ended one, which is the most expensive thing to get wrong
    about an option position.
    """
    write_artifact("strategy", underlying="SPY", strategy="iron_condor",
                   analysis={"trade_type": "credit", "net_cash": 1.85,
                             "breakevens": [498.15, 521.85],
                             "max_gain": 185.0, "max_loss": -315.0},
                   probability={"profit": 0.62},
                   friction={"verdict": "wide",
                             "reason": "the short leg spread is 14% of mid"})

    context = store.context_for("SPY")

    assert ("iron_condor credit: net 1.85, breakevens [498.15, 521.85], "
            "max gain 185.0, max loss -315.0.") in context
    assert "model probability of profit 62.0%." in context
    assert "friction wide: the short leg spread is 14% of mid" in context


def test_a_strategy_with_no_probability_or_friction_omits_both_lines(
        store, write_artifact):
    """Catches an absent model probability rendering as a real one.

    A structure the model could not price a probability for must show no
    probability line at all. A bare 0.0%, or an "n/a" next to a percent
    sign, both read as a computed answer.
    """
    write_artifact("strategy", underlying="SPY", strategy="covered_call",
                   analysis={"trade_type": "credit", "net_cash": 2.1,
                             "breakevens": [], "max_gain": 210.0,
                             "max_loss": None})

    context = store.context_for("SPY")

    assert "covered_call credit: net 2.1" in context
    assert "probability of profit" not in context
    assert "friction" not in context


def test_the_simulation_summary_lists_each_structure(store, write_artifact):
    """Catches the per structure rows being dropped from a simulation.

    The point of the simulation artifact is the gap between the
    probability under realised volatility and the one under implied. A
    summary carrying only the headline risk numbers loses the comparison
    the artifact exists to make.
    """
    write_artifact("simulation", underlying="SPY",
                   simulation={"horizon_days": 5, "paths": 20000},
                   posterior={"converged": True},
                   risk={"var_95": -0.031, "es_95": -0.047},
                   structures=[
                       {"strategy": "iron_condor",
                        "realised_vol_probability_of_profit": 0.71,
                        "implied_vol_probability_of_profit": 0.64},
                       {"strategy": "straddle",
                        "realised_vol_probability_of_profit": 0.38,
                        "implied_vol_probability_of_profit": 0.45}])

    context = store.context_for("SPY")

    assert ("horizon 5 days, 20000 paths, converged True. value at risk 95 "
            "-3.10%, expected shortfall 95 -4.70%.") in context
    assert ("iron_condor: probability of profit 71.0% under realised "
            "volatility against 64.0% under implied.") in context
    assert "straddle: probability of profit 38.0%" in context


def test_only_the_first_five_simulated_structures_are_quoted(store,
                                                             write_artifact):
    """Catches a whole playbook of structures being inlined per artifact.

    simulate can carry every structure it could build. Twelve of them,
    times twelve artifacts, is the context window.
    """
    write_artifact("simulation", underlying="SPY",
                   simulation={"horizon_days": 5, "paths": 100},
                   structures=[{"strategy": "s{}".format(index),
                                "realised_vol_probability_of_profit": 0.5,
                                "implied_vol_probability_of_profit": 0.5}
                               for index in range(9)])

    context = store.context_for("SPY")

    assert len([ln for ln in context.splitlines()
                if "probability of profit" in ln]) == 5
    assert "s4: probability of profit" in context
    assert "s5: probability of profit" not in context


# --------------------------------------------------------------------------
# The flag precedes the numbers, for every kind of artifact.
# --------------------------------------------------------------------------

# One artifact per kind, each carrying a figure a reader would quote, and
# the fragment of the summary that quotes it.
FIGURES = [
    ("chain", {"spot": 512.4, "contracts": [{}, {}],
               "counts": {"with_iv": 2, "without_iv": 0}}, "spot 512.4"),
    ("greeks", {"spot": 505.0, "skipped": {"no_iv": 1},
                "rows": [{"strike": 500.0, "type": "call", "iv": 0.2,
                          "delta": 0.5, "gamma": 0.01, "vega": 0.3,
                          "theta": -0.05}]}, "at the money call strike"),
    ("exposure", {"exposure": {"net_gex": 1234.0, "regime": "long gamma",
                               "assumption": "dealers are short puts"}},
     "net gamma exposure 1234"),
    ("strategy", {"strategy": "iron_condor",
                  "analysis": {"trade_type": "credit", "net_cash": 1.85,
                               "breakevens": [], "max_gain": 185.0,
                               "max_loss": -315.0}}, "max loss -315.0"),
    ("comparison", {"rankable_count": 6, "excluded_count": 2,
                    "leader": {"strategy": "iron_condor",
                               "expected_return_on_risk": 0.12}},
     "6 structures ranked"),
    ("simulation", {"simulation": {"horizon_days": 5, "paths": 20000},
                    "posterior": {"converged": True}},
     "horizon 5 days, 20000 paths"),
    ("backtest", {"strategy": "iron_condor",
                  "statistics": {"trades": 41, "win_rate": 0.66,
                                 "mean_return": 0.031}},
     "over 41 trades"),
]


@pytest.mark.parametrize("kind, extra, figure",
                         FIGURES, ids=[row[0] for row in FIGURES])
def test_degradation_precedes_every_number_for_every_kind(
        store, write_artifact, kind, extra, figure):
    """Catches a kind whose detail block is emitted above the degraded flag.

    Reporting rule 1 is the rule the whole project rests on: the flag comes
    before any number taken from the artifact. It was only ever proved on
    the chain summary, and each kind builds its own detail block, so a new
    kind that appended its figures first would break the rule for that kind
    alone and no test would notice.
    """
    write_artifact(kind, underlying="SPY", degraded=True,
                   degraded_reason="provider fell back to delayed quotes",
                   **extra)

    lines = store.context_for("SPY").splitlines()

    assert lines[1].startswith("DEGRADED: provider fell back to delayed")
    quoted = [i for i, line in enumerate(lines) if figure in line]
    assert quoted, "no line quoted {}: {}".format(figure, lines)
    assert min(quoted) > 1


# --------------------------------------------------------------------------
# An artifact that does not match the current schema.
# --------------------------------------------------------------------------

# Nothing validates an artifact on the way in: records() accepts any JSON
# object whose filename prefix is a known kind. Each of these reached the
# summariser and raised, and because context_for summarises the directory
# in one pass, each one cost the caller every other artifact as well.
MALFORMED = [
    ("greeks ladder with no spot",
     "greeks", {"rows": [{"strike": 500.0, "type": "call"}]}),
    ("greeks row with no strike",
     "greeks", {"spot": 500.0, "rows": [{"type": "call"}]}),
    ("greeks row with no type",
     "greeks", {"spot": 500.0, "rows": [{"strike": 500.0}]}),
    ("greeks row with a null delta",
     "greeks", {"spot": 500.0, "rows": [{"strike": 500.0, "type": "call",
                                         "delta": None}]}),
    ("chain with a null counts block", "chain", {"counts": None}),
    ("chain with a null contract list", "chain", {"contracts": None}),
    ("exposure with a null exposure block", "exposure", {"exposure": None}),
    ("exposure with a null net gamma",
     "exposure", {"exposure": {"net_gex": None}}),
    ("strategy with a null analysis block", "strategy", {"analysis": None}),
    ("simulation with a null posterior", "simulation", {"posterior": None}),
    ("simulation with a null simulation block",
     "simulation", {"simulation": None}),
]


@pytest.mark.parametrize("label, kind, extra",
                         MALFORMED, ids=[row[0] for row in MALFORMED])
def test_an_artifact_that_does_not_match_the_schema_still_summarises(
        store, write_artifact, label, kind, extra):
    """Catches one stale artifact emptying the context for every underlying.

    The store validates nothing on read, so a file from an older schema, or
    one an interrupted command left half populated, arrives here intact.
    Raising costs the caller the whole directory, and the caller is a model
    that will then answer from memory because it was handed nothing.
    """
    write_artifact(kind, underlying="SPY", **extra)

    text = store.context_for("SPY")

    assert "{} for SPY".format(kind) in text
    assert "detail unavailable" in text
    assert "no number is quoted from it" in text


def test_a_null_skipped_block_still_reports_the_graded_count(store,
                                                             write_artifact):
    """Catches the skipped counts being read without allowing for a null.

    This one is handled where it happens rather than by the fallback, so
    the summary keeps its count line. A test asserting only that it does
    not raise would pass just as well against the fallback, and would not
    notice the count going missing.
    """
    write_artifact("greeks", underlying="SPY", spot=500.0, skipped=None,
                   rows=[])

    text = store.context_for("SPY")

    assert "0 contracts graded, None skipped" in text
    assert "detail unavailable" not in text


def test_a_bad_artifact_does_not_take_down_the_good_ones(store,
                                                         write_artifact):
    """Catches the failure being contained per directory instead of per file.

    The other artifacts in the directory are still exactly as good as they
    were. Losing them because a neighbouring file is stale is the failure
    this containment exists to prevent.
    """
    write_artifact("greeks", underlying="SPY", rows=[{"type": "call"}])
    write_artifact("chain", underlying="SPY", spot=512.4,
                   contracts=[{}], counts={"with_iv": 1, "without_iv": 0})

    text = store.context_for("SPY")

    assert "detail unavailable" in text
    assert "spot 512.4" in text
    assert len(store.documents("SPY")) == 2


def test_a_malformed_artifact_keeps_its_degraded_flag(store, write_artifact):
    """Catches the degraded flag being lost with the numbers it qualifies.

    The flag is built before the detail block and must survive the detail
    block failing. An artifact reported as merely unreadable, when it is
    both unreadable and degraded, understates what is wrong with it.
    """
    write_artifact("greeks", underlying="SPY", degraded=True,
                   degraded_reason="stale underlying quote",
                   rows=[{"type": "call"}])

    lines = store.context_for("SPY").splitlines()

    assert lines[1] == "DEGRADED: stale underlying quote"
    assert any("detail unavailable" in line for line in lines)


def test_an_artifact_with_no_degraded_key_is_read_as_clean(store, tmp_path):
    """Catches an absent flag being reported as anything but clean.

    Every envelope schema makes meta.degraded required, so an artifact
    without it is not one the current shell wrote. Both reads of the flag
    use .get, so it renders clean rather than raising. That default is
    worth having written down, because it is the assumption the whole
    reporting rule rests on: absence reads as not degraded, and the only
    thing keeping that honest is the command that writes the envelope.
    """
    write_raw(tmp_path, "chain_SPY_na.json", {
        "underlying": "SPY", "spot": 512.4,
        "meta": {"generated_utc": "2026-08-30T12:00:00+00:00"}})

    document = store.documents("SPY")[0]

    assert document.metadata["degraded"] is False
    assert "DEGRADED" not in document.page_content


@pytest.mark.parametrize("meta", [None, "oops", ["a"], 7, True],
                         ids=["null", "string", "list", "number", "bool"])
def test_an_envelope_that_is_not_an_object_is_treated_as_empty(store,
                                                               tmp_path,
                                                               meta):
    """Catches the envelope read failing before the degraded flag is built.

    The envelope is read first and on every path, so it is the one part
    that cannot raise. Everything after it is contained by the fallback,
    but a failure here happens above the containment and takes the whole
    directory with it, exactly as a null meta did.
    """
    write_raw(tmp_path, "chain_SPY_na.json",
              {"underlying": "SPY", "spot": 512.4, "meta": meta})

    document = store.documents("SPY")[0]

    assert document.metadata["degraded"] is False
    assert document.metadata["generated_utc"] is None
    assert document.page_content.startswith("chain for SPY")
    assert "spot 512.4" in document.page_content


def test_a_null_meta_block_does_not_break_the_document(store, tmp_path):
    """Catches meta present but null, where the default never fires.

    payload.get("meta", {}) returns the null rather than the default, so
    every read of the envelope raises. The document metadata is built from
    the same block, so a retriever loses the artifact too, not just the
    summary.
    """
    write_raw(tmp_path, "chain_SPY_na.json",
              {"underlying": "SPY", "meta": None})

    document = store.documents("SPY")[0]

    assert document.metadata["degraded"] is False
    assert document.metadata["generated_utc"] is None
    assert document.page_content.startswith("chain for SPY")


# --------------------------------------------------------------------------
# Where the store reads when nobody says.
# --------------------------------------------------------------------------

def test_a_store_with_no_directory_reads_the_desk_artifact_directory(
        monkeypatch, tmp_path):
    """Catches the default store pointing somewhere the desk never writes.

    The no argument constructor is what an application uses. If it resolved
    to the process working directory, every question would be answered
    against an empty desk while the artifacts sat where the CLI put them.
    """
    import optiondesk.artifacts as shell_artifacts

    target = tmp_path / "desk-artifacts"
    monkeypatch.setattr(shell_artifacts, "artifact_dir", lambda: target)

    assert ArtifactStore().directory == target


def test_a_file_that_vanishes_mid_read_does_not_kill_the_whole_read(
        tmp_path, monkeypatch):
    """The artifact directory is written to while this reads it.

    records() stats every file to sort by age. A command writing a new
    artifact, or a refresh replacing one, can remove a path between the
    glob and the stat, and that used to raise FileNotFoundError out of
    records: one vanished file cost the caller every artifact for every
    underlying, and the model was then handed nothing.
    """
    from optiondesk_agent.artifacts import ArtifactStore

    good = tmp_path / "chain_TEST_2026-09-18.json"
    good.write_text('{"underlying": "TEST", "meta": {}}', encoding="utf-8")
    ghost = tmp_path / "chain_GONE_2026-09-18.json"
    ghost.write_text('{"underlying": "GONE", "meta": {}}', encoding="utf-8")

    store = ArtifactStore(tmp_path)

    real_stat = Path.stat

    def vanishing(self, *args, **kwargs):
        # Delete it for real before raising, so this is the actual race
        # rather than a stat that lies about a file still on disk.
        # os.path, not Path.exists: the latter calls stat and this IS stat.
        if self.name == ghost.name and os.path.exists(ghost):
            os.unlink(ghost)
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", vanishing)
    records = store.records()

    assert [r[1]["underlying"] for r in records] == ["TEST"], (
        "a file that disappeared mid-read should be dropped, not raise")
