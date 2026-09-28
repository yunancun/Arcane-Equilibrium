import pytest

from rust_default_contract import assert_contract_token, assert_derived_default_fields


@pytest.mark.parametrize("source", [
    "pub struct Gate { pub ready: bool, } impl Default for Gate { fn default() -> Self { Self { ready: false } } }",
    "#[derive(Debug, Default)] pub struct Gate { pub ready: bool, }",
    "#[derive(Default)] #[serde(rename_all = \"snake_case\")] pub enum Gate { #[default] Denied, Allowed, }",
])
def test_default_trait_recognizes_both_compiler_supported_forms(source):
    assert_contract_token(source, "impl Default for Gate")


@pytest.mark.parametrize("source", [
    "#[derive(Debug)] pub struct Gate { pub ready: bool, }",
    "#[derive(Default)] pub struct Other { pub ready: bool, } pub struct Gate { pub ready: bool, }",
    "// #[derive(Default)]\npub struct Gate { pub ready: bool, }",
    "/* impl Default for Gate {} */ pub struct Gate { pub ready: bool, }",
])
def test_default_trait_rejects_missing_foreign_or_commented_implementation(source):
    with pytest.raises(AssertionError):
        assert_contract_token(source, "impl Default for Gate")


def test_derived_fields_pin_primitive_default_semantics():
    source = "#[derive(Default)] pub struct Gate { pub ready: bool, pub version: u32, pub identity: String, }"
    expected = {"ready": "bool", "version": "u32", "identity": "String"}
    assert_derived_default_fields(source, "Gate", expected)
    for mutation in (source.replace("bool", "AllowByDefault"), source.replace("Default", "Debug"), source.replace("pub ready", "pub unrelated")):
        with pytest.raises(AssertionError):
            assert_derived_default_fields(mutation, "Gate", expected)
