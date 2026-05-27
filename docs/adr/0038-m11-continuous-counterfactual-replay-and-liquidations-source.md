# ADR 0038: M11 Continuous Counterfactual Replay — Self-Hosted PG `market.liquidations` As Historical Source

Date: 2026-05-21
Status: **Proposed-pending-commit**（v5.8 §2 M11 module ADR 級落地；BB 5.21 audit push back 落地：「Bybit historical liquidations REST API 不存在」→ M11 nightly replay 必用自家累積 PG `market.liquidations` table，不依賴 vendor optionality）
Operator Sign-off: 2026-05-21（主會話 PM dispatch via v5.8 §2 M11「Continuous Counterfactual Replay + nightly source」)
Related: v5.8 §2 M11 / ADR-0017 (Scanner is evidence not authority — runtime decision 不依賴 vendor-side history) / ADR-0029 (market.public_trades + orderbook_l2_snapshot storage policy — trade tape baseline) / ADR-0034 (Decision Lease Layered Approval LAL — replay window 擴展受 LAL 2 約束) / v5.7 §6 market.liquidations writer existing / `docs/references/2026-04-04--bybit_api_reference.md` (Bybit V5 API surface — historical liquidations 不存在 confirmation) / BB C6 PROOF PASS memory project (`project_decision_outcomes_not_dead` — `market.liquidations` 31,473 rows 已驗) / V107 schema spec (placeholder pending CR-7) / V109 anomaly schema (per CR-7 M11+M7 dedup contract)

## Context

### 起源

v5.8 §2 M11 將 v5.7 baseline 的「Stage 0R replay one-time preflight」升級為 **continuous nightly counterfactual replay**：

```
Nightly job:
  1. Pull last 24h of market data
  2. Run all live strategies through replay engine with same data
  3. Compare replay-decided vs production-executed trades
  4. Flag divergences (PnL / decision count / slippage bps)
```

v5.8 §2 M11 **沒有明寫**「historical market data 從哪裡 pull」。Naive 假設是「從 Bybit historical REST API 拉」。BB 5.21 audit 在 v5.8 dispatch consolidation review 中 catch 到一個結構性 gap：

> **Bybit historical liquidations REST API 不存在**。Bybit V5 liquidations 只在 WebSocket push event 形式提供（per `docs/references/2026-04-04--bybit_api_reference.md` line 1088-1092；2026-04-05 已知 `liquidation.{symbol}` 已移除避免 broken topic 毒化整個 WS 連接，2026-05-15 W-AUDIT-8a C1 確認 `allLiquidation.{symbol}` 是 Bybit V5 official topic 但 production 未訂閱）。**無 historical batch query endpoint**。

若 M11 nightly replay 假設可從 Bybit historical API 拉 liquidations 歷史 → 永遠拉不到 → replay 在 liquidation-sensitive strategy（如 funding_arb spike detection / bb_breakout absorption）的 fidelity 必然斷裂。（注：funding_arb 已 retired per AMD-2026-05-26-01；此處保留作為 liquidation-sensitive strategy 範式說明，replay fidelity 議題對 bb_breakout 及未來 ADR-0046 funding_arb 重設計仍適用。）

### 既有 v5.7 §6 self-hosted `market.liquidations` writer

v5.7 §6 已落地 `market.liquidations` 寫入路徑：

- WS subscription baseline：**production 未訂閱**（per BB W-AUDIT-8a C1 spec — `allLiquidation.{symbol}` 在 24h BB proof PASS + MIT schema sign-off 前不入 production subscription list）；但 schema 已存在
- BB C6 PROOF PASS memory（per `project_decision_outcomes_not_dead`）：實際 **31,473 rows accumulated** 已驗（透過 historical backfill 路徑 + 部分 WS sampling 累積）
- 預期 v5.8 M11 期間 W-AUDIT-8a C1 結束後 production 訂閱 enabled，往後 rolling 累積

### 為什麼這形成 ADR 級治理決策

如果 M11 dispatch 時不明寫「historical source = self-hosted PG `market.liquidations`」：

1. **PA / E1 IMPL 時誤判** — 可能假設「等 Bybit 開 historical API」或「找第三方數據源（CoinGecko / Coinglass）」，浪費 sprint bandwidth 在 vendor optionality
2. **跨 sub-agent review drift** — 不同 review surface 對「historical source」假設不一致，downstream evidence chain 斷裂
3. **違反 ADR-0017 scanner-is-evidence-not-authority 原則** — runtime decision（即使是 replay 也是 decision-graph）不可依賴 vendor-side history；vendor API 可能 rate limit / ToS 限制 / 突然關閉

本 ADR 把「self-hosted PG only」立場鎖入治理紀律。

### 為什麼 historical source 範圍不僅 liquidations，而是「所有 market.* 數據」

BB push back 的核心 insight 是「**vendor historical query 永遠不可作為 production replay dependency**」，不限 liquidations：

- `market.public_trades`（per ADR-0029 trade tape policy）— Bybit `/v5/market/recent-trade` REST 有 1000-trade rate limit + 不可重建 14d 歷史
- `market.orderbook_l2_snapshot`（per ADR-0029 L2 snapshot policy）— Bybit historical orderbook endpoint 不存在
- `market.market_tickers` / `market.kline_*` — historical OHLCV 雖然 Bybit 提供 REST endpoint，但 rate limit + 為 production replay 跑 daily query 違反 vendor relationship 紀律
- `market.liquidations` — 本次 BB 5.21 audit 焦點

故本 ADR Decision 1 範圍**統一立場 = M11 nightly replay 所有 `market.*` historical query 限制到 self-hosted PG**。

### v5.8 §2 M11 4h budget + 5 strategy × all live symbols 約束

M11 spec 隱含資源預算：「24h replay 完整 5 strategy × all live symbols」必須在 nightly cron window 完成。E4 audit 對 4h wall-clock 提出資源邊界要求（per `feedback_v_migration_pg_dry_run.md` Linux runtime dry-run 紀律 + `project_hardware_constraints` 128GB 統一記憶體 / PG 4-8GB shared_buffers 限制）。

若用 vendor API：
- Bybit REST rate limit 全 cohort 1d historical kline / liquidations / orderbook 拉取 = 預估 6-10h（即使無 rate limit 都超 budget）
- vendor API timeout / 503 episodic failure 不在我方控制範圍 → replay 不可重現

self-hosted PG query 在 4-8GB shared_buffers 限制下 + TimescaleDB hypertable + Track-based attribution 既有 compression pattern 估算可在 1-2h 完成；4h budget 有 buffer。

### v5.8 CR-7 M11+M7 dedup contract 的對齊要求

v5.8 dispatch consolidation report `2026-05-21--v58_dispatch_consolidation.md` CR-7 明示「M7 strategy decay detection 與 M11 replay divergence 必須 dedup」：

- M7 是 **single decay authority**（一次決定 strategy demote / param shrink / cooldown）
- M11 divergence 是 **input source** to M7（CRITICAL divergence 升級為 M7 input），**不**作 independent demote
- 這意味本 ADR Decision 3 divergence threshold 設計必須與 M7 對齊：M11 不可在 CRITICAL threshold 跨過時自行 demote strategy，只能 emit M7 input + Slack alert + 紀錄到 `replay_divergence_log`

### v5.7 ADR-0029 trade tape policy 與本 ADR 關係

ADR-0029 落地 `market.public_trades` + `market.orderbook_l2_snapshot` 為 fidelity 升級 schema；本 ADR Decision 1 **延伸**該政策到「historical source 統一治理」：

- ADR-0029 焦點：fidelity uplift（tick-level trade tape + L2 snapshot 替換 BBO-cross-proxy）
- 本 ADR 焦點：sourcing posture（self-hosted PG only，禁止依賴 vendor historical query）

兩者**正交並存**；ADR-0029 schema 落地後本 ADR Decision 1 範圍自動覆蓋新表（all `market.*` namespace 統一）。

## Decision

**Proposed**：以下 5 個治理立場 + 工程 scope 落地為 ADR 級規範。本 ADR 不 commit V107 schema 細節（待 CR-7 dedup contract finalize 後 promote 至 Accepted）；本 ADR 為**設計意圖 + 治理基線**的鎖定。

### Decision 1 — M11 Nightly Replay Historical Source = Self-Hosted PG（禁依賴 vendor optionality）

| 元素 | 設計 |
|---|---|
| 規則 | M11 nightly replay 任何 historical `market.*` query 限制到 self-hosted PG `market.*` namespace |
| 涵蓋範圍 | `market.liquidations` / `market.public_trades`（per ADR-0029）/ `market.orderbook_l2_snapshot`（per ADR-0029）/ `market.market_tickers` / `market.kline_*` / `market.trade_agg_1m` / `market.ob_snapshots` / `market.binance_*`（per ADR-0033 Y1 Binance market data Y1 接入後對齊同 policy）|
| 禁止 | (a) 為了 M11 retroactive backfill 而向 Bybit historical API request（即使該 API 對某數據類型存在如 kline）(b) 採第三方數據源（CoinGecko / Coinglass / Glassnode）作為 replay primary source (c) 任何 cross-exchange historical query（Binance historical 即使 Y1 market-data 接入也只走 self-hosted accumulation）|
| 為什麼 | (1) ADR-0017 scanner-is-evidence-not-authority — runtime decision 不依賴 vendor-side history；replay 是 decision-graph 重放也適用 (2) vendor API rate limit + ToS 不在我方控制範圍，不可作 production dependency (3) 30d+ historical 在 self-hosted PG 已累積（per BB C6 PROOF PASS `market.liquidations` 31,473 rows 已驗；ADR-0029 trade tape land 後同 pattern）(4) 4h wall-clock budget 在 vendor API rate limit 下不可達 |
| 例外 | M11 ADR-level approval 後 enabled 但本 ADR 不預判：**首次 cold start** 場景下，新 strategy 在 self-hosted PG 累積期不足時，**仍走 self-hosted PG with degraded sample** + Slack warn；不允許暫時走 vendor backfill 補洞 |

### Decision 2 — Replay Window 約束 + LAL 2 對齊

| 元素 | 設計 |
|---|---|
| 默認窗口 | **Last 24h**（T-24h → T-0h）— per v5.8 §2 M11 default |
| 擴展窗口要求 | 任何 > 24h replay window（如 last 7d backtest / 30d regression）必經 LAL 2（cross-strategy reweight）等級 approval（per ADR-0034 Decision 3 Y1 LAL 2 = Advisory mode + operator review；Y2 conditional auto with gate）|
| 為什麼 | (a) 24h window 是 v5.8 §2 M11 spec 默認，超出範圍是「結構性 strategy review」非「nightly hygiene」(b) 7d+ replay 計算成本顯著（per 4h budget §Decision 5）；不該 silent expand (c) 多策略 cross-window backtest 涉及 LAL 2 cross-strategy reweight 領域，必走 ADR-0034 governance |
| 數據可得性約束 | replay window 不可超過 `market.*` retention policy：per ADR-0029 OQ-3 候選「public_trades 30d-90d retention / orderbook_l2_snapshot 30d retention」；超出 retention window → degraded sample + warn 不抛 error |

### Decision 3 — Divergence Threshold（per CR-7 M11+M7 dedup contract，3 級 statistical derivation）

**重要**：閾值是**統計推導**得到，不是 ad-hoc 拍腦袋；threshold derivation 走 5d empirical baseline → mean + σ multiplier 路徑。

| 級別 | Threshold 定義 | 行為 |
|---|---|---|
| **NOISE floor** | 5d empirical mean Δ + 0.5σ（5d rolling 取每日 replay_pnl vs live_pnl Δ 的 mean + 0.5 標準差）| 不記 log（避免 daily noise 灌爆 V107 表）|
| **WARN** | 5d empirical mean Δ + **2.5σ**（覆蓋 99.4% normal distribution; ~0.6% false positive expected）| emit `replay_divergence_log` row with `divergence_level='WARN'` + Slack daily digest（不打斷 nightly run）|
| **CRITICAL** | 5d empirical mean Δ + **3σ**（覆蓋 99.7%; ~0.27% false positive expected）| emit log + Slack immediate alert + **升級為 M7 input**（**不**作 independent strategy demote，per CR-7 M7 為 single decay authority）|

#### 3σ 統計推導理由（QC pending review）

- **2.5σ vs 3σ 為什麼分開** — 2.5σ 是 day-to-day operational warn（每月 ~2 次 WARN 是 acceptable noise level）；3σ 是 strategy decay signal（每月 ~0.7 次 CRITICAL 已是 unusual 信號值）
- **為什麼用 σ 而非絕對 bps** — 不同 strategy / symbol scale 不同（grid 日 PnL volatility 與 bb_breakout 差 5-10x）；絕對 bps threshold 會 over-flag low-vol strategy / under-flag high-vol strategy
- **為什麼 5d rolling baseline 而非 longitudinal mean** — strategy regime 變化下（如 funding cycle flip / volatility regime shift）long-window mean 對近期偏離不敏感；5d 是 short enough to capture regime + long enough to smooth daily noise
- **QC review 範圍** — (a) 5d baseline 在 strategy cold start 期（< 5d data）的 fallback 策略 (b) 不同 strategy（grid vs bb_breakout vs funding_arb）是否需 per-strategy σ 還是全 cohort 統一 σ；funding_arb retired per AMD-2026-05-26-01，QC review 對 ADR-0046 future redesign slot 仍適用 (c) σ 對 outlier-driven distribution 的 robust 替代（如 MAD-based threshold）

#### CRITICAL → M7 dedup 路徑（per CR-7）

```
M11 CRITICAL divergence detection
  ↓
emit replay_divergence_log row (level=CRITICAL)
  ↓
Slack immediate alert (operator awareness)
  ↓
emit M7 strategy_decay_input event (NOT auto-demote)
  ↓
M7 single decay authority decides: demote / param shrink / cooldown / accept
  ↓
M7 decision 走 ADR-0034 LAL 1（intra-strategy reparam）或 LAL 2（cross-strategy reweight）路徑
```

**M11 不可在 CRITICAL 時直接 demote strategy / shrink param**；M11 是 sensor，M7 是 actuator。違反此 dedup 紀律 = 違反 §二 原則 7「Learning ≠ Live」+ ADR-0034 LAL gate（M11 不是 governance object）。

### Decision 4 — V107 `learning.replay_divergence_log` Schema（候選，待 CR-7 finalize）

**候選 schema**（不在本 ADR commit；待 CR-7 dedup contract + V109 anomaly schema cross-check 後 finalize）：

```sql
CREATE TABLE IF NOT EXISTS learning.replay_divergence_log (
    replay_id          TEXT        NOT NULL,    -- nightly run UUID
    ts                 TIMESTAMPTZ NOT NULL,    -- divergence detection ts
    strategy_name      TEXT        NOT NULL,    -- per CR-7 attribution chain
    asset              TEXT        NOT NULL,    -- symbol
    live_pnl_bps       REAL        NOT NULL,
    replay_pnl_bps     REAL        NOT NULL,
    divergence_bps     REAL        NOT NULL,    -- (replay - live) signed bps
    divergence_level   TEXT        NOT NULL,    -- 'NOISE' / 'WARN' / 'CRITICAL'
    engine_mode        TEXT        NOT NULL,    -- 'live' / 'live_demo' / 'demo' (per ADR-0005)
    baseline_5d_mean   REAL,                     -- empirical baseline at detection time
    baseline_5d_sigma  REAL,                     -- empirical sigma at detection time
    m7_dispatched      BOOLEAN     NOT NULL DEFAULT FALSE,    -- per CR-7 dedup gate
    PRIMARY KEY (replay_id, strategy_name, asset)
);

CREATE INDEX IF NOT EXISTS idx_replay_div_log_ts_desc
  ON learning.replay_divergence_log (ts DESC, replay_id);
```

**PK 設計理由**：對齊 ADR-0029 V094 close-maker audit + V095 liquidations identity 既有 PK 範式（必含 lossy-pk avoidance）；`replay_id + strategy + asset` 是 nightly 內部 idempotency。

**Retention**：90d（per v5.8 H-22 R4 governance retention 規範對齊 learning.* 表標準），超出 90d 走 nightly cleanup cron。

**Guard 範式**：對齊 V094 / V095 / V107（per ADR-0010 TimescaleDB hypertable + Guard migrations）三 Guard layer（表存在 + 欄位型別 + DDL 結果驗證）— per `feedback_v_migration_pg_dry_run.md` Linux PG dry-run mandatory。

### Decision 5 — Resource Budget（per E4 H-15 對齊）

| 元素 | 設計 |
|---|---|
| Wall-clock budget | **≤ 4h** for 24h replay × 5 strategy × all live symbols |
| Mac dev policy | **不跑 full replay**（Mac is dev only per ADR-0007 Mac dev / Linux runtime split）；Mac 上跑 sampled 1h replay 用於 IMPL debug |
| Linux runtime cron | `helper_scripts/cron/m11_nightly_replay.sh`（待 IMPL）；schedule 對齊既有 ml_training cron 範式（避開 02:00-04:00 ml_training_maintenance window）|
| 超 budget 行為 | wall-clock > 4h → emit M3 HEALTH_WARN（per CR-7 dedup contract M3 為 single health authority）+ Slack warn；**不**作 strategy demote（per Decision 3 M7 dedup）|
| 升級條件 | 連續 7d 超 budget → operator 仲裁 decision matrix：(a) downgrade replay sample rate (b) split nightly into 2-shard (c) cohort filtering（high-vol strategy only）|
| IPC / PG 通量 | replay query 走 read-only PG hot path；不阻塞 fill writer 路徑（per ADR-0001 Rust 為唯一交易權威 + ADR-0029 fail-closed writer 紀律對齊）|

## Open Questions（不在本 ADR resolve）

### OQ-1: 5d baseline cold start fallback

**待 QC review**：strategy 首次 deploy 後 < 5d 期間如何 derive baseline？候選：

- 用前一個同類 strategy（grid family）的 5d baseline 作 priors
- 用 cohort 級 baseline（all live strategy 合併 5d）作 substitute
- 不 emit divergence_level 直到 5d 累積（NULL level row 仍 log 用於 debug）

**建議起點**：cohort 級 baseline + degraded warn flag；QC calibration 後 promote。

### OQ-2: Per-strategy vs cohort-uniform σ

**待 QC review + MIT empirical analysis**：

- 不同 strategy（grid 低 vol vs bb_breakout 高 vol vs funding_arb 中 vol）的 PnL distribution variance scale 不同；funding_arb retired per AMD-2026-05-26-01，本表保留作為 future ADR-0046 redesign 設計參考
- Per-strategy σ 計算更精確但 schema 變複雜（V107 多 per-strategy baseline column）
- Cohort-uniform σ 計算簡單但對 low-vol strategy 不敏感

**建議起點**：per-strategy σ，schema 預留 column（per §Decision 4 候選 schema 已有 `baseline_5d_mean` + `baseline_5d_sigma` per row）。

### OQ-3: Outlier-driven distribution 的 robust threshold

**待 QC review**：

- σ-based threshold 在 fat-tail distribution（如 funding spike / flash crash episode）下 over-trigger
- MAD（Median Absolute Deviation）-based threshold 對 outlier robust 但 dynamic 計算開銷高
- Hampel filter / Tukey fence 替代方案 trade-off

**建議起點**：σ-based as baseline；QC review 後若實測 false positive rate > 1% 升級 MAD。

### OQ-4: V109 anomaly schema 與 V107 replay log dedup

**待 CR-7 dedup contract finalize**：

- v5.8 §2 M8 anomaly detection 用 V109（per dispatch consolidation report）
- M11 CRITICAL divergence 也可能進 anomaly category
- V107 replay log 與 V109 anomaly log 是否 cross-reference 或 merge

**建議起點**：兩表獨立 + `replay_divergence_log.m7_dispatched` flag 對齊 M7 dispatch；V109 anomaly 由 M8 主導，V107 由 M11 主導；M7 是 down-stream 整合 surface。

### OQ-5: Stage 0R preflight 路徑與 nightly replay 共存

**待 R4 review**：

- AMD-2026-05-15-01 Stage 0R 是 promotion preflight（one-time per promotion）
- M11 是 continuous nightly hygiene
- 兩者用同套 replay engine 但 dispatch context 不同
- Engineering scope 階段需確認 Stage 0R infra extension 可同時服務兩 use case（per v5.8 §2 M11 Sprint 3「extend existing Stage 0R infra」）

**建議起點**：共用 replay engine + 不同 cron + 不同 output schema（V107 replay log vs Stage 0R preflight 既有 schema）；R4 review 後確認 boundary。

## Alternatives Considered

| Alternative | 棄因 |
|---|---|
| **依賴 Bybit historical liquidations API**（即使現在不存在，未來可能開放） | (a) Bybit V5 baseline 不存在；roadmap 不可預測 (b) 即使開放也違反 ADR-0017 scanner-is-evidence-not-authority — vendor side history 不可作 production dependency (c) governance posture 不押 vendor optionality |
| **採 cross-exchange Binance historical liquidations 替代** | 違反 ADR-0033 §Decision 1「Binance market-data Y1 不作 strategy trigger」；replay 是 strategy decision 重放路徑，違反精神；且 cross-exchange liquidation event 在 Bybit-specific position context 下意義不對等 |
| **採第三方數據源（Coinglass / Glassnode / CoinGecko）historical liquidations** | (a) 付費服務違反 §二 原則 14「baseline 系統可在無外部付費服務運作」 (b) 第三方數據 vendor risk + freshness lag + ToS 紀律 (c) 數據對齊（symbol mapping / exchange tag）成本顯著 |
| **Hourly replay 替代 nightly** | (a) 4h budget × 24 = 96h/d 不可能 (b) IPC 通量 + L2 cost 不合理（per `project_hardware_constraints` 128GB 統一記憶體 / PG 4-8GB shared_buffers 限制）(c) hourly granularity 對 day-level strategy decay 不必要 |
| **不設 statistical threshold，用固定 bps cutoff** | 不同 strategy / symbol scale 不同；固定 bps 對 low-vol / high-vol strategy 不對稱（per §Decision 3 為什麼 σ 而非絕對 bps）|
| **M11 CRITICAL 直接 demote strategy（不走 M7）** | 違反 CR-7 dedup contract（M7 為 single decay authority）+ §二 原則 7（Learning ≠ Live）；M11 是 sensor 不是 actuator |
| **Replay window 默認 7d 而非 24h** | (a) v5.8 §2 M11 spec 默認 24h，7d default 是 spec drift (b) 7d 計算成本顯著超 4h budget (c) 7d 包含多個 funding cycle / regime shift，divergence interpretation 變難 |
| **不設 retention，永久保留 V107 log** | learning.* 表 retention 90d 是 v5.8 H-22 R4 governance baseline；永久保留違反 storage budget 紀律（per ADR-0029 hard cap）|

## Consequences

### Positive

- **M11 replay 不押 vendor optionality** — Bybit historical API 永遠不開也不影響 nightly replay 運作；對齊 §二 原則 5（生存 > 利潤）+ 原則 14（baseline 系統可在無外部付費服務運作）
- **Self-hosted PG 數據累積路徑明確** — `market.liquidations` 31,473 rows BB C6 PROOF PASS + ADR-0029 trade tape / L2 snapshot 落地後 historical accumulation 自然形成
- **CR-7 M11+M7 dedup 紀律落地** — M11 是 sensor / M7 是 actuator；避免 multi-authority strategy demote 衝突
- **Statistical 3σ threshold derivation** — 不是 ad-hoc 拍腦袋；threshold 隨 5d empirical baseline rolling adjust，對 regime shift 自適應
- **與 ADR-0029 trade tape policy 正交並存** — fidelity uplift + sourcing posture 兩個 ADR 服務不同治理層
- **4h budget hard cap** — 對 PG shared_buffers 4-8GB 限制與 nightly cron window 兼容；E4 H-15 對齊
- **V107 schema PK 設計** — 對齊 V094 / V095 既有 lossy-pk avoidance 範式

### Negative / Risk

- **Cold start 期 baseline 不足** — 新 strategy < 5d data 時 σ-based threshold 不適用，mitigation = OQ-1 cohort-level baseline fallback + degraded warn flag
- **`market.liquidations` WS subscription 未 production enabled** — 當前 BB W-AUDIT-8a C1 spec 要 24h proof PASS + MIT schema sign-off 才入 production；mitigation = M11 first nightly run 在 C1 PASS 後啟動；本 ADR 不阻塞 W-AUDIT-8a C1 timeline
- **4h budget 在 strategy cohort 擴張下可能超** — Y2 Copy Trading scaling AUM 增加 → strategy cohort 擴張 → wall-clock 增加；mitigation = §Decision 5 升級條件（連續 7d 超 budget → operator 仲裁 decision matrix）
- **Statistical threshold 對 outlier-driven distribution 不夠 robust** — funding spike / flash crash 期 σ 失效；mitigation = OQ-3 QC review + 必要時升級 MAD-based threshold
- **CR-7 M7 dedup gate 若 IMPL drift** — M11 CRITICAL 不升級 M7 / M7 不接 M11 input = silent drift；mitigation = V107 `m7_dispatched` flag + 對應 healthcheck 監測 dispatch chain 完整性
- **Retention 90d 對長期 trend regression 限制** — 不能直接從 V107 跑 6m strategy decay analysis；mitigation = QC 需 long-window analysis 走 separate aggregation table（non-blocking for nightly）
- **Self-hosted PG accumulation 期長** — `market.liquidations` 31,473 rows ≈ 數週累積；新 strategy 首次 M11 replay 可能因 historical 數據不足 degraded；mitigation = OQ-1 + Decision 1 例外條款（首次 cold start 仍走 self-hosted with degraded sample，**不**允許 vendor backfill）

### 與既存設計協作

| 既存元素 | 與本 ADR 關係 |
|---|---|
| ADR-0017 (Scanner is evidence not authority) | **基礎原則延伸**；M11 replay 是 decision-graph 重放，同 vendor-side history 不依賴邏輯 |
| ADR-0029 (market.public_trades + orderbook_l2_snapshot storage policy) | **本 ADR Decision 1 範圍自動覆蓋新表**；ADR-0029 schema 落地後 historical query 統一走 self-hosted PG namespace |
| ADR-0034 (Decision Lease LAL) | **replay window 擴展受 LAL 2 約束**（per Decision 2）；M11 CRITICAL → M7 dispatch 走 LAL 1 或 LAL 2 路徑 |
| v5.7 §6 market.liquidations writer existing | **基礎設施**；本 ADR Decision 1 historical source 即指此 writer 累積數據 |
| BB W-AUDIT-8a C1 spec (`allLiquidation.{symbol}` probe) | **依賴**；W-AUDIT-8a C1 PASS 是 production WS subscription enabled 的前置條件；本 ADR 不阻塞該 timeline |
| BB C6 PROOF PASS (`market.liquidations` 31,473 rows) | **數據可得性證據**；證明 self-hosted accumulation 路徑可行 |
| v5.8 §2 M7 (strategy decay detection) | **down-stream actuator**（per CR-7 dedup contract）；M11 CRITICAL → M7 input not direct demote |
| v5.8 §2 M3 (HEALTH_WARN routing) | **wall-clock budget 超 → M3 dispatch 路徑**（per CR-7 dedup contract M3 為 single health authority）|
| v5.8 §2 M8 (anomaly detection) | **V109 anomaly schema 與 V107 replay log dedup**（per OQ-4）|
| AMD-2026-05-15-01 (Canary Rebase Replay Preflight Stage 0R-4) | **Stage 0R preflight 與 M11 nightly replay 共用 replay engine**（per OQ-5）；兩者 dispatch context 不同 |
| ADR-0001 (Rust 為唯一交易權威) | **replay query 不阻塞 trading thread**；fail-closed writer 紀律對齊 |
| ADR-0007 (Mac dev / Linux runtime split) | **Mac 不跑 full replay**；nightly cron 限 Linux runtime |
| `feedback_v_migration_pg_dry_run.md` | **V107 schema 落地必須 Linux PG dry-run mandatory** |
| `project_hardware_constraints` (4-8GB PG shared_buffers) | **storage / query throughput 強約束**；本 ADR 4h budget 對齊該限制 |

## §二 16 根原則合規確認

| # | 原則 | 是否相容 | 說明 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | M11 是 read-only replay；不創造 trade 寫入口 |
| 2 | 讀寫分離 | ✅ | replay 純讀 self-hosted PG `market.*` 表；無寫入 live state |
| 3 | AI 輸出 ≠ 命令 | ✅ | M11 divergence detection 走 V107 log + M7 dispatch；不繞 Decision Lease |
| 4 | 策略不繞風控 | ✅ | M11 CRITICAL 不 auto-demote；走 M7 + LAL gate |
| 5 | 生存 > 利潤 | ✅ | 不依賴 vendor API optionality；vendor incident 不影響 nightly 運作 |
| 6 | 失敗默認收縮 | ✅ | wall-clock 超 budget → M3 WARN；cohort 數據不足 → degraded sample + warn |
| 7 | 學習 ≠ Live | ✅ | M11 是 evidence accumulation；不寫 live state；CRITICAL 必走 M7 + LAL |
| 8 | 交易可解釋 | ✅ | V107 replay_divergence_log 提供完整 audit trail；每筆 divergence 可重構 |
| 9 | 雙重防線 | ✅ | M11（sensor）+ M7（actuator）雙層；CRITICAL gate 不可單一路徑跳過 |
| 11 | Agent 最大自主 | ✅ | Agent 在 P0/P1 內走 LAL 1 auto-approve；LAL 2 cross-strategy reweight 受 ADR-0034 約束 |
| 12 | 系統演化由 evidence 驅動 | ✅ | M11 持續累積 divergence evidence 是 evidence-based decision 的基礎設施 |
| 13 | cost 感知 | ✅ | 4h wall-clock budget 紀律；不增加 AI call cost |
| 14 | 零外部成本 | ✅ | self-hosted PG only；不依賴外部付費 historical API / 第三方數據源 |
| 16 | Portfolio > 孤立 trade | ✅ | M11 cohort-level replay 是 portfolio thinking 的 audit infrastructure |

## Cross-References

- **v5.8 §2 M11**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md:391-423`（本 ADR 對應 module）
- **v5.8 §2 M3 + M7 + M8**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md`（CR-7 dedup contract downstream）
- **ADR-0017**：`docs/adr/0017-scanner-is-evidence-not-authority.md`（基礎原則）
- **ADR-0029**：`docs/adr/0029-market-trade-tape-and-orderbook-l2-storage-policy.md`（trade tape policy + storage budget 紀律）
- **ADR-0034**：`docs/adr/0034-decision-lease-layered-approval-lal.md`（LAL 2 replay window 約束 + M7 dispatch 路徑）
- **ADR-0001**：`docs/adr/0001-rust-as-trading-authority.md`（replay 不阻塞 trading thread）
- **ADR-0007**：`docs/adr/0007-mac-dev-linux-runtime-split.md`（Mac 不跑 full replay）
- **ADR-0010**：`docs/adr/0010-timescale-hypertable-with-guard-migrations.md`（V107 Guard 範式）
- **v5.7 §6 market.liquidations writer existing**：`docs/execution_plan/2026-05-20--execution-plan-v5.7.md`
- **BB W-AUDIT-8a C1 spec**：`docs/execution_plan/2026-05-15--w_audit_8a_c1_liquidation_topic_probe_plan.md`
- **BB C6 PROOF PASS memory**：`memory/project_decision_outcomes_not_dead.md`（`market.liquidations` 31,473 rows accumulated 證據）
- **Bybit API reference**：`docs/references/2026-04-04--bybit_api_reference.md:1080-1108`（Bybit V5 historical liquidations 不存在 confirmation）
- **AMD-2026-05-15-01**：`docs/governance_dev/amendments/2026-05-15--canary_rebase_replay_preflight.md`（Stage 0R preflight 共用 replay engine）
- **PA dispatch consolidation report**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md`（CR-7 dedup contract 來源）
- **`feedback_v_migration_pg_dry_run.md`**：V107 schema land 前 Linux PG dry-run mandatory
- **`project_hardware_constraints`**：4-8GB PG shared_buffers 強約束
- **V107 schema spec**：pending CR-7 finalize（候選 schema in §Decision 4）
- **V109 anomaly schema**：pending CR-7 dedup contract（per OQ-4）

## Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | 主會話 PM dispatch via v5.8 §2 M11 「Continuous Counterfactual Replay + nightly source」立場 | 2026-05-21 | 🟡 PROPOSED-pending-commit |
| TW | 本文件起草（v5.8 §2 M11 module ADR 級落地 + BB 5.21 audit push back 對齊） | 2026-05-21 | ✅ Drafted |
| BB | Bybit historical liquidations API 不存在 confirmation + `allLiquidation.{symbol}` W-AUDIT-8a C1 spec 對齊 | 2026-05-21 | ✅ Drafted (PROOF PASS recommendation per BB 5.21 audit) |
| E4 | 4h wall-clock budget validation + PG hot path 不阻塞 trading thread 對齊 | TBD（Sprint 1A） | 🟡 PENDING |
| QC | 3σ statistical threshold derivation review + OQ-1/2/3 cold start / per-strategy σ / robust threshold | TBD（Sprint 1A） | 🟡 PENDING |
| MIT | V107 schema PK + retention + Guard 範式 review（per ADR-0010 + V094/V095 對齊）| TBD（Sprint 1A） | 🟡 PENDING |
| R4 | OQ-5 Stage 0R preflight 與 M11 nightly 共存 boundary review | TBD（Sprint 3） | 🟡 PENDING |
| PM | CR-7 dedup contract finalize → promote 至 Accepted；V107 schema commit | TBD（Sprint 1A 結束） | 🟡 PENDING |

---

*OpenClaw / Arcane Equilibrium ADR-0038 — M11 Continuous Counterfactual Replay: Self-Hosted PG `market.liquidations` As Historical Source (Proposed-pending-commit; vendor optionality not assumed)*
