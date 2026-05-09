# PA Full Dispatch Engineering Plan — Post 4-Agent Loss Audit

**作者**：PA（Project Architect）
**日期**：2026-05-09
**性質**：Operator 拍板 dispatch list 後的 sprint-by-sprint engineering plan + sign-off pre-flight checklist
**輸入文件**：
- `2026-05-09--full_loss_architectural_root_cause_redesign.md`（PA 5 root cause + R-1..R-5）
- `2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md`（W-AUDIT-8a 4 phase × ~40 person-day）
- `2026-05-09--AMD-2026-05-09-03-graduated-canary-default.md`（W-AUDIT-9 1.5-2 sprint × 7 sub-task）
- `2026-05-09--full_audit_pa_fix_plan_v2.md`（self-adversarial 6 push back）
- QC v3 strategy verification（5 既存策略 verdict）
- CLAUDE.md §三 W-AUDIT-1 sync `b91487f2`
**讀者**：Operator（首讀 sign-off）/ PM（Sign-off 後派發）/ E1×N（IMPL）/ E2 / E4 / MIT / QC / BB / CC
**前置**：A2-followup G3-08 `OPENCLAW_H_STATE_GATEWAY=1` ops 並行執行（標 done in §1 Sprint N+0）

---

## §0 Executive Summary（給 PM/Operator，250 字）

Operator 拍板的 dispatch list 拆 5 群（A 新策略 / B ML 三斷層 / C Promotion + Dormant / D Architectural Wave / E G3-08 enable）合計 **~140 person-day across 6 sprint (Sprint N+0 → N+5)**，最大 E1 capacity 5 並行。critical path 是 **W-AUDIT-9 graduated canary IMPL** + **W-AUDIT-8a Phase A trait migration** 兩條串行依賴，控 Sprint N+1 milestone（first alpha source 跑通 7d evidence）。**Sprint N+0 滿載**（W-AUDIT-9 + 8a Phase A + B 群 ML 三斷層 + C 群 A6+D-05-wire + W-AUDIT-6 mid-ground 6 子項並行）— E1 capacity 5/5 hot；Sprint N+1 鬆（8a Phase B+C 並行 + A4-C IMPL 啟動）；Sprint N+5 收斂 first per-alpha-source supervised live。**最大跨 wave 衝突**：W-AUDIT-8a Phase A migration 與 W-AUDIT-6 mid-ground 5 個策略改動同 file overlap（`bb_breakout/mod.rs`, `ma_crossover/strategy_impl.rs`, `bb_reversion/mod.rs`）— 必序列化（先 6 mid-ground 再 8a Phase A）避免 merge conflict。**Sign-off 前 11 invariant** 列 §6 給 PM 跑。

---

## §1 Sprint-by-Sprint Dispatch DAG（Sprint N+0 → N+5）

### 1.1 Sprint N+0（current → +2 weeks）— FOUNDATION HEAVY

**Sprint goal**：W-AUDIT-9 graduated canary foundation IMPL（解 P0-EDGE-1 雞蛋死循環）+ W-AUDIT-8a Phase A trait migration spec→IMPL handoff + B 群 ML 三斷層 IMPL + C 群 A6 promotion evidence + W-AUDIT-6 mid-ground 6 子項並行 + A2-followup G3-08 enable（ops 並行）

**E1 capacity 用量：5/5（HOT 滿載）**

| Wave | Sub-task | E1 slot | Owner | Person-day | Critical path? | Dependencies |
|---|---|---|---|---:|:---:|---|
| W-AUDIT-9 | T1 Rust schema 升級（`config/risk.rs`） | E1-A | E1 | 2 | ✅ | 無 |
| W-AUDIT-9 | T2 V### migration + Linux PG dry-run | E1-B | E1 | 2 | ✅ | 無（與 T1 並行）|
| W-AUDIT-8a Phase A | trait 升級 + 5 策略 declare + AlphaSurface struct | E1-C | E1 | 5 | ✅（後續所有 alpha wave 前置）| W-AUDIT-6 mid-ground 5 策略改動序列化先做 |
| B-M1 | decision_features producer 改 intent-only emit + evaluation 拆表 V0XX migration | E1-D | E1 + MIT review V### | 5 | ⚠️（並行 critical path）| 無 |
| W-AUDIT-6 mid-ground | 6 子項 batch（ma_crossover 重寫 / bb_breakout 5m sweep / bb_reversion 配 ma pair / Kelly tier config 化 / DSR/PBO wired confirmed / funding_arb retire confirmed）| E1-E | E1 + QC review math | 5 | ❌ | 無但與 8a Phase A 同 file overlap |
| C-A6 | DSR/PBO/CPCV evidence pipeline 自動化 + trial_sharpes 持久化（V079 已 land）| 借 E1-D 後段 | E1 | 2 | ❌ | B-M1 後段 |
| C-D-05-wire | `set_promotion_pipeline()` singleton init | 借 E1-E 後段 | E1 | 0.5 | ❌ | C-A6 |
| A2-followup | G3-08 OPENCLAW_H_STATE_GATEWAY=1 enable | ops 並行 | ops | 0.5 | ❌（並行 ops） | 無 |

**E2 / E4 review chain timing**：
- Sprint N+0 W1 結束：E2 first-pass review T1+T2+W-AUDIT-6 mid-ground (C 群)
- Sprint N+0 W2 中：E2 second-pass review T3+B-M1+C-A6
- Sprint N+0 W2 結束：E4 regression（W-AUDIT-9 5-stage transition + 8a Phase A E2E byte-diff + B-M1 schema test + C-A6 DSR/PBO query test）
- 全部 review 結束後 PM Sign-off Sprint N+0 milestone

**Sprint N+0 milestone**：
1. W-AUDIT-9 5-stage canary foundation runtime ready（healthcheck `[58]` PASS / `governance.canary_stage_log` 表 active / `shadow_mode_provider` stage-aware）
2. W-AUDIT-8a Phase A trait 升級 land（5 策略 declare + AlphaSurface struct + dispatch tracking metric）
3. B 群 ML 三斷層 IMPL：M1 (intent-only emit) + M2 (entry_context_id INSERT trigger) + M3 (negative label + class weight)
4. C-A6 promotion evidence 自動化（DSR/PBO 跑得起 + trial_sharpes 持久化）
5. W-AUDIT-6 mid-ground 6 子項 land（5 既存策略 minimum 改動 + Kelly tier config 化）
6. G3-08 OPENCLAW_H_STATE_GATEWAY=1 enable（ops 並行 done）

### 1.2 Sprint N+1（+2 → +4 weeks）— ALPHA SURFACE PANEL WIRING

**Sprint goal**：W-AUDIT-8a Phase B + C 並行（Tier 2 panel + Tier 3 microstructure）+ B-M2/M3 IMPL（lag from N+0 if 任 fail）+ A4-C BTC→Alt Lead-Lag spec phase 啟動 + W-AUDIT-9 Stage 1 cohort 開始 7d 觀察期

**E1 capacity 用量：4/5（一個 slot reserved for catch-up）**

| Wave | Sub-task | E1 slot | Owner | Person-day | Critical path? | Dependencies |
|---|---|---|---|---:|:---:|---|
| W-AUDIT-8a Phase B | funding_curve_collector + oi_delta_collector + V### migration + Rust IPC slot | E1-A | E1 + MIT review V### | 5 | ✅ | Phase A done |
| W-AUDIT-8a Phase C | liquidation_writer.py + allLiquidation WS handler revert + V### migration + LiquidationPulseProvider IPC | E1-B | E1 + BB review WS topic + MIT review V### | 5 | ✅ | Phase A done（與 Phase B 並行）|
| A4-C BTC→Alt Lead-Lag | spec phase（PA 撰 RFC + QC 數學審計 + MIT data feasibility）| E1-C | PA + QC + MIT | 3（spec only）| ⚠️ | W-AUDIT-8a Phase A done（需用 surface ref）|
| W-AUDIT-9 | T7 E4 regression 5-stage transition test | E1-D | E1 + E4 | 3 | ❌ | Sprint N+0 T1-T6 done |
| Catch-up reserved | （for B-M2/M3 / W-AUDIT-6 mid-ground 任 spillover） | E1-E | E1 | 5 | - | 無 |

**Sprint N+1 milestone**：
1. W-AUDIT-8a Phase B + C land：funding_curve / oi_delta_panel / liquidation_pulse 三 panel 真實 populate
2. A4-C Lead-Lag RFC sign-off（QC 通過 + MIT data feasibility 通過）
3. W-AUDIT-9 Stage 1 cohort active（operator 拍板 1 strategy × 1 symbol × paper × 7d 開始觀察）
4. healthcheck `[新-funding_curve_freshness]` + `[新-oi_delta_panel_freshness]` + `[新-liquidation_pulse_freshness]` 全 PASS

### 1.3 Sprint N+2（+4 → +6 weeks）— A4-C IMPL + A4-B SPEC + 8a Phase D INTEGRATION

**Sprint goal**：A4-C BTC→Alt Lead-Lag IMPL（第一個用 AlphaSurface 的真新策略）+ W-AUDIT-8a Phase D（5 策略 callsite 全用 surface + Tier 4 wire）+ A4-B Liquidation Cluster Reaction spec phase + W-AUDIT-9 Stage 2 cohort（demo）開始

**E1 capacity 用量：5/5（HOT）**

| Wave | Sub-task | E1 slot | Owner | Person-day | Critical path? | Dependencies |
|---|---|---|---|---:|:---:|---|
| A4-C IMPL | BTCUSDT 1m 急動 ≥1.5σ → 60s alt 同方向 entry IMPL（用 AlphaSurface CrossAsset tag）| E1-A | E1 + QC review | 7 | ✅ | A4-C RFC sign-off + Phase D done |
| W-AUDIT-8a Phase D | EventAlert wire from Scout + RegimeTag from existing ATR/Hurst/EwmaVol + 5 策略 callsite 全用 surface + 7d replay E2E | E1-B | E1 + CC review IPC schema | 5 | ✅ | Phase B + C done |
| A4-B Liquidation Cluster | spec phase（PA + QC + MIT）| E1-C | PA + QC + MIT | 3 | ⚠️ | Phase C done（liquidation_pulse populate）|
| W-AUDIT-9 Stage 2 | operator 拍板 demo cohort（1 strategy × 1 symbol × demo × 14d）| ops + E1 監控 | ops + E1 | 1 | ❌ | Stage 1 7d PASS |
| W-AUDIT-6 mid-ground spillover / W-AUDIT-2 / -5 | catch-up | E1-D + E1-E | E1 | 8 | ❌ | 無 |

**Sprint N+2 milestone**：
1. A4-C BTC→Alt Lead-Lag IMPL land + 7d demo evidence accumulation start
2. W-AUDIT-8a Phase D land：5 策略 100% via surface + 7d replay E2E byte-identical
3. A4-B RFC sign-off
4. W-AUDIT-9 Stage 2 cohort active
5. AlphaSurface API 文檔 + ADR 落地（W-AUDIT-8a 整 wave acceptance）

### 1.4 Sprint N+3（+6 → +8 weeks）— A4-B IMPL + R-2 SPEC + W-AUDIT-9 Stage 3

**Sprint goal**：A4-B Liquidation Cluster Reaction IMPL + R-2 W-AUDIT-8e Strategist Alpha Source Orchestrator spec phase + A4-A Funding Skew Directional spec phase + W-AUDIT-9 Stage 3 demo full universe 開始

| Wave | Sub-task | E1 slot | Owner | Person-day | Critical path? | Dependencies |
|---|---|---|---|---:|:---:|---|
| A4-B IMPL | Liquidation Cluster Reaction IMPL（用 AlphaSurface LiquidationCascade tag）| E1-A | E1 + QC review | 7 | ✅ | A4-B RFC sign-off |
| W-AUDIT-8e (R-2) spec | Strategist Alpha Source Orchestrator + AlphaSourceRegistry spec（不重定義 Strategist scope，而是 Analyst hypothesis dispatcher + Strategist propose 通道）| E1-B | PA + FA + QC | 5（spec only）| ⚠️ | Phase D done |
| A4-A Funding Skew Directional | spec phase（demo signal noise 高，3rd priority）| E1-C | PA + QC | 3 | ❌ | Phase D done + 8a Phase B funding_curve panel populate |
| W-AUDIT-9 Stage 3 | operator 拍板 demo full universe 5 strategies × 21d | ops + E1 監控 | ops + E1 | 1 | ❌ | Stage 2 14d PASS |
| Catch-up + W-AUDIT-2 / -5 | maintenance | E1-D + E1-E | E1 | 8 | ❌ | 無 |

**Sprint N+3 milestone**：
1. A4-B Liquidation Cluster IMPL land + demo evidence accumulation
2. R-2 W-AUDIT-8e RFC sign-off
3. A4-A RFC sign-off
4. W-AUDIT-9 Stage 3 demo full universe active

### 1.5 Sprint N+4（+8 → +10 weeks）— R-3 SPEC + A4-A IMPL + 8e IMPL

**Sprint goal**：R-3 W-AUDIT-8f Hypothesis Pipeline first-class object spec phase（**含 W-AUDIT-4 ML 基座併入**，Decision-3 confirmed）+ A4-A IMPL + W-AUDIT-8e IMPL

| Wave | Sub-task | E1 slot | Owner | Person-day | Critical path? | Dependencies |
|---|---|---|---|---:|:---:|---|
| W-AUDIT-8f (R-3) spec | Hypothesis Pipeline + W-AUDIT-4 ML 基座併入 spec + V### migration design | E1-A | PA + MIT + FA | 5（spec only）| ✅ | W-AUDIT-8e RFC sign-off |
| A4-A IMPL | Funding Skew Directional IMPL（用 AlphaSurface FundingSkew tag）| E1-B | E1 + QC review | 7 | ⚠️ | A4-A RFC sign-off + 8a Phase B funding_curve panel populate |
| W-AUDIT-8e IMPL | Analyst hypothesis dispatcher + Strategist propose 通道 + AlphaSourceRegistry IMPL | E1-C | E1 + FA review | 8 | ✅ | W-AUDIT-8e RFC sign-off |
| W-AUDIT-9 | Stage 3 觀察期維護 + auto-rollback metric monitoring | ops + E1 監控 | ops + E1 | 1 | ❌ | Stage 3 active |
| Catch-up | maintenance | E1-D + E1-E | E1 | 5 | ❌ | 無 |

**Sprint N+4 milestone**：
1. R-3 W-AUDIT-8f RFC sign-off（含 W-AUDIT-4 併入細節）
2. A4-A IMPL land + demo evidence
3. W-AUDIT-8e IMPL land
4. 三新策略（A4-A/B/C）全 demo evidence 累積中

### 1.6 Sprint N+5（+10 → +12 weeks）— R-3 IMPL + R-4 SPEC + FIRST PER-ALPHA-SOURCE SUPERVISED LIVE

**Sprint goal**：W-AUDIT-8f Hypothesis Pipeline IMPL + W-AUDIT-8g (R-4) Per-alpha-source Live Promotion Gate spec + first per-alpha-source supervised live promotion（first alpha source 拿到 budget slice）

| Wave | Sub-task | E1 slot | Owner | Person-day | Critical path? | Dependencies |
|---|---|---|---|---:|:---:|---|
| W-AUDIT-8f IMPL | Hypothesis state machine + Decision Lease originating_hypothesis_id 接線 + ExecutionPlan + fills propagate + attribution chain rewire base on hypothesis_id | E1-A + E1-B | E1 + MIT + FA | 12（並行） | ✅ | W-AUDIT-8f RFC sign-off |
| W-AUDIT-8g (R-4) spec | Per-alpha-source Live Promotion Gate + LiveBudget(alpha_source_id, slice) | E1-C | PA + FA + QC | 5（spec only）| ⚠️ | W-AUDIT-8f IMPL ≥ 50% |
| First per-alpha-source live | Stage 4 cohort 拍板（最 mature 的 alpha source 先進）+ supervised live monitoring | ops + E1 監控 | ops + E1 + operator | 3 | ✅ | Stage 3 21d PASS + W-AUDIT-9 Stage 3 healthy |
| W-AUDIT-10 (R-5) | Spec-as-Code + Module Lifecycle SM spec | 借 PA bandwidth | PA + TW | 3 | ❌ | 無 |

**Sprint N+5 milestone**：
1. W-AUDIT-8f Hypothesis Pipeline IMPL land
2. W-AUDIT-8g RFC sign-off
3. **First per-alpha-source supervised live promotion**（最早 supervised live 對應里程碑，非整 system live_reserved）
4. attribution_chain_ok ratio 從 0.5% → ≥ 70%（hypothesis_id 接線後 trivial）

### 1.7 Sprint DAG 全景圖

```
Sprint N+0:                              Sprint N+1:                           Sprint N+2:
┌───────────────┐                        ┌─────────────────┐                   ┌─────────────────┐
│ W-AUDIT-9 T1+T2│ ─┐                    │ W-AUDIT-8a Phase B│ ─┐                │ A4-C IMPL        │ ─┐
│ W-AUDIT-9 T3+T4│ ─┤                    │ W-AUDIT-8a Phase C│ ─┤                │ W-AUDIT-8a Phase D│ ─┤
│ W-AUDIT-9 T5+T6│ ─┤                    │ A4-C SPEC          │ ─┤                │ A4-B SPEC         │ ─┤
│ 8a Phase A     │ ─┤   ─→ Sprint N+0    │ W-AUDIT-9 T7       │ ─┤   ─→ N+1 done  │ W-AUDIT-9 Stage 2│ ─┤   ─→ N+2 done
│ B-M1 + B-M2 +M3│ ─┤      milestone     │ catch-up           │ ─┘                │ catch-up          │ ─┘
│ C-A6 + D-05    │ ─┤
│ W-AUDIT-6 mid-G│ ─┤
│ G3-08 enable   │ ─┘
└───────────────┘

Sprint N+3:                              Sprint N+4:                           Sprint N+5:
┌─────────────────┐                      ┌─────────────────┐                   ┌─────────────────┐
│ A4-B IMPL        │ ─┐                  │ R-3 8f SPEC      │ ─┐                │ 8f IMPL           │ ─┐
│ R-2 8e SPEC      │ ─┤                  │ A4-A IMPL         │ ─┤                │ R-4 8g SPEC       │ ─┤
│ A4-A SPEC        │ ─┤                  │ 8e IMPL           │ ─┤                │ FIRST per-alpha   │ ─┤   ─→ supervised
│ W-AUDIT-9 Stage 3│ ─┤   ─→ N+3 done   │ Stage 3 obs       │ ─┤   ─→ N+4 done  │ supervised live   │ ─┤      live milestone
│ catch-up         │ ─┘                  │ catch-up          │ ─┘                │ R-5 W-AUDIT-10    │ ─┘
└─────────────────┘                      └─────────────────┘                   └─────────────────┘
```

---

## §2 每 Wave 詳細 Sub-task

### 2.1 W-AUDIT-8a Alpha Surface Foundation（4 phase × ~10 person-day）

| Sub-task | Owner | Person-day | Files | Dependency | Acceptance | Failure fallback |
|---|---|---:|---|---|---|---|
| **Phase A — Foundation** | E1 主 IMPL | 10 | `rust/openclaw_engine/src/strategies/mod.rs` (trait 升級) + `tick_pipeline/mod.rs` (TickContext 加 surface ref) + 5 策略 mod 各加 `declared_alpha_sources()` + 新 `openclaw_core::alpha_surface` mod + Orchestrator dispatch tracking metric | 無前置 | 5 策略 byte-identical replay 1h paper session (E2E baseline binary diff PASS) | byte-diff 不為零 → rollback Phase A patch + PA 重設計 dispatch 邏輯 |
| **Phase B — Tier 2 Panel** | E1 collector + MIT V### review | 10 | V0XX `market.funding_rates_panel` + `market.oi_delta_panel` migration + `tools/alpha_surface/funding_curve_collector.py` + `tools/alpha_surface/oi_delta_collector.py` + Rust `tick_pipeline` `FundingCurveProvider` + `OIDeltaProvider` IPC slot | Phase A done | `funding_curve.is_some()` + `oi_delta_panel.is_some()` 24h ratio ≥ 90% / freshness < 5 min | retention 不夠 → 降 refresh 30s → 60s |
| **Phase C — Tier 3 Microstructure** | E1 + BB review WS topic + MIT V### review | 10 | V0XX `market.liquidations` migration + Rust `ws_client/parsers.rs` `allLiquidation` topic parser revert + `liquidation_writer.py` + Rust IPC slot `LiquidationPulseProvider` + `OrderflowFeatures` stub mock IMPL | Phase A done（與 Phase B 並行）| `allLiquidation` 24h 0 rate-limit + `liquidation_pulse.is_some()` ratio ≥ 70% | rate-limit → 降為 per-symbol 訂閱 |
| **Phase D — Tier 4 + Integration** | E1 + CC review IPC schema | 10 | Rust `EventAlertSlot` + Python `scout_agent` IPC slot writer + `RegimeClassifier` mod + 5 策略 callsite migration ctx.indicators → surface.indicators (純 mechanical) | Phase B + C done | `surface.regime != RegimeTag::Unknown` ratio ≥ 80% / 7d replay E2E byte-identical | Scout schema mismatch → Phase D EventAlert 改為 `&[]` empty slice 直到 Scout schema 對齊 |

**E1 派發**：Phase A 單 E1 串行（trait 升級不可並行）；Phase B + C 兩 E1 並行；Phase D 單 E1 串行（5 策略 callsite migration 不可並行避 merge conflict）。

**E2 重點審查 3 點**：
1. `declared_alpha_sources()` 5 策略全部非空 slice + slice 內 tag 與策略真實邏輯對齊（QC 必查）
2. AlphaSurface lifetime annotation `'a` 不洩漏 deep clone（borrow check 通過）
3. dispatch tracking metric `alpha_source_dispatched_total` 對 declared tag 全部 +1（或 unavailable +1），不漏 tag

### 2.2 W-AUDIT-9 Graduated Canary Foundation（1.5-2 sprint × 7 sub-task）

| Sub-task | Owner | Person-day | Files | Dependency | Acceptance | Failure fallback |
|---|---|---:|---|---|---|---|
| **T1 Rust schema 升級** | E1-A | 2 | `rust/openclaw_engine/src/config/risk.rs` 加 `ExecutorRiskConfig.canary_stage/canary_cohort/stage_entered_at_ms/observation_period_ms` + serde 上下游 | 無 | `cargo build --release` 綠 + serde round-trip test PASS | IPC schema break → dual-field（保 binary `shadow_mode` 並列 `canary_stage`）|
| **T2 V### migration** | E1-B | 2 | `sql/migrations/V080__governance_canary_stage.sql`（`canary_stage_log` + `canary_stage_metric_registry`）+ Linux PG dry-run | 無 | Linux PG idempotency × 2 PASS + Guard A/B/C NOTICE PASS | DB 性能 → metric SQL 改 6h 抽樣 |
| **T3 shadow_mode_provider stage-aware** | E1-C | 3 | `executor_config_cache.py` + `executor_agent.py` `_read_shadow_mode` 升級 stage-aware（cohort match + observation_period 計算 + auto-promote/rollback eval）| T1 done | unit test stage 0/1/2/3/4 transition PASS + cohort match PASS + exception path fail-closed Stage 0 PASS | exception path 任一漏判 → reject merge |
| **T4 healthcheck [58]** | E1-D | 2 | `helper_scripts/db/passive_wait_healthcheck/checks_governance.py` `check_58_graduated_canary_stage_invariant(cur)` + cron `0 */6 * * *` | T2 done | `[58]` PASS for active cohort / FAIL on rollback metric trip | metric SQL 撞 PG → `[58a]` 6h 抽樣 + `[58b]` daily full |
| **T5 GUI surface** | E1-E | 4 | OpenClaw Control Console settings/governance tab + IPC client + 「Graduated Canary Cohort Status」區塊 | T1 + T2 done | GUI read-only 顯示 cohort + stage + rollback metric live + 手動 promote 按鈕走 IPC | GUI 超期 → Stage 0/1 用 IPC CLI 觸發（不阻塞 Stage 1 entry）|
| **T6 manual promote Decision Lease** | E1-F | 1 | `governance_hub.py` `LeaseScope::CanaryStagePromotion` 新增 + Rust facade | T1 done | manual_promote with TTL 60s decision_lease_id PASS audit chain | lease scope kind 衝突 → 重命名 |
| **T7 E4 regression** | E1-G | 3 | `tests/test_graduated_canary_*.py` 5 stage transition + rollback + boundary test | 全部 done | 5 stage transition + auto-rollback + SM-04 L3 trigger 全 PASS | regression fail → 重 IMPL 對應 sub-task |

**T1+T2+T3+T6 可 4-way parallel**；T4+T5 待 T2/T1 完；T7 final。

**E2 重點審查 3 點**（PA 已標 in AMD-2026-05-09-03 §7）：
1. `shadow_mode` legacy `false` 配 `canary_stage=0` 的組合必 reject；`shadow_mode_provider` exception path 仍 fail-closed 至 Stage 0（不是 Stage 1）— `_read_shadow_mode` invariant，break 即雞蛋死循環復活
2. `canary_stage_log.decision_lease_id` for `manual_promote` 必填的 NOT NULL constraint 在 PG 層強制（不只 application 層）
3. healthcheck `[58]` 對 SM-04 ≥ L3 escalate 必 hard FAIL → 觸 stage = 0 rollback；不可降為 WARN

### 2.3 W-AUDIT-6 Mid-Ground 細部派工（保 6 子項）

| Sub-task | Owner | Person-day | Files:Line | Sprint slot | Acceptance |
|---|---|---:|---|---|---|
| **保-1：ma_crossover 結構性重寫** | E1-E | 2 | `rust/openclaw_engine/src/strategies/ma_crossover/strategy_impl.rs` (R:R 已 IMPL ✅，補 結構性 audit) + tests | Sprint N+0 | tests PASS + QC R:R 數學審計 PASS |
| **保-2：bb_breakout 5m timeframe sweep** | E1-E | 1.5 | `rust/openclaw_engine/src/strategies/bb_breakout/runtime_params.rs` + 5m vs 1m timeframe sweep param | Sprint N+0 | sweep result 持久化 + 5m baseline DSR/PBO 跑得起 |
| **保-3：bb_reversion 配 ma pair** | E1-E | 1 | `rust/openclaw_engine/src/strategies/bb_reversion/mod.rs` 加 ma pair entry filter | Sprint N+0 | bb_reversion + ma_crossover combine test PASS |
| **保-4：Kelly tier config 化** | E1-E | 1 | `rust/openclaw_engine/src/ml/kelly_sizer.rs` 加 `KellyTierConfig` from `risk_config.kelly` + 4 risk_config*.toml schema 加 [kelly.tier_thresholds] | Sprint N+0 | tier_thresholds hot-reload PASS + tests PASS |
| **保-5：funding_arb retire (done ✅)** | - | 0 | ADR-0018 已落地 + risk_config 4 TOML cleaned | done | done |
| **保-6：DSR/PBO wired (done ✅)** | - | 0 | V079 已 land | done | done |

**砍 6 子項明確不在 scope**（避免動到）：
- ❌ OU σ sweep
- ❌ EWMA λ sweep
- ❌ Kelly sub-fraction sweep
- ❌ fast_track 15%/5%+3σ threshold sweep
- ❌ per-strategy cost_gate threshold sweep
- ❌ 個別 strategy hardcoded magic number patch

**E2 必查**：grep diff 確認 `OU_sigma\|EWMA_lambda\|kelly_sub_fraction\|fast_track_threshold\|per_strategy_cost_gate\|hardcoded_magic` 字面 0 命中。

### 2.4 A 群 — Alpha 升級 3 候選新策略

| Sub-task | Owner | Person-day | Files | Sprint | Acceptance | Failure fallback |
|---|---|---:|---|---|---|---|
| **A4-C BTC→Alt Lead-Lag SPEC** | PA + QC + MIT | 3 | `docs/execution_plan/2026-05-XX--a4_c_btc_alt_lead_lag_spec.md` | Sprint N+1 | QC 數學審計 PASS（ρ60s>0.7 假設可測 / 1.5σ 急動定義 leak-free / 90-180s time-based 退場 sample-size 足）+ MIT data feasibility PASS | spec fail → push back operator 改順序 |
| **A4-C IMPL** | E1 + QC review | 7 | 新策略 mod `rust/openclaw_engine/src/strategies/btc_alt_lead_lag/` + AlphaSurface CrossAsset tag 消費 + tests | Sprint N+2 | demo n ≥ 30 entry / gross > 0 / DSR > 0 跑 7d PASS | gross < 0 跑 7d → 不 IMPL Stage 2 cohort 直接退役 |
| **A4-B Liquidation Cluster Reaction SPEC** | PA + QC + MIT | 3 | `docs/execution_plan/2026-05-XX--a4_b_liquidation_cluster_spec.md` | Sprint N+2 | QC 數學審計 PASS（cluster_score 公式 leak-free + cluster threshold sample-size 足）+ Phase C liquidation_pulse populate 確認 | 同 A4-C |
| **A4-B IMPL** | E1 + QC review | 7 | 新策略 mod `rust/openclaw_engine/src/strategies/liquidation_cluster/` + AlphaSurface LiquidationCascade tag 消費 + tests | Sprint N+3 | 同 A4-C | 同 A4-C |
| **A4-A Funding Skew Directional SPEC** | PA + QC | 3 | `docs/execution_plan/2026-05-XX--a4_a_funding_skew_directional_spec.md` | Sprint N+3 | QC 數學審計 PASS（demo signal noise 高，需 explicit signal-to-noise 估算）+ Phase B funding_curve panel populate 確認 | 同 A4-C |
| **A4-A IMPL** | E1 + QC review | 7 | 新策略 mod `rust/openclaw_engine/src/strategies/funding_skew_directional/` + AlphaSurface FundingSkew tag 消費 + tests | Sprint N+4 | 同 A4-C | 同 A4-C |

**E2 重點審查 3 點**（每個新策略）：
1. `declared_alpha_sources()` 與策略真實邏輯對齊（不 declare 後不消費）
2. `requires_spot_capability` flag for Basis 策略（A4-A 不需要，但 future basis arb 需要）
3. demo evidence sample-size ≥ 30 entry 才能進 Stage 2（與 W-AUDIT-9 acceptance 對齊）

### 2.5 B 群 — ML Pipeline 三道斷層

| Sub-task | Owner | Person-day | Files | Sprint | Acceptance | Failure fallback |
|---|---|---:|---|---|---|---|
| **A5-M1 decision_features producer 改 intent-only emit** | E1-D + MIT review | 5 | `rust/openclaw_engine/src/database/decision_feature_writer.rs` 改 intent-only emit + V0XX migration 拆 evaluation 表 + Python 上游 `intent_emitter.py` schema | Sprint N+0 | intent-only emit 24h INSERT 量 vs 舊 evaluation+intent 混合 ratio ≥ 80% drop（純 evaluation row 不再 INSERT decision_features） + evaluation 拆表 schema test PASS | schema break → backward-compat dual-write 1 week 後 cutover |
| **A5-M2 Fill writer entry_context_id INSERT trigger** | E1-D 後段 | 2.5 | `rust/openclaw_engine/src/database/fill_writer.rs` 加 entry_context_id 寫入 + V0XX trigger migration | Sprint N+0 | 24h fill writer entry_context_id 非 NULL ratio ≥ 95% | trigger 性能 → app 層補寫 |
| **A5-M3 Governance reject 寫 negative label + class weight handling** | E1-D 後段 | 5 | `rust/openclaw_engine/src/governance_core.rs` reject path 加 negative label INSERT + ML class_weight handling in `program_code/ml_training/label_generator.py` | Sprint N+0 | reject 24h 寫 negative label 非空 / class_weight balanced ratio PASS | label imbalance → SMOTE 或 weighted loss |

**E2 重點審查 3 點**：
1. `decision_features` intent-only emit 不漏 evaluation row 的關鍵欄位（PA-RFC v2 verify drift）
2. `entry_context_id` INSERT trigger 性能（PG hot path，不阻塞 fill_writer）
3. Negative label class_weight 防 imbalance（MIT must-review）

### 2.6 C 群 — Promotion + Dormant Unlock

| Sub-task | Owner | Person-day | Files | Sprint | Acceptance | Failure fallback |
|---|---|---:|---|---|---|---|
| **C-A6 DSR/PBO/CPCV evidence pipeline 自動化 + trial_sharpes 持久化** | E1-D 後段 | 5 | `program_code/ml_training/promotion_evidence.py` + V079 已 land + cron install | Sprint N+0 | DSR/PBO query 跑得起 + trial_sharpes 24h 持久化 row ≥ 100 + cron `0 * * * *` active | cron install fail → operator 手動 cron 安裝 + healthcheck `[40]` PASS |
| **C-D-05-wire `set_promotion_pipeline()` singleton init** | E1-E 後段 | 0.5 | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring.py` 加 `set_promotion_pipeline(promotion_gate_singleton)` | Sprint N+0 | strategy_wiring 加 row 顯式登記 + singleton 表 sync | wire site 衝突 → 改 sibling |
| **D-02 Layer 2 manual 7d 試運行** | operator 自決 | 0 | FA SOP 內含 | operator 自決 | operator 自決 | operator 自決 |

### 2.7 D 群 — Architectural Wave

| Sub-task | Owner | Sprint | 狀態 |
|---|---|---|:---:|
| **W-AUDIT-8a Alpha Surface Foundation** | E1 主 IMPL | Sprint N+0..N+2 (4 phase × 10 person-day) | SPEC PHASE done @ commit `c13c811e` |
| **W-AUDIT-9 Graduated Canary IMPL** | E1-A..E1-G | Sprint N+0..N+1 (1.5-2 sprint × 7 sub-task) | SPEC done via AMD-2026-05-09-03 |
| **W-AUDIT-8e (R-2) Strategist Alpha Source Orchestrator** | PA + FA + QC | Sprint N+3 SPEC + N+4 IMPL | defer 8a Phase A done |
| **W-AUDIT-8f (R-3) Hypothesis Pipeline first-class（含 W-AUDIT-4 併入）** | PA + MIT + FA | Sprint N+4 SPEC + N+5 IMPL | defer 8a Phase B done + Decision-3 confirmed |
| **W-AUDIT-8g (R-4) Per-alpha-source Live Promotion Gate** | PA + FA + QC | Sprint N+5 SPEC + N+6+ IMPL | defer 後期 |
| **W-AUDIT-10 (R-5) Spec-as-Code + Module Lifecycle SM** | PA + TW | Sprint N+5 SPEC + N+6+ IMPL | 中期 |

### 2.8 E 群 — Dispatch 拍板

| Sub-task | 狀態 |
|---|:---:|
| **A2-followup G3-08 OPENCLAW_H_STATE_GATEWAY=1 enable**（ops 並行）| Sprint N+0 done（ops 並行執行）|
| **Decision-2 W-AUDIT-6 mid-ground**（已上）| Sprint N+0 dispatch |
| **Decision-3 W-AUDIT-4 併入 R-3 (W-AUDIT-8f) confirmed** | Sprint N+4 SPEC |

---

## §3 Critical Path + 並行 Conflict 分析

### 3.1 Longest path（最早 supervised live milestone）

```
Sprint N+0 → N+1 → N+2 → N+3 → N+4 → N+5
W-AUDIT-9 T1+T2 → T3+T4 → T5+T6 → T7 (Stage 1 active)
                ↓
W-AUDIT-8a Phase A → Phase B+C → Phase D → A4-C IMPL → A4-B IMPL → A4-A IMPL
                                                                          ↓
                                                W-AUDIT-9 Stage 2 → Stage 3 → Stage 4 (per-alpha-source live)
                                                                                  ↑
                                                                R-3 Hypothesis Pipeline → first per-alpha-source supervised live
```

**Critical path total**：~12 weeks（6 sprint × 2 weeks per sprint）對應 first per-alpha-source supervised live milestone。

**Critical path 限制因素**：
1. W-AUDIT-9 Stage 1 必觀察 7d（不可壓縮）
2. W-AUDIT-9 Stage 2 必觀察 14d（不可壓縮）
3. W-AUDIT-9 Stage 3 必觀察 21d（不可壓縮）
4. W-AUDIT-8a Phase A → B+C → D 串行（不可並行 phase A/D）

**最早 supervised live 重定義**：~2026-08-01 ± 2 weeks（Sprint N+5 結束點，event-driven），不是 hard date。

### 3.2 E1 capacity bottleneck 分析

| Sprint | E1-A | E1-B | E1-C | E1-D | E1-E | Capacity util |
|---|---|---|---|---|---|---:|
| N+0 | W-AUDIT-9 T1+T3+T6 | W-AUDIT-9 T2+T4 | 8a Phase A | B-M1+B-M2+B-M3 | W-AUDIT-6 mid-G + C-A6+D-05 | **5/5 HOT** |
| N+1 | 8a Phase B | 8a Phase C | A4-C SPEC | W-AUDIT-9 T7 | reserved catch-up | **4/5** |
| N+2 | A4-C IMPL | 8a Phase D | A4-B SPEC | W-AUDIT-9 Stage 2 ops | catch-up + W-AUDIT-2/-5 | **5/5 HOT** |
| N+3 | A4-B IMPL | R-2 8e SPEC | A4-A SPEC | W-AUDIT-9 Stage 3 ops | catch-up | **4/5** |
| N+4 | R-3 8f SPEC | A4-A IMPL | 8e IMPL | Stage 3 obs | catch-up | **4/5** |
| N+5 | 8f IMPL pt1 | 8f IMPL pt2 | R-4 8g SPEC | first per-alpha live ops | R-5 W-AUDIT-10 SPEC | **5/5 HOT** |

**Bottleneck Sprint**：N+0 + N+2 + N+5 三 sprint E1 capacity 5/5 HOT，無 catch-up slot。

**Mitigation**：
- N+0：W-AUDIT-9 7 sub-task 中 T1+T2+T3+T6 4-way 並行壓縮，T4+T5 後置 N+1；W-AUDIT-6 mid-G 6 子項與 8a Phase A 序列化避 file overlap
- N+2：Phase D 串行 5 策略 callsite migration（單 E1）+ A4-C IMPL 並行
- N+5：8f IMPL 拆兩 E1 並行（schema part + state machine part）

### 3.3 跨 Wave 共用代碼衝突

#### 衝突 1：W-AUDIT-8a Phase A migration 與 W-AUDIT-6 mid-ground 5 策略改動同 file overlap

**衝突 file**：
- `rust/openclaw_engine/src/strategies/bb_breakout/mod.rs`
- `rust/openclaw_engine/src/strategies/ma_crossover/strategy_impl.rs`
- `rust/openclaw_engine/src/strategies/bb_reversion/mod.rs`
- `rust/openclaw_engine/src/strategies/grid_trading/`（grid_helpers.rs 不在 6 子項 scope）
- `rust/openclaw_engine/src/strategies/funding_arb.rs`（已 retire 不動）

**衝突性質**：
- W-AUDIT-6 mid-G 5 策略 minimum 改動（保-2 bb_breakout 5m sweep / 保-3 bb_reversion 配 ma pair / 保-1 ma_crossover R:R audit）
- W-AUDIT-8a Phase A trait 升級需在每個策略 impl Strategy trait 加 `declared_alpha_sources()` + `on_tick(ctx, surface)` 簽名

**解決方案**：**Sprint N+0 序列化先 6 mid-G 後 8a Phase A**（Sprint N+0 W1 跑 W-AUDIT-6 mid-G + W2 跑 8a Phase A）。**禁止並行**。

**E2 必查**：merge 順序 `git log --oneline rust/openclaw_engine/src/strategies/` 確認 W-AUDIT-6 mid-G commit 早於 W-AUDIT-8a Phase A commit。

#### 衝突 2：W-AUDIT-9 T3 `shadow_mode_provider` stage-aware 與 ExecutorAgent shadow_mode 接線

**衝突 file**：
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_config_cache.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_agent.py:_read_shadow_mode`

**衝突性質**：T3 升級 `_read_shadow_mode` 為 stage-aware 後與 v2 已 close 的「lambda:True 已移除 + IPC fail-closed」邏輯需保 backward compat。

**解決方案**：T3 升級時先 grep `_read_shadow_mode` 所有 callsite + 改 stage-aware logic 但 exception path 仍 fail-closed Stage 0（不是 Stage 1）。**E2 必查 invariant**：exception path 任一漏判即雞蛋死循環復活。

#### 衝突 3：W-AUDIT-8a Phase B + C 與 W-AUDIT-5 性能 wave 同 `tick_pipeline/mod.rs`

**衝突 file**：`rust/openclaw_engine/src/tick_pipeline/mod.rs`（已 800+ 行）

**衝突性質**：
- W-AUDIT-8a Phase B + C 加 IPC slot（FundingCurveProvider / OIDeltaProvider / LiquidationPulseProvider）→ tick_pipeline/mod.rs LOC 增 ~200 行
- W-AUDIT-5 性能 wave 可能 split tick_pipeline/mod.rs

**解決方案**：Sprint N+1 W-AUDIT-5 split 必先 Phase B + C，或 W-AUDIT-5 split 延後到 Sprint N+2 Phase D 後。

**Pre-existing baseline exception clause**（CLAUDE.md §九）：tick_pipeline/mod.rs baseline > 800 但 < 2000，加 200 行進入 ~1000 仍 < 2000 hard cap，可接受。

#### 衝突 4：A 群 3 新策略與 W-AUDIT-9 Stage 1 cohort 選擇

**衝突性質**：W-AUDIT-9 Stage 1 cohort 必為 1 strategy × 1 symbol。A4-A/B/C IMPL 後新策略候選會與既存 5 策略一起進 cohort 候選池。

**解決方案**：operator 在 Settings tab 顯式拍板 cohort 選擇，不由 system auto-pick。Sprint N+1 Stage 1 cohort 必選**既存 5 策略中的最 mature 一個**（不選新 IMPL 策略，因新策略無 demo evidence sample）。Sprint N+3 Stage 2 進 demo 後，A4-C IMPL 已 land 且有 demo n ≥ 30 evidence，可作 Stage 2 cohort 候選。

### 3.4 Risk Mitigation 表

| Risk | 觸發條件 | Mitigation | Fallback |
|---|---|---|---|
| W-AUDIT-8a Phase A E2E byte-diff fail | 5 策略 stdout fingerprint 任一 bit 變 | rollback Phase A patch + PA 重設計 dispatch 邏輯 | 不進 Phase B+C，降 priority 重新評估 |
| W-AUDIT-9 T3 stage-aware exception path 漏判 | E2 review 發現 Stage 1 fall-back | reject merge + 重 IMPL exception path | T3 延後 1 sprint，operator IPC CLI 觸發 |
| Phase B/C collector 寫 PG 過大 | retention policy 1 week 即觸發 disk 警報 | 降 refresh 30s → 60s | retention 降 14d → 7d |
| Bybit allLiquidation rate-limit | Phase C 24h 收 rate-limit error > 0 | 降為 per-symbol liquidation 訂閱 | Phase C liquidation_pulse 從 PG 讀 historical（非 real-time）|
| A 群 3 新策略 demo gross < 0 | demo n ≥ 30 後 gross < 0 | 不進 Stage 2 直接退役（按 ADR-0018 funding_arb 退役模式）| FA push back evaluation period 延長到 60d |
| W-AUDIT-9 Stage 2/3 rollback trip | demo 損失達閾值 | auto-rollback Stage 0 + incident log | operator 手動拍板修正 |
| First per-alpha-source supervised live 觸 SM-04 L3 | live 期間 SM-04 escalate | auto-rollback Stage 0 + cancel_token shutdown | operator + post-mortem |

---

## §4 W-AUDIT-6 Mid-Ground 細部派工（具體 file:line + sprint slot）

### 4.1 保 6 子項 file:line 對應

| 保 # | 子項 | File | Line range | Sprint slot | E1 owner | Person-day |
|---|---|---|---:|---|---|---:|
| 保-1 | ma_crossover 結構性重寫 (R:R 已 IMPL ✅補 audit) | `rust/openclaw_engine/src/strategies/ma_crossover/strategy_impl.rs` | 全 file (audit only) | Sprint N+0 W1 | E1-E | 2 |
| 保-2 | bb_breakout 5m timeframe sweep | `rust/openclaw_engine/src/strategies/bb_breakout/runtime_params.rs` | sweep param block | Sprint N+0 W1 | E1-E | 1.5 |
| 保-3 | bb_reversion 配 ma pair | `rust/openclaw_engine/src/strategies/bb_reversion/mod.rs` | entry filter section | Sprint N+0 W1 | E1-E | 1 |
| 保-4 | Kelly tier config 化 | `rust/openclaw_engine/src/ml/kelly_sizer.rs` + `settings/risk_control_rules/risk_config_*.toml` × 4 | KellyTierConfig struct + [kelly.tier_thresholds] block | Sprint N+0 W2 | E1-E | 1 |
| 保-5 | funding_arb retire | (done ✅ ADR-0018 + 4 risk_config*.toml cleaned) | - | done | - | 0 |
| 保-6 | DSR/PBO wired | (done ✅ V079 land) | - | done | - | 0 |

**E1-E Sprint N+0 total**：2 + 1.5 + 1 + 1 = **5.5 person-day**（剩 ~4.5 day for catch-up + C-A6 後段 + D-05-wire）

### 4.2 砍 6 子項明確不在 scope

| 砍 # | 子項 | File 不動 | Reason |
|---|---|---|---|
| 砍-1 | OU σ sweep | `rust/openclaw_engine/src/strategies/ma_crossover/`（不動 OU 參數）| L2 reach 不到的 polishing |
| 砍-2 | EWMA λ sweep | `rust/openclaw_engine/src/indicators/`（不動 EWMA）| 同上 |
| 砍-3 | Kelly sub-fraction sweep | `rust/openclaw_engine/src/ml/kelly_sizer.rs`（只 tier config 化，不 sub-fraction sweep）| 同上 |
| 砍-4 | fast_track 15%/5%+3σ threshold sweep | `rust/openclaw_engine/src/risk/fast_track.rs`（不動）| 同上 |
| 砍-5 | per-strategy cost_gate threshold sweep | `settings/risk_control_rules/risk_config_*.toml`（cost_gate 不 per-strategy override）| 同上 |
| 砍-6 | 個別 strategy hardcoded magic number patch | 所有 strategies/*.rs（不 patch magic number）| 同上 |

**E2 必查**：grep 確認 PR diff 中以下字面 0 命中：
```bash
grep -rE "(ou_sigma|ewma_lambda|kelly_sub_fraction|fast_track_threshold|per_strategy_cost_gate|hardcoded_magic_number)" <diff>
```
任一命中 = 砍項被誤動，reject merge。

---

## §5 W-AUDIT-8f (R-3) Hypothesis Pipeline 含 W-AUDIT-4 併入詳細 Schema 設計

### 5.1 `learning.hypotheses` table state machine（PG schema）

```sql
-- V0XX: Hypothesis Pipeline first-class governance object
-- 對應 PA report Layer 3.4 + AMD-2026-05-09-03 §5.4 W-AUDIT-4 併入 R-3

CREATE TABLE IF NOT EXISTS learning.hypotheses (
    hypothesis_id        TEXT        PRIMARY KEY,           -- e.g. 'hyp-funding-skew-001'
    state                TEXT        NOT NULL DEFAULT 'DRAFT'
        CHECK (state IN ('DRAFT', 'REGISTERED', 'EXPERIMENTING', 'EVIDENCE_GATE', 'PROMOTED', 'REJECTED', 'EXPIRED')),
    proposer             TEXT        NOT NULL                -- 'strategist' | 'analyst' | 'operator'
        CHECK (proposer IN ('strategist', 'analyst', 'operator')),
    statement            TEXT        NOT NULL,               -- 「ranging regime + funding > 0.05% → spread alpha」
    null_hypothesis      TEXT        NOT NULL,               -- 「funding > 0.05% 對 ranging 無 effect」
    alpha_source_tag     TEXT        NOT NULL,               -- AlphaSourceTag SoT (lowercase snake_case)
    evidence_required    JSONB       NOT NULL,               -- {n_samples_min: 30, dsr_min: 0.5, pbo_max: 0.3}
    experiment_target    JSONB       NOT NULL,               -- {cohort: ..., paper_engine: ..., timeframe: ...}
    verdict              JSONB,                              -- nullable; PROMOTED/REJECTED 必填
    audit_chain          JSONB[]     NOT NULL DEFAULT '{}',  -- [{ts, action, actor, ...}]
    originating_lease_id TEXT,                                -- nullable; for AI-proposed
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    state_updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at           TIMESTAMPTZ                         -- nullable; EVIDENCE_GATE 後 auto-expire
);

CREATE INDEX IF NOT EXISTS idx_hypotheses_state_proposer
    ON learning.hypotheses (state, proposer);
CREATE INDEX IF NOT EXISTS idx_hypotheses_alpha_source
    ON learning.hypotheses (alpha_source_tag, state);
CREATE INDEX IF NOT EXISTS idx_hypotheses_state_expiry
    ON learning.hypotheses (state, expires_at)
    WHERE expires_at IS NOT NULL;
```

**state machine transitions**（state machine 形式化）：
```
DRAFT          → REGISTERED       (Analyst review pass)
REGISTERED     → EXPERIMENTING    (operator manual trigger or auto-dispatch from Strategist)
EXPERIMENTING  → EVIDENCE_GATE    (n_samples_min reached)
EVIDENCE_GATE  → PROMOTED         (DSR/PBO PASS + manual sign-off)
EVIDENCE_GATE  → REJECTED         (DSR/PBO FAIL OR manual veto)
EXPERIMENTING  → EXPIRED          (timeout without evidence)
EVIDENCE_GATE  → EXPIRED          (manual review timeout)
```

### 5.2 W-AUDIT-4 6 表 dead schema 如何 wire 進 Hypothesis Pipeline

W-AUDIT-4 ML 基座 6 表（v2 verification §6 P1）：
1. `learning.feature_baselines`（0 row）
2. `learning.drift_events`（0 row）
3. `learning.outcome_features`（0 row, sparse INSERT）
4. `learning.attribution_chain`（0.5% ok ratio）
5. `learning.calibration_sets`（0 row）
6. `learning.label_distributions`（0 row）

**併入策略**：每筆 hypothesis 自動 link 到 6 表的相關 row，使 6 表「有 caller」即「有 hypothesis 來解釋」。

| 表 | wire 進 hypothesis pipeline 方式 |
|---|---|
| `learning.feature_baselines` | 加 column `hypothesis_id` FK to `learning.hypotheses` + 每 hypothesis EVIDENCE_GATE 時 snapshot baseline |
| `learning.drift_events` | 加 column `hypothesis_id` FK；drift detector run 時對 hypothesis active cohort 寫 row |
| `learning.outcome_features` | 加 column `hypothesis_id` FK；fill writer 寫 fill 時 join hypothesis_id → 補 row |
| `learning.attribution_chain` | 加 column `hypothesis_id` FK；attribution rewire base on hypothesis_id（不再從 fill 拼湊）|
| `learning.calibration_sets` | 加 column `hypothesis_id` FK；hypothesis EVIDENCE_GATE 時觸發 calibration |
| `learning.label_distributions` | 加 column `hypothesis_id` FK；class_weight handling 對 hypothesis label 計算 distribution |

**Sprint N+5 W-AUDIT-8f IMPL 包含**：
1. `V0XX__hypothesis_pipeline.sql` 建 `learning.hypotheses` 表
2. `V0XX__w_audit4_hypothesis_link.sql` 6 表 ALTER ADD COLUMN hypothesis_id
3. `program_code/ml_training/hypothesis_pipeline.py` Python state machine（state transition + validate logic）
4. `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub.py` 加 `acquire_hypothesis_lease()` for AI-proposed hypothesis
5. `rust/openclaw_engine/src/database/decision_lease_writer.rs` 加 `originating_hypothesis_id` propagate
6. `rust/openclaw_engine/src/database/fill_writer.rs` 加 hypothesis_id propagate
7. `rust/openclaw_engine/src/database/decision_feature_writer.rs` 加 hypothesis_id propagate
8. `program_code/ml_training/attribution_chain_writer.py` rewire base on hypothesis_id

### 5.3 Decision Lease + Hypothesis 關係

```
Hypothesis (long-lived governance object, days to weeks)
    └─→ originates Decision Lease (per-intent, 0.1-300s TTL)
            └─→ ExecutionPlan (single intent execution)
                    └─→ Fill (single fill row)
                            └─→ outcome_features / attribution_chain (link back to hypothesis)
```

**新加 column**：
- `governance.decision_lease_log.originating_hypothesis_id` (TEXT NULLABLE FK to `learning.hypotheses`)
- `replay.simulated_fills.hypothesis_id` (TEXT NULLABLE FK)
- `trading.fills.hypothesis_id` (TEXT NULLABLE FK)
- `learning.outcome_features.hypothesis_id` (TEXT NULLABLE FK + index)

### 5.4 Attribution chain 從 0.5% 拉到 80%+ 的 dependency 鏈

**當前 0.5% 根因**（v2 verification）：
1. mlde_demo_applier filter 對 NULL context_id row drop
2. 6 表 0 INSERT path 接線
3. 5 ML 訓練腳本 cron 0 install
4. **沒有 hypothesis 來歸因** = attribution 無對象

**dependency 鏈拉到 80%+**：

```
Step 1 (Sprint N+0): B 群 ML 三斷層 IMPL
    A5-M1 intent-only emit → decision_features 不再被 evaluation row 污染
    A5-M2 entry_context_id INSERT trigger → fill writer 100% 寫 entry_context_id
    A5-M3 negative label + class_weight → governance reject 也歸因
    → attribution_chain_ok 從 0.5% → ~30%（M2/M3 直接拉）

Step 2 (Sprint N+0): C-A6 + D-05-wire
    DSR/PBO/CPCV pipeline 自動化 + cron install → 5 ML 腳本跑得起
    → attribution_chain_ok ~30% → ~50%

Step 3 (Sprint N+5): W-AUDIT-8f IMPL
    Hypothesis Pipeline first-class → 每筆 fill 帶 originating_hypothesis_id
    6 表 ALTER ADD COLUMN hypothesis_id → 6 表 INSERT path 接線
    attribution_chain rewire base on hypothesis_id → trivial join
    → attribution_chain_ok ~50% → ~80%+

Step 4 (Sprint N+6+, post-supervised live): Continuous improvement
    actively 執行的 hypothesis 增多 → attribution_chain_ok ratio 自然上升
    → 最終 ~95%+
```

**healthcheck `[42b]` settled eligible strategies ratio**（current 1.000）對齊：每 hypothesis EVIDENCE_GATE 時必須 attribution_chain_ok ratio ≥ 0.7（W-AUDIT-9 Stage 3 acceptance 之一）。

---

## §6 Sign-off Pre-flight Checklist（11 invariant）

PM Sign-off 前必驗證以下 11 條 invariant，逐條 PASS 才能拍板：

### 6.1 結構 invariant（4 條）

| # | Invariant | 驗證方式 | 失敗 = |
|---|---|---|:---:|
| 1 | Sprint N+0 W-AUDIT-9 7 sub-task 全 land | `git log --grep="W-AUDIT-9"` 7 commit + `[58]` PASS | BLOCKER |
| 2 | Sprint N+0 W-AUDIT-8a Phase A trait 升級 land + 5 策略 byte-identical replay PASS | E2E byte-diff test PASS + `cargo build --release` 綠 | BLOCKER |
| 3 | W-AUDIT-6 mid-ground 6 子項 land + 砍 6 子項未動 | grep 6 子項砍項 0 命中 + 6 保項 commit 存在 | BLOCKER |
| 4 | W-AUDIT-9 Stage 1 cohort active + Stage 1 7d wall-clock 觀察期未提前升級 | `governance.canary_stage_log` Stage 1 entered_at_ms + auto-promote 條件未提前觸 | BLOCKER |

### 6.2 安全 invariant（4 條）

| # | Invariant | 驗證方式 | 失敗 = |
|---|---|---|:---:|
| 5 | DOC-08 §12 9 條安全不變量未違反 | 逐條 grep + healthcheck pass | BLOCKER |
| 6 | live boundary 5-gate 在所有 stage active 期間未被繞過 | LiveDemo authorization.json 簽名+TTL+env_allowed 全 pass | BLOCKER |
| 7 | §二 16 根原則合規（ESPECIALLY 原則 1/4/5/6/9）| 逐條 grep + 引用 AMD-2026-05-09-03 §6.3 校核 | BLOCKER |
| 8 | `shadow_mode_provider` exception path fail-closed Stage 0（不是 Stage 1）| E2 review T3 + unit test PASS | BLOCKER |

### 6.3 治理 invariant（3 條）

| # | Invariant | 驗證方式 | 失敗 = |
|---|---|---|:---:|
| 9 | `canary_stage_log.decision_lease_id` for `manual_promote` PG 層 NOT NULL 強制 | V0XX migration 含 `CHECK (transition_kind != 'manual_promote' OR decision_lease_id IS NOT NULL)` | BLOCKER |
| 10 | healthcheck `[58]` 對 SM-04 ≥ L3 escalate 必 hard FAIL → 觸 stage = 0 rollback | `[58]` IMPL 對 SM-04 L3 邏輯 explicit + unit test PASS | BLOCKER |
| 11 | A 群 3 新策略 IMPL 後 `declared_alpha_sources()` 與真實邏輯對齊 | grep 3 新策略 ctor + QC review report sign-off | BLOCKER |

### 6.4 PM Sign-off 操作流程

1. PM 拿到 Sprint N+0 milestone report 後逐條跑 11 invariant
2. 對每條 invariant 寫驗證 evidence（commit hash / test output / healthcheck PASS log）
3. 任一 invariant FAIL → BLOCK Sprint N+0 closure → push back 對應 E1
4. 全部 11 PASS → PM Sign-off → 進 Sprint N+1
5. Sprint N+0 closure 後 PA 同步更新 CLAUDE.md §三 + memory + workspace report

### 6.5 git status clean 強制（CLAUDE.md §七 P0-GOV-3）

PM Sign-off 前必跑：
```bash
git status --porcelain
```
對應檔案必 clean（不能有 staged/untracked 對應的代碼/測試檔）。違反 = PM 拒絕 sign-off。

---

## §7 跨平台合規（CLAUDE.md §七 ★★）

本 plan 所有 IMPL 必符合：

1. **路徑不硬編碼**：所有路徑用 `OPENCLAW_BASE_DIR` / `OPENCLAW_DATA_DIR` 等 env var
2. **依賴管理乾淨**：新 import 同步更新 `requirements.txt`
3. **Linux PG dry-run mandatory**（V### migration 涉 PG reflection 函數時）：先 PM 端 Linux PG empirical query 驗，再 dispatch E1 IMPL（CLAUDE.md §七 V055 5-round loop 教訓）
4. **Mac dev 必跑 pytest** 後 Linux operator deploy
5. **三環境風控 config 獨立**：4 個 risk_config*.toml 故意分開，禁「純衛生」合併

E2 必查：`grep -E '(/home/ncyu|/Users/[^/]+)' <diff>` 命中 → reject merge。

---

## §8 接收後動作（PM 派發）

PM 拿到本 plan + Operator sign-off 後：

1. **Sprint N+0 W1（Day 0-3）派發**：
   - `@E1 W-AUDIT-9 T1 Rust schema 升級`（並行 `@QC` enum review）
   - `@E1 W-AUDIT-9 T2 V### migration`（並行 `@MIT` review）
   - `@E1 W-AUDIT-9 T3 shadow_mode_provider stage-aware`
   - `@E1 W-AUDIT-9 T6 manual promote Decision Lease`
   - `@E1 W-AUDIT-6 mid-ground 6 子項`（並行 `@QC` 數學審計）
   - `@E1 B-M1 decision_features intent-only emit`（並行 `@MIT` review V### migration）
   - `@ops A2-followup G3-08 OPENCLAW_H_STATE_GATEWAY=1 enable`

2. **Sprint N+0 W1 結束（Day 3-5）E2 first-pass**：
   - `@E2` review T1+T2+W-AUDIT-6 mid-G + B-M1
   - `@E4` regression schema test

3. **Sprint N+0 W2 開始（Day 5-7）派發**：
   - `@E1 W-AUDIT-8a Phase A trait 升級`（W-AUDIT-6 mid-G done 後序列化開始）
   - `@E1 B-M2 entry_context_id trigger`
   - `@E1 B-M3 negative label + class weight`
   - `@E1 C-A6 DSR/PBO evidence pipeline`
   - `@E1 W-AUDIT-9 T4 healthcheck [58]`
   - `@E1 W-AUDIT-9 T5 GUI surface`

4. **Sprint N+0 W2 結束（Day 12-14）full E2/E4 review chain**：
   - `@E2` second-pass review T3+T4+T5+T6+8a Phase A+B-M2+B-M3+C-A6
   - `@E4` regression 5 stage transition + byte-diff E2E + B 群 schema + C-A6 DSR/PBO
   - `@QC` 5 策略數學審計 + AlphaSourceTag enum 完整性
   - `@MIT` V### migration row-rate 估算 + cron install
   - `@CC` Scout IPC schema preview（為 Phase D N+2）
   - `@BB` Bybit V5 levels 對齊 review（為 Phase C N+1）

5. **Sprint N+0 closure（Day 14-15）PM Sign-off 11 invariant**

6. **Sprint N+0 closure 後 PA 動作**：
   - 更新 CLAUDE.md §三：W-AUDIT-9 + W-AUDIT-8a Phase A 從 SPEC PHASE → ACTIVE BLOCKER 列入；6 mid-ground 加完成里程碑
   - PA memory.md 加 entry：dispatch plan 落地經驗 + 跨 wave conflict 處理教訓
   - 報告歸檔 + 結論性報告同步 Operator

---

## §9 結語

本 dispatch plan 是 4-agent loss audit + Operator 拍板 dispatch list 後的 engineering ground truth。**Critical insight**：

1. **Sprint N+0 是 highest-leverage**：解 W-AUDIT-9 雞蛋死循環 + 8a Phase A 開「未來新 alpha source 高速公路」 + B 群 ML 三斷層解 attribution 0.5% root cause + C 群 promotion + D-05-wire 解 5 策略 None evidence 卡 promotion gate — 這 5 個事是 architectural 級 forcing function 同步 install
2. **6 sprint 12 weeks 對 first per-alpha-source supervised live**：與 88 finding patch 估的 6-8 sprint 同數量級，但收斂可能性顯著高（不是修一條已知必虧路徑）
3. **W-AUDIT-9 5-stage canary** 是 fail-closed 哲學的 stage 化（不是放寬）+ rollback 永遠回 Stage 0 stricter，符合原則 #6
4. **W-AUDIT-8a Alpha Surface Foundation** 是「架構在主動激勵非 TA alpha」的 forcing function，不是「修 5 個 TA 策略」陷阱
5. **R-3 Hypothesis Pipeline 含 W-AUDIT-4 併入** 解 attribution_chain 0.5% root cause（不只是 SQL bug，是「沒有 hypothesis 來歸因」的必然）

**Push back 給 Operator**（最後一條）：本 plan Sprint N+0 滿載 5/5 E1，**任一 E1 故障 = 阻塞整 Sprint critical path**。建議 operator 預備 1 個 stand-by E1（即 6 並行 capacity，5 active + 1 stand-by），以防：
- W-AUDIT-9 T3 stage-aware exception path 翻車重 IMPL
- W-AUDIT-8a Phase A byte-diff fail 重 IMPL
- W-AUDIT-6 mid-ground 與 8a Phase A 序列化 deadline 撞牆

如不接受 stand-by，請 operator 顯式 sign-off 接受「Sprint N+0 5/5 HOT capacity 風險」。

---

**報告路徑**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_dispatch_engineering_plan.md`

**結論性報告同步至**：`srv/docs/CCAgentWorkSpace/Operator/`（PM 收到後處理）

**PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_dispatch_engineering_plan.md**
