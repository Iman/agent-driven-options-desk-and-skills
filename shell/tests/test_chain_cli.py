"""optiondesk chain: retrieval, the volatility solve, and what degrades.

No network: the provider is a stub registered through providers.register and
the registry is restored by the provider_registry fixture in conftest.
"""

import json

import pytest

from optiondesk import engine_bridge
from optiondesk.artifacts import read_json
from optiondesk.cli import chain as chain_cmd
from optiondesk.contracts import CHAIN_SNAPSHOT, SCHEMA_FILES, validate
from optiondesk.providers.base import ProviderDataError

from marks import needs_engine

WIDE = tuple(float(s) for s in range(75, 130, 5))  # 11 strikes, 22 contracts


def chain_args(args_factory, tmp_path, **overrides):
    kwargs = {"symbol": "TEST", "expiry": None, "provider": None,
              "rate": None, "dividend_yield": 0.0, "out_dir": str(tmp_path)}
    kwargs.update(overrides)
    return args_factory(**kwargs)


@needs_engine
def test_snapshot_is_written_and_validates(stub_provider, provider_chain,
                                           args_factory, tmp_path):
    """Catches a run that stops validating, or writes the wrong schema id.

    The artifact is the interface every other consumer reads, so a payload
    that no longer satisfies chain_snapshot/v1 has broken all of them.
    """
    stub_provider(chain=provider_chain())
    result = chain_cmd.run(chain_args(args_factory, tmp_path))

    payload = read_json(result["artifact"])
    assert payload["meta"]["schema"] == CHAIN_SNAPSHOT
    assert validate(payload, SCHEMA_FILES[CHAIN_SNAPSHOT]) is payload
    assert payload["underlying"] == "TEST"
    assert payload["counts"]["calls"] == 9
    assert payload["counts"]["puts"] == 9
    assert result["provider_used"] == "stub"


@needs_engine
def test_volatility_is_solved_from_the_mid_not_taken_from_the_provider(
        stub_provider, provider_chain, args_factory, tmp_path):
    """Catches the solve being dropped in favour of the published figure.

    A solved volatility is reproducible from the quote; the provider's is
    not, and the two are distinguished by iv_source for exactly that reason.
    """
    stub_provider(chain=provider_chain())
    result = chain_cmd.run(chain_args(args_factory, tmp_path))
    contracts = read_json(result["artifact"])["contracts"]

    assert all(c["iv_source"] == "solved_mid" for c in contracts)
    # The fixture priced every contract at a known volatility, so the solve
    # has to return that volatility back.
    for contract in contracts:
        expected = 0.30 - 0.0008 * (contract["strike"] - 100.0)
        assert contract["iv"] == pytest.approx(expected, abs=1e-4)


@needs_engine
def test_contract_with_no_usable_volatility_is_skipped_and_counted(
        stub_provider, provider_chain, args_factory, tmp_path):
    """Catches a default being substituted for a missing volatility.

    A defaulted volatility produces a complete and entirely fictional Greek
    ladder that looks exactly as authoritative as a real one. The contract
    must carry iv null, be counted in without_iv, and be reported as a note
    rather than as a degradation.
    """
    stub_provider(chain=provider_chain(no_price={(120.0, "call"),
                                                (120.0, "put")}))
    result = chain_cmd.run(chain_args(args_factory, tmp_path))
    payload = read_json(result["artifact"])

    dead = [c for c in payload["contracts"] if c["strike"] == 120.0]
    assert len(dead) == 2
    assert all(c["iv"] is None and c["iv_source"] is None for c in dead)
    assert payload["counts"]["without_iv"] == 2
    assert payload["counts"]["with_iv"] == 16
    # An ordinary chain, not a defective run.
    assert result["degraded"] is False
    assert result["degraded_reason"] is None
    assert any("no usable implied volatility" in note
               for note in result["notes"])


@needs_engine
def test_a_material_fallback_to_published_volatility_is_a_degradation(
        stub_provider, provider_chain, args_factory, tmp_path):
    """Catches the degradation branch being deleted or its test inverted.

    Five percent or more of the chain priced off the provider's own figure
    is lower quality than this pipeline can produce, which is what degraded
    means. Below that share it is a note.
    """
    unsolvable = {(80.0, "call"), (85.0, "call"), (90.0, "call")}
    stub_provider(chain=provider_chain(unsolvable=unsolvable))
    result = chain_cmd.run(chain_args(args_factory, tmp_path))

    assert result["degraded"] is True
    assert "provider's published implied volatility" in result["degraded_reason"]
    assert "3 of 18" in result["degraded_reason"]
    contracts = read_json(result["artifact"])["contracts"]
    fell_back = [c for c in contracts if c["iv_source"] == "provider"]
    assert len(fell_back) == 3
    # None of them was left without a volatility: the published one is used.
    assert all(c["iv"] is not None for c in fell_back)


@needs_engine
def test_an_immaterial_fallback_is_a_note_not_a_degradation(
        stub_provider, provider_chain, args_factory, tmp_path):
    """Catches notes and degradation being conflated.

    One contract in twenty-two is 4.5 percent, under the threshold. If this
    were filed as degraded, nearly every real artifact would be degraded and
    the flag would stop carrying information.
    """
    stub_provider(chain=provider_chain(strikes=WIDE,
                                       unsolvable={(75.0, "call")}))
    result = chain_cmd.run(chain_args(args_factory, tmp_path))

    assert result["degraded"] is False
    assert result["degraded_reason"] is None
    assert any("provider's published implied volatility" in note
               for note in result["notes"])
    assert any("1 of 22" in note for note in result["notes"])


@needs_engine
def test_an_expiry_already_past_degrades_the_snapshot(
        stub_provider, provider_chain, args_factory, tmp_path):
    """Catches the expired flag being ignored.

    Time to expiry is floored so a contract expiring today still prices. If
    the floor is applied to an expiry that has already gone, every value
    derived from it is meaningless and the artifact has to say so.
    """
    stub_provider(chain=provider_chain(expired=True))
    result = chain_cmd.run(chain_args(args_factory, tmp_path))

    assert result["degraded"] is True
    assert "already passed" in result["degraded_reason"]


@needs_engine
def test_a_mid_taken_from_the_last_trade_is_recorded(
        stub_provider, provider_chain, args_factory, tmp_path):
    """Catches the last-trade substitution becoming invisible.

    A mid that is really a stale last trade is not a mid. It is not a
    degradation, but a reader has to be able to see how much of the chain
    it covers.
    """
    chain = provider_chain()
    for contract in chain["contracts"][:4]:
        contract["mid_source"] = "last_trade"
    stub_provider(chain=chain)
    result = chain_cmd.run(chain_args(args_factory, tmp_path))

    assert result["degraded"] is False
    assert any("no two-sided quote" in note for note in result["notes"])
    assert any("4 of 18" in note for note in result["notes"])


@needs_engine
def test_a_supplied_rate_is_used_and_nothing_is_fetched(
        stub_provider, provider_chain, args_factory, tmp_path):
    """Catches the rate flag being ignored and a fetch happening anyway.

    A user who passes --rate has stated the rate. Fetching one behind their
    back would price the whole chain off a number they did not choose.
    """
    stub = stub_provider(chain=provider_chain())
    result = chain_cmd.run(chain_args(args_factory, tmp_path, rate=0.055))
    payload = read_json(result["artifact"])

    assert payload["risk_free_rate"] == 0.055
    assert payload["meta"]["inputs"]["rate_source"] == "user"
    assert "risk_free_rate" not in stub.calls


def test_a_json_snapshot_file_is_accepted_without_network_access(tmp_path,
                                                                args_factory):
    """Catches a path-only chain run requiring no provider traffic."""
    snapshot = {
        "underlying": "SPY",
        "spot": 600.0,
        "spot_asof": "2026-09-02T14:00:00Z",
        "expiry": "2026-09-18",
        "days_to_expiry": 16,
        "contracts": [
            {
                "strike": 600,
                "type": "call",
                "bid": 5.2,
                "ask": 5.6,
                "volume": 50,
                "open_interest": 200,
            },
            {
                "strike": 600,
                "type": "put",
                "bid": 4.8,
                "ask": 5.0,
                "volume": 80,
                "open_interest": 120,
            },
        ],
    }
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")

    args = args_factory(symbol="SPY", out_dir=str(tmp_path),
                        from_file=str(path), source_path=None,
                        rate=0.05, dividend_yield=0.0,
                        data_source="licensed test fixture",
                        rights_confirmed=True)
    result = chain_cmd.run(args)

    payload = read_json(result["artifact"])
    assert payload["meta"]["provider_used"] == "user snapshot"
    assert payload["risk_free_rate"] == 0.05
    assert payload["spot_asof"] == "2026-09-02T14:00:00Z"
    assert payload["counts"]["calls"] == 1
    assert payload["counts"]["puts"] == 1


def test_csv_snapshot_file_is_accepted_without_network_access(tmp_path,
                                                             args_factory):
    """Catches a CSV path reaching the same parser and writer path."""
    csv_text = "\n".join([
        "underlying,expiry,spot,strike,type,bid,ask,volume,open_interest,iv",
        "SPY,2026-09-18,600.0,590,call,4.1,4.5,20,40,0.22",
        "SPY,2026-09-18,600.0,590,put,3.2,3.4,10,30,0.27",
    ])
    path = tmp_path / "snapshot.csv"
    path.write_text(csv_text, encoding="utf-8")

    args = args_factory(symbol="SPY", out_dir=str(tmp_path),
                        from_file=str(path), source_path=None,
                        rate=0.03, dividend_yield=0.0,
                        data_source="licensed test fixture",
                        rights_confirmed=True)
    result = chain_cmd.run(args)

    payload = read_json(result["artifact"])
    assert payload["meta"]["provider_used"] == "user snapshot"
    assert payload["counts"]["calls"] == 1
    assert payload["counts"]["puts"] == 1
    assert len(payload["contracts"]) == 2
    calls = [c for c in payload["contracts"] if c["type"] == "call"]
    assert calls[0]["iv"] == 0.22
    assert payload["counts"]["without_iv"] == 0


def test_source_path_is_honoured_by_the_chain_runner(tmp_path, args_factory):
    """Catches MCP/agent field naming from `source_path` from_file mismatch."""
    snapshot = {
        "underlying": "SPY",
        "spot": 600.0,
        "expiry": "2026-09-18",
        "days_to_expiry": 16,
        "contracts": [
            {
                "strike": 600,
                "type": "call",
                "bid": 5.2,
                "ask": 5.6,
                "iv": 0.21,
            },
            {
                "strike": 600,
                "type": "put",
                "bid": 4.8,
                "ask": 5.0,
                "iv": 0.22,
            },
        ],
    }
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")

    args = args_factory(symbol="SPY", out_dir=str(tmp_path),
                        source_path=str(path), from_file=None,
                        rate=0.05, dividend_yield=0.0,
                        data_source="licensed test fixture",
                        rights_confirmed=True)
    result = chain_cmd.run(args)

    payload = read_json(result["artifact"])
    assert payload["meta"]["provider_used"] == "user snapshot"


def test_inline_json_is_normalized_and_written_for_chat(tmp_path,
                                                        args_factory):
    """A remote MCP client can send structured rows without a local path."""
    source_data = {
        "underlying": "SPY",
        "spot": "600.00",
        "snapshot_timestamp": "2026-09-02T14:00:00Z",
        "expiry": "2026-09-18",
        "contracts": [
            {"strike_price": "600", "right": "C", "bid": "5.2",
             "ask": "5.6", "implied_volatility": "22",
             "openinterest": "1,200"},
            {"strike_price": "600", "right": "P", "bid": "4.8",
             "ask": "5.0", "implied_volatility": "24",
             "openinterest": "980"},
        ],
    }
    args = args_factory(
        symbol="SPY", out_dir=str(tmp_path), source_path=None,
        from_file=None, source_data=source_data, source_text=None,
        source_format=None, data_source="user broker export",
        rights_confirmed=True, rate=0.05, dividend_yield=0.0)

    result = chain_cmd.run(args)
    payload = read_json(result["artifact"])

    assert payload["data_source"] == "user broker export"
    assert payload["data_rights"]["asserted_by_user"] is True
    assert payload["data_rights"]["public_display"] is False
    assert payload["contracts"][0]["iv"] == pytest.approx(0.22)
    assert payload["contracts"][0]["open_interest"] == 1200
    assert result["normalization"]["repair_count"] >= 4
    assert any("converted implied volatility" in repair
               for repair in result["normalization"]["repairs"])


def test_user_snapshot_requires_rights_confirmation(tmp_path, args_factory):
    args = args_factory(
        symbol="SPY", out_dir=str(tmp_path), source_path=None,
        from_file=None, source_data={"contracts": []}, source_text=None,
        source_format=None, data_source="unknown", rights_confirmed=False,
        rate=0.05, dividend_yield=0.0)

    with pytest.raises(ValueError, match="rights confirmation"):
        chain_cmd.run(args)


def test_user_snapshot_reports_all_repairable_rows(tmp_path, args_factory):
    source_data = {
        "underlying": "SPY", "spot": 600, "expiry": "2026-09-18",
        "contracts": [
            {"strike": 600, "type": "unknown"},
            {"strike": -1, "type": "put"},
        ],
    }
    args = args_factory(
        symbol="SPY", out_dir=str(tmp_path), source_path=None,
        from_file=None, source_data=source_data, source_text=None,
        source_format=None, data_source="user export", rights_confirmed=True,
        rate=0.05, dividend_yield=0.0)

    with pytest.raises(ValueError, match="row 1.*row 2"):
        chain_cmd.run(args)


@needs_engine
def test_a_degraded_rate_degrades_the_snapshot(
        stub_provider, provider_chain, args_factory, tmp_path):
    """Catches a fallback rate being used without saying so.

    Every Greek and every rho in everything computed downstream rests on
    this number, so a substituted constant is a quality warning.
    """
    stub_provider(chain=provider_chain(),
                  rate={"rate": 0.04, "source": "fallback_constant",
                        "degraded": True, "reason": "^IRX unavailable"})
    result = chain_cmd.run(chain_args(args_factory, tmp_path))

    assert result["degraded"] is True
    assert "risk-free rate" in result["degraded_reason"]
    assert "^IRX unavailable" in result["degraded_reason"]


def test_a_provider_that_raises_is_not_swallowed(stub_provider, args_factory,
                                                 tmp_path):
    """Catches a provider failure being turned into an empty artifact.

    An empty result that looks like a real one is worse than an error, so
    the failure has to reach the caller.
    """
    stub_provider(raises=ProviderDataError("TEST: no price history returned"))
    with pytest.raises(ProviderDataError) as excinfo:
        chain_cmd.run(chain_args(args_factory, tmp_path))
    assert "no price history" in str(excinfo.value)


def test_an_unknown_provider_name_is_refused(stub_provider, args_factory,
                                             tmp_path):
    """Catches a named provider being silently substituted.

    Someone who names a provider usually has a data-quality reason, so an
    unavailable one must raise rather than quietly serve another source.
    """
    from optiondesk.providers import ProviderUnavailable

    stub_provider()
    with pytest.raises(ProviderUnavailable) as excinfo:
        chain_cmd.run(chain_args(args_factory, tmp_path,
                                 provider="not_a_provider"))
    assert "no substitute was permitted" in str(excinfo.value)


# ------------------------------------------------------------- _solve_iv

@needs_engine
def test_solve_iv_prefers_the_solved_value():
    """Catches the two volatility sources being labelled the same.

    iv_source is what tells a reader whether a number can be reproduced
    from the quote or was taken on trust.
    """
    engine = engine_bridge.require()
    contract = {"strike": 100.0, "type": "call", "mid": 3.5911230320233614,
                "iv_provider": 0.99}
    iv, source = chain_cmd._solve_iv(engine, contract, 100.0, 30 / 365.0,
                                     0.04, 0.0)
    assert source == "solved_mid"
    assert iv == pytest.approx(0.30, abs=1e-6)


@needs_engine
def test_solve_iv_falls_back_to_the_published_figure():
    """Catches the fallback disappearing, which would drop usable contracts.

    A mid below intrinsic has no solution. The provider's own figure is
    still better than nothing, provided it is labelled as theirs.
    """
    engine = engine_bridge.require()
    contract = {"strike": 90.0, "type": "call", "mid": 0.01,
                "iv_provider": 0.42}
    iv, source = chain_cmd._solve_iv(engine, contract, 100.0, 30 / 365.0,
                                     0.04, 0.0)
    assert (iv, source) == (0.42, "provider")


def test_solve_iv_without_an_engine_uses_the_published_figure():
    """Catches the no-engine path crashing instead of degrading.

    The shell has to keep running without the separately licensed engine,
    writing an honest degraded artifact rather than failing.
    """
    contract = {"strike": 100.0, "type": "call", "mid": 3.6,
                "iv_provider": 0.31}
    iv, source = chain_cmd._solve_iv(None, contract, 100.0, 30 / 365.0,
                                     0.04, 0.0)
    assert (iv, source) == (0.31, "provider")


@pytest.mark.parametrize("published", [None, 0.0, 0.001, 5.0, 6.0, -0.2])
def test_solve_iv_refuses_an_out_of_range_published_figure(published):
    """Catches the sanity bounds being widened or dropped.

    A provider that publishes zero, a negative, or 500 percent volatility
    has published nothing usable. Accepting it would put a fictional number
    into the artifact under the label of a real one.
    """
    contract = {"strike": 100.0, "type": "call", "mid": None,
                "iv_provider": published}
    assert chain_cmd._solve_iv(None, contract, 100.0, 30 / 365.0, 0.04,
                               0.0) == (None, None)


@needs_engine
def test_solve_iv_does_not_solve_from_a_zero_or_missing_mid():
    """Catches a zero mid being fed to the solver as though it were a price.

    Zero is not a premium any model can invert, so the published figure is
    the only remaining source.
    """
    engine = engine_bridge.require()
    for mid in (None, 0.0):
        contract = {"strike": 100.0, "type": "call", "mid": mid,
                    "iv_provider": 0.27}
        assert chain_cmd._solve_iv(engine, contract, 100.0, 30 / 365.0,
                                   0.04, 0.0) == (0.27, "provider")
