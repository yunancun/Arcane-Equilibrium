from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RUST = ROOT / "rust"
CRATE = RUST / "openclaw_alr_fit_verifier"
MANIFEST = CRATE / "Cargo.toml"
LOCK = RUST / "Cargo.lock"
CI = ROOT / ".github" / "workflows" / "ci.yml"
CRATES_IO_SOURCE = "registry+https://github.com/rust-lang/crates.io-index"
EXPECTED_METADATA_CLOSURE_SIZE = 52
EXPECTED_METADATA_PROJECTION_SHA256 = (
    "a50f46f0735e45019fa845bcd426cbfdebd84fdae2a1e1456bd86e2e28891386"
)

EXPECTED_RUST_FILES = {
    "src/contract.rs",
    "src/lib.rs",
    "src/verifier.rs",
    "tests/strict_verifier_contract.rs",
}

DIRECT_DEPENDENCIES = {
    "base64": ("0.22.1", None),
    "ed25519-dalek": ("2.2.0", None),
    "serde_json": ("1.0.149", "dev"),
    "sha2": ("0.10.9", None),
}

FORBIDDEN_DEPENDENCIES = {
    "chrono",
    "openclaw_core",
    "openclaw_engine",
    "openclaw_types",
    "reqwest",
    "sqlx",
    "tokio",
}

FORBIDDEN_SOURCE_PATTERNS = (
    r"\bSigningKey\b",
    r"\bSecretKey\b",
    r"\bKeypair\b",
    r"\bVerifier\s*::\s*verify\b",
    r"\.verify\s*\(",
    r"\bverify_prehashed\b",
    r"\bverify_batch\b",
    r"\bhazmat\b",
    r"\blegacy_compatibility\b",
    r"\bpkcs8\b",
    r"\bpem\b",
    r"\brand\b",
    r"\bstd\s*::\s*(?:env|fs|io|net|path|process)\b",
    r"\bstd\s*::\s*os\s*::\s*(?:unix|windows)\s*::\s*(?:fd|fs|io|net)\b",
    r"\b(?:tokio|sqlx|reqwest|chrono)\s*::",
    r"\bextern\s+\"C\"",
    r"#\s*\[\s*link",
    r"\binclude(?:_bytes|_str)?!\s*\(",
)

EXPECTED_TRANSITIVE_BUILD_SCRIPTS = {
    ("curve25519-dalek", "4.1.3"),
    ("generic-array", "0.14.7"),
    ("libc", "0.2.184"),
    ("proc-macro2", "1.0.106"),
    ("quote", "1.0.45"),
    ("rustversion", "1.0.22"),
    ("serde", "1.0.228"),
    ("serde_core", "1.0.228"),
    ("serde_json", "1.0.149"),
    ("typenum", "1.19.0"),
    ("wasm-bindgen", "0.2.117"),
    ("wasm-bindgen-shared", "0.2.117"),
    ("zmij", "1.0.21"),
}

# This inventory is deliberately package-level and conservatively follows the
# workspace metadata feature-union graph. Package tests and generated support
# may contain reviewed unsafe code, while the first-party verifier contains none.
# The set is tightened against the reviewed lock and checked only in metadata mode.
EXPECTED_TRANSITIVE_UNSAFE_PACKAGES = {
    ("base64", "0.22.1"),
    ("block-buffer", "0.10.4"),
    ("bumpalo", "3.20.2"),
    ("cpufeatures", "0.2.17"),
    ("curve25519-dalek", "4.1.3"),
    ("curve25519-dalek-derive", "0.1.1"),
    ("ed25519-dalek", "2.2.0"),
    ("futures-core", "0.3.32"),
    ("futures-macro", "0.3.32"),
    ("futures-sink", "0.3.32"),
    ("futures-task", "0.3.32"),
    ("futures-util", "0.3.32"),
    ("generic-array", "0.14.7"),
    ("getrandom", "0.2.17"),
    ("itoa", "1.0.18"),
    ("js-sys", "0.3.94"),
    ("libc", "0.2.184"),
    ("memchr", "2.8.0"),
    ("once_cell", "1.21.4"),
    ("pin-project-lite", "0.2.17"),
    ("proc-macro2", "1.0.106"),
    ("rand_core", "0.6.4"),
    ("rustversion", "1.0.22"),
    ("semver", "1.0.27"),
    ("serde", "1.0.228"),
    ("serde_core", "1.0.228"),
    ("serde_json", "1.0.149"),
    ("sha2", "0.10.9"),
    ("slab", "0.4.12"),
    ("subtle", "2.6.1"),
    ("syn", "2.0.117"),
    ("unicode-ident", "1.0.24"),
    ("wasi", "0.11.1+wasi-snapshot-preview1"),
    ("wasm-bindgen", "0.2.117"),
    ("wasm-bindgen-macro-support", "0.2.117"),
    ("zmij", "1.0.21"),
}

# Reviewed version disposition only. This is not a live or exhaustive advisory
# database query and must be refreshed by a separately governed security review.
REVIEWED_ADVISORY_SNAPSHOT = (
    (
        "curve25519-dalek",
        "4.1.3",
        "RUSTSEC-2024-0344",
        "PATCHED_VERSION_SNAPSHOT",
    ),
    (
        "ed25519-dalek",
        "2.2.0",
        "RUSTSEC-2022-0093/GHSA-w5vr-6qhr-36cc",
        "PATCHED_VERSION_SNAPSHOT",
    ),
)


def _source_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((CRATE / "src").glob("*.rs"))
    )


_MAX_RUST_SCAN_BYTES = 1_048_576
_MAX_RUST_SCAN_TOKENS = 262_144
_MAX_RUST_SCAN_DEPTH = 128
_RUST_KEYWORDS = {"as", "crate", "extern", "mod", "self", "super", "use"}
_FORBIDDEN_STD_CHILDREN = {"env", "fs", "io", "net", "os", "path", "process"}
_FORBIDDEN_OUTPUT_MACROS = {"dbg", "eprint", "eprintln", "print", "println"}
_FORBIDDEN_STD_USE_CHILDREN = (
    _FORBIDDEN_STD_CHILDREN | _FORBIDDEN_OUTPUT_MACROS
)
_EMPTY_PATH = ("empty", None, None)


def _rust_lexer(source: str) -> list[tuple[str, str]] | None:
    if len(source.encode("utf-8")) > _MAX_RUST_SCAN_BYTES:
        return None
    tokens: list[tuple[str, str]] = []
    source_characters = len(source)

    def emit(kind: str, value: str) -> bool:
        tokens.append((kind, value))
        return (
            len(tokens) <= _MAX_RUST_SCAN_TOKENS
            and len(tokens) <= source_characters
        )

    cursor = 0
    while cursor < source_characters:
        character = source[cursor]
        if character.isspace():
            cursor += 1
            continue

        if source.startswith("//", cursor):
            newline = source.find("\n", cursor + 2)
            cursor = source_characters if newline == -1 else newline + 1
            continue
        if source.startswith("/*", cursor):
            depth = 1
            cursor += 2
            while cursor < source_characters and depth:
                if source.startswith("/*", cursor):
                    depth += 1
                    if depth > _MAX_RUST_SCAN_DEPTH:
                        return None
                    cursor += 2
                elif source.startswith("*/", cursor):
                    depth -= 1
                    cursor += 2
                else:
                    cursor += 1
            if depth:
                return None
            continue

        raw_literal = False
        for prefix in ("br", "cr", "r"):
            if not source.startswith(prefix, cursor):
                continue
            delimiter_cursor = cursor + len(prefix)
            hash_count = 0
            while (
                delimiter_cursor < source_characters
                and source[delimiter_cursor] == "#"
            ):
                hash_count += 1
                delimiter_cursor += 1
            if (
                delimiter_cursor >= source_characters
                or source[delimiter_cursor] != '"'
            ):
                continue
            if hash_count > _MAX_RUST_SCAN_DEPTH:
                return None
            closing = '"' + "#" * hash_count
            content_cursor = delimiter_cursor + 1
            while content_cursor < source_characters and not source.startswith(
                closing, content_cursor
            ):
                content_cursor += 1
            if content_cursor >= source_characters:
                return None
            cursor = content_cursor + len(closing)
            raw_literal = True
            break
        if raw_literal:
            continue

        quote_cursor: int | None = None
        if character == '"':
            quote_cursor = cursor
        elif character in {"b", "c"} and source.startswith(
            character + '"', cursor
        ):
            quote_cursor = cursor + 1
        if quote_cursor is not None:
            literal_end = _rust_quoted_literal_end(source, quote_cursor)
            if literal_end is None:
                return None
            cursor = literal_end
            continue

        if character == "b" and source.startswith("b'", cursor):
            literal_end = _rust_quoted_literal_end(source, cursor + 1)
            if literal_end is None:
                return None
            cursor = literal_end
            continue

        if character == "'":
            identifier_cursor = cursor + 1
            if (
                identifier_cursor < source_characters
                and _rust_identifier_start(source[identifier_cursor])
            ):
                identifier_end = identifier_cursor + 1
                while (
                    identifier_end < source_characters
                    and _rust_identifier_continue(source[identifier_end])
                ):
                    identifier_end += 1
                if (
                    identifier_end >= source_characters
                    or source[identifier_end] != "'"
                ):
                    if not emit("lifetime", source[identifier_cursor:identifier_end]):
                        return None
                    cursor = identifier_end
                    continue
            literal_end = _rust_quoted_literal_end(source, cursor)
            if literal_end is None:
                return None
            cursor = literal_end
            continue

        if source.startswith("r#", cursor):
            identifier_cursor = cursor + 2
            if (
                identifier_cursor < source_characters
                and _rust_identifier_start(source[identifier_cursor])
            ):
                identifier_end = identifier_cursor + 1
                while (
                    identifier_end < source_characters
                    and _rust_identifier_continue(source[identifier_end])
                ):
                    identifier_end += 1
                if not emit("raw_identifier", source[identifier_cursor:identifier_end]):
                    return None
                cursor = identifier_end
                continue

        if _rust_identifier_start(character):
            identifier_end = cursor + 1
            while (
                identifier_end < source_characters
                and _rust_identifier_continue(source[identifier_end])
            ):
                identifier_end += 1
            identifier = source[cursor:identifier_end]
            kind = "keyword" if identifier in _RUST_KEYWORDS else "identifier"
            if not emit(kind, identifier):
                return None
            cursor = identifier_end
            continue

        if character.isdigit():
            number_end = cursor + 1
            while number_end < source_characters and (
                _rust_identifier_continue(source[number_end])
                or source[number_end] == "."
            ):
                number_end += 1
            if not emit("number", source[cursor:number_end]):
                return None
            cursor = number_end
            continue

        if source.startswith("::", cursor):
            if not emit("symbol", "::"):
                return None
            cursor += 2
            continue
        if not emit("symbol", character):
            return None
        cursor += 1

    return tokens


def _rust_identifier_start(character: str) -> bool:
    return character == "_" or (
        not character.isdecimal() and character.isidentifier()
    )


def _rust_identifier_continue(character: str) -> bool:
    return character == "_" or character.isalnum() or ("a" + character).isidentifier()


def _rust_quoted_literal_end(source: str, quote_cursor: int) -> int | None:
    cursor = quote_cursor + 1
    while cursor < len(source):
        if source[cursor] == "\\":
            cursor += 2
            if cursor > len(source):
                return None
        elif source[cursor] == source[quote_cursor]:
            return cursor + 1
        else:
            cursor += 1
    return None


def _token_is(
    tokens: list[tuple[str, str]], cursor: int, kind: str, value: str
) -> bool:
    return cursor < len(tokens) and tokens[cursor] == (kind, value)


def _token_name(token: tuple[str, str]) -> str | None:
    if token[0] in {"identifier", "raw_identifier", "keyword"}:
        return token[1]
    return None


def _token_is_alias(token: tuple[str, str]) -> bool:
    return token[0] in {"identifier", "raw_identifier"}


def _resolved_path_child(
    path: tuple[str, str | None, str | None],
    token: tuple[str, str],
    *,
    absolute: bool = False,
) -> tuple[str, str | None, str | None] | None:
    name = _token_name(token)
    if name is None:
        return None
    if token == ("keyword", "self"):
        if path != _EMPTY_PATH:
            return path
        return ("non_root", None, name)
    if token in {("keyword", "crate"), ("keyword", "super")}:
        return ("non_root", None, name)
    root, first_std_child, _ = path
    if root == "empty":
        if name == "std":
            return ("abs_std" if absolute else "rel_std", None, name)
        return ("non_root", None, name)
    if root in {"rel_std", "abs_std"} and first_std_child is None:
        return (root, name, name)
    return (root, first_std_child, name)


def _path_is_exact_root_std(
    path: tuple[str, str | None, str | None]
) -> bool:
    return path[0] in {"rel_std", "abs_std"} and path[1] is None


def _path_is_forbidden_std(
    path: tuple[str, str | None, str | None]
) -> bool:
    return path[0] in {"rel_std", "abs_std"} and (
        path[1] in _FORBIDDEN_STD_USE_CHILDREN
    )


def _parse_use_tree(
    tokens: list[tuple[str, str]],
    cursor: int,
    path: tuple[str, str | None, str | None],
    depth: int,
) -> tuple[int, bool, bool] | None:
    if depth > _MAX_RUST_SCAN_DEPTH or cursor >= len(tokens):
        return None
    absolute = False
    if _token_is(tokens, cursor, "symbol", "::"):
        path = _EMPTY_PATH
        absolute = True
        cursor += 1
        if cursor >= len(tokens):
            return None

    if _token_is(tokens, cursor, "symbol", "{"):
        cursor += 1
        if _token_is(tokens, cursor, "symbol", "}"):
            return None
        forbidden = False
        binds_safe_std = False
        while True:
            parsed = _parse_use_tree(tokens, cursor, path, depth + 1)
            if parsed is None:
                return None
            cursor, member_forbidden, member_binds_safe_std = parsed
            forbidden = forbidden or member_forbidden
            binds_safe_std = binds_safe_std or member_binds_safe_std
            if _token_is(tokens, cursor, "symbol", "}"):
                return cursor + 1, forbidden, binds_safe_std
            if not _token_is(tokens, cursor, "symbol", ","):
                return None
            cursor += 1
            if _token_is(tokens, cursor, "symbol", "}"):
                return cursor + 1, forbidden, binds_safe_std

    if _token_is(tokens, cursor, "symbol", "*"):
        if path == _EMPTY_PATH:
            return None
        return (
            cursor + 1,
            _path_is_exact_root_std(path) or _path_is_forbidden_std(path),
            False,
        )

    resolved = _resolved_path_child(path, tokens[cursor], absolute=absolute)
    if resolved is None:
        return None
    cursor += 1
    while _token_is(tokens, cursor, "symbol", "::"):
        cursor += 1
        if _token_is(tokens, cursor, "symbol", "{"):
            return _parse_use_tree(tokens, cursor, resolved, depth)
        if _token_is(tokens, cursor, "symbol", "*"):
            return (
                cursor + 1,
                _path_is_exact_root_std(resolved)
                or _path_is_forbidden_std(resolved),
                False,
            )
        if cursor >= len(tokens):
            return None
        resolved = _resolved_path_child(resolved, tokens[cursor])
        if resolved is None:
            return None
        cursor += 1

    binding_name = resolved[2]
    if _token_is(tokens, cursor, "keyword", "as"):
        cursor += 1
        if cursor >= len(tokens) or not _token_is_alias(tokens[cursor]):
            return None
        binding_name = tokens[cursor][1]
        cursor += 1
    forbidden = _path_is_forbidden_std(resolved) or _path_is_exact_root_std(
        resolved
    )
    return cursor, forbidden, binding_name == "std" and not forbidden


def _parse_use_declaration(
    tokens: list[tuple[str, str]], use_cursor: int
) -> tuple[int, bool, bool] | None:
    parsed = _parse_use_tree(tokens, use_cursor + 1, _EMPTY_PATH, 0)
    if parsed is None:
        return None
    cursor, forbidden, binds_safe_std = parsed
    if not _token_is(tokens, cursor, "symbol", ";"):
        return None
    return cursor + 1, forbidden, binds_safe_std


def _parse_extern_crate(
    tokens: list[tuple[str, str]], extern_cursor: int
) -> tuple[int, bool, bool] | None:
    cursor = extern_cursor + 2
    if cursor >= len(tokens) or (
        not _token_is_alias(tokens[cursor])
        and tokens[cursor] != ("keyword", "self")
    ):
        return None
    crate_name = tokens[cursor][1]
    cursor += 1
    binding_name = crate_name
    if _token_is(tokens, cursor, "keyword", "as"):
        cursor += 1
        if cursor >= len(tokens) or not _token_is_alias(tokens[cursor]):
            return None
        binding_name = tokens[cursor][1]
        cursor += 1
    if not _token_is(tokens, cursor, "symbol", ";"):
        return None
    forbidden = crate_name == "std"
    return cursor + 1, forbidden, binding_name == "std" and not forbidden


def _parse_mod_declaration(
    tokens: list[tuple[str, str]], mod_cursor: int
) -> tuple[int, bool, int | None] | None:
    name_cursor = mod_cursor + 1
    if name_cursor >= len(tokens) or not _token_is_alias(tokens[name_cursor]):
        return None
    cursor = name_cursor + 1
    if _token_is(tokens, cursor, "symbol", ";"):
        return cursor + 1, tokens[name_cursor][1] == "std", None
    if _token_is(tokens, cursor, "symbol", "{"):
        return cursor + 1, tokens[name_cursor][1] == "std", cursor
    return None


def _delimiter_pairs(
    tokens: list[tuple[str, str]],
) -> tuple[dict[int, int], dict[int, int]] | None:
    opening_for = {")": "(", "]": "[", "}": "{"}
    stack: list[tuple[str, int]] = []
    open_to_close: dict[int, int] = {}
    close_to_open: dict[int, int] = {}
    for cursor, token in enumerate(tokens):
        if token[0] != "symbol":
            continue
        if token[1] in {"(", "[", "{"}:
            stack.append((token[1], cursor))
            if len(stack) > _MAX_RUST_SCAN_DEPTH:
                return None
        elif token[1] in opening_for:
            if not stack or stack[-1][0] != opening_for[token[1]]:
                return None
            _, opening_cursor = stack.pop()
            open_to_close[opening_cursor] = cursor
            close_to_open[cursor] = opening_cursor
    if stack:
        return None
    return open_to_close, close_to_open


def _macro_token_mask(
    tokens: list[tuple[str, str]], open_to_close: dict[int, int]
) -> list[bool]:
    mask_delta = [0] * (len(tokens) + 1)
    for cursor, token in enumerate(tokens):
        if token != ("symbol", "!"):
            continue
        opening_cursor = cursor + 1
        if (
            opening_cursor < len(tokens)
            and _token_name(tokens[opening_cursor]) is not None
        ):
            opening_cursor += 1
        if opening_cursor not in open_to_close:
            continue
        closing_cursor = open_to_close[opening_cursor]
        mask_delta[opening_cursor] += 1
        mask_delta[closing_cursor + 1] -= 1
    masked = [False] * len(tokens)
    active = 0
    for cursor in range(len(tokens)):
        active += mask_delta[cursor]
        masked[cursor] = active > 0
    return masked


def _forbidden_output_macro_invocation(
    tokens: list[tuple[str, str]], open_to_close: dict[int, int]
) -> bool:
    for cursor, token in enumerate(tokens):
        if _token_name(token) not in _FORBIDDEN_OUTPUT_MACROS:
            continue
        if not _token_is(tokens, cursor + 1, "symbol", "!"):
            continue
        if cursor + 2 in open_to_close:
            return True
    return False


def _macro_incomplete_declaration_has_metavariable(
    tokens: list[tuple[str, str]],
    declaration_cursor: int,
    macro_mask: list[bool],
) -> bool:
    root_cursor = declaration_cursor + 1
    if tokens[declaration_cursor] == ("keyword", "extern"):
        root_cursor += 1
    elif _token_is(tokens, root_cursor, "symbol", "::"):
        root_cursor += 1
    if root_cursor < len(tokens):
        if (
            tokens[root_cursor] == ("symbol", "$")
            and root_cursor + 1 < len(tokens)
            and _token_name(tokens[root_cursor + 1]) == "crate"
        ):
            return False
        literal_root = _token_name(tokens[root_cursor])
        if literal_root is not None and literal_root != "std":
            return False

    nested_delimiters = 0
    has_non_special_metavariable = False
    cursor = declaration_cursor + 1
    while cursor < len(tokens) and macro_mask[cursor]:
        token = tokens[cursor]
        if token == ("symbol", "$") and cursor + 1 < len(tokens):
            metavariable_name = _token_name(tokens[cursor + 1])
            if metavariable_name is not None and metavariable_name != "crate":
                has_non_special_metavariable = True
        if token[0] == "symbol" and token[1] in {"(", "[", "{"}:
            nested_delimiters += 1
        elif token[0] == "symbol" and token[1] in {")", "]", "}"
        }:
            if nested_delimiters == 0:
                return False
            nested_delimiters -= 1
        elif token == ("symbol", ";") and nested_delimiters == 0:
            return has_non_special_metavariable
        cursor += 1
    return False


def _macro_group_has_forbidden_first_child(
    tokens: list[tuple[str, str]],
    opening_cursor: int,
    open_to_close: dict[int, int],
) -> bool:
    closing_cursor = open_to_close[opening_cursor]
    cursor = opening_cursor + 1
    at_member_start = True
    while cursor < closing_cursor:
        token = tokens[cursor]
        if token == ("symbol", ","):
            at_member_start = True
            cursor += 1
            continue
        if (
            at_member_start
            and token == ("symbol", "$")
            and cursor + 1 < closing_cursor
            and _token_name(tokens[cursor + 1]) is not None
        ):
            return True
        if at_member_start and _token_name(token) is not None:
            if _token_name(token) in _FORBIDDEN_STD_CHILDREN:
                return True
            at_member_start = False
        if token[0] == "symbol" and token[1] in {"(", "[", "{"}:
            nested_close = open_to_close.get(cursor)
            if nested_close is None:
                return False
            cursor = nested_close + 1
            continue
        cursor += 1
    return False


def _macro_metavariable_forbidden_path(
    tokens: list[tuple[str, str]],
    macro_mask: list[bool],
    open_to_close: dict[int, int],
    macro_special_crate_group_mask: list[bool],
) -> bool:
    for cursor, token in enumerate(tokens):
        if not macro_mask[cursor]:
            continue
        if token == ("symbol", "$"):
            root_cursor = cursor + 1
            separator_cursor = cursor + 2
            child_cursor = cursor + 3
            if (
                root_cursor >= len(tokens)
                or _token_name(tokens[root_cursor]) in {None, "crate"}
                or not _token_is(tokens, separator_cursor, "symbol", "::")
                or child_cursor >= len(tokens)
            ):
                continue
        elif _token_name(token) == "std":
            if macro_special_crate_group_mask[cursor]:
                continue
            if (
                cursor > 0
                and _token_is(tokens, cursor - 1, "symbol", "::")
                and cursor >= 2
                and _token_is_path_segment(tokens[cursor - 2])
            ):
                continue
            separator_cursor = cursor + 1
            child_cursor = cursor + 2
            if (
                not _token_is(tokens, separator_cursor, "symbol", "::")
                or child_cursor >= len(tokens)
            ):
                continue
        else:
            continue
        child_name = _token_name(tokens[child_cursor])
        if child_name in _FORBIDDEN_STD_CHILDREN:
            return True
        if (
            tokens[child_cursor] == ("symbol", "$")
            and child_cursor + 1 < len(tokens)
            and _token_name(tokens[child_cursor + 1]) is not None
        ):
            return True
        if (
            tokens[child_cursor] == ("symbol", "{")
            and child_cursor in open_to_close
            and _macro_group_has_forbidden_first_child(
                tokens, child_cursor, open_to_close
            )
        ):
            return True
    return False


def _macro_special_crate_group_mask(
    tokens: list[tuple[str, str]],
    macro_mask: list[bool],
    open_to_close: dict[int, int],
) -> list[bool]:
    mask_delta = [0] * (len(tokens) + 1)
    for cursor, token in enumerate(tokens):
        opening_cursor = cursor + 3
        if (
            not macro_mask[cursor]
            or token != ("symbol", "$")
            or cursor + 2 >= len(tokens)
            or _token_name(tokens[cursor + 1]) != "crate"
            or not _token_is(tokens, cursor + 2, "symbol", "::")
            or opening_cursor not in open_to_close
            or tokens[opening_cursor] != ("symbol", "{")
        ):
            continue
        closing_cursor = open_to_close[opening_cursor]
        mask_delta[opening_cursor + 1] += 1
        mask_delta[closing_cursor] -= 1
    masked = [False] * len(tokens)
    active = 0
    for cursor in range(len(tokens)):
        active += mask_delta[cursor]
        masked[cursor] = active > 0
    return masked


def _module_openings(
    tokens: list[tuple[str, str]], macro_mask: list[bool]
) -> set[int] | None:
    openings: set[int] = set()
    for cursor in range(len(tokens)):
        if macro_mask[cursor] or tokens[cursor] != ("keyword", "mod"):
            continue
        parsed = _parse_mod_declaration(tokens, cursor)
        if parsed is None:
            return None
        _, _, opening_cursor = parsed
        if opening_cursor is not None:
            openings.add(opening_cursor)
    return openings


def _module_has_path_override(
    tokens: list[tuple[str, str]],
    module_cursor: int,
    close_to_open: dict[int, int],
) -> bool:
    attribute_cursor = module_cursor
    if (
        attribute_cursor > 0
        and tokens[attribute_cursor - 1] == ("symbol", ")")
    ):
        opening_cursor = close_to_open.get(attribute_cursor - 1)
        if (
            opening_cursor is not None
            and opening_cursor > 0
            and _token_name(tokens[opening_cursor - 1]) == "pub"
        ):
            attribute_cursor = opening_cursor - 1
    elif (
        attribute_cursor > 0
        and _token_name(tokens[attribute_cursor - 1]) == "pub"
    ):
        attribute_cursor -= 1

    while (
        attribute_cursor > 0
        and tokens[attribute_cursor - 1] == ("symbol", "]")
    ):
        closing_cursor = attribute_cursor - 1
        opening_cursor = close_to_open.get(closing_cursor)
        if (
            opening_cursor is None
            or opening_cursor == 0
            or tokens[opening_cursor - 1] != ("symbol", "#")
        ):
            break
        attribute_name = _token_name(tokens[opening_cursor + 1])
        if attribute_name == "path":
            return True
        if attribute_name == "cfg_attr":
            for cursor in range(opening_cursor + 2, closing_cursor):
                if (
                    _token_name(tokens[cursor]) == "path"
                    and _token_is(tokens, cursor + 1, "symbol", "=")
                ):
                    return True
        attribute_cursor = opening_cursor - 1
    return False


def _token_scopes(
    tokens: list[tuple[str, str]], module_openings: set[int]
) -> tuple[list[int], list[tuple[int | None, bool, int]]] | None:
    scopes: list[tuple[int | None, bool, int]] = [(None, True, 0)]
    scope_at = [0] * len(tokens)
    stack = [0]
    for cursor, token in enumerate(tokens):
        scope_at[cursor] = stack[-1]
        if token == ("symbol", "{"):
            parent = stack[-1]
            is_module = cursor in module_openings
            scope_id = len(scopes)
            module_id = scope_id if is_module else scopes[parent][2]
            scopes.append((parent, is_module, module_id))
            stack.append(scope_id)
        elif token == ("symbol", "}"):
            if len(stack) == 1:
                return None
            stack.pop()
    if len(stack) != 1:
        return None
    return scope_at, scopes


def _declaration_is_cfg_conditioned(
    tokens: list[tuple[str, str]],
    declaration_cursor: int,
    close_to_open: dict[int, int],
) -> bool:
    attribute_cursor = declaration_cursor
    if (
        attribute_cursor > 0
        and tokens[attribute_cursor - 1] == ("symbol", ")")
    ):
        opening_cursor = close_to_open.get(attribute_cursor - 1)
        if (
            opening_cursor is not None
            and opening_cursor > 0
            and _token_name(tokens[opening_cursor - 1]) == "pub"
        ):
            attribute_cursor = opening_cursor - 1
    elif (
        attribute_cursor > 0
        and _token_name(tokens[attribute_cursor - 1]) == "pub"
    ):
        attribute_cursor -= 1

    conditioned = False
    while (
        attribute_cursor > 0
        and tokens[attribute_cursor - 1] == ("symbol", "]")
    ):
        opening_cursor = close_to_open.get(attribute_cursor - 1)
        if (
            opening_cursor is None
            or opening_cursor == 0
            or tokens[opening_cursor - 1] != ("symbol", "#")
        ):
            break
        attribute_name_cursor = opening_cursor + 1
        if (
            attribute_name_cursor < len(tokens)
            and _token_name(tokens[attribute_name_cursor]) in {"cfg", "cfg_attr"}
        ):
            conditioned = True
        attribute_cursor = opening_cursor - 1
    return conditioned


def _token_is_path_segment(token: tuple[str, str]) -> bool:
    return _token_name(token) is not None


def _safe_std_visible(
    cursor: int,
    scope_at: list[int],
    scopes: list[tuple[int | None, bool, int]],
    module_bindings: set[int],
    lexical_bindings: set[int],
) -> bool:
    scope_id = scope_at[cursor]
    module_id = scopes[scope_id][2]
    if module_id in module_bindings:
        return True
    while scopes[scope_id][2] == module_id:
        if scope_id in lexical_bindings:
            return True
        parent = scopes[scope_id][0]
        if parent is None:
            break
        scope_id = parent
    return False


def _direct_forbidden_std_path(
    tokens: list[tuple[str, str]],
    consumed: list[bool],
    macro_mask: list[bool],
    macro_special_crate_group_mask: list[bool],
    scope_at: list[int],
    scopes: list[tuple[int | None, bool, int]],
    module_bindings: set[int],
    lexical_bindings: set[int],
) -> bool:
    for cursor, token in enumerate(tokens):
        if consumed[cursor] or _token_name(token) != "std":
            continue
        if not _token_is(tokens, cursor + 1, "symbol", "::"):
            continue
        absolute = cursor > 0 and _token_is(
            tokens, cursor - 1, "symbol", "::"
        )
        if absolute:
            if cursor >= 2 and _token_is_path_segment(tokens[cursor - 2]):
                continue
        child_cursor = cursor + 2
        if (
            child_cursor < len(tokens)
            and _token_name(tokens[child_cursor]) in _FORBIDDEN_STD_CHILDREN
        ):
            if not absolute and macro_special_crate_group_mask[cursor]:
                continue
            if absolute or macro_mask[cursor] or not _safe_std_visible(
                cursor,
                scope_at,
                scopes,
                module_bindings,
                lexical_bindings,
            ):
                return True
    return False


def _forbidden_io_socket_path_surface(source: str) -> bool:
    tokens = _rust_lexer(source)
    if tokens is None:
        return True
    delimiters = _delimiter_pairs(tokens)
    if delimiters is None:
        return True
    open_to_close, close_to_open = delimiters
    if _forbidden_output_macro_invocation(tokens, open_to_close):
        return True
    macro_mask = _macro_token_mask(tokens, open_to_close)
    macro_special_crate_group_mask = _macro_special_crate_group_mask(
        tokens, macro_mask, open_to_close
    )
    if _macro_metavariable_forbidden_path(
        tokens,
        macro_mask,
        open_to_close,
        macro_special_crate_group_mask,
    ):
        return True
    module_openings = _module_openings(tokens, macro_mask)
    if module_openings is None:
        return True
    scope_state = _token_scopes(tokens, module_openings)
    if scope_state is None:
        return True
    scope_at, scopes = scope_state
    consumed = [False] * len(tokens)
    module_bindings: set[int] = set()
    lexical_bindings: set[int] = set()
    cursor = 0
    while cursor < len(tokens):
        parsed: tuple[int, bool, bool] | None = None
        relevant = False
        if _token_is(tokens, cursor, "keyword", "use"):
            relevant = True
            parsed = _parse_use_declaration(tokens, cursor)
        elif _token_is(tokens, cursor, "keyword", "extern") and _token_is(
            tokens, cursor + 1, "keyword", "crate"
        ):
            relevant = True
            parsed = _parse_extern_crate(tokens, cursor)
        elif _token_is(tokens, cursor, "keyword", "mod"):
            relevant = True
            mod_parsed = _parse_mod_declaration(tokens, cursor)
            if mod_parsed is not None:
                if _module_has_path_override(
                    tokens, cursor, close_to_open
                ):
                    return True
                end_cursor, binds_safe_std, _ = mod_parsed
                parsed = end_cursor, False, binds_safe_std
        if parsed is None:
            if relevant:
                if not macro_mask[cursor]:
                    return True
                if (
                    tokens[cursor] in {
                        ("keyword", "use"),
                        ("keyword", "extern"),
                    }
                    and _macro_incomplete_declaration_has_metavariable(
                        tokens, cursor, macro_mask
                    )
                ):
                    return True
            cursor += 1
            continue
        end_cursor, forbidden, binds_safe_std = parsed
        for consumed_cursor in range(cursor, end_cursor):
            consumed[consumed_cursor] = True
        if forbidden:
            return True
        if (
            binds_safe_std
            and not macro_mask[cursor]
            and not _declaration_is_cfg_conditioned(
                tokens, cursor, close_to_open
            )
        ):
            scope_id = scope_at[cursor]
            if scopes[scope_id][1]:
                module_bindings.add(scopes[scope_id][2])
            else:
                lexical_bindings.add(scope_id)
        cursor = end_cursor
    return _direct_forbidden_std_path(
        tokens,
        consumed,
        macro_mask,
        macro_special_crate_group_mask,
        scope_at,
        scopes,
        module_bindings,
        lexical_bindings,
    )


def _forbidden_in_physical_sources(sources: list[str]) -> bool:
    return any(_forbidden_io_socket_path_surface(source) for source in sources)


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _package_blocks(lock_text: str) -> list[str]:
    return [block for block in lock_text.split("[[package]]") if block.strip()]


def _lock_package(lock_text: str, name: str, version: str) -> str:
    matches = [
        block
        for block in _package_blocks(lock_text)
        if re.search(rf'^name = "{re.escape(name)}"$', block, re.MULTILINE)
        and re.search(rf'^version = "{re.escape(version)}"$', block, re.MULTILINE)
    ]
    assert len(matches) == 1, f"locked package identity is not unique: {name} {version}"
    return matches[0]


def _lock_checksum(lock_text: str, name: str, version: str) -> str:
    block = _lock_package(lock_text, name, version)
    assert f'source = "{CRATES_IO_SOURCE}"' in block
    match = re.search(r'^checksum = "([0-9a-f]{64})"$', block, re.MULTILINE)
    assert match is not None, f"missing registry checksum: {name} {version}"
    return match.group(1)


def test_exact_workspace_and_private_library_manifest() -> None:
    assert MANIFEST.is_file()
    workspace = (RUST / "Cargo.toml").read_text(encoding="utf-8")
    manifest = MANIFEST.read_text(encoding="utf-8")

    assert workspace.count('"openclaw_alr_fit_verifier"') == 1
    assert "ed25519-dalek" not in workspace
    assert "base64" not in workspace

    required_manifest_literals = (
        'name = "openclaw_alr_fit_verifier"',
        "publish = false",
        "build = false",
        "autobins = false",
        "autoexamples = false",
        "autobenches = false",
        "autotests = false",
        "[lib]",
        'path = "src/lib.rs"',
        "[[test]]",
        'name = "strict_verifier_contract"',
        'path = "tests/strict_verifier_contract.rs"',
        'base64 = { version = "=0.22.1", default-features = false }',
        'ed25519-dalek = { version = "=2.2.0", default-features = false }',
        'sha2 = { version = "=0.10.9", default-features = false }',
        'serde_json = "=1.0.149"',
    )
    for literal in required_manifest_literals:
        assert literal in manifest
    assert "[features]" not in manifest
    assert "workspace = true" not in manifest
    substitution_header = re.compile(
        r"(?m)^\s*\[(?:patch(?:\.[^\]]+)?|replace)\]\s*$"
    )
    assert substitution_header.search(workspace) is None
    assert substitution_header.search(manifest) is None


def test_exact_first_party_file_and_target_surface() -> None:
    actual = {
        path.relative_to(CRATE).as_posix()
        for path in CRATE.rglob("*.rs")
        if path.is_file()
    }
    assert actual == EXPECTED_RUST_FILES
    for forbidden in (
        CRATE / "build.rs",
        CRATE / "src" / "main.rs",
        CRATE / "examples",
        CRATE / "benches",
        CRATE / "bin",
    ):
        assert not forbidden.exists()


def test_first_party_source_is_unsafe_io_and_signing_free() -> None:
    lib = (CRATE / "src" / "lib.rs").read_text(encoding="utf-8")
    source = _source_text()
    assert "#![forbid(unsafe_code)]" in lib
    assert "#![deny(missing_debug_implementations)]" in lib
    assert "#![allow(unsafe_code)]" not in source
    assert re.search(r"\bunsafe\s*(?:\{|fn\b|impl\b|trait\b)", source) is None
    for pattern in FORBIDDEN_SOURCE_PATTERNS:
        assert re.search(pattern, source, re.IGNORECASE) is None, pattern
    physical_sources = [
        path.read_text(encoding="utf-8")
        for path in sorted((CRATE / "src").glob("*.rs"))
    ]
    assert not _forbidden_in_physical_sources(physical_sources)

    assert "VerifyingKey::from_bytes" in source
    assert "Signature::from_bytes" in source
    assert "verify_strict" in source


def test_public_contract_and_unattested_ceiling_literals_exist() -> None:
    source = _source_text()
    required = (
        "verify_unattested_phase_v1",
        "VerifiedSignatureJobV1",
        "UnattestedVerificationReceiptV1",
        "ALR_TRUSTED_FIT_HANDSHAKE_SIGNING",
        "ALR_TRUSTED_FIT_REQUEST_V1",
        "ALR_ISOLATED_FIT_TERMINAL_RECEIPT_V1",
        "ALR_V159_INNER_FIT_RECEIPT_V1",
        "alr_fit_ed25519_verification_receipt_v1",
        "STRICT_SIGNATURES_VALID_INPUT_BINDINGS_CAPABILITY_UNATTESTED",
        "SOURCE_ONLY_UNATTESTED",
        "NOT_ESTABLISHED",
        "ed25519_dalek_2.2.0_verify_strict_zip215",
        "semantic_phase_established",
        "canonical_input_bytes_established",
        "envelope_payload_binding_established",
        "policy_overlay_adjudication_established",
        "trusted_time_established",
        "platform_attested",
        "coordinator_eligible",
        "durable_consumption_established",
        "persistence_allowed",
        "training_allowed",
        "authority_granted",
        "TrustPolicySnapshot",
        "KeyStatusOverlay",
        "RequestEnvelope",
        "RequestSignedMaterial",
        "SignedStatusEnvelope",
        "SignedStatusSignedMaterial",
        "OuterTerminalEnvelope",
        "OuterTerminalSignedMaterial",
        "V159InnerEnvelope",
        "V159InnerSignedMaterial",
    )
    for literal in required:
        assert literal in source
    for forbidden in (
        "AlrFitEd25519VerificationReceiptV1",
        "Envelope(SignatureRoleV1)",
        "SignedMaterial(SignatureRoleV1)",
        "attest_receipt",
        "verify_and_attest",
        "platform_attested: true",
    ):
        assert forbidden not in source

    for type_name in (
        "VerifiedSignatureJobV1",
        "UnattestedVerificationReceiptV1",
        "UnattestedVerificationOutputV1",
    ):
        declaration = re.search(
            rf"(?P<prefix>(?:#\[[^\n]+\]\s*)*)pub struct {type_name}\s*\{{(?P<body>.*?)\n\}}",
            source,
            re.DOTALL,
        )
        assert declaration is not None
        assert "Clone" not in declaration.group("prefix")
        assert re.search(r"(?m)^\s*pub(?:\([^)]*\))?\s+", declaration.group("body")) is None
    assert re.search(r"pub\s+fn\s+(?:new|builder|deserialize)\b", source) is None
    assert re.search(r"pub\s+fn\s+\w+_mut\b", source) is None
    assert "impl Default for VerifiedSignatureJobV1" not in source
    assert "impl Default for UnattestedVerificationReceiptV1" not in source


def test_forbidden_io_socket_path_alias_fixture_matrix_is_detected() -> None:
    forbidden = (
        "use std;",
        "use ::std;",
        "use {std};",
        "use std::{self};",
        "use {std::{self}};",
        "extern crate std;",
        "fn probe() { print!(\"x\"); }",
        "fn probe() { println!(\"x\"); }",
        "fn probe() { eprint!(\"x\"); }",
        "fn probe() { eprintln!(\"x\"); }",
        "fn probe() { let _ = dbg!(1); }",
        "fn probe() { std::print!(\"x\"); std::println!(\"x\"); }",
        "fn probe() { std::eprint!(\"x\"); std::eprintln!(\"x\"); }",
        "fn probe() { let _ = std::dbg!(1); }",
        "#[path = \"../../effectful.rs\"] mod injected;",
        "#[path = r#\"../../effectful.rs\"#] pub(crate) mod injected;",
        "#[allow(dead_code)] #[path = \"/tmp/effectful.rs\"] pub mod injected;",
        "#[cfg_attr(all(), path = \"../../effectful.rs\")] mod injected;",
        "#[cfg_attr(all(), path = r#\"../../effectful.rs\"#)] pub(crate) mod injected;",
        "use std::println as emit; fn probe() { emit!(\"x\"); }",
        (
            "use std::{eprintln as emit_error, dbg as inspect}; "
            "fn probe() { emit_error!(\"x\"); let _ = inspect!(1); }"
        ),
        "pub(crate) use ::std::print as emit;",
        "pub use ::std::{eprint as emit_error, println as emit_line};",
        "use r#std::r#eprintln as emit; fn probe() { emit!(\"x\"); }",
        (
            "mod bridge { pub use std::dbg as inspect; } "
            "use bridge::inspect as examine; fn probe() { let _ = examine!(1); }"
        ),
        "use std::io::Read;",
        "use ::std::net::TcpStream;",
        "use std::path::{Path, PathBuf};",
        "use std::os::unix::net::UnixStream;",
        "use std::os::unix::fd::RawFd;",
        "use std::os::windows::fs::OpenOptionsExt;",
        "use std::os::windows::io::RawHandle;",
        "use std::{io::{Read, Write}, error::Error};",
        "use std::{\n    net::TcpStream,\n    fmt,\n};",
        "use std::{os::{unix::{net::UnixStream, fd::RawFd}}, fmt};",
        "use std::os as local_os; use local_os::unix::net::UnixStream;",
        "use std::os::unix as local_unix; use local_unix::net::UnixStream;",
        "use std::os::fd as local_fd; use local_fd::RawFd;",
        "use std::os::windows as local_windows; use local_windows::io::RawHandle;",
        "use std::os::{unix::net::UnixStream};",
        "use std::os::{windows::{fs::OpenOptionsExt, io::RawHandle}};",
        "use std::{os as local_os}; use local_os::unix::fd::RawFd;",
        "use std::{net as local_net}; use local_net::TcpStream;",
        "use std::{path as local_path}; use local_path::Path;",
        "use std::{self as platform}; platform::net::TcpStream;",
        "pub use std as platform_std; platform_std::env::var;",
        "pub(crate) use std as platform_std; platform_std::net::TcpStream;",
        "pub use ::std as platform_std; platform_std::path::Path;",
        "use {std as platform_std}; platform_std::io::Read;",
        "pub(crate) use {std as platform_std}; platform_std::fs::File;",
        "#[allow(unused_imports)]\npub(crate) use ::std as platform_std;\nplatform_std::process::Command;",
        "#![allow(unused_imports)]\npub use {std as platform_std};\nplatform_std::os::unix::net::UnixStream;",
        "use {foo::{bar}, std as platform_std}; platform_std::net::TcpStream;",
        "use {std as platform_std, foo::{bar}}; platform_std::fs::File;",
        "use {foo::{bar}, ::std as platform_std, qux::{baz}}; platform_std::io::Read;",
        "use {\n    foo::{bar, baz},\n    std as platform_std,\n}; platform_std::path::Path;",
        "use {alpha::{beta}, std as platform_std, omega::{gamma}}; platform_std::env::var;",
        "use {left::{right}, ::std as platform_std}; platform_std::process::Command;",
        "use {std as platform_std, unix_like::{thing}}; platform_std::os::unix::net::UnixStream;",
        "use std as platform_std;",
        "extern crate std as platform_std;",
        "use std as platform_std; platform_std::io::stdin();",
        "use std as platform_std; use platform_std::{path::Path, fmt};",
        "extern crate std as platform_std; platform_std::net::TcpStream;",
        "use std::io as local_io; use local_io::Read;",
        "use std::{io as local_io}; use local_io::Read;",
        "use r#std as platform_std; platform_std::net::TcpStream;",
        "use r#std as r#platform_std; r#platform_std::fs::File;",
        "use {core::{fmt}, r#std as platform_std}; platform_std::io::Read;",
        "use std as 平台; 平台::path::Path;",
        "use std/**/as platform_std; platform_std::process::Command;",
        "use std as/**/platform_std; platform_std::io::stdin;",
        "use/**/std/**/as/**/platform_std; platform_std::env::var;",
        "use std // line gap\nas platform_std; platform_std::net::TcpStream;",
        "use std/* outer /* inner */ tail */as platform_std; platform_std::fs::File;",
        "use {core::{fmt}, std /* gap */ as platform_std}; platform_std::path::Path;",
        "extern crate std as r#platform_std; r#platform_std::net::TcpStream;",
        "extern crate r#std as platform_std; platform_std::fs::File;",
        "extern/**/crate/**/r#std/**/as/**/平台; 平台::process::Command;",
        "use std::*; net::TcpStream;",
        "use ::std::*; fs::File;",
        "use std::{*}; path::Path;",
        "use {std::*}; process::Command;",
        "use {core::{fmt}, std::*}; io::stdin;",
        "use {std::{net::TcpStream}, core::fmt};",
        "use std::{path::{Path}};",
        "use {core::{fmt}, ::std::{process::{Command}}};",
        "use {std::{self as platform_std}}; platform_std::net::TcpStream;",
        "use {core::{fmt}, std::{self as r#platform_std}}; r#platform_std::io::stdin;",
        "use std::{self as 平台}; 平台::process::Command;",
        "r#std::r#net::TcpStream;",
        "std/**/::/**/fs/**/::File;",
        "const TEXT: &str = \"/* not a comment\"; use std as platform_std; platform_std::net::TcpStream;",
        "const TEXT: &str = r#\"// not a comment\"#; use r#std::*;",
        "/* unterminated block comment",
        "\"unterminated ordinary string",
        "r###\"unterminated raw string\"##",
        "b'unterminated byte character",
        "use std::{net::TcpStream;",
        "use std::net::TcpStream",
        "extern crate std as ;",
        "extern crate std as platform_std",
        "x" * 1_048_577,
        ";" * 262_145,
        "/*" * 129 + "*/" * 129,
        "r" + "#" * 129 + "\"safe\"" + "#" * 129,
        "use " + "foo::{" * 129 + "bar" + "}" * 129 + ";",
        (
            "extern crate std; use crate::std as platform; "
            "fn f() { let _: Option<platform::net::TcpStream> = None; }"
        ),
        (
            "extern crate std; use self::std as platform; "
            "fn f() { let _: Option<platform::io::Error> = None; }"
        ),
        (
            "mod outer { extern crate std; use super::std as platform; "
            "fn f() { let _: Option<platform::fs::File> = None; } }"
        ),
        (
            "extern crate std; use {crate::std as platform}; "
            "fn f() { let _: Option<platform::path::PathBuf> = None; }"
        ),
        (
            "extern crate std; use crate::{std::{self as platform}}; "
            "fn f() { let _: Option<platform::process::Command> = None; }"
        ),
        (
            "mod foo { pub mod net { pub struct TcpStream; } } "
            "fn local() { use foo as std; let _: Option<std::net::TcpStream> = None; } "
            "fn external() { let _: Option<std::net::TcpStream> = None; }"
        ),
        (
            "mod foo { pub mod net { pub struct TcpStream; } } "
            "use foo as std; mod child { fn f() { "
            "let _: Option<std::net::TcpStream> = None; } }"
        ),
        (
            "mod foo { pub mod net { pub struct TcpStream; } } "
            "mod left { use crate::foo as std; } "
            "mod right { fn f() { let _: Option<std::net::TcpStream> = None; } }"
        ),
        (
            "mod foo { pub mod net { pub struct TcpStream; } } use foo as std; "
            "fn f() { let _: Option<::std::net::TcpStream> = None; }"
        ),
        (
            "macro_rules! bind { () => { use foo as std; }; } "
            "fn f() { let _: Option<std::net::TcpStream> = None; }"
        ),
        (
            "tokens! { use foo as std; } "
            "fn f() { let _: Option<std::net::TcpStream> = None; }"
        ),
        (
            "tokens!(extern crate self as std); "
            "fn f() { let _: Option<std::net::TcpStream> = None; }"
        ),
        (
            "stringify!(mod std); "
            "fn f() { let _: Option<std::net::TcpStream> = None; }"
        ),
        "stringify!(std::net::TcpStream);",
        (
            "macro_rules! root_alias { () => {{ use std as platform; "
            "let _: Option<platform::net::TcpStream> = None; }}; } "
            "fn probe() { root_alias!(); }"
        ),
        (
            "macro_rules! root_glob { () => {{ use std::*; "
            "let _: Option<net::TcpStream> = None; }}; } "
            "fn probe() { root_glob!(); }"
        ),
        (
            "macro_rules! extern_alias { () => {{ extern crate std as platform; "
            "let _: Option<platform::fs::File> = None; }}; } "
            "fn probe() { extern_alias!(); }"
        ),
        (
            "macro_rules! root_alias { ($root:ident) => {{ use $root as platform; "
            "let _: Option<platform::net::TcpStream> = None; }}; } "
            "fn probe() { root_alias!(std); }"
        ),
        (
            "macro_rules! root_glob { ($root:ident) => {{ use $root::*; "
            "let _: Option<net::TcpStream> = None; }}; } "
            "fn probe() { root_glob!(std); }"
        ),
        (
            "macro_rules! extern_alias { ($root:ident) => {{ "
            "extern crate $root as platform; "
            "let _: Option<platform::fs::File> = None; }}; } "
            "fn probe() { extern_alias!(std); }"
        ),
        (
            "macro_rules! direct_children { ($root:ident) => {{ "
            "let _: Option<$root::env::Args> = None; "
            "let _: Option<$root::fs::File> = None; "
            "let _: Option<$root::io::Error> = None; "
            "let _: Option<$root::net::TcpStream> = None; "
            "let _: Option<$root::path::PathBuf> = None; "
            "let _: Option<$root::process::Command> = None; "
            "let _: Option<$root::os::unix::net::UnixStream> = None; "
            "}}; } fn probe() { direct_children!(std); }"
        ),
        (
            "macro_rules! grouped_children { ($root:ident) => {{ "
            "use $root::{env, fs, io, net, os, path, process}; "
            "let _ = core::mem::size_of::<Option<net::TcpStream>>(); "
            "}}; } fn probe() { grouped_children!(std); }"
        ),
        (
            "macro_rules! two_parts { ($root:ident, $child:ident) => {{ "
            "let _: Option<$root::$child::TcpStream> = None; }}; } "
            "fn probe() { two_parts!(std, net); }"
        ),
        (
            "macro_rules! child_only { ($child:ident) => {{ "
            "let _: Option<std::$child::TcpStream> = None; }}; } "
            "fn probe() { child_only!(net); }"
        ),
        (
            "macro_rules! call_part { ($root:ident, $child:ident) => {{ "
            "let _ = $root::$child::stdin; }}; } "
            "fn probe() { call_part!(std, io); }"
        ),
        (
            "macro_rules! grouped_parts { ($root:ident, $child:ident) => {{ "
            "use $root::{$child::TcpStream}; }}; } "
            "fn probe() { grouped_parts!(std, net); }"
        ),
        (
            "macro_rules! grouped_child { ($child:ident) => {{ "
            "use std::{$child::TcpStream}; }}; } "
            "fn probe() { grouped_child!(net); }"
        ),
        (
            "mod foo { pub mod net { pub struct TcpStream; } } "
            "#[cfg(any())] use foo as std; fn probe() { "
            "let _: Option<std::net::TcpStream> = None; }"
        ),
        (
            "mod foo { pub mod net { pub struct TcpStream; } } fn probe() { "
            "#[cfg(any())] use crate::foo as std; "
            "let _: Option<std::net::TcpStream> = None; }"
        ),
        (
            "#[cfg(any())] mod std { pub mod net { pub struct TcpStream; } } "
            "fn probe() { let _: Option<std::net::TcpStream> = None; }"
        ),
        (
            "#[cfg(any())] extern crate self as std; "
            "fn probe() { let _: Option<std::net::TcpStream> = None; }"
        ),
        (
            "mod foo { pub mod net { pub struct TcpStream; } } "
            "#[allow(unused_imports)] #[cfg(any())] pub(crate) use foo as std; "
            "fn probe() { let _: Option<std::net::TcpStream> = None; }"
        ),
        (
            "mod foo { pub mod net { pub struct TcpStream; } } "
            "#[cfg_attr(all(), cfg(any()))] pub use foo as std; "
            "fn probe() { let _: Option<std::net::TcpStream> = None; }"
        ),
        "#[cfg(any())] use std as platform;",
        "#[cfg(any())] use std::*;",
        "#[cfg(any())] extern crate std as platform;",
    )
    for fixture in forbidden:
        assert _forbidden_io_socket_path_surface(fixture), fixture


def test_allowed_std_surface_fixture_matrix_is_not_overblocked() -> None:
    allowed = (
        "use core::fmt;",
        "impl std::error::Error for ClosedError {}",
        "use std::error::Error;",
        "use std::{error::Error, fmt};",
        "pub use std::error::Error;",
        "#[allow(unused_imports)] pub(crate) use ::std::error::Error;",
        "use foo::{std as platform_std}; platform_std::net::TcpStream;",
        "use {foo::{std as platform_std}}; platform_std::path::Path;",
        "use {foo::{bar, std as platform_std}, qux::{baz}}; platform_std::env::var;",
        "use {foo::{std as platform_std}, qux::{bar, baz}}; platform_std::process::Command;",
        "use core::{fmt, convert::TryFrom};",
        "use r#std::error::Error;",
        "use foo::{r#std as r#platform_std}; r#platform_std::net::TcpStream;",
        "use foo::{std as 平台}; 平台::path::Path;",
        "use foo::{std::{net}}; net::TcpStream;",
        "use std::collections;",
        "use std::{collections, error::Error};",
        "const TEXT: &str = \"use std as platform_std; /* //\";",
        "const TEXT: &str = \"escaped quote: \\\" use std::*\";",
        "const TEXT: &str = r\"use std as platform_std;\";",
        "const TEXT: &str = r###\"use r#std::*; \"###;",
        "const TEXT: &[u8] = b\"use std::net\";",
        "const TEXT: &[u8] = br##\"use std::*\"##;",
        "const TEXT: &core::ffi::CStr = c\"use std::path\";",
        "const TEXT: &core::ffi::CStr = cr##\"use std::process\"##;",
        "const CHARACTER: char = '/'; const ESCAPED: char = '\\'';",
        "const BYTE: u8 = b'/'; const ESCAPED_BYTE: u8 = b'\\'';",
        "fn lifetime<'a>(value: &'a str) -> &'a str { 'label: loop { break 'label value; } }",
        "// use std as platform_std; platform_std::net::TcpStream;\nuse core::fmt;",
        "/* use std::*; /* nested use r#std as x; */ */ use std::error::Error;",
        "const TEXT: &str = \"/*\"; // safe line comment\nuse std::error::Error;",
        "const TEXT: &str = \"//\"; use core::fmt;",
        "/*" * 128 + "*/" * 128 + " use core::fmt;",
        ";" * 262_144,
        "const TEXT: &str = r" + "#" * 128 + "\"safe\"" + "#" * 128 + ";",
        "use " + "foo::{" * 128 + "bar" + "}" * 128 + ";",
        (
            "mod foo { pub mod net { pub struct TcpStream; } } use foo as std; "
            "fn f() { let _: Option<std::net::TcpStream> = None; }"
        ),
        (
            "mod foo { pub mod net { pub struct TcpStream; } } use foo as r#std; "
            "fn f() { let _: Option<r#std::net::TcpStream> = None; }"
        ),
        (
            "mod foo { pub mod std { pub mod net { pub struct TcpStream; } } } "
            "use foo::std; fn f() { let _: Option<std::net::TcpStream> = None; }"
        ),
        (
            "mod foo { pub mod std { pub mod net { pub struct TcpStream; } } } "
            "use foo::{std}; fn f() { let _: Option<std::net::TcpStream> = None; }"
        ),
        (
            "mod foo { pub mod net { pub struct TcpStream; } } "
            "use std::collections as std; fn f() { let _: Option<std::net::TcpStream> = None; }"
        ),
        (
            "mod foo { pub mod net { pub struct TcpStream; } } "
            "fn before() { let _: Option<std::net::TcpStream> = None; } use foo as std;"
        ),
        (
            "mod foo { pub mod net { pub struct TcpStream; } } fn f() { "
            "use crate::foo as std; let _: Option<std::net::TcpStream> = None; "
            "{ let _: Option<std::net::TcpStream> = None; } }"
        ),
        (
            "mod foo { pub mod net { pub struct TcpStream; } } fn f() { "
            "let _: std::net::TcpStream = crate::foo::net::TcpStream; "
            "use crate::foo as std; }"
        ),
        (
            "mod foo { pub mod net { pub struct TcpStream; } } fn f() { "
            "{ let _: std::net::TcpStream = crate::foo::net::TcpStream; } "
            "use crate::foo as std; }"
        ),
        (
            "mod foo { pub mod net { pub struct TcpStream; } } mod child { "
            "use crate::foo as std; fn f() { let _: Option<std::net::TcpStream> = None; } }"
        ),
        "extern crate self as current_crate;",
        (
            "pub mod net { pub struct TcpStream; } extern crate self as std; "
            "fn f() { let _: Option<std::net::TcpStream> = None; }"
        ),
        "mod std { pub mod net { pub struct TcpStream; } } fn f() { let _: Option<std::net::TcpStream> = None; }",
        "stringify!(use);",
        "stringify!(use std);",
        "macro_rules! m { (use) => {}; }",
        "macro_rules! metavariable_matcher { ($root:ident) => {}; }",
        "macro_rules! print { () => {}; }",
        "struct Printer; impl Printer { fn print(&self) {} } fn probe(value: &Printer) { value.print(); }",
        "const TEXT: &str = \"print!(\\\"x\\\"); #[path = \\\"x.rs\\\"] mod hidden;\";",
        "// println!(\"x\"); #[path = \"x.rs\"] mod hidden;\nmod visible {}",
        "#[allow(dead_code)] mod ordinary {}",
        "#[cfg(any())] mod disabled;",
        "use local::println as emit; fn probe() { emit!(\"x\"); }",
        (
            "pub mod net { pub struct TcpStream; } macro_rules! local_direct { "
            "() => {{ let _: Option<$crate::net::TcpStream> = None; }}; } "
            "fn probe() { local_direct!(); }"
        ),
        (
            "pub mod net { pub struct TcpStream; } macro_rules! local_group { "
            "() => {{ use $crate::{net::TcpStream}; "
            "let _: Option<TcpStream> = None; }}; } "
            "fn probe() { local_group!(); }"
        ),
        (
            "pub mod std { pub mod net { pub struct TcpStream; } } "
            "macro_rules! local_std_group { () => {{ "
            "use $crate::{std::net::TcpStream}; "
            "let _: Option<TcpStream> = None; }}; } "
            "fn probe() { local_std_group!(); }"
        ),
        (
            "pub mod local_net { pub struct TcpStream; } "
            "macro_rules! crate_child { ($child:ident) => {{ "
            "let _: Option<$crate::$child::TcpStream> = None; }}; } "
            "fn probe() { crate_child!(local_net); }"
        ),
        (
            "pub mod local { pub mod net { pub struct TcpStream; } } "
            "macro_rules! nonroot_child { ($child:ident) => {{ "
            "let _: Option<local::$child::TcpStream> = None; }}; } "
            "fn probe() { nonroot_child!(net); }"
        ),
        (
            "pub mod local_net { pub struct TcpStream; } "
            "macro_rules! crate_group_child { ($child:ident) => {{ "
            "use $crate::{$child::TcpStream}; }}; } "
            "fn probe() { crate_group_child!(local_net); }"
        ),
        (
            "mod foo { pub mod net { pub struct TcpStream; } } "
            "#[allow(unused_imports)] pub(crate) use foo as std; "
            "fn f() { let _: Option<std::net::TcpStream> = None; }"
        ),
        (
            "mod foo { pub mod std { pub mod net { pub struct TcpStream; } } } "
            "use crate::foo::std; fn f() { let _: Option<std::net::TcpStream> = None; }"
        ),
        (
            "mod foo { pub mod std { pub mod net { pub struct TcpStream; } } } "
            "use self::foo::std; fn f() { let _: Option<std::net::TcpStream> = None; }"
        ),
        (
            "mod foo { pub mod std { pub mod net { pub struct TcpStream; } } } "
            "mod inner { use super::foo::std; fn f() { "
            "let _: Option<std::net::TcpStream> = None; } }"
        ),
    )
    for fixture in allowed:
        assert not _forbidden_io_socket_path_surface(fixture), fixture

    scanner_source = Path(__file__).read_text(encoding="utf-8")
    scanner_start = scanner_source.index("def _rust_lexer(")
    scanner_end = scanner_source.index("def _normalized(")
    scanner_slice = scanner_source[scanner_start:scanner_end]
    assert "re." not in scanner_slice
    assert "prefix + (" not in scanner_slice

    long_safe_path = "use " + "a::" * 100_000 + "z;"
    start = time.perf_counter()
    assert not _forbidden_io_socket_path_surface(long_safe_path)
    assert time.perf_counter() - start < 3.0

    safe_file = (
        "mod foo { pub mod net { pub struct TcpStream; } } use foo as std; "
        "fn f() { let _: Option<std::net::TcpStream> = None; }"
    )
    forbidden_file = "fn f() { let _: Option<std::net::TcpStream> = None; }"
    assert not _forbidden_in_physical_sources([safe_file])
    assert _forbidden_in_physical_sources([forbidden_file])
    assert _forbidden_in_physical_sources([safe_file, forbidden_file])


def test_lock_has_exact_registry_pins_and_checksums() -> None:
    lock_text = LOCK.read_text(encoding="utf-8")
    for name, (version, _) in DIRECT_DEPENDENCIES.items():
        block = _lock_package(lock_text, name, version)
        if name != "openclaw_alr_fit_verifier":
            assert 'source = "registry+https://github.com/rust-lang/crates.io-index"' in block
            assert re.search(r'^checksum = "[0-9a-f]{64}"$', block, re.MULTILINE)
    for name, version in (
        ("curve25519-dalek", "4.1.3"),
        ("ed25519", "2.2.3"),
        ("signature", "2.2.0"),
    ):
        block = _lock_package(lock_text, name, version)
        assert re.search(r'^checksum = "[0-9a-f]{64}"$', block, re.MULTILINE)


def test_ci_has_online_clean_offline_graph_and_macos_gates() -> None:
    ci = _normalized(CI.read_text(encoding="utf-8"))
    required = (
        "CARGO_TARGET_DIR=target/alr-online cargo test --locked -p openclaw_alr_fit_verifier",
        "CARGO_NET_OFFLINE=true CARGO_TARGET_DIR=target/alr-offline cargo test --locked -p openclaw_alr_fit_verifier",
        "CARGO_NET_OFFLINE=true cargo metadata --locked --offline --format-version 1",
        "python3 tests/structure/test_alr_fit_verifier_source_static.py",
        "python3 -m pytest -q tests/structure/test_alr_fit_verifier_source_static.py",
        "cargo test --locked -p openclaw_alr_fit_verifier",
    )
    for command in required:
        assert command in ci
    assert "github.event_name != 'push'" in ci


def _metadata_from_env() -> dict[str, Any] | None:
    raw_path = os.environ.get("ALR_FIT_VERIFIER_METADATA_JSON")
    if raw_path is None:
        return None
    path = Path(raw_path)
    assert path.is_file()
    return json.loads(path.read_text(encoding="utf-8"))


def _select_verifier_package(metadata: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        package
        for package in metadata["packages"]
        if package["name"] == "openclaw_alr_fit_verifier"
        and package["version"] == "0.1.0"
        and package["source"] is None
        and Path(package["manifest_path"]).resolve() == MANIFEST.resolve()
    ]
    assert len(candidates) == 1
    return candidates[0]


def _workspace_packages_by_name(
    metadata: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for package in metadata["packages"]:
        if package["source"] is not None:
            continue
        assert package["name"] not in result
        result[package["name"]] = package
    return result


def _direct_package_bindings(
    metadata: dict[str, Any], verifier: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    packages = {package["id"]: package for package in metadata["packages"]}
    nodes = {node["id"]: node for node in metadata["resolve"]["nodes"]}
    assert len(packages) == len(metadata["packages"])
    assert len(nodes) == len(metadata["resolve"]["nodes"])
    verifier_node = nodes[verifier["id"]]
    edge_candidates: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for edge in verifier_node["deps"]:
        package = packages[edge["pkg"]]
        edge_candidates.setdefault(package["name"], []).append((edge, package))
    assert set(edge_candidates) == set(DIRECT_DEPENDENCIES)

    result: dict[str, dict[str, Any]] = {}
    for name, (version, kind) in DIRECT_DEPENDENCIES.items():
        assert len(edge_candidates[name]) == 1
        edge, package = edge_candidates[name][0]
        declarations = [
            dependency
            for dependency in verifier["dependencies"]
            if dependency["name"] == name
        ]
        assert len(declarations) == 1
        declaration = declarations[0]
        assert package["name"] == name
        assert package["version"] == version
        assert package["source"] == CRATES_IO_SOURCE
        assert declaration["source"] == CRATES_IO_SOURCE
        assert declaration["req"] == f"={version}"
        assert declaration["kind"] == kind
        assert edge["dep_kinds"] == [{"kind": kind, "target": None}]
        result[name] = {
            "declaration": declaration,
            "edge": edge,
            "package": package,
        }
    return result


def _dependency_closure(metadata: dict[str, Any], root_id: str) -> set[str]:
    nodes = {node["id"]: node for node in metadata["resolve"]["nodes"]}
    assert len(nodes) == len(metadata["resolve"]["nodes"])
    seen: set[str] = set()
    stack = [root_id]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(dep["pkg"] for dep in nodes[current]["deps"])
    return seen


def _package_key(package: dict[str, Any]) -> str:
    return f'{package["name"]}@{package["version"]}'


def _canonical_sort_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _portable_declared_dependency(dependency: dict[str, Any]) -> dict[str, Any]:
    return {
        "features": sorted(dependency["features"]),
        "kind": dependency["kind"] or "normal",
        "name": dependency["name"],
        "optional": dependency["optional"],
        "registry": dependency["registry"],
        "rename": dependency["rename"],
        "requirement": dependency["req"],
        "source": dependency["source"],
        "target_predicate": dependency["target"],
        "uses_default_features": dependency["uses_default_features"],
    }


def _portable_target(target: dict[str, Any]) -> dict[str, Any]:
    return {
        "crate_types": sorted(target["crate_types"]),
        "doc": target["doc"],
        "doctest": target["doctest"],
        "edition": target["edition"],
        "kind": sorted(target["kind"]),
        "name": target["name"],
        "required_features": sorted(target.get("required-features", [])),
        "test": target["test"],
    }


def _assert_no_absolute_paths(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _assert_no_absolute_paths(key)
            _assert_no_absolute_paths(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _assert_no_absolute_paths(child)
    elif isinstance(value, str):
        assert not value.startswith("/")
        assert re.match(r"^[A-Za-z]:[\\/]", value) is None


def _metadata_projection(
    metadata: dict[str, Any],
    closure_ids: set[str],
    lock_checksums: dict[str, str | None],
    build_scripts: set[tuple[str, str]],
    unsafe_packages: set[tuple[str, str]],
) -> dict[str, Any]:
    packages = {package["id"]: package for package in metadata["packages"]}
    nodes = {node["id"]: node for node in metadata["resolve"]["nodes"]}
    assert len(packages) == len(metadata["packages"])
    assert len(nodes) == len(metadata["resolve"]["nodes"])
    keys = {package_id: _package_key(packages[package_id]) for package_id in closure_ids}
    assert len(set(keys.values())) == len(keys)

    package_projection: list[dict[str, Any]] = []
    forward_edges: list[dict[str, Any]] = []
    for package_id in sorted(closure_ids, key=keys.__getitem__):
        package = packages[package_id]
        node = nodes[package_id]
        declared_dependencies = [
            _portable_declared_dependency(dependency)
            for dependency in package["dependencies"]
        ]
        targets = [_portable_target(target) for target in package["targets"]]
        package_projection.append(
            {
                "checksum": lock_checksums[package_id],
                "declared_dependencies": sorted(
                    declared_dependencies, key=_canonical_sort_key
                ),
                "declared_features": {
                    name: sorted(values)
                    for name, values in sorted(package["features"].items())
                },
                "enabled_features": sorted(node["features"]),
                "license": package["license"],
                "name": package["name"],
                "source": (
                    "workspace-root"
                    if package["source"] is None
                    else package["source"]
                ),
                "targets": sorted(targets, key=_canonical_sort_key),
                "version": package["version"],
            }
        )
        for dependency in node["deps"]:
            assert dependency["pkg"] in closure_ids
            assert dependency["dep_kinds"]
            for dependency_kind in dependency["dep_kinds"]:
                assert dependency_kind["kind"] in (None, "dev", "build")
                assert dependency_kind["target"] is None or isinstance(
                    dependency_kind["target"], str
                )
                forward_edges.append(
                    {
                        "dependency_name": dependency["name"],
                        "from": keys[package_id],
                        "kind": dependency_kind["kind"] or "normal",
                        "target_predicate": dependency_kind["target"],
                        "to": keys[dependency["pkg"]],
                    }
                )

    forward_edges.sort(key=_canonical_sort_key)
    reverse_edges = sorted(
        (
            {
                "dependency_name": edge["dependency_name"],
                "dependent": edge["from"],
                "kind": edge["kind"],
                "package": edge["to"],
                "target_predicate": edge["target_predicate"],
            }
            for edge in forward_edges
        ),
        key=_canonical_sort_key,
    )
    projection = {
        "build_script_packages": [
            f"{name}@{version}" for name, version in sorted(build_scripts)
        ],
        "forward_edges": forward_edges,
        "package_count": len(package_projection),
        "packages": package_projection,
        "reverse_edges": reverse_edges,
        "reviewed_advisory_snapshot": [
            {
                "advisory": advisory,
                "disposition": disposition,
                "package": name,
                "version": version,
            }
            for name, version, advisory, disposition in REVIEWED_ADVISORY_SNAPSHOT
        ],
        "root": "openclaw_alr_fit_verifier@0.1.0",
        "schema_version": "alr_fit_verifier_metadata_projection_v1",
        "unsafe_source_packages": [
            f"{name}@{version}" for name, version in sorted(unsafe_packages)
        ],
    }
    _assert_no_absolute_paths(projection)
    return projection


def test_duplicate_registry_names_cannot_redirect_root_or_direct_selection() -> None:
    declarations: list[dict[str, Any]] = []
    direct_packages: list[dict[str, Any]] = []
    direct_edges: list[dict[str, Any]] = []
    for name, (version, kind) in DIRECT_DEPENDENCIES.items():
        package_id = f"registry-good:{name}@{version}"
        declarations.append(
            {
                "kind": kind,
                "name": name,
                "req": f"={version}",
                "source": CRATES_IO_SOURCE,
            }
        )
        direct_packages.append(
            {
                "id": package_id,
                "name": name,
                "source": CRATES_IO_SOURCE,
                "version": version,
            }
        )
        direct_edges.append(
            {
                "dep_kinds": [{"kind": kind, "target": None}],
                "name": name.replace("-", "_"),
                "pkg": package_id,
            }
        )

    root = {
        "dependencies": declarations,
        "id": "workspace-root-id",
        "manifest_path": str(MANIFEST),
        "name": "openclaw_alr_fit_verifier",
        "source": None,
        "version": "0.1.0",
    }
    metadata = {
        "packages": [
            root,
            *direct_packages,
            {
                "id": "registry-decoy-root",
                "manifest_path": "/registry/decoy/Cargo.toml",
                "name": "openclaw_alr_fit_verifier",
                "source": CRATES_IO_SOURCE,
                "version": "0.1.0",
            },
            {
                "id": "registry-decoy-base64",
                "name": "base64",
                "source": "git+https://invalid.example/base64",
                "version": "0.22.1",
            },
        ],
        "resolve": {
            "nodes": [
                {
                    "deps": direct_edges,
                    "id": root["id"],
                }
            ]
        },
    }

    verifier = _select_verifier_package(metadata)
    assert verifier["id"] == "workspace-root-id"
    assert _workspace_packages_by_name(metadata)["openclaw_alr_fit_verifier"][
        "id"
    ] == "workspace-root-id"
    bindings = _direct_package_bindings(metadata, verifier)
    assert bindings["base64"]["package"]["id"] == "registry-good:base64@0.22.1"


def test_offline_metadata_graph_when_supplied() -> None:
    metadata = _metadata_from_env()
    if metadata is None:
        return
    assert metadata["resolve"] is not None
    packages = {package["id"]: package for package in metadata["packages"]}
    assert len(packages) == len(metadata["packages"])
    verifier = _select_verifier_package(metadata)
    workspace_packages = _workspace_packages_by_name(metadata)
    direct_bindings = _direct_package_bindings(metadata, verifier)
    assert verifier["features"] == {}

    assert set(direct_bindings) == set(DIRECT_DEPENDENCIES)
    for name, (version, kind) in DIRECT_DEPENDENCIES.items():
        binding = direct_bindings[name]
        dependency = binding["declaration"]
        package = binding["package"]
        assert package["name"] == name
        assert package["version"] == version
        assert package["source"] == CRATES_IO_SOURCE
        assert dependency["req"] == f"={version}"
        assert dependency["kind"] == kind
        if kind is None:
            assert dependency["uses_default_features"] is False
            assert dependency["features"] == []

    target_kinds = {tuple(target["kind"]) for target in verifier["targets"]}
    assert target_kinds == {("lib",), ("test",)}
    assert all("custom-build" not in target["kind"] for target in verifier["targets"])

    closure_ids = _dependency_closure(metadata, verifier["id"])
    assert len(closure_ids) == EXPECTED_METADATA_CLOSURE_SIZE
    path_package_ids = {
        package_id
        for package_id in closure_ids
        if packages[package_id]["source"] is None
    }
    assert path_package_ids == {verifier["id"]}
    assert Path(verifier["manifest_path"]).resolve() == MANIFEST.resolve()

    lock_text = LOCK.read_text(encoding="utf-8")
    root_block = _lock_package(lock_text, verifier["name"], verifier["version"])
    assert re.search(r'^source = ', root_block, re.MULTILINE) is None
    assert re.search(r'^checksum = ', root_block, re.MULTILINE) is None
    lock_checksums: dict[str, str | None] = {verifier["id"]: None}
    for package_id in closure_ids - {verifier["id"]}:
        package = packages[package_id]
        assert package["source"] == CRATES_IO_SOURCE
        assert isinstance(package["license"], str) and package["license"]
        lock_checksums[package_id] = _lock_checksum(
            lock_text, package["name"], package["version"]
        )
        for dependency in package["dependencies"]:
            assert dependency["source"] == CRATES_IO_SOURCE
    for dependency in verifier["dependencies"]:
        assert dependency["source"] == CRATES_IO_SOURCE

    closure_names = {packages[package_id]["name"] for package_id in closure_ids}
    assert closure_names.isdisjoint(FORBIDDEN_DEPENDENCIES)

    for existing in ("openclaw_core", "openclaw_engine", "openclaw_types"):
        existing_package = workspace_packages[existing]
        assert existing_package["source"] is None
        existing_closure = _dependency_closure(metadata, existing_package["id"])
        existing_names = {packages[package_id]["name"] for package_id in existing_closure}
        assert "openclaw_alr_fit_verifier" not in existing_names
        assert "ed25519-dalek" not in existing_names

    for name in ("base64", "ed25519-dalek", "sha2", "serde_json"):
        package = direct_bindings[name]["package"]
        assert package["source"] == CRATES_IO_SOURCE
        assert package["license"]

    build_scripts = {
        (packages[package_id]["name"], packages[package_id]["version"])
        for package_id in closure_ids
        if any("custom-build" in target["kind"] for target in packages[package_id]["targets"])
    }
    assert build_scripts == EXPECTED_TRANSITIVE_BUILD_SCRIPTS

    unsafe_packages: set[tuple[str, str]] = set()
    for package_id in closure_ids:
        package = packages[package_id]
        manifest = Path(package["manifest_path"])
        if package["source"] is None:
            continue
        if any(
            re.search(r"\bunsafe\b", path.read_text(encoding="utf-8", errors="ignore"))
            for path in manifest.parent.rglob("*.rs")
        ):
            unsafe_packages.add((package["name"], package["version"]))
    assert unsafe_packages == EXPECTED_TRANSITIVE_UNSAFE_PACKAGES

    projection = _metadata_projection(
        metadata,
        closure_ids,
        lock_checksums,
        build_scripts,
        unsafe_packages,
    )
    canonical_projection = json.dumps(
        projection,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    projection_digest = hashlib.sha256(canonical_projection).hexdigest()
    assert projection_digest == EXPECTED_METADATA_PROJECTION_SHA256, (
        f"metadata projection SHA-256 drift: {projection_digest}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata-json", required=True)
    args = parser.parse_args()
    os.environ["ALR_FIT_VERIFIER_METADATA_JSON"] = args.metadata_json
    for check in (
        test_exact_workspace_and_private_library_manifest,
        test_exact_first_party_file_and_target_surface,
        test_first_party_source_is_unsafe_io_and_signing_free,
        test_public_contract_and_unattested_ceiling_literals_exist,
        test_forbidden_io_socket_path_alias_fixture_matrix_is_detected,
        test_allowed_std_surface_fixture_matrix_is_not_overblocked,
        test_lock_has_exact_registry_pins_and_checksums,
        test_ci_has_online_clean_offline_graph_and_macos_gates,
        test_duplicate_registry_names_cannot_redirect_root_or_direct_selection,
        test_offline_metadata_graph_when_supplied,
    ):
        check()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
