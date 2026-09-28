"""Recognize Default contracts without requiring a hand-written Rust impl.

These source guards supplement compiled Rust default/denial acceptance tests;
they do not evaluate custom field types or replace behavioral verification.
"""

import re


def _without_comments(source: str) -> str:
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)


def _derived_body(source: str, type_name: str) -> str:
    declaration = re.search(
        r"(?P<attrs>(?:#\[[^\]]*\]\s*)+)pub\s+(?:struct|enum)\s+"
        + re.escape(type_name)
        + r"\s*\{(?P<body>[^}]*)\}",
        _without_comments(source),
    )
    assert declaration is not None, f"missing attributed declaration for {type_name}"
    derives = re.findall(r"#\[derive\(([^)]*)\)\]", declaration["attrs"])
    assert any("Default" in [trait.strip() for trait in traits.split(",")]
               for traits in derives), f"missing derived Default for {type_name}"
    return declaration["body"]


def assert_contract_token(source: str, token: str) -> None:
    prefix = "impl Default for "
    if token.startswith(prefix):
        type_name = token[len(prefix):]
        manual = r"\bimpl\s+Default\s+for\s+" + re.escape(type_name) + r"\s*\{"
        if not re.search(manual, _without_comments(source)):
            _derived_body(source, type_name)
    else:
        assert token in source, f"missing contract token {token!r}"


def assert_derived_default_fields(source: str, type_name: str, fields: dict[str, str]) -> None:
    """Pin field types whose Rust Default supplies the required safe baseline."""
    body = _derived_body(source, type_name)
    for field, field_type in fields.items():
        pattern = r"\bpub\s+" + re.escape(field) + r"\s*:\s*" + re.escape(field_type) + r"\s*,"
        assert re.search(pattern, body), f"default field type changed: {type_name}.{field}"
