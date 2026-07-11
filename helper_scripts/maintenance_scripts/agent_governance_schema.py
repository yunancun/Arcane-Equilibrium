"""Small stdlib JSON-Schema subset shared by governance contracts."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any


def _schema_pointer(root_schema: dict[str, Any], pointer: str) -> dict[str, Any]:
    if not pointer.startswith("#/"):
        raise ValueError(f"unsupported schema reference: {pointer}")
    node: Any = root_schema
    for part in pointer[2:].split("/"):
        node = node[part.replace("~1", "/").replace("~0", "~")]
    if not isinstance(node, dict):
        raise ValueError(f"schema reference is not an object: {pointer}")
    return node


def _json_type_matches(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, False)


def schema_subset_errors(
    value: Any,
    schema: dict[str, Any],
    root_schema: dict[str, Any] | None = None,
    path: str = "$",
) -> list[str]:
    """Validate the JSON-Schema keywords used by checked-in governance schemas."""

    root_schema = root_schema or schema
    if "$ref" in schema:
        return schema_subset_errors(
            value, _schema_pointer(root_schema, schema["$ref"]), root_schema, path
        )

    errors: list[str] = []
    if "anyOf" in schema:
        if not any(
            not schema_subset_errors(value, option, root_schema, path)
            for option in schema["anyOf"]
        ):
            errors.append(f"{path}: does not satisfy anyOf")
            return errors
    if "not" in schema and not schema_subset_errors(value, schema["not"], root_schema, path):
        errors.append(f"{path}: matches forbidden not-schema")

    expected_type = schema.get("type")
    if expected_type is not None:
        choices = [expected_type] if isinstance(expected_type, str) else list(expected_type)
        if not any(_json_type_matches(value, choice) for choice in choices):
            errors.append(f"{path}: expected type {choices}")
            return errors

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value is outside enum")

    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)):
            errors.append(f"{path}: string is shorter than minLength")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            errors.append(f"{path}: string is longer than maxLength")
        if "pattern" in schema and re.search(str(schema["pattern"]), value) is None:
            errors.append(f"{path}: string does not match pattern")
        if schema.get("format") == "date-time":
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError("timezone missing")
            except (TypeError, ValueError):
                errors.append(f"{path}: invalid date-time")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: number is below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: number is above maximum")

    if isinstance(value, list):
        if len(value) < int(schema.get("minItems", 0)):
            errors.append(f"{path}: array is shorter than minItems")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            errors.append(f"{path}: array is longer than maxItems")
        if schema.get("uniqueItems") and len({repr(item) for item in value}) != len(value):
            errors.append(f"{path}: array items are not unique")
        if "items" in schema:
            for index, item in enumerate(value):
                errors.extend(
                    schema_subset_errors(item, schema["items"], root_schema, f"{path}[{index}]")
                )
        if "contains" in schema and not any(
            not schema_subset_errors(item, schema["contains"], root_schema, f"{path}[{index}]")
            for index, item in enumerate(value)
        ):
            errors.append(f"{path}: array does not contain a required matching item")

    if isinstance(value, dict):
        required = set(schema.get("required", []))
        for key in sorted(required - set(value)):
            errors.append(f"{path}: missing required property {key}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in sorted(set(value) - set(properties)):
                errors.append(f"{path}: unexpected property {key}")
        for key, child_schema in properties.items():
            if key in value:
                errors.extend(
                    schema_subset_errors(value[key], child_schema, root_schema, f"{path}.{key}")
                )

    for clause in schema.get("allOf", []):
        if "if" in clause:
            condition_matches = not schema_subset_errors(value, clause["if"], root_schema, path)
            if condition_matches and "then" in clause:
                errors.extend(schema_subset_errors(value, clause["then"], root_schema, path))
            if not condition_matches and "else" in clause:
                errors.extend(schema_subset_errors(value, clause["else"], root_schema, path))
        else:
            errors.extend(schema_subset_errors(value, clause, root_schema, path))
    return errors
