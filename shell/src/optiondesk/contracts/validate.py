"""Schema validation with no mandatory dependency.

If the jsonschema package is installed it is used, because it implements the
whole specification. If it is not, a deliberately small subset validator runs
instead: type, required, properties, items, enum, minimum, exclusiveMinimum,
minLength and local $ref.

The subset is enough for the contracts in this package and it means a fresh
clone validates its own output with nothing but the standard library. Where
the subset cannot express a rule, the rule is written into the schema
description so a human reviewer still sees it.
"""

import json
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent

try:  # pragma: no cover - environment dependent
    import jsonschema as _jsonschema
except ImportError:  # pragma: no cover
    _jsonschema = None


class ValidationError(ValueError):
    """Raised when a payload does not satisfy its contract."""


def load_schema(filename):
    """Read one schema file from the contracts directory."""
    with open(SCHEMA_DIR / filename, "r", encoding="utf-8") as handle:
        return json.load(handle)


def validate(payload, filename):
    """Validate payload against the named schema file. Returns payload."""
    schema = load_schema(filename)
    if _jsonschema is not None:
        try:
            _jsonschema.validate(payload, schema)
        except _jsonschema.ValidationError as exc:
            raise ValidationError(str(exc)) from exc
        except Exception as exc:
            # A reference the library cannot retrieve raises something
            # that is not a ValidationError, and letting it escape turns
            # an optional dependency into a crash in two commands.
            raise ValidationError(
                "schema {} could not be evaluated: {}: {}".format(
                    filename, type(exc).__name__, exc)) from exc
        return payload
    _check(payload, schema, schema, "$")
    return payload


def _resolve(node, root):
    """Resolve a local $ref.

    A cross-file reference raises. An earlier version returned a
    "skipped" marker that the caller discarded, so the meta block of two
    artifact types passed validation whatever it contained: a bare
    string, an integer, None. The docstring claimed the miss was
    reported; nothing reported it. Raising is the only honest option
    available to a function whose only output is pass or fail.
    """
    ref = node.get("$ref")
    if not ref:
        return node
    if ref.startswith("#/"):
        target = root
        for part in ref[2:].split("/"):
            target = target[part]
        return target
    raise ValidationError(
        "schema contains a cross-file reference this validator cannot "
        "resolve: {}. Inline the definition, or install jsonschema and "
        "register the sibling schemas.".format(ref))


def _type_ok(value, expected):
    types = expected if isinstance(expected, list) else [expected]
    for name in types:
        if name == "object" and isinstance(value, dict):
            return True
        if name == "array" and isinstance(value, list):
            return True
        if name == "string" and isinstance(value, str):
            return True
        if name == "integer" and isinstance(value, int) \
                and not isinstance(value, bool):
            return True
        if name == "number" and isinstance(value, (int, float)) \
                and not isinstance(value, bool):
            return True
        if name == "boolean" and isinstance(value, bool):
            return True
        if name == "null" and value is None:
            return True
    return False


def _check(value, schema, root, path):
    schema = _resolve(schema, root)
    if "type" in schema and not _type_ok(value, schema["type"]):
        raise ValidationError(
            "{}: expected type {}, got {}".format(
                path, schema["type"], type(value).__name__))
    if "enum" in schema and value not in schema["enum"]:
        raise ValidationError(
            "{}: {!r} is not one of {}".format(path, value, schema["enum"]))
    if isinstance(value, str) and "minLength" in schema:
        if len(value) < schema["minLength"]:
            raise ValidationError("{}: shorter than minLength".format(path))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ValidationError(
                "{}: {} below minimum {}".format(path, value,
                                                 schema["minimum"]))
        if "exclusiveMinimum" in schema \
                and value <= schema["exclusiveMinimum"]:
            raise ValidationError(
                "{}: {} not above exclusiveMinimum {}".format(
                    path, value, schema["exclusiveMinimum"]))
    if isinstance(value, dict):
        for name in schema.get("required", ()):
            if name not in value:
                raise ValidationError(
                    "{}: missing required property {!r}".format(path, name))
        for name, subschema in schema.get("properties", {}).items():
            if name in value:
                _check(value[name], subschema, root,
                       "{}.{}".format(path, name))
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            _check(item, schema["items"], root,
                   "{}[{}]".format(path, index))
