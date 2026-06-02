"""Gate-B 隔離探針測試 — 隔離自證 + 狀態機 + capture_lag + markout + verdict。

MODULE_NOTE:
  模塊用途：對 Gate-B 探針四件 module 做單元測試，其中**最重要**的是 import 隔離
    測試（test_isolation_*）——在全新子進程裡 import 每個 gate_b_* module，斷言載入
    後 sys.modules 沒有任何被禁的生產模組（openclaw_engine / SymbolRegistry /
    KlineManager / governance_hub / production bybit_rest_client / scanner / strategy
    / intent / decision_lease），對應 E3 之後會 grep 的 I1-I4 隔離不變量，先自證。
  其餘測試覆蓋：PreLaunch→Trading 狀態機、capture_lag（含 5min 閾值 PASS/SLOW）、
    MidPriceRing markout 回填、BTC control unpoisoned 判定、verdict 必含
    INCONCLUSIVE_NO_TRANSITION、artifact root 跨平台（OPENCLAW_DATA_DIR）。
  依賴：pytest + 標準庫；不連 WS、不打 REST（全部用注入式 fake / 直接餵 dict）。
  執行：``python3 -m pytest helper_scripts/research/tests/test_gate_b_probe.py -q``
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import gate_b_artifact as artifact
import gate_b_rest as rest
import gate_b_ws as ws

_RESEARCH_DIR = Path(__file__).resolve().parent.parent
# repo 根（srv/）：用於路徑式隔離檢查——任何被連帶 import 的 module，其 __file__
# 不得落在生產樹 program_code/ 或 rust/ 下。這是 E3 I1-I4 grep 想保證的真正不變量。
_REPO_ROOT = _RESEARCH_DIR.parent.parent

# E3 I1-I4 對應的生產模組名黑名單（探針載入後 sys.modules 不得出現任一者）。
# 為什麼用「精確 dotted-component 比對」而非裸 substring：裸 substring 會把 stdlib
# 的 ``json.scanner`` 之類誤判（"scanner" 命中）。改成把每個已載入 module 名拆成
# 點分量，只要任一量精確等於黑名單字才算命中。
# 為什麼**只列生產獨有的多字 token**（不列 scanner / strategy / intent / lease 這類
# 通用單字）：這些通用字會與 stdlib/三方 module 的點分量碰撞（json.scanner 等）；
# 而生產樹裡真正的 scanner/strategy/intent_processor/decision_lease 一定有 __file__
# 落在 program_code/ 或 rust/ 下，已被上面「路徑式檢查」精準涵蓋。名稱式檢查只負責
# 補抓那些難從路徑判定、但名稱獨特的生產 package 根。
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
    ["gate_b_rest", "gate_b_ws", "gate_b_artifact", "aeg_gate_b_probe"],
)
def test_isolation_no_production_module_imported(module_name: str) -> None:
    """全新子進程 import 探針 module 後，不得拉進任何生產樹 module。

    為什麼用子進程：本測試進程本身可能已 import 過生產模組（pytest 其他測試），
    在同進程檢查 sys.modules 會有偽陽性。全新 ``python -c`` 子進程提供乾淨基線，
    精準量「import 這個 module 自己會連帶拉進什麼」。

    兩道檢查（取聯集回報）：
      1. 路徑式（最強）：任一已載入 module 的 __file__ 落在 program_code/ 或 rust/
         生產樹下 → 命中（這正是 E3 grep I1-I4 想保證的隔離不變量）。
      2. 名稱式：module 名點分量精確等於黑名單字（避開 json.scanner 偽陽性）。
    """
    tokens = list(_FORBIDDEN_MODULE_TOKENS)
    repo_root = str(_REPO_ROOT)
    script = textwrap.dedent(
        f"""
        import sys, os
        sys.path.insert(0, {str(_RESEARCH_DIR)!r})
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


def test_isolation_no_auth_order_db_symbols_in_source() -> None:
    """靜態自證：四件 module 原始碼不出現 auth / order 下單 / DB 寫入的呼叫面。

    為什麼補靜態檢查：import-time 黑名單抓「被連帶 import 的模組」；此處再從原始碼
    層面確認沒有 psycopg2/sqlalchemy 連線、沒有 place_order/submit_intent、沒有
    authorization 簽核呼叫，雙重保險（E3 grep 前自證）。
    """
    files = [
        _RESEARCH_DIR / "gate_b_rest.py",
        _RESEARCH_DIR / "gate_b_ws.py",
        _RESEARCH_DIR / "gate_b_artifact.py",
        _RESEARCH_DIR / "aeg_gate_b_probe.py",
    ]
    # 禁止出現的「執行面」符號（註釋/字串裡的說明字眼不算——這些是 import/呼叫名）。
    forbidden_calls = (
        "import psycopg2",
        "import sqlalchemy",
        "psycopg2.connect",
        "place_order",
        "submit_intent",
        "create_order",
        "authorization.json",
        "import requests",  # 探針只用 stdlib urllib，不引 requests
    )
    for f in files:
        src = f.read_text(encoding="utf-8")
        for token in forbidden_calls:
            assert token not in src, f"{f.name} contains forbidden call surface: {token}"


# ── REST phase 狀態機 ───────────────────────────────────────────────────────


def _phase(symbol, status, launch=None, observed=1000):
    return rest.InstrumentPhase(
        symbol=symbol,
        status=status,
        launch_time_ms=launch,
        cur_auction_phase=None,
        pre_listing_phases=(),
        observed_ingest_ts_ms=observed,
    )


def test_state_machine_detects_prelaunch_to_trading() -> None:
    sm = rest.PhaseStateMachine()
    # 第一輪：FOOUSDT 在 PreLaunch（無轉移）。
    t1 = sm.observe([_phase("FOOUSDT", "PreLaunch", launch=5000)])
    assert t1 == []
    assert sm.prelaunch_symbols() == {"FOOUSDT"}
    # 第二輪：FOOUSDT 轉 Trading → 偵測到一個轉移。
    t2 = sm.observe([_phase("FOOUSDT", "Trading", observed=6000)])
    assert len(t2) == 1
    assert t2[0].symbol == "FOOUSDT"
    assert t2[0].prev_status == "PreLaunch"
    assert t2[0].new_status == "Trading"
    # launchTime 被鎖定（第二輪 row 沒帶 launch 也仍取得首見值）。
    assert t2[0].launch_time_ms == 5000
    assert sm.prelaunch_symbols() == set()


def test_state_machine_no_transition_when_stays_prelaunch() -> None:
    sm = rest.PhaseStateMachine()
    sm.observe([_phase("BARUSDT", "PreLaunch")])
    t = sm.observe([_phase("BARUSDT", "PreLaunch")])
    assert t == []


def test_poller_parses_prelisting_phases_and_launchtime() -> None:
    captured = {}

    def fake_urlopen(req, timeout=None):  # noqa: ARG001
        class _Resp:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

            def read(self_inner):
                captured["url"] = req.full_url
                payload = {
                    "retCode": 0,
                    "result": {
                        "list": [
                            {
                                "symbol": "NEWUSDT",
                                "status": "PreLaunch",
                                "launchTime": "1717200000000",
                                "preListingInfo": {
                                    "curAuctionPhase": "CallAuction",
                                    "phases": [{"phase": "CallAuction", "startTime": "1"}],
                                },
                            }
                        ]
                    },
                }
                return json.dumps(payload).encode("utf-8")

        return _Resp()

    poller = rest.InstrumentsInfoPoller(urlopen=fake_urlopen, clock_ms=lambda: 9999)
    phases = poller.fetch_prelaunch()
    assert "instruments-info" in captured["url"]
    assert "status=PreLaunch" in captured["url"]
    assert len(phases) == 1
    p = phases[0]
    assert p.symbol == "NEWUSDT"
    assert p.launch_time_ms == 1717200000000
    assert p.cur_auction_phase == "CallAuction"
    assert p.pre_listing_phases[0]["phase"] == "CallAuction"
    assert p.observed_ingest_ts_ms == 9999


def test_poller_rejects_disallowed_endpoint() -> None:
    poller = rest.InstrumentsInfoPoller()
    with pytest.raises(rest.GateBRestError):
        poller._request_json("/v5/order/create", {})


# ── WS capture_lag / markout / control 哨兵 ─────────────────────────────────


def _collect_writers():
    sink: dict[str, list] = {}

    def make(channel):
        sink.setdefault(channel, [])
        return lambda row: sink[channel].append(row)

    writers = {ch: make(ch) for ch in ("kline", "publictrade", "control", "capture_lag", "markout")}
    return writers, sink


def _trade_msg(symbol, event_ts, price, size="1.0", side="Buy"):
    return {
        "topic": f"publicTrade.{symbol}",
        "data": [{"T": event_ts, "p": str(price), "v": size, "S": side}],
    }


def test_capture_lag_pass_within_5min() -> None:
    writers, sink = _collect_writers()
    probe = ws.GateBWsProbe(jsonl_writers=writers, clock_ms=lambda: 0)
    launch = 1_000_000
    probe.set_launch_time("NEWUSDT", launch)
    # 首筆成交在 launch + 60s（< 5min）→ PASS_CAPTURE。
    probe.handle_message(_trade_msg("NEWUSDT", launch + 60_000, 10.0), ingest_ts_local_ms=launch + 60_500)
    cl = sink["capture_lag"]
    assert len(cl) == 1
    assert cl[0]["capture_lag_ms"] == 60_000
    assert cl[0]["verdict"] == "PASS_CAPTURE"
    # provenance 三欄齊全（event/ingest/skew）。
    pt = sink["publictrade"][0]
    assert pt["event_ts_exchange_ms"] == launch + 60_000
    assert pt["ingest_ts_local_ms"] == launch + 60_500
    assert pt["ingest_minus_event_ms"] == 500


def test_capture_lag_slow_beyond_5min() -> None:
    writers, sink = _collect_writers()
    probe = ws.GateBWsProbe(jsonl_writers=writers, clock_ms=lambda: 0)
    launch = 1_000_000
    probe.set_launch_time("LATEUSDT", launch)
    # 首筆成交在 launch + 10min（> 5min）→ SLOW_CAPTURE。
    probe.handle_message(_trade_msg("LATEUSDT", launch + 600_000, 5.0), ingest_ts_local_ms=launch + 600_000)
    assert sink["capture_lag"][0]["verdict"] == "SLOW_CAPTURE"
    assert sink["capture_lag"][0]["capture_lag_ms"] == 600_000


def test_capture_lag_only_first_trade_recorded() -> None:
    writers, sink = _collect_writers()
    probe = ws.GateBWsProbe(jsonl_writers=writers, clock_ms=lambda: 0)
    probe.set_launch_time("NEWUSDT", 0)
    probe.handle_message(_trade_msg("NEWUSDT", 100, 1.0), ingest_ts_local_ms=100)
    probe.handle_message(_trade_msg("NEWUSDT", 200, 2.0), ingest_ts_local_ms=200)
    # 只記首筆 capture_lag。
    assert len(sink["capture_lag"]) == 1
    assert sink["capture_lag"][0]["first_trade_event_ts_ms"] == 100


def test_markout_ring_fills_horizons() -> None:
    ring = ws.MidPriceRing()
    ring.push(1000, 100.0)
    ring.push(1000 + 30_000, 101.0)
    ring.push(1000 + 60_000, 102.0)
    ring.push(1000 + 300_000, 105.0)
    # +30s：第一個 ts ≥ target。
    assert ring.mid_at_or_after(1000 + 30_000) == (1000 + 30_000, 101.0)
    # 尚未到的時點回 None（不臆造）。
    assert ring.mid_at_or_after(1000 + 999_000) is None


def test_markout_fill_emits_bps() -> None:
    writers, sink = _collect_writers()
    probe = ws.GateBWsProbe(jsonl_writers=writers, clock_ms=lambda: 0)
    probe.set_launch_time("NEWUSDT", 0)
    # 首筆成交 → 建 trigger（mid=100）。
    probe.handle_message(_trade_msg("NEWUSDT", 0, 100.0), ingest_ts_local_ms=0)
    # +30s 後有成交 mid=101 → markout_fill +30s 應為 +100bps。
    probe.handle_message(_trade_msg("NEWUSDT", 30_000, 101.0), ingest_ts_local_ms=30_000)
    fills = [r for r in sink["markout"] if r.get("kind") == "markout_fill" and r.get("horizon_s") == 30]
    assert len(fills) == 1
    assert fills[0]["markout_bps"] == pytest.approx(100.0, abs=1e-4)


def test_control_btc_trade_unpoisoned_liveness() -> None:
    writers, sink = _collect_writers()
    probe = ws.GateBWsProbe(jsonl_writers=writers, clock_ms=lambda: 50_000)
    # BTC control tick 進來 → liveness 更新，且不寫進 publictrade（避免污染候選）。
    probe.handle_message(_trade_msg("BTCUSDT", 49_900, 60000.0), ingest_ts_local_ms=50_000)
    live = probe.control_liveness()
    assert live["control_tick_count"] == 1
    assert live["poisoned_suspect"] is False
    assert sink["publictrade"] == []  # BTC 不進候選 publictrade 檔
    assert any(r.get("kind") == "control_trade" for r in sink["control"])


def test_control_poisoned_suspect_when_no_tick() -> None:
    writers, _sink = _collect_writers()
    probe = ws.GateBWsProbe(jsonl_writers=writers, clock_ms=lambda: 0)
    # 從未收到 control tick → poisoned_suspect=True（handler-not-found 毒化嫌疑）。
    live = probe.control_liveness()
    assert live["control_tick_count"] == 0
    assert live["poisoned_suspect"] is True


def test_subscribe_failed_logged_to_control() -> None:
    writers, sink = _collect_writers()
    probe = ws.GateBWsProbe(jsonl_writers=writers, clock_ms=lambda: 0)
    # 模擬 Bybit handler-not-found 回應（success=false）→ 必須顯式落 control。
    probe.handle_message(
        {"op": "subscribe", "success": False, "ret_msg": "error:handler not found"},
        ingest_ts_local_ms=0,
    )
    assert any(r.get("kind") == "ws_subscribe_failed" for r in sink["control"])


def test_sync_subscriptions_batches_and_excludes_control() -> None:
    sent: list[dict] = []

    class _FakeWs:
        def send(self, payload):
            sent.append(json.loads(payload))

    probe = ws.GateBWsProbe(jsonl_writers={}, clock_ms=lambda: 0)
    probe._ws = _FakeWs()
    # 6 個候選 → 12 topics（kline.1 + publicTrade 各 6）→ 必須分 2 批（≤10/批）。
    candidates = {f"S{i}USDT" for i in range(6)}
    probe.sync_subscriptions(candidates)
    sub_msgs = [m for m in sent if m["op"] == "subscribe"]
    assert all(len(m["args"]) <= 10 for m in sub_msgs)
    total_topics = sum(len(m["args"]) for m in sub_msgs)
    assert total_topics == 12
    # control topic 不在候選集合內，故不會被退訂。
    probe.sync_subscriptions(set())
    unsub_msgs = [m for m in sent if m["op"] == "unsubscribe"]
    unsub_topics = {t for m in unsub_msgs for t in m["args"]}
    assert "publicTrade.BTCUSDT" not in unsub_topics


# ── artifact / verdict / 跨平台 root ────────────────────────────────────────


def test_artifact_root_respects_openclaw_data_dir(monkeypatch, tmp_path) -> None:
    # 跨平台：root 由 OPENCLAW_DATA_DIR 決定，不硬編碼 /tmp/openclaw。
    monkeypatch.setenv("OPENCLAW_DATA_DIR", str(tmp_path / "mydata"))
    root = artifact.resolve_artifact_root()
    assert str(root).startswith(str(tmp_path / "mydata"))
    assert root.name == "aeg_gate_b_runs"


def test_artifact_root_fallback_when_env_unset(monkeypatch) -> None:
    monkeypatch.delenv("OPENCLAW_DATA_DIR", raising=False)
    root = artifact.resolve_artifact_root()
    # fallback 僅在 env 未設時 /tmp/openclaw（非硬編碼在邏輯路徑中段）。
    assert str(root) == "/tmp/openclaw/aeg_gate_b_runs"


def test_verdict_inconclusive_when_no_transition() -> None:
    summary = artifact.build_phase_transition_summary([], [])
    verdict = artifact.build_verdict(summary, {"poisoned_suspect": False})
    assert verdict["capture_verdict"] == artifact.VERDICT_INCONCLUSIVE_NO_TRANSITION
    assert verdict["transition_count"] == 0


def test_verdict_pass_capture_with_fast_transition() -> None:
    transitions = [{"symbol": "NEWUSDT", "prev_status": "PreLaunch", "new_status": "Trading", "launch_time_ms": 0, "detected_ingest_ts_ms": 1}]
    capture_lags = [{"symbol": "NEWUSDT", "launch_time_ms": 0, "first_trade_event_ts_ms": 60_000, "capture_lag_ms": 60_000, "verdict": "PASS_CAPTURE"}]
    summary = artifact.build_phase_transition_summary(transitions, capture_lags)
    verdict = artifact.build_verdict(summary, {"poisoned_suspect": False})
    assert verdict["capture_verdict"] == artifact.VERDICT_PASS_CAPTURE


def test_verdict_transition_but_no_capture_not_pass() -> None:
    """FIX-2 對抗測試：有 phase 轉移但零有效 capture（capture_lags 全空）絕不可 PASS_CAPTURE。

    這是 Gate-B 唯一要 catch 的核心失敗——轉移發生卻一筆首成交都沒抓到（WS 漏訂閱 /
    handler-not-found 毒化 / 斷線）。先前 build_verdict 只掃 per_symbol 的 capture_lag_ms，
    對缺 block/None 一律當「不慢」→ 誤報 PASS_CAPTURE。
    """
    transitions = [
        {"symbol": "NEWUSDT", "prev_status": "PreLaunch", "new_status": "Trading", "launch_time_ms": 0, "detected_ingest_ts_ms": 1}
    ]
    # 轉移有了，但 capture_lags 為空（WS 沒收到任何首成交）。
    summary = artifact.build_phase_transition_summary(transitions, [])
    assert summary["transition_count"] == 1
    assert summary["symbols_with_capture_lag"] == 0
    verdict = artifact.build_verdict(summary, {"poisoned_suspect": False})
    assert verdict["capture_verdict"] != artifact.VERDICT_PASS_CAPTURE
    assert verdict["capture_verdict"] == artifact.VERDICT_TRANSITION_BUT_NO_CAPTURE


def test_verdict_transition_with_none_capture_lag_not_pass() -> None:
    """FIX-2 對抗測試：轉移 + capture_lag block 存在但 capture_lag_ms 為 None 仍不可 PASS。

    模擬 WS 收到的 capture row 被毒化（無有效 first_trade_event_ts → capture_lag_ms=None）。
    symbols_with_capture_lag 只計 capture_lag_ms is not None 的 symbol，故仍為 0。
    """
    transitions = [
        {"symbol": "NEWUSDT", "prev_status": "PreLaunch", "new_status": "Trading", "launch_time_ms": 0, "detected_ingest_ts_ms": 1}
    ]
    capture_lags = [
        {"symbol": "NEWUSDT", "launch_time_ms": 0, "first_trade_event_ts_ms": None, "capture_lag_ms": None, "verdict": None}
    ]
    summary = artifact.build_phase_transition_summary(transitions, capture_lags)
    assert summary["transition_count"] == 1
    assert summary["symbols_with_capture_lag"] == 0
    verdict = artifact.build_verdict(summary, {"poisoned_suspect": False})
    assert verdict["capture_verdict"] != artifact.VERDICT_PASS_CAPTURE
    assert verdict["capture_verdict"] == artifact.VERDICT_TRANSITION_BUT_NO_CAPTURE


def test_verdict_partial_capture_miss_two_symbols_not_pass() -> None:
    """FIX-2 re-E2 邊界：2 轉移、僅 1 symbol 抓到首成交 → 不可 PASS_CAPTURE。

    先前漏徑：symbols_with_capture_lag==1 != 0 → else 分支只把 lag>閾值 標 SLOW，缺
    capture 的 symbol 被當「不慢」靜默吞 → 誤報 PASS_CAPTURE。partial-miss 與 total-miss
    同 class（轉移發生卻有 symbol 沒抓到首成交 = 捕捉失敗），fail-closed 標 NO_CAPTURE。
    """
    transitions = [
        {"symbol": "AUSDT", "prev_status": "PreLaunch", "new_status": "Trading", "launch_time_ms": 0, "detected_ingest_ts_ms": 1},
        {"symbol": "BUSDT", "prev_status": "PreLaunch", "new_status": "Trading", "launch_time_ms": 0, "detected_ingest_ts_ms": 1},
    ]
    # 只有 AUSDT 抓到（快），BUSDT 完全沒 capture row（WS 對 BUSDT 漏抓）。
    capture_lags = [
        {"symbol": "AUSDT", "launch_time_ms": 0, "first_trade_event_ts_ms": 60_000, "capture_lag_ms": 60_000, "verdict": "PASS_CAPTURE"}
    ]
    summary = artifact.build_phase_transition_summary(transitions, capture_lags)
    assert summary["transition_count"] == 2
    assert summary["symbols_with_capture_lag"] == 1
    verdict = artifact.build_verdict(summary, {"poisoned_suspect": False})
    assert verdict["capture_verdict"] != artifact.VERDICT_PASS_CAPTURE
    assert verdict["capture_verdict"] == artifact.VERDICT_TRANSITION_BUT_NO_CAPTURE


def test_verdict_partial_capture_miss_three_symbols_one_none_block_not_pass() -> None:
    """FIX-2 re-E2 邊界：3 轉移、僅 1 抓到 / 1 capture block 為 None / 1 全無 block → 不可 PASS。

    覆蓋 partial-miss 的兩種缺法並存：B 有 capture row 但 capture_lag_ms=None（毒化/無效），
    C 完全沒 capture row。任一缺即不完備，fail-closed 標 TRANSITION_BUT_NO_CAPTURE。
    """
    transitions = [
        {"symbol": "AUSDT", "prev_status": "PreLaunch", "new_status": "Trading", "launch_time_ms": 0, "detected_ingest_ts_ms": 1},
        {"symbol": "BUSDT", "prev_status": "PreLaunch", "new_status": "Trading", "launch_time_ms": 0, "detected_ingest_ts_ms": 1},
        {"symbol": "CUSDT", "prev_status": "PreLaunch", "new_status": "Trading", "launch_time_ms": 0, "detected_ingest_ts_ms": 1},
    ]
    capture_lags = [
        {"symbol": "AUSDT", "launch_time_ms": 0, "first_trade_event_ts_ms": 60_000, "capture_lag_ms": 60_000, "verdict": "PASS_CAPTURE"},
        {"symbol": "BUSDT", "launch_time_ms": 0, "first_trade_event_ts_ms": None, "capture_lag_ms": None, "verdict": None},
        # CUSDT 無任何 capture row。
    ]
    summary = artifact.build_phase_transition_summary(transitions, capture_lags)
    assert summary["transition_count"] == 3
    assert summary["symbols_with_capture_lag"] == 1  # 只有 AUSDT 的 capture_lag_ms 非 None
    verdict = artifact.build_verdict(summary, {"poisoned_suspect": False})
    assert verdict["capture_verdict"] != artifact.VERDICT_PASS_CAPTURE
    assert verdict["capture_verdict"] == artifact.VERDICT_TRANSITION_BUT_NO_CAPTURE


def test_verdict_all_transitions_captured_passes() -> None:
    """正向對照：3 轉移全部抓到有效首成交且皆 ≤5min → PASS_CAPTURE（確認集合檢查不 over-block）。

    安全方向雖偏 fail-closed，但真就緒（每個轉移 symbol 都抓到且快）必須 PASS，否則
    over-block 會讓 Gate-B 永遠無法判定管線就緒，失去意義。
    """
    transitions = [
        {"symbol": f"{x}USDT", "prev_status": "PreLaunch", "new_status": "Trading", "launch_time_ms": 0, "detected_ingest_ts_ms": 1}
        for x in ("A", "B", "C")
    ]
    capture_lags = [
        {"symbol": f"{x}USDT", "launch_time_ms": 0, "first_trade_event_ts_ms": 60_000, "capture_lag_ms": 60_000, "verdict": "PASS_CAPTURE"}
        for x in ("A", "B", "C")
    ]
    summary = artifact.build_phase_transition_summary(transitions, capture_lags)
    assert summary["transition_count"] == 3
    assert summary["symbols_with_capture_lag"] == 3
    verdict = artifact.build_verdict(summary, {"poisoned_suspect": False})
    assert verdict["capture_verdict"] == artifact.VERDICT_PASS_CAPTURE


def test_verdict_transition_missing_symbol_not_pass() -> None:
    """FIX-2 fail-closed 邊界：transition row 缺 symbol（無從歸因）→ 不可 PASS。

    build_phase_transition_summary 對缺 symbol 的 transition 會跳過不入 per_symbol，導致
    transition_count>0 但 per_symbol 無任何轉移 symbol。此時無從證明任何轉移有抓到首成交，
    純集合 issubset（空集 ⊆ 任意）會誤判已涵蓋 → 假 PASS。all_transitions_captured 用
    bool(transition_symbols) 前置守衛把這條也擋成 TRANSITION_BUT_NO_CAPTURE。
    """
    transitions = [
        {"symbol": None, "prev_status": "PreLaunch", "new_status": "Trading", "launch_time_ms": 0, "detected_ingest_ts_ms": 1}
    ]
    summary = artifact.build_phase_transition_summary(transitions, [])
    assert summary["transition_count"] == 1
    assert summary["per_symbol"] == {}  # 缺 symbol 被跳過
    verdict = artifact.build_verdict(summary, {"poisoned_suspect": False})
    assert verdict["capture_verdict"] != artifact.VERDICT_PASS_CAPTURE
    assert verdict["capture_verdict"] == artifact.VERDICT_TRANSITION_BUT_NO_CAPTURE


def test_verdict_slow_capture_flags_late() -> None:
    transitions = [{"symbol": "LATEUSDT", "prev_status": "PreLaunch", "new_status": "Trading", "launch_time_ms": 0, "detected_ingest_ts_ms": 1}]
    capture_lags = [{"symbol": "LATEUSDT", "launch_time_ms": 0, "first_trade_event_ts_ms": 600_000, "capture_lag_ms": 600_000, "verdict": "SLOW_CAPTURE"}]
    summary = artifact.build_phase_transition_summary(transitions, capture_lags)
    verdict = artifact.build_verdict(summary, {"poisoned_suspect": False})
    assert verdict["capture_verdict"] == artifact.VERDICT_SLOW_CAPTURE


def test_verdict_pipeline_error_takes_priority() -> None:
    summary = artifact.build_phase_transition_summary([], [])
    verdict = artifact.build_verdict(summary, {"poisoned_suspect": True}, pipeline_error="rest_poll_failed:boom")
    assert verdict["capture_verdict"] == artifact.VERDICT_PIPELINE_ERROR
    assert verdict["isolation_health_warning"] is True


def test_verdict_isolation_warning_does_not_change_capture_verdict() -> None:
    # control 疑似被毒化只在 verdict 標警示，不把 PASS 改成別的（人工判讀資料可信度）。
    transitions = [{"symbol": "NEWUSDT", "prev_status": "PreLaunch", "new_status": "Trading", "launch_time_ms": 0, "detected_ingest_ts_ms": 1}]
    capture_lags = [{"symbol": "NEWUSDT", "launch_time_ms": 0, "first_trade_event_ts_ms": 1000, "capture_lag_ms": 1000, "verdict": "PASS_CAPTURE"}]
    summary = artifact.build_phase_transition_summary(transitions, capture_lags)
    verdict = artifact.build_verdict(summary, {"poisoned_suspect": True})
    assert verdict["capture_verdict"] == artifact.VERDICT_PASS_CAPTURE
    assert verdict["isolation_health_warning"] is True


def test_artifact_writer_creates_run_dir_and_manifest(tmp_path) -> None:
    writer = artifact.GateBArtifactWriter("testrun", artifact_root=tmp_path, clock_ms=lambda: 123)
    w = writer.writer_for("capture_lag")
    w({"kind": "capture_lag", "symbol": "X"})
    manifest_path = writer.write_manifest({"dry_run": True, "verdict": "INCONCLUSIVE_NO_TRANSITION"})
    writer.close()
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    # manifest 必含 point_in_time=true + 隔離聲明 + provenance 規格。
    assert manifest["point_in_time"] is True
    assert manifest["isolation"]["imports_production_modules"] is False
    assert manifest["isolation"]["auth_used"] is False
    assert manifest["isolation"]["db_writes"] is False
    assert manifest["provenance"]["ordering_rule"] == "research_must_sort_by_event_ts_exchange_only"
    assert manifest["counts"]["capture_lag"] == 1
