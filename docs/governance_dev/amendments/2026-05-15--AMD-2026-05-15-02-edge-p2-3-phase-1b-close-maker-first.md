# Amendment AMD-2026-05-15-02 — EDGE-P2-3 Phase 1b: Close-Maker-First Refactor

**對應 spec**: EDGE-P2-3 · DOC-01 §5.1/§5.4/§5.5/§5.6/§5.8/§5.9/§5.16 · DOC-08 §12 · `docs/references/2026-04-24--postonly_design_intent.md`
**修訂對象**: EDGE-P2-3 Phase 1a entry-only scope-limiting 設計（`commands.rs:792-797` hard-coded `order_type:"market"` with comment「Close path stays Market (EDGE-P2-3 Phase 1a entry-only scope)」）
**Supersedes**:
- EDGE-P2-3 Phase 1a 的 close-path-entry-only scope boundary（自然延伸到 close path）
- 過去任何「close path 永遠 market」字面語義（仍對真風控止損成立，對策略級 close 解除）

**日期**: 2026-05-15
**作者**: PM applying main-session PM+PA+FA convergent verdict + 4-agent (QC+FA+BB+MIT) adversarial review consolidated patch；2026-05-15 PA Wave 1.5 patch v0.3（A3 portfolio_var verify + E3 maker fill empirical baseline + A4 W-C Caveat 2 V094 schema 兩段式 + writer gap + E1 KAMA fallback gate by-the-way）；2026-05-15 PA Wave 2a Track A2 patch v0.3.1（V094 hybrid schema migration spec finalize, F-FA-1 ✅ DONE）；2026-05-15 PA Wave 1.5b patch v0.4（Wave 3a 4-agent re-review consolidation — AC-1..AC-19 + V094 trading_writer.rs:430 details writer upgrade explicit + negative whitelist 補 risk_close:fast_track* / halt_session* + 16 原則 #3/#11/#13/#15 明列 PASS）
**狀態**: **DRAFT v0.4** — Wave 1.5b consolidated patch（AC range 對齊 AC-19 / 字面修正 + Wave 3a 4-agent re-review 純 numerical / cosmetic 增量無新風險）；IMPL Prereq 條件 2 SATISFIED；pending Wave 2b reject_cooldown split + 3-gate
**索引**: `docs/governance_dev/SPECIFICATION_REGISTER.md` Amendments section
**TODO 連結**: P0-EDGE-1（fee bleed 影響 edge measurement）/ EDGE-P2-3 Phase 1b / W-AUDIT-8b（後續 funding alpha 不被執行成本掩蓋）

---

## 1. Executive Decision

**Close path is now an alpha-impact-adjacent execution-quality pathway**（消除 fee bleed 對 alpha 量測的污染；本身不是 alpha source）。[^v03_fee]

[^v03_fee]: **per Wave 1 Track E3 empirical baseline**：fee saving revised 4.5 → 0.5-2.0 bps net per close attempt（per `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--maker_fill_rate_empirical_baseline.md` §6-§8 三層解讀：fill-conditional best 3.31 / per submitted mid 0.95 / close conservative 0.66）；對 Executive Decision 結論不變（execution-quality optimization 而非 alpha source），但全年估算修正為 $50-$200（v0.2 寫 $160-$400 太樂觀）。

EDGE-P2-3 Phase 1a 的「entry-only PostOnly」scope 在 close path 延伸為按 `exit_reason` 白名單分流的 maker-first 機制。安全止損 / 賬戶風控 / 對賬 / operator override 強制保 market 不變。

> **分類消歧（Consensus-MF-1，QC + FA round-2 align）**：本 AMD 內部統一語義 = **alpha-impact-adjacent execution-quality**。Close-maker-first 不引入新 alpha source，而是消除 fee bleed 對 alpha 量測的雜訊，讓 P0-EDGE-1 edge floor 判斷更乾淨。**因此不適用 W-AUDIT-9 5-stage canary 強制 gate**（那條 gate 是 alpha-bearing 新策略；本 AMD 仍 mirror Phase 1a 三段灰度模式即可）。詳 §5。

決策邏輯：
1. 經 3 輪對抗審核 + DB / 代碼核驗，5 textbook 策略 30d demo `-110.43` / live_demo `-27.31` USDT structural alpha-deficient；其中 `live_demo grid 7d 100% active taker close 全是策略級`（grid_close_short 74% / bb_mean_revert 18% / grid_close_long 7% / ma_reverse_cross <1%），**0% 真風控**。
2. 現有「Close path stays Market」comment 是 **governance scope-limiting decision，不是技術限制**（PA 驗 dispatch.rs:504-538 IPC chain 已完整支援 Limit + PostOnly + maker_timeout）。
3. `phys_lock_gate4_giveback` / `phys_lock_gate4_stale_roc_neg` 是 **profit-protection 4-gate 鏈**（edge floor → hold age → peak ATR → giveback / stale ROC），非 §5.9 hard-stop（FA verified；exit_features/v2.rs:286-288 PhysicalDecision::Lock 證據）。
4. Phase 1B-4.2 resting_orders.rs 是 paper-only path，與 exchange close 正交，**0 依賴**（PA verified）。

---

## 2. Scope Change

### 2.1 Newly Permitted Path

`OrderDispatchRequest` 在 `commands.rs:778-816` / `commands.rs:940` (ipc_close_all) / `commands.rs:1123` (ipc_close_symbol) 三個 close dispatcher 可按 `trigger_tag` / `exit_reason` 白名單構造 PostOnly Limit + maker_timeout_ms，timeout 後 fallback to market。

### 2.2 Positive Whitelist（8 maker-first reasons）

| exit_reason | 來源 |
|---|---|
| `grid_close_short` | grid_trading/signal.rs:316 |
| `grid_close_long` | grid_trading/signal.rs:348 |
| `bb_mean_revert` | bb_reversion/mod.rs:629（**same-strategy exit; not cross-strategy**） |
| `phys_lock_gate4_giveback` | exit_features/v2.rs Lock decision |
| `phys_lock_gate4_stale_roc_neg` | exit_features/v2.rs Lock decision |
| `ma_reverse_cross` | ma_crossover/strategy_impl.rs |
| `bw_squeeze` | bb_breakout/mod.rs（CONDITIONAL with healthcheck `min_samples_gate=30`，per Consensus-MF-2 升 normative AC） |
| `pctb_revert` | bb_breakout/mod.rs:524-550（同上） |

### 2.3 Negative Whitelist（強制保 market）

| 類別 | 顯式 reason |
|---|---|
| 真風控 | `risk_close:HARD STOP` / `risk_close:TRAILING STOP` / `risk_close:TIME STOP` / `risk_close:DYNAMIC STOP` / `risk_close:fast_track*` / `halt_session*`（**v0.4 patch per Wave 3a FA-#3 cosmetic finding，PA 識別變體**；spec §4.3 已列；本 AMD 同步以對齊 §三/§四 fail-closed semantic）|
| 帳戶級風控 | `DAILY LOSS` / `DRAWDOWN` / `CONSECUTIVE LOSS` |
| 利潤達標 | `TAKE PROFIT: pnl X% >= Y%` |
| AI cost gate | `COST EDGE: ratio X >= 0.80` |
| 對賬 | `bybit_sync` / `orphan_*` / `dust_frozen` |
| Operator override | IPC `/operator/close_position` 強制平倉 |
| 災難保護 | Engine shutdown / cancel_token / circuit breaker / authorization 失效 |
| 策略內部歧義 keyword | bb_breakout 內部 `trailing_stop`（chandelier exit；與 `risk_close:TRAILING STOP` 同 keyword，必 source 識別） |
| 未識別 reason | fail-closed 走 market（§5.6） |

---

## 3. Rollout Posture

**Mirror EDGE-P2-3 Phase 1a entry-only 模式**：

| Phase | 期間 | 環境 | TOML | 啟動條件 |
|---|---|---|---|---|
| **Phase 2a Demo** | **7d primary + 7d extended observation = 14d total**（v0.3 per Track E3 conservative discount） | demo | `use_maker_close = true` per-策略 | IMPL 完成 + 三閘全過 + AMD 4-agent review PASS |
| **Phase 2b LiveDemo** | 7d | live_demo | `use_maker_close = true` per-策略 | Phase 2a 14d PASS（AC-1..AC-7 + AC-14 Wilson + AC-15 reject sample + AC-16 NULL ladder + **AC-18 fallback-to-taker rate ≥ 95%** + **AC-19 14d close_maker_fill_rate ≥ 30%** v0.3 新增） |
| **Phase 3 Live (Mainnet)** | indefinite | live | `use_maker_close = true` per-策略 per-exit_reason | Phase 2b PASS + operator 顯式 sign-off + 本 AMD 補件（live carve-out section） |

> **AC SoT 引用（FA-SF-2 + v0.4 patch per Wave 3a FA-#1 cosmetic finding）**：本 rollout table 的 PASS criteria 全文 = `docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md` §11 **AC-1..AC-19**（v0.2 寫 AC-1..AC-16；v1.2 加 AC-17/18/19；v1.3 修 AC-5/AC-11/AC-18 字面值）；本 AMD 不重複 AC 文字，避免雙文 drift。

**Rust struct cold-boot default**: `use_maker_close = false`（§5.6 fail-safe）。

**Kill-switch（任一觸發自動回 market）**：
- TOML hot-reload `use_maker_close=false` → ArcSwap 1 tick 內生效
- `close_maker_fail_rate > 50% over 5min` → IPC 自動 disable
- engine shutdown / authorization 失效 → cancel_token 觸發 best-effort cancel pending + 後續 close 走 market

---

## 4. phys_lock Live 分軌（不在本 AMD scope 內，DEFER）

**現狀**：
- demo: `risk_config_demo.toml:199` override `missing_edge_fallback_bps = 10.0`（EDGE-DIAG-1 對照實驗）→ Gate 1 pass → demo 7d 86 fires
- live (含 live_demo): 無 override → Rust default `-10.0`（exit_features/v2.rs:174-180）→ Gate 1 永遠 Hold → 7d 0 fires（**by design fail-safe**）

**本 AMD 不啟用 live phys_lock**。理由：
1. 啟用 = 跨 §5.6 fail-safe（同 sprint 引入 2 個 surface 行為改變，違反 one-flag-per-phase 模式）
2. close-maker-first 白名單包含 `phys_lock_gate4_*` 是「未來啟用後同步走 maker」的前置面，不需要當前 fire 樣本
3. `feedback_demo_loose_live_strict_policy` 政策：demo 放寬不要連帶放寬 live，反向亦真

**啟用時點**：close-maker-first Phase 2b PASS 後另開 PR，與 P0-EDGE-1 alpha-source 決策合併評估（QC math 佐證 + operator sign-off）。

### 4.1 V### Migration Hybrid Schema 強制決策（Consensus-MF-4 + MIT-SF-1/2）

**Migration slot**：**V094**（next-free；當前 max applied V093）。**File name**：`V094__fills_close_maker_audit.sql`（mirror V083 `V083__fills_partial_fill_columns.sql` 命名規範）。

**Hybrid schema design（明文，禁止 IMPL 階段分叉）**：

| 欄位 | 類型 | 載體 | 設計理由 |
|---|---|---|---|
| `close_maker_attempt` | `BOOLEAN NOT NULL DEFAULT FALSE` | **new column on `trading.fills`** | high-frequency group-by query（healthcheck [62] / [63] 都會 `GROUP BY close_maker_attempt`）；`partial index WHERE close_maker_attempt = true` 比 JSONB GIN 高效 100x（per MIT F-MIT-1 verified） |
| `close_maker_fallback_reason` | `TEXT NULL` (CHECK enum) | **new column on `trading.fills`** | enum allowlist 約束（CHECK constraint）+ healthcheck [63] NULL ladder 計算需獨立欄位；不適合 JSONB |
| `close_initial_limit_price` | `NUMERIC` | **`trading.fills.details` JSONB key** | 單筆 audit 讀取，無 group-by；JSON-column extension append-only（FA-MF-3 backward-compat） |
| `close_final_fill_price` | `NUMERIC` | **`trading.fills.details` JSONB key** | 同上 |
| `close_maker_eligible_reason` | `TEXT` | **`trading.fills.details` JSONB key** | 鏡像 trigger_tag，僅 audit 讀取 |

**enum allowlist（`close_maker_fallback_reason` CHECK constraint）**：
```
'timeout_taker',                    -- maker timeout fallback to market
'postonly_reject',                  -- EC_PostOnlyWillTakeLiquidity
'cancel_grace_expired',             -- 2s cancel ack grace 過期
'ack_lost',                         -- IPC ack 遺失，best-effort fallback
'rate_limit_pause',                 -- TooManyPending 觸發
'fast_escalate_safety_upgrade',     -- Race A：pending close + 新 risk trigger
'not_attempted_safety_path',        -- 走 market 真風控（Negative whitelist）
'engine_shutdown_safety',           -- cancel_token / authorization 失效
NULL                                -- close_maker_attempt = false 才允許 NULL（healthcheck [63] 不算 NULL）
```

**Linux PG dry-run mandatory**（per `feedback_v_migration_pg_dry_run.md` + V055/V083/V084 incident precedent）：
- E1 IMPL Mac 完成 → Linux PG **round 1**：`psql -f V094__fills_close_maker_audit.sql` + INSERT test data 驗 CHECK constraint reject 非 enum 值
- Linux PG **round 2**：再跑一次 V094，必須不 RAISE（idempotent verification）
- sqlx checksum verify：`bin/repair_migration_checksum` 處理 V094 file edit 後 DB checksum 同步
- E2 / E4 / A3 review 必含 Linux PG dry-run gate 證據 ID
- 禁 Mac mock pytest PASS = Linux PG runtime semantic PASS（V055 5-round loop 教訓）

**對應 V094 配套 healthcheck**：
- 新增 `[62] close_maker_fill_rate`（per Consensus-MF-2 Wilson-CI gate；spec §8.1）
- 新增 `[63] close_maker_fallback_audit`（per Consensus-MF-3 NULL ladder；spec §8.1）
- 新增 `[64] close_maker_rate_limit_pause_duration`（per BB-SF-1；spec §8.1）

---

## 5. Stage 0R Replay Preflight 對齊

**本 AMD 不啟動 Stage 0R 流程**（close-maker-first 是 execution-quality optimization，不是 alpha promotion；per §1 framing）。但需 mirror AMD-2026-05-15-01 的 evidence discipline：

| Stage | 對應 close-maker-first 階段 | Promotion authority |
|---|---|---|
| Stage 0 | 本 AMD draft 期 + IMPL 開發期（shadow） | none |
| Stage 0R | （N/A — replay 無法驗執行成本與 fill 行為） | （N/A） |
| Phase 2a | demo 7d 觀察（mirror Stage 1 demo micro-canary） | empirical demo evidence only |
| Phase 2b | live_demo 7d（mirror Stage 2） | empirical live_demo evidence only |
| Phase 3 | live (Mainnet)（mirror Stage 4 LIVE_PENDING） | operator + AMD 補件 |

> **W-AUDIT-8b Stage 0R 消歧（FA-SF-3）**：W-AUDIT-8b Funding Skew 的「Stage 0R Replay Preflight」是 **alpha-bearing pathway** 的 evidence gate（per AMD-2026-05-15-01 framing），與本 AMD 不適用 — 兩者命名相同但語義不同：W-AUDIT-8b Stage 0R = 「新 alpha 是否值得 demo micro-canary」；本 AMD 則純 execution-quality 不需 replay 驗 fill 行為。

### 5.1 Multiple Testing Protocol（QC-MF-1）

Phase 2a → 2b → 3 共 3 phase × 8 exit_reason × 2 env = **48 test points** 累積測試：每個 Phase × env × exit_reason cell 都會跑 AC-1..AC-16 評估 → 若各 cell 獨立檢驗無修正，cumulative false discovery rate 爆炸。

**強制採用**：**FDR 0.10 with Benjamini-Hochberg procedure**（不採 Bonferroni — 太嚴會卡死整個 Phase 1b；FDR 0.10 是 crypto research 通用 default）。

**實作**：
- Phase 2a / 2b / 3 結束時 PM + QC 聯合 produce «48-cell BH adjustment table»，輸出 q-value 後再判 PASS/FAIL
- p-value 對應的 statistical test：per-cell Wilson-CI 上下界（per Consensus-MF-2）vs Phase 1a baseline net_bps + fill_rate
- q < 0.10 cell → discovery（PASS 證據）；q ≥ 0.10 cell → 視為 NEUTRAL（不能宣稱 PASS）
- 該 PM cell 進 Phase 2b / Phase 3 promotion 前必審 BH table 完整性（無 cell 漏列、無 cherry-pick）

**Counterfactual cost simulation pre-IMPL evidence packet（QC-SF-2）**：IMPL 開發期間派 PA / E1 跑 historical 7d demo grid_close_short 數據 × estimated maker fill probability（per Bybit V5 BBO interaction model）× bootstrap CI，產出 «预计 fee saving range + 95% CI» 報告，作為 IMPL prereq 4-gate 之外的軟 evidence。

**Spread guard（QC-SF-4）**：spec §6 `compute_close_limit_price()` 補 `spread_bps > 50 → strict-skip`（與既有 PostOnly entry side `compute_post_only_price` 對齊）— 防 wide-spread book 下 maker 被吃成 worst-case slippage。

**Phase 2b holdout 顯著性（QC-SF-5）**：Phase 2a → 2b 不能直接 cross-validate；Phase 2b 必加 7d **fresh holdout** 評估（in-sample overfit 防護）。

**Retention / compression（MIT-SF-4）**：`trading.fills` 365d retention + 14d after compress 對 close_maker audit 跨 Phase 觀察足夠（columnar scan 不影響 audit query）；retention 不需要為本 AMD 改。

---

## 5.4 Race D Mitigation — Dynamic Backoff Per-Symbol（BB-MF-2）

**情境**：Bybit `EC_ReachMaxPendingOrders` (MakerRejectionCategory::TooManyPending) reject 觸發；當前 spec v1.0 設計「全域 5min pause」過度保守（Bybit V5 Order group 20 req/s per UID，rate-limit recovery 是 sub-second 級；5min 是 3000x overshoot，會 starve close path）。

**新規則（取代 5min global pause）**：

1. **Per-symbol dynamic backoff**：
   - 起始 backoff = **1s**
   - Binary exponential：每次同 symbol 連續 trigger TooManyPending → backoff `*= 2`
   - 上限 = **60s**
   - 重置條件：該 symbol 5min 內無 TooManyPending → backoff 重置 1s
   - 該 symbol close 路徑在 backoff 期間直接走 market；其他 symbol 不受影響

2. **Conditional global pause（防 cascade）**：
   - 若同一 1min window 內有 **≥ 10 個 distinct symbol 同時處於 backoff 狀態** → 升級全域 close maker pause 5min
   - 全域 pause 期間所有 symbol close 路徑走 market
   - 全域 pause 結束 → 所有 symbol backoff 重置 1s

3. **State 持久化**：
   - In-memory `HashMap<Symbol, BackoffState>`（per-symbol next_eligible_ms + consecutive_count）
   - 全域 `Option<u64>` global_pause_until_ms
   - engine restart 後重置（accepted trade-off：rate-limit state 不跨 process boundary）

4. **healthcheck `[64] close_maker_rate_limit_pause_duration` 對應**（BB-SF-1）：
   - per env 7d 累計 backoff time（per symbol sum + global pause sum）
   - per symbol > 5 min/day → WARN
   - per symbol > 30 min/day → FAIL
   - 全域 pause > 5 min/day → WARN
   - 全域 pause > 30 min/day → FAIL

5. **Audit row 標記**：
   - per-symbol backoff 觸發 → `close_maker_fallback_reason = "rate_limit_pause"`（既有 enum）
   - global pause 觸發 → `close_maker_fallback_reason = "rate_limit_pause"` + `details.rate_limit_scope = "global"` JSONB 子欄位

**IMPL 補丁**：spec v1.1 §5.4 對應更新 + spec §6.2 maker_rejection.rs 端 dispatch handler 增 backoff state 管理 + spec §9.2 新增 `close_maker_dynamic_backoff_tests.rs`（per-symbol exp backoff + global pause cascade）。

**估算 IMPL 工作量**：~50 LOC backoff state machine + ~80 LOC integration test。

**Pre-IMPL prove**：dispatch dry-run test 驗 binary exp 邏輯 + 10-symbol cascade 觸 global pause 行為。

---

## 6. compute_close_limit_price() Spec

**位置**：`srv/rust/openclaw_engine/src/strategies/common/maker_price.rs`（與 entry side `compute_post_only_price()` 同檔）。

**設計（PA Option C）**：
- 內部複用 `compute_post_only_price(is_long=close_direction_inverted, MakerPriceInputs, offset, buffer_ticks, ...)` strict-skip 模式
- per-exit_reason 變體通過 `buffer_ticks` + `offset_bps` + `timeout_ms` 三參數微調，不寫多套 algorithm
- strict-skip：BBO 不存在 / tick_size 不存在 / inverted price ≤ 0 / **`spread_bps > 50`** → return None → 回退 market（§5.6 fail-safe + QC-SF-4）

**Per-exit_reason 參數（QC-MF-2 修訂後）**：

| exit_reason | buffer_ticks | offset_bps | timeout_ms | 修訂理由 |
|---|---|---|---|---|
| grid_close_short / grid_close_long | 1 | 0.5 | 30000 | 翻轉信號，不急 |
| bb_mean_revert | 1 | 0.5 | 30000 | mean revert exit |
| ma_reverse_cross | 1 | 0.5 | 30000 | trend reverse |
| `phys_lock_gate4_giveback` | **1** | **0.5** | **15000** | **QC-MF-2 修正**：原 spec v1.0 給 `buffer_ticks=2 / offset=1.0 / timeout=30000ms` 反向擴大 slippage（gate4 fire 時已是 peak ATR giveback，價繼續逆的條件期望 `E[Y\|maker_pending] < X` 嚴格小於 market 立即鎖；buffer=2/offset=1.0 限價偏好更深 → 成交機率更低 → timeout fallback 更可能 → 吃更大 slippage）。修為 `buffer=1 / offset=0.5 / timeout=15000ms`，footnote ↓ |
| `phys_lock_gate4_stale_roc_neg` | 1 | 0.5 | 10000 | ROC<0 + stale 已偏弱（保留 spec v1.0 的 10s）|
| bw_squeeze / pctb_revert | 1 | 0.5 | 30000 | 樣本量低，conservative |

> **Footnote (QC-MF-2)**：phys_lock_gate4_giveback 的 timeout / buffer 參數選擇基於「gate4 fire condition 帶 unfavourable drift bias」— gate4 fire 時 peak ATR 已 surrender，下一秒價格繼續 unfavourable 的條件機率高於隨機 walk；故 maker pending 期 expected fill price 嚴格 worse than 立即 market；縮短 timeout + 收緊 buffer = 控制 unfavourable drift expose 視窗。

> **Footnote (QC-SF-1, AC-5 fee saving 推導)**：
> - Bybit fee tier 0 真實 maker = 2.0 bps / taker = 5.5 bps（per BB-SF-2 實測修正，原 spec 寫 1 bps maker 太樂觀）
> - 單筆 close fee delta = 5.5 - 2.0 = **3.5 bps**（不是 4.5 bps）
> - 假設 maker fill rate = 70%（mirror entry）→ avg fee saving per close = 3.5 × 0.70 = **2.45 bps**
> - 扣 fallback overhead（30% 走 market；估 0.30 × 6 bps timeout 期 adverse drift）= -1.8 bps
> - 淨估 close avg fee saving = 2.45 - 1.8 ≈ **+0.65 bps net**（保守）；高估：3.5 × 0.85 - 0.15 × 4 = +2.4 bps net
> - 因此 AC-5 應改 **改善 ≥ taker baseline 的 +1.5 bps（保守，不再是 +3 bps）**；spec v1.1 §11 同步改

> **Footnote (BB-SF-3, small-tick alt symbol corner case)**：`compute_close_limit_price()` 必須 handle small-tick 1000-prefix 合約（1000PEPEUSDT / 1000BONKUSDT 等）— 這些 symbol tick_size = 0.000001，buffer_ticks=1 對應只 0.000001 USDT 偏移，可能小於 BBO spread 而被 PostOnly reject `EC_PostOnlyWillTakeLiquidity`。E1 IMPL 補：若 `tick_size * buffer_ticks < spread_bps / 2 * mid_price` → 自動 widen buffer 到滿足 strict-skip 邊界，否則 strict-skip 走 market。

---

## 7. 16 條根原則合規

| 原則 | 判定 | 機制 |
|---|---|---|
| #1 單一寫入口 | PASS | close path 仍走 `execute_position_close → OrderDispatchRequest → order_dispatch_tx` 單通道 |
| #4 策略不繞風控 | PASS | DYNAMIC/TRAILING/TIME/HARD STOP/TAKE PROFIT/COST EDGE 強制保 market；§2.3 negative whitelist 明文 |
| #5 生存 > 利潤 | CONDITIONAL | `phys_lock_gate4_stale_roc_neg` timeout 10s / `phys_lock_gate4_giveback` timeout 15s（QC-MF-2）；AC-2 fallback ≤30%；新 AC: close_timeout_pre_stopout_rate ≤ 5% |
| #6 失敗默認收縮 | CONDITIONAL | cold-boot=false / live 預設不啟用 / 三段灰度 / kill-switch |
| #7 學習 ≠ 改寫 Live | PASS（強化）| **Non-training surface invariant（MIT-MF-1）**：`close_maker_attempt` / `close_maker_fallback_reason` / `close_initial_limit_price` / `close_final_fill_price` / `close_maker_eligible_reason` 是 **ops audit metadata**，禁餵任何 ML training pipeline（LinUCB / scorer / quantile / MLDE shadow / MLDE demo / DL3）。E3 grep guard rule 永久化（mirror §五 `replay.simulated_fills 'synthetic_replay'` precedent）：`grep -nrE '(linucb\|scorer\|quantile\|mlde\|dl3).*close_maker_(attempt\|fallback_reason\|initial_limit\|final_fill\|eligible_reason)' program_code/` 命中即 reject |
| #8 交易可解釋 | CONDITIONAL | `trading.fills` 新 column `close_maker_attempt` + `close_maker_fallback_reason` + `details` JSONB key 4 欄位（per §4.1 hybrid schema）；NULL ladder 0.1% / 1.0% threshold（per Consensus-MF-3） |
| #9 災難保護 | CONDITIONAL | cancel_token 觸發 cancel_resting_maker_order best-effort；authorization 失效 → 清 pending |
| #16 組合風險 | **MAINTAIN（v0.3 修正 per Wave 1 Track A3 verify finding）** | **per `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--f_fa_2_portfolio_var_exposure_sot_verify.md` empirical**：close path `is_reducing → return PositionCheck::allow()`（`risk_checks.rs:137-138`）**根本不觸 portfolio gate**；real systemic gap 在 entry-side resting maker 不入 `compute_correlated_exposure_pct` / `compute_exposure_pct`（`intent_processor/mod.rs:761-805` 只讀 PaperPosition.qty filled，不讀 paper_state.resting_orders）。close-maker-first IMPL **不引入新 portfolio risk vector**，僅繼承 entry-side resting maker Phase 1B-4.2 既有 systemic gap。**新 P1 ticket `P1-PORTFOLIO-RESTING-EXPOSURE-1` 平行 IMPL，不阻 Phase 1b**（per A3 推薦選項 A，PM 已預批；ticket scope 見 spec §15）。原 v0.2 「maker pending 期 portfolio_var 用 request_qty」framing 由 A3 verify 證實方向反了：close pending 對「後續 NEW open intent」是 OVER-estimate（不是 under-estimate）；entry pending 才是 under-estimate scenarios |
| #3 AI 輸出 ≠ 即時命令 | **PASS（v0.4 明列 per Wave 3a FA-#4 cosmetic finding）** | close maker dispatch 仍走 `OrderDispatchRequest` 單通道（與 entry maker 對偶）；不繞 GovernanceHub / Lease 鏈；PostOnly Limit + maker_timeout_ms 是 execution-quality optimization，不引入 AI 直接下單路徑 |
| #11 Agent 最大自主權 | **PASS（v0.4 明列 per Wave 3a FA-#4 cosmetic finding）** | exit_reason whitelist + carve-out 不影響 Agent 自主決定 timing / symbol / 策略；`use_maker_close` per-strategy TOML flag 是 execution-quality 配置，不限制 Agent 自主邊界（P0/P1 風控不變）|
| #13 AI 資源成本感知 | **PASS（v0.4 明列 per Wave 3a FA-#4 cosmetic finding）** | close-maker-first 純 execution-quality optimization 不增 AI 調用；`COST EDGE: ratio X >= 0.80` reason 在 §2.3 Negative Whitelist 強制 market（觸發即收倉，maker 未成交違反 cost gate semantic）|
| #15 多 Agent 協作 | **PASS（v0.4 明列 per Wave 3a FA-#4 cosmetic finding）** | 不變動 5-Agent 架構（Scout / Strategist / Guardian / Analyst / Executor）；不變動 Conductor 編排；不引入新 agent 通信 topic；新 audit 欄位純 ops metadata（per #7 invariant）|
| 其他 | PASS / 不觸 | — |

### 7.1 9 條安全不變量 mini-table（FA-SF-1）

per `srv/CLAUDE.md §四` SoT 對齊：

| # | 不變量 | 本 AMD 判定 | 機制 |
|---|---|---|---|
| 1 | Pre-trade audit/replay 必開 | PASS | close path 仍走 dispatch.rs；新 audit 欄位寫 fills.details + new column |
| 2 | Lease 必在執行前已 acquired | PASS | close path 不依賴 lease（per spec §2.3 W-C Caveat 2）|
| 3 | 執行回報必落 fills 表 | CONDITIONAL | V094 hybrid schema 新欄位 + NULL ladder 0.1%/1.0%（per Consensus-MF-3）|
| 4 | 風控降級 → engine 自動止血 | PASS | Negative whitelist 明文 fail-safe 走 market |
| 5 | Authorization 過期 → engine cancel_token | PASS | spec §5.4 + AC-9 cancel pending on shutdown |
| 6 | Mainnet 無 OPENCLAW_ALLOW_MAINNET → spawn 拒絕 | PASS | 不觸（本 AMD 不改 spawn 邏輯）|
| 7 | Bybit retCode != 0 → fail-closed 不重試 | PASS | maker_rejection.rs PostOnlyCross / TooManyPending 走 market 不重 quote |
| 8 | Reconciler 對賬差異 → 自動降級 paper | PASS | 不觸（本 AMD 不改 reconciler）|
| 9 | Operator 角色與 live_reserved 缺一即拒 | PASS | 不觸（本 AMD 不改 auth 邏輯）|

**結論**：9/9 PASS or PASS-with-stated-mitigation；**無 BLOCKER**（FA round-1 + round-2 verified）。

### 7.2 W-C Caveat 2 不變式明文（FA-MF-2）

**Carve-out**：close path 不寫 spine lineage（commands.rs:809-815）；新 audit 欄位走 **`trading.fills` 對應 column + `details` JSONB**，**不**走 spine lineage 鏈。

**意涵**：
- IMPL agent 禁誤把 `close_maker_attempt` 等欄位 INSERT 到 `agent_spine.execution_plans` / `agent_spine.lease_lineage` 等表
- F-FA-3 對應 lineage contract guard test：grep `agent_spine` writer code 確認沒任何 `close_maker_*` field 出現
- 對齊 MAG-082 W-C Caveat 2 evidence mode（spine shadow lineage 邊界，per `docs/governance_dev/2026-05-08--w_c_lease_router_authorized.md`）

---

## 8. IMPL Prerequisites（6-gate AUTH，從 4 升 6）

**所有條件必滿足才能進 IMPL**：

1. ✅ PA spec finalize（`docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md` v1.1）
2. ⏳ 本 AMD v0.2 經 **QC + FA + BB + MIT 4-agent 並行 short re-review** 確認 17 must-fix + 14 should-fix 收口完整
3. ⏳ 三閘全過：
   - P0-EDGE-1 closed（[40] negative realized edge resolved）
   - W-AUDIT-8b Stage 0R passed（funding skew empirical evidence）
   - W-AUDIT-8a C1 BB/MIT sign-off（24h liquidation proof passed）
4. ⏳ 強制工作鏈：PA spec → E1 並行（A/B/C/D/E 5 worktree）→ E2 review → E4 regression → QA → PM sign-off。**不走 P0 快速通道**
5. ✅ **F-FA-1 + F-FA-2 + F-FA-3 P1 finding pre-IMPL（FA-MF-1）全 RESOLVED（v0.3.1 update）**：
   - ✅ **F-FA-1 DONE Wave 2a Track A2** (commit `9b1117a0`)：V094 hybrid schema migration spec finalize ✅；spec land `srv/docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md` (1176 LOC / 15 sections)；含 (a) V094 SQL design + Guard A/B/C + enum allowlist 10 values（spec/AMD 8 + 本 spec 補 2: rate_limit_backoff_per_symbol + fallback_to_taker_mandatory）+ (b) trading_writer.rs upgrade spec + TradingMsg::Fill enum 21→24 fields + 13 caller sites enumeration + (c) Linux PG empirical schema verify + dry-run × 2 round protocol + sqlx checksum repair SOP + healthcheck [62][63][64][65] integration spec + Backward-compat append-only + Rollback paths；3 critical empirical findings（trading.fills.details JSONB 已存在 V003 line 284 / 24h 98 fills 0% details rate / Linux runtime applied max V90 not V93）；PA verdict report `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--v094_schema_migration_spec_pa_verdict.md` (commit `14a561ec`)
   - ✅ **F-FA-2 DONE Wave 1 Track A3** (commit `96995b61`)：portfolio_var exposure 計算 SoT verify ✅；verdict = **MAINTAIN + 新 P1 ticket `P1-PORTFOLIO-RESTING-EXPOSURE-1` 平行 IMPL**（per A3 推薦選項 A，PM 已預批）；A3 verify 揭示 close path `is_reducing → allow()` 不觸 portfolio gate，real systemic gap 在 entry-side resting maker（Phase 1B-4.2 既有），ticket scope 見 spec §15；v0.2 原 framing「maker pending 期間用 `request_qty` 不用 `filled_qty`」由 A3 修正方向反了
   - ✅ **F-FA-3 DONE Wave 1 Track A4** (commit `a5a7107c`)：audit 欄位不走 spine lineage guard tests 設計 ✅；4 integration test specs + 6 grep guard patterns + V094 schema 兩段式（hot column 2 + JSON extension 3）+ healthcheck [63] dual-gate 設計 + writer gap explicit（`trading_writer.rs:430` INSERT 漏 details，V094 IMPL 必同步升 writer 寫 details payload）；E1 IMPL prereq 解後 E4 直接照 spec 寫 ~30-50 LOC test code
6. ⏳ **`reject_cooldown` entry/close 拆分升 P0 priority pre-Phase 2a Demo enable 必 land（BB-MF-3）**：
   - **問題嚴重度提升**：當前 `reject_cooldown_until_ms` 不分 entry/close（grid_trading/signal.rs:152-158 per-symbol cooldown），entry side 觸 rate-limit-adjacent 條件後 → close path silent degradation 永遠走 market（失去整個 maker 優化價值）
   - **必拆**：`reject_cooldown_entry_until_ms` + `reject_cooldown_close_until_ms` 兩個獨立 map
   - **Priority**：原 spec §15 後續工作項 by-the-way scope-in 升為 **P0 IMPL prereq**；E1-D ticket 在 Phase 2a Demo enable 前必 merged + Linux runtime 驗 entry/close cooldown isolation
   - **驗證**：`event_consumer/cooldown_isolation_tests.rs` 新增 entry reject 不影響 close path regression test

---

## 9. Removed Path（顯式禁止）

- ❌ Close path 不走 W-AUDIT-9 Stage 0R replay preflight（不適用：execution-quality optimization 非 alpha promotion；per §1 framing + §5 消歧）
- ❌ 不在 W3 active scope 內 implement（PM 拒 W3 scope-in；queue Sprint N+2 P1 backlog）
- ❌ 不走 P0 快速通道（FA / E5 / E3 / CC 不可省）
- ❌ 不在本 AMD 內啟用 live phys_lock（DEFER 至 Phase 2b 後另 PR）
- ❌ 不修改 stop_manager / reconciliation engine / paper_state/resting_orders 任何代碼
- ❌ 不依賴 Phase 1B-4.2 完整實裝（PA verified 0 dependency）
- ❌ 不餵 close_maker_* 任何欄位到 ML training pipeline（MIT-MF-1 永久 invariant）
- ❌ 不寫 close_maker_* 到 `agent_spine.*` 任何 table（W-C Caveat 2 carve-out）
- ❌ 不寫 close_maker_* 到 `replay.simulated_fills`（per spec §五 `replay.simulated_fills 'synthetic_replay'` non-training tier 對齊；MIT-SF-8 P2 backlog）

---

## 10. Rollback Path

| 時機 | 動作 |
|---|---|
| Phase 2a demo 觀察 FAIL | TOML hot-reload `use_maker_close=false` → 1 tick 內回 market；FA / QC root cause review；spec 修訂或 reject |
| Phase 2b live_demo FAIL | 同上 + DOC-08 §12 incident response |
| Phase 3 live regression | operator-triggered kill-switch + AMD 補件回溯 |

回滾路徑 100% 走原 hard-coded market 路徑（已存在，零改動），**無 schema migration 回滾需求**。

### 10.1 V094 Backward-Compat Clarify（FA-MF-3）

**Append-only 設計**：
- V094 加 2 new column on `trading.fills`（`close_maker_attempt` / `close_maker_fallback_reason`）+ `details` JSONB key 3 個（`close_initial_limit_price` / `close_final_fill_price` / `close_maker_eligible_reason`）
- 既有 fills row 在 V094 apply 後：new column 取 default 值（`close_maker_attempt = FALSE`、`close_maker_fallback_reason = NULL`），既有 `details` JSONB 不被觸碰
- **不破現有 SELECT / INSERT / UPDATE**：V094 純粹 ADD COLUMN + ADD CONSTRAINT，沒 ALTER existing column type / DROP column / RENAME column
- 既有 healthcheck 未引用新欄位 → 0 影響；新 healthcheck [62]/[63]/[64] 全為 V094 配套

**回退場景**：
- 若 Phase 2a / 2b FAIL 必須 disable feature → TOML flip 即可，**V094 schema 不需要 rollback**（new column 留著，只是後續 fills row `close_maker_attempt` 全 FALSE）
- 若必須 rollback V094 schema（極端場景）→ DROP COLUMN + DROP CONSTRAINT 是純物理操作，不影響歷史 row 邏輯一致性
- **如果 IMPL 階段 PA 改設計從 hybrid 變成 separate column（即 `close_initial_limit_price` 等也走 new column）→ 必重評 backward-compat 影響 + 重派 4-agent review**

**v0.4 IMPL kickoff 必含項（per Wave 1 Track A4 finding §4.4 + Wave 3a FA-#2 cosmetic finding）**：
- IMPL kickoff 必含 `trading_writer.rs:430` details payload writer 升級（per Wave 2a Track A2 V094 spec §6 trading_writer.rs upgrade）—  避免 5 audit 欄位中 3 個 JSONB key 100% NULL fail 風險（24h 98 fills 0% details rate empirical confirmed）
- TradingMsg::Fill enum 21 → 24 fields；13 caller sites enumeration；E2 grep verify 39 hit count
- 兩段式 schema invariant（hot column 2 + JSON extension 3）IMPL phase 不可變更

---

## 11. Verdict from Source Audits

- **PM**: APPROVED-CONDITIONAL（Sprint N+2 P1，非 P0；6 IMPL 條件；6 governance gates；MA KAMA fix scope-in W3-6 by-the-way）
- **PA**: READY-FOR-SPEC（1 NEEDS-PROBE on rate-limit；0 BLOCKED-BY-1B-4.2；估 ~985 LOC, 7-9 E1-day, 3-5 worktree 並行）
- **FA round-1**: APPROVED-CONDITIONAL（5 conditions：negative whitelist 顯式 / cold-boot=false / audit 欄位 V### migration / cancel pending on shutdown / request_qty exposure 確認）
- **QC round-2**: APPROVED-CONDITIONAL（4 must-fix：framing / multiple testing / phys_lock timeout / sample-size + Wilson CI）
- **FA round-2**: APPROVED-CONDITIONAL（4 must-fix：F-FA-1/2/3 prereq / W-C invariant / V### backward-compat / framing）
- **BB round-2**: APPROVED-CONDITIONAL（5 must-fix：dictionary doc / dynamic backoff / reject_cooldown P0 / classifier reuse / reject sample healthcheck）
- **MIT round-2**: APPROVED-CONDITIONAL（4 must-fix：hybrid schema / Wilson sample-size / NULL ladder / non-training invariant）

**Consolidated verdict（4-agent → AMD v0.2）**：4/4 APPROVED-CONDITIONAL，0 REJECT；17 must-fix + 14 should-fix 全部 integrated；patch 無爭議性新風險 → 待 PM 派 4-agent short re-review 確認收口。

### 11.1 Wave 1 Source Audits（v0.3 新增）

post-AMD v0.2 land 後 Wave 1 並行派 5 track（A1/A3/A4/E1/E3），結果：
- **PA Track A1 v0.2/v1.1 patch**：commit `2e7a1b2f` — 17 must-fix + 14 should-fix consolidated patch land
- **PA Track A3 portfolio_var verify**：commit `96995b61` — verdict **MAINTAIN + 新 P1 ticket option A**（PM 已預批；§7 #16 由 CONDITIONAL → MAINTAIN）
- **PA Track A4 W-C Caveat 2 guard tests**：commit `a5a7107c` — 4 integration test specs + 6 grep guard patterns + V094 schema **兩段式**（hot column 2 + JSON extension 3）+ writer gap explicit（trading_writer.rs:430 INSERT 漏 details）
- **PA Track E3 maker fill baseline**：commit `b98706d5` — fee saving 4.5 → 0.5-2.0 bps net per close attempt（per empirical 0.66/0.95/3.31 三層解讀）+ no-fallback-to-taker gap identified（entry 70% PostOnly timeout 直接放棄，close 不可繼承）
- **E1 KAMA fallback gate**：commit `9df44183` — W3-6 by-the-way 完成（debug → warn + skip entry when KAMA unavailable）

**Consolidated verdict（Wave 1 → AMD v0.3）**：5/5 land；2 substantive new findings（A3 + E3）trigger Wave 1.5 spec v1.2 + AMD v0.3 patch；patch 純增量無 reverse decision → 待 Wave 3 4-agent short re-review on AMD v0.3 + spec v1.2 確認收口。

---

## 12. 變更歷史

| 日期 | 版本 | 變更 | 作者 |
|---|---|---|---|
| 2026-05-15 | v0.1 DRAFT | 初版 — pending QC+FA+BB+MIT 4-agent adversarial review | Main session |
| 2026-05-15 | v0.2 | 4-agent review consolidated patch — 17 must-fix（4 consensus + 13 unique）+ 14 should-fix 全 integrated；§1 framing 改 alpha-impact-adjacent execution-quality；§4.1 V094 hybrid schema explicit；§5.1 multiple testing FDR 0.10 BH；§5.4 dynamic backoff per-symbol → conditional global；§6 phys_lock_gate4_giveback timeout 30→15s + buffer 2→1；§7 #7 non-training invariant + §7.2 W-C Caveat 2 explicit；§8 IMPL prereq 4→6（含 F-FA-1/2/3 + reject_cooldown split P0）；§10.1 V094 backward-compat clarify | PA per main-session 派 Wave 1 Track A1 |
| 2026-05-15 | v0.3 | A3+E3+A4+E1 finding consolidated post-Wave 1（fee revision + race fallback gap + portfolio MAINTAIN + IMPL Prereq 5 partial-resolved）— §1 footnote per E3 fee saving revised 4.5 → 0.5-2.0 bps + 全年估 $50-$200；§3 Phase 2a 7d → 14d (7d primary + 7d extended observation) + Phase 2b 啟動條件加 AC-18 + AC-19；§7 #16 組合風險 CONDITIONAL → MAINTAIN per A3 verify finding（close path is_reducing 不觸 portfolio gate；新 P1 ticket option A PM 預批）；§8 IMPL Prereq 5 partial-resolved（F-FA-2 ✅ Wave 1 Track A3 commit `96995b61` + F-FA-3 ✅ Wave 1 Track A4 commit `a5a7107c`；F-FA-1 V094 spec 留 Wave 2 dispatch）；§11.1 NEW Wave 1 Source Audits 5 commit 引用（A1/A3/A4/E1/E3）| PA per main-session 派 Wave 1.5 (post-Track A3+E3) |
| 2026-05-15 | v0.3.1 | F-FA-1 ✅ DONE Wave 2a Track A2 patch（V094 hybrid schema migration spec finalize land commit `9b1117a0` + PA verdict report `14a561ec`）— §8 IMPL Prereq 5 第 1 子條件 marker 從 ⏳ → ✅；spec 1176 LOC / 15 sections 含 schema design + Guard A/B/C + Linux PG dry-run × 2 round + sqlx checksum repair SOP + trading_writer.rs upgrade + TradingMsg::Fill enum 21→24 fields + 13 caller sites enumeration + healthcheck [62][63][64][65] integration + Backward-compat append-only + Rollback paths；3 critical empirical findings（trading.fills.details JSONB 已存在 V003 line 284 / 24h 98 fills 0% details rate / Linux runtime applied max V90 not V93 — spec/AMD wording drift caveat noted）；enum allowlist 補 2 值（rate_limit_backoff_per_symbol + fallback_to_taker_mandatory）upgrade spec/AMD 8 → 10 superset；F-FA-1/2/3 全 ✅ → IMPL Prereq 5 全 RESOLVED | PA per main-session 派 Wave 2 (Track A2) |
| 2026-05-15 | v0.4 | Wave 3a 4-agent short re-review consolidation — QC + FA + BB + MIT 4/4 verdict（QC APPROVED-CONDITIONAL 1 NEW MUST QC-MF-3 + 1 NEW SHOULD QC-SF-6；FA APPROVED 4 cosmetic；BB APPROVED `2026-05-15--amd_v0_3_spec_v1_2_bb_short_re_review.md` 5/5 must + 3/3 should 全 land + v1.2/v0.3 增量無新 Bybit-side risk；MIT APPROVED 2 P3 advisory）。本 patch 純 numerical / cosmetic 增量無新風險 → IMPL Prereq 條件 2 SATISFIED：(a) §3 rollout table AC SoT 引用「AC-1..AC-16」→ **「AC-1..AC-19」** (per FA-#1 cosmetic) + (b) §10.1 V094 backward-compat 加 IMPL kickoff 必含項「`trading_writer.rs:430` details payload writer 升級」+ TradingMsg::Fill enum 21→24 + 兩段式 schema invariant (per FA-#2 + Wave 1 Track A4 §4.4) + (c) §2.3 negative whitelist 真風控行補 PA 識別變體 `risk_close:fast_track*` / `halt_session*` (per FA-#3，spec §4.3 已列；AMD 同步) + (d) §7 16 原則表補 #3/#11/#13/#15 明列 PASS（治理 trace 完整度 7/12 → 11/12, per FA-#4） | PA per main-session 派 Wave 1.5b (Wave 3a re-review consolidation) |

**下一步**：IMPL Prereq 條件 2 SATISFIED（4-agent re-review 4/4 verdict + Wave 1.5b spec v1.3 + AMD v0.4 patch 收口）；條件 5 全 RESOLVED（F-FA-1 + F-FA-2 + F-FA-3 全 ✅）；條件 6 reject_cooldown split 在 Wave 2b E1 progress；條件 3 三閘（P0-EDGE-1 / W-AUDIT-8b / W-AUDIT-8a C1）等待 → Wave 3b BB 字典 6 處更新（並行）→ Wave 3.5 PA 補 Linux V81/V91/V92/V93 backlog migration apply 檢查（per V094 spec §4.4 caveat）→ IMPL kickoff Wave 4（3-gate + 條件 6 解後派 E1 5-worktree）。
