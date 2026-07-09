# G3-08 Phase 1 Sub-task B — Python h_state_invalidator + query_handler

- **Agent**：E1（Backend Developer）
- **任務**：G3-08 Phase 1 Sub-task B
- **時間**：2026-04-26 14:30 - 14:52 CEST
- **Commit**：`1c7b20e`（pushed origin/main + Linux pulled）
- **PA design plan**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g3_08_h1_h5_ipc_gateway_design.md`（commit `7564d07`，§4 Option C / §5 IPC schema / §7 Python hook / §10.1 prompt）
- **Phase 1 Sub-task A**（Rust h_state_cache）：隔壁並行 sub-agent（worktree isolation per PA §13.1）
- **Phase 1 Sub-task C**（接線 + healthcheck [20]）：下次 session 串行（待 A+B 同時 commit）

---

## 範圍與完成狀態

| 子項 | 狀態 |
|---|---|
| 新建 `app/h_state_invalidator.py`（singleton + env-gate + fire-and-forget） | ✅ ~340 LOC |
| 新建 `app/h_state_query_handler.py`（Phase 1 stub 空殼） | ✅ ~150 LOC |
| 新增 reverse IPC route `query_h_state_full` 於 `ai_service_dispatch.py` | ✅ |
| 17+ pytest（singleton dedup / env-gate / fail-closed / IPC mock / threadsafe） | ✅ 35 tests |
| Mac pytest 全綠 | ✅ 35/0 in 0.11s |
| Linux pytest 全綠 | ✅ 35/0 in 0.12s |
| DEFAULT-OFF + DEFAULT-ON 雙路徑 smoke test | ✅ |
| Commit + push + Linux pull | ✅ |

---

## 改動清單

| 路徑 | 動作 | 行數 |
|---|---|---|
| `app/h_state_invalidator.py` | 新增 | 340 |
| `app/h_state_query_handler.py` | 新增 | 150 |
| `tests/test_h_state_invalidator.py` | 新增 | 370 |
| `tests/test_h_state_query_handler.py` | 新增 | 180 |
| `app/ai_service.py` | 修改 +12 | HANDLER_TTLS +1 條 |
| `app/ai_service_dispatch.py` | 修改 +50 | _register_handlers +1 mapping + _handle_query_h_state_full method |

Total +1222 / -0. Engine binary baseline 2161 不變（純 Python，0 Rust 改動）。

---

## 不擴範圍（per task prompt）

- ✅ 不接 H1-H5 + 5-Agent producers（Phase 2-4）
- ✅ 不動 `strategy_wiring.py`（Sub-task C）
- ✅ 不動 `CLAUDE.md §九` singleton 表（Sub-task C）
- ✅ 不動 Rust h_state_cache（Sub-task A）
- ✅ 不影響既有 ExecutorConfigCache singleton

---

## 設計亮點（與 PA design plan 對齊）

### A. DEFAULT-OFF 嚴格 "1" env-gate

對齊 PA §4.5 + §8.1：

- `OPENCLAW_H_STATE_GATEWAY != "1"` → `init_h_state_invalidator()` 回 None、`invalidate_async()` no-op、零負擔
- 5 個 env-gate test 覆蓋：missing / "1" / "0" / "true"（嚴格 == "1"，"true" 不啟用）/ ""（空字串）
- 對齊 G3-03 ExecutorConfigCache pattern（commit `51608fe`）— singleton + threading.Lock + double-checked locking

### B. Reverse IPC route 永遠註冊（env-gate independent）

對齊 PA §10.1 完成標準：「env=0 時 query_h_state_full 仍 callable（route exists）但回 empty」

- `ai_service_dispatch.py:_register_handlers()` 加 `"query_h_state_full": self._handle_query_h_state_full` 無條件 mapping
- env=0 dispatch → 仍走 `_handle_query_h_state_full` → 回 `build_h_state_full_response()` 空殼
- 這設計確保 Rust poller daemon 在 env flip 時不需重新發現 handler

### C. Fire-and-forget 三層保險

對齊 PA §4.3 + CLAUDE.md §二 原則 #6：

1. **inner**（`_dispatch_one`）：`try/except Exception` 吞所有 IPC 例外 → 統計 failed
2. **outer**（`invalidate_async`）：第二層 `try/except` 守 thread.spawn 失敗（資源緊張）
3. **disconnect cleanup**（`_call_invalidate_ipc.finally`）：第三層 `try/except` 守斷線失敗

→ `invalidate_async` 永不 raise，呼叫端**毋須** try/except wrap。

### D. Phase 1 stub schema = canonical empty shell

對齊 PA §5.1 + §4.2.1：

```python
{
    "version":       0,
    "fetched_at_ms": int(time.time() * 1000),
    "h_states":      {},      # Phase 2-4 fill
    "agent_states":  {},      # Phase 4 fill
}
```

兩桶分組（`h_states` / `agent_states`）對齊 Rust `HStateCache.h1/.../agents` DashMap 結構（PA §6.1），讓 Rust deserializer 每桶一個 top-level 欄位。

---

## 跨平台兼容性（CLAUDE.md §七 ★★）

| 項目 | 狀態 |
|---|---|
| 路徑硬編碼 | ✅ 無（純 Python module，無 OS path） |
| LocalLLMClient 抽象 | ✅ 不涉及（不調 LLM） |
| 服務遷移 | ✅ 純 in-process，無 systemd / launchd 依賴 |
| requirements.txt | ✅ 不需新增（用 stdlib：threading / asyncio / typing） |
| Mac + Linux pytest 一致 | ✅ 35/35 兩端綠 |

---

## 雙語注釋（CLAUDE.md §七 強制）

- `h_state_invalidator.py`：MODULE_NOTE EN+中（雙頂部塊）+ 每個 class/method 中英 docstring + inline 雙語 fail-closed 路徑注釋
- `h_state_query_handler.py`：同上
- `ai_service_dispatch.py:_handle_query_h_state_full`：中英 docstring + 防禦性 include 驗證雙語注釋
- `ai_service.py:HANDLER_TTLS`：新加條目雙語 inline 注釋（短 TTL 設計理由）

---

## 不確定之處（轉送 E2/E4）

1. **`EngineIPCClient.call()` vs notify**：PA design 寫 `client.notify(...)`，但 ipc_client 沒此方法；用 `call()` 帶 monotonic id。Sub-task A Rust handler 落地後做 e2e roundtrip 驗證；若 Rust 端 strict 校驗 `id == null` 才視為 notification，需要 ipc_client 加 `notify()` 方法。
2. **daemon thread 進程退出時被打斷**：`atexit` graceful join 暫不加（YAGNI），對齊 ExecutorConfigCache pattern；Sub-task C 部署後若見 stale socket 警告再加。
3. **`query_h_state_full` 是否需要 FastAPI route 鏡射**：PA §5.1 提到 `governance_routes.py` 或 `h_state_routes.py`，可能想要 FastAPI route 給 GUI scrape；本 sub-task 走 reverse IPC handler 對齊 §4.4 + §10.1。Sub-task C 可加 thin FastAPI wrapper 5 行對 `build_h_state_full_response`。

---

## 教訓（已寫入 E1 memory.md）

1. **Reverse IPC route 真相**：Python 端 reverse IPC 註冊位置 = `ai_service_dispatch.py:_register_handlers()`（不是 `ipc_dispatch.py`）
2. **AIService import circular trap**：tests 用 `from app.ai_service import AIService`，**不**用 `from app.ai_service_dispatch import AIService`（會觸發 partial init circular）
3. **stale staged state（multi-session race）**：commit 後 index stale，`git diff --cached` 為空但 `git status` 報 staged → `git add` 主動 refresh
4. **`git commit --only` vs explicit path add**：multi-session 下絕不用 `-A` / `-a` / `.`；明確列 path
5. **threading.Thread + asyncio.new_event_loop()**：daemon thread 內無 caller's running loop → 安全；對齊 ExecutorConfigCache pattern
6. **DEFAULT-OFF 完整覆蓋**：env-gate 5 case + init no-op + invalidate_async no-op + invalidate_async with disabled+init 三層 no-op 驗證

---

## 下一步

- E2 代碼審查（CLAUDE.md §七 強制鏈）
- E4 測試回歸
- 等 Sub-task A Rust 端 commit 後做 e2e IPC roundtrip 驗證
- Sub-task C 接線（`strategy_wiring.py` + CLAUDE.md §九 + healthcheck [20]）

---

**E1 IMPLEMENTATION DONE: 待 E2 審查**
