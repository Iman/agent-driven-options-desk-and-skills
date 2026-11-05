"""Run explicitly with QuantLib installed; never silently skip the backend."""
import copy
import importlib.util
from pathlib import Path

import pytest
import QuantLib as ql

spec = importlib.util.spec_from_file_location("backend_evaluation", Path(__file__).with_name("evaluate.py"))
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


def test_european_agreement_american_bounds_and_convergence():
    rows = evaluation.compare_prices()
    assert len(rows) >= 3
    for row in rows:
        assert abs(row["european_quantlib"] - row["european_optiondesk"]) < 1e-9
        assert row["american_800"] >= row["intrinsic"] - 1e-7
        assert row["american_800"] >= row["european_quantlib"] - 1e-3
        assert abs(row["american_800"] - row["american_400"]) < .001
    assert rows[1]["american_800"] - rows[1]["european_quantlib"] > 3


def test_quantlib_date_is_restored():
    before = ql.Settings.instance().evaluationDate
    evaluation.compare_prices()
    assert ql.Settings.instance().evaluationDate == before


def plan():
    return {"underlying": "SPY", "expiry": "2016-01-15", "legs": [
        {"kind": "call", "side": "long", "qty": 1.0, "strike": 200.0, "price": 2.0}]}


def test_export_keeps_contract_quantity_and_does_not_use_model_premium(tmp_path):
    bundle = evaluation.export_plan(plan(), tmp_path / "bundle", start="2016-01-04", end="2016-01-06",
                                    exercise_style="american", multiplier=100, data_mode="synthetic")
    assert bundle["legs"][0]["quantity"] == 1
    assert "price" not in bundle["legs"][0]
    assert bundle["data_mode"] == "synthetic"
    assert (tmp_path / "bundle" / "main.py").exists()


@pytest.mark.parametrize("change", [
    {"qty": .5}, {"qty": 0}, {"qty": float("nan")}, {"kind": "underlying"},
    {"side": "buy"}, {"strike": -1}, {"strike": float("inf")}, {"expiry": "2016-02-19"},
    {"days_to_expiry": 45},
])
def test_export_refuses_ambiguous_or_unsupported_legs(tmp_path, change):
    value = copy.deepcopy(plan())
    value["legs"][0].update(change)
    with pytest.raises(ValueError):
        evaluation.export_plan(value, tmp_path / "bundle", start="2016-01-04", end="2016-01-06",
                               exercise_style="american", multiplier=100, data_mode="synthetic")


@pytest.mark.parametrize("change", [
    {"far_expiry": "2016-02-19"}, {"meta": {"degraded": True, "degraded_reason": "missing inputs"}},
])
def test_export_refuses_time_spread_metadata_and_degraded_sources(tmp_path, change):
    value = plan()
    value.update(change)
    with pytest.raises(ValueError):
        evaluation.export_plan(value, tmp_path / "bundle", start="2016-01-04", end="2016-01-06",
                               exercise_style="american", multiplier=100, data_mode="synthetic")


@pytest.mark.parametrize("change", [
    {"exercise_style": "european"}, {"multiplier": 10}, {"data_mode": "unknown"},
    {"end": "2016-01-16"}, {"start": "2016-01-07"},
])
def test_export_refuses_unvalidated_semantics(tmp_path, change):
    args = dict(start="2016-01-04", end="2016-01-06", exercise_style="american", multiplier=100,
                data_mode="synthetic")
    args.update(change)
    with pytest.raises(ValueError):
        evaluation.export_plan(plan(), tmp_path / "bundle", **args)


def result():
    return {"state": {"Status": "Completed", "RuntimeError": "", "Hostname": "private-host"},
            "runtimeStatistics": {"OptionDesk Data Mode": "synthetic"},
            "orders": {str(i): {"status": 3, "tag": "OptionDesk plan sha256: " + "a"*64} for i in (1, 2)},
            "statistics": {"Total Orders": "2", "Net Profit": "0.01%"}}


def test_import_preserves_raw_statistics_and_omits_host_metadata():
    value = evaluation.summarize_result(result(), {"plan_sha256": "a"*64, "data_mode": "synthetic"})
    assert value["filled_orders"] == 2
    assert value["statistics"]["Net Profit"] == "0.01%"
    assert "private-host" not in str(value)


@pytest.mark.parametrize("change", [
    {"state": {"Status": "RuntimeError", "RuntimeError": "error"}},
    {"state": {"Status": "Running"}}, {"orders": {}},
    {"orders": {"1": {"status": 7}}}, {"runtimeStatistics": {}},
    {"orders": {"1": {"status": 3, "tag": "unrelated"}}},
])
def test_import_refuses_failed_empty_or_unrelated_results(change):
    value = result()
    value.update(change)
    with pytest.raises(ValueError):
        evaluation.summarize_result(value, {"plan_sha256": "a"*64, "data_mode": "synthetic"})
