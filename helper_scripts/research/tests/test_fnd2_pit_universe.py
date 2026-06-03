"""FND-2 PIT universe builder 測試矩陣（PA §5 T1-T10）。

MODULE_NOTE:
  模塊用途：驗證 FND-2 builder 純函數核心 + artifact 落地 + seed regression。核心
    case（T1/T2/T3/T7）全 synthetic（Mac 可跑，不連 PG），證「錯誤實作會 fail」
    （bite-proof 哲學，mirror sibling）。
  涵蓋：T1 delisted-inclusion / T2 lifetime-mask / T3 survivor-rejection /
    T4 determinism / T5 seed-regression / T6 forbidden-route 靜態 / T7 lifetime-edge /
    T8 ticker-tier-not-truncation / T9 payload_hash-hex / T10 manifest/index 完整。
  依賴：pytest + 標準庫（conftest 已把 research/ 加 sys.path）。
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from fnd2_pit_universe.builder import (
    SymbolLifecycle,
    WindowSpec,
    build_universe,
    compute_universe_id,
)
from fnd2_pit_universe.cohorts import CORE25_PINNED, CORE25_PINNED_SET
from fnd2_pit_universe import artifact as artifact_mod


UTC = dt.timezone.utc


def _win():
    """標準 18mo 窗（OQ-5）：2024-06-03 → 2026-06-03。"""
    return WindowSpec(
        window_start_utc=dt.datetime(2024, 6, 3, tzinfo=UTC),
        window_end_utc=dt.datetime(2026, 6, 3, tzinfo=UTC),
        asof_utc=dt.datetime(2026, 6, 3, tzinfo=UTC),
        closed_bar_cutoff_utc=dt.datetime(2026, 6, 2, tzinfo=UTC),
    )


def _lc(symbol, *, listed_at=None, delisted_at=None, seen_delisted=False,
        status="Trading", is_delisted=False, first_seen=None, last_seen=None,
        turnover=None, in_scanner=False, tick_size=0.1, payload_hash="abcdef",
        statuses=None):
    """synthetic SymbolLifecycle 構造 helper。"""
    return SymbolLifecycle(
        symbol=symbol,
        listed_at=listed_at,
        delisted_at=delisted_at,
        seen_delisted=seen_delisted,
        statuses_seen=tuple(statuses or [status]),
        first_seen_ts=first_seen if first_seen is not None else dt.datetime(2026, 5, 7, tzinfo=UTC),
        last_seen_ts=last_seen if last_seen is not None else dt.datetime(2026, 6, 3, tzinfo=UTC),
        status_raw=status,
        base_coin=symbol.replace("USDT", ""),
        quote_coin="USDT",
        contract_type="LinearPerpetual",
        tick_size=tick_size,
        qty_step=0.001,
        min_notional=5.0,
        is_delisted_at_asof=is_delisted,
        source_uri="bybit-public://v5/market/instruments-info?category=linear",
        source_snapshot_ts=dt.datetime(2026, 6, 3, tzinfo=UTC),
        source_payload_hash=payload_hash,
        turnover_24h=turnover,
        in_scanner_window=in_scanner,
    )


def _row_by_symbol(rows, symbol):
    for r in rows:
        if r["symbol"] == symbol:
            return r
    return None


# ─────────────────────────── T1 delisted-inclusion ───────────────────────────
def test_t1_delisted_symbol_included_with_exact_alive_to():
    """窗內 delist 的 symbol 必 included，alive_to 精確 = delisted_at（含 delisted）。"""
    win = _win()
    delist = win.window_start_utc + dt.timedelta(days=30)
    lcs = [
        _lc("SYMXUSDT",
            listed_at=win.window_start_utc - dt.timedelta(days=100),
            delisted_at=delist, seen_delisted=True, status="Closed", is_delisted=True),
        _lc("BTCUSDT", listed_at=dt.datetime(2020, 3, 15, tzinfo=UTC)),  # survivor 陪襯
    ]
    rows, summary = build_universe(lcs, win, run_id="t1")
    r = _row_by_symbol(rows, "SYMXUSDT")
    assert r is not None and r["included"] is True
    assert r["seen_delisted"] is True
    assert r["alive_to_utc"] == delist.isoformat()  # 精確 = delisted_at
    assert r["alive_days_in_window"] == 30
    assert summary["delisted_proof_count"] >= 1


# ─────────────────────────── T2 lifetime-mask ───────────────────────────
def test_t2_listed_after_window_start_alive_from_is_listed_not_window_start():
    """listed_at 在窗內 → alive_from = listed_at（NOT window_start，NOT first_seen_ts）。

    R-1 核心：first_seen_ts ≈ 2026-05-07，若誤 coalesce 會把 alive_from 錯夾。此 case
    listed_at=window_start+50d 但 first_seen_ts=2026-05-07，斷言 alive_from 用 listed_at。
    """
    win = _win()
    listed = win.window_start_utc + dt.timedelta(days=50)
    lcs = [_lc("SYMYUSDT", listed_at=listed,
               first_seen=dt.datetime(2026, 5, 7, tzinfo=UTC))]
    rows, _ = build_universe(lcs, win, run_id="t2")
    r = _row_by_symbol(rows, "SYMYUSDT")
    assert r["included"] is True
    assert r["alive_from_utc"] == listed.isoformat()  # listed_at，不是 window_start
    assert r["alive_from_utc"] != win.window_start_utc.isoformat()
    # 不是 first_seen_ts
    assert r["alive_from_utc"] != dt.datetime(2026, 5, 7, tzinfo=UTC).isoformat()
    expected_days = (win.window_end_utc - listed).days
    assert r["alive_days_in_window"] == expected_days


def test_t2b_r1_old_listing_not_clamped_to_first_seen():
    """R-1 反 trap：2024 上市 + first_seen=2026-05 → alive_from clip 到 window_start，
    NOT first_seen_ts。若實作誤用 coalesce(listed_at, first_seen_ts) 仍會用 listed_at；
    若誤把 first_seen_ts 當下界，alive_from 會錯成 2026-05-07。"""
    win = _win()
    # listed 早於窗 → clip 到 window_start（2024-06-03）。
    lcs = [_lc("OLDUSDT",
               listed_at=dt.datetime(2021, 1, 1, tzinfo=UTC),
               first_seen=dt.datetime(2026, 5, 7, tzinfo=UTC))]
    rows, _ = build_universe(lcs, win, run_id="t2b")
    r = _row_by_symbol(rows, "OLDUSDT")
    # 早於窗的 listed → alive_from = window_start（greatest(listed, ws)）。
    assert r["alive_from_utc"] == win.window_start_utc.isoformat()
    # 絕不等於 first_seen_ts（2026-05-07）——那是 R-1 的錯誤實作會產生的值。
    assert r["alive_from_utc"] != dt.datetime(2026, 5, 7, tzinfo=UTC).isoformat()
    assert r["listed_at_utc"] == dt.datetime(2021, 1, 1, tzinfo=UTC).isoformat()


# ─────────────────────────── T3 survivor-rejection ───────────────────────────
def test_t3a_universe_with_delisted_in_window_passes():
    """窗含 delisted 且 included 納入 → survivor_rejection_status=PASS。"""
    win = _win()
    lcs = [
        _lc("BTCUSDT", listed_at=dt.datetime(2020, 3, 15, tzinfo=UTC)),
        _lc("DEADUSDT", listed_at=dt.datetime(2023, 1, 1, tzinfo=UTC),
            delisted_at=win.window_start_utc + dt.timedelta(days=60),
            seen_delisted=True, status="Closed", is_delisted=True),
    ]
    rows, summary = build_universe(lcs, win, run_id="t3a")
    assert summary["survivor_rejection_status"] == "PASS"
    assert summary["delisted_proof_count"] >= 1
    assert _row_by_symbol(rows, "DEADUSDT")["included"] is True


def test_t3b_current_survivor_only_when_delisted_excluded_fails():
    """窗內存在 delisted-proof，但 included 全 current-survivor（delisted 被排除/未納入）
    → survivor_rejection_status=FAIL（bite：current-survivor-only 捷徑被 reject）。

    構造：DEADUSDT seen_delisted=true 但其 lifetime 不與窗交（delisted 在窗開始前），
    故被 excluded；included 集只剩 current survivor。這正是 survivorship truncation
    的指紋——窗內有 delisted 證據但 universe 只留活的。"""
    win = _win()
    lcs = [
        _lc("BTCUSDT", listed_at=dt.datetime(2020, 3, 15, tzinfo=UTC)),
        # delisted 在窗開始前 → excluded（lifetime_outside_window），但 seen_delisted=true。
        _lc("GONEUSDT", listed_at=dt.datetime(2022, 1, 1, tzinfo=UTC),
            delisted_at=win.window_start_utc - dt.timedelta(days=10),
            seen_delisted=True, status="Closed", is_delisted=True),
    ]
    rows, summary = build_universe(lcs, win, run_id="t3b")
    gone = _row_by_symbol(rows, "GONEUSDT")
    assert gone["included"] is False  # delisted 在窗前 → 排除
    assert gone["exclusion_reason"] == "lifetime_outside_window"
    # rows 含 seen_delisted=true（GONEUSDT），但 included 全 current-survivor → FAIL。
    assert summary["survivor_rejection_status"] == "FAIL"


def test_t3c_proven_none_in_window():
    """窗內根本無 delisted 證據 → PROVEN_NONE_IN_WINDOW（非 fail，但須證明 none）。"""
    win = _win()
    lcs = [
        _lc("BTCUSDT", listed_at=dt.datetime(2020, 3, 15, tzinfo=UTC)),
        _lc("ETHUSDT", listed_at=dt.datetime(2021, 3, 15, tzinfo=UTC)),
    ]
    rows, summary = build_universe(lcs, win, run_id="t3c")
    assert summary["survivor_rejection_status"] == "PROVEN_NONE_IN_WINDOW"
    assert summary["delisted_proof_count"] == 0


# ─────────────────────────── T4 determinism ───────────────────────────
def test_t4_determinism_same_input_same_universe_id_and_bytes(tmp_path):
    """同 lifecycle input 跑兩次 → universe_id 相同 + universe.csv bytes 相同。"""
    win = _win()
    lcs = [
        _lc("BTCUSDT", listed_at=dt.datetime(2020, 3, 15, tzinfo=UTC), turnover=1.9e9),
        _lc("ZZZUSDT", listed_at=dt.datetime(2023, 6, 1, tzinfo=UTC),
            delisted_at=win.window_start_utc + dt.timedelta(days=200),
            seen_delisted=True, status="Closed", is_delisted=True, turnover=5e6),
    ]
    rows1, sum1 = build_universe(lcs, win, run_id="run_a")
    rows2, sum2 = build_universe(lcs, win, run_id="run_b")
    # universe_id 與 run_id 無關（contract §4）。
    assert sum1["universe_id"] == sum2["universe_id"]

    w1 = artifact_mod.write_all(
        rows1, sum1, run_id="run_a", window=win,
        universe_sources=["market.symbol_universe_snapshots"],
        repo_root=Path("."), runtime_host="test", artifact_root=tmp_path,
    )
    w2 = artifact_mod.write_all(
        rows2, sum2, run_id="run_b", window=win,
        universe_sources=["market.symbol_universe_snapshots"],
        repo_root=Path("."), runtime_host="test", artifact_root=tmp_path,
    )
    # csv bytes 相同（除了 run_id 欄；故比對去掉 run_id 後）。drop run_id 欄做穩定比對。
    def _csv_no_runid(path):
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        return [ln.split(",", 1)[1] if "," in ln else ln for ln in lines]
    assert _csv_no_runid(w1["universe_csv"]) == _csv_no_runid(w2["universe_csv"])


def test_t4b_different_lifetime_changes_universe_id():
    """lifetime 改變 → universe_id 改變（digest 有 bite，非常數）。"""
    win = _win()
    base = [_lc("BTCUSDT", listed_at=dt.datetime(2020, 3, 15, tzinfo=UTC))]
    changed = [_lc("BTCUSDT", listed_at=dt.datetime(2021, 3, 15, tzinfo=UTC))]
    _, s1 = build_universe(base, win, run_id="x")
    _, s2 = build_universe(changed, win, run_id="x")
    assert s1["universe_id"] != s2["universe_id"]


# ─────────────────────────── T5 seed regression ───────────────────────────
def test_t5_seed_regression_counts_and_drift_explained(tmp_path):
    """seed regression：載入真 seed CSV 比對 count，drift 須有解釋（非 fail）。"""
    from fnd2_pit_universe.harness import compute_seed_regression, _repo_root, _DEFAULT_SEED_REL

    win = _win()
    # 用 core25 子集 + 一個 delisted 模擬 built。
    lcs = [_lc(s, listed_at=dt.datetime(2021, 1, 1, tzinfo=UTC)) for s in CORE25_PINNED[:5]]
    lcs.append(_lc("DEADUSDT", listed_at=dt.datetime(2023, 1, 1, tzinfo=UTC),
                   delisted_at=win.window_start_utc + dt.timedelta(days=10),
                   seen_delisted=True, status="Closed", is_delisted=True))
    rows, summary = build_universe(lcs, win, run_id="t5")

    seed_path = _repo_root() / _DEFAULT_SEED_REL
    reg = compute_seed_regression(rows, summary, seed_path=seed_path)
    assert reg["seed_present"] is True
    assert reg["seed_sha256_match"] is True  # 鎖定 seed 未被竄改
    assert reg["seed_row_count"] == 797
    assert reg["drift_explanation"] is not None
    assert "tier-name drift" in reg["drift_explanation"]
    assert reg["built_row_count"] == summary["included_count"]


def test_t5b_seed_regression_absent_seed_no_crash(tmp_path):
    """seed CSV 缺 → 不 crash，drift_explanation 標 absent。"""
    from fnd2_pit_universe.harness import compute_seed_regression
    win = _win()
    rows, summary = build_universe([_lc("BTCUSDT", listed_at=dt.datetime(2020, 3, 15, tzinfo=UTC))],
                                   win, run_id="t5b")
    reg = compute_seed_regression(rows, summary, seed_path=tmp_path / "nope.csv")
    assert reg["seed_present"] is False
    assert "absent" in reg["drift_explanation"]


# ─────────────────────────── T6 forbidden-route 靜態 ───────────────────────────
def _strip_comments_and_strings(src: str) -> str:
    """以 tokenize 移除註釋與字串字面值，只留「可執行 code 識別字」。

    為什麼必須 strip：module docstring 刻意「文件化」禁用函數名（``絕不呼叫
    _fetch_historical_universe_snapshot_sync`` 是硬邊界註記，是好事）。forbidden-route
    test 要驗的是「沒有真正**呼叫/import** 禁用路徑」，不是「文本不得提及」。對 code
    tokens（NAME/OP/...）grep 才是正確語義；mirror multiday 的 read-only 靜態測哲學。
    """
    import io
    import tokenize
    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type in (tokenize.STRING, tokenize.COMMENT):
                continue
            out.append(tok.string)
    except tokenize.TokenError:
        return src  # 退化：tokenize 失敗則回原文（保守，寧誤報）
    return " ".join(out)


def test_t6_forbidden_routes_static():
    """builder/data_loader 原始碼（去註釋/字串後）：0 禁用函數呼叫 / 0 max_symbols /
    universe SQL 無 LIMIT 截斷 / 0 current_scanner fallback / read-only session 強制。"""
    pkg = Path(__file__).resolve().parents[1] / "fnd2_pit_universe"
    dl_raw = (pkg / "data_loader.py").read_text(encoding="utf-8")
    bd_raw = (pkg / "builder.py").read_text(encoding="utf-8")
    art_raw = (pkg / "artifact.py").read_text(encoding="utf-8")
    dl_code = _strip_comments_and_strings(dl_raw)
    bd_code = _strip_comments_and_strings(bd_raw)
    art_code = _strip_comments_and_strings(art_raw)

    # 禁用函數**呼叫**：去掉註釋/字串後不得出現（docstring 的硬邊界註記允許提及）。
    for forbidden in ("_fetch_historical_universe_snapshot_sync",
                      "fetch_historical_universe_snapshot_sync",
                      "max_symbols", "current_scanner_fallback"):
        assert forbidden not in dl_code, f"data_loader code 不得呼叫 {forbidden}"
        assert forbidden not in bd_code, f"builder code 不得呼叫 {forbidden}"

    # read-only session 強制（fail-closed）。此為真實 code call（在 raw 驗確切字串；
    # tokenize 會以空白分隔 token 故不在 stripped code 上比對無空白形式）。
    assert "set_session(readonly=True)" in dl_raw

    # universe SQL（symbol_universe_snapshots / market_tickers）不得有 LIMIT 截斷。
    # 唯一允許的 LIMIT 是 scanner_snapshots 取「最新一筆 snapshot」（latest metadata，
    # 非 universe 截斷）。逐 SQL 字串區塊驗（SQL 在字串裡，故用 raw + 三引號擷取）。
    import re
    sql_blocks = re.findall(r'"""(.*?)"""', dl_raw, re.DOTALL)
    checked_universe_sql = False
    for blk in sql_blocks:
        # 只認「首個非空白 token 是 SQL 動詞」的區塊為 SQL（排除 module docstring，
        # docstring 內中文 "只 SELECT" 等提及不應誤判）。
        if not blk.strip().upper().startswith(("SELECT", "WITH")):
            continue
        low = blk.lower()
        if "symbol_universe_snapshots" in low or "market_tickers" in low:
            checked_universe_sql = True
            assert "limit" not in low, f"universe/ticker SQL 不得有 LIMIT:\n{blk}"
        # scanner_snapshots 的 LIMIT 1 是 latest-snapshot（允許）。
        if "scanner_snapshots" in low and "limit" in low:
            assert "limit 1" in low, "scanner LIMIT 只能是 LIMIT 1 (latest snapshot)"
    assert checked_universe_sql, "未找到 universe SQL 區塊（測試自身失效保護）"

    # 絕不 import control_api_v1 runtime（code-level，去字串後）。
    for code in (dl_code, bd_code, art_code):
        assert "control_api_v1" not in code


# ─────────────────────────── T7 lifetime-edge ───────────────────────────
def test_t7a_listed_after_window_end_excluded():
    """listed_at 在 window_end 之後 → excluded（lifetime_outside_window）。"""
    win = _win()
    lcs = [_lc("FUTUREUSDT", listed_at=win.window_end_utc + dt.timedelta(days=10),
               status="PreLaunch")]
    rows, _ = build_universe(lcs, win, run_id="t7a")
    r = _row_by_symbol(rows, "FUTUREUSDT")
    assert r["included"] is False
    assert r["exclusion_reason"] == "lifetime_outside_window"


def test_t7b_delisted_before_window_start_excluded():
    """delisted_at 在 window_start 之前 → excluded。"""
    win = _win()
    lcs = [_lc("ANCIENTUSDT", listed_at=dt.datetime(2022, 1, 1, tzinfo=UTC),
               delisted_at=win.window_start_utc - dt.timedelta(days=5),
               seen_delisted=True, status="Closed", is_delisted=True)]
    rows, _ = build_universe(lcs, win, run_id="t7b")
    r = _row_by_symbol(rows, "ANCIENTUSDT")
    assert r["included"] is False
    assert r["exclusion_reason"] == "lifetime_outside_window"


def test_t7c_unknown_lifetime_excluded_diagnostic():
    """兩 lifetime 權威欄全 NULL → unknown_lifetime，excluded（診斷-only），
    NOT coalesce 到 first_seen_ts、NOT 退回 current scanner。"""
    win = _win()
    lcs = [_lc("MYSTERYUSDT", listed_at=None, delisted_at=None,
               first_seen=dt.datetime(2026, 5, 7, tzinfo=UTC),
               last_seen=dt.datetime(2026, 6, 3, tzinfo=UTC))]
    rows, summary = build_universe(lcs, win, run_id="t7c")
    r = _row_by_symbol(rows, "MYSTERYUSDT")
    assert r["unknown_lifetime"] is True
    assert r["included"] is False
    assert r["exclusion_reason"] == "unknown_lifetime"
    assert r["alive_from_utc"] is None  # 不偽造 alive_from
    assert summary["unknown_lifetime_count"] == 1


def test_t7d_prelaunch_included_as_metadata():
    """PreLaunch（已上市於窗內）→ included 但 inclusion_reason=prelaunch_metadata。"""
    win = _win()
    lcs = [_lc("NEWPERPUSDT",
               listed_at=win.window_end_utc - dt.timedelta(days=5),
               status="PreLaunch", statuses=["PreLaunch"])]
    rows, _ = build_universe(lcs, win, run_id="t7d")
    r = _row_by_symbol(rows, "NEWPERPUSDT")
    assert r["included"] is True
    assert r["status_class"] == "prelaunch"
    assert r["inclusion_reason"] == "prelaunch_metadata"


# ─────────────────────────── T8 ticker-tier-not-truncation ───────────────────────────
def test_t8_turnover_sorts_tier_but_never_truncates():
    """餵 100 symbol（含 turnover=None）→ 全 100 included；NULL-turnover 不排除；
    recommended_tier 排序正確；無任何 LIMIT 行為。"""
    win = _win()
    lcs = []
    for i in range(100):
        sym = f"S{i:03d}USDT"
        # 一半有 turnover（降序），一半 None。
        turnover = (1e9 - i * 1e6) if i % 2 == 0 else None
        lcs.append(_lc(sym, listed_at=dt.datetime(2023, 1, 1, tzinfo=UTC), turnover=turnover))
    rows, summary = build_universe(lcs, win, run_id="t8")
    included = [r for r in rows if r["included"]]
    assert len(included) == 100  # 全 included（NULL-turnover 不排除）
    # turnover 最高者應拿到 top_liquidity tier（非 core25/scanner 時）。
    top = _row_by_symbol(rows, "S000USDT")  # turnover=1e9（最高）
    assert top["recommended_tier"] == "top_liquidity_40_50"
    # NULL-turnover symbol → full_survivorship（rank-unknown，但 included）。
    null_sym = _row_by_symbol(rows, "S001USDT")  # turnover=None
    assert null_sym["included"] is True
    assert null_sym["recommended_tier"] == "full_survivorship"


# ─────────────────────────── T9 payload_hash hex ───────────────────────────
def test_t9_payload_hash_hex_passthrough():
    """source_payload_hash 是 hex text（非 raw bytes / 非 \\x 前綴）。"""
    win = _win()
    lcs = [_lc("BTCUSDT", listed_at=dt.datetime(2020, 3, 15, tzinfo=UTC),
               payload_hash="deadbeef0123")]
    rows, _ = build_universe(lcs, win, run_id="t9")
    r = _row_by_symbol(rows, "BTCUSDT")
    assert r["source_payload_hash"] == "deadbeef0123"
    assert not r["source_payload_hash"].startswith("\\x")


# ─────────────────────────── T10 manifest/index 完整 ───────────────────────────
def test_t10_manifest_and_index_complete(tmp_path):
    """全 artifact write → 4 檔皆生成；artifact_index 每 child 有 path/sha256/byte_size/
    row_count/schema_version；manifest universe_sources 含 symbol_universe_snapshots。"""
    win = _win()
    lcs = [
        _lc("BTCUSDT", listed_at=dt.datetime(2020, 3, 15, tzinfo=UTC), turnover=1.9e9),
        _lc("DEADUSDT", listed_at=dt.datetime(2023, 1, 1, tzinfo=UTC),
            delisted_at=win.window_start_utc + dt.timedelta(days=10),
            seen_delisted=True, status="Closed", is_delisted=True),
    ]
    rows, summary = build_universe(lcs, win, run_id="t10")
    written = artifact_mod.write_all(
        rows, summary, run_id="t10", window=win,
        universe_sources=["market.symbol_universe_snapshots"],
        repo_root=Path("."), runtime_host="test", artifact_root=tmp_path,
    )
    run_dir = Path(written["run_dir"])
    assert (run_dir / "universe.csv").exists()
    assert (run_dir / "universe_summary.json").exists()
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "artifact_index.json").exists()

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert "market.symbol_universe_snapshots" in manifest["universe_sources"]
    assert manifest["universe_id"] == summary["universe_id"]
    assert manifest["program"] == "AEG"

    index = json.loads((run_dir / "artifact_index.json").read_text(encoding="utf-8"))
    names = {e["name"] for e in index["artifacts"]}
    assert {"universe.csv", "universe_summary.json", "manifest.json"} <= names
    for e in index["artifacts"]:
        assert e["sha256"] and len(e["sha256"]) == 64
        assert e["byte_size"] > 0
        assert "schema_version" in e
    # universe.csv 的 row_count = rows 數。
    csv_entry = next(e for e in index["artifacts"] if e["name"] == "universe.csv")
    assert csv_entry["row_count"] == len(rows)


# ─────────────────────────── core25 凍結驗 ───────────────────────────
def test_core25_frozen_25_members():
    """core25 恰 25 成員，且為從 seed 提取的凍結集合（含 BTC/ETH/SOL 等）。"""
    assert len(CORE25_PINNED) == 25
    assert len(CORE25_PINNED_SET) == 25
    for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "TONUSDT"):
        assert s in CORE25_PINNED_SET
    # 確認 in_core25_pinned 欄正確標記。
    win = _win()
    rows, _ = build_universe([_lc("BTCUSDT", listed_at=dt.datetime(2020, 3, 15, tzinfo=UTC)),
                             _lc("RANDOMUSDT", listed_at=dt.datetime(2023, 1, 1, tzinfo=UTC))],
                            win, run_id="c25")
    assert _row_by_symbol(rows, "BTCUSDT")["in_core25_pinned"] is True
    assert _row_by_symbol(rows, "RANDOMUSDT")["in_core25_pinned"] is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
