#!/usr/bin/env python3
"""S2.4 §2.1 engine-scanner 靜態 SQL **文字面**規範化與分類葉。

自 ``agent_governance_s2_4_install`` 依 2000 行治理拆分抽出(install 模組逐名
re-export,既有 ``install._classify_sql_statement`` 等匯入面/monkeypatch 縫不變)。
本葉零 I/O、零 effect、零 authority:輸入一條常量 SQL 文字,輸出「語句類別 + 必要
權限 + typed errors」。AST 面(``.execute(...)`` 常量解析)與裁決面留在 install。

W2 recheck 修補的三條真縫(E2):

* **P2-D(已證實的規避)**:``DELETE /*evade*/ FROM …`` 與 ``DELETE --evade\\n FROM …``
  兩種寫法 PG 都照收,但舊的 ``DELETE\\s+FROM`` 掃描要求兩個 token 相鄰,於是整條
  data-modifying CTE 被判成 read、零 error。故**分類前先剝除 SQL 註解**——且必須
  避開字串常量/dollar-quoted body/引號識別子,否則會把資料當註解剝掉。
* **P2-E**:``MERGE``(PG15+;PG17 起可入 CTE)不在 data-modifying 動詞集內。
* **P2-F**:``ON CONFLICT DO UPDATE SET`` 的 ``SET`` 被關聯抽取誤判成關聯名,
  該路徑於是**永遠不可能 PASS**(``unqualified_relation:SET``),未來一條合法語句
  會被以誤導理由攔下。
"""
from __future__ import annotations

import re
from typing import Any

# 進 manifest functions 段的 pg_catalog 家族(PUBLIC-default EXECUTE):advisory-lock
# 三支 + §8.3 在帶身分閘用到的 current_database/current_setting。
ADVISORY_FUNCTION_NAMES = (
    "current_database",
    "current_setting",
    "hashtext",
    "pg_advisory_unlock",
    "pg_try_advisory_lock",
)
_ADVISORY_FUNCTION_RE = re.compile(
    r"\b(current_database|current_setting|hashtext|pg_advisory_unlock"
    r"|pg_try_advisory_lock)\s*\("
)
_QUALIFIED_TABLE_RE = re.compile(r"\b(?:trading|learning)\.[a-z_][a-z0-9_]*")
_INSERT_TARGET_RE = re.compile(
    r"^\s*INSERT\s+INTO\s+((?:trading|learning)\.[a-z_][a-z0-9_]*)", re.IGNORECASE
)
_UPDATE_TARGET_RE = re.compile(
    r"^\s*UPDATE\s+((?:trading|learning)\.[a-z_][a-z0-9_]*)", re.IGNORECASE
)
_DELETE_TARGET_RE = re.compile(
    r"^\s*DELETE\s+FROM\s+((?:trading|learning)\.[a-z_][a-z0-9_]*)", re.IGNORECASE
)
# P2-F:``DO\s+`` 前綴必須被一併吃掉——``ON CONFLICT ... DO UPDATE SET x = 1`` 的
# ``SET`` 不是關聯名。舊 regex 把它當關聯,於是每一條 ON CONFLICT DO UPDATE 都固定
# 產出 unqualified_relation:SET,derive-UPDATE 路徑永遠不可能 PASS。
_RELATION_KEYWORD_RE = re.compile(
    r"\b(?P<conflict>DO\s+)?(?:FROM|JOIN|INTO|UPDATE)\s+(?P<name>[A-Za-z_][A-Za-z0-9_.]*)",
    re.IGNORECASE,
)
_CTE_NAME_RE = re.compile(r"(?:\bWITH\s+|,\s*)([a-z_][a-z0-9_]*)\s+AS\s*\(", re.IGNORECASE)
# W2 P1-B(E3 P1-1)+ P2-E(E2 recheck):data-modifying CTE。第一個 token 分類會把
# ``WITH x AS (DELETE FROM ... RETURNING ...) SELECT ...`` 判成 read,§2.1 的
# 「零 retention mutation / 零 DELETE」在閘口即被繞過。故分類前先全句掃描
# DELETE/UPDATE/INSERT/MERGE/TRUNCATE(含 CTE 內),導出真目標的真權限;read 類語句
# 一旦內含任一 mutation 即 typed 拒絕(必然 fail split 謂詞)。
# ``DO UPDATE`` 是 INSERT 的 ON CONFLICT 子句而非獨立 mutation,單獨在 INSERT 分支
# 導出 UPDATE 權限,故此處以 ``conflict`` 群組辨識並排除。
_EMBEDDED_MUTATION_RE = re.compile(
    r"\b(?P<conflict>DO\s+)?"
    r"(?P<op>DELETE\s+FROM|INSERT\s+INTO|MERGE(?:\s+INTO)?|TRUNCATE(?:\s+TABLE)?|UPDATE)\s+"
    r"(?:ONLY\s+)?(?P<target>[A-Za-z_][A-Za-z0-9_.]*)?",
    re.IGNORECASE,
)
# MERGE 的 WHEN 分支可同時做 INSERT/UPDATE/DELETE,且靜態文字面無法保證只用其中之一;
# 故 fail-closed 導出三者(MERGE 本身在 read 類語句內恆為 typed 違規,不影響 PASS 面)。
_MUTATION_PRIVILEGES: dict[str, frozenset[str]] = {
    "DELETE": frozenset({"DELETE"}),
    "INSERT": frozenset({"INSERT"}),
    "MERGE": frozenset({"DELETE", "INSERT", "UPDATE"}),
    "TRUNCATE": frozenset({"TRUNCATE"}),
    "UPDATE": frozenset({"UPDATE"}),
}


def strip_sql_comments(sql: str) -> str:
    """剝除 SQL 註解(``--`` 到行尾、``/* */`` 含巢狀),字面量內原樣保留。

    P2-D:PG 在 verb 與 ``FROM`` 之間接受任意註解,``DELETE /*evade*/ FROM t`` 與
    ``DELETE --evade\\n FROM t`` 都是合法 DELETE。分類/掃描若吃原文,這兩條會被判成
    read。剝除時必須尊重三種「註解字元不是註解」的語境,否則會反過來破壞資料:

    * 單引號字串常量(``''`` 為轉義,反斜線不特殊——PG 預設 ``standard_conforming_strings``);
    * 雙引號識別子;
    * dollar-quoted body(``$$ ... $$`` / ``$tag$ ... $tag$``)。

    註解一律代換為單一空白(而非刪除),避免 ``DELETE/*x*/FROM`` 被黏成一個 token。
    本函數 idempotent:對已剝除過的字串再跑一次結果不變。
    """

    out: list[str] = []
    index = 0
    length = len(sql)
    while index < length:
        char = sql[index]
        if char == "'":
            end = index + 1
            while end < length:
                if sql[end] == "'":
                    if end + 1 < length and sql[end + 1] == "'":
                        end += 2
                        continue
                    end += 1
                    break
                end += 1
            out.append(sql[index:end])
            index = end
            continue
        if char == '"':
            end = index + 1
            while end < length:
                if sql[end] == '"':
                    if end + 1 < length and sql[end + 1] == '"':
                        end += 2
                        continue
                    end += 1
                    break
                end += 1
            out.append(sql[index:end])
            index = end
            continue
        if char == "$":
            tag = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", sql[index:])
            if tag is not None:
                marker = tag.group(0)
                close = sql.find(marker, index + len(marker))
                end = length if close == -1 else close + len(marker)
                out.append(sql[index:end])
                index = end
                continue
        if sql.startswith("--", index):
            end = sql.find("\n", index)
            out.append(" ")
            index = length if end == -1 else end  # 保留換行本身(行結構不變)
            continue
        if sql.startswith("/*", index):
            depth = 1
            cursor = index + 2
            while cursor < length and depth:
                if sql.startswith("/*", cursor):
                    depth += 1
                    cursor += 2
                elif sql.startswith("*/", cursor):
                    depth -= 1
                    cursor += 2
                else:
                    cursor += 1
            out.append(" ")
            index = cursor
            continue
        out.append(char)
        index += 1
    return "".join(out)


def statement_unqualified_relations(sql: str) -> list[str]:
    """找出未以 trading./learning. 限定、又非 CTE 名的關聯目標(fail-closed)。"""

    sql = strip_sql_comments(sql)
    cte_names = {match.group(1).lower() for match in _CTE_NAME_RE.finditer(sql)}
    violations: list[str] = []
    for match in _RELATION_KEYWORD_RE.finditer(sql):
        # P2-F:``DO UPDATE SET`` 的 SET 是子句關鍵字,不是關聯名。
        if match.group("conflict") is not None:
            continue
        name = match.group("name")
        if "." in name:
            if _QUALIFIED_TABLE_RE.fullmatch(name.lower()) is None:
                violations.append(name)
            continue
        # LATERAL 是 JOIN 後的結構關鍵字(如 JOIN LATERAL (subquery)),非關聯名。
        if name.lower() == "lateral":
            continue
        if name.lower() in cte_names:
            continue
        violations.append(name)
    return sorted(set(violations))


def embedded_data_modifications(sql: str) -> list[tuple[str, str | None]]:
    """全句掃描 data-modifying 動詞及其目標(含 CTE 內部);回 [(op, target|None)]。

    P1-B:第一個 token 不足以判定語句是否會改資料——``WITH x AS (DELETE ...) SELECT``
    的 head 是 WITH。此處以動詞為準,目標未 schema-qualified 時回 None(呼叫端 typed 拒絕)。
    P2-D:先剝註解,``DELETE /*evade*/ FROM`` 這類寫法不得逃過本掃描。
    """

    sql = strip_sql_comments(sql)
    found: list[tuple[str, str | None]] = []
    for match in _EMBEDDED_MUTATION_RE.finditer(sql):
        if match.group("conflict") is not None:
            continue  # P2-F:ON CONFLICT DO UPDATE 由 INSERT 分支導出,非獨立 mutation
        op = match.group("op").split()[0].upper()
        target = match.group("target")
        if target is not None and _QUALIFIED_TABLE_RE.fullmatch(target.lower()) is None:
            target = None
        found.append((op, None if target is None else target.lower()))
    return found


def classify_sql_statement(sql: str) -> dict[str, Any]:
    """把一條常量 SQL 分類並導出必要權限;無法分類即回 errors(fail-closed)。"""

    # P2-D:整條分類面(head token、目標抽取、關聯抽取、函數抽取)一律吃剝註解後的文字。
    sql = strip_sql_comments(sql)
    head = sql.strip().split()[0].upper() if sql.strip() else ""
    tables: dict[str, set[str]] = {}
    errors: list[str] = []
    mutation = False
    referenced = sorted({match.lower() for match in _QUALIFIED_TABLE_RE.findall(sql)})
    embedded = embedded_data_modifications(sql)
    if head in {"SELECT", "WITH"} and embedded:
        # P1-B:read-class 語句內含 data-modifying CTE → 導出真目標的真權限並 typed 拒絕
        # (§2.1 的「零 retention mutation / 零 DELETE」不可經 CTE 繞過)。
        statement_class = "data_modifying_cte"
        mutation = True
        for table in referenced:
            tables.setdefault(table, set()).add("SELECT")
        for op, target in embedded:
            if target is None:
                errors.append(f"data_modifying_cte_target_not_schema_qualified:{op}")
                continue
            tables.setdefault(target, set()).update(_MUTATION_PRIVILEGES[op])
            errors.append(f"data_modifying_cte:{op}:{target}")
    elif head in {"SELECT", "WITH"}:
        statement_class = "read"
        for table in referenced:
            tables.setdefault(table, set()).add("SELECT")
    elif head == "INSERT":
        statement_class = "insert"
        target_match = _INSERT_TARGET_RE.match(sql)
        if target_match is None:
            errors.append("insert_target_not_schema_qualified")
        else:
            target = target_match.group(1).lower()
            tables.setdefault(target, set()).add("INSERT")
            # PG 語義:INSERT .. ON CONFLICT 需讀 arbiter 欄位 → 目標表另需 SELECT
            # (disposable trace 以真 42501 實證;見 W2a 佐證測試)。
            if re.search(r"\bON\s+CONFLICT\b", sql, re.IGNORECASE):
                tables[target].add("SELECT")
            # P1-B:ON CONFLICT DO UPDATE 是真 mutation(PG 於 plan 期即要求 UPDATE 權限)。
            if re.search(r"\bDO\s+UPDATE\b", sql, re.IGNORECASE):
                tables[target].add("UPDATE")
                mutation = True
            for table in referenced:
                if table != target:
                    tables.setdefault(table, set()).add("SELECT")
            # P1-B:INSERT 之外的第二個 data-modifying 動詞(如 CTE 內 DELETE)必須被導出。
            for op, cte_target in embedded:
                if op == "INSERT":
                    continue
                mutation = True
                if cte_target is None:
                    errors.append(f"data_modifying_cte_target_not_schema_qualified:{op}")
                    continue
                tables.setdefault(cte_target, set()).update(_MUTATION_PRIVILEGES[op])
                errors.append(f"data_modifying_cte:{op}:{cte_target}")
    elif head == "UPDATE":
        statement_class = "update"
        mutation = True
        target_match = _UPDATE_TARGET_RE.match(sql)
        if target_match is None:
            errors.append("update_target_not_schema_qualified")
        else:
            tables.setdefault(target_match.group(1).lower(), set()).add("UPDATE")
    elif head == "DELETE":
        statement_class = "delete"
        mutation = True
        target_match = _DELETE_TARGET_RE.match(sql)
        if target_match is None:
            errors.append("delete_target_not_schema_qualified")
        else:
            tables.setdefault(target_match.group(1).lower(), set()).add("DELETE")
    elif head == "LISTEN":
        statement_class = "listen"
    else:
        statement_class = "unrecognized"
        errors.append(f"unrecognized_statement_class:{head or 'EMPTY'}")
    if statement_class != "listen":
        for name in statement_unqualified_relations(sql):
            errors.append(f"unqualified_relation:{name}")
    functions = sorted({match for match in _ADVISORY_FUNCTION_RE.findall(sql)})
    return {
        "statement_class": statement_class,
        "tables": {name: sorted(privileges) for name, privileges in tables.items()},
        "functions": [f"pg_catalog.{name}" for name in functions],
        "mutation": mutation,
        "errors": errors,
    }


__all__ = [
    "ADVISORY_FUNCTION_NAMES",
    "classify_sql_statement",
    "embedded_data_modifications",
    "statement_unqualified_relations",
    "strip_sql_comments",
]
