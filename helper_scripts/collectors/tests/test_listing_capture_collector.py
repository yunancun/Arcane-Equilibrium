"""production listing capture-only collector 測試。

MODULE_NOTE:
  模塊用途：對 listing capture collector 做單元測試。最重要的是 import 隔離自證
    （test_isolation_*）——全新子進程 import 每個 collector module 後，斷言沒拉進
    任何生產交易模組（openclaw_engine / governance_hub / intent_processor /
    decision_lease / production bybit_rest_client），對應 §4 硬邊界 grep，先自證。
    其餘覆蓋：pg_sink dedup（ON CONFLICT + JSONL fallback）、persist_control_ticks
    開關（control 不落盤但 liveness + capture_lag/markout 不受影響）、capture_state
    生命週期（deadlock-free + quota + resume）、daemon 事件路由。
  依賴：pytest + 標準庫；不連 WS、不打 REST、不連真 PG（fake conn / 注入 clock / 餵 dict）。
  執行：``python3 -m pytest helper_scripts/collectors/tests/ -q``
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import config as collector_config
import daemon as daemon_mod
import gate_b_ws as ws
import healthcheck as hc
import pg_sink as pg_sink_mod
from capture_state import CaptureStateLedger

_TESTS_DIR = Path(__file__).resolve().parent
_COLLECTORS_DIR = _TESTS_DIR.parent
_LISTING_DIR = _COLLECTORS_DIR / "listing_capture"
_RESEARCH_DIR = _COLLECTORS_DIR.parent / "research"
# repo 根（srv/）：路徑式隔離檢查——任何被連帶 import 的 module，__file__ 不得落生產樹。
_REPO_ROOT = _COLLECTORS_DIR.parent.parent

# §4 硬邊界對應的生產模組名黑名單（collector 載入後 sys.modules 不得出現任一者）。
# 同 test_gate_b_probe：用精確 dotted-component 比對避免 stdlib 偽陽性。
_FORBIDDEN_MODULE_TOKENS = (
    "openclaw_engine",
    "symbol_registry",
    "kline_manager",
    "governance_hub",
    "bybit_rest_client",
    "intent_processor",
    "decision_lease",
    "bybit_connector",
    "control_api_v1",
)


# ── 最重要：import 隔離自證（子進程，乾淨 sys.modules + 路徑式檢查） ──────────


@pytest.mark.parametrize(
    "module_name",
    ["config", "pg_sink", "capture_state", "healthcheck", "daemon"],
)
def test_isolation_no_production_module_imported(module_name: str) -> None:
    """全新子進程 import collector module 後，不得拉進任何生產交易樹 module。

    兩道檢查（取聯集回報）：
      1. 路徑式（最強）：任一已載入 module 的 __file__ 落在 program_code/ 或 rust/
         生產樹下 → 命中（§4 無洩漏硬邊界）。
      2. 名稱式：module 名點分量精確等於黑名單字（避開 json.scanner 偽陽性）。
    """
    tokens = list(_FORBIDDEN_MODULE_TOKENS)
    repo_root = str(_REPO_ROOT)
    listing_dir = str(_LISTING_DIR)
    research_dir = str(_RESEARCH_DIR)
    script = textwrap.dedent(
        f"""
        import sys, os
        sys.path.insert(0, {listing_dir!r})
        sys.path.insert(0, {research_dir!r})
        import {module_name}  # noqa: F401
        tokens = {tokens!r}
        repo_root = {repo_root!r}
        prod_roots = (
            os.path.join(repo_root, "program_code") + os.sep,
            os.path.join(repo_root, "rust") + os.sep,
        )
        path_hits = []
        name_hits = []
        for name, mod in list(sys.modules.items()):
            f = getattr(mod, "__file__", None)
            if f and any(os.path.abspath(f).startswith(r) for r in prod_roots):
                path_hits.append(name)
            parts = name.split(".")
            if any(p in tokens for p in parts):
                name_hits.append(name)
        all_hits = sorted(set(path_hits) | set(name_hits))
        print("HITS:" + ",".join(all_hits))
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, f"import {module_name} failed: {proc.stderr}"
    out = proc.stdout.strip()
    assert out.startswith("HITS:"), f"unexpected probe output: {out!r} / {proc.stderr}"
    hits = out[len("HITS:"):].strip()
    assert hits == "", f"{module_name} imported forbidden production module(s): {hits}"


def test_isolation_no_auth_order_ipc_in_source() -> None:
    """靜態自證：collector module 原始碼不出現 auth / order / intent / IPC / live 的硬邊界面。

    對應 §4 grep。collector 只該打 public market REST/WS + 寫 research/klines PG。
    """
    files = [
        _LISTING_DIR / "config.py",
        _LISTING_DIR / "pg_sink.py",
        _LISTING_DIR / "capture_state.py",
        _LISTING_DIR / "healthcheck.py",
        _LISTING_DIR / "daemon.py",
        _LISTING_DIR / "__init__.py",
    ]
    # §4 硬邊界 grep 詞表（這些是 import/呼叫面，非註釋說明字眼——故排除註釋行）。
    forbidden = (
        "execution_authority",
        "live_execution_allowed",
        "decision_lease",
        "OPENCLAW_ALLOW_MAINNET",
        "live_reserved",
        "authorization.json",
        "IntentProcessor",
        "submit_intent",
        "place_order",
        "governance_hub",
        "import psycopg2",  # pg_sink 用延遲 import（psycopg2 字串只在註釋/延遲 import 行內）
    )
    for f in files:
        src = f.read_text(encoding="utf-8")
        # 逐行檢查，跳過註釋行（# 開頭）與 docstring 區——只看真實碼面。
        code_lines = []
        in_docstring = False
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                # 單行 docstring（開閉同行）不切換狀態
                if stripped.count('"""') == 2 or stripped.count("'''") == 2:
                    continue
                in_docstring = not in_docstring
                continue
            if in_docstring:
                continue
            if stripped.startswith("#"):
                continue
            # 移除行內註釋（簡化：# 後內容；字串內 # 罕見於本碼，可接受）
            if "#" in line:
                line = line.split("#", 1)[0]
            code_lines.append(line)
        code = "\n".join(code_lines)
        for token in forbidden:
            # import psycopg2 特例：pg_sink/daemon 用「延遲 import」是合法的（連線時才 import）；
            # 但不得在模組頂層 import。檢查「行首縮排 0 的 import psycopg2」=頂層 import 才算違反。
            if token == "import psycopg2":
                for cl in code_lines:
                    assert not cl.startswith("import psycopg2"), (
                        f"{f.name} 頂層 import psycopg2（應延遲到連線時 import）"
                    )
                continue
            assert token not in code, f"{f.name} 含硬邊界禁用面 {token!r}（§4 無洩漏違反）"


# ── persist_control_ticks 開關（G1；最關鍵的既有檔改動，PA §9 E2 重點 #1）─────


def test_persist_control_ticks_false_skips_control_jsonl_but_keeps_liveness() -> None:
    """persist_control_ticks=False：control tick 不落盤，但 liveness counter 仍更新。

    bite：control 路徑唯一改動。False 時 (a) control writer 0 次呼叫（firehose 殺），
    (b) control_tick_count / control_last_seen 仍更新（poison 哨兵不破）。
    """
    control_rows: list[dict] = []
    probe = ws.GateBWsProbe(
        jsonl_writers={"control": lambda r: control_rows.append(r)},
        clock_ms=lambda: 1_000,
        persist_control_ticks=False,
    )
    msg = {
        "topic": "publicTrade.BTCUSDT",
        "data": [{"T": 999, "p": "50000", "S": "Buy", "v": "0.1", "i": "btc-1"}],
    }
    probe.handle_message(msg, ingest_ts_local_ms=1_000)
    # firehose 殺：control 不落盤
    assert control_rows == [], "persist_control_ticks=False 不應落 control JSONL"
    # liveness 仍工作（poison 哨兵依據）
    liveness = probe.control_liveness()
    assert liveness["control_tick_count"] == 1
    assert liveness["control_last_seen_ms"] == 1_000
    assert liveness["poisoned_suspect"] is False


def test_persist_control_ticks_true_keeps_probe_behavior_byte_identical() -> None:
    """persist_control_ticks=True（探針預設）：control tick 照舊落盤（向後相容）。

    bite：證明探針不傳此參數時行為不變（32 既有測試前提）。
    """
    control_rows: list[dict] = []
    probe = ws.GateBWsProbe(
        jsonl_writers={"control": lambda r: control_rows.append(r)},
        clock_ms=lambda: 1_000,
        # 不傳 persist_control_ticks → 預設 True
    )
    msg = {
        "topic": "publicTrade.BTCUSDT",
        "data": [{"T": 999, "p": "50000", "S": "Buy", "v": "0.1", "i": "btc-1"}],
    }
    probe.handle_message(msg, ingest_ts_local_ms=1_000)
    assert len(control_rows) == 1, "persist_control_ticks 預設應落 control JSONL（探針相容）"
    assert control_rows[0]["kind"] == "control_trade"
    assert control_rows[0]["tick_count"] == 1


def test_persist_control_ticks_false_does_not_affect_capture_lag_or_markout() -> None:
    """persist_control_ticks=False 不影響非 control symbol 的 capture_lag / markout。

    bite：餵一個真實 PreLaunch symbol 的首筆成交，capture_lag / markout 照常產出
    （control 開關只關 BTC control 落盤，候選 symbol 路徑完全不碰）。
    """
    captured: dict[str, list] = {"capture_lag": [], "markout": [], "publictrade": []}
    probe = ws.GateBWsProbe(
        jsonl_writers={
            "capture_lag": lambda r: captured["capture_lag"].append(r),
            "markout": lambda r: captured["markout"].append(r),
            "publictrade": lambda r: captured["publictrade"].append(r),
        },
        clock_ms=lambda: 10_000,
        persist_control_ticks=False,
    )
    probe.set_launch_time("NEWUSDT", 9_000)  # launchTime 9s
    msg = {
        "topic": "publicTrade.NEWUSDT",
        "data": [{"T": 9_500, "p": "1.5", "S": "Buy", "v": "100", "i": "new-1"}],
    }
    probe.handle_message(msg, ingest_ts_local_ms=10_000)
    # capture_lag 照常（9500 - 9000 = 500ms ≤ 5min → PASS）
    assert len(captured["capture_lag"]) == 1
    assert captured["capture_lag"][0]["capture_lag_ms"] == 500
    assert captured["capture_lag"][0]["verdict"] == "PASS_CAPTURE"
    # publictrade 照常 + 帶 trade_id（OQ-3）
    assert len(captured["publictrade"]) == 1
    assert captured["publictrade"][0]["trade_id"] == "new-1"
    # markout trigger 已註冊
    assert any(r.get("kind") == "markout_trigger" for r in captured["markout"])


def test_public_trade_emits_trade_id_for_oq3() -> None:
    """OQ-3：publicTrade emit row 帶 Bybit trade_id `i`（dedup PK 成員）。"""
    rows: list[dict] = []
    probe = ws.GateBWsProbe(
        jsonl_writers={"publictrade": lambda r: rows.append(r)},
        clock_ms=lambda: 5_000,
    )
    msg = {
        "topic": "publicTrade.NEWUSDT",
        "data": [
            {"T": 4_900, "p": "1.5", "S": "Buy", "v": "100", "i": "trade-A"},
            {"T": 4_900, "p": "1.5", "S": "Sell", "v": "50", "i": "trade-B"},  # 同價同毫秒，不同 i
        ],
    }
    probe.handle_message(msg, ingest_ts_local_ms=5_000)
    assert len(rows) == 2
    assert {r["trade_id"] for r in rows} == {"trade-A", "trade-B"}, (
        "同價同毫秒兩筆須各帶不同 trade_id（OQ-3 防誤併）"
    )


# ── pg_sink dedup（ON CONFLICT + JSONL fallback + normalize）──────────────────


class _FakeCursor:
    def __init__(self, store: list, fetch: list | None = None) -> None:
        self._store = store
        self._fetch = fetch or []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self._store.append(("execute", sql, params))

    def fetchall(self):
        return self._fetch


class _FakeConn:
    """fake psycopg2 conn：記錄 execute_batch 餵入的 rows + commit 計數。"""

    def __init__(self, fetch: list | None = None, fail_times: int = 0) -> None:
        self.batches: list = []
        self.commits = 0
        self._fetch = fetch or []
        self._fail_times = fail_times
        self._calls = 0

    def cursor(self):
        return _FakeCursor(self.batches, self._fetch)

    def commit(self):
        self.commits += 1

    def close(self):
        pass


@pytest.fixture(autouse=True)
def _patch_execute_batch(monkeypatch):
    """patch psycopg2.extras.execute_batch 成記錄式 fake（避免真 psycopg2 依賴）。"""
    import types

    fake_extras = types.ModuleType("psycopg2.extras")

    def _fake_execute_batch(cur, sql, rows, page_size=500):
        # 把 rows 推進 cursor 底層 store（_FakeCursor 共享 list）。
        cur._store.append(("batch", sql, list(rows)))

    fake_extras.execute_batch = _fake_execute_batch  # type: ignore[attr-defined]
    fake_psycopg2 = types.ModuleType("psycopg2")
    fake_psycopg2.extras = fake_extras  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "psycopg2", fake_psycopg2)
    monkeypatch.setitem(sys.modules, "psycopg2.extras", fake_extras)
    yield


def test_pg_sink_research_write_uses_on_conflict_do_nothing() -> None:
    """research 寫入 SQL 用 ON CONFLICT DO NOTHING（dedup）。"""
    conn = _FakeConn()
    sink = pg_sink_mod.ListingPgSink(
        collector_version="test_v1",
        conn_factory=lambda: conn,
    )
    sink.write_research_events([{
        "event_ts_exchange": "2026-06-03T00:00:00Z",
        "symbol": "NEWUSDT",
        "event_kind": "public_trade",
        "trade_id": "t1",
        "price": 1.5,
        "ingest_ts_local_ms": 1000,
        "event_ts_exchange_ms": 900,
        "ingest_minus_event_ms": 100,
    }])
    batch_calls = [b for b in conn.batches if b[0] == "batch"]
    assert len(batch_calls) == 1
    sql = batch_calls[0][1]
    assert "research.listing_capture_events" in sql
    assert "ON CONFLICT DO NOTHING" in sql
    assert conn.commits == 1
    # collector_version 被注入
    written_row = batch_calls[0][2][0]
    assert written_row["collector_version"] == "test_v1"


def test_pg_sink_klines_write_uses_pk_on_conflict() -> None:
    """market.klines 寫入用 ON CONFLICT (symbol,timeframe,ts) DO NOTHING（與 engine 同 dedup）。"""
    conn = _FakeConn()
    sink = pg_sink_mod.ListingPgSink(
        collector_version="test_v1",
        conn_factory=lambda: conn,
    )
    sink.write_klines([{
        "ts": "2026-06-03T00:00:00Z", "open_ts_ms": 0, "close_ts_ms": 60000,
        "symbol": "NEWUSDT", "timeframe": "1m",
        "open": 1.0, "high": 1.2, "low": 0.9, "close": 1.1,
        "volume": 100.0, "turnover": None, "tick_count": None,
    }])
    batch_calls = [b for b in conn.batches if b[0] == "batch"]
    assert len(batch_calls) == 1
    sql = batch_calls[0][1]
    assert "market.klines" in sql
    assert "ON CONFLICT (symbol, timeframe, ts) DO NOTHING" in sql


def test_pg_sink_normalize_fills_pk_defaults() -> None:
    """research row normalize：trade_id None → ''；price None → 0.0（PK 成員 NOT NULL 對齊）。"""
    conn = _FakeConn()
    sink = pg_sink_mod.ListingPgSink(collector_version="v", conn_factory=lambda: conn)
    # phase_transition 事件無 trade_id / price
    sink.write_research_events([{
        "event_ts_exchange": "2026-06-03T00:00:00Z",
        "symbol": "NEWUSDT",
        "event_kind": "phase_transition",
        "prev_status": "PreLaunch",
        "new_status": "Trading",
        "ingest_ts_local_ms": 1000,
        "event_ts_exchange_ms": 1000,
        "ingest_minus_event_ms": 0,
    }])
    row = [b for b in conn.batches if b[0] == "batch"][0][2][0]
    assert row["trade_id"] == ""  # None → '' (V130 DEFAULT '')
    assert row["price"] == 0.0    # None → 0.0 (PK 不可 NULL)


def test_pg_sink_write_failure_spills_to_jsonl_fallback(tmp_path) -> None:
    """OQ-5：PG 寫失敗（重試耗盡）→ 落 JSONL fallback，WS 不中斷（回傳行數）。"""

    class _AlwaysFailConn:
        def cursor(self):
            raise RuntimeError("simulated PG down")

        def commit(self):
            pass

        def close(self):
            pass

    sink = pg_sink_mod.ListingPgSink(
        collector_version="v",
        pg_write_max_attempts=2,
        conn_factory=lambda: _AlwaysFailConn(),
        fallback_dir=tmp_path / "fallback",
    )
    n = sink.write_research_events([{
        "event_ts_exchange": "2026-06-03T00:00:00Z",
        "symbol": "NEWUSDT", "event_kind": "public_trade", "trade_id": "t1",
        "price": 1.5, "ingest_ts_local_ms": 1, "event_ts_exchange_ms": 1,
        "ingest_minus_event_ms": 0,
    }])
    assert n == 1  # 回傳嘗試行數（WS 不中斷）
    stats = sink.stats()
    assert stats["pg_write_errors"] >= 2  # 重試耗盡
    assert stats["fallback_rows_written"] == 1
    # JSONL fallback 檔有資料
    fallback_files = list((tmp_path / "fallback").glob("research_events_*.jsonl"))
    assert len(fallback_files) == 1
    assert "NEWUSDT" in fallback_files[0].read_text(encoding="utf-8")


def test_pg_sink_resume_query_returns_window_symbols() -> None:
    """restart-resume query 回傳 window 內 symbol（含最早事件 ts + launchTime）。"""
    fetch = [
        ("NEWUSDT", 1_000_000, 999_000),
        ("FOOUSDT", 2_000_000, None),
    ]
    conn = _FakeConn(fetch=fetch)
    sink = pg_sink_mod.ListingPgSink(
        collector_version="v",
        conn_factory=lambda: conn,
        clock_ms=lambda: 5_000_000,
    )
    rows = sink.query_resume_symbols(lookback_hours=72.0)
    assert len(rows) == 2
    by_sym = {r["symbol"]: r for r in rows}
    assert by_sym["NEWUSDT"]["earliest_event_ts_ms"] == 1_000_000
    assert by_sym["NEWUSDT"]["launch_time_ms"] == 999_000
    assert by_sym["FOOUSDT"]["launch_time_ms"] is None


# ── capture_state 生命週期（deadlock-free + quota + resume）─────────────────


def test_capture_window_admits_marks_and_expires() -> None:
    """window 進場 → active → 過期出場（deadlock-free：必有出口）。"""
    now = {"v": 0}
    ledger = CaptureStateLedger(hold_hours=1.0, max_concurrent=5, clock_ms=lambda: now["v"])
    now["v"] = 1_000
    assert ledger.mark_captured("NEWUSDT", 900) is True
    assert "NEWUSDT" in ledger.active_window_symbols()
    # 未過期：still active
    now["v"] = 1_000 + 30 * 60 * 1000  # +30min < 1h HOLD
    assert "NEWUSDT" in ledger.active_window_symbols()
    assert ledger.expire_due() == []
    # 過期：出場
    now["v"] = 1_000 + 61 * 60 * 1000  # +61min > 1h HOLD
    expired = ledger.expire_due()
    assert expired == ["NEWUSDT"]
    assert ledger.active_window_symbols() == set()


def test_capture_window_quota_fail_closed() -> None:
    """quota 滿 → 不收新 symbol（fail-closed）；已在 window 者仍可。"""
    ledger = CaptureStateLedger(hold_hours=72.0, max_concurrent=2, clock_ms=lambda: 0)
    assert ledger.mark_captured("A", None) is True
    assert ledger.mark_captured("B", None) is True
    # quota 滿
    assert ledger.can_admit("C") is False
    assert ledger.mark_captured("C", None) is False
    # 已在 window 者仍可（重複 mark 不增量）
    assert ledger.can_admit("A") is True
    assert ledger.mark_captured("A", None) is True
    assert ledger.size() == 2


def test_capture_window_not_extended_on_remark() -> None:
    """重複 mark 不延長 window（防無限續；expiry 從首次 captured_at 起算）。"""
    now = {"v": 1_000}
    ledger = CaptureStateLedger(hold_hours=1.0, max_concurrent=5, clock_ms=lambda: now["v"])
    ledger.mark_captured("NEWUSDT", None)
    w1 = ledger.window_of("NEWUSDT")
    # 30min 後重新 mark（這次帶 launchTime）
    now["v"] = 1_000 + 30 * 60 * 1000
    ledger.mark_captured("NEWUSDT", 5_000)
    w2 = ledger.window_of("NEWUSDT")
    assert w2.expiry_ms == w1.expiry_ms, "重複 mark 不應延長 window expiry"
    assert w2.launch_time_ms == 5_000, "launchTime 由 None → 有值應更新（鎖 capture_lag 基準）"


def test_capture_window_resume_recomputes_expiry_from_earliest_event() -> None:
    """resume：window_expiry 從 PG 最早事件推算（不從 now 重起算，不無限續）。"""
    now = {"v": 10_000_000}
    ledger = CaptureStateLedger(hold_hours=1.0, max_concurrent=5, clock_ms=lambda: now["v"])
    rows = [
        # NEWUSDT 最早事件在 now - 30min（仍在 1h window 內）→ resume
        {"symbol": "NEWUSDT", "earliest_event_ts_ms": now["v"] - 30 * 60 * 1000, "launch_time_ms": 1},
        # OLDUSDT 最早事件在 now - 2h（已超 1h HOLD）→ 不 resume（殭屍 window）
        {"symbol": "OLDUSDT", "earliest_event_ts_ms": now["v"] - 2 * 60 * 60 * 1000, "launch_time_ms": 2},
    ]
    resumed = ledger.resume_from_rows(rows)
    assert resumed == ["NEWUSDT"]
    assert "NEWUSDT" in ledger.active_window_symbols()
    assert "OLDUSDT" not in ledger.active_window_symbols()


def test_capture_window_resume_respects_quota() -> None:
    """resume 也 fail-closed：超 quota 的多餘 symbol 不收（保留較新的）。"""
    now = {"v": 10_000_000}
    ledger = CaptureStateLedger(hold_hours=72.0, max_concurrent=2, clock_ms=lambda: now["v"])
    rows = [
        {"symbol": "OLD", "earliest_event_ts_ms": now["v"] - 60 * 60 * 1000, "launch_time_ms": None},
        {"symbol": "MID", "earliest_event_ts_ms": now["v"] - 30 * 60 * 1000, "launch_time_ms": None},
        {"symbol": "NEW", "earliest_event_ts_ms": now["v"] - 10 * 60 * 1000, "launch_time_ms": None},
    ]
    resumed = ledger.resume_from_rows(rows)
    assert len(resumed) == 2  # quota=2
    # 保留較新的 NEW / MID（按最早事件新→舊排序）
    assert set(resumed) == {"NEW", "MID"}


# ── config clamp ─────────────────────────────────────────────────────────────


def test_config_defaults_and_clamps(monkeypatch) -> None:
    """config 預設值（OQ-6 72h/20）+ env clamp。"""
    # 清空相關 env 取預設
    for k in list(__import__("os").environ):
        if k.startswith("OPENCLAW_LISTING"):
            monkeypatch.delenv(k, raising=False)
    cfg = collector_config.current_collector_config()
    assert cfg.capture_hold_hours == 72.0  # OQ-6 預設
    assert cfg.max_concurrent_symbols == 20  # OQ-6 預設
    assert cfg.capture_lag_sla_ms == 5 * 60 * 1000  # PA §3.6
    assert cfg.persist_control_ticks is False  # collector 預設關 firehose
    # clamp：超上界
    monkeypatch.setenv("OPENCLAW_LISTING_CAPTURE_MAX_CONCURRENT", "9999")
    cfg2 = collector_config.current_collector_config()
    assert cfg2.max_concurrent_symbols == 100  # clamp 上界
    # clamp：解析失敗回預設
    monkeypatch.setenv("OPENCLAW_LISTING_CAPTURE_HOLD_HOURS", "not-a-number")
    cfg3 = collector_config.current_collector_config()
    assert cfg3.capture_hold_hours == 72.0


def test_config_persist_control_ticks_env_override(monkeypatch) -> None:
    """persist_control_ticks 可由 env 覆寫為 True（如需 debug control 落盤）。"""
    monkeypatch.setenv("OPENCLAW_LISTING_COLLECTOR_PERSIST_CONTROL_TICKS", "1")
    cfg = collector_config.current_collector_config()
    assert cfg.persist_control_ticks is True


# ── healthcheck 三態 ─────────────────────────────────────────────────────────


def test_healthcheck_pass_when_healthy() -> None:
    """全健康 → PASS（capture window=0 不是 fail，listing 窗常無上市）。"""
    out = hc.build_healthcheck(
        started_at_ms=0,
        last_poll_ok_ms=9_000,
        ws_connected=True,
        control_liveness={"poisoned_suspect": False, "control_tick_count": 100},
        active_window_count=0,  # 無上市是正常
        pg_stats={"pg_write_errors": 0, "fallback_rows_written": 0,
                  "research_rows_written": 0, "klines_rows_written": 0},
        clock_ms=lambda: 10_000,
    )
    assert out["verdict"] == "PASS"
    assert out["warnings"] == []


def test_healthcheck_warn_on_poison_and_fallback() -> None:
    """poison 疑似 / JSONL fallback active → WARN（非 fail）。"""
    out = hc.build_healthcheck(
        started_at_ms=0,
        last_poll_ok_ms=9_500,
        ws_connected=True,
        control_liveness={"poisoned_suspect": True, "control_tick_count": 0},
        active_window_count=2,
        pg_stats={"pg_write_errors": 0, "fallback_rows_written": 5,
                  "research_rows_written": 0, "klines_rows_written": 0},
        clock_ms=lambda: 10_000,
    )
    assert out["verdict"] == "WARN"
    assert "control_poisoned_suspect" in out["warnings"]
    assert "jsonl_fallback_active" in out["warnings"]


# ── daemon 事件路由（不啟真連線；直接呼叫 writer 路由）──────────────────────


class _RecordingSink:
    """記錄 daemon 路由進來的 research / klines row。"""

    def __init__(self):
        self.research: list = []
        self.klines: list = []

    def write_research_events(self, rows):
        self.research.extend(rows)
        return len(rows)

    def write_klines(self, rows):
        self.klines.extend(rows)
        return len(rows)

    def query_resume_symbols(self, *, lookback_hours):
        return []

    def stats(self):
        return {"pg_write_errors": 0, "fallback_rows_written": 0,
                "research_rows_written": len(self.research),
                "klines_rows_written": len(self.klines), "last_write_ok_ms": None}

    def close(self):
        pass


def _make_daemon_with_recording_sink():
    sink = _RecordingSink()
    ledger = CaptureStateLedger(hold_hours=72.0, max_concurrent=20, clock_ms=lambda: 10_000)
    daemon = daemon_mod.ListingCaptureDaemon(
        cfg=collector_config.current_collector_config(),
        pg_sink=sink,
        ledger=ledger,
        clock_ms=lambda: 10_000,
    )
    return daemon, sink, ledger


def test_daemon_public_trade_routes_to_research_with_trade_id() -> None:
    """daemon publicTrade writer → research(public_trade) 帶 trade_id（OQ-3 端到端）。"""
    daemon, sink, ledger = _make_daemon_with_recording_sink()
    ledger.mark_captured("NEWUSDT", 9_000)
    daemon._on_ws_public_trade({
        "symbol": "NEWUSDT", "event_ts_exchange_ms": 9_500, "price": 1.5,
        "side": "Buy", "size": 100.0, "trade_id": "t-1",
        "ingest_ts_local_ms": 10_000, "ingest_minus_event_ms": 500,
    })
    assert len(sink.research) == 1
    row = sink.research[0]
    assert row["event_kind"] == "public_trade"
    assert row["trade_id"] == "t-1"
    assert row["launch_time_ms"] == 9_000  # 從 ledger 補

def test_daemon_confirm_kline_dual_writes_klines() -> None:
    """daemon confirm kline → research(kline_1m) + 雙寫 market.klines；未 confirm 不雙寫。"""
    daemon, sink, _ledger = _make_daemon_with_recording_sink()
    # confirm bar → 雙寫
    daemon._on_ws_kline({
        "symbol": "NEWUSDT", "event_ts_exchange_ms": 60_000,
        "open": 1.0, "high": 1.2, "low": 0.9, "close": 1.1, "volume": 100.0,
        "confirm": True, "ingest_ts_local_ms": 61_000, "ingest_minus_event_ms": 1_000,
    })
    assert len(sink.research) == 1
    assert sink.research[0]["event_kind"] == "kline_1m"
    assert len(sink.klines) == 1  # confirm → 雙寫主 klines
    assert sink.klines[0]["timeframe"] == "1m"
    assert sink.klines[0]["symbol"] == "NEWUSDT"
    # 未 confirm bar → 只 research 不雙寫
    daemon._on_ws_kline({
        "symbol": "NEWUSDT", "event_ts_exchange_ms": 120_000,
        "open": 1.1, "high": 1.3, "low": 1.0, "close": 1.2, "volume": 50.0,
        "confirm": False, "ingest_ts_local_ms": 121_000, "ingest_minus_event_ms": 1_000,
    })
    assert len(sink.research) == 2
    assert len(sink.klines) == 1  # 未 confirm 不增 klines


def test_daemon_phase_transition_writes_research() -> None:
    """daemon phase transition → research(phase_transition) 帶相位。"""
    daemon, sink, _ledger = _make_daemon_with_recording_sink()

    class _T:
        symbol = "NEWUSDT"
        prev_status = "PreLaunch"
        new_status = "Trading"
        launch_time_ms = 9_000
        detected_ingest_ts_ms = 10_000

    daemon._write_phase_transition(_T(), cur_auction_phase="ContinuousTrading")
    assert len(sink.research) == 1
    row = sink.research[0]
    assert row["event_kind"] == "phase_transition"
    assert row["prev_status"] == "PreLaunch"
    assert row["new_status"] == "Trading"
    assert row["cur_auction_phase"] == "ContinuousTrading"
