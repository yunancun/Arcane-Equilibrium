"""Read-only local docs context retrieval helpers."""

from .retriever import (
    DEFAULT_SOURCE_PATHS,
    INDEX_SCHEMA_VERSION,
    QUERY_SCHEMA_VERSION,
    build_index,
    load_index,
    query_index,
    write_index,
)

__all__ = [
    "DEFAULT_SOURCE_PATHS",
    "INDEX_SCHEMA_VERSION",
    "QUERY_SCHEMA_VERSION",
    "build_index",
    "load_index",
    "query_index",
    "write_index",
]
