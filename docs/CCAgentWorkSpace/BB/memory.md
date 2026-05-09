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


---

## 2026-05-08 審計（HEAD `4e2d2883`）

### 04-24 → 05-08 closure 進度（5/8）

✅ **closed**：
- H-1（字典 confirm-mmr → confirm-pending-mmr）：字典 v1.1 line 21/570/576/1161 已修（2026-04-26 G9-01 audit）
- M-1（ws_client handler not found 無強制重連）：G9-02 + UnknownHandlerGuard 488 LOC 新模組接線到 public + private WS；ProcessOutcome::ForceReconnect 路徑 + runtime env-gate `OPENCLAW_WS_FORCE_RECONNECT_ON_UNKNOWN_ENABLED`
- M-2（bybit_public_connectivity_check 硬編碼 mainnet URL）：env override `OPENCLAW_BYBIT_PUBLIC_BASE_URL` 已加，default fallback mainnet 公開（無簽名）= 可接受
- M-3（bybit_private_ws_smoke_test legacy read_only slot）：兩個 smoke test 檔已從 io_and_persistence/ 刪除（移到 readonly_observer_pipeline/ 改 `bybit_full_readonly_observer_cycle.py`，舊腳本 dead）
- L-1 / L-4：closed via M-1 修復
- F-27 / L5-1..L5-4（Bybit 字典 drift）：2026-05-09 source/test close. 字典 v1.2 修正 `get_open_interest` request key `intervalTime`、補 `/v5/user/query-api` Python key-validation path、補 G9-02 UnknownHandlerGuard 章節，並把 `account-ratio` endpoint `1d` vs enum `4d` 官方文檔矛盾標為 exchange-smoke-required，而非虛構 runtime truth。

⚠ **持續 open（非 hot-path）**：
- L5-2 follow-up only：若未來新增日級 `account-ratio` polling，需先用 exchange smoke 實測 `"1d"` vs `"4d"`；當前 runtime 只 poll `"1h"`，無 hot-path impact。

### 本次新發現

- **Critical / High**：0 / 0 ✅
- **Medium**：2（純政策層，非代碼）
  - **M5-1 ToS / KYC / 地理禁區 0 governance entry**（CLAUDE.md §三 18 Live Blocker #17）operator 必確認 6 項自證入 git
  - **M5-2 API key IP whitelist 無代碼可驗** — operator 在 Bybit UI 確認
- **Low**：4（L5-1/2/3/4 字典 drift 已於 2026-05-09 F-27 source/test close；L5-2 留 exchange-smoke follow-up only）
- **Advisory**：9（A5-1 至 A5-9）

### 關鍵結構性變動 vs 04-24

1. ★ **`bybit_rest_client.rs` 1725 → 933 行**（簽名邏輯抽到 `common/bybit_signer.rs:164`）— E1-P0-3 dedup
2. ★ **`ws_client.rs` 1136 行單檔 → 6 檔模組 1335 LOC**（mod/connection/dispatch/parsers/run_loop/tests）— 符合 CLAUDE.md §九 800 行警告線
3. ★ **`ws_unknown_handler_guard.rs:488`** 新模組 — G9-02 sliding window + threshold + runtime env-gate `OPENCLAW_WS_FORCE_RECONNECT_ON_UNKNOWN_ENABLED`
4. ★ **`live_auth_watcher.rs:970`** 新獨立模組 — 5min re-verify cancel_token graceful shutdown（教訓 `project_live_auth_watcher_event_consumer_spawn.md`）

### funding_arb BUSDT reject loop Bybit-side RCA

- **Root cause**：Bybit demo 不支援 spot lending（mainnet `/v5/spot-margin-trade/data` 才有），funding_arb V2 long spot leg 抵押不足 → short perp leg 反覆被 Bybit 110017/110007 reject
- **非 ToS 違規**：reject loop 是正常拒單行為，是 OpenClaw 該做 retry budget control
- **修復狀態**：三端 `[funding_arb] active=false`（commit `a19797d` + `2d6a4057`）✅；fee_execution_calibrator.py 加 BUSDT+110017 過濾保護 ML rate estimate ✅；殘倉 ~110017 USD 待 operator 手動 dust clear
- **未來重啟 V3 預檢**：`BybitEnvironment::is_demo()` → demo 直接拒絕 funding_arb 開倉

### Bybit V5 changelog 過去 30d（2026-04-08 至 2026-05-08）

7 條變動，**0 breaking change**：
- 新欄位（symbolId / withdrawMax / openTime） — OpenClaw `serde(default)` 解析不影響
- 新端點（/v5/finance/earn/easy-onchain/position 改、/v5/strategy/create-strategy 新、/v5/new-crypto-loan/...） — OpenClaw 不用
- deprecated `remainAmount`（asset/coin-info） — OpenClaw 用 `chain_withdraw` 不受影響

### Verdict

- **技術合規度**：~95%（47 Rust endpoint 全對齊 / HMAC 100% / rate limit 100% / WS auth 100% / LIVE-GUARD 100%）
- **政策合規度**：~70%（6 項 operator 必確認自證 0 完成）
- **無 ship-stop blocker**；剩餘 gap 純 governance / operator action

### 下次啟動需查驗項

1. M5-1 是否寫入 `docs/governance_dev/YYYY-MM-DD--bybit_compliance_signoff.md`
2. M5-2 IP whitelist operator 在 Bybit UI 確認狀態（無代碼可驗）
3. 若新增日級 account-ratio polling，先實測官方 endpoint `1d` vs enum `4d` 的 drift
4. Bybit V5 changelog 更新（每月例行）
5. funding_arb 是否真正止血（檢查 BUSDT 殘倉 + reject log 不再湧現）
6. broker partnership 申請門檻（30d volume vs $10M）— 當前 $45K 差 222× 不申

---

## 2026-05-09 v2 對抗性核實（v1 → v2 跨 34 commits, `455d796e` → `1bd55689`）

### v1 → v2 closure 進度（6/12）

✅ **v2 真前進**：
- 字典 drift L5-1..L5-4 維持 closed（v1 → v2 無 regression）
- W-AUDIT-6 funding_arb risk config 真清乾（4 個 risk_config TOML 全清，commit `af4942b6`）
- ADR-0018 + ADR-0020 + AMD-2026-05-09-02 + SM-05 governance 收口
- [56] LiveDemo healthcheck IMPL（commit `c15985a5` 加 sentinel + 158 LOC + 125 LOC test）
- A5-4 OPENCLAW_BYBIT_PUBLIC_BASE_URL env override 維持 closed
- 30d Bybit V5 changelog 0 breaking change

⚠ **v1 → v2 stuck**：
- A5-2 110017 Rust enum 仍缺（fee_filter 字串匹配維持工作但 enum 應補）
- A5-6 / NEW-2 [33] fee_filter asymmetry 仍 8 天未做 1 hr fix
- NEW-1 BUSDT PG 殘倉 12186 條仍 stale（demo 9327 + live_demo 2859，5-6 天前最後 snapshot）
  - W-AUDIT-6 是 policy/risk authority cleanup
  - 不是 operational dust clear → operator 仍欠 `/v5/position/list?symbol=BUSDT` 實測

❌ **v2 0 進展**：
- M5-1 ToS / KYC / 地理禁區 governance entry（v1 已列 P0 0-day）
- M5-2 IP whitelist 自檢工具 `helper_scripts/preflight/`（v1 已列 P0 1-day，目錄仍不存在）
- A5-1 / A5-3 / A5-5 / A5-7 / A5-9 advisory 維持

🆕 **v2 NEW REGRESSION**：
- **NEW-3 LiveDemo authorization.json 缺失**（HIGH）：14:33 UTC 直查 [56] = FAIL，pipeline_snapshot_live.json 44 min stale；commit `c15985a5` 加 sentinel 但 sentinel 真實 trip → operator 沒收到 alert（observability theatre）
- **NEW-4 §三 [56] drift**（MED）：CLAUDE.md §三 寫 09:41 UTC PASS，5h 後實測 FAIL → §五 衛生規則 7 day 寬容期不適用 critical health gate；建議副規則 [55]/[56] ≤6h drift

### Bybit-side overall

- **技術合規度**：97%（funding_arb risk config +1pp 但 LiveDemo healthcheck -1pp 平手）
- **政策合規度**：70%（M5-1 / M5-2 仍 0 進展）
- **新增 ship-stop blocker**：authorization.json missing → 重簽 + RCA 為何 09:33 UTC --keep-auth 部署 5h 後 auth 消失

### 下次啟動需查驗項

1. M5-1 `docs/governance_dev/2026-05-09--bybit_compliance_signoff.md` 是否建檔
2. M5-2 `helper_scripts/preflight/check_bybit_ip_whitelist.py` 是否 IMPL
3. NEW-1 BUSDT PG 殘倉是否 dust clear（operator 端 `/v5/position/list` 結果）
4. NEW-3 [56] healthcheck PASS 維持狀態 + auth lifecycle 穩
5. A5-2 BybitRetCode enum 110017 是否補
6. NEW-2 [33] fee_filter funding_arb 過濾是否補

