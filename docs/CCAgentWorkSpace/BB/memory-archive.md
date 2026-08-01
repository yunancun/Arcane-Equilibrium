# BB Memory Archive（append-only：壓實遷入原文，勿刪改）

--- 2026-06-10 壓實遷入（原 memory.md 第 1-1074 行）---
# BB (Bybit Broker Compatibility Auditor) — Memory

## Memory Usage Contract (2026-05-16)

- 本文件保存歷史教訓與角色偏好，不是 active state、TODO 或 runtime ledger。
- 若舊條目與 `TODO.md`、`README.md`、`CLAUDE.md`、`.codex/MEMORY.md`、`docs/agents/context-loading.md`、代碼或 runtime 證據衝突，信任較新的有證據來源並顯式說明衝突。
- 不要靜默刪除舊條目；只追加可復用的 durable lesson。長報告放 `workspace/reports/`，active 進度放 `TODO.md`。

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


---

## 2026-05-10 Sprint N+0 final review (HEAD `18e212f9`, 28 commits since v3 baseline)

### Verdict: **APPROVE** (Sprint N+0 整體 BB 視角)

### Sprint N+0 28 commits Bybit-side impact 核實

- `git diff --stat 1bd55689..HEAD -- 'rust/openclaw_engine/src/{bybit_*,ws_client*,market_data_client*}'` = **空** (0 Bybit endpoint 接線變動)
- Strategy trait 升級 (W-AUDIT-8a Phase A) + W-AUDIT-9 IMPL 全部 internal struct/enum/PG schema/Python provider/GUI surface
- W-AUDIT-9 7 sub-task 全 land + E2/E4 third-pass APPROVE/PASS

### W-AUDIT-9 graduated canary 對 Bybit live 影響

- Stage 0/1 = 0 Bybit API call (shadow + paper simulation)
- Stage 2/3 = api-demo.bybit.com + wss://stream-demo.bybit.com (與 LiveDemo 同 endpoint, 不需 LiveDemo authorization.json)
- Stage 4 = LIVE_PENDING, 仍受 Live boundary 5-gate 全強制 (CLAUDE.md §四 line 125-136 不放寬)
- canary_stage_log entry **0 影響** Bybit broker rebate / market maker / VIP tier (純 internal governance audit table)
- LiveDemo authorization.json 5min re-verify 與 canary stage transitions 完全解耦 (無 deadlock 可能)

### W-AUDIT-8a Phase A AlphaSurface Tier 2/3 對 Bybit 影響

- Phase A IMPL = 0 Bybit endpoint 變動 (純 Rust struct/enum/trait migration + 5 策略 declare)
- BB v3 三 push back NEW-5/6/8 全採納 ✅:
  - **NEW-5 PA spec L25 不存在** — spec line 151-156 「禁止 L25」+ 預設 orderbook.50 + alpha_surface.rs `OrderflowImbalance` 0 「L25」字串
  - **NEW-6 liquidation_pulse 已 deleted 需 revert** — spec line 162-170 `requires_revival: true` + alpha_surface.rs dormant 註釋 + 永遠 `None`
  - **NEW-8 basis demo 限 observation 沒分** — spec line 132-138 `requires_spot_capability: true` + IntentRouter 檢查 + alpha_surface.rs 「永遠是 observation-only signal」

### 字典 drift verify

- Sprint N+0 0 endpoint 變動 → 字典 v1.2 vs source = 0 drift
- 30d Bybit V5 changelog 0 breaking change (繼承 v3)

### 政策合規度仍 70% (與 v3 持平)

- M5-1 / M5-2 / BUSDT PG 殘倉 dust clear / A5-2 / A5-6 維持 outstanding
- 不阻 Sprint N+0 sign-off (W-AUDIT-9 不引入新地區/KYC 變動;Stage 4 才需 5-gate 全 closed)

### N+1+ FLAG follow-up

- **HIGH**:
  1. W-AUDIT-8a Phase B Sprint N+1 Tier 2 collector IMPL 必 BB review (WS 優先於 REST / 25-sym aggregator pattern / IntentRouter `requires_spot_capability && !env_has_spot` 檢查)
  2. W-AUDIT-8c Sprint N+2 spec Liquidation 復活前必跑 BB rate-limit 估算 + UnknownHandlerGuard 串接
- **MEDIUM**:
  1. W-AUDIT-9 Stage 1 cohort symbol 不可為 BUSDT
  2. Stage 1 cohort symbol 必於 30d listing/delisting 確認

### 下次啟動需查驗項

1. W-AUDIT-9 Stage 1 啟動時 operator 拍板的 cohort symbol 是否 BB pre-flight pass (BUSDT 排除 + listing 確認)
2. W-AUDIT-8a Phase B IMPL 是否 BB review 25-sym collector pattern
3. W-AUDIT-8a Phase C+1 sprint Liquidation 復活 spec 是否 BB rate-limit 估算
4. M5-1 governance entry / M5-2 IP whitelist preflight 是否 IMPL (Stage 4 前 mandatory)
5. BUSDT PG 殘倉 (12186 條,11 天延遲) operator 是否手動 dust clear


---

## 2026-05-10 W1+W2 Bybit V5 rate budget review (Sprint N+1 pre-flight)

### Trigger

Sprint N+1 W1 (W-AUDIT-8a Phase B Tier 2 collector funding_curve + oi_delta_panel) + W2 (A4-C BTC→Alt Lead-Lag) + W3 Stage 1 cohort observation 啟動前 PM 預跑 rate budget review。

### 真實 Bybit V5 cap (verified 2026-05-10)

- Per IP HTTP: **600 req / 5s = 120 req/s**（公共 `/v5/market/*` 端點）
- Per UID Order/Position/Account: **20 req/s each**（VIP 升）
- Per UID Market: **120 req/s**
- Per UID Asset: 5 req/s
- 違反 IP cap → 403 + 10 min cooldown
- WS conn cap: 500/5min, market data 1000/IP

### 既有 baseline rate (verified `rest_poller.rs` HEAD)

- Funding poller: 25 sym / 900s = 0.028 req/s
- OI poller: 25 sym / 300s = 0.083 req/s
- LSR poller: 25 sym / 900s = 0.028 req/s
- WS public (kline.1 + tickers + orderbook.50 × 25 sym): 0 REST cost
- Authenticated REST cycle: < 0.5 req/s
- Healthcheck: < 0.1 req/s
- **Baseline 合計 ~0.7 req/s**

### W1+W2+W3 增量

- W1 dispatch v3.3 寫 25 sym × 60 = 1500 req/h = 0.42 req/s × 2 endpoint = 0.83 req/s 增量（如走 REST polling）
- W1 BB 推薦 **WS-first pattern**：tickers topic 已 broadcast fundingRate + openInterest field（字典 line 974）→ 真實增量 = **0 ~ 0.5 req/s**
- W2 (BTCUSDT 1m kline + orderbook): WS 已預設訂閱 → **0 REST 增量**
- W3 Stage 1: shadow + paper simulator → **0 真實 Bybit API**

### Verdict: PASS（~99% headroom）

- 總和（WS-first IMPL）: 0.7 ~ 1.2 req/s = 利用率 0.6 ~ 1.0% Bybit IP cap
- 多 writer 同 launch burst: 25 sym × 3 endpoint cold-start = 75 req 瞬發 ≪ 600/5s
- ToS / KYC / 地理: **0 風險**（read-only market data, no order, no quote, 25 sym 全 USDT-perp linear, demo + LiveDemo 不觸 KYC tier 3, 不觸 broker rebate volume tally）

### 主要 push back (HIGH)

W1 spec "1500 req/h REST polling" = over-engineering。`tickers` WS topic 已 broadcast 全部 funding + OI field。建議 PA Phase B IMPL **WS-first**, REST 只 cold-start backfill。如 PA 採納 → W1 真實增量 ~0 req/s 而非 0.83 req/s。

### 次要 push back (MEDIUM)

- 若 PA 堅持 REST polling，加 `is_group_near_limit(Market, 30)` 預警（防未來 cohort scale 觸 cap）
- W3 Stage 1 cohort 拍板必排除 BUSDT（funding_arb retire 殘倉風險，v3 carry-over）

### Report path

srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-10--w1_w2_bybit_v5_rate_budget_review.md

### 下次啟動需查驗項

1. PA Phase B spec 是否採納 WS-first pattern
2. 若採納 → W1 collector IMPL 是否真用 `tickers` WS topic 解析 fundingRate / openInterest field（不重複 REST poll）
3. 若未採納 → collector 是否加 rate group monitoring + aggregator pattern
4. W3 Stage 1 cohort 拍板 symbol 是否確認 BUSDT 排除


---

## 2026-05-11 LG-3 Supervised-Live State Machine Spec v1 review (Wave 2.1.5)

### Trigger

PM 派 Wave 2.1.5 三方並行 review (QC math + BB Bybit + MIT data/audit) on PA spec v1
`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v1.md` (1221 行).

### Verdict: **APPROVE WITH 6 BYBIT CAVEATS** (5 spec 必補章節 + 1 mainnet checklist + 1 meta pre-flight)

### Bybit V5 endpoint alignment

LG-3 觸發 endpoint inventory (5 endpoint + Private WS):
- `POST /v5/order/create` (close_position on kill) — Order 20 r/s — 字典 line 306/1054
- `POST /v5/order/cancel-all` (pending on kill) — Order 20 r/s — 字典 line 389
- `GET /v5/account/wallet-balance` (engine boot) — Account 20 r/s — 字典 line 638
- `GET /v5/position/list` (reconcile) — Position 20 r/s — 字典 line 502
- Private WS `[order, execution, position, wallet, dcp]` — 字典 line 1000

**字典 v1.2 vs PA spec v1 = 0 drift**. 30d Bybit V5 changelog 0 breaking change.

### 6 Caveats for PA spec v2

| # | 嚴重度 | spec v2 章節 | 補 |
|---|---|---|---|
| 1 | MEDIUM | §7.6 new | WS reconnect 不觸 SM transition |
| 2 | HIGH | §6.6 new + §1.2 | Kill batch_wait rate-limit pattern (per-symbol 0.3s margin) |
| 3 | LOW | §3.6 new | Renew 走既有 `live_trust_routes.renew()` 不重複 |
| 4 | HIGH | §6.3 改 | Cancel-all THEN close-position THEN revoke 順序，DCP 不可作 primary |
| 5 | MEDIUM | §7.4 改 + §3.3 Gate 7 加 | Bybit KYC tier 與 EarnedTrust tier cross-ref |
| 6 | HIGH | §15.4 new | Mainnet 解鎖前 8 項 BB mandatory checklist |
| 7 (meta) | LOW | §13.4 改 | Wave 2.4 IMPL pre-flight changelog 自查 |

### Bybit-side overall

- 技術合規度: 97% (LG-3 0 endpoint 變動，仍維持 v3 baseline)
- 政策合規度: 70% (M5-1 + M5-2 12+ day 0 進展，mainnet 解鎖前 mandatory)
- 0 ship-stop blocker
- 0 endpoint deprecation 觸碰
- 5-gate live boundary 不放寬

### 關鍵 push back 重點

1. **caveat 2 + 4 HIGH**：`/kill` IMPL 必走「per-symbol 序列化 cancel-all → close-position → revoke」順序，每 step 0.3s safety margin。**禁止**先 revoke → engine cancel_token → cancel-all 沒 fire 靠 DCP fallback (DCP 是 backup 不是 primary)。
2. **caveat 6 HIGH**：Mainnet 解鎖前 BB mandatory 8 項 checklist 進 spec v2 §15.4，覆蓋 M5-1 / M5-2 / API key / runbook / KYC / IP whitelist / first-day limit 等。
3. **caveat 5 MEDIUM**：EarnedTrust T0-T3 與 Bybit KYC tier cross-ref，approval Gate 7 加 `bybit_kyc_tier_below_trust_tier_requirement` reason code。

### 下次啟動需查驗項

1. PA spec v2 是否採納 6 caveats (特別 caveat 2 + 4)
2. Wave 2.4 IMPL 前 Bybit V5 changelog 0 breaking change verify
3. LG3-T5 IMPL `/kill` 是否真用 0.3s safety margin
4. LG3-T3 approval Gate 7 是否加 Bybit KYC tier check
5. spec v2 §15.4 Mainnet 解鎖 8 項 checklist 是否完整入 spec
6. M5-1 / M5-2 進展 (仍 stale；mainnet 解鎖 mandatory)

### Report path

`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-11--lg3_spec_bb_review.md`


---

## 2026-05-15 Wave 3a BB short re-review on AMD v0.3 + spec v1.2 (HEAD `47b8cd23` → `6713bcdc`)

### Trigger

PM 派 Wave 3a (4-agent QC+FA+BB+MIT 各 30 min 並行 short re-review) on AMD v0.3 + spec v1.2 at HEAD `47b8cd23`，verify round 2 BB 5 must-fix + 3 should-fix + 4 補錄 collection 完整 + v1.1→v1.2 + v0.2→v0.3 增量 Bybit-side risk。

### Verdict: **APPROVED**

5/5 must-fix all landed + 3/3 should-fix all landed + 4 補錄字典手冊 deferred Wave 3b correctly + v1.2/v0.3 增量無新 Bybit-side risk。

Confidence HIGH (cross-check spec/AMD 22 處 BB-MF/BB-SF 引用 + Bybit V5 fee/rate/reject doc consistency).

### Round 2 BB-MF/BB-SF 收口 verification

| BB-MF/SF | Verification status |
|---|---|
| BB-MF-1 (字典 PostOnly+reduceOnly) | ✅ DEFERRED Wave 3b correctly (spec §6.2 line 474-477 標 TODO; AMD §10 表保留 6 項清單) |
| BB-MF-2 (dynamic backoff per-symbol) | ✅ FULLY ADOPTED (AMD §5.4 line 181-218 + spec §5.4 line 352-381 完整 mirror per-symbol 1s→60s exp + conditional global 10-symbol cascade) |
| BB-MF-3 (reject_cooldown split P0) | ✅ FULLY ADOPTED (AMD §8 prereq 6 + spec §6.1 + §14 升 P0 IMPL prereq) |
| BB-MF-4 (classifier 復用 entry enum) | ✅ FULLY ADOPTED (spec §6.2 line 434-472 不新建 Close*Variant + dispatch handler `side: OrderSide` flag) |
| BB-MF-5 (reject sample healthcheck) | ✅ FULLY ADOPTED (spec §8.3 [65] + AC-15) |
| BB-SF-1 ([64] healthcheck) | ✅ FULLY ADOPTED (spec §8.1 line 562-580 per-symbol + global thresholds) |
| BB-SF-2 (fee 4.5→3.5→0.5-2.0 bps) | ✅ FULLY ADOPTED + ENHANCED (v1.2 進一步 conservative range per Track E3 三層解讀; 全年 $50-$200; tier 0 maker 2.0/taker 5.5 一致) |
| BB-SF-3 (small-tick alt symbol) | ✅ FULLY ADOPTED (spec §4.2 footnote line 205 + AMD §6 + spec §9.2 test 表) |

### v1.2/v0.3 增量 Bybit-side risk verdict

1. **E3 fee revision (4.5→0.5-2.0 bps + $50-$200/year)**: ✅ Bybit fee tier 0 結構一致；保守 range cover empirical uncertainty；BTC/ETH alt 無區分需求 (per-account 維度)；維持 tier 0 (30d volume ≪ VIP 1 $1M)
2. **§5.5 NEW Race E mandatory fallback to taker**: ✅ Bybit Order group rate budget worst case 0.017 req/s (vs 20 req/s cap = 0.085% 利用率)；burst 5s 50% 餘裕；無新 conservative cooldown 需求；fallback enum 完整 cover Bybit reject 場景
3. **AC-18 fallback ≥ 95%**: ✅ COMPATIBLE 與 Order group rate limit (worst case 0.006 req/s = 0.03% 利用率)；race window 5% allowance 設計合理
4. **AC-19 14d ≥ 30%**: ✅ APPROVED + Demo→Mainnet drift 通過 AC-15 reject sample probe + Phase 3 mandatory operator sign-off + 7 條 BB Mainnet prereq (round 2 §9 outstanding) 覆蓋鏈完整
5. **3 E3 意外發現 (orders.intent_id NULL / orders.status fire-and-forget / 無 fallback to taker)**: ✅ 0 ToS / 0 broker rebate / 0 market maker eligibility 風險；P2 ticket 開立合理；observability note: BB future audit 跟蹤 close-maker fallback path 對 Order group rate limit 30d trend (baseline 0.7 → close-maker 部署後 ≤ 1.5 req/s sustained)

### AMD prereq condition 2 status

**BB-side PASS**：等待 QC + FA + MIT 並行 Wave 3a 視角 verdict 收齊後 PM 統一 sign-off；BB 不阻其他 agent 並行 review；本 BB short re-review 不需 follow-up patch。

### Wave 3b BB1 字典手冊 6 處更新清單 (本 task record SoT)

1. §1.2 PostOnly + reduceOnly 並用合法 (HIGH)
2. §4.1 Order group 20 r/s shared quota (MEDIUM)
3. §4.3 demo PostOnly silent degradation 警告 (HIGH)
4. §1.9 per-symbol PostOnly minimum effective offset (MEDIUM)
5. §4.2.1 close side 與 entry side 同 classifier (MEDIUM)
6. §1.10 NEW close maker dispatch 小節 (LOW, IMPL DONE 後)

估算 BB1 工作量 ~2-3h docs update + commit + push。

### Report path

`srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-15--amd_v0_3_spec_v1_2_bb_short_re_review.md` (commit `6713bcdc`)

### 下次啟動需查驗項

1. Wave 3a QC + FA + MIT 並行 verdict 是否完成 + PM consolidated sign-off
2. Wave 3b BB1 字典手冊 6 處更新是否啟動
3. AMD prereq 條件 2 (4-agent re-review) 是否 marked DONE
4. AMD prereq 條件 6 (reject_cooldown split) Wave 2 IMPL 是否 land
5. 3-gate (P0-EDGE-1 / W-AUDIT-8b Stage 0R / W-AUDIT-8a C1) 是否 closed
6. close-maker-first IMPL kickoff 期 BB 必跟蹤 close-maker fallback path 對 Order group rate limit 30d trend

---

## 2026-05-16 Round 3 — Wave 2 WP-10 + BB-MF-3 push 後核驗 (HEAD `c0d34fcb`)

### Verdict: **APPROVE-CONDITIONAL Round 3** (1 P2 dict + 1 P1 wiring + 2 P2 follow-up)

### Round 2 → Round 3 closure (2/3)

✅ **closed**：
- WP-10 BybitRetCode::ReduceOnlyReject=110017 enum + from_code + 5 classifier false × 7 assertion (`bybit_rest_client.rs:339+394` + `bybit_rest_client_tests.rs:362-377`)
- BB-MF-3 grid_trading entry/close cooldown split 8/8 unit test (`tests.rs:1392-1686` 完整覆蓋 entry-freeze-close / close-freeze-entry / TooManyPending-5min / PostOnlyCross-no-cooldown / 1min-default × 3-category / both-active short-circuit / multi-symbol isolation / i64-saturating-add)
- backtest_routes.py:110 `_BYBIT_BASE_URL = os.getenv("OPENCLAW_BYBIT_BACKTEST_URL", "https://api-demo.bybit.com")` 確認 demo default

⚠️ **Round 2 conditional 仍 open**：
- **字典 §4.2 110017 row ABSENT**（Wave 3b BB1 從 6 升 7；`P2-BB-DICT-110017` ticket est 15 min）
- 3 檔殘餘 mainnet hardcode reframe：1 已 fix (backtest_routes) / 1 acceptable env-fallback (`bybit_public_microstructure_builder.py`，line 396 `os.getenv` pattern) / 2 STUB 模組 (`market_scanner.py` + `kline_manager.py`，file header `STUB:` 全 `return None`/`return {}` 0 hot path) → 真實 risk 0；`P2-MAINNET-HARDCODE-CLEANUP` cleanup-only ticket
- `on_post_only_rejected` Strategy trait + `arm_close_cooldown` 公共 API → 仍 0 production caller (grep `bybit_private_ws_status_writer.rs / order_manager.rs / strategy_runner.rs / dispatch.rs / commands.rs` 0 hit)；Wave 2b 自承「不接線 production dispatcher」屬實；**P1-BBMF-WIRING-1** ticket 強烈推薦（est 4-6h，Phase 1b 主軸 IMPL 範圍）

### 關鍵 Round 3 發現

1. ★ **`is_exchange_backoff` comment CLEAN**：`bybit_rest_client.rs:427-435` 完整 EDGE-P2-3 Phase 1B-1 reference + 中英對照 + matches enum，0 BB-MF-3 cooldown / arm_close 字串侵入；`ef6ea79f` 自承 revert 邏輯成立。Race incident root cause：Wave 2 並行兩分支共享 strategy crate diff context，BB-MF-3 doc 跨檔誤滲到 retCode classifier doc。
2. ★ **maker_rejection.rs sibling revert 完整**：216 行 source 0 出現 `BB-MF-3 / reject_cooldown_entry / arm_close_cooldown / split`；Wave 2b E1 sign-off 描述「+7 LOC doc reference 指向 close_reject_cooldown_ms_for_category()」**未 land**。建議 `P2-BBMF3-DOC-XREF` follow-up（est 10 min，補 7 LOC pointer），non-blocking。
3. ★ **110017 五 classifier 全 false 正確**：Bybit V5 `ReduceOnly Order Failed` = 終態錯誤（倉位不存在/方向不匹配，重試無意義） + non-noop（caller 邏輯錯誤非 lifecycle race） + non-balance / non-exchange-backoff / non-instrument-filter；VIP/tier 對 110017 行為 0 差異（pos-state-driven）。
4. ★ **BB-MF-3 8 test 質量 EXCEPTIONAL**：cross-symbol regression + i64-overflow safety + double-active short-circuit + cross-category default cover 全 land；`signal.rs:294-297` 從 entry map 讀 cooldown gate；`constructors.rs:60+119+192` 3 構造路徑全初始化。

### EDGE-P2-3 Phase 1b prereq 解除進度

✅ Prereq 6 BB-MF-3 reject_cooldown split = ASSESSED-DONE (helper + 8 test land；production wiring 屬主軸 IMPL 範圍非 prereq)
✅ Prereq 5 第 3 子條件 F-FA-1 V094 spec = DONE (commit a9b3a792)
⏳ Prereq 1-4 + 5(第 1/2 子條件) 仍 open
⏳ 3-gate (P0-EDGE-1 / W-AUDIT-8b Stage 0R / W-AUDIT-8a C1) RED × 3

Phase 1b 主軸 IMPL kickoff 仍 BLOCKED（4 prereq + 3-gate）但 BB-side 不阻。

### PostOnly close → market + TooManyPending 5min 固定 Bybit 視角

- PostOnlyCross close fallback to taker：spec §5.3 Race C 容忍率 5-15% → +0.275~+0.825 bps cost shift，遠 << +5bps maker rebate saving，APPROVE
- TooManyPending close 5min 固定：Order group 利用率 0.083 r/s = 0.4% cap (25 sym × 0.0033 r/s/sym)，絕對保守；dynamic backoff (§5.4 1s→60s exp + 10-sym cascade) 留 P1-BBMF-2-DYNAMIC-BACKOFF-1

### Wave 3b BB1 字典手冊更新清單（從 6 升 7）

1. §1.2 PostOnly + reduceOnly 並用合法 (HIGH)
2. §4.1 Order group 20 r/s shared quota (MEDIUM)
3. §4.2 110017 ReduceOnlyReject row 補 (MEDIUM)  ← 本輪新增
4. §4.3 demo PostOnly silent degradation 警告 (HIGH)
5. §1.9 per-symbol PostOnly minimum effective offset (MEDIUM)
6. §4.2.1 close side 與 entry side 同 classifier (MEDIUM)
7. §1.10 NEW close maker dispatch 小節 (LOW，IMPL DONE 後)

估算工作量 ~2.5-3h docs update + commit + push。

### Bybit-side overall

- 技術合規度：97% (110017 + BB-MF-3 split + dual-map cooldown gate + signal.rs read path land)
- 政策合規度：70% (M5-1 / M5-2 12+ day 0 進展)
- 0 ship-stop blocker；剩 ALL non-blocking docs / follow-up wiring

### 下次啟動需查驗項

1. `P2-BB-DICT-110017` 字典 §4.2 row 補 (Wave 3b BB1 啟動)
2. `P1-BBMF-WIRING-1` production dispatcher → strategy callback wiring (Phase 1b 主軸)
3. `P2-BBMF3-DOC-XREF` maker_rejection.rs 7 LOC pointer (non-blocking)
4. `P2-MAINNET-HARDCODE-CLEANUP` 2 stub URL default (non-blocking)
5. P1-BBMF-2-DYNAMIC-BACKOFF-1 (spec §5.4，acceptable defer)
6. close-maker fallback path Order group 30d trend (baseline 0.7 → 部署後預估 ≤ 1.5 req/s sustained)

### Report path

`srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-16--wave2_wp10_bbmf3_round3_bb_review.md`

---

## 2026-05-16 Wave 3b BB1 — 字典手冊 6 處更新 LAND（HEAD `55f35adb`）

### Trigger

PM 派 Wave 3b followup from Wave 3a re-review；2026-05-15 BB short re-review §7 SoT 列 6 處字典手冊更新項，本任務把 6 項實際 land 進 `srv/docs/references/2026-04-04--bybit_api_reference.md`。

### Verdict: **LANDED 6/6 + Mac/Linux 雙端 verified**

字典 v1.2 → v1.3 版本 bump 完成。Mac commit `28c571c7` + Linux trade-core git pull --ff-only verified（1330 行雙端一致）。BB workspace report commit `55f35adb`。

### 6 處改動 summary

| # | 字典位置 | 等級 | 改動 |
|---|---|---|---|
| 1 | §1.2 Orders | HIGH (BB-MF-1) | Rate Group 一致化 (10→20 r/s, sync §4.1) + 新增 PostOnly+reduceOnly 並用合法子段（含 sample request body + Bybit V5 doc 引用）|
| 2 | §4.1 Rate Limit 分組 | MED (BB-SF-1) | Order group 20 r/s shared quota 註腳（create/cancel/cancel-all/amend/batch/execution.* 共用）+ close-maker-first kill-switch budget 估算 0.085% utilization + LG-3 0.3s safety margin |
| 3 | §4.3 #14 已知陷阱 | HIGH | Demo silent degradation 警告（per Bybit V5 demo doc 「not a complete function」+ Wave 1 Track E3 70% timeout empirical baseline + [65] mainnet probe gate）|
| 4 | §1.9 Instrument Cache | MED (BB-SF-3) | Per-symbol PostOnly min offset guidance + 4 categories 風險表 + 1000PEPE/1000BONK corner case + status != Trading |
| 5 | §4.2.1 reject reason 表 | MED (BB-MF-4) | Classifier 復用 entry/close 同 enum 註腳 + dispatch handler `side: OrderSide` flag 4-row matrix |
| 6 | §1.10 NEW (close maker dispatch) | LOW | spec-level reference 章節 (10 sub-section)：8-condition whitelist + negative whitelist + reject classifier 復用 + cooldown split + Race D dynamic backoff + Race E mandatory fallback + [65] healthcheck + V094 audit schema + non-training surface invariant |

### 工時 / Race 防範

- 估算 ~2-3h；實際 ~1.2h（beat estimate）
- ✅ commit-only 單檔 + push-immediate + `[skip ci]`
- ✅ Mac → Linux trade-core ssh git pull --ff-only verified
- ✅ 0 scope creep；0 sibling session race conflict

### 下次啟動需查驗項

1. Wave 4 E1 dispatch 後字典 §1.10 IMPL DONE 補錄是否 land（commands.rs line range 修正 + V094 actual migration apply timestamp）
2. `[62]/[63]/[64]/[65]` 4 healthcheck PASS 7d 持續監控（per OBSERVABILITY NOTE）
3. Order group rate limit 30d trend 是否 ≤ 1.5 req/s sustained（baseline 0.7 → close-maker-first 部署後）
4. Phase 2a Demo 14d empirical reject sample 真實計數收集（per [65] mainnet probe 觸發判斷）
5. AMD v0.3.1 prereq condition 6（reject_cooldown split P0）IMPL closure 進度（per Wave 2c-1/2 已開工）
6. Wave 4 IMPL kickoff（3-gate 解後派 E1 5-worktree）

### Report path

`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-16--bybit_dict_6_updates_bb_verdict.md`


---

## 2026-05-16 W-AUDIT-8a C1 v2 resilient harness BB pre-review (HEAD `5983f955`)

### Trigger

PM 派 W-AUDIT-8a C1 v2 942 LOC E1 IMPL pre-deploy BB pre-review；v1 17055s/86400s FAIL_CONNECTION 後 v2 加 reconnect + TCP keepalive + per-hour checkpoint + restart budget=3。Worktree branch `worktree-agent-a58d99ef4ea1a440b` HEAD `5983f955`，未進 main。

### Verdict: **APPROVE-CONDITIONAL** (5/5 focus PASS + 3 LOW advisory + 0 ship-stop)

### 5 Focus Verdict

- F1 allLiquidation payload real schema: ✅ PASS — v1 5 frame / 9 entry 與 Bybit V5 docs 1:1 對齊（T/s/S/v/p；type=snapshot；push 500ms batch）
- F2 WS endpoint + rate limit + ToS: ✅ PASS — 500 conn/5min cap 99.997% headroom；21000 chars subscribe 99.3% headroom；ToS 0 違規
- F3 5 topic / 1 connection 共存: ✅ PASS — v1 5h 實證 backpressure 0；orderbook 76.7% / liquidation 0.0025% 流量分布
- F4 reconnect 策略 vs ToS: ✅ PASS — worst case 24 conn/24h vs 500/5min cap = 99.97% headroom
- F5 v1 15 messages schema delta 預檢: ✅ PASS — MIT pre-review 可基於 v1 數據直接做 mapping

### 3 Advisory LOW (non-blocking)

- A-1 v2 ping_interval=10s vs Bybit 推薦 20s（probe over-aggressive 但合法）
- A-2 v2 reconnect base=1s vs production engine 3s 不對稱
- A-3 字典 §2.1 `allLiquidation.{symbol}` 完整 schema 補錄（C1 PASS 後 W-AUDIT-8a Phase C IMPL kickoff 期）

### 4 待答 BB-side Answers

1. `market.liquidations` PG schema — **MIT 主負**（正確 design）
2. v1 15 messages JSON dump — ✅ `trade-core:/tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_latest.json` `candidate_samples[]` (5 frame + 9 inner entry)
3. Schema delta V09X migration 需要否 — **MIT 主負**（BB advisory：v1 vs docs 1:1 對齊，若 schema 既有對應 column → delta=0）
4. `allLiquidation` payload type field — ✅ Bybit 當前實作只推 `snapshot`，**無 delta type** 觀察到

### v2 設計 Bybit-side overall

- 技術合規度：97%（C1 v2 0 endpoint 改動 / 0 字典 drift）
- 政策合規度：70%（M5-1 / M5-2 持平）
- 30d changelog 0 breaking change（5/14 Card affiliate / 5/7 Earn / 5/6 Crypto Loan 全與 OpenClaw 無關）
- 0 ship-stop blocker
- 16 根原則 + 硬邊界 5 gate + DOC-08 §12 9 不變量 全 0 觸碰

### 下次啟動需查驗項

1. operator 啟 v2 24h proof 後 BB sign-off invariant 4 條（elapsed≥82800 / poison=0 / uptime_ratio≥0.95 / MIT verdict APPROVE）
2. v2 ping 10s/20s + reconnect base 1s/3s（A-1 / A-2）operator 決定
3. C1 PASS 後字典 §2.1 補錄（A-3）+ Phase C IMPL kickoff
4. v2 production-builder kickoff 期 UnknownHandlerGuard 串接 + cross-symbol multiplexing 驗證（W-AUDIT-8c 25-sym）

### Report path

`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-16--w_audit_8a_c1_v2_harness_bb_pre_review.md`

---

## 2026-05-21 v5.7 C4 + C5 + C6 三件 advisory verdict (HEAD pending)

### Trigger

PM 派 v57 dispatch-safe patch Sprint 1A 派發前 3 件 BB advisory（v57 executability audit §4 列「PA / FA 必收 top 3」延伸）：C4 Earn endpoint 存在性 / C5 Stake/Redeem API key scope / C6 W-AUDIT-8a C1 24h proof verdict。

### Verdict

| # | 三選一 |
|---|---|
| C4 | **(a) API exists**（`/v5/earn/flexible/*` + `/v5/earn/fixed/*` + `/v5/finance/earn/easy-onchain/*`），12 endpoint 完整，2025-02-20 launch；字典 0 entries → drift 5+ 個月 |
| C5 | **(a) non-withdraw scope sufficient**（dedicated `Earn` scope，2026-04-09 後 key 自動帶；2026-04-09 前 key 缺）；不違 D1d / Hard Boundaries |
| C6 | **(a) PROOF PASS** — PG `market.liquidations` 31,473 rows / 3.7 day / 99 rows 5min 持續流入；writer production-grade |

### 重大發現：推翻 2026-05-21 v57 executability audit Risk 1 BLOCKED claim

v57 audit Risk 1 claim「§6 30k+ rows 是 2026-04-05 之前舊資料 + writer 未恢復 + Sprint 1A scope 反向 +30~50 hr」**完全錯誤**。實際：
- PG empirical query: 31,473 rows, time range 2026-05-17 23:12 → 2026-05-21 16:01（3.7 day）
- writer 是 production engine PID 2934602 `/home/ncyu/BybitOpenClaw/srv` from 13:31，canary mode + paper=0
- `multi_interval_topics.rs:131` / `ws_client/dispatch.rs:115` / `parsers.rs:295` / `market_writer.rs:475` 全 wired
- 99 rows in last 5 min (16 cohort + 23 non-cohort symbols)

Root cause：v57 audit 過信字典 line 1092 + W-AUDIT-8a C1 plan「BLOCKED」status，**沒做 PG empirical query** 直接驗證；字典 + plan stale ~5 day。

### Sprint 1A 工時 net 修正

| 項目 | v5.7 estimate | v57 audit | BB-real（本次） |
|---|---|---|---|
| §4 Earn API integration | 15 hr | 30~40 hr 或 BD waiting | **18~25 hr**（read-only first） |
| §6 Liquidation writer | -15~20 hr 節省 | +30~50 hr 反向 | **0~+1 hr**（writer 已 prod） |
| **Sprint 1A total** | **60~80 hr** | **90~130 hr** | **65~85 hr** |

v57 audit total over-estimated by ~30 hr，主因 §6 Risk 1 過度反估 +50 hr。

### 字典補錄清單（BB1 Wave 3b 從 7 升 13）

新增 6 處：
1. §3 NEW Earn API 章節（12 endpoint，HIGH）
2. §1.10 line 1092/1099/1325 移除 allLiquidation BLOCKED 字樣（HIGH）
3. §2.1 WS topic table `allLiquidation.{symbol}` 標 active production（HIGH）
4. §3 NEW `/v5/earn/byusdt/*` 章節（LOW）
5. §3 NEW `/v5/earn/fixed-saving/*` 章節（LOW）
6. §4.1 Rate Limit table 新加 Earn group（LOW）

估 ~4-6 hr 與既有 BB1 工作合併。

### Sprint 1A 派發前 must-fix（從 v57 7 項修正為 4 項）

1. 字典 ref handbook §3 NEW Earn API 章節 + §1.10 W-AUDIT-8a C1 BLOCKED 字樣修正（HIGH，4-6 hr，BB1）
2. operator 查 OpenClaw API key 發行日 + Bybit account UI `Earn` scope toggle 確認（HIGH，5-10 min）
3. W-AUDIT-8a C1 plan §Verdict 標 PASS-by-empirical-evidence + MIT 補 schema mapping sign-off（HIGH，5-8 hr）
4. Bybit demo / LiveDemo Earn endpoint smoke test（HIGH，0.5 hr，operator + BB）

原 v57 must-fix #5（options chain recorder schema review）+ #7（§4 driver endpoint 環境決策）保持。

### Bybit-side overall（2026-05-21 本次）

- 技術合規度：96%（writer production-confirmed 但字典 + plan 仍標 BLOCKED 屬 governance drift）
- 政策合規度：72%（Earn scope 0 違反 + key 發行日待 operator 驗）
- 0 ship-stop blocker
- 0 hard boundary 違反
- 30d Bybit V5 changelog 0 breaking change（Earn `/v5/earn/byusdt/*` + `/v5/earn/fixed-saving/*` 新加但與 OpenClaw 當前無交集）

### 下次啟動需查驗項

1. BB1 sub-agent Wave 3b 13 項字典更新是否啟動（從 7 升 13）
2. operator API key 發行日 + Earn scope toggle 確認結果
3. W-AUDIT-8a C1 plan PASS-by-empirical-evidence 是否 land（execution plan + 字典同步）
4. MIT schema mapping sign-off 是否補（5 col PG schema → Rust `MarketDataMsg::Liquidation` mapping）
5. Sprint 1A §4 scope 是否限定 read-only Earn API（不接 stake/redeem programmatic）
6. Bybit demo / LiveDemo `/v5/earn/flexible/product` smoke 結果
7. 25-cohort filter 策略決策（QC/PA 拍板）
8. v57 executability audit 是否 deprecate Risk 1 段落 + 補本 verdict cross-ref

### Report path

`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-21--v57_c4_c5_c6_bybit_verdict.md`
（同檔複製到 `docs/CCAgentWorkSpace/Operator/`，因 Risk 1 推翻 + 工時 ±50 hr 修正屬 HIGH severity operator advisory）


---

## 2026-05-23 Sprint 1B Pending 3.2 Earn cross-ref BB review (HEAD `875de212`)

### Trigger

PM 派 5 角色 (FA/E3/QA/MIT/BB) 並行 cross-ref on earn_governance spec amendment + 5 E1 IMPL Wave B DONE（含 E1c `bybit_earn_client.rs` 601 LOC）。1-2 hr single-thread review。

### Verdict: **APPROVE-WITH-3-CAVEATS**

1 spec amend mandatory (BB-C1 MED) + 2 follow-up advisory (BB-C2/C3 LOW)；0 ship-stop。

### 重大發現：Bybit V5 path SSOT drift fix verify

- **E1c IMPL 揭露 spec drift fix**：PA dispatch packet §1.2 + BB 5/21 own verdict Part A.2 兩處都列 2025 SDK 舊 path（`/v5/earn/flexible/*` + `/v5/earn/fixed/*` 12 endpoint）。E1c Rust IMPL 採真實 2026 V5 unified path：`/v5/earn/product` + `/v5/earn/place-order` + `/v5/earn/position` + `/v5/earn/apr-history` 4 unique endpoint，stake/redeem 共用 place-order 走 orderType=Stake/Redeem 區分。
- **WebFetch verify tiagosiebler 2026 SDK endpointFunctionList**：4 unique path 對齊 SDK SSOT；BB 5/21 own verdict 自己過時。
- **SSOT 原則生效**：代碼為真，PA packet + BB 5/21 + 字典三方都需向 E1c IMPL 對齊；不該硬改 PA packet 舊表（保 audit trail）但 forward dispatch 不再引用。

### Caveat 1 (MEDIUM mandatory) — earn_governance spec amend

| 章節 | 改 |
|---|---|
| §3.5 NEW | 補真實 V5 unified path 表（4 endpoint constant + stake/redeem orderType 區分） |
| §4.2 condition A line 233-238 | 明示 demo + live 同走 4 unique endpoint |
| §10.2 line 463-465 | **內部矛盾**：§4.5 line 257-267 已採 condition A finalize；line 463 仍寫 `BB v57-C4 verdict PENDING` 須同步改 `✅ DONE 2026-05-21 (a)` |
| §13 amend log | 加 caveat 3 entry 記錄 BB cross-ref 揭露 PA §1.2 stale + E1c IMPL SSOT |

### Caveat 2 (LOW follow-up) — 字典 §3 Earn 章節

- grep 0 hit `/v5/earn` `FlexibleSaving` 全部 0
- BB memory 5/21 verdict 列「§3 NEW Earn API 章節，HIGH」**從 7 升 13** — 仍未 land
- Wave 3b BB1 啟動時用 **E1c IMPL 4 unique endpoint** 為 SSOT；12 SDK function name 為 alias reference；估 4-6 hr 合併 Wave 3b

### Caveat 3 (LOW awareness) — Bybit Dynamic Settlement Frequency System

- 2025-10-30 launch；funding rate 達 ±0.75% 上下限 → auto shift 1h cadence
- 當前 Earn-only scope **0 影響**（Earn 是 staking yield 非 perp funding）
- Sprint 5+ 若加 perp funding reconciliation，UTC 02:00 cron 須重評

### RateLimit + ToS + KYC verify

| 項目 | 狀態 |
|---|---|
| RateLimitGroup::Asset 5 req/s patch `bybit_rest_client.rs:240-258` | ✅ verified |
| 共享 budget Asset (5 req/s) `/v5/earn/` + `/v5/asset/` + `/v5/spot-margin` | ✅ < 0.15 req/s 用量 = 3% 利用率 (97% headroom) |
| OP-1 `Earn` non-withdraw scope 充分覆蓋 5 endpoint read + write | ✅ verified (per 5/21 C5 verdict (a)) |
| OP-3 flexible-only vs Bybit Earn product matrix | ✅ verified (5 endpoint = FlexibleSaving only；Fixed/Easy-Onchain/BYUSDT/Fixed-Saving/DualAssets/Crypto-Loan 全 defer) |
| ToS / KYC / broker rebate / 地理禁區 | ✅ 0 觸碰 |
| funding settlement UTC 02:00 amend caveat 2 | ✅ 對齊 Bybit 8h default cadence |

### Bybit-side overall

- 技術合規度: 98%（spec §3.5 補 endpoint 表後 100%）
- 政策合規度: 72%（M5-1/M5-2 stale + OP-1 < 2026-04-09 key 重發 pending）
- 0 ship-stop
- 30d Bybit V5 changelog 0 breaking change

### 下次啟動需查驗項

1. earn_governance spec §3.5 NEW endpoint 表 + §4.2 / §10.2 / §13 amend 是否 land
2. 字典 §3 Earn 章節是否啟動（Wave 3b BB1，從 7 升 13）
3. OP-1 D+1 OpenClaw key 發行日 5-min operator action 是否完成
4. Sprint 1B Wave C E2 adversarial review 後 5 角色 verdict consolidate
5. Bybit V5 changelog 30d 例行 audit (per BB SOP 每月)
6. M5-1 / M5-2 governance entry + IP whitelist preflight 是否啟動

### Report path

`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-23--earn_governance_cross_ref_bb_review.md`

---

## 2026-05-26 P0-OPS-3 Bybit ToS / geography / KYC tier / Tax reporting audit (Sprint 4 W18-21 prep)

### Trigger

PM 派 P0-OPS-3 per KNOWN_ISSUES.md:531-535 + TODO.md §1.7 line 49 (P0-OPS-1..4 Sprint 4 first Live W18-21 前必 closure)。覆蓋 Bybit 16 restricted jurisdictions + KYC 3 tier + tax reporting CSV + 90d ToS/policy changelog + Earn Flexible 額外條款。

### Verdict: **CONDITIONAL** — 5 operator confirm 阻 Sprint 4 first Live

- Sprint 4 first Live $500: **CONDITIONAL-BLOCKED**（C-1 ~ C-4 必 land）
- Earn Wave C first stake $100-200: **CONDITIONAL-GO**（C-1 + C-2 + C-3 + C-5 必 land；不阻 OP-1 ~ OP-3）
- 技術合規 98% / 政策合規 70%
- 0 ship-stop technical blocker

### 16 restricted jurisdictions verified (2026-05-26)

US / Mainland China / Hong Kong (2025+) / Singapore / Canada / France / Japan (2026 phase-out) / North Korea / Cuba / Iran / Syria / Sudan / Uzbekistan / Crimea / Donetsk+Luhansk / Sevastopol + Dubai (retail derivatives restricted)。UK 2026 re-entry spot+P2P only via Archax (derivatives 仍不開)；India 2026 fully resumed。

### KYC tier coverage

- Standard L1 (Gov ID + face): 1M USDT/day withdraw → Sprint 4 $500 + Earn $100-200 充分
- Advanced L2 (+ utility bill): 2M USDT/day
- Pro L3 (enhanced DD): 30~60M USDT/day
- ✅ OpenClaw scale 無需超 L1

### Tax reporting

- ❌ Bybit 不發 1099-DA / 1099-MISC (HQ Dubai, no US reporting infra)
- ✅ CSV export (Transaction Log / Order History / Account Statement)
- ⚠️ Account Statement **excludes Earn / structured products** → V100 `learning.earn_movement_log` 自主 audit trail mandatory
- ⚠️ EU DAC8 自動 reporting 2026-01-01 生效；CRS jurisdiction 適用 (取決 operator residence)

### 5 operator-must-confirm

| # | Item | 阻 first Live? | 阻 Earn? |
|---|---|---|---|
| C-1 | residence 自證 + 非 16 restricted | ✅ | ✅ |
| C-2 | KYC tier (≥ Standard) 自證 | ✅ | ✅ |
| C-3 | KYC 完成日 ≥ 2026-04-09 (Earn scope key) | ⚠️ | ✅ |
| C-4 | tax authority filing jurisdiction 拍板 | ⚠️ (first Live + 30d) | ❌ |
| C-5 | Earn APR floating + default risk 自承 | ❌ | ⚠️ (OP-3) |

### M5-1 governance entry 18 day 0 進展

BB 5/8 → 5/9 → 5/21 → 5/23 → 5/26 五次 carry-over：`docs/governance_dev/YYYY-MM-DD--bybit_compliance_signoff.md` 仍未建檔。**18 day stale = Sprint 4 W18-21 first Live 真實 ship-stop**。M5-2 已由 2026-05-25 `P1-OP1-IP-WHITELIST-CORRECTION` 選項 (b) 「no IP restriction」closure；BB 0 push back。

### 字典補錄清單（從 13 升 19）

新增 §0.1 ~ §0.6：16 restricted / Japan exit / UK re-entry / Tax CSV / Earn APR risk / KYC 3 tier。估 ~3-4 hr 與 BB1 工作合併。

### 重大發現

1. operator residence **完全 0 governance trace** (CLAUDE.md / CONTEXT.md / README.md / TODO.md / governance_dev/ / adr/ 全 0 hit) — 必須 flag operator question
2. CONTEXT.md line 282 「single human supervisor `cloud@ncyu.me`」是唯一 operator identifier，無 residence / country
3. Hong Kong 2025+ 全 restricted；若 operator HK → 整 Sprint 4 first Live 必 cancel
4. Japan 2026 phase-out + KYC L2 by 2026-01-22 deadline 已過期 — operator 若曾被誤判 Japan → 已 restriction
5. Bybit 用 advanced geolocation；misrepresent residency → terminate account + liquidate positions = OpenClaw integral capital risk

### 下次啟動需查驗項

1. `docs/governance_dev/2026-05-26--bybit_compliance_signoff.md` 是否建檔 + C-1 ~ C-5 5 自證是否 land
2. 字典 §0.1 ~ §0.6 6 新章節 + §3 Earn 章節（含 5/21 13 處 carry-over 共 19 處）是否啟動
3. Earn Wave C OP-1 ~ OP-3 hand action chain 是否觸發（per TODO.md §7 D+2~D+3）
4. Sprint 4 first Live W18-21 預備期前 30d operator tax filing cadence 拍板
5. Japan exit 2026 + UK re-entry 2026 政策更新是否影響 operator (取決 C-1)
6. M5-1 governance entry 18 day → 1 month 升級 risk

### Report path

`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-26--p0-ops-3-bybit-tos-geo-kyc-audit.md`
（同檔複製 `docs/CCAgentWorkSpace/Operator/`，因 5 operator confirm 屬 P0 SHIP-STOP severity）

---

## 2026-05-29 v80 cold audit Wave 1 PkgB pre-deploy spot-check (commit `b93d3210`, HEAD `9b18f348`)

### Verdict: **APPROVE-WITH-CONDITIONS** (6/6 items source-correct vs Bybit V5; 1 P3 doc drift, 0 ship-stop)

PkgB Rust exchange-authority hardening verified READ-ONLY against Bybit V5 official docs + dict v1.3. No live calls.

- **P1-03 cancel-all → Rust authority: PASS.** `order_manager.rs:518 cancel_all_scoped` body = `{category:linear, settleCoin:USDT}` single account-scope call (no per-symbol loop) — matches Bybit V5 cancel-all (settleCoin valid for linear; priority symbol>baseCoin>settleCoin; official doc confirmed). Runs in `loop_handlers.rs:607` async, NOT gated by execution_authority (risk-reducing, must work post-revoke per Stop Phase 1) — correct. Grep: live REST cancel-all GONE (`live_session_routes.py:686`=removed comment, `live_session_endpoints.py:358`=IPC). Only demo `_sweep_orphan_orders` + paper_trading_routes demo + `bybit_rest_client.py:681` helper retained — correct scope.
- **P1-06 trading-stop tick: PASS.** `normalize_trading_stop_price` (instrument_info.rs:766) side-aware: long SL floor / short SL ceil / TP+trailing+active nearest round_price; missing-spec→None→fail-closed skip exchange stop (local StopManager retained, dual-rail). Validates Bybit 10001 "Price invalid" off-tick rejection (cross-endpoint priceFilter applies to trading-stop). trailingStop tick-aligned via round_price — correct (Bybit needs tick alignment even for distance).
- **P1-07 retry: PASS.** `dispatch.rs:646 OPEN_NO_RETRY:[u64;0]` → OPEN single-attempt fail-closed on any timeout/parse/transport/nonzero retCode; CLOSE keeps `CLOSE_RETRY_DELAY_MS` bounded reduce-only retry. Aligns Bybit reality: no order-create idempotency key by default → single-attempt correct; order_link_id is mitigation not retry license (CLAUDE.md §四).
- **P1-08 LiveDemo cred: PASS.** `is_live_slot = slot=="live"` (bybit_rest_client.rs:946) covers Mainnet+LiveDemo → disables env-var fallback. LiveDemo uses `api-demo.bybit.com` REST + `stream-demo.bybit.com` WS but live secret slot provenance enforced. OPENCLAW_ALLOW_MAINNET + empty-cred fail-closed correctly stay keyed on is_mainnet (real-money only).
- **P2-02 amend: PASS.** `order_manager.rs:587` fail-closed Err on cache-miss when any qty/price/trigger/TP/SL present; rounds all price fields. No raw off-tick/off-step.
- **P2-03 rate-limit: PASS.** `wait_if_rate_limited(path)` group-aware (from_path → Order/Position/Account/Market/Asset/Other) + per-group `group_reset_ms[6]` w/ global fallback. Threshold Order/Pos/Acct/Asset=2, Market=10 (vs 20/120 r/s caps) — conservative, 10006 avoidance correct.

### CONDITION (1 P3 doc/comment drift — feeds TW P2-04 batch)
- `bybit_rest_client.rs:222-227` RateLimitGroup enum comments still say "10 req/s" for Order/Position/Account; dict v1.3 (line 291/1243/1255) + runtime correctly = **20 req/s**. Stale comment only (threshold logic correct, not load-bearing). TW: sync enum doc-comment to 20 r/s in P2-04 patch. Non-blocking.

### Bybit V5 alignment
- 30d changelog: 0 breaking change (inherited; PkgB 0 new endpoint).
- cancel-all settleCoin: confirmed Bybit V5 official.
- trading-stop tick: 10001 off-tick rejection confirmed via ccxt/pybit issue corpus.
- 0 ToS / 0 KYC / 0 geo / 0 rate-budget risk (PkgB = authority hardening, no new traffic).

### 下次啟動需查驗項
1. TW P2-04 patch: enum comment 10→20 r/s + PA's pre_check_order/demo-dcp drift items landed
2. P1-03 IPC end-to-end (cancel_all_orders reaches engine) requires operator-gated non-mutating IPC probe on Linux — deferred per PA §Linux empirical
3. Linux cargo test PASS confirmed in commit body (Rust 3584/0) — re-verify on next deploy --rebuild

---

## 2026-05-29 retCode 110017 收斂語意安全審查（PHYS-LOCK zero-position close loop 治本）

### Trigger
PA RCA `2026-05-29--phys_lock_zero_position_close_loop_rca.md` §5 主修需 BB exchange-facing 背書：TRXUSDT 本地殘倉 + Bybit 端已平 → reduce-only close 每 tick 回 110017 → engine 把 110017 當 Structural（no retry、不本地收斂）→ 倉永不刪、~1.4/sec 自持迴圈。修法擬把 110017 Structural→NoOp + 消費端本地 positions_remove。

### Verdict: APPROVE-WITH-MANDATORY-GUARD
**不可「無條件收到 110017 就本地刪倉」。** 方向正確但 110017 在 Bybit V5 非零倉專屬碼，須加 guard。

### 關鍵 FACT
- **110017 ≠ 可靠等價零倉**：官方 + 字典 §4.2 line 1295 三 trigger「(a)無倉 (b)方向反 (c)qty>size」。BB WP-10 自己標「切勿視為 idempotent silent success」。裸刪倉 = 誤刪真倉災難風險。
- **本系統 = one-way mode（4 指紋驗）**：(1) OrderDispatchRequest 無 positionIdx 欄位 (2) order create body 不送 positionIdx (3) `switch_position_mode`（position_manager.rs:356）**0 production caller** (4) demo_state TRXUSDT position_idx=None。→ corner case C-2（hedge positionIdx 不符）結構性不存在。
- **qty=0 全平 form（close_sizing.rs）消除 C-1**：qty=0 無顯式 qty → 不可能因 qty>size 回 110017 → 110017 在 qty=0 form 下可靠等價零倉。
- **現有 NoOp 消費端（dispatch.rs:708-734）只發 LeaseOutcome::Consumed + log，不本地刪倉**。所以「110017→NoOp」單獨改 classifier **無法斷迴圈**；PA 主修「消費端 positions_remove」是新行為，對 110001/110009 也是行為變更，E2 須確認無 regression。
- close side 正確反向：commands.rs:982 `is_long: !is_long`（one-way 下正確）。

### E1 安全收斂條件（一句話）
僅當 `is_close==true` ∧ `reduce_only==true` ∧ qty=0 全平 form ∧（建議）同 symbol 連續 ≥2 次 110017，才本地 positions_remove + pending_close_symbols.remove；one-way 為前提（hedge 啟用須重審）；110017 不可裸放進 `110001|110009` arm，須帶 guard 分支。
最小安全集 = G-1(close) ∧ G-2(reduce_only) ∧ G-4路徑a(qty=0 form)；G-3(one-way 前提守衛) + G-5(連發熔斷防 race) 建議納入。

### live 安全性: 在 guard 齊備下誤刪真倉結構路徑為空
live 真倉送 qty=0 全平不會回 110017（會正常成交）；只有 exchange 確已無倉（手動/強平/liquidation）才回 → 收斂=對齊真相正確。不違 fail-closed 開倉語意（110017→NoOp 仍 no-retry）。

### rate-limit/ToS: 0 風險
1.4 req/s = 7% Order group 20 r/s cap；非 wash/spoof/multi-account；同 BUSDT funding_arb 110017 reject loop 性質（memory line 200-202 正常拒單非 ToS 違規）。真實成本 = demo edge 污染 + 27k log 噪音（治理 P1，非合規）。

### follow-up
1. 字典 §4.2 110017 row 修法 land 後補「one-way+qty=0 form 可安全收斂」新語意（現只警告不可 silent success，會與新 code drift）
2. ★ **110009 doc 版本歧義**：官方 error 表有「110009=PositionNotFound」vs「110009=stop orders 超上限」兩版本；本系統 dispatch 採 PositionNotFound 落 NoOp。若 110009 真是 stop 上限 → NoOp 會靜默吞 SL/TP 設置失敗（既有潛在風險，本修法不引入但應順查）。
3. G-3 hedge-mode 前提：one-way 是收斂安全前提，未來啟 hedge → 收斂路徑 mandatory re-review。

### Report path
`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-29--retcode_110017_convergence_semantics.md`

---

## 2026-05-29 D2 reconcile Ghost = exchange-truth 信任邊界審查（Track C P2-110017-D2-RECONCILE）

### Verdict: **RETURN**（1 CRITICAL ship-stop）

worktree `wt-c-d2` / branch `fix/retcode-110017-d2-reconcile`（working-tree only，無 commit；prompt 引用的 spec 檔在 worktree 不存在）。

### ★ CRITICAL 教訓（durable）：D2 與 D1 的安全地基根本不同

- **D1（110017 reactive）安全來源** = 「qty=0 全平 form 撞 110017 = 交易所**主動針對該 symbol** 自證倉已不在」，不依賴列舉完整性。
- **D2（reconciler proactive）安全來源** = 「該 symbol **不在** 一次 `/v5/position/list` fetch 回應」→ 把「列舉完整性」變成 silent 安全前提。
- **破口**：`get_positions(Linear, None)`（position_manager.rs:158）單次 `get_checked` + `settleCoin=USDT`，**無 cursor 迴圈、無顯式 limit**；`parse_position_list`（:545）**只讀 result.list，丟棄 nextPageCursor**。
- **Bybit V5 官方 [FACT]**：`/v5/position/list` default `limit=20`、max 200、分頁 nextPageCursor；`symbol=null+settleCoin` 只回 size>0 且可被分頁截斷。
- **scanner_config.toml `[universe] max_symbols=40`** → 持倉 > 20 時 page 1 截斷 → 第 21+ 真倉不在 current → 判 Ghost → 收斂刪真倉。
- **streak/fail-closed 擋不住**：截斷是**穩態**（每輪截同一批尾端 symbol），非抖動 → streak 必滿；fail-closed 只在 REST `Err` arm，截斷回 `Ok(20條)` 走 happy path。
- **live 真錢生效**：reconciler 對 Mainnet|LiveDemo 也 spawn（tasks.rs:860-864），D2 env-agnostic 共用碼 → 結構性誤刪 live 真倉 + 失本地止損（違 Root Principle 5/9）。

### 各裁決點

1. **Ghost=真無倉**：size==0 本身可靠 ✅；但「不在回應 ≠ size==0」分頁陷阱**成立**=CRITICAL（1b）。one-way/hedge 當前安全，G-3 守衛已對齊 D1 ✅。
2. **2-cycle streak**：≥2 正確 + 維持 mandatory，不需加碼；防 C-3 暫態綽綽有餘（perp position 結算 <1s）。但**澄清能力邊界**：streak 防抖動不防穩態，不可當 (1b) 補償。
3. **live 誤刪防護**：暫態足夠 ✅；穩態分頁截斷**不足** ❌。
4. **rate-limit**：process_ghosts 復用同一 fetch + IPC 收斂 = **0 額外 REST** ✅。

### 修復條件（RETURN → APPROVE 最小集）

- MUST 二擇一：**修法 A** 收斂前 `get_positions(Linear, Some(symbol))` 單 symbol 點查確認 size==0（不受 limit=20 截斷）；**修法 B（BB 偏好）** `get_positions` 加 nextPageCursor 分頁 + 顯式 limit=200（同時修 reconciler Orphan/baseline 完整性盲區，SSOT 更乾淨）。
- SHOULD：補「baseline 有 / current 截斷頁缺 → 不收斂」test（當前 6 新 test 全在 process_ghosts 下游已分類 drifts，**0 覆蓋分頁截斷上游**）；spec S-2 改「**完整列舉**確認 size==0」。
- 已背書無需改：streak≥2 mandatory / fail-closed-on-Err / 走 converge_exchange_zero_close 不走 ipc_close_symbol / mirror 無方向不收斂 / G-3 hedge re-review 註解 / 0 rate-limit。

### 下次啟動需查驗項

1. D2 fetch 完整性修法（A 或 B）是否 land；修法 B 是否同步修 `get_positions(None)` 全 caller（Orphan/baseline）
2. 分頁截斷 test 是否補（baseline 有 / current 截斷缺 → 不誤刪）
3. 字典 §get_positions（line 527-542）是否補「default limit=20 / nextPageCursor / 單頁不翻頁、caller 不可假設已列舉全部」
4. D2 spec 落檔後 S-2 是否改「完整列舉確認 size==0」
5. 若 live universe 放開 > 20 symbol，D2 修法必須先 land（不可靠「現在持倉少」偶然安全 ship）

### Report path

`srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-29--d2_reconcile_ghost_exchange_truth.md`（CRITICAL 已複製 Operator/）

---

## 2026-05-29 Round 2 re-confirm — D2 CRITICAL 分頁截斷誤刪真倉（worktree `wt-c-d2` branch `fix/retcode-110017-d2-reconcile`）

### Verdict: **APPROVE**（round 1 的 1 CRITICAL 結構性關閉）

E1 round 2 採我的修法 A（S-6 單 symbol 點查 gate），不採修法 B（get_positions 分頁）。CRITICAL 結構性消除確認。

### CRITICAL 關閉根基驗證（3 點全 ✓）

1. **單 symbol query 不受 limit=20 截斷 ✓**：`position_manager.rs:158-178` `get_positions(Linear, Some(symbol))` 在 `Some(sym)` arm 真實 `params.push(("symbol", sym))`（line 164-165）→ Bybit V5 `/v5/position/list` 帶 symbol filter 只回該 symbol 單一 entry，不觸 default limit=20 + nextPageCursor 分頁（單一 symbol one-way 永遠 ≤1 entry，無「第 21+ 個被截斷」可能）。修法 A 安全根基成立。
2. **三分支正確 ✓**：`ghost_point_query`（mod.rs:101-123）映射用 `position_info_to_view`（mod.rs:224-227 `size <= 0.0 || side == "None"` → None）。`positions.iter().any(|p| position_info_to_view(p).is_some())` = 任一非空倉 entry（size>0 任一 side）→ `StillHasPosition`（不收斂）；全空/空列表 → `ConfirmedZero`（收斂）；`Err`（timeout/nonzero retCode）→ `QueryFailed`（fail-closed 不收斂，CLAUDE §四）。涵蓋所有「非空倉」情況。
3. **CRITICAL 結構性消除 ✓**：分頁截斷假 Ghost（真倉在 page 2+）→ S-6 點查命中該 symbol 回 size>0 → `StillHasPosition` → `kept.push` 保留 + log `pagination_false_ghost`（mod.rs:231-241），不發 `ConvergeExchangeZero`。streak（C-3 暫態）擋不住穩態截斷，由點查 gate 擋（comment S-6 明寫「streak 對每輪都截斷同一 symbol 零作用，必須由點查擋」）。真錢誤刪路徑關閉。

### 防護疊加正確（S-1..S-6 全 AND）

S-1 mirror 有方向 → S-5 streak≥2（C-3 race）→ S-6 點查 ConfirmedZero（分頁截斷）三層全滿足才 `dispatch_ghost_converge`。S-6 疊在 S-1..S-5 之上（非取代）。`dispatch_ghost_converge` 走 `ConvergeExchangeZero`（本地收斂）不走 `CloseSymbol`/reduce-only（反 110017 重入迴圈守衛，orphan_handler.rs:295-334）。

### Test 覆蓋（對抗驗證 load-bearing）

新增 4 個 S-6 test：`ghost_pagination_truncation_false_ghost_not_converged`（★ BB CRITICAL 直接 regression，StillHasPosition → 不收斂 + 無命令）/ `ghost_point_query_confirmed_zero_converges` / `ghost_point_query_failed_fail_closed_not_converged` / `ghost_point_query_gate_is_load_bearing`（對比 ConfirmedZero 誤刪 vs StillHasPosition 不收斂，鎖「gate 必須能改變收斂結果」不變量）。注入 closure（`F: Fn(String) -> Fut`）非直接持 PositionManager，可單測 mock 三分支。lib 3618/0（E1 報）。

### 修法 B 降 follow-up — 同意 ✓

採 A 後 D2 收斂路徑本身已安全（每個 Ghost 候選收斂前必過點查）。修法 B（get_positions(None) 分頁 + 字典 §get_positions limit=20/nextPageCursor 警告）降為治本既有 Orphan/baseline 盲區的**非阻** follow-up `P2-RECONCILER-GET-POSITIONS-PAGINATION`（PM 登記）。理由：`get_positions(None)` 截斷仍會讓 Orphan 偵測（exchange 有/baseline 無）漏報 page 2+ 的 orphan，及 baseline 完整性盲區——但這些不會誤刪真倉（漏報 ≠ 誤刪），故非 ship-stop。字典補錄（§get_positions line 527-542 缺 limit/分頁語意）併入該 follow-up。

### 下次啟動需查驗項

1. `fix/retcode-110017-d2-reconcile` merge 後 lib 3618/0 是否 Linux 復現（Mac sign-off ≠ runtime）
2. `P2-RECONCILER-GET-POSITIONS-PAGINATION` follow-up 是否 PM 登記（修法 B + 字典補錄）
3. 若 live universe 放開 > 20 symbol，D2 已安全（點查 gate 擋穩態截斷），但 Orphan 偵測盲區需修法 B 才完整
4. ConvergeExchangeZero handler 端 `converge_exchange_zero_close` is_exchange() 守衛（paper noop）維持

---

## 2026-05-29 C4 fail-safe wire · set_trading_stop 交易所信任邊界（worktree `wt-c4` branch `fix/packet-c-c4-wire`）

### Verdict: **APPROVE-WITH-GUARD**（交易所面安全；1 非阻 G-1 字典補錄）

E2 APPROVE-WITH-CONDITIONS 把 set_trading_stop 交易所面深審交 BB。6 項全過。

### 6 裁決點

1. **既有路徑非新 client ✓**：`InBandStopSync::sync_stop`（risk.rs:660-675）只 `stop_tx.send(StopRequest)`，復用既有 `stop_request_tx`（pipeline_helpers.rs:629-646）→ bootstrap.rs:752 consumer → position_manager.rs:237 `set_trading_stop`。與既有開倉 SL 路徑（step_4_5_dispatch.rs:1298）共用同一 channel/consumer/`set_trading_stop`。StopRequest struct/consumer/set_trading_stop **C4 全未改**。owner pipeline 不持 PositionManager → 故走 channel 不新構 client（Root Principle 1）。0 第二 client。
2. **SL 語義/方向/誤平 ✓（含 G-1）**：(a) lock-profit（risk_gov.rs:327，buffer 0.5）Buy `new_sl=entry+atr×0.5`（entry **上方**）/ Sell `entry-atr×0.5`（下方）——這是**鎖利**，方向故意相反於既有開倉 SL（Buy `entry×(1-pct)` 下方）；設計正確非 bug。(b) **誤平結構路徑為空**：Bybit V5 long SL 須 < lastPrice，否則**拒單**（34040/10001 "expect Rising but trigger<=current"）**非立即市價平倉**；未獲利倉 lock-profit SL 在 market 上方 → Bybit fail 掉 → consumer 回 Err fail-closed → 倉不誤平（代價僅鎖利靜默設不上，可接受，雙軌兜底）。(c) positionIdx=Some(0) one-way 正確；slTriggerBy=LastPrice；tpslMode 未送=Full 整倉，繼承既有；normalize tick floor/ceil 繼承 P1-06。
   - ★ **G-1 advisory（非阻）**：lock-profit 計算只用 entry+current_sl，**不讀 current market price** → 無本地「SL 錯側即跳過」預檢，靠 Bybit 拒單兜底（安全）。字典 §set_trading_stop（line 559+）應補方向約束 + 「未獲利倉 lock-profit SL 被拒屬預期 fail-closed，勿誤加 retry」。
3. **retCode fail-closed ✓**：C4 **0 新 retry**。consumer（bootstrap.rs:778-794）Err→warn+本地 stop，不重試不假成功；post_checked nonzero/timeout→Err（CLAUDE §四）；sync_stop fire-and-forget，channel 關回 Transport Err 不 rollback transition（survival）。
4. **paper 不誤觸 ✓（三層）**：watcher loop 只迭代 [demo,live] 不含 paper（tasks.rs:932）；sync_stop `engine_mode=="paper"→Ok(())` 不 send（risk.rs:665）；paper 無 exchange client log-only。test e2e_c4_paper_skips_exchange_sync 斷言 0 StopRequest。
5. **rate-limit/ToS 0 風險 ✓**：Position group 20 r/s（字典 1254）；觸發極罕見（3路fail+1h）+ incident-trigger 未接 → 當前實際頻率 0；收緊自己倉 SL 合規。
6. **半 wire → deploy 交易所面 0 影響 ✓ [FACT]**：斷點 = 武裝 timer 唯一入口 `observe_dispatch(AllFail)` 的 outcome 來源 `outcome_rx`（tasks.rs:923）的 `outcome_tx` 註冊進 `FAILSAFE_FEED_SENDERS` OnceLock **供 Sprint 3 取用，C4 0 producer**。故 outcome_rx 永空 → timer_armed_at_ms=None → timer_expired（mod.rs:345 None=>false）→ timer_expired_and_claim 永 false → escalate 永不發 → set_trading_stop 永不被 C4 呼。**deploy 安全**；watcher task 30s 空轉 select! 0 副作用。

### 機制側已 live（非交易所面）
SM-04 transition / lock-profit 計算 / 雙軌 sync 通道 / paper noop / claim-before-await idempotent 全 land + e2e test（demo escalate / paper skip / arm-then-claim-once）。Sprint 3 接 outcome producer 即全功能 live。

### 下次啟動查驗項
1. G-1 字典 §set_trading_stop 補方向約束（併 BB1 backlog，非阻）
2. ★ **Sprint 3 incident-trigger（P2-INCIDENT-POLICY-DISPATCH-TRIGGER）接上時 BB mandatory re-review**：set_trading_stop 真實觸發；驗 incident 頻率 vs Position rate budget、market 錯側 SL 被拒比例 vs 鎖利覆蓋率、live slot respawn cmd_tx 不 stale（LIVE-AUTH-WATCHER 教訓）
3. live 首次 escalate 前確認 one-way 前提（hedge 啟用復活 positionIdx corner case 須重審）

### Report path
`srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-29--c4_set_trading_stop_trust.md`（worktree wt-c4 內）

---


<!-- ROLE_MEMORY_COMPACTION_V1
role: BB
payload_sha256: sha256:4f4d054236a2f17ce37b280f4b40a1c736a8575099dfeefb9109d7cd917533c3
payload_bytes: 59930
-->
# BB (Bybit Broker Compatibility Auditor) — Memory

> 本檔=長期教訓+近期記錄；超 300 行由 R4 巡檢標記、PM 派工壓實，舊條目原文遷 memory-archive.md（append-only）；agent 完成序列照常追加於檔尾。

## 長期教訓（2026-06-10 壓實蒸餾；原條目全文見 memory-archive.md）

- 角色鐵則：BB=Bybit V5 合規審計員（外部視角），READ-ONLY 靜態審計不打交易 API（查證限官方 doc WebFetch / 公開 market curl）；代碼為 SSOT，字典 `docs/references/2026-04-04--bybit_api_reference.md` 配合；每個 verdict 必三方對齊（官方 doc ↔ 字典 ↔ code）。
- Empirical 優先：字典/plan/status 與 BB 自己的舊 verdict 都會 stale（v57「writer BLOCKED」被 PG 實查 31,473 rows 推翻；5/21 Earn path 被 E1c IMPL 證舊）→ 下 verdict 前做 PG/curl/WebFetch 實證，不靠記憶或舊報告。
- Rate limit 不變事實：per-UID Order/Position/Account=20 r/s、Market=120、Asset=5（`/v5/earn/` 與 `/v5/asset/` 共用）、Other=10；per-IP 600 req/5s 違反→403+10min cooldown；WS conn 500/5min；OpenClaw baseline ~0.7 req/s headroom 巨大，REST polling 提案先推 WS-first（tickers topic 已 broadcast fundingRate/openInterest）。
- retCode 鐵則：timeout/非零 retCode 一律 fail-closed 不重試；open 單次（OPEN_NO_RETRY）；NoOp/冪等 upgrade ≠ retry license；duplicate 類（110072、10001+"duplicate"）open fail-closed / close 冪等成功。
- 110017 非零倉專屬碼（三 trigger：無倉/方向反/qty>size）；僅 is_close ∧ reduce_only ∧ qty=0 全平 form ∧ one-way 前提下可本地收斂刪倉；無 guard 裸刪=誤刪真倉災難。
- one-way mode 是 110017 收斂、D2 reconcile、set_trading_stop positionIdx 等多項安全裁決的結構前提；hedge 啟用時全部 mandatory re-review（G-3）。
- 列舉完整性陷阱：`/v5/position/list` default limit=20+nextPageCursor，「不在回應 ≠ 無倉」；streak 防抖動不防穩態截斷；單 symbol 點查不受截斷=安全 gate；proactive reconciler 禁把列舉完整性當 silent 前提。
- 分頁範式：funding/history=time-window 無 cursor（只傳 startTime 會 error，endTime 回溯，limit max/default=200）；open-interest=cursor+window（default limit=50）；統一 shrinking-end 回溯+三閘終止（空頁/游標不進/MAX_PAGES）。
- fake-zero 地雷：`parse_str_f64 .unwrap_or(0.0)`+NOT NULL 欄位 → strict-parse 必用「JSON 欄位存在且 parse 成功」判定而非 >0（funding 合法可 0/負）；timestamp string-ms parse-fail 必 reject 不落 epoch。
- funding cap SSOT=instruments-info `upperFundingRate`/`lowerFundingRate`/`fundingInterval`（per-symbol 0.5~1.0%/8h；interval 可 4h 非全 8h）；IR baseline +0.01%/8h 是 floor 非 cap；禁從 history 樣本窗 max 反推 cap（樣本落 regime 內必誤判）。
- Demo 環境差異：不支援 execution.fast+dcp topic / spot lending / PostOnly silent degradation；demo reject loop=正常拒單非 ToS 違規，屬 retry budget 治理；`BybitEnvironment` 分支是標準處理軸。
- 政策合規長期短板：技術 ~95-98% vs 政策 ~70%；ToS/KYC/地理 governance entry（M5-1）多月 stale=mainnet 解鎖真 ship-stop；16 restricted jurisdictions、KYC Standard L1 足夠 OpenClaw scale、Bybit 不發 1099（CSV 自理且 Account Statement 不含 Earn）、Earn scope 需 2026-04-09 後 key。
- kill/close 順序鐵則：cancel-all → close-position → revoke，per-symbol 0.3s safety margin；DCP 是 backup 非 primary。
- trading-stop/SL：tick 對齊 side-aware（long SL floor / short SL ceil），missing spec→fail-closed skip；Bybit 拒錯側 SL 是拒單非市價平倉，可作 lock-profit fail-closed 兜底，勿加 retry。
- BB 工作慣例：每 verdict 例行查 30d Bybit V5 changelog（迄今 0 breaking change）；report 落 `workspace/reports/`+commit；CRITICAL/operator-action 級同檔複製 `Operator/`；字典補錄走 BB1 backlog 累積清單不即興散修。
- Mac sign-off ≠ runtime：Linux cargo test/--rebuild/PG 復現必列「下次啟動查驗項」；LIVE-GUARD 三閘+五 gate live boundary 永不放寬；LiveDemo 用 live slot 憑證 provenance（is_live_slot 禁 env fallback）但 endpoint=api-demo。

## 近期記錄

## 2026-05-31 funding_short_v2 結構性 NO-GO 斷言 — BB 反證 REJECTED audit cap 詮釋

### Trigger

PM 對抗性質疑 `srv/docs/audits/2026-05-31--funding_short_v2_structural_infeasibility.md` §2.4 的核心斷言：「Bybit linear perp 正側 funding **結構性封頂 +0.01%/8h (+10.9% APR)**，連 memecoin 亦然，0 筆破 30% gate」。PM 懷疑這是低-premium regime 觀察，非結構性 cap。BB 用官方文件 + 實際 curl 查證。

### Verdict: **audit §2.4 結構性封頂斷言 ERRONEOUS（過度詮釋）**。正側 funding **NOT** 鎖在 <30% APR。真實 per-symbol cap 遠超 30%，bull regime 下歷史頻繁破 30%。

### 決定性證據（官方文件 + 實證 curl，非記憶）

1. **官方 funding 公式**（Bybit Help Center, via WebSearch）：
   `F = clamp[ P + clamp(I − P, +0.05%, −0.05%), upperFundingRate, lowerFundingRate ]`
   - I (interest rate) = 0.03%/day = **0.01%/8h**（BTCUSD 例）。premium P≈0 時 `F = clamp(0.01%, ±0.05%) = +0.01%`。
   - ★ **audit 觀察到的「4 symbol 正側 max 全 = 精確 +0.0001」就是 IR baseline，NOT cap**。低-premium regime 下 funding 落在 IR=+0.01% 是公式必然，不是上限。
   - cap 公式係數 0.75（記憶 ±0.75% 方向對但非 cap 本身）：`upper = min((IMR−MMR)×0.75, MMR)`，high-divergence 時 0.75 可調 0.5~1.0。

2. **`/v5/market/instruments-info` 暴露 per-symbol cap 欄位**（audit 完全沒查）：
   - `upperFundingRate` = "Upper limit of funding date"（= 正側 cap，per-symbol 真實欄位）
   - `lowerFundingRate` = 負側 cap；`fundingInterval` = 結算間隔（分鐘）
   - 實 curl api.bybit.com（2026-05-31）：

   | Symbol | upperFundingRate | = APR | fundingInterval |
   |--------|------------------|-------|-----------------|
   | BTCUSDT | +0.005 (0.5%/8h) | **+547.5% APR** | 480 (8h) |
   | SOLUSDT | +0.005 | **+547.5%** | 480 |
   | DOGEUSDT | +0.0058 | **+635%** | 480 |
   | 1000PEPEUSDT | +0.01 | **+1095%** | 480 |
   | WIFUSDT | +0.01 | **+2190%** | 240 (4h!) |

   → 真實正側 cap 是 audit 宣稱「10.9% 封頂」的 **50×~200×**。

3. **歷史反證**（實 curl funding/history，2024 bull 窗）：
   - BTCUSDT 2024-03（突破前高）：n=43 **全部 > +0.0001**，max +0.001128 = **123.5% APR**
   - BTCUSDT 2024-11（川普當選 bull）：max +0.001086 = 118.9% APR，**32/106 筆 > +30% APR**
   - DOGEUSDT 2024-11：max +0.001146 = 125.5% APR，**53/106 破 30%**
   - 1000PEPEUSDT 2024-11：max +0.001228 = **134.5% APR，73/106 (69%) 破 30%**
   → audit「0 筆破 30%」純因 ~66 天樣本落在低-premium regime；換 bull 窗 alt 半數以上時間破門檻。

### audit 其他錯誤

- WIFUSDT fundingInterval=240（4h，一天 6 次結算非 3 次）；audit 用統一 8h×3×365 算 WIF -85% APR 倍率錯（應 ×6×365）。
- audit §2.3「三源一致 max +1.0 bps」只證明**我方 pipeline 無 clamp 且當前 regime 確實低**（這部分 BB 認同，數據忠實），但被誤推成「結構性 cap」。pipeline 忠實 ≠ 結構封頂。

### 對 funding_short_v2 NO-GO 結論的影響

- audit 的 NO-GO **結論可能仍成立，但理由錯**：不是「物理上永遠無法 fire」（bull regime 可破 30%），而是「需賭 bull/high-premium regime，低-premium 期 0 機會 + break-even 160% APR 門檻過高（160% < BTC cap 547% 但 > 多數實際 funding）」。這是 **regime-dependent 低頻策略**，非「數學上永遠不可能」。正確 reframe 應交 QC：策略入場頻率取決於 bull regime 出現頻率 + 160% break-even 在歷史 bull 窗的實際命中率（2024-11 BTC max 118.9% < 160% break-even → 即使該 bull 窗 break-even 仍未過，但 30% 入場 gate 過了 32 次；門檻間 30%~160% 的 gap 是真問題，但屬 QC 成本/門檻設計，非 Bybit 結構封頂）。

### 下次啟動需查驗項

1. audit `2026-05-31--funding_short_v2_structural_infeasibility.md` §2.4 是否更正「結構性封頂 10.9%」措辭（建議標 erratum：cap 是 per-symbol upperFundingRate 0.5%~1.0%/8h，非 +0.01%）。
2. `quant-strategy-design` checklist 建議改為「查 `instruments-info.upperFundingRate` per-symbol cap」而非靠 funding/history 樣本窗 max 推斷 cap（樣本窗會落在 regime 內，必誤判）。
3. 字典手冊 §1 funding 章節是否補 `upperFundingRate`/`lowerFundingRate`/`fundingInterval` 三欄位 + 完整 clamp 公式（含 IR baseline = +0.01% 的 floor 語意，防後續 agent 再犯同樣 cap 誤判）。

---

## 2026-06-02 funding + OI history backfill writer — Bybit endpoint spec for E1 (AEG-S1 V125 fill)

### Trigger
PM 派 BB spec funding-rate + open-interest history backfill writer 的 Bybit 端點語義（QC 多日持倉策略線 P0 基礎，複用已部署 daily_kline_backfill 模式 commit 0f19c861 回填到 V125 research.alpha_funding_rates_history + research.alpha_open_interest_history，目前空）。READ-ONLY，不寫碼。

### 三方核實（Bybit 官方 WebFetch + dict + code）
- **funding/history**：官方確認 = **time-window 分頁（NO cursor）**，limit max=200/default=200，「**只傳 startTime 會 error**；只傳 endTime 回 200 筆 up-till-endTime」。code `get_funding_history(category,symbol,start,end,limit)` 已送 startTime/endTime/limit（mod.rs:254）。8h 結算 → 18mo ≈ 1644 筆/symbol → ⌈1644/200⌉ = **9 頁/symbol** → 20 symbol = **~180 req** 一次性。Market group 120 req/s，sequential 0 burst。
- **open-interest**：官方確認 = **同時有 cursor（nextPageCursor）+ startTime/endTime window**，limit max=200/**default=50**，lookback = symbol launch time。**但 code `get_open_interest(category,symbol,interval,limit)` 只送 category/symbol/intervalTime/limit，NOT start/end/cursor**（mod.rs:184-219）→ dict line 141 列 start/end 是 **drift（client 簽名無此參數）**。OI backfill 需 **E1 擴 client**（加 startTime/endTime/cursor）才能回填歷史窗（與 funding 不同：funding client 已 ready，OI client 不 ready）。
- **intervalTime 建議 = 1h**（多日策略成本模型）：18mo×1h = ~13140 筆/symbol → ⌈13140/200⌉=66 頁/symbol → 20 sym = **~1320 req**；1d = 547 筆/sym = 3 頁/sym = 60 req 但顆粒太粗（成本模型/listing fade 需 intraday OI 變動）。1h 是量/顆粒平衡點。

### 關鍵 BB 發現（spec 交付重點）
1. **【CRITICAL for E1】fake-zero 地雷同 kline**：`get_funding_history` 用 `parse_str_f64(item,"fundingRate")`（parsers.rs:24-28 `.unwrap_or(0.0)`）；`get_open_interest` 用 `parse_str_f64(item,"openInterest")`。V125 C-3 funding_rate/open_interest 都是 NOT NULL；**E1 必複刻 daily_kline strict-parse 範式**：parse-fail → reject row（不寫 0.0），coverage 降 partial/failed。**funding rate 合法可為 0.0/負**（與 OHLC 恆>0 不同）→ strict 判定不能用「>0」，要用「**原始 JSON 欄位存在且 parse 成功**」（區分「真 0.0 funding」vs「缺值 default 0.0」），須在 parser 層分辨 None vs Some(0.0)，不可沿用 kline 的 >0 斷言。OI 同理（OI 可為極小但通常>0；仍以「欄位存在且 parse 成功」為準，非數值門檻）。
2. **funding 分頁方向**：官方「只傳 startTime error」→ E1 分頁必走 **endTime 向後回溯**（cursor_end = 上頁最早 fundingRateTimestamp − 1），與 daily_kline paginate_daily_klines 的 shrinking-end 範式一致；終止三閘（空頁/游標不進/MAX_PAGES）照抄。
3. **OI 分頁有 cursor**：與 funding 不同，OI 可用 nextPageCursor（更穩）或 endTime-window；建議 E1 用 **endTime-window 回溯**（與 funding/kline 統一範式，避免兩套分頁碼）+ cursor 作終止輔助。V125 alpha_open_interest_history 有 cursor_lineage 欄可記。
4. **timestamp 都是 string ms**：funding fundingRateTimestamp / OI timestamp 都是字串毫秒，E1 須 parse → TIMESTAMPTZ（funding_ts / ts），parse-fail reject（不落 1970 epoch，抄 writer.rs utc_from_ms None 範式）。
5. **【cap 紀律】此 backfill 回填已實現 funding history（成本估計）≠ funding cap**。cap SSOT = instruments-info `upperFundingRate`/`lowerFundingRate`/`fundingInterval`（dict §167-196 已記，funding_short_v2 教訓）。**E1 此任務不碰 cap**，禁從 history max 反推。已實現 funding 是成本輸入，cap 是另一個 endpoint（get_instruments_info，目前未拉 cap 欄）。
6. **signed-GET-via-demo**：funding/OI 走 get_checked（HMAC signed GET，demo slot），非 no-auth public（與 daily_kline 同；demo 空憑證 request-time fail-closed，非建構期）。Market group 公共端點但 client 統一簽名。
7. **V125 schema 映射**：
   - funding → alpha_funding_rates_history：funding_rate（DOUBLE NOT NULL，C-3）/ funding_ts（TIMESTAMPTZ from fundingRateTimestamp）/ category='linear' / symbol / source_endpoint='GET /v5/market/funding/history' / funding_interval_minutes（可從 instruments-info fundingInterval 取，或留 NULL；**非 cap**）/ run_id+provenance。PK (category,symbol,funding_ts,run_id)。
   - OI → alpha_open_interest_history：open_interest（DOUBLE NOT NULL，C-3）/ ts（TIMESTAMPTZ from timestamp）/ interval_time TEXT（'1h'）/ category / symbol / source_endpoint='GET /v5/market/open-interest' / cursor_lineage（可記 nextPageCursor）/ run_id。PK (category,symbol,interval_time,ts,run_id)。
8. **rate/ToS**：read-only market data，0 KYC/地理/wash/broker-rebate 風險；180（funding）+1320（OI 1h）req 一次性遠 < Market 120 req/s 持續 cap；sequential per-symbol 0 burst；退避走既有 wait_if_rate_limited（Market threshold=10）。ToS 合規退避重試已由 client 層 fail-closed（retCode!=0 不重試）。

### 字典更新需求（drift）
- **dict line 141 OI start/end 標 client-not-wired**：dict 列 `start/end` 為 get_open_interest input，但 code 簽名無此參。E1 擴 client 加 start/end/cursor 後，同 commit 更新 dict §132-146（標 client 已送 startTime/endTime/cursor + nextPageCursor 分頁 + default limit=50/max=200 + lookback=symbol launch）。**此為 BB 交付的 dict cleanup debt，E1 IMPL 時連帶修**。
- funding §150-163 基本準確；補 limit default=200 + 「只傳 startTime error」+ time-window（no cursor）分頁註。
- 兩者皆「引入新端點用法」（backfill 歷史回溯分頁），E1 IMPL 後須更新 bybit_api_reference.md。

### Verdict: SPEC DELIVERED — funding client ready / OI client 需擴 start+end+cursor / 兩者 fake-zero 須 strict-parse（funding/OI 用「欄位存在且 parse 成功」非 >0）/ cap 不碰。

### 下次啟動需查驗項
1. E1 OI backfill 是否擴了 get_open_interest client 簽名（加 startTime/endTime/cursor）+ 同 commit 更新 dict line 141
2. E1 funding/OI strict-parser 是否用「JSON 欄位存在且 parse 成功」判定（非 kline >0），守住「真 0.0/負 funding」vs「缺值 default 0.0」區分
3. timestamp string→TIMESTAMPTZ parse-fail 是否 reject（不落 epoch）
4. backfill 是否誤碰 funding cap（應只回已實現 history）
5. dict §132-146 OI + §150-163 funding 分頁/limit 註是否同 IMPL commit 更新

---

## 2026-06-07 P2 #6 follow-up — 10001+"duplicate" close-idempotent narrow（接 2026-06-06 110072 裁決）

### Trigger
PM 派 BB 確認 P2 #6 follow-up 交易所側語意：把 `classify_business_retcode` 的 `10001+"duplicate"` 由**無條件 NoOp** 改為 **Structural**，由 consumption 層 `close_dup_is_idempotent_success`（擴為認 110072 OR 10001+duplicate）只 upgrade close path 成冪等成功。即與 110072 完全對齊（open+dup→fail-closed；close+dup→冪等成功）。READ-ONLY。代碼已落（dispatch.rs comment 標 2026-06-07 follow-up），BB 對交易所側語意背書。

### Verdict: **APPROVE**（0 ship-stop；1 字典補錄 LOW 非阻）

代碼已正確 IMPL 且測試完整。三方對齊（Bybit 官方 error doc ↔ dict ↔ code）後 BB 從交易所立場確認方向正確、安全。

### 決定性官方證據（Bybit error doc WebFetch 2026-06-07）
- **110072 = "OrderLinkedID is duplicate"** 是 orderLinkId 重複的**專屬權威碼**。
- **10001 = "Request parameter error"** 泛 InvalidParam。實際 retMsg 變體（github/ccxt corpus）：`"Request parameter error"` / `"order link id is longer than 45"` / `"position idx not match position mode"` / `"invalid order_link_id format"` / `"qty must be > 0"`——**全部不含 "duplicate" 子串**。
- 所有含 "duplicate" 的 Bybit 碼皆**獨立 retCode 非 10001**：110030 "Duplicate orderId" / 110072 "OrderLinkedID is duplicate" / 170141 "Duplicate clientOrderId" / 20006 "reqId is duplicated" / 176021 "Repeated borrowing requests" / 148039 "Duplicate collateral assets" / **10014 "Request is duplicate"**。

### substring 誤判風險裁決（任務核心問題）：**可接受，誤吞面為空**
- 唯一進入 substring 比對的分支是 `ret_code==10001`（close_dup_is_idempotent_success line 412）。官方 10001 的**所有已知 retMsg 變體都不含 "duplicate"** → 不存在「10001+'duplicate' 但語意非 orderLinkId 重複」的官方情境。
- **10014 "Request is duplicate"**（唯一 substring 同形誤判候選）**不會被誤觸**：helper 只 match 110072 與 10001（line 409-412），10014 落 `_ => false`；classify 層 10014 亦落 `_ => Structural`（無 10014 arm）。ret_code gate 先於 substring → 10014 永不進 substring 比對。
- 即使極端：未來 Bybit 在 10001 retMsg 夾帶非-orderLinkId 的 "duplicate" 文字（如 "duplicate parameter"），誤吞**僅限 is_close==true** 場景（open 永遠 fail-closed），且後果是「把一個本該 fail 的 close 當冪等成功」→ 下一 tick close 決策若倉仍在會重發新 id 自然重試/或撞 110017 自癒（與 110072 同自癒機制）。close 側誤吞的 blast radius 遠小於 open（open 誤吞=幻倉，已被 is_close guard 結構性排除）。風險可接受。

### 4 裁決點
1. **open fail-closed 正確**：open+10001-dup（is_close=false）→ helper false → Structural else 分支 → `req.is_primary` → `DispatchFailed{terminal="Rejected"}` + `LeaseOutcome::Failed`（dispatch.rs:972-1006），與 open+110072 同路徑。open 單次無重試（OPEN_NO_RETRY），撞 dup = id 撞歷史 = 開倉未成功，絕不可當成功。正確。
2. **close idempotent-success 正確**：close+10001-dup（is_close=true）→ helper true → 只發 `LeaseOutcome::Consumed`（line 946-951），不發 DispatchFailed、**不收斂本地倉**（noop_is_exchange_zero_position 對 10001 回 false，與 110072 一致；只有 110017 收斂）。鏡像 Ok/NoOp 成功路徑。close retry 撞 dup（首次已達 Bybit、response 丟、retry 重發同 id）= 冪等成功，與 110072 同理成立。
3. **與既有 10001 子串邏輯交互無破壞**：10001 arm 由「duplicate→NoOp / else→Structural」改為一律 `10001 => Structural`（line 272），retMsg 不再在 classify 層被讀；duplicate 偵測下移 consumption 層。10002 的 recv_window/timestamp 子串（line 288-295）是**另一個碼**，完全不受影響。非-duplicate 的 10001（格式錯/qty 非法）正確維持 Structural fail（test_close_dup_is_idempotent_success_close_10001_non_duplicate_false 覆蓋）。
4. **rate-limit / ToS**：0 風險。NoOp/upgrade ≠ retry（無新 REST 流量）；close-dup 冪等收尾不增 Order group 用量。

### 測試覆蓋（dispatch_tests.rs，load-bearing 對抗驗證）
- classify：test_classify_duplicate_order_link_id_10001_is_structural（含大小寫）+ test_classify_invalid_param_is_structural（非-dup 10001 仍 Structural）+ test_classify_110072_..._is_structural。
- helper：close_10001_duplicate_true（含大寫）/ open_10001_duplicate_false（★ open fail-closed 關鍵，註明拿掉 is_close guard 應 FAIL）/ close_10001_non_duplicate_false（格式錯/qty 非法）/ 110072 對應 4 test / non_business_error_false / does_not_trigger_local_convergence（10001-dup 與 110072 皆不收斂）。
- 回歸：test_open_retry_budget_unchanged_after_110072_change（OPEN_NO_RETRY 空 slice）。

### 字典補錄（1 LOW 非阻，併 BB1 backlog）
dict §4.2 110072 註記（line 1355）結尾的 follow-up 句目前寫「既有 10001+duplicate → NoOp 無 close guard…列 PM follow-up」——此 follow-up 已 land，該句須更新為「**10001 + retMsg contains "duplicate" 亦適用同 close-only 冪等語意**（與 110072 同 narrow：open fail-closed / close idempotent-success；classify 層 10001=>Structural，consumption 層 close_dup_is_idempotent_success 以 is_close+substring guard upgrade）。注意：substring 僅在 ret_code==10001 分支生效，10014 'Request is duplicate' 為獨立碼不誤觸」。另 §4.2 retCode 表 10001 row（line 1315）可加註腳指向 110072 註記。精確文字見本次 verdict §reference。E2 同 commit 或 BB1 backlog 補。

### 給 PM/E2 注意事項
1. 代碼為 SSOT 且已正確 land；BB 此裁決為交易所側語意背書，**非要求改碼**。
2. open path fail-closed 是此 follow-up 的**收緊**（10001-dup 從 fail-open NoOp 改 fail-closed Structural-else）——方向更保守，與 110072 一致，0 倉位安全回歸。
3. 不可恢復 hidden open retry（NoOp/upgrade ≠ retry）；OPEN_NO_RETRY 不變量由 test_open_retry_budget_unchanged 鎖定。
4. Mac sign-off ≠ runtime：Linux cargo test 需在下次 --rebuild 復現（dispatch_tests 全綠）。
5. 字典 §4.2 line 1355 follow-up 句更新（LOW，非阻 deploy）。

### 下次啟動需查驗項
1. dict §4.2 line 1355 follow-up 句是否更新為「10001+duplicate 已 land 同 close-only 語意」+ 10014 不誤觸註（BB1 backlog 或 E2 同 commit）
2. Linux --rebuild 後 dispatch_tests.rs 10001-dup + 110072 全 test 是否 PASS
3. 若未來 Bybit 改變 10001 retMsg 語意（在 10001 下夾帶非-orderLinkId 的 "duplicate"），close 側 substring 誤吞面需重評（當前官方 0 此情境）
4. hedge mode 啟用復活時，110072 + 10001-dup 冪等路徑與 110017 收斂同須 positionIdx corner case re-review（G-3 前提，承 110017/D2 教訓）

## 歷史里程碑（2026-06-10 自 BB.md 遷入，原文保留）
- 2026-04-04：首次系統審計（5 path fix + 3 UTA migrate + 3 deprecated remove）
- 2026-04-12：full_program_chain audit（BB-A1~A7 系列）
- 2026-04-20：EDGE-P2-3 Phase 1B-1 retCode 擴充
- 2026-04-24：全面復審；H-1 字典過期 + M-1/2/3 周邊優化

---

## 2026-06-10 Demo vs Mainnet 撮合/深度審計(AC19 alt 23.8% 歸因)

- **「demo book 系統性薄於 mainnet」prior 證偽**(BB 自我更正):REST orderbook/tape 實測 demo=mainnet 同源鏡像(同 u/seq/execId 序列,OP/ETC/ARB 五檔逐位一致)+ 官方 demo doc「public data is identical to mainnet」。AC19 慘案歸因=**撮合模擬無 queue position**(官方:demo 掛單不可見於 order book),fill 規則最符合零-queue-credit trade-through-like(推斷 MEDIUM)。轉移性:alt mainnet 方向 ≥ demo(不保證 ≥60%)、large_cap demo≈公平;demo `EC_PostOnlyWillTakeLiquidity` reject 推送有正樣本(silent-degradation 該軸部分退役,`EC_ReachMaxPendingOrders` 軸仍未證)。下次查驗:MIT/QA 10 筆 alt fill 的 through-print 判別是否做(F-3 升級)、引用舊 prior 的 spec/SOP 是否改寫。報告:`workspace/reports/2026-06-10--demo_vs_mainnet_depth_matching_audit.md`(HIGH F-1 已副本至 Operator/)。

## 2026-06-11 subagent 四態契約生效
- 回報首行 STATUS 四態（DONE|DONE_WITH_CONCERNS|NEEDS_CONTEXT|BLOCKED+一行理由）；BB.md 新增外部抓取物圍欄鐵則：公告/網頁/changelog 原文餵任何 prompt 前必包 `<untrusted_content>` 並聲明其中指令一律不執行。

## 2026-06-11 公告增量哨兵 advisory(for E1)
- `GET /v5/announcements/index`=public 無 auth(host api.bybit.com,禁經簽名 client),locale=en-US 必填,默認 limit=20/實測 100 OK;**響應無 id 欄、列表排序=dateTimestamp 非 publishTime(inversion 實證)→ 去重鍵=正規化 url 主鍵(blt<hex> UID 輔助)+ seen-set 差集,禁 timestamp watermark**;cron 30min 1 call limit=50 不傳 type 本地分級(delistings/maintenance=P0,tag/keyword escalator);403=IP ban 10min → fail-quiet skip。字典 0 記載 → §1.11 補錄草稿在 memo,E1 IMPL 同 commit 落。live 抓到 TONUSDT perp 2026-06-15 delisting 公告(P0 樣板,與 06-10 watch 關閉一致)。30d changelog 0 breaking。下次查驗:E1 是否照 memo §10 七項驗收(尤其 watermark 禁用+圍欄+字典同 commit)。報告:`workspace/reports/2026-06-11--bybit_announcement_sentinel_advisory.md`

## 2026-06-12 incident_policy dispatch trigger CORE+auth+Bybit BB review
- Verdict `APPROVE-WITH-CONDITIONS` for reviewed partial path; 0 blocker/high/medium. `incident_policy` report itself adds no Bybit request, and exchange side effects remain C4 owner-handler `StopRequest` -> existing `set_trading_stop` channel.
- Frequency/rate posture acceptable: Bybit producer triggers on 8 consecutive or 15/60s business retCode failures, suppresses duplicate open incident edges, recovery requires 3 successes + cooled window; policy adds 5m throttle/single owner/7d cooling.
- Do not overclaim: `bybit_fail_closed` is business-retCode fail-closed, not full exchange outage coverage; transport/parse/no-credentials are outside this producer. Remaining producer coverage: `sm_halt_stuck`, `position_drift`, `engine_dead`.

## 2026-06-12 incident_policy sm_halt_stuck source update (not BB-reviewed yet)
- PM/E1 source slice added `sm_halt_stuck` producer via `event_consumer/sm_halt_incident.rs`, using `TickPipeline.halt_kind` + `halt_set_ts_ms` as runtime source-of-truth and explicitly not using stale passive healthcheck `[69]`.
- This update has not received BB re-review. BB next check should focus on whether active HaltSession -> incident notification -> possible C4 Defensive escalation keeps the same exchange-side boundary: no new Bybit request at report time, no direct stop write outside C4 owner handler, and no false claim that a policy/sticky halt equals exchange outage.
- Remaining producer coverage after this source slice: `position_drift` notify-only and external `engine_dead` watchdog notify-only.

## 2026-06-12 incident_policy position_drift source update (not BB-reviewed yet)
- PM/E1 source slice added `position_drift` producer via `position_reconciler/incident.rs`, observing only unresolved post-orphan/post-ghost reconciler drift after 3 consecutive cycles and feeding `IncidentClass::PositionDrift`.
- BB boundary to verify in review: this is notify-only and must not send C4 AllFail; it adds no Bybit request, no order, no close, no stop write, and no exchange-side mutation. Existing reconciler `PipelineCommand` escalation/close behavior is unchanged.
- Remaining producer coverage after this source slice: external `engine_dead` watchdog notify-only; `sm_halt_stuck` + `position_drift` both still need BB/E2 focused review before E4/QA/full-chain.

## 2026-06-13 盈利研判（成本側 BB 域，read-only runtime 親證）

**核心：leak 不在 funding，在 fee+execution gap。** trading.fills 親證（demo+live_demo all-time）：taker fee **5.9-6.1 bps/side**、maker **2.1 bps/side**（PostOnly 真省 ~4bps，命中時）；但 close-maker 30d 僅 **35% 成交**（46 maker / 66 timeout→taker / 19 postonly_reject = 131 attempt），~50% 平倉退回 taker。intents 99.99% limit（145k/163k）但 fill ~50% taker = **intent-vs-fill 執行漏損**。RT 成本 ~4bps(maker-maker)→~12bps(taker-taker)。realized PnL 近平（demo +$9.47 / live_demo +$6.57 all-time on $680k/$106k notional ≈ 0.1-0.6bps net）。
- **funding 非 leak（證偽 funding-drag 假說）**：median hold 7-11min、p95 ~67min、30d 僅 4/3 RT 跨 8h 結算 → 短持倉幾乎不碰 funding 結算。funding-tilt/carry 在此 turnover 下無基礎。
- **broker rebate DOA**：30d gross ~$407k demo + $25k live_demo = **~$432k << $10M 門檻（~23x 不足）**；單帳戶 size 太小，未來 scale 才談。
- **★ 新機會 rpiTakerAccess（changelog 2026-06-03，full rollout 2026-06-12）**：UTA taker order 加 `rpiTakerAccess=true` 可吃 RPI maker 流動性拿價格改善 → 直擊 OpenClaw ~50% taker-close 路徑。engine 已用 UNIFIED（platform_client.rs:651）、order body 組裝在 order_manager.rs:353-422，加單一 optional body field 可行；code 0 處引用=unrealized。需 BB review fee 語義（RPI 是否改 taker fee 分類）+ E1 IMPL。
- **30d changelog 2 項 BB-relevant**：(1) rpiTakerAccess（上述機會）；(2) 2026-05-21 transaction log rate limit 50→25 req/s（OpenClaw baseline ~0.7 req/s，0 衝擊，advisory）。0 breaking。
- per-symbol funding cap live 再證：BTCUSDT ±0.5%/8h、WIFUSDT 4h interval；current funding 低/混（BTC +1.8% / SOL -10% APR）= down-regime 低-premium，任何 funding 正面結果標 regime-bet。
- 報告：returned inline to PM（無獨立 .md per task instruction）。

## 2026-06-14 srv 全倉 read-only Bybit 合規審計 — rate-limit SSOT 三方矛盾為主發現
- 核心交易路徑（HMAC REST+WS 簽名、4-env base-url/slot/topic 映射、live gate 4/5 HMAC+constant-time、retCode fail-closed 分類、account-scoped cancel-all kill、order body one-way positionIdx、Earn <2026-04-09 mock gate、withdraw 架構級零引用）= 技術 PASS / 0 ship-stop。
- **BB-1 HIGH**：字典 §4.1 (line 1315-1333) rate SSOT 與官方 V5 doc 全面矛盾。官方（2026-06-14 WebFetch×2）：order create/cancel/amend=**10/s per-endpoint 非 shared 20/s pool**、cancel-all 有獨立 limit（部分 tier 1/s）、position-list/wallet-balance=**50/s**、fee-rate=**5/s**。字典「Order/Position/Account=20/s shared quota」+「cancel-all 無獨立 budget」三組數字全錯。**更正 BB 舊 memory line 9「Order/Position/Account=20 r/s」=亦 stale，真值見此**。
- **BB-2 MEDIUM**：code 內部不一致——RateLimitGroup enum docstring (229-233) 寫 20/s、default seed (297-299) 寫 10、註解 (286/1450) 稱「10 req/s 窄組」。三處三值。BB-3：runtime 靠 x-bapi-limit-status header authoritative，seed 僅 cold-start → 不撞 cap（安全），但 SSOT 文檔誤導。
- BB-5 LOW：live_authorization now_ms duration_since 失敗 fallback=0 理論 expiry fail-open（鐘<1970 不可能，nit）。
- BB-6 advisory：rpiTakerAccess（changelog 06-03/full 06-12）order body 仍 0 引用=機會未取，承 06-13 盈利研判。
- BB-7 MEDIUM-policy：公告哨兵仍未 IMPL（code 0 消費者）；30d 多筆 perp delisting（RLS/CLOUD/CTK/ORBS/EPT…USDT）未對 25-symbol 核對；靠 110074 被動兜底。
- 30d changelog 0 breaking。報告 `workspace/reports/2026-06-14--bybit_api_compat_audit.md`（已複製 Operator/）。
- 下次查驗：(1) 字典 §4.1 是否改 per-endpoint 表並標 erratum；(2) code rate docstring/seed 是否統一；(3) E1 哨兵 IMPL 進度。

## 2026-06-14 seam 查證 — shadow_decision_builder 客戶端 3-桶 qty pre-round（PARTIAL）
- seam 指 `shadow_decision_builder.py:269-274` 客戶端按 price>10000→5dp/>100→3dp/else→1dp 粗桶 round qty，於交 Rust authoritative round 前。查證：**verdict=PARTIAL**。
- **路徑為 paper-only 且生產 latent**：`submit_paper_order`→`submit_external_order`(commands.rs:163) 走 paper IntentProcessor，**絕不碰真實 Bybit 下單**（docstring line 38 + IPC 方法名雙證）；觸發鏈 L2 engine run_session 需真 model call（operator-gated/dormant）→ 生產不可達除非 L2 顯式激活。故非 bybit-incompat（不打交易所）、非 ship-stop。
- **Rust authoritative round 比 seam 假設更穩**：instrument_info.rs round_qty=floor-to-qtyStep；commands.rs:266-275 有 **min_qty 救援**（rounded→0 且 min_qty notional ≤ balance*10% 時補到 min_qty）。seam 講「Rust 再 round 成零靜默丟單 reason=qty_rounds_to_zero」**措辭錯**：`qty_rounds_to_zero` 是 Python line 276 reason；Rust drop reason=`"fill_qty rounded to 0"`(line 279) 且有救援。
- **真實缺口（narrow，成立部分）**：Python pre-round 在 qty 落 < bucket 精度時先吐 `qty_rounds_to_zero`（line 275-278）**無任何 log**（_record 僅 append 200-cap 記憶體 history，唯一消費=paper route 1087 pull-only debug，無 alert）→ 搶在 Rust min_qty 救援前丟單。觸發需 price≤100 且 qtyStep 細於 0.1 + 極小 notional（小 balance）。pinned 25 實測 qtyStep：BTC 0.001/DOGE 1/XRP 0.1/ADA 1/TRX 1/BCH 0.01/LINK 0.1，多為 whole-step → 正常 2% sizing 下 round-to-1dp 反而比真 step 細，**典型路徑不丟單**；僅小餘額+細-step 邊角觸發。
- defect_type=dead-code-leaning + missing-gate（silent drop 無 log）；非 bybit-incompat（不打交易所）。fix=Python pre-round 移除或對齊 instrument cache step，把 round 權威全交 Rust（已有 floor+救援）；至少 line 275 加 logger.warning。

## 2026-06-14 rpiTakerAccess fee 語義裁決（WS3 cost_gate gating，read-only 設計階段）
- **核心：rpiTakerAccess=true 的 taker 單吃 RPI maker 流動性 → 仍付 taker 費率，改善在 PRICE（price improvement）不在 fee，無 fee 分類變更、無 taker rebate**（affects_taker_fee_class=FALSE，confidence HIGH）。RPI 兩角色須拆清：`timeInForce=RPI`=MM-only post-only maker（OpenClaw 不可用，下了報 "restricted to approved Market Makers"）；`rpiTakerAccess`=任何 UTA taker 解鎖匹配 RPI 報價（OpenClaw 適用方=吃單側）。官方 RPI fee 調整公告對象=「RPI market makers」非 taker。
- **cost_gate 口徑：A 預交易 CostGate（`cost_gate.rs` COST_TIERS taker_fee_pct=0.055）+ B fill-path `fee_rate_for_tif`（maker 0.0002/taker 0.00055）均不改**。A=保守 taker 假設=fail-safe（RPI 只會讓實際成本 ≤ 假設，把 improvement 算進門檻反而錯誤放鬆）；B=`loop_exchange.rs:189-197` 真實 feeRate 優先、TIF 常量僅 cold-start/fast-topic 兜底→RPI 後若費率真變記帳自動跟真值。環境：demo/livedemo normal-exec 帶真 feeRate（自動正確）/mainnet execution.fast 無 feeRate 用常量（保守高估=安全）。
- ToS 無礙（tos_ok=TRUE）：官方標準 param 主動推 API taker，0 wash/KYC/rate/withdraw 牽動，30d 0 breaking。E1 WS3 落地=僅加 1 optional body 欄 rpiTakerAccess（絕不碰 timeInForce=RPI）+ 選配 WS rpiMatchedQty/isRPITrade 觀測（不進 gate）+ 字典 RPI 補錄（dict 目前 0 記載）。屬「無悔縮虧 A 桶」執行衛生非搜索空間翻正。殘留 2 LOW UNCERTAIN（官方未逐字書面化 taker-fee 條款 / 不排除未來折扣 taker 費率，但雙保險架構皆安全）。
- 報告：`workspace/reports/2026-06-14--rpi_taker_access_fee_semantics_ruling.md`（Conditional PASS，0 ship-stop，未達 CRITICAL/HIGH 故不複製 Operator/）。

## 2026-06-14 delta-中性 funding/basis carry 探索 — CONDITIONAL-EDGE（carry 真但構造被夾死）
- **carry 信號 STRUCTURAL（非 IC 範式可判死）**：2yr research.alpha_funding_rates_history（20 sym×~2190 結算）實證 — funding 正偏 persistent（top ARB/SUI/LINK/DOGE +6.0~6.6% APR、78-80% 結算為正）、AC1 高（majors 0.6-0.68）、sign 命中率 77-87%（prev>0→next>0）；條件進場（prev>+0.005% point-in-time）realized **+8.5~9.9% APR on majors**，negative-surprise 僅 6-17%。季度分解每季皆正（+2.1%~+16.3%，2024-Q4 +16.3% bull spike / 2026-Q2 +2.5% 當前 down-regime）→ sign 結構性、magnitude regime-dependent。
- **構造 A cash-carry（long spot+short perp，唯一吃完整 funding）★killer=spot 在 engine 0 callers**：OrderCategory::Spot enum 存在（order_manager.rs:102）+ body builder category-agnostic，但 decision/reconciler/position-query/bootstrap/pending-sweep 全 hardcode Linear；get_positions 只查 linear（spot 無 /position/list）。需新建 spot 執行+wallet reconcile+risk+fill 子系統=major build。fee 牆主在 spot 腿（non-VIP ~10bps/side）；break-even @+6% ~15-20天/@+2.5% ~38-47天（一次性 fee 多日攤薄，與 7-11min 主策略每 10min 付 fee 結構不同）。
- **構造 B calendar（long expiry+short perp，derivatives-only demo 可交易）★killer=basis 套利掉 carry**：api-demo 實證暴露 36 LinearFutures（BTC/ETH/SOL/DOGE/MNT majors，非全 25）。expiry contango premium 到期收斂 ≈ perp funding（市場 priced-in）；實測 net pre-fee≈0（5d −5.4~+4.8bps；103d annualized BTC −4.6%/ETH +1.4% APR），再扣 4-leg fee（8.4-24bps RT）=負。**dead by arbitrage equilibrium，調參無法翻正**。
- 構造 C perp-perp 非真 delta-中性（跨 symbol=方向 bet），reject。
- 30d changelog 0 breaking（singleOpenInterest/withdrawal-compliance/rpiTakerAccess/pov，皆與 carry 正交）。cash-carry/calendar 政策合規、0 rate 衝擊、withdraw=false 不變。
- **下次查驗**：若 operator 批 spot subsystem，先 QC 算「regime-dependent +2.5%~+9% APR × 帳戶 size」絕對金額 vs build 成本；spot 啟用前 BB review UTA spot 開通+spot fee tier。報告 `workspace/reports/2026-06-14--delta_neutral_carry_exploration.md`。

## 2026-06-14 delta-中性 carry lens 對抗複核（attacker mindset，獨立取證）— verdict=NEEDS-MORE-EVIDENCE
- **carry 信號獨立取證 CONFIRMED（FACT 非 assumption）**：自跑 production PG（trading_ai.research.alpha_funding_rates_history，730d）復現 top SUI/ARB +6.4% APR、LINK/DOGE/NEAR +6.0%、77-80% pct_pos、16/20 正；自跑 conditional（prev>+0.005% point-in-time）BTC +9.18%/ETH +9.32%/SUI +9.82%/SOL +8.47%/ARB +8.77% APR、negative-surprise 5.9-17.3%。報告數字全部對得上實查。
- **構造 B calendar killer 用 live public curl 獨立坐實（lens 自身失效模式，非 IC 論證）**：mainnet 36 LinearFutures 確認（BTCUSDT-19JUN26 命名）；即時量 perp-vs-expiry basis：basisAPR 3-7% ≈ 歷史 fundingAPR 5-6%（結構恆等=expiry premium 就是 priced-in funding）；calendar net carry(funding−basisCarry) live = BTC −5~−6.4%/ETH −0.36~+1.7%(≈0)/SOL −16.3%/XRP −19.9% APR（perp funding 現負時 short-perp 腿反付）→ pre-fee≈0~負，扣 4-leg fee 必負。**dead by arbitrage equilibrium 成立。**
- **構造 A spot 0-callers 坐實但措辭微鬆**：grep OrderCategory::Spot 全 srv 僅 6 命中——enum def + as_str() test + loop_handlers.rs:673 一個 IPC cancel-all 字串 parse arm（latent，引擎從不發 spot 單故永不觸）；position_reconciler 409/551/901 + get_positions 全 hardcode Linear。「0 callers」精確說法=「0 execution/reconcile/fill wiring」（有 1 latent parse arm）。實質 major-build 結論成立。
- **regime 現況比報告更尖**：live BTC perp funding **現為負 −1.73% APR**、SOL −14.85%/XRP −13.34%；ETH 僅 +4.05%。+6% 結構均值是 2yr/bull-weighted，point-in-time majors 在 break-even 或以下，多 symbol 現負 → 2024-Q4 +16.3% 須標 regime-bet（CLAUDE Alpha Evidence Governance）。
- **報告未計成本（殘留 edge 算式關鍵）**：cash-carry +6% gross 只扣 4-fill fee，**未扣多日綁定 spot 腿 USDT 抵押的 cost-of-capital / opportunity cost**，亦未驗 spot maker/taker 實況。扣此後當前 regime 殘留 harvestable net ≈ 0~微負。
- **residual_edge_after_refute**：構造 B=0（套利均衡，live 坐實）；構造 A 信號真但 harvestable=0~負（未建 + 現 regime sub-break-even + cost-of-capital 未計）。delta 中性本身成立（非隱藏 beta，與 stat-arb lens 不同）。survives=false（當前無可部署淨正 edge）；非 FATAL（bull regime + spot subsystem + 足夠 size 下可翻正）→ NEEDS-MORE-EVIDENCE。operator-gated：(a) build 成本 vs regime-dependent 美元 carry×size；(b) live UTA cross-margin/spot financing 行為。

## 2026-06-14 跨所 lead-lag / 三角微結構探索 — 雙線 NONE/NEEDS-DATA（read-only production 親證）
- **lens=跨所 lead-lag + intra-venue 統計套利**。execution 仍 Bybit-only；ADR-0033/0040 允許 Binance read-only。
- **跨所 leg = NEEDS-LIVE-DATA（結構性阻塞）**：production **0 Binance 表**（`market.binance_*` 不存在）、0 WS connector code、order_router 對 BinancePerp/Option 走 `VenueDeferred("Y3+ per ADR-0033")` hardcode。ADR-0033 §Decision1 批 Binance market-data Y1 但 Sprint 1A WS NEW **從未 IMPL**。「Binance lead Bybit」假設無數據可驗 → 需先建 Binance market-data WS（~10-15hr，E1）才談。
- **intra-venue 跨資產 lead-lag (BTC→ALT) = NONE-FOUND**：1m grid 同期 corr 強（ETH 0.88/多 alt 0.4-0.5=共因子 BTC beta）但 lead-lag 交叉相關全期 |corr|<0.03（k≠0），lead_asym 多為負（強 alt 如 ATOM/FIL/ARB/XRP 反而微領先 BTC，~0.01-0.03 遠低成本牆）。1m bar 已吸收跨資產傳導；真 lead-lag 在 sub-second tick（無存儲）。
- **統計套利 (協整 pairs) = NONE-FOUND after cost**：in-sample Engle-Granger 138/190 pair 過 ADF<-3.34（half-life 5-35min）**但 OOS 協整崩潰**（SUI/ADA spread mean 漂移 +4776bps OOS=stale hedge）。修正 drift-capture artifact（rolling-beta + dollar-neutral 兩腿 return 分計）後：maker 8bps→1/190 net+，taker 24bps→**0/190 net+**（median −10497/−34808bps）。低換手變體（z>3/30min minhold）13/190 maker-net+ 但 8/13 含 NEAR=單 symbol regime；taker 成本下幾乎全翻負；IS/OOS sign-flip。dirR~0.0-0.14（dollar-neutral 真去 BTC beta=唯一正面）。
- **killer**：成本牆（同 6 週主病）——pair trade=4 fill，maker 8/taker 24bps RT；mean-rev edge/trade <成本，且需 ~100% maker fill（系統實況 35% close-maker fill，06-13 親證）。NEAR winner=regime-bet（OOS>>IS=近 10d 集中）。
- 報告：`workspace/reports/2026-06-14--cross_exchange_leadlag_statarb_exploration.md`。下次查驗：若 operator 批 Binance market-data WS IMPL，跨所 lead-lag 才有數據可第一階驗（execution 仍 Bybit-only，信號跨所）。

## 2026-06-14 from-zero crypto-native 微結構 edge 發散（cost_gate 結構偏誤再審 + 數據可用性翻案）
- **cost_gate 結構偏誤 CONFIRMED（operator 循環論證質疑成立）**：`gates.rs:45/218/328` `threshold_bps = fee_bps/wr * safety_multiplier` + `cost_gate.rs` `min_move = c_round/wr*1.3`（c_round=2×(taker0.055+slippage)）= **per-trade 方向性 ATR move > 雙邊 taker 成本**。此式結構上**只能評方向性 taker 策略**：做市賺 spread/rebate、delta-中性籃、vol-harvest 這類「edge=spread 或 carry 非方向 move」的構造，永遠無「ATR move > cost」→ **必被拒，與其真實 PnL 無關**。99.97% reject「全真負」是用同一方向性框架判同一方向性策略=循環，**不證明非方向類也該被擋**。fix 非調參=該類策略需**繞過 cost_gate 走另一條 viability 閘**（spread-capture 算 expected_spread − 2×maker_fee；carry 算 funding − fee；非 ATR-vs-cost）。
- **數據可用性翻案（推翻 profit-diagnosis「OBI/cascade 無存儲不可測」）**：production PG 親查——`market.trade_agg_1m`=**1.92M rows / 152 sym / ~70d**，欄位 buy_volume/sell_volume(=OFI)、buy_count/sell_count、**large_buy_count/large_sell_count(=meta-order/whale 偵測)**、max_single_qty(=sweep)。`market.liquidations`=**266K rows / 84+ sym / ~28d 且 live-growing(372/h)**，欄位 ts/symbol/side/qty/price。→ **OFI/meta-order + cascade-fade 兩軸 $0 離線 leak-free 可測，數據早在庫**（之前說無表是錯的；無表的只有 sub-second tick + L2 book snapshot）。
- **cascade-fade ≠ 已killed 的 cascade-follow**：6/3 + 6/14 killed 的是 cascade **方向跟隨**（raw IC 0.45=純 down-beta R²0.962，殘差崩 0.03）。**fade=反向接 overshoot 均值回歸 + 時間出場**，是 delta-中性 LP 行為非方向 bet，結構不同未測過。crude 1m 對齊 sketch（liq≥30/min cluster，T1→T5 revert）=inconclusive（revert 1.2/6.4bps，std 183-334bps，t<1.1）——但這只證**1m naive 太粗非自由午餐**，非證偽（文獻用 velocity+volume 濾 + sub-5min flush 減速錨點，須 proper 構造）。
- **Bybit-native 機械點**：(1) spread-capture——live spread 實測 ADA 5.9bps/BCH 4.9bps/LTC 2.3bps/INJ 2.0bps（vs BTC 0.016bps 鎖死、ETH 0.06bps）=寬-spread alt 是 maker-spread-harvest 角落，BTC/ETH 1-tick 鎖死不可做；(2) rpiTakerAccess(承 6/14 ruling)=close 側繞 taker 成本拿 price improvement；(3) funding-snipe（跨 settlement 持倉只在 |F| 極端時，delta-hedge 價格腿）=未測機械流。
- **why_not_crowded / 小資金可行（文獻+結構）**：cascade-fade 是 LP 領域，機構容量受限（fade climax 需 rapid micro-trading）；crypto 高槓桿 retail 持續再生 cascade 供給=reflexive 不衰竭；$298 帳戶實證 ~25bps gross/trade（太小機構吃不下=正是我方甜區）。VPIN/OFI 方向性已 crowd-decayed（82→38→12 bps/trade 2024→26）但 **meta-order/whale 偵測 IC 仍 ~0.10**（large_*_count 欄位正對應）。
- 報告 inline 回 PM（per task：不落獨立 .md，Write findings 直接回傳）。下次查驗：(1) operator 是否批 QC/MIT 跑 cascade-fade proper 構造（velocity+vol 濾+sub-5min）+ OFI/meta-order(large_count) 離線 leak-free IC/反應曲線於 trade_agg_1m；(2) 是否為非方向類策略加獨立 viability 閘（spread/carry 口徑）繞過方向性 cost_gate。

## 2026-06-14 執行架構/做市/微結構執行成熟方案搜索（lens=fork-3 execution，harvest D2 sub-min alpha）
- **hftbacktest (nkaz001) = 最高價值 fork-3 find**：MIT、Rust75%+Python bindings、**原生 Bybit 範例**、queue-position-aware fill sim（SquareProb/LogProb/PowerProb 概率隊列模型，用 trading-intensity 校準）、同一算法碼 backtest→live。直擊任務(2)誠實估 maker fill（非樂觀 intrabar-touch）+ 與 OpenClaw Rust 引擎同架構。其 OFI market-making-with-alpha 範例 = D2 harvest 的現成 worked example。
- **★ 致命經濟學發現（決定 D2 harvest 可行性）**：hftbacktest OFI 範例 Sharpe 10.83/34.2%（2023-05 BTC）**完全靠 -0.5bp maker rebate**，return/trade=1.39bps；無 favorable rebate 跌至 0.86bps（2025-02）。**OpenClaw 付 +2.1bp maker fee（非 rebate），1bp/trade OBI 毛 edge 結構性淨負**——這就是 D2「需 maker-queue 執行才 harvest」的成本真相，maker-queue 必要但不充分，rebate 是缺的腿。Bybit MM rebate（-0.01%~-0.015%）需 institutional apply + 相對市佔分檔，$432k/30d vs ~$50M 門檻 = DOA（承 06-13）。
- **nautilus_trader (nautechsystems) = 架構鏡像 fork-3**：production-grade Rust-native 確定性 event-driven、原生 BybitExecutionClient+HMAC+rate-limit、**Bybit WS Trade API 低延遲下單**、TWAP exec algo、research→live 統一。**關鍵約束：WS Trade API demo 不支援→自動退 REST**（承 BB memory「demo 不支援 execution.fast」）→ sub-min WS-order-entry harvest 只能 testnet/mainnet 驗，demo 不可。
- **Bybit-native 執行機械點（changelog/doc 實證）**：(1) `bboSideType`/`bboLevel`=原生 BBO-peg maker 單（自動貼最優價，直擊 ~50% taker-close）；(2) WS Order Placement 比 REST 快且穩（Bybit 自家 benchmark repo 證）；(3) rpiTakerAccess（06-03/full 06-12）承 6/14 ruling=price-improvement 非 fee class。30d changelog 0 breaking（singleOpenInterest 06-11/MMP vegaLimit 06-09 options-only/withdrawal-compliance 06-10/SBE 06-02）。
- **逆選擇規避（D2 死因）三方案**：(a) Stoikov microprice（quote 繞 microprice 非 mid，OBI 預測下一步 move=逆選擇來源）grayvalley/microprice-calibration 校準 BitMEX perp+HJB-QVI，research-only；(b) VPIN/order-flow toxicity（flowrisk 等），方向性已 crowd-decay（82→12bps 2024→26）；(c) Hawkes（Deep Hawkes MM, arXiv 2109.15110）核心洞察=「fills 非低成本隨機，而是與不利價格 move 同時發生」=D2 alt 腿逆選擇的學術根本，paper-only。
- **cascade-fade（承 6/3+6/14 reframe）OOS-BACKTESTED 外證**：curupira.dev cascade-fade scalper=velocity(5-bar 位移)+volume(3×)雙濾 1m、sub-5min 時間出場、5-window walk-forward（SOL PF~2.5/ETH 2.9/BTC 1.5 rejected）；**但 live 僅 +$0.51 micro-capital + 非開源 + 自承「5-10bps execution eats it to marginal」**=證據強度 OOS-BACKTESTED 非 PROVEN-LIVE，且成本牆與 OpenClaw 同。構造（velocity+vol+sub-5min）正是 memory 說的 proper 構造，與 D2 sub-5min 半衰期吻合。
- **RL 執行/ABM**：RL-Exec（arXiv 2511.07434）impact-aware RL 勝 TWAP/VWAP on BTC-USD replay=paper-only replay，小帳戶 sub-5min maker 適配差；ABIDES/JAX-LOB=ABM LOB 模擬器（fill realism 研究工具非策略）。OpenClaw 單筆 size 小，TWAP/VWAP/RL 切片暫不需（承 microstructure skill §5.2）。
- **總裁決**：D2 harvest 的執行腿（maker-queue fill sim + OBI-skew quoting + microprice + WS 低延遲下單）有成熟 Bybit-ready 開源（hftbacktest + nautilus_trader），**離線可零成本驗**；但 harvest 的經濟可行性卡在 **maker rebate 缺口**（OpenClaw 付 fee 非收 rebate）→ OBI-MM ~1bp/trade 毛 edge 淨負，與 cost_gate 結構偏誤（非方向類需另閘）+ broker rebate DOA 三線同源。**執行框架 adopt 成本低但不解經濟學**；翻正仍需 rebate-tier 或更大 edge/更低 turnover。
- 報告：`workspace/reports/2026-06-14--execution_microstructure_frameworks_survey.md`（未達 CRITICAL/HIGH，不複製 Operator/）。下次查驗：(1) operator 是否批 QC/MIT 用 hftbacktest queue-model 離線回測 D2 OBI-MM 在 OpenClaw fee 結構（非 rebate）下的真 net；(2) nautilus_trader BybitExecutionClient 是否值得作 WS-order-entry 參考實作（testnet 驗）；(3) bboSideType/bboLevel maker-peg 是否進字典+ E1 評估接 ~50% taker-close。

## 2026-06-19 fee-tier / MM / API-broker eligibility audit — current scale NO-GO, operator-only lever
- 官方 Bybit docs rechecked：VIP1 derivatives requires $10M/30d or $100k eligible assets; API Broker Level 1 derivatives also starts at $10M/30d; MM rebates require application plus weighted maker share. MNT fee discount excludes API users.
- Linux read-only PG current 30d fills proxy = $840,299 notional total, $477,049 maker; all demo/live_demo, therefore not direct mainnet eligibility evidence and only ~8.4% of $10M if used as capacity proxy.
- Verdict: PM-local fee reduction work is closed; remaining lever is operator capital/scale/Bybit BD action. Report `docs/CCAgentWorkSpace/BB/workspace/reports/2026-06-19--bybit_fee_tier_mm_rebate_eligibility.md`.

## 2026-07-03 srv 全倉 read-only 合規審計 — 公告哨兵停擺為主發現
- **F-1 HIGH**：bybit_announcement_sentinel cron 條目 06-27 起從 trade-core crontab 消失（疑 demo-learning cron 批次覆寫，原 7,37 槽被佔），heartbeat/log 停在 06-27 17:37，delisting/maintenance P0 watch 無聲死亡 ~6d；30d 有 14 檔 perp delisting（pinned 25 0 中招，TON 已換 BNB）；F-1b：heartbeat age 無監控消費者。**F-2 HIGH**：字典 §4.1 rate 表 erratum 仍未修（官方 07-03 再證 per-endpoint：create/cancel/amend/cancel-all 各 10/s、position-list/wallet/execution-list/realtime 50/s、fee-rate 5/s）；BB-1 第二輪重申。**F-4 MEDIUM**：Python `_resolve_credentials` 僅 mainnet 禁 env fallback，live_demo（live slot）仍接受 BYBIT_API_KEY env → 與 Rust P1-08 is_live_slot 契約 drift（runtime 現況 0 env creds，latent）。**F-5 MEDIUM**：unattributed:bybit_auto fills 仍活躍（最新 07-03）+ 本地 Working 尾態 111 筆堆積，lineage 缺口自 06-24 未修。F-6：rpiTakerAccess 第三輪 0 引用。已閉：OI/funding backfill client+dict、10001-dup 字典註記、哨兵代碼本身對齊 advisory。30d changelog 0 breaking（第 5 輪）；rate 30d 0 hit；LIVE-GUARD 三閘 + gate5 HMAC runtime 實證乾淨。報告 `workspace/reports/2026-07-03--bybit_api_compat_audit.md`（HIGH 已複製 Operator/）。

## 2026-07-06 maker-first pivot 可行性 fact sheet（feed QC/PM go-no-go，read-only）
- **fee/rebate 三方確認（承 06-19 audit，官方 fee doc + WebSearch 復核）**：USDT-perp VIP0 = **maker 0.0200% / taker 0.0550%**（= OpenClaw 當前實測 fee）；maker 費率隨 VIP 降但**到 Supreme VIP 才 = 0.0000%**（VIP1-5 maker 0.018→0.010% 全為正）。**負 maker（真 rebate）只有兩條路**：(a) Supreme VIP 之上無負 maker；(b) **Market Maker Incentive Program**=唯一 negative-maker 途徑，derivatives MM1-3 rebate −0.0010%~−0.0125%（按 symbol group 1-5 分檔）。**結論：一般 VIP 階梯給不出 rebate；rebate=MM-program-only。**
- **MM program eligibility（今日 WebSearch 官方確認新增細節）**：application-based（institutional_services@bybit.com，subject "Market Maker Application"）；**必為 API user + 必完成 KYB（Know Your Business，機構實體）**；門檻=30d weighted maker share MM1≥0.03%/MM2≥0.50%/MM3≥1.00%（分母=全 Bybit MM maker volume，本地不可算）；MM order size 須 ≥ 10× 合約最小單量；月度考核，未達標當月取消資格沒收 benefit；1-month trial。**對單一 retail bot 帳戶=institution-gated，非 attainable**（$477k/30d demo maker proxy vs 需搶 Bybit-wide maker share）。
- **API 高報價率約束（今日官方 rate-limit doc verbatim）**：★**linear(USDT-perp) 比舊 memory 更寬**——order create/cancel/cancel-all/create-batch/amend-batch/cancel-batch **各 20/s**（UTA2.0-Pro/inverse 才 10/s），amend=10/s；per-IP 600/5s；batch 消耗=req×orders；全部 Upgradable=Y（VIP 可升）。**更正 07-03 memory line「create/cancel/amend/cancel-all 各 10/s」→ 該值是 UTA2.0-Pro/inverse 檔；OpenClaw 走 linear = 20/s（amend 10/s 例外）**。字典 §4.1 erratum 應補 linear 20/s 欄。
- **無 published cancel-ratio / OTR / quote-stuffing 數字罰則**（WebSearch 官方 Trading Rules 查無）：Bybit 靠 per-endpoint rate limit 硬節流 + price-limit/anti-spoofing 定性條款兜底，非 OTR 上限。quoting bot 的硬牆=rate limit 本身 + MM-program「未達標取消資格」自律。→ post-only quoting 不違 ToS（PostOnly 合規），高 quote-rate 唯一硬約束是 20/s(amend 10/s)。
- **geo/KYC（承 05-26 audit，不變）**：16 restricted jurisdictions；KYC Standard L1 足夠 perp；maker posture 不改 geo/KYC 面（無新增限制）。operator residence 仍 0 governance trace（M5-1 ship-stop 對 mainnet，與 maker pivot 正交）。
- **code 面**：rpiTakerAccess/bboSideType/bboLevel/referer/broker 全 engine 0 引用（第 4 輪）；PostOnly 已 wired（order_manager/order_router）；rate-limit group Order seed=10 保守（linear 真值 20，靠 header 收斂不撞 cap，安全但 seed 偏保守）。
- **底線 verdict**：maker economics 對 OpenClaw **當前 scale = 淨負不可翻正**——付 +2.0bps maker fee（非收 rebate），OBI/spread-capture 毛 edge ~1bp/trade 結構淨負（承 06-14 hftbacktest 經濟學）；rebate 的唯一門（MM program）institution-gated（KYB+Bybit-wide share+SLA），單帳戶不 attainable。favorable 起點=MM1（rebate −0.001%）但 gate=operator BD action + 機構實體 + 搶 maker share，非工程可解。30d changelog 0 breaking。報告 inline 回 PM（per task 不落獨立 .md）。

## 2026-07-09 盈利研判（BB 成本/微結構/新品 lens，read-only）
- 守：30d true net −406 USDT fee-dominated（fee 佔淨虧 63%）；close-maker fill 率惡化 35%→27.9%（90/323；postonly_reject 116 可被 bboSideType 機械消除）；funding 非 leak 三度確認（hold p50 5min，7/497 跨結算）；哨兵 07-04 已復活（閉 07-03 F-1）；fee-tier 前提惡化（30d notional $690k=VIP1 的 6.9%）。
- 攻（三個 2026-Q2 新結構角落，全未被系統檢視）：(1) TradFi 股票 perp 家族（G9 fee group 06-16 全 tier 調低；30d 62 檔新上市，股票 perp spread 15-116bps=唯一 spread>>fee population）×IBKR read-only anchor=新機制候選；(2) /v5/spread FundingRateArb 原生 spot+perp 原子 spread（50% fee off，拆 06-14 carry 的 build/leg-risk 牆）但 venue 現死市 volume24h=0→設 BB 月度監測（volume>$100k×7d + majors funding>+8% APR 觸發，現 BTC +6.77% 從 −1.73% 回正中）；(3) Alpha Prediction Market API 07-02 NEW（事件軸 venue 候選，需 CC 產品邊界裁決）。rpiTakerAccess 第 6 輪 0 引用。30d changelog 0 breaking（第 6 輪）。報告 `workspace/reports/2026-07-09--bybit_profit_diagnosis_readonly.md`。

## 2026-07-09 engine --engine-only --rebuild Bybit-side deploy gate（read-only 實測）— GO
- **probe-on-boot=SAFE（雙獨立 fail-closed 閘，adapter env=1 不相關）**：canonical soak plan（`.../bounded_demo_probe_soak_plan.json`）雖含 top-level `order_authority=DEMO_LEARNING_PROBE_GRANTED`+`status=READY_FOR_DEMO_LEARNING_PROBE`+operator auth `order_authority_granted=true`，但 admission 鏈（`demo_learning_lane.rs::evaluate_probe_admission`）在 adapter_enabled 檢查**之前**先撞兩閘：(1) plan staleness — `max_plan_age_hours=24`,plan generated_at=2026-07-08T19:01Z 已 26.6h>24h → `PLAN_STALE_OR_MISSING_GENERATED_AT`;(2) operator auth expiry — `validate_operator_authorization_envelope` line861 `expires_ms<=now_ms` → EXPIRED（expires 2026-07-09T00:12:30Z,now 21:37Z）。**活引擎當下實證**：probe_ledger.jsonl 21:43Z 連續 `code=PLAN_STALE_OR_MISSING_GENERATED_AT allowed=False`;ledger 0 筆真 bounded_probe_attempt/order（record_type 僅 probe_admission_decision×297+blocked_signal_outcome×199）。probe 非 boot 動作,是 tick-driven（需 ma_crossover|NEARUSDT|Buy cost_gate reject 全鏈過閘才 fire）。⚠️advisory:adapter env=1+write-connector 使 probe「熱待命」,唯一屏障=plan 新鮮度+auth 未過期;若 operator 重簽 fresh plan+auth 則會 fire 2 單——本次 restart 兩閘皆閉故 SAFE。
- **demo book（活引擎 reconciled 視角,非 Bybit private API）**：status_report 21:48Z `positions=0 fills=0 intents=0 balance=9519.15 symbols=31`。boot 06:28Z adopt 1 既存倉 AVAXUSDT Buy 0.1（$0.66),06:28:36 EVICT-ON-DUST（<$1 floor,boot_reaper）→ 本地 flat;Bybit demo 仍留該 0.1 dust（PHANTOM-FILL-FIX-1 advisory 08:00/16:00Z「WS 報有倉本地 flat」）=pre-existing 良性 dust,restart deterministic 重跑 adopt→evict 不下單。working orders restored=0。private WS order-topic msg=0=無 resting order churn。**DB trading.* 凍在 04:48Z（boot 前）=quiet 引擎 0 fills since boot 之良性,非 bug**。
- **reconnect/rate/WS**：單次 demo 重連（private wss://stream-demo.bybit.com/v5/private auth_ok=1/disconnect=0/running=true;public 9 topics/sym×31+allLiquidation;boot REST 少量）;since-boot WS disconnect=0。baseline headroom 巨大,可忽略。demo 已知非致命 quirk（DCP 10032/fee-rate 10001 seed taker0.00055/auto-margin 110076）boot 重現屬正常。live pipeline 正確 REFUSED（authorization.json absent,gate5 fail-closed）。binary on-disk=07-05 build（stale,符），process 06:28Z 起。30d changelog 0 breaking（同日第6輪已證）。**verdict=GO,可安全 --engine-only --rebuild restart**。post-restart 查驗:boot 重現 adopt→dust-evict/WS connect/probe admission fail-closed;新 HEAD binary demo 行為 runtime 再證（Mac/build≠runtime）。

<!-- /ROLE_MEMORY_COMPACTION_V1 payload_sha256=sha256:4f4d054236a2f17ce37b280f4b40a1c736a8575099dfeefb9109d7cd917533c3 -->
