"""Regressions for the seven defects the test-writing audit reported.

Each uses the reproduction the audit gave. They are grouped here rather
than scattered so the set can be re-run against any future change to the
same paths.
"""

import json

import pytest

from optiondesk.cli import compare as compare_cmd
from optiondesk.cli import expiries as expiries_cmd
from optiondesk.cli import simulate as simulate_cmd
from optiondesk.dashboard import data as dashboard_data
from optiondesk.dashboard import page as dashboard_page


def test_the_empty_dashboard_page_keeps_its_own_body():
    """The body was built and then dropped by the return statement.

    The first page a new user sees rendered blank between the wrapper and
    the footer: no heading, no instructions, no artifact directory.
    """
    payload = {"artifact_dir": "/tmp/nowhere", "ladder": None,
               "exposure": None, "comparison": None, "plans": [],
               "groups": [], "selected": None, "simulation": None,
               "backtests": [], "series": {"calls": [], "puts": []},
               "disclaimer": "not investment advice"}
    html = dashboard_page.render(payload)
    assert "Nothing to show yet" in html
    assert "optiondesk chain SPY" in html
    assert "/tmp/nowhere" in html
    assert "not investment advice" in html


def test_max_rhat_survives_chains_too_short_to_split():
    """Every R-hat is None then, and max() raised after the artifact was
    already on disk, so the command failed while leaving a complete file
    for the dashboard to read."""
    assert simulate_cmd._max_rhat({"mu": None, "omega": None}) is None
    assert simulate_cmd._max_rhat({"mu": 1.01, "omega": None}) == 1.01


@pytest.mark.parametrize("content", ["[]", '"a string"', "42", "null"])
def test_valid_json_of_the_wrong_shape_is_skipped(tmp_path, content):
    """A JSON array in the artifact directory reached .get() and raised.

    The existing guard caught unreadable files, so the failure only
    appeared for a file that parsed perfectly well.
    """
    (tmp_path / "chain_X_2026-09-18.json").write_text(content,
                                                      encoding="utf-8")
    assert dashboard_data.index(tmp_path) == []

    class Args:
        symbol = None
        provider = None
        out_dir = str(tmp_path)

    result = expiries_cmd.run(Args())
    assert result["on_disk"] == []


def test_a_builder_that_raises_does_not_abort_the_comparison(
        tmp_path, snapshot, monkeypatch):
    """One structure that cannot be priced took the other nine with it.

    This drives compare.run itself rather than re-implementing its loop,
    because a test that reimplements the code under test proves only that
    the test author can write the same lines twice.
    """
    from optiondesk.artifacts import write_json

    path = write_json(snapshot, "chain_TEST_2026-09-18.json", tmp_path)

    real_run = compare_cmd.strategy_cmd.run

    def explode_on_one(args):
        if args.name == "iron_condor":
            raise ValueError("no priced contracts to choose from")
        return real_run(args)

    monkeypatch.setattr(compare_cmd.strategy_cmd, "run", explode_on_one)

    class Args:
        snapshot = str(path)
        size = 1.0
        include_underlying = False
        rebuild = True
        out_dir = str(tmp_path)

    result = compare_cmd.run(Args())
    # The comparison completed, and the exploding structure is catalogued
    # rather than having taken everything with it.
    assert result["compared"] > 0
    assert any(entry["strategy"] == "iron_condor"
               and "ValueError" in entry["reason"]
               for entry in result["not_compared"])


def test_rebuild_reuses_existing_plans_unless_asked(tmp_path, snapshot,
                                                    monkeypatch):
    """The flag was declared and never read, so every run rebuilt all.

    Counting builder calls is the only way to see the difference from the
    outside: both runs return the same plans either way.
    """
    from optiondesk.artifacts import write_json

    path = write_json(snapshot, "chain_TEST_2026-09-18.json", tmp_path)
    real_run = compare_cmd.strategy_cmd.run
    calls = {"n": 0}

    def counted(args):
        calls["n"] += 1
        return real_run(args)

    monkeypatch.setattr(compare_cmd.strategy_cmd, "run", counted)

    class Args:
        snapshot = str(path)
        size = 1.0
        include_underlying = False
        rebuild = True
        out_dir = str(tmp_path)

    first = compare_cmd.run(Args())
    built_first = calls["n"]
    assert built_first > 0
    assert first["reused_existing_plans"] == 0

    calls["n"] = 0
    Args.rebuild = False
    second = compare_cmd.run(Args())
    assert second["reused_existing_plans"] > 0
    assert calls["n"] < built_first

    calls["n"] = 0
    Args.rebuild = True
    compare_cmd.run(Args())
    assert calls["n"] == built_first


def test_net_greeks_are_none_when_nothing_could_be_priced():
    """Zeros were indistinguishable from a genuinely hedged position."""
    class FakeLeg:
        def __init__(self, kind, iv):
            self.kind = kind
            self.side = 1
            self.qty = 1.0
            self.strike = 100.0
            self.ref = {"iv": iv}

    engine = {"all_greeks": lambda *a, **k: {}}
    net = simulate_helper = simulate_cmd  # keep the import used
    from optiondesk.cli import strategy as strategy_cmd

    result = strategy_cmd._net_greeks(engine, [FakeLeg("call", None)],
                                      100.0, 30.0, 0.04, 0.0)
    assert result["legs_priced"] == 0
    assert result["legs_skipped_without_iv"] == 1
    assert result["complete"] is False
    assert result["delta"] is None and result["vega"] is None


def test_history_counts_the_gaps_it_splices():
    """The docstring said a bad close ends the series; the code splices.

    A splice joins two prices that were never adjacent, which understates
    volatility across the gap, so the count must be visible rather than
    the behaviour being misdescribed. This drives the real method through
    a fake client instead of asserting on prose.
    """
    from optiondesk.providers.yahoo import YahooProvider

    class FakeIndex:
        def __init__(self, value):
            self.value = value

        def date(self):
            return self.value

    class FakeSeries:
        def __init__(self, values):
            self.values = values
            self.index = [FakeIndex("2026-01-{:02d}".format(i % 28 + 1))
                          for i in range(len(values))]

        def dropna(self):
            return self

        def tolist(self):
            return self.values

        def __len__(self):
            return len(self.values)

    class FakeFrame:
        def __init__(self, closes):
            self.empty = False
            self._closes = FakeSeries(closes)

        def __getitem__(self, key):
            return self._closes

    closes = [100.0 + i for i in range(60)]
    closes[30] = 0.0            # one bad print in the middle
    closes[31] = -5.0           # and one impossible one

    class FakeTicker:
        def history(self, period=None, auto_adjust=None):
            return FakeFrame(closes)

    class FakeClient:
        def Ticker(self, symbol):
            return FakeTicker()

    provider = YahooProvider()
    provider._yf = FakeClient()
    history = provider.underlying_history("TEST")

    # Three pairs touch a bad close: 29-30, 30-31 and 31-32.
    assert history["spliced_gaps"] == 3
    assert len(history["returns"]) == len(closes) - 1 - 3
    assert all(abs(r) < 1.0 for r in history["returns"])
