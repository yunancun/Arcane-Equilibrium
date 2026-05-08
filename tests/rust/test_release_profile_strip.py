from __future__ import annotations

import re
from pathlib import Path


def test_rust_release_profile_strips_symbols() -> None:
    cargo_toml = Path(__file__).resolve().parents[2] / "rust" / "Cargo.toml"
    text = cargo_toml.read_text(encoding="utf-8")
    match = re.search(r"(?ms)^\[profile\.release]\s*(.*?)(?:^\[|\Z)", text)

    assert match is not None
    assert re.search(r'(?m)^strip\s*=\s*"symbols"\s*$', match.group(1))
