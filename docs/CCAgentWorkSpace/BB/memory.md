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
