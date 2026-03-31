# OpenClaw TODO — 工作計劃清單
# 最後更新：2026-03-31（Wave 0-2 完成後 · E5/E3/PM/PA/FA 審計後）
# 注意：compact 後從此文件恢復工作狀態

---

## 強制工作流程（每 Wave 必須遵守）

```
任何修復/功能 → E1/E1a 並行執行 → E2 代碼審查（必須）→ E4 全量回歸（必須）→ PM 確認 → commit
緊急通道（P0）：跳過 FA/A3/R4，但 E2+E4 絕對不可跳過
最大並行：5 個 E1 Agent 同時修不同文件
15 角色定義詳見 CLAUDE.md §十三
```

---

## 當前測試基準線

```
2445 passed / 17 failed（全部 pre-existing） / 23 warnings（Wave 3c P1-4/10/17 後確認）
路徑：program_code/exchange_connectors/bybit_connector/control_api_v1/
命令：python3 -m pytest tests/ -q --tb=no
```

---

## ██ Wave 3a — P0 新發現（立即執行，~2h）

> 安全閘門缺失，不修復前存在真實攻擊面。
> **前置確認（PA 已完成）**：SEC-H2（/auth/request）為設計意圖，不修。

### [x] P0-NEW-1：`governance_routes.py` `/reconcile` 缺少 Operator 角色驗證
- **檔案**：`app/governance_routes.py`（第 865 行附近 `trigger_manual_reconciliation`）
- **修復**：函數體開頭添加 `_require_operator_role(actor)`
- **同步修復**：第 884 行日誌 `actor` → `_sanitize_log(actor.actor_id)`，`body.reason` → `_sanitize_log(body.reason)`
- **違反原則**：原則 1（單一寫入口）+ 原則 4（策略不能繞過風控）
- **工時**：30m
- **E1 指派**：E1-Alpha

### [x] P0-NEW-2：`governance_routes.py` logger 重複/錯序參數
- **檔案**：`app/governance_routes.py`（第 496-500 行，`request_authorization`）
- **問題**：中文格式字串的 `auth_id` 和 `actor.actor_id` 順序對調，造成日誌顯示誤導
- **修復**：統一參數順序或拆為兩條獨立日誌
- **工時**：10m
- **E1 指派**：E1-Alpha（與 P0-NEW-1 同文件，合併執行）

### [x] P0-NEW-3：`governance_routes.py` 18+ 處 `detail=str(e)` 洩漏內部錯誤
- **檔案**：`app/governance_routes.py`（第 288/446/636/910/935/1038/1065/1107/1145/1186/1433/1477/1504/1550/1590/1627/1654/1732 行，共 18 處）
- **修復**：全部改為 `detail="Internal server error"`，保留 server-side `logger.error(..., exc_info=True)`
- **⚠️ 副作用**：E4 中斷言錯誤訊息內容的測試需同步更新（修復後不再含原始異常字符串）
- **違反原則**：原則 10（認知誠實）
- **工時**：1h + E4 測試更新
- **E1 指派**：E1-Beta

### Wave 3a 強制工作鏈
```
E1-Alpha（P0-NEW-1+2）‖ E1-Beta（P0-NEW-3）
           ↓ 兩者均完成
    E2 代碼審查（所有改動）
           ↓
    E4 全量回歸（重點：governance_routes 測試，含錯誤訊息斷言更新確認）
           ↓
    commit: fix(security): Wave 3a — /reconcile Operator 角色驗證 + 錯誤信息屏蔽
```

---

## ██ Wave 3b — P1 快修（~5h，Wave 3a commit 後並行）

> 所有 P1 快修可最大並行，P1-NEW-1 需 PA 架構確認後才能動手。

### [x] P1-NEW-1：`main.py` openclaw_proxy 轉發 Bearer Token（需 PA 確認）
- **檔案**：`app/main.py`（第 199 行 headers 過濾）
- **問題**：`Authorization` 頭未過濾，原樣轉發至 OpenClaw Gateway（127.0.0.1:18789）
- **PA 確認事項**：OpenClaw Gateway 是否依賴透傳 Token 認證？
  - 若否 → 在過濾列表加 `"authorization"` 即可
  - 若是 → 改用 service-to-service token 方案（需另外設計）
- **違反原則**：原則 2（讀寫分離）
- **工時**：2h（含架構確認）
- **E1 指派**：E1-Zeta（PA 確認後啟動）

### [x] P1-NEW-2：`main_legacy.py` `_COMPILE_STATE_SIG_CACHE` id(fn) → WeakKeyDictionary
- **檔案**：`app/main_legacy.py`（第 658 行附近）
- **問題**：`id(fn)` 作為鍵，Python GC 回收後可能 reuse id 導致緩存誤判
- **修復**：`import weakref` + `weakref.WeakKeyDictionary()` 替換 `dict[int, bool]`，訪問改為 `.get(fn, None)`
- **工時**：45m
- **E1 指派**：E1-Alpha

### [x] P1-NEW-3：`main_legacy.py` `_login_fail_counts` 加 asyncio.Lock + 容量上限
- **檔案**：`app/main_legacy.py`（第 51 行附近）
- **問題雙維度**：(1) 無 `asyncio.Lock`，並發登錄計數競態；(2) 無容量上限，IP 掃描攻擊 OOM
- **修復**：
  - 新增 `_login_fail_lock = asyncio.Lock()`
  - 在 `auth_login` 的讀-修改-寫序列加 `async with _login_fail_lock:`
  - 新增常量 `_LOGIN_FAIL_MAX_IPS = 2000`
  - 清理邏輯：超過上限時先掃描刪除過期（>15min）條目；仍超限則 FIFO 淘汰
- **工時**：1.5h
- **E1 指派**：E1-Beta

### [x] P1-NEW-4：`main_legacy.py` `auth_login` token 重讀文件 → `settings.api_token`
- **檔案**：`app/main_legacy.py`（第 4210-4218 行）
- **問題**：登錄成功後從磁盤重讀 `api_token`，與啟動緩存 `settings.api_token` 不一致
- **修復**：移除文件讀取，直接 `api_token = settings.api_token`
- **工時**：30m
- **E1 指派**：E1-Gamma

### [x] P1-NEW-5：`main.py` openclaw_proxy 異常無日誌
- **檔案**：`app/main.py`（第 214 行 except 塊）
- **修復**：添加 `logger.warning("openclaw_proxy error [%s]: %s", path, type(e).__name__)`（不洩漏完整異常到客戶端）
- **工時**：20m
- **E1 指派**：E1-Gamma（與 P1-NEW-4 同批次）

### [x] P1-NEW-6：`main.py` `OPENCLAW_GATEWAY_HOST` 每次請求讀 env → 啟動緩存
- **檔案**：`app/main.py`（第 192 行）
- **修復**：模組頂層 `_OC_HOST = os.getenv("OPENCLAW_GATEWAY_HOST", "127.0.0.1")`，proxy 函數改用 `_OC_HOST`
- **工時**：30m
- **E1 指派**：E1-Gamma（同批次）

### [x] P1-NEW-7：`layer2_engine.py` `_session_lock` threading.Lock → asyncio.Lock
- **檔案**：`app/layer2_engine.py`（第 185 行）
- **問題**：`run_session` 是 `async def`，混用 `threading.Lock` 語義不清，重構時易死鎖
- **修復**：`asyncio.Lock()` 替換；`acquire(blocking=False)` 改為 `if self._session_lock.locked(): return ...; async with self._session_lock:`
- **⚠️ 注意**：`_client_lock`（模塊級，第 702 行）在 `asyncio.to_thread` 的同步上下文中使用，**保留 threading.Lock 不動**
- **工時**：30m
- **E1 指派**：E1-Delta

### Wave 3b 強制工作鏈
```
E1-Alpha（P1-NEW-2）‖ E1-Beta（P1-NEW-3）‖ E1-Gamma（P1-NEW-4+5+6）‖ E1-Delta（P1-NEW-7）
[PA確認後] E1-Zeta（P1-NEW-1）
           ↓ 全部完成
    E2 代碼審查
           ↓
    E4 全量回歸（重點：auth_login 速率限制測試，Layer2Engine 並發測試）
           ↓
    commit: fix(security): Wave 3b — Token 隔離 + Lock 安全 + 緩存修復
```

---

## ██ Wave 3c — 原有 P1 深度任務（Wave 3b 後，各自獨立）

### [x] P1-4：Decision Lease 閉環驗證（3-4h）
- **問題**：lease 超時後訂單應自動失效，當前未驗證閉環
- **驗收**：lease TTL 到期 → 相關訂單狀態自動變為 REJECTED/CANCELLED
- ✅ 完成：（2026-03-31）
  - **根因 1**：`governance_hub.py` `acquire_lease()` 接受 `ttl_seconds` 參數但從未傳入 `create_draft()`，每個 lease 的 `expires_at_ms` 恆為 `None`，永遠不會過期
  - **根因 2**：`paper_trading_engine.py` `submit_order()` 在 lease 取得後沒有 TOCTOU 二次確認（acquire 後到執行前的過期邊緣情況）
  - **修復 1**：`governance_hub.py` 行 801-814 — `create_draft()` 補傳 `expires_at_ms = now_ms + int(ttl_seconds * 1000)`
  - **修復 2**：`paper_trading_engine.py` 行 1173 後 — acquire 後立即以 `is_within_valid_window` 做二次驗證，失效則 reject + reason="governance_lease_expired"
  - **測試 1（governance_hub）**：`TestLeaseManagement` 新增 3 個 TTL 測試 — expires_at_ms 設定驗證、check_expiry() 自動 EXPIRE、過期後可重新取得新 lease
  - **測試 2（paper_trading_engine）**：`TestGovernanceLeaseFailClosed` 新增 2 個測試 — TOCTOU 過期拒絕（已過期 lease → reject）、有效 lease 不誤拒
  - **結果**：8/8 TestLeaseManagement 通過，5/5 TestGovernanceLeaseFailClosed 通過；整體 2415 passed（較修前 +5），15 pre-existing failures 不變

### [x] P1-10：Perception Plane `register_data()` 注入（3-4h）
- **問題**：register_data() 零調用，Perception Plane 完全未接入任何數據源
- **驗收**：至少 1 條市場數據流調用 register_data() 並可在 Perception Plane 查詢到
- ✅ 完成：（2026-03-31）
  - **根因確認**：`register_data()` 調用代碼早已存在於 `pipeline_bridge.py` 行 330-344（on_tick WS價格 FACT）和行 1335-1348（交易結果 INFERENCE）。注入代碼也存在於 `phase2_strategy_routes.py` 行 356-366。問題是測試中完全缺失 perception plane mock，導致 `_perception_plane` 恆為 None。
  - **修復**：`test_pipeline_bridge.py` 新增 `TestPipelineBridgePerceptionPlane` 類（3 個測試）：
    - Test 1：`set_perception_plane()` 注入路徑驗證
    - Test 2：`on_tick()` 觸發後 mock.register_data 被調用，且 source_type=EXCHANGE_WS + cognitive_level=FACT（EX-07 §1）
    - Test 3：真實 PerceptionPlane.get_stats() 中 objects_registered 在 3 次 tick 後遞增
  - **結果**：8 passed（原 5 + 新增 3），所有測試通過

### [x] P1-17：GovernanceHub TTL 競態修復（3-4h）
- **問題**：lease TTL 與 SM-01 授權 TTL 競態（E3-M5 也指出 is_authorized 緩存鎖外讀取）
- **驗收**：並發場景下 TTL 到期與緩存失效不存在 race window
- ✅ 完成：本次 commit（2026-03-31）
  - **修復 1（E3-M5 鎖外讀取）**：`is_authorized()` 行 530 — 將 `self._cached_auth_state` 先讀到局部變量 `_cached`，避免 `is not None` 判斷通過後另一個線程調用 `_invalidate_auth_cache()` 將其設 `None`，造成 unpack TypeError
  - **TTL 競態確認**：`acquire_lease()` 中 `create_draft` 已傳入 `expires_at_ms`（Wave 2 P1-4/Batch 11 已修），lease TTL 已對齊。無需額外修改
  - **測試**：54/54 test_governance_hub.py 全部通過（含 TestThreadSafety / TestEdgeCasesCacheExpiryRace）

### [ ] P1-16：H0 Gate 確定性門控（3天，獨立 branch，Live 前必須）
> Day 1 ✅ 完成：commit 3ccd982（2026-03-31）— H0GateConfig/Snapshot dataclass + 5 check + 37 tests
> Day 2 ✅ 完成：commit 5d53619（2026-03-31）— H0HealthWorker + 40 新測試（health/risk/cooldown/SLA/worker）
> Day 3 🔄 進行中：pipeline_bridge 集成 + API 端點 + E2+E4 → merge PR
- **要求**：DOC-02 §3.1 · <1ms SLA · 純確定性邏輯 · 無 AI 調用
- **branch**：`feature/p1-16-h0-gate-deterministic`
- **新增文件**：`app/h0_gate.py`（~350 行）+ `tests/test_h0_gate.py`（80+ 測試）
- **修改文件**：`pipeline_bridge.py` / `risk_manager.py` / `governance_routes.py` / `main.py`
- **Day 1**：H0GateConfig/Snapshot dataclass + check_freshness + check_eligibility（E1-Alpha + E1-Beta）
- **Day 2**：check_health + check_risk + check_cooldown + H0HealthWorker + SLA 驗證（<1ms timeit）
- **Day 3**：pipeline_bridge 集成 + API 端點 + E4 全量回歸 + E2 審查 → commit
- **5 個 check**：Freshness（數據 <1000ms）/ Health（CPU/mem/db/network）/ Eligibility（品種白名單）/ Risk Envelope（倉位/曝險/kill switch）/ Cooldown（連虧暫停）
- **集成點**：`pipeline_bridge._process_pending_intents()` 最前置（paper 模式 warn-only，Live 前改 fail-closed）
- **⚠️ Live 前必須**：paper 模式 warn-only 改 fail-closed
- **驗收**：SLA 測試通過（<1ms 均值） · 2522+ tests passed · E2 PASS

### Wave 3c 工作鏈
```
P1-4 ‖ P1-10 ‖ P1-17（並行，各自獨立 E1）
P1-16（獨立 branch，E1 × 2）
每項完成後獨立走 E2 → E4 → commit，不互相等待
```

---

## ██ P2 批次（Wave 3 全部完成後）

### [ ] P3-TECH-1：`GovernanceHub.get_lease(id)` 公開方法（消除 _lease_sm 私有穿透）
- **來源**：E2 Wave 3c 審查 P1-4
- **檔案**：`app/governance_hub.py` + `app/paper_trading_engine.py`
- **工時**：30m

### [ ] P3-TECH-2：`test_acquire_new_lease_after_expiry_is_rejected_by_is_authorized` 命名修正
- **來源**：E2 Wave 3c 審查 P1-4
- **改為**：`test_new_lease_acquirable_after_expiry`
- **工時**：5m

### [ ] P3-TECH-3：`governance_hub.py` 行 755 `grant_paper_authorization` lock 外 invalidate
- **來源**：E2 Wave 3c 審查 P1-17
- **問題**：`_invalidate_auth_cache()` 在鎖釋放後調用，非功能 bug（fail-closed 安全），但 cache 新鮮度有短暫窗口
- **工時**：20m

### [ ] P2-NEW-1：`/paper-live-gate/evaluate` 缺少 Operator 角色（審計污染）
- **檔案**：`app/governance_routes.py`（第 1657 行）
- **修復**：添加 `_require_operator_role(actor)`
- **工時**：20m

### [ ] P2-NEW-2：`pipeline_bridge.py` `_analyst_agent` 重複 None 賦值清理
- **檔案**：`app/pipeline_bridge.py`（第 110 行）
- **修復**：移除重複賦值，保留第 104 行
- **工時**：5m

### [ ] P2-NEW-3：`governance_routes.py` Depends 括號歧義重構
- **檔案**：`app/governance_routes.py`（全部 26 處 `Depends(_get_auth_actor())`）
- **方案（PA 建議）**：新增 `_require_operator` Depends 函數，讓端點签名直接聲明所需角色，消除遺漏可能
- **⚠️ 注意**：語義變化需先在測試環境確認再合並，副作用風險中等
- **工時**：30m（謹慎）

### [ ] P2-NEW-4：`ollama_client.py` retry 死代碼清理（可選）
- **說明**：`max_retries=0`（CLAUDE.md 硬邊界），retry 循環實際只執行一次，分支永不觸發
- **方案 A**：添加注釋說明死代碼為硬邊界執行結果
- **方案 B**：移除 retry 分支（需 PA 確認是否永久硬邊界）
- **工時**：30m

### [ ] P2-NEW-5：`main.py` GATEWAY_HOST 已在 Wave 3b 修復（此項可刪）

### [ ] P2-NEW-6：trading.html class 屬性 CSS injection（降為 LOW）
- **說明**：PA 確認影響極小（不可執行 JS），降為低優先級
- **工時**：45m（E1a 前端）

---

## ██ FA 額外提示（Wave 3 後必須跟進的審計方向）

### 1. 治理端點角色矩陣（Wave 3 後立即，FA + E3）
- `governance_routes.py` 全部 ~30 個端點逐一建立「操作類型 → 所需最低角色」矩陣
- 特別關注：所有觸發 SM 狀態轉換的 POST 端點
- 驗收：端點-角色矩陣文件 + E3 二輪確認無漏項

### 2. 對帳引擎輸入驗證（Wave 3 後，FA + E3 聯合）
- `reconciliation_engine.py` 的 `_reconcile_positions`/`_reconcile_balances` 對邊界值的處理
- 重點：惡意構造的 `paper_state`（如 `qty=-999999`）是否能觸發 FATAL severity 升級風控
- 路徑：`hub.reconcile()` → `_on_reconciliation_mismatch()` → 風控 SM 狀態切換

### 3. threading.Lock 系統性風險評估（Wave 3+ ，E5 + E4）
- 受影響模塊：`decision_lease_state_machine.py` / `authorization_state_machine.py` / `reconciliation_engine.py` / `governance_hub.py` / `multi_agent_framework.py`
- 任務：映射哪些 async 路由調用了帶 threading.Lock 的同步函數
- 設計混合壓力測試（高並發 + 同時觸發 SM 狀態轉換）確認無 event loop 阻塞

### 4. ChangeAuditLog `who` 欄位完整性（Wave 3 後，E4）
- 確保所有審計路徑的 `who` 字段不為 "unknown"
- 驗收：E4 測試覆蓋所有寫入 ChangeAuditLog 的路徑，斷言 who != "unknown"

---

## ██ 後續大方向（P3 / Phase 1-4）

```
P3 批次（~36h · 16 項）：
  GUI 術語友好化（SM-01 等工程術語 → 中文操作員視角）
  性能優化（E5 報告 49 項中優先級最高的）

Phase 1（Wave 3 全部完成後）：
  Batch 1A：H0 Gate 確定性門控（DOC-02 · <1ms SLA · Live 前必須）← P1-16 即此項
  Batch 1B：Cooldown 聯動 + M-of-N 簽名驗證 + 數據品質→風控降級

Phase 2（~10天）：
  L2 模式發現自動化 + Truth Source Registry 形式化
  回測引擎 MVP（策略 alpha 驗證基礎設施）

Phase 3（~15天）：
  L3 假設與實驗管線 + L4 策略進化
  策略 Alpha 驗證 + SM-04 延遲 SLA 壓測

Phase 4（5+21天）：
  Paper Trading 穩定運行 21 天觀察期
  Live 前置條件核驗 + Supervised Live Gate（M 章）
```

---

## ██ 下一步確認事項（PA 架構決策）

在啟動 Wave 3b P1-NEW-1 前，需要 Operator 或 PA 確認：

> **問題**：OpenClaw Gateway（127.0.0.1:18789）是否使用 HTTP `Authorization` header 來驗證來自控制 API 的請求？
> - 若**否** → 直接在 proxy 過濾列表加 `"authorization"`，工時 30m
> - 若**是** → 需要設計獨立的 service-to-service token 機制，工時升至 3-4h

---

## 已完成記錄（可查 git log）

```
bf75254 — fix(governance): Wave 3c — Lease TTL 閉環 + Perception 測試 + TTL 競態
2eda4ec — fix(security): Wave 3b — Token 隔離 + Lock 安全 + 緩存修復
c6a8845 — fix(security): Wave 3a — /reconcile Operator 角色驗證 + 錯誤信息屏蔽
ec0e794 — fix(security): P0+P1 Wave 0-2 安全修復第一批（16 files）
c113ab2 — fix(security): P0 Wave 0-2 安全修復第二批 — paper_engine + pipeline_bridge（10 files）
7f1324f — docs(CLAUDE.md): 更新至 Wave 0-2 全部完成狀態 + 15 角色工作鏈

Wave 0：✅ P0（5項）+ P1（5項）全部完成（E2+E4 通過）
Wave 1：✅ PA-4.3 DI 統一（26 Depends）+ HTTPException 穿透（E2+E4 通過）
Wave 2：✅ P0-8/P1-1/P1-2/P1-6/P1-8/P1-9/P1-13/P1-18 全部完成（E2+E4 通過）
Wave 3a：✅ P0-NEW-1/2/3 全部完成（E2+E4 通過，2026-03-31）
Wave 3b：✅ P1-NEW-1~7 全部完成（E2+E4 通過，2026-03-31）
Wave 3c：✅ P1-4/P1-10/P1-17 完成（E2+E4 通過，2026-03-31）· P1-16 獨立 branch 進行中
```
