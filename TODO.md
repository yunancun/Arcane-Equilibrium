# OpenClaw TODO — 工作計劃清單
# 最後更新：2026-04-01（Batch 7 積壓清掃 · 3440 tests）
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
3440 passed / 21 failed / 17 errors（Batch 7 後；+53 新測試；pre-existing failures 不影響本工作）
路徑：program_code/exchange_connectors/bybit_connector/control_api_v1/ + program_code/local_model_tools/
命令：python3 -m pytest --ignore=database_files -q --tb=no
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

### [x] P1-16：H0 Gate 確定性門控（3天，獨立 branch，Live 前必須）
> Day 1 ✅ 完成：commit 3ccd982（2026-03-31）— H0GateConfig/Snapshot dataclass + 5 check + 37 tests
> Day 2 ✅ 完成：commit 5d53619（2026-03-31）— H0HealthWorker + 40 新測試（health/risk/cooldown/SLA/worker）
> Day 3 ✅ 完成：commit 2ed20f0（2026-03-31）— pipeline 集成 + API 端點 + risk cooldown 推送 + 18 新測試
- ✅ 完成：commit 2ed20f0（2026-03-31）
- **要求**：DOC-02 §3.1 · <1ms SLA · 純確定性邏輯 · 無 AI 調用
- **branch**：`feature/p1-16-h0-gate-deterministic`
- **新增文件**：`app/h0_gate.py`（~830 行）+ `tests/test_h0_gate.py`（94 測試）
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

### [x] P3-TECH-1：`GovernanceHub.get_lease(id)` 公開方法（消除 _lease_sm 私有穿透）
- **來源**：E2 Wave 3c 審查 P1-4
- **修復**：新增 `get_lease()` + `drive_lease_expiry()` 公開方法；`paper_trading_engine.py` 改用公開 API
- **工時**：30m
- ✅ 完成：Sprint 4b（2026-03-31）

### [x] P3-TECH-2：`test_acquire_new_lease_after_expiry_is_rejected_by_is_authorized` 命名修正
- **改為**：`test_new_lease_acquirable_after_expiry`
- **工時**：5m
- ✅ 完成：Sprint 4b（2026-03-31）

### [x] P3-TECH-3：`governance_hub.py` 行 755 `grant_paper_authorization` lock 外 invalidate
- **修復**：`_invalidate_auth_cache()` 移入 `with self._lock:` 塊末尾（RLock 可重入，無死鎖風險）
- **工時**：20m
- ✅ 完成：Sprint 4b（2026-03-31）

### [x] P2-NEW-1：`/paper-live-gate/evaluate` 缺少 Operator 角色（審計污染）
- **檔案**：`app/governance_routes.py`（第 1657 行）
- **修復**：添加 `_require_operator_role(actor)` + `except HTTPException: raise` 穿透 + logger %s 佔位符
- **工時**：20m
- ✅ 完成：Sprint 4a（2026-03-31）

### [x] P2-NEW-2：`pipeline_bridge.py` `_analyst_agent` 重複 None 賦值清理
- **檔案**：`app/pipeline_bridge.py`（第 110 行）
- **修復**：移除重複賦值，保留第 104 行
- **工時**：5m
- ✅ 完成：Sprint 4a（2026-03-31）

### [x] P2-NEW-3：`governance_routes.py` Depends 括號歧義重構
- **檔案**：`app/governance_routes.py`（全部 26 處 `Depends(_get_auth_actor())`）
- **方案（PA 建議）**：新增 `_require_operator_auth()` 函數定義（行 110-129），不替換現有端點（副作用風險控制）
- **⚠️ 注意**：語義變化需先在測試環境確認再合並，副作用風險中等
- **工時**：30m（謹慎）
- ✅ 完成：Sprint 4b（2026-03-31）
- **FA-1 發現**：`POST /auth/request` + `POST /risk/de-escalation/request` 缺 Operator 驗證 → 追加為 P2-NEW-7/8

### [x] P2-NEW-4：`ollama_client.py` retry 死代碼清理（可選）
- **說明**：`max_retries=0`（CLAUDE.md 硬邊界），retry 循環實際只執行一次，分支永不觸發
- **修復（方案 A）**：3 處 NOTE 注釋（OllamaConfig 欄位 + retry 分支 + 不可達 return）
- **工時**：30m
- ✅ 完成：Sprint 4b（2026-03-31）

### [x] P2-NEW-5：`main.py` GATEWAY_HOST 已在 Wave 3b 修復（此項可刪）
- ✅ 完成：條目已確認過時，Wave 3b P1-NEW-6 已修復，無需代碼改動

### [x] P2-NEW-9：`scout_routes.py` async 路由阻塞 event loop（Live 前必須修復）
- **來源**：FA-3 threading.Lock 系統性評估（2026-03-31）
- **修復（方案 A）**：5 個路由全部 `async def` → `def`（post_market_signal / post_event_alert / get_status / get_intel / get_alerts）
- **工時**：1h + E4
- ✅ 完成：Sprint 4e（2026-03-31）

### [x] P2-NEW-7：`POST /auth/request` 缺少 Operator 角色驗證
- **來源**：FA-1 端點角色矩陣審計（Sprint 4b）
- **檔案**：`app/governance_routes.py`（`request_authorization` 函數）
- **問題**：調用 `create_draft()` + `submit_for_approval()`，屬寫入操作，但無 `_require_operator_role(actor)`
- **修復**：函數體開頭添加 `_require_operator_role(actor)` + `except HTTPException: raise`
- **工時**：20m
- ✅ 完成：Sprint 4c（2026-03-31）

### [x] P2-NEW-8：`POST /risk/de-escalation/request` 缺少 Operator 角色驗證
- **來源**：FA-1 端點角色矩陣審計（Sprint 4b）
- **檔案**：`app/governance_routes.py`（`request_de_escalation` 函數）
- **問題**：調用 `hub.request_de_escalation()`，向降級隊列寫入，但無 `_require_operator_role(actor)`
- **修復**：函數體開頭添加 `_require_operator_role(actor)` + `except HTTPException: raise`；logger f-string → %s
- **工時**：20m
- ✅ 完成：Sprint 4c（2026-03-31）

### [x] P2-NEW-6：trading.html class 屬性 CSS injection（降為 LOW）
- **說明**：PA 確認影響極小（不可執行 JS），降為低優先級
- **修復**：`common.js` 新增 `ocSanitizeClass()` 白名單函數；`trading.html` 行 461 改用 `ocSanitizeClass(state)`
- **工時**：45m（E1a 前端）
- ✅ 完成：Sprint 4a（2026-03-31）

---

## ██ FA 額外提示（Wave 3 後必須跟進的審計方向）

### 1. 治理端點角色矩陣（Wave 3 後立即，FA + E3）
- `governance_routes.py` 全部 ~30 個端點逐一建立「操作類型 → 所需最低角色」矩陣
- 特別關注：所有觸發 SM 狀態轉換的 POST 端點
- 驗收：端點-角色矩陣文件 + E3 二輪確認無漏項

### [x] 2. 對帳引擎輸入驗證（FA-2，Wave 3 後，FA + E1 聯合）
- `reconciliation_engine.py` 的 `_reconcile_positions`/`_reconcile_balances` 對邊界值的處理
- 重點：惡意構造的 `paper_state`（如 `qty=-999999`）是否能觸發 FATAL severity 升級風控
- 路徑：`hub.reconcile()` → `_on_reconciliation_mismatch()` → 風控 SM 狀態切換
- ✅ 完成：修復 3 個漏洞（BUG-1 NaN qty WARNING→FATAL / BUG-2 NaN balance 靜默接受→CRITICAL / BUG-3 負數 qty local-only 不報告→FATAL）
  + 新增 TestBoundaryInputValidation（11 測試全過），55/55 passed（2026-03-31）

### [x] 3. threading.Lock 系統性風險評估（FA-3，Wave 3+ ，E5 + FA）
- 受影響模塊：`decision_lease_state_machine.py` / `authorization_state_machine.py` / `reconciliation_engine.py` / `governance_hub.py` / `multi_agent_framework.py`
- ✅ 完成：評估報告（2026-03-31）— 整體風險 MEDIUM，4/5 模塊安全
- **發現：`scout_routes.py` 2 個 async 路由直接調用 `threading.Lock` 同步方法（ScoutAgent）**
  - `async def post_market_signal()` → `SCOUT_AGENT.produce_intel()`（Lock @ multi_agent_framework:378）
  - `async def post_event_alert()` → `SCOUT_AGENT.produce_event_alert()`（Lock @ multi_agent_framework:378）
  - 修復方案：改為 `def`（sync routes）或用 `asyncio.to_thread()` 包裝
  - 追加為 P2-NEW-9（Live trading 前必須修復）

### [x] 4. ChangeAuditLog `who` 欄位完整性（Wave 3 後，E4）
- 確保所有審計路徑的 `who` 字段不為 "unknown"
- 驗收：E4 測試覆蓋所有寫入 ChangeAuditLog 的路徑，斷言 who != "unknown"
- ✅ 完成：新增 TestChangeAuditLogWhoField（6 測試，5 passed + 1 skipped），test_governance_hub.py 59 passed（2026-03-31）

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

## ██ Wave 5：多 Agent 正式落地 + H1-H5 接通（CC 條件通過 · Sprint 0 先行）

**CC 評級**：條件通過（G-01 + G-05 兩個 BLOCKER 修復後才能啟動 Sprint 5a）
**Wave 5 目標**：≥ 2600 tests · 業務完整度 32% → ~45%
**設計文件**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-03-31--wave5_final_dispatch.md`

---

### ██ Sprint 0：BLOCKER 前置修復（並行執行，~6h 含 E2+E4）

### [x] G-05【硬阻塞 · 原則 3】`executor_agent.py` 缺少 `acquire_lease()`
- **違反**：原則 3（AI 輸出≠命令）— Guardian 批准 ≠ Decision Lease
- **文件**：`app/executor_agent.py`
- **問題**：`execute_order()` 第 280 行 `submit_order()` 前無 `acquire_lease()` 調用；`__init__()` 無 `governance_hub` 參數
- **修復**：
  1. `__init__()` 新增 `governance_hub: Optional[Any] = None` → `self._governance_hub = governance_hub`
  2. `execute_order()` 第 280 行前插入：
     ```python
     lease_id = self._governance_hub.acquire_lease(intent_id=intent_id, scope="TRADE_ENTRY", ttl_seconds=30) if self._governance_hub else None
     if self._governance_hub and lease_id is None:
         return ExecutionReport(..., success=False, error="governance_lease_acquisition_failed")
     ```
  3. 更新所有 `ExecutorAgent(...)` 初始化調用點（`phase2_strategy_routes.py` + 測試文件）傳入 `governance_hub`
  4. 補充 lease=None fail-closed 測試用例
- **指派**：E1-Alpha（2h）→ E2（1.5h）→ E4（1.5h，與 G-01 共用）
- **前置**：無（直接開始）
- ✅ 完成：commit d57ed05（2026-03-31）

### [x] G-01【硬阻塞 · DOC-08 §12】每日 AI 硬上限 `$15.0` → `$2.0`
- **違反**：DOC-08 §12 安全不變量 + 原則 5（生存>利潤）
- **修復文件**（5 處）：
  - `app/layer2_types.py:58`：`DEFAULT_DAILY_HARD_CAP_USD = 15.0` → `= 2.0`
  - `app/static/tab-ai.html:335`：`|| 15` → `|| 2`
  - `app/static/tab-ai.html:426`：`|| 15` → `|| 2`
  - `app/static/tab-ai.html:441`：`|| 15` → `|| 2`
  - `tests/test_layer2.py:201`：`assert d["daily_hard_cap_usd"] == 15.0` → `== 2.0`
- **指派**：E1-Beta（1h）→ 與 G-05 共用 E2+E4
- **前置**：無（與 G-05 並行）
- ✅ 完成：commit d57ed05（2026-03-31）

---

### ██ Sprint 5a：H1-H5 核心接通（Sprint 0 E2+E4 通過後啟動，~15h 含 E2+E4）

### [x] 5a-1：Scout→Strategist 情報鏈路端到端驗證
- **代碼已確認**：`produce_intel()` 已有 `bus.send(STRATEGIST, INTEL_OBJECT)` 實現（multi_agent_framework.py:428），bus 已注入，Strategist 已訂閱。此任務是**驗證**而非**實現**。
- **驗證清單**：
  1. pipeline_bridge.py:903 的 produce_intel() 調用確認 relevance_score ≥ 0.3（threshold）
  2. Strategist on_message() INTEL_OBJECT 收到後 `stats["intel_received"]` 遞增可觀察
  3. 端到端：scout_routes 手動觸發 → bus.send → Strategist._handle_intel() 確認執行
- **如發現 relevance_score 低於 threshold**：調整 threshold 或提高調用端 score
- **指派**：E1-Alpha（1h，純驗證 + E4 觀察點補充）
- **前置**：Sprint 0 完成
- ✅ 完成：commit ccdff73（2026-03-31）— bus.send 鏈路確認，intel_received stats 可觀察

### [x] 5a-2：H0 Gate warn-only → blocking 正式啟用
- **文件**：`app/pipeline_bridge.py` `_process_pending_intents()`
- **問題**：H0 Gate 目前 warn-only，不實際攔截 TradeIntent
- **修復**：H0 Gate 返回 False 時 skip 該 intent；確認 `max_pending_intents=50` 上限真實生效
- **指派**：E1-Alpha（1h）
- **前置**：Sprint 0 完成
- ✅ 完成：commit ccdff73（2026-03-31）— `continue` blocking + `intents_h0_blocked` 計數器

### [x] 5a-3：H1 ThoughtGate MVP（budget / complexity / cooldown 三條規則）
- **文件**：`app/strategist_agent.py` `_handle_intel()` 方法（第 287 行）
- **實現**：AI 調用前插入 H1 判斷：(1) budget 充足？ (2) signal complexity（rule-based）(3) cooldown 檢查
- **CC 強制**：Ollama 超時（timeout=5s）→ 必須走 `_heuristic_evaluate()`，**不可 allow-all**（原則 6）
- **注意**：`_handle_intel()` 是同步方法（MessageBus 回調），Ollama 調用用同步 HTTP 或 threading.Thread，不可用 await
- **指派**：E1-Beta（3h）
- **前置**：Sprint 0 完成
- ✅ 完成：commit ccdff73（2026-03-31）— H1 三條 gate（budget/complexity/cooldown）均 fail-closed → heuristic

### [x] 5a-4：Strategist shadow=False 驗證 + 正式切換
- **文件**：`app/phase2_strategy_routes.py:155`（`StrategistConfig(shadow=True)`）
- **實現**：
  1. shadow=True 狀態先確認 AC-3（intel 到達 Strategist stats counter 遞增）
  2. 通過 `SYSTEM_DIRECTIVE shadow_off` 切換 shadow=False
  3. 確認 TradeIntent → Guardian → `acquire_lease()` → `execute_order()` 完整鏈路
- **前置**：5a-1、5a-2、**G-05（必須先完成）**
- **指派**：E1-Alpha（1.5h）
- ✅ 完成：commit ccdff73（2026-03-31）— shadow=False 正式切換，acquire_lease 前置條件確認

### [x] 5a-5：H2 預算門控接入 Strategist
- **文件**：`app/strategist_agent.py` `_handle_intel()`
- **實現**：H1 判斷 should_call_ai=True 後，調用 `layer2_cost_tracker.check_daily_budget(model_tier)` → 超預算降級 L1 或 block
- **前置**：5a-3
- **指派**：E1-Beta（1.5h）
- ✅ 完成：commit ccdff73（2026-03-31）— Layer2CostTracker 注入 StrategistAgent，H1 budget gate 接入

### [x] 5a-6：H3 ModelRouter 路由接入（l1_9b / l1_27b / l2）
- **文件**：`app/strategist_agent.py` `_handle_intel()`
- **實現**：基於 complexity + urgency 路由模型 tier；**L2 必須在 threading.Thread 執行，不阻塞 on_tick**
- **前置**：5a-5
- **指派**：E1-Beta（2h）
- ✅ 完成：commit ccdff73（2026-03-31）— 三段路由 l1_9b/l1_27b/l2，L2 threading.Thread daemon=True

### Sprint 5a 工作鏈
```
E1-Alpha（5a-1+2+4）‖ E1-Beta（5a-3+5+6）完全並行
  ↓ 均完成
E2（2h，重點：H1 timeout 走 heuristic / L2 在獨立線程 / max_pending_intents 上限）
  ↓
E4（2h，AC-3 Scout intel 可觀察 + H1 timeout mock 測試 + ≥ 2575 passed）
```

---

### ██ Sprint 5b：Agent 落地完善（Sprint 5a E2+E4 通過後啟動，~13h 含 E2+E4）

### [x] 5b-1：H4 AI 輸出驗證（validate_output）
- **文件**：`app/strategist_agent.py`，H3 AI 調用後
- **實現**：驗證輸出非空 / action 字段存在 / confidence ∈ [0,1] / 驗證失敗 → fallback heuristic
- **指派**：E1-Gamma（1.5h）
- **前置**：Sprint 5a 完成
- ✅ 完成：commit 9478c00（2026-03-31）— `_validate_ai_output()` confidence∈[0,1] fail-closed → heuristic

### [x] 5b-2/6：H5 CostLogger 接入（Ollama 追蹤 + ROI disclaimer）
- **文件**：`app/layer2_cost_tracker.py`
- **實現**：
  1. 新增 `record_ollama_call(model: str, duration_ms: float, prompt_tokens: int)` 方法
  2. Strategist L1 調用後同步記錄
  3. **CC 原則 10 要求**：`get_summary()` / `get_cost_edge_ratio()` 回傳 dict 加 `roi_basis: "paper_simulation_only"` + `roi_disclaimer: "基於模擬 PnL，非真實盈虧"`
- **指派**：E1-Gamma（2.5h）
- **前置**：Sprint 5a 完成
- ✅ 完成：commit 9478c00（2026-03-31）— `record_ollama_call()` + `roi_basis:"paper_simulation_only"` 雙端 marker

### [x] 5b-3：`apply_ai_consultation()` stub 替換為真實 H 鏈
- **文件**：`app/main_legacy.py:3876`（stub 位置）
- **實現**：接入 `strategist_agent._handle_intel()` 路徑，或標記廢棄並移除死代碼
- **指派**：E1-Delta（2h）
- **前置**：Sprint 5a 完成
- ✅ 完成：commit 9478c00（2026-03-31）— 標記 DEPRECATED + `deprecation_notice` 字段，簽名不變保持向後兼容

### [x] 5b-4：ScoutWorker 後台定時掃描線程
- **文件**：新建 `app/scout_worker.py`
- **實現**：`threading.Thread(daemon=True)`，每 30min 觸發全品種掃描；進程退出正確停止
- **指派**：E1-Delta（3h）
- **前置**：5a-1 確認後
- ✅ 完成：commit 9478c00（2026-03-31）— ScoutWorker daemon + 1s interruptible sleep + exception-safe + start() 冪等

### [x] 5b-5：原則 14 集成測試（Mock Ollama 崩潰全流程）
- **文件**：新建 `tests/test_h_chain_integration.py`
- **實現**：Mock `is_available()=False` → 確認系統退化 L0 → 交易鏈路不中斷（FA AC-2 / CC 原則 14）
- **指派**：E4 直接執行（1.5h）
- **前置**：Sprint 5a 完成
- ✅ 完成：commit 9478c00（2026-03-31）— 6 個 P14 集成測試，Mock Ollama crash → L0 fallback → 交易鏈路不中斷

### Sprint 5b 工作鏈
```
E1-Gamma（5b-1+2/6）‖ E1-Delta（5b-3+4）‖ E4（5b-5）完全並行
  ↓ 均完成
E2（1.5h，重點：ScoutWorker 線程安全 / roi_basis 標記覆蓋完整）
  ↓
E4（2h，AC-1/2/7/8 驗收 + Mock Ollama 崩潰集成測試 + ≥ 2600 passed）
```

---

## ██ 後續大方向（P3 / Phase 1-4）

```
P3 批次（~36h · 16 項）：
  GUI 術語友好化（SM-01 等工程術語 → 中文操作員視角）— 用戶確認延後
  性能優化（E5 報告 49 項中優先級最高的）

Phase 1 Batch 1B（Wave 5 完成後）：
  Cooldown 聯動確認（H0Gate → RiskManager set_h0_gate 注入驗證）
  數據品質 → 風控降級（H0Gate freshness_score warn-only 先行）
  ~~M-of-N 簽名驗證~~ — 移出，待有多個 Operator 時再設計

Phase 2（~10天）：
  L2 模式發現自動化 + Truth Source Registry 形式化
  回測引擎 MVP（策略 alpha 驗證基礎設施）

Phase 3（~15天）：
  L3 假設與實驗管線 + L4 策略進化

Phase 4（5+21天）：
  Paper Trading 穩定運行 21 天觀察期
  Live 前置條件核驗 + Supervised Live Gate（M 章）
```

---

## ██ Wave 6：TD-1 修復 + FA-7 學習管線注入 + Batch 1B

> **啟動條件**：Wave 5 全部完成（2610 passed），Wave 5a/5b commit 已 push。
> **目標**：消除 Principle 3 雙重標準 + 打通學習管線輸入 + Batch 1B 安全閘補全
> **工作鏈強制規則**：E1 完成 → E2 審查 → E4 回歸（任何情況不跳過）

---

### ██ Sprint 0（TD-1）：pipeline_bridge acquire_lease 補入（P1，~2h + E2+E4）

> **優先順序最高**：PA 發現架構缺口，Principle 3 在 pipeline_bridge 直接路徑未完整實施。
> **前置確認**：`_governance_hub` 已存在於 pipeline_bridge（`__init__` line 95，`set_governance_hub()` line 165）。`acquire_lease(intent_id, scope, ttl_seconds)` 簽名在 governance_hub.py line 772。

### [x] TD-1：`pipeline_bridge.py` `_process_pending_intents()` 補入 `acquire_lease()`
- **文件**：`app/pipeline_bridge.py`，line 695-710（Guardian APPROVED 後、`submit_order()` 前）
- **問題**：Guardian 批准後直接調用 `self._engine.submit_order()`，跳過 Decision Lease 控制面
- **修復方案**：
  1. 在 line 700 的 `# B6: For limit orders...` 之前，Guardian APPROVED 分支結束後插入：
     ```python
     # Principle 3: acquire Decision Lease before submit (DOC-01 §5.3)
     # 原則 3：提交訂單前必須獲取決策租約
     if self._governance_hub:
         _intent_id = getattr(intent, "intent_id", None) or str(id(intent))
         _lease_token = self._governance_hub.acquire_lease(
             intent_id=_intent_id,
             scope="TRADE_ENTRY",
             ttl_seconds=30.0,
         )
         if _lease_token is None:
             # acquire_lease fail-closed: lease not granted → skip this intent
             # acquire_lease fail-closed：租約未獲批 → 跳過此意圖
             logger.warning(
                 "Lease not granted for intent %s %s — skipped (fail-closed) / 租約未獲批，跳過意圖",
                 intent.symbol, intent.side,
             )
             with self._lock:
                 self._stats["intents_rejected"] += 1
             continue
     ```
  2. 修改後須確認 `MODIFIED` 路徑（verdict.result == MODIFIED）也走同樣的 lease gate（目前 MODIFIED 路徑與 APPROVED 路徑合流至同一 `submit_order()` 調用，只需插入在 submit_order 之前即可）
- **E2 審查重點**：租約在 `submit_order()` 失敗時是否需要 `release_lease()`？（確認 GovernanceHub TTL 到期自動釋放即可，無需手動 release）
- **E4 新增測試**：
  1. `test_process_pending_intents_acquire_lease_called`：Guardian APPROVED → `acquire_lease()` 被調用
  2. `test_process_pending_intents_lease_fail_closed`：`acquire_lease()` 返回 None → intent 跳過，`intents_rejected` +1
  3. `test_process_pending_intents_no_governance_hub`：`_governance_hub=None` → 跳過 lease 直接 submit（向後兼容）
- **違反原則**：原則 3（AI 輸出 ≠ 即時命令）
- **指派**：E1-Alpha
- **工時**：2h（E1 實現 1h + E2 0.5h + E4 0.5h）
- **目標測試數**：≥ 2615 passed（+5）
- ✅ 完成：commit 待提交（2026-03-31）— 4 個新測試，2614 passed，E2 PASS，E4 PASS

### Sprint 0 工作鏈
```
E1-Alpha（TD-1，~1h）
  ↓
E2 代碼審查（重點：fail-closed 路徑 / lease 在 MODIFIED+APPROVED 兩條路徑均覆蓋 / 無 release 遺漏）
  ↓
E4 全量回歸（新增 3 個 lease 測試 + ≥ 2615 passed 確認）
  ↓
PM 確認 + commit
```

---

### ██ Sprint 1a（FA-7）：Perception Plane 學習管線注入（阻塞 Phase 2，~3h + E2+E4）

> **重要性**：FA 判定 BLOCKER for learning。Principle 12（持續進化）唯一未實施原則。
> `register_data()` 在 `on_tick()` 的 WS ticker 路徑已有調用（line 347），在 `_emit_round_trip()` 也有 (line 1473)。
> 問題：`position_close` 事件（止損觸發路徑）未調用。需補 `_on_round_trip_complete` 調用後的注入路徑。

### [x] FA-7：`pipeline_bridge.py` position_close 事件注入 `register_data()`
- **文件**：`app/pipeline_bridge.py`
- **問題分析**：
  - `_emit_round_trip()` （line 1470-1476）：已有 `register_data()` 調用 ✅
  - `_on_round_trip_complete()` （line 1490-1498）：委託給 `_emit_round_trip()`，間接覆蓋 ✅
  - `on_tick_result()` （line 1500+）：tick 路徑平倉（risk_auto_close/time stop/soft stop）只調用 `_emit_round_trip`，應已覆蓋
  - **真正的缺口**：`_check_stops()` 的止損平倉路徑（line 839-844），`submit_order()` 結果後未觸發 `register_data()`
- **修復方案**：
  1. 確認 `_check_stops()` 的 `submit_order()` 成功後，仿照 `_on_round_trip_complete()` 調用 `self._emit_round_trip()`（或直接調用 `_perception_plane.register_data()`）
  2. 在 `phase2_strategy_routes.py` 中確認 `set_perception_plane()` 已注入（確認不是死代碼）
  3. 新增測試：mock `_perception_plane` → 觸發止損 → 確認 `register_data()` 被調用至少 1 次
- **E2 審查重點**：`register_data()` 是否線程安全？（查 PerceptionPlane 實現，確認加鎖）
- **E4 新增測試**（FA 驗收標準）：
  1. `test_perception_plane_register_data_on_stop_close`：止損觸發 → `register_data()` 調用
  2. `test_perception_plane_register_data_on_tick_close`：tick 路徑平倉 → `register_data()` 調用
  3. `test_perception_plane_register_data_on_intent_close`：intent 路徑平倉 → `register_data()` 調用
- **可觀察性要求**：L2 observation count 在一個交易週期後至少遞增 1（FA 驗收標準）
- **違反原則**：原則 12（持續進化）
- **指派**：E1-Beta
- **工時**：3h（E1 實現 1.5h + E2 0.5h + E4 1h）
- **前置**：Sprint 0 完成後（同一文件，避免衝突）
- **目標測試數**：≥ 2620 passed（+5）
- ✅ 完成：commit 8f123a7（2026-03-31）— 5 個新測試，含 P1-1 rejected_reason 守衛修復

### Sprint 1a 工作鏈
```
（Sprint 0 完成後啟動，避免同文件衝突）
E1-Beta（FA-7，~1.5h）
  ↓
E2 代碼審查（重點：stop 路徑是否有 round_trip 完整鏈路 / perception_plane 線程安全 / register_data 參數正確）
  ↓
E4 全量回歸（3 個 register_data 場景測試 + ≥ 2620 passed 確認）
  ↓
PM 確認 + commit
```

---

### ██ Sprint 1b（Batch 1B）：安全閘補全（可與 Sprint 1a 並行，~5.5h + E2+E4）

> Sprint 1b 與 Sprint 1a 操作不同文件，可並行啟動。

### [x] 1B-1：Cooldown 聯動端到端 smoke test（E4，~2h）
- **文件**：`tests/test_h0_gate_cooldown_integration.py`（新建）
- **目標**：驗證 RiskManager 觸發 cooldown 事件後，H0Gate.update_risk() 接收並在下一次 check() 中阻塞
- **測試場景**（FA 驗收標準，最少 5 個）：
  1. RiskManager 觸發 cooldown → H0Gate.update_risk() 被調用
  2. Cooldown 期間 H0Gate.check() 返回 allowed=False
  3. Cooldown 到期後 H0Gate.check() 恢復 allowed=True
  4. 邊界：cooldown_seconds=0 不阻塞
  5. 邊界：cooldown 期間不同 symbol 仍可通過（若設計為 global，全阻；若 symbol 粒度，僅阻同 symbol）
- **指派**：E4 直接執行（不需 E1）
- **工時**：2h
- ✅ 完成：commit 8f123a7（2026-03-31）— 5 個 smoke test，RiskManager→H0Gate 聯動鏈路驗證通過

### [x] 1B-2：H0Gate freshness 狀態 API 擴充（E1，~1.5h）
- **文件**：`app/governance_routes.py`（`/governance/h0-gate/status` 端點擴充）
- **問題**：現有 `/governance/h0-gate/status` 返回基礎狀態，但 freshness 原始值（`price_ts` 距今毫秒數）和 freshness_score 未暴露，Operator 無法判斷數據新鮮度
- **修復方案**：在現有端點回應 dict 中增加：
  ```python
  "freshness_age_ms": int(time.time() * 1000) - gate._last_price_ts if gate._last_price_ts else None,
  "freshness_score": gate._freshness_score if hasattr(gate, "_freshness_score") else None,
  "data_quality_warn_only": True,  # 說明 freshness 目前為 warn-only 模式
  ```
- **指派**：E1-Gamma
- **工時**：1.5h
- ✅ 完成：commit 8f123a7（2026-03-31）— freshness_age_ms + freshness_score + data_quality_warn_only 三個字段

### [x] 1B-3：TD-3 H5 cost_tracker 靜默異常修復（E1，~15m）
- **文件**：`app/strategist_agent.py`（約 line 485，`record_ollama_call()` except Exception: pass）
- **問題**：記錄 AI 成本失敗時靜默吞異常（PA TD-3）
- **修復**：改為 `logger.warning("H5 cost record failed: %s", e)`
- **指派**：E1-Gamma（與 1B-2 同時執行）
- **工時**：15m
- ✅ 完成：commit 8f123a7（2026-03-31）

### [x] 1B-4：TD-4 _h1_cooldown LRU cap（E1，~30m）
- **文件**：`app/strategist_agent.py`（_h1_cooldown 字典）
- **問題**：無容量上限（PA TD-4），650 symbol 長期運行後無清理機制
- **修復**：改用 `collections.OrderedDict` 手動 LRU（容量上限 1000）或直接設時間窗口清理
- **指派**：E1-Gamma（與 1B-2 同時執行）
- **工時**：30m
- ✅ 完成：commit 8f123a7（2026-03-31）— 過期清理策略，容量上限 1000

### Sprint 1b 工作鏈
```
E4（1B-1 Cooldown smoke test，~2h）‖ E1-Gamma（1B-2+TD-3+TD-4，~2.5h）完全並行
  ↓ 均完成
E2 代碼審查（E1-Gamma 改動：freshness API + cost_tracker logger + LRU cap）
  ↓
E4 全量回歸（1B-1 新測試 + 1B-2 端點測試 + ≥ 2630 passed 確認）
  ↓
PM 確認 + commit
```

---

### ██ Sprint 2（P2 批次選擇性，可分批，~20h）

> Sprint 1a+1b 完成後啟動。以下為初步清單，正式啟動前 PA 確認文件/行號。

### [x] P2-6/7/8：RiskManager 邊界值與極端市況測試（E1+E4，~6h）
- **文件**：`app/risk_manager.py`
- **內容**：邊界值（position limit 剛好觸發）+ 極端市況（price=0, qty=0, NaN）+ 連虧止損重置
- **指派**：E1-Alpha + E4
- ✅ 完成：commit 43dd2f5（2026-03-31）

### [x] P2-12/15：pipeline_bridge 邊界用例（E1+E4，~4h）
- **文件**：`app/pipeline_bridge.py`
- **內容**：on_tick 邊界（price=None, ts 超前）+ pending_intents 清理邏輯（積壓 > max_pending_intents）
- **指派**：E1-Beta + E4
- ✅ 完成：commit 43dd2f5（2026-03-31）

### [x] TD-2：廢棄 StrategistAgent collect 路徑（E1+E2+E4，~3h）
- **文件**：`app/pipeline_bridge.py` + `app/strategist_agent.py`
- **內容**：所有 AI intent 強制走 MessageBus → ExecutorAgent（PA 建議，消除語義模糊）
- **前置**：Sprint 0 TD-1 完成後（同文件）
- **指派**：E1-Alpha
- ✅ 完成：commit 43dd2f5（2026-03-31）

### [x] FA-8：GUI cost_edge_ratio None 處理（E1a，~1h）
- **文件**：`static/tabs/tab-ai.html`（或對應 JS 文件）
- **內容**：`get_cost_edge_ratio()` 返回 None 時顯示 "N/A（數據不足）" 而非崩潰
- **指派**：E1a
- ✅ 完成：commit 43dd2f5（2026-03-31）

### Sprint 2 工作鏈
```
PA 確認具體行號 → E1-Alpha（P2-6/7/8）‖ E1-Beta（P2-12/15）‖ E1-Alpha-2（TD-2）‖ E1a（FA-8）並行
  ↓
E2 + E4
  ↓
PM 確認 + commit
```

---

### Wave 6 測試目標

| Sprint | 目標 | 新增測試說明 |
|--------|------|------------|
| Sprint 0 完成後 | ≥ 2615 passed | +5（TD-1：lease gate 3 個 + 向後兼容 2 個）|
| Sprint 1a 完成後 | ≥ 2620 passed | +5（FA-7：register_data 3 個場景 + 2 個邊界）|
| Sprint 1b 完成後 | ≥ 2630 passed | +10（1B-1 smoke test 5 個 + 1B-2 端點 3 個 + 其他）|
| Sprint 2 完成後 | ≥ 2650 passed | +20（P2-6/7/8 + P2-12/15 + TD-2 + FA-8）|

---

## ██ 後續大方向（P3 / Phase 1-4）

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
Wave 3c：✅ P1-4/P1-10/P1-17 完成（E2+E4 通過，2026-03-31）
P1-16：✅ Day 1+2+3 全部完成（commit 3ccd982/5d53619/2ed20f0，2026-03-31）· 已 merge（commit 03a5b29）
Wave 4 Sprint 4a：✅ P2-NEW-1/2/6 安全修復 + CSS（commit a2f4c70，2026-03-31）
Wave 4 Sprint 4b：✅ P2-NEW-3/4 + P3-TECH-1/2/3 技術清理（commit 6c80bc9，2026-03-31）
Wave 4 Sprint 4c：✅ P2-NEW-7/8 Operator 驗證補齊（commit 448f1e7，2026-03-31）
Wave 4 Sprint 4d：✅ FA-2/3/4 邊界值防護 + threading 評估（commit 9cc134a，2026-03-31）
Wave 4 Sprint 4e：✅ P2-NEW-9 async→sync + P2-NEW-5 清理（commit 87c2651，2026-03-31）
Wave 6 Sprint 2：✅ P2-6/7/8 + P2-12/15 + TD-2 + FA-8（commit 43dd2f5，2026-03-31）
Cleanup Sprint：✅ H0 stale → False + GovernanceHub.is_globally_enabled() + startup integrity + MessageBus load tests（commit 973c595，2026-03-31）
Phase 2 Batch 2A：✅ TruthSourceRegistry 46 tests + AnalystAgent/StrategistAgent 集成（commit cf7ef5d，2026-03-31）
Phase 2 Batch 2B：✅ BacktestEngine MVP 57 tests（commit cf7ef5d，2026-03-31）
```

---

## ██ Cleanup Sprint（已完成）

### [x] CS-1：H0 Gate `data_quality_warn_only` 過時注釋修正
- **文件**：`app/governance_routes.py`（`/governance/h0-gate/status` 端點）
- **問題**：`data_quality_warn_only: True` 是過時注釋，H0 Gate 自 Sprint 5a 起已為 fail-closed
- **修復**：改為 `False`（反映真實行為）
- ✅ 完成：commit 973c595（2026-03-31）

### [x] CS-2：GovernanceHub `is_globally_enabled()` 公開方法（封裝 `._enabled`）
- **文件**：`app/governance_hub.py`
- **問題**：`governance_routes.py` 7 處直接訪問 `hub._enabled`（私有屬性穿透）
- **修復**：新增 `is_globally_enabled() -> bool`；`governance_routes.py` 7 處改為公開方法調用
- ✅ 完成：commit 973c595（2026-03-31）

### [x] CS-3：FastAPI 啟動完整性檢查
- **文件**：`app/main.py`（新增 `_startup_integrity_check()`）
- **實現**：Hard deps（GOV_HUB/ENGINE/RISK_MANAGER）→ RuntimeError；Soft deps（PIPELINE_BRIDGE/H0_GATE）→ warning
- **測試**：`tests/test_startup_integrity.py`（6 個場景，使用 `asyncio.run()`）
- ✅ 完成：commit 973c595（2026-03-31）

### [x] CS-4：MessageBus 負載測試（文件化 ISSUE-1/ISSUE-2）
- **文件**：`tests/test_message_bus_load.py`（新建，11 個測試）
- **ISSUE-1**（已文件化，未修復）：`_messages` 列表無界，長期運行可 OOM
- **ISSUE-2**（已文件化，未修復）：subscriber 在 `_lock` 持有期間被調用，死鎖風險
- ✅ 完成：commit 973c595（2026-03-31）

---

## ██ Phase 2 Batch 2A：TruthSourceRegistry（已完成）

### [x] P2A-1：`truth_source_registry.py` 核心模組
- **文件**：`app/truth_source_registry.py`（新建）
- **實現**：CognitiveLevel（FACT/INFERENCE/HYPOTHESIS）+ PatternClaim dataclass（14 欄位）+ TruthSourceRegistry（register/query/falsify/expire/snapshot）
- **原則 7 隔離**：學習平面（register_claim）與 Live 平面完全分離
- **AI 信心上限**：evidence_source="ai" → max confidence 0.85，永遠不是 FACT
- **TTL**：ai=86400s, backtest=604800s, market_obs=3600s
- **測試**：`tests/test_truth_source_registry.py`（46 個測試，A1-A8 驗收標準）
- ✅ 完成：commit cf7ef5d（2026-03-31）

### [x] P2A-2：AnalystAgent 集成 `set_truth_registry()` + `_register_pattern_claims()`
- **文件**：`app/analyst_agent.py`
- **集成**：從 `winning_patterns` 向 registry 注入 PatternClaim（keyword-only args）
- ✅ 完成：commit cf7ef5d（2026-03-31）

### [x] P2A-3：StrategistAgent 集成 `set_truth_registry()` + `_apply_pattern_insight()`
- **文件**：`app/strategist_agent.py`
- **集成**：從 registry 讀取高信心 claim，動態調整 `_strategy_preference_weights`（±10% per claim）
- **fail-open**：registry 查詢失敗 → `logger.warning`，不影響交易路徑
- ✅ 完成：commit cf7ef5d（2026-03-31）

---

## ██ Phase 2 Batch 2B：BacktestEngine MVP（已完成）

### [x] P2B-1：`backtest_engine.py` 核心引擎
- **文件**：`program_code/local_model_tools/backtest_engine.py`（新建，531 行）
- **設計**：純函數指標（不複用 live IndicatorEngine，原則 7 隔離）
- **`_BacktestKlineAdapter`**：`register_on_kline_close()` 為 no-op（防止污染 live 狀態）
- **安全邊界**：`backtest_mode=False` → ValueError；<30 bars → 返回警告結果
- **指標**：`_compute_sma`/`_compute_ema`/`_compute_rsi`/`_compute_indicators_pure`
- **Sharpe 計算**：ANNUALIZATION_FACTORS dict，<2 筆交易 → 返回 0.0
- **測試**：`tests/test_backtest_engine.py`（57 個測試，B1-B9 驗收標準）
- ✅ 完成：commit cf7ef5d（2026-03-31）

---

## ██ Wave 7a — Spot 品類啟用（已完成 · 2026-04-01）

> 目標：讓 Paper + Demo 雙引擎支持 Spot 現貨交易（634 個幣對）。
> Bybit V5 API 4 個合法 category：linear（已啟用）、spot、inverse、option。

### [x] SPOT-1：市場掃描器支持 spot category
- ✅ 完成：注入點已確認有 `categories=["linear","spot"]`；補 `test_market_scanner.py` 16 個測試（commit 054d1ae）

### [x] SPOT-2：Position 記錄 category 字段
- ✅ 完成：flip 路徑補 `pos.get("category","linear")`（commit 054d1ae）

### [x] SPOT-3：Spot 保證金邏輯（現貨 = 100% 名義價值）
- ✅ 完成：paper_trading_engine `if category=="spot": required_margin=notional`；risk_manager spot max_leverage=1.0 P0 override（commit 054d1ae）

### [x] SPOT-4：策略部署器 + Pipeline 驗證
- ✅ 完成：pipeline_bridge `_infer_category_from_symbol` + kline/funding category 修正；spot funding rate 跳過 HTTP（commit 054d1ae）

### [x] SPOT-5：端到端測試 + Demo 驗證
- ✅ 完成：test_pipeline_bridge_spot.py（20 個）+ test_risk_manager.py（+6）+ test_paper_trading_engine.py（+3）（commit 054d1ae）

### [x] 方案 B：PipelineBridge `_symbol_category_map` 運行時映射
- ✅ 完成：pipeline_bridge + strategy_auto_deployer + phase2_strategy_routes 雙向注入（commit 054d1ae）
- **設計決策**：`docs/decisions/2026-04-01--symbol_category_mapping_design.md`
- **待辦（Wave 7b）**：方案 A `SymbolCategoryRegistry` 啟動時 API 批量填充；`spot_allow_margin` enforce

### [x] 方案 A：SymbolCategoryRegistry（長期穩定）
- ✅ 完成：symbol_category_registry.py 新建；main.py soft dep 初始化；pipeline_bridge.py fallback warning（commit a0f87b6）
- **待辦（Wave 7b）**：TradeIntent.metadata["category"] 改為必填；分頁支持（spot >1000 symbols）

---

## ██ Wave 7b — Inverse 品類完善（已完成 · 2026-04-01）

> Inverse 幣本位合約（27 個幣對：BTCUSD, ETHUSD 等）。
> PnL 計算公式與 linear 完全不同，需要更多改動。

### [x] INV-1：Paper Engine PnL 公式修正（CRITICAL）
- **檔案**：`app/paper_trading_engine.py`（`update_unrealized_pnl()` + `_compute_close_pnl()`）
- **問題**：當前 `pnl = (exit - entry) * qty` 只對 linear 正確
- **Inverse 正確公式**：`pnl = qty * (1/entry - 1/exit)`（幣本位）
- ✅ 完成：commit 待提交（2026-04-01）— category 分支 + 除零保護 + 雙語 docstring + 數值驗證
- **額外**：新增 SLIPPAGE_TIERS + compute_dynamic_slippage（動態滑點，依 24h 成交額分級）

### [x] INV-2：市場掃描器支持 inverse（symbol 命名不同 BTCUSD vs BTCUSDT）
- **檔案**：`market_scanner.py`
- **問題**：USDT 過濾器會排除所有 inverse 合約
- ✅ 完成：commit 待提交（2026-04-01）— volume 過濾跳過 inverse（turnover 幣本位計）+ symbol suffix category-aware

### [x] INV-3：qty 步長精度（inverse 多為整數合約）
- **檔案**：`bybit_demo_connector.py`（`round_qty_for_exchange()`）
- **問題**：BTCUSD step=1（整數），當前啟發式可能 round 錯
- ✅ 完成：commit 待提交（2026-04-01）— 加 `category` 參數（默認 "linear"，向後兼容）；pipeline_bridge 調用點傳入 category

### [x] INV-4：Inverse 專用風控配置
- **檔案**：`risk_manager.py`
- **內容**：inverse 槓桿上限（通常 50x vs linear 125x）、保證金計算
- ✅ 完成：已含於 user commit 7158a44（`if "inverse" not in self._category_configs` auto-inject, max_leverage=50.0）

### [x] INV-5：端到端測試 + Demo 驗證
- ✅ 完成：commit 待提交（2026-04-01）— `tests/test_paper_trading_engine_inverse.py`（32 個測試，5 個 Class）
- TestInverseClosePnL（8）+ TestInverseUnrealizedPnL（6）+ TestInverseRoundQty（7）+ TestInverseRiskConfig（6）+ TestInverseMarketScanner（5）

---

## ██ Phase 2 Batch 2C（已完成 · 2026-04-01）

### [x] 2C-1：_register_pattern_claims() 接通雙路徑
- **修復**：_ai_pattern_analysis() + _statistical_pattern_analysis() 均在 bus.send() 前調用
- **修復**：_extract_strategy_from_pattern() 確保 applies_to_strategy 永不為 "all"
- **修復**：補入 losing_patterns 循環（confidence=0.4，"losing: " 前綴）
- ✅ 完成：commit 5794db1（2026-04-01）

### [x] 2C-2：BacktestEngine API 路由
- **新建**：backtest_routes.py（POST /api/v1/backtest/run + GET /api/v1/backtest/status）
- **特性**：Operator 認證 + asyncio.to_thread + sharpe>1.0 自動注入 TruthSourceRegistry
- **隔離**：原則 7，不導入任何 live 模組
- ✅ 完成：commit 5794db1（2026-04-01）

### [x] 2C-3：StrategistAgent 決策路徑使用 _strategy_preference_weights
- **修復**：adjusted_confidence = min(1.0, evaluation.confidence * weight)
- **可觀察**：metadata 新增 raw_confidence + strategy_weight 供審計追溯
- ✅ 完成：commit 5794db1（2026-04-01）

---

## ██ Phase 3 Batch 3A — L3 假設與實驗管線基礎設施（✅ 完成 2026-04-01）

> **目標**：建立管線讓系統能提出假設（Hypothesis）並用 BacktestEngine 驗證，
> 驗證結果自動回饋 TruthSourceRegistry + StrategistAgent 決策權重。
> 基礎設施先建好，等 Paper Trading 數據積累後自然生效。
>
> **前置條件（已全部就緒）**：TruthSourceRegistry ✅ · BacktestEngine ✅ · AnalystAgent ✅ · StrategistAgent ✅
> **原則遵守**：原則 7（學習平面隔離）· 原則 10（認知誠實，HYPOTHESIS 最低信心級別）
>
> **PM 重新規劃**：實際實作與原計劃有調整，詳見下方 [x] 條目說明。

---

### [x] 3A-1：ExperimentLedger（新建 — PM 調整為更完整的生命週期管理）
- **實際實作**：`app/experiment_ledger.py`（294 行）
- **職責**：假設完整生命週期管理（PENDING→RUNNING→CONFIRMED/REFUTED/EXPIRED），65% 觀測支持閾值 + TTL 過期 + TruthSourceRegistry fail-open 注入
- **測試**：`tests/test_experiment_ledger.py`（32 個測試，全通過）
- **E1 指派**：E1-Alpha
- ✅ 完成：commit Phase3Batch3A（2026-04-01）

---

### [x] 3A-2：ExperimentRoutes API（新建 — 4 個端點，含 propose/observe/get/status）
- **實際實作**：`app/experiment_routes.py`（328 行）
- **端點**：POST /propose（Operator）、POST /{id}/observe（Operator）、GET /status（auth only）、GET /{id}（auth only）
- **設計**：GET /status 在 GET /{id} 前注冊（防 FastAPI 路由衝突），asyncio.to_thread，singleton
- **掛載**：`main.py` 已加 `app.include_router(experiment_router)`
- **測試**：`tests/test_experiment_routes.py`（25 個測試，全通過）
- **E1 指派**：E1-Beta
- ✅ 完成：commit Phase3Batch3A（2026-04-01）

---

### [x] 3A-3：EvolutionEngine（新建 — 策略參數自動優化，原計劃調整）
- **實際實作**：`program_code/local_model_tools/evolution_engine.py`（280 行）
- **職責**：以 BacktestEngine 為評估函數，網格搜索策略最優參數組合（原則 7 隔離，原則 5 資源防護 max_combinations=50）
- **核心設計**：ParameterGrid + EvolutionResult（is_simulated 強制 True）+ EvolutionEngine 網格搜索 + TruthSourceRegistry fail-open 注入
- **測試**：`tests/test_evolution_engine.py`（31 個測試，全通過，含 AST 原則 7 驗證）
- **E1 指派**：E1-Gamma
- ✅ 完成：commit Phase3Batch3A（2026-04-01）

---

### [x] 3A-4：TruthSourceRegistry 持久化
- **實際實作**：`app/truth_source_registry.py` 新增 `save_snapshot()` / `load_snapshot()` / `_schedule_debounced_save()`
- `register_claim()` 後自動觸發 30s debounced save（threading.Timer daemon）
- 啟動時 `_startup_integrity_check()` 自動 load snapshot（fail-open）
- 環境變數 `OPENCLAW_TRUTH_REGISTRY_PATH`，默認 `settings/truth_registry_snapshot.json`
- **測試**：`test_truth_source_registry.py` +6（52 total）
- ✅ 完成：commit Phase3Batch3B（2026-04-01）

---

### Phase 3 Batch 3A + 3B + 3C 工作鏈（✅ Phase 3 全部完成）

```
3A-1/2/3 ExperimentLedger + ExperimentRoutes + EvolutionEngine ✅ 3289 passed
3A-4 TruthSourceRegistry 持久化 ✅
3B-1 AnalystAgent → ExperimentLedger 觀測記錄 ✅
3B-2 ExperimentLedger.auto_seed_from_claims() ✅
3B-3 EvolutionRoutes POST /run + GET /status ✅
3B-4 main.py 啟動自動填充（load_snapshot + auto_seed_from_claims）✅
3C-1 tab-ai.html 假設實驗狀態 + 進化 dashboard（30s 刷新）✅
3C-2 EvolutionScheduler 週進化 daemon（週日 UTC 00:30）✅
3C-3 ExperimentLedger 小時清理 daemon ✅
E4 全量回歸 ✅ 3330 passed（+20 新測試）
```

### 驗收標準（全部達成）
- ✅ TruthSourceRegistry 持久化（save/load/debounced，跨重啟保留）
- ✅ AnalystAgent winning/losing → ExperimentLedger 觀測（fail-open）
- ✅ ExperimentLedger 啟動自動從快照填充（min_confidence=0.5）
- ✅ EvolutionRoutes POST /run（Operator auth）+ GET /status
- ✅ 所有模組零 live 模組 import（原則 7）
- ✅ E4 3310 passed

---

## ██ 已知待辦（已文件化，非緊急）

### MessageBus 架構問題（ISSUE-1/ISSUE-2）
- **ISSUE-1**：`_messages` 無界列表 → 長期運行 OOM 風險
- **ISSUE-2**：subscriber 在鎖內被調用 → 死鎖風險
- **建議**：換用 `collections.deque(maxlen=N)` 或獨立分發線程
- **優先級**：P3（非緊急，測試已文件化）

### TruthSourceRegistry 持久化（跨 session 清零問題）
- 目前僅記憶體，重啟清零
- **優先級**：Phase 3 Batch 3A 候選

### Intent 被拒時策略內部狀態不回退（P2 · 已復現）

**問題**：當 intent 被 governance/H0/Guardian 拒絕時，策略的 `_current_position` 不會回退。
策略以為自己開了倉（因為已發出 intent），但 Paper Engine 實際沒有持倉。
後續信號觸發「平倉」時，策略發出反向 intent，意外開了不該存在的新倉位。

**復現案例（2026-04-01 13:16–13:32 PIPPINUSDT）**：
1. 13:16 MA 死叉 → Sell intent → `rejected_governance`（重啟後授權丟失）
2. 策略內部 `_current_position = "short"`，但 Paper Engine 無持倉
3. 13:31 MA 金叉 → Buy intent（reason: "Close short"）→ submitted → 意外開了多單
4. 37 秒後止損自動平掉 → 淨虧損 $0.09（毛利 +$0.07 被手續費 $0.16 吃掉）

**修復方向**：
- [ ] `pipeline_bridge` 在 intent 被拒後，回調通知策略清除 `_current_position`
- [ ] 或：策略在 `_emit_intent()` 時不立即更新 position，等收到 execution report 再更新
- **相關檔案**：`pipeline_bridge.py`（_gate_intent 拒絕路徑）、`strategies/base.py`（_current_position）
- **優先級**：P2（非緊急但會造成假開倉虧損，授權恢復後不再觸發）

### Paper-Demo 差異校準系統（長期）

Paper 與 Demo 是「內部模擬 + 外部驗證」雙軌架構，差異本身是系統健康度信號。

**短期（現狀維持）：**
- 現有 fail-open + DIVERGED 日誌 + 雙遍歷清倉已處理分歧，無需改動

**中期 — GUI 差異可視化：**
- [ ] tab-trading.html 明確標示「Paper 數據」vs「Demo 數據」來源
- [ ] 新增 Paper-Demo 差異率儀表板卡片（持倉數量差異、PnL 差異百分比）
- [ ] 對賬引擎 reconcile() 結果在 GUI 上可視化（MATCH / MISMATCH_MINOR / DIVERGED）

**長期 — 自動滑點模型校準：**
- [ ] 累積 Demo 實際成交數據（滑點、費率、成交率）到 PostgreSQL
- [ ] 定期（如每1000筆交易後）用 Demo 實際滑點統計反推 Paper SLIPPAGE_TIERS 參數準確度
- [ ] 若 Paper-Demo 滑點偏差 > 閾值，自動建議調整 SLIPPAGE_TIERS（不自動改，原則 3）
- [ ] 費率校準：比較 Paper 硬編碼費率 vs Demo 實際費率，標記偏差
- **相關檔案**：`paper_trading_engine.py`（SLIPPAGE_TIERS, DEFAULT_TAKER_FEE_RATE）、`bybit_demo_sync.py`（_sync_executions）
- **優先級**：Phase 4 觀察期候選（需先累積足夠 Paper+Demo 並行交易數據）
- **定位**：Paper = System of Record（風控/學習以此為準）；Demo = Validation Oracle（校準/Live Gate 權重更高）

---

# ═══════════════════════════════════════════════════════════════
# April 1 審計修復批次（8 份審計報告 · PA 交叉驗證 · 78 項去重）
# PM 執行計劃：2026-04-01
# 完整報告：docs/audit/April01/PM_execution_plan_2026-04-01.md
# ═══════════════════════════════════════════════════════════════

## ██ April 1 Audit — Batch 1: P0 知識閉環 + 快速 P1（~3.5h）

> 激活 Phase 2 學習管線死代碼 + 確保知識跨重啟保留。ROI 最高的一批修復。
> 前置：無。並行度：3 E1。

### [x] APR01-P0-1: TruthSourceRegistry 從未注入 StrategistAgent/AnalystAgent — Phase 2 知識閉環死代碼
- **檔案**: `app/phase2_strategy_routes.py`（+ `app/main.py` singleton 統一）
- **修復**: 統一 `_seed_registry`（main.py）為全局 singleton；在 phase2_strategy_routes 中調用 `STRATEGIST_AGENT.set_truth_registry(registry)` + `ANALYST_AGENT.set_truth_registry(registry)`
- **來源**: FA P0-FA-1 + AI-E §5.2
- **工時**: 0.5h
- **E1 指派**: E1-Alpha

### [x] APR01-P1-1: TruthSourceRegistry save_snapshot() 從未被自動調用 — 重啟丟失所有知識
- **檔案**: `app/truth_source_registry.py`, `app/phase2_strategy_routes.py`
- **修復**: register_claim() 中 debounced auto_save（或 atexit hook + 定時 save）；確保 main.py 啟動時 load_snapshot 路徑對齊
- **來源**: FA P1-FA-6 + AI-E P1-AI-1
- **工時**: 1h
- **E1 指派**: E1-Alpha

### [x] APR01-P1-2: ExperimentLedger 純記憶體狀態 — 重啟歸零
- **檔案**: `app/experiment_ledger.py`
- **修復**: 新增 save_snapshot()/load_snapshot() + debounced auto_save + 啟動時 load
- **來源**: AI-E P1-AI-1
- **工時**: 1.5h
- **E1 指派**: E1-Beta

### [x] APR01-P1-3: pipeline_bridge 仍調用已廢棄的 collect_pending_intents() — 每 tick 日誌噪音
- **檔案**: `app/pipeline_bridge.py`（line 482-510）
- **修復**: 移除 strategist collect 調用（TD-2 已標記 DEPRECATED，永遠返回 []）
- **來源**: FA P1-FA-4
- **工時**: 0.3h
- **E1 指派**: E1-Gamma

### Batch 1 工作鏈
```
✅ 完成：commit 1237744（2026-04-01）— E2 8/8 PASS，E4 3355 passed
```

---

## ██ April 1 Audit — Batch 2: BacktestEngine 接通 + 安全加固（~3h）

> 解鎖回測 API + CORS 安全校驗 + 信息洩露修復。
> 前置：Batch 1。並行度：3 E1。

### [x] APR01-P1-4: BacktestEngine API 無數據源（KlineManager 未注入）
- **檔案**: `app/backtest_routes.py`
- **修復**: get_backtest_engine() 注入 KlineManager（從 phase2_strategy_routes 導入）；或在 POST /run handler 中從 Bybit API 直接拉取歷史 K 線
- **來源**: FA P0-FA-2（PA 降級為 P1）
- **工時**: 1h
- **E1 指派**: E1-Alpha

### [x] APR01-HIGH-1: CORS allow_credentials=True 缺少啟動校驗
- **檔案**: `app/main_legacy.py`（CORS 配置處）
- **修復**: 啟動時校驗 _cors_origins 不含 `*`；若含 → 拒絕啟動或 warning + 自動移除
- **來源**: E3 HIGH-LEGACY-1
- **工時**: 0.5h
- **E1 指派**: E1-Beta

### [x] APR01-MEDIUM-1: paper_trading_routes + backtest_routes detail=str(e) 信息洩露
- **檔案**: `app/paper_trading_routes.py`（5 處）, `app/backtest_routes.py`（1 處）
- **修復**: 全部改為 `detail="Internal server error"` + 保留 logger.error
- **來源**: E3 MEDIUM-NEW-3 + LOW-NEW-3
- **工時**: 0.5h
- **E1 指派**: E1-Gamma

### [x] APR01-MEDIUM-2: experiment_routes ProposeHypothesisRequest 無 max_length 驗證
- **檔案**: `app/experiment_routes.py`
- **修復**: 對 title/description/conditions 加 `max_length` Field 約束
- **來源**: E3 MEDIUM-NEW-2
- **工時**: 0.5h
- **E1 指派**: E1-Gamma

### Batch 2 工作鏈
```
✅ 完成：commit d99f1a9（2026-04-01）— E2 PASS，E4 3355 passed
```

---

## ██ April 1 Audit — Batch 3: MessageBus 路徑 + 安全響應頭（~4h）

> 5-Agent MessageBus 全路徑接通 + HTTP 安全加固。
> 前置：Batch 1。並行度：2 E1 + 1 E1a。

### [x] APR01-P1-5: MessageBus Guardian→Executor APPROVED_INTENT 路徑斷裂
- **檔案**: `app/guardian_agent.py` 或 `app/multi_agent_framework.py`
- **修復**: PA 建議方案 B：pipeline_bridge 調用 Conductor.process_trade_intent()；或方案 A：Guardian._handle_trade_intent() APPROVED 後發送 APPROVED_INTENT 到 Executor
- **來源**: FA P1-FA-2
- **工時**: 2h
- **E1 指派**: E1-Alpha

### [x] APR01-MEDIUM-3: 缺乏安全 HTTP 響應頭（CSP/X-Frame-Options/X-Content-Type-Options）
- **檔案**: `app/main.py` 或 `app/main_legacy.py`
- **修復**: 添加安全中間件（SecurityHeaderMiddleware 或自定義）
- **來源**: E3 MEDIUM-LEGACY-3
- **工時**: 1h
- **E1 指派**: E1-Beta

### [x] APR01-MEDIUM-4: tab-governance.html 30+ 處 innerHTML 未轉義
- **檔案**: `app/static/tab-governance.html`
- **修復**: 動態數據來源逐一用 ocEsc() 包裹
- **來源**: E3 MEDIUM-NEW-1
- **工時**: 1h
- **E1 指派**: E1a-Alpha

### Batch 3 工作鏈
```
✅ 完成：commit 5f4ac3c（2026-04-01）— E2 PASS（含 MUST-FIX 修復），E4 3362 passed
```

---

## ██ April 1 Audit — Batch 4: 記憶體保護 + 文檔索引（~4h）

> Registry/Ledger 記憶體上限 + 文檔索引補全。
> 前置：Batch 1（持久化完成後再加上限）。並行度：2 E1 + R4。

### [x] APR01-MEDIUM-5: TruthSourceRegistry _claims 無上限 + 過期不清理
- **檔案**: `app/truth_source_registry.py`
- **修復**: MAX_CLAIMS=5000 + register_claim() 中定期清理 is_expired() 條目
- **來源**: E5 NEW-P2（PA 降級為 MEDIUM）
- **工時**: 1h
- **E1 指派**: E1-Alpha

### [x] APR01-MEDIUM-6: ExperimentLedger _hypotheses 無上限
- **檔案**: `app/experiment_ledger.py`
- **修復**: MAX_HYPOTHESES=2000 + 清理已結案超 TTL 條目
- **來源**: E5 NEW-P3（PA 降級為 MEDIUM）
- **工時**: 1h
- **E1 指派**: E1-Beta

### [x] APR01-HIGH-2: audit/March31/ 7 份核心報告 + README 結構圖缺 audit/ 目錄
- **檔案**: `docs/README.md`
- **修復**: 補 audit/March31/ 和 audit/April01/ 索引區塊
- **來源**: R4 R4-01/02
- **工時**: 1h
- **E1 指派**: R4

### [x] APR01-MEDIUM-7: decisions/ .docx 未索引 + governance_dev 補全
- **檔案**: `docs/README.md`
- **修復**: 在索引中添加 decisions/ 專區 + governance_dev 補全
- **來源**: R4 R4-03/04
- **工時**: 1h
- **E1 指派**: R4

### Batch 4 工作鏈
```
✅ 完成：commit b5fee2e（2026-04-01）— E2 PASS，E4 3362 passed
```

---

## ██ April 1 Audit — Batch 5: 性能優化 + 覆蓋率提升（~8h）

> BacktestEngine O(n^2) 修復 + 關鍵模塊測試覆蓋率。
> 前置：Batch 2（BacktestEngine API 接通後）。並行度：3 E1 + E4。

### [x] APR01-HIGH-3: backtest_engine O(n^2) 列表切片 + EMA/RSI 從頭重算
- **檔案**: `program_code/local_model_tools/backtest_engine.py`
- **修復**: 使用索引而非切片：_compute_indicators_pure 接收 end_idx 參數；增量 EMA 計算
- **來源**: E5 NEW-P1/P4（PA 降級為 HIGH）
- **工時**: 3h
- **E1 指派**: E1-Alpha

### [x] APR01-MEDIUM-8: backtest_engine 指標函數與 indicators/ 重複
- **檔案**: `program_code/local_model_tools/backtest_engine.py`, `program_code/local_model_tools/indicators/`
- **修復**: 提取純函數到 indicators/pure.py；backtest_engine 從此導入（保持原則 7 隔離）
- **來源**: E5 NEW-S1
- **工時**: 1h
- **E1 指派**: E1-Alpha

### [x] APR01-MEDIUM-9: L2 後台線程結果被完全丟棄
- **檔案**: `app/strategist_agent.py`
- **修復**: L2 結果回注 _strategy_preference_weights 或 cache 供下次決策參考
- **來源**: AI-E P2-AI-2
- **工時**: 2h
- **E1 指派**: E1-Beta

### [x] APR01-MEDIUM-10: MarketScanner MAX_SYMBOLS_TO_TRADE=5 vs deployer 25 不一致
- **檔案**: `program_code/local_model_tools/market_scanner.py`
- **修復**: 統一為可配置常量，從 deployer 配置讀取
- **來源**: FA P2-FA-1
- **工時**: 0.5h
- **E1 指派**: E1-Gamma

### [x] APR01-E4-1: strategy_auto_deployer 0% 測試覆蓋率
- **檔案**: `tests/test_strategy_auto_deployer.py`（新建）
- **修復**: 至少 15 個核心測試（部署/撤回/symbol 限制/掃描回調）
- **來源**: E4 報告 2.5
- **工時**: 2h
- **E1 指派**: E4

### Batch 5 工作鏈
```
✅ 完成：commit 9276fdd（2026-04-01）— E2 8/8 PASS，E4 3387 passed（+40 test_strategy_auto_deployer）
```

---

## ██ April 1 Audit — Batch 6: 技術債精選 + 文檔合規（~6h）

> sys.path 重複消除 + MODULE_NOTE 補全 + 鎖範圍收窄。
> 前置：無（可與 Batch 3-5 並行）。並行度：3 E1 + TW。

### [x] APR01-MEDIUM-11: 4 個路由文件重複 sys.path 5 層 dirname
- **檔案**: `app/backtest_routes.py`, `app/evolution_routes.py`, `app/experiment_routes.py`, `app/phase2_strategy_routes.py`
- **修復**: 提取公共函數 `_ensure_program_code_on_path()` 到共用模塊
- **來源**: E5 NEW-S2 + #44
- **工時**: 1h
- **E1 指派**: E1-Alpha

### [x] APR01-MEDIUM-12: _process_pending_intents 鎖持有範圍過大
- **檔案**: `app/pipeline_bridge.py`
- **修復**: 收窄鎖範圍：鎖內只讀共享狀態 + 收集 intents，解鎖後執行 Guardian/edge filter 等 I/O
- **來源**: E5 NEW-P5
- **工時**: 2h
- **E1 指派**: E1-Beta

### [x] APR01-MEDIUM-13: Token 存儲在 localStorage（安全風險）
- **檔案**: `app/static/common.js`, `app/main_legacy.py`
- **修復**: 改用 HttpOnly secure cookie（後端 Set-Cookie + 前端移除 localStorage）
- **來源**: E3 MEDIUM-LEGACY-2
- **工時**: 2h
- **E1 指派**: E1-Gamma

### [x] APR01-TW-1: main.py / multi_agent_framework / perception_data_plane 缺 MODULE_NOTE
- **檔案**: `app/main.py`, `app/multi_agent_framework.py`, `app/perception_data_plane.py`
- **修復**: 補充中英雙語 MODULE_NOTE 區塊
- **來源**: TW B1/B2/B3
- **工時**: 1h
- **E1 指派**: TW

### Batch 6 工作鏈
```
✅ 完成：與 Batch 5 合併 commit 9276fdd（2026-04-01）— E2 8/8 PASS，E4 3387 passed
```

---

## ██ April 1 Audit — Batch 7: 積壓一次清掃（2026-04-01 完成大部分）

> 8 並行 Agent 一次執行。中長期功能型項目延後。

### [x] APR01-HIGH-4: _process_pending_intents 462 行超巨方法拆分
- **來源**: E5 NEW-R1
- **修復**: 拆分為 4 個子方法（_collect_pending_intents / _gate_intent / _submit_approved_intent / _post_execution_hooks）+ 30 行依賴文檔
- ✅ 完成：Batch 7（2026-04-01）

### [x] APR01-CC-1: 原則 15 Conductor 自動編排完善
- **來源**: CC §二（部分合規）
- **修復**: dispatch_to_agent() + get_agent_health() + make_tracked_subscriber() + 154 行新增
- ✅ 完成：Batch 7（2026-04-01）

### [ ] APR01-CC-2: 原則 12 L5 元學習實施
- **來源**: CC §二（部分合規）
- **工時**: 15h+（延後，功能型需求）

### [ ] APR01-FA-P2-2: Regime-aware 策略選擇
- **來源**: FA P2-FA-2
- **工時**: 8h（延後，功能型需求）

### [ ] APR01-FA-P2-3: 策略優化→部署自動化循環
- **來源**: FA P2-FA-3
- **工時**: 10h（延後，功能型需求）

### [ ] APR01-E5-LEGACY: main_legacy.py 5113 行單文件重構
- **來源**: E5 #15
- **工時**: 20h+（延後，需整體重構規劃）

### [x] APR01-E5-LOGGER: 194 處 logger f-string → %s 佔位符
- **來源**: E5 #20
- **修復**: governance_hub.py（68 處）+ 19 個其他 app 文件（126 處）= 194 處全部轉換
- ✅ 完成：Batch 7（2026-04-01）

### [x] APR01-B7-SECURITY: Pydantic 輸入驗證 + 靜默異常修復
- **來源**: E3 LOW-NEW-1/2/3/4
- **修復**: backtest_routes Field(max_length) + evolution_routes validator + experiment_routes Literal + audit_persistence 5 處 except-pass→logger.debug
- ✅ 完成：Batch 7（2026-04-01）

### [x] APR01-B7-QUALITY: 代碼質量提升（magic number + timeout + H4 擴展）
- **來源**: E5 NEW-S2/S3/S5/S6/S7 + E5 #20
- **修復**: phase2_strategy_routes magic number 注釋 + ollama health timeout 5→1s + scout_worker 可配置 interval + analyst_agent 可配置 min_observations + strategist H4 validate 擴展（has_edge/reason/action）+ layer2_cost_tracker unified record_call()
- ✅ 完成：Batch 7（2026-04-01）

### [x] APR01-B7-DOCS: MODULE_NOTE 雙語補全 + docs/README 修復
- **來源**: TW + R4
- **修復**: 6 個文件 MODULE_NOTE 補全（data_source_enforcer / governance_events / runtime_bridge / scanner_rate_limiter / main_legacy / main_snapshot_stable）+ docs/README.md 重複項移除 + 命名慣例說明
- ✅ 完成：Batch 7（2026-04-01）

### [x] APR01-B7-TESTS: 邊界用例測試補強
- **來源**: E4
- **修復**: 3 個新測試文件（test_risk_manager_edge 8 + test_stop_manager_edge 10 + test_paper_trading_engine_edge 4）+ 5 個已有文件擴展（+16）= +38 新測試
- ✅ 完成：Batch 7（2026-04-01）

### ~50 項 LOW/P3 問題（部分已隨上述修復一併解決）
- 詳見各原始審計報告（E5 Low 15 項 / TW P3 7 項 / R4 Low 4 項 / FA P3 4 項 / E3 Low 4 項 / AI-E P3 1 項）

---

## ██ April 1 Audit — 依賴關係圖

```
Batch 1（P0 知識閉環 · 0.5 天）
  ├─→ Batch 2（BacktestEngine + 安全 · 0.5 天）
  │     └─→ Batch 5（性能 + 覆蓋率 · 1 天）
  ├─→ Batch 3（MessageBus + 安全頭 · 0.5 天）
  └─→ Batch 4（記憶體保護 + 文檔 · 0.5 天）

Batch 6（技術債 + 文檔合規 · 1 天 · 無前置依賴，可任意並行）

關鍵路徑：Batch 1 → Batch 2 → Batch 5 = 2 天
最短完成時間：2 天（Batch 1-6 全部）
Batch 7 延後不排程
```
