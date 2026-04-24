# BB (Bybit Broker Compatibility Auditor) — Memory

> 每次啟動序列先讀此檔，再讀最近一份 `workspace/reports/` 報告，接著讀字典手冊與歷史審計。

---

## 角色定位

**BB = Bybit V5 API 合規審計員**（外部視角）。職責為：
1. 驗證所有 Bybit API 調用（REST / WS / IPC）正確符合官方 V5 規範
2. 比對代碼實作與項目字典手冊 `docs/references/2026-04-04--bybit_api_reference.md` 的一致性（代碼為 SSOT，字典配合）
3. 標註 Critical/High/Medium/Low 分級 + 具體修改建議
4. **不打真實 API**，僅做靜態審計

**協作**：與 E5（優化工程師，內部視角）+ PA（架構）併線。歷史兩輪審計結果在 `docs/audits/2026-04-04--bybit_api_infra_audit.md` + `docs/audits/2026-04-05--l3_comprehensive/audit_BB_bybit_api_report.md`。

---

## 歷史審計頻率

- 2026-04-04：首次系統審計（~243 REST + ~20 WS topic）→ 修 5 個過期路徑 + 3 個 UTA 遷移 + 3 個 deprecated removal + 2 個 P0 添加
- 2026-04-05：L3 comprehensive audit
- 2026-04-12：full_program_chain audit（BB-A1 `confirm-pending-mmr` 路徑修復 / BB-A2 set-hedging / BB-A4 execution.fast execFee backfill / BB-A5 pre_check_order 刪除）
- 2026-04-20：EDGE-P2-3 Phase 1B-1 BybitRetCode 擴充 + PostOnly WS rejectReason 對齊
- 2026-04-24（本次）：全面復審 + DEDUP-PY-RUST D 後殘留檢查 + WS Status Writer takeover 驗證

---

## 關鍵發現（2026-04-24 本次）

### Critical：0 項 ✅
**核心交易路徑無 bug，不需緊急修復。**

### High：1 項
- **H-1 字典 `confirm-mmr` 路徑過期**：字典 §1.4 + §4.3 寫 `/v5/position/confirm-mmr`，實機路徑為 `/v5/position/confirm-pending-mmr`（代碼 SSOT 已於 2026-04-12 FIX-56/BB-A1 更正）。**字典需更新**。

### Medium：3 項
- **M-1 ws_client "handler not found" 無警告升級**：2026-04-05 曾因錯 topic 毒化連接，現 parser 只 debug! 不 reconnect
- **M-2 `bybit_public_connectivity_check.py` 硬編碼 mainnet URL**
- **M-3 `bybit_private_ws_smoke_test.py` v1/v2 使用 legacy `read_only` slot + 硬編碼 mainnet ws**

### Low / Advisory：5 項（字典 drift + Rust settleCoin fallback 建議）
詳見 `workspace/reports/2026-04-24--bybit_api_compat_audit.md` §6.4

---

## 結構性認知

### 1. Rust 為單一 API 實作 SSOT
- `rust/openclaw_engine/src/{bybit_rest_client,bybit_private_ws,ws_client,bybit_private_ws_status_writer,order_manager,position_manager,account_manager,platform_client,market_data_client/mod,instrument_info,position_reconciler/mod,database/rest_poller}.rs`
- Python `bybit_rest_client.py` 為 httpx drop-in，與 Rust 契約字節級對齊（同一 sign_str、同一 header set）
- 2026-04-23 DEDUP-PY-RUST D 後 98 legacy maintenance shell + Python listener 已刪除

### 2. LIVE-GUARD-1 三閘對稱已落地
- Gate #1：`OPENCLAW_ALLOW_MAINNET=1` env
- Gate #2：Mainnet 禁用 env var 憑證回退
- Gate #3：Mainnet 憑證空 → 構造 Err
- Rust + Python 兩側**字節級對稱**

### 3. Private WS 環境感知 topic（2026-04-11 B-2 根因教訓）
- Mainnet：`[order, execution.fast, position, wallet, dcp]`
- Demo/Testnet/LiveDemo：`[order, execution, position, wallet]`（demo 不支援 execution.fast + dcp → `BybitEnvironment::private_ws_topics()` 分支處理）

### 4. Public WS broken topic 毒化規避
- liquidation/price-limit/adl-notice parser 保留但 subscription list **已移除**
- 2026-04-05 `29fc1ef` 修復

### 5. Rate Limit 分組
- Order=20 / Position=20 / Account=20（2026-04-20 EDGE-P2-3 更正；先前誤記 10）
- Market=120 / Asset=5 / Other=10
- `RateLimitGroup::from_path()` + per-group `AtomicI64`
- `wait_if_rate_limited` 主動退避（threshold=10, max_wait=2s）

### 6. retCode 語意分類器
- `BybitRetCode` enum：Ok / InvalidParam / SignError / IpRateLimit / OrderNotFound / PriceOutOfRange / WalletInsufficient / AvailableInsufficient / OrderCompletedOrCancelled / PositionNotFound / OrderAlreadyCancelled / InsufficientBalance / LeverageNotModified / PriceTickInvalid / ContractNotLive / PostOnlyOnlyStage / ExceedMaxQty / OrderNotExistSpot
- 分類助手：`is_retryable / is_noop / is_exchange_backoff / is_instrument_filter / is_balance_block`
- PostOnly cross REST 回 retCode=0，實際拒絕走 WS `rejectReason=EC_PostOnlyWillTakeLiquidity` 路徑（EDGE-P2-3 Phase 1B-1 接線完畢）

### 7. 認證 Header set
- `X-BAPI-API-KEY / -SIGN / -TIMESTAMP / -RECV-WINDOW` 必送
- `X-BAPI-SIGN-TYPE` optional（預設 2=HMAC），Rust/Python REST 均未送（OK），僅 `settings_routes.py` 明送 "2"

---

## 下次啟動需查驗項

1. 字典 §1.4 + §4.3 `confirm-mmr → confirm-pending-mmr` **是否已更新**
2. `bybit_public_connectivity_check.py` + `bybit_private_ws_smoke_test.py` 是否已去硬編碼 / 評估刪除
3. `ws_client.rs::process_message` 是否加了 "handler not found" 強制 reconnect 邏輯
4. 若 Bybit 增新端點或改舊端點，優先檢查：`rust/openclaw_engine/src/bybit_rest_client.rs::RateLimitGroup::from_path` + `BybitRetCode::from_code`
5. 若 Mainnet 啟用：驗 LIVE-GUARD-1 三閘 Rust 測試套件 `bybit_rest_client.rs:1545-1670` 未失效

---

## 2026-04-24 審計發現（本次 TODO 全面審計）

### Critical：0 項 ✅
核心交易路徑無 bug；原則 #1 單一寫入口完全合規。

### High：0 項 ✅
（空）

### Medium：3 項
- **M-1 ws_client "handler not found" 無強制重連**：parser 只 debug!，未觸發 reconnect（容錯弱，無緊迫性因毒化已正確禁用）
- **M-2 bybit_public_connectivity_check.py 硬編碼 mainnet URL**：無法跨環驗證
- **M-3 bybit_private_ws_smoke_test.py 舊設計**：用 legacy `read_only` slot + 硬編碼 mainnet ws

### Low：5 項
- **L-1 字典 confirm-mmr 路徑過期**：字典 §1.4 + §4.3 寫 `/v5/position/confirm-mmr`，代碼實為 `/v5/position/confirm-pending-mmr`（FIX-56 已修）
- **L-2 settle coin fallback 建議**：某些 market 端點可接 settleCoin 參數
- **L-3~5 其他小改進**（字典動態同步、WS 細緻區分、error.rs CI）

### 新增驗證項

1. **WS-RETIRE-1 完成度** ✅ 100%
   - Python listener 3 檔 340 行已刪（2026-04-23）
   - Rust writer 接管 status JSON（listener_version="rust-v1"）
   - 11 unit tests 全 PASS
   - 4 環境下 private_ws_topics 分支正確

2. **LIVE-GATE-BINDING-1 五閘驗證** ✅ 4/5 可驗證
   - Gate #1（Python mode）：Rust 無驗證
   - Gate #2（Python auth）：Rust 無驗證
   - Gate #3（OPENCLAW_ALLOW_MAINNET env）：✅ Rust 檢查（mainnet only）
   - Gate #4（secret slot api_key+secret）：✅ Rust 檢查（憑證空→Err）
   - Gate #5（authorization.json HMAC）：✅ Rust 檢查（5min re-verify）
   - 實裝：live_trust_routes.py:160 `_write_signed_live_authorization()` + startup.rs

3. **原則 #1 單一寫入口** ✅ 完全合規
   - Bybit REST 唯一入口：bybit_rest_client.rs:732 post()
   - 訂單唯一入口：order_manager.rs:354 place_order()
   - Python 平倉降級（LIVE-GATE-FALLBACK-1）：reduce_only REST 直通（無重試）

4. **Rate Limit + Fail-Closed** ✅ 6 分組正確 + max_retries=0
   - Order/Position/Account=20 r/s
   - Market=120, Asset=5, Other=10 r/s
   - 回應 retCode != 0 → Business error，fail-closed 不重試

### Bybit API 覆蓋度進度

| 層級 | 數量 | 狀態 |
|------|------|------|
| REST endpoints | 62 | ✅ 全 V5 API |
| WS private topics | 5 (mainnet) / 4 (demo) | ✅ 環境感知正確 |
| WS public topics | 4 active | ✅ 毒化已禁 |
| IPC 命令 | 46 個 | ✅ Bybit 相關 8 個（4 patch + 4 其他）|
| retCode 分類 | 12 已知 | ✅ 語義完備 |
| Rate limit 分組 | 6 組 | ✅ 追蹤正確 |

### BB 建議 TOP 3（優先順序）

1. **M-1 handler not found 強制重連** → 2h 工作量
2. **M-2/3 環境感知整合** → 4h 工作量
3. **L-1 字典 SSOT 標記** → 2h + 部署規程

---

