# E5 對抗性核實 v3 — 5 commits 結構/性能影響 + PA architectural redesign cross-check

**baseline**：`faf2d131`
**HEAD**：`da2aba11`
**核實時間**：2026-05-09 v3
**核實口徑**：對抗性嚴苛 — commit message 不算數，必驗 LOC/binary/PG/真實 caller；PA architectural claim 必逐條 grep 證據對照
**Engine runtime**：Linux trade-core PID 298034 etime 02:58:24，binary 20.6 MB stripped (5/9 14:02 build)
**5 commits 中 source-only**：5 全部 (engine 不跑任何 5 commit 改動，全部待 --rebuild)

> **總體判定（任務 A 5 commits）**：✅ **STRUCTURAL CLEAN**（0 hard cap violation 引入，1 純結構性 +505 LOC 在 helper_script，hot path 性能淨影響 ≤ 0.5μs）
> **總體判定（任務 B PA redesign）**：⚠️ **PARTIAL AGREE** — 結構診斷正確 (5 root cause 中 4 證據成立)，但 LOC 估計樂觀 (R-1 真實是 8-12 sprint 不是 3-4)，且部分主張過度 (e.g. strategist_agent.py 不是 45000 LOC，是 799)。

---

## §1 任務 A — 5 commits 結構 / 性能對抗核實

### 1.1 LOC delta 全量

| File | before | after | delta | warn (>800) | hard (>2000) |
|---|---:|---:|---:|---|---|
| `helper_scripts/cron/ml_training_maintenance.py` | 430 | **935** | **+505 (+118%)** | 🟡 NEW warn | ✅ no |
| `program_code/exchange_connectors/.../app/edge_estimator_scheduler.py` | 855 | **977** | +122 | 🟡 已 warn (pre-existing) | ✅ no |
| `program_code/exchange_connectors/.../app/promotion_pipeline.py` | 827 | **847** | +20 | 🟡 已 warn (pre-existing) | ✅ no |
| `program_code/exchange_connectors/.../app/ai_service_dispatch.py` | 727 | 767 | +40 | ✅ <800 | ✅ no |
| `program_code/ml_training/promotion_evidence.py` | NEW | **558** | +558 | ✅ <800 | ✅ no |
| `program_code/exchange_connectors/.../app/governance_promotion_routes.py` | NEW | 327 | +327 | ✅ | ✅ |
| `helper_scripts/db/audit/blocked_symbols_7d_counterfactual.py` | NEW | 247 | +247 | ✅ | ✅ |
| `rust/openclaw_engine/src/strategist_scheduler/evaluate.rs` | 400 | **481** | +81 | ✅ <800 | ✅ |
| `rust/openclaw_core/src/indicators/mod.rs` | 335 | 361 | +26 | ✅ | ✅ |
| `rust/openclaw_engine/src/strategies/bb_breakout/tests.rs` | 1105 | **1186** | +81 | 🟡 已 warn (pre-existing) | ✅ no |
| `sql/migrations/V079__promotion_evidence_trial_ledger.sql` | NEW | 67 | NEW | n/a | n/a |
| **Net Insertions** | | | **+2933 LOC across 37 files** | | |

**重要 NEW WARN**：`helper_scripts/cron/ml_training_maintenance.py` **430 → 935 (+505)** — da2aba11 commit 引入 5 個新 ML scope job (thompson_sampling/optuna_optimizer/cpcv_validator/dl3_foundation/weekly_report_generator) — 從 5 個跳到 10 個 ML jobs。

**對抗評估 ml_training_maintenance.py**：
- **不是 production code**（在 `helper_scripts/cron/`），是 cron orchestrator
- **§九 「800 行警告線」適用範圍**：CLAUDE.md §九 沒明文豁免 helper_scripts，但 spirit 對 cron orchestrator 適用
- **內聚性 vs 拆檔**：當前是 thin orchestrator，10 個 ML scope 共用相同 status JSON / lockfile / status snapshot 邏輯。拆檔會破封裝
- **建議**：標 P2 監控（不阻 merge），下次 +200 LOC 觸 1100 才強制拆

### 1.2 5 commits 性能影響

#### `ad14db07` Donchian guard

**Hot path？** ✅ — `IndicatorEngine::compute_all_with_lambda` 在 `tick_pipeline/on_tick_helpers.rs:557` 每 tick 跑

**改動本質**：`indicators/mod.rs:150` `donchian(...)` → `donchian_prior(...)`
- `donchian_prior` 內部 = `donchian(&high[..n-1], &low[..n-1], &close[..n-1], period)`
- O(period=20) max/min 改 O(period=20) 在 slice[..n-1]
- **+3 slice borrows (O(1) zero-cost)**
- **-1 element from inner loop** (n vs n-1)
- 淨效能：**~0 nanoseconds**（slice borrow 是 fat pointer copy，max/min loop 縮 1 元素）

**真實業務語意修復**：bb_breakout `is_long && ctx.price < dc.upper → return []`。如 dc 含 current bar，price ≤ max(包含 current) 永真，**Hard mode 永不通過 = 系統性 leak-bias 反業務 bug**。指標改前 = current bar 是自己 max 的一部分 → strategy 永等不到「真突破」。

**SLA 驗證**：
- H0 Gate <1ms — ✅ 0 影響
- Tick path <0.3ms — ✅ 0 影響
- 31 lib test 全綠（bb_breakout/tests.rs +81 LOC = `test_w_audit_6_bb_breakout_5m_hard_gate_uses_prior_donchian` 等）

**結論**：✅ 性能淨 0，**修真實 logical leak-bias 是 high-leverage fix**

#### `c2ab7b1a` strategist wide adjustment

**Hot path？** ❌ — `strategist_scheduler/evaluate.rs` 是 5 分鐘 cycle (NORMAL_INTERVAL=300s)，非 tick path

**Rust diff**：純結構性抽 fn `build_strategist_eval_payload`，加 1 個 const + 1 個 test
- 0 hot path impact
- 唯一語意改動：max_delta_pct 從 30% 拓寬為 50%（已記在 ai_service_dispatch.py:37 `_STRATEGIST_DEFAULT_MAX_DELTA_PCT = 0.50`）

**Python diff `ai_service_dispatch.py` +86 LOC**：教 LLM 用 `wide_skill_range`（30%-50%）vs `normal range`（0-30%），降低 LLM 算錯範圍機率

**結論**：✅ 0 hot path 性能影響；business logic 升級 reasoning quality

#### `48227607` learning push promotion evidence

**Hot path？** ❌ — `edge_estimator_scheduler.py:600 _run_promotion_evidence_push` 每 estimator cycle 跑 (cycle interval 由 scheduler 決定，非 per-tick)

**新模組**：
- `promotion_evidence.py` 558 LOC — **真實 production caller**：`edge_estimator_scheduler.py:621 lazy import`（不在頂層 import 是好做法，避免 circular + cold path 不收 startup cost）
- `governance_promotion_routes.py` 327 LOC — 6-01~03 promotion endpoints
- V079 SQL migration 67 LOC — `learning.promotion_evidence_trial_ledger`（待 PG empirical 驗 schema 真實 INSERT 行為）

**對抗評估 lazy import**：
```python
# edge_estimator_scheduler.py:621
try:
    from ml_training.promotion_evidence import (  # noqa: PLC0415
        push_promotion_evidence_from_js_results,
    )
```
- 用 `# noqa: PLC0415`（pylint disable for lazy import）= acceptable trade-off
- import 時間 + cycle 觸發頻率（>5min）= cold cost 攤平 ≈ 0
- **真實接線**確認

**結論**：✅ 結構乾淨；新模組 558 LOC + 327 LOC 全 <800 warn；非 hot path

#### `c081029d` blocked symbols freeze

**Hot path？** ❌ — `helper_scripts/db/audit/blocked_symbols_7d_counterfactual.py` 是 audit script，按需執行

**新模組**：247 LOC audit script + 66 LOC test + 83 LOC test_strategy_blocked_symbols_freeze.py + 31 LOC settings/strategy_blocked_symbols_freeze.json

**結論**：✅ 純治理工件；governance freeze artifact，非 production code path

#### `da2aba11` audit f08 ml cron scope correction

**Hot path？** ❌ — cron orchestrator

**改動本質**：擴增 5 個 ML jobs（CORE_JOBS 5 個 + EXTENDED_JOBS 5 個 = 10 個），加 dispatch logic + status JSON 結構化

**LOC 警告**：935 LOC 觸 §九 800 warn（NEW warn）；helper_script 範疇可接受

**結論**：✅ 非 hot path，但 NEW 800 warn 已標

### 1.3 任何 commit 引入 dead schema / dead code？

| Commit | dead 檢查 | 結果 |
|---|---|---|
| `ad14db07` | indicators/mod.rs `donchian_prior` reuse `trend.rs::donchian_prior` | ✅ 0 dead，純 wiring 改 |
| `c2ab7b1a` | strategist_scheduler 抽 fn + Python new const | ✅ 0 dead，1 test 覆蓋 |
| `48227607` | promotion_evidence.py 558 LOC, V079 schema | ⚠️ V079 schema 待 PG 驗證真 INSERT |
| `c081029d` | blocked_symbols_7d_counterfactual.py | ⚠️ 247 LOC audit script，需 cron 觸發才會 active；非 dead 但 dormant |
| `da2aba11` | ml_training_maintenance.py +505 LOC | ⚠️ 5 新 EXTENDED_JOBS 是 spec 添加，需後續 cron --include-extended 才會跑 |

**Dead 風險 NEW**：3 個（V079 schema / blocked_symbols audit / 5 EXTENDED_JOBS），全為 governance artifact，需後續 cron 接線生效。**沒有 silent dead code**，但需 follow-up activation。

### 1.4 5 commits source-only 風險

**Critical 治理紅旗**：5 commits **全部 source-only**，engine 5/9 14:02 build (etime 02:58:24)，源碼改動 vs runtime 之間 drift：
- `ad14db07` Donchian guard 改 indicators/mod.rs:150 production code → engine 仍跑 leak-bias 版本
- `c2ab7b1a` strategist_scheduler/evaluate.rs Rust 改 81 LOC → engine 仍跑舊 payload schema
- 其他 3 commits 是 Python，不需 engine rebuild

**對抗 push back**：v2 lesson #4「source-only commits 累積風險」連續 v2→v3 仍存在。建議 deploy gate ticket 或 next operator restart_all --rebuild 觸發前必先 audit 累積 source-only Rust 改動清單。

---

## §2 任務 B — PA redesign architectural cross-check

### 2.1 PA 5 root cause 證據對照

#### Root cause 1：Strategy interface alpha-poverty

**PA 主張**：「Strategy interface 結構性激勵 1m kline + classic indicator 路徑」+「TA 高速公路 vs 其他泥路」

**E5 實證 grep**：

`rust/openclaw_engine/src/tick_pipeline/mod.rs:665-708` — TickContext 真實字段（12 個）：
- `symbol`, `price`, `timestamp_ms`
- `indicators` (1m), `indicators_5m`, `signals`, `h0_allowed`
- `funding_rate` ✅ (EDGE-P1-2)
- `index_price` ✅ (OC-5)
- `open_interest` ✅ (EDGE-P2-2，註明「Raw value — consumer strategies buffer + compute delta on their own window」)
- `best_bid`, `best_ask` ✅ (G7-09c Phase 1)
- `tick_size` ✅ (G7-09c)

**5 production strategies 真實使用**（grep 證據）：
- `funding_arb.rs:380` 用 `funding_rate + index_price`（已 RETIRE per ADR-0018）
- `grid_trading/signal.rs:66` 用 `best_bid/best_ask` for PostOnly maker
- 其餘 3 (bb_breakout/bb_reversion/ma_crossover) 全部以 `IndicatorSnapshot` 為核心輸入

**E5 verdict**：
- ✅ PA 字段觀察**正確**
- ✅ 5 策略 OHLCV-driven 偏向**正確**
- ⚠️ PA 的「TA 高速公路」隱喻**部分過度**：funding_rate / index_price / best_bid/ask / open_interest **已是 first-class TickContext field**，不是 strategy 自己 buffer。EDGE-P2-2:686-688 註明 OI 需 strategy own buffer 是真的，但 funding_rate / best_bid 不需要
- **真實摩擦**：cross-section snapshot（25 symbols funding curve / OI delta panel / large-trade tape）確實是 strategy 自己 buffer。這是 PA 的 R-1 leverage point 真實存在
- **PA 升級 AlphaSurface 設計合理**，但 PA 沒區分「已是 first-class field（funding_rate, best_bid/ask, open_interest, index_price）」vs「真需新增（cross-symbol panel, microprice, liquidation_pulse, sentiment_panel）」

**verdict**：⚠️ **PARTIAL AGREE**（觀察 7/10 正確，但 over-stated「結構性激勵」，缺 nuance）

#### Root cause 2：Strategist scope = 調參器

**PA 主張**：strategist_agent.py 45000 LOC + `_REGIME_STRATEGY_PREFERENCES` 4×5 hardcoded

**E5 實證**：
- `strategist_agent.py` Mac local + Linux runtime 都是 **799 LOC**，不是 45000 LOC（PA 引 CLAUDE.md §三 是錯讀；CLAUDE.md §三 沒寫 45000）
- `_REGIME_STRATEGY_PREFERENCES` 在 strategist_agent.py:128-134 ✅ 確實 hardcoded 4×5
- 5 agent 總和：scout 349 + strategist 799 + analyst 802 + executor 900 + guardian 1458 = **4308 LOC**

**verdict**：✅ **核心觀察正確**（hardcoded regime preferences）但 **LOC 數字錯**（799 不是 45000，差 56 倍）。PA 推論「scope 縮在調參器」**邏輯成立**

#### Root cause 3：Analyst L2-L5 dormant

**PA 主張**：alpha discovery loop spec 在 EX-06 但 IMPL 0%

**E5 實證**：
- EX-06 spec：`docs/decisions/EX-06_OpenClaw_Bybit_Multi-Agent_Orchestration_*_V1.md:159` 確實寫「策略匹配：根据 regime 和币种特征选择最优策略（MA Crossover / Grid / Funding Arb / BB Breakout / 自主孵化策略）」
- analyst_agent.py 802 LOC，未 grep 到 hypothesis pipeline / dispatch experiment 路徑
- ADR-0020 標 Layer 2 manual + supervisor-only by design

**verdict**：✅ **正確**

#### Root cause 4：風控鐵血 vs alpha 放羊

**PA 主張**：4 risk_config*.toml + Guardian SM-04 5-step + Cost Gate vs 1 strategy_params*.toml + 4×5 regime weight

**E5 實證**：
- `find srv/settings -name "risk_config*"` 4 個 TOML（paper/demo/live + base）
- `strategy_params*.toml` 確實 1 個（per env override）
- guardian_agent.py 1458 LOC（5 agent 中最大）vs strategist 799

**verdict**：✅ **正確**（治理 forcing function 不對稱真實存在）

#### Root cause 5：5-Agent under-implemented over-spec

**PA 主張**：5-Agent 骨架正確但「靈魂」沒裝（Analyst L2-L5 + Strategist alpha-discovery + Layer 2）

**E5 實證**：
- 5-agent code 4308 LOC **存在**（不是 stub）
- Layer 2 ANTHROPIC_API_KEY 未設（CLAUDE.md §四）→ Layer 2 0 actor 真實
- ADR-0020 manual + supervisor-only 確實 freeze Layer 2 自主路徑

**verdict**：✅ **正確**

### 2.2 LOC 重構估計（E5 system architect 視角）

#### R-1 升級 Strategy Interface 為 Alpha Surface Bundle

PA 估計 **3-4 sprint**。

**E5 真實估算**：

**直接影響範圍**（grep TickContext = 28 files）：
- 5 production strategy impls（trait `on_tick` 6 callsites in strategies/）
- 3 stub impls（orchestrator MockStrategy / strategies/tests StubStrategy / replay/runner_tests 3 stubs = 5 stubs）
- replay/strategy_adapter.rs（context_builder + adapter）
- tick_pipeline/on_tick_helpers.rs:557 + step_4_5_dispatch.rs (production dispatcher)
- 1 trait method signature 改（`on_tick(&mut self, ctx) → on_tick(&mut self, ctx, surface)`）

**強制機制 LOC 估算**（PA 設計）：
- `AlphaSurface<'a>` struct 定義：~100 LOC（10 field + lifetime + Default + Debug）
- `AlphaSourceTag` enum：~30 LOC（10 variant）
- `declared_alpha_sources()` per-strategy：5 × ~5 LOC = 25 LOC
- TickContext 加 surface field 或構造 surface in pipeline：~50 LOC
- Orchestrator dispatch tracking：~150 LOC（hash map per alpha source × strategy）
- Strategy Registry waiver mechanism：~100 LOC

**間接影響**（cross-symbol panel / microprice / liquidation_pulse / sentiment_panel）：
- 每個 panel 收集邏輯（從 Bybit WS / REST 拉資料 + 維護 buffer）：~500 LOC × 4 = 2000 LOC
- IPC 序列化 + Python 端對應 model：~300 LOC
- Test coverage：~1500 LOC

**Migration 5 既存策略**：5 × ~50 LOC（聲明 alpha sources + 補空 surface 引用）= 250 LOC

**真實估算**：
- Spec phase：1 sprint
- IMPL（trait + struct + Tier 1-2 surface）：2 sprint
- 5 panel 真實接線（funding curve / OI delta / orderflow / liquidation）：2-3 sprint
- 5 既存策略 migration + test：1 sprint
- E2E + replay 鏈整合：1 sprint
- 治理 acceptance + cleanup：1 sprint

**E5 估算 = 8-9 sprint**（PA 樂觀 2.5×）

**判定**：⚠️ **PA 估計樂觀 2.5×**。3-4 sprint 只能完成 Tier 1（trait + struct + 5 既存策略 backward compat），**真正的「architectural forcing function」需 8-9 sprint**

#### R-2 Strategist scope reframe + AlphaSourceRegistry

PA 估計 **2-3 sprint**。

**E5 估算**：
- AlphaSourceRegistry Python class：~300 LOC（4-stage state machine + persist + lookup）
- 移除 `_REGIME_STRATEGY_PREFERENCES` + 動態 Sharpe-by-regime：~400 LOC（cross-strategy historical data fetcher + Sharpe by regime aggregation）
- `propose_alpha_source()` method：~200 LOC（Hypothesis emit + AI dispatch）
- Layer 2 alpha-source proposal flow（AMD §4 manual + supervisor-only 約束）：~150 LOC
- strategist_agent.py 799 → 估 ~1300 LOC（+500 LOC scope reframe）— 觸 800 warn 但 <1500
- Test coverage：~800 LOC

**真實 Sprint**：
- Spec + AlphaSourceRegistry：1 sprint
- Strategist refactor：1.5 sprint
- Test + integration：1 sprint
- Manual Layer 2 supervised flow IMPL：1 sprint

**E5 估算 = 4-5 sprint**（PA 樂觀 1.5×）

**判定**：⚠️ **PA 估計樂觀 1.5×**

#### R-3 Hypothesis Pipeline first-class

PA 估計 **3 sprint**。

**E5 估算**：
- `learning.hypotheses` schema (V### migration + Guard A/B/C per CLAUDE.md §七 SQL 規範)：~150 LOC SQL
- Hypothesis CRUD class：~500 LOC Python
- Decision Lease 加 `originating_hypothesis_id`：trait + DB schema migration + 接線 ~300 LOC
- ExecutionPlan / fills propagate hypothesis_id：~400 LOC
- attribution chain rewrite based on hypothesis_id：existing attribution_chain_ok 0.5% denominator artifact bug 需先解 ~200 LOC
- Analyst L3 IMPL（hypothesis state machine driver）：~600 LOC
- ML training feed from hypothesis verdict：~300 LOC
- Test coverage：~1200 LOC

**真實 Sprint**：
- Schema + state machine spec：1 sprint
- CRUD + Decision Lease integration：1.5 sprint
- attribution rewrite + ML feed：1.5 sprint
- E2E + 治理 acceptance：1 sprint

**E5 估算 = 5 sprint**（PA 樂觀 1.7×）

**判定**：⚠️ **PA 估計樂觀 1.7×**

#### R-1 + R-2 + R-3 總估算

| Wave | PA 估 | E5 估 | 倍率 |
|---|---:|---:|---:|
| R-1 Alpha Surface | 3-4 sprint | 8-9 sprint | 2.5× |
| R-2 Strategist reframe | 2-3 sprint | 4-5 sprint | 1.5× |
| R-3 Hypothesis Pipeline | 3 sprint | 5 sprint | 1.7× |
| **R-1+R-2+R-3 總** | **8-10 sprint** | **17-19 sprint** | **2×** |

**E5 對抗判定**：PA 估計 8-10 sprint 是 spec phase 完成的時間，**真正 IMPL + 5 panel wiring + Hypothesis state machine wired-up + cross-strategy Sharpe + ML feed 鏈 = ~17-19 sprint**（PA 整體樂觀 2×）

### 2.3 openclaw_core 9 dead modules sunset 評估

**E5 grep 證據**：

| Module | LOC | Production caller in engine | Test caller |
|---|---:|---|---|
| attention | 424 | ❌ 0 | ⚠️ unknown |
| attribution | 267 | ❌ 0 | ⚠️ unknown |
| backtest | 490 | ❌ 0 | ✅ openclaw_core/tests/golden_extreme.rs:8 |
| cognitive | 524 | ❌ 0 | ⚠️ unknown |
| **dream** | **936** | ❌ 0 | ⚠️ unknown |
| message_bus | 296 | ❌ 0 | ⚠️ unknown |
| opportunity | 861 | ❌ 0 (engine 內 `crate::scanner::opportunity` 是 sibling 不是 openclaw_core::opportunity) | ⚠️ unknown |
| order_match | 308 | ❌ 0 | ⚠️ unknown |
| portfolio | 362 | ❌ 0 | ✅ openclaw_core/tests/golden_extreme.rs:14 |
| **Total** | **4468 LOC** | **0 production callers** | 2 test callers |

**對抗 push back PA**：

PA 主張「sunset 9 模組」**證據基本成立**（4468 LOC dead production-wise），但：

**PA 主張 dream_engine 在 alpha-discovery 的角色**：
- `openclaw_core/src/dream.rs` 936 LOC 是 Rust port 候選 / Phase 0 placeholder
- PA 提出 R-3 Hypothesis Pipeline = 「Analyst L3 hypothesis dispatch」，邏輯上 dream_engine（Monte Carlo simulation / counterfactual play）**確實是 R-3 的潛在 IMPL 載體**
- E5 verdict：dream_engine 不應 sunset，應 reactivate as R-3 IMPL backbone（PA 自己沒明說）

**E5 建議分類**：
- **Sunset candidates（4 個 ~1295 LOC）**：attention 424 / attribution 267 / message_bus 296 / order_match 308 — 100% Python 重複 + 0 caller
- **Hold for R-3 IMPL（2 個 ~1898 LOC）**：dream 936（Hypothesis 反事實實驗載體）+ cognitive 524 + opportunity 861（factor library 候選）= 3 個 hold for review by PA + QC
- **Test-callable retain（2 個 ~852 LOC）**：backtest 490（golden_extreme 在用）+ portfolio 362（同）

**verdict**：⚠️ **PA 9 模組 sunset 判定過度**（漏看 dream/cognitive/opportunity 在 R-3/R-1 IMPL 角色）

### 2.4 「TA 高速公路 vs 其他泥路」architectural friction 真實性

**E5 grep tick_pipeline/mod.rs:665-708 + production strategy on_tick 對照**：

**TickContext 真實提供「first-class」**：
- ✅ funding_rate（EDGE-P1-2）
- ✅ index_price（OC-5）
- ✅ open_interest（raw value，need own buffer for delta）
- ✅ best_bid / best_ask（G7-09c Phase 1）
- ✅ tick_size（instrument cache）
- ✅ indicators (1m + 5m IndicatorSnapshot)
- ✅ signals (5 strategy crossover/breakout/etc)
- ✅ h0_allowed (H0 gate)

**TickContext 沒提供（PA 主張 R-1 加）**：
- ❌ cross-symbol funding curve（25 symbols snapshot for funding skew arb）
- ❌ cross-symbol OI delta panel
- ❌ orderflow features（microprice, queue imbalance）
- ❌ liquidation pulse（large trade tape）
- ❌ sentiment panel（from Scout）
- ❌ basis curve（spot vs perp basis aggregated）
- ❌ event_alerts typed（從 Scout IntelObject）

**對抗判定**：

PA 描述「TA 高速公路」隱喻 **誇大**：
- TA primitive 是 first-class（IndicatorSnapshot 16 indicators, pre-computed in tick path）
- 但 cross-asset / microstructure 也 partial first-class（5 個字段已存在）
- 真正的「architectural friction」是 **cross-section panel + orderflow tape + sentiment 在當前 architecture 下需要 strategy own-buffer + own-cycle pull**，**沒有中央化 panel maintainer**（這是 PA leverage point）

**E5 真實 friction 評估**：
- Single-symbol cross-asset alpha（funding_rate, index_price, best_bid）：✅ 已 first-class，friction = 0
- Cross-section panel alpha：⚠️ HIGH friction（need own buffer）
- Microstructure orderflow alpha：⚠️ HIGH friction（need WS subscription + own buffer）
- Event-driven alpha：⚠️ MEDIUM friction（Scout 已 emit IntelObject 但 Strategist 路徑不真依賴）

**verdict**：⚠️ **PARTIAL AGREE** — friction 真實存在但 PA 描述過度集中在「TA vs 其他」二分法，實際是「single-symbol vs cross-section vs microstructure」三層 friction

---

## §3 對抗性紅旗 + 治理 push back

### 3.1 5 commits 治理紅旗

| 紅旗 | 觀察 | 建議 |
|---|---|---|
| 🟡 ml_training_maintenance.py +505 LOC NEW warn | 430→935 (+118%) 觸 800 warn | P2 監控；如 +200 LOC 再強制拆 |
| 🔴 5 commits 全 source-only | engine 仍跑 5/9 14:02 build；Donchian fix + Rust strategist_scheduler 改動全是 dead code 直到 --rebuild | **deploy gate ticket**：累積 source-only Rust 改動清單 + 下次 restart_all 觸發前必審 |
| 🟡 V079 schema 未 PG empirical 驗 | sqlx hash drift incident（2026-05-02 P0）後遺；commit 加 V079 但無 Linux PG dry-run 證據 | 違反 CLAUDE.md §七「Linux PG dry-run mandatory (V055 5-round loop 衍生)」— PA 收尾必補 |
| 🟡 promotion_evidence.py 558 LOC 無 production 主路徑 caller | 唯一 caller `edge_estimator_scheduler.py:621` 是 lazy import；其他 0 caller | 待 cron 觸發 + monitor cycle 真實落 row |
| 🟡 5 EXTENDED_JOBS（thompson/optuna/cpcv/dl3/weekly）spec only | da2aba11 加 5 新 ML scope 但 cron --include-extended 未開 | spec only 不算 dead 但需明文 enablement plan |

### 3.2 PA redesign 治理 push back

| 紅旗 | PA 主張 | E5 對抗 |
|---|---|---|
| 🔴 strategist_agent.py LOC | PA 引「45000 LOC」 | 真實 799 LOC（Mac + Linux 都驗）；PA 引 CLAUDE.md §三 錯讀 |
| ⚠️ R-1 Sprint 估計 | 3-4 sprint | E5 真估 8-9 sprint（cross-symbol panel + microstructure + 5 既存 migration + E2E）= 2.5× |
| ⚠️ R-1+R-2+R-3 總時間 | 8-10 sprint | E5 真估 17-19 sprint = 2× |
| ⚠️ TA 高速公路隱喻 | 「strategy interface 結構性激勵 1m kline + classic indicator」 | TickContext 已含 funding_rate/index_price/best_bid/ask/OI 5 field；真正 friction = cross-section panel + orderflow，非 TA vs 其他二分 |
| 🟡 9 dead modules sunset | 全 sunset | dream 936 / cognitive 524 / opportunity 861 是 R-3 / Hypothesis Pipeline 潛在 IMPL 載體；建議 hold for review |
| ✅ 5 root cause 結構診斷 | A/B/C/D/E | E5 認可 4/5（root 1-4 證據成立；root 5 「under-implemented」更精確） |
| ✅ Hypothesis Pipeline first-class | R-3 設計 | E5 強烈認可（attribution_chain 0.5% 真因 = 沒 hypothesis 來歸因，PA 命中 root） |
| ✅ Per-alpha-source live promotion | R-4 設計 | E5 認可（單 alpha source 樣本量足先 graduate 比整 system live_reserved 更合理） |

---

## §4 結論

### 4.1 任務 A 5 commits 結構/性能

| 等級 | finding | 數 |
|---|---|---:|
| ✅ 合格 | LOC clean (0 hard 2000)，hot path 性能淨 0，純結構修真 logical bug (Donchian leak-bias) + 治理工件擴展 | 5/5 commit |
| ⚠️ Partial | ml_training_maintenance.py NEW 800 warn / V079 schema 待 PG 驗 / promotion_evidence cold path 接線 / 5 EXTENDED_JOBS spec only | 4 finding |
| ❌ Fail | 5 commits 全 source-only：Donchian production 修 + Rust strategist 改 = engine 跑 dead code | 1 finding |
| 🆕 NEW | 任何新 LOC 違反或 dead code | 0（純治理工件擴展） |

**淨判定**：✅ **STRUCTURAL CLEAN**，零 §九 hard cap 違反；hot path 性能淨 0；唯一治理紅旗 = source-only Rust commit 累積（與 v2 lesson #4 同類）

### 4.2 任務 B PA redesign

**E5 system architect 視角 verdict**：⚠️ **PARTIAL AGREE**

**PA 強項**：
- ✅ 5 root cause 結構診斷 4/5 證據成立
- ✅ Hypothesis Pipeline first-class（R-3）+ AlphaSurface（R-1）= **真實 leverage point**，這兩個是「砍對 88 finding 的根」
- ✅ Per-alpha-source live promotion（R-4）優於整 system live_reserved

**PA 弱項**：
- ❌ strategist_agent.py LOC 數字錯（799 不是 45000，差 56×）
- ⚠️ Sprint 估計樂觀 2×（17-19 sprint vs PA 8-10 sprint）
- ⚠️ TA 高速公路隱喻過度（TickContext 已含 cross-asset 5 field）
- 🟡 9 模組 sunset 判定過度（dream/cognitive/opportunity 是 R-3 IMPL 候選載體）
- ⚠️ 沒區分「single-symbol cross-asset 已 first-class」vs「cross-section/microstructure 真 friction」

**重構 LOC 總估**：
- AlphaSurface struct + AlphaSourceTag enum + declared_alpha_sources：~225 LOC
- 5 panel 真實接線（funding curve / OI delta / orderflow / liquidation / sentiment）：~2000 LOC
- IPC + Python model：~300 LOC
- Strategist refactor + AlphaSourceRegistry：~700 LOC，strategist_agent.py 799 → 估 ~1300 LOC
- Hypothesis CRUD + Decision Lease integration + attribution rewrite：~1900 LOC
- Test coverage：~3500 LOC
- **總 R-1+R-2+R-3 IMPL ~ 9000 LOC across 30+ files**

### 4.3 對抗性 sign-off SOP v3 補充

新加（基於本次核實教訓）：
1. **PA architectural claim 必逐條 grep 證據對照**（不採信抽象斷言）
2. **PA LOC 數字必逐檔 wc -l 對照**（45000 vs 799 是 56× 誤差，重要決策不能基於錯數據）
3. **Sprint 估計必拆「直接 trait 改 vs 間接 panel wiring vs E2E」三層**（避免 PA 樂觀 2.5×）
4. **Dead module sunset 必查 R-X redesign 是否複用該模組**（避免砍掉 R-3 IMPL 候選）
5. **5 commits 後 source-only Rust 累積必標**（v2 lesson #4 持續中，需 deploy gate ticket）

---

**報告路徑**：`srv/docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-09--optimization_verification_v3.md`

**核實口徑**：對抗性嚴苛 — commit message 不算數，必驗 LOC + binary + PG + 真實 caller + PA architectural claim 逐條 grep
