"""REF-20 Sprint C2 R7-T8 — lookup_replay_config_blob reuse audit。

模組目的：
    對 4 個 R7 producer + finalize_route 在 W6 R6-T9 finalize chain 後
    取 manifest_hash / experiment_id metadata 邏輯做 reuse audit：

      1. 4 producer (dream_engine / opportunity_tracker / mlde_shadow_advisor
         / future LinUCB) 統一透過 ``replay_metadata_helper.build_replay_metadata``
         構造 4-tuple（tier / experiment_id / manifest_hash_hex / expires_at），
         不在 producer 端重複 SQL SELECT。
      2. ``run_finalize_route._compute_and_persist_calibration`` 取
         strategy_name + symbol via JOIN replay.experiments + trading.fills
         pattern，與 helper 對齊（SELECT replay.experiments 為主）。
      3. R7 producer 端**不應**有 inline SELECT manifest_hash 的 SQL，全
         走 helper（避免邏輯散在多檔）。

    E1 W1 push back accept context (per dispatch §1.3)：W1 sign-off 揭
    helper 直接 SELECT V049.manifest_hash 而非 reuse experiment_registry
    的 lookup_replay_config_blob fn（後者只取 manifest_jsonb 內 blob，
    無 manifest_hash key；driver test 接受此獨立 SELECT 模式）。
    本 R7-T8 不強要求 reuse 既有 helper — 改驗 manifest_hash 取值邏輯
    一致性 across 4 producer + finalize_route。

參考：
    - program_code/local_model_tools/replay_metadata_helper.py (helper)
    - program_code/local_model_tools/dream_engine.py R7-T1 caller
    - program_code/local_model_tools/opportunity_tracker.py R7-T3 caller
    - program_code/ml_training/mlde_shadow_advisor.py R7-T1.5 caller
    - program_code/exchange_connectors/.../replay/run_finalize_route.py
      W6 R6-T9 caller
    - AI-E advisory §3 + dispatch §1.3 + E1 W1 push back semantics

Hard contracts:
    - 純 grep static analysis；0 PG hit / 0 import 任何 producer module。
    - 0 hardcoded path / 0 forbidden import。
    - 接受 helper 用獨立 SELECT 模式（W1 sign-off 已 closed）；
      只驗 producer 不在自己 module 內 inline manifest_hash SELECT 即可。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


# ─── 路徑常量（從 repo root 用 OPENCLAW_BASE_DIR 解析） ─────────────────


def _repo_root() -> Path:
    """解析 repo root（從本檔案位置反推；兼容 Mac / Linux）。"""
    # 此 test 檔位於 program_code/exchange_connectors/.../tests/replay/
    # repo root = parent[7]：tests/replay → tests → control_api_v1 →
    # bybit_connector → exchange_connectors → program_code → srv
    return Path(__file__).resolve().parents[6]


HELPER_PATH = _repo_root() / "program_code" / "local_model_tools" / "replay_metadata_helper.py"
DREAM_ENGINE_PATH = _repo_root() / "program_code" / "local_model_tools" / "dream_engine.py"
OPPORTUNITY_TRACKER_PATH = (
    _repo_root() / "program_code" / "local_model_tools" / "opportunity_tracker.py"
)
MLDE_SHADOW_ADVISOR_PATH = _repo_root() / "program_code" / "ml_training" / "mlde_shadow_advisor.py"
FINALIZE_ROUTE_PATH = (
    _repo_root()
    / "program_code"
    / "exchange_connectors"
    / "bybit_connector"
    / "control_api_v1"
    / "replay"
    / "run_finalize_route.py"
)


# ─── §1：helper 取 manifest_hash 邏輯確存 ──────────────────────────────


def test_replay_metadata_helper_uses_independent_select_pattern():
    """W1 push back accept：helper 用獨立 SELECT V049.manifest_hash 模式（per
    AI-E spec lookup_replay_config_blob signature 不對應 manifest_hash key）。

    本 test 驗 helper 確含 SELECT manifest_hash 邏輯（OR 等價：reuse
    既有 lookup helper）；接受其中一種模式即 PASS。
    """
    assert HELPER_PATH.exists(), f"helper 檔不存在：{HELPER_PATH}"
    src = HELPER_PATH.read_text(encoding="utf-8")

    # 模式 A：helper 自己 SELECT manifest_hash 取值（W1 IMPL）
    has_inline_select = bool(
        re.search(r"SELECT\s+manifest_hash", src, re.IGNORECASE)
    )

    # 模式 B：helper reuse experiment_registry.lookup_replay_config_blob
    # （AI-E spec §3.2 reference；E1 W1 push back accept 不採用此模式）
    has_lookup_helper_import = bool(
        re.search(r"from .* import .*lookup_replay_config_blob", src)
        or re.search(r"lookup_replay_config_blob\(", src)
    )

    # PASS 條件：兩模式至少一個（W1 採模式 A）
    assert has_inline_select or has_lookup_helper_import, (
        "helper 必含 SELECT manifest_hash 邏輯（inline OR reuse lookup_replay_config_blob）；"
        "W1 sign-off accept 模式 A，本 R7-T8 接受兩模式之一"
    )

    # 額外驗 helper 對應實際 W1 IMPL：應有 SELECT FROM replay.experiments
    assert "FROM replay.experiments" in src, (
        "helper 必查 V049 replay.experiments 表（manifest_hash 來源）"
    )


def test_replay_metadata_helper_select_uses_experiment_id_predicate():
    """helper SELECT 必透 experiment_id WHERE clause 取唯一 row（避全表掃）。"""
    src = HELPER_PATH.read_text(encoding="utf-8")
    assert "WHERE experiment_id" in src, (
        "helper SELECT 必含 WHERE experiment_id = %s（V049 PK lookup）"
    )
    # LIMIT 1 為防禦性（V049 experiment_id 是 PK，唯一性已保證）
    assert "LIMIT 1" in src.upper() or "limit 1" in src.lower(), (
        "helper SELECT 推薦含 LIMIT 1 防禦"
    )


# ─── §2：finalize_route 取 strategy_name + symbol 模式對齊 ──────────────


def test_finalize_route_uses_consistent_lookup_pattern():
    """finalize_route 取 strategy_name + symbol via JOIN replay.experiments
    pattern（W6 R6-T9 land 路徑）— 與 helper 對齊（兩者都 SELECT FROM
    replay.experiments）。

    W6 R6-T9 finalize 端取 V049 strategy/symbol（caller 上游 R6 calibration
    derive 用），與 helper 同表查詢。本 test 驗 finalize_route 確含
    SELECT FROM replay.experiments + 處理 trading.fills query。
    """
    assert FINALIZE_ROUTE_PATH.exists(), f"finalize_route 檔不存在：{FINALIZE_ROUTE_PATH}"
    src = FINALIZE_ROUTE_PATH.read_text(encoding="utf-8")

    # 必含 SELECT FROM replay.experiments（取 strategy_name + symbol）
    assert "FROM replay.experiments" in src, (
        "finalize_route 必 SELECT FROM replay.experiments（W6 R6-T9 caller）"
    )

    # 必含 trading.fills 查詢（W6 calibration 用 14d window fills）
    assert "FROM trading.fills" in src, (
        "finalize_route 必 SELECT FROM trading.fills（calibration label 14d window）"
    )

    # caller 模式對齊 helper：兩者都使用 cur.execute + parameterized SQL
    assert "cur.execute" in src
    # finalize_route 用 %s 參數化（防 SQL injection）
    assert "%s" in src


# ─── §3：3 producer 端不應 inline SELECT manifest_hash（全走 helper） ──


def _grep_inline_manifest_hash_select(path: Path) -> list[str]:
    """grep 檔內 inline SELECT manifest_hash SQL pattern；回傳 hits list。

    僅找 SELECT manifest_hash 出現於 SQL 字串（execute / cur.execute 後），
    不算 docstring / comment / argv name 出現。
    """
    if not path.exists():
        return []
    src = path.read_text(encoding="utf-8")
    # 找 cur.execute / execute / executemany 開頭後接 SELECT manifest_hash 的 SQL
    # （簡化：找 raw SELECT manifest_hash 字串於 raw string 中）
    hits = []
    pattern = re.compile(r"SELECT\s+manifest_hash", re.IGNORECASE)
    for line_no, line in enumerate(src.splitlines(), 1):
        # 排除 docstring / comment 出現
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith('"""'):
            continue
        if pattern.search(line):
            hits.append(f"line {line_no}: {line.strip()[:120]}")
    return hits


def test_dream_engine_no_inline_manifest_hash_select():
    """dream_engine.py 端不應 inline SELECT manifest_hash SQL（全走 helper）。"""
    hits = _grep_inline_manifest_hash_select(DREAM_ENGINE_PATH)
    assert hits == [], (
        f"dream_engine.py 含 inline SELECT manifest_hash（應走 helper）：\n"
        + "\n".join(hits)
    )


def test_opportunity_tracker_no_inline_manifest_hash_select():
    """opportunity_tracker.py 端不應 inline SELECT manifest_hash SQL。"""
    hits = _grep_inline_manifest_hash_select(OPPORTUNITY_TRACKER_PATH)
    assert hits == [], (
        f"opportunity_tracker.py 含 inline SELECT manifest_hash（應走 helper）：\n"
        + "\n".join(hits)
    )


def test_mlde_shadow_advisor_no_inline_manifest_hash_select():
    """mlde_shadow_advisor.py 端不應 inline SELECT manifest_hash SQL。"""
    hits = _grep_inline_manifest_hash_select(MLDE_SHADOW_ADVISOR_PATH)
    assert hits == [], (
        f"mlde_shadow_advisor.py 含 inline SELECT manifest_hash（應走 helper）：\n"
        + "\n".join(hits)
    )


# ─── §4：3 producer 都 import build_replay_metadata helper ─────────────


def _has_helper_import(path: Path) -> bool:
    """驗檔內 import build_replay_metadata helper（W1 IMPL pattern）。"""
    if not path.exists():
        return False
    src = path.read_text(encoding="utf-8")
    # 容錯多種 import 模式：
    # - from program_code.local_model_tools.replay_metadata_helper import ...
    # - from .replay_metadata_helper import ...
    # - import program_code.local_model_tools.replay_metadata_helper as ...
    patterns = [
        r"from\s+.*replay_metadata_helper\s+import",
        r"import\s+.*replay_metadata_helper",
        r"build_replay_metadata",  # 至少 reference helper 名稱
    ]
    return any(re.search(p, src) for p in patterns)


def test_dream_engine_imports_helper():
    """dream_engine.py 必 import build_replay_metadata helper（R7-T1）。"""
    assert _has_helper_import(DREAM_ENGINE_PATH), (
        "dream_engine.py 缺 build_replay_metadata import（R7-T1 should land）"
    )


def test_opportunity_tracker_imports_helper():
    """opportunity_tracker.py 必 import build_replay_metadata（R7-T3）。"""
    assert _has_helper_import(OPPORTUNITY_TRACKER_PATH), (
        "opportunity_tracker.py 缺 build_replay_metadata import（R7-T3 should land）"
    )


def test_mlde_shadow_advisor_imports_helper():
    """mlde_shadow_advisor.py 必 import build_replay_metadata（R7-T1.5）。"""
    assert _has_helper_import(MLDE_SHADOW_ADVISOR_PATH), (
        "mlde_shadow_advisor.py 缺 build_replay_metadata import（R7-T1.5 should land）"
    )


# ─── §5：W1 push back contract documentation ──────────────────────────


def test_helper_module_docstring_documents_w1_design_decision():
    """helper 端 MODULE_NOTE 應記錄「為何不 reuse lookup_replay_config_blob」
    的設計決策（W1 sign-off §9.4）。

    本 test 驗 helper docstring 至少提及 ``lookup_replay_config_blob`` 名
    稱（document why not reuse；防未來 reader 重新提案 reuse）。
    """
    src = HELPER_PATH.read_text(encoding="utf-8")
    # docstring 必提 lookup_replay_config_blob 名（提示讀者 W1 設計決策）
    assert "lookup_replay_config_blob" in src, (
        "helper docstring 應記錄與 lookup_replay_config_blob 的差異設計"
        "（W1 push back accept context）"
    )
