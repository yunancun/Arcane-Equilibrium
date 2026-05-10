# A4-C BTC→Alt Lead-Lag Spec — Sprint N+1 W2 PA C-1 Spec Phase Draft v1

**Author**: PA (project architect)
**Date**: 2026-05-10
**Phase**: W2 Spec phase Day 1-2 — PA C-1 deliverable（QC C-2 + MIT C-3 三角 review pending）
**Scope**: Sprint N+1 W2 A4-C fast-track 第一份 spec draft；spec 拍板後直接派 paper IMPL（C-IMPL-1..4），D+5 起 paper engine 累積 7d edge evidence，gate ≥ +5 bps 才進 N+2 demo IMPL。
**Reference dispatch**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--sprint_n1_dispatch_draft.md` §3.2 W2
**Reference trait coord**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--alpha_surface_trait_final_shape_w1_w2_coord.md`
**Reference alpha surface**: `srv/docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md` + W-AUDIT-8c §515 (BTC→Alt lead-lag 候選 C, 留給 N+5)

---

## §1 Background + Hypothesis

### 1.1 Why A4-C now

W6 baseline + 4-agent loss audit 雙重確認（2026-05-10）：5 textbook 策略（ma_crossover / grid_trading / bb_breakout / bb_reversion / funding_arb）**結構性 alpha-deficient**。post-V082 demo 7d gross **−26.44 USDT**；live_demo 7d gross **+0.43 USDT**。realized edge `[40]` avg_net 持續 **−6 bps**。P0-EDGE-1 不靠 textbook 策略本身能解。

A4-C BTC→Alt Lead-Lag 是 W-AUDIT-8c 候選 C 的 fast-track 預跑：用 BTC microstructure 的 informational lead 預測 alt cohort 的短期 momentum / mean reversion，抓 textbook 策略看不見的 cross-asset alpha source。Operator 2026-05-10 拍板 B 路徑 = 直接 paper IMPL，7d evidence 拿真實 edge 才決定是否 promote demo。

### 1.2 Alpha source classification

- AlphaSurface **Tier 2（cross-asset panel）** — `AlphaSourceTag::CrossAsset`
- W-AUDIT-8a Phase A 已 land enum tag (`alpha_surface.rs:84-85`)
- W2 PA D+0 trait skeleton (HEAD `c9fb0b8f`) 已 land `BtcLeadLagPanel` struct + `AlphaSurface.btc_lead_lag: Option<&'a BtcLeadLagPanel>` field + 3 constructor 加 `btc_lead_lag: None`
- BTCUSDT 為 lead source；alt cohort 為 follower

### 1.3 Hypothesis（spec 出發點）

**核心假設**：BTC 的 1m price/volume movement leads alt symbols 60-300 秒。Crypto microstructure literature well-documented（Easley / De Prado / O'Hara 2018-2023 工作；Bybit demo 也驗 BTC tick 動先於 ETH 5-30s 區間）。

**信號方向**：
- BTC 突破性 return + xcorr 高 → alt 短期 momentum 跟漲（同向）
- BTC 大量反向 + xcorr 高 → alt mean-reverse 接力（反向 lag-trade）

**驗證方式**：W2 paper IMPL 收 7d 樣本算 paper avg_net_bps + DSR + alpha decay 半衰期；gate ≥ +5 bps 才 promote N+2。

---

## §2 Cohort Symbol Scope

### 2.1 Lead source（fixed）

- **BTCUSDT** — 唯一 lead source；BTC 在 crypto 流動性與資訊發現是 anchor

### 2.2 Alt cohort（recommend 7-10 mid/large cap）

| Symbol | 必含？ | 理由 |
|---|---|---|
| ETHUSDT | YES | 第二大流動性，Layer 1 anchor |
| SOLUSDT | YES | High beta to BTC, Layer 1 |
| XRPUSDT | YES | 大流動性，獨立 narrative，xcorr 變動性 |
| DOGEUSDT | YES | High beta, retail-driven |
| ADAUSDT | YES | Layer 1, mid cap |
| AVAXUSDT | optional | Layer 1, narrative driven |
| DOTUSDT | optional | Layer 1, mid cap |
| LINKUSDT | optional | Oracle category, 獨立 catalyst |

**最終 8 symbol**：BTCUSDT + ETHUSDT / SOLUSDT / XRPUSDT / DOGEUSDT / ADAUSDT / AVAXUSDT / DOTUSDT（PA recommend；QC C-2 + MIT C-3 可改）

### 2.3 Excluded symbols

- **BUSDT** — ADR-0018 funding_arb retire 後 demoted；不可 cohort
- **INXUSDT** — `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--p1_ma_crossover_duplicate_intent_audit.md`：ma_crossover INXUSDT hot loop 殘留風險，避免 W2 cohort 與 W7-3 fix 撞車
- **frozen symbols** — `srv/docs/governance_dev/strategy_blocked_symbols_freeze.json` 列入 grid_trading.blocked_symbols 的全部（含 BSBUSDT / PRLUSDT / ZBTUSDT / FARTCOINUSDT 等）

---

## §3 Signal Formula

### 3.1 Lead signal（從 BTCUSDT 計算）

三個 component，組合成 lead signal vector：

#### 3.1.1 Return component

```
btc_lead_return_pct(N) =
    (close_btc[t] - close_btc[t-N]) / close_btc[t-N] * 10000   // bps
```

**N 候選**：60s / 120s / 300s 三檔（QC C-2 拍板最佳 N；spec draft 預設 120s）。

#### 3.1.2 Volume z-score

```
btc_volume_z(N) =
    (volume_btc[t-N..t].sum() - rolling_1h_mean(volume_btc)) / rolling_1h_std(volume_btc)
```

Rolling window = 1h baseline；用 `shift(1)` 排除 current bar。

#### 3.1.3 Orderbook imbalance proxy

```
btc_book_imbalance =
    (bid_size_top10 - ask_size_top10) / (bid_size_top10 + ask_size_top10)
```

從 Bybit V5 `/v5/market/orderbook` snapshot top-10 抽（snapshot 頻率 = 1m grain，與 lead signal bucket 對齊）。

### 3.2 Cross-correlation（per alt symbol）

```
xcorr_alt[i] = pearson_corr(
    btc_lead_return_pct(N) over [t-1h, t-N],  // BTC lead window strict shift(N)
    alt_return_pct[i] over [t-1h+N, t]         // Alt follow window shift forward N
)
```

**Window**：rolling 1h baseline；最少 30 樣本才寫值，否則 `xcorr_alt[i] = NaN`（consumer 視 NaN 為 no-signal）。

**Lead window strict shift(N)**（**critical**）：必用 `shift(1)` 後 N 秒前的 BTC value，**禁止含 current bar**（per `feedback_indicator_lookahead_bias` Rolling-window breach look-ahead bias 反模式）。MIT C-3 leak detection 必跑 strict shift 驗證。

### 3.3 Predicted direction（per alt symbol）

```
def alt_expected_dir(i, btc_lead_return, xcorr, threshold_X, threshold_Y):
    if abs(xcorr) < threshold_Y:        # xcorr 太弱 → 不 trust BTC 預測力
        return 0
    if btc_lead_return > +threshold_X:
        return +1 * sign(xcorr)         # xcorr > 0 → momentum LONG; xcorr < 0 → reverse SHORT
    if btc_lead_return < -threshold_X:
        return -1 * sign(xcorr)
    return 0
```

**threshold_X 候選**：5 / 10 / 20 bps（QC C-2 拍板）
**threshold_Y 候選**：0.30 / 0.40 / 0.50（QC C-2 拍板）

PA spec draft 預設：`threshold_X = 10 bps`、`threshold_Y = 0.40`、`N = 120s`。

---

## §4 Producer (Python Writer + V088 Migration)

### 4.1 PG table — `panel.btc_lead_lag_panel`（V088 migration）

| Column | Type | Notes |
|---|---|---|
| `snapshot_ts_ms` | bigint | snapshot timestamp（1m grain） |
| `lead_window_secs` | int | 60 / 120 / 300（spec 預設 120） |
| `btc_lead_return_pct` | real | bps，per §3.1.1 |
| `btc_volume_z` | real | per §3.1.2 |
| `btc_book_imbalance` | real | per §3.1.3 |
| `alt_symbols` | text[] | cohort symbol list（per §2.2） |
| `alt_xcorr` | real[] | per §3.2，與 alt_symbols 同序，NaN 表 sample 不足 |
| `alt_expected_dir` | smallint[] | −1 / 0 / +1，per §3.3 |
| `source_tier` | text | 固定 `'cross_asset_btc_lead_lag'` |

**Hypertable 設計**（per W-AUDIT-8a Phase B 模板）：
- TimescaleDB hypertable，`chunk_time_interval = 1 day`
- Retention `INTERVAL '14 days'`（paper-only 期；N+2 promote demo 後升 30d，新開 V###）
- 索引：`(snapshot_ts_ms DESC, lead_window_secs)` covering
- Per-snapshot 1 row（不是 per-cohort-symbol N row）— W-AUDIT-8a Phase A `BtcLeadLagPanel` struct 已固定為 vector layout

**Migration template**：套 `sql/migrations/templates/schema_guard_template.sql` Guard A/B/C；MIT C-3 必審 PL/pgSQL 語法、idempotency dry-run 兩次。

### 4.2 Python writer — `program_code/exchange_connectors/bybit_connector/control_api_v1/app/btc_lead_lag_writer.py`

**新檔（W2 E1-δ C-IMPL-2 IMPL）**。職責：

1. 從 Bybit V5 `/v5/market/kline` 拉 BTCUSDT 1m kline + alt cohort 1m kline（rolling 1h buffer）
2. 從 Bybit V5 `/v5/market/orderbook` 拉 BTCUSDT top-10 snapshot（每 1m）
3. 計算 lead signal（§3.1）、xcorr（§3.2）、expected_dir（§3.3）
4. 1m grain bucketing：每 60 秒 1 個 snapshot 寫入 `panel.btc_lead_lag_panel`
5. 更新 Rust IPC slot `BtcLeadLagPanelSlot`（per `slots.rs` 新增）
6. **paper-only fence Layer 2**：啟動讀 `OPENCLAW_ENABLE_PAPER` env；若未設 + 偵測 demo/live engine active → writer 不啟動（per PA #1 trait final shape §5）

### 4.3 Bybit V5 rate budget 整合

Bybit V5 market endpoint group rate limit = **120 req/s**（per `docs/references/2026-04-04--bybit_api_reference.md:1131`）。

**W2 預估流量**（per minute）：
- BTCUSDT kline: 1 req
- BTCUSDT orderbook: 1 req
- Alt cohort kline (7 symbol): 7 req
- 合計 9 req/min = 0.15 req/s — well under 120 req/s budget

**與其他 wave 同窗整合**：W1 Phase B Tier 2 collector + W3 Stage 1 cohort + W2 同 market endpoint group；BB review 必確認 W1+W2+W3 合計 budget < 50% upper bound（per BB review 慣例）。

---

## §5 Consumer (Strategy Paper-only Shadow Log)

### 5.1 Strategy 接收：ma_crossover + grid_trading（**paper engine only**）

**W2 E1-ε C-IMPL-3 IMPL**。改動兩個策略的 `strategy_impl.rs` / `mod.rs`：

#### 5.1.1 declared_alpha_sources 加 `CrossAsset`

```rust
// ma_crossover/strategy_impl.rs:37-40 改
fn declared_alpha_sources(&self) -> &[AlphaSourceTag] {
    const TAGS: &[AlphaSourceTag] = &[
        AlphaSourceTag::Ta1m,
        AlphaSourceTag::CrossAsset,    // W2 新加
    ];
    TAGS
}
```

grid_trading/mod.rs:320-322 同樣 pattern。

#### 5.1.2 on_tick shadow log only（**不直接 trade**）

```rust
fn on_tick(&mut self, ctx: &TickContext<'_>, surface: &AlphaSurface<'_>) -> Vec<StrategyAction> {
    // ... existing TA1m logic ...

    // W2 paper-only consume
    if let Some(panel) = surface.btc_lead_lag {
        let alt_idx = panel.alt_symbols.iter().position(|s| s == ctx.symbol);
        if let Some(i) = alt_idx {
            let xcorr = panel.alt_xcorr.get(i).copied().unwrap_or(f64::NAN);
            let dir = panel.alt_expected_dir.get(i).copied().unwrap_or(0);
            log::info!(
                target: "btc_alt_lead_lag_shadow",
                "strategy={} symbol={} btc_lead={:.4} window={} xcorr={:.4} expected_dir={}",
                self.name(), ctx.symbol, panel.btc_lead_return_pct,
                panel.lead_window_secs, xcorr, dir
            );
        }
        // **不**改 actions，純 evidence 收集供 7d paper edge evaluation
    }

    actions  // 原 TA1m logic 結果
}
```

**目的**：7d paper engine 跑後，從 `btc_alt_lead_lag_shadow` log 對齊每筆 entry/exit fill 反算「如果 follow lead signal expected_dir 進場，paper engine net edge 是多少」（counterfactual analysis）。

### 5.2 不接收：bb_breakout / bb_reversion / funding_arb

| Strategy | 為何不接 |
|---|---|
| bb_breakout | 已 declare `OiDeltaPanel` (Tier 2.3)，不重疊 alpha source；避免污染既有 oi_delta panel evidence |
| bb_reversion | 樣本量不足，paper edge baseline 還在收 |
| funding_arb | ADR-0018 已 retire；不再做策略改動 |

---

## §6 Paper-only Fence — 三層深度防禦（per PA #1 §5）

### 6.1 Layer 1（主防線）：`step_4_5_dispatch.rs` engine_mode gate

`tick_pipeline/on_tick/step_4_5_dispatch.rs` line 191-196 已有 anchor comment：

```rust
let btc_lead_lag = match self.effective_engine_mode() {
    "paper" => self.btc_lead_lag_slot.latest(),
    _ => None,  // demo / live_demo / live → 永遠 None
};
let alpha_surface = AlphaSurface {
    ..AlphaSurface::tier1_only(indicators, indicators_5m.as_ref()),
    btc_lead_lag,
};
```

**Critical**：default branch 必為 `_ => None`（不是 `_ => Some(...)`）；E2 必 grep verify。

### 6.2 Layer 2：Python writer paper-only fence

`btc_lead_lag_writer.py` 啟動讀 `OPENCLAW_ENABLE_PAPER` env；未設 + 偵測 demo/live engine active → writer 不啟動或只寫 placeholder row。**目的**：避免 PG `panel.btc_lead_lag_panel` 累積 demo/live 期樣本污染下游 ML pipeline。

### 6.3 Layer 3：Strategy 端 defensive guard（被 §5.1.2 contract 覆蓋）

`if let Some(panel) = surface.btc_lead_lag` 已隱含 None → skip。Layer 1 保證 demo/live 永遠 None，此 guard 是 redundant safety。

### 6.4 為何三層

- 原則 7（學習 ≠ 改寫 Live）+ 原則 4（不繞風控）+ 原則 11（Agent 最大自主僅在 P0/P1 邊界內）三線交叉
- W2 paper-only fence 失靈 = 5 策略 demo edge baseline 被污染 → 整個 P0-EDGE-1 觀察被破壞
- 三層任一仍守住 → fence 整體 fail-closed

---

## §7 Backtest Counterfactual Spec

### 7.1 7d paper engine 跑後 evaluate

| Metric | 計算 |
|---|---|
| paper avg_net_bps (overall) | per cohort symbol + overall，含成本 fee + slippage |
| paper sample size n | per cohort symbol，gate n ≥ 100 fills |
| DSR PASS test | mu_0 = sqrt(2 ln K)，K 含 A4-C 加入後重算（per QC C-2 量化） |
| Alpha decay 半衰期 | lead signal 對 alt return 的 forward predictive R^2 隨 lead window 增長的衰減速率 |
| Counterfactual net edge | 用 shadow log 對齊每筆 entry，反算「follow lead signal expected_dir 進場 vs 既有 TA1m 進場」net edge delta |

### 7.2 Counterfactual reconstruction

shadow log 寫到 `btc_alt_lead_lag_shadow` target；7d 後跑離線 SQL：
```sql
SELECT
    symbol,
    AVG(net_edge_bps) AS avg_net_bps,
    COUNT(*) AS sample_n,
    -- counterfactual: if expected_dir=+1 → assume LONG entry; net_edge_bps proxy from forward 30s-300s alt return
    AVG(CASE WHEN expected_dir = +1 THEN forward_return_bps ELSE 0 END) AS cf_long_avg
FROM btc_alt_lead_lag_shadow_with_forward_returns
WHERE engine_mode = 'paper' AND ts >= NOW() - INTERVAL '7 days'
GROUP BY symbol;
```

---

## §8 Acceptance Gate（QC + MIT review 必審）

### 8.1 QC C-2 review scope

- Alpha decay 估算（critical）：lead window 60s/120s/300s 對應 forward predictive R^2 衰減；半衰期 < 60s → spec 失敗（信號太短沒實用價值），> 300s → window 太長不抓 microstructure
- DSR penalty K 量化：A4-C 加入後 mu_0 = sqrt(2 ln K) 重算，K 含 5 textbook + A4-C 共 6
- Paper edge gate threshold：≥ +5 bps avg_net 進 N+2 demo IMPL；< +5 bps 進 revise spec 不浪費 N+2
- Threshold X / Y / N 三參數最佳值拍板

### 8.2 MIT C-3 review scope

- Time-series CV 設計：purged k-fold + embargo（per De Prado 2018 §7.4）；embargo ≥ N seconds 防 leak
- Leak detection（critical）：strict shift(N) 必驗，`rolling(N).max()` 反模式 grep
- Cohort sample size demand：per cohort symbol n ≥ 100 fills 7d 內可達？BTCUSDT 1m 7d = 10080 bar 足夠 lead signal；alt cohort fills 倚賴 5 策略 paper baseline 活躍度
- V088 hypertable PL/pgSQL 語法 + retention drop_chunks policy + idempotency dry-run

### 8.3 三方 APPROVE 後才 paper IMPL phase

D+3 起 W2 paper IMPL（C-IMPL-1 NO-OP 驗收 + C-IMPL-2 producer + V088 + C-IMPL-3 strategy shadow + C-IMPL-4 paper engine 7d evidence collection 開始）。

---

## §9 Risk + Mitigation

| Risk | 等級 | 緩解 |
|---|---|---|
| **Look-ahead bias**（lead window 含 current bar） | **極高** | strict `shift(N)` 禁含 current bar；MIT C-3 必跑 leak detection；對照 `feedback_indicator_lookahead_bias` |
| Self-fulfilling bias（paper engine 自己 trade BTC alt 推動 BTC lead signal） | 高 | 5 策略 paper engine 流量極小（demo 7d gross −26 USDT），對 BTC global liquidity 無影響；但仍 paper-only fence 三層防禦避免 demo 污染 |
| ML pipeline 污染（demo/live 期 BtcLeadLag 寫進 ML training table） | 高 | bb_breakout/bb_reversion/funding_arb 不接收 + paper-only fence Layer 2 Python writer 不啟動 → 5 策略 demo edge baseline 不污染 |
| Cohort 樣本不足 7d 內 < 100 fills | 中 | n ≥ 100 是 gate；不達標延長收 evidence 至 14d 或 cohort 縮減；QC C-2 量化 |
| Bybit rate limit 撞 W1+W3 同窗 | 低 | W2 預估 9 req/min 占 < 1% upper bound（per §4.3）；BB review 確認三 wave 合計 < 50% |
| W6 ML retrain 4-gate 衝突（Q&A pending） | 低 | A4-C 是新 alpha source，不是 ML feature retrain；走 W6 4-gate 不適用本 wave |
| `CrossAsset` enum tag 對應多個未來 panel | 中 | 接受；W-AUDIT-8c 真接 generic 跨資產 panel 時拆 `BtcAltLeadLag` 為獨立 enum variant（ADR 觸發） |
| MIT 揭露 W2 與 W6-5 同類 category error | 待 D+1 review | QC + MIT 三角 review 1 day 必揭露；如類似 W6-5 → revise spec 重派 |

---

## §10 N+2 Promotion Path（gate ≥ +5 bps）

如 D+12 paper edge report 顯示 avg_net_bps ≥ +5：

- N+2 dispatch draft 加 A4-C demo IMPL phase
- 5 策略 全 demo engine 接 BtcLeadLag panel（含 bb_breakout/bb_reversion）
- 真 trade decision logic（不只 shadow log）— Strategy on_tick 把 expected_dir 整合進 TA1m signal，weighted ensemble
- N+2 spec 三角 review 重做（PA + QC + MIT）
- V### migration 升級 retention 14d → 30d
- 加入 graduated canary state machine Stage 1 cohort（per W-AUDIT-9）

如 D+12 paper edge report 顯示 avg_net_bps < +5：

- N+2 dispatch draft 加 A4-C revise spec phase（不浪費 N+2 demo IMPL）
- QC + MIT 對 alpha decay / threshold X/Y/N / cohort scope 重審
- 如三輪 revise 仍 < +5 bps → A4-C 路徑 archive，W-AUDIT-8c 候選 D（orderbook imbalance）替補 fast-track

---

## §11 E1 派發計劃（D+3-5 W2 IMPL phase）

per dispatch v3.3 §3.2 W2 fast-track：

| Sub-agent | Scope | 動的 file | est LOC |
|---|---|---|---|
| **W2 E1-γ (C-IMPL-1)** | trait extension **NO-OP**（PA D+0 已 land） | **無檔可動** — 範圍縮為 BtcLeadLagPanel typedef 驗收 + 對照 producer schema | 0 LOC |
| **W2 E1-δ (C-IMPL-2)** | lead-lag producer + V088 + IPC slot | `program_code/.../btc_lead_lag_writer.py`（新）+ `sql/migrations/V088__btc_lead_lag_panel.sql`（新）+ `rust/openclaw_engine/src/ipc_server/slots.rs`（加 `BtcLeadLagPanelSlot`） + `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`（一行 surface field assignment + paper-only engine_mode gate） | ~350 LOC |
| **W2 E1-ε (C-IMPL-3)** | strategy paper-only shadow | `ma_crossover/strategy_impl.rs`（declare `CrossAsset` + on_tick shadow log）+ `grid_trading/mod.rs`（同） | ~80 LOC |
| **W2 E1-ζ (C-IMPL-4)** | paper engine 7d evidence collection 開始 | 操作 only，無代碼；D+5 起 paper engine deploy 後跑 7d；D+12 land paper edge report | 0 LOC |

**衝突點全部消除**：alpha_surface.rs trait 已 PA D+0 commit；slots.rs / step_4_5_dispatch.rs 用 anchor comment 隔離 W1+W2 sub-agent；V088 編號預留無撞。

---

## §12 E2 重點審查 3 點

per PA 輸出物標準：

1. **Layer 1 paper-only fence default → None**：E2 必 grep `btc_lead_lag = match self.effective_engine_mode()` in step_4_5_dispatch.rs，confirm `_ => None`（**不是** `_ => Some(...)`）。漏 `None` default = demo/live 污染主路徑。

2. **Strict shift(N) lookahead-free 驗證**：E2 必 grep `btc_lead_lag_writer.py` 內所有 `rolling()` / `[t-N..t]` slice operation，確認 BTC return / volume z-score 計算 strict 用 `shift(1)` 後的 N 秒前 value，**禁** include current bar。對照 `feedback_indicator_lookahead_bias` Rolling-window breach 反模式。

3. **V088 hypertable retention drop_chunks policy 必設**：E2 + MIT 必審 V088 SQL 含 `SELECT add_retention_policy('panel.btc_lead_lag_panel', INTERVAL '14 days');`；漏設 → PG table 永久膨脹。同時 idempotency dry-run 兩次，第二次必須不 RAISE。

---

## §13 16 根原則合規（CLAUDE.md §二）

- **原則 1 單一寫入口**：BtcLeadLag 不寫 trade order 路徑，consumer 只 shadow log → ✅
- **原則 4 不繞風控**：paper-only fence Layer 1 + W2 C-IMPL-3 純 shadow log 不 trade → 不觸碰 SM-04 Guardian → ✅
- **原則 7 學習 ≠ 改寫 Live**：三層 paper-only fence → demo/live engine 完全 None → 5 策略 demo edge baseline 不污染 → ✅
- **原則 8 交易可解釋**：panel snapshot 寫 PG (`source_tier='cross_asset_btc_lead_lag'`) + Strategy on_tick shadow log 含 `lead_window_secs` + `expected_dir` → 可 reconstruct alpha source 來源 → ✅
- **原則 13 AI 成本感知**：W2 是 deterministic signal，不調用 AI → 不影響 cost_edge_ratio gate → ✅
- **原則 14 零外部成本**：BTC kline + orderbook 都用 Bybit V5 free endpoint → ✅
- **DOC-08 §12 9 條安全不變量**：本 wave 不動 lease / authorization / audit / reconciler / mainnet env / Bybit retCode 任何路徑 → 全 9 條無關 → ✅
- **硬邊界 5 項**：本 wave 不動 `live_execution_allowed` / `max_retries=0` / `OPENCLAW_ALLOW_MAINNET` / `decision_lease` / `authorization.json` → 全 5 項無關 → ✅

---

## §14 一句總結

**A4-C BTC→Alt Lead-Lag 是 W-AUDIT-8c 候選 C 的 N+1 fast-track 預跑：BTCUSDT 1m kline + orderbook 算 lead signal（return / volume z / book imbalance over N=120s 預設）→ 7-symbol alt cohort xcorr + expected_dir 寫 `panel.btc_lead_lag_panel` (V088 hypertable, retention 14d) → ma_crossover + grid_trading 在 paper engine mode 接 `BtcLeadLag` 為 `CrossAsset` tag, on_tick shadow log only 不 trade（C-IMPL-3）；三層 paper-only fence（step_4_5_dispatch engine_mode gate 主防線 + Python writer fence + Strategy if let Some guard）保證 demo/live engine 永遠 surface.btc_lead_lag = None 不污染 5 策略 demo edge baseline；7d paper engine 收 evidence，gate avg_net_bps ≥ +5 bps 進 N+2 demo IMPL，否則 revise spec 不浪費 N+2；trait skeleton 已 PA D+0 commit (HEAD c9fb0b8f) IMPL phase 全 0 file 重疊 0 git merge 衝突；16 原則 + DOC-08 §12 不變量 + 硬邊界 5 項全 0 觸碰；QC C-2 alpha decay + DSR + threshold + paper edge gate / MIT C-3 purged k-fold + embargo + leak detection + cohort sample demand 三角 review pending D+1。**

---

**Spec end. PA C-1 spec phase Day 1-2 deliverable land. QC C-2 + MIT C-3 三角 review pending D+1（1 day）；APPROVE 後 D+3 起派 C-IMPL-1..4 paper IMPL，D+5 paper engine deploy 後跑 7d，D+12 paper edge report land。**

PA DESIGN DONE: report path: srv/docs/execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md
