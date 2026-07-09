# REF-20 Sprint C — Task DAG Design (R6 Fee/Execution Calibration + R7 MLDE/Dream Advisory Integration)

**Date**: 2026-05-05
**Author**: PA (Project Architect)
**Status**: design ready (read-only; no IMPL, no commit)
**Sprint context**:
- Sprint A closed (HEAD `0ad79f67` Mac/Linux/origin sync) — R1+R2+R3 4 表 row > 0 evidence E2E PASS
- Sprint B closed (4 commit `2a69addb` → `c679a8b4` → `a2f819c5` → `4ffb24c4`) — R4 UI 5-state machine + R5 ReplayStrategyAdapter + ReplayRiskAdapter + IsolatedPipeline wire + config blob path 全綠；A4/A5 hermetic + proof_7/8 wiring PASS
- replay_routes.py 1500 → **1146 LOC**（Sprint B B1 R0-T0 釋放 354 LOC margin）
- 未 land：A6 fee-aware PnL / A7 confidence honesty / A10 MLDE-Dream advisory boundary（Sprint C scope）
- 未 land：A8 UI usable end-to-end（Sprint D R8 maintenance + R9 sign-off scope）
- `evidence_source_tier='synthetic_replay'` 仍非 ML training data（CLAUDE.md §九 既登記）

**PM 派發 scope**：Sprint C = R6（Fee/Execution Calibration）+ R7（MLDE/Dream Advisory Integration）

---

## §0. PA Push Back（必填，PM 須先回答）

### §0.1 強烈建議拆 Sprint C → C1（R6）+ C2（R7）兩個獨立 sprint

| # | 證據 | 風險級別 |
|---|---|---|
| 1 | R6 task chain owner = PM → QC → MIT → E1 → E2 → E4 → PM。R7 task chain owner = PM → QC → MIT → **AI-E** → E1 → E2 → E4 → PM。**AI-E 在 R7 才入鏈**。R7 的 advisory boundary 設計（candidate generation veto / verified insert / replay_experiment_id 鏈條）需要 AI-E 從 MLDE/Dream 學習平面立場拍板，不是純 IMPL 工。 | 高 — 兩條 owner chain 不對稱，merge 進單 sprint 會 serialize bottleneck（QC 必先做完 R6 calibration 數學審計，才能放 R7 的 advisory threshold；MIT 必先做完 R6 calibration sample size sufficiency 才能拍 R7 的 verify gate）。 |
| 2 | R6 數學負擔極重 — 既有 `AccountManager::refresh_fee_rates()` + `IntentProcessor::fee_rate_for_intent()` + `slippage_rate_for_intent()` 與 `cost_gate_paper` 形成 4 個介面點。**任一點數學錯誤** = 全 simulated_fills.fee_bps 被污染。校驗 demo/live_demo 7d/14d/30d 樣本與 confidence label 的數學需 QC（confidence interval bounds / kalman / regime detection）+ MIT（calibration sample size enough? out-of-sample test? overfitting?）兩位 advisor 介入。1 sprint 內串到 QC + MIT 已緊。 | 極高 — Sprint A 8-commit chain 教訓：「即使簡單 IMPL 也會出 6-layer blocker chain」。R6 + R7 同 sprint 至少 8-10 task，blocker 鏈條風險倍增。 |
| 3 | **R7 完全依賴 R6 calibration label**。MLDE/Dream advisory 鏈條的 `evidence_source_tier='calibrated_replay'` 只有在 R6 deliver `execution_confidence='calibrated'` 後才能存在。R7 同 sprint 平行做 = 工作流根本不通（R7 IMPL 跑 0 row 因為 R6 還在開工）。 | 極高 — 工作鏈天然 serialize。 |
| 4 | LOC §九 1500 cap 風險 — Sprint B 已釋 354 LOC margin（replay_routes.py 1500→1146），但 R6 估增 ~150-250 LOC（fee model wiring + slippage model + label producer），R7 估增 ~200-300 LOC（4 producer wire 真 replay metadata + verify gate + handoff_routes 接 calibrated tier）。**單 sprint 把 newly-landed B 預算燒回 cap 邊緣**，下次 wave 又破。 | 中 — 預算規劃不利長期。 |
| 5 | R6 的 calibration data 基礎：grid_trading 7d demo 642 fills + live_demo 520 fills（CLAUDE.md §三）；ma_crossover 7d demo 378 + live_demo 257 fills。**樣本量 confidence 邊界**：grid 已可達 'limited'/'calibrated' 邊緣；ma 接近 'limited'；funding/bb_breakout/bb_reversion 樣本不足必為 'none'。R6 樣本量決策需 QC + MIT 拍板「dataset cut threshold」，這本身是 1 個 task。 | 中 — pilot scope 與 calibration confidence 拉鋸。 |
| 6 | **LG-3 RFC `5ce777b` 0% IMPL 問題**：CLAUDE.md §三 18-blocker #3 列「LG-3 provider pricing binding IMPL（0% binding contract）」。但 PA cold review 真實源碼後發現：`AccountManager::refresh_fee_rates` + `seed_default_fee_rates` + hourly task spawn (`tasks.rs:54`) 全已 land；`IntentProcessor::fee_rate_for_intent` 已根據 PostOnly TIF 區分 maker/taker；DEFAULT_TAKER_FEE=0.00055 + DEFAULT_MAKER_FEE=0.0002 已在 `account_manager.rs:136-138`。**LG-3 RFC 0% 指的不是 fee runtime IMPL，是 binding contract / staleness HC / startup assertion 三件治理事**。R6 真正阻塞點是「provider source label + last_refresh_age 透出」，不是「fee 模型本身不存在」。 | 中 — 風險點認知偏差。RFC 真正需 IMPL 的是 healthcheck output（`pricing_binding: mode=live category=linear source=bybit last_refresh_age=...`）。R6 只需 reuse 現有 fee runtime + 加 calibration label。 |
| 7 | **P1-DATA-1 LG5-W3-FUP-2 attribution_chain_ok writer fix** sibling CC 仍在 flight（CLAUDE.md §三 18-blocker #11：MLDE training row 84.6% `attribution_chain_ok=false`）。R7 的 MLDE evidence 路徑 (`mlde_demo_applier.py::_insert_live_candidate` 已 verify_replay_evidence call) 與 attribution_chain_ok 是兩條獨立路徑（前者寫 mlde_shadow_recommendations，後者寫 mlde_demo_attribution training data），不在同一 row。但 R7 expand 後 demo applier 寫的 calibrated_replay row 可能被 sibling CC 的 attribution writer fix 影響 — 必須 align 接線時序。 | 中 — 跨 CC session 協作風險。 |
| 8 | **Sprint A 8-commit chain 顯示「即使 contract 看似明確的 IMPL 也會出 blocker chain」**：R6 + R7 同 sprint 估計至少 12-14 task，每 task 加 1 個 blocker 鏈節點 = 12-14 commit chain 風險。 | 中 — 歷史模式。 |

**PA 建議切分**：

```
Sprint C1 (3-4d wall): R6 Fee/Execution Calibration
                       - grid_trading + ma_crossover pilot
                       - fee model + slippage model + label producer
                       - confidence label 'none' / 'limited' / 'calibrated'
                       - LG-3 healthcheck output（順帶 unblock）

Sprint C2 (3-4d wall): R7 MLDE/Dream Advisory Integration
                       - 4 producer (MLDE / Dream / OpportunityTracker / LinUCB) 升級 verify_replay_evidence 真 replay metadata 路徑
                       - mlde_demo_applier_evidence_filter 對 calibrated_replay 解封
                       - handoff_routes 接 calibrated tier
                       - R6 deliver 後再啟，依賴 R6 label producer
```

**若 PM 仍堅持單 Sprint C 涵蓋 R6+R7**：本 report §1-§9 仍適用，但 §7 task DAG 假設 PA push back 被 accept；§7 末尾附「PM override 路徑」說明若不拆會增加哪些 risk。

> **PA 報告其餘章節先以 C1=R6 / C2=R7 為基礎**。PM 拍板後再依結果回讀。

### §0.2 進一步拆分 R6 是否需要？

**PA 答**：**不需要**。R6 雖然 task 數中等（估 7-8），但全部都在 fee/slippage/calibration 同一 conceptual cluster。Wave 結構天然清晰（fee + slippage 並行 → calibration → label producer → integrate writer），不必再切。

**例外**：若 PM 要求加做 LG-3 RFC 的「startup assertion」（live engine 不能在 fee table stale beyond max age 時 spawn），R6 必額外加 1 task — 但**強烈建議延 Sprint D**（startup assertion 屬 maintenance / observation 範疇）。

### §0.3 進一步拆分 R7 是否需要？

**PA 答**：**不需要**，但 task 內部 ordering 較緊。R7 task 數估 8-9，但 4 producer (MLDE / Dream / OpportunityTracker / LinUCB) 全是同型模式，可並行 dispatch（4 sub-agent same-pattern）。

### §0.4 是否需要先派 QC + MIT advisory 才能完成 task DAG（pre-DAG advisory）？

**PA 答**：**部分必要**。建議 1h 內並行派 QC + MIT 各做 1 個 advisory deliverable，然後 PA 回讀並調整 task DAG：

| Advisor | Deliverable | 阻塞點 |
|---|---|---|
| QC | R6 confidence label 'limited' vs 'calibrated' 切點數學定義 — 至少需要 (a) sample count threshold（如 ≥30 fills/strategy/symbol/regime）、(b) freshness threshold（如 last fill ≤ 7d）、(c) confidence interval bound（如 fee_bps σ < 5 bps）、(d) regime detection（trending vs mean-reverting market）。**QC 不寫 code，只給數學 spec**。 | 1d 內 |
| MIT | (1) `verify_replay_evidence_and_insert` 既有 4 producer (mlde/dream/opportunity/linucb) 升級 evidence_source_tier 到 calibrated_replay 後 `mlde_demo_applier_evidence_filter` 是否會誤拒 row（看 `caps["replay_experiments_has_expires_at"]` capability 探測邏輯）；(2) `replay.handoff_requests` schema 是否需擴 calibrated_replay tier（V044 既 ship 但 result CHECK 3-value 是 success/failed/rejected，不含 tier）。**MIT 不寫 code，只給 schema risk assessment**。 | 1d 內 |

**並行 dispatch 後 PA 1h 回讀** → 調整 §3.R6-T2/R6-T5 + §4.R7-T2/R7-T6 task spec → 再 dispatch E1。

### §0.5 LG-3 RFC 0% IMPL 是否阻塞 R6？

**PA 答**：**不阻塞 R6 calibration IMPL**，但 R6 應**順帶 unblock LG-3 healthcheck output** 一個 task（~30 LOC），把 fee_rate_count + last_fee_refresh_age + provider source 透出。理由：
- LG-3 RFC §IMPL T1（contract tests）+ T2（healthcheck）+ T3（startup assertion）三件，T1 + T2 屬 R6 自然延伸
- T3 startup assertion 是 LG-4 supervised live IMPL 前提，不在 R6 scope
- **PA 建議 R6 順手把 T1 + T2 closed**（R6-T7 healthcheck task），LG-3 RFC closure 從 0% → 70%

### §0.6 P1-DATA-1 LG5-W3-FUP-2 attribution_chain_ok writer fix in flight 是否阻塞 R7？

**PA 答**：**不阻塞，但需 align 時序**。理由：
- LG5-W3-FUP-2 是寫 `mlde_demo_attribution.attribution_chain_ok` field 的 writer fix，只影響 ML training row
- R7 的 4 producer 寫 `mlde_shadow_recommendations` 透 `verify_replay_evidence_and_insert`，不寫 `mlde_demo_attribution`
- 兩條路徑 schema 級獨立，**0 schema-level 衝突**
- 但**logic 級需 align**：sibling CC FUP-2 完工後，`attribution_chain_ok=true` 的 mlde_demo_attribution row 會被 mlde_demo_applier 用作 source — 該 row 透 `_insert_live_candidate` 寫 mlde_shadow_recommendations 用 `evidence_source_tier='real_outcome'`（demo→live promotion candidate audit row 屬 legacy producer 路徑，已在 mlde_demo_applier.py:1273 寫死）。**R7 不需動 _insert_live_candidate**；R7 改的是 dream_engine.py / opportunity_tracker.py 的 evidence_source_tier 寫 calibrated_replay 路徑（針對 dream/opportunity 從 replay artifact 取 candidate 的 case）。

**結論**：兩 CC session 互不衝突，但 R7 dispatch 前必先 `git fetch && git branch -r | grep "fup-2"` 看 sibling 是否已 land；若 sibling 還在 flight 且 R7 動 `mlde_demo_applier_evidence_filter.py`，則 conflict 風險 +1。

---

## §1. R6 Inventory — 真實 Fee/Slippage/Cost Gate Call Graph

### §1A. Rust 端 fee runtime（已 land，**無需重做**）

| 元件 | 真實位點 | 角色 | 狀態 |
|---|---|---|---|
| `FeeRate` struct | `account_manager.rs:80-87` | maker_fee_rate + taker_fee_rate per symbol | ✅ |
| `DEFAULT_TAKER_FEE = 0.00055` | `account_manager.rs:136` | conservative fallback | ✅ |
| `DEFAULT_MAKER_FEE = 0.0002` | `account_manager.rs:138` | conservative fallback | ✅ |
| `AccountManager::refresh_fee_rates(&client, "linear")` | `account_manager.rs:266` | Bybit V5 `GET /v5/account/fee-rate` | ✅ |
| `AccountManager::seed_default_fee_rates(symbols)` | `account_manager.rs:324` | demo/unsupported endpoint fallback | ✅ |
| `AccountManager::get_fee_rate(symbol)` | `account_manager.rs:361` | hot-path read | ✅ |
| `AccountManager::maker_fee(symbol)` / `taker_fee(symbol)` | `account_manager.rs:376-388` | per-class hot-path | ✅ |
| `AccountManager::last_fee_refresh_ms()` | `account_manager.rs:170` | staleness atomic counter | ✅ |
| `tasks::spawn_fee_rate_tasks()` hourly refresh task | `tasks.rs:54` | live engine 每小時 refresh | ✅ |
| `IntentProcessor::fee_rate_for_intent(symbol, intent)` | `intent_processor/mod.rs:1131` | PostOnly → maker / 否則 taker | ✅ |
| `IntentProcessor::slippage_rate_for_intent(intent, volume_24h)` | `intent_processor/mod.rs:1175` | turnover-based slippage estimate | ✅ |
| `IntentProcessor::cost_gate_paper(strategy, symbol, atr, conf, qty, price, fee_rate, slippage_rate)` | `intent_processor/router.rs:512` | edge vs cost gate | ✅ |

**結論**：Rust live 端 fee/slippage 運行時**完全 ready**。R6 的工作不在「重做 fee 模型」，而在「把 live 端的 fee/slippage 運行時 mirror 到 replay 端 + 加 calibration label」。

### §1B. Strategy 端 fee-aware logic

| Strategy | 哪裡用 fee_rate | 影響 | 純度 for replay |
|---|---|---|---|
| grid_trading | `grid_helpers.rs:90` `compute_ou_step(history, ou_lookback, fee_rate)` 計 OU spacing 含 fee floor (`fee_floor = 2.0 * fee_rate * mu * multiplier`) | grid spacing 不能小於 fee 帶寬 | 純 — 純函數，已可 replay |
| grid_trading | `grid_layout.rs:105` 用 `self.fee_rate` 重算 | 同上 | 純 |
| grid_trading | `constructors.rs:199` `set_fee_rate(rate)` setter | TickPipeline 啟動時注入 fee_rate | 純 — replay 端 ReplayStrategyAdapter 可用 set_fee_rate 注入 |
| grid_trading | `constructors.rs:58/109/174` `fee_rate: DEFAULT_FEE_PCT` 預設 | grid 預設 fee | 純 |
| ma_crossover / bb_breakout / bb_reversion / funding_arb | 0 fee_rate 參數 | 不 fee-aware | 0 風險 |

**結論**：grid_trading 是唯一 fee-aware strategy，但 fee_rate 是純參數，replay 端可直接呼 `set_fee_rate(...)` 注入。**5 strategy 對 R6 的 IMPL 0 改動**。

### §1C. Replay 端既有 fee 處理

| 元件 | 真實位點 | 當前狀態 | R6 需做 |
|---|---|---|---|
| Rust replay_runner `apply_fill` | `replay/runner.rs:908-985` | 「Sprint A baseline `fee=0.0`；Sprint C R6 將引入真實 maker/taker」（注釋已標 R6） | replace fee=0 with maker/taker model |
| Rust replay_runner SimulatedFill struct | `replay/runner.rs:170` | 「price = event close (we do not model slippage in T1)」 | inject calibrated slippage |
| Rust replay_runner KellyConfig injection | `bin/replay_runner.rs:486-488` | 「when fee model lands... R6 落 fee 模型時注入 calibrated KellyConfig」 | wire calibrated KellyConfig with fee_rate |
| Python writer `simulated_fills_writer.py:20-23` | replay/simulated_fills_writer.py:20 | 「`fee = 0.0`, `fee_rate = 0.0` — Sprint A has no fee model」 | parse fee_bps + slippage_bps from Rust JSON |
| Python writer `liquidity_role = 'taker'` | replay/simulated_fills_writer.py:72 | synthetic walker 寫死 taker | parse maker/taker from Rust（依 PostOnly TIF） |
| Python writer `execution_model_version = 'synthetic_v1'` | replay/simulated_fills_writer.py:74 | sentinel | replace with `'calibrated_v1'` 等 R6 模型 ID |
| Python writer `ci_low_bps / ci_mid_bps / ci_high_bps` | replay/simulated_fills_writer.py:75 | NULL — Sprint A 無 confidence | populate from R6 calibration |

### §1D. Bybit fee runtime 真實值（從 `account_manager.rs` + `docs/references/2026-04-04--bybit_api_reference.md`）

| Tier | maker_fee_rate | taker_fee_rate | 來源 |
|---|---:|---:|---|
| Bybit linear default (no VIP) | 0.0002 (2 bps) | 0.00055 (5.5 bps) | `account_manager.rs:136-138` const |
| Bybit live API real-time | depends on VIP tier | depends on VIP tier | `GET /v5/account/fee-rate?category=linear` |
| Demo endpoint | unsupported → fallback | unsupported → fallback | `seed_default_fee_rates` |

**Sprint C R6 實際決策**：
- demo/live_demo replay → use seed_default fees（不依賴 demo endpoint）
- 真實 demo+live_demo 7d/14d/30d historical fills → 從 `trading.fills.fee_rate` column 直接取（已存在 column；trading_writer 寫入）
- 未來 live 端 replay → use AccountManager.taker_fee/maker_fee live-cached values

### §1E. Calibration data source — `trading.fills` 真實 schema 與樣本量

```sql
-- 7d gross PnL（CLAUDE.md §三）
-- grid_trading: 642 demo + 520 live_demo
-- ma_crossover: 378 demo + 257 live_demo
-- funding_arb: 99 demo（V2 棄策略）
-- bb_breakout: 14d 34 demo / 0 live_demo
-- bb_reversion: 7 demo / 0 live_demo
```

R6 calibration 樣本切點建議（**待 QC advisor 拍板**）：

| Strategy | 7d 樣本 | confidence label 推薦 |
|---|---:|---|
| grid_trading | 1162 | 'calibrated'（樣本充足） |
| ma_crossover | 635 | 'limited'（樣本中等，需 14d 拓寬） |
| funding_arb | 99 | 'none'（V2 棄策略，不在 pilot） |
| bb_breakout | 34 | 'none'（樣本不足） |
| bb_reversion | 7 | 'none'（樣本嚴重不足） |

**R6 pilot scope**：grid_trading + ma_crossover（與 Sprint B2 R5 pilot 一致；不擴 5 strategy）。

---

## §2. R7 Inventory — 真實 MLDE/Dream/Handoff Call Graph

### §2A. `learning.verify_replay_evidence_and_insert()` (V036) — 已 land 完整

**真實位點**：`sql/migrations/V036__replay_evidence_source_guard.sql`

**Function signature**（17 args）：
```sql
verify_replay_evidence_and_insert(
    p_engine_mode TEXT,
    p_symbol TEXT,
    p_strategy_name TEXT,
    p_source TEXT,                         -- ∈ {ml_shadow, dream_engine, opportunity_tracker, linucb}
    p_recommendation_type TEXT,
    p_expected_net_bps DOUBLE PRECISION,
    p_confidence DOUBLE PRECISION,
    p_sample_count INTEGER,
    p_payload JSONB,
    p_applied BOOLEAN,
    p_requires_governance BOOLEAN,
    p_created_by TEXT,
    p_evidence_source_tier TEXT DEFAULT 'real_outcome',
                                           -- ∈ {real_outcome, calibrated_replay,
                                           --     synthetic_replay, counterfactual_replay}
    p_replay_experiment_id TEXT DEFAULT NULL,
    p_manifest_hash TEXT DEFAULT NULL,
    p_expires_at TIMESTAMPTZ DEFAULT NULL,
    p_decision_lease_id TEXT DEFAULT NULL,
    p_context_id TEXT DEFAULT NULL,
    p_intent_id TEXT DEFAULT NULL
) RETURNS BIGINT
```

**Compound CHECK**:
- `tier='real_outcome'` ⇒ `replay_experiment_id IS NULL AND manifest_hash IS NULL`
- `tier!='real_outcome'` ⇒ `replay_experiment_id IS NOT NULL AND manifest_hash IS NOT NULL AND expires_at IS NOT NULL AND expires_at > now()`

**結論**：R7 **不需新加 V### migration**。整個 verify gate + producer allowlist + tier compound CHECK + TTL hard check 已 land。R7 的工作 = 把 4 producer 從 hardcoded `'real_outcome' / NULL,NULL,NULL` 升級到「真 replay metadata 路徑」（看 §2B / §2C）。

### §2B. 4 producer 既有寫入路徑

| Producer | 真實位點 | 當前 evidence_source_tier 行為 | R7 需做 |
|---|---|---|---|
| `mlde_demo_applier._insert_live_candidate` | `mlde_demo_applier.py:1260` | hardcoded `'real_outcome' / NULL, NULL, NULL`（line 1273-1274）— LG-5 audit row legacy 路徑 | **不動**（PA 解讀：mlde_demo_applier 的 demo→live promotion candidate 是 legacy LG-5 audit 路徑，與 replay 無關） |
| `dream_engine.persist_replay_candidate_recommendations` | `dream_engine.py:447` | hardcoded `'real_outcome' / NULL, NULL, NULL, NULL`（line 462-465） | **升級**：dream_engine 從 replay artifact 取 candidate 時，evidence_source_tier='calibrated_replay'（依 R6 label） + replay_experiment_id + manifest_hash + expires_at |
| `dream_engine.generate_replay_candidates` | `dream_engine.py:790`（Wave 6 R20-P4-Q4 既有 surface） | （需驗位點是否已寫 verify_replay_evidence call） | **升級或新加**：generate_replay_candidates 接 replay artifact 後寫 verified row |
| `opportunity_tracker.persist_replay_outcome` | `opportunity_tracker.py:247` | hardcoded `'real_outcome' / NULL, NULL, NULL`（line 260） | **升級**：從 replay run 取 row 時改 calibrated_replay |
| `linucb` (location TBD) | grep `linucb.*verify_replay`（記憶體 [LinUCB shadow compare 保留 (2026-04-23)] 中說 4-06 deferred；可能 0 caller） | 可能無 caller | **驗證並決定**：若 0 caller，R7 不必動；若有 caller，升級 |

### §2C. MLDE evidence filter (consumer side)

**真實位點**：`mlde_demo_applier_evidence_filter.py`

```python
# Block A: evidence_source_tier='real_outcome' OR
# Block B: replay_experiment_id NOT NULL AND
#          manifest_hash NOT NULL AND
#          expires_at > now() AND
#          status IN (...)
```

**capabilities probe**（line 110-148）：
- `has_replay_experiment_id` (mlde_shadow_recommendations 端是否有此 column)
- `has_manifest_hash` (同上)
- `replay_experiments_has_expires_at` (replay.experiments 端是否有 expires_at)
- 三條 capability 全 true 才走 Block B；否則 graceful fallback Block A only

**結論**：R7 啟用 calibrated_replay 後，mlde_demo_applier_evidence_filter 自動切走 Block B（capability 已滿）。**0 IMPL 改動**，但 R7-T7 必加 integration test 驗 capability 探測 + Block B SQL 真行。

### §2D. `replay.handoff_requests` schema (V044 already land)

**真實位點**：`sql/migrations/V044__replay_handoff_idempotency_unique.sql`

| 欄位 | 型別 | 約束 |
|---|---|---|
| `handoff_id` | UUID PK | |
| `actor_id` | TEXT | UNIQUE(actor_id, idempotency_key) |
| `idempotency_key` | TEXT | (合 actor_id 唯一) |
| `trace_id` | UUID | UNIQUE |
| `result` | TEXT | CHECK ∈ ('success', 'failed', 'rejected') |
| `reject_reason` | TEXT | CHECK ∈ ('phrase_format_invalid', 'phrase_mismatch', 'cooldown_in_progress', 'experiment_not_found', 'manifest_signature_failed', NULL) |
| `experiment_id` | UUID | FK 不強制至 replay.experiments per V045 fixture-vs-migration pattern |

**結論**：handoff_requests 是 operator typed-confirmation 路徑（Wave 8 P6 demo handoff），**與 R7 advisory 路徑解耦**。R7 不需動 handoff schema。

但 **handoff_routes.py** 的 lookup 路徑可能需擴 calibrated_replay tier — 看下節 §2E。

### §2E. handoff_routes.py 與 R7 advisory 互動

**真實位點**：`program_code/exchange_connectors/bybit_connector/control_api_v1/app/handoff_routes.py`

**現狀**（從 main.py:280 注釋讀出）：
- handoff_routes.py 是獨立 file（非 replay_routes.py 內），承 P6-S13/S14/S15 trio
- handoff_routes 處理 operator 觸發的「demo handoff」（typed confirmation phrase）
- 與 advisory 路徑（dream_engine / mlde_demo_applier）獨立

**R7 是否需動 handoff_routes**：**否**（PA 解讀）。handoff_routes 是 operator UI → SQL handoff_requests 寫入路徑，advisor evidence 不走此路徑。

**E2 必查**：R7 IMPL 完工後 grep `handoff_routes.py` 看是否有 calibrated_replay 字串相關改動 — 若有則 PA push back（不應在 R7 動）。

### §2F. V051 mlde_recommendations 雙路 CHECK

**真實位點**：`sql/migrations/V051__mlde_recommendations_replay_columns.sql`

```sql
ALTER TABLE learning.mlde_shadow_recommendations
ADD COLUMN IF NOT EXISTS replay_experiment_id UUID,
ADD COLUMN IF NOT EXISTS manifest_hash BYTEA;

CONSTRAINT chk_mlde_shadow_replay_lineage CHECK (
  (evidence_source_tier = 'real_outcome' AND replay_experiment_id IS NULL AND manifest_hash IS NULL)
  OR
  (evidence_source_tier IN ('calibrated_replay', 'synthetic_replay', 'counterfactual_replay')
   AND replay_experiment_id IS NOT NULL AND manifest_hash IS NOT NULL)
);
```

**結論**：V051 雙路 CHECK 已 land，與 V036 verify_replay_evidence_and_insert 對齊。R7 啟用 calibrated_replay 後，paired CHECK 自動守門（producer 漏傳 metadata → DB 層 reject）。

**R7 是否需擴 V051 CHECK to advisory tier**：**否**。3 個 replay tier (calibrated/synthetic/counterfactual) 已含 R7 advisory 所需。

---

## §3. R6 Task DAG（Sprint C1 假設 PA push back accept）

### §3.1 R6 task 分解

| Task | scope | LOC est | 並行？ | 依賴 | 改檔位點 |
|---|---|---:|---|---|---|
| R6-T0 | (advisory) QC 給 confidence label 'limited' vs 'calibrated' 數學 spec | 0 (spec only) | ❌ pre-DAG | 0 | 無 |
| R6-T1 | Rust replay_runner `apply_fill` fee model — replace `fee=0.0` with maker/taker selection by TIF | +60 (Rust) | ✅ T2 並行 | 0 | `rust/openclaw_engine/src/replay/runner.rs:908-985` |
| R6-T2 | Rust replay_runner slippage model — replace `price=event_close` with spread/slippage estimate | +80 (Rust) | ✅ T1 並行 | 0 | `rust/openclaw_engine/src/replay/runner.rs:170+677` |
| R6-T3 | Rust replay_runner KellyConfig injection — wire calibrated KellyConfig with fee_rate | +30 (Rust) | ❌ 序列 | T1 | `rust/openclaw_engine/src/bin/replay_runner.rs:486-488` |
| R6-T4 | Rust replay_runner CalibrationLabelProducer — derive execution_confidence from sample count + freshness + CI bound + regime | +120 (Rust) | ❌ 序列 | T1+T2+T3 | `rust/openclaw_engine/src/replay/calibration_label.rs`（新檔） |
| R6-T5 | Python `simulated_fills_writer.py` payload extension — parse fee_bps + slippage_bps + ci_low/mid/high_bps + execution_model_version + liquidity_role from Rust JSON | +60 (Python) | ✅ T6 並行 | T4 | `replay/simulated_fills_writer.py:491+602+621` |
| R6-T6 | Python `experiment_registry.py` — 寫 `execution_confidence` column from R6 calibration result | +40 (Python) | ✅ T5 並行 | T4 | `replay/experiment_registry.py:1063` |
| R6-T7 | LG-3 healthcheck（順帶 unblock）— add `pricing_binding` healthcheck output (mode/category/source/last_refresh_age/verdict) | +40 (Rust 或 Python) | ✅ T1-T6 並行 | 0 | `helper_scripts/db/passive_wait_healthcheck.py` 或 Rust ipc_server status route |
| R6-T8 | Calibration smoke + parameter delta replay test — A6 + A7 acceptance | +200 (Python+Rust test) | ❌ 序列 | T1-T7 | `tests/replay/test_fee_calibration.py`（新檔） |
| R6-T9 | E2 review + E4 regression | (review only) | ❌ 序列 | T1-T8 | n/a |

### §3.2 R6 Wave 結構

```
Wave 0（advisory, 1d）：QC 給 confidence label 數學 spec（pre-DAG）
                       MIT 給 mlde_demo_applier_evidence_filter capability 風險 assessment

Wave 1（並行 4 task，1.5d）：T1 / T2 / T7 / (T6 可起跑等 T4 deliver schema 後再 final)
  T1: Rust fee model in apply_fill
  T2: Rust slippage model in apply_fill
  T7: LG-3 healthcheck（與 T1/T2 解耦）

Wave 2（序列 1 task，0.5d）：T3 wire KellyConfig

Wave 3（序列 1 task，1d）：T4 CalibrationLabelProducer

Wave 4（並行 2 task，0.5d）：T5 / T6
  T5: Python simulated_fills_writer.py payload extension
  T6: Python experiment_registry.py execution_confidence write

Wave 5（序列 1 task，1d）：T8 calibration smoke + param delta replay test

Wave 6（序列 1 task，1d）：T9 E2 review + E4 regression
```

**總 wall**：1d (advisory) + 1.5d (W1) + 0.5d (W2) + 1d (W3) + 0.5d (W4) + 1d (W5) + 1d (W6) = **6.5d wall**

**並行 sub-agent 派發**：

```
Sprint C1 dispatch wave:

  pre-DAG advisory wave (1d):
    QC: confidence label 數學 spec (1h)
    MIT: capability risk assessment (1h)

  Wave 1 (1.5d wall):
    E1-A: R6-T1 (Rust fee model in apply_fill) — isolated（runner.rs 內 apply_fill 函數）
    E1-B: R6-T2 (Rust slippage model in apply_fill) — isolated（runner.rs 內 SimulatedFill struct）
    E1-C: R6-T7 (LG-3 healthcheck) — isolated（healthcheck 端，不動 runtime）
    => 3 sub-agent 並行（同檔但不同函數，加 isolation: worktree）

  Wave 2 (0.5d):
    E1-A: R6-T3 (Rust KellyConfig wire — bin/replay_runner.rs)
    （single task，不並行）

  Wave 3 (1d):
    E1-A: R6-T4 (Rust CalibrationLabelProducer 新模組)
    （single task；新檔不並行）

  Wave 4 (0.5d):
    E1-A: R6-T5 (Python simulated_fills_writer.py payload extension)
    E1-B: R6-T6 (Python experiment_registry.py execution_confidence write)
    => 2 sub-agent 並行（不同檔）

  Wave 5 (1d):
    E1-A: R6-T8 (calibration smoke + param delta replay test)

  Wave 6 (1d):
    E2 review pass
    E4 regression PASS
```

---

## §4. R7 Task DAG（Sprint C2 假設 PA push back accept；R6 deliver 後再啟）

### §4.1 R7 task 分解

| Task | scope | LOC est | 並行？ | 依賴 | 改檔位點 |
|---|---|---:|---|---|---|
| R7-T0 | (advisory) AI-E 給「dream/opportunity/linucb 從 replay artifact 取 candidate 的真實流程」spec | 0 (spec only) | ❌ pre-DAG | 0 | 無 |
| R7-T1 | `dream_engine.py::persist_replay_candidate_recommendations` — replay_experiment_id + manifest_hash 從 replay artifact 取，evidence_source_tier='calibrated_replay'（依 R6 label） | +50 (Python) | ✅ T2 並行 | R6 done | `program_code/local_model_tools/dream_engine.py:447-487` |
| R7-T2 | `dream_engine.py::generate_replay_candidates` (Wave 6 既 ship 但需驗 verify_replay_evidence_and_insert 接線) | +30 (Python) 或 +0 (verify only) | ✅ T1 並行 | R6 done | `program_code/local_model_tools/dream_engine.py:790`（grep 確認位點） |
| R7-T3 | `opportunity_tracker.py::persist_replay_outcome` — 同 T1 模式 | +50 (Python) | ✅ T1+T2 並行 | R6 done | `program_code/local_model_tools/opportunity_tracker.py:247-278` |
| R7-T4 | LinUCB caller 驗（grep `linucb.*verify_replay`）— 若 0 caller，task 結束；若有，升級同 T1 模式 | +0 to +50 (Python) | ✅ T1+T2+T3 並行 | R6 done | TBD（grep 後決定） |
| R7-T5 | `mlde_demo_applier_evidence_filter.py` capability probe + Block B integration test | +100 (Python test) | ✅ T6 並行 | T1+T3 | `program_code/ml_training/mlde_demo_applier_evidence_filter.py` + `tests/ml_training/test_evidence_filter_capability.py`（新） |
| R7-T6 | E2E test：register replay → run → finalize → MLDE consume → mlde_demo_applier filter → calibrated_replay row promotes | +250 (Python+integration) | ❌ 序列 | T1-T4 | `tests/replay/test_mlde_dream_advisory_integration.py`（新） |
| R7-T7 | replay_experiment_id + manifest_hash FK chain audit — V049 → V051 → mlde_shadow_recommendations 全鏈 SQL acceptance | +100 (Python+SQL test) | ✅ T6 並行 | T1+T3 | `tests/replay/test_advisory_lineage_fk.py`（新） |
| R7-T8 | `lookup_replay_config_blob` reuse audit — verify dream/opportunity 用同一 helper 取 manifest metadata（experiment_registry.py:566） | +30 (Python) | ✅ T7 並行 | T1+T3 | `replay/experiment_registry.py:566` reuse audit |
| R7-T9 | E2 review + E4 regression | (review only) | ❌ 序列 | T1-T8 | n/a |

### §4.2 R7 Wave 結構

```
Wave 0（advisory, 1d）：AI-E 給 dream/opportunity/linucb 從 replay artifact 取 candidate 真實流程

Wave 1（並行 4 task，1.5d）：T1 / T2 / T3 / T4
  T1: dream_engine persist_replay_candidate_recommendations 升級
  T2: dream_engine generate_replay_candidates 驗證
  T3: opportunity_tracker persist_replay_outcome 升級
  T4: linucb 驗證（可能 0 改動）
  => 4 sub-agent 並行（不同檔；T2 是 verify-only 可能歸 E2）

Wave 2（並行 3 task，1d）：T5 / T7 / T8
  T5: evidence_filter capability probe test
  T7: FK chain audit
  T8: lookup_replay_config_blob reuse audit

Wave 3（序列 1 task，1.5d）：T6 E2E integration test

Wave 4（序列 1 task，1d）：T9 E2 review + E4 regression
```

**總 wall**：1d (advisory) + 1.5d (W1) + 1d (W2) + 1.5d (W3) + 1d (W4) = **6d wall**

**並行 sub-agent 派發**：

```
Sprint C2 dispatch wave:

  pre-DAG advisory wave (1d):
    AI-E: dream/opportunity/linucb 從 replay artifact 取 candidate 流程 spec (1h)

  Wave 1 (1.5d wall):
    E1-A: R7-T1 (dream_engine.persist_replay_candidate_recommendations)
    E1-B: R7-T3 (opportunity_tracker.persist_replay_outcome)
    E2:   R7-T2 (dream_engine.generate_replay_candidates 接線驗證)
    E2:   R7-T4 (linucb caller grep 並裁定)
    => 2 E1 + 2 E2 並行（4 並行）

  Wave 2 (1d):
    E1-A: R7-T5 (evidence_filter capability probe test)
    E1-B: R7-T7 (FK chain audit)
    E1-C: R7-T8 (lookup_replay_config_blob reuse audit)
    => 3 sub-agent 並行（不同 test 檔；isolation: worktree if 同 test dir）

  Wave 3 (1.5d):
    E1-A: R7-T6 (E2E integration test)

  Wave 4 (1d):
    E2 review pass
    E4 regression PASS
```

### §4.3 R7 PM Override 路徑（若 Sprint C 不拆，R6+R7 同 sprint）

| 額外任務 | 工時 |
|---|---|
| R6 + R7 全 16 task 串接 | 12.5d wall（單 sprint 上限破） |
| advisory wave 跨 sprint serialize | +1d 排程 buffer（QC + MIT 出 R6 spec → AI-E 才能起 R7 spec） |
| QC + MIT review buffer 共享 | +0.5d 排程衝突 |

**單 sprint 總 wall**：14d — **嚴重超出 7d sprint 上限**。Blocker chain 風險倍增。

---

## §5. R6 + R7 Acceptance Contract（對應 Plan §7 + §6.R6/R7）

### §5.1 A6 Acceptance — Fee-aware PnL（plan §7）

| # | Acceptance | 真實 evidence | SQL 可跑驗證 |
|---|---|---|---|
| A6-1 | Fee model is never omitted from PnL | simulated_fills.fee > 0 ∧ fee_rate > 0 | `SELECT COUNT(*) FROM replay.simulated_fills WHERE fee = 0 AND evidence_source_tier='calibrated_replay'` 必為 0 |
| A6-2 | Calibration report includes sample count, freshness, and confidence | replay.experiments.execution_confidence ≠ NULL ∧ payload.calibration ⊃ {sample_count, last_fill_age_ms, ci_bps_p95} | `SELECT COUNT(*) FROM replay.experiments WHERE execution_confidence IS NOT NULL` 等於總 calibrated experiment 數 |
| A6-3 | Maker/taker liquidity_role mapped from PostOnly TIF | simulated_fills.liquidity_role ∈ {'maker', 'taker'} | `SELECT liquidity_role, COUNT(*) FROM replay.simulated_fills GROUP BY 1` 兩值都 > 0 |
| A6-4 | execution_model_version 不為 'synthetic_v1' | simulated_fills.execution_model_version = 'calibrated_v1'（或 R6 定的真模型 ID） | `SELECT execution_model_version, COUNT(*) FROM replay.simulated_fills WHERE evidence_source_tier='calibrated_replay'` 0 'synthetic_v1' row |
| A6-5 | ci_low_bps ≤ ci_mid_bps ≤ ci_high_bps（V050 CHECK） | 三 column 全非 NULL（R6 lifted from Sprint A NULL） | `SELECT COUNT(*) FROM replay.simulated_fills WHERE ci_low_bps IS NULL AND evidence_source_tier='calibrated_replay'` 必為 0 |

### §5.2 A7 Acceptance — Confidence Honesty（plan §7）

| # | Acceptance | 真實 evidence | SQL 可跑驗證 |
|---|---|---|---|
| A7-1 | Weak calibration sample auto-downgrades label | sample_count < threshold ⇒ execution_confidence='none' | smoke test：跑 funding_arb (99 fills) → assert execution_confidence='none' |
| A7-2 | Sufficient sample + freshness + CI bound ⇒ 'limited' or 'calibrated' | grid_trading + ma_crossover sample > threshold ⇒ 'limited' or 'calibrated' | smoke test：跑 grid_trading replay → assert execution_confidence ∈ ('limited', 'calibrated') |
| A7-3 | Stale calibration auto-downgrades | last_fill > 14d ago ⇒ 'none' | smoke test：fixture 用 30d-old data → assert 'none' |
| A7-4 | UI labels match label producer | tab-paper.html replay subtab 顯示與 SQL execution_confidence column 一致 | playwright e2e：assert DOM execution_confidence badge value |

### §5.3 A10 Acceptance — MLDE/Dream Advisory Boundary（plan §7）

| # | Acceptance | 真實 evidence | SQL 可跑驗證 |
|---|---|---|---|
| A10-1 | Advisory only / verified insert only — no replay-derived row without replay_experiment_id + manifest_hash 進 applier | mlde_shadow_recommendations.evidence_source_tier IN ('calibrated_replay', 'synthetic_replay', 'counterfactual_replay') ⇒ replay_experiment_id NOT NULL ∧ manifest_hash NOT NULL | V051 paired CHECK 已 enforce；`SELECT COUNT(*) FROM learning.mlde_shadow_recommendations WHERE evidence_source_tier!='real_outcome' AND (replay_experiment_id IS NULL OR manifest_hash IS NULL)` 必為 0 |
| A10-2 | dream_engine 寫 calibrated_replay row 時帶真 expires_at | replay-derived row.expires_at > now() | `SELECT COUNT(*) FROM learning.mlde_shadow_recommendations WHERE evidence_source_tier!='real_outcome' AND (expires_at IS NULL OR expires_at <= now())` 必為 0（V036 verify_replay 已 enforce） |
| A10-3 | mlde_demo_applier_evidence_filter Block B 真行 — 期望 row promoted from MLDE shadow to applier 必經 Block B path | capability probe + SQL trace | integration test：register replay → run → dream_engine consume → mlde_demo_applier 讀 → log 顯示 'block_b_promoted' |
| A10-4 | replay-derived row 從未 bypass verify gate | grep `INSERT INTO learning.mlde_shadow_recommendations` 0 hit on direct INSERT path（V037 PUBLIC INSERT REVOKE）| `cd program_code && grep -rn "INSERT INTO learning.mlde_shadow_recommendations\|INSERT.*mlde_shadow_recommendations" --include="*.py"` 0 hit |

### §5.4 跨 R6+R7 acceptance：A6 → A7 → A10 chain

```
R6-T4 CalibrationLabelProducer → execution_confidence ∈ {none, limited, calibrated}
  ↓
R7 producer 寫 mlde_shadow_recommendations 時帶 evidence_source_tier
  if execution_confidence='calibrated' → tier='calibrated_replay'
  if execution_confidence='limited' → tier='calibrated_replay' (degraded)
                                     OR 'synthetic_replay' (per QC advisor)
  if execution_confidence='none' → 不寫 advisory（discarded by replay_evidence guard）
  ↓
mlde_demo_applier_evidence_filter Block B SQL
  WHERE replay_experiment_id NOT NULL
    AND manifest_hash NOT NULL
    AND expires_at > now()
    AND status IN (...)
```

---

## §6. Risk Register

### §6.1 LG-3 RFC 0% IMPL 對 R6 阻塞風險

**評估**：**不阻塞**。LG-3 真實 fee runtime 已 100% land（§1A 列舉 12 個元件 ✅）；RFC 0% 指 binding contract / staleness HC / startup assertion 三件治理事 — 三件中 R6-T7 順手做 healthcheck（T2），剩 T1（contract test）+ T3（startup assertion）延 Sprint D LG-4 supervised live IMPL 前。**沒有 R6 必要 IMPL 被 LG-3 RFC 卡住**。

**Mitigation**：R6-T7 把 LG-3 RFC closure 從 0% → 70%（順帶清債）。

### §6.2 P1-DATA-1 LG5-W3-FUP-2 sibling CC 對 R7 阻塞風險

**評估**：**不阻塞，但需 align**。詳見 §0.6。

**Mitigation**：R7 dispatch 前 PA 必 `git fetch && git branch -r | grep "fup-2"` 看 sibling CC 是否 land；若 in flight 且 R7-T5 動 mlde_demo_applier_evidence_filter，PA push back（R7-T5 改交 sibling CC 完工後再做）。

### §6.3 Sprint A 8-commit chain 6-layer blocker 教訓對 Sprint C 預期 blocker 數量

**評估**：**Sprint C 預期 4-6 commit chain**。理由：
- R6 主要 IMPL 是「mirror live 端 fee runtime 到 replay 端 + 加 calibration」，不是新建 — blocker 風險中
- R7 主要 IMPL 是「升級 4 producer 已有 verify_replay_evidence call」，不是新建 verify gate — blocker 風險低
- 但 Wave 順序敏感（R6 calibration label deliver 才能起 R7 advisory），blocker 可能在 wave 邊界出現
- 預期：R6 = 3-4 commit；R7 = 2-3 commit。**單 Sprint 涵蓋兩者 = 5-7 commit chain**。

**Mitigation**：拆 C1 + C2 分開兩個 sprint（PA §0.1 已強推）。

### §6.4 LOC §九 1500 cap 風險

**評估**：**單 task 不破，但整體燒 margin**。

| 檔案 | pre-Sprint C | post-Sprint C est | 警告/硬上限 |
|---|---:|---:|---|
| `replay_routes.py` | 1146 | 1146 | 0 改動 |
| `experiment_registry.py` | 1278 | 1318 (+R6-T6 +40) | warning(800) 已破，< 1500 |
| `simulated_fills_writer.py` | 893 | 953 (+R6-T5 +60) | warning(800) 已破，< 1500 |
| `dream_engine.py` | (TBD; 估 ~800-900) | +50-80 (R7-T1+T2) | warning(800) 邊緣，< 1500 |
| `opportunity_tracker.py` | (TBD; 估 ~400-500) | +50 (R7-T3) | warning(800) 內 |
| `runner.rs` (Rust) | 1466 | 1646 (+R6-T1+T2 +180) | **🛑 破 1500 硬上限** |
| `replay_runner.rs` (Rust bin) | 1427 | 1457 (+R6-T3 +30) | warning(800) 已破，< 1500 |
| `account_manager.rs` (Rust) | 903 | 943 (+R6-T7 順帶 +40) | warning(800) 已破，< 1500 |
| 新檔 `replay/calibration_label.rs` | 0 | ~120 | warning(800) 內 |

**結論**：**runner.rs 1466 + R6-T1+T2 ~180 LOC = 1646 破 §九 1500 硬上限**。**必須 R0-T0 拆檔**（與 Sprint B B1 模式一致）。

**R0-T0 拆檔策略（PA 強推 Sprint C 第一手）**：
- 把 `runner.rs` 內 `IsolatedPipeline::execute` (line ~677) 抽到 `replay/isolated_pipeline.rs`（新檔 ~400 LOC）
- 把 `apply_fill` (line 908-985) 抽到 `replay/apply_fill.rs`（新檔 ~250 LOC）
- runner.rs 1466 → ~750 LOC（warning(800) 內）
- R6-T1/T2 改在新 `apply_fill.rs` 內，0 §九 cap 風險

**LOC 影響**：runner.rs 1466 → 750；新增 isolated_pipeline.rs 400 + apply_fill.rs 250；總 +180 LOC（拆檔不增實際邏輯）。

### §6.5 V### migration 需求

**評估**：**0 新 migration 需求**。

| Migration | 用途 | 狀態 |
|---|---|---|
| V036 | verify_replay_evidence_and_insert | ✅ 既有 |
| V038-V040 | evidence_source_tier add/finalize | ✅ 既有 |
| V043 | mlde_replay_veto_log | ✅ 既有 |
| V044 | replay_handoff_idempotency_unique | ✅ 既有 |
| V049 | replay.experiments 22 col 含 execution_confidence | ✅ 既有 |
| V050 | replay.simulated_fills 17 col 含 ci_low/mid/high_bps + fee + fee_rate + liquidity_role + execution_model_version | ✅ 既有 |
| V051 | mlde_recommendations 雙路 CHECK | ✅ 既有 |

**結論**：**Sprint C 全憑既有 schema**。0 V### reservation 需求。

### §6.6 跨平台合規（CLAUDE.md §七）

| 項目 | R6 風險 | R7 風險 |
|---|---|---|
| 路徑硬編碼 | 0（所有 Rust IMPL 走 `OPENCLAW_BASE_DIR` / `OPENCLAW_DATA_DIR`；Python 同） | 0 |
| LocalLLMClient 抽象 | N/A（不涉 LLM） | N/A |
| systemd → launchd 遷移 | N/A | N/A |
| requirements.txt 同步 | 0（全用 stdlib + psycopg2 已 ship） | 0 |

**結論**：Mac 部署目標 0 影響。

---

## §7. Owner Chain & Dispatch Order

### §7.1 為何按此順序派 sub-agent

**Sprint C1 (R6) owner chain**：PM → QC → MIT → E1 → E2 → E4 → PM

| Stage | Owner | 任務 | 為何此順序 |
|---|---|---|---|
| 0a | PM | 拆 C1+C2 拍板 | PA push back §0.1 必先 closed |
| 0b | QC | confidence label 數學 spec（pre-DAG advisory） | E1 IMPL CalibrationLabelProducer 前必有數學 spec |
| 0c | MIT | mlde_demo_applier_evidence_filter capability 風險（pre-DAG advisory） | R7 dispatch 前必有 capability 評估，但 R6 也參考（R7 依賴 R6 deliver） |
| 1a | PA | 派 E1 4 sub-agent Wave 1（T1/T2/T3/T7） | 並行 Rust IMPL 4 並行 |
| 1b | E1 | Wave 1 IMPL | 0 業務邏輯衝突（不同檔/不同函數） |
| 2 | PA | 派 E1 Wave 2 (T3) → Wave 3 (T4) → Wave 4 (T5+T6) | 序列依賴 |
| 3 | E1 | Wave 5 (T8) calibration smoke + param delta replay | 整合驗證 |
| 4 | E2 | 代碼審查 — 重點 §7.4 三點 | E2 永不跳 |
| 5 | E4 | 全測試回歸 PASS | E4 永不跳 |
| 6 | PM | 簽收 R6 closure；触發 C2 dispatch | C1 closed 才啟 C2 |

**Sprint C2 (R7) owner chain**：PM → QC → MIT → AI-E → E1 → E2 → E4 → PM

| Stage | Owner | 任務 | 為何此順序 |
|---|---|---|---|
| 0 | PM | C1 closed sign-off → C2 啟 | C2 完全依賴 C1 deliver |
| 1 | AI-E | dream/opportunity/linucb replay artifact spec（pre-DAG advisory） | R7 IMPL 前必有 advisor spec |
| 2 | PA | 派 E1 4 sub-agent Wave 1（T1/T2/T3/T4） | 並行 Python IMPL 4 並行 |
| 3 | E1 | Wave 1 IMPL | 4 producer 同型模式並行 |
| 4 | PA | 派 E1 Wave 2 (T5/T7/T8) → Wave 3 (T6) | 序列依賴 |
| 5 | E1 | Wave 3 (T6) E2E integration test | A10 acceptance |
| 6 | E2 | 代碼審查 — 重點 §7.4 三點 | E2 永不跳 |
| 7 | E4 | 全測試回歸 PASS | E4 永不跳 |
| 8 | PM | 簽收 R7 closure；REF-20 Sprint C closed | Sprint D 啟 |

### §7.2 QC + MIT advisory 邊界（read-only 不寫業務）

**QC advisory deliverable（R6-T0 pre-DAG，1h）**：
- 文件：`docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-05--ref20_r6_calibration_label_spec.md`
- 內容：
  - 'limited' vs 'calibrated' 切點（sample count threshold ≥30/symbol/strategy/regime）
  - freshness threshold（last fill ≤ 7d for 'calibrated'，≤14d for 'limited'）
  - confidence interval bound（fee_bps σ < 5 bps for 'calibrated'）
  - regime detection（trending vs mean-reverting；optional）
- 邊界：純數學 spec，**0 code 改動**

**MIT advisory deliverable（R6-T0/R7-T0 pre-DAG，1h）**：
- 文件：`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-05--ref20_r6_r7_capability_risk.md`
- 內容：
  - capability probe 在 capability 部分缺 column 時 graceful fallback 行為驗
  - calibrated_replay tier 加入後 mlde_demo_applier_evidence_filter Block B 是否 cardinality 預估
  - V051 paired CHECK 對 4 producer 升級後的拒 row rate 預估
- 邊界：純 schema/risk assessment，**0 code 改動**

**AI-E advisory deliverable（R7-T0 pre-DAG，1h）**：
- 文件：`docs/CCAgentWorkSpace/AI-E/workspace/reports/2026-05-05--ref20_r7_advisory_chain_spec.md`
- 內容：
  - dream_engine.generate_replay_candidates 真實流程（誰呼叫、何時、用什麼 manifest 取 replay artifact）
  - opportunity_tracker.persist_replay_outcome 真實流程
  - LinUCB caller 是否需動（grep + 裁定）
  - 4 producer 統一接口設計（manifest_hash 從哪取、replay_experiment_id 從哪取、expires_at 從哪取）
- 邊界：純 advisory spec，**0 code 改動**

### §7.3 預估 dispatch 時點 + 並行可能性

| 時點 | 可派 | 平行度 |
|---|---|---|
| T+0 (PM 拍板 C1+C2 拆分) | QC + MIT 兩 advisor | 2 並行 |
| T+1d (advisor deliver 後) | E1 Wave 1 4 sub-agent (R6-T1/T2/T7) | 4 並行 |
| T+2.5d (W1 done) | E1 Wave 2 1 sub-agent (R6-T3) | 1 |
| T+3d (W2 done) | E1 Wave 3 1 sub-agent (R6-T4) | 1 |
| T+4d (W3 done) | E1 Wave 4 2 sub-agent (R6-T5/T6) | 2 |
| T+4.5d (W4 done) | E1 Wave 5 1 sub-agent (R6-T8) | 1 |
| T+5.5d (W5 done) | E2 review pass | 1 |
| T+6.5d (W6 done) | C1 closed → AI-E advisor dispatch | 1 (C2 開) |
| T+7.5d (advisor deliver) | E1 Wave 1 4 sub-agent (R7-T1/T2/T3/T4) | 4 並行 |
| T+9d (W1 done) | E1 Wave 2 3 sub-agent (R7-T5/T7/T8) | 3 並行 |
| T+10d (W2 done) | E1 Wave 3 1 sub-agent (R7-T6) | 1 |
| T+11.5d (W3 done) | E2 review pass | 1 |
| T+12.5d (W4 done) | C2 closed | (Sprint C closed) |

**Sprint C 總 wall**：12.5d（C1=6.5d + C2=6d）

**若 PM override 不拆，單 sprint**：14d（含跨 advisor 排程衝突 buffer），**嚴重超 7d**。

### §7.4 E2 重點審查 3 點（每 wave 必查）

#### Sprint C1 (R6) E2 必查 3 點

1. **`runner.rs` apply_fill fee/slippage 計算與 live `IntentProcessor::fee_rate_for_intent` + `slippage_rate_for_intent` byte-equal**
   - grep `let fee_rate = ` in `replay/apply_fill.rs` (新檔)；對比 `intent_processor/router.rs:488`
   - 必同源呼叫（reuse `AccountManager::get_fee_rate`，不重新算）
   - 跨 Rust live + Rust replay byte-equal test required

2. **CalibrationLabelProducer 不偷推 'calibrated'**
   - 只有 sample_count ≥ QC 給的 threshold ∧ freshness OK ∧ CI bound OK → 'calibrated'
   - 任何 short-circuit fallback（如預設 'limited'）= E2 拒收
   - smoke test 驗：funding_arb 99 fills → 必 'none'

3. **Sprint A QA round 6 lessons retained**
   - 任何新加 spawn / subprocess 路徑：stderr 不可 DEVNULL（必落 disk）
   - 任何新加 fail-closed assertion：必 raise + log，不 silent return
   - 任何 placeholder 字串：必 grep 0 hit before commit

#### Sprint C2 (R7) E2 必查 3 點

1. **4 producer 升級後 0 直 INSERT path**
   - grep `INSERT INTO learning.mlde_shadow_recommendations` 在 `dream_engine.py` + `opportunity_tracker.py` 必 0 hit（V037 PUBLIC INSERT REVOKE）
   - 唯一寫路徑必走 `verify_replay_evidence_and_insert`

2. **replay_experiment_id + manifest_hash 來源真確**
   - 不允許 hardcoded UUID / hardcoded hash
   - manifest_hash 必從 `lookup_replay_config_blob` 或同等 helper 取
   - replay_experiment_id 必從真 replay run 取

3. **handoff_routes.py 0 改動**
   - R7 不應動 handoff_routes（與 advisory 路徑解耦，§2E 已釐清）
   - grep diff 確認 0 hit on handoff_routes.py

### §7.5 派發前 sub-agent fetch 提醒（feedback_fetch_before_dispatch.md）

派發 R6-T1/T2 前必 `git fetch && git branch -r | grep -E "(replay|sprint_c|fee|calibration)"` 確認無 sibling CC 已開 feature branch。

派發 R7-T1/T3 前必 `git fetch && git branch -r | grep -E "(replay|sprint_c|advisory|fup-2)"` 確認無 sibling CC（特別 LG5-W3-FUP-2 in flight）。

---

## §8. PA Sign-off Readiness（report 用）

### §8.1 Hard boundary check（CLAUDE.md §四）

- ❌ 未觸 `live_execution_allowed`（R6 + R7 完全不接 IPC / order dispatch）
- ❌ 未觸 `max_retries=0`（不變）
- ❌ 未觸 `OPENCLAW_ALLOW_MAINNET`（replay binary 不接 mainnet）
- ❌ 未觸 `live_reserved`（不接 live mode）
- ❌ 未觸 `authorization.json`（不接 live_authorization）
- ❌ 未觸 `decision_lease`（ReplayProfile::Isolated.requires_lease=false 強制；R7 advisory 不取 lease）
- ✅ 0 violation

### §8.2 Root principle check（16 條 + DOC-08 §12 9 條）

| # | 原則 | 狀態 | 證據 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ 加強 | replay 物理上不寫 trading.* |
| 2 | 讀寫分離 | ✅ 加強 | replay 端 ReplayPaperState 只讀；MLDE/Dream advisory 經 V036 verify gate |
| 3 | AI 輸出 ≠ 命令 | ✅ 加強 | R7 advisory 寫 mlde_shadow_recommendations 必經 V036 verify gate；evidence_source_tier 強分類 |
| 4 | 策略不繞風控 | ✅ 加強 | R7 寫 calibrated_replay row 必有 expires_at TTL（V036 enforce） |
| 5 | 生存 > 利潤 | ✅ | R6 fee/slippage 模型逼真化反而觸發 cost_gate 更積極 reject 不利 entry |
| 6 | 失敗默認收縮 | ✅ | calibration weak → execution_confidence='none'，下游 advisor 無 row 可信 |
| 7 | 學習 ≠ 改寫 Live | ✅ | R7 advisory 只寫 learning.mlde_shadow_recommendations，0 trading.* 寫入 |
| 8 | 交易可解釋 | ✅ 加強 | replay_experiment_id + manifest_hash + expires_at 全 audit chain wire |
| 9 | 災難保護 | N/A | replay 不接 exchange |
| 10 | 認知誠實 | ✅ | execution_confidence label 嚴依數據量；不偷推 'calibrated' |
| 11 | Agent 最大自主 | ✅ | replay 是 advisory 不限制 agent，但 advisory 必經 verify gate |
| 12 | 持續進化 | ✅ 加強 | R7 啟用 calibrated_replay 後 MLDE 真有 replay-based candidate 來學 |
| 13 | AI 成本感知 | ✅ | R6 fee/slippage 真實化反映 cost_edge_ratio 真實值 |
| 14 | 零外部成本可運行 | ✅ | R6 fee 模型用 Bybit V5 free endpoint + AccountManager.refresh hourly task；R7 advisory 0 外部成本 |
| 15 | 多 Agent 協作 | ✅ | R7 dream/mlde/opportunity/linucb 4 producer 統一接口 |
| 16 | 組合級風險 | ✅ | R6 calibration 含 sample_count + freshness 逼近真實 portfolio risk |

**DOC-08 §12 安全不變量 9 條**：
1. ✅ Pre-trade audit/replay 必開 — R6 加強
2. ✅ Lease 必在執行前已 acquired — N/A（replay 不取 lease）
3. ✅ 執行回報必落 fills 表 — R6 simulated_fills 必含 fee + ci 三 cell
4. ✅ 風控降級 → engine 自動止血 — N/A（replay 不接 engine）
5. ✅ Authorization 過期/失效 → engine cancel_token shutdown — N/A
6. ✅ Mainnet 無 OPENCLAW_ALLOW_MAINNET → spawn 拒絕 — N/A
7. ✅ Bybit retCode != 0 → fail-closed 不重試 — R6 fee fetch error 已 fail-closed
8. ✅ Reconciler 對賬差異 → 自動降級 paper — N/A
9. ✅ Operator 角色與 live_reserved 缺一即拒 — N/A

### §8.3 評級

**A 級**：16/16 完全合規 + 硬邊界 0 觸碰。

---

## §9. PM Open Questions

### Q1: Sprint C 拆 C1+C2，還是堅持單一 sprint 涵蓋 R6+R7?

**PA 推薦**：**拆 C1（R6 grid + ma pilot）+ C2（R7 4 producer 升級）**。

**若 PM 拒拆**：必同步 accept R0-T0 拆檔作為 Sprint C 第一手 task；**且** Sprint C wall budget 至少 14d（嚴重超 7d 上限），blocker chain 風險倍增。

### Q2: R6 IMPL 在 Rust 還是 Python?

**PA 答**：**Rust 端做 calibration**（強推），**Python 端只 parse**。

理由：
- replay_runner 已是 Rust binary
- 既有 fee/slippage runtime 全 Rust（AccountManager / IntentProcessor）
- Python 只需在 simulated_fills_writer.py 解析 Rust JSON 多寫 4 column

### Q3: R6 pilot 是 grid + ma vs 5 strategy 全做?

**PA 答**：**pilot first**（grid + ma）。

理由：
- grid 樣本 1162 fills（充足 'calibrated'）；ma 635 fills（'limited'/'calibrated' 邊緣）
- funding_arb V2 棄策略路徑（commit `a19797d`）— 不涵蓋
- bb_breakout 14d 34 fills + bb_reversion 7 fills — 樣本嚴重不足，必為 'none'
- pilot 模式與 Sprint B2 R5 一致

### Q4: R6 是否同 sprint 加 LG-3 RFC T1 (contract test) + T3 (startup assertion)?

**PA 答**：**T1 NO（延 Sprint D）**，**T2（healthcheck）已含 R6-T7（順帶 unblock 70%）**，**T3 NO（屬 LG-4 supervised live IMPL 前提）**。

理由：
- T1 contract test 需 Rust + Python 雙語對齊；屬 LG-2 H0 blocking IMPL（CLAUDE.md §三 18-blocker #2）前提，非 R6 必要
- T2 healthcheck 是 R6-T7 自然順手做（LG-3 RFC closure 從 0% → 70%）
- T3 startup assertion 是 LG-4 supervised live IMPL 前提（CLAUDE.md §三 18-blocker #4），非 R6 scope

### Q5: R7 是否升級 mlde_demo_applier._insert_live_candidate 的 evidence_source_tier?

**PA 答**：**不升級**。

理由：mlde_demo_applier._insert_live_candidate (line 1260) 寫的是 LG-5 demo→live promotion candidate audit row，屬 legacy LG-5 audit 路徑，與 replay 無關。已正確標記 `evidence_source_tier='real_outcome'`。R7 改的是 dream_engine + opportunity_tracker + linucb 從 replay artifact 取 candidate 的路徑。

### Q6: R7 的 4 producer 是否全部要升級?

**PA 答**：**只升級 dream_engine + opportunity_tracker（必）**，**linucb 待 grep 後決定**，**mlde_demo_applier._insert_live_candidate 不升級**。

理由：
- dream_engine.persist_replay_candidate_recommendations + generate_replay_candidates → 必升（Wave 6 R20-P4-Q4 surface 設計就是給 R7 用）
- opportunity_tracker.persist_replay_outcome → 必升
- linucb → 看 grep 結果（記憶體：LinUCB shadow compare 4-06 deferred）；若 0 caller 則 R7 不必動，加 `# R7-T4 verified: linucb 0 replay caller, no upgrade needed` 注釋即可
- mlde_demo_applier._insert_live_candidate → §0.6 解釋

### Q7: R6 + R7 中是否需要新加 V### migration?

**PA 答**：**0 V### 需求**。詳見 §6.5。

### Q8: R6 + R7 之間是否需要中介 sprint?

**PA 答**：**不需要**。R6 closed sign-off + AI-E advisor deliverable + dispatch R7 三步緊接，0 中介需求。

### Q9: R6 是否同時做 advisory tier 的 'synthetic_replay' 升級（即 Sprint A baseline simulation 是否需 hardware-tier 升級）?

**PA 答**：**不做**。

理由：
- Sprint A baseline 已正確標記 'synthetic_replay'（V050 schema enforce）
- 'synthetic_replay' tier 設計就是「不可作 ML training data」（CLAUDE.md §九 既登記）
- R6 只升級 'calibrated_replay' 路徑，不動 'synthetic_replay'
- 'counterfactual_replay' tier 屬 Sprint D R9 reality-calibrated final sign-off scope，不在 Sprint C

### Q10: R6 calibration weak 時 dream/opportunity 是否還寫 advisor row?

**PA 答**：**不寫**（V036 verify gate 已 enforce — execution_confidence='none' → 不應產生 calibrated_replay row）。

但**留 escape hatch**：QC + MIT 可在 Sprint D R9 sign-off 階段定義「'limited' confidence advisor row 是否值得 promote」的閾值。R6 + R7 階段嚴格走「'calibrated' → calibrated_replay；'limited' → 不寫 OR synthetic_replay（per QC advisor)」路徑。

---

## §10. 結論 + Operator decision needed

### Sprint C 推薦切分

```
Sprint C1（6.5d wall）：R6 Fee/Execution Calibration
  - QC + MIT pre-DAG advisory (1d)
  - R0-T0 runner.rs 拆 isolated_pipeline.rs + apply_fill.rs (LOC 預算釋放)
  - R6-T1: Rust apply_fill fee model
  - R6-T2: Rust apply_fill slippage model
  - R6-T3: Rust replay_runner KellyConfig wire
  - R6-T4: Rust CalibrationLabelProducer 新模組
  - R6-T5: Python simulated_fills_writer.py payload extension
  - R6-T6: Python experiment_registry.py execution_confidence write
  - R6-T7: LG-3 healthcheck 順帶 unblock (RFC closure 70%)
  - R6-T8: Calibration smoke + parameter delta replay
  - R6-T9: E2 review + E4 regression

Sprint C2（6d wall）：R7 MLDE/Dream Advisory Integration
  - AI-E pre-DAG advisory (1d)
  - R7-T1: dream_engine.persist_replay_candidate_recommendations 升級
  - R7-T2: dream_engine.generate_replay_candidates 接線驗證
  - R7-T3: opportunity_tracker.persist_replay_outcome 升級
  - R7-T4: linucb caller grep + 裁定（可能 0 改動）
  - R7-T5: mlde_demo_applier_evidence_filter capability test
  - R7-T6: E2E integration test (A10 acceptance)
  - R7-T7: replay_experiment_id + manifest_hash FK chain audit
  - R7-T8: lookup_replay_config_blob reuse audit
  - R7-T9: E2 review + E4 regression
```

### PM Decision Required

1. ✅ Accept C1+C2 切分（PA 強推）
2. ⚠️ Reject 切分，single Sprint C 涵蓋 R6+R7（接 §4.3 PM override 路徑成本，14d 嚴重超 7d sprint 上限）
3. 其他切分提案

**PA 建議**：選 (1)。

### 派發前 sub-agent fetch 提醒（feedback_fetch_before_dispatch.md）

派發 R6 W1 前 `git fetch && git branch -r | grep -E "(replay|sprint_c|fee|calibration)"` 確認 0 sibling 衝突。

派發 R7 W1 前 `git fetch && git branch -r | grep -E "(replay|sprint_c|advisory|fup-2)"` 確認 0 sibling 衝突（特別 LG5-W3-FUP-2 in flight）。

---

## §11. Appendix — File Inventory Quick Ref

### R6 改動檔案

**Rust 端**：
- `rust/openclaw_engine/src/replay/runner.rs`（拆檔；R0-T0 -700 LOC）
- `rust/openclaw_engine/src/replay/isolated_pipeline.rs`（新檔，~400 LOC，R0-T0 切出）
- `rust/openclaw_engine/src/replay/apply_fill.rs`（新檔，~250 + R6-T1+T2 IMPL ~140 LOC = ~390 LOC）
- `rust/openclaw_engine/src/replay/calibration_label.rs`（新檔，~120 LOC，R6-T4）
- `rust/openclaw_engine/src/bin/replay_runner.rs`（+30 LOC，R6-T3 KellyConfig wire）
- `rust/openclaw_engine/src/replay/mod.rs`（+ pub mod 兩條，~5 LOC）

**Python 端**：
- `program_code/exchange_connectors/bybit_connector/control_api_v1/replay/simulated_fills_writer.py`（+60 LOC，R6-T5）
- `program_code/exchange_connectors/bybit_connector/control_api_v1/replay/experiment_registry.py`（+40 LOC，R6-T6）

**Healthcheck**：
- `helper_scripts/db/passive_wait_healthcheck.py` 或 `rust/openclaw_engine/src/account_manager.rs`（+40 LOC，R6-T7）

**Test**：
- `tests/replay/test_fee_calibration.py`（新，~200 LOC，R6-T8）
- `tests/replay/test_calibration_label_producer.py`（新，~100 LOC）
- `tests/replay/test_apply_fill_xlang.py`（新，~80 LOC，跨 Rust live + Rust replay byte-equal）

### R7 改動檔案

**Python 端**：
- `program_code/local_model_tools/dream_engine.py`（+50-80 LOC，R7-T1+T2）
- `program_code/local_model_tools/opportunity_tracker.py`（+50 LOC，R7-T3）
- 可能 `program_code/local_model_tools/linucb*.py` 或 `program_code/ml_training/linucb*.py`（待 R7-T4 grep 確認）

**Test**：
- `tests/ml_training/test_evidence_filter_capability.py`（新，~100 LOC，R7-T5）
- `tests/replay/test_advisory_lineage_fk.py`（新，~100 LOC，R7-T7）
- `tests/replay/test_mlde_dream_advisory_integration.py`（新，~250 LOC，R7-T6）

### Reference docs

- Plan V1 SoT: `docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md`
- Plan V3 (legacy schema): `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md`
- Sprint A R3 round 6 PA design: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-05--ref20_sprint_a_r3_round6_task_dag.md`
- Sprint B PA design: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-05--ref20_sprint_b_task_dag.md`
- LG-3 RFC: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-01--lg3_provider_pricing_binding_rfc.md`
- AMD-2026-05-02-01 Decision Lease retrofit path A: `docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md`
- AMD-2026-05-03-01 Wave 7 amendment: `docs/governance_dev/amendments/2026-05-03--ref20_wave7_p5_impl_accept_deploy_blocked.md`
- Bybit V5 fee endpoint dictionary: `docs/references/2026-04-04--bybit_api_reference.md` line 655-662

### Existing Schema (0 V### 需求)

- V036 `verify_replay_evidence_and_insert` (4 producer allowlist + tier compound CHECK + TTL)
- V037 PUBLIC INSERT REVOKE
- V038-V040 evidence_source_tier add/finalize
- V043 `replay.mlde_replay_veto_log` (12 col)
- V044 `replay.handoff_requests` (12 col, V035 event_type CHECK enum 'replay_handoff_request')
- V049 `replay.experiments` 22 col 含 `execution_confidence` CHECK enum (none/limited/calibrated)
- V050 `replay.simulated_fills` 17 col 含 `ci_low_bps`/`ci_mid_bps`/`ci_high_bps`/`fee`/`fee_rate`/`liquidity_role` (maker/taker/unknown CHECK)/`execution_model_version`
- V051 `mlde_recommendations_replay_columns` paired CHECK + FK V049 ON DELETE NO ACTION
- V054 `lease_transitions_audit_writer` (含 `replay_handoff_request` event_type)

---

## §13. PM-Appended Post-Advisory Updates (2026-05-05, after QC + MIT)

**Trigger**: QC + MIT pre-DAG advisor 完成（QC `2026-05-05--ref20_r6_calibration_label_spec.md` + MIT `2026-05-05--ref20_r6_r7_capability_risk.md`）。Operator 拍板 D1=V055 accept / D2=7d TTL / D3=PM 自接補 task DAG（不重派 PA）。

### §13.1 NEW R6-T0' V055 retrofit (P0 BLOCKER fix from MIT §3.5 / §8.2)

**Source**: PM 自驗 `srv/sql/migrations/V036__replay_evidence_source_guard.sql:208-242` 確認 V036 INSERT 漏寫 4 metadata column（`evidence_source_tier` / `replay_experiment_id` / `manifest_hash` / `expires_at`）。V036 docstring line 200-207 自承「PR1 函數先 land、PR3 補 function body」— PR3 從未發生。

**Silent corruption scenario**（必修不修則 R7 acceptance 假綠）：
1. R7 producer 傳 calibrated_replay tier + replay_experiment_id + manifest_hash + expires_at
2. V036 verify portion (line 137-191) PASS（caller args OK）
3. V036 INSERT (line 208-242) 漏寫 4 column → row 走 V038-V040 default = `real_outcome` / NULL / NULL / NULL
4. V051 paired CHECK PASS（real_outcome 路徑自動 valid）
5. Row 看似 inserted 成功，但 tier 是 `real_outcome` 而非 `calibrated_replay`
6. mlde_demo_applier Block B 永不會 promote 此 row → A10-1/2/3 假綠

**新 task: R6-T0' V055 retrofit**（在 W1 前完成）：

| field | 值 |
|---|---|
| File | `srv/sql/migrations/V055__verify_replay_evidence_function_full_insert.sql` |
| Type | `CREATE OR REPLACE FUNCTION learning.verify_replay_evidence_and_insert` |
| Signature | unchanged 19-arg (V036 一致) |
| INSERT | +4 column (`evidence_source_tier`, `replay_experiment_id`, `manifest_hash`, `expires_at`) |
| Guard A | function existence + arg signature (19-arg) unchanged + post-INSERT smoke：synthetic call → row body tier matches caller arg |
| Idempotency | `CREATE OR REPLACE` → re-run 0 RAISE |
| LOC est | ~80 LOC SQL（含 Guard + bilingual MODULE_NOTE per §七）|
| Python sibling test | `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_v055_evidence_insert_fix.py` 4 case：real_outcome / calibrated_replay / synthetic_replay / counterfactual_replay 路徑各驗 row body tier match caller arg |
| Owner chain | E1 → E2 → E4 → Linux apply via SSH bridge → C1 W1 dispatch unblock |
| Wall | ~0.5d |

**REF-20_RESERVATION ledger update**：V055 row 加入 reservation table。

### §13.2 7d expires_at TTL 決策 (operator D2)

**Decision**: R7 4 producer 升級時 caller 端傳 `expires_at = now() + INTERVAL '7 days'`，**不採 V036 docstring default 30d**。

**理由**（QC + MIT 一致）：
- QC §4.3：`label='calibrated' → TTL 7d`、`label='limited' → TTL 3d`（信心衰減 enforce）
- MIT §6.2：crypto market regime 切換 7-14d 內，30d advisory 失效但 still in TTL → live trading 可能用 stale fee model
- 工程實作：caller 端傳 TTL，0 V055 / V036 schema 改動需要

**對應 R7 IMPL**：
- `dream_engine.persist_dream_insights` 升級時 caller 計算 `expires_at = R6_label_to_ttl(execution_confidence) + now()`
- `opportunity_tracker.persist_regret_summary` 同上
- 全用 QC §4.3 `label_to_ttl` map：calibrated→7d / limited→3d / none→never_inserted

### §13.3 PA Report 修正（doc hygiene）

**§0.6 修正**：`P1-DATA-1 LG5-W3-FUP-2 attribution_chain_ok writer fix sibling CC` 已 land 於 commit `34211ab4`（2026-05-02 E2 round 1 PASS to E4）— **不在 flight**，R7 dispatch 0 wait constraint。CLAUDE.md §三 18-blocker #11 已同步 update（同 commit）。

**§2C 補正**：capability probe 真實 6 個 key（不是 3 個）：
1. `has_evidence_source_tier`（top-level fail-soft 條件）
2. `has_replay_experiment_id`
3. `has_manifest_hash`
4. `has_replay_experiments`（table existence via to_regclass）
5. `replay_experiments_has_expires_at`
6. `replay_experiments_has_status`

實際 4-level gate（不是「3 capability 全 true 走 Block B」這麼簡單）：
- Top-level fail-soft（`has_evidence_source_tier=False`）→ legacy schema 0 filter
- Block A only（`has_evidence_source_tier=True`）→ tier allowlist filter
- Block B partial（`has_replay_experiment_id=True` + `has_replay_experiments=True` 但 expires_at/status 缺）→ FK existence-only gate
- Block B 完整版（4 capability 全 true）→ FK + manifest_hash + expires_at + status NOT IN cancelled/expired/compromised

**真實 runtime 狀態 HEAD `e5b5227c`**：V040 + V049 + V051 全 land → 6/6 capability 全 true → Block B 完整版啟用。0 fail-soft 路徑被觸發。

### §13.4 R7-T7 NEW: capability log observability（MIT §1.5 推薦）

**新 task**：`fetch_pending_sql_and_params` end 加 1-line INFO log dump active capabilities + Block B mode（full / partial / skip / fail-soft）。

**理由**：
- MLDE consumer-side 即時可見 mode flow
- 順帶 R7-T7 加進 LG-3 healthcheck `pricing_binding` output（`mode=demo block_a=on block_b=full|partial|skip caps=N/M ...`）

**LOC est**: ~10-15 LOC Python；不另增 task 編號，併入 R7-T7 既有 logging scope。

### §13.5 修訂 Sprint C 路線圖

| 階段 | scope | wall | dispatch order |
|---|---|---:|---|
| **R6-T0'**（NEW）| V055 retrofit + Python sibling test | 0.5d | E1 立即派 → E2 → E4 → Linux apply |
| C1 W1 | R6-T1 fee model + R6-T2 slippage + R6-T7 LG-3 healthcheck（並行 3 sub-agent + R0-T0 拆檔）| 1.5d | V055 closed 後 |
| C1 W2-W6 | R6-T3 KellyConfig → T4 CalibrationLabelProducer → T5/T6 writer → T8 smoke → T9 review | 4.5d | sequential |
| C1 sign-off | E2 + E4 + PM | 0.5d | — |
| **C1 total** | | **~7d** | — |
| C2 advisory | AI-E spec 1d | 1d | C1 closed 後 |
| C2 W1-W4 | R7 4 producer 升級 + capability test + FK audit + E2E + review | 5d | sequential |
| **C2 total** | | **~6d** | — |
| **Sprint C total** | | **~13d** | — |

### §13.6 後續 hygiene action

| Action | Owner | When |
|---|---|---|
| Sprint D R8 retention policy on `mlde_shadow_recommendations`（30-60d）| E1 | C2 closed 後 |
| MIT advisory R8 加 partial index `WHERE evidence_source_tier IN replay_tier_set AND expires_at > now() - 7d`（optional）| E5 | Sprint D 維護週期 |

---

**END OF REPORT**

PA DESIGN DONE: report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-05--ref20_sprint_c_task_dag.md
PM POST-ADVISORY UPDATES: §13 appended 2026-05-05 (V055 R6-T0' + 7d TTL + §0.6/§2C corrections + R7-T7 observability)
