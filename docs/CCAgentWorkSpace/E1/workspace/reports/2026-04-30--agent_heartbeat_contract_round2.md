# E1 — 5-Agent `last_heartbeat_ms` 契約 round 2（E2 退回 5 finding 修復）

完整報告見 `.claude_reports/20260430_e1_agent_heartbeat_round2.md`（CC Mac 本機）。

## 摘要

round 1 (2026-04-30 20:32) 完成後 E2 對抗審查找出 2 MAJOR + 3 MEDIUM。round 2 按 PM 已決定方案（M-1=A 嚴格化 / MED-2 collapse / MED-3 DRY）執行修復。**不擴大範圍 / 不改 Strategist card 邏輯 / 不改前端 / 不改 BaseAgent**。

## 5 個 finding 修法（一句話）

| Finding | 修法 |
|---|---|
| **M-1 (4 agent on_message 蓋章 vs RUNNING gate)** | 4 處 (guardian/analyst/executor/strategist) 把 `self._last_heartbeat_ms = ...` 從 RUNNING gate **之前**移到 **之後** — 嚴格化方案 A（CLAUDE.md 原則 #10 認知誠實 > debug 便利）|
| **M-2 (對應 negative test 鎖契約)** | 新增 `TestStoppedAgentDoesNotStampOnMessage` 共 4 case：`test_{guardian,analyst,executor,strategist}_on_message_does_not_stamp_when_stopped`，建 agent → 不 start → 灌 SYSTEM_DIRECTIVE → 驗 `_last_heartbeat_ms == 0` |
| **MED-1 (scout record_scan race ordering)** | `self._last_heartbeat_ms = ...` 從 lock 外移進 `with self._lock:` block 第一行，使 heartbeat & `scans_completed` 同 lock atomic（鏡 executor 風格） |
| **MED-2 (scout 3 處冗餘蓋章 collapse 到 1 處)** | 刪除 `produce_intel` + `produce_event_alert` 兩處 `self._last_heartbeat_ms = ...` 賦值；保留 `record_scan` 為 canonical cycle 訊號。對應 2 個 positive test (`*_refreshes`) 改寫為 negative test (`*_does_not_stamp`) |
| **MED-3 (helper DRY)** | 抽 `_surface_heartbeat_ts(stats, card)` module-private helper；4 個 build fn (scout/guardian/analyst/executor) 3 行 inline → 1 行 call。Strategist `_build_strategist_card` 不改（eval_log fallback 特殊邏輯不能套通用 helper） |

## 修改清單

| 檔 | round 2 變動 |
|---|---|
| `app/scout_agent.py` | record_scan 蓋章移入 lock；produce_intel/produce_event_alert 蓋章刪除（保留雙語注釋說明 MED-2 collapse 原因）；ctor + start 注釋更新 |
| `app/guardian_agent.py` | on_message 蓋章移到 RUNNING gate 後；雙語注釋更新（M-1 strict 標註）|
| `app/analyst_agent.py` | 同 Guardian |
| `app/executor_agent.py` | 同 Guardian |
| `app/strategist_agent.py` | 同 Guardian（雙語注釋註明 stopped guard 不需要 — eval_log+stats fallback 自然回 None）|
| `app/agents_routes_helpers.py` | 新增 `_surface_heartbeat_ts` helper + `__all__` export；4 處 inline (scout/guardian/analyst/executor) 改 1 行 call。淨 +8 LOC vs round 1 (819→827) |
| `tests/test_agent_heartbeat_contract.py` | 改寫 2 個 scout produce 測試為 `*_does_not_stamp`；新增 4 個 stopped negative test。net +110 LOC (504 → 614) |
| `tests/test_agents_routes.py` | size threshold docstring 更新為 round 1+2 累計，閾值仍維持 850 |

## 測試輸出尾部

```
test_agent_heartbeat_contract.py: 36 passed (round 1 30 + 4 negative + 2 改寫)
test_agents_routes.py + 4 agent unit + scout suite + audit/multi_agent: 353 passed
全 control_api_v1 regression（ignore concurrent operator WIP test_layer2_tools.py）:
  3195 passed / 1 failed / 10 skipped
  唯一 failed = test_batch_d_risk_fail_closed::test_rc_002 (Rust loop_handlers.rs
  symbol miss — pre-existing, 隔壁 operator WIP，git diff 確認本任務未動 Rust 檔)
```

## Grep 自查

```
$ grep -nE "self\._last_heartbeat_ms" {guardian,analyst,executor,strategist}_agent.py
guardian_agent.py:183:    self._last_heartbeat_ms = int(time.time() * 1000)  # ← post RUNNING gate
analyst_agent.py:235:     self._last_heartbeat_ms = int(time.time() * 1000)  # ← post RUNNING gate
executor_agent.py:336:    self._last_heartbeat_ms = int(time.time() * 1000)  # ← post RUNNING gate
strategist_agent.py:378:  self._last_heartbeat_ms = now_ms()                 # ← post RUNNING gate

$ grep -c "_last_heartbeat_ms" scout_agent.py
4    # 1 ctor init + 1 start() + 1 record_scan() (lock-internal) + 1 get_stats() 讀
     # produce_intel / produce_event_alert 蓋章已刪（MED-2）

$ grep -cE "_surface_heartbeat_ts|last_heartbeat_ms" agents_routes_helpers.py
19   # 含 helper 定義 + 4 處 call + Strategist 主路徑 + __all__ + docstring
```

## 治理對照

| 規範 | 符合 |
|---|---|
| §二 #10 認知誠實 | ✅ M-1 strict 修正（stopped agent 不蓋章避免 GUI 矛盾訊號） |
| §二 #6 失敗默認收縮 | ✅ |
| §二 #11 硬邊界不碰 | ✅（max_retries=0/live_execution_allowed/execution_authority/system_mode 0 觸碰） |
| §七 跨平台 | ✅（無路徑硬編碼 / 無 Linux-only API） |
| §七 雙語注釋 | ✅（每處改動均含中英對照） |
| §九 800/1200 | ✅（helpers 827 < 1200 hard cap；test threshold 850 docstring 更新理由） |
| 不擴大範圍 | ✅（只動 PA 指定 8 檔；前端 / BaseAgent / Strategist card 邏輯未動） |
| 不新增 except/log | ✅（MED-1 純改 lock 範圍） |

## 不確定 / 留尾

1. helper 行數 827 仍 >820（無法回 round 1 baseline），原因記入 test docstring（5-Agent + verdicts + intent + heartbeat 多責任）。E2 round 2 review 確認可否接受
2. pre-existing failure `test_rc_002_h0_status_refresh_preserves_cooldown_and_kill_switch` 與本任務正交，不應 block round 2 簽核

## Operator 下一步

- E2 round 2 對抗審查（聚焦 5 finding 修法精確性 + 雙語注釋 + 測試契約鎖）
- E4 回歸（uvicorn reload 即生效，純 Python 不需 `--rebuild`）
- PM 統一 commit + push（鏈：E1 round 2 → E2 round 2 → E4 → PM）

E1 IMPLEMENTATION DONE: 待 E2 round 2 審查
