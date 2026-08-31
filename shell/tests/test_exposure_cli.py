"""optiondesk exposure: positioning across the whole chain."""

import pytest

from optiondesk.artifacts import read_json, write_json
from optiondesk.cli import exposure as exposure_cmd
from optiondesk.contracts import EXPOSURE, SCHEMA_FILES, validate

from marks import needs_engine

pytestmark = needs_engine


def exposure_args(args_factory, tmp_path, **overrides):
    kwargs = {"snapshot": None, "multiplier": 100.0,
              "out_dir": str(tmp_path)}
    kwargs.update(overrides)
    return args_factory(**kwargs)


def put_snapshot(chain_snapshot, tmp_path, **overrides):
    snapshot = chain_snapshot(**overrides)
    write_json(snapshot, "chain_{}_{}.json".format(
        snapshot["underlying"], snapshot["expiry"]), tmp_path)
    return snapshot


def test_exposure_artifact_validates_and_states_its_assumption(
        chain_snapshot, args_factory, tmp_path):
    """Catches the sign convention being dropped from the artifact.

    Every wall and every regime label rests on assuming dealers are long
    calls and short puts. That convention is often wrong for a single name,
    so a reader who cannot see it cannot judge the numbers.
    """
    put_snapshot(chain_snapshot, tmp_path)
    result = exposure_cmd.run(exposure_args(args_factory, tmp_path))

    payload = read_json(result["artifact"])
    assert payload["meta"]["schema"] == EXPOSURE
    assert validate(payload, SCHEMA_FILES[EXPOSURE]) is payload
    assert "dealers are long calls and short puts" in result["assumption"]
    assert payload["exposure"]["assumption"] == result["assumption"]
    assert result["call_wall"] and result["put_wall"]
    assert result["max_pain"] is not None


def test_the_whole_chain_is_used_not_a_band_around_spot(
        chain_snapshot, args_factory, tmp_path):
    """Catches a band filter creeping into the exposure profile.

    A wall three hundred points away is exactly the thing a band would
    hide, which is why this command differs from the ladder.
    """
    put_snapshot(chain_snapshot, tmp_path)
    result = exposure_cmd.run(exposure_args(args_factory, tmp_path))
    rows = read_json(result["artifact"])["exposure"]["rows"]
    strikes = {row["strike"] for row in rows}

    assert 80.0 in strikes and 120.0 in strikes


def test_contracts_without_volatility_are_excluded_and_counted(
        chain_snapshot, args_factory, tmp_path):
    """Catches a missing volatility being defaulted to keep a strike in.

    A gamma computed from an invented volatility moves a wall to a strike
    nothing is actually hedged at.
    """
    put_snapshot(chain_snapshot, tmp_path,
                 no_iv={(80.0, "call"), (80.0, "put"), (120.0, "call")})
    result = exposure_cmd.run(exposure_args(args_factory, tmp_path))

    assert any("3 contracts carry no usable implied volatility" in note
               for note in result["notes"])
    # Excluding them is correct behaviour, not a defect.
    assert read_json(result["artifact"])["meta"]["degraded"] is False


def test_contracts_without_open_interest_are_excluded_not_zeroed(
        chain_snapshot, args_factory, tmp_path):
    """Catches missing open interest being counted as zero.

    Zero open interest and unknown open interest are different facts, and
    treating the second as the first silently shrinks every wall.
    """
    put_snapshot(chain_snapshot, tmp_path,
                 no_open_interest={(85.0, "call"), (85.0, "put")})
    result = exposure_cmd.run(exposure_args(args_factory, tmp_path))

    assert any("no open interest recorded" in note
               for note in result["notes"])
    assert any("excluded rather than counted as zero" in note
               for note in result["notes"])


def test_the_multiplier_scales_the_exposure(chain_snapshot, args_factory,
                                            tmp_path):
    """Catches the contract multiplier being ignored or hard-coded.

    Exposure quoted per contract rather than per hundred shares is out by
    two orders of magnitude, which is the difference between a number a
    desk can act on and one it cannot.
    """
    # Open interest has to be lopsided, or the call and put sides cancel to
    # a net of exactly zero and the scaling is untestable.
    snapshot = chain_snapshot()
    for contract in snapshot["contracts"]:
        contract["open_interest"] = 500 if contract["type"] == "call" else 100
    write_json(snapshot, "chain_TEST_2026-09-18.json", tmp_path)
    hundred = exposure_cmd.run(exposure_args(args_factory, tmp_path))
    one = exposure_cmd.run(exposure_args(args_factory, tmp_path,
                                         multiplier=1.0))

    assert one["net_gex"] > 0
    assert hundred["net_gex"] == pytest.approx(one["net_gex"] * 100.0,
                                               rel=1e-9)


def test_snapshot_degradation_is_inherited(chain_snapshot, args_factory,
                                           tmp_path):
    """Catches an exposure artifact looking clean while its chain was not."""
    put_snapshot(chain_snapshot, tmp_path, degraded=True,
                 degraded_reason="risk-free rate: ^IRX unavailable")
    result = exposure_cmd.run(exposure_args(args_factory, tmp_path))

    meta = read_json(result["artifact"])["meta"]
    assert meta["degraded"] is True
    assert "^IRX unavailable" in meta["degraded_reason"]


def test_missing_snapshot_is_an_actionable_error(args_factory, tmp_path):
    """Catches an empty artifact directory producing an opaque failure."""
    with pytest.raises(FileNotFoundError) as excinfo:
        exposure_cmd.run(exposure_args(args_factory, tmp_path))
    assert "optiondesk chain" in str(excinfo.value)


def test_a_named_snapshot_is_used_in_preference_to_the_newest(
        chain_snapshot, args_factory, tmp_path):
    """Catches --snapshot being ignored in favour of whatever is newest.

    Mixing one expiry's request with another expiry's file is the exact
    confusion the grouping elsewhere exists to prevent.
    """
    september = put_snapshot(chain_snapshot, tmp_path, expiry="2026-09-18")
    put_snapshot(chain_snapshot, tmp_path, expiry="2026-10-16")
    wanted = tmp_path / "chain_TEST_2026-09-18.json"

    result = exposure_cmd.run(exposure_args(args_factory, tmp_path,
                                            snapshot=str(wanted)))
    assert result["expiry"] == september["expiry"] == "2026-09-18"


def test_a_missing_volatility_is_not_reported_as_missing_open_interest(
        chain_snapshot, args_factory, tmp_path):
    """The note has to name the cause that applied.

    On the live SPY chain every one of 394 contracts carried open interest
    and eight were skipped for having no gamma, while the artifact said all
    eight had no open interest recorded. Two notes about the same contracts
    gave two different causes and one was false.
    """
    put_snapshot(chain_snapshot, tmp_path, no_iv={(85.0, "call")})
    result = exposure_cmd.run(exposure_args(args_factory, tmp_path))

    assert not any("no open interest recorded" in note
                   for note in result["notes"]), (
        "a contract skipped for missing volatility was reported as missing "
        "open interest")
    assert any("no gamma" in note for note in result["notes"])
