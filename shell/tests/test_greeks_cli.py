"""The vertical slice: snapshot in, validated ladder artifact out."""

import pytest

from optiondesk import engine_bridge
from optiondesk.artifacts import read_json, write_json
from optiondesk.cli import greeks as greeks_cmd

pytestmark = pytest.mark.skipif(
    not engine_bridge.AVAILABLE,
    reason="analytics engine not installed; ladder cannot be computed")


def test_ladder_from_snapshot(tmp_path, snapshot, args_factory):
    write_json(snapshot, "chain_TEST_2026-09-18.json", tmp_path)
    result = greeks_cmd.run(args_factory(
        snapshot=None, band=0.10, type="both", out_dir=str(tmp_path)))

    # Band 0.10 around spot 100 keeps 90 to 105 and drops 150. The 110
    # strike has no implied volatility and is skipped for that reason.
    assert result["rows"] == 8
    assert result["skipped"]["out_of_band"] == 2
    assert result["skipped"]["no_iv"] == 2
    # Skipping contracts that carry no implied volatility is correct
    # behaviour, so the run is not degraded. It is recorded as a note, and
    # the count stands on its own in skipped.
    assert result["degraded"] is False
    assert result["degraded_reason"] is None
    assert any("no implied volatility" in note for note in result["notes"])
    assert any("outside the 0.1 band" in note for note in result["notes"])

    payload = read_json(result["artifact"])
    assert payload["meta"]["schema"] == "optiondesk/greeks_ladder/v1"
    assert payload["units"]["vega"].startswith("dV/dsigma")
    assert len(payload["rows"]) == 8
    for row in payload["rows"]:
        assert row["iv"] > 0
        assert set(("delta", "gamma", "vega", "theta", "vanna", "charm",
                    "speed", "ultima")) <= set(row)


def test_call_delta_positive_put_delta_negative(tmp_path, snapshot,
                                                args_factory):
    write_json(snapshot, "chain_TEST_2026-09-18.json", tmp_path)
    result = greeks_cmd.run(args_factory(
        snapshot=None, band=0.10, type="both", out_dir=str(tmp_path)))
    rows = read_json(result["artifact"])["rows"]
    assert all(r["delta"] > 0 for r in rows if r["type"] == "call")
    assert all(r["delta"] < 0 for r in rows if r["type"] == "put")
    # Long options decay, so theta per day is negative on both sides.
    assert all(r["theta"] < 0 for r in rows)


def test_band_zero_keeps_every_strike(tmp_path, snapshot, args_factory):
    write_json(snapshot, "chain_TEST_2026-09-18.json", tmp_path)
    result = greeks_cmd.run(args_factory(
        snapshot=None, band=0, type="call", out_dir=str(tmp_path)))
    assert result["skipped"]["out_of_band"] == 0
    assert result["rows"] == 5


def test_missing_snapshot_is_a_clear_error(tmp_path, args_factory):
    with pytest.raises(FileNotFoundError) as excinfo:
        greeks_cmd.run(args_factory(snapshot=None, band=0.10, type="both",
                                    out_dir=str(tmp_path)))
    assert "optiondesk chain" in str(excinfo.value)


def test_snapshot_degradation_is_inherited(tmp_path, snapshot, args_factory):
    # A degraded snapshot must degrade everything computed from it, because
    # a consumer reading only the ladder would otherwise never learn that
    # the inputs were suspect.
    snapshot["meta"]["degraded"] = True
    snapshot["meta"]["degraded_reason"] = "engine missing when chain was pulled"
    write_json(snapshot, "chain_TEST_2026-09-18.json", tmp_path)
    result = greeks_cmd.run(args_factory(
        snapshot=None, band=0.10, type="both", out_dir=str(tmp_path)))
    assert result["degraded"] is True
    assert "engine missing" in result["degraded_reason"]
