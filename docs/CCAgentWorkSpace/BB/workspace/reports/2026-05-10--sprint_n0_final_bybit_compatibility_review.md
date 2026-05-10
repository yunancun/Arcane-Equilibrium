# BB Sprint N+0 Final Bybit Compatibility Review

**Auditor**: BB (Bybit Broker Compatibility Auditor)
**Date**: 2026-05-10
**Baseline**: v3 `da2aba11` → final `18e212f9` (28 commits over Sprint N+0)
**Scope**: W-AUDIT-9 graduated canary 對 Bybit live 影響 + W-AUDIT-8a Phase A AlphaSurface Tier 2/3 stub 對應 Bybit V5 API + 30d changelog drift

---

## §A — W-AUDIT-9 Graduated Canary 對 Bybit Live 影響審計

### A.1 5-stage transition 對應 Bybit endpoint

| Stage | Cohort | Environment | Bybit endpoint | LiveDemo authorization 需求 |
|---|---|---|---|---|
| **0** shadow | 全鏈 shadow，不送 intent 到 Rust submit path | n/a | n/a (0 API call) | n/a |
| **1** paper × 7d | 1 strategy × 1 symbol | `Environment::Paper` | n/a (paper simulation) | n/a |
| **2** demo × 14d | 1 strategy × 1 symbol | `Environment::Demo` | `api-demo.bybit.com` (Bybit demo) + `wss://stream-demo.bybit.com/v5/{public,private}` | LiveDemo signed authorization.json **NOT required** (Demo 走獨立 demo endpoint) |
| **3** demo full × 21d | 5 active strategies × full universe | `Environment::Demo` | 同 Stage 2 | 同 Stage 2 |
| **4** LIVE_PENDING | LIVE_PENDING (operator 顯式拍板) | `Environment::Live` (Mainnet 或 LiveDemo) | Mainnet `api.bybit.com` 或 LiveDemo `api-demo.bybit.com` | **LiveDemo authorization.json mandatory**（gate 5 invariant 7） |

**Bybit-side verdict**: Stage 0/1 完全 0 Bybit API impact（shadow + paper simulator）；Stage 2/3 走 Bybit demo endpoint（與 W-AUDIT-1 sync 描述的 LiveDemo runtime 一致）；**Stage 4 才碰 mainnet** 且**仍受 5-gate live boundary 全強制**（CLAUDE.md §四 line 125-136）。

### A.2 LiveDemo authorization.json 在 graduated canary stage transitions 中保持有效（invariant 7 verify）

**驗證**：AMD-2026-05-09-03 §3.3 explicit 列「Live boundary 5-gate」為 graduated canary **不適用範圍**，任何 stage 升降不放寬 5-gate。`canary_stage_log` PG 表（V080）`transitioned_at_ms` 與 LiveDemo authorization 5min re-verify cycle 互不耦合 → stage transition 不會觸發 authorization revoke / expire / cancel_token shutdown。

**Push back 觸發點**：若未來 IMPL 出現 `canary_stage_provider.shadow_mode_provider()` 路徑與 `live_auth_watcher.rs` 5min re-verify 路徑共用 mutex / shared state → 立即 BB Critical（互相 deadlock 可能 starve LiveDemo authorization 重簽）。**當前 IMPL 兩路徑完全解耦** → ✅ PASS。

### A.3 canary_stage_log entry 對 Bybit broker rebate / market maker eligibility 影響

V080 `governance.canary_stage_log` 是純 internal governance audit table，**0 Bybit broker rebate / market maker / VIP tier eligibility 影響**：
- canary_stage_log row 不影響 Bybit 帳戶 30d volume tally
- 不影響 maker fill rate（W-AUDIT-9 不改 IntentProcessor / OrderManager / PostOnly 行為）
- 不向 Bybit 上報任何 metadata（無 X-BAPI-* header 注入）

**Bybit-side**：W-AUDIT-9 對 Bybit 是「透明的」，broker partnership 30d volume threshold (~$10M) 不被觸碰；當前 OpenClaw $45K 30d volume × 222× gap 與 graduated canary 無關。

### A.4 ToS / KYC / 地理禁區 不變

W-AUDIT-9 IMPL 不引入：
- 新地區 deployment（KYC tier 變動）
- 新 API key permission 申請（仍 read+trade，**無 withdraw**）
- 新 IP whitelist 配置（M5-2 仍 outstanding 但 W-AUDIT-9 不惡化）
- 新 Bybit 帳戶創建 / sub-account / master-sub topology 變動

**Bybit-side**：W-AUDIT-9 對 Bybit ToS / KYC / 地理禁區 0 影響。M5-1 governance entry 仍 outstanding 但**獨立於本 wave**，不影響 Sprint N+0 sign-off。

### A.5 Risk Item — Stage 1 Sprint N+1 啟動需 operator 拍板 cohort + symbol

**Bybit-side push back**：AMD §2.4 規定 Stage 1 cohort 由 operator 在 Settings tab 拍板（不 auto-pick）。Sprint N+1 啟動 Stage 1 前 operator 需確認所選 symbol：
1. 不在 Bybit 30d delisting 候選名單（30d Bybit changelog 0 delisting → ✅ 全 25 symbol safe）
2. 不在 Bybit perp suspension 名單（funding_arb retire 後 BUSDT 不可選為 Stage 1 cohort）
3. **不違反 W-AUDIT-9 cross-wave conflict #4**：A4-C (8d) 用 W-AUDIT-9 Stage 1 paper cohort 入場，但「非 W-AUDIT-9 7 sub-task 完整 land 不啟動」— W-AUDIT-9 7 sub-task 已全 land + E2 third-pass APPROVE + E4 third-pass PASS（commit `30b34b9b` + `18e212f9`）→ ✅ 解封

---

## §B — W-AUDIT-8a Phase A AlphaSurface Tier 2/3 對應 Bybit V5 API 審計

### B.1 Phase A IMPL 對 Bybit endpoint 影響 = 0

**驗證**：`git diff --stat 1bd55689..HEAD -- 'rust/openclaw_engine/src/{bybit_*,ws_client*,market_data_client*}'` = **空輸出**。Phase A 完全 0 Bybit endpoint 變動：
- `alpha_surface.rs` (513 行新模組) 是 struct + enum 定義 + 7 unit test，無 Bybit API call
- 5 策略 `declared_alpha_sources()` 是 const slice declare，無 runtime API call
- `step_4_5_dispatch.rs` 升級 `Strategy::on_tick(ctx, surface)` 簽名，surface = `AlphaSurface::tier1_only(indicators, indicators_5m)` — 純內部 indicator borrow，0 Bybit API call

**Bybit-side verdict**：Phase A E1 IMPL report `2026-05-10--w_audit_8a_phase_a_trait_alpha_surface.md` claim「0 行為變化」**從 Bybit endpoint 視角全證實**。

### B.2 Tier 2 stub (FundingCurveSnapshot / BasisCurveSnapshot / OIDeltaPanel) 對應 Bybit V5

| Stub field | Phase B 對應 Bybit V5 endpoint | 字典手冊 alignment | rate limit feasibility |
|---|---|---|---|
| `FundingCurveSnapshot.funding_rates_bps` | `GET /v5/market/funding/history` (per symbol, 200 row max) **OR** `tickers` WS `fundingRate` field (broadcast) | ✅ 字典 line 148-161 + line 974 | 25 sym REST = 25 calls/8h cycle = 0.0009 req/s（Market 限 120 req/s 充裕）; WS 是免費 broadcast (預設訂閱) |
| `BasisCurveSnapshot.basis_pct` | `GET /v5/market/instruments-info` (perp index_price) + `GET /v5/market/tickers` (spot last_price) **OR** `tickers` WS（含 mark_price / index_price） | ✅ 字典 line 96-99 + line 974 | 25 sym REST = 50 calls / refresh = 0.05 req/s (Phase B 30s refresh 合理); WS 免費 |
| `OIDeltaPanel.oi_delta_5m_pct` | `GET /v5/market/open-interest` (interval=5min/15min/30min/1h/4h/1d) **OR** `tickers` WS `openInterest` field | ✅ 字典 line 130-144 + line 974（注意：字典 line 137 explicit 標註 request key 必為 `intervalTime` 不是 `interval` — F-27 修正） | 25 sym REST = 25 calls / refresh = 0.025 req/s; WS 免費 |

**Bybit-side push back（Phase B IMPL 前必查）**：
1. **Phase B collector 必優先用 WS `tickers` topic 數據**（已預設訂閱），REST `funding/history` / `open-interest` 只當 WS 數據缺漏 fallback
2. 若 PA Phase B spec 指定 REST polling → 必須在 collector 內合併 25 symbol 為 batch wait（aggregator pattern），避免 25 separate calls 等同 25× rate limit 計數

**字典 drift verify**：funding_rate (line 148-161) / open-interest (line 130-144) / tickers (line 96-99) / orderbook (line 113-126) **字典手冊 SSOT 與 W-AUDIT-8a Tier 2 stub 完全對齊**，0 drift。

### B.3 Tier 3 stub (OrderflowFeatures / LiquidationPulse) 對應 Bybit V5

#### OrderflowFeatures (W-AUDIT-8a Phase C stub mock，真接留 W-AUDIT-8d)

**Bybit V5 真實 orderbook depth levels = `1 / 50 / 200 / 1000`，沒有 L25**（字典 line 973 + alpha_surface.rs line 175 + spec line 151 一致）。

`alpha_surface.rs` line 65 `AlphaSourceTag::OrderflowImbalance` enum variant 不指定 depth level（"L25" / "L50"），由 Phase C/W-AUDIT-8d IMPL 時對齊 `orderbook.50.{symbol}` 預設訂閱（字典 line 973 + line 979）。

**Bybit-side verdict**：✅ BB v3 NEW-5「PA spec L25 不存在」**已被 PA spec 採納**：
- `spec.md` line 154 explicit「**禁止**任何「L25」字眼進 spec / IMPL / migration / healthcheck」
- `spec.md` line 153 預設用 `orderbook.50.{symbol}`，deeper book 用 `orderbook.200.{symbol}`
- W-AUDIT-8a Phase C 排程 stub mock + dummy data 為主，真接留 W-AUDIT-8d
- `alpha_surface.rs` 新 enum + struct 0 「L25」字串 → grep 證實

#### LiquidationPulse (W-AUDIT-8a Phase C dormant，requires_revival)

**Bybit V5 真實**：`allLiquidation` WS topic 真實存在但**OpenClaw 於 2026-04-06 已刪除 handler**（字典 line 990 + spec line 162-166 一致）。

**Bybit-side verdict**：✅ BB v3 NEW-6「liquidation_pulse 已 deleted 需 revert」**已被 PA spec 採納**：
- `spec.md` line 162-170 explicit `requires_revival: true` + 「Phase C 先 dormant + schema reserved；Phase C+1 sprint（單獨 sub-phase）做 WS handler revert + writer 重啟 + 真接」
- `spec.md` line 165「禁止 stub mock 數據（避免「假 alpha source dispatched」污染 dispatch tracking metric）」
- `alpha_surface.rs` line 220-225 `LiquidationPulse` struct 註釋「**狀態 dormant** — `allLiquidation` WS handler 於 2026-04-06 已移除...復活前 `AlphaSurface.liquidation_pulse` 永遠 `None`」

**Phase C+1 sprint 啟動前 BB review 預警**：
1. 復活時 `ws_client/parsers.rs` 新增 `allLiquidation` parser → 必驗 unknown handler guard 策略（M-1 G9-02 UnknownHandlerGuard）
2. `allLiquidation` topic 訂閱可能觸 Bybit IP rate-limit（per spec §6 Risk-5），需 BB pre-flight rate-limit 估算（25 sym × 平均 liquidation events/min × peak factor）
3. `market.liquidations` PG retention 30d 需 MIT review

#### BasisCurveSnapshot (W-AUDIT-8a Phase B Tier 2.2，requires_spot_capability)

**Bybit-side verdict**：✅ BB v3 NEW-8「basis demo 限 observation 沒分」**已被 PA spec 採納**：
- `spec.md` line 132-138 explicit「**execution 邊界（明文）**: basis = observation-only signal until mainnet；Bybit demo 環境**不支援 spot lending execution**（與 funding_arb v2 retire 同因，ADR-0018）；perp 與 spot 之間真 cash-and-carry 在 demo 不可行」
- `spec.md` line 134「吃 `Basis` tag 的策略 ctor 必須 declare `requires_spot_capability: true`」
- `spec.md` line 135-136「IntentRouter 應有 `requires_spot_capability && !env_has_spot` 檢查」
- `alpha_surface.rs` line 133-148 `BasisCurveSnapshot` struct 註釋「**`requires_spot_capability: true`**」+「永遠是 observation-only signal」

**Phase B IMPL 預警**：IntentRouter `requires_spot_capability && !env_has_spot` 檢查未 IMPL 前，任何吃 `Basis` 的策略 IMPL 必 BB Critical（funding_arb v2 同陷阱風險）。

### B.4 Tier 4 stub (EventAlert / RegimeTag / SentimentPanel) 對 Bybit 影響

| Stub field | 對應 Bybit V5 endpoint | Bybit impact |
|---|---|---|
| `EventAlert` | n/a (Scout `intel_objects` 內部 IPC slot, 0 Bybit API call) | 0 |
| `RegimeTag` | n/a (純內部 indicator 組合 ATR/Hurst/EwmaVol) | 0 |
| `SentimentPanel` | n/a (W-AUDIT-8a stub-only, external feed 未接) | 0 |

**Bybit-side verdict**：Tier 4 完全 internal compute / external non-Bybit feed，0 Bybit endpoint 影響。

---

## §C — Bybit V5 字典 drift 30d verify

### C.1 W-AUDIT-9 + W-AUDIT-4b 不引入新 Bybit V5 endpoint

`git diff --stat 1bd55689..HEAD -- 'rust/openclaw_engine/src/{bybit_*,ws_client*,market_data_client*}'` = **空輸出**。Sprint N+0 28 commits 完全 0 Bybit endpoint 接線變動。

**Bybit-side verdict**：字典手冊 `docs/references/2026-04-04--bybit_api_reference.md` v1.2 entries vs Sprint N+0 source code = **0 drift**。

### C.2 30d Bybit V5 changelog (2026-04-09 至 2026-05-09)

繼承 v3 audit：30d Bybit V5 changelog **0 breaking change**（v3 §A.1 結論維持，v3 baseline 至今 24h 無新公告）。
- 7 條變動，0 影響 OpenClaw（新欄位 `serde(default)` 兼容 / 新 endpoint 不用 / deprecated 欄位不在 hot-path）
- 0 endpoint deprecation 影響 25 symbol perp universe
- 0 listing/delisting 影響 25 symbol active universe

---

## §D — Push back / Risk 識別 for N+1+ wave

### D.1 W-AUDIT-8b (A4-A Funding Skew) Sprint N+3 Spec → N+4 IMPL

**BB pre-flight checklist for PA spec drafting (Sprint N+3)**:
1. funding skew 25-symbol cross-section 拉取頻率：建議 30s WS aggregate（已預設訂閱），不開 `/v5/market/funding/history` REST polling
2. 若需 REST history backfill (cold start) → 25 calls × 1 batch wait，rate limit 充裕但需明文寫 spec batch_wait pattern
3. funding settlement 8h cycle (00:00 / 08:00 / 16:00 UTC) 前後 ±5 min 高波動：建議策略內 explicit halt-trade window，避免 settlement instant 持倉風險

### D.2 W-AUDIT-8c (A4-B Liquidation Cluster Reaction) Sprint N+2 Spec → N+3 IMPL

**BB pre-flight checklist for PA spec drafting (Sprint N+2)**:
1. **Bybit V5 WS topic `allLiquidation` 真接 = 必走 W-AUDIT-8a Phase C+1 sprint 復活路徑**（spec line 162-170 + Risk-5 line 385）
2. 復活前置：(a) `ws_client/parsers.rs` 加 `allLiquidation` parser；(b) UnknownHandlerGuard 串接 `allLiquidation` topic；(c) Python `liquidation_writer.py` 重接 `market.liquidations` PG 表；(d) BB rate-limit 預估 (peak liquidation events / 60s window)
3. event-trigger 模式：策略消費 `LiquidationPulse.recent_events` rolling 60s window；不可在 cascade 進行中 trend-follow（CLAUDE.md `crypto-microstructure-knowledge` skill §2.4 反模式）

### D.3 W-AUDIT-8d (A4-C BTC→Alt Lead-Lag) Sprint N+1 Spec → N+2 IMPL

**BB pre-flight checklist for PA spec drafting (Sprint N+1, **第一 IMPL** 最高 impact)**:
1. BTC 1m 急動 ≥1.5σ 信號：靠 BTCUSDT WS kline.1.{symbol} (預設訂閱)；0 新 endpoint
2. alt-BTC 60s ρ>0.7 + alt 仍未動 ≥50%：cross-symbol correlation 計算需 25 symbol kline.1 同步 buffer（已預設訂閱）；0 新 endpoint
3. 半衰期 30-180s = 1m sampling 完美匹配 → 0 sub-1m WS 需求
4. **W-AUDIT-9 Stage 1 cohort 入場**：A4-C 用 W-AUDIT-9 Stage 1 paper × 7d 入場（cross-wave conflict #4）— W-AUDIT-9 7 sub-task 已全 land → **解封**

### D.4 v3 殘留 outstanding 維持監控

| v3 finding | Sprint N+0 進展 | N+1+ 預警 |
|---|---|---|
| **NEW-1 BUSDT PG 殘倉 12186 條** | 0 進展（10 天延遲）| operator action 仍欠 `/v5/position/list?symbol=BUSDT` 實測；W-AUDIT-9 Stage 1 不可選 BUSDT 為 cohort |
| **M5-1 ToS / KYC governance entry** | 0 進展（12 天延遲）| true-live 前 mandatory；不影響 Sprint N+0 sign-off（W-AUDIT-9 不引入新地區 / KYC 變動）|
| **M5-2 IP whitelist preflight** | 0 進展（12 天延遲）| 同上 |
| **A5-2 BybitRetCode enum 110017** | 0 進展 | fee_filter 字串匹配維持工作；P2 不阻 Sprint N+0 |
| **A5-6 fee_drop funding_arb 過濾** | 0 進展 | funding_arb 已 retire（`af4942b6`）→ 樣本污染衰減自然發生；P2 |

---

## §E — Sprint N+0 整體 BB 視角 verdict

### E.1 技術合規度：97%（與 v3 持平）

- Bybit V5 endpoint alignment：100%（Sprint N+0 0 endpoint 變動）
- HMAC + Rate limit + LIVE-GUARD：100%
- 字典 SSOT vs source：100% align（0 drift）
- LiveDemo healthcheck `[56]`：active（CLAUDE.md §三 sync 維持）
- W-AUDIT-9 graduated canary IMPL **不放寬** 5-gate live boundary（AMD §3.3 invariant）：✅ 確認
- W-AUDIT-8a Phase A 0 Bybit endpoint 變動：✅ 確認
- A5-2 / A5-6 殘留 -3pp 維持

### E.2 政策合規度：70%（與 v3 持平，0 進展）

- M5-1 governance entry：仍 0
- M5-2 IP whitelist preflight：仍 0
- 30d Bybit changelog 0 breaking：✅
- BUSDT PG 殘倉 dust clear：仍 0 進展（10 天延遲）

**政策合規不阻 Sprint N+0 sign-off**：W-AUDIT-9 graduated canary 5-stage transition 無一 stage 涉真 mainnet（Stage 4 才到 mainnet 且仍受全部 5-gate 強制）；W-AUDIT-8a Phase A 0 Bybit API call。M5-1/M5-2 是 true-live (Stage 4) 前置，與 Sprint N+0/N+1 IMPL 並行。

### E.3 BB v3 NEW-5/6/8 採納驗證：3/3 ✅

| Finding | PA spec 採納 | alpha_surface.rs IMPL 反映 |
|---|---|---|
| NEW-5 PA spec L25 levels 不存在 | ✅ spec line 151-156 「禁止 L25」+ 預設 orderbook.50 | ✅ `OrderflowImbalance` enum variant 0 「L25」字串 |
| NEW-6 liquidation_pulse 已 deleted 需 revert | ✅ spec line 162-170 `requires_revival: true` + Phase C+1 sprint | ✅ `LiquidationPulse` 註釋 + dormant + 永遠 `None` |
| NEW-8 basis demo 限 observation 沒分 | ✅ spec line 132-138 `requires_spot_capability: true` + IntentRouter 檢查 | ✅ `BasisCurveSnapshot` 註釋「永遠是 observation-only signal」 |

---

## §F — Final Verdict

### Sprint N+0 BB 視角整體 verdict: **APPROVE**

**理由**：
1. W-AUDIT-9 graduated canary 5-stage 機制對 Bybit live 影響 = 0（Stage 0/1 0 API call；Stage 2/3 走 demo endpoint；Stage 4 才碰 mainnet 且全 5-gate 強制不放寬）
2. W-AUDIT-8a Phase A AlphaSurface trait + 5 策略 declare = 0 Bybit endpoint 變動（純 internal struct/enum migration）
3. W-AUDIT-8a Tier 2/3 stub 對應 Bybit V5 API 設計 = PA spec 已完整採納 BB v3 NEW-5/6/8 三 push back（L50 not L25 / liquidation requires_revival / basis requires_spot_capability）
4. 字典手冊 v1.2 vs Sprint N+0 source code = 0 drift
5. 30d Bybit V5 changelog = 0 breaking change
6. LiveDemo authorization.json 5min re-verify 與 canary stage transitions 完全解耦（無 deadlock 可能）
7. broker rebate / market maker / VIP tier 0 影響（W-AUDIT-9 不向 Bybit 上報 metadata）

### FLAG follow-up for N+1+

**HIGH (PA Phase B/C 啟動前 mandatory BB review)**：
1. W-AUDIT-8a Phase B (Sprint N+1) Tier 2 collector IMPL 必驗：(a) WS `tickers` topic 優先於 REST polling；(b) 25-symbol funding curve 使用 aggregator 不開 25 separate REST calls；(c) IntentRouter `requires_spot_capability && !env_has_spot` 檢查 IMPL（NEW-8 配套）
2. W-AUDIT-8c (Sprint N+2 spec) Liquidation IMPL 復活前必跑 BB rate-limit 估算 + UnknownHandlerGuard 串接

**MEDIUM (N+1 啟動 cohort 拍板前 BB 確認)**：
1. W-AUDIT-9 Stage 1 cohort symbol 不可為 BUSDT（funding_arb retire 殘倉風險）
2. W-AUDIT-9 Stage 1 cohort symbol 必於 30d Bybit listing/delisting 確認（當前 0 風險，N+1 再驗）

**LOW (N+1+ 待 operator action)**：
1. M5-1 / M5-2 / BUSDT PG dust clear / A5-2 / A5-6 殘留 — 不阻 Sprint N+0；Stage 4 (true-live) 前必 closed
2. 字典 v1.3 補 04-30 新欄位 catalog (P2 TW)

---

**BB AUDIT DONE**: srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-10--sprint_n0_final_bybit_compatibility_review.md
