"""episode_slice_pin 離線單元測試（0 live PG）。

覆蓋：窗口數學 [t-60s, t+360s]、per-symbol gap-dedup、fake-cursor 端到端匯出 +
manifest/sha256 shape + write-once 拒覆蓋。全程用 fake cursor / injected fetch，不連任何 PG。
"""
from __future__ import annotations

import gzip
import hashlib
import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from program_code.research.microstructure import episode_slice_pin as esp


# ── 窗口數學 ──
def test_compute_window_math_t_minus_60_plus_360():
    win = esp.compute_window("2026-06-28T12:00:00+00:00")
    assert win["lo_dt"] == datetime(2026, 6, 28, 11, 59, 0, tzinfo=timezone.utc)
    assert win["hi_dt"] == datetime(2026, 6, 28, 12, 6, 0, tzinfo=timezone.utc)  # +τ(60)+300 = +360s
    assert win["hi_ms"] - win["lo_ms"] == 420_000  # 60 + 360 = 420s span
    assert win["anchor_ms"] - win["lo_ms"] == 60_000


def test_compute_window_naive_ts_treated_as_utc():
    a = esp.compute_window("2026-07-01T00:00:00")
    b = esp.compute_window("2026-07-01T00:00:00+00:00")
    assert a["lo_ms"] == b["lo_ms"] and a["hi_ms"] == b["hi_ms"]


# ── gap-dedup ──
def test_dedup_per_symbol_30min_gap():
    rows = [
        {"ts": "2026-06-28T12:00:00Z", "symbol": "BTCUSDT", "signal_id": "a"},
        {"ts": "2026-06-28T12:10:00Z", "symbol": "BTCUSDT", "signal_id": "b"},  # <30min → 折疊
        {"ts": "2026-06-28T12:45:00Z", "symbol": "BTCUSDT", "signal_id": "c"},  # >30min → 新 episode
        {"ts": "2026-06-28T12:05:00Z", "symbol": "ETHUSDT", "signal_id": "d"},  # 不同 symbol → 獨立
    ]
    kept = esp.dedup_episodes(rows, gap_s=1800)
    ids = sorted(k["signal_id"] for k in kept)
    assert ids == ["a", "c", "d"]
    for k in kept:
        assert isinstance(k["anchor_ts"], datetime) and k["anchor_ts"].tzinfo is not None


# ── fake cursor：解析 + 匯出端到端 ──
class _FakeCursor:
    """最小 psycopg2-like cursor：依 SQL 關鍵字回不同固定 row 集。"""

    def __init__(self, store):
        self._store = store
        self._rows = []
        self.description = []

    def execute(self, sql, params=None):
        s = " ".join(sql.split())
        if "FROM trading.signals WHERE strategy_name" in s and "signal_type" in s:
            self._set(self._store["bb"])
        elif "FROM trading.fills WHERE strategy_name" in s and "close_maker_attempt = TRUE" in s:
            self._set(self._store["g8"])
        elif "FROM trading.fills WHERE strategy_name" in s and "side" in s:
            self._set(self._store.get("bb_fills", []))
        elif s.startswith("SELECT now()"):
            self._set([{"now": datetime(2026, 7, 11, 0, 0, tzinfo=timezone.utc)}])
        elif "min(ts), max(ts), count(*) FROM market.l1_events" in s:
            self._set([{
                "min": datetime(2026, 6, 20, tzinfo=timezone.utc),
                "max": datetime(2026, 7, 10, tzinfo=timezone.utc),
                "count": 332432554,
            }])
        elif s.startswith("SELECT * FROM"):
            table = s.split("FROM ", 1)[1].split(" WHERE", 1)[0]
            self._set(self._store["slices"].get(table, []))
        else:
            self._set([])

    def _set(self, rows):
        self._rows = rows
        self.description = [(k,) for k in (rows[0].keys() if rows else [])]

    def fetchall(self):
        return [tuple(r.values()) for r in self._rows]

    def fetchone(self):
        return tuple(self._rows[0].values()) if self._rows else None

    def close(self):
        pass


class _FakeConn:
    def __init__(self, store):
        self._store = store

    def cursor(self):
        return _FakeCursor(self._store)

    def close(self):
        pass


class _RecCursor:
    """記錄 execute 的 SQL（供 read-only session SET 護欄斷言）。"""

    def __init__(self, log):
        self._log = log

    def execute(self, sql, params=None):
        self._log.append(" ".join(sql.split()))

    def close(self):
        pass


class _RecConn:
    def __init__(self):
        self.log = []
        self.committed = False

    def cursor(self):
        return _RecCursor(self.log)

    def commit(self):
        self.committed = True

    def close(self):
        pass


def _store():
    return {
        "bb": [
            {"ts": datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc), "signal_id": "s1",
             "symbol": "BTCUSDT", "strategy_name": "bb_reversion", "signal_type": "OpenLong",
             "strength": 0.8, "context_id": "c1"},
            {"ts": datetime(2026, 6, 28, 12, 10, tzinfo=timezone.utc), "signal_id": "s2",
             "symbol": "BTCUSDT", "strategy_name": "bb_reversion", "signal_type": "OpenLong",
             "strength": 0.7, "context_id": "c2"},  # 折疊
        ],
        # bb 成交 anchor：BTCUSDT Buy@12:03 → 窗 [12:02,12:09) 與 signal 窗 [11:59,12:06) 重疊 → 合併
        "bb_fills": [
            {"ts": datetime(2026, 6, 28, 12, 3, tzinfo=timezone.utc), "fill_id": "bf1",
             "order_id": "bo1", "symbol": "BTCUSDT", "strategy_name": "bb_reversion", "side": "Buy"},
        ],
        "g8": [
            {"ts": datetime(2026, 6, 29, 3, 0, tzinfo=timezone.utc), "fill_id": "f1",
             "order_id": "o1", "symbol": "SOLUSDT", "strategy_name": "grid_trading",
             "close_maker_attempt": True},
        ],
        "slices": {
            "market.l1_events": [
                {"ts": datetime(2026, 6, 28, 12, 0, 1, tzinfo=timezone.utc), "symbol": "BTCUSDT",
                 "best_bid": 60000.0, "best_ask": 60001.0},
            ],
            "trading.fills": [],
            "trading.orders": [],
            "trading.signals": [
                {"ts": datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc), "signal_id": "s1",
                 "symbol": "BTCUSDT"},
            ],
        },
    }


def test_resolve_and_window_plan_with_fake_conn():
    conn = _FakeConn(_store())
    since = datetime(2026, 6, 20, tzinfo=timezone.utc)
    until = datetime(2026, 7, 11, tzinfo=timezone.utc)
    bb = esp.resolve_episodes(conn, since, until)
    fills = esp.resolve_bb_fill_anchors(conn, since, until)
    g8 = esp.resolve_g8_attempts(conn, since, until)
    assert len(bb) == 1  # s2 折疊進 s1
    assert len(fills) == 1  # fill 不 dedup
    assert len(g8) == 1
    bb_windows = esp.build_bb_windows(bb, fills)
    windows = bb_windows + esp.plan_windows(g8, "g8")
    assert [w["kind"] for w in windows] == ["bb", "g8"]
    # signal 窗 [11:59,12:06) ∪ fill 窗 [12:02,12:09) → 合併成單一 [11:59,12:09)=600s，provenance 併集
    assert len(bb_windows) == 1
    assert windows[0]["provenance"] == ["bb_signal", "bb_fill"]
    assert windows[0]["n_anchors"] == 2
    assert windows[0]["hi_ms"] - windows[0]["lo_ms"] == 600_000


def test_write_artifact_manifest_and_sha256_shape(tmp_path):
    conn = _FakeConn(_store())
    since = datetime(2026, 6, 20, tzinfo=timezone.utc)
    until = datetime(2026, 7, 11, tzinfo=timezone.utc)
    bb = esp.resolve_episodes(conn, since, until)
    fills = esp.resolve_bb_fill_anchors(conn, since, until)
    g8 = esp.resolve_g8_attempts(conn, since, until)
    windows = esp.build_bb_windows(bb, fills) + esp.plan_windows(g8, "g8")
    source_head = esp.resolve_source_head(conn)

    out = tmp_path / "pin1"
    manifest = esp.write_artifact(conn, windows, out, source_head)

    # manifest shape
    assert manifest["artifact_kind"] == "episode_slice_pin_v1"
    assert manifest["n_windows"] == 2  # 1 merged bb window + 1 g8 window
    assert manifest["n_bb_windows"] == 1
    assert manifest["n_bb_signal_anchors"] == 1 and manifest["n_bb_fill_anchors"] == 1
    assert manifest["n_g8_attempts"] == 1
    assert manifest["g8_status"] == "pinned"  # 本 store 有 g8 窗
    assert manifest["window_def"]["effective"] == "[t-60s, t+360s]"
    assert manifest["source_pg"]["l1_events_total_rows"] == 332432554
    assert manifest["data_format"] in ("parquet", "csv.gz")
    assert manifest["git_source_head"] is None or isinstance(manifest["git_source_head"], str)

    # 檔案存在 + sha256sums 覆蓋每個 data file + manifest
    assert (out / "manifest.json").is_file()
    sums = (out / "sha256sums").read_text(encoding="utf-8").strip().splitlines()
    covered = {line.split("  ", 1)[1] for line in sums}
    assert "manifest.json" in covered
    # 每窗口 4 表 × 2 窗口 = 8 data files
    data_files = [c for c in covered if c.startswith("data/")]
    assert len(data_files) == 8
    # sha256 值正確
    for line in sums:
        digest, rel = line.split("  ", 1)
        h = hashlib.sha256((out / rel).read_bytes()).hexdigest()
        assert h == digest

    # csv.gz 內容可讀（若走 csv.gz 分支）
    if manifest["data_format"] == "csv.gz":
        l1 = [c for c in data_files if "market_l1_events__bb000" in c][0]
        with gzip.open(out / l1, "rt", encoding="utf-8") as f:
            df = pd.read_csv(f)
        assert len(df) == 1 and "best_bid" in df.columns


def test_write_artifact_is_write_once(tmp_path):
    out = tmp_path / "pin2"
    out.mkdir()
    (out / "sentinel").write_text("x", encoding="utf-8")
    with pytest.raises(RuntimeError, match="write-once"):
        esp.write_artifact(_FakeConn(_store()), [], out, {})


# ── fill-anchor union + 重疊窗合併 ──
def test_bb_fill_anchor_union_and_overlap_merge():
    """signal ∪ fill 對同一 symbol、窗口重疊 → 單一合併窗，provenance=['bb_signal','bb_fill']。"""
    store = {
        "bb": [
            {"ts": datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc), "signal_id": "s1",
             "symbol": "BTCUSDT", "strategy_name": "bb_reversion", "signal_type": "OpenLong",
             "strength": 0.8, "context_id": "c1"},
        ],
        "bb_fills": [
            {"ts": datetime(2026, 6, 28, 12, 3, tzinfo=timezone.utc), "fill_id": "bf1",
             "order_id": "bo1", "symbol": "BTCUSDT", "strategy_name": "bb_reversion", "side": "Buy"},
        ],
        "g8": [],
    }
    conn = _FakeConn(store)
    since = datetime(2026, 6, 20, tzinfo=timezone.utc)
    until = datetime(2026, 7, 11, tzinfo=timezone.utc)
    bb = esp.resolve_episodes(conn, since, until)
    fills = esp.resolve_bb_fill_anchors(conn, since, until)
    assert len(bb) == 1 and len(fills) == 1

    windows = esp.build_bb_windows(bb, fills)
    assert len(windows) == 1  # 兩 anchor 窗口重疊 → 合併成單一窗，不重複釘存
    w = windows[0]
    assert w["symbol"] == "BTCUSDT"
    assert w["provenance"] == ["bb_signal", "bb_fill"]  # signal 前 fill 後（固定序）
    assert w["n_anchors"] == 2
    # union 覆蓋 = signal.lo(11:59) → fill.hi(12:09)
    assert w["lo_ts_utc"].startswith("2026-06-28T11:59:00")
    assert w["hi_ts_utc"].startswith("2026-06-28T12:09:00")
    assert w["hi_ms"] - w["lo_ms"] == 600_000


def test_bb_fill_anchor_non_overlap_stays_separate():
    """同 symbol 但窗口不重疊（相距 >7min）→ 兩獨立窗，各自 provenance。"""
    store = {
        "bb": [
            {"ts": datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc), "signal_id": "s1",
             "symbol": "ETHUSDT", "strategy_name": "bb_reversion", "signal_type": "OpenShort",
             "strength": 0.6, "context_id": "c9"},
        ],
        "bb_fills": [
            {"ts": datetime(2026, 6, 28, 12, 30, tzinfo=timezone.utc), "fill_id": "bf9",
             "order_id": "bo9", "symbol": "ETHUSDT", "strategy_name": "bb_reversion", "side": "Sell"},
        ],
        "g8": [],
    }
    conn = _FakeConn(store)
    since = datetime(2026, 6, 20, tzinfo=timezone.utc)
    until = datetime(2026, 7, 11, tzinfo=timezone.utc)
    bb = esp.resolve_episodes(conn, since, until)
    fills = esp.resolve_bb_fill_anchors(conn, since, until)
    windows = esp.build_bb_windows(bb, fills)
    assert len(windows) == 2
    assert windows[0]["provenance"] == ["bb_signal"]
    assert windows[1]["provenance"] == ["bb_fill"]


# ── G8 誠實化：g8 查無 row → manifest 帶 g8_status 解釋 ──
def test_manifest_g8_status_unpinnable_when_g8_empty(tmp_path):
    store = _store()
    store["g8"] = []  # 模擬 G8 L1 已 aged-out：查無 in-window row
    conn = _FakeConn(store)
    since = datetime(2026, 6, 20, tzinfo=timezone.utc)
    until = datetime(2026, 7, 11, tzinfo=timezone.utc)
    bb = esp.resolve_episodes(conn, since, until)
    fills = esp.resolve_bb_fill_anchors(conn, since, until)
    g8 = esp.resolve_g8_attempts(conn, since, until)
    assert len(g8) == 0  # g8 query 回空 → 自然 0 窗（無聲失敗會漏這事實）
    windows = esp.build_bb_windows(bb, fills) + esp.plan_windows(g8, "g8")
    manifest = esp.write_artifact(conn, windows, tmp_path / "pin_g8empty", esp.resolve_source_head(conn))

    assert manifest["n_g8_attempts"] == 0
    assert manifest["g8_status"] == "unpinnable_l1_aged_out"
    detail = manifest["g8_detail"]
    assert detail["last_close_maker_attempt_utc"] == "2026-06-19T18:48:00Z"
    assert detail["l1_events_min_utc"].startswith("2026-06-20")
    assert detail["surviving_l1_attempts"] == 0


# ── read-only session 護欄：SET statement_timeout + default_transaction_read_only ──
def test_apply_readonly_guards_issue_session_sets():
    conn = _RecConn()
    esp._apply_readonly_guards(conn, statement_timeout_ms=60000)
    assert any("SET statement_timeout = 60000" in s for s in conn.log)
    assert any("SET default_transaction_read_only = on" in s for s in conn.log)
    assert conn.committed  # read-only txn commit 使 session-level SET 持久生效


def test_apply_readonly_guards_custom_timeout():
    conn = _RecConn()
    esp._apply_readonly_guards(conn, statement_timeout_ms=15000)
    assert any("SET statement_timeout = 15000" in s for s in conn.log)


def test_dry_run_main_does_not_connect(tmp_path, capsys, monkeypatch):
    # 若 dry-run 誤連 PG，connect 會 raise → 測試失敗
    def _boom(*a, **k):
        raise AssertionError("dry-run 不得連 PG")
    monkeypatch.setattr(esp, "connect", _boom)

    fixture = tmp_path / "fx.json"
    fixture.write_text(json.dumps({
        "bb_signals": [
            {"ts": "2026-06-28T12:00:00Z", "symbol": "BTCUSDT", "signal_id": "s1"},
            {"ts": "2026-06-28T12:05:00Z", "symbol": "BTCUSDT", "signal_id": "s2"},  # <30min → 折疊
        ],
        "bb_fills": [
            {"ts": "2026-06-28T12:03:00Z", "symbol": "BTCUSDT", "fill_id": "bf1", "side": "Buy"},
        ],
        "g8_attempts": [{"ts": "2026-06-29T03:00:00Z", "symbol": "SOLUSDT", "fill_id": "f1"}],
    }), encoding="utf-8")

    rc = esp.main(["--dry-run", "--anchors-fixture", str(fixture), "--out", str(tmp_path / "plan")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "DRY-RUN" in out
    # 修正後的 entry literal（非 LONG/SHORT）
    assert "OpenLong, OpenShort" in out
    # signal 折疊成 1 + fill 1，窗口重疊 → 1 merged bb window；provenance 併集
    assert "1 bb signals + 1 bb fills → 1 merged bb windows + 1 g8 attempts = 2 windows" in out
    assert "prov=bb_signal,bb_fill" in out
    assert "[t-60s, t+360s]" in out
    # G8 誠實化在計畫預覽出現
    assert "unpinnable_l1_aged_out" in out
