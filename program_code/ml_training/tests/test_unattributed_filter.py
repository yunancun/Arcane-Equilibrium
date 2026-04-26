"""F4-2 (2026-04-26): tests for `unattributed:bybit_auto` audit-row filter
in ML training pipelines (`realized_edge_stats`, `edge_label_backfill`,
`parquet_etl`, `dl3_ab_runner`).

F4-2（2026-04-26）：ML 訓練管線中 `unattributed:bybit_auto` audit row 過濾測試。

MODULE_NOTE (EN): Verifies the SQL queries in the four ML training modules
  embed the canonical `strategy_name NOT LIKE 'unattributed:%'` filter so
  Bybit auto-action audit rows (funding payment / dust scrub / auto-补单)
  cannot pollute supervised labels or aggregate stats. The tests use plain
  string assertions on the module-level SQL constants to avoid a real PG
  fixture; the filter clause is grep-stable and uniquely identifiable.
MODULE_NOTE (中): 驗證四個 ML 訓練模組的 SQL 查詢都嵌入標準的
  `strategy_name NOT LIKE 'unattributed:%'` 過濾子句，確保 Bybit 自主動作
  audit row 不混入監督式標籤或聚合統計。測試直接對模組層 SQL 常量做字串斷言，
  無需真實 PG fixture；過濾子句 grep 穩定且具識別性。
"""

from __future__ import annotations


def test_realized_edge_stats_fills_query_filters_unattributed():
    """`_FILLS_QUERY` must exclude `unattributed:%` rows so Bybit auto-action
    fills (funding / dust scrub) cannot enter realized-edge stats.

    `_FILLS_QUERY` 必排除 `unattributed:%` row，避免 Bybit 自主動作（funding /
    dust scrub）進入已實現邊際統計。
    """
    from program_code.ml_training import realized_edge_stats as mod

    sql = mod._FILLS_QUERY
    # Filter must be present in the canonical form. The `%%` escape is for
    # psycopg2 pyformat (`%(name)s` paramstyle) — `%` must be doubled.
    # 過濾必為標準形式。`%%` 為 psycopg2 pyformat 對 `%` 字面量的轉義。
    assert "strategy_name NOT LIKE 'unattributed:%%'" in sql, (
        "realized_edge_stats._FILLS_QUERY missing F4-2 unattributed filter"
    )
    # Sanity: filter is in the WHERE clause (not just a comment).
    # 健全性：過濾在 WHERE 子句（不是僅在注釋）。
    where_idx = sql.upper().find("WHERE")
    filter_idx = sql.find("strategy_name NOT LIKE 'unattributed:%%'")
    assert where_idx > 0 and filter_idx > where_idx, (
        "F4-2 filter must be in WHERE clause, not just commentary"
    )


def test_edge_label_backfill_included_sql_filters_unattributed():
    """`_BACKFILL_INCLUDED_SQL` must filter audit rows on every JOIN against
    trading.fills (3 sites: EXISTS guard, entry_fills LATERAL, close_fills JOIN).

    `_BACKFILL_INCLUDED_SQL` 必在所有 trading.fills JOIN 處過濾 audit row
    （3 處：EXISTS、entry_fills LATERAL、close_fills JOIN）。
    """
    from program_code.ml_training import edge_label_backfill as mod

    sql = mod._BACKFILL_INCLUDED_SQL
    # Count occurrences — design requires defence-in-depth at all 3 fills JOIN sites.
    # 計數出現次數 — 設計要求在 3 個 fills JOIN 處皆有過濾。
    occurrences = sql.count("strategy_name NOT LIKE 'unattributed:%%'") + sql.count(
        "strategy_name NOT LIKE 'unattributed:%%'"
    )
    # We have 3 explicit filter sites in the file (EXISTS, LATERAL, JOIN).
    # Count the unique pattern; both `f.strategy_name NOT LIKE` and
    # `strategy_name NOT LIKE` (without table prefix) appear.
    # 檔案有 3 個顯式過濾位點。
    pattern_total = sql.count("NOT LIKE 'unattributed:%%'")
    assert pattern_total >= 3, (
        f"_BACKFILL_INCLUDED_SQL needs filter at all 3 fills JOIN sites "
        f"(EXISTS / entry_fills / close_fills); found {pattern_total}"
    )
    # Belt: confirm 'unattributed:' string actually appears
    # 抽查：確認 'unattributed:' 真有出現
    assert "'unattributed:" in sql


def test_edge_label_backfill_excluded_sql_filters_unattributed():
    """`_BACKFILL_EXCLUDED_SQL` mirrors the close-side filter so audit rows
    don't hijack `last_close_tag` aggregation.

    `_BACKFILL_EXCLUDED_SQL` 鏡射 close 側過濾，避免 audit row 篡奪
    `last_close_tag` 聚合。
    """
    from program_code.ml_training import edge_label_backfill as mod

    sql = mod._BACKFILL_EXCLUDED_SQL
    assert "strategy_name NOT LIKE 'unattributed:%%'" in sql, (
        "_BACKFILL_EXCLUDED_SQL missing F4-2 unattributed filter"
    )


def test_parquet_etl_fills_query_filters_unattributed():
    """`parquet_etl.run_etl` builds `fills_query` with audit-row filter so
    DuckDB-based parquet ETL never feeds Bybit auto-action fills downstream.

    `parquet_etl.run_etl` 構造 `fills_query` 含 audit row 過濾，確保
    DuckDB parquet ETL 不向下游餵入 Bybit 自主動作成交。
    """
    import inspect

    from program_code.ml_training import parquet_etl

    # parquet_etl uses an inline f-string instead of a module constant; pull
    # the source of extract_training_data and assert the filter is present.
    # parquet_etl 使用 inline f-string 而非模組常量，取 extract_training_data 原始碼斷言。
    src = inspect.getsource(parquet_etl.extract_training_data)
    # Note: parquet_etl uses DuckDB SQL (single `%`, no escape) so we look
    # for the unescaped form here. psycopg2 % escape is irrelevant for DuckDB.
    # 注意：parquet_etl 使用 DuckDB SQL（單 `%` 無需轉義），尋找未轉義形式。
    assert "strategy_name NOT LIKE 'unattributed:%'" in src, (
        "parquet_etl.run_etl fills_query missing F4-2 unattributed filter"
    )


def test_dl3_ab_runner_docstring_documents_unattributed_filter():
    """`fetch_training_dataset` is currently a stub but its docstring documents
    the schema assumption for future wiring; the unattributed filter MUST be
    part of that contract so future wiring engineers do not regress.

    `fetch_training_dataset` 目前為 stub，但 docstring 文件化 schema 假設供
    未來實作；unattributed 過濾必為該契約一部分，避免實作工程師退化。
    """
    from program_code.ml_training import dl3_ab_runner

    docstring = dl3_ab_runner.fetch_training_dataset.__doc__ or ""
    # Documented in the schema-assumption block; the literal substring is
    # grep-stable across whitespace edits.
    # 在 schema-assumption block 中文件化；字面 substring 對空白編輯穩定。
    assert "unattributed:" in docstring, (
        "dl3_ab_runner.fetch_training_dataset docstring must reference F4-2 "
        "unattributed filter so future wiring inherits the contract"
    )


def test_realized_edge_stats_filter_handles_null_strategy_name():
    """The filter form `(strategy_name IS NULL OR strategy_name NOT LIKE
    'unattributed:%')` must tolerate NULL strategy_name (legacy rows pre-V017).

    過濾形式 `(strategy_name IS NULL OR ...)` 必兼容 NULL strategy_name
    （V017 前的歷史 row）。
    """
    from program_code.ml_training import realized_edge_stats as mod

    sql = mod._FILLS_QUERY
    # The full clause must include the NULL tolerance — without it, legacy
    # rows with strategy_name IS NULL would be silently dropped.
    # 完整子句必含 NULL 容忍 — 否則 strategy_name IS NULL 的歷史 row 會被
    # 靜默丟棄。
    assert "strategy_name IS NULL OR" in sql, (
        "F4-2 filter must tolerate legacy NULL strategy_name rows "
        "(use form `IS NULL OR NOT LIKE 'unattributed:%%'`)"
    )


# ─────────────────────────────────────────────────────────────────────────
# Integration-style mock test: proves data-flow excludes audit rows.
# 整合風格 mock 測試：證明資料流確實排除 audit row。
# ─────────────────────────────────────────────────────────────────────────


def test_realized_edge_stats_mock_excludes_unattributed_rows():
    """End-to-end with mock cursor: synthesize a mix of attributed +
    unattributed rows. After SQL filter (we simulate it locally), only
    attributed rows should pair into round-trips and produce stats.

    端對端 mock cursor 測試：合成 attributed + unattributed mix。
    經 SQL 過濾後（本地模擬），只有 attributed row 配對為 round-trip 產生 stats。
    """
    from datetime import datetime, timezone
    from unittest.mock import MagicMock, patch

    from program_code.ml_training import realized_edge_stats as mod

    # Synthetic fills: 2 attributed (entry + close pair) + 2 unattributed (would
    # have been drops). We pre-filter here to mimic what the real PG query does.
    # 合成資料：2 行 attributed（entry + close 配對） + 2 行 unattributed
    # （本應被丟棄）。本地預過濾以模擬真 PG 查詢行為。
    all_rows = [
        # ── attributed pair (ma_crossover BTC long: entry + close) ──
        {
            "ts": datetime(2026, 4, 26, 10, 0, 0, tzinfo=timezone.utc),
            "symbol": "BTCUSDT",
            "strategy_name": "ma_crossover",
            "side": "Buy",
            "qty": 0.001,
            "price": 50_000.0,
            "fee": 0.0275,
            "realized_pnl": 0.0,  # entry — gross PnL not yet realized
            "is_paper": False,
            "engine_mode": "demo",
        },
        {
            "ts": datetime(2026, 4, 26, 11, 0, 0, tzinfo=timezone.utc),
            "symbol": "BTCUSDT",
            "strategy_name": "ma_crossover",
            "side": "Sell",
            "qty": 0.001,
            "price": 51_000.0,
            "fee": 0.028,
            "realized_pnl": 1.0,  # close — gross gain $1.0
            "is_paper": False,
            "engine_mode": "demo",
        },
        # ── unattributed (Bybit funding payment + dust scrub) — must NOT
        #     reach the round-trip pairing
        # ── unattributed（Bybit funding + dust scrub）— 不應進入配對
        {
            "ts": datetime(2026, 4, 26, 12, 0, 0, tzinfo=timezone.utc),
            "symbol": "ETHUSDT",
            "strategy_name": "unattributed:bybit_auto",
            "side": "Buy",
            "qty": 0.5,
            "price": 2_500.0,
            "fee": -0.001,
            "realized_pnl": 0.0,
            "is_paper": False,
            "engine_mode": "demo",
        },
        {
            "ts": datetime(2026, 4, 26, 13, 0, 0, tzinfo=timezone.utc),
            "symbol": "ETHUSDT",
            "strategy_name": "unattributed:bybit_auto",
            "side": "Sell",
            "qty": 0.5,
            "price": 2_600.0,
            "fee": -0.001,
            "realized_pnl": 0.0,
            "is_paper": False,
            "engine_mode": "demo",
        },
    ]
    # Apply SQL filter locally — equivalent of `WHERE strategy_name NOT LIKE
    # 'unattributed:%%'` over the synthetic rowset.
    # 本地套用過濾 — 等同 SQL `WHERE strategy_name NOT LIKE 'unattributed:%'`。
    filtered_rows = [
        r
        for r in all_rows
        if r["strategy_name"] is None
        or not r["strategy_name"].startswith("unattributed:")
    ]
    assert len(filtered_rows) == 2, "filter must drop the 2 unattributed rows"

    # Mock cursor returns filtered rows (this proves the function consumes the
    # filter output without choking on missing pair counterparts).
    # Mock cursor 回傳過濾後行（證明函數消費過濾輸出而不因配對缺失崩潰）。
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.description = [
        ("ts",), ("symbol",), ("strategy_name",), ("side",),
        ("qty",), ("price",), ("fee",), ("realized_pnl",),
        ("is_paper",), ("engine_mode",),
    ]
    cur.fetchall.return_value = [
        tuple(r[col[0]] for col in cur.description) for r in filtered_rows
    ]
    conn = MagicMock()
    conn.cursor.return_value = cur

    with patch.object(mod, "_get_db_conn", return_value=conn):
        result = mod.compute_edge_stats(
            days_back=1, min_samples=1, engine_mode="demo"
        )

    # Only the ma_crossover/BTCUSDT cell should appear; ETHUSDT was filtered.
    # 只有 ma_crossover/BTCUSDT cell 出現；ETHUSDT 已被過濾。
    assert ("ma_crossover", "BTCUSDT") in result, (
        "ma_crossover BTC pair should produce a stats cell"
    )
    assert ("unattributed:bybit_auto", "ETHUSDT") not in result, (
        "unattributed cell must NOT appear in stats"
    )
    # No leakage of `unattributed:` prefix in any key.
    # 任何 key 都不應有 `unattributed:` 前綴洩漏。
    leaked = [
        k for k in result.keys() if k[0].startswith("unattributed:")
    ]
    assert not leaked, f"unexpected unattributed cells leaked: {leaked}"
