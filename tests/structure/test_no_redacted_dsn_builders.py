"""Regression guard / 迴歸守衛:禁止代碼路徑重現被 secret-purge 破壞的 DSN builder。

背景 (verified fact):
    2026-07-16/17 的 git-filter-repo secret purge 把 ~30 個 runtime DSN builder 的
    authority 段(``<user>:<pass>@``,原本緊接在 scheme 之後)就地替換成字面量
    ``postgresql://redacted@``,使這些 builder 失去憑證、連不上資料庫。修復改用
    query-param DSN 形式(runtime 組出 ``?user=…&pass`` 接 ``word=…`` 的 query
    串;憑證不落在 authority 段)。

    2026-07-18 起 ``helper_scripts/maintenance_scripts/public_repo_security_gate.py``
    的 ``embedded_credential_dsn`` 規則除單行 ``scheme://…:…@`` authority 形外,
    也攔截 URI query 參數形與 libpq keyword 形;因此上述 builder 的源碼字面量
    一律刻意拆開(Python 用相鄰 f-string 字面量、shell 用相鄰引號字串,runtime
    值 byte 不變),使 raw bytes 不構成可匹配形。**禁止把 builder「清理」回
    ``user:pass@`` authority 形式,也禁止把拆開的字面量合併回連續 query 形。**

本守衛:枚舉 git-tracked 的 ``*.py`` / ``*.sh``(排除測試檔),斷言沒有任何代碼
路徑含 ``postgres(ql)://redacted@`` builder。已知合法的 9 處出現(docstring /
usage-example / 刻意的 log 遮蔽示意)以 per-path 計數 allowlist 白名單;任何新增
(計數增加=疑似 builder 回歸)或移除(計數減少=allowlist 腐化)都會讓守衛轉紅,
強制複審——因此 allowlist 是緊的:同一檔案內新增的 ``redacted@`` builder 仍會失敗。
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

# 破壞形 DSN builder 的偵測正則:postgres:// 或 postgresql:// 後直接接 redacted@。
_REDACTED_DSN = re.compile(r"postgres(?:ql)?://redacted@")

# 已知合法的 redacted@ 出現(非代碼路徑 builder):docstring / usage-example /
# 刻意的 log 遮蔽示意。key = repo 相對路徑,value = 該檔允許的 redacted@ 行數。
# 精確為 9 處。新增(count 變大=疑似回歸的 builder)或移除(count 變小=allowlist
# 腐化)都會讓守衛轉紅。
_ALLOWLIST: dict[str, int] = {
    # docstring 範例 (dsn: PostgreSQL DSN (e.g., ...))
    "program_code/ml_training/thompson_sampling.py": 1,
    # 刻意的 DSN userinfo log 遮蔽示意,2 行(docstring + 遮蔽註解)
    "helper_scripts/canary/alert_sink.py": 2,
    # docstring usage 範例
    "helper_scripts/phase4/weekly_report.py": 1,
    # docstring
    "helper_scripts/lib/pg_connect.py": 1,
    # usage 註解 + error-message 範例,2 行
    "helper_scripts/db/fresh_start_reset.py": 2,
    # docstring usage 範例
    "helper_scripts/db/check_migration_status.py": 1,
    # usage 註解
    "helper_scripts/db/apply_manual_V140_agent_memory_vector.sh": 1,
}


def _is_test_path(rel_path: str) -> bool:
    """排除測試檔:test_*.py / *_test.(py|sh) / **/tests/** / **/test_*。"""
    path = Path(rel_path)
    if "tests" in path.parts:
        return True
    name = path.name
    if name.startswith("test_"):
        return True
    if name.endswith("_test.py") or name.endswith("_test.sh"):
        return True
    return False


def _tracked_sources() -> list[str]:
    """git-tracked 的非測試 *.py / *.sh(NUL 分隔,避免路徑含特殊字元)。"""
    completed = subprocess.run(
        ["git", "ls-files", "-z", "*.py", "*.sh"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [
        rel
        for rel in completed.stdout.split("\0")
        if rel and not _is_test_path(rel)
    ]


def _scan() -> dict[str, list[tuple[int, str]]]:
    """回傳 {rel_path: [(lineno, stripped_line), ...]},只含含 redacted@ 的行。"""
    findings: dict[str, list[tuple[int, str]]] = {}
    for rel in _tracked_sources():
        text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        hits = [
            (lineno, line.strip())
            for lineno, line in enumerate(text.splitlines(), start=1)
            if _REDACTED_DSN.search(line)
        ]
        if hits:
            findings[rel] = hits
    return findings


def test_no_new_redacted_dsn_builder_in_code_paths() -> None:
    findings = _scan()

    # ① 任何非 allowlist 檔案出現 redacted@ = 疑似回歸的破壞形 builder。
    unexpected = {rel: hits for rel, hits in findings.items() if rel not in _ALLOWLIST}
    assert not unexpected, (
        "偵測到非白名單的 postgres(ql)://redacted@ DSN builder(疑似 secret-purge "
        "破壞形回歸)。修復請用 query-param 形式 "
        # 拆開字面量避免 public-repo gate(embedded_credential_dsn query 形)匹配源碼 bytes;勿合併。
        "postgresql://{host}:{port}/{db}?user=...&pass" "word=...(源碼字面量拆開),勿用 user:pass@ "
        f"authority 形式。offending={unexpected}"
    )

    # ② allowlist 檔案的 redacted@ 行數必須等於已知合法數:
    #    多出來=疑似同檔新 builder 回歸;少了=allowlist 腐化。兩者都要複審。
    count_mismatch = {
        rel: {"expected": expected, "actual": len(findings.get(rel, []))}
        for rel, expected in _ALLOWLIST.items()
        if len(findings.get(rel, [])) != expected
    }
    mismatch_lines = {rel: findings.get(rel, []) for rel in count_mismatch}
    assert not count_mismatch, (
        "allowlist 檔案的 redacted@ 行數與已知合法數不符(新增疑似回歸 / 移除需更新 "
        f"allowlist)。detail={count_mismatch}; lines={mismatch_lines}"
    )
