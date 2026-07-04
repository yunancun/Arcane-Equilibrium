"""
MODULE_NOTE
模塊用途：P2-13（冷審計 R2 AI-E confirmed）Layer2CostTracker 跨進程併發寫回歸測試。
主要類/函數：_hammer_worker（multiprocessing spawn 目標）、TestCostTrackerMultiprocess。
依賴：app.layer2_cost_tracker、multiprocessing（spawn context，Mac/Linux 行為一致）。
硬邊界：4 個 uvicorn worker 各持一份 tracker 實例共寫同一 layer2_cost_state.json；
threading.RLock 只擋同進程線程，跨進程 read-modify-write 若無 flock 會互吞成本
（lost update）→ daily_spend 低估 → DOC-08 $2/day 預算閘可被繞過。
本測試以 4 進程 × N 次 rollup 寫入驗證：計數/金額無丟失、state 檔無損壞。
"""

import json
import multiprocessing
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.layer2_cost_tracker import Layer2CostTracker

N_WORKERS = 4
N_ITERS = 150
COST_PER_ITER = 0.001


def _hammer_worker(state_file: str, n_iters: int, cost: float) -> None:
    """子進程寫入者：模擬單一 uvicorn worker 內的成本記錄熱路徑。

    為什麼直打 _add_daily_claude_cost / _increment_daily_session_count：
    這兩條是 read-modify-write 臨界區本體（record_claude_cost 外層還會
    起 IPC daemon thread，對併發正確性測試是噪音）。session_count 是
    整數遞增，為 lost-update 最乾淨的偵測器（金額有浮點捨入干擾）。
    """
    # spawn 子進程重新 import 本模組，模組頭部的 sys.path 注入保證 app 可解析。
    tracker = Layer2CostTracker(state_file=state_file)
    for _ in range(n_iters):
        tracker._add_daily_claude_cost(cost)
        tracker._increment_daily_session_count()


class TestCostTrackerMultiprocess:
    """P2-13 驗收：multiprocessing 4 寫者無丟失 / 無損壞。"""

    def test_four_process_concurrent_writes_no_lost_update(self, tmp_path):
        state_file = str(tmp_path / "layer2_cost_state.json")
        # 先由父進程建立初始 state 檔，排除「首寫建檔」競態干擾主斷言。
        Layer2CostTracker(state_file=state_file)

        # 顯式用 spawn context：macOS 預設即 spawn，Linux 預設 fork——統一取
        # spawn 使兩平台測的是同一種進程模型（也更貼近獨立 uvicorn worker）。
        ctx = multiprocessing.get_context("spawn")
        procs = [
            ctx.Process(target=_hammer_worker, args=(state_file, N_ITERS, COST_PER_ITER))
            for _ in range(N_WORKERS)
        ]
        try:
            for p in procs:
                p.start()
            for p in procs:
                # join 帶 timeout：若 flock 重入實作有自我死鎖，這裡以
                # exitcode=None 明確失敗而非掛死整個 suite。
                p.join(timeout=120)
            assert all(p.exitcode == 0 for p in procs), (
                f"worker exitcodes={[p.exitcode for p in procs]}（None=超時/死鎖）"
            )
        finally:
            for p in procs:
                if p.is_alive():
                    p.terminate()

        # 無損壞：整份 state 檔必須是完整可解析 JSON。
        with open(state_file, encoding="utf-8") as f:
            raw = json.load(f)

        # 無丟失：跨日切換（UTC 午夜跨測試窗）極罕見但可能，故對全部
        # daily_spend 求和而非只看單一 date key。
        total_sessions = sum(
            day.get("session_count", 0) for day in raw.get("daily_spend", {}).values()
        )
        total_claude_usd = sum(
            day.get("claude_usd", 0.0) for day in raw.get("daily_spend", {}).values()
        )
        expected_sessions = N_WORKERS * N_ITERS
        expected_usd = N_WORKERS * N_ITERS * COST_PER_ITER
        assert total_sessions == expected_sessions, (
            f"session_count 丟失 {expected_sessions - total_sessions}/{expected_sessions} 筆"
        )
        assert total_claude_usd == pytest.approx(expected_usd, abs=1e-6), (
            f"claude_usd 丟失：expected={expected_usd} actual={total_claude_usd}"
        )

    def test_state_lock_reentrant_same_thread(self, tmp_path):
        """同線程重入 _state_lock 不得自我死鎖。

        為什麼：record_session 在 _state_lock 內呼叫
        _increment_daily_session_count（其自身也取 _state_lock）；flock 對
        同進程第二個 fd 是會互斥的，重入必須靠 depth 計數消化。
        """
        tracker = Layer2CostTracker(state_file=str(tmp_path / "state.json"))
        with tracker._state_lock():
            with tracker._state_lock():
                tracker._write_raw(tracker._read_raw())
        # 走到這裡即證明：嵌套進入/退出無死鎖，且鎖已完全釋放（可再次取得）。
        with tracker._state_lock():
            pass
