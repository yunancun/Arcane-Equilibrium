"""Small stdlib JSON-Schema subset shared by governance contracts."""

from __future__ import annotations

import re
from datetime import datetime
from functools import lru_cache
from typing import Any


# ── E2 F-04(2026-08-04 三輪複核;全 repo 級) ─────────────────────────────────
# Python 的 `$` 匹配「字串尾**或尾端換行之前**」,ECMA-262(JSON Schema 指定的 regex
# 方言)的 `$` 則只匹配字串尾。E2 實測 `{"h": "<40hex>\n"}` 通過 `^[0-9a-f]{40}$`
# ——本檔是全 repo 556 個 `pattern` 的唯一執行點,所以那是一個全 repo 級的假不變量。
#
# **不改成 `fullmatch`**:JSON Schema 的 `pattern` 依規範是**非錨定的 search**
# (例:本 repo 既有的 `^https://api\.github\.com/` 前綴式、以及 `not` 裡的
# `(^|/)\.\.(/|$)` 都靠 search 語義才正確)。改 fullmatch 會讓這兩類 pattern 全部失效。
# 正解是把**錨點**翻成 ECMA 語義:未逸出且不在字元類內的 `^`→`\A`、`$`→`\Z`,
# search 語義原封不動。
@lru_cache(maxsize=512)
def _compiled_pattern(pattern: str) -> re.Pattern[str]:
    """把 pattern 的 `^`/`$` 翻成 `\\A`/`\\Z` 後編譯(逸出與字元類內的一律當字面)。"""

    translated: list[str] = []
    in_class = False
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "\\" and index + 1 < len(pattern):
            translated.append(pattern[index:index + 2])
            index += 2
            continue
        if in_class:
            in_class = char != "]"
        elif char == "[":
            in_class = True
        elif char == "^":
            translated.append("\\A")
            index += 1
            continue
        elif char == "$":
            translated.append("\\Z")
            index += 1
            continue
        translated.append(char)
        index += 1
    return re.compile("".join(translated))


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
    if "oneOf" in schema:
        matches = sum(
            not schema_subset_errors(value, option, root_schema, path)
            for option in schema["oneOf"]
        )
        if matches != 1:
            errors.append(f"{path}: satisfies {matches} oneOf branches, expected one")
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
        if "pattern" in schema and _compiled_pattern(
            str(schema["pattern"])
        ).search(value) is None:
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
        if len(value) < int(schema.get("minProperties", 0)):
            errors.append(f"{path}: object has fewer than minProperties")
        if "maxProperties" in schema and len(value) > int(schema["maxProperties"]):
            errors.append(f"{path}: object has more than maxProperties")
        required = set(schema.get("required", []))
        for key in sorted(required - set(value)):
            errors.append(f"{path}: missing required property {key}")
        properties = schema.get("properties", {})
        pattern_properties = schema.get("patternProperties", {})
        # E3 round-4 R4-2:`patternProperties` 原本直接 `re.compile`,於是
        # `6f563c299` 宣稱的「本檔是全部 pattern 唯一的 ECMA 忠實執行點」不成立
        # ——`$` 在 Python 允許尾隨換行,`properties` 側已翻成 `\Z` 而這側沒有。
        # 兩側改用同一個編譯器;search 語義(JSON Schema 對兩者皆為 search)不變。
        compiled_patterns = [
            (_compiled_pattern(str(pattern)), child_schema)
            for pattern, child_schema in pattern_properties.items()
        ]
        for key in sorted(set(value) - set(properties)):
            matches = [
                child_schema for pattern, child_schema in compiled_patterns
                if pattern.search(key)
            ]
            if matches:
                for child_schema in matches:
                    errors.extend(schema_subset_errors(
                        value[key], child_schema, root_schema, f"{path}.{key}"
                    ))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: unexpected property {key}")
            elif isinstance(schema.get("additionalProperties"), dict):
                errors.extend(schema_subset_errors(
                    value[key], schema["additionalProperties"], root_schema,
                    f"{path}.{key}",
                ))
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
