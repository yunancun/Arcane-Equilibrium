"""Exact bounded repository projections for active TODO state and task history."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEADING_RE = re.compile(r"^(#{1,6})\s+.+$")
HISTORY_HEADING_RE = re.compile(r"^## [^\r\n]+$")
HISTORY_PATH_RE = re.compile(
    r"^docs/CCAgentWorkSpace/[A-Za-z0-9_-]+/"
    r"(?:memory(?:-archive)?\.md|workspace/reports/(?:[^/]+/)*[^/]+\.md)$"
)
ACTIVE_ID_RE = re.compile(r"\bS2E\.[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*\b")
MAX_HISTORY_REFS = 4
MAX_HISTORY_SECTION_BYTES = 16 * 1024
MAX_HISTORY_TOTAL_BYTES = 32 * 1024


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _markdown_lines(data: bytes) -> list[str]:
    try:
        return data.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError as error:
        raise ValueError("selected Markdown must be UTF-8") from error


def exact_markdown_section(data: bytes, heading: str) -> bytes:
    """Return one exact Markdown heading section, including its heading line."""

    if not isinstance(heading, str) or not HISTORY_HEADING_RE.fullmatch(heading):
        raise ValueError("history_refs heading must be an exact Markdown H2")
    lines = _markdown_lines(data)
    matches = [
        index for index, line in enumerate(lines)
        if line.rstrip("\r\n") == heading
    ]
    if len(matches) != 1:
        raise ValueError("history_refs heading must match exactly one section")
    start = matches[0]
    level = 2
    end = len(lines)
    for index in range(start + 1, len(lines)):
        candidate = HEADING_RE.match(lines[index].rstrip("\r\n"))
        if candidate and len(candidate.group(1)) <= level:
            end = index
            break
    return "".join(lines[start:end]).encode("utf-8")


def _safe_history_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("history_refs path must be a non-empty string")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or value.startswith(("~", "-", "!"))
        or path.as_posix() != value
        or ".." in path.parts
        or any(character in value for character in ("\0", "\n", "\r", "\\", "*", "?", "[", "]", "#"))
        or not HISTORY_PATH_RE.fullmatch(value)
    ):
        raise ValueError("history_refs path is outside the exact role-memory/report allowlist")
    return value


def normalize_history_refs(value: Any) -> list[dict[str, str]]:
    """Validate and canonicalize the task-contract history reference list."""

    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_HISTORY_REFS:
        raise ValueError("history_refs must be a list with at most four entries")
    normalized: list[dict[str, str]] = []
    identities: set[tuple[str, str]] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"path", "heading", "digest"}:
            raise ValueError("history_refs entries require exact path/heading/digest fields")
        path = _safe_history_path(item.get("path"))
        heading = item.get("heading")
        digest = item.get("digest")
        if not isinstance(heading, str) or not HISTORY_HEADING_RE.fullmatch(heading):
            raise ValueError("history_refs heading must be an exact Markdown H2")
        if not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest):
            raise ValueError("history_refs digest must be exact sha256")
        identity = (path, heading)
        if identity in identities:
            raise ValueError("history_refs path/heading identities must be unique")
        identities.add(identity)
        normalized.append({"path": path, "heading": heading, "digest": digest})
    return sorted(normalized, key=lambda item: (item["path"], item["heading"]))


def _safe_repo_file(root: Path, relative: str) -> Path:
    root_resolved = root.resolve()
    cursor = root
    for part in PurePosixPath(relative).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("history_refs path may not traverse a symlink")
    try:
        resolved = (root / relative).resolve(strict=True)
        resolved.relative_to(root_resolved)
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        raise ValueError("history_refs path is missing or outside the repository") from error
    if not resolved.is_file():
        raise ValueError("history_refs path must resolve to a regular file")
    return resolved


def project_history_refs(
    root: Path, refs: list[dict[str, str]],
) -> tuple[dict[str, Any], bytes]:
    """Materialize only digest-bound selected history sections."""

    refs = normalize_history_refs(refs)
    if not refs:
        raise ValueError("history_refs projection requires at least one reference")
    sections: list[dict[str, str]] = []
    aggregate_bytes = 0
    for ref in refs:
        source = _safe_repo_file(root, ref["path"])
        section = exact_markdown_section(source.read_bytes(), ref["heading"])
        if len(section) > MAX_HISTORY_SECTION_BYTES:
            raise ValueError("history_refs selected section exceeds 16KiB")
        aggregate_bytes += len(section)
        if aggregate_bytes > MAX_HISTORY_TOTAL_BYTES:
            raise ValueError("history_refs selected sections exceed 32KiB aggregate")
        if _digest(section) != ref["digest"]:
            raise ValueError("history_refs selected section digest mismatch")
        sections.append({
            **ref,
            "content": section.decode("utf-8"),
        })
    content = {"sections": sections}
    raw = json.dumps(
        content,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return content, raw


def _table_cells(line: str) -> list[str]:
    stripped = line.rstrip("\r\n").strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        raise ValueError("active TODO table row must use leading and trailing pipes")
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def _plain_cell(value: str) -> str:
    return re.sub(r"[*_`]", "", value).strip()


def project_todo_active_rows(data: bytes, spec: dict[str, Any]) -> bytes:
    """Project the unique ACTIVE row and its direct dependency rows."""

    heading = spec.get("heading")
    if not isinstance(heading, str) or not heading:
        raise ValueError("todo_active_rows heading must be exact")
    lines = _markdown_lines(data)
    heading_matches: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line.rstrip("\r\n"))
        if match and line.rstrip("\r\n")[len(match.group(1)):].strip() == heading:
            heading_matches.append((index, len(match.group(1))))
    if len(heading_matches) != 1:
        raise ValueError("todo_active_rows heading must match exactly once")
    start, level = heading_matches[0]
    end = len(lines)
    for index in range(start + 1, len(lines)):
        match = HEADING_RE.match(lines[index].rstrip("\r\n"))
        if match and len(match.group(1)) <= level:
            end = index
            break
    section = lines[start + 1:end]

    tables: list[list[str]] = []
    cursor = 0
    while cursor < len(section):
        if not section[cursor].lstrip().startswith("|"):
            cursor += 1
            continue
        table: list[str] = []
        while cursor < len(section) and section[cursor].lstrip().startswith("|"):
            table.append(section[cursor])
            cursor += 1
        if len(table) >= 2:
            try:
                separator = _table_cells(table[1])
            except ValueError:
                continue
            if separator and all(re.fullmatch(r":?-{3,}:?", cell) for cell in separator):
                tables.append(table)
    if len(tables) != 1:
        raise ValueError("todo_active_rows section must contain exactly one Markdown table")
    table = tables[0]
    headers = _table_cells(table[0])
    required_columns = (
        spec.get("id_column"),
        spec.get("status_column"),
        spec.get("dependency_column"),
    )
    if any(not isinstance(column, str) or headers.count(column) != 1 for column in required_columns):
        raise ValueError("todo_active_rows required columns must each occur exactly once")
    id_index, status_index, dependency_index = (
        headers.index(column) for column in required_columns
    )
    rows: list[tuple[str, list[str], str]] = []
    by_id: dict[str, tuple[str, list[str], str]] = {}
    for raw_line in table[2:]:
        cells = _table_cells(raw_line)
        if len(cells) != len(headers):
            raise ValueError("todo_active_rows table width is inconsistent")
        row_id = _plain_cell(cells[id_index])
        if not row_id or row_id in by_id:
            raise ValueError("todo_active_rows IDs must be non-empty and unique")
        row = (raw_line, cells, row_id)
        rows.append(row)
        by_id[row_id] = row
    active = [
        row for row in rows
        if _plain_cell(row[1][status_index]).upper().startswith("ACTIVE")
    ]
    if len(active) != 1:
        raise ValueError("todo_active_rows requires exactly one ACTIVE row")
    active_row = active[0]
    dependency_ids = ACTIVE_ID_RE.findall(active_row[1][dependency_index])
    missing = sorted(set(dependency_ids) - set(by_id))
    if missing:
        raise ValueError(f"todo_active_rows missing dependency rows: {missing}")
    dependency_rows = [
        row for row in rows if row[2] in set(dependency_ids)
    ]
    selected_lines = [table[0], table[1], *[row[0] for row in dependency_rows], active_row[0]]
    projection = "".join(selected_lines).encode("utf-8")
    if len(projection) > 8 * 1024:
        raise ValueError("todo_active_rows projection exceeds 8KiB")
    return projection


EMPTY_DISPATCH_MARKER = (
    "S2E-DISPATCH-PROJECTION:\n"
    "schema_version=todo_dispatch_projection_v1\n"
    "queue_state=NO_ACTIVE_UNIT\n"
    "active_unit_id=null\n"
    "active_count=0\n"
    "next_candidate=S2E-LW2\n"
    "next_candidate_state=WAITING_FRESH_ADMISSION\n"
    "dispatchable=false\n"
    "next_action=null\n"
)


def project_todo_dispatch_projection(
    data: bytes, spec: dict[str, Any]
) -> dict[str, Any]:
    """Project a legal empty dispatch lane from one exact TODO section."""

    heading = spec.get("heading")
    if not isinstance(heading, str) or not heading:
        raise ValueError("todo_dispatch_projection heading must be exact")
    lines = _markdown_lines(data)
    matches: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line.rstrip("\r\n"))
        if match and line.rstrip("\r\n")[len(match.group(1)):].strip() == heading:
            matches.append((index, len(match.group(1))))
    if len(matches) != 1:
        raise ValueError("todo_dispatch_projection heading must match exactly once")
    start, level = matches[0]
    end = len(lines)
    for index in range(start + 1, len(lines)):
        match = HEADING_RE.match(lines[index].rstrip("\r\n"))
        if match and len(match.group(1)) <= level:
            end = index
            break
    section_lines = lines[start + 1:end]
    section = "".join(section_lines)
    tables: list[list[str]] = []
    cursor = 0
    while cursor < len(section_lines):
        if not section_lines[cursor].lstrip().startswith("|"):
            cursor += 1
            continue
        table: list[str] = []
        while (
            cursor < len(section_lines)
            and section_lines[cursor].lstrip().startswith("|")
        ):
            table.append(section_lines[cursor])
            cursor += 1
        if len(table) >= 2:
            separator = _table_cells(table[1])
            if separator and all(
                re.fullmatch(r":?-{3,}:?", cell) for cell in separator
            ):
                tables.append(table)
    if len(tables) != 1:
        raise ValueError(
            "todo_dispatch_projection section must contain exactly one Markdown table"
        )
    table = tables[0]
    headers = _table_cells(table[0])
    required_columns = (
        spec.get("id_column"),
        spec.get("status_column"),
        spec.get("dependency_column"),
    )
    if any(
        not isinstance(column, str) or headers.count(column) != 1
        for column in required_columns
    ):
        raise ValueError(
            "todo_dispatch_projection required columns must each occur exactly once"
        )
    id_index, status_index, dependency_index = (
        headers.index(column) for column in required_columns
    )
    rows: list[tuple[str, list[str], str]] = []
    by_id: dict[str, tuple[str, list[str], str]] = {}
    for raw_line in table[2:]:
        cells = _table_cells(raw_line)
        if len(cells) != len(headers):
            raise ValueError("todo_dispatch_projection table width is inconsistent")
        row_id = _plain_cell(cells[id_index])
        if not row_id or row_id in by_id:
            raise ValueError(
                "todo_dispatch_projection IDs must be non-empty and unique"
            )
        row = (raw_line, cells, row_id)
        rows.append(row)
        by_id[row_id] = row
    active_rows = [
        row for row in rows
        if _plain_cell(row[1][status_index]).upper().startswith("ACTIVE")
    ]
    marker_count = section.count(EMPTY_DISPATCH_MARKER)
    marker_label_count = section.count("S2E-DISPATCH-PROJECTION:")
    if active_rows and marker_label_count:
        raise ValueError(
            "todo_dispatch_projection EMPTY marker cannot coexist with ACTIVE rows"
        )
    if len(active_rows) > 1:
        raise ValueError("todo_dispatch_projection permits at most one ACTIVE row")
    if not active_rows and marker_count != 1:
        raise ValueError("todo_dispatch_projection EMPTY marker must match exactly once")
    if active_rows:
        active_row = active_rows[0]
        dependency_ids = ACTIVE_ID_RE.findall(active_row[1][dependency_index])
        missing = sorted(set(dependency_ids) - set(by_id))
        if missing:
            raise ValueError(
                f"todo_dispatch_projection missing dependency rows: {missing}"
            )
        dependency_rows = [
            row for row in rows if row[2] in set(dependency_ids)
        ]
        selected_lines = [
            table[0], table[1],
            *[row[0] for row in dependency_rows],
            active_row[0],
        ]
        projection = "".join(selected_lines)
        if len(projection.encode("utf-8")) > 8 * 1024:
            raise ValueError("todo_dispatch_projection projection exceeds 8KiB")
        return {
            "schema_version": "todo_dispatch_projection_v1",
            "projection_state": "ACTIVE",
            "active_rows": [{
                "active_unit_id": active_row[2],
                "content": projection,
            }],
            "active_count": 1,
            "dispatchable": True,
            "next_action": active_row[2],
        }
    return {
        "schema_version": "todo_dispatch_projection_v1",
        "projection_state": "EMPTY",
        "active_rows": [],
        "active_count": 0,
        "dispatchable": False,
        "next_action": None,
    }
