# G3-09 cost_edge_ratio Hot-Path Integration RFC（PA Plan Only）

- **作者**：PA（Project Architect）
- **日期**：2026-04-26
- **Tier**：9 Track 2
- **狀態**：Plan only — 不寫實作代碼
- **觸發**：CLAUDE.md §二 原則 #13「AI 資源成本感知 — 每次 AI 調用計費，cost_edge_ratio ≥ 0.8 → 建議關倉」+ Tier 8 G3-08 Phase 3 COMPLETE（H5 cost_logging Rust hot-path snapshot ≤1ms p99 已 live）
- **依賴前置**（硬阻塞 ✅）：
  - G3-08 Phase 1（commits `aa287c4` / `1c7b20e` / `5943337` / `9120948` / `f2ed286`）
  - G3-08 Phase 3 H5 sub-task 3-3（commit `d1a2252`，Tier 8 Track 4 sign-off `e5f1b2d`）
  - `Layer2CostTracker.get_h5_snapshot()` 4-field projection 已 land
  - Rust `H5CostStats` (`h_state_cache/types.rs:167-178`) `cost_edge_ratio: Option<f64>` field 可達
- **解阻 後續**：
  - Phase 4 5-Agent state events（弱依賴：Strategist/Executor stats 與 cost-aware 決策有交互）
  - Layer 2 自主推理「資源成本感知」具體措施（`memory/project_layer2_agent_design.md`）

---

## §1 背景

### 1.1 CLAUDE.md §二 原則 #13 完整重述

> **AI 資源成本感知** — 每次 AI 調用計費，cost_edge_ratio ≥ 0.8 → 建議關倉

**字面解析**：
- **誰計費**：H5 `Layer2CostTracker.record_claude_cost()` + `record_search_cost()`，以 USD/cycle 累積
- **誰計算 ratio**：`Layer2CostTracker.get_cost_edge_ratio()` (line 860-896)
- **比率語意**：`paper_pnl_7d_usd / ai_spend_7d_usd`（**注意原則 10 認知誠實**：分子是 paper PnL，非真實交易 PnL）
- **觸發閾值**：≥ 0.8（**模糊處**：0.8 是 ratio 還是「abs 值」？看公式 paper_pnl/ai_spend，ratio 越**小**越糟，**大**越好。CLAUDE.md 原文「≥ 0.8」與公式方向**矛盾**——詳 §2.4 解析）
- **建議關倉**：「建議」非強制；落地語意未明確（advisory log? gate 阻新倉？close 持倉？）

### 1.2 Phase 3 H5 解阻具體影響

**G3-08 Phase 3 sub-task 3-3 commit `d1a2252` 結果**：
- Python 側：`Layer2CostTracker.get_h5_snapshot()` 回 4-key dict（drop `roi_basis` / `roi_disclaimer` metadata）+ 2 invalidate hooks (`record_claude_cost` 加 `h5.claude_cost_recorded` / `record_search_cost` 加 `h5.search_cost_recorded`)
- Rust 側：`h_state_cache/types.rs:167-178 H5CostStats` 4 fields (`ai_spend_7d_usd: f64` / `paper_pnl_7d_usd: f64` / `cost_edge_ratio: Option<f64>` / `data_days: u32`) `#[serde(default)]` 全可選
- IPC：每 10s daemon poll + invalidation hint 提早 ad-hoc poll，DashMap shard lookup ≤ 1ms p99

**對 G3-09 的關鍵效應**：
- Rust hot-path 直讀 `h_state_cache.snapshot().h5.cost_edge_ratio` 可拿到當前值
- 無 IPC roundtrip（hot-path SLA ≤ 1ms 達標）
- staleness 30s 容忍下 fail-soft（Python crash 沿用 last good snapshot + stale flag）
- `Option<f64>::None` = data_days < ADAPTIVE_MIN_DAYS=3 樣本不足，**G3-09 必須處理 None 情況**（fail-closed 預設 = 不觸發關倉，因樣本不足無權判斷）

### 1.3 為什麼 Phase 3 之前不能做 G3-09

| 阻塞點 | Phase 3 前 | Phase 3 後 |
|---|---|---|
| Rust hot-path 取 cost_edge_ratio | 必走 IPC roundtrip 1-3ms | DashMap lookup ≤1ms p99 |
| Python crash 韌性 | Rust 卡死或拿 stale value 不知 | 沿用 last good snapshot + staleness flag |
| Schema 演化 | 改一次 lock-step Python+Rust deploy | `#[serde(default)]` forward-compat |

G3-09 演算法本身**不複雜**（單一閾值比較 + 觸發 advisory event），瓶頸是「Rust 端能不能即時讀 H5 cost_edge_ratio」+「破壞性低 + 可逆 + 多 env 安全」。Phase 3 解了第一個，本 RFC 解後三個。

---

## §2 演算法定義

### 2.1 公式（沿用 Python `get_cost_edge_ratio`）

```
cost_edge_ratio = paper_pnl_7d_usd / ai_spend_7d_usd  (when data_days >= 3 and ai_spend > 0)
                = None                                  (otherwise)
```

**單位**：dimensionless（USD/USD），可正可負可零。

**範例**：
- ai_spend = $4.23、paper_pnl = -$2.15 → ratio = **-0.508**（虧錢但不嚴重）
- ai_spend = $5.00、paper_pnl = $2.50 → ratio = **0.50**（賺一半）
- ai_spend = $5.00、paper_pnl = -$5.00 → ratio = **-1.0**（每塊 AI 錢虧一塊）
- ai_spend = $1.00、paper_pnl = -$10.0 → ratio = **-10.0**（極端負，稀有）
- ai_spend = $10.0、paper_pnl = $8.00 → ratio = **0.80**（正向 80%）

### 2.2 變數來源（Rust 端）

```rust
// rust/openclaw_engine/src/h_state_cache/types.rs:167-178
pub struct H5CostStats {
    pub ai_spend_7d_usd: f64,        // 已可達
    pub paper_pnl_7d_usd: f64,       // 已可達
    pub cost_edge_ratio: Option<f64>, // 已可達（Python 預先算好）
    pub data_days: u32,               // 已可達
}
```

Rust hot-path 取值：

```rust
// pseudocode
let h5 = h_state_cache.snapshot().h5;
let ratio_opt = h5.cost_edge_ratio;       // Option<f64>
let data_days = h5.data_days;              // u32
let stale = h_state_cache.is_stale();     // bool（staleness > 30s）
```

### 2.3 ratio 與 trigger 關係 — Hold/Lock 二值

**設計原則**（衍自 #13）：
1. ratio **大** = AI 投資回報好 → **不**觸發
2. ratio **小**（負或趨負）= AI 燒錢沒報酬 → **觸發**「建議關倉」
3. `None`（data_days < 3）= 樣本不足 → **不**觸發（fail-closed 不擅自關倉）
4. `Some(NaN)` 或 `Some(Inf)` = 數值異常（理論上不可能但 defensive）→ **不**觸發 + emit warn log

### 2.4 CLAUDE.md「ratio ≥ 0.8 → 建議關倉」的方向性矛盾

**字面條文**：「cost_edge_ratio ≥ 0.8 → 建議關倉」
**實際公式語意**：ratio 越大越好（賺錢）→ ≥ 0.8 表示**很賺**，不應該關倉
**結論**：CLAUDE.md 原文與 `get_cost_edge_ratio` 公式方向**互相矛盾**

**3 種可能解釋**：

| 解釋 | 含義 | 評估 |
|---|---|---|
| A. ≥ 0.8 是 typo，應為 ≤ -0.8 | 嚴重虧 → 關倉 | 與「燒錢」一致，但跳整個 0 區間 |
| B. ≥ 0.8 是 typo，應為 ≤ 0.8 | 不賺 80% → 關倉 | 過度敏感（每虧一點就關倉）|
| C. ratio 公式應為 `ai_spend / paper_pnl`（倒數）| 越小越好 → ≥ 0.8 = 燒得太兇 | 與 Python 公式不一致，需重命名 |

**Recommend**：採 **解釋 A 變體** — `cost_edge_ratio ≤ COST_EDGE_TRIGGER_THRESHOLD` 觸發，**初始 threshold 可調**，為**負值**（保守起步 -0.5，運行 ≥30d 後 calibrate per memory `feedback_demo_over_paper_for_edge`）。

**理由**：
- 解釋 A 邏輯一致（虧錢觸發）+ 與既有 `get_cost_edge_ratio` 公式向兼容
- 0.8 改 threshold value 為 operator-tunable 而非硬編碼，避免反覆糾結 CLAUDE.md 字面值
- 初始 -0.5 = 「paper 虧損達 AI 花費 50%」= 顯著燒錢狀態（≠ 隨機波動）

**保留 0.8 字面義的退路**：本 RFC 推薦 `RiskConfig.exit.cost_edge_trigger_threshold: f64`（預設 -0.5），允許 operator 將 threshold 改為任意值（包含 0.8 若解釋為「正向但低於成本回收期望」）。RFC 不鎖死，留 operator 經驗校準權力。

### 2.5 Cost-aware close 的「建議」語意（advisory vs binding）

CLAUDE.md 原文「**建議**關倉」非「**強制**關倉」，3 種落地語意：

| 落地語意 | 行為 | 風險 |
|---|---|---|
| L1: advisory log only | hot-path log warn + 寫 audit；不影響 close decision | 安全但無實質效果（與 healthcheck 等同） |
| L2: gate 阻新倉 | 從觸發起 reject 新 SubmitOrder（IntentProcessor 加 gate） | 中（不關現有倉，避免 false-positive close） |
| L3: 觸發 close | 視為 risk_close 行動，與 P0/P1 風控同 priority | 高（false-positive 直接虧損） |

**Recommend Phase rollout**：
- **Phase A schema** = L1 advisory only（log + audit + healthcheck，純 observability）
- **Phase B shadow** = L1 + DryRun 模擬「若 trigger 會關哪些倉」(`exit_source = ShadowCostEdge`)
- **Phase C live triggered** = L2 阻新倉（**不**強制關現有倉）+ Operator 顯式 enable

**為什麼 L3 不推**：
- false-positive 直接虧損（vs L2 只是錯過機會）
- AI 成本 ≠ position 成本，attribute confusion（一個 BTCUSDT 倉位被關 ≠ 它導致 AI 燒錢）
- 「哪個倉位最該關」演算法複雜，會撞上既有 P0/P1 hard_stop / Track P phys_lock 邏輯

**未來** L3 可選：搭配 Phase 4 5-Agent state 聯動（如 `Strategist.intel_evaluated >> intents_produced` 表「成本不對等」可作補充信號），需另寫 RFC。本 G3-09 不涉。

---

## §3 Hot-Path Integration 候選評估

### 3.1 候選 1：`intent_processor::gates::cost_gate_*`

**位置**：`rust/openclaw_engine/src/intent_processor/gates.rs:14-216`（既有 cost_gate_paper / cost_gate_moderate / cost_gate_live 三函式）

**整合方式**：在既有 cost_gate 框架內加 `cost_edge_ratio_gate()` sibling，或在現有 cost_gate 函式末尾追加 cost_edge_ratio 檢查。

**優點**：
- 對應 §2.5 L2 語意（gate 阻新倉，不關現有倉）= 與 cost_gate 既有定位（pre-trade gate）一致
- 既有 cost_gate 結構成熟（slippage tier + win-rate weighting + grand_mean fallback）
- gates.rs 217 行尚有空間（800 警告線）
- E2 review 路徑簡單（cost_gate 是 review focus area）

**缺點**：
- 與 cost_gate_grand_mean 概念有重疊風險（兩 gate 都是「成本壓不住 edge → 拒」），operator 配置時可能混淆
- per-intent 觸發頻率高，audit emit rate 需控（>每 intent 1 條會撐爆 audit log）

### 3.2 候選 2：`combine_layer::combine_exit_decision`

**位置**：`rust/openclaw_engine/src/combine_layer.rs:183`（physical/ml fusion 主路徑）

**整合方式**：在 combine_exit_decision 加新 branch — 當 physical=Hold + ml=None 時檢查 cost_edge_ratio，超 threshold → `ExitSignal::Lock` + `ExitSource::CostEdge { ratio, threshold }`

**優點**：
- 對應 §2.5 L3 語意（**強制**關倉，與 P0/P1 同優先級）
- combine_layer 是 exit decision 唯一 unified point，不分散邏輯
- Phase 1a INFRA-PREBUILD-1 Part A shadow_enabled 已準備 dual-write，shadow infra 可重用

**缺點**：
- ❌ **致命**：與 §2.5 L3 風險高度重合（false-positive 直接虧損）
- combine_layer 設計意圖是「physical vs ML fusion」，加 cost_edge_ratio 違反 single-responsibility
- 觸發後關**哪些**倉位邏輯複雜（每倉 evaluate cost_edge？= scope creep）
- 與 EX-04 Reconciler 對賬路徑潛在衝突（risk_close 大量觸發會擾亂 paper_state 對賬）

### 3.3 候選 3：`physical_micro_profit_lock_v2`

**位置**：`rust/openclaw_engine/src/exit_features/v2.rs:305`（4-Gate phys_lock 主函式）

**整合方式**：加第 5 Gate「Gate 5 cost-edge」— 在 Gate 4 後檢查 cost_edge_ratio，超 threshold → Lock with `phys_lock_cost_edge_trigger` reason

**優點**：
- v2 函式為 pure fn，加 gate 結構清晰
- 與 phys_lock 既有 4-Gate「依序過濾」pattern 一致
- 重用既有 `phys_lock_*` reason 字串 + `parse_exit_tag` 下游 parser

**缺點**：
- ❌ **致命**：違反 v2.rs:8-13 設計意圖「**只有 Gate 4 (trailing) 才是合法的 Lock 路徑**」（DUAL-TRACK-EXIT-1 §三 L108-111）— 加 Gate 5 = 違反核心契約
- v2 是 per-position 評估，cost_edge_ratio 是 portfolio-level metric — semantic mismatch（每倉位都用同個 ratio，重複觸發）
- 與 §3.2 同 false-positive 風險（per-position 強制 close）

### 3.4 候選 4：新建 `cost_edge_advisor`（模組級新檔）★ **推薦**

**位置**：新建 `rust/openclaw_engine/src/cost_edge_advisor/mod.rs`（~200 LOC）

**機制**：
- 純 advisory 模組，無 hot-path close 邏輯
- 由現有 hot-path 點（intent_processor 入口 + tick pipeline 適當點）**讀取** advisor state，進行 conditional gate
- Advisor 自身**不**觸發 close，只更新內部 state「現在是否處於 cost-edge 警告態」
- Phase A only emit advisory log + audit + healthcheck
- Phase B 加 shadow dry-run（log「假設 binding 會 reject N 個 intent」）
- Phase C 加 IntentProcessor.cost_edge_pre_intent_check() 阻新倉 gate（但不關現有倉）

**ASCII 流程圖**：

```
H5 H State Cache (Phase 3 ✅) ──read──▶ cost_edge_advisor.evaluate(snapshot)
                                                  │
                                                  ▼
                                       Advisor State {
                                         status: OK / Warn / Trigger,
                                         ratio: Option<f64>,
                                         threshold: f64,
                                         data_days: u32,
                                         last_eval_ms: i64,
                                       }
                                                  │
                                ┌─────────────────┼─────────────────┐
                                ▼                 ▼                 ▼
                       Phase A: log only    Phase B: dry-run    Phase C: gate
                       audit + healthcheck   shadow rejection    IntentProcessor
                                              count                pre-intent check
```

**優點**：
- ★ Single-responsibility（cost_edge logic 獨立）
- ★ Phase A advisory only = 0 trade impact，可 24h dogfood
- ★ Phase B shadow 可在 0 風險下驗 trigger 頻率合理性
- ★ Phase C gate 阻新倉是最低破壞性的「建議關倉」實踐
- ★ 不違反 v2.rs Gate 4-only Lock 契約（cost_edge ≠ phys_lock）
- ★ 與既有 cost_gate（per-intent）區分清楚（cost_edge_advisor = portfolio-level）
- ★ 解 §2.5「建議」語意 — advisor 結構自然 modulate close 觸發點（**不**自己 close）

**缺點**：
- 新模組成本（schema + tests + doc）
- 需訓練 operator 區分 cost_gate vs cost_edge_advisor

### 3.5 候選 5：`risk_checks::check_position_on_tick` 新 risk action

**位置**：`rust/openclaw_engine/src/risk_checks.rs:382-388`（既有 phys_lock_v2 caller）

**整合方式**：在 phys_lock_v2 之後加新 RiskAction::AdvisoryClose 分支，類似 §3.3 但作 caller 級而非 callee

**優點**：
- 與既有 RiskAction 列舉自然擴展
- 不破壞 v2 pure fn 契約

**缺點**：
- 仍是 per-position 評估（同 §3.3 semantic mismatch）
- 新 RiskAction 變體需 dispatch.rs 全鏈跟改

### 3.6 5 候選評估矩陣

| 評分維度 | 1 cost_gate | 2 combine_layer | 3 phys_lock_v2 | **4 advisor** ★ | 5 risk_checks |
|---|---|---|---|---|---|
| Single responsibility | 中（與 cost_gate 重疊）| 低 | 低（破 4-Gate 契約） | ✅ 高 | 中 |
| False-positive 風險 | 中 | 高 | 高 | ✅ 低（Phase A/B advisory）| 高 |
| Phased rollout 易度 | 中 | 中 | 低 | ✅ 高（A/B/C 三階乾淨） | 中 |
| 與既有 16 原則一致 | 中 | 中 | 低 | ✅ 高 | 中 |
| Hot-path SLA | ✅ 1μs | ✅ 1μs | ✅ 1μs | ✅ 1μs（簡單比較）| ✅ 1μs |
| Cross-env safety（paper/demo/live） | 中 | 低 | 低 | ✅ 高（advisory 不執行）| 低 |
| LOC cost | 低（~50） | 中（~120） | 中（~80） | 中（~200）| 中（~100） |
| 可逆性 | 中（cost_gate 已上線難回退） | 低 | 低 | ✅ 高（env-gate + Phase rollback）| 中 |
| **總分** | 5/8 | 2/8 | 1/8 | **8/8** | 4/8 |

### 3.7 推薦：**候選 4 cost_edge_advisor 模組**

**核心理由**：
1. **Single-responsibility 滿足**：cost_edge logic 與 cost_gate（per-intent slippage）+ phys_lock（per-position trailing）+ combine_layer（exit fusion）物理隔離
2. **「建議關倉」語意自然落地** — advisor 結構天生對應 advisory，Phase rollout 可 0 → A → B → C 漸進放權
3. **Cross-env 安全**：Phase A advisory only，paper/demo/live 三 env 行為一致（純 log/audit），無 trade path 影響
4. **不違反 DUAL-TRACK-EXIT-1 契約**：cost_edge_advisor 不在 v2.rs Gate 序列內，Gate 4-only Lock 契約保留

---

## §4 「建議關倉」執行語意（Phased）

### 4.1 與既有 P0/P1 風控止損的關係

| 既有 risk 機制 | 觸發條件 | 動作 | 與 cost_edge 關係 |
|---|---|---|---|
| P0 hard_stop | 跌破 entry × (1 - hard_stop_pct) | RiskAction::ClosePosition | **獨立**：hard_stop 是 single-position max-loss，與 cost_edge 無直接衝突 |
| P0 trailing_stop | peak × (1 - trailing_pct) | RiskAction::ClosePosition | **獨立**：track P phys_lock_v2 主導，cost_edge 不影響 |
| P1 ATR phys_lock_v2 | 4-Gate 通過 | RiskAction::ClosePosition (`phys_lock_*`) | **獨立**：v2 Gate 4-only Lock 契約保留 |
| P1 SESSION DRAWDOWN | session_drawdown_pct >= max | RiskAction::HaltSession | **獨立**：session-level kill switch，cost_edge 不影響 |
| P2 cost_gate | per-intent slippage breach | reject intent | **互補**：cost_gate 是 per-intent，cost_edge 是 portfolio-level |
| **G3-09 cost_edge_advisor (NEW)** | ratio ≤ threshold + data_days >= 3 | Phase A: log + audit / Phase B: shadow / Phase C: gate 新倉 | **互補非衝突**，Phase C 阻新倉不影響既有倉位 close 路徑 |

### 4.2 Phase A 觸發語意（advisory only）

**邏輯**：

```
EVERY 10s (or on_invalidate from H5):
  cache = h_state_cache.snapshot()
  h5 = cache.h5
  if cache.is_stale():
    advisor.status = Stale  // 不更新 ratio，沿用 last good
    return
  match h5.cost_edge_ratio:
    None => advisor.status = WarmUp  // data_days < 3
    Some(ratio) if ratio.is_nan() || ratio.is_infinite() => advisor.status = Anomaly
    Some(ratio) if ratio <= threshold => {
      advisor.status = Trigger
      advisor.ratio = Some(ratio)
      advisor.audit_emit("cost_edge_trigger", ratio, threshold, h5.data_days)
      log::warn!("cost_edge_advisor triggered: ratio={:.3} <= threshold={:.3}", ratio, threshold)
    }
    Some(ratio) => {
      advisor.status = OK
      advisor.ratio = Some(ratio)
    }
```

**Action**：純更新 `advisor.status` + log + audit，**不影響任何 trade path**。

### 4.3 Phase B 觸發語意（shadow dry-run）

Phase A 邏輯保持。額外加 shadow counter：當 status=Trigger 時，IntentProcessor `process_intent()` 入口先進入 advisor.would_reject(intent) check，若 would-reject = true 則 `advisor.shadow_reject_count += 1` + log dry-run reason，**不真實 reject**。

### 4.4 Phase C 觸發語意（gate 新倉）

Phase A + Phase B 邏輯保持。額外加 binding gate：當 status=Trigger 且 `RiskConfig.exit.cost_edge_gate_enabled=true` 時，IntentProcessor `process_intent()` 入口直接 reject 新倉（`reject_reason = "cost_edge_advisor: ratio ≤ threshold"`）。

**重要 — 不關現有倉**：
- Phase C 只阻新 SubmitOrder，**不**對既有 position 強制 close
- 既有倉位仍由 P0/P1 hard_stop / trailing / phys_lock_v2 / SESSION DRAWDOWN 各自管理
- 「建議關倉」的「關倉」實際**透過自然滾動關閉**（既有止損機制自會關，cost_edge 只是不讓新倉開）

**可逆**：env=0 即整個 advisor 進入 dormant，Phase C gate 等同 noop。

---

## §5 Threshold 設計

### 5.1 初始值（per memory `feedback_demo_over_paper_for_edge`）

**Recommend 預設**：`COST_EDGE_TRIGGER_THRESHOLD = -0.5`

**理由**：
- ratio ≤ -0.5 = paper PnL 虧損達 AI 花費 50% = 顯著燒錢
- 0 vs -1 中間取保守值，避免 false-positive
- 經驗無據（CLAUDE.md 0.8 字面義方向矛盾），故採保守起點 + operator calibrate

### 5.2 per-strategy override pattern（對齊 G2-03 schema staging）

**Recommend B2 候選**（per `2026-04-26--g2_03_option_b_rfc.md`）— 擴 `RiskConfig.per_strategy.StrategyOverride` 加 `cost_edge_threshold_override: Option<f64>`

**為什麼 per-strategy**：
- 不同策略 AI 需求不同（grid 低需求 / ma_crossover 高需求）→ ratio 可比性差
- per-strategy override 讓 ma_crossover 用 -1.0（高燒錢容忍），grid 用 -0.3（低容忍）
- 對齊 G2-03 RiskConfig.per_strategy 既有 staging 不增新 schema 層

**Schema patch（Phase A 不落，Phase C 才落）**：

```rust
// rust/openclaw_engine/src/config/risk_config_per_strategy.rs
pub struct StrategyOverride {
    // ... 既有 4 SL/TP override 字段（G2-03 已 land）...

    /// G3-09 cost_edge per-strategy threshold override.
    /// `None` = use global RiskConfig.exit.cost_edge_trigger_threshold.
    /// G3-09 cost_edge per-strategy 閾值 override；None = 用全域。
    #[serde(default)]
    pub cost_edge_threshold_override: Option<f64>,
}
```

### 5.3 Threshold 動態 calibration（Phase D + 留給未來）

**Phase A/B/C 不涉**，但設計留 hook：

- 累積 ≥30d demo 數據後，可 cron run `helper_scripts/research/cost_edge_threshold_calibrator.py` 算 per-strategy「經驗 ratio 分布 5th/95th percentile」
- Operator manual approve 後 IPC `patch_risk_config` 寫入新 threshold
- **嚴禁**自動 binding（per memory `feedback_env_config_independence` 自動寫風控 = 高風險，與 EDGE-P1b RFC §3 同 SOP）

---

## §6 Audit / Observability

### 6.1 Rust → Python audit IPC

**Pattern**：對齊既有 `phys_lock` audit emit pattern（emit_close_fill 走 trading_writer，audit log 走 audit channel）。

**新增 audit event type**：

```rust
// rust/openclaw_engine/src/audit/types.rs（or 既有 audit module）
pub enum AuditEvent {
    // ... 既有 events ...

    /// G3-09 cost_edge_advisor trigger event.
    /// G3-09 cost_edge_advisor 觸發事件。
    CostEdgeAdvisorTrigger {
        ratio: f64,
        threshold: f64,
        data_days: u32,
        ai_spend_7d_usd: f64,
        paper_pnl_7d_usd: f64,
        phase: String,  // "A_advisory" / "B_shadow" / "C_gate"
        triggered_at_ms: i64,
    },

    /// G3-09 status transitions (OK / Warn / Trigger / WarmUp / Stale / Anomaly).
    CostEdgeAdvisorStatusChange {
        prev_status: String,
        new_status: String,
        at_ms: i64,
    },
}
```

**Emit 頻率**：
- Phase A trigger 事件：state 變化時 emit（OK→Trigger / Trigger→OK），**不**每 evaluate cycle 重複（避免 audit 撐爆）
- Status change 事件：所有狀態變化（含 Trigger→Trigger 不發，確保 idempotent）

### 6.2 Healthcheck [22] spec

**新增 `helper_scripts/db/passive_wait_healthcheck.py [22]`**：

```python
def check_cost_edge_advisor_status() -> tuple[str, str]:
    """[22] G3-09 cost_edge_advisor status freshness + state inspection.

    當前 healthcheck slot allocation:
        [19] paper_state_dust_inventory (per dust_restore_audit RFC §7 → §13 Deviation Log
             slot upgrade [19]→[21] 已記錄；當前 [19] 是 observer pipeline)
        [20] h_state_gateway freshness (Phase 1C live)
        [21] paper_state_dust_inventory (per dust_restore_audit RFC §13 amend slot)
        [22] (NEW, this) cost_edge_advisor status

    PASS rules:
    - env=0 (advisor not enabled) → PASS skip
    - env=1 + status in {OK, WarmUp, Stale} → PASS
    - env=1 + status=Trigger 持續 < 1h → WARN (尚屬正常；可能短期 ratio 觸線)
    - env=1 + status=Trigger 持續 >= 1h → FAIL (持續觸發需 operator 注意)
    - env=1 + status=Anomaly → FAIL (NaN/Inf 數值錯誤，需 P0 audit)
    - env=1 + advisor.last_eval_ms 過時 > 60s → FAIL (advisor daemon 卡住)
    """
    if os.environ.get("OPENCLAW_COST_EDGE_ADVISOR") != "1":
        return "PASS", "cost_edge_advisor disabled (env=0), skipping"
    status = ipc_call("get_cost_edge_advisor_status", {})
    if not status:
        return "FAIL", "advisor status unavailable (IPC failed)"
    last_eval_ms = status.get("last_eval_ms", 0)
    age_sec = (now_ms() - last_eval_ms) / 1000.0
    if age_sec > 60:
        return "FAIL", f"advisor last_eval_ms stale {age_sec:.0f}s > 60s"
    state = status.get("status", "UNKNOWN")
    if state in ("OK", "WarmUp", "Stale"):
        ratio = status.get("ratio")
        return "PASS", f"status={state} ratio={ratio if ratio is None else f'{ratio:.3f}'}"
    if state == "Trigger":
        trigger_age_sec = (now_ms() - status.get("triggered_at_ms", 0)) / 1000.0
        ratio = status.get("ratio")
        if trigger_age_sec < 3600:
            return "WARN", f"TRIGGER ratio={ratio:.3f} for {trigger_age_sec:.0f}s (< 1h)"
        return "FAIL", f"TRIGGER ratio={ratio:.3f} for {trigger_age_sec:.0f}s (>= 1h, operator attention needed)"
    if state == "Anomaly":
        return "FAIL", "ratio NaN/Inf - data corruption suspected (P0)"
    return "FAIL", f"unknown advisor status: {state}"
```

**新 IPC handler**：`get_cost_edge_advisor_status` 回 `{status, ratio, threshold, data_days, last_eval_ms, triggered_at_ms, shadow_reject_count_24h}`。

### 6.3 GUI dashboard hook（不是 G3-09 範圍但留指標）

healthcheck [22] + IPC `get_cost_edge_advisor_status` 已足供 GUI 拉取展示。Phase A 未要求新 GUI tab；Phase B/C 啟動可選 add `learning_cockpit` 上加 cost_edge advisor 狀態 widget（屬 GUI ticket）。

---

## §7 Phase Rollout 路線圖

### 7.1 Phase A：schema 落地 + advisory only（解阻 G3-09 PRD）

**範圍**：
- 新建 `rust/openclaw_engine/src/cost_edge_advisor/{mod.rs, types.rs, advisor.rs, tests.rs}` (~500 LOC + ~250 tests)
- 修改 `RiskConfig` 加 `pub cost_edge: CostEdgeConfig`（新 sub-struct，2 fields: `enabled: bool` (預設 false) + `trigger_threshold: f64` (預設 -0.5)）
- 修改 `main_boot_tasks.rs` env-gate spawn cost_edge_advisor daemon
- 新 IPC `get_cost_edge_advisor_status` handler
- 新 audit event types (CostEdgeAdvisorTrigger / StatusChange)
- 新 healthcheck [22]
- 3 env TOML 加 `[cost_edge]` section（全 enabled=false 預設）

**完成標準**：
- env=1 + advisor daemon spawn + 每 10s evaluate H5 snapshot + status 隨 ratio 變化
- env=0 全 dormant（advisor not spawned，IPC return uninitialized）
- 24+ Rust unit tests（5 status transitions × OK/Warn/Trigger/WarmUp/Stale/Anomaly 邊界）+ 5 IPC integration test
- healthcheck [22] cron 6h 跑 + 紀錄連續 24h 全 PASS（env=0 PASS skip）
- Cross-env 三 toml 驗 hot-reload 不破

**工時**：
- E1-Alpha (Rust advisor) 3d + E1-Beta (IPC handler + audit + healthcheck) 1.5d + E2 0.5d + E4 0.5d = **5.5d 全鏈**（並行折扣 ~4.5d wall-clock）

**Rollback**：env=0 即關（無 schema migration 影響、無業務變化）

### 7.2 Phase B：shadow dry-run（驗證 trigger 頻率合理性）

**範圍**：
- IntentProcessor 入口加 `advisor.would_reject_intent(&intent)` shadow check（only 在 status=Trigger 且 env=1）
- shadow counter 寫入 advisor state（`shadow_reject_count_24h: AtomicU64`）
- IPC status 加 shadow_reject_count_24h 欄位
- Healthcheck [22] WARN/FAIL 邏輯加「shadow_reject_count > N/h」項

**完成標準**：
- env=1 advisor enabled=true 運作 ≥7d
- shadow_reject_count vs 預期數量級（每天 0-5 次 trigger 為合理 baseline，>50 為過敏，需 calibrate threshold）
- Operator review shadow log + 確認 no false positive trigger pattern

**工時**：1d + E2 0.25d + E4 0.25d = **1.5d 全鏈**

**Rollback**：env=0 + advisor.enabled=false（IPC patch_risk_config 即生效）

### 7.3 Phase C：live triggered close（gate 新倉）

**範圍**：
- IntentProcessor 加 `cost_edge_pre_intent_check()` binding gate（only 在 advisor.enabled=true + status=Trigger）
- 新 RiskConfig field `cost_edge_gate_enabled: bool` (預設 false)
- per-strategy override 字段（`StrategyOverride.cost_edge_threshold_override: Option<f64>`，per §5.2）
- IPC `patch_risk_config` 路徑驗 cost_edge_gate_enabled flip 立即生效

**完成標準**：
- Operator 顯式 enable cost_edge_gate_enabled=true
- live demo 環境驗證 ≥7d 無 false-positive close（記錄 reject 與 close 數據）
- Per-strategy override 至少 1 strategy 測試 active 並驗 IPC patch hot-reload OK

**工時**：1.5d + E2 0.5d + E4 0.5d = **2.5d 全鏈**

**Rollback**：cost_edge_gate_enabled=false（IPC 立即生效，<60s）

### 7.4 Phase 工時總計

| Phase | E1 | E2 | E4 | 全鏈 wall-clock |
|---|---|---|---|---|
| A schema + advisor | 4.5d | 0.5d | 0.5d | **4.5d**（Rust+Py 並行折扣） |
| B shadow dry-run | 1d | 0.25d | 0.25d | **1.5d** |
| C live triggered gate | 1.5d | 0.5d | 0.5d | **2.5d** |
| **合計** | 7d | 1.25d | 1.25d | **8.5d wall-clock** |

並行/順序：A → 24h dogfood → B → ≥7d shadow accumulation → C。

---

## §8 Cross-Env Safety

### 8.1 三環境行為保證

| 環境 | Phase A 行為 | Phase B 行為 | Phase C 行為 |
|---|---|---|---|
| **paper** | advisor advisory only；H5 cost_tracker 在 paper 仍累積 ai_spend；ratio 計算用 paper_pnl/ai_spend；觸發只 log + audit | shadow reject count 累積；不影響 paper trade | gate 新 paper intent（與 paper engine 對齊：paper 通常 disabled OPENCLAW_ENABLE_PAPER=0；envoy 自然兜底） |
| **demo** | advisor advisory only；ratio 計算用 demo paper_pnl（per memory `feedback_demo_over_paper_for_edge`，demo 是 main edge source）；觸發只 log + audit | shadow reject count 累積；觀察 demo 流量響應 | gate 新 demo intent；不影響既有 demo 倉位 close 路徑 |
| **live (LiveDemo)** | advisor advisory only；ratio 計算用 live paper_pnl proxy（live 還沒真實 PnL，paper_pnl 為 LiveDemo 模擬）；觸發只 log + audit | shadow reject count 累積；不影響 live trade | gate 新 live intent；**Operator 必先審核 ≥7d demo Phase B shadow data** 才考慮在 live enable |

### 8.2 Cross-env config 隔離（per memory `feedback_env_config_independence`）

**3 env TOML 各自配 `[cost_edge]` section**：

```toml
# settings/risk_control_rules/risk_config_paper.toml
[cost_edge]
enabled = false                    # Phase A default
trigger_threshold = -0.5           # 保守起點

# settings/risk_control_rules/risk_config_demo.toml
[cost_edge]
enabled = false                    # Phase A default
trigger_threshold = -0.5           # demo 起點同 paper

# settings/risk_control_rules/risk_config_live.toml
[cost_edge]
enabled = false                    # Phase A default
trigger_threshold = -0.3           # live 更保守（ratio 容忍更小）
```

**禁止「衛生合併」**：cost_edge 在不同 env 的閾值/啟用狀態必須**獨立**演化，不可一行 TOML 改三 env。

### 8.3 Phase C live enable 前置 Operator 必查清單

```
□ Phase B demo 環境連續 ≥7d shadow_reject_count 在合理區間（每日 0-10 次）
□ Phase B 觀察期內無 cost_edge_advisor Anomaly 事件
□ Phase B 期間 healthcheck [22] 全 PASS / WARN，無 FAIL
□ Operator 自驗 cost_edge_threshold 與當期 demo ratio 分布合理（不在 30d 5th percentile 以下）
□ live 環境 trigger_threshold 設值 ≤ demo（保守：-0.3 vs demo -0.5）
□ live 環境 cost_edge_gate_enabled=false → 改 true 走 IPC patch_risk_config（不改 TOML 直接編輯）
□ live enable 後 ≤24h 內監控 [22] healthcheck 連續 PASS
```

### 8.4 16 根原則對照（CLAUDE.md §二）

| # | 原則 | 影響 | 措施 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | advisor 不寫 order；Phase C gate 經 IntentProcessor 唯一入口 |
| 2 | 讀寫分離 | ✅ | advisor 讀 H5 snapshot，不寫 H5 |
| 3 | AI 輸出 ≠ 命令 | ✅ | advisor 經 IPC + Operator approve（不繞 lease）|
| 4 | 策略不繞風控 | ✅ | Phase C gate 是 risk gate，與 cost_gate / SM-04 同層 |
| 5 | 生存 > 利潤 | ✅ | 觸發時不關現有倉，避免 false-positive 強制 close |
| 6 | 失敗默認收縮 | ✅ | env=0 default + None ratio fail-closed（不觸發 close）|
| 7 | 學習 ≠ 改寫 Live | ✅ | calibration 走 cron + manual approve（per §5.3）|
| 8 | 交易可解釋 | ✅ | audit emit 含 ratio/threshold/data_days，可重建 |
| 9 | 災難保護 | ✅ | advisor 不依賴 Python，crash 沿用 last good H5 snapshot |
| 10 | 認知誠實 | ⭐ | ratio 基於 paper_pnl 已標 (`roi_basis: paper_simulation_only`)；advisor 觸發 log 須含此 marker |
| 11 | Agent 最大自主權 | ✅ | advisor 是 metadata gate，不限 Agent 能力；只阻新倉不關既有倉 |
| 12 | 持續進化 | ✅ | calibration cron 屬學習平面，不改 Live 主路徑 |
| 13 | AI 成本感知 | ⭐⭐⭐ | **G3-09 直接落地原則 #13** |
| 14 | 零外部成本 | ✅ | advisor 不需新 LLM/API，純 read H5 snapshot |
| 15 | 多 Agent 協作 | 中性 | 不直接涉 Agent 通信；未來可 Phase D 與 5-Agent state 聯動 |
| 16 | 組合級風險 | ⭐ | cost_edge 是 portfolio-level metric，補強 #16（per-strategy override 對齊 #16）|

### 8.5 §四 5 項 live 硬邊界

| 邊界 | 觸碰 | 說明 |
|---|---|---|
| live_reserved | ❌ | advisor 純 observability + advisory gate |
| Operator 角色 auth | ❌ | advisor 不影響 auth |
| OPENCLAW_ALLOW_MAINNET | ❌ | 不影響 Mainnet gate |
| API key/secret slot | ❌ | 不影響 secret resolution |
| authorization.json HMAC | ❌ | 不影響 5min re-verify |

**全 5 項零觸碰** ✅

---

## §9 Backward Compat / Env-gate

### 9.1 Env-gate 策略

**主開關**：`OPENCLAW_COST_EDGE_ADVISOR=1`

- env=0（**預設**）：advisor 完全 dormant，daemon not spawned，IPC return uninitialized，所有 hot-path no-op
- env=1：advisor daemon spawned，evaluate H5 snapshot every 10s，read RiskConfig.cost_edge for behavior

**為何 env-gate（而非僅靠 RiskConfig.cost_edge.enabled）**：
- env-gate 是 binary on/off，不依賴 RiskConfig hot-reload 路徑（rollback 一鍵 unset）
- 與 G3-08 OPENCLAW_H_STATE_GATEWAY pattern 對齊（env-gate + RiskConfig flag 雙保險）
- env=0 zero overhead（poller 不 spawn / no IPC handler register / no audit emit）

### 9.2 RiskConfig flag 雙保險

```toml
[cost_edge]
enabled = false                    # default OFF, RiskConfig hot-reloadable via IPC
trigger_threshold = -0.5
cost_edge_gate_enabled = false     # Phase C gate, default OFF
```

| env | RiskConfig.cost_edge.enabled | 結果 |
|---|---|---|
| 0 | * | dormant（env-gate 主導，無 daemon spawn） |
| 1 | false | daemon spawned 但 advisor.enabled=false → evaluate 跳過 + IPC 回 disabled state |
| 1 | true | full operation |

**好處**：
- env=0 = ultimate kill switch（系統重啟需要才能 unset）
- RiskConfig.enabled=true/false = runtime toggle（IPC patch_risk_config 即生效）
- 兩層提供獨立 rollback paths

### 9.3 Phase 切換的舊行為兼容

| Phase 切 | 風險 | 兼容措施 |
|---|---|---|
| Phase A → B | 加入 shadow check 可能影響 IntentProcessor 性能 | `would_reject_intent` 是 pure fn O(1)，benchmark < 100ns |
| Phase B → C | shadow 變 binding gate，可能 reject 真新倉 | RiskConfig.cost_edge_gate_enabled=true 才 binding，預設 false 保留 shadow only |
| Phase C → 退回 B | gate 突然移除，新倉湧入 | IPC patch_risk_config cost_edge_gate_enabled=false 立即生效，advisor 退回 shadow |
| 全部退回 A | 完全 revert advisory only | env=0 unset 一鍵 |

---

## §10 Risk 識別 + Mitigation

### 10.1 Risk 矩陣

| # | 風險 | 機率 | 影響 | 緩解 |
|---|---|---|---|---|
| **R1** | False-positive trigger 阻新倉，影響真實機會 | 中（Phase C） | 中（錯過機會非虧損）| (a) 預設 -0.5 保守起點 (b) Phase B ≥7d shadow 觀察 (c) per-strategy override (d) IPC <60s rollback |
| **R2** | data_days < 3 期間（warm-up）advisor 不能起作用 | 高（每次部署/restart）| 低（fail-closed 不觸發）| 設計上 None ratio = WarmUp status，advisor 不 trigger，與既有 risk 機制 fallback OK |
| **R3** | H5 cost_tracker race（多 worker uvicorn）導致 ratio 跳變 | 中 | 低（observability 字段）| Phase 1 已 accept；Phase D 評估 leader-only flock |
| **R4** | per-strategy threshold drift（operator 配 -10 等不合理值）| 低 | 中（advisor 失效或過敏）| RiskConfig.cost_edge validation: trigger_threshold ∈ [-100, 100] + per_strategy_override ∈ [-100, 100] |
| **R5** | cost_tracker race（IPC pull H5 時 Python 正寫）| 中 | 低（一次 stale 不影響趨勢）| H5 snapshot 通過 H state cache，已有 lock pattern；ratio 計算為 instantaneous 非 cumulative，stale 1 cycle 影響 < 1%|
| **R6** | Phase C gate 與 cost_gate（per-intent）邏輯衝突 | 低 | 中（intent 雙 gate fail）| cost_edge_advisor 是 portfolio-level，cost_gate 是 per-intent；兩 gate 並存 = AND 條件（更保守，符合 #6）；audit 區分兩 reject 來源 |
| **R7** | Anomaly status（NaN/Inf）長期 stuck，advisor 永不恢復 | 低 | 中（advisor 失效）| healthcheck [22] FAIL on Anomaly → operator 介入；evaluate cycle 每 10s 重試，正常數值會自然恢復 |
| **R8** | calibration cron 自動寫 RiskConfig（違反 #7）| **N/A** | 高 | **本 RFC §5.3 明文嚴禁自動 binding**，calibration cron 只 propose，operator manual approve |
| **R9** | Phase C 啟動後 ratio 卡在 trigger，新倉永遠開不了 | 低 | 高（系統凍結）| (a) Operator IPC patch_risk_config cost_edge_gate_enabled=false 60s 內 rollback (b) trigger threshold 校準避免長期 trigger (c) healthcheck [22] FAIL @ 1h 連續 trigger 自動告警 |
| **R10** | advisor daemon spawn 失敗 silent | 中 | 中（advisor 失效）| main_boot_tasks env=1 spawn fail = log error + advisor slot stays None；IPC `get_cost_edge_advisor_status` 回 `{status: "Uninitialized"}` 暴露失敗 |

### 10.2 Top 3 高優先風險的 mitigation 細節

#### R1 False-positive trigger 阻新倉

**機制**：data_days=3 prevent warm-up trigger，但若初期幾天 paper PnL 偶然 -50%（市場震盪），advisor 立刻 trigger，gate 阻新倉。

**緩解**：
- Phase A advisory only，**收 ≥30d** 經驗 ratio distribution 後才 calibrate threshold
- Phase B shadow 期間 operator 觀察「合理」trigger 頻率（每天 0-5 次為健康）
- per-strategy override 允許高燒錢策略（ma_crossover）容忍更負 ratio

#### R6 cost_edge_advisor 與 cost_gate 邏輯衝突

**機制**：
- cost_gate (per-intent slippage)：reject intent if intent.expected_edge_bps < cost
- cost_edge_advisor (portfolio-level)：reject intent if portfolio cost_edge_ratio ≤ threshold

兩 gate 邏輯獨立但都可能 reject 同一 intent。

**緩解**：
- 兩 gate 並存設計上是 **AND 條件**（任一 reject = 整體 reject），符合 #6 fail-closed
- audit reject reason 必含 source field：`cost_gate` vs `cost_edge_advisor`，operator 可分辨
- IntentProcessor reject log 加 explicit gate name 區分

#### R9 Phase C 啟動後系統凍結

**機制**：若 trigger_threshold 校準錯（如 -100 寬鬆）+ ratio 持續 -1.0 → status 永遠 OK；反之 threshold 0.0 + ratio -0.1 → status 永遠 Trigger，新倉永開不了。

**緩解**：
- IPC patch_risk_config 寫 cost_edge_gate_enabled=false 60s 內 rollback
- healthcheck [22] FAIL @ 1h 連續 trigger（per §6.2）→ operator 介入
- 啟動 Phase C 前 Operator checklist §8.3 第 3 條「Phase B ≥7d 連續 PASS」確保啟動安全

---

## §11 E1 Prompt Template — Phase A 落地

下次 session PM 直接 paste 給 E1（self-contained，無需 PM 補上下文）。

````markdown
## 任務：G3-09 Phase A — cost_edge_advisor schema + advisory only

### 背景

CLAUDE.md §二 原則 #13「AI 資源成本感知 — 每次 AI 調用計費，cost_edge_ratio ≥ 0.8 → 建議
關倉」需 Rust 端 hot-path 落地。G3-08 Phase 3 H5 cost_logging 已 land（commit `d1a2252`），
Rust h_state_cache.snapshot().h5.cost_edge_ratio 可達。本 sub-task = Phase A schema 落地 +
advisor advisory only（純 log/audit，0 trade impact）。

### 前置驗證（開工前必跑）

```bash
# G3-08 Phase 3 H5 已 land
git log --oneline -10 | grep -iE "G3-08 Phase 3 Sub-task 3-3" || echo "❌ Phase 3 not landed"

# H5CostStats schema 確認
ssh trade-core "cd ~/BybitOpenClaw/srv/rust && grep -A 12 'pub struct H5CostStats' \
  rust/openclaw_engine/src/h_state_cache/types.rs"

# H State Gateway healthcheck [20] 仍綠
ssh trade-core "cd ~/BybitOpenClaw/srv && python3 helper_scripts/db/passive_wait_healthcheck.py \
  2>&1 | grep -i '\[20\]'"
```

### 改動文件（新建 5 + 修改 6）

#### 新建（Rust）

1. `rust/openclaw_engine/src/cost_edge_advisor/mod.rs` (~200 LOC)
   - struct CostEdgeAdvisor + spawn_cost_edge_advisor + status enum
2. `rust/openclaw_engine/src/cost_edge_advisor/types.rs` (~80 LOC)
   - CostEdgeAdvisorStatus enum: Uninitialized / Disabled / WarmUp / OK / Trigger / Stale / Anomaly
   - CostEdgeAdvisorState struct
3. `rust/openclaw_engine/src/cost_edge_advisor/advisor.rs` (~150 LOC)
   - evaluate(snapshot: HStateSnapshot, cfg: &CostEdgeConfig) -> CostEdgeAdvisorState
4. `rust/openclaw_engine/src/cost_edge_advisor/tests.rs` (~250 LOC)
   - 24+ unit tests: 6 status × edge cases (None ratio / NaN / Inf / threshold boundary / staleness)
5. `rust/openclaw_engine/src/ipc_server/handlers/cost_edge_advisor.rs` (~100 LOC)
   - get_cost_edge_advisor_status handler

#### 修改（Rust）

6. `rust/openclaw_engine/src/lib.rs` — 加 `pub mod cost_edge_advisor;`
7. `rust/openclaw_engine/src/config/risk_config.rs` — 加 `pub cost_edge: CostEdgeConfig` field
   + `pub struct CostEdgeConfig { enabled: bool, trigger_threshold: f64 }`
8. `rust/openclaw_engine/src/ipc_server/slots.rs` — 加 `CostEdgeAdvisorSlot` type alias
9. `rust/openclaw_engine/src/ipc_server/dispatch.rs` — 加 1 method arm (`get_cost_edge_advisor_status`)
10. `rust/openclaw_engine/src/main_boot_tasks.rs` — env-gate spawn cost_edge_advisor daemon
11. `rust/openclaw_engine/src/audit/types.rs` (or 既有 audit module) — 加 2 audit event types
    (CostEdgeAdvisorTrigger / StatusChange)

#### 修改（TOML）

12. 三個 TOML `settings/risk_control_rules/risk_config_{paper,demo,live}.toml` 加 `[cost_edge]`
    section（per §8.2）

#### 修改（Python）

13. `helper_scripts/db/passive_wait_healthcheck.py` 加 check_cost_edge_advisor_status (per §6.2)

### 具體實作要點

#### CostEdgeAdvisorStatus enum

```rust
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum CostEdgeAdvisorStatus {
    Uninitialized,    // env=0 or daemon spawn failed
    Disabled,         // env=1 but RiskConfig.cost_edge.enabled=false
    WarmUp,           // ratio=None (data_days < 3)
    OK,               // ratio Some(_) > threshold
    Trigger,          // ratio Some(_) <= threshold
    Stale,            // h_state_cache.is_stale() = true
    Anomaly,          // ratio Some(NaN) or Some(Inf)
}
```

#### evaluate() pure fn

```rust
pub fn evaluate(
    snapshot: HStateSnapshot,
    cfg: &CostEdgeConfig,
    is_stale: bool,
) -> CostEdgeAdvisorState {
    if !cfg.enabled {
        return CostEdgeAdvisorState::disabled();
    }
    if is_stale {
        return CostEdgeAdvisorState::stale(snapshot.h5.cost_edge_ratio);
    }
    let ratio_opt = snapshot.h5.cost_edge_ratio;
    let data_days = snapshot.h5.data_days;
    let threshold = cfg.trigger_threshold;
    match ratio_opt {
        None => CostEdgeAdvisorState::warm_up(data_days),
        Some(r) if !r.is_finite() => CostEdgeAdvisorState::anomaly(r),
        Some(r) if r <= threshold => {
            CostEdgeAdvisorState::trigger(r, threshold, data_days, snapshot.h5.ai_spend_7d_usd, snapshot.h5.paper_pnl_7d_usd)
        }
        Some(r) => CostEdgeAdvisorState::ok(r),
    }
}
```

#### Daemon (poll + emit audit on transition)

```rust
pub fn spawn_cost_edge_advisor(
    h_state_cache: Arc<HStateCache>,
    risk_config: Arc<ArcSwap<RiskConfig>>,
    audit_tx: AuditChannel,
    poll_interval: Duration,
    cancel: CancellationToken,
) -> JoinHandle<()> {
    tokio::spawn(async move {
        let mut prev_state = CostEdgeAdvisorState::uninitialized();
        loop {
            tokio::select! {
                _ = cancel.cancelled() => break,
                _ = tokio::time::sleep(poll_interval) => {
                    let cfg = &risk_config.load().cost_edge;
                    let snapshot = h_state_cache.snapshot();
                    let is_stale = h_state_cache.is_stale();
                    let new_state = evaluate(snapshot, cfg, is_stale);
                    if new_state.status != prev_state.status {
                        // emit StatusChange audit
                        audit_tx.emit(AuditEvent::CostEdgeAdvisorStatusChange {
                            prev_status: prev_state.status.to_string(),
                            new_status: new_state.status.to_string(),
                            at_ms: now_ms(),
                        });
                        // emit Trigger audit (only when entering Trigger state)
                        if matches!(new_state.status, CostEdgeAdvisorStatus::Trigger) {
                            audit_tx.emit(AuditEvent::CostEdgeAdvisorTrigger {
                                ratio: new_state.ratio.unwrap_or(0.0),
                                threshold: cfg.trigger_threshold,
                                data_days: snapshot.h5.data_days,
                                ai_spend_7d_usd: snapshot.h5.ai_spend_7d_usd,
                                paper_pnl_7d_usd: snapshot.h5.paper_pnl_7d_usd,
                                phase: "A_advisory".to_string(),
                                triggered_at_ms: now_ms(),
                            });
                            log::warn!(
                                "cost_edge_advisor: TRIGGER ratio={:.3} <= threshold={:.3} (Phase A advisory only)",
                                new_state.ratio.unwrap_or(0.0), cfg.trigger_threshold,
                            );
                        }
                    }
                    prev_state = new_state;
                }
            }
        }
    })
}
```

### 完成標準

- ✅ `cargo test --release -p openclaw_engine --lib cost_edge_advisor` 全綠（24+ tests）
- ✅ env=1 + advisor daemon spawn + 每 10s evaluate H5 snapshot
- ✅ env=0 zero overhead（grep main_boot_tasks 驗 not spawned；IPC return Uninitialized）
- ✅ `pytest test_passive_wait_healthcheck.py -v` 加 [22] check 全綠
- ✅ healthcheck [22] cron 6h 跑連續 24h 全 PASS（env=0 PASS skip）
- ✅ 三個 TOML 添加 `[cost_edge]` section + cargo test deserialize 綠
- ✅ Cross-env 三 toml hot-reload 不破（IPC patch_risk_config cost_edge.enabled flip OK）
- ✅ Audit emit on Trigger transition + StatusChange transition 兩 event types

### 不要做（留 Phase B/C）

- ❌ 不接 IntentProcessor.cost_edge_pre_intent_check（Phase C 範圍）
- ❌ 不寫 shadow_reject_count（Phase B 範圍）
- ❌ 不寫 per_strategy.cost_edge_threshold_override（Phase C 範圍）
- ❌ 不寫 calibration cron（未來 Phase D）
- ❌ 不改 cost_gate 任何邏輯（兩者獨立）

### 副作用警示

- main_boot_tasks.rs 改動 = startup sequence 變化，cargo integration tests 必跑
- ipc_server/dispatch.rs 加 1 method arm（當前 ~600 行，加 +5 行 → 仍安全 < 1200 hard cap）
- audit/types.rs 加 2 events 屬 schema 演化，downstream consumer（如 audit log writer）serde forward-compat
- RiskConfig 加 cost_edge field 屬 Phase A schema 落地，預設 enabled=false 保留 bit-identical 行為

### Commit message

```
feat(rust): G3-09 Phase A — cost_edge_advisor schema + advisory only

- new module cost_edge_advisor (~480 LOC + 250 tests)
  - CostEdgeAdvisorStatus enum (7 variants: Uninitialized/Disabled/WarmUp/OK/Trigger/Stale/Anomaly)
  - evaluate() pure fn reads HStateSnapshot.h5.cost_edge_ratio + threshold compare
  - spawn_cost_edge_advisor daemon polls every 10s + emits audit on status transition
- new IPC handler get_cost_edge_advisor_status
- new audit event types CostEdgeAdvisorTrigger + StatusChange
- new RiskConfig.cost_edge sub-struct (enabled bool, trigger_threshold f64)
  defaults: enabled=false (Phase A dormant) / threshold=-0.5 (conservative)
- new healthcheck [22] check_cost_edge_advisor_status (PASS skip env=0)
- env-gate OPENCLAW_COST_EDGE_ADVISOR + RiskConfig.cost_edge.enabled dual safeguard
- 3 env TOML add [cost_edge] section (paper/demo/live)
  live threshold -0.3 more conservative than demo/paper -0.5

Phase A advisory only — 0 trade impact / no IntentProcessor wiring / no close trigger.
Phase B (shadow dry-run) + Phase C (gate新倉) deferred to follow-up sub-tasks.
Per PA RFC docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g3_09_cost_edge_ratio_design.md
- Recommend hot-path integration: cost_edge_advisor (NEW module, single-responsibility)
  vs intent_processor (cost_gate overlap) / combine_layer (Gate 4-only Lock contract)
  / phys_lock_v2 (per-position semantic mismatch).
- CLAUDE.md §二 #13 字面義方向矛盾 → §2.4 採解釋 A 變體（threshold 為負值）

Verified: cargo test pass; env=1 daemon spawn + 10s poll OK; env=0 zero overhead;
healthcheck [22] cron 6h PASS; cross-env hot-reload OK.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

### Estimated time

- E1-Alpha (Rust advisor module + daemon + IPC) 3d
- E1-Beta (audit events + healthcheck + TOML) 1.5d
- 並行折扣 wall-clock ~3d
- E2 0.5d + E4 0.5d = **4.5d 全鏈**

### 一行回報

```
G3-09 PHASE A DONE — cost_edge_advisor commit <hash> pushed; healthcheck [22] PASS; advisory only
```
````

---

## §12 Phase 4 5-Agent Dependency

### 12.1 G3-09 是否解阻 Phase 4

**強依賴**：無。Phase 4（5-Agent state events）獨立於 G3-09，兩者**並行**可派。

**弱依賴**：
- Phase 4 land 後可寫 G3-09 Phase D 補充演算法 — `cost_edge_advisor.evaluate()` 加入 5-Agent state weight（如 `Strategist.intel_evaluated >> intents_produced` 比率異常 = AI 工作量 vs 產出失衡，補充 ratio 信號）
- 兩者**互不阻塞**，可任意順序

### 12.2 G3-09 是否被 Phase 4 阻塞

**否**。G3-09 Phase A/B/C 只依賴 H5 cost_edge_ratio（Phase 3 已 land），不需 5-Agent state。

### 12.3 Phase 4 解阻條件

**Phase 4 解阻不依賴 G3-09**。Phase 4 自身依賴：
- G3-08 Phase 3 H5 ✅（已 land）
- strategist_agent.py 拆檔（per `2026-04-26--g3_08_phase3_subtask_split.md` §10.4 `strategist_agent.py 1170+~25=~1195 行接近 §九 1200 硬上限，Phase 4 Strategist sub-task 必先拆檔`）

### 12.4 整體依賴圖

```
G3-08 Phase 3 H5 ✅ (commit d1a2252, sign-off e5f1b2d)
       │
       ├──→ G3-09 Phase A advisory ★ this RFC
       │       │
       │       └──→ G3-09 Phase B shadow ──→ G3-09 Phase C gate (operator approve)
       │                                           │
       │                                           └──→ G3-09 Phase D 5-Agent weight (uses Phase 4 5-Agent state)
       │
       └──→ G3-08 Phase 4 5-Agent state events (依賴 strategist_agent.py 拆檔，獨立於 G3-09)
                              │
                              └──→ G8-01 認知自適應 e2e (依賴 Phase 4)
```

### 12.5 派發順序建議

**第一波**（next session 立刻可派，並行）：
- G3-09 Phase A 派發（per §11 prompt template）
- G3-08 Phase 4 5-Agent state events 派發（**先**派 strategist_agent.py 拆檔 sub-task / **後**派 5-Agent integration sub-task）

**第二波**（G3-09 Phase A land + 24h dogfood 後）：
- G3-09 Phase B shadow dry-run 派發

**第三波**（G3-09 Phase B ≥7d shadow 觀察 + Operator approve 後）：
- G3-09 Phase C gate 派發

---

## §13 沒做的事（E1/E2 領域）

- 沒寫 cost_edge_advisor 任何實作代碼（純 design + prompt template）
- 沒派 sub-agent（純 PA 主 agent 串行讀 + 寫）
- 沒跑 cargo test / pytest（E1/E4 任務）
- 沒擴範圍到 Phase B shadow / Phase C gate 實作（屬 Phase B/C 後續 sub-task）
- 沒擴範圍到 Phase D 5-Agent weight calibration（屬 G3-09 Phase D 未來 RFC）
- 沒寫 cost_edge_threshold_calibrator.py 工具（屬 Phase D / 未來 helper script）
- 沒動 production code（cost_tracker / intent_processor / etc.）

---

## §14 教訓備忘（給未來 PA / PM）

1. **CLAUDE.md 字面義 vs 實際公式可能矛盾** — #13 「ratio ≥ 0.8 → 關倉」與 `get_cost_edge_ratio` 公式（ratio 越大越好）方向衝突。RFC 應顯式 surface 此矛盾並提解釋（§2.4），而非默認字面義 = 實際語意。

2. **「建議關倉」≠「強制關倉」** — advisor pattern 是「建議」最自然的落地，**而非**強制 close。close 是 hard 動作（false-positive 直接虧損），advisor 是 soft（advisory log/gate 阻新倉），不混淆。

3. **Single-responsibility 優於「黏在既有 hot-path」** — 候選 1/2/3 都嘗試在既有 hot-path 加 cost_edge logic，但都違反某個既有 contract（cost_gate 重疊 / Gate 4-only Lock / per-position vs portfolio）。新模組 (候選 4) 雖加 LOC，但 single-responsibility 滿足 + Phased rollout 易做。

4. **Phase A advisory only 是 cross-env 安全的關鍵** — Phase A 純 log/audit/healthcheck，0 trade impact，paper/demo/live 三 env 行為完全一致，可 24h dogfood 無風險。Phase B shadow + Phase C gate 都是漸進放權，符合 #6 失敗默認收縮。

5. **env-gate + RiskConfig.enabled 雙保險** — 對齊 G3-08 OPENCLAW_H_STATE_GATEWAY pattern。env-gate = ultimate kill switch（unset 一鍵），RiskConfig.enabled = runtime toggle（IPC patch 即生效）。雙層提供獨立 rollback paths，rollback drill 容易。

6. **per-strategy override 對齊 G2-03 既有 staging 不增新層** — `RiskConfig.per_strategy.StrategyOverride` 已是 per-strategy 風控的唯一 staging，G3-09 加 `cost_edge_threshold_override` 自然延展，不增新 schema 層。

7. **calibration 永不自動 binding** — 對齊 EDGE-P1b RFC §3 + memory `feedback_env_config_independence`。cost_edge_threshold 自動 calibrate + 自動 IPC 寫風控值 = 高風險（與 §7「學習 ≠ 改寫 Live」衝突）。任何 calibration 必 cron + manual approve。

8. **healthcheck slot allocation 衝突要先 grep** — 本 RFC §6.2 [22] slot 號需 cross-check 既有 [19]/[20]/[21] 占用情況（[19] paper_state observer / [20] h_state_gateway / [21] paper_state_dust_inventory amend slot）。任何新 healthcheck 必先 grep `passive_wait_healthcheck.py` 確認 slot free。

---

## §15 報告索引追加

| 日期 | 報告類型 | 文件位置 |
|---|---|---|
| 2026-04-26 | G3-09 cost_edge_ratio Hot-Path Integration RFC（推 候選 4 cost_edge_advisor 模組 / 3 phase rollout / Phase A E1 prompt template ready） | workspace/reports/2026-04-26--g3_09_cost_edge_ratio_design.md |

---

**全文完。next: PM next session 啟動 G3-09 Phase A 派發（per §11 prompt template，self-contained）+ 並行可派 G3-08 Phase 4 5-Agent state events（先 strategist_agent.py 拆檔 sub-task）。Phase A land + 24h dogfood 後評估 Phase B shadow 派發。Phase B ≥7d 觀察 + Operator approve 後評估 Phase C live triggered gate。**
