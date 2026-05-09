"""Fast JSON helpers with an orjson fast path and stdlib fallback."""

from __future__ import annotations

import json as _json
from typing import Any, Callable

try:  # pragma: no cover - exercised only when optional wheel is installed
    import orjson as _orjson  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - fallback is covered in local tests
    _orjson = None


JSONDecodeError = ValueError
ORJSON_AVAILABLE = _orjson is not None


def loads(data: str | bytes | bytearray | memoryview) -> Any:
    if _orjson is not None:
        return _orjson.loads(data)
    if isinstance(data, memoryview):
        data = data.tobytes()
    return _json.loads(data)


def dumps(
    value: Any,
    *,
    ensure_ascii: bool = True,
    sort_keys: bool = False,
    separators: tuple[str, str] | None = None,
    default: Callable[[Any], Any] | None = None,
    indent: int | None = None,
) -> str:
    if _should_use_orjson(
        ensure_ascii=ensure_ascii,
        separators=separators,
        indent=indent,
    ):
        return _orjson.dumps(  # type: ignore[union-attr]
            value,
            option=_orjson_options(sort_keys=sort_keys),  # type: ignore[arg-type]
            default=default,
        ).decode("utf-8")
    return _json.dumps(
        value,
        ensure_ascii=ensure_ascii,
        sort_keys=sort_keys,
        separators=separators,
        default=default,
        indent=indent,
    )


def dumps_bytes(
    value: Any,
    *,
    ensure_ascii: bool = True,
    sort_keys: bool = False,
    separators: tuple[str, str] | None = None,
    default: Callable[[Any], Any] | None = None,
    indent: int | None = None,
) -> bytes:
    if _should_use_orjson(
        ensure_ascii=ensure_ascii,
        separators=separators,
        indent=indent,
    ):
        return _orjson.dumps(  # type: ignore[union-attr]
            value,
            option=_orjson_options(sort_keys=sort_keys),  # type: ignore[arg-type]
            default=default,
        )
    return dumps(
        value,
        ensure_ascii=ensure_ascii,
        sort_keys=sort_keys,
        separators=separators,
        default=default,
        indent=indent,
    ).encode("utf-8")


def dumps_line_bytes(
    value: Any,
    *,
    ensure_ascii: bool = False,
    sort_keys: bool = False,
) -> bytes:
    return dumps_bytes(
        value,
        ensure_ascii=ensure_ascii,
        sort_keys=sort_keys,
        separators=(",", ":"),
    ) + b"\n"


def _should_use_orjson(
    *,
    ensure_ascii: bool,
    separators: tuple[str, str] | None,
    indent: int | None,
) -> bool:
    return (
        _orjson is not None
        and not ensure_ascii
        and indent is None
        and separators == (",", ":")
    )


def _orjson_options(*, sort_keys: bool) -> int:
    if _orjson is None:
        return 0
    options = 0
    if sort_keys:
        options |= _orjson.OPT_SORT_KEYS
    return options
