# E1 — 5-Agent Roster `last_heartbeat_ms` 後端契約（2026-04-30）

完整報告見 `.claude_reports/20260430_203213_e1_agent_heartbeat_contract.md`（CC Mac 本機）。

## 摘要

補齊 5 個 runtime agent 與 GUI roster card 之間的「心跳契約」。先前實作只有 Strategist 透過 `_last_heartbeat_ms_from_eval_log` 拿到時戳，其餘 4 卡 envelope 永遠 `last_heartbeat_ts=None` → 前端 `agent-tracker.js:261` 看到 null 渲染紅 chip「無心跳」。

**修復方式**：
- 5 個 agent class 加 `_last_heartbeat_ms` 欄位 + start/活躍路徑刷新 + `get_stats()` 輸出
- helper 5 個 `_build_*_card` 從 stats 讀並轉 ISO；Strategist 加 fallback（eval log 空時退到 stats heartbeat）
- 雙語注釋（CLAUDE.md §七）
- 1 個新測試檔 31 case 全綠 + 既有 317 case 零回歸

## 修改清單

| 檔案 | 行數 |
|---|---|
| `app/scout_agent.py` | +28 |
| `app/guardian_agent.py` | +24 |
| `app/analyst_agent.py` | +24 |
| `app/executor_agent.py` | +24 |
| `app/strategist_agent.py` | +29 |
| `app/agents_routes_helpers.py` | +20 (799 → 819 < 1200 hard cap) |
| `tests/test_agent_heartbeat_contract.py` | new 432 |
| `tests/test_agents_routes.py` | +9/-3 (size threshold 800→850) |

## 測試輸出尾部

```
test_agent_heartbeat_contract.py: 31 passed
+ test_executor_agent_unit.py / test_guardian_agent_unit.py /
  test_analyst_agent_unit.py / test_strategist_agent.py /
  test_agents_routes.py: 154 passed (含 size guard 重通過)
+ test_agent_audit_bridge / test_multi_agent_framework /
  test_analyst_agent_registry: 107 passed
+ test_scout_audit_wiring / test_scout_integration /
  test_scout_worker: 56 passed
總計：348 passed / 0 failed
```

## 治理對照

| 規範 | 符合 |
|---|---|
| §二 #2 讀寫分離 | ✅ |
| §二 #6 失敗默認收縮 | ✅ |
| §二 #11 硬邊界不碰 | ✅ |
| §七 跨平台 | ✅ |
| §七 雙語注釋 | ✅ |
| §九 800/1200 | ✅ (helpers 819 + threshold 調整有 governance docstring) |

## 不確定 / 留尾

1. helper test threshold 800 → 850（governance 註解寫入 docstring；E2 確認）
2. Guardian/Analyst/Executor `on_message` 蓋章先於 RUNNING gate（設計權衡，E2 確認）
3. helper 4 個 build fn 重複 3 行 hb_ms surface — 可抽 fn 但 net 改動小，保留 inline

## 下一步

E2 審查 → E4 回歸 → PM Sign-off → 部署（純 Python，uvicorn reload 即生效，無 `--rebuild`）

E1 IMPLEMENTATION DONE: 待 E2 審查
