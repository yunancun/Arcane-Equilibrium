# A4-C BTC→Alt Lead-Lag Spec — Sprint N+1 W2 PA C-1 Spec Phase v1.2

**Author**: PA (project architect)
**Date**: 2026-05-10
**Phase**: W2 Spec phase Day 1-2 — PA C-1 deliverable（QC C-2 sign-off CONDITIONAL APPROVE 5 conditions revised；MIT C-3 σ verify 已交付 → dual-layer σ + PSR(0) skew/kurt formula 強制 land，MIT + QC 直接收 W2 IMPL）
**Scope**: Sprint N+1 W2 A4-C fast-track；spec v1.2 拍板後直接派 paper IMPL（C-IMPL-1..4），D+5 起 paper engine 累積 7d edge evidence，gate 三檔（+15 promote / +5~+15 extend 14d / <+5 revise）才決定 N+2 demo IMPL 路徑。
**Reference dispatch**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--sprint_n1_dispatch_draft.md` §3.2 W2
**Reference trait coord**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--alpha_surface_trait_final_shape_w1_w2_coord.md`
**Reference alpha surface**: `srv/docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md` + W-AUDIT-8c §515 (BTC→Alt lead-lag 候選 C, 留給 N+5)
**Reference QC review**: `srv/docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-10--w2_a4c_qc_review_alpha_decay_dsr.md`
**Reference MIT C-3 σ verify**: `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--w2_c3_sigma_verify_btcusdt_1m_forward_return.md`

---

## Change Log

### v1.2 (2026-05-10) — MIT C-3 σ verify CONDITIONAL PASS 落地：dual-layer σ + PSR(0) skew/kurt strict formula

| # | Section | 改動 essence |
|---|---|---|
| 1 | §7.1 acceptance prerequisite | 從單一「σ MIT C-3 必 verify」line 改為 **dual-layer σ table**（L1 raw market σ_60=4.54/σ_120=6.28/σ_300=10.08 bps + L2 net edge σ=50-80 bps EDGE-DIAG-1 baseline）；強制 prerequisite condition：spec power calculation 用 net edge σ，禁用 raw market σ；任何 paper edge gate threshold 變動必對 σ_net=50/80 bps 兩 case 重算 power |
| 2 | §7.1 metric (3) PSR(0) | 從「PSR(0) ≥ 0.95 用 skew/kurt-aware formula」soft 描述改為**強制條件**：BTCUSDT 1m forward-return ex_kurt 7-12 ≫ 0 → JB normality 必拒（5d block resampling 已 verify）→ 禁用 normal SR z-test → 強制用 Bailey-López de Prado 2012 PSR(0) formula `PSR(0) = Φ((SR - 0) × √(n-1) / √(1 - skew·SR + (kurt-1)/4·SR²))`；threshold ≥ 0.95；σ_net=80 bps + ex_kurt=10 → PSR(0) ≈ 0.94 接近下界，必並列 σ_net=50/80 bps 兩 case |
| 3 | §8.1 +15 bps gate verification | 補強 power verification table（per MIT C-3 verify §5）：σ_net=50 + μ=15 → t-stat=2.68, p=0.0044 (comfortable PASS)；σ_net=80 + μ=15 → t-stat=1.68, p=0.0487 (marginal PASS)；結論：+15 bps gate 在 σ_net 50-80 range 全 PASS（marginal at upper bound）；+5/+15 中段 + +5 下界 verification 同步補完 |
| 4 | §8.3 sign-off path 簡化 | MIT C-3 σ verify 已交付 → dual-layer σ + PSR(0) strict formula land 為 spec internal cleanup（不增 condition、不改 IMPL scope）→ **MIT + QC 直接收 W2 IMPL**，不需 D+1 PA + MIT 重 sign-off |
| 5 | §1 header status | v1.1 → v1.2；reference MIT C-3 σ verify report path 補完 |

### v1.1 (2026-05-10) — QC C-2 review CONDITIONAL APPROVE 5 conditions revision

| # | Section | 改動 essence |
|---|---|---|
| 1 | §8.1 | DSR K 從 6 修正為 95（active strategy×symbol cell 總數，引 Bailey-López de Prado 2014 §4.2「DSR with multiple trial」）；mu_0 從錯誤值改為 √(2 ln 95) = 3.018 |
| 2 | §8.1 | paper edge gate 從 「≥ +5 bps」單檔改為三檔（+15 promote N+2 demo IMPL / +5~+15 extend paper window 14d 重評 / <+5 revise spec 或 archive） |
| 3 | §3.1 + §7.1 | N 鎖 120s 但 §7.1 evaluate 強制要求 R²(N=60/120/300) 三檔 decay curve；半衰期 < 60s → archive |
| 4 | §7.1 | Mandatory metric set 補完：(a) per-symbol breakdown + per-symbol n ≥ 100 + per-symbol t > 2.0 (b) block-bootstrap 95% CI block_size=60min 1000 iter (c) DSR with K=95 deflate（non-negotiable）+ PSR(0) ≥ 0.95 用 skew/kurt-aware formula (d) Alpha decay regime test |
| 5 | §9 | 加 BTC regime extreme guard（\|1h return\| > 200 bps shadow-only，shadow log 標 `regime=extreme` 不計入 7d edge avg） |
| extra | §7.1 | σ=30 bps 是下界假設，**MIT C-3 必 verify**（BTCUSDT 1m forward-return realized σ 7d 經驗值）；若 σ ≥ 60 bps 需重算 power → spec metric set 加「σ verified by MIT C-3」 acceptance prerequisite |

### v1.0 (2026-05-10) — PA C-1 spec phase Day 1-2 initial draft

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

**N 鎖定 = 120s**（QC C-2 review v1.1 拍板，per Easley/López de Prado/O'Hara *Microstructure in the Age of Machine Learning* 2021 + Makarov & Schoar JFE 2020 BTC→alt informational lead 半衰期 30-180s estimate；N=120s 對應預期 R²=0.06-0.10，half-life ≈ 90s 折衷 sweet spot）。

**N=60/120/300 三檔 decay curve 強制要求（v1.1 condition #3）**：D+12 paper edge report **必含** 三檔 N 對應的 forward predictive R²(60s alt return) decay curve，per §7.1 mandatory metric (4)。實測判定：
- N=120s R² < 0.04 → revise spec 改 N=60s
- N=60s R² 也 < 0.04 → archive A4-C 路徑
- N=300s R² > N=120s → 重評 N 選擇（trend-continuation 未被 arbitrage 完全消化）

**保留 60/120/300 三 lead_window_secs evidence**：writer 同 1m grain 寫 1 row 含 lead_window_secs=120 主信號 + 同 row metadata 帶 (60s, 300s) shadow value（per §4.1 schema 微調）。

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
| `lead_window_secs` | int | 主信號固定 120（v1.1 N 鎖定） |
| `btc_lead_return_pct` | real | bps，per §3.1.1，主信號 N=120 |
| `btc_lead_return_pct_60s` | real | bps，shadow value N=60（v1.1 condition #3 decay curve evidence） |
| `btc_lead_return_pct_300s` | real | bps，shadow value N=300（v1.1 condition #3 decay curve evidence） |
| `btc_volume_z` | real | per §3.1.2，主信號 N=120 |
| `btc_book_imbalance` | real | per §3.1.3 |
| `alt_symbols` | text[] | cohort symbol list（per §2.2） |
| `alt_xcorr` | real[] | per §3.2，主 N=120，與 alt_symbols 同序，NaN 表 sample 不足 |
| `alt_expected_dir` | smallint[] | −1 / 0 / +1，per §3.3，主 N=120 |
| `regime_tag` | text | v1.1 §9 regime extreme guard：`'normal'` / `'extreme'`（\|BTC 1h return\| > 200 bps 標 extreme，shadow log only 不計入 7d edge avg） |
| `source_tier` | text | 固定 `'cross_asset_btc_lead_lag'` |

**Hypertable 設計**（per W-AUDIT-8a Phase B 模板）：
- TimescaleDB hypertable，`chunk_time_interval = 1 day`
- Retention `INTERVAL '14 days'`（paper-only 期；N+2 promote demo 後升 30d，新開 V###）
- 索引：`(snapshot_ts_ms DESC, lead_window_secs)` covering
- Per-snapshot 1 row（不是 per-cohort-symbol N row）— W-AUDIT-8a Phase A `BtcLeadLagPanel` struct 已固定為 vector layout

**Migration template**：套 `sql/migrations/templates/schema_guard_template.sql` Guard A/B/C；MIT C-3 必審 PL/pgSQL 語法、idempotency dry-run 兩次。

### 4.2 Python writer — `program_code/exchange_connectors/bybit_connector/control_api_v1/app/btc_lead_lag_writer.py`

**新檔（W2 E1-δ C-IMPL-2 IMPL）**。職責：

1. 從 Bybit V5 `/v5/market/kline` 拉 BTCUSDT 1m kline + BTCUSDT 1h kline（v1.1 regime_tag 用）+ alt cohort 1m kline（rolling 1h buffer）
2. 從 Bybit V5 `/v5/market/orderbook` 拉 BTCUSDT top-10 snapshot（每 1m）
3. 計算 lead signal（§3.1）、xcorr（§3.2）、expected_dir（§3.3）；**主信號 N=120s**，同時計算 N=60s + N=300s shadow value 寫 `btc_lead_return_pct_60s` + `btc_lead_return_pct_300s` columns（v1.1 condition #3 decay curve evidence）
4. **v1.1 regime_tag 計算（§9 condition #5）**：每 1m 用 BTCUSDT 1h kline shift(1) 算 1h return；`abs(btc_1h_return_bps) > 200` → `regime_tag = 'extreme'`，否則 `'normal'`；shadow log 標記不影響 main signal 寫入
5. 1m grain bucketing：每 60 秒 1 個 snapshot 寫入 `panel.btc_lead_lag_panel`
6. 更新 Rust IPC slot `BtcLeadLagPanelSlot`（per `slots.rs` 新增）；**主 N=120 信號寫主 panel 欄位，60s/300s shadow value 寫 schema column 但不寫 IPC slot**（避免 Rust 端 surface 接 60s/300s 引發 strategy 接觸下游）
7. **paper-only fence Layer 2**：啟動讀 `OPENCLAW_ENABLE_PAPER` env；若未設 + 偵測 demo/live engine active → writer 不啟動（per PA #1 trait final shape §5）
8. **strict shift(N) lookahead-free（v1.1 condition #4）**：所有 `rolling()` / `[t-N..t]` slice operation 必用 `shift(1)` 後 N 秒前 BTC value，禁含 current bar；MIT C-3 grep verification gate

### 4.3 Bybit V5 rate budget 整合

Bybit V5 market endpoint group rate limit = **120 req/s**（per `docs/references/2026-04-04--bybit_api_reference.md:1131`）。

**W2 預估流量**（per minute）：
- BTCUSDT 1m kline: 1 req
- BTCUSDT 1h kline (v1.1 §9 regime_tag 計算用): 1 req
- BTCUSDT orderbook: 1 req
- Alt cohort kline (7 symbol): 7 req
- 合計 10 req/min = 0.17 req/s — well under 120 req/s budget

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

### 7.1 7d paper engine 跑後 evaluate（v1.1 mandatory metric set 6 條 + acceptance prerequisite）

#### Acceptance prerequisite（IMPL phase 啟動前必驗）— v1.2 dual-layer σ reframe

**v1.1 單一 σ=30 bps preliminary 已被 MIT C-3 verify report 否決（2026-05-10）**：30 bps 不對應任何真實層（raw market σ 4.5-10 bps × 3-7 underestimate；net edge σ 50-80 bps × 1.7-2.7 overestimate）。v1.2 改為 dual-layer σ acceptance：

| σ layer | source | value (per MIT C-3 verify 2026-05-10) | spec 用途 |
|---|---|---|---|
| **Raw market σ (L1)** | BTCUSDT 1m forward-return realized σ 7d (n=10050, MIT report §2) | σ_60 = 4.54 bps / σ_120 = 6.28 bps / σ_300 = 10.08 bps | Alpha decay R²(N) 計算 baseline、price horizon scaling reference (σ ∝ √horizon 已驗 σ_300/σ_60 = 2.22 ≈ √5) |
| **Net edge σ (L2)** | EDGE-DIAG-1 demo cost-aware fill σ historical empirical baseline | σ_net = 50-80 bps（含 fee + slippage + adverse selection + holding 內 hedge cost） | Paper edge gate threshold power calculation、PSR(0) ≥ 0.95 skew/kurt deflation 計算 |

**Prerequisite condition（強制）**：
1. spec power calculation **強制用 net edge σ_net = 50-80 bps**；**禁止用 raw market σ 計算 paper edge gate power**（raw σ 視角 t-stat 13-29，過度樂觀，會放 false-PASS 通過）
2. 任何 paper edge gate threshold 變動（§8.1 三檔調整 / future revision）必對 **σ_net = 50 bps + 80 bps 兩 case** 各重算 power、t-stat、p-value，並列報告
3. raw market σ 僅用於 §3.1.1 Return component 半衰期 reference + §7.1 metric (4) Alpha decay R²(N) 計算 baseline
4. MIT C-3 D+1 verify 已交付（report path: `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--w2_c3_sigma_verify_btcusdt_1m_forward_return.md`），W2 IMPL 直接收，**不需 D+1 MIT C-3 重跑 σ verify**

#### Mandatory metric set 6 條（D+12 paper edge report 必含）

| # | Metric | 計算 + 拍板 |
|---|---|---|
| 1 | **Pooled + per-symbol breakdown** | per cohort symbol + overall pooled，含 avg_net_bps + std + Sharpe + sample n + per-symbol t-stat。**Gate**：per-symbol n ≥ 100 fills + per-symbol t > 2.0（不只 overall pooled，避免 underpowered 單 symbol promote 決策） |
| 2 | **DSR PASS test with K=95 deflate**（**non-negotiable**）| mu_0 = √(2 ln K)，K=95（**v1.1 修正**：active strategy×symbol cell 總數，per Bailey-López de Prado 2014 §4.2 DSR with multiple trial）；mu_0 = √(2 ln 95) = **3.018**（舊 K=79 → 2.956；Δmu_0 = +0.062 即 +2.1%）。warning：8 cohort × 2 strat 全 promote → K 升至 ~111；future ADR 必記錄 K 累積對 multiple-testing budget 長期約束 |
| 3 | **PSR(0) ≥ 0.95 — 強制 skew/kurt-aware formula（v1.2 升級）** | **強制條件（v1.2 per MIT C-3 verify）**：BTCUSDT 1m forward-return excess kurt = 7-12 (MIT report §2 實測 σ_60 ex_kurt=11.76 / σ_120=7.82 / σ_300=10.34) ≫ 0 → crypto JB normality 必拒（5d block resampling 已 verify per MIT report §7），**禁用 normal SR z-test**；**強制用 Bailey-López de Prado 2012 PSR(0) skew/kurt-aware formula**：`PSR(0) = Φ((SR - 0) × √(n-1) / √(1 - skew·SR + (kurt-1)/4·SR²))`（Φ = standard normal CDF；SR = annualized Sharpe；n = sample size；skew + kurt 用 7d empirical estimate）。**Threshold**：PSR(0) ≥ 0.95；**MIT C-3 verify report §4 已預估**：σ_net=80 bps + ex_kurt=10 → PSR(0) ≈ 0.94（接近下界 0.95），σ_net=100 bps → PSR(0) ≈ 0.86（FAIL）→ σ_net 高端 case PSR(0) deflation 顯著，必並列報告 σ_net=50/80 bps 兩 case PSR(0) 值 |
| 4 | **Alpha decay regime test**：R²(N=60/120/300) 三檔 decay curve | lead signal 對 alt return forward predictive R²(60s alt return) 隨 7d window rolling 30-min bucket 衰減曲線；半衰期 < 60s → spec 失敗（信號太短沒實用價值），> 300s → window 太長不抓 microstructure；N=120s 主信號 R² < 0.04 → revise spec 或 archive |
| 5 | **Block-bootstrap 95% CI**（pooled + per-symbol）| block_size=60min（對齊 BTC autocorr scale），1000 iter；per-symbol CI 與 pooled CI 並列報告 |
| 6 | **Per-cohort-symbol counterfactual delta** | `(if-followed-lead net_edge) − (TA1m baseline net_edge)`；用 shadow log 對齊每筆 entry，反算「follow lead signal expected_dir 進場 vs 既有 TA1m 進場」net edge delta |

### 7.2 Counterfactual reconstruction

shadow log 寫到 `btc_alt_lead_lag_shadow` target；7d 後跑離線 SQL：
```sql
SELECT
    symbol,
    AVG(net_edge_bps) AS avg_net_bps,
    COUNT(*) AS sample_n,
    -- counterfactual: if expected_dir=+1 → assume LONG entry; net_edge_bps proxy from forward 30s-300s alt return
    AVG(CASE WHEN expected_dir = +1 THEN forward_return_bps ELSE 0 END) AS cf_long_avg,
    -- v1.1: regime extreme exclusion，per §9
    AVG(net_edge_bps) FILTER (WHERE regime_tag = 'normal') AS avg_net_bps_normal_regime,
    COUNT(*) FILTER (WHERE regime_tag = 'extreme') AS extreme_regime_n
FROM btc_alt_lead_lag_shadow_with_forward_returns
WHERE engine_mode = 'paper' AND ts >= NOW() - INTERVAL '7 days'
GROUP BY symbol;
```

### 7.3 Strict shift(N) leak-free 對比強制（v1.1 condition #4）

**Counterfactual backtest 必並列 strict `shift(N)` 版 vs naive `[t-N..t]` 版**，差異 > 30% → spec 失敗（log 內含 current bar leak），對照 `feedback_indicator_lookahead_bias.md` Donchian RETRACT 教訓。MIT C-3 D+1 review 同步必跑 strict shift grep verification（`btc_lead_lag_writer.py` 內所有 `rolling()` / `[t-N..t]` slice operation）。

---

## §8 Acceptance Gate（QC + MIT review 必審）

### 8.1 QC C-2 review scope（v1.1 sign-off CONDITIONAL APPROVE — 5 conditions revised in spec）

- **Alpha decay 估算（critical, v1.1 condition #3）**：lead window 60s/120s/300s 對應 forward predictive R² 衰減；N 鎖定 = 120s（per §3.1 Easley/De Prado/O'Hara 2021 + Makarov-Schoar JFE 2020 estimate），但 D+12 evaluate 強制報三檔 decay curve；半衰期 < 60s → spec 失敗，> 300s → window 太長不抓 microstructure
- **DSR penalty K 量化（v1.1 condition #1）**：mu_0 = √(2 ln K)，**K = 95**（active strategy×symbol cell 總數，per Bailey-López de Prado *The Deflated Sharpe Ratio* (2014) §4.2「DSR with multiple trial」；舊草稿錯寫 K=6 = 策略 family 數）→ **mu_0 = √(2 ln 95) = 3.018**。對既有 5 策略 cells DSR PASS shift < 1 σ 空間可忽略；warning：8 cohort × 2 strat 全 promote → K ≈ 111，future ADR 必記錄 K 累積對 multiple-testing budget 長期約束
- **Paper edge gate threshold 三檔（v1.1 condition #5 — 替代原單檔 ≥ +5 bps）**：

| paper avg_net_bps | 動作 | 理由 |
|---|---|---|
| **≥ +15 bps** | promote N+2 demo IMPL（fast track） | demo cost 15-20 bps round-trip → +15 paper edge → demo 環境 ~0 buffer，promote 後 live cost 8-12 bps 才有正 edge headroom |
| **+5 ≤ avg_net_bps < +15** | extend paper window 至 14d，重評（marginal） | 樣本不足 + edge 邊緣，再收 7d 確認；不浪費 N+2 demo |
| **< +5 bps** | revise spec 或 archive | demo cost 下無 net edge survive；單檔 ≥ +5 拍板門檻在 demo 必虧 net −10 ~ −15 bps |

**理由源**：CLAUDE.md §三 cost_gate JS-demo `[40] avg_net = -17.82 → +8.75 bps after V083`（3C audit），demo 5 策略當前 cost burden ≈ 15-20 bps round-trip（fee + slippage + adverse selection）；live 環境降至 ≈ 8-12 bps（PostOnly maker rebate）

**v1.2 +15 bps gate power verification（per MIT C-3 verify §5 net edge σ 視角，N_fills=80, μ=15 bps paper avg_net）**：

| σ_net case | SE = σ_net/√N | t-stat = μ/SE | p-value (one-sided) | verdict |
|---|---|---|---|---|
| **σ_net = 50 bps** | 50/√80 = 5.59 | 15/5.59 = 2.68 | 0.0044 | **comfortable PASS** |
| **σ_net = 80 bps** | 80/√80 = 8.94 | 15/8.94 = 1.68 | 0.0487 | **marginal PASS**（剛 < 0.05 邊緣） |

**結論（v1.2 拍板）**：+15 bps gate 在 σ_net ∈ [50, 80] bps range 全 PASS（lower bound comfortable，upper bound marginal），**門檻設定有效不過寬不過緊**。σ_net = 100 bps 已 FAIL（t-stat=1.34, p=0.092 per MIT report §5），但 EDGE-DIAG-1 baseline 上限 80 bps 之外為極端 case 不在常規 acceptance scope。如 D+12 paper edge report empirical σ_net 顯示超出 80 bps，必觸發 spec revise 重評 +15 gate 是否上調至 +20 bps。

**+5/+15 中段 gate verification**：σ_net=50 bps + μ=10 bps → t-stat=1.79, p=0.039（marginal PASS）；σ_net=80 bps + μ=10 bps → t-stat=1.12, p=0.13（FAIL）→ 中段 gate「extend 14d」決策合理（樣本擴大降 SE 至 SE = σ_net/√160 才可能 PASS upper bound）。

**+5 bps 下界 verification**：σ_net=50 bps + μ=5 bps → t-stat=0.89, p=0.19（FAIL）→ +5 以下 archive/revise 決策合理（無 statistical significance 即 promote 等於賭機）。

- Threshold X / Y / N 三參數最佳值：N=120s 已鎖定（v1.1）；threshold_X=10 bps + threshold_Y=0.40 維持 PA 預設，QC + MIT D+1 review 不再可改

### 8.2 MIT C-3 review scope

- Time-series CV 設計：purged k-fold + embargo（per De Prado 2018 §7.4）；embargo ≥ N seconds 防 leak
- Leak detection（critical）：strict shift(N) 必驗，`rolling(N).max()` 反模式 grep
- Cohort sample size demand：per cohort symbol n ≥ 100 fills 7d 內可達？BTCUSDT 1m 7d = 10080 bar 足夠 lead signal；alt cohort fills 倚賴 5 策略 paper baseline 活躍度
- V088 hypertable PL/pgSQL 語法 + retention drop_chunks policy + idempotency dry-run

### 8.3 三方 sign-off path（v1.2 — MIT C-3 σ verify 已交付，sign-off 簡化）

**v1.2 sign-off path（per MIT C-3 verify report 2026-05-10 已交付）**：
- **QC C-2**：已 sign-off CONDITIONAL APPROVE 5 conditions（v1.1 已落實 spec），**v1.2 dual-layer σ + PSR(0) skew/kurt formula 強制 + +15 bps gate power verification 為 spec 補強**（不增加新 condition），QC 直接收
- **MIT C-3**：σ verify 已交付（report `2026-05-10--w2_c3_sigma_verify_btcusdt_1m_forward_return.md`），dual-layer σ acceptance + PSR(0) skew/kurt formula 已落 spec v1.2，**MIT 直接收，不需 D+1 重 review**
- **W2 IMPL phase 直接啟動**：spec v1.2 sign-off 後 D+3 起派 C-IMPL-1..4 paper IMPL，**不需 D+1 PA + MIT 重 sign-off**（v1.2 補強為 spec internal cleanup，不改 IMPL scope）

**MIT C-3 D+1 review focus（保留 IMPL phase 啟動前驗）**：
- §7.3 strict shift(N) leak-free grep verification（`btc_lead_lag_writer.py` 內 `rolling()` / slice operation 全掃）
- §4.1 V088 hypertable PL/pgSQL 語法 + retention drop_chunks policy + idempotency dry-run
- §4.1 60s/300s shadow value column 寫入路徑與主信號 N=120 disjoint 不污染

**Sign-off 後 timeline**：D+3 起派 C-IMPL-1..4 paper IMPL（C-IMPL-1 NO-OP 驗收 + C-IMPL-2 producer + V088 + C-IMPL-3 strategy shadow + C-IMPL-4 paper engine 7d evidence collection 開始），D+5 paper engine deploy，D+12 paper edge report land（含 §7.1 mandatory metric 6 條 + dual-layer σ acceptance + PSR(0) skew/kurt formula 計算 + +15 bps gate power verification σ_net=50/80 bps 兩 case 並列）。

---

## §9 Risk + Mitigation

| Risk | 等級 | 緩解 |
|---|---|---|
| **Look-ahead bias**（lead window 含 current bar） | **極高** | strict `shift(N)` 禁含 current bar；MIT C-3 必跑 leak detection（per §7.3 strict shift 並列對比，差異 > 30% 即 spec 失敗）；對照 `feedback_indicator_lookahead_bias` |
| **σ acceptance 單層假設不對應真實層**（v1.2 MIT C-3 verify 落地） | **已 closed** | §7.1 acceptance prerequisite v1.2 改 dual-layer σ table（L1 raw market σ_60=4.54/σ_120=6.28/σ_300=10.08 bps + L2 net edge σ=50-80 bps EDGE-DIAG-1 baseline）；spec 30 bps 不對應任何真實層已 retire；強制 prerequisite：spec power calculation 用 net edge σ 禁用 raw market σ；§7.1 metric (3) PSR(0) ≥ 0.95 強制用 Bailey-López de Prado 2012 skew/kurt-aware formula（ex_kurt 7-12 ≫ 0 JB normality 必拒，禁用 normal SR z-test）；§8.1 +15 bps gate σ_net=50/80 bps 兩 case power verification 已落地 |
| **per-symbol n=100 underpowered**（v1.1 condition #4 (1)） | **中** | §7.1 metric (1) per-symbol gate：per-symbol n ≥ 100 + per-symbol t > 2.0 才允許單 symbol promote；不只 overall pooled 看 |
| **K=95 deflate 漏算**（v1.1 condition #1） | **中** | §8.1 spec 文字已修正 K=95（不是 6）；§7.1 metric (2) DSR PASS test 強制 K=95 deflate non-negotiable |
| **+5 bps gate 太鬆無法 survive demo cost**（v1.1 condition #5） | **極高** | §8.1 改三檔 gate（+15 promote / +5~+15 extend 14d / <+5 revise） |
| **Alpha decay quick (half-life < N)**（v1.1 condition #3） | **中-高** | §7.1 metric (4) R²(N=60/120/300) decay curve 強制；半衰期 < 60s → archive；§4.1 schema 加 60s/300s shadow value column 收 evidence |
| **BTC regime extreme**（pump 時 lead signal saturate）（v1.1 condition #5） | **中** | xcorr threshold_Y ≥ 0.40 + return threshold_X clamp ≤ 50 bps（避 outlier 主導）；**v1.1 新加：\|BTCUSDT 1h return\| > 200 bps 視為 regime extreme，shadow log 標 `regime=extreme`（per §4.1 `regime_tag` column）不計入 7d edge avg**（per §7.2 `FILTER (WHERE regime_tag = 'normal')` SQL pattern）；BB regime data 來源：BTCUSDT 1h kline shift(1)，writer 同 1m grain 內每分鐘重算 |
| Self-fulfilling bias（paper engine 自己 trade BTC alt 推動 BTC lead signal） | 高 | 5 策略 paper engine 流量極小（demo 7d gross −26 USDT），對 BTC global liquidity 無影響；但仍 paper-only fence 三層防禦避免 demo 污染 |
| ML pipeline 污染（demo/live 期 BtcLeadLag 寫進 ML training table） | 高 | bb_breakout/bb_reversion/funding_arb 不接收 + paper-only fence Layer 2 Python writer 不啟動 → 5 策略 demo edge baseline 不污染 |
| Cohort 樣本不足 7d 內 < 100 fills | 中 | n ≥ 100 是 gate；不達標延長收 evidence 至 14d 或 cohort 縮減；QC C-2 量化 |
| Bybit rate limit 撞 W1+W3 同窗 | 低 | W2 預估 9 req/min（v1.1 加 BTCUSDT 1h kline 1 req/min = 10 req/min）占 < 1% upper bound（per §4.3）；BB review 確認三 wave 合計 < 50% |
| W6 ML retrain 4-gate 衝突（Q&A pending） | 低 | A4-C 是新 alpha source，不是 ML feature retrain；走 W6 4-gate 不適用本 wave |
| `CrossAsset` enum tag 對應多個未來 panel | 中 | 接受；W-AUDIT-8c 真接 generic 跨資產 panel 時拆 `BtcAltLeadLag` 為獨立 enum variant（ADR 觸發） |
| MIT 揭露 W2 與 W6-5 同類 category error | 待 D+1 review | MIT C-3 D+1 review 必揭露；QC C-2 已 sign-off CONDITIONAL APPROVE 5 conditions 已落地 spec v1.1 |

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
| **W2 E1-δ (C-IMPL-2)** | lead-lag producer + V088 + IPC slot（v1.1 含 60s/300s shadow value column + regime_tag column + BTCUSDT 1h kline regime 計算 + strict shift(N) lookahead-free） | `program_code/.../btc_lead_lag_writer.py`（新）+ `sql/migrations/V088__btc_lead_lag_panel.sql`（新）+ `rust/openclaw_engine/src/ipc_server/slots.rs`（加 `BtcLeadLagPanelSlot`） + `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`（一行 surface field assignment + paper-only engine_mode gate） | ~400 LOC（v1.1 +50 LOC for regime_tag + 60s/300s shadow value + 1h kline integration） |
| **W2 E1-ε (C-IMPL-3)** | strategy paper-only shadow | `ma_crossover/strategy_impl.rs`（declare `CrossAsset` + on_tick shadow log）+ `grid_trading/mod.rs`（同） | ~80 LOC |
| **W2 E1-ζ (C-IMPL-4)** | paper engine 7d evidence collection 開始 | 操作 only，無代碼；D+5 起 paper engine deploy 後跑 7d；D+12 land paper edge report | 0 LOC |

**衝突點全部消除**：alpha_surface.rs trait 已 PA D+0 commit；slots.rs / step_4_5_dispatch.rs 用 anchor comment 隔離 W1+W2 sub-agent；V088 編號預留無撞。

---

## §12 E2 重點審查 3 點（v1.1 補強）

per PA 輸出物標準：

1. **Layer 1 paper-only fence default → None**：E2 必 grep `btc_lead_lag = match self.effective_engine_mode()` in step_4_5_dispatch.rs，confirm `_ => None`（**不是** `_ => Some(...)`）。漏 `None` default = demo/live 污染主路徑。

2. **Strict shift(N) lookahead-free 驗證（v1.1 condition #4）**：E2 必 grep `btc_lead_lag_writer.py` 內所有 `rolling()` / `[t-N..t]` slice operation，確認 BTC return（含 N=60s + N=120s + N=300s 三檔 shadow value）/ volume z-score 計算 strict 用 `shift(1)` 後的 N 秒前 value，**禁** include current bar；BTCUSDT 1h kline regime 計算同樣 strict shift(1)。對照 `feedback_indicator_lookahead_bias` Rolling-window breach 反模式。MIT C-3 D+1 review 同步必跑 grep（Q4 strict shift 並列對比 §7.3，差異 > 30% spec 失敗）。

3. **V088 hypertable retention drop_chunks policy 必設 + v1.1 schema 完整**：E2 + MIT 必審 V088 SQL 含 `SELECT add_retention_policy('panel.btc_lead_lag_panel', INTERVAL '14 days');`；漏設 → PG table 永久膨脹。**v1.1 schema 補完驗證**：必含 `btc_lead_return_pct_60s` + `btc_lead_return_pct_300s` + `regime_tag` 三新欄位（per §4.1 condition #3 + condition #5）。idempotency dry-run 兩次，第二次必須不 RAISE。

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

## §14 一句總結（v1.2）

**A4-C BTC→Alt Lead-Lag W-AUDIT-8c 候選 C 的 N+1 fast-track 預跑（v1.2 MIT C-3 σ verify 落地 dual-layer σ + PSR(0) strict）：BTCUSDT 1m kline + orderbook 算 lead signal（return / volume z / book imbalance over N=120s **鎖定**，60s/300s shadow value 同 schema 收 decay curve evidence）+ BTCUSDT 1h kline 算 regime_tag（\|1h return\| > 200 bps → extreme，shadow log 不計入 7d edge avg）→ 7-symbol alt cohort xcorr + expected_dir 寫 `panel.btc_lead_lag_panel` (V088 hypertable, retention 14d) → ma_crossover + grid_trading 在 paper engine mode 接 `BtcLeadLag` 為 `CrossAsset` tag, on_tick shadow log only 不 trade（C-IMPL-3）；三層 paper-only fence + strict shift(N) lookahead-free 保證 demo/live engine 永遠 surface.btc_lead_lag = None 不污染 5 策略 demo edge baseline；7d paper engine 收 evidence，**gate 三檔（avg_net ≥ +15 bps promote N+2 / +5~+15 extend 14d / <+5 revise）+15 bps gate 已 verify σ_net=50 bps t-stat=2.68 p=0.0044 / σ_net=80 bps t-stat=1.68 p=0.0487 全 PASS**，DSR PASS 用 K=95 deflate (mu_0 = √(2 ln 95) = 3.018)，**PSR(0) ≥ 0.95 強制用 Bailey-López de Prado 2012 skew/kurt-aware formula（ex_kurt 7-12 ≫ 0 JB normality 必拒，禁用 normal SR z-test），σ_net=80 bps + ex_kurt=10 → PSR(0) ≈ 0.94 必並列 σ_net=50/80 兩 case**，per-symbol n ≥ 100 + per-symbol t > 2.0 才允許單 symbol promote，block-bootstrap 95% CI block_size=60min 1000 iter，alpha decay R²(N=60/120/300) 三檔 curve 強制；**σ acceptance v1.2 改 dual-layer：L1 raw market σ_60=4.54/σ_120=6.28/σ_300=10.08 bps（MIT C-3 verify）用於 alpha decay R² baseline + L2 net edge σ=50-80 bps EDGE-DIAG-1 baseline 用於 power calculation + PSR(0) deflation；spec 30 bps 不對應任何真實層已 retire**；trait skeleton 已 PA D+0 commit (HEAD c9fb0b8f) IMPL phase 全 0 file 重疊 0 git merge 衝突；16 原則 + DOC-08 §12 不變量 + 硬邊界 5 項全 0 觸碰；QC C-2 已 sign-off CONDITIONAL APPROVE 5 conditions 落 spec v1.1，MIT C-3 σ verify 已交付 dual-layer σ + PSR(0) strict 落 spec v1.2 → **QC + MIT 直接收 W2 IMPL，不需 D+1 PA + MIT 重 sign-off**。**

---

**Spec v1.2 end. PA C-1 spec dual-layer σ + PSR(0) skew/kurt strict + +15 bps gate power verification land。QC C-2 已 sign-off，MIT C-3 σ verify 已交付 → QC + MIT 直接收 W2 IMPL → D+3 起派 C-IMPL-1..4 paper IMPL，D+5 paper engine deploy 後跑 7d，D+12 paper edge report land（含 §7.1 mandatory metric 6 條 + dual-layer σ acceptance + PSR(0) skew/kurt formula 計算 + +15 bps gate power verification σ_net=50/80 bps 兩 case 並列）。**

PA DESIGN DONE: report path: srv/docs/execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md（v1.2）
