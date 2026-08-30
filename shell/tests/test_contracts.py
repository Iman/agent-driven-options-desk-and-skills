import pytest

from optiondesk.contracts import (
    CHAIN_SNAPSHOT,
    SCHEMA_FILES,
    ValidationError,
    load_schema,
    validate,
)


def test_valid_snapshot_passes(snapshot):
    assert validate(snapshot, SCHEMA_FILES[CHAIN_SNAPSHOT]) is snapshot


def test_missing_required_property_fails(snapshot):
    del snapshot["spot"]
    with pytest.raises(ValidationError):
        validate(snapshot, SCHEMA_FILES[CHAIN_SNAPSHOT])


def test_bad_enum_fails(snapshot):
    snapshot["contracts"][0]["type"] = "straddle"
    with pytest.raises(ValidationError):
        validate(snapshot, SCHEMA_FILES[CHAIN_SNAPSHOT])


def test_non_positive_spot_fails(snapshot):
    snapshot["spot"] = 0
    with pytest.raises(ValidationError):
        validate(snapshot, SCHEMA_FILES[CHAIN_SNAPSHOT])


def test_null_iv_is_allowed(snapshot):
    # A contract with no usable volatility must remain representable.
    # If the schema ever forbids it, the pipeline would be pushed into
    # inventing a number, which is the failure this project exists to avoid.
    assert any(c["iv"] is None for c in snapshot["contracts"])
    validate(snapshot, SCHEMA_FILES[CHAIN_SNAPSHOT])


def test_every_schema_file_loads():
    for filename in SCHEMA_FILES.values():
        schema = load_schema(filename)
        assert "$id" in schema and "properties" in schema


def test_ladder_meta_is_actually_validated():
    """The ladder schema referenced the snapshot schema across files.

    The fallback validator skipped that reference and reported nothing, so
    the meta block of every ladder artifact accepted anything at all: a
    bare string, an integer, None. The fields it was not checking are the
    ones the whole design leans on, degraded and disclaimer among them.
    """
    from optiondesk.contracts import GREEKS_LADDER

    base = {"underlying": "X", "spot": 1.0,
            "units": {"delta": "a", "vega": "b", "theta": "c"}, "rows": []}
    for bad_meta in ("GARBAGE", 12345, None, [], {}):
        payload = dict(base, meta=bad_meta)
        with pytest.raises(ValidationError):
            validate(payload, SCHEMA_FILES[GREEKS_LADDER])


def test_cross_file_reference_raises_rather_than_passing_silently():
    from optiondesk.contracts import validate as validate_module_functions
    from optiondesk.contracts.validate import SCHEMA_DIR

    schema = {"type": "object",
              "properties": {"meta": {"$ref": "other.schema.json#/$defs/m"}}}
    path = SCHEMA_DIR / "_probe.schema.json"
    path.write_text(__import__("json").dumps(schema), encoding="utf-8")
    try:
        with pytest.raises(ValidationError) as excinfo:
            validate({"meta": {}}, "_probe.schema.json")
        assert "cross-file reference" in str(excinfo.value)
    finally:
        path.unlink()
